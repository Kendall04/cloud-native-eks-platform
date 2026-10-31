import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from validate_r7 import snapshot,validate,ROOT
from postgres_gate import check_trx
from secret_scan import inspect_text
sys.path.insert(0,str(ROOT/'scripts/cd'))
from scan_policy import require_clean_scan

class ClosureTests(unittest.TestCase):
    def test_freeze_metadata_cannot_revert_to_proposed_candidate(self):
        for field in ('tagCreated', 'constructionFrozen'):
            data=snapshot(); data['candidate'][field]=False
            with self.subTest(field=field), self.assertRaises(ValueError): validate(data)

    def test_valid(self):validate(snapshot())
    def test_isolated_dependabot_module_lock_update_remains_blocked(self):
        module_lock = ROOT / 'infra/modules/vpc/.terraform.lock.hcl'
        read_bytes = Path.read_bytes
        def changed_lock(path):
            content = read_bytes(path)
            return content + b'\n# isolated provider update\n' if path == module_lock else content
        with patch.object(Path, 'read_bytes', changed_lock), self.assertRaisesRegex(ValueError, 'Stack/module provider locks drift'):
            validate(snapshot())
    def test_false_certification_rejected(self):
        data=snapshot();data['candidate']['runtimeCertified']=True
        with self.assertRaises(ValueError):validate(data)
    def test_missing_r3_skip_gate_rejected(self):
        data=snapshot();data['ci']=data['ci'].replace('postgres_gate.py r3','-m unittest discover')
        with self.assertRaises(ValueError):validate(data)
    def test_missing_r5_skip_gate_rejected(self):
        data=snapshot();data['ci']=data['ci'].replace('postgres_gate.py trx','echo accepted')
        with self.assertRaises(ValueError):validate(data)
    def test_remote_deploy_regression(self):
        data=snapshot();data['deploy']+='\n# kubectl forbidden'
        with self.assertRaises(ValueError):validate(data)
    def test_trx_skipped_failed_or_empty_cannot_pass(self):
        for total,passed,failed,skipped in [(0,0,0,0),(26,10,0,16),(26,25,1,0),(26,26,0,0)]:
            with tempfile.TemporaryDirectory() as directory:
                p=Path(directory)/'test.trx';p.write_text(f'<TestRun><Counters total="{total}" passed="{passed}" failed="{failed}" notExecuted="{skipped}"/></TestRun>')
                if total==26 and passed==26:check_trx(p)
                else:
                    with self.assertRaises(ValueError):check_trx(p)
    def test_secret_detection_redacts(self):
        key='AK'+'IA'+'A'*16
        issues=inspect_text('fixture.txt',key)
        self.assertTrue(issues);self.assertNotIn(key,str(issues))
        self.assertTrue(inspect_text('appsettings.json',json.dumps({'Jwt':{'Secret':'unsafe-not-a-placeholder'}})))
    def test_secret_examples(self):
        self.assertFalse(inspect_text('appsettings.json',json.dumps({'Jwt':{'Secret':'replace-with-a-32-byte-or-longer-secret'}})))

class ScanGateTests(unittest.TestCase):
    def test_clean_scan(self):
        ecr=Mock();ecr.describe_image_scan_findings.return_value={'imageScanStatus':{'status':'COMPLETE'},'imageScanFindings':{'imageScanCompletedAt':datetime.now(timezone.utc),'findingSeverityCounts':{'LOW':2}}}
        require_clean_scan(ecr,'fixture','sha256:'+'a'*64)
    def test_findings_and_unknown_fail_closed(self):
        for status,findings in [('COMPLETE',{'imageScanCompletedAt':'test','findingSeverityCounts':{'HIGH':1}}),('FAILED',{}),('ACTIVE',{}),('COMPLETE',{})]:
            ecr=Mock();ecr.describe_image_scan_findings.return_value={'imageScanStatus':{'status':status},'imageScanFindings':findings}
            with self.assertRaises(ValueError):require_clean_scan(ecr,'fixture','sha256:'+'a'*64)
    def test_pending_timeout(self):
        ecr=Mock();ecr.describe_image_scan_findings.return_value={'imageScanStatus':{'status':'PENDING'}}
        with self.assertRaises(TimeoutError):require_clean_scan(ecr,'fixture','digest',timeout=1,clock=Mock(side_effect=[0,0,2]),sleep=lambda _:None)


class EntrypointTests(unittest.TestCase):
    def test_external_skips_never_silently_pass(self):
        from validate_release_candidate import result_exit_code
        self.assertEqual(2,result_exit_code(False,True,'local',False))
        self.assertEqual(0,result_exit_code(False,True,'local',True))
        self.assertEqual(2,result_exit_code(False,True,'ci',False))
        self.assertEqual(1,result_exit_code(True,True,'local',True))
    def test_inventory_includes_all_release_validators(self):
        from validate_release_candidate import inventory
        self.assertEqual([f'validate_r{i}.py' for i in range(1,8)],inventory()['validators'])
        self.assertIn('tests/EventReliability.Tests/EventReliability.Tests.csproj',inventory()['dotnet'])
