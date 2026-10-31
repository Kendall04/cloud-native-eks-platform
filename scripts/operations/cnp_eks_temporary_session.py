"""User-started, EKS-only temporary STS lease. Never run start/serve during preparation.

Secrets travel once over verified SSH stdin, remain in process memory, and reach AWS
SDKs through credential_process pipes. No long-term credential is sent to Linux.
"""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import logging
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import socket
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
import zipfile

ACCOUNT = '341936017254'
PROFILE = 'cnp-cert-dev'
ARN = f'arn:aws:iam::{ACCOUNT}:user/cnp-cert-admin'
REGION = 'us-east-1'
DEADLINE = datetime.fromisoformat('2026-10-17T04:33:05+00:00')
ROOT = Path(__file__).resolve().parents[2]
META = ROOT / '.validation-results/cloud-authorization/temporary-session.json'
TOOLS = ROOT / '.validation-results/cloud-authorization/tools/linux-amd64'
PINS = {
    'terraform': ('https://releases.hashicorp.com/terraform/1.13.4/terraform_1.13.4_linux_amd64.zip',
                  '98aa516201e948306698efd9954ab4cc0d1227c2578ba56245898b5f679e590b'),
    'terragrunt': ('https://github.com/gruntwork-io/terragrunt/releases/download/v0.93.3/terragrunt_linux_amd64',
                   '017c0417dd6d4bedac830766cc16ea52d8a02d02ca2452bc80b581ed0a993775'),
    'kubectl': ('https://dl.k8s.io/release/v1.35.0/bin/linux/amd64/kubectl',
                'a2e984a18a0c063279d692533031c1eff93a262afcc0afdc517375432d060989')}
LIMIT = 256 * 1024


class LeaseError(ValueError): pass


def require(value, code):
    if not value: raise LeaseError(code)


def now(): return datetime.now(timezone.utc)
def stamp(value): return value.astimezone(timezone.utc).isoformat()
def digest(path): return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def duration(at):
    remaining = int((DEADLINE - at).total_seconds()) - 60
    require(remaining >= 4 * 3600, 'LESS_THAN_FOUR_HOURS_REMAIN_NO_TOKEN_ISSUED')
    return min(21600, remaining)


def clean_env(config=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('AWS_', 'TF_LOG'))
           and k not in ('BASH_ENV', 'ENV', 'BASH_XTRACEFD')}
    env.update(AWS_PROFILE=PROFILE, AWS_DEFAULT_PROFILE=PROFILE, AWS_REGION=REGION,
               AWS_DEFAULT_REGION=REGION, AWS_SHARED_CREDENTIALS_FILE='/dev/null',
               AWS_EC2_METADATA_DISABLED='true', AWS_SDK_LOAD_CONFIG='1', AWS_MAX_ATTEMPTS='1',
               AWS_PAGER='', TG_NO_AUTO_INIT='true', TG_BACKEND_REQUIRE_BOOTSTRAP='true')
    env.update(CHECKPOINT_DISABLE='1', TF_IN_AUTOMATION='1')
    if config: env['AWS_CONFIG_FILE'] = str(config)
    env['PATH'] = str(TOOLS) + os.pathsep + env.get('PATH', '')
    return env


def config_text(sock):
    # All paths are absolute, no environment-variable or tilde expansion.
    return (f'[profile {PROFILE}]\nregion = {REGION}\n'
            f'credential_process = /usr/bin/python3 {Path(__file__).resolve()} credential-process {sock}\n')


def read_json_line(stream, limit=LIMIT):
    raw = stream.readline(limit + 1)
    require(raw and len(raw) <= limit, 'INVALID_PROTOCOL_FRAME')
    return json.loads(raw)


def exchange(sock, request):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(10); client.connect(str(sock))
        client.sendall((json.dumps(request) + '\n').encode())
        with client.makefile('rb') as stream: return read_json_line(stream)


def process_start(pid):
    try: return Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[19]
    except (FileNotFoundError, ProcessLookupError): return None


class Lease:
    def __init__(self, credentials, folder, expiry):
        self.credentials, self.folder, self.expiry = credentials, folder, expiry
        self.children = {}; self.lock = threading.Lock()
        self.closed = threading.Event()

    def respond(self, peer_pid, peer_uid, request):
        require(peer_uid == os.getuid() and not self.closed.is_set() and now() < self.expiry,
                'LEASE_UNAVAILABLE')
        op = request.get('op')
        if op == 'credentials': return {'Version': 1, **self.credentials}
        if op == 'register':
            pid = request['pid']; start = process_start(pid)
            require(start and os.getpgid(pid) == pid and
                    Path(f'/proc/{pid}/status').read_text().find(f'PPid:\t{peer_pid}\n') >= 0,
                    'CHILD_NOT_OWNED_BY_WRAPPER')
            with self.lock: self.children[pid] = start
            return {'registered': True}
        if op == 'unregister':
            with self.lock: self.children.pop(request['pid'], None)
            return {'registered': False}
        raise ValueError('UNKNOWN_LEASE_OPERATION')

    def stop_children(self):
        with self.lock: children = dict(self.children)
        for sig in (signal.SIGTERM, signal.SIGKILL):
            for pid, start in children.items():
                if process_start(pid) == start:
                    try:
                        if os.getpgid(pid) == pid: os.killpg(pid, sig)
                    except ProcessLookupError: pass
            if sig == signal.SIGTERM: time.sleep(2)


class RequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            pid, uid, _ = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            response = self.server.lease.respond(pid, uid, read_json_line(self.rfile, 4096))
            self.wfile.write((json.dumps(response) + '\n').encode())
        except Exception:
            self.wfile.write(b'{"error":"LEASE_REQUEST_FAILED"}\n')


if sys.platform == 'linux':
    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True
else:
    class Server:
        def __init__(self, *args): raise LeaseError('LINUX_SERVER_REQUIRED')


def prepare_tools():
    require(sys.platform == 'linux' and shutil.disk_usage(ROOT).free > 3 * 1024**3, 'LINUX_TOOL_PREFLIGHT_FAILED')
    TOOLS.mkdir(parents=True, exist_ok=True); TOOLS.chmod(0o700)
    receipts = TOOLS/'verified-pins.json'
    verified = json.loads(receipts.read_text()) if receipts.exists() else {}
    for name, (url, expected) in PINS.items():
        target = TOOLS / name
        if target.exists():
            require(verified.get(name, {}).get('archiveSha256') == expected and
                    verified[name]['binarySha256'] == hashlib.sha256(target.read_bytes()).hexdigest(),
                    'EXISTING_PRIVATE_TOOL_NOT_VERIFIED')
            continue
        # Exact source-pinned releases only. No global installation or version substitution.
        with urllib.request.urlopen(url, timeout=45) as response: data = response.read(180 * 1024**2)
        require(hashlib.sha256(data).hexdigest() == expected, 'PINNED_DOWNLOAD_CHECKSUM_FAILED')
        if name == 'terraform':
            import io
            with zipfile.ZipFile(io.BytesIO(data)) as archive: data = archive.read('terraform')
        target.write_bytes(data); target.chmod(0o700)
        verified[name] = {'archiveSha256': expected, 'binarySha256': hashlib.sha256(data).hexdigest()}
        receipts.write_text(json.dumps(verified, indent=2)+'\n')
    tf = json.loads(subprocess.check_output([str(TOOLS/'terraform'), 'version', '-json'], text=True))
    tg = subprocess.check_output([str(TOOLS/'terragrunt'), '--version'], text=True)
    kube = json.loads(subprocess.check_output([str(TOOLS/'kubectl'), 'version', '--client', '-o', 'json'], text=True))
    require(tf['terraform_version'] == '1.13.4' and 'v0.93.3' in tg and
            kube['clientVersion']['gitVersion'] == 'v1.35.0', 'PINNED_TOOL_VERSION_MISMATCH')
    require(subprocess.check_output(['helm', 'version', '--short'], text=True).startswith('v4.2.2')
            and shutil.which('session-manager-plugin'), 'HELM_OR_SSM_NOT_READY')
    # Check actual provider/schema before requesting any temporary credentials.
    with tempfile.TemporaryDirectory(prefix='cnp-eks-schema-', dir=TOOLS) as temp:
        folder = Path(temp)
        (folder/'main.tf').write_text('terraform {\n required_providers {\n aws = { source = "hashicorp/aws", version = "5.100.0" }\n }\n}\n')
        (folder/'.terraform.lock.hcl').write_bytes((ROOT/'infra/live/dev/vpc/.terraform.lock.hcl').read_bytes())
        (folder/'empty-config').write_text('')
        cache = TOOLS/'provider-cache'; cache.mkdir(exist_ok=True)
        env = clean_env(folder/'empty-config'); env['TF_PLUGIN_CACHE_DIR'] = str(cache)
        for command in (['init', '-backend=false', '-get=false', '-lockfile=readonly', '-input=false'],
                        ['providers', 'schema', '-json']):
            result = subprocess.run([str(TOOLS/'terraform'), *command], cwd=folder, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
            require(result.returncode == 0, 'PINNED_LINUX_PROVIDER_SCHEMA_FAILED_NO_TOKEN_ISSUED')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    clean = not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()
    require(clean, 'REMOTE_SOURCE_NOT_CLEAN')
    print(json.dumps({'scriptSha256LF': digest(Path(__file__)), 'toolsReady': True, 'head': head}))


def serve():
    require(sys.platform == 'linux', 'LINUX_SERVER_REQUIRED')
    import resource
    logging.disable(logging.CRITICAL)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0)); os.umask(0o077)
    payload = read_json_line(sys.stdin.buffer)
    credentials = payload['credentials']
    require(set(credentials) == {'AccessKeyId', 'SecretAccessKey', 'SessionToken', 'Expiration'} and
            credentials['AccessKeyId'].startswith('ASIA') and payload.get('mfaAuthenticated') is True,
            'TEMPORARY_MFA_SESSION_REQUIRED')
    expiry = datetime.fromisoformat(credentials['Expiration'].replace('Z', '+00:00'))
    require(now() < expiry <= DEADLINE, 'EXPIRATION_OUTSIDE_APPROVED_WINDOW')
    runtime = Path('/run/user')/str(os.getuid())
    require(runtime.is_dir() and subprocess.check_output(['stat', '-f', '-c', '%T', str(runtime)], text=True).strip() == 'tmpfs', 'TMPFS_REQUIRED')
    if META.exists():
        previous = json.loads(META.read_text())
        require(previous.get('status') != 'ACTIVE' or not process_start(previous.get('pid', -1)), 'EXISTING_EKS_LEASE_ACTIVE')
    folder = Path(tempfile.mkdtemp(prefix='cnp-eks-sts-', dir=runtime)); folder.chmod(0o700)
    sock = folder/'credentials.sock'; config = folder/'config'; config.write_text(config_text(sock)); config.chmod(0o600)
    lease = Lease(credentials, folder, expiry)
    server = Server(str(sock), RequestHandler); server.lease = lease
    threading.Thread(target=server.serve_forever, daemon=True).start()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP): signal.signal(sig, lambda *args: stop.set())
    metadata = {'status': 'STARTING', 'pid': os.getpid(), 'uid': os.getuid(), 'config': str(config),
                'socket': str(sock), 'expiresUtc': stamp(expiry), 'account': ACCOUNT, 'profile': PROFILE}
    try:
        result = subprocess.run(['aws', '--profile', PROFILE, '--region', REGION, '--no-cli-pager',
            '--cli-connect-timeout', '5', '--cli-read-timeout', '20', 'sts', 'get-caller-identity',
            '--query', '{Account:Account,Arn:Arn}', '--output', 'json'], env=clean_env(config),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=40)
        require(result.returncode == 0, 'REMOTE_STS_VERIFICATION_FAILED')
        identity = json.loads(result.stdout)
        require(identity == {'Account': ACCOUNT, 'Arn': ARN}, 'REMOTE_IDENTITY_MISMATCH')
        metadata['status'] = 'ACTIVE'; META.parent.mkdir(parents=True, exist_ok=True)
        META.write_text(json.dumps(metadata, indent=2)+'\n'); META.chmod(0o600)
        print(json.dumps({**identity, 'Expiration': stamp(expiry)}), flush=True)
        def read_stop():
            sys.stdin.buffer.readline(); stop.set()  # STOP or stdin EOF closes this lease.
        threading.Thread(target=read_stop, daemon=True).start()
        while not stop.wait(1) and now().timestamp() < expiry.timestamp()-120: pass
    finally:
        lease.closed.set(); lease.stop_children(); server.shutdown(); server.server_close()
        metadata['status'] = 'CLOSED'
        META.write_text(json.dumps(metadata, indent=2)+'\n')
        require(folder.parent == runtime and folder.name.startswith('cnp-eks-sts-'), 'CLEANUP_PATH_INVALID')
        for path in (config, sock): path.unlink(missing_ok=True)
        folder.rmdir()


def validate_command(command):
    require(command and command[0] in {'aws', 'terraform', 'terragrunt', 'helm', 'kubectl', 'python3', 'docker'}, 'COMMAND_NOT_ALLOWLISTED')
    require(not any(x in {'--debug', '--no-verify-ssl', '-debug', '--password'} or x.startswith('--endpoint-url') for x in command), 'DEBUG_OR_CREDENTIAL_ARGUMENT_FORBIDDEN')
    for index, value in enumerate(command):
        if value == '--profile': require(index+1 < len(command) and command[index+1] == PROFILE, 'OTHER_PROFILE_FORBIDDEN')
        if value == '--region': require(index+1 < len(command) and command[index+1] == REGION, 'OTHER_REGION_FORBIDDEN')
        if value.startswith('--profile='): require(value.split('=', 1)[1] == PROFILE, 'OTHER_PROFILE_FORBIDDEN')
        if value.startswith('--region='): require(value.split('=', 1)[1] == REGION, 'OTHER_REGION_FORBIDDEN')
    require('private-cd' not in ' '.join(command), 'PRIVATE_CD_OUT_OF_SCOPE')
    if command[0] == 'aws':
        require(not any(x in command for x in ('configure', 'get-session-token', 'get-federation-token', 'assume-role',
                'get-secret-value', 'batch-get-secret-value', 'get-login-password', 'get-token', '--with-decryption')),
                'CREDENTIAL_OUTPUT_FORBIDDEN')
    if command[0] == 'python3':
        require(len(command) > 1 and not command[1].startswith('-') and
                (ROOT/command[1]).resolve().is_relative_to(ROOT/'scripts'), 'PYTHON_SOURCE_OUTSIDE_EKS_SCRIPTS')
    if command[0] == 'kubectl': require(not any(x.lower() in {'secret', 'secrets'} for x in command), 'RAW_KUBERNETES_SECRETS_FORBIDDEN')
    for index, value in enumerate(command):
        if value in {'--working-dir', '--terragrunt-working-dir'}:
            require((ROOT/command[index+1]).resolve().is_relative_to(ROOT), 'WORKDIR_OUTSIDE_EKS')
        if value.startswith(('-chdir=', '--working-dir=')):
            require((ROOT/value.split('=', 1)[1]).resolve().is_relative_to(ROOT), 'WORKDIR_OUTSIDE_EKS')


def run(command):
    validate_command(command)
    metadata = json.loads(META.read_text())
    require(metadata['status'] == 'ACTIVE' and metadata['uid'] == os.getuid() and
            metadata['account'] == ACCOUNT and metadata['profile'] == PROFILE and
            now().timestamp() < datetime.fromisoformat(metadata['expiresUtc']).timestamp()-300,
            'NO_USABLE_EKS_LEASE')
    secrets = exchange(metadata['socket'], {'op': 'credentials'})
    require('Version' in secrets, 'LEASE_NOT_AVAILABLE')
    env = clean_env(metadata['config'])
    process = subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace')
    try:
        registered = exchange(metadata['socket'], {'op': 'register', 'pid': process.pid})
        require(registered.get('registered'), 'COMMAND_REGISTRATION_FAILED')
        for line in process.stdout:
            for key in ('AccessKeyId', 'SecretAccessKey', 'SessionToken'): line = line.replace(secrets[key], '[REDACTED]')
            sys.stdout.write(line); sys.stdout.flush()
        return process.wait()
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL)
        try: exchange(metadata['socket'], {'op': 'unregister', 'pid': process.pid})
        except Exception: pass


def start():
    require(os.name == 'nt', 'START_FROM_KENDALL_WINDOWS_TERMINAL')
    logging.disable(logging.CRITICAL)
    duration(now())
    local_head = subprocess.check_output(['git', '-c', 'safe.directory='+str(ROOT), 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(not subprocess.check_output(['git', '-c', 'safe.directory='+str(ROOT), 'status', '--porcelain'], cwd=ROOT, text=True).strip(), 'LOCAL_SOURCE_NOT_CLEAN')
    sys.path.insert(0, str(ROOT/'.validation-results/python-deps'))
    import boto3
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    identity = session.client('sts').get_caller_identity()
    require(identity['Account'] == ACCOUNT and identity['Arn'] == ARN, 'LOCAL_IDENTITY_MISMATCH')
    iam = session.client('iam')
    devices = iam.list_mfa_devices(UserName='cnp-cert-admin')['MFADevices']
    if not devices:
        print('MFA TOTP obligatorio para que GetSessionToken permita IAM. Registra una app autenticadora de códigos para cnp-cert-admin; verifica la cuenta 341936017254:')
        print('https://console.aws.amazon.com/iam/home#/users/details/cnp-cert-admin?section=security_credentials')
        input('Pulsa Enter cuando esté registrado, o Ctrl+C para cancelar: ')
        devices = iam.list_mfa_devices(UserName='cnp-cert-admin')['MFADevices']
    require(len(devices) == 1, 'EXACTLY_ONE_MFA_DEVICE_REQUIRED_NO_TOKEN_ISSUED')
    ssh = ['ssh', '-F', str(Path.home()/'.ssh/config'), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
           '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=2', 'codex-vm']
    remote = '/home/kendall/work/cloud-native-platform-eks/scripts/operations/cnp_eks_temporary_session.py'
    preflight = subprocess.run([*ssh, '/usr/bin/python3', remote, 'prepare-tools'], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, timeout=600)
    require(preflight.returncode == 0, 'REMOTE_PINNED_PREFLIGHT_FAILED_NO_TOKEN_ISSUED')
    check = json.loads(preflight.stdout)
    require(check['scriptSha256LF'] == digest(Path(__file__)) and check['toolsReady'] and
            check['head'] == local_head, 'REMOTE_SOURCE_MISMATCH')
    code = getpass.getpass('Código MFA de seis dígitos (oculto): ')
    require(re.fullmatch('[0-9]{6}', code), 'INVALID_MFA_INPUT')
    credentials = session.client('sts').get_session_token(DurationSeconds=duration(now()),
        SerialNumber=devices[0]['SerialNumber'], TokenCode=code)['Credentials']
    credentials['Expiration'] = stamp(credentials['Expiration'])
    payload = json.dumps({'credentials': credentials, 'mfaAuthenticated': True})+'\n'
    process = subprocess.Popen([*ssh, '/usr/bin/python3', '-u', remote, 'serve'], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    try:
        process.stdin.write(payload); process.stdin.flush()
        messages = queue.Queue()
        threading.Thread(target=lambda: messages.put(process.stdout.readline(16384)), daemon=True).start()
        ready = json.loads(messages.get(timeout=50))
        require(set(ready) == {'Account', 'Arn', 'Expiration'} and ready['Account'] == ACCOUNT and ready['Arn'] == ARN,
                'REMOTE_READY_IDENTITY_FAILED')
        print(json.dumps(ready, indent=2))
        print('Sesión EKS activa. Mantén esta terminal abierta hasta completar la retirada. Ctrl+C cierra el contexto; no borra recursos AWS.')
        while process.poll() is None: time.sleep(1)
    finally:
        try: process.stdin.write('STOP\n'); process.stdin.flush(); process.stdin.close()
        except (BrokenPipeError, OSError, ValueError): pass
        try: process.wait(timeout=12)
        except subprocess.TimeoutExpired: process.terminate()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='mode', required=True)
    for mode in ('start', 'prepare-tools', 'serve'): sub.add_parser(mode)
    credential = sub.add_parser('credential-process'); credential.add_argument('socket')
    command = sub.add_parser('run'); command.add_argument('command', nargs=argparse.REMAINDER)
    args = p.parse_args()
    if args.mode == 'start': start()
    elif args.mode == 'prepare-tools': prepare_tools()
    elif args.mode == 'serve': serve()
    elif args.mode == 'credential-process':
        require(not sys.stdout.isatty(), 'SDK_PIPE_REQUIRED')
        result = exchange(args.socket, {'op': 'credentials'})
        require('Version' in result, 'LEASE_UNAVAILABLE')
        print(json.dumps(result))  # SDK private pipe only. Never invoke manually.
    else: return run(args.command[1:] if args.command[:1] == ['--'] else args.command)
    return 0


if __name__ == '__main__':
    try: sys.exit(main())
    except KeyboardInterrupt: sys.exit(130)
    except LeaseError as error:
        code = str(error)
        sys.exit('HANDOFF_STOPPED: '+code if re.fullmatch('[A-Z0-9_]+', code) else 'HANDOFF_STOPPED')
    except Exception: sys.exit('HANDOFF_STOPPED: inspect documented prerequisites; no credential details emitted')
