"""Offline tests with synthetic in-memory values. Never issues or sends real STS tokens."""
from datetime import timedelta
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cnp_eks_lease', Path(__file__).resolve().parents[1]/'operations/cnp_eks_temporary_session.py')
lease = importlib.util.module_from_spec(spec); spec.loader.exec_module(lease)


class TemporarySessionTests(unittest.TestCase):
    def test_duration_is_bounded_and_requires_cleanup_time(self):
        self.assertEqual(lease.duration(lease.DEADLINE-timedelta(hours=6, minutes=1)), 21600)
        self.assertLess(lease.duration(lease.DEADLINE-timedelta(hours=5)), 21600)
        with self.assertRaises(ValueError): lease.duration(lease.DEADLINE-timedelta(hours=3))
        with self.assertRaises(ValueError): lease.duration(lease.DEADLINE+timedelta(seconds=1))

    def test_environment_removes_credentials_other_profiles_and_debug(self):
        with patch.dict(os.environ, {'AWS_ACCESS_KEY_ID': 'synthetic', 'AWS_SECRET_ACCESS_KEY': 'synthetic',
                'AWS_SESSION_TOKEN': 'synthetic', 'AWS_PROFILE': 'unrelated', 'TF_LOG': 'TRACE', 'AWS_ENDPOINT_URL': 'invalid'}):
            env = lease.clean_env('/run/user/1000/cnp-eks-test/config')
        self.assertEqual(env['AWS_PROFILE'], 'cnp-cert-dev')
        self.assertEqual(env['AWS_SHARED_CREDENTIALS_FILE'], '/dev/null')
        self.assertEqual(env['AWS_EC2_METADATA_DISABLED'], 'true')
        for name in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'TF_LOG', 'AWS_ENDPOINT_URL'):
            self.assertNotIn(name, env)

    def test_config_contains_only_profile_region_and_sdk_process(self):
        text = lease.config_text('/run/user/1000/cnp-eks-test/credentials.sock')
        self.assertIn('[profile cnp-cert-dev]', text)
        self.assertIn('credential_process = /usr/bin/python3 ', text)
        self.assertNotIn('aws_access_key_id', text)
        self.assertNotIn('aws_secret_access_key', text)

    def test_sensitive_and_other_scope_commands_are_rejected(self):
        commands = [ ['bash', '-c', 'anything'], ['aws', '--profile', 'other', 'sts', 'get-caller-identity'],
            ['aws', '--profile=us-east-1', 'sts', 'get-caller-identity'], ['aws', '--region=cnp-cert-dev', 'sts', 'get-caller-identity'],
            ['aws', 'configure', 'export-credentials'], ['aws', 'sts', 'get-session-token'],
            ['aws', 'secretsmanager', 'get-secret-value'], ['aws', 'eks', 'get-token'],
            ['aws', '--debug', 'sts', 'get-caller-identity'], ['kubectl', 'get', 'secrets'],
            ['python3', '-c', 'anything'], ['python3', '../other-project/run.py'],
            ['terragrunt', '--working-dir', '../terragrunt_demo', 'apply'],
            ['terragrunt', '--working-dir', 'infra/live/dev/private-cd', 'apply'] ]
        for command in commands:
            with self.subTest(command=command), self.assertRaises(ValueError): lease.validate_command(command)

    def test_expected_child_commands_are_accepted(self):
        for command in (['aws', '--profile', 'cnp-cert-dev', '--region', 'us-east-1', 'sts', 'get-caller-identity'],
                        ['terragrunt', '--working-dir', 'infra/live/dev/vpc', 'plan'],
                        ['python3', 'scripts/bootstrap/bootstrap.py', '--phase', '0'],
                        ['kubectl', 'get', 'pods', '-n', 'apps']):
            lease.validate_command(command)

    def test_protocol_frames_are_bounded(self):
        self.assertEqual(lease.read_json_line(io.BytesIO(b'{"op":"test"}\n')), {'op': 'test'})
        with self.assertRaises(ValueError): lease.read_json_line(io.BytesIO(b'x'*20), 10)
        with self.assertRaises(ValueError): lease.read_json_line(io.BytesIO(b''))

    @unittest.skipUnless(sys.platform == 'linux', 'Linux SO_PEERCRED and credential_process integration')
    def test_real_aws_cli_profile_resolution_uses_only_synthetic_socket_data(self):
        # configure list resolves the provider without making an AWS service request.
        with tempfile.TemporaryDirectory(prefix='cnp-eks-fake-sdk-') as temp:
            folder = Path(temp); sock = folder/'credentials.sock'; config = folder/'config'
            credentials = {'AccessKeyId': 'ASIA'+'X'*16, 'SecretAccessKey': 'synthetic-test-only',
                           'SessionToken': 'synthetic-test-only', 'Expiration': lease.stamp(lease.now()+timedelta(hours=1))}
            memory = lease.Lease(credentials, folder, lease.now()+timedelta(hours=1))
            server = lease.Server(str(sock), lease.RequestHandler); server.lease = memory
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                config.write_text(lease.config_text(sock))
                result = subprocess.run(['aws', '--profile', 'cnp-cert-dev', 'configure', 'list'],
                    env=lease.clean_env(config), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
                self.assertEqual(result.returncode, 0)
                self.assertIn('custom-process', result.stdout)
                self.assertNotIn(credentials['SecretAccessKey'], result.stdout)
                self.assertNotIn(credentials['SessionToken'], result.stdout)
                memory.closed.set()
                denied = lease.exchange(sock, {'op': 'credentials'})
                self.assertEqual(denied, {'error': 'LEASE_REQUEST_FAILED'})
            finally:
                server.shutdown(); server.server_close()


if __name__ == '__main__': unittest.main()
