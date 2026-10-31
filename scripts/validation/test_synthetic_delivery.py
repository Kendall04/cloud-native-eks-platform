"""Synthetic producer -> real local Helm artifact -> host contract, no AWS.

Every identity below is an explicitly synthetic fixture, not an observed future
AWS ID. boto3 clients and host cloud/kube adapters are always replaced locally.
"""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/bootstrap'))
sys.path.insert(0, str(ROOT / 'scripts/cd'))
import environment
import bootstrap
import package as packaging
import publish
import export_environment
import orchestrate
from contract import read_tar, sha, validate_bundle
from executor import Host, validate_request
from synthetic_contract import binding_hash, publication_scope

RUN = '11111111-1111-4111-8111-111111111111'
ENV = 'trial-' + RUN.replace('-', '')
NAMESPACE = 'cnp-' + ENV
ACCOUNT = '341936017254'
REGION = 'us-east-1'
COMMIT = 'a' * 40


def packet_fixture():
    arn = lambda service, name: f'arn:aws:{service}:{REGION}:{ACCOUNT}:{name}'
    role = lambda suffix: f'arn:aws:iam::{ACCOUNT}:role/{NAMESPACE}-{suffix}'
    queue, dlq, delivery = (NAMESPACE + suffix for suffix in ('-shipment-events-queue', '-shipment-events-dlq', '-shipment-delivery-dlq'))
    qarn = lambda name: arn('sqs', name)
    qurl = lambda name: f'https://sqs.{REGION}.amazonaws.com/{ACCOUNT}/{name}'
    shared = {'auth-jwt': 'auth-service-jwt-secret', 'gateway-trust': 'platform-trusted-proxy-secret'}
    secrets = {key: arn('secretsmanager', 'secret:cnp/' + ENV + '/' + (
        'api-gateway-authorizer/' + shared[key] if key in shared else 'runtime/' + key) + '-Aa11bb')
        for key in environment.RETAINED_SECRET_NAMES}
    vpc = 'vpc-abcdef123456789ab'
    key = 'a1b2c3d4-1234-4567-89ab-cdef12345678'
    return {
        'schemaVersion': 1,
        'settings': {'project_name': 'cnp', 'environment': ENV, 'region': REGION, 'eks_cluster_name': NAMESPACE + '-cluster'},
        'accountId': ACCOUNT,
        'outputs': {
            'vpc': {'vpc_id': vpc, 'private_subnet_ids': ['subnet-abcdef123456789ab', 'subnet-bcdef123456789abc'], 'private_subnet_cidrs': ['10.77.1.0/24', '10.77.2.0/24']},
            'eks': {'vpc_id': vpc, 'cluster_name': NAMESPACE + '-cluster'},
            'ecr': {'repository_urls': {s + '-service': f'{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{s}-service' for s in environment.SERVICES}},
            'apigateway-core': {'api_id': 'syntheticfixture', 'vpc_link_id': 'syntheticlink', 'api_endpoint': f'https://syntheticfixture.execute-api.{REGION}.amazonaws.com', 'alb_frontend_security_group_id': 'sg-abcdef123456789ab', 'vpc_link_security_group_id': 'sg-bcdef123456789abc'},
        },
        'synthetic_data': {
            'schemaVersion': 1, 'dataClass': 'SYNTHETIC_ONLY', 'trialId': RUN,
            'database': {'host': NAMESPACE + '-postgres.fixture.invalid', 'identifier': NAMESPACE + '-postgres', 'masterSecretArn': arn('secretsmanager', 'secret:rds!db-' + RUN + '-Aa11bb')},
            'secretArns': secrets, 'eventBus': {'name': NAMESPACE + '-bus', 'arn': arn('events', 'event-bus/' + NAMESPACE + '-bus')},
            'queueArns': {name: qarn(name) for name in (queue, delivery)}, 'queueUrls': {name: qurl(name) for name in (queue, delivery)},
            'consumerDlqArns': {queue: qarn(dlq)}, 'consumerDlqUrls': {queue: qurl(dlq)},
        },
        'bindings': {'esoRoleArn': role('eso'), 'workloadRoles': {'shipment': role('shipment'), 'tracking': role('tracking')},
                     'addons': {'loadBalancerControllerRoleArn': role('lbc'), 'clusterAutoscalerRoleArn': role('autoscaler')},
                     'eventEncryption': {'keyArn': arn('kms', 'key/' + key), 'keyId': key, 'alias': 'alias/' + NAMESPACE + '-events', 'rotation': True, 'deletionWindowDays': 30}},
        'integration': {'alb_arn': arn('elasticloadbalancing', 'loadbalancer/app/synthetic/abcdef1234567890'), 'alb_listener_arn': arn('elasticloadbalancing', 'listener/app/synthetic/abcdef1234567890/abcdef1234567890')},
    }


def contract_fixture(packet=None):
    p = packet_fixture() if packet is None else packet
    return environment.build_contract(p['settings'], p['accountId'], p['outputs'], p['integration'],
                                      synthetic_data=p['synthetic_data'], bindings=p['bindings'])


def records_fixture(c):
    return [{'name': s, 'sourceCommit': COMMIT, 'imageRepository': c['repositories'][s],
             'imageDigest': 'sha256:' + 'b' * 64, 'buildRunId': '123'} for s in environment.SERVICES]


def request_fixture(data):
    digest = sha(data)
    return {'ArtifactKey': f'deploy-artifacts/{ENV}/{COMMIT}/{digest}.tar.gz', 'ArtifactVersionId': 'fixture-version',
            'ArtifactSha256': digest, 'DeploymentId': 'fixture-delivery', 'ExpectedPreviousRevision': '0'}


class ProducerTests(unittest.TestCase):
    def test_generate_consumes_data_before_any_historical_read(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(environment, 'ROOT', Path(tmp)), \
             patch.object(environment, 'command') as command, patch.object(environment, 'output') as output, \
             patch.object(environment, 'environment_settings') as settings:
            c = environment.generate(ENV, final=True, synthetic_inputs=packet_fixture())
            command.assert_not_called(); output.assert_not_called(); settings.assert_not_called()
            self.assertEqual(c['schemaVersion'], 3)
            self.assertEqual(c['dataScope']['namespace'], NAMESPACE)
            self.assertEqual(c['dataScope']['bindingSha256'], binding_hash(c))
            saved = json.loads((Path(tmp) / '.generated' / ENV / 'environment.json').read_text())
            self.assertEqual(saved, c)
            values = yaml.safe_load((Path(tmp) / '.generated' / ENV / 'platform.values.yaml').read_text())
            self.assertEqual(values['secretArns'], c['secrets'])
            self.assertEqual(values['workloadRoles'], c['workloadRoles'])

    def test_bootstrap_phase1_never_applies_protected_owners(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(environment, 'ROOT', Path(tmp)), \
             patch.object(bootstrap, 'run') as run, patch.object(bootstrap, 'command') as command, \
             patch.object(bootstrap, 'output') as output, patch.object(bootstrap, 'environment_settings') as settings:
            with redirect_stdout(io.StringIO()):
                c = bootstrap.phase(1, ENV, None, synthetic_inputs=packet_fixture())
            self.assertEqual(c['environment'], ENV)
            run.assert_not_called(); command.assert_not_called(); output.assert_not_called(); settings.assert_not_called()
            for phase in (0, 2, 3, 4, 5, 6):
                with self.assertRaises(ValueError): bootstrap.phase(phase, ENV, None, synthetic_inputs=packet_fixture())
            with self.assertRaises(ValueError): bootstrap.phase(1, ENV, None)

    def test_missing_dev_or_protected_inputs_fail_before_reads(self):
        for mutate in (
            lambda p: p.pop('bindings'),
            lambda p: p['bindings'].pop('esoRoleArn'),
            lambda p: p['bindings'].pop('workloadRoles'),
            lambda p: p['settings'].update(environment='dev'),
            lambda p: p['synthetic_data'].update(dataClass='dev'),
            lambda p: p['outputs'].update(rds={'db_instance_address': 'anything'}),
            lambda p: p['outputs'].update(state={'key': 'dev/rds/terraform.tfstate'}),
            lambda p: p['outputs']['vpc'].update(private_subnet_cidrs=['0.0.0.0/0', '10.77.2.0/24']),
            lambda p: p['outputs']['ecr']['repository_urls'].update(extra='not-a-binding'),
            lambda p: p['outputs']['vpc'].update(vpc_id='vpc-05a8ec8d7de5a8271'),
            lambda p: p['bindings']['eventEncryption'].update(keyArn=f'arn:aws:kms:{REGION}:{ACCOUNT}:key/88e09005-a830-4f4f-90e3-493fe721272f'),
            lambda p: p['synthetic_data']['secretArns'].update({'auth-jwt': next(v for v in json.loads((ROOT / 'infra/trials/synthetic-data/protected-resources.json').read_text())['identifiers'] if ':secret:' in v)}),
            lambda p: p['synthetic_data']['database'].update(host=next(v for v in json.loads((ROOT / 'infra/trials/synthetic-data/protected-resources.json').read_text())['identifiers'] if v.endswith('.rds.amazonaws.com'))),
            lambda p: p['synthetic_data']['queueUrls'].update({next(iter(p['synthetic_data']['queueUrls'])): next(v for v in json.loads((ROOT / 'infra/trials/synthetic-data/protected-resources.json').read_text())['identifiers'] if v.startswith('https://sqs.'))}),
        ):
            p = packet_fixture(); mutate(p)
            with patch.object(environment, 'command') as command, patch.object(environment, 'output') as output, \
                 patch.object(environment, 'environment_settings') as settings:
                with self.assertRaises((ValueError, KeyError)):
                    environment.generate(ENV, final=True, synthetic_inputs=p)
                command.assert_not_called(); output.assert_not_called(); settings.assert_not_called()

    def test_trial_without_packet_or_with_legacy_contract_cannot_fallback(self):
        with patch.object(environment, 'command') as command, patch.object(environment, 'output') as output:
            with self.assertRaises(ValueError): environment.generate(ENV)
            command.assert_not_called(); output.assert_not_called()
        c = contract_fixture()
        with self.assertRaises(ValueError): environment.validate_contract(c, 'dev')
        c['schemaVersion'] = 2
        with self.assertRaises(ValueError): environment.validate_contract(c, ENV)

    def test_protected_api_short_id_is_not_an_alias_escape(self):
        p = packet_fixture()
        protected = json.loads((ROOT / 'infra/trials/synthetic-data/protected-resources.json').read_text())['identifiers']
        arn = next(v for v in protected if ':apigateway:' in v and '/apis/' in v)
        api_id = arn.split('/apis/')[1].split('/')[0]
        p['outputs']['apigateway-core'].update(api_id=api_id, api_endpoint=f'https://{api_id}.execute-api.{REGION}.amazonaws.com')
        with self.assertRaisesRegex(ValueError, 'protected reference'):
            contract_fixture(p)

    def test_host_policy_copy_is_exact_and_legacy_schema_is_not_relaxed(self):
        host = ROOT / 'infra/modules/management-host/deployer'
        self.assertEqual((host / 'synthetic-protected-resources.json').read_bytes(), (ROOT / 'infra/trials/synthetic-data/protected-resources.json').read_bytes())
        old = json.loads((host / 'manifest.schema.json').read_text())
        self.assertEqual(old['properties']['environment']['const'], 'dev')
        self.assertEqual(old['properties']['requiredDeployerVersion']['const'], '1.4.0')


class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helm = shutil.which(os.environ.get('HELM_BIN', 'helm'))
        if cls.helm is None: raise RuntimeError('Qualified Helm binary is required')
        cls.c = contract_fixture()
        cls.target = packaging.target_from_environment(cls.c)
        cls.records = records_fixture(cls.c)
        cls.data, cls.manifest = packaging.package(packaging.canonical(cls.c), cls.records, COMMIT, 'v1.0.0',
            expected_environment=ENV, expected_data_scope=cls.c['dataScope'])

    def test_real_local_package_and_consumer_propagate_namespace_and_bindings(self):
        files, manifest = validate_bundle(self.data, sha(self.data), self.target)
        self.assertEqual(manifest['artifactSchemaVersion'], 2)
        self.assertEqual(manifest['requiredDeployerVersion'], '1.5.0')
        self.assertEqual(manifest['dataScope'], self.c['dataScope'])
        values = json.loads(files['values.resolved.yaml'])
        for service in environment.SERVICES:
            self.assertEqual(values['services'][service]['env']['Database__Host'], self.c['database']['host'])
            self.assertEqual(values['services'][service]['env']['Telemetry__Environment'], ENV)
        self.assertEqual(values['global']['ingress']['annotations']['alb.ingress.kubernetes.io/group.name'], NAMESPACE)
        validate_request(request_fixture(self.data), self.target)
        with self.assertRaises(ValueError): validate_request(request_fixture(self.data))
        with self.assertRaises(ValueError): validate_bundle(self.data, sha(self.data), {k: v for k, v in self.target.items() if k != 'dataScope'})

    def test_unbound_or_dev_packaging_and_publication_metadata_are_rejected(self):
        for kwargs in ({}, {'expected_environment': ENV}, {'expected_environment': 'dev', 'expected_data_scope': self.c['dataScope']}):
            with self.assertRaises(ValueError): packaging.package(packaging.canonical(self.c), self.records, COMMIT, 'v1.0.0', **kwargs)
        for supplied in ({'DEPLOYMENT_ENVIRONMENT': ENV}, {'SYNTHETIC_DATA_SCOPE': json.dumps(self.c['dataScope'])},
                         {'DEPLOYMENT_ENVIRONMENT': 'dev', 'SYNTHETIC_DATA_SCOPE': json.dumps(self.c['dataScope'])}):
            with self.assertRaises(ValueError): publication_scope(supplied)

    def test_export_requires_explicit_environment_and_scope(self):
        raw = packaging.canonical(self.c)
        self.assertEqual(export_environment.export_key(raw, ENV, self.c['dataScope']), f'environment-contracts/{ENV}/{sha(raw)}.json')
        with self.assertRaises(ValueError): export_environment.export_key(raw)
        with self.assertRaises(ValueError): export_environment.export_key(raw, ENV)

    def rebundle(self, change):
        files = read_tar(self.data, outer=True)
        change(files)
        m = json.loads(files['manifest.json'])
        for field, name in (('chartSha256', 'platform-services.tgz'), ('valuesSha256', 'values.resolved.yaml'), ('environmentContractSha256', 'environment.contract.json')):
            m[field] = sha(files[name])
        files['manifest.json'] = packaging.canonical(m)
        files['checksums.sha256'] = ''.join(f'{sha(content)}  {name}\n' for name, content in sorted(files.items()) if name != 'checksums.sha256').encode()
        return packaging.archive(files)

    def test_recomputed_checksums_cannot_change_scope_environment_or_data_host(self):
        def change_values(files):
            values = yaml.safe_load(files['values.resolved.yaml'])
            values['services']['auth']['env']['Database__Host'] = 'another-db.fixture.invalid'
            files['values.resolved.yaml'] = yaml.safe_dump(values).encode()
        def change_scope(files):
            c = json.loads(files['environment.contract.json'])
            c['database']['host'] = NAMESPACE + '-postgres.other.invalid'
            c['dataScope']['bindingSha256'] = binding_hash(c)
            files['environment.contract.json'] = packaging.canonical(c)
            m = json.loads(files['manifest.json']); m['dataScope'] = c['dataScope']
            files['manifest.json'] = packaging.canonical(m)
        def downgrade(files):
            m = json.loads(files['manifest.json']); m['environment'] = 'dev'
            files['manifest.json'] = packaging.canonical(m)
        for change in (change_values, change_scope, downgrade):
            data = self.rebundle(change)
            with self.assertRaises(ValueError): validate_bundle(data, sha(data), self.target)
        with self.assertRaises(ValueError): validate_bundle(self.data + b'bad', sha(self.data), self.target)

    def test_host_preflight_uses_same_contract_and_real_helm_with_only_local_cloud_doubles(self):
        with tempfile.TemporaryDirectory() as tmp:
            host = Host({**self.target, 'bucket': 'fixture-only'}, tmp, tmp)
            def aws(*args):
                if args[:2] == ('s3api', 'head-object'): return {'ContentLength': len(self.data)}
                if args[:2] == ('s3api', 'get-object'):
                    Path(args[-1]).write_bytes(self.data); return {'VersionId': 'fixture-version'}
                if args[:2] == ('eks', 'describe-cluster'):
                    return {'cluster': {'arn': f'arn:aws:eks:{REGION}:{ACCOUNT}:cluster/{self.c["clusterName"]}', 'resourcesVpcConfig': {'endpointPrivateAccess': True, 'endpointPublicAccess': False}}}
                raise AssertionError('Unexpected fake AWS call')
            def run(args, timeout=900):
                if args[:3] == ['aws', 'eks', 'update-kubeconfig']: return ''
                if args[0] == 'kubectl': return json.dumps({'spec': {'podIdentity': {'provider': 'aws', 'identityOwner': 'keda'}}})
                self.assertEqual(args[0], 'helm')
                return subprocess.check_output([self.helm, *args[1:]], text=True)
            host.aws, host.run = aws, run
            self.assertEqual(host.preflight(request_fixture(self.data)), self.manifest)
            self.assertEqual(host.receipt_key('fixture.json'), f'deployment-receipts/{ENV}/fixture.json')

    def test_existing_publication_entrypoint_preserves_scope_and_immutable_namespace(self):
        puts = []
        raw = packaging.canonical(self.c)
        key = export_environment.export_key(raw, ENV, self.c['dataScope'])
        def get_object(**args):
            if args['Key'] == key:
                self.assertEqual(args['VersionId'], 'fixture-contract-version')
                return {'Body': io.BytesIO(raw)}
            service = args['Key'].rsplit('/', 1)[-1].removesuffix('.json')
            self.assertEqual(args['Key'], f'image-records/dev/{COMMIT}/{service}.json')
            return {'Body': io.BytesIO(packaging.canonical(next(r for r in self.records if r['name'] == service)))}
        s3 = Mock(); s3.get_object.side_effect = get_object
        def put_object(**args):
            self.assertEqual(args['IfNoneMatch'], '*'); puts.append(args)
            return {'VersionId': 'fixture-artifact-version'}
        s3.put_object.side_effect = put_object
        ecr = Mock(); ecr.describe_images.return_value = {'imageDetails': [{'imageDigest': 'sha256:' + 'b' * 64}]}
        env = {'GITHUB_SHA': COMMIT, 'GITHUB_REF': 'refs/heads/main', 'GITHUB_REPOSITORY': 'fixture/fixture',
               'GH_TOKEN': 'local-fixture-only', 'ARTIFACT_BUCKET': 'fixture-only', 'AWS_REGION': REGION, 'AWS_ACCOUNT_ID': ACCOUNT,
               'ENVIRONMENT_CONTRACT_KEY': key, 'ENVIRONMENT_CONTRACT_VERSION': 'fixture-contract-version', 'ENVIRONMENT_CONTRACT_SHA256': sha(raw),
               'MIGRATION_COMPATIBILITY': 'previous-release-compatible', 'RELEASE_VERSION': 'v1.0.0',
               'DEPLOYMENT_ENVIRONMENT': ENV, 'SYNTHETIC_DATA_SCOPE': json.dumps(self.c['dataScope']), 'HELM_BIN': self.helm}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True), patch.object(sys, 'argv', ['publish.py', 'release']), \
             patch.object(publish.boto3, 'client', side_effect=[s3, ecr]), patch.object(publish, 'verify_build_run'), \
             patch.object(publish, 'require_clean_scan'), redirect_stdout(io.StringIO()):
            before = Path.cwd()
            try:
                os.chdir(tmp); publish.main()
                receipt = json.loads(Path('publication-receipt.json').read_text())
                self.assertEqual(receipt['environment'], ENV)
                self.assertEqual(receipt['dataScope'], self.c['dataScope'])
            finally: os.chdir(before)
        self.assertEqual(len(puts), 1)
        data = puts[0]['Body']
        self.assertEqual(puts[0]['Key'], f'deploy-artifacts/{ENV}/{COMMIT}/{sha(data)}.tar.gz')
        validate_bundle(data, sha(data), self.target)

    def test_orchestrator_explicit_scope_and_request_key_never_default_to_dev(self):
        source = {'AWS_ACCOUNT_ID': ACCOUNT, 'AWS_REGION': REGION, 'EKS_CLUSTER_NAME': self.c['clusterName'],
                  'PLATFORM_ALB_GROUP_NAME': NAMESPACE, 'ALB_FRONTEND_SECURITY_GROUP_ID': self.c['alb']['frontendSecurityGroupId'],
                  'SHIPMENT_QUEUE_URL': self.c['shipmentQueue']['url'], 'DEPLOYMENT_ENVIRONMENT': ENV,
                  'SYNTHETIC_DATA_SCOPE': json.dumps(self.c['dataScope'])}
        self.assertEqual(orchestrate.deployment_target(source), self.target)
        with self.assertRaises(ValueError): orchestrate.deployment_target({k: v for k, v in source.items() if k != 'SYNTHETIC_DATA_SCOPE'})

    def test_same_environment_cannot_reuse_receipt_after_binding_scope_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            host = Host({**self.target, 'bucket': 'fixture-only'}, tmp, tmp)
            host.save({'deploymentId': 'fixture-receipt', 'status': 'RUNNING'})
            self.assertEqual(host.load('fixture-receipt')['target']['dataScope'], self.c['dataScope'])
            host.config = deepcopy(host.config)
            host.config['dataScope']['bindingSha256'] = 'c' * 64
            with self.assertRaises(ValueError): host.load('fixture-receipt')

    def test_incomplete_synthetic_publication_stops_before_client_construction(self):
        with patch.dict(os.environ, {'DEPLOYMENT_ENVIRONMENT': ENV}, clear=True), \
             patch.object(sys, 'argv', ['publish.py', 'release']), patch.object(publish.boto3, 'client') as client:
            with self.assertRaises(ValueError): publish.main()
            client.assert_not_called()


if __name__ == '__main__':
    unittest.main()
