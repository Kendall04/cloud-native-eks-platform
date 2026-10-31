"""Offline current-profile network/cache contracts. No AWS clients or live state."""
import os
import hcl2
from validate_r1 import ROOT, require
from validate_r3 import platform_render


def peer(service):
    return {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'apps'}},
            'podSelector': {'matchLabels': {'app.kubernetes.io/name': service + '-service',
                                          'platform.cloud-native.io/workload': 'runtime'}}}


def validate_network(documents, private_cidrs):
    policies = [d for d in documents if d.get('kind') == 'NetworkPolicy']
    require(len(policies) == 3, 'Exactly three runtime policies required')
    require(len(set(private_cidrs)) == 3 and all(c != '0.0.0.0/0' for c in private_cidrs), 'Private subnet fixture invalid')
    objects = {d['metadata']['name']: d for d in policies}
    require(set(objects) == {s + '-runtime-boundary' for s in ('auth', 'shipment', 'tracking')}, 'Unexpected runtime policy identity')
    subnets = [{'ipBlock': {'cidr': cidr}} for cidr in private_cidrs]
    tcp = lambda port: [{'protocol': 'TCP', 'port': port}]
    for service in ('auth', 'shipment', 'tracking'):
        ingress = [{'from': subnets, 'ports': tcp(8080)}]
        if service == 'shipment': ingress.append({'from': [peer('tracking')], 'ports': tcp(8080)})
        if service == 'auth':
            ingress += [{'from': [peer(caller)], 'ports': tcp(8080)} for caller in ('shipment', 'tracking')]
        egress = [
            {'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                     'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
             'ports': [{'protocol': 'UDP', 'port': 53}, {'protocol': 'TCP', 'port': 53}]},
            {'to': subnets, 'ports': tcp(5432)},
            {'to': [{'ipBlock': {'cidr': '0.0.0.0/0', 'except': private_cidrs}}], 'ports': tcp(443)}]
        if service in ('shipment', 'tracking'): egress.append({'to': [peer('auth')], 'ports': tcp(8080)})
        if service == 'tracking': egress.append({'to': [peer('shipment')], 'ports': tcp(8080)})
        expected = {'podSelector': peer(service)['podSelector'], 'policyTypes': ['Ingress', 'Egress'],
                    'ingress': ingress, 'egress': egress}
        actual = objects[service + '-runtime-boundary']
        require(actual['apiVersion'] == 'networking.k8s.io/v1' and actual['metadata']['namespace'] == 'apps', 'Wrong network boundary')
        require(actual['spec'] == expected, 'Unreviewed network policy rule/selector/port: ' + service)


def validate_cache(variables, core, live):
    values = {key: value for row in variables['variable'] for key, value in row.items()}
    ttl = values['jwt_authorizer_result_ttl_in_seconds']
    require(ttl['type'] == 'number' and type(ttl['default']) is int and ttl['default'] == 0, 'Authorizer result caching must default to zero')
    authorizers = {name: value for row in core['resource'] for name, value in row.get('aws_apigatewayv2_authorizer', {}).items()}
    require(set(authorizers) == {'jwt'}, 'Unreviewed authorizer')
    authorizer = authorizers['jwt']
    require(authorizer['authorizer_result_ttl_in_seconds'] == '${var.jwt_authorizer_result_ttl_in_seconds}', 'Result TTL bypasses reviewed variable')
    require(authorizer['authorizer_type'] == 'REQUEST' and authorizer['identity_sources'] == '${var.jwt_authorizer_identity_sources}', 'Authorizer identity boundary changed')
    override = live['inputs'].get('jwt_authorizer_result_ttl_in_seconds', 0)
    require(type(override) is int and override == 0, 'Live inputs re-enable result caching')


def cache_snapshot():
    return tuple(hcl2.loads((ROOT / path).read_text(encoding='utf-8')) for path in (
        'infra/modules/apigateway-core/variables.tf', 'infra/modules/apigateway-core/main.tf',
        'infra/live/dev/apigateway-core/terragrunt.hcl'))


if __name__ == '__main__':
    documents, fixture = platform_render(os.environ.get('HELM_BIN', 'helm'))
    validate_network(documents, fixture['network']['privateSubnetCidrs'])
    validate_cache(*cache_snapshot())
    print('Current-profile exact network rules and authorizer result TTL 0: PASS')
