"""Closed synthetic contract, shared by the existing producer and host consumer.

Pure validation only. No identity discovery, permissions, execution or admission.
"""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote
from uuid import UUID

SYNTHETIC_VERSION = '1.5.0'
HERE = Path(__file__).resolve().parent
SECRET_KEYS = tuple(f'{s}-{p}-db' for s in ('auth', 'shipment', 'tracking') for p in ('runtime', 'migration')) + (
    'internal-trust', 'bootstrap-admin', 'auth-jwt', 'gateway-trust')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def reject_protected(value):
    policy = json.loads((HERE / 'synthetic-protected-resources.json').read_text())
    forbidden = policy['identifiers'] + policy['forbiddenPrefixes']
    def visit(item):
        if isinstance(item, dict):
            for key, child in item.items(): visit(key); visit(child)
        elif isinstance(item, list):
            for child in item: visit(child)
        elif isinstance(item, str):
            text = unquote(unquote(item)).casefold()
            require(not any(v.casefold() in text for v in forbidden), 'Synthetic protected reference forbidden')
    visit(value)


def check_schema(value, spec):
    kind = spec['type']
    if isinstance(kind, list):
        if value is None and 'null' in kind: return
        kind = next(k for k in kind if k != 'null')
    require(type(value) is {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool}[kind], 'Synthetic field type mismatch')
    if kind == 'object':
        require(set(value) == set(spec['properties']), 'Synthetic fields missing or unknown')
        for key, child in value.items(): check_schema(child, spec['properties'][key])
    if kind == 'array':
        require(len(value) >= spec.get('minItems', 0), 'Synthetic array incomplete')
        for child in value: check_schema(child, spec['items'])
    if 'const' in spec: require(value == spec['const'], 'Synthetic constant mismatch')
    if 'pattern' in spec: require(re.fullmatch(spec['pattern'], value), 'Synthetic identifier mismatch')


def scope_identity(scope):
    require(type(scope) is dict and set(scope) == {'mode', 'trialId', 'environment', 'namespace', 'bindingSha256'}, 'Explicit synthetic scope required')
    require(scope['mode'] == 'SYNTHETIC_ONLY', 'Synthetic mode required')
    try: run = UUID(scope['trialId'])
    except (ValueError, TypeError, AttributeError): raise ValueError('Synthetic UUID required') from None
    require(str(run) == scope['trialId'] and run.version == 4, 'Canonical synthetic UUIDv4 required')
    require(scope['environment'] == 'trial-' + run.hex and scope['namespace'] == 'cnp-trial-' + run.hex, 'Synthetic namespace/environment mismatch; no dev fallback')
    require(type(scope['bindingSha256']) is str and re.fullmatch('[0-9a-f]{64}', scope['bindingSha256']), 'Synthetic binding hash required')
    return scope


def binding_hash(c):
    return canonical_hash({k: v for k, v in c.items() if k != 'dataScope'})


def validate_environment(c, expected_scope=None):
    check_schema(c, json.loads((HERE / 'environment.synthetic.schema.json').read_text()))
    scope = scope_identity(c['dataScope'])
    require(c['environment'] == scope['environment'] and c['project'] == 'cnp', 'Synthetic deployment environment mismatch')
    require(scope['bindingSha256'] == binding_hash(c), 'Synthetic binding integrity mismatch')
    if expected_scope is not None:
        require(scope == scope_identity(expected_scope), 'Synthetic trusted target mismatch')
    reject_protected(c)
    serialized = json.dumps(c)
    require(not re.search(r'123456789012|000000000000|(?:sg|vpc|subnet)-([0-9a-f])\1{7,}|EXAMPLE|replace-me|AKIA[0-9A-Z]{16}|-----BEGIN|(?i:password|jwtsecret|proxysecret|accesskey|sessiontoken|connectionstring)', serialized), 'Synthetic mock/secret material forbidden')
    a, r, n = c['accountId'], c['region'], scope['namespace']
    policy = json.loads((HERE / 'synthetic-protected-resources.json').read_text())
    require(a == policy['accountId'] and r == policy['region'], 'Synthetic account/region mismatch')
    require(c['clusterName'].startswith(n + '-'), 'Explicit trial cluster required')
    require(len(set(c['privateSubnetIds'])) == len(c['privateSubnetIds']) and len(c['privateSubnetIds']) <= 3, 'Distinct synthetic subnets required')
    require(c['database']['host'].startswith(n + '-postgres.'), 'Synthetic DB host namespace mismatch')
    require(c['database']['masterSecretArn'].startswith(f'arn:aws:secretsmanager:{r}:{a}:secret:rds!db-'), 'Explicit new RDS master secret required')
    require(len(set(c['secrets'].values())) == 10, 'Distinct synthetic secrets required')
    for key, arn in c['secrets'].items():
        shared = {'auth-jwt': 'auth-service-jwt-secret', 'gateway-trust': 'platform-trusted-proxy-secret'}
        path = 'api-gateway-authorizer/' + shared[key] if key in shared else 'runtime/' + key
        require(re.fullmatch(re.escape(f'arn:aws:secretsmanager:{r}:{a}:secret:cnp/{scope["environment"]}/{path}-') + '[A-Za-z0-9]{6}', arn), 'Synthetic secret namespace mismatch')
    roles = [c['esoRoleArn'], *c['workloadRoles'].values(), *c['addons'].values()]
    require(len(set(roles)) == len(roles), 'Distinct explicit synthetic role bindings required')
    for role in roles:
        require(re.fullmatch(re.escape(f'arn:aws:iam::{a}:role/{n}-') + '[A-Za-z0-9_-]{1,21}', role), 'Explicit namespaced synthetic role required')
    require(c['eventBus'] == {'name': n + '-bus', 'arn': f'arn:aws:events:{r}:{a}:event-bus/{n}-bus'}, 'Synthetic event bus mismatch')
    for prefix, suffix in (('', '-shipment-events-queue'), ('consumerDlq', '-shipment-events-dlq'), ('deliveryDlq', '-shipment-delivery-dlq')):
        ak, uk = (prefix + 'Arn', prefix + 'Url') if prefix else ('arn', 'url')
        name = n + suffix
        require(c['shipmentQueue'][ak] == f'arn:aws:sqs:{r}:{a}:{name}' and c['shipmentQueue'][uk] == f'https://sqs.{r}.amazonaws.com/{a}/{name}', 'Synthetic queue namespace mismatch')
    enc = c['eventEncryption']
    require(enc['keyArn'] == f'arn:aws:kms:{r}:{a}:key/{enc["keyId"]}' and enc['alias'] == f'alias/{n}-events', 'Explicit synthetic encryption binding mismatch')
    require(c['alb']['discoveryTags'] == {'elbv2.k8s.aws/cluster': c['clusterName'], 'ingress.k8s.aws/stack': n, 'Project': 'cnp', 'Environment': scope['environment']}, 'Synthetic ALB tags mismatch')
    for service, repo in c['repositories'].items():
        require(repo == f'{a}.dkr.ecr.{r}.amazonaws.com/{service}-service', 'Synthetic image repository mismatch')
    require(c['apiGateway']['endpoint'] == f'https://{c["apiGateway"]["apiId"]}.execute-api.{r}.amazonaws.com', 'Synthetic API mismatch')
    # The snapshot contains canonical API ARNs, while environment fields carry
    # short IDs/URLs. Reconstruct the identity before the protected lookup.
    reject_protected([f'arn:aws:apigateway:{r}::/apis/{c["apiGateway"]["apiId"]}',
                      f'arn:aws:apigateway:{r}::/vpclinks/{c["apiGateway"]["vpcLinkId"]}'])
    for value in (c['alb']['arn'], c['alb']['listenerArn']):
        if value is not None: require(value.startswith(f'arn:aws:elasticloadbalancing:{r}:{a}:'), 'Synthetic ALB account mismatch')
    require((c['alb']['arn'] is None) == (c['alb']['listenerArn'] is None), 'Partial synthetic ALB')
    if c['alb']['arn'] is not None:
        require(c['alb']['listenerArn'].split(':listener/')[1].startswith(c['alb']['arn'].split(':loadbalancer/')[1] + '/'), 'Synthetic listener parent mismatch')
    return c


def validate_values(values, c):
    reject_protected(values)
    for service in ('auth', 'shipment', 'tracking'):
        env = values['services'][service]['env']
        require(env['Database__Host'] == c['database']['host'] and env['Telemetry__Environment'] == c['environment'], 'Synthetic workload data/environment mismatch')
    require(values['services']['tracking']['env']['AWS__EventBusName'] == c['eventBus']['name'], 'Synthetic workload bus mismatch')
    shipment = values['services']['shipment']
    require(shipment['env']['AWS__ShipmentEventsQueueUrl'] == c['shipmentQueue']['url'] and shipment['keda']['queueURL'] == c['shipmentQueue']['url'], 'Synthetic workload queue mismatch')


def publication_scope(environment):
    """Explicit platform-owned inputs, never inferred from an untrusted bundle."""
    raw = environment.get('SYNTHETIC_DATA_SCOPE')
    if raw is None:
        require(environment.get('DEPLOYMENT_ENVIRONMENT', 'dev') == 'dev', 'Synthetic scope missing; no dev fallback')
        return 'dev', None
    require('DEPLOYMENT_ENVIRONMENT' in environment, 'Explicit synthetic environment required')
    scope = scope_identity(json.loads(raw))
    require(environment['DEPLOYMENT_ENVIRONMENT'] == scope['environment'], 'Publication environment/scope mismatch')
    return scope['environment'], scope


def target_environment(target):
    if 'dataScope' in target:
        scope = scope_identity(target['dataScope'])
        require(target['environment'] == scope['environment'], 'Target environment/scope mismatch')
        reject_protected(target)
        require(target['clusterName'].startswith(scope['namespace'] + '-'), 'Explicit synthetic cluster binding required')
        require(target['shipmentQueueUrl'] == f'https://sqs.{target["region"]}.amazonaws.com/{target["accountId"]}/{scope["namespace"]}-shipment-events-queue', 'Explicit synthetic queue binding required')
        return scope['environment']
    require(target['environment'] == 'dev', 'Synthetic target scope required; no dev fallback')
    return 'dev'
