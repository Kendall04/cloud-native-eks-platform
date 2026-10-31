"""Opt-in integration against a disposable local PostgreSQL 15 database named platform.
Never set R3_POSTGRES_TEST_DSN to RDS or a database containing user data.
"""
import os
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bootstrap'))
from secret_values import SERVICES,initial_value
import json

@unittest.skipUnless(os.environ.get('R3_POSTGRES_TEST_DSN'),'No disposable local PostgreSQL available')
class PostgreSQLPrivileges(unittest.TestCase):
    def test_bootstrap_idempotency_isolation_and_future_objects(self):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        from database import configure
        dsn=os.environ['R3_POSTGRES_TEST_DSN']; options=conninfo_to_dict(dsn)
        self.assertIn(options.get('host'),('localhost','127.0.0.1'))
        self.assertEqual('platform',options.get('dbname'))
        credentials={f'{s}-{p}-db':json.loads(initial_value(f'{s}-{p}-db',None)) for s in SERVICES for p in ('runtime','migration')}
        with psycopg.connect(dsn,autocommit=True) as admin:
            # Disposable local superuser simulates the RDS parameter group.
            admin.execute('SET log_parameter_max_length = 0')
            admin.execute('SET log_parameter_max_length_on_error = 0')
            configure(admin,credentials); configure(admin,credentials)
        for s in SERVICES:
            cred=credentials[f'{s}-migration-db']
            with psycopg.connect(**{**options,'user':cred['username'],'password':cred['password']},autocommit=True) as migrator:
                migrator.execute(f'CREATE TABLE {s}.r3_test (id bigserial PRIMARY KEY, value text)')
        for s in SERVICES:
            def connect(p):
                cred=credentials[f'{s}-{p}-db']
                return psycopg.connect(**{**options,'user':cred['username'],'password':cred['password']},autocommit=True)
            with connect('migration') as migrator:
                other=next(x for x in SERVICES if x!=s)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege): migrator.execute(f'CREATE TABLE {other}.forbidden(id int)')
            with connect('runtime') as runtime:
                runtime.execute(f"INSERT INTO {s}.r3_test(value) VALUES ('test')")
                self.assertEqual(1,runtime.execute(f'SELECT count(*) FROM {s}.r3_test').fetchone()[0])
                with self.assertRaises(psycopg.errors.InsufficientPrivilege): runtime.execute(f'CREATE TABLE {s}.forbidden(id int)')
                for other in SERVICES:
                    if other!=s:
                        with self.assertRaises(psycopg.errors.InsufficientPrivilege): runtime.execute(f'SELECT * FROM {other}.r3_test')
                with self.assertRaises(psycopg.errors.InsufficientPrivilege): runtime.execute('CREATE ROLE forbidden')
        for s in SERVICES:
            cred=credentials[f'{s}-migration-db']
            with psycopg.connect(**{**options,'user':cred['username'],'password':cred['password']},autocommit=True) as migrator:
                migrator.execute(f'DROP TABLE {s}.r3_test')

if __name__=='__main__': unittest.main()
