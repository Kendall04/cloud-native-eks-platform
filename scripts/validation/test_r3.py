import copy
import io
import json
import os
from contextlib import redirect_stdout
import unittest
from unittest.mock import Mock, patch
import yaml
from validate_r1 import ROOT, render
from validate_r3 import validate_values, validate_platform, validate_apps, platform_render, validate_iac
from test_r2 import contract_fixture
from environment import validate_contract
from secret_values import initialize, initial_value, validate_value
from bootstrap import database_marker, runtime_secret_gate

class R3Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs,cls.fixture=platform_render(os.environ.get('HELM_BIN','helm'))
        cls.apps=render(os.environ.get('HELM_BIN','helm'),ROOT/'k8s/environments/dev/platform-services.values.yaml')
    def test_baseline(self):
        validate_platform(self.docs,self.fixture); validate_apps(self.apps); validate_iac()
    def test_literal_password_rejected(self):
        values=yaml.safe_load((ROOT/'k8s/environments/dev/platform-services.values.yaml').read_text())
        values['services']['auth']['env']['Database__Password']='test-only-injected'
        with self.assertRaises(ValueError): validate_values(values)
    def test_secret_in_inventory_rejected(self):
        c=contract_fixture(); c['database']['password']='test-only-injected'
        with self.assertRaises(ValueError): validate_contract(c,'dev')
    def test_rbac_forbidden_capabilities(self):
        for resource in ('pods/exec','serviceaccounts','namespaces','clusterroles','*'):
            docs=copy.deepcopy(self.docs)
            next(d for d in docs if d['kind']=='Role')['rules'][0]['resources'].append(resource)
            with self.assertRaises(ValueError): validate_platform(docs,self.fixture)
    def test_wrong_secret_source(self):
        docs=copy.deepcopy(self.docs)
        next(d for d in docs if d['kind']=='ExternalSecret' and d['metadata']['name']=='auth-jwt')['spec']['data'][0]['remoteRef']['key']='wrong'
        with self.assertRaises(ValueError): validate_platform(docs,self.fixture)
    def test_runtime_cannot_use_migrator(self):
        docs=copy.deepcopy(self.apps)
        pod=next(d for d in docs if d and d['kind']=='Deployment')['spec']['template']['spec']
        next(e for e in pod['containers'][0]['env'] if e['name']=='Database__Password')['valueFrom']['secretKeyRef']['name']='auth-migration-db'
        with self.assertRaises(ValueError): validate_apps(docs)
    def test_app_cannot_own_service_accounts(self):
        with self.assertRaises(ValueError): validate_apps(self.apps+[{'kind':'ServiceAccount'}])
    def test_changed_secret_blocks_migration(self):
        with patch('bootstrap.command',return_value=json.dumps({'data':{'auth-runtime-db':'old'}})):
            with self.assertRaises(ValueError): database_marker({'auth-runtime-db':'new'})
    def test_initialization_does_not_overwrite_or_print(self):
        c={'region':'us-east-1','secrets':{'auth-runtime-db':'test-arn'}}
        client=Mock(); client.describe_secret.return_value={'VersionIdsToStages':{'v1':['AWSCURRENT']}}
        client.get_secret_value.return_value={'SecretString':initial_value('auth-runtime-db',None)}
        with redirect_stdout(io.StringIO()) as output:
            initialize(c,client=client); initialize(c,client=client)
        self.assertEqual('',output.getvalue()); client.put_secret_value.assert_not_called()
    def test_initialization_only_puts_missing_version(self):
        client=Mock(); client.describe_secret.return_value={}
        initialize({'region':'us-east-1','secrets':{'tracking-migration-db':'test-arn'}},client=client)
        kwargs=client.put_secret_value.call_args.kwargs
        self.assertEqual('tracking_migrator',json.loads(kwargs['SecretString'])['username'])
        self.assertEqual(36,len(kwargs['ClientRequestToken']))

    def test_read_gate_accepts_existing_ready_sync_without_requesting_new_refresh(self):
        status = json.dumps({'status': {'conditions': [{'type': 'Ready', 'status': 'True'}],
                                      'refreshTime': '2020-01-01T00:00:00Z'}})
        def query(args):
            if 'externalsecret' in args: return status
            if any('go-template' in value for value in args): return 'username\npassword\nemail\nvalue\n'
            return '123'
        with patch('bootstrap.command', side_effect=query), patch('bootstrap.run') as run:
            versions = runtime_secret_gate()
            self.assertEqual(10, len(versions))
            self.assertEqual({'123'}, set(versions.values()))
            run.assert_not_called()
    def test_invalid_existing_secret_never_replaced(self):
        client=Mock(); client.describe_secret.return_value={'VersionIdsToStages':{'v1':['AWSCURRENT']}}
        client.get_secret_value.return_value={'SecretString':'placeholder'}
        with self.assertRaises(ValueError): initialize({'region':'us-east-1','secrets':{'auth-jwt':'test-arn'}},client=client)
        client.put_secret_value.assert_not_called()
    def test_db_identity_and_admin_seed_validation(self):
        with self.assertRaises(ValueError): validate_value('auth-runtime-db',json.dumps({'username':'platform_admin','password':'x'*48}))
        with self.assertRaises(ValueError): initial_value('bootstrap-admin',None)
    def test_platform_gates_order(self):
        import inspect, bootstrap
        source=inspect.getsource(bootstrap.phase)
        self.assertLess(source.index('secretstore/platform-aws'),source.index("'platform-secret-sync'"))
        self.assertLess(source.index('versions = runtime_secret_gate(request_refresh=True)'),source.index('bootstrap(c)'))
        self.assertLess(source.index('bootstrap(c)'),source.index('database_marker(versions, write=True)'))
        self.assertLess(source.index('database_marker(versions)'),source.index("'platform-services', ROOT"))

    def test_phase2_labels_new_and_existing_apps_before_addon_install(self):
        import bootstrap
        class BeforeAddonInstall(Exception):
            pass
        label = ['kubectl','label','namespace','apps',
                 'elbv2.k8s.aws/pod-readiness-gate-inject=enabled','--overwrite']
        for exists in (False, True):
            with self.subTest(namespace_exists=exists):
                namespace = Mock(stdout='namespace/apps\n' if exists else '')
                with patch('bootstrap.generate', return_value=contract_fixture()), \
                     patch('bootstrap.kube_context'), \
                     patch('bootstrap.subprocess.run', return_value=namespace), \
                     patch('bootstrap.run') as run, \
                     patch('bootstrap.tempfile.TemporaryDirectory', side_effect=BeforeAddonInstall):
                    with self.assertRaises(BeforeAddonInstall):
                        bootstrap.phase(2, 'dev', None)
                expected = ([] if exists else [['kubectl','create','namespace','apps']]) + [label]
                self.assertEqual(expected, [call.args[0] for call in run.call_args_list])

class SqlGenerationTests(unittest.TestCase):
    def test_roles_grants_defaults_and_transaction_boundary(self):
        from contextlib import contextmanager
        from database import configure
        from secret_values import SERVICES
        class Cursor:
            def __init__(self): self.statements=[]; self.last=''
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def execute(self,statement,parameters=None):
                self.last=statement if isinstance(statement,str) else statement.as_string()
                self.statements.append(self.last)
            def fetchone(self):
                if self.last=='SELECT current_user': return ('operator',)
                if self.last=='SELECT current_setting(%s)': return ('0',)
                if self.last.startswith('SELECT rolsuper'): return (False,)
                return None
        class Connection:
            def __init__(self): self.record=Cursor(); self.committed=False
            def cursor(self): return self.record
            @contextmanager
            def transaction(self):
                yield
                self.committed=True
        connection=Connection()
        credentials={f'{s}-{p}-db':json.loads(initial_value(f'{s}-{p}-db',None)) for s in SERVICES for p in ('runtime','migration')}
        configure(connection,credentials)
        statements=connection.record.statements
        self.assertTrue(connection.committed)
        self.assertEqual(6,sum(x.startswith('CREATE ROLE') for x in statements))
        for service in SERVICES:
            self.assertIn(f'ALTER DEFAULT PRIVILEGES FOR ROLE "{service}_migrator" IN SCHEMA "{service}" GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{service}_runtime"',statements)
            self.assertIn(f'REVOKE CREATE ON SCHEMA "{service}" FROM "{service}_runtime"',statements)
            self.assertIn(f'REVOKE "{service}_migrator" FROM "operator"',statements)
        self.assertIn("SET LOCAL log_statement = 'none'",statements)
        self.assertIn('REVOKE ALL ON DATABASE platform FROM PUBLIC',statements)

    def test_parameter_logging_blocks_password_ddl(self):
        from database import configure
        from unittest.mock import MagicMock
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ('-1',)
        with self.assertRaisesRegex(ValueError, 'parameter logging'):
            configure(connection, {})
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertFalse(any(isinstance(statement, str) and statement.startswith('CREATE ROLE') for statement in statements))

if __name__=='__main__': unittest.main()
