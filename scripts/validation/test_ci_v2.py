"""Behavioral security policy and CI topology regressions; no cloud adapters."""
import copy
from datetime import date
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
from security import findings, evaluate, identify_local_sbom, verify_registry_identity, validate_sbom, scan
from regressions import files


def workflow(name='validate.yml'):
    return yaml.load((ROOT / '.github/workflows' / name).read_text(), Loader=yaml.BaseLoader)


class SecurityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.report = {'SchemaVersion': 2, 'Results': [{'Target': 'app.deps.json', 'Vulnerabilities': [{
            'VulnerabilityID': 'CVE-fixture', 'PkgName': 'Fixture', 'InstalledVersion': '1.0',
            'Severity': 'HIGH', 'FixedVersion': '1.1'}]}]}
        self.item = findings(self.report, 'image/auth')[0]
        self.baseline = {'schemaVersion': 1, 'reviewedOn': '2026-10-14', 'exceptions': [{
            'fingerprint': self.item['fingerprint'], 'reason': 'Reviewed fixture', 'expires': '2027-01-12'}]}

    def test_new_high_blocks(self):
        self.assertEqual(1, len(evaluate([self.item], {**self.baseline, 'exceptions': []})['newBlocking']))

    def test_existing_is_visible_within_window(self):
        self.assertEqual([self.item], evaluate([self.item], self.baseline, date(2026, 10, 14))['acceptedExisting'])

    def test_expiry_blocks(self):
        self.assertEqual([self.item], evaluate([self.item], self.baseline, date(2027, 1, 12))['expiredBlocking'])

    def test_missing_fix_is_not_suppressed(self):
        self.item['fixedVersion'] = ''
        self.assertEqual([self.item], evaluate([self.item], {**self.baseline, 'exceptions': []})['newBlocking'])

    def test_medium_is_advisory(self):
        self.item['severity'] = 'MEDIUM'
        self.assertEqual([self.item], evaluate([self.item], self.baseline)['advisory'])

    def test_exception_cannot_cover_other_service_version_or_severity(self):
        for change in ('scope', 'installed', 'severity', 'target'):
            other = copy.deepcopy(self.report)
            if change == 'scope': item = findings(other, 'image/shipment')[0]
            else:
                if change == 'target': other['Results'][0]['Target'] = 'other.deps.json'
                else: other['Results'][0]['Vulnerabilities'][0][{'installed': 'InstalledVersion', 'severity': 'Severity'}[change]] = {'installed': '2.0', 'severity': 'CRITICAL'}[change]
                item = findings(other, 'image/auth')[0]
            with self.subTest(change=change):
                self.assertEqual([item], evaluate([item], self.baseline)['newBlocking'])

    def test_invalid_reports_fail_closed(self):
        for report in ({}, {'SchemaVersion': 3, 'Results': []}, {'SchemaVersion': 2}):
            with self.subTest(report=report), self.assertRaises(ValueError): findings(report, 'source')

    def test_exceptions_need_reason_and_bounded_expiry(self):
        for key, value in (('reason', ''), ('expires', '2028-01-01')):
            baseline = copy.deepcopy(self.baseline)
            baseline['exceptions'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): evaluate([self.item], baseline)

    def test_misconfiguration_is_scoped_to_resource(self):
        report = {'SchemaVersion': 2, 'Results': [{'Target': 'main.tf', 'Misconfigurations': [{
            'ID': 'AVD-fixture', 'Severity': 'HIGH', 'CauseMetadata': {'Resource': 'aws_s3_bucket.example'}}]}]}
        item = findings(report, 'config/infra/modules')[0]
        self.assertEqual('aws_s3_bucket.example', item['resource'])
        self.assertEqual('misconfiguration', item['kind'])

    def test_kubernetes_exceptions_do_not_cover_other_objects(self):
        report = {'SchemaVersion': 2, 'Results': [{'Target': 'addons.yaml', 'Misconfigurations': [{
            'ID': 'KSV-fixture', 'Severity': 'HIGH', 'Message': 'Deployment auth requires review'}]}]}
        first = findings(report, 'config/kubernetes')[0]
        report['Results'][0]['Misconfigurations'][0]['Message'] = 'Deployment shipment requires review'
        self.assertNotEqual(first['fingerprint'], findings(report, 'config/kubernetes')[0]['fingerprint'])

    def test_local_sbom_never_claims_registry_digest(self):
        document = {'metadata': {'component': {'bom-ref': 'synthetic', 'purl': 'pkg:oci/fake',
                     'properties': [{'name': 'aquasecurity:trivy:RepoDigest', 'value': 'synthetic'}]}},
                    'dependencies': [{'ref': 'synthetic', 'dependsOn': ['dependency']}]}
        result = identify_local_sbom(document, 'sha256:' + 'a' * 64)
        component = result['metadata']['component']
        self.assertNotIn('purl', component)
        self.assertEqual([], component['properties'])
        self.assertEqual(component['bom-ref'], result['dependencies'][0]['ref'])

    def test_os_fingerprint_does_not_depend_on_local_tag(self):
        report = copy.deepcopy(self.report)
        report['Metadata'] = {'OS': {'Name': '22.04'}}
        report['Results'][0].update(Class='os-pkgs', Type='ubuntu', Target='auth:commit-one (ubuntu 22.04)')
        first = findings(report, 'image/auth')[0]
        report['Results'][0]['Target'] = 'auth:commit-two (ubuntu 22.04)'
        self.assertEqual(first['fingerprint'], findings(report, 'image/auth')[0]['fingerprint'])

    def test_registry_metadata_requires_a_resolved_digest(self):
        from unittest.mock import patch
        digest = 'sha256:' + 'a' * 64
        image = 'example.invalid/auth@' + digest
        with patch('security.run', return_value=json.dumps([image])):
            verify_registry_identity(image, digest)
        with patch('security.run', return_value='[]'), self.assertRaises(ValueError):
            verify_registry_identity(image, digest)
        with self.assertRaises(ValueError):
            verify_registry_identity('local:tag', digest)

    def test_offline_sbom_schema_rejects_invalid_inventory(self):
        import tempfile
        from jsonschema import ValidationError
        document = {'bomFormat': 'CycloneDX', 'specVersion': '1.7', 'version': 1,
                    'metadata': {'component': {'type': 'container', 'name': 'local-fixture'}},
                    'components': [{'type': 'library', 'name': 'fixture', 'version': '1.0'}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sbom.json'
            path.write_text(json.dumps(document))
            self.assertEqual(1, validate_sbom(path)['components'])
            document['components'][0]['type'] = 'invented-type'
            path.write_text(json.dumps(document))
            with self.assertRaises(ValidationError): validate_sbom(path)

    def test_scanner_failure_remains_failure_and_records_safe_diagnostics(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.json'
            error = subprocess.CalledProcessError(1, ['trivy', 'fs', 'fixture'], stderr='sensitive diagnostic fixture')
            with patch('security.subprocess.run', side_effect=error), self.assertRaises(subprocess.CalledProcessError):
                scan(['fs', 'fixture'], output)
            diagnostic = output.with_suffix('.error.json').read_text()
            self.assertNotIn('sensitive diagnostic fixture', diagnostic)
            self.assertEqual('SCANNER_FAILED', json.loads(diagnostic)['status'])


class WorkflowTests(unittest.TestCase):
    def test_aws_free_events_and_permissions(self):
        ci = workflow()
        self.assertEqual(['main', 'develop'], ci['on']['push']['branches'])
        self.assertEqual(['develop', 'main'], ci['on']['pull_request']['branches'])
        self.assertIn('workflow_call', ci['on'])
        self.assertEqual({'contents': 'read'}, ci['permissions'])
        text = (ROOT / '.github/workflows/validate.yml').read_text()
        for forbidden in ('configure-aws-credentials', 'docker push', 'pull_request_target', 'role-to-assume', 'secrets.'):
            self.assertNotIn(forbidden, text)
        self.assertIn('shellcheck scripts/ci/', text)
        self.assertNotIn('-shellcheck=', text)

    def test_only_dispatch_can_publish(self):
        build = workflow('build-sha-images.yml')
        self.assertEqual({'workflow_dispatch'}, set(build['on']))
        self.assertEqual('validate', build['jobs']['build']['needs'])
        self.assertEqual('true', build['jobs']['validate']['with']['skip_containers'])

    def test_timeouts_and_deployment_serialization(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            for name, job in workflow(path.name)['jobs'].items():
                if 'runs-on' in job:
                    self.assertGreater(int(job['timeout-minutes']), 0, (path, name))
        self.assertEqual({'group': 'deploy-dev', 'cancel-in-progress': 'false'}, workflow('deploy-platform.yml')['concurrency'])

    def test_active_regressions_are_exhaustive_and_nonempty(self):
        active = set((ROOT / 'scripts/validation').glob('test_*.py'))
        self.assertTrue(active)
        self.assertEqual(active, set(files('platform')))
        self.assertEqual(active, set(files('all')))
        with self.assertRaises(ValueError):
            files('lifecycle')
        ci = workflow()['jobs']['regression-tests']
        self.assertNotIn('strategy', ci)
        self.assertIn('regressions.py all', str(ci['steps']))

    def test_empty_regression_suite_fails(self):
        from unittest.mock import patch
        from regressions import main
        with patch('regressions.files', return_value=[]), patch.object(sys, 'argv', ['regressions.py', 'all']):
            with self.assertRaisesRegex(SystemExit, 'No active regression tests'):
                main()

    def test_sdk_and_lock_inventory(self):
        sdk = json.loads((ROOT / 'global.json').read_text())['sdk']['version']
        for service in ('auth', 'shipment', 'tracking'):
            folder = ROOT / 'microservices' / (service + '-service')
            source = (folder / 'Dockerfile').read_text()
            self.assertIn('sdk:' + sdk + '-noble@sha256:', source)
            self.assertRegex(source, r'aspnet:10\.0\.14-noble-chiseled-extra@sha256:[0-9a-f]{64}')
            self.assertIn('restore --locked-mode', source)
            self.assertIn('--no-restore', source)
            for project in folder.rglob('*.csproj'):
                if {'obj', 'bin'}.intersection(project.parts): continue
                self.assertTrue(project.with_name('packages.lock.json').is_file(), project)
                lock = json.loads(project.with_name('packages.lock.json').read_text())
                self.assertEqual({'net10.0'}, set(lock['dependencies']), project)
        self.assertTrue((ROOT / 'tests/EventReliability.Tests/packages.lock.json').is_file())

    def test_dependabot_directories_and_commit_policy(self):
        config = yaml.safe_load((ROOT / '.github/dependabot.yml').read_text())
        self.assertEqual(2, config['version'])
        self.assertEqual({'github-actions', 'terraform', 'nuget', 'docker', 'pip', 'npm'}, {u['package-ecosystem'] for u in config['updates']})
        seen = set()
        for update in config['updates']:
            target = update.get('target-branch', 'main')
            self.assertIn(target, ('develop', 'main'))
            self.assertEqual(0, update['open-pull-requests-limit'])
            self.assertEqual('weekly', update['schedule']['interval'])
            self.assertRegex(update['commit-message']['prefix'] + ': update fixture', r'^chore\([^)]+\): .+')
            for directory in update['directories']:
                key = (update['package-ecosystem'], target, directory)
                self.assertNotIn(key, seen); seen.add(key)
                self.assertTrue((ROOT / directory.lstrip('/')).is_dir(), directory)

    def test_dependabot_security_configuration_is_separate_from_version_updates(self):
        updates = yaml.safe_load((ROOT / '.github/dependabot.yml').read_text())['updates']
        for ecosystem in ('github-actions', 'terraform', 'nuget', 'docker', 'pip', 'npm'):
            entries = [u for u in updates if u['package-ecosystem'] == ecosystem]
            # No target-branch means default-branch security customization.
            # Limit zero disables version proposals there, not security fixes.
            self.assertEqual(2, len(entries))
            version = next(u for u in entries if u.get('target-branch') == 'develop')
            security = next(u for u in entries if 'target-branch' not in u)
            self.assertEqual(version['directories'], security['directories'])
            self.assertEqual(0, security['open-pull-requests-limit'])
            self.assertEqual('chore(deps)', security['commit-message']['prefix'])

    def test_security_only_groups_preserve_default_branch_scope(self):
        updates = yaml.safe_load((ROOT / '.github/dependabot.yml').read_text())['updates']
        for ecosystem in ('nuget', 'pip', 'npm'):
            entry = next(u for u in updates if u['package-ecosystem'] == ecosystem and 'target-branch' not in u)
            self.assertEqual(0, entry['open-pull-requests-limit'])
            self.assertEqual({'security-fixes': {'applies-to': 'security-updates', 'patterns': ['*']}}, entry['groups'])

    def test_metadata_only_edits_keep_policy_and_retarget_checks(self):
        ci = workflow()
        self.assertIn('edited', ci['on']['pull_request']['types'])
        self.assertEqual("github.event_name == 'pull_request'", ci['jobs']['pull-request-policy']['if'])
        gate = "github.event_name != 'pull_request' || github.event.action != 'edited' || github.event.changes.base != null"
        for name, job in ci['jobs'].items():
            if name == 'pull-request-policy':
                continue
            expected = '${{ ' + gate + ' }}'
            if name == 'containers':
                expected = '${{ !inputs.skip_containers && (' + gate + ') }}'
            self.assertEqual(expected, job['if'], name)
        # Semantic fixture table: edited base changes must never be treated as metadata-only.
        for event, action, changes, should_run in [
            ('pull_request', 'edited', {'title': {}}, False),
            ('pull_request', 'edited', {'body': {}}, False),
            ('pull_request', 'edited', {'base': {'ref': {'from': 'develop'}}}, True),
            ('pull_request', 'synchronize', {}, True),
            ('pull_request', 'opened', {}, True),
            ('push', None, {}, True),
            ('workflow_dispatch', None, {}, True),
        ]:
            actual = event != 'pull_request' or action != 'edited' or changes.get('base') is not None
            self.assertEqual(should_run, actual, (event, action, changes))

    def test_metadata_only_edits_cannot_cancel_source_validation(self):
        ci = workflow()
        suffix = "${{ github.event_name == 'pull_request' && github.event.action == 'edited' && github.event.changes.base == null && '-metadata' || '' }}"
        self.assertEqual('validate-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}' + suffix,
                         ci['concurrency']['group'])
        self.assertEqual("${{ github.event_name == 'pull_request' || github.event_name == 'push' }}",
                         ci['concurrency']['cancel-in-progress'])
        source_group = 'validate-Validate-92'
        for action, changes, expected in [
            ('edited', {'title': {}}, source_group + '-metadata'),
            ('edited', {'body': {}}, source_group + '-metadata'),
            ('edited', {'base': {}}, source_group),
            ('opened', {}, source_group),
            ('synchronize', {}, source_group),
        ]:
            group = source_group + ('-metadata' if action == 'edited' and changes.get('base') is None else '')
            self.assertEqual(expected, group, (action, changes))

    def test_provider_updates_coordinate_every_module_stack_pair(self):
        updates = yaml.safe_load((ROOT / '.github/dependabot.yml').read_text())['updates']
        terraform = next(u for u in updates if u['package-ecosystem'] == 'terraform' and u.get('target-branch') == 'develop')
        self.assertEqual({'provider-updates': {'patterns': ['*'], 'group-by': 'dependency-name'}}, terraform['groups'])
        directories = set(terraform['directories'])
        for stack in (ROOT / 'infra/live/dev').glob('*/terragrunt.hcl'):
            module = re.search(r'source\s*=\s*"[^"]*/modules/+([^"/]+)"', stack.read_text())[1]
            self.assertIn('/' + stack.parent.relative_to(ROOT).as_posix(), directories)
            self.assertIn('/infra/modules/' + module, directories)

    def test_npm_versions_and_security_cover_the_frontend_lock(self):
        updates = yaml.safe_load((ROOT / '.github/dependabot.yml').read_text())['updates']
        entries = [u for u in updates if u['package-ecosystem'] == 'npm']
        self.assertEqual(2, len(entries))
        for entry in entries:
            self.assertEqual(['/frontend'], entry['directories'])
        self.assertTrue((ROOT / 'frontend/package-lock.json').is_file())

    @unittest.skipIf(sys.platform == 'win32', 'Bash policy behavior is validated on Linux')
    def test_branch_policy_accepts_dependabot_to_develop(self):
        import os
        step = workflow()['jobs']['pull-request-policy']['steps'][1]['run']
        for base, head, same_repo, expected in [
            ('develop', 'dependabot/nuget/update', True, 0),
            ('main', 'develop', True, 0),
            ('main', 'develop', False, 1),
            ('main', 'dependabot/nuget/update', True, 1),
            ('main', 'dependabot/security/fake', False, 1),
        ]:
            result = subprocess.run(['bash', '-c', step], env={**os.environ, 'BASE_REF': base, 'HEAD_REF': head,
                'BASE_REPO': 'owner/platform', 'HEAD_REPO': 'owner/platform' if same_repo else 'attacker/platform'}, capture_output=True)
            self.assertEqual(expected, result.returncode)

    @unittest.skipIf(sys.platform == 'win32', 'Bash policy behavior is validated on Linux')
    def test_conventional_commits_allow_optional_scope_but_pr_title_requires_it(self):
        import os
        import tempfile
        steps = workflow()['jobs']['pull-request-policy']['steps']
        title = next(s['run'] for s in steps if s.get('name') == 'Validate PR title')
        commits = next(s['run'] for s in steps if s.get('name') == 'Validate commit subjects')
        for subject, expected in [('docs(portfolio): improve navigation', 0), ('docs: improve navigation', 1), ('unstructured title', 1)]:
            result = subprocess.run(['bash', '-c', title], env={**os.environ, 'TITLE': subject}, capture_output=True)
            self.assertEqual(expected, result.returncode)
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / 'git'
            fake.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$FIXTURE_SUBJECT"\n')
            fake.chmod(0o755)
            for subject, expected in [('docs: preserve published history', 0), ('fix(ci)!: change interface', 0), ('unstructured subject', 1)]:
                result = subprocess.run(['bash', '-c', commits], env={**os.environ, 'PATH': directory + os.pathsep + os.environ['PATH'], 'BASE_SHA': 'fixture', 'HEAD_SHA': 'fixture', 'FIXTURE_SUBJECT': subject}, capture_output=True)
                self.assertEqual(expected, result.returncode)

    @unittest.skipIf(sys.platform == 'win32', 'Bash policy behavior is validated on Linux')
    def test_merge_generated_by_update_branch_preserves_commit_gate(self):
        import os
        import tempfile
        step = next(s['run'] for s in workflow()['jobs']['pull-request-policy']['steps']
                    if s.get('name') == 'Validate commit subjects')
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=directory, text=True, stderr=subprocess.DEVNULL).strip()
            git('init', '-b', 'base')
            git('config', 'user.name', 'Policy fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            git('commit', '--allow-empty', '-m', 'chore: base')
            base = git('rev-parse', 'HEAD')
            git('checkout', '-b', 'bot')
            git('commit', '--allow-empty', '-m', 'chore(deps): update dependency')
            git('checkout', 'base')
            git('commit', '--allow-empty', '-m', 'fix(ci): update validation')
            git('merge', '--no-ff', 'bot', '-m', 'Merge branch bot')
            for bad, expected in [(False, 0), (True, 1)]:
                if bad: git('commit', '--allow-empty', '-m', 'unstructured subject')
                result = subprocess.run(['bash', '-c', step], cwd=directory, capture_output=True,
                    env={**os.environ, 'BASE_SHA': base, 'HEAD_SHA': git('rev-parse', 'HEAD')})
                self.assertEqual(expected, result.returncode)


if __name__ == '__main__':
    unittest.main()
