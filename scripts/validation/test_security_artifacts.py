"""Publication-boundary regressions; fixtures are deliberately nonfunctional secrets."""
import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import security_artifacts as artifacts
from security import evaluate, findings, scan

# Construct only a marker and invalid body: never generate a usable test key.
FAKE_PEM = '-----BEGIN ' + 'PRIVATE KEY-----\nnot-a-real-key\n-----END ' + 'PRIVATE KEY-----'


class PublicEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private = self.root / 'private'
        self.public = self.root / 'public'
        self.private.mkdir()
        self.item = findings({'SchemaVersion': 2, 'Results': [{
            'Target': 'fixture.json', 'Vulnerabilities': [{
                'VulnerabilityID': 'CVE-fixture', 'PkgName': 'fixture',
                'InstalledVersion': '1.0', 'FixedVersion': '1.1', 'Severity': 'HIGH',
            }]}]}, 'source/fixture')[0]
        self.baseline = {'schemaVersion': 1, 'reviewedOn': '2026-10-14', 'exceptions': [{
            'fingerprint': self.item['fingerprint'], 'reason': 'Reviewed fixture only',
            'expires': '2027-01-12'}]}

    def write(self, name, value):
        (self.private / name).write_text(json.dumps(value), encoding='utf-8')

    def complete(self, items=None):
        from datetime import date
        items = items if items is not None else [self.item]
        self.write('findings.json', {'schemaVersion': 1, 'findings': items})
        self.write('policy-result.json', evaluate(items, self.baseline, date(2026, 11, 3)))
        self.write('metadata.json', {'commit': 'a' * 40, 'tool': {'Version': '0.71.2'},
                   'event': 'pull_request', 'scannedAt': '2026-11-03T00:00:00Z',
                   'workflowRunId': '123', 'workflowRunAttempt': '1'})

    def stage(self, outcome='success'):
        return artifacts.stage(self.private, self.public, outcome, self.baseline)

    def test_normal_manifest_without_secret_is_safe(self):
        artifacts.inspect_document('apiVersion: v1\nkind: ConfigMap\ndata:\n  mode: demo\n')

    def test_secret_stringdata_is_rejected(self):
        with self.assertRaises(artifacts.UnsafeEvidence):
            artifacts.inspect_document('kind: Secret\nstringData:\n  credential: synthetic-only\n')

    def test_base64_tls_key_is_rejected(self):
        value = {'kind': 'Secret', 'data': {'tls.key': base64.b64encode(FAKE_PEM.encode()).decode()}}
        with self.assertRaises(artifacts.UnsafeEvidence):
            artifacts.inspect_document(yaml.safe_dump(value))

    def test_direct_pem_is_rejected(self):
        with self.assertRaisesRegex(artifacts.UnsafeEvidence, 'PRIVATE_KEY'):
            artifacts.inspect_document(FAKE_PEM)

    def test_scanner_json_embedded_manifest_is_rejected(self):
        value = {'Results': [{'Code': {'Content': 'kind: Secret\nstringData:\n  token: synthetic'}}]}
        with self.assertRaises(artifacts.UnsafeEvidence):
            artifacts.inspect_document(json.dumps(value))

    def test_embedded_json_and_base64_layers_are_inspected(self):
        for text in (FAKE_PEM, json.dumps({'kind': 'Secret', 'data': {'x': 'synthetic'}})):
            for layers in range(1, 4):
                encoded = text.encode()
                for _ in range(layers):
                    encoded = base64.b64encode(encoded)
                with self.subTest(layers=layers), self.assertRaises(artifacts.UnsafeEvidence):
                    artifacts.inspect_document(json.dumps({'description': encoded.decode()}))

    def test_unexpected_staging_file_is_rejected(self):
        self.complete(); self.stage()
        (self.public / 'extra.json').write_text('{}')
        with self.assertRaisesRegex(artifacts.UnsafeEvidence, 'UNEXPECTED_STAGING_FILE'):
            artifacts.verify_staging(self.public)

    def test_nested_archive_is_rejected_by_format_policy(self):
        self.complete(); self.stage()
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, 'w') as z:
            z.writestr('key.pem', FAKE_PEM)
        with zipfile.ZipFile(self.public / 'nested.zip', 'w') as z:
            z.writestr('inner.zip', inner.getvalue())
        with self.assertRaisesRegex(artifacts.UnsafeEvidence, 'UNEXPECTED_STAGING_FILE'):
            artifacts.verify_staging(self.public)

    def test_archive_disguised_as_allowed_json_is_rejected(self):
        self.public.mkdir()
        with zipfile.ZipFile(self.public / artifacts.PUBLIC_FILE, 'w') as z:
            z.writestr('key.pem', FAKE_PEM)
        with self.assertRaises(artifacts.UnsafeEvidence):
            artifacts.verify_staging(self.public)

    def test_failed_scanner_exposes_only_validated_diagnostic(self):
        error = subprocess.CalledProcessError(2, ['trivy', 'fixture'], stderr=FAKE_PEM)
        with patch('security.subprocess.run', side_effect=error), self.assertRaises(subprocess.CalledProcessError):
            scan(['config', 'fixture'], self.private / 'report.json')
        self.stage('failure')
        public = (self.public / artifacts.PUBLIC_FILE).read_text()
        self.assertNotIn(FAKE_PEM, public)
        report = json.loads(public)
        self.assertEqual('SCAN_FAILED', report['status'])
        self.assertEqual([], report['findings'])
        artifacts.verify_staging(self.public)

    def test_success_without_scan_outputs_fails_closed(self):
        with self.assertRaisesRegex(artifacts.UnsafeEvidence, 'MISSING_SCAN_OUTPUT'):
            self.stage()
        self.assertFalse(self.public.exists())

    def test_valid_summary_keeps_findings_classification_and_exception(self):
        self.complete()
        digest = self.stage()
        report = json.loads((self.public / artifacts.PUBLIC_FILE).read_text())
        self.assertEqual([self.item['fingerprint']], report['policy']['acceptedExisting'])
        self.assertEqual([self.baseline['exceptions'][0]], report['exceptions'])
        self.assertEqual(1, len(report['findings']))
        for key in artifacts.FINDING_FIELDS:
            self.assertEqual(self.item[key], report['findings'][0][key])
        self.assertEqual(digest, hashlib.sha256((self.public / artifacts.PUBLIC_FILE).read_bytes()).hexdigest())

    def test_duplicate_scanner_occurrences_keep_counts_and_one_exception(self):
        self.complete([self.item, deepcopy(self.item)])
        self.stage()
        report = json.loads((self.public / artifacts.PUBLIC_FILE).read_text())
        self.assertEqual(2, len(report['findings']))
        self.assertEqual(2, len(report['policy']['acceptedExisting']))
        self.assertEqual(1, len(report['exceptions']))
        report['findings'][1]['title'] = 'Conflicting evidence for same fingerprint'
        with self.assertRaisesRegex(artifacts.UnsafeEvidence, 'FINGERPRINT_COLLISION'):
            artifacts.validate_report(report)

    def test_policy_failure_is_preserved_not_relabelled_pass(self):
        self.baseline['exceptions'] = []
        self.complete(); self.stage('failure')
        report = json.loads((self.public / artifacts.PUBLIC_FILE).read_text())
        self.assertEqual([self.item['fingerprint']], report['policy']['newBlocking'])
        self.assertEqual('failure', report['scanOutcome'])

    def test_raw_render_and_scanner_code_never_copied(self):
        self.item['resource'] = FAKE_PEM
        self.complete()
        (self.private / 'rendered').mkdir()
        (self.private / 'rendered/addons.yaml').write_text(FAKE_PEM)
        self.write('kubernetes-config.json', {'Code': FAKE_PEM})
        self.stage()
        self.assertEqual([artifacts.PUBLIC_FILE], [p.name for p in self.public.iterdir()])
        data = (self.public / artifacts.PUBLIC_FILE).read_text()
        self.assertNotIn(FAKE_PEM, data)
        self.assertIn(hashlib.sha256(FAKE_PEM.encode()).hexdigest(), data)

    def test_secret_in_allowlisted_field_blocks_staging(self):
        self.item['title'] = FAKE_PEM
        self.complete()
        with self.assertRaisesRegex(artifacts.UnsafeEvidence, 'PRIVATE_KEY'):
            self.stage()
        self.assertFalse(self.public.exists())

    def test_policy_cannot_drop_a_finding(self):
        self.complete()
        self.write('policy-result.json', {k: [] for k in artifacts.CATEGORIES})
        with self.assertRaisesRegex(artifacts.UnsafeEvidence, 'POLICY_FINDING_MISMATCH'):
            self.stage()

    def test_stale_staging_and_symlinks_are_not_reused(self):
        self.complete(); self.public.mkdir()
        with self.assertRaisesRegex(artifacts.UnsafeEvidence, 'NON_FRESH_STAGING'):
            self.stage()
        with patch.object(Path, 'is_symlink', return_value=True), self.assertRaises(artifacts.UnsafeEvidence):
            artifacts.verify_staging(self.public)

    def test_unknown_public_json_field_and_duplicate_keys_fail(self):
        self.complete(); self.stage()
        path = self.public / artifacts.PUBLIC_FILE
        original = path.read_text()
        data = json.loads(original); data['unreviewed'] = 'anything'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(artifacts.UnsafeEvidence, 'PUBLIC_SCHEMA'):
            artifacts.verify_staging(self.public)
        path.write_text('{"status": "SCAN_FAILED", "status": "SCANNED"}')
        with self.assertRaises(artifacts.UnsafeEvidence):
            artifacts.verify_staging(self.public)

    def test_cli_failure_does_not_print_payload(self):
        self.complete(); self.stage()
        path = self.public / artifacts.PUBLIC_FILE
        report = json.loads(path.read_text()); report['findings'][0]['title'] = FAKE_PEM
        path.write_text(json.dumps(report))
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/ci/security_artifacts.py'),
                                 'verify', '--public', str(self.public)], capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn(FAKE_PEM, result.stdout + result.stderr)
        self.assertNotIn('not-a-real-key', result.stdout + result.stderr)
        self.assertIn('BLOCKED category=PRIVATE_KEY', result.stderr)

    def test_workflow_only_uploads_verified_staging_after_failed_or_passed_scan(self):
        workflow = yaml.load((ROOT / '.github/workflows/validate.yml').read_text(), Loader=yaml.BaseLoader)
        for name in ('source-security', 'containers'):
            job = workflow['jobs'][name]
            stage = next(s for s in job['steps'] if s.get('id') == 'public-evidence')
            upload = next(s for s in job['steps'] if 'actions/upload-artifact@' in s.get('uses', ''))
            self.assertEqual('always()', stage['if'])
            self.assertEqual("${{ always() && steps.public-evidence.outcome == 'success' }}", upload['if'])
            self.assertIn('security-public/', upload['with']['path'])
            self.assertNotIn('security-private', upload['with']['path'])
            self.assertIn('security_artifacts.py stage', stage['run'])
            self.assertIn('security_artifacts.py verify', stage['run'])
            self.assertNotIn('continue-on-error', next(s for s in job['steps'] if s.get('id') == 'scan'))



if __name__ == '__main__':
    unittest.main()
