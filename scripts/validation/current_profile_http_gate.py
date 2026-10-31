"""Explicit isolated HTTP gate: cached PostgreSQL + source APIs, never AWS or existing data.

Run only when authorized: --run-isolated --dotnet /path/to/pinned/dotnet.
No image/package download, image build, existing volume or global cleanup is performed.
The local Development database owner/HTTP topology is not production certification.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]


class GateFailure(Exception):
    pass


def fixture_state(name, run_id):
    """An inspect transport/permission error is unknown, never proof of absence."""
    inspected = subprocess.run(['docker', 'inspect', '--format', '{{json .Config.Labels}}', name],
                               text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if inspected.returncode == 0:
        labels = json.loads(inspected.stdout)
        if labels.get('com.codex.validation') != 'eks-current-profile' or labels.get('com.codex.run') != run_id:
            raise GateFailure('Fixture ownership mismatch; container not touched')
        return 'owned'
    message = inspected.stderr.lower()
    if inspected.returncode == 1 and any(marker + name.lower() in message for marker in ('no such object: ', 'no such container: ')):
        return 'absent'
    raise GateFailure('Fixture presence cannot be verified; no absence claim')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-isolated', action='store_true', required=True)
    parser.add_argument('--dotnet', required=True)
    args = parser.parse_args()
    run_id = uuid.uuid4().hex
    name = 'cnp-auth-profile-' + run_id[:12]
    output = ROOT / '.validation-results/auth-equivalence/protected/http' / run_id
    output.mkdir(parents=True)
    before_free = shutil.disk_usage(ROOT).free
    if before_free < 2 * 1024**3:
        raise GateFailure('Insufficient free disk for bounded isolated gate')
    for port in (8080, 8081, 8082, 55436):
        with socket.socket() as probe:
            try: probe.bind(('127.0.0.1', port))
            except OSError: raise GateFailure('Required loopback port is already owned: ' + str(port)) from None
    process_env = {k: v for k, v in os.environ.items() if not k.startswith('AWS_')}
    process_env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', MSBUILDDISABLENODEREUSE='1',
                       AWS_EC2_METADATA_DISABLED='true', AWS_SHARED_CREDENTIALS_FILE='/dev/null', AWS_CONFIG_FILE='/dev/null',
                       AWS_ACCESS_KEY_ID='local-synthetic-access', AWS_SECRET_ACCESS_KEY='local-synthetic-secret',
                       HTTP_PROXY='', HTTPS_PROXY='', ALL_PROXY='', NO_PROXY='127.0.0.1,localhost')
    sensitive = []
    def command(*parts, env=None, timeout=90):
        completed = subprocess.run(parts, cwd=ROOT, env=env or process_env, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        if completed.returncode:
            diagnostic = completed.stdout
            for value in sensitive: diagnostic = diagnostic.replace(value, "[REDACTED]")
            (output / 'failed-command.log').write_text(diagnostic)
            completed.check_returncode()
        return completed.stdout.strip()
    command('docker', 'image', 'inspect', 'postgres:15.18')
    if command(args.dotnet, '--version') != '10.0.402': raise GateFailure('SDK does not match global.json')
    password, signing, proxy_secret, internal_secret = (secrets.token_hex(32) for _ in range(4))
    sensitive.extend((password, signing, proxy_secret, internal_secret))
    processes, handles, service_envs, assemblies = {}, [], {}, {}
    checks = []
    attempted_container, cleanup_confirmed = False, False
    result = {'result': 'FAIL', 'runId': run_id, 'awsApiCalls': 0, 'environment': 'isolated-development-http',
              'postgresImage': 'postgres:15.18', 'containerMemoryMiB': 256, 'persistentVolumes': False}
    stage = 'prepare'
    def sql(statement):
        return command('docker', 'exec', name, 'psql', '-U', 'postgres', '-d', 'platform', '-v', 'ON_ERROR_STOP=1', '-tAc', statement)
    def stop(service):
        process = processes.pop(service, None)
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    def start(service):
        handle = (output / (service + '-runtime.log')).open('a')
        handles.append(handle)
        processes[service] = subprocess.Popen([args.dotnet, str(assemblies[service])], cwd=ROOT,
                                             env=service_envs[service], stdout=handle, stderr=subprocess.STDOUT)
        port = 8080 + ('auth', 'shipment', 'tracking').index(service)
        for _ in range(100):
            if processes[service].poll() is not None: raise GateFailure(service + ' exited; inspect private local runtime log')
            try:
                with urllib.request.urlopen('http://127.0.0.1:' + str(port) + '/health/ready', timeout=1) as response:
                    if response.status == 200: return
            except (OSError, urllib.error.URLError): pass
            time.sleep(.1)
        raise GateFailure(service + ' readiness deadline exceeded')
    def http(label, port, path, expected=200, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request('http://127.0.0.1:' + str(port) + path, data=data,
                                         headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            response = urllib.request.urlopen(request, timeout=12)
        except urllib.error.HTTPError as error: response = error
        with response:
            status = response.status
            payload = response.read(1024 * 1024)
            cache = response.headers.get('Cache-Control')
        if status != expected: raise GateFailure(label + ': expected ' + str(expected) + ', got ' + str(status))
        if port != 8080 and cache != 'no-store': raise GateFailure(label + ': missing no-store')
        checks.append({'name': label, 'status': status})
        return json.loads(payload) if payload else None
    def attest(user, token, **changes):
        return {'Authorization': 'Bearer ' + token, 'X-Platform-User-Id': user,
                'X-Platform-Email': 'snapshot@example.invalid', 'X-Platform-Roles': 'ADMIN',
                'X-Platform-Proxy-Secret': proxy_secret, **changes}
    try:
        stage = 'start-postgres'
        attempted_container = True
        command('docker', 'run', '-d', '--rm', '--pull=never', '--name', name,
                '--label', 'com.codex.validation=eks-current-profile', '--label', 'com.codex.run=' + run_id,
                '--memory', '256m', '--memory-swap', '256m', '--cpus', '1', '--pids-limit', '128',
                '--tmpfs', '/var/lib/postgresql/data:rw,nosuid,nodev,size=128m',
                '-p', '127.0.0.1:55436:5432', '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_DB=platform',
                'postgres:15.18', '-c', 'shared_buffers=16MB', '-c', 'max_connections=40',
                env={**process_env, 'POSTGRES_PASSWORD': password})
        for _ in range(100):
            try:
                command('docker', 'exec', name, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres', '-d', 'platform', timeout=3)
                break
            except subprocess.CalledProcessError: time.sleep(.1)
        else: raise GateFailure('PostgreSQL readiness deadline exceeded')
        sql('CREATE SCHEMA auth; CREATE SCHEMA shipment; CREATE SCHEMA tracking;')
        for index, service in enumerate(('auth', 'shipment', 'tracking')):
            stage = 'build-and-migrate-' + service
            project_name = service.title() + 'Service.Api'
            project = ROOT / ('microservices/' + service + '-service/src/' + project_name) / (project_name + '.csproj')
            log = command(args.dotnet, 'build', str(project), '-c', 'Release', '--no-restore', '-m:1',
                          '-p:UseSharedCompilation=false', '-p:BuildInParallel=false')
            (output / (service + '-build.log')).write_text(log + '\n')
            assemblies[service] = project.parent / 'bin/Release/net10.0' / (project_name + '.dll')
            env = {**process_env, 'ASPNETCORE_ENVIRONMENT': 'Development', 'DOTNET_ENVIRONMENT': 'Development',
                   'ASPNETCORE_CONTENTROOT': str(project.parent), 'ASPNETCORE_URLS': 'http://127.0.0.1:' + str(8080 + index),
                   'ConnectionStrings__Postgres': 'Host=127.0.0.1;Port=55436;Database=platform;Username=postgres;Password=' + password,
                   'Database__Schema': service, 'Jwt__Secret': signing,
                   'PlatformAuth__TrustedProxySecret': proxy_secret, 'PlatformAuth__InternalServiceSecret': internal_secret,
                   'ShipmentConsumer__Enabled': 'false', 'Outbox__Enabled': 'false',
                   'ShipmentService__BaseUrl': 'http://127.0.0.1:8081', 'Logging__LogLevel__Default': 'Warning'}
            service_envs[service] = env
            log = command(args.dotnet, str(assemblies[service]), '--migrate', env=env)
            (output / (service + '-migration.log')).write_text(log + '\n')
            start(service)
        stage = 'http-authorization'
        accounts = []
        for number in range(3):
            email = 'auth-profile-' + run_id[:12] + '-' + str(number) + '@example.invalid'
            credentials = {'email': email, 'password': 'Fixture!Aa9' + secrets.token_hex(12)}
            profile = http('register-' + str(number), 8080, '/auth/register', 201,
                           {**credentials, 'firstName': 'Offline', 'lastName': 'Synthetic'})
            user = str(uuid.UUID(profile['userId']))
            tokens = http('login-' + str(number), 8080, '/auth/login', body=credentials)
            accounts.append((user, tokens['accessToken'], credentials))
        user, token, credentials = accounts[0]
        other, other_token, _ = accounts[1]
        deleted, deleted_token, _ = accounts[2]
        headers = attest(user, token)
        http('current-user-list', 8081, '/shipments', headers=headers)
        shipment = http('create-owned-shipment', 8081, '/shipments', 201,
                        {'customerId': user, 'origin': 'Synthetic origin', 'destination': 'Synthetic destination', 'weight': 1.25}, headers)
        path = '/shipments/by-id/' + shipment['id']
        http('owner-detail', 8081, path, headers=headers)
        http('other-user-hidden', 8081, path, 404, headers=attest(other, other_token))
        tracking_path = '/tracking/by-tracking-number/' + shipment['trackingNumber']
        timeline = http('internal-shipment-lookup-preserved', 8082, tracking_path, headers=headers)
        if timeline != []: raise GateFailure('Unexpected synthetic tracking event')
        http('tracking-other-user-hidden', 8082, tracking_path, 404, headers=attest(other, other_token))
        http('forged-proxy-secret', 8081, '/shipments', 401, headers=attest(user, token, **{'X-Platform-Proxy-Secret': 'forged'}))
        http('mismatched-attested-user', 8081, '/shipments', 401, headers=attest(other, token))
        http('no-bearer-no-fallback', 8081, '/shipments', 401, headers={k: v for k, v in headers.items() if k != 'Authorization'})
        http('forged-admin-header-is-not-authority', 8082, '/admin/tracking-events', 403, {}, headers)
        sql('INSERT INTO auth."AspNetUserRoles" ("UserId","RoleId") SELECT \'' + user + '\', "Id" FROM auth."AspNetRoles" WHERE "Name"=\'ADMIN\';')
        admin_token = http('login-with-admin-snapshot', 8080, '/auth/login', body=credentials)['accessToken']
        admin_headers = attest(user, admin_token)
        http('current-admin-reaches-model-validation', 8082, '/admin/tracking-events', 400, {}, admin_headers)
        sql('DELETE FROM auth."AspNetUserRoles" WHERE "UserId"=\'' + user + '\' AND "RoleId" IN (SELECT "Id" FROM auth."AspNetRoles" WHERE "Name"=\'ADMIN\');')
        http('removed-admin-same-token-denied', 8082, '/admin/tracking-events', 403, {}, admin_headers)
        http('remaining-user-role-preserved', 8081, '/shipments', headers=admin_headers)
        sql('UPDATE auth."AspNetUsers" SET "IsActive"=false WHERE "Id"=\'' + user + '\';')
        http('disabled-user-shipment-denied', 8081, '/shipments', 401, headers=admin_headers)
        http('disabled-user-tracking-denied', 8082, tracking_path, 401, headers=admin_headers)
        sql('UPDATE auth."AspNetUsers" SET "IsActive"=true WHERE "Id"=\'' + user + '\';')
        sql('DELETE FROM auth."AspNetUsers" WHERE "Id"=\'' + deleted + '\';')
        http('deleted-user-denied', 8081, '/shipments', 401, headers=attest(deleted, deleted_token))
        parts = token.split('.')
        parts[2] = ('a' if parts[2][0] != 'a' else 'b') + parts[2][1:]
        http('invalid-signature-denied-by-real-auth', 8081, '/shipments', 401, headers=attest(user, '.'.join(parts)))
        encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip('=')
        now = int(time.time())
        unsigned = encode(b'{"alg":"HS256","typ":"JWT"}') + '.' + encode(json.dumps(
            {'sub': user, 'userId': user, 'roles': ['USER'], 'iss': 'logistics-platform', 'aud': 'logistics-platform-clients',
             'nbf': now-7200, 'iat': now-7200, 'exp': now-3600}).encode())
        expired = unsigned + '.' + encode(hmac.new(signing.encode(), unsigned.encode(), hashlib.sha256).digest())
        http('expired-signed-token-denied-by-real-auth', 8081, '/shipments', 401, headers=attest(user, expired))
        stage = 'identity-outage'
        stop('auth')
        http('auth-outage-shipment-fails-closed', 8081, '/shipments', 503, headers=headers)
        http('auth-outage-tracking-fails-closed', 8082, tracking_path, 503, headers=headers)
        start('auth')
        http('auth-recovery-same-token', 8081, '/shipments', headers=headers)
        http('removed-admin-still-denied-after-recovery', 8082, '/admin/tracking-events', 403, {}, admin_headers)
        result.update(result='PASS', httpAssertions=len(checks), checks=checks,
                      realAuthAndPostgres=True, awsEventsTested=False, eksNetworkEnforcementTested=False,
                      gatewayResultCacheTested=False)
    except Exception as error:
        result.update(stage=stage, errorType=type(error).__name__, checks=checks)
        if isinstance(error, GateFailure): result['error'] = str(error)
    finally:
        for service in tuple(processes): stop(service)
        for handle in handles: handle.close()
        if attempted_container:
            try:
                if fixture_state(name, run_id) == 'owned': command('docker', 'rm', '-f', name)
                cleanup_confirmed = fixture_state(name, run_id) == 'absent'
            except (GateFailure, subprocess.SubprocessError, OSError, ValueError) as error:
                result.update(result='FAIL', cleanupErrorType=type(error).__name__)
        result.update(cleanupConfirmed=cleanup_confirmed, freeDiskGiBBefore=round(before_free/1024**3, 3),
                      freeDiskGiBAfter=round(shutil.disk_usage(ROOT).free/1024**3, 3))
        (output/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'result': result['result'], 'httpAssertions': result.get('httpAssertions', len(checks)),
                      'stage': result.get('stage'), 'errorType': result.get('errorType'), 'error': result.get('error'),
                      'cleanupConfirmed': cleanup_confirmed, 'evidence': str((output/'summary.json').relative_to(ROOT))}))
    return 0 if result['result'] == 'PASS' and cleanup_confirmed else 1


if __name__ == '__main__':
    raise SystemExit(main())
