"""Finite cloud preparation: read-only AWS observation, manifest generation, HTTP receipts.

No AWS/Kubernetes mutation command exists here. HTTP phases require an explicit flag;
they are future live tests and must not be run under preparation-only authorization.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

ACCOUNT = '341936017254'
PROFILE = 'cnp-cert-dev'
REGION = 'us-east-1'
BASE = 'e7a7035fe17db55a6774a5cfc4704786f15880f3'
ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name('cloud_network_probe')
FLOW = {('shipment', 'auth'): True, ('tracking', 'auth'): True,
        ('tracking', 'shipment'): True, ('shipment', 'tracking'): False,
        ('auth', 'shipment'): False, ('auth', 'tracking'): False}
PHASES = {'baseline': (200, 200, 400), 'revoked': (200, 200, 403),
          'disabled': (401, 401, 401), 'outage': (503, 503),
          'restored': (200, 200, 403)}


def require(value, message):
    if not value:
        raise ValueError(message)


def aws(*args, runner=subprocess.run):
    env = {k: v for k, v in os.environ.items() if not k.startswith('AWS_')}
    env.update(AWS_EC2_METADATA_DISABLED='true', AWS_MAX_ATTEMPTS='1')
    command = ['aws', '--profile', PROFILE, '--region', REGION, '--no-cli-pager',
               '--cli-connect-timeout', '5', '--cli-read-timeout', '20', *args, '--output', 'json']
    result = runner(command, capture_output=True, text=True, env=env, timeout=30)
    if result.returncode:
        match = re.search(r'\(([A-Za-z0-9_.-]+)\) when calling', result.stderr)
        code = match.group(1) if match else 'READ_FAILED'
        return {'status': 'ABSENT' if code in ('ResourceNotFoundException', 'DBInstanceNotFound',
                                              'RepositoryNotFoundException') else 'INCOMPLETE', 'code': code}
    return {'status': 'OBSERVED', 'value': json.loads(result.stdout or '{}')}


def observe(reader=aws):
    identity = reader('sts', 'get-caller-identity', '--query', '{Account:Account,Arn:Arn}')
    require(identity.get('status') == 'OBSERVED' and identity['value']['Account'] == ACCOUNT,
            'STOP: exclusive profile identity unavailable or wrong account')
    calls = {
        'cluster': ('eks', 'describe-cluster', '--name', 'logistics-platform-dev', '--query',
                    'cluster.{name:name,status:status,version:version,private:resourcesVpcConfig.endpointPrivateAccess,public:resourcesVpcConfig.endpointPublicAccess}'),
        'database': ('rds', 'describe-db-instances', '--db-instance-identifier',
                     'cloud-native-platform-dev-postgres', '--query', 'DBInstances[].{id:DBInstanceIdentifier,status:DBInstanceStatus,type:DBInstanceClass}'),
        'apis': ('apigatewayv2', 'get-apis', '--query',
                 "Items[?Name=='cloud-native-platform-dev-http-api'].{id:ApiId,name:Name}"),
        'backend': ('s3api', 'head-bucket', '--bucket',
                    f'cloud-native-platform-{ACCOUNT}-dev-us-east-1-tfstate', '--expected-bucket-owner', ACCOUNT),
        'locks': ('dynamodb', 'describe-table', '--table-name',
                  f'cloud-native-platform-{ACCOUNT}-dev-terraform-locks', '--query', 'Table.{name:TableName,status:TableStatus}'),
    }
    for service in ('auth', 'shipment', 'tracking'):
        calls['ecr-' + service] = ('ecr', 'describe-repositories', '--registry-id', ACCOUNT,
                                   '--repository-names', service + '-service', '--query',
                                   'repositories[].{name:repositoryName}')
    resources = {name: reader(*args) for name, args in calls.items()}
    apis = resources['apis']
    if apis['status'] == 'OBSERVED' and len(apis['value']) == 1:
        api = apis['value'][0]['id']
        resources['authorizers'] = reader('apigatewayv2', 'get-authorizers', '--api-id', api,
            '--query', 'Items[].{id:AuthorizerId,type:AuthorizerType,ttl:AuthorizerResultTtlInSeconds,sources:IdentitySource}')
        resources['routes'] = reader('apigatewayv2', 'get-routes', '--api-id', api,
            '--query', 'Items[].{route:RouteKey,type:AuthorizationType,authorizer:AuthorizerId}')
    return {'schemaVersion': 1, 'observedAt': datetime.now(timezone.utc).isoformat(),
            'identity': identity['value'], 'resources': resources,
            'scope': 'metadata-only; not a deployment or live authorization verdict'}


def manifests(run_id):
    require(re.fullmatch('[a-f0-9]{24}', run_id), 'Run ID must be 24 lowercase hex characters')
    docker = (ROOT / 'microservices/auth-service/Dockerfile').read_text()
    image = re.search(r'^FROM (mcr.microsoft.com/dotnet/sdk:10\.0\.403-noble@sha256:[a-f0-9]{64}) AS build$', docker, re.M)
    require(image, 'Reviewed SDK image pin missing; do not choose latest')
    label = {'platform.cloud-native.io/validation-run': run_id}
    config = 'current-profile-probe-' + run_id
    data = {name: (PROBE / name).read_text() for name in ('Program.cs', 'NetworkProbe.csproj', 'NuGet.Config')}
    items = [{'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': config, 'namespace': 'apps', 'labels': label}, 'data': data}]
    for source in ('auth', 'shipment', 'tracking'):
        labels = {**label, 'app.kubernetes.io/name': source + '-service',
                  'platform.cloud-native.io/workload': 'runtime'}
        # Deliberately omit app.kubernetes.io/instance: production Services must not select probes.
        items.append({'apiVersion': 'batch/v1', 'kind': 'Job',
            'metadata': {'name': config + '-' + source, 'namespace': 'apps', 'labels': label},
            'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': 180,
                'template': {'metadata': {'labels': labels}, 'spec': {
                    'restartPolicy': 'Never', 'automountServiceAccountToken': False,
                    'securityContext': {'runAsNonRoot': True, 'runAsUser': 1654, 'runAsGroup': 1654,
                                        'fsGroup': 1654, 'seccompProfile': {'type': 'RuntimeDefault'}},
                    'containers': [{'name': 'probe', 'image': image.group(1),
                        'workingDir': '/tmp', 'command': ['bash', '-ec'],
                        'args': ['cp /probe/* /tmp/; dotnet run --project /tmp/NetworkProbe.csproj --configuration Release --no-launch-profile -- ' + run_id + ' ' + source],
                        'env': [{'name': k, 'value': v} for k, v in {
                            'HOME': '/tmp', 'DOTNET_CLI_HOME': '/tmp', 'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1',
                            'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'DOTNET_NOLOGO': '1'}.items()],
                        'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'},
                                      'limits': {'cpu': '500m', 'memory': '512Mi'}},
                        'securityContext': {'readOnlyRootFilesystem': True, 'allowPrivilegeEscalation': False,
                                            'capabilities': {'drop': ['ALL']}},
                        'volumeMounts': [{'name': 'source', 'mountPath': '/probe', 'readOnly': True},
                                         {'name': 'tmp', 'mountPath': '/tmp'}]}],
                    'volumes': [{'name': 'source', 'configMap': {'name': config}},
                                {'name': 'tmp', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '128Mi'}}]}}}})
    return {'apiVersion': 'v1', 'kind': 'List', 'items': items}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_live_authorizer(authorizers, routes):
    require(len(authorizers) == 1, 'Exactly one reviewed authorizer required')
    authorizer = authorizers[0]
    require(authorizer['type'] == 'REQUEST' and type(authorizer['ttl']) is int and authorizer['ttl'] == 0
            and authorizer['sources'] == ['$request.header.Authorization'], 'Actual authorizer is not uncached REQUEST/Authorization')
    for key in ('GET /shipments', 'GET /tracking/by-shipment/{shipmentId}', 'POST /admin/tracking-events'):
        selected = [r for r in routes if r['route'] == key]
        require(len(selected) == 1 and selected[0]['type'] == 'CUSTOM' and
                selected[0]['authorizer'] == authorizer['id'], 'Protected route authorizer differs')


def guard_api(api, reader=aws):
    identity = reader('sts', 'get-caller-identity', '--query', '{Account:Account}')
    require(identity.get('status') == 'OBSERVED' and identity['value']['Account'] == ACCOUNT, 'Wrong profile account')
    values = []
    for operation, query in (
            ('get-api', '{name:Name}'),
            ('get-authorizers', 'Items[].{id:AuthorizerId,type:AuthorizerType,ttl:AuthorizerResultTtlInSeconds,sources:IdentitySource}'),
            ('get-routes', 'Items[].{route:RouteKey,type:AuthorizationType,authorizer:AuthorizerId}')):
        result = reader('apigatewayv2', operation, '--api-id', api, '--query', query)
        require(result.get('status') == 'OBSERVED', 'Incomplete API metadata')
        values.append(result['value'])
    require(values[0]['name'] == 'cloud-native-platform-dev-http-api', 'Wrong project API')
    validate_live_authorizer(*values[1:])


def http_phase(api, phase, private, guard=guard_api):
    require(re.fullmatch('[a-z0-9]{6,15}', api), 'Invalid API ID')
    require(set(private) == {'token', 'trackingPath'}, 'Private input needs token and trackingPath only')
    token, tracking = private['token'], private['trackingPath']
    require(isinstance(token, str) and 0 < len(token) <= 8192 and not re.search(r'\s', token), 'Invalid bearer')
    require(isinstance(tracking, str) and re.fullmatch('/tracking/by-shipment/[a-fA-F0-9-]{36}', tracking), 'Use reviewed shipment tracking lookup path')
    guard(api)
    targets = [('GET', '/shipments', None), ('GET', tracking, None),
               ('POST', '/admin/tracking-events', b'{}')][:len(PHASES[phase])]
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))
    rows = []
    for round_id in range(3):
        for index, (method, path, body) in enumerate(targets):
            request = urllib.request.Request(f'https://{api}.execute-api.{REGION}.amazonaws.com' + path,
                data=body, method=method, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            try:
                response = opener.open(request, timeout=12)
            except urllib.error.HTTPError as error:
                response = error
            # Never read/persist bodies or Authorization. A transport failure aborts the receipt.
            with response:
                rows.append({'round': round_id, 'index': index, 'status': response.code,
                    'noStore': 'no-store' in response.headers.get('Cache-Control', '').lower(),
                    'requestId': response.headers.get('apigw-requestid', ''),
                    'observedAt': datetime.now(timezone.utc).isoformat()})
    return {'phase': phase, 'apiId': api, 'tokenSha256': hashlib.sha256(token.encode()).hexdigest(), 'checks': rows}


def evaluate_http(receipts):
    require(len(receipts) == len(PHASES) and {r['phase'] for r in receipts} == set(PHASES), 'All five distinct phases required')
    require([r['phase'] for r in receipts] == list(PHASES), 'Phase order differs from reviewed transitions')
    require(len({r['tokenSha256'] for r in receipts}) == 1 and
            all(re.fullmatch('[a-f0-9]{64}', r['tokenSha256']) for r in receipts), 'Same original token required')
    require(len({r['apiId'] for r in receipts}) == 1, 'Same API required')
    timestamps = []
    identifiers = []
    for receipt in receipts:
        expected = PHASES[receipt['phase']]
        rows = receipt['checks']
        require(len(rows) == 3 * len(expected), 'Exactly three samples per case required')
        require({(x['round'], x['index']) for x in rows} ==
                {(r, i) for r in range(3) for i in range(len(expected))}, 'Missing/duplicate sample')
        require(all(type(x['status']) is int and x['status'] == expected[x['index']] and
                    x['noStore'] is True and bool(x['requestId']) for x in rows), 'Status/cache/request identity failed')
        timestamps.extend(datetime.fromisoformat(x['observedAt']) for x in rows)
        identifiers.extend(x['requestId'] for x in rows)
    require(all(t.tzinfo is not None for t in timestamps) and timestamps == sorted(timestamps)
            and (max(timestamps) - min(timestamps)).total_seconds() <= 1800,
            'Receipt chronology exceeds the finite 30-minute acceptance window')
    require(len(identifiers) == len(set(identifiers)), 'Repeated gateway request identity')
    return 'HTTP_RECEIPTS_ACCEPTED_REQUIRES_RAW_EVIDENCE_REVIEW'


def evaluate_network(records, run_id):
    require(len(records) == 3 and {r['source'] for r in records} == {'auth', 'shipment', 'tracking'}, 'Three distinct probe origins required')
    for record in records:
        require(record['runId'] == run_id, 'Mixed run identity')
        expected = {(round_id, target) for round_id in range(3)
                    for source, target in FLOW if source == record['source']}
        require(len(record['samples']) == 6 and {(s['round'], s['target']) for s in record['samples']} == expected, 'Incomplete/repeated flow samples')
        for sample in record['samples']:
            outcome = 'connected' if FLOW[record['source'], sample['target']] else 'timeout'
            require(sample['port'] == 8080 and sample['addresses'] and sample['outcome'] == outcome,
                    'Network sample failed; DNS/refused sockets cannot prove denial')
    return 'NETWORK_RECEIPTS_ACCEPTED_REQUIRES_POLICY_BINDINGS_AND_READY_TARGETS'


def evaluate_network_bindings(receipt, capture, expected_specs, service_uids, addon_version):
    """Offline joins for one captured run; never certifies a new live generation."""
    import ipaddress
    run=receipt['runId'];evaluate_network(receipt['records'],run)
    for field,kind,version in [('policies','NetworkPolicy','networking.k8s.io/v1'),('policyEndpoints','PolicyEndpoint','networking.k8s.aws/v1alpha1'),('endpointSlices','EndpointSlice','discovery.k8s.io/v1'),('jobs','Job','batch/v1')]:
        require(all(x.get('kind')==kind and x.get('apiVersion')==version for x in capture[field]),'Wrong captured object GVK')
    require(capture['daemonset'].get('apiVersion')=='apps/v1','Wrong CNI object version')
    names={x+'-service' for x in ('auth','shipment','tracking')}
    policies=capture['policies'];compiled=capture['policyEndpoints'];slices=capture['endpointSlices']
    require(len(policies)==3 and {x['metadata']['name'] for x in policies}==set(expected_specs),'Missing/extra captured policy')
    require(set(service_uids)==names and all(service_uids.values()) and len(set(service_uids.values()))==3,'Service generations required')
    require(all(type(x.get('uid')) is str and x['uid'] for x in expected_specs.values()) and len({x['uid'] for x in expected_specs.values()})==3,'Policy generations required')
    require(len(slices)==3 and len(compiled)==3,'One captured service/compiled policy per workload required')
    addon=capture['addon'];config=json.loads(addon['configuration'])
    require(addon['name']=='vpc-cni' and addon['status']=='ACTIVE' and addon['version']==addon_version
            and config.get('enableNetworkPolicy')=='true' and config.get('env',{}).get('NETWORK_POLICY_ENFORCING_MODE')=='standard','Captured CNI pin/mode mismatch')
    ds=capture['daemonset'];st=ds['status'];containers=ds['spec']['template']['spec']['containers']
    require(ds['kind']=='DaemonSet' and ds['metadata']['namespace']=='kube-system' and ds['metadata']['name']=='aws-node'
            and ds['metadata'].get('uid') and st.get('observedGeneration')==ds['metadata']['generation']
            and type(st.get('desiredNumberScheduled')) is int and st['desiredNumberScheduled']>0
            and all(st.get(x)==st['desiredNumberScheduled'] for x in ('numberReady','numberAvailable','updatedNumberScheduled')),'CNI agent readiness unavailable')
    agent=[x for x in containers if x['name']=='aws-eks-nodeagent'];node=[x for x in containers if x['name']=='aws-node']
    require(len(agent)==len(node)==1 and '--enable-network-policy=true' in agent[0].get('args',[])
            and [e.get('value') for e in node[0].get('env',[]) if e['name']=='NETWORK_POLICY_ENFORCING_MODE']==['standard'],'Observed CNI enforcement disabled')
    ready={};selected={};bindings=[]
    for name in sorted(names):
        ps=[x for x in policies if x['metadata']['name']==name.replace('-service','-runtime-boundary')]
        require(len(ps)==1,'Policy identity missing');policy=ps[0];pm=policy['metadata']
        require(pm.get('namespace')=='apps' and pm.get('uid')==expected_specs[pm['name']]['uid'] and policy['spec']==expected_specs[pm['name']]['spec'],'Policy differs from reviewed rendered artifact')
        pe=[x for x in compiled if x['spec']['policyRef']=={'name':pm['name'],'namespace':'apps'}]
        require(len(pe)==1,'Compiled policy missing/duplicate');pe=pe[0];owner=pe['metadata'].get('ownerReferences',[])
        require(pe['metadata'].get('namespace')=='apps' and pe['metadata'].get('uid') and len(owner)==1
                and owner[0].get('kind')=='NetworkPolicy' and owner[0].get('name')==pm['name'] and owner[0].get('uid')==pm['uid']
                and owner[0].get('controller') is True and pe['spec']['podSelector']==policy['spec']['podSelector']
                and set(pe['spec']['podIsolation'])=={'Ingress','Egress'},'Compiled policy parent/selector mismatch')
        es=[x for x in slices if x['metadata'].get('labels',{}).get('kubernetes.io/service-name')==name]
        require(len(es)==1,'Service slice missing/duplicate');es=es[0];owner=es['metadata'].get('ownerReferences',[])
        require(es['metadata'].get('namespace')=='apps' and es['metadata'].get('uid') and len(owner)==1
                and owner[0].get('kind')=='Service' and owner[0].get('name')==name and owner[0].get('uid')==service_uids[name]
                and es['ports']==[{'name':'http','port':8080,'protocol':'TCP'}],'Service generation/port mismatch')
        targets=[]
        for endpoint in es['endpoints']:
            ref=endpoint['targetRef'];conditions=endpoint['conditions']
            require(ref.get('kind')=='Pod' and ref.get('namespace')=='apps' and ref.get('uid') and ref.get('name')
                    and conditions.get('ready') is True and conditions.get('serving') is True and conditions.get('terminating') is False
                    and len(endpoint['addresses'])==1,'Unready/unbound destination')
            targets.append((ref['name'],endpoint['addresses'][0],ref['uid']))
        require(targets and len(set(targets))==len(targets),'Duplicate/empty destination')
        actual=[(x['name'],x['podIP']) for x in pe['spec']['podSelectorEndpoints'] if x['namespace']=='apps']
        require(len(actual)==len(pe['spec']['podSelectorEndpoints']) and len(set(actual))==len(actual)
                and set(actual)=={(n,ip) for n,ip,uid in targets},'Compiled targets and ready Service targets differ')
        ready[name]={ip for n,ip,uid in targets};selected[name]=pe
        bindings.append({'service':name,'serviceUid':service_uids[name],'policyUid':pm['uid'],'compiledUid':pe['metadata']['uid'],
                         'readyPodUids':sorted(uid for n,ip,uid in targets),'policySpecSha256':hashlib.sha256(json.dumps(policy['spec'],sort_keys=True).encode()).hexdigest()})
    for name,pe in selected.items():
        policy=next(x for x in policies if x['metadata']['name']==name.replace('-service','-runtime-boundary'))
        ingress=set()
        for rule in policy['spec'].get('ingress',[]):
            require(rule.get('ports')==[{'port':8080,'protocol':'TCP'}],'Unsupported captured ingress contract')
            for peer in rule['from']:
                if set(peer)=={'ipBlock'}:ingress.add(peer['ipBlock']['cidr'])
                else:
                    require(peer.get('namespaceSelector')=={'matchLabels':{'kubernetes.io/metadata.name':'apps'}},'Unexpected peer namespace')
                    labels=peer['podSelector']['matchLabels'];require(labels.get('platform.cloud-native.io/workload')=='runtime' and labels.get('app.kubernetes.io/name') in ready,'Unbound peer selector')
                    ingress.update(ready[labels['app.kubernetes.io/name']])
        observed=pe['spec'].get('ingress',[])
        require(all(x.get('ports')==[{'port':8080,'protocol':'TCP'}] and set(x)=={'cidr','ports'} for x in observed)
                and len({x['cidr'] for x in observed})==len(observed) and {x['cidr'] for x in observed}==ingress,'Compiled ingress differs from selected source policy')
    for record in receipt['records']:
        source=record['source']+'-service';pe=selected[source]
        for sample in record['samples']:
            target=sample['target']+'-service';addresses=set(sample['addresses'])|ready[target]
            rules=[x for x in pe['spec']['egress'] if any(y.get('port')==8080 and y.get('protocol')=='TCP' for y in x.get('ports',[]))]
            allows=lambda ip:any(ipaddress.ip_address(ip) in ipaddress.ip_network(x['cidr'],strict=False)
                                and not any(ipaddress.ip_address(ip) in ipaddress.ip_network(z,strict=False) for z in x.get('except',[])) for x in rules)
            require(all(allows(ip)==FLOW[record['source'],sample['target']] for ip in addresses),'Compiled egress contradicts observed flow')
    jobs=capture['jobs'];require(len(jobs)==3,'Probe Jobs missing/extra')
    cleanup={x['name']:x for x in receipt['cleanup'] if x['kind']=='jobs'}
    for origin in ('auth','shipment','tracking'):
        name='current-profile-probe-'+run+'-'+origin;found=[x for x in jobs if x['metadata']['name']==name]
        require(len(found)==1,'Probe origin missing');job=found[0];labels=job['spec']['template']['metadata']['labels']
        selector=next(x for x in policies if x['metadata']['name']==origin+'-runtime-boundary')['spec']['podSelector']['matchLabels']
        require(job['metadata']['namespace']=='apps' and job['metadata']['labels'].get('platform.cloud-native.io/validation-run')==run
                and all(labels.get(k)==v for k,v in selector.items()) and 'app.kubernetes.io/instance' not in labels
                and job['status'].get('succeeded')==1 and job['spec']['backoffLimit']==0 and job['spec']['activeDeadlineSeconds']==180
                and job['spec']['template']['spec'].get('automountServiceAccountToken') is False
                and cleanup.get(name,{}).get('uid')==job['metadata']['uid'] and cleanup[name].get('deletedNormally') is True,'Probe selection/provenance/cleanup mismatch')
    return {'status':'CAPTURED_NETWORK_BINDINGS_ACCEPTED','runId':run,'bindings':bindings,'liveCertification':False,
            'limit':'Historical policy/compiled endpoint/ready Service snapshot only; separate pod lists from other rollout moments are not joined.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('observe')
    manifest = sub.add_parser('manifest'); manifest.add_argument('--run-id', required=True)
    http = sub.add_parser('http-phase'); http.add_argument('--run-http', action='store_true', required=True)
    http.add_argument('--api-id', required=True); http.add_argument('--phase', choices=PHASES, required=True)
    http.add_argument('--private-input', type=Path, required=True)
    evaluate = sub.add_parser('evaluate'); evaluate.add_argument('--http', type=Path, required=True)
    evaluate.add_argument('--network', type=Path, required=True); evaluate.add_argument('--run-id', required=True)
    args = p.parse_args()
    if args.command == 'observe': result = observe()
    elif args.command == 'manifest': result = manifests(args.run_id)
    elif args.command == 'http-phase': result = http_phase(args.api_id, args.phase, json.loads(args.private_input.read_text()))
    else:
        result = {'http': evaluate_http(json.loads(args.http.read_text())),
                  'network': evaluate_network(json.loads(args.network.read_text()), args.run_id),
                  'liveCertification': False, 'note': 'Raw provenance, actual TTL/routes/CNI bindings, restoration and teardown still require review.'}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('STOP: preparation/read/receipt validation failed; no sensitive error body emitted')
