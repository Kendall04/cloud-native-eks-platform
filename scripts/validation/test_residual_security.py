"""Offline residual-hardening contracts; no AWS clients or scanner ignores."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest

import hcl2
import yaml

from validate_r1 import render
from validate_r3 import platform_render

ROOT = Path(__file__).resolve().parents[2]


class NatInfrastructureSecurityTests(unittest.TestCase):
    # These source-only checks need no rendered Helm fixtures or temporary files.
    def test_public_subnet_defaults_do_not_allocate_addresses(self):
        variables = hcl2.loads((ROOT / 'infra/modules/vpc/variables.tf').read_text())
        value = next(v['map_public_ip_on_launch'] for v in variables['variable'] if 'map_public_ip_on_launch' in v)
        self.assertIs(value['default'], False)
        nat = hcl2.loads((ROOT / 'infra/modules/nat/launch_template.tf').read_text())
        template = next(r['aws_launch_template']['nat'] for r in nat['resource'] if 'aws_launch_template' in r)
        self.assertIs(template['network_interfaces'][0]['associate_public_ip_address'], True)
        self.assertIs(template['network_interfaces'][0]['delete_on_termination'], True)
        self.assertEqual('required', template['metadata_options'][0]['http_tokens'])
        self.assertIs(template['block_device_mappings'][0]['ebs'][0]['encrypted'], True)
        allocations = hcl2.loads((ROOT / 'infra/modules/nat/elastic_ip.tf').read_text())
        kinds = {kind for row in allocations['resource'] for kind in row}
        self.assertIn('aws_eip', kinds)
        self.assertNotIn('aws_eip_association', kinds)
        self.assertIn('ec2:AssociateAddress', (ROOT / 'infra/modules/nat-egress/iam.tf').read_text())


class ResidualSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.addons = [d for d in yaml.safe_load_all(subprocess.check_output(
            ['helm', 'template', 'cluster-addons', 'k8s/charts/cluster-addons', '-n', 'kube-system'],
            cwd=ROOT, text=True)) if d]
        cls.apps = render('helm', ROOT / 'k8s/environments/dev/platform-services.values.yaml')
        cls.platform, _ = platform_render('helm')

    def obj(self, kind, name):
        return next(d for d in self.addons if (d['kind'], d['metadata']['name']) == (kind, name))

    def test_rds_has_no_outbound_initiation_or_alternate_group(self):
        doc = hcl2.loads((ROOT / 'infra/modules/rds/main.tf').read_text())
        resources = {kind: values for row in doc['resource'] for kind, values in row.items()}
        self.assertNotIn('aws_vpc_security_group_egress_rule', resources)
        self.assertNotIn('aws_security_group_rule', resources)
        self.assertNotIn('egress', resources['aws_security_group']['this'])
        self.assertEqual(['${aws_security_group.this.id}'],
                         resources['aws_db_instance']['this']['vpc_security_group_ids'])

    def test_keda_uses_builtin_scalable_kinds_without_wildcards_or_secret_cache(self):
        rules = self.obj('ClusterRole', 'keda-operator')['rules']
        for rule in rules:
            self.assertNotIn('*', rule['apiGroups'])
            self.assertFalse(any('*' in r for r in rule['resources']))
            self.assertNotIn('secrets', rule['resources'])
        scale = next(r for r in rules if 'deployments/scale' in r['resources'])
        self.assertEqual(['apps'], scale['apiGroups'])
        self.assertTrue({'get', 'update', 'patch'} <= set(scale['verbs']))
        self.assertTrue(any('horizontalpodautoscalers' in r['resources'] and 'create' in r['verbs'] for r in rules))
        pod = self.obj('Deployment', 'keda-operator')['spec']['template']['spec']
        env = {v['name']: v.get('value') for v in pod['containers'][0]['env']}
        self.assertEqual('true', env['KEDA_RESTRICT_SECRET_ACCESS'])

    def test_keda_bindings_preserve_apps_and_certificate_role(self):
        bindings = [d for d in self.addons if d['kind'] == 'RoleBinding'
                    and d['roleRef']['name'] == 'keda-operator']
        self.assertEqual({'apps', 'kube-system'}, {d['metadata']['namespace'] for d in bindings})
        self.assertFalse(any(d['kind'] == 'ClusterRoleBinding' and d['roleRef']['name'] == 'keda-operator' for d in self.addons))
        cert = self.obj('Role', 'keda-operator-certs')
        self.assertEqual('kube-system', cert['metadata']['namespace'])
        self.assertTrue(any('secrets' in r['resources'] and 'update' in r['verbs'] for r in cert['rules']))

    def test_eso_cert_writes_stay_named_and_webhook_rotation_preserved(self):
        rules = self.obj('ClusterRole', 'external-secrets-cert-controller')['rules']
        for r in rules:
            self.assertNotIn('secrets', r['resources'])
            self.assertNotIn('mutatingwebhookconfigurations', r['resources'])
            if 'validatingwebhookconfigurations' in r['resources'] and 'update' in r['verbs']:
                self.assertEqual({'secretstore-validate', 'externalsecret-validate'}, set(r['resourceNames']))
        role = self.obj('Role', 'external-secrets-cert-controller')
        secrets = next(r for r in role['rules'] if 'secrets' in r['resources'])
        self.assertEqual(['external-secrets-webhook'], secrets['resourceNames'])
        self.assertEqual({'get', 'update', 'patch'}, set(secrets['verbs']))

    def test_addons_have_explicit_nonroot_pod_contexts(self):
        for name in ('metrics-server', 'external-secrets', 'external-secrets-webhook',
                     'external-secrets-cert-controller', 'cluster-autoscaler'):
            pod = self.obj('Deployment', name)['spec']['template']['spec']
            with self.subTest(name=name):
                self.assertIs(pod['securityContext']['runAsNonRoot'], True)
                for c in pod['containers']:
                    self.assertIs(c['securityContext']['readOnlyRootFilesystem'], True)
                    self.assertIs(c['securityContext']['allowPrivilegeEscalation'], False)
                    self.assertIn('ALL', c['securityContext']['capabilities']['drop'])

    def test_runtime_and_migrations_use_only_bounded_scratch(self):
        workloads = [d for d in self.apps if d and d['kind'] in ('Deployment', 'Job')]
        self.assertEqual(6, len(workloads))
        for d in workloads:
            pod = d['spec']['template']['spec']
            with self.subTest(name=d['metadata']['name']):
                self.assertEqual(1654, pod['securityContext']['fsGroup'])
                self.assertEqual({'name': 'runtime-tmp', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '64Mi'}}, pod['volumes'][0])
                c = pod['containers'][0]
                self.assertIs(c['securityContext']['readOnlyRootFilesystem'], True)
                self.assertEqual({'name': 'runtime-tmp', 'mountPath': '/tmp'}, c['volumeMounts'][0])
                self.assertTrue(c['volumeMounts'][1]['readOnly'])

    def test_proposed_render_rejects_writable_or_unbounded_scratch(self):
        # Isolate the render validator; bundle/template allowlists are NOT changed
        # or mocked. Full bundle approval is tested separately by R4.
        sys.path.insert(0, str(ROOT / 'scripts/cd'))
        from common import validate_render
        from package import merge, target_from_environment
        from test_r2 import contract_fixture
        from environment import overlay

        env = contract_fixture()
        target = target_from_environment(env)
        records = [{'name': s, 'imageRepository': target['repositories'][s],
                    'imageDigest': 'sha256:' + 'b' * 64} for s in ('auth', 'shipment', 'tracking')]
        chart = ROOT / 'k8s/charts/platform-services'
        values = merge(yaml.safe_load((chart / 'values.yaml').read_text(encoding='utf-8')),
                       yaml.safe_load((ROOT / 'k8s/environments/dev/platform-services.values.yaml').read_text(encoding='utf-8')))
        values = merge(values, overlay(env))
        for record in records:
            values['services'][record['name']]['image'].update(
                repository=record['imageRepository'], digest=record['imageDigest'], tag='')
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / 'values.yaml'
            filename.write_text(yaml.safe_dump(values), encoding='utf-8')
            docs = [d for d in yaml.safe_load_all(subprocess.check_output(
                ['helm', 'template', 'platform-services', str(chart), '-n', 'apps', '-f', str(filename)],
                text=True)) if d]
        manifest = {'services': records}
        validate_render(docs, manifest, target)
        for change in ('writable-root', 'unbounded-tmp', 'disk-tmp', 'host-volume', 'tmp-mount', 'scratch-group'):
            changed = deepcopy(docs)
            pod = next(d for d in changed if d['kind'] == 'Deployment')['spec']['template']['spec']
            container = pod['containers'][0]
            if change == 'writable-root': container['securityContext']['readOnlyRootFilesystem'] = False
            if change == 'unbounded-tmp': pod['volumes'][0]['emptyDir'].pop('sizeLimit')
            if change == 'disk-tmp': pod['volumes'][0]['emptyDir'].pop('medium')
            if change == 'host-volume': pod['volumes'][0] = {'name': 'runtime-tmp', 'hostPath': {'path': '/'}}
            if change == 'tmp-mount': container['volumeMounts'][0]['mountPath'] = '/app'
            if change == 'scratch-group': pod['securityContext']['fsGroup'] = 0
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_render(changed, manifest, target)

    def test_scaler_auth_remains_irsa_without_secret_reference(self):
        auth = next(d for d in self.platform if d['kind'] == 'TriggerAuthentication')
        self.assertEqual({'podIdentity': {'provider': 'aws', 'identityOwner': 'keda'}}, auth['spec'])
        self.assertEqual(2, len([d for d in self.apps if d and d['kind'] == 'HorizontalPodAutoscaler']))
        scaled = next(d for d in self.apps if d and d['kind'] == 'ScaledObject')
        self.assertEqual('Deployment', scaled['spec']['scaleTargetRef']['kind'])
        self.assertEqual('aws-sqs-queue', scaled['spec']['triggers'][0]['type'])


if __name__ == '__main__':
    unittest.main()
