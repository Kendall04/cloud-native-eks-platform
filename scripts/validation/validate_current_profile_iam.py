"""Offline grammar, size, provenance and source-coverage checks for three IAM proposals.

The small decision helper supports only the operators these proposals contain. It is
not AWS IAM simulation and cannot establish effective permissions, SCP or live access.
"""
from fnmatch import fnmatchcase
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / 'docs/operations/current-profile-iam'
NAMES = {f'cnp-cert-{kind}-workload-boundary' for kind in ('eks', 'app', 'management')}
ACCOUNT = '341936017254'


def require(condition, message):
    if not condition: raise ValueError(message)


def sequence(value): return value if isinstance(value, list) else [value]
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
def actions(document): return {a for s in document['Statement'] for a in sequence(s['Action'])}


def validate_shape(document):
    require(set(document) == {'Version', 'Statement'} and document['Version'] == '2012-10-17', 'Unexpected policy document')
    require(isinstance(document['Statement'], list) and document['Statement'], 'Missing statements')
    require(len(canonical(document)) <= 6144, 'Managed policy exceeds IAM 6144-character limit')
    for statement in document['Statement']:
        require(set(statement) <= {'Sid', 'Effect', 'Action', 'Resource', 'Condition'} and
                {'Effect', 'Action', 'Resource'} <= set(statement), 'Unsupported IAM grammar')
        require(statement['Effect'] == 'Allow', 'Only recovered Allow ceilings are supported')
        require(all(isinstance(a, str) and re.fullmatch('[a-z0-9-]+:[A-Za-z0-9]+', a)
                    for a in sequence(statement['Action'])), 'Action wildcard or invalid IAM action')
        resources = sequence(statement['Resource'])
        require(resources and all(isinstance(r, str) and (r == '*' or r.startswith('arn:aws:')) for r in resources), 'Invalid resource')
        conditions = statement.get('Condition', {})
        require(isinstance(conditions, dict) and set(conditions) <= {'StringEquals', 'StringLike'}, 'Unsupported condition operator')
        for operator, entries in conditions.items():
            require(isinstance(entries, dict) and entries, 'Invalid condition entries')
            require(all(isinstance(k, str) and all(isinstance(v, str) for v in sequence(values))
                        for k, values in entries.items()), 'Invalid condition values')


def boundary_allows(document, action, resource, context):
    validate_shape(document)
    for statement in document['Statement']:
        if action.lower() not in {a.lower() for a in sequence(statement['Action'])}: continue
        if not any(fnmatchcase(resource, r) for r in sequence(statement['Resource'])): continue
        matched = True
        for operator, entries in statement.get('Condition', {}).items():
            for key, values in entries.items():
                supplied = sequence(context.get(key, []))
                wanted = sequence(values)
                matched &= any((actual == expected if operator == 'StringEquals' else fnmatchcase(actual, expected))
                               for actual in supplied for expected in wanted)
        if matched: return True
    return False


def validate(directory=DIRECTORY, root=ROOT):
    manifest = json.loads((directory / 'manifest.json').read_text())
    require(manifest['classification'] == 'LOCAL_REVIEW_PROPOSAL_NOT_APPLIED' and manifest['schemaVersion'] == 1,
            'Not a review-only proposal')
    require((manifest['accountId'], manifest['profile'], manifest['region']) ==
            (ACCOUNT, 'cnp-cert-dev', 'us-east-1'), 'Wrong execution identity')
    require(len(manifest['policies']) == 3 and {p['policyName'] for p in manifest['policies']} == NAMES, 'Unexpected CreatePolicy scope')
    documents = {}
    for item in manifest['policies']:
        name = item['policyName']
        require(item['document'] == name + '.json' and item['path'] == '/' and
                item['expectedArn'] == f'arn:aws:iam::{ACCOUNT}:policy/{name}', 'Wrong policy target or path')
        require(item['tags'] == {'Project': 'cloud-native-platform', 'Environment': 'dev',
                'Owner': 'platform-team', 'Purpose': 'current-profile-validation'}, 'Wrong creation ownership tags')
        raw = (directory / item['document']).read_bytes().replace(b'\r\n', b'\n')
        doc = json.loads(raw)
        validate_shape(doc)
        require(hashlib.sha256(raw).hexdigest() == item['sha256LF'] and
                hashlib.sha256(canonical(doc)).hexdigest() == item['canonicalSha256'], 'Unreviewed policy bytes')
        require(len(actions(doc)) == item['actionCount'] and len(canonical(doc)) == item['compactCharacters'], 'Policy inventory drift')
        documents[name] = doc
    managed = manifest['awsManagedPolicyObservations']
    require(set(managed) == {'AmazonEKSClusterPolicy', 'AmazonEKSWorkerNodePolicy', 'AmazonEC2ContainerRegistryPullOnly',
                            'AmazonEKS_CNI_Policy', 'service-role/AmazonEBSCSIDriverPolicy'}, 'Unexpected managed-policy inputs')
    expected = {action for row in managed.values() for action in row['actions']}
    expected |= actions(json.loads((root / 'infra/modules/eks/policies/aws-load-balancer-controller-iam-policy.json').read_text()))
    eks_source = (root / 'infra/modules/eks/main.tf').read_text()
    section = eks_source[eks_source.index('data "aws_iam_policy_document" "cluster_autoscaler"'):
                         eks_source.index('resource "aws_iam_policy" "cluster_autoscaler"')]
    expected |= set(re.findall(r'"([a-z0-9-]+:[A-Za-z0-9]+)"', section))
    eks = documents['cnp-cert-eks-workload-boundary']
    require(actions(eks) == expected, 'Recovered EKS cap differs from actual declared grants/observed AWS versions')
    slr = [s for s in eks['Statement'] if 'iam:CreateServiceLinkedRole' in sequence(s['Action'])]
    require(len(slr) == 1 and slr[0]['Resource'] ==
            f'arn:aws:iam::{ACCOUNT}:role/aws-service-role/elasticloadbalancing.amazonaws.com/*' and
            slr[0]['Condition'] == {'StringEquals': {'iam:AWSServiceName': 'elasticloadbalancing.amazonaws.com'}}, 'Service-linked role scope widened')
    expected_app = set()
    for path in ('infra/live/dev/iam/terragrunt.hcl', 'infra/modules/runtime-secrets/main.tf', 'infra/modules/observability/main.tf'):
        expected_app |= set(re.findall(r'"([a-z0-9-]+:[A-Za-z0-9]+)"', (root / path).read_text()))
    expected_app.discard('sts:AssumeRoleWithWebIdentity')  # Trust is not an identity permission grant.
    app = documents['cnp-cert-app-workload-boundary']
    require(actions(app) == expected_app, 'App cap differs from actual inline grants')
    secret_statement = [s for s in app['Statement'] if 'secretsmanager:GetSecretValue' in sequence(s['Action'])]
    require(len(secret_statement) == 1 and set(sequence(secret_statement[0]['Resource'])) == {
        f'arn:aws:secretsmanager:us-east-1:{ACCOUNT}:secret:cloud-native-platform/dev/runtime/*',
        f'arn:aws:secretsmanager:us-east-1:{ACCOUNT}:secret:cloud-native-platform/dev/api-gateway-authorizer/auth-service-jwt-secret-*',
        f'arn:aws:secretsmanager:us-east-1:{ACCOUNT}:secret:cloud-native-platform/dev/api-gateway-authorizer/platform-trusted-proxy-secret-*'}, 'ESO secret paths differ from current source')
    require(all(s.get('Condition', {}).get('StringEquals', {}).get('aws:RequestedRegion') == 'us-east-1'
                for s in app['Statement']), 'App region ceiling lost')
    current = json.loads((root / 'infra/operator-policies/cnp-cert-management-workload-boundary.json').read_text())
    require(documents['cnp-cert-management-workload-boundary'] == current, 'Existing management boundary changed')
    return documents


if __name__ == '__main__':
    result = validate()
    print('IAM proposals: PASS (three exact targets; finite actions; <=6144 characters; source coverage; no AWS calls)')
