"""Inspect parsed Terraform/HCL and rendered Helm, not grep-only contracts."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

import hcl2
from validate_r1 import ROOT, render
sys.path.insert(0, str(ROOT / 'scripts/bootstrap'))
from environment import require

MODULES = ('event-encryption', 'sqs', 'eventbridge', 'apigateway-core', 'apigateway-integration')


def snapshot():
    result = {}
    for name in MODULES:
        result[name] = hcl2.loads('\n'.join(p.read_text() for p in (ROOT / 'infra/modules' / name).glob('*.tf')))
    for name in ('sqs', 'eventbridge', 'iam', 'apigateway-core', 'apigateway-integration', 'ecr'):
        result['live/' + name] = hcl2.loads((ROOT / 'infra/live/dev' / name / 'terragrunt.hcl').read_text())
    def normalize(value):
        if isinstance(value, dict): return {k.strip('"'): normalize(v) for k, v in value.items()}
        if isinstance(value, list): return [normalize(v) for v in value]
        return value
    return normalize(result)


def blocks(data, kind):
    return {(type_, name): body for block in data.get(kind, []) for type_, named in block.items() for name, body in named.items()}


def decode_policy(expression):
    require(expression.startswith('${jsonencode(') and expression.endswith(')}'), 'Expected HCL jsonencode policy')
    return hcl2.loads('value = ' + expression[len('${jsonencode('):-2])['value']


def validate(data):
    kms = blocks(data['event-encryption'], 'resource')
    key = kms['aws_kms_key', 'events']
    require(key['enable_key_rotation'] is True and key['deletion_window_in_days'] == 30 and key['customer_master_key_spec'] == 'SYMMETRIC_DEFAULT', 'CMK rotation/type/deletion policy changed')
    require(key['policy'] == '${data.aws_iam_policy_document.key.json}', 'CMK lost policy')
    require(kms['aws_kms_alias', 'events']['name'] == 'alias/${var.project_name}-${var.environment}-events', 'CMK alias changed')
    statements = blocks(data['event-encryption'], 'data')['aws_iam_policy_document', 'key']['statement']
    eb = next(s for s in statements if s['sid'] == 'AllowEventBridgeDeliveryToEncryptedQueues')
    require(eb['principals'] == [{'type': 'Service', 'identifiers': ['events.amazonaws.com']}] and set(eb['actions']) == {'kms:GenerateDataKey', 'kms:Decrypt'} and eb['resources'] == ['*'], 'EventBridge KMS permissions invalid')
    require('condition' not in eb, 'Unreviewed KMS context restriction')
    require(any(s['sid'] == 'EnableAccountAdministrationAndIAMDelegation' and s['actions'] == ['kms:*'] for s in statements), 'CMK recovery path missing')
    queues = blocks(data['sqs'], 'resource')
    for name in ('this', 'dlq'):
        require(queues['aws_sqs_queue', name]['kms_master_key_id'] == '${var.event_kms_key_arn}', 'Active queues must use environment CMK')
    live = data['live/sqs']['inputs']
    require(live['event_kms_key_arn'] == '${dependency.event_encryption.outputs.key_arn}', 'SQS key must be a Terraform output')
    require(set(live['queues']) == {'${local.project_name}-${local.environment}-shipment-events-queue', '${local.project_name}-${local.environment}-shipment-delivery-dlq'}, 'Unexpected active queue scope')
    require(live['queues']['${local.project_name}-${local.environment}-shipment-events-queue']['create_dlq'] is True, 'Consumer DLQ missing')
    require(live['queues']['${local.project_name}-${local.environment}-shipment-delivery-dlq']['create_dlq'] is False, 'Delivery queue must not have another DLQ')
    eb_resources = blocks(data['eventbridge'], 'resource')
    target = eb_resources['aws_cloudwatch_event_target', 'sqs']
    require(target['arn'] == '${each.value.target_queue_arn}' and target['dead_letter_config'] == [{'arn': '${each.value.delivery_dlq_arn}'}], 'Target/DLQ wiring invalid')
    require(target['retry_policy'] == [{'maximum_event_age_in_seconds': '${each.value.maximum_event_age_in_seconds}', 'maximum_retry_attempts': '${each.value.maximum_retry_attempts}'}], 'Explicit target retry policy missing')
    for name, resource in [('queue_policy', '${each.value.target_queue_arn}'), ('delivery_queue_policy', '${each.value.delivery_dlq_arn}')]:
        statement = blocks(data['eventbridge'], 'data')['aws_iam_policy_document', name]['statement'][0]
        require(statement['actions'] == ['sqs:SendMessage'] and statement['resources'] == [resource], 'Queue policy resource/actions invalid')
        require(statement['principals'] == [{'type': 'Service', 'identifiers': ['events.amazonaws.com']}], 'Queue policy principal invalid')
        require(statement['condition'] == [{'test': 'ArnEquals', 'variable': 'aws:SourceArn', 'values': ['${aws_cloudwatch_event_rule.this[each.key].arn}']}], 'Queue SourceArn restriction missing')
    rules = data['live/eventbridge']['inputs']['rules']
    require(set(rules) == {'trk-upd-shipment'}, 'Analytics/notification must not be in active wiring')
    rule = rules['trk-upd-shipment']
    require(rule['maximum_event_age_in_seconds'] == 3600 and rule['maximum_retry_attempts'] == 10, 'Retry budget changed')
    require(rule['delivery_dlq_arn'] == '${dependency.sqs.outputs.queue_arns[local.delivery_dlq_name]}', 'Delivery DLQ must be distinct output')
    roles = data['live/iam']['inputs']['roles']
    for name, role in roles.items():
        policy = decode_policy(next(iter(role['inline_policies'].values())))
        statements = policy['Statement']
        if 'shipment' in name:
            decrypt = [s for s in statements if s['Action'] == ['kms:Decrypt']]
            require(len(decrypt) == 1 and decrypt[0]['Resource'] == '${dependency.event_encryption.outputs.key_arn}', 'Shipment lacks scoped KMS decrypt')
        elif 'tracking' in name:
            require(len(statements) == 1 and statements[0]['Action'] == ['events:PutEvents'], 'Tracking gained unnecessary KMS/SQS privileges')
    core = blocks(data['apigateway-core'], 'resource')
    require(core['aws_security_group', 'alb_frontend']['vpc_id'] == '${var.vpc_id}', 'Frontend SG not owned in expected VPC')
    inbound = core['aws_vpc_security_group_ingress_rule', 'alb_from_vpc_link']
    require(inbound['referenced_security_group_id'] == '${aws_security_group.vpc_link.id}' and inbound['security_group_id'] == '${aws_security_group.alb_frontend.id}' and inbound['from_port'] == 80 and inbound['to_port'] == 80 and 'cidr_ipv4' not in inbound, 'Frontend ingress must be VPC Link SG only')
    egress = core['aws_vpc_security_group_egress_rule', 'vpc_link_http_to_alb']
    require(egress['referenced_security_group_id'] == '${aws_security_group.alb_frontend.id}', 'VPC Link egress ownership invalid')
    integration = data['apigateway-integration']
    discovery = blocks(integration, 'data')
    require(set(discovery) == {('aws_lb', 'ingress_by_tags'), ('aws_lb_listener', 'ingress')}, 'Discovery must not use literal/name fallback')
    alb = discovery['aws_lb', 'ingress_by_tags']; listener = discovery['aws_lb_listener', 'ingress']
    require(alb['tags'] == '${var.alb_discovery_tags}' and 'arn' not in alb and 'name' not in alb, 'ALB tags required')
    condition = alb['lifecycle'][0]['postcondition'][0]['condition']
    require(all(part in condition for part in ('self.vpc_id == var.vpc_id', 'self.internal', 'self.load_balancer_type == "application"', 'var.frontend_security_group_id')), 'ALB postconditions missing')
    require(listener['load_balancer_arn'] == '${data.aws_lb.ingress_by_tags[0].arn}' and listener['port'] == '${var.alb_listener_port}', 'Listener must be discovered from ALB')
    require('self.protocol == "HTTP"' in listener['lifecycle'][0]['postcondition'][0]['condition'], 'Listener protocol gate missing')
    inputs = data['live/apigateway-integration']['inputs']
    require(not ({'alb_arn', 'alb_listener_arn', 'alb_name'} & set(inputs)), 'Hardcoded listener/ALB input forbidden')
    require(inputs['frontend_security_group_id'] == '${dependency.apigateway_core.outputs.alb_frontend_security_group_id}' and inputs['vpc_id'] == '${dependency.vpc.outputs.vpc_id}', 'Discovery identity must come from outputs')
    require(set(inputs['alb_discovery_tags']) == {'elbv2.k8s.aws/cluster', 'ingress.k8s.aws/stack', 'Project', 'Environment'}, 'Discovery tags incomplete')
    require(set(data['live/ecr']['inputs']['repositories']) == {'auth-service', 'shipment-service', 'tracking-service'}, 'Unused active ECR repositories')


def validate_hardcodes(parsed):
    def visit(value, path=''):
        if isinstance(value, dict):
            for k, v in value.items():
                if k == 'mock_outputs': continue
                if k == 'mock_outputs_allowed_terraform_commands':
                    require(set(v) <= {'init', 'validate', 'plan'}, 'Mocks allowed in runtime command')
                visit(v, path + '/' + k)
        elif isinstance(value, list):
            for v in value: visit(v, path)
        elif isinstance(value, str):
            require(not re.search(r'(?<![A-Za-z0-9])(?:sg|subnet|vpc|vpce|i)-[0-9a-f]{8,17}(?![A-Za-z0-9])|(?<![0-9])[0-9]{12}(?![0-9])|arn:aws:elasticloadbalancing:[^\s]+', value), 'Active hardcoded AWS identifier at ' + path)
    visit(parsed)


def validate_ingress(documents):
    ingress = next(d for d in documents if d and d['kind'] == 'Ingress')
    annotations = ingress['metadata']['annotations']
    require(annotations['alb.ingress.kubernetes.io/security-groups'] == 'sg-123456789abcdef12', 'Ingress ignored generated SG')
    require(annotations['alb.ingress.kubernetes.io/manage-backend-security-group-rules'] == 'true', 'LBC backend management missing')
    require('alb.ingress.kubernetes.io/inbound-cidrs' not in annotations, 'Old VPC CIDR ingress annotation retained')
    require('Project=r2-fixture' in annotations['alb.ingress.kubernetes.io/tags'], 'Discovery tags not rendered')


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--helm', default=os.environ.get('HELM_BIN', 'helm')); args = parser.parse_args()
    validate(snapshot())
    for file in (ROOT / 'infra/live').rglob('*.hcl'):
        if '.terragrunt-cache' in file.parts: continue
        validate_hardcodes(hcl2.loads(file.read_text()))
    import yaml
    for file in (ROOT / 'k8s/environments').glob('*/platform-services.values.yaml'):
        validate_hardcodes(yaml.safe_load(file.read_text()))
        validate_ingress(render(args.helm, file))
    require(not (ROOT / 'infra/live/dev/notification-lambda/terragrunt.hcl').exists(), 'Optional notification must not be an active stack')
    print('R2 parsed IaC, encryption, event scope, SG ownership, discovery, hardcodes and rendered Ingress: PASS')


if __name__ == '__main__': main()
