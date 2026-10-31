"""Offline isolation regressions. Fixture IDs are not observed future resources."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bootstrap'))
import synthetic_trial as trial

RUN = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'


def fixture_bindings():
    return {'vpc_id': 'vpc-' + 'f1' * 8 + '1',
            'private_subnet_ids': ['subnet-' + 'f2' * 8 + '2', 'subnet-' + 'f3' * 8 + '3'],
            'workload_security_group_ids': ['sg-' + 'f4' * 8 + '4'],
            'event_kms_key_arn': 'arn:aws:kms:us-east-1:341936017254:key/ffffffff-ffff-4fff-8fff-ffffffffffff'}


class IsolationTests(unittest.TestCase):
    def test_protection_policy_covers_original_secrets_database_and_all_dev_state_keys(self):
        policy = trial.protection_policy()
        retained = json.loads((trial.ROOT / 'docs/operations/eks-retained-secret-policy.json').read_text())
        self.assertLessEqual(set(retained['categories']['secrets']['resourceIds']), set(policy['identifiers']))
        self.assertEqual(sum(':secret:' in v and v.startswith('arn:') for v in policy['identifiers']), 11)
        self.assertIn('db-RCFKI3BK5VNW4OFBOBGD652PMY', policy['identifiers'])
        self.assertEqual(policy['sourceContractSha256'], '5a36df1003559541bd501154eea6c06c31e39564156a8f41072dcc4e2dad3513')
        for directory in (trial.ROOT / 'infra/live/dev').iterdir():
            if directory.is_dir() and (directory / 'terragrunt.hcl').exists():
                with self.assertRaisesRegex(ValueError, 'PROTECTED_REFERENCE_FORBIDDEN'):
                    trial.reject_protected(f'dev/{directory.name}/terraform.tfstate')

    def test_local_configuration_is_closed_and_has_no_existing_data_source(self):
        c = trial.configuration(RUN)
        self.assertEqual(set(c), {'terraform', 'provider', 'variable', 'module', 'output'})
        self.assertEqual(set(c['module']), {'database', 'secrets', 'queues', 'events'})
        self.assertEqual(set(c['variable']), {'bindings'})
        self.assertNotIn('default', c['variable']['bindings'])
        self.assertIs(trial.validate_configuration(c, RUN), c)

    def test_new_database_preserves_protection_and_has_no_restore_or_original_host(self):
        db = trial.configuration(RUN)['module']['database']
        self.assertTrue(db['deletion_protection'])
        self.assertFalse(db['skip_final_snapshot'])
        self.assertTrue(db['storage_encrypted'])
        self.assertFalse(db['publicly_accessible'])
        self.assertEqual((db['allocated_storage'], db['max_allocated_storage']), (20, 20))
        self.assertNotIn('teardown', db)
        self.assertNotIn('snapshot_identifier', db)
        self.assertNotIn('password', db)
        self.assertEqual(db['allowed_cidr_blocks'], [])
        self.assertLessEqual(len(db['name']), 63)

    def test_ten_new_secret_containers_are_not_a_reused_eso_owner(self):
        secrets = trial.configuration(RUN)['module']['secrets']
        self.assertEqual(set(secrets['secrets']), set(trial.SECRET_KEYS))
        self.assertEqual(len({s['name'] for s in secrets['secrets'].values()}), 10)
        self.assertTrue(all(s['recovery_window_in_days'] == 30 for s in secrets['secrets'].values()))
        self.assertNotIn('runtime-secrets', secrets['source'])
        self.assertNotIn('oidc_provider_arn', secrets)
        self.assertNotIn('shared_secret_arns', secrets)

    def test_queue_and_event_edges_resolve_only_the_new_queue_module(self):
        c = trial.configuration(RUN)
        queues = c['module']['queues']['queues']
        self.assertEqual(len(queues), 2)
        primary = next(name for name, spec in queues.items() if spec['create_dlq'])
        delivery = next(name for name, spec in queues.items() if not spec['create_dlq'])
        self.assertNotEqual(primary, delivery)
        self.assertNotIn(queues[primary]['dlq_name'], queues)
        self.assertTrue(all(len(name) <= 80 for name in (*queues, queues[primary]['dlq_name'])))
        rule = c['module']['events']['rules']['trk-upd-shipment']
        self.assertEqual(rule['target_queue_arn'], '${module.queues.queue_arns["' + primary + '"]}')
        self.assertEqual(rule['delivery_dlq_arn'], '${module.queues.queue_arns["' + delivery + '"]}')
        self.assertEqual(rule['target_queue_url'], '${module.queues.queue_urls["' + primary + '"]}')
        self.assertEqual(rule['delivery_dlq_url'], '${module.queues.queue_urls["' + delivery + '"]}')

    def test_consumable_data_outputs_reference_only_the_new_data_modules(self):
        output = trial.configuration(RUN)['output']['synthetic_data']['value']
        self.assertEqual(output['dataClass'], 'SYNTHETIC_ONLY')
        self.assertEqual(output['database']['host'], '${module.database.db_instance_address}')
        self.assertEqual(output['database']['masterSecretArn'], '${module.database.master_user_secret_arn}')
        self.assertEqual(output['secretArns'], '${module.secrets.secret_arns}')
        self.assertEqual(output['queueUrls'], '${module.queues.queue_urls}')

    def test_runs_never_share_state_database_secrets_queues_or_bus_names(self):
        def identities(run):
            c = trial.configuration(run)
            return ({c['terraform']['backend']['s3']['bucket'], c['terraform']['backend']['s3']['key'],
                     c['module']['database']['name'], c['module']['events']['event_bus_name']}
                    | {s['name'] for s in c['module']['secrets']['secrets'].values()}
                    | set(c['module']['queues']['queues']))
        self.assertFalse(identities(RUN) & identities(OTHER))

    def test_backend_cannot_adopt_retained_state_or_lineage(self):
        backend = trial.configuration(RUN)['terraform']['backend']['s3']
        self.assertEqual(backend['key'], f'synthetic-trials/{RUN}/data/terraform.tfstate')
        self.assertTrue(backend['use_lockfile'])
        self.assertTrue(backend['encrypt'])
        self.assertNotIn('dynamodb_table', backend)

    def test_every_exact_protected_reference_is_rejected_in_configuration(self):
        # Includes original DB identifiers/endpoint, all 11 secret identities,
        # original queues, backend keys/lineages and native network identities.
        for identifier in trial.protection_policy()['identifiers']:
            with self.subTest(identifier_type=identifier.split(':')[0]):
                candidate = trial.configuration(RUN)
                candidate['output']['unexpected'] = {'value': identifier}
                with self.assertRaisesRegex(ValueError, '^PROTECTED_REFERENCE_FORBIDDEN$'):
                    trial.validate_configuration(candidate, RUN)

    def test_alias_qualified_encoded_or_connection_string_reference_is_rejected(self):
        p = trial.protection_policy()
        original = next(v for v in p['identifiers'] if v.startswith('db-'))
        secret = next(v for v in p['identifiers'] if ':secret:' in v)
        for value in (original.upper(), 'Host=' + original + ';', secret + ':AWSCURRENT',
                      quote(quote(secret, safe=''), safe=''), {'nested': [{'ref': original}]}):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaisesRegex(ValueError, 'PROTECTED_REFERENCE_FORBIDDEN'):
                    trial.reject_protected(value)

    def test_no_dev_fallback_or_user_added_references_are_accepted(self):
        for mutate in (
            lambda c: c['module']['database'].update(name='cloud-native-platform-dev-postgres'),
            lambda c: c['terraform']['backend']['s3'].update(key='dev/rds/terraform.tfstate'),
            lambda c: c['module']['secrets'].update(source='../../../infra/live/dev/runtime-secrets'),
            lambda c: c.update(data={'terraform_remote_state': {'source': {}}}),
            lambda c: c['module']['database'].update(teardown={'decision': 'PURGE_DATABASE_EVIDENCE'}),
            lambda c: c['module']['queues'].update(queues={}),
            lambda c: c['variable']['bindings'].update(default=fixture_bindings()),
        ):
            with self.subTest(mutation=mutate.__code__.co_firstlineno):
                c = trial.configuration(RUN)
                mutate(c)
                with self.assertRaises(ValueError):
                    trial.validate_configuration(c, RUN)

    def test_protected_data_cannot_enter_through_any_binding_field(self):
        ids = trial.protection_policy()['identifiers']
        originals = [next(v for v in ids if v.startswith('db-')),
                     next(v for v in ids if ':secret:' in v),
                     next(v for v in ids if v.startswith('https://sqs.')),
                     'dev/rds/terraform.tfstate', next(v for v in ids if v.startswith('vpc-'))]
        for field in trial.BINDING_KEYS:
            for original in originals:
                with self.subTest(field=field):
                    b = fixture_bindings()
                    b[field] = [original] if isinstance(b[field], list) else original
                    with self.assertRaisesRegex(ValueError, '^PROTECTED_REFERENCE_FORBIDDEN$'):
                        trial.validate_bindings(b)

    def test_only_observed_binding_shapes_without_extra_payload_or_duplicates(self):
        trial.validate_bindings(fixture_bindings())
        mutations = (
            lambda b: b.update(database_host='not-an-input'),
            lambda b: b.pop('event_kms_key_arn'),
            lambda b: b.update(vpc_id='${data.external.lookup.result.id}'),
            lambda b: b.update(private_subnet_ids=[b['private_subnet_ids'][0]] * 2),
            lambda b: b.update(workload_security_group_ids=[]),
            lambda b: b.update(event_kms_key_arn=b['event_kms_key_arn'].replace('us-east-1', 'us-west-2')),
            lambda b: b.update(event_kms_key_arn=b['event_kms_key_arn'].replace('341936017254', '999999999999')),
            lambda b: b.update(private_subnet_ids='not-a-list'),
        )
        for mutate in mutations:
            b = fixture_bindings()
            mutate(b)
            with self.assertRaises(ValueError):
                trial.validate_bindings(b)

    def test_trial_id_cannot_inject_paths_names_expressions_or_default_to_dev(self):
        for value in ('dev', '../dev', 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA', '${var.run}',
                      RUN.replace('4111', '1111'), '', None, {}):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):
                    trial.configuration(value)

    def test_pins_and_selected_child_modules_add_no_iam_or_read_of_original_data(self):
        c = trial.configuration(RUN)
        self.assertEqual(c['terraform']['required_version'], '= 1.13.4')
        self.assertEqual(c['terraform']['required_providers']['aws']['version'], '= 5.100.0')
        for module in c['module'].values():
            self.assertLessEqual({'project_name', 'environment', 'region', 'tags'}, set(module))
            directory = trial.ROOT / 'infra/modules' / module['source'].rsplit('/', 1)[1]
            text = '\n'.join(p.read_text() for p in directory.glob('*.tf'))
            types = re.findall(r'resource\s+"([^"]+)"', text)
            self.assertFalse(any(t.startswith('aws_iam_') or t == 'aws_secretsmanager_secret_version' for t in types))
            self.assertNotIn('data "terraform_remote_state"', text)

    def test_renderer_has_no_cloud_sdk_process_or_network_execution_import(self):
        tree = ast.parse(Path(trial.__file__).read_text())
        allowed = {'argparse', 'json', 'pathlib', 're', 'urllib.parse', 'uuid'}
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        imports |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertLessEqual(imports, allowed)


class LocalArtifactTests(unittest.TestCase):
    def setUp(self):
        # Keep fixture paths below legacy Windows MAX_PATH without changing OS settings.
        fixture_base = trial.ROOT / '.validation-results/t'
        fixture_base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=fixture_base)
        self.root = Path(self.temp.name)
        # Verify the recursive fixture cleanup target stays inside this workspace.
        self.assertTrue(self.root.resolve().is_relative_to(fixture_base.resolve()))
        self.addCleanup(self.temp.cleanup)
        lock = self.root / 'infra/modules/rds/.terraform.lock.hcl'
        lock.parent.mkdir(parents=True)
        shutil.copyfile(trial.ROOT / 'infra/modules/rds/.terraform.lock.hcl', lock)
        self.patch = patch.object(trial, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_render_without_bindings_has_no_fabricated_ids_and_validates_round_trip(self):
        target = trial.render(RUN)
        self.assertEqual({p.name for p in target.iterdir()}, {'main.tf.json', 'protected-resources.json', '.terraform.lock.hcl'})
        config = json.loads((target / 'main.tf.json').read_text())
        trial.validate_configuration(config, RUN)
        trial.check_artifact(target / 'main.tf.json', RUN)
        self.assertNotRegex(json.dumps(config), r'(?:vpc|subnet|sg)-[0-9a-f]{17}')
        for module in config['module'].values():
            self.assertEqual((target / module['source']).resolve().parent, self.root / 'infra/modules')

    def test_refuses_overwrite_or_protected_binding_before_writing_anything(self):
        target = trial.render(RUN)
        (target / 'terraform.tfstate').write_text('fixture-existing-state')
        with self.assertRaises(FileExistsError):
            trial.render(RUN)
        self.assertEqual((target / 'terraform.tfstate').read_text(), 'fixture-existing-state')
        b = fixture_bindings()
        b['vpc_id'] = next(v for v in trial.protection_policy()['identifiers'] if v.startswith('vpc-'))
        with self.assertRaises(ValueError):
            trial.render(OTHER, b)
        self.assertFalse((self.root / '.generated/synthetic-trials' / OTHER).exists())

    def test_explicit_fixture_bindings_do_not_become_configuration_defaults(self):
        target = trial.render(RUN, fixture_bindings())
        saved = json.loads((target / 'bindings.auto.tfvars.json').read_text())
        self.assertEqual(saved, {'bindings': fixture_bindings()})
        self.assertNotIn('default', json.loads((target / 'main.tf.json').read_text())['variable']['bindings'])
        trial.check_artifact(target / 'main.tf.json', RUN)

    def test_checked_artifact_rejects_extra_terraform_state_imports_or_overrides(self):
        target = trial.render(RUN)
        for name in ('terraform.tfstate', 'extra.tf', 'override.tf', 'terraform.tfvars', 'import.tf.json'):
            with self.subTest(file=name):
                p = target / name
                p.write_text('fixture-not-a-real-state')
                with self.assertRaisesRegex(ValueError, 'ARTIFACT_EXTRA_OR_MISSING_FILES'):
                    trial.check_artifact(target / 'main.tf.json', RUN)
                p.unlink()

    def test_checked_artifact_rejects_changed_policy_lock_or_protected_bindings(self):
        target = trial.render(RUN, fixture_bindings())
        for name in ('protected-resources.json', '.terraform.lock.hcl'):
            p = target / name
            before = p.read_bytes()
            p.write_text('{}')
            with self.assertRaises(ValueError):
                trial.check_artifact(target / 'main.tf.json', RUN)
            p.write_bytes(before)
        inputs = target / 'bindings.auto.tfvars.json'
        b = fixture_bindings()
        b['vpc_id'] = next(v for v in trial.protection_policy()['identifiers'] if v.startswith('vpc-'))
        inputs.write_text(json.dumps({'bindings': b}))
        with self.assertRaisesRegex(ValueError, 'PROTECTED_REFERENCE_FORBIDDEN'):
            trial.check_artifact(target / 'main.tf.json', RUN)


if __name__ == '__main__':
    unittest.main()
