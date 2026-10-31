"""Explicit bootstrap phases. Default is a plan of commands; --execute opts in.
Run phases 2/3 from a private-network operator session with bootstrap EKS permissions.
This is an operator bootstrap, not GitHub CD or an SSM deployment implementation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import time
from urllib.parse import urlparse
from datetime import datetime, timezone

import yaml
from environment import ROOT, SERVICES, command, environment_settings, generate, overlay, output, require, validate_contract, retained_secret_arns

CORE = ['vpc', 'nat', 's3', 'ecr', 'event-encryption', 'sqs', 'eventbridge', 'eks',
        'api-gateway-authorizer-secrets', 'api-gateway-authorizer', 'iam', 'apigateway-core', 'management', 'rds']
PHASES = {
    0: 'Verify caller, backend S3 bucket and DynamoDB lock table (read only).',
    1: 'Apply core stacks in order with interactive Terraform approval; excludes integration.',
    2: 'Platform operator: metrics/KEDA/CloudWatch, addons/ESO, secret initialization and sync, RBAC/SAs, transactional DB role bootstrap.',
    3: 'Gate ESO Secrets and completed DB bootstrap; migrate using scoped identities, then workloads.',
    4: 'Wait for unique tagged internal ALB, HTTP/80 listener and healthy target groups.',
    5: 'Repeat Phase 4 gate, then apply API Gateway integration using Terraform discovery.',
    6: 'Generate final contract; verify VPC Link, listener, target groups and integration URIs (read only).',
}


def run(args, cwd=None):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True, env={**os.environ, 'AWS_PAGER': '', 'TG_BACKEND_REQUIRE_BOOTSTRAP': 'true'})


def aws(c, *args):
    return json.loads(command(['aws', '--region', c['region'], *args, '--output', 'json']))


def wait_for(description, predicate, timeout=600, interval=5):
    deadline = time.monotonic() + timeout
    while True:
        result = predicate()
        if result:
            print(description + ': READY')
            return result
        if time.monotonic() >= deadline:
            raise TimeoutError(description + ': prerequisite not ready; rerun after resolving dependency')
        # Poll interval is not a correctness gate; only predicate success permits progress.
        time.sleep(interval)


def select_alb(candidates, c):
    matches = [lb for lb in candidates if all(lb.get('Tags', {}).get(k) == v for k, v in c['alb']['discoveryTags'].items())]
    require(len(matches) <= 1, 'Ambiguous ALB discovery: more than one tag match')
    if not matches: return None
    lb = matches[0]
    require(lb['VpcId'] == c['vpcId'] and lb['Scheme'] == 'internal' and lb['Type'] == 'application', 'ALB tags matched wrong VPC/scheme/type')
    require(c['alb']['frontendSecurityGroupId'] in lb['SecurityGroups'], 'ALB is missing Terraform-owned frontend SG')
    return lb if lb['State']['Code'] == 'active' else None


def select_listener(listeners):
    matches = [listener for listener in listeners if listener['Port'] == 80]
    require(len(matches) <= 1, 'Ambiguous listener discovery: more than one port-80 listener')
    if not matches: return None
    require(matches[0]['Protocol'] == 'HTTP', 'Expected HTTP listener on port 80')
    return matches[0]


def discover(c):
    def query():
        lbs = aws(c, 'elbv2', 'describe-load-balancers')['LoadBalancers']
        for start in range(0, len(lbs), 20):
            batch = lbs[start:start + 20]
            tags = aws(c, 'elbv2', 'describe-tags', '--resource-arns', *[lb['LoadBalancerArn'] for lb in batch])['TagDescriptions']
            by_arn = {d['ResourceArn']: {t['Key']: t['Value'] for t in d['Tags']} for d in tags}
            for lb in batch: lb['Tags'] = by_arn[lb['LoadBalancerArn']]
        return select_alb(lbs, c)
    lb = wait_for('Unique expected ALB', query)
    listener = wait_for('HTTP/80 listener', lambda: select_listener(aws(c, 'elbv2', 'describe-listeners', '--load-balancer-arn', lb['LoadBalancerArn'])['Listeners']))
    def targets_ready():
        groups = aws(c, 'elbv2', 'describe-target-groups', '--load-balancer-arn', lb['LoadBalancerArn'])['TargetGroups']
        if len(groups) != len(SERVICES): return False
        for group in groups:
            # LBC uses a sentinel group port for named Kubernetes targetPorts.
            # The registered target and health-check ports carry the real port.
            require(group['TargetType'] == 'ip' and group['Protocol'] == 'HTTP' and group['HealthCheckPath'] == '/health/ready', 'Unexpected target group contract')
            states = aws(c, 'elbv2', 'describe-target-health', '--target-group-arn', group['TargetGroupArn'])['TargetHealthDescriptions']
            require(all(s['Target']['Port'] == 8080 and s['HealthCheckPort'] == '8080' for s in states), 'Unexpected registered target port')
            if len(states) < 2 or any(s['TargetHealth']['State'] != 'healthy' for s in states): return False
        return True
    wait_for('Three target groups with at least two healthy targets each', targets_ready)
    return lb['LoadBalancerArn'], listener['ListenerArn']


def verify_cluster(c):
    cluster = wait_for('EKS ACTIVE', lambda: (cluster if (cluster := aws(c, 'eks', 'describe-cluster', '--name', c['clusterName'])['cluster'])['status'] == 'ACTIVE' else None))
    require(cluster['resourcesVpcConfig']['vpcId'] == c['vpcId'] and not cluster['resourcesVpcConfig']['endpointPublicAccess'], 'Wrong VPC or non-private EKS')
    for name in ('vpc-cni', 'kube-proxy', 'coredns', 'aws-ebs-csi-driver'):
        wait_for('EKS addon ' + name, lambda name=name: aws(c, 'eks', 'describe-addon', '--cluster-name', c['clusterName'], '--addon-name', name)['addon']['status'] == 'ACTIVE')
    groups = aws(c, 'eks', 'list-nodegroups', '--cluster-name', c['clusterName'])['nodegroups']
    require(len(groups) >= 2, 'Expected API and worker node groups')
    for group in groups:
        wait_for('Node group ' + group, lambda group=group: aws(c, 'eks', 'describe-nodegroup', '--cluster-name', c['clusterName'], '--nodegroup-name', group)['nodegroup']['status'] == 'ACTIVE')
    return cluster


def kube_context(c):
    cluster = verify_cluster(c)
    if os.environ.get('KUBECONFIG'):
        current = json.loads(command(['kubectl', 'config', 'view', '--minify', '--raw', '-o', 'json']))
        config = current['clusters'][0]['cluster']
        endpoint = urlparse(cluster['endpoint'])
        supplied = urlparse(config['server'])
        direct = config['server'] == cluster['endpoint']
        forwarded = (supplied.scheme == 'https' and supplied.hostname == '127.0.0.1'
                     and config.get('tls-server-name') == endpoint.hostname)
        require(direct or forwarded, 'kubectl context endpoint mismatch')
        require(not config.get('insecure-skip-tls-verify') and
                config.get('certificate-authority-data') == cluster['certificateAuthority']['data'],
                'kubectl must verify the exact EKS certificate authority')
        command(['kubectl', 'get', '--raw=/readyz'])
        return
    directory = ROOT / '.generated' / c['environment']
    kubeconfig = directory / 'kubeconfig'
    run(['aws', '--region', c['region'], 'eks', 'update-kubeconfig', '--name', c['clusterName'], '--kubeconfig', kubeconfig])
    os.environ['KUBECONFIG'] = str(kubeconfig)
    current = json.loads(command(['kubectl', 'config', 'view', '--minify', '-o', 'json']))
    require(current['clusters'][0]['cluster']['server'] == cluster['endpoint'], 'kubectl context endpoint mismatch')
    command(['kubectl', 'get', '--raw=/readyz'])


def addon_gate():
    for name in ('aws-load-balancer-controller', 'cluster-autoscaler'):
        run(['kubectl', '-n', 'kube-system', 'rollout', 'status', 'deployment/' + name, '--timeout=600s'])


def scaling_gate(c):
    addon = aws(c, 'eks', 'describe-addon', '--cluster-name', c['clusterName'], '--addon-name', 'vpc-cni')['addon']
    config = json.loads(addon.get('configurationValues', '{}'))
    require(config.get('enableNetworkPolicy') == 'true' and config.get('env', {}).get('NETWORK_POLICY_ENFORCING_MODE') == 'standard', 'VPC CNI policy enforcement missing')
    run(['kubectl','-n','kube-system','rollout','status','daemonset/aws-node','--timeout=600s'])
    for deployment in ('metrics-server','keda-operator','keda-operator-metrics-apiserver','keda-admission-webhooks'):
        run(['kubectl','-n','kube-system','rollout','status','deployment/'+deployment,'--timeout=600s'])
    for api in ('v1beta1.metrics.k8s.io','v1beta1.external.metrics.k8s.io'):
        run(['kubectl','wait','--for=condition=Available','apiservice/'+api,'--timeout=300s'])
    for crd in ('scaledobjects.keda.sh','triggerauthentications.keda.sh'):
        run(['kubectl','wait','--for=condition=Established','crd/'+crd,'--timeout=300s'])


def observability(c, install=False):
    version = 'v6.2.0-eksbuild.1'
    if install and 'amazon-cloudwatch-observability' not in aws(c, 'eks', 'list-addons', '--cluster-name', c['clusterName'])['addons']:
        versions = aws(c,'eks','describe-addon-versions','--addon-name','amazon-cloudwatch-observability','--kubernetes-version','1.35')['addons']
        require(any(v['addonVersion'] == version for a in versions for v in a['addonVersions']), 'Pinned CloudWatch addon unavailable for region/EKS 1.35; review pin, do not select latest')
        schema = json.loads(aws(c,'eks','describe-addon-configuration','--addon-name','amazon-cloudwatch-observability','--addon-version',version)['configurationSchema'])
        require(all(k in json.dumps(schema) for k in ('otelContainerInsights','applicationSignals','containerInsights')), 'CloudWatch configuration schema lacks reviewed controls')
        directory = ROOT / 'infra/live' / c['environment'] / 'observability'
        run(['terragrunt','init'],directory)
        run(['terragrunt','apply'],directory)
    wait_for('CloudWatch addon ACTIVE', lambda: aws(c,'eks','describe-addon','--cluster-name',c['clusterName'],'--addon-name','amazon-cloudwatch-observability')['addon']['status'] == 'ACTIVE')
    # v6.2.0's Helm merge drops service.telemetry and its operator forces host
    # networking. Preserve the generated pipelines and correct only the
    # singleton scraper's self-metrics port in the existing agent resource.
    scraper = json.loads(command(['kubectl', '-n', 'amazon-cloudwatch', 'get',
                                  'amazoncloudwatchagent', 'cloudwatch-agent-cluster-scraper', '-o', 'json']))
    config = yaml.safe_load(scraper['spec']['otelConfig'])
    metrics = config.setdefault('service', {}).setdefault('telemetry', {}).setdefault('metrics', {})
    metrics['readers'] = [{'pull': {'exporter': {'prometheus': {'host': 'localhost', 'port': 8889}}}}]
    run(['kubectl', '-n', 'amazon-cloudwatch', 'patch', 'amazoncloudwatchagent',
         'cloudwatch-agent-cluster-scraper', '--type=merge',
         '-p', json.dumps({'spec': {'hostNetwork': True, 'otelConfig': yaml.safe_dump(config)}})])
    # The generated ConfigMap changes without a pod-template checksum. Restart
    # the singleton collector so it binds the corrected port before waiting
    # for the node agent sharing that host's network namespace.
    run(['kubectl', '-n', 'amazon-cloudwatch', 'rollout', 'restart',
         'deployment/cloudwatch-agent-cluster-scraper'])
    for kind, name in (('daemonset','cloudwatch-agent'),('daemonset','fluent-bit'),('deployment','cloudwatch-agent-cluster-scraper'),('deployment','kube-state-metrics')):
        run(['kubectl','-n','amazon-cloudwatch','rollout','status',kind+'/'+name,'--timeout=600s'])


def images_overlay(path):
    require(path is not None, 'Phase 3 requires --images <digest-only YAML> (new R1-compatible builds)')
    data = yaml.safe_load(path.read_text())
    require(isinstance(data, dict) and set(data) == {'services'}, 'Images file must contain services only')
    require(set(data['services']) == set(SERVICES), 'Images file must cover exactly three services')
    import re
    for value in data['services'].values():
        require(set(value) == {'image'} and set(value['image']) == {'digest'}, 'Only image.digest overrides are allowed')
        require(re.fullmatch(r'sha256:[0-9a-f]{64}', value['image']['digest']), 'Invalid image digest')
    return data


def runtime_secret_gate(request_refresh=False):
    versions = {}
    names = [f'{service}-{purpose}-db' for service in SERVICES for purpose in ('runtime', 'migration')] + ['auth-jwt', 'gateway-trust', 'internal-trust', 'bootstrap-admin']
    for name in names:
        started = datetime.now(timezone.utc)
        if request_refresh:
            run(['kubectl','-n','apps','annotate','externalsecret',name,'force-sync='+str(time.time_ns()),'--overwrite'])
        def fresh():
            status = json.loads(command(['kubectl','-n','apps','get','externalsecret',name,'-o','json'])).get('status',{})
            ready = any(item.get('type')=='Ready' and item.get('status')=='True' for item in status.get('conditions',[]))
            refreshed = status.get('refreshTime')
            return ready and refreshed and (not request_refresh or
                datetime.fromisoformat(refreshed.replace('Z','+00:00')) >= started.replace(microsecond=0))
        wait_for('Fresh secret synchronization: '+name, fresh, timeout=300)
        # Only key names and resourceVersion leave kubectl, never base64 data.
        keys = command(['kubectl', '-n', 'apps', 'get', 'secret', name, '-o', 'go-template={{range $k,$v := .data}}{{$k}}{{"\\n"}}{{end}}']).splitlines()
        expected = {'username', 'password'} if name.endswith('-db') else ({'email','password'} if name == 'bootstrap-admin' else {'value'})
        require(expected.issubset(keys), 'Synced Secret missing required keys')
        versions[name] = command(['kubectl', '-n', 'apps', 'get', 'secret', name, '-o', 'jsonpath={.metadata.resourceVersion}']).strip()
    return versions


def database_marker(versions, write=False):
    if write:
        # Metadata-only marker. A deployer is privileged in apps; this is an ordering gate, not a security boundary.
        value = {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'platform-db-bootstrap','namespace':'apps'},'data':versions}
        subprocess.run(['kubectl','apply','-f','-'], input=json.dumps(value), text=True, check=True)
    else:
        current = json.loads(command(['kubectl','-n','apps','get','configmap','platform-db-bootstrap','-o','json']))['data']
        require(current == versions, 'Secret versions changed or DB bootstrap missing; rerun platform Phase 2 before migration')


def require_egress_admission(settings):
    """Pure preflight: inhibited NAT must stop core creation before any effects."""
    mode = settings.get('nat_mode')
    require(mode in ('instance', 'gateway'), 'Explicit NAT egress mode required')
    if mode == 'instance':
        require(settings.get('nat_recovery_enabled') is True,
                'NAT recovery is inhibited; separately review migration and activation before core creation')


def phase(number, environment, images, *, synthetic_inputs=None):
    if synthetic_inputs is not None or environment.startswith('trial-'):
        require(synthetic_inputs is not None and number == 1, 'Synthetic runtime bootstrap is not admitted; explicit phase1 packet required')
        # The existing phase1 entry point consumes the new producer, but cannot
        # apply any legacy owner or imply that a local packet admits execution.
        c = generate(environment, synthetic_inputs=synthetic_inputs)
        print('LOCAL SYNTHETIC CONTRACT ONLY: no core owner apply or AWS operation.')
        return c
    settings = environment_settings(environment)
    if number == 0:
        account = json.loads(command(['aws', 'sts', 'get-caller-identity', '--output', 'json']))['Account']
        bucket = f'{settings["project_name"]}-{account}-{environment}-{settings["region"]}-tfstate'
        command(['aws', 's3api', 'head-bucket', '--bucket', bucket, '--expected-bucket-owner', account])
        table = f'{settings["project_name"]}-{account}-{environment}-terraform-locks'
        command(['aws', '--region', settings['region'], 'dynamodb', 'describe-table', '--table-name', table])
        print('Backend prerequisites found; no backend resources created.')
        return
    if number == 1:
        require_egress_admission(settings)
        phase(0, environment, None)
        account = json.loads(command(['aws', 'sts', 'get-caller-identity', '--output', 'json']))['Account']
        retained_secret_arns(settings, account, output('runtime-secrets', environment))
        for stack in CORE:
            directory = ROOT / 'infra/live' / environment / stack
            run(['terragrunt', 'init'], directory)
            run(['terragrunt', 'apply'], directory)  # Interactive plan/approval, never auto-approve.
        generate(environment)
        return
    c = generate(environment)
    if number in (2, 3):
        kube_context(c)
        if number == 2:
            result = subprocess.run(['kubectl','get','namespace','apps','--ignore-not-found','-o','name'], capture_output=True,text=True,check=True)
            if not result.stdout.strip(): run(['kubectl','create','namespace','apps'])
            run(['kubectl','label','namespace','apps','elbv2.k8s.aws/pod-readiness-gate-inject=enabled','--overwrite'])
            # Reuse existing addon chart, with every identity value derived from EKS outputs.
            with tempfile.TemporaryDirectory(prefix='eks-addons-') as tmp:
                chart = Path(tmp) / 'chart'
                shutil.copytree(ROOT / 'k8s/charts/cluster-addons', chart)
                values = {
                    'keda': {'podIdentity': {'aws': {'irsa': {'enabled': True, 'roleArn': output('iam', environment)['role_arns'][f'{c["project"]}-{environment}-keda-irsa']}}}},
                    'external-secrets': {'serviceAccount': {'annotations': {'eks.amazonaws.com/role-arn': c['esoRoleArn']}}},
                    'aws-load-balancer-controller': {'clusterName': c['clusterName'], 'region': c['region'], 'vpcId': c['vpcId'],
                        'serviceAccount': {'name': 'aws-load-balancer-controller', 'annotations': {'eks.amazonaws.com/role-arn': c['addons']['loadBalancerControllerRoleArn']}}},
                    'cluster-autoscaler': {'awsRegion': c['region'], 'autoDiscovery': {'clusterName': c['clusterName']},
                        'rbac': {'serviceAccount': {'name': 'cluster-autoscaler', 'annotations': {'eks.amazonaws.com/role-arn': c['addons']['clusterAutoscalerRoleArn']}}}}}
                generated = Path(tmp) / 'values.yaml'; generated.write_text(yaml.safe_dump(values))
                run([sys.executable, ROOT/'scripts/validation/helm_dependencies.py', '--chart', chart])
                run(['helm', 'upgrade', '--install', 'cluster-addons', chart, '-n', 'kube-system', '--rollback-on-failure', '--wait', '--timeout', '10m', '-f', chart / 'values-dev.yaml', '-f', generated])
            addon_gate()
            scaling_gate(c)
            observability(c, install=True)
            for deployment in ('external-secrets', 'external-secrets-webhook', 'external-secrets-cert-controller'):
                run(['kubectl','-n','kube-system','rollout','status','deployment/'+deployment,'--timeout=600s'])
            for crd in ('secretstores.external-secrets.io','externalsecrets.external-secrets.io'):
                run(['kubectl','wait','--for=condition=Established','crd/'+crd,'--timeout=300s'])
            from secret_values import initialize
            initialize(c, os.environ.get('BOOTSTRAP_ADMIN_EMAIL'))
            values = ROOT / '.generated' / environment / 'platform.values.yaml'
            run(['helm','upgrade','--install','platform-bootstrap',ROOT/'k8s/charts/platform-bootstrap','-n','apps','-f',values,'--wait','--timeout','10m'])
            run(['kubectl','-n','apps','wait','--for=condition=Ready','secretstore/platform-aws','--timeout=300s'])
            run(['helm','upgrade','--install','platform-secret-sync',ROOT/'k8s/charts/platform-secret-sync','-n','apps','-f',values,'--wait','--timeout','10m'])
            versions = runtime_secret_gate(request_refresh=True)
            from database import bootstrap
            bootstrap(c)
            require(runtime_secret_gate() == versions, 'Secrets changed during DB bootstrap; rerun before migration')
            database_marker(versions, write=True)
            return
        addon_gate()
        scaling_gate(c)
        observability(c)
        versions = runtime_secret_gate()
        database_marker(versions)
        revision = hashlib.sha256(json.dumps(versions,sort_keys=True).encode()).hexdigest()
        data = images_overlay(images)
        for s in SERVICES:
            aws(c, 'ecr', 'describe-images', '--repository-name', s + '-service', '--image-ids', 'imageDigest=' + data['services'][s]['image']['digest'])
        run(['helm', 'upgrade', '--install', 'platform-services', ROOT / 'k8s/charts/platform-services', '-n', 'apps', '--rollback-on-failure', '--wait', '--timeout', '10m',
             '-f', ROOT / 'k8s/environments' / environment / 'platform-services.values.yaml', '-f', ROOT / '.generated' / environment / 'infra.values.yaml', '-f', images, '--set-string', 'global.secretRevision='+revision])
        for s in SERVICES: run(['kubectl', '-n', 'apps', 'rollout', 'status', 'deployment/' + s + '-service', '--timeout=600s'])
        command(['kubectl', '-n', 'apps', 'get', 'ingress', 'platform-services', '-o', 'name'])
        return
    alb, listener = discover(c)
    if number == 5:
        directory = ROOT / 'infra/live' / environment / 'apigateway-integration'
        run(['terragrunt', 'init'], directory)
        run(['terragrunt', 'apply'], directory)  # Terraform discovers again; no ARN handoff input.
    if number in (5, 6):
        c = generate(environment, final=True)
        require(c['alb']['arn'] == alb and c['alb']['listenerArn'] == listener, 'Integration output differs from live discovery; rerun Phase 5')
        wait_for('VPC Link AVAILABLE', lambda: aws(c, 'apigatewayv2', 'get-vpc-link', '--vpc-link-id', c['apiGateway']['vpcLinkId'])['VpcLinkStatus'] == 'AVAILABLE')
        integrations = aws(c, 'apigatewayv2', 'get-integrations', '--api-id', c['apiGateway']['apiId'])['Items']
        require(len(integrations) == 2 and all(i['IntegrationUri'] == listener and i['ConnectionId'] == c['apiGateway']['vpcLinkId'] for i in integrations), 'Unexpected API integration wiring')
        print('Infrastructure dependency gates READY; functional/auth/event smoke remains R7, not verified here.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment')
    parser.add_argument('--synthetic-input', type=Path)
    parser.add_argument('--phase', type=int, choices=PHASES, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--images', type=Path)
    args = parser.parse_args()
    require(not args.synthetic_input or args.environment is not None, 'Explicit synthetic environment required')
    selected = args.environment or 'dev'
    print(f'Phase {args.phase}: {PHASES[args.phase]}')
    if args.phase == 1: print('LOCAL SYNTHETIC; owner applies disabled' if args.synthetic_input else ' -> '.join(CORE))
    if args.execute:
        try:
            phase(args.phase, selected, args.images, **({'synthetic_inputs': json.loads(args.synthetic_input.read_text())} if args.synthetic_input else {}))
        except Exception:
            # SDK/SQL exceptions can include values; never serialize their messages/tracebacks.
            raise SystemExit('Bootstrap failed; dependent phases were not run. Diagnose using sanitized service status and the runbook.')
    else:
        print('PLAN ONLY. No commands executed. Supply --execute only in an authorized operator session.')
