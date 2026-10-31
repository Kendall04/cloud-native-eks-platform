"""R2 negative regressions and pure bootstrap/discovery tests. Never use AWS."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validate_r2 import snapshot, validate, validate_hardcodes, blocks, validate_ingress
from validate_r1 import ROOT, render
from environment import build_contract, validate_contract, overlay
from bootstrap import select_alb, select_listener, wait_for, images_overlay, CORE, require_egress_admission


class NatAdmissionTests(unittest.TestCase):
    def test_instance_mode_requires_explicit_boolean_activation(self):
        for value in (False, None, 'true', 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                require_egress_admission({'nat_mode': 'instance', 'nat_recovery_enabled': value})

    def test_reviewed_activation_and_gateway_mode_are_accepted(self):
        require_egress_admission({'nat_mode': 'instance', 'nat_recovery_enabled': True})
        require_egress_admission({'nat_mode': 'gateway', 'nat_recovery_enabled': False})

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError): require_egress_admission({})

    def test_inhibited_phase_one_stops_before_aws_output_or_terragrunt(self):
        import bootstrap
        with patch('bootstrap.environment_settings', return_value={'nat_mode': 'instance', 'nat_recovery_enabled': False}), \
             patch('bootstrap.command') as command, patch('bootstrap.run') as run, \
             patch('bootstrap.output') as output, patch('bootstrap.generate') as generate:
            with self.assertRaisesRegex(ValueError, 'inhibited'): bootstrap.phase(1, 'dev', None)
        command.assert_not_called(); run.assert_not_called()
        output.assert_not_called(); generate.assert_not_called()


class PrivateCdAccountWiring(unittest.TestCase):
    def test_provider_arn_uses_verified_current_account(self):
        text = (ROOT / 'infra/live/dev/private-cd/terragrunt.hcl').read_text()
        self.assertIn('arn:aws:iam::${get_aws_account_id()}:oidc-provider/token.actions.githubusercontent.com', text)
        self.assertNotIn('arn:aws:iam::341936017254:oidc-provider/', text)


class PrivateOperatorContext(unittest.TestCase):
    def check(self, config):
        cluster = {'endpoint': 'https://private.example.invalid',
                   'certificateAuthority': {'data': 'test-ca'}}
        with patch.dict(os.environ, {'KUBECONFIG': '/private/operator.kubeconfig'}), \
             patch('bootstrap.verify_cluster', return_value=cluster), \
             patch('bootstrap.command', side_effect=[json.dumps({'clusters': [{'cluster': config}]}), 'ok']) as command, \
             patch('bootstrap.run') as run:
            from bootstrap import kube_context
            kube_context({'clusterName': 'fixture'})
            run.assert_not_called()
            self.assertEqual(['kubectl', 'get', '--raw=/readyz'], command.call_args.args[0])

    def test_verified_ssm_forward_reuses_context(self):
        self.check({'server': 'https://127.0.0.1:18443', 'tls-server-name': 'private.example.invalid',
                    'certificate-authority-data': 'test-ca'})

    def test_direct_verified_context_reused(self):
        self.check({'server': 'https://private.example.invalid', 'certificate-authority-data': 'test-ca'})

    def test_wrong_forward_hostname_rejected(self):
        with self.assertRaises(ValueError):
            self.check({'server': 'https://127.0.0.1:18443', 'tls-server-name': 'other.example.invalid',
                        'certificate-authority-data': 'test-ca'})

    def test_unverified_certificate_rejected(self):
        for extra in ({'insecure-skip-tls-verify': True}, {'certificate-authority-data': 'wrong-ca'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.check({'server': 'https://private.example.invalid', 'certificate-authority-data': 'test-ca', **extra})

    def test_nonloopback_forward_rejected(self):
        with self.assertRaises(ValueError):
            self.check({'server': 'https://proxy.example.invalid:18443', 'tls-server-name': 'private.example.invalid',
                        'certificate-authority-data': 'test-ca'})


def contract_fixture():
    # Synthetic TEST_FIXTURE output inventory, never accepted by generate() as a source.
    account = '999988887777'; region = 'us-east-1'; project = 'r2-fixture'; env = 'dev'
    prefix = project + '-' + env
    queue = prefix + '-shipment-events-queue'; delivery = prefix + '-shipment-delivery-dlq'
    qarn = lambda name: f'arn:aws:sqs:{region}:{account}:{name}'
    qurl = lambda name: f'https://sqs.{region}.amazonaws.com/{account}/{name}'
    key_id = 'a1b2c3d4-1234-4567-89ab-cdef12345678'
    role = lambda name: f'arn:aws:iam::{account}:role/{name}'
    outputs = {
        'vpc': {'vpc_id': 'vpc-abcdef123456789ab', 'private_subnet_ids': ['subnet-abcdef123456789ab', 'subnet-bcdef123456789abc']},
        'eks': {'vpc_id': 'vpc-abcdef123456789ab', 'cluster_name': 'r2-fixture-dev', 'aws_load_balancer_controller_role_arn': role('r2-lbc'), 'cluster_autoscaler_role_arn': role('r2-ca')},
        'event-encryption': {'key_arn': f'arn:aws:kms:{region}:{account}:key/{key_id}', 'key_id': key_id, 'alias': f'alias/{prefix}-events', 'rotation_enabled': True, 'deletion_window_in_days': 30},
        'sqs': {'queue_arns': {queue:qarn(queue), delivery:qarn(delivery)}, 'queue_urls': {queue:qurl(queue), delivery:qurl(delivery)}, 'dlq_arns':{queue:qarn(prefix+'-shipment-events-dlq')}, 'dlq_urls':{queue:qurl(prefix+'-shipment-events-dlq')}},
        'eventbridge': {'event_bus_name': prefix+'-bus', 'event_bus_arn': f'arn:aws:events:{region}:{account}:event-bus/{prefix}-bus'},
        'iam': {'role_arns': {f'{prefix}-{s}-service-irsa':role(f'{prefix}-{s}-service-irsa') for s in ('shipment','tracking')}},
        'ecr': {'repository_urls': {s+'-service': f'{account}.dkr.ecr.{region}.amazonaws.com/{s}-service' for s in ('auth','shipment','tracking')}},
        'apigateway-core': {'api_id':'r2fixture','vpc_link_id':'r2link', 'api_endpoint':f'https://r2fixture.execute-api.{region}.amazonaws.com', 'alb_frontend_security_group_id':'sg-abcdef123456789ab', 'vpc_link_security_group_id':'sg-bcdef123456789abc'},
    }
    outputs['rds']={'db_instance_address':'db.example.invalid','master_user_secret_arn':f'arn:aws:secretsmanager:{region}:{account}:secret:rds-master-fixture'}
    names=[f'{s}-{p}-db' for s in ('auth','shipment','tracking') for p in ('runtime','migration')]+['internal-trust','bootstrap-admin','auth-jwt','gateway-trust']
    paths = {n: ('api-gateway-authorizer/' + {'auth-jwt':'auth-service-jwt-secret','gateway-trust':'platform-trusted-proxy-secret'}[n] if n in ('auth-jwt','gateway-trust') else 'runtime/'+n) for n in names}
    outputs['runtime-secrets']={'secret_arns':{n:f'arn:aws:secretsmanager:{region}:{account}:secret:{project}/{env}/{paths[n]}-Aa11bb' for n in names},'eso_role_arn':role(prefix+'-external-secrets')}
    outputs['iam']['role_arns'][prefix+'-external-secrets-cert-irsa'] = role(prefix+'-external-secrets-cert-irsa')
    return build_contract({'project_name':project,'environment':env,'region':region}, account, outputs)


class IaCRegressions(unittest.TestCase):
    def setUp(self): self.data = snapshot()

    def test_baseline(self): validate(self.data)

    def test_aws_managed_key_fails(self):
        self.data['live/sqs']['inputs']['event_kms_key_arn'] = 'alias/aws/sqs'
        with self.assertRaises(ValueError): validate(self.data)

    def test_missing_eventbridge_key_permission_fails(self):
        stmt = blocks(self.data['event-encryption'], 'data')['aws_iam_policy_document','key']['statement'][1]
        stmt['actions'].remove('kms:Decrypt')
        with self.assertRaises(ValueError): validate(self.data)

    def test_shipment_decrypt_missing_fails(self):
        roles = self.data['live/iam']['inputs']['roles']
        role = next(value for name,value in roles.items() if 'shipment' in name)
        role['inline_policies']['shipment-service'] = role['inline_policies']['shipment-service'].replace('kms:Decrypt', 'kms:Encrypt')
        with self.assertRaises(ValueError): validate(self.data)

    def test_main_queue_aws_key_fails(self):
        blocks(self.data['sqs'],'resource')['aws_sqs_queue','this']['kms_master_key_id']='alias/aws/sqs'
        with self.assertRaises(ValueError): validate(self.data)

    def test_missing_target_dlq_fails(self):
        blocks(self.data['eventbridge'], 'resource')['aws_cloudwatch_event_target','sqs']['dead_letter_config'] = []
        with self.assertRaises(ValueError): validate(self.data)

    def test_analytics_target_fails(self):
        rules = self.data['live/eventbridge']['inputs']['rules']
        rules['trk-upd-analytics'] = deepcopy(rules['trk-upd-shipment'])
        with self.assertRaises(ValueError): validate(self.data)

    def test_literal_listener_fails(self):
        self.data['live/apigateway-integration']['inputs']['alb_listener_arn'] = 'arn:aws:elasticloadbalancing:us-east-1:145023118802:listener/app/old/old/old'
        with self.assertRaises(ValueError): validate(self.data)

    def test_vpc_wide_frontend_ingress_fails(self):
        rule = blocks(self.data['apigateway-core'],'resource')['aws_vpc_security_group_ingress_rule','alb_from_vpc_link']
        rule['cidr_ipv4'] = '10.0.0.0/16'
        with self.assertRaises(ValueError): validate(self.data)

    def test_historical_id_rejected_outside_mock(self):
        with self.assertRaises(ValueError): validate_hardcodes({'inputs':{'sg':'sg-079c5a1e99c17270a'}})
        validate_hardcodes({'dependency':[{'test':{'mock_outputs':{'sg':'sg-00000000000000000'}, 'mock_outputs_allowed_terraform_commands':['init','validate','plan']}}]})

    def test_mock_output_runtime_command_fails(self):
        with self.assertRaises(ValueError): validate_hardcodes({'mock_outputs_allowed_terraform_commands':['output']})


class ContractTests(unittest.TestCase):
    def setUp(self): self.c = contract_fixture()

    def test_generated_core_and_overlay(self):
        validate_contract(self.c, 'dev')
        values = overlay(self.c)
        self.assertEqual(values['global']['ingress']['frontendSecurityGroupId'], self.c['alb']['frontendSecurityGroupId'])
        self.assertEqual(values['services']['shipment']['env']['AWS__ShipmentEventsQueueUrl'], self.c['shipmentQueue']['url'])
        self.assertNotIn('serviceAccount', values['services']['tracking']) # R3: platform release owns IRSA identities
        self.assertNotIn('digest', values['services']['auth']['image'])

    def test_mock_sg_fails(self):
        self.c['alb']['frontendSecurityGroupId']='sg-00000000000000000'
        with self.assertRaises(ValueError): validate_contract(self.c,'dev')

    def test_secret_field_fails(self):
        self.c['jwtSecret']='not-a-real-secret'
        with self.assertRaises(ValueError): validate_contract(self.c,'dev')

    def test_wrong_environment_fails(self):
        with self.assertRaises(ValueError): validate_contract(self.c,'prod')

    def test_cross_account_key_fails(self):
        self.c['eventEncryption']['keyArn']=self.c['eventEncryption']['keyArn'].replace('999988887777','888877776666')
        with self.assertRaises(ValueError): validate_contract(self.c,'dev')

    def test_incomplete_contract_not_ready(self):
        with self.assertRaises(ValueError): validate_contract(self.c,'dev',ready=True)

    def test_final_contract_requires_matching_listener(self):
        prefix='arn:aws:elasticloadbalancing:us-east-1:999988887777:'
        self.c['alb']['arn']=prefix+'loadbalancer/app/test/abcdef'
        self.c['alb']['listenerArn']=prefix+'listener/app/test/abcdef/123abc'
        validate_contract(self.c,'dev',ready=True)
        self.c['alb']['listenerArn']=prefix+'listener/app/other/abcdef/123abc'
        with self.assertRaises(ValueError): validate_contract(self.c,'dev',ready=True)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.c=contract_fixture()
        self.lb={'Tags':deepcopy(self.c['alb']['discoveryTags']), 'VpcId':self.c['vpcId'], 'Scheme':'internal', 'Type':'application', 'SecurityGroups':[self.c['alb']['frontendSecurityGroupId']], 'State':{'Code':'active'}}

    def test_exact_match(self): self.assertEqual(select_alb([self.lb],self.c),self.lb)
    def test_named_target_port_checks_registered_endpoints(self):
        import bootstrap
        self.lb['LoadBalancerArn'] = 'test-alb'
        target = {'Target': {'Id': '10.0.1.2', 'Port': 8080},
                  'HealthCheckPort': '8080', 'TargetHealth': {'State': 'healthy'}}
        def query(c, service, operation, *args):
            if operation == 'describe-load-balancers': return {'LoadBalancers': [self.lb]}
            if operation == 'describe-tags':
                return {'TagDescriptions': [{'ResourceArn': 'test-alb', 'Tags': [{'Key': k, 'Value': v} for k, v in self.lb['Tags'].items()]}]}
            if operation == 'describe-listeners': return {'Listeners': [{'Port': 80, 'Protocol': 'HTTP', 'ListenerArn': 'test-listener'}]}
            if operation == 'describe-target-groups':
                return {'TargetGroups': [{'TargetGroupArn': str(i), 'TargetType': 'ip', 'Protocol': 'HTTP', 'HealthCheckPath': '/health/ready', 'Port': 1} for i in range(3)]}
            return {'TargetHealthDescriptions': [target, deepcopy(target)]}
        with patch('bootstrap.aws', side_effect=query), redirect_stdout(io.StringIO()):
            self.assertEqual(('test-alb', 'test-listener'), bootstrap.discover(self.c))
            target['Target']['Port'] = 8081
            with self.assertRaisesRegex(ValueError, 'registered target port'):
                bootstrap.discover(self.c)
    def test_zero_match_not_ready(self): self.assertIsNone(select_alb([],self.c))
    def test_multiple_fail(self):
        with self.assertRaises(ValueError): select_alb([self.lb,self.lb],self.c)
    def test_wrong_vpc_fails(self):
        self.lb['VpcId']='vpc-wrong'
        with self.assertRaises(ValueError): select_alb([self.lb],self.c)
    def test_public_fails(self):
        self.lb['Scheme']='internet-facing'
        with self.assertRaises(ValueError): select_alb([self.lb],self.c)
    def test_listener_zero_one_multiple(self):
        item={'Port':80,'Protocol':'HTTP'}
        self.assertIsNone(select_listener([])); self.assertEqual(select_listener([item]),item)
        with self.assertRaises(ValueError): select_listener([item,item])
        with self.assertRaises(ValueError): select_listener([{'Port':80,'Protocol':'HTTPS'}])
    def test_wait_requires_predicate_success(self):
        with self.assertRaises(TimeoutError): wait_for('missing ALB',lambda:False,timeout=0)
        with patch('bootstrap.time.sleep') as sleep, redirect_stdout(io.StringIO()):
            self.assertTrue(wait_for('ready',lambda:True,timeout=0))
            sleep.assert_not_called()
    def test_scope_order(self):
        self.assertLess(CORE.index('event-encryption'),CORE.index('sqs'))
        self.assertLess(CORE.index('eks'),CORE.index('rds'))
        self.assertLess(CORE.index('management'),CORE.index('rds'))
        self.assertNotIn('notification-lambda',CORE)
        self.assertNotIn('apigateway-integration',CORE)
    def test_image_file_cannot_override_infrastructure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'images.yaml'
            path.write_text('global: {}')
            with self.assertRaises(ValueError): images_overlay(path)
    def test_rendered_ingress(self):
        validate_ingress(render(os.environ.get('HELM_BIN','helm'), ROOT/'k8s/environments/dev/platform-services.values.yaml'))


if __name__ == '__main__': unittest.main()
