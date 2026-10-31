"""Generated, non-secret environment inventory. Never read a Terraform state file."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import UUID

import hcl2
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'infra/modules/management-host/deployer'))
from synthetic_contract import binding_hash, reject_protected, validate_environment as validate_synthetic
SERVICES = ('auth', 'shipment', 'tracking')
RETAINED_SECRET_NAMES = tuple(f'{s}-{p}-db' for s in SERVICES for p in ('runtime', 'migration')) + ('internal-trust', 'bootstrap-admin', 'auth-jwt', 'gateway-trust')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command(args, cwd=None):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                            env={**os.environ, 'TG_NO_AUTO_INIT': 'true', 'TG_BACKEND_REQUIRE_BOOTSTRAP': 'true', 'AWS_PAGER': ''})
    # Never print captured output: a failed command could contain sensitive material.
    require(result.returncode == 0, f'{args[0]} {args[1]} failed (exit {result.returncode}); inspect locally. No output was persisted.')
    return result.stdout


def output(stack, environment):
    data = json.loads(command(['terragrunt', 'output', '-json'], ROOT / 'infra/live' / environment / stack))
    # output is NOT in mock_outputs_allowed_terraform_commands. Missing real state fails.
    return {key: value['value'] for key, value in data.items() if not value.get('sensitive', False)}


def environment_settings(environment):
    require(re.fullmatch(r'[a-z][a-z0-9-]*', environment), 'Invalid environment')
    with (ROOT / 'infra/live' / environment / 'env.hcl').open() as file:
        return hcl2.load(file)['locals'][0]


def retained_secret_arns(settings, account, runtime):
    """Read existing output identities only; never apply the retained owner."""
    project, env, region = (settings[k] for k in ('project_name', 'environment', 'region'))
    require(runtime.get('eso_role_arn') == f'arn:aws:iam::{account}:role/{project}-{env}-external-secrets', 'Retained ESO identity mismatch')
    secrets = runtime.get('secret_arns', {})
    require(set(secrets) == set(RETAINED_SECRET_NAMES), 'Retained ten-secret coverage mismatch')
    shared = {'auth-jwt': 'auth-service-jwt-secret', 'gateway-trust': 'platform-trusted-proxy-secret'}
    for name, value in secrets.items():
        path = f'api-gateway-authorizer/{shared[name]}' if name in shared else f'runtime/{name}'
        prefix = f'arn:aws:secretsmanager:{region}:{account}:secret:{project}/{env}/{path}-'
        require(isinstance(value, str) and re.fullmatch(re.escape(prefix) + r'[A-Za-z0-9]{6}', value), 'Retained secret identity mismatch')
    require(len(set(secrets.values())) == 10, 'Duplicate retained secret identity')
    return secrets


def temporary_eso_role(settings, account, runtime, iam):
    retained_secret_arns(settings, account, runtime)
    name = f'{settings["project_name"]}-{settings["environment"]}-external-secrets-cert-irsa'
    expected = f'arn:aws:iam::{account}:role/{name}'
    require(iam.get('role_arns', {}).get(name) == expected, 'Missing or mismatched temporary ESO owner output; no historical fallback')
    return expected


def build_contract(settings, account, outputs, integration=None, *, synthetic_data=None, bindings=None):
    project, env, region = (settings[k] for k in ('project_name', 'environment', 'region'))
    synthetic = synthetic_data is not None or bindings is not None
    require(synthetic or not env.startswith('trial-'), 'Explicit synthetic data and bindings required; no dev fallback')
    if synthetic:
        require(integration is None or set(integration) == {'alb_arn', 'alb_listener_arn'}, 'Synthetic integration fields incomplete or unknown')
        if integration is not None: reject_protected(integration)
        require(type(synthetic_data) is dict and type(bindings) is dict, 'Synthetic data/bindings incomplete')
        require(set(outputs) == {'vpc', 'eks', 'ecr', 'apigateway-core'}, 'Synthetic inputs must not read historical data owners')
        require(set(bindings) == {'esoRoleArn', 'workloadRoles', 'addons', 'eventEncryption'}, 'Explicit synthetic identity/encryption bindings required')
        require(set(bindings['eventEncryption']) == {'keyArn', 'keyId', 'alias', 'rotation', 'deletionWindowDays'}, 'Synthetic encryption fields incomplete or unknown')
        require(set(synthetic_data) == {'schemaVersion', 'dataClass', 'trialId', 'database', 'secretArns', 'eventBus', 'queueArns', 'queueUrls', 'consumerDlqArns', 'consumerDlqUrls'}, 'Synthetic data fields incomplete or unknown')
        require(synthetic_data['schemaVersion'] == 1 and synthetic_data['dataClass'] == 'SYNTHETIC_ONLY', 'Synthetic data classification required')
        run = UUID(synthetic_data['trialId'])
        require(project == 'cnp' and env == 'trial-' + run.hex and str(run) == synthetic_data['trialId'] and run.version == 4, 'Synthetic namespace/environment mismatch')
        require(set(synthetic_data['database']) == {'host', 'identifier', 'masterSecretArn'} and synthetic_data['database']['identifier'] == f'{project}-{env}-postgres', 'Synthetic database identity mismatch')
        require(set(synthetic_data['eventBus']) == {'name', 'arn'}, 'Synthetic bus fields mismatch')
        for name, fields in {'vpc': {'vpc_id', 'private_subnet_ids', 'private_subnet_cidrs'},
                             'eks': {'vpc_id', 'cluster_name'}, 'ecr': {'repository_urls'},
                             'apigateway-core': {'api_id', 'vpc_link_id', 'api_endpoint', 'alb_frontend_security_group_id', 'vpc_link_security_group_id'}}.items():
            require(set(outputs[name]) == fields, 'Synthetic infrastructure fields incomplete or unknown')
        require(set(outputs['ecr']['repository_urls']) == {s + '-service' for s in SERVICES}, 'Synthetic image repository coverage mismatch')
        cidrs = outputs['vpc']['private_subnet_cidrs']
        require(type(cidrs) is list and len(cidrs) == len(outputs['vpc']['private_subnet_ids']), 'Synthetic private CIDR bindings incomplete')
        networks = [ipaddress.ip_network(value, strict=True) for value in cidrs]
        private = [ipaddress.ip_network(value) for value in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
        require(len(set(networks)) == len(networks) and all(n.version == 4 and any(n.subnet_of(p) for p in private) for n in networks), 'Synthetic CIDRs must be distinct private IPv4 networks')
        queue, delivery = f'{project}-{env}-shipment-events-queue', f'{project}-{env}-shipment-delivery-dlq'
        require(set(synthetic_data['secretArns']) == set(RETAINED_SECRET_NAMES), 'Synthetic ten-secret coverage required')
        for key in ('queueArns', 'queueUrls'):
            require(set(synthetic_data[key]) == {queue, delivery}, 'Synthetic queue coverage mismatch')
        for key in ('consumerDlqArns', 'consumerDlqUrls'):
            require(set(synthetic_data[key]) == {queue}, 'Synthetic consumer DLQ coverage mismatch')
        reject_protected([settings, outputs, bindings, synthetic_data])
        outputs = {**outputs,
            'event-encryption': {source: bindings['eventEncryption'][target] for source, target in (
                ('key_arn', 'keyArn'), ('key_id', 'keyId'), ('alias', 'alias'), ('rotation_enabled', 'rotation'), ('deletion_window_in_days', 'deletionWindowDays'))},
            'sqs': {'queue_arns': synthetic_data['queueArns'], 'queue_urls': synthetic_data['queueUrls'],
                    'dlq_arns': synthetic_data['consumerDlqArns'], 'dlq_urls': synthetic_data['consumerDlqUrls']},
            'eventbridge': {'event_bus_name': synthetic_data['eventBus']['name'], 'event_bus_arn': synthetic_data['eventBus']['arn']},
            'iam': {}, 'rds': {'db_instance_address': synthetic_data['database']['host'], 'master_user_secret_arn': synthetic_data['database']['masterSecretArn']}}
    vpc, eks, kms, sqs, bus, iam, ecr, api = (outputs[k] for k in ('vpc', 'eks', 'event-encryption', 'sqs', 'eventbridge', 'iam', 'ecr', 'apigateway-core'))
    queue = f'{project}-{env}-shipment-events-queue'
    delivery = f'{project}-{env}-shipment-delivery-dlq'
    require(eks['vpc_id'] == vpc['vpc_id'], 'EKS/VPC output mismatch')
    c = {
        'schemaVersion': 3 if synthetic else 2, 'environment': env, 'project': project, 'accountId': account,
        'region': region, 'vpcId': vpc['vpc_id'], 'privateSubnetIds': vpc['private_subnet_ids'],
        'clusterName': eks['cluster_name'], 'namespace': 'apps',
        'eventBus': {'name': bus['event_bus_name'], 'arn': bus['event_bus_arn']},
        'eventEncryption': {'keyArn': kms['key_arn'], 'keyId': kms['key_id'], 'alias': kms['alias'],
                            'rotation': kms['rotation_enabled'], 'deletionWindowDays': kms['deletion_window_in_days']},
        'shipmentQueue': {'arn': sqs['queue_arns'][queue], 'url': sqs['queue_urls'][queue],
                          'consumerDlqArn': sqs['dlq_arns'][queue], 'consumerDlqUrl': sqs['dlq_urls'][queue],
                          'deliveryDlqArn': sqs['queue_arns'][delivery], 'deliveryDlqUrl': sqs['queue_urls'][delivery]},
        'alb': {'arn': integration['alb_arn'] if integration else None,
                'listenerArn': integration['alb_listener_arn'] if integration else None,
                'frontendSecurityGroupId': api['alb_frontend_security_group_id'],
                'discoveryTags': {'elbv2.k8s.aws/cluster': eks['cluster_name'], 'ingress.k8s.aws/stack': project,
                                  'Project': project, 'Environment': env}},
        'apiGateway': {'apiId': api['api_id'], 'vpcLinkId': api['vpc_link_id'],
                       'vpcLinkSecurityGroupId': api['vpc_link_security_group_id'], 'endpoint': api['api_endpoint']},
        'workloadRoles': bindings['workloadRoles'] if synthetic else {s: iam['role_arns'][f'{project}-{env}-{s}-service-irsa'] for s in ('shipment', 'tracking')},
        'repositories': {s: ecr['repository_urls'][s + '-service'] for s in SERVICES},
        'database': {'host': outputs['rds']['db_instance_address'], 'name': 'platform', 'masterSecretArn': outputs['rds']['master_user_secret_arn']},
        'secrets': synthetic_data['secretArns'] if synthetic else retained_secret_arns(settings, account, outputs['runtime-secrets']),
        'esoRoleArn': bindings['esoRoleArn'] if synthetic else temporary_eso_role(settings, account, outputs['runtime-secrets'], iam),
        'addons': bindings['addons'] if synthetic else {'loadBalancerControllerRoleArn': eks['aws_load_balancer_controller_role_arn'],
                   'clusterAutoscalerRoleArn': eks['cluster_autoscaler_role_arn']},
    }
    if synthetic:
        c['alb']['discoveryTags']['ingress.k8s.aws/stack'] = f'{project}-{env}'
        c['dataScope'] = {'mode': 'SYNTHETIC_ONLY', 'trialId': synthetic_data['trialId'],
                          'environment': env, 'namespace': f'{project}-{env}', 'bindingSha256': binding_hash(c)}
        validate_synthetic(c)
    return c


def validate_contract(c, environment, ready=False):
    if c.get('schemaVersion') == 3:
        require(c['environment'] == environment, 'Explicit synthetic environment mismatch')
        validate_synthetic(c)
        if ready: require(c['alb']['arn'] is not None, 'Synthetic integration bindings incomplete')
        return c
    require(not environment.startswith('trial-') and 'dataScope' not in c, 'Synthetic schema required; no dev fallback')
    schema = json.loads((Path(__file__).with_name('environment.schema.json')).read_text())
    # Small closed schema: all nested properties required, unknown fields prohibited.
    def check(value, spec, path):
        kind = spec['type']
        if isinstance(kind, list):
            if value is None and 'null' in kind:
                return
            kind = next(k for k in kind if k != 'null')
        types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool}
        require(type(value) is types[kind], f'Invalid type at {path}')
        if kind == 'object':
            require(set(value) == set(spec['properties']), f'Missing or unknown fields at {path}')
            for k, v in value.items(): check(v, spec['properties'][k], path + '.' + k)
        if kind == 'array':
            require(len(value) >= spec.get('minItems', 0), f'Insufficient entries at {path}')
            for v in value: check(v, spec['items'], path)
        if 'const' in spec: require(value == spec['const'], f'Unexpected value at {path}')
        if 'pattern' in spec: require(re.fullmatch(spec['pattern'], value), f'Invalid identifier at {path}')
    check(c, schema, 'contract')
    require(c['environment'] == environment, 'Wrong environment')
    serialized = json.dumps(c)
    require(not re.search(r'123456789012|000000000000|(?:sg|vpc|subnet)-([0-9a-f])\1{7,}|EXAMPLE|replace-me|AKIA[0-9A-Z]{16}|-----BEGIN', serialized), 'Mock or secret material in contract')
    require(not re.search(r'(?i)password|jwtsecret|proxysecret|accesskey|sessiontoken|connectionstring', serialized), 'Secret material is not permitted')
    a, r, p, e = (c[k] for k in ('accountId', 'region', 'project', 'environment'))
    def arn(value, service):
        require(value.startswith(f'arn:aws:{service}:{"" if service == "iam" else r}:{a}:'), 'Cross-account/region ARN')
    enc, q, alb = c['eventEncryption'], c['shipmentQueue'], c['alb']
    arn(enc['keyArn'], 'kms')
    require(enc['keyArn'].endswith('/' + enc['keyId']), 'KMS ID/ARN mismatch')
    require(enc['alias'] == f'alias/{p}-{e}-events', 'Wrong KMS alias')
    arn(c['eventBus']['arn'], 'events')
    require(c['eventBus']['name'] == f'{p}-{e}-bus' and c['eventBus']['arn'].endswith('/' + c['eventBus']['name']), 'Wrong event bus')
    for prefix, name in (('', f'{p}-{e}-shipment-events-queue'), ('consumerDlq', f'{p}-{e}-shipment-events-dlq'), ('deliveryDlq', f'{p}-{e}-shipment-delivery-dlq')):
        ak, uk = (prefix + 'Arn', prefix + 'Url') if prefix else ('arn', 'url')
        require(q[ak] == f'arn:aws:sqs:{r}:{a}:{name}' and q[uk] == f'https://sqs.{r}.amazonaws.com/{a}/{name}', 'Wrong queue identity')
    require(alb['discoveryTags'] == {'elbv2.k8s.aws/cluster': c['clusterName'], 'ingress.k8s.aws/stack': p, 'Project': p, 'Environment': e}, 'Wrong discovery tags')
    for s, role in c['workloadRoles'].items():
        arn(role, 'iam')
        require(role.endswith(f':role/{p}-{e}-{s}-service-irsa'), 'Wrong workload role')
    for role in c['addons'].values(): arn(role, 'iam')
    arn(c['esoRoleArn'], 'iam')
    require(c['esoRoleArn'] == f'arn:aws:iam::{a}:role/{p}-{e}-external-secrets-cert-irsa', 'Wrong temporary ESO role; no historical fallback')
    for secret in c['secrets'].values(): arn(secret, 'secretsmanager')
    arn(c['database']['masterSecretArn'], 'secretsmanager')
    for s, repo in c['repositories'].items():
        require(repo == f'{a}.dkr.ecr.{r}.amazonaws.com/{s}-service', 'Wrong ECR repository')
    require(c['apiGateway']['endpoint'] == f'https://{c["apiGateway"]["apiId"]}.execute-api.{r}.amazonaws.com', 'Wrong API endpoint')
    require((alb['arn'] is None) == (alb['listenerArn'] is None), 'Partial ALB discovery')
    if ready: require(alb['arn'] is not None, 'Integration not configured; complete Phase 5')
    if alb['arn'] is not None:
        arn(alb['arn'], 'elasticloadbalancing'); arn(alb['listenerArn'], 'elasticloadbalancing')
        require(alb['listenerArn'].split(':listener/')[1].startswith(alb['arn'].split(':loadbalancer/')[1] + '/'), 'Listener belongs to another ALB')
    return c


def overlay(c):
    values = {'global': {'ingress': {
        'frontendSecurityGroupId': c['alb']['frontendSecurityGroupId'],
        'discoveryTags': {'Project': c['project'], 'Environment': c['environment']},
        'annotations': {'alb.ingress.kubernetes.io/group.name': c['dataScope']['namespace'] if c['schemaVersion'] == 3 else c['project']}}}, 'services': {}}
    for s in SERVICES:
        values['services'][s] = {'image': {'repository': c['repositories'][s]}, 'env': {'Database__Host': c['database']['host']}}
        if c['schemaVersion'] == 3:
            values['services'][s]['env']['Telemetry__Environment'] = c['environment']
        if s != 'auth':
            values['services'][s]['env']['AWS__Region'] = c['region']
        if s == 'tracking':
            values['services'][s]['env']['AWS__EventBusName'] = c['eventBus']['name']
    values['services']['shipment']['env']['AWS__ShipmentEventsQueueUrl'] = c['shipmentQueue']['url']
    values['services']['shipment']['keda'] = {'queueURL': c['shipmentQueue']['url'], 'awsRegion': c['region']}
    return values


def generate(environment, final=False, *, synthetic_inputs=None):
    if synthetic_inputs is not None:
        require(type(synthetic_inputs) is dict and set(synthetic_inputs) == {'schemaVersion', 'settings', 'accountId', 'outputs', 'synthetic_data', 'bindings', 'integration'}, 'Synthetic input packet incomplete or unknown')
        require(synthetic_inputs['schemaVersion'] == 1 and type(environment) is str and environment.startswith('trial-'), 'Explicit synthetic environment required')
        settings, account, outputs = (synthetic_inputs[k] for k in ('settings', 'accountId', 'outputs'))
        require(set(settings) == {'project_name', 'environment', 'region', 'eks_cluster_name'} and settings['environment'] == environment, 'Synthetic settings incomplete or mismatched')
        require('private_subnet_cidrs' in outputs['vpc'], 'Explicit synthetic private CIDRs required')
        c = build_contract(settings, account, outputs, synthetic_inputs['integration'], synthetic_data=synthetic_inputs['synthetic_data'], bindings=synthetic_inputs['bindings'])
    else:
        require(not environment.startswith('trial-'), 'Synthetic input packet required before historical reads')
        settings = environment_settings(environment)
        account = json.loads(command(['aws', 'sts', 'get-caller-identity', '--output', 'json']))['Account']
        names = ('vpc', 'eks', 'event-encryption', 'sqs', 'eventbridge', 'iam', 'ecr', 'apigateway-core', 'rds', 'runtime-secrets')
        outputs = {name: output(name, environment) for name in names}
        c = build_contract(settings, account, outputs, output('apigateway-integration', environment) if final else None)
    require(c['clusterName'] == settings['eks_cluster_name'], 'Cluster output does not match selected environment')
    validate_contract(c, environment, ready=final)
    directory = ROOT / '.generated' / environment
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in [('environment.json', json.dumps(c, indent=2)), ('infra.values.yaml', yaml.safe_dump(overlay(c), sort_keys=False)), ('platform.values.yaml', yaml.safe_dump({'region': c['region'], 'secretArns': c['secrets'], 'workloadRoles': c['workloadRoles'], 'network': {'privateSubnetCidrs': outputs['vpc']['private_subnet_cidrs']}}))]:
        temporary = directory / (name + '.tmp')
        temporary.write_text(content + '\n')
        temporary.replace(directory / name)
    return c


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment')
    parser.add_argument('--synthetic-input', type=Path)
    parser.add_argument('--final', action='store_true')
    parser.add_argument('--validate', type=Path)
    args = parser.parse_args()
    require(not args.synthetic_input or args.environment is not None, 'Explicit synthetic environment required')
    selected = args.environment or 'dev'
    if args.validate:
        require(not args.synthetic_input, 'Validation cannot mix source packets')
        validate_contract(json.loads(args.validate.read_text()), selected, args.final)
    else:
        generate(selected, args.final, **({'synthetic_inputs': json.loads(args.synthetic_input.read_text())} if args.synthetic_input else {}))
    print('Environment contract validated; no secret values exported.')
