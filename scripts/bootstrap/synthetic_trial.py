"""Render isolated synthetic data configuration locally; never invoke a cloud tool.

This does not configure bootstrap/CD, provision a backend, qualify retirement or
admit execution. Network and encryption inputs have no dev/historical fallback.
"""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import unquote
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'infra/trials/synthetic-data/protected-resources.json'
SERVICES = ('auth', 'shipment', 'tracking')
SECRET_KEYS = tuple(f'{s}-{role}-db' for s in SERVICES for role in ('runtime', 'migration')) + (
    'internal-trust', 'bootstrap-admin', 'auth-jwt', 'gateway-trust')
BINDING_KEYS = {'vpc_id', 'private_subnet_ids', 'workload_security_group_ids', 'event_kms_key_arn'}


def require(condition, code):
    if not condition:
        # No supplied value is included: a rejected input might contain a secret.
        raise ValueError(code)


def protection_policy():
    policy = json.loads(POLICY.read_text(encoding='utf-8'))
    require(policy['schemaVersion'] == 1 and policy['identifiers'] and
            policy['forbiddenPrefixes'], 'PROTECTION_POLICY_INVALID')
    return policy


def trial_identity(trial_id):
    require(type(trial_id) is str, 'TRIAL_ID_INVALID')
    try:
        parsed = UUID(trial_id)
    except (ValueError, AttributeError):
        raise ValueError('TRIAL_ID_INVALID') from None
    require(str(parsed) == trial_id and parsed.version == 4, 'TRIAL_ID_INVALID')
    return parsed


def reject_protected(value, policy=None):
    policy = protection_policy() if policy is None else policy
    forbidden = (*policy['identifiers'], *policy['forbiddenPrefixes'])

    def visit(item):
        if isinstance(item, dict):
            for key, child in item.items():
                visit(key)
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str):
            normalized = unquote(unquote(item)).casefold()
            require(not any(token.casefold() in normalized for token in forbidden),
                    'PROTECTED_REFERENCE_FORBIDDEN')
    visit(value)
    return value


def validate_bindings(bindings):
    """Check explicitly supplied IDs only; none are obtained or fabricated here."""
    require(type(bindings) is dict and set(bindings) == BINDING_KEYS, 'BINDINGS_FIELDS_INVALID')
    reject_protected(bindings)
    for key in ('private_subnet_ids', 'workload_security_group_ids'):
        require(type(bindings[key]) is list and all(type(v) is str for v in bindings[key]),
                'BINDINGS_TYPE_INVALID')
        require(len(bindings[key]) == len(set(bindings[key])), 'BINDINGS_DUPLICATE')
    require(len(bindings['private_subnet_ids']) in (2, 3) and
            1 <= len(bindings['workload_security_group_ids']) <= 2, 'BINDINGS_COVERAGE_INVALID')
    for key, values, pattern in (
        ('vpc_id', [bindings['vpc_id']], r'vpc-[0-9a-f]{17}'),
        ('private_subnet_ids', bindings['private_subnet_ids'], r'subnet-[0-9a-f]{17}'),
        ('workload_security_group_ids', bindings['workload_security_group_ids'], r'sg-[0-9a-f]{17}'),
    ):
        require(all(type(v) is str and re.fullmatch(pattern, v) for v in values), 'BINDINGS_ID_INVALID')
    p = protection_policy()
    pattern = (rf'arn:aws:kms:{re.escape(p["region"])}:{p["accountId"]}:key/'
               r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
    require(type(bindings['event_kms_key_arn']) is str and
            re.fullmatch(pattern, bindings['event_kms_key_arn']), 'BINDINGS_KEY_INVALID')
    return bindings


def configuration(trial_id):
    run = trial_identity(trial_id)
    policy = protection_policy()
    # Full UUID namespaces avoid collisions between trials; compact project name
    # keeps the longest RDS/EventBridge/SQS names within native limits.
    project, environment = 'cnp', 'trial-' + run.hex
    prefix = f'{project}-{environment}'
    queue = prefix + '-shipment-events-queue'
    consumer_dlq = prefix + '-shipment-events-dlq'
    delivery_dlq = prefix + '-shipment-delivery-dlq'
    tags = {'Project': project, 'Environment': environment, 'OwnerRunId': trial_id,
            'DataClass': 'SYNTHETIC_ONLY'}
    common = {'project_name': project, 'environment': environment, 'region': policy['region'], 'tags': tags}
    module = lambda name, values: {'source': '../../../infra/modules/' + name, **common, **values}
    refs = 'concat([var.bindings.vpc_id, var.bindings.event_kms_key_arn], var.bindings.private_subnet_ids, var.bindings.workload_security_group_ids)'
    policy_file = 'jsondecode(file("${path.module}/protected-resources.json"))'
    forbidden = f'concat({policy_file}.identifiers, {policy_file}.forbiddenPrefixes)'
    not_protected = f'alltrue([for value in {refs} : !anytrue([for protected in {forbidden} : strcontains(lower(value), lower(protected))])])'
    secret_names = {
        key: f'{project}/{environment}/' + (
            'api-gateway-authorizer/' + {'auth-jwt': 'auth-service-jwt-secret', 'gateway-trust': 'platform-trusted-proxy-secret'}[key]
            if key in ('auth-jwt', 'gateway-trust') else 'runtime/' + key)
        for key in SECRET_KEYS
    }
    root = {
        'terraform': {
            'required_version': '= 1.13.4',
            'required_providers': {'aws': {'source': 'hashicorp/aws', 'version': '= 5.100.0'}},
            # Terraform's backend does not create this intended new bucket.
            # It is not the retained backend, and has no existing state lineage.
            'backend': {'s3': {'bucket': f'cnp-{policy["accountId"]}-trial-{run.hex}',
                                'key': f'synthetic-trials/{trial_id}/data/terraform.tfstate',
                                'region': policy['region'], 'encrypt': True, 'use_lockfile': True}},
        },
        'provider': {'aws': {'region': policy['region'], 'allowed_account_ids': [policy['accountId']]}},
        'variable': {'bindings': {
            'description': 'Observed, separately reviewed network/encryption IDs; no defaults or historical fallbacks.',
            'type': 'object({vpc_id=string, private_subnet_ids=list(string), workload_security_group_ids=list(string), event_kms_key_arn=string})',
            'nullable': False,
            'validation': [
                {'condition': '${' + not_protected + '}', 'error_message': 'Protected resource references are forbidden.'},
                {'condition': '${can(regex("^vpc-[0-9a-f]{17}$", var.bindings.vpc_id)) && length(var.bindings.private_subnet_ids) >= 2 && length(var.bindings.private_subnet_ids) <= 3 && length(distinct(var.bindings.private_subnet_ids)) == length(var.bindings.private_subnet_ids) && alltrue([for id in var.bindings.private_subnet_ids : can(regex("^subnet-[0-9a-f]{17}$", id))])}', 'error_message': 'Supply distinct private subnet IDs and an observed VPC ID.'},
                {'condition': '${length(var.bindings.workload_security_group_ids) >= 1 && length(var.bindings.workload_security_group_ids) <= 2 && length(distinct(var.bindings.workload_security_group_ids)) == length(var.bindings.workload_security_group_ids) && alltrue([for id in var.bindings.workload_security_group_ids : can(regex("^sg-[0-9a-f]{17}$", id))])}', 'error_message': 'Supply one or two distinct reviewed workload security groups.'},
                {'condition': '${can(regex("^arn:aws:kms:' + policy['region'] + ':' + policy['accountId'] + ':key/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", var.bindings.event_kms_key_arn))}', 'error_message': 'Supply an observed same-account/region key ARN.'},
            ],
        }},
        'module': {
            'database': module('rds', {
                'name': prefix + '-postgres', 'engine': 'postgres', 'engine_version': '15.18',
                'instance_class': 'db.t4g.micro', 'allocated_storage': 20, 'max_allocated_storage': 20,
                'database_name': 'platform', 'username': 'platform_admin',
                'vpc_id': '${var.bindings.vpc_id}', 'subnet_ids': '${var.bindings.private_subnet_ids}',
                'allowed_security_group_ids': '${var.bindings.workload_security_group_ids}', 'allowed_cidr_blocks': [],
                'publicly_accessible': False, 'storage_encrypted': True,
                'manage_master_user_password': True, 'deletion_protection': True,
                'backup_retention_period': 7, 'skip_final_snapshot': False,
                'final_snapshot_identifier': prefix + '-final',
            }),
            # Secret containers only. No values, ESO role, IAM or trust changes.
            'secrets': module('authorizer-secrets', {
                'secrets': {key: {'name': name, 'description': 'Isolated synthetic trial; no original secret value reused.', 'recovery_window_in_days': 30}
                            for key, name in secret_names.items()},
            }),
            'queues': module('sqs', {
                'event_kms_key_arn': '${var.bindings.event_kms_key_arn}',
                'queues': {
                    queue: {'dlq_name': consumer_dlq, 'create_dlq': True, 'max_receive_count': 5,
                            'visibility_timeout_seconds': 60, 'receive_wait_time_seconds': 20},
                    delivery_dlq: {'create_dlq': False, 'message_retention_seconds': 1209600, 'receive_wait_time_seconds': 20},
                },
            }),
            'events': module('eventbridge', {
                'event_bus_name': prefix + '-bus',
                'rules': {'trk-upd-shipment': {
                    'event_pattern': json.dumps({'source': ['tracking-service'], 'detail-type': ['TrackingStatusUpdated']}),
                    'target_queue_arn': '${module.queues.queue_arns["' + queue + '"]}',
                    'target_queue_url': '${module.queues.queue_urls["' + queue + '"]}',
                    'delivery_dlq_arn': '${module.queues.queue_arns["' + delivery_dlq + '"]}',
                    'delivery_dlq_url': '${module.queues.queue_urls["' + delivery_dlq + '"]}',
                    'maximum_event_age_in_seconds': 3600, 'maximum_retry_attempts': 10, 'input_path': '$.detail',
                }},
            }),
        },
        'output': {'synthetic_data': {'value': {
            'schemaVersion': 1, 'dataClass': 'SYNTHETIC_ONLY', 'trialId': trial_id,
            'database': {'host': '${module.database.db_instance_address}', 'identifier': '${module.database.db_instance_id}',
                         'masterSecretArn': '${module.database.master_user_secret_arn}'},
            'secretArns': '${module.secrets.secret_arns}',
            'eventBus': {'name': '${module.events.event_bus_name}', 'arn': '${module.events.event_bus_arn}'},
            'queueArns': '${module.queues.queue_arns}', 'queueUrls': '${module.queues.queue_urls}',
            'consumerDlqArns': '${module.queues.dlq_arns}', 'consumerDlqUrls': '${module.queues.dlq_urls}',
        }}},
    }
    return reject_protected(root, policy)


def validate_configuration(candidate, trial_id):
    reject_protected(candidate)
    require(candidate == configuration(trial_id), 'TRIAL_CONFIGURATION_DRIFT')
    return candidate


def check_artifact(path, trial_id):
    require(path.name == 'main.tf.json', 'ARTIFACT_PATH_INVALID')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'OUTPUT_SYMLINK_FORBIDDEN')
    required = {'main.tf.json', 'protected-resources.json', '.terraform.lock.hcl'}
    actual = {p.name for p in path.parent.iterdir()}
    require(required <= actual <= required | {'bindings.auto.tfvars.json'}, 'ARTIFACT_EXTRA_OR_MISSING_FILES')
    require((path.parent / 'protected-resources.json').read_bytes() == POLICY.read_bytes(), 'ARTIFACT_POLICY_CHANGED')
    require((path.parent / '.terraform.lock.hcl').read_bytes() ==
            (ROOT / 'infra/modules/rds/.terraform.lock.hcl').read_bytes(), 'ARTIFACT_LOCK_CHANGED')
    validate_configuration(json.loads(path.read_text()), trial_id)
    inputs = path.parent / 'bindings.auto.tfvars.json'
    if inputs.exists():
        values = json.loads(inputs.read_text())
        require(type(values) is dict and set(values) == {'bindings'}, 'BINDINGS_FIELDS_INVALID')
        validate_bindings(values['bindings'])


def render(trial_id, bindings=None):
    config = configuration(trial_id)
    if bindings is not None:
        validate_bindings(bindings)
    target = ROOT / '.generated/synthetic-trials' / trial_id
    # No overwrite, merge with existing state, or symlink traversal.
    require(not any(p.is_symlink() for p in (target, *target.parents)), 'OUTPUT_SYMLINK_FORBIDDEN')
    target.mkdir(parents=True, exist_ok=False)
    (target / 'main.tf.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    (target / 'protected-resources.json').write_bytes(POLICY.read_bytes())
    (target / '.terraform.lock.hcl').write_bytes((ROOT / 'infra/modules/rds/.terraform.lock.hcl').read_bytes())
    if bindings is not None:
        (target / 'bindings.auto.tfvars.json').write_text(json.dumps({'bindings': bindings}, indent=2) + '\n', encoding='utf-8')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial-id', required=True)
    parser.add_argument('--bindings', type=Path)
    parser.add_argument('--check', type=Path)
    args = parser.parse_args()
    require(not (args.bindings and args.check), 'CHECK_BINDINGS_CONFLICT')
    if args.check:
        check_artifact(args.check, args.trial_id)
        print('PASS: isolated configuration matches the reviewed local generator; execution not admitted.')
    else:
        target = render(args.trial_id, json.loads(args.bindings.read_text()) if args.bindings else None)
        print(f'Local configuration written to {target}; no IDs observed, backend created or AWS command executed.')


if __name__ == '__main__':
    main()
