"""Controlled private PostgreSQL bootstrap, no master material in Kubernetes.
All DDL runs in one transaction. Do not enable client debug or SQL parameter logging.
"""
import json
import os
from pathlib import Path
from environment import ROOT, require
from secret_values import SERVICES, validate_value

CA = ROOT / 'k8s/charts/platform-bootstrap/files/rds-global-bundle.pem'

def configure(connection, credentials):
    from psycopg import sql
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(731903)")
            # Password literals must never be included in server statement/error/parameter logs.
            cursor.execute("SET LOCAL log_statement = 'none'")
            cursor.execute("SET LOCAL log_min_duration_statement = -1")
            cursor.execute("SET LOCAL log_min_duration_sample = -1")
            cursor.execute("SET LOCAL log_transaction_sample_rate = 0")
            cursor.execute("SET LOCAL pgaudit.log = 'none'")
            cursor.execute("SET LOCAL log_min_error_statement = 'panic'")
            # RDS manages these privileged settings through the parameter group.
            # Fail before any password DDL if server-side safeguards are absent.
            for setting in ('log_parameter_max_length', 'log_parameter_max_length_on_error'):
                cursor.execute('SELECT current_setting(%s)', (setting,))
                require(cursor.fetchone()[0] == '0', 'RDS parameter logging must be disabled before credential bootstrap')
            cursor.execute('REVOKE ALL ON DATABASE platform FROM PUBLIC')
            cursor.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
            cursor.execute('SELECT current_user')
            operator=sql.Identifier(cursor.fetchone()[0])
            for service in SERVICES:
                runtime, migrator = service + '_runtime', service + '_migrator'
                schema = sql.Identifier(service)
                for purpose, name in (('runtime',runtime),('migration',migrator)):
                    role = sql.Identifier(name)
                    cursor.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', (name,))
                    exists = cursor.fetchone()
                    if not exists: cursor.execute(sql.SQL('CREATE ROLE {} LOGIN').format(role))
                    # Refuse to adopt privileged/member roles. Do not silently leave inherited grants.
                    cursor.execute('SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=%s', (name,))
                    require(not cursor.fetchone()[0], 'Existing DB principal has privileged attributes; manual review required')
                    cursor.execute('SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=%s', (name,))
                    require(cursor.fetchone() is None, 'Existing DB principal has memberships; manual review required')
                    cursor.execute(sql.SQL('ALTER ROLE {} LOGIN NOINHERIT PASSWORD {}').format(role,sql.Literal(credentials[service+'-'+purpose+'-db']['password'])))
                    cursor.execute(sql.SQL('REVOKE ALL ON DATABASE platform FROM {}').format(role))
                    cursor.execute(sql.SQL('GRANT CONNECT ON DATABASE platform TO {}').format(role))
                    cursor.execute(sql.SQL('ALTER ROLE {} IN DATABASE platform SET search_path TO {}').format(role,schema))
                cursor.execute(sql.SQL('GRANT {} TO {}').format(sql.Identifier(migrator),operator))
                cursor.execute('SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname=%s',(service,))
                existing=cursor.fetchone()
                require(existing is None or existing[0] == migrator, 'Existing schema has legacy ownership; reviewed ownership migration required')
                cursor.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}').format(schema,sql.Identifier(migrator)))
                cursor.execute(sql.SQL('REVOKE ALL ON SCHEMA {} FROM PUBLIC').format(schema))
                cursor.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(schema,sql.Identifier(runtime)))
                cursor.execute('SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND pg_get_userbyid(c.relowner)<>%s LIMIT 1',(service,migrator))
                require(cursor.fetchone() is None, 'Schema contains objects with legacy ownership; review required')
                cursor.execute(sql.SQL('REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM {}, PUBLIC').format(schema,sql.Identifier(runtime)))
                cursor.execute(sql.SQL('REVOKE ALL ON ALL SEQUENCES IN SCHEMA {} FROM {}, PUBLIC').format(schema,sql.Identifier(runtime)))
                cursor.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}').format(schema,sql.Identifier(runtime)))
                cursor.execute(sql.SQL('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}').format(schema,sql.Identifier(runtime)))
                cursor.execute(sql.SQL('ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}').format(sql.Identifier(migrator),schema,sql.Identifier(runtime)))
                cursor.execute(sql.SQL('ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT USAGE, SELECT ON SEQUENCES TO {}').format(sql.Identifier(migrator),schema,sql.Identifier(runtime)))
                cursor.execute(sql.SQL('ALTER DEFAULT PRIVILEGES FOR ROLE {} REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC').format(sql.Identifier(migrator)))
            # All roles now exist: remove cross-schema grants and runtime CREATE consistently.
            for service in SERVICES:
                for other in SERVICES:
                    for suffix in ('runtime','migrator'):
                        if other == service: continue
                        role=sql.Identifier(other+'_'+suffix); schema=sql.Identifier(service)
                        cursor.execute(sql.SQL('REVOKE ALL ON SCHEMA {} FROM {}').format(schema,role))
                        cursor.execute(sql.SQL('REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM {}').format(schema,role))
                        cursor.execute(sql.SQL('REVOKE ALL ON ALL SEQUENCES IN SCHEMA {} FROM {}').format(schema,role))
                cursor.execute(sql.SQL('REVOKE CREATE ON SCHEMA {} FROM {}').format(sql.Identifier(service),sql.Identifier(service+'_runtime')))
                cursor.execute(sql.SQL('REVOKE {} FROM {}').format(sql.Identifier(service+'_migrator'),operator))

def bootstrap(c):
    import boto3
    import psycopg
    client=boto3.client('secretsmanager',region_name=c['region'])
    credentials={}
    for name,arn in c['secrets'].items():
        if name.endswith('-db'):
            credentials[name]=json.loads(validate_value(name,client.get_secret_value(SecretId=arn)['SecretString']))
    master=json.loads(client.get_secret_value(SecretId=c['database']['masterSecretArn'])['SecretString'])
    # Root CA and DNS identity both verified. Never construct a password-bearing CLI string.
    # An existing SSM forward may carry TCP; TLS still verifies the real RDS DNS identity.
    forwarded = os.environ.get('RDS_LOCAL_FORWARD_PORT')
    transport = {}
    if forwarded:
        require(forwarded.isdigit() and 1024 <= int(forwarded) <= 65535, 'Invalid local RDS forward port')
        transport = {'hostaddr': '127.0.0.1', 'port': int(forwarded)}
    with psycopg.connect(host=c['database']['host'], dbname='platform', user=master['username'], password=master['password'], sslmode='verify-full', sslrootcert=str(CA), connect_timeout=10, autocommit=True, **transport) as connection:
        configure(connection,credentials)
