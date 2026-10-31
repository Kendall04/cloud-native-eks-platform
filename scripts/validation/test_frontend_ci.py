"""AWS-free frontend CI gates must execute, fail closed and retain only safe reports."""
import copy
import json
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE_EVENT_GATE = "${{ github.event_name != 'pull_request' || github.event.action != 'edited' || github.event.changes.base != null }}"


def contract(workflow):
    job = workflow['jobs']['frontend']
    assert job.get('if') == SOURCE_EVENT_GATE and 'continue-on-error' not in job
    assert 'paths' not in workflow['on']['pull_request']
    assert 'paths' not in workflow['on']['push']
    assert workflow['permissions'] == {'contents': 'read'}
    for step in job['steps']:
        assert 'continue-on-error' not in step
    commands = '\n'.join(s.get('run', '') for s in job['steps'])
    for required in ('npm ci', 'npm run check:lock', 'npm run typecheck', 'npm run lint',
                     'npm run format:check', 'npm test', 'npm run build',
                     'npm run check:architecture', 'npm audit', 'npm run test:browser'):
        assert required in commands, required
    for forbidden in ('--if-present', '--passWithNoTests', '|| true', 'exit 0'):
        assert forbidden not in commands, forbidden


class FrontendCITests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.load((ROOT / '.github/workflows/validate.yml').read_text(), Loader=yaml.BaseLoader)

    def test_frontend_covers_source_events_and_only_skips_metadata_edits(self):
        contract(self.workflow)

    def test_base_changes_and_reusable_calls_cannot_be_skipped(self):
        for gate in (
            "${{ github.event_name != 'pull_request' || github.event.action != 'edited' }}",
            "${{ github.event_name == 'pull_request' && github.event.action != 'edited' }}",
            "${{ github.event.action == 'synchronize' }}",
        ):
            value = copy.deepcopy(self.workflow)
            value['jobs']['frontend']['if'] = gate
            with self.subTest(gate=gate), self.assertRaises(AssertionError):
                contract(value)

    def test_disabling_a_job_or_browser_gate_is_rejected(self):
        for change in ('skip', 'soft-fail', 'remove-browser'):
            value = copy.deepcopy(self.workflow)
            job = value['jobs']['frontend']
            if change == 'skip': job['if'] = 'false'
            elif change == 'soft-fail': job['steps'][1]['continue-on-error'] = 'true'
            else: job['steps'] = [s for s in job['steps'] if 'npm run test:browser' not in s.get('run', '')]
            with self.subTest(change=change), self.assertRaises(AssertionError): contract(value)

    def test_toolchain_and_lock_are_explicit(self):
        self.assertEqual('24.18.0', (ROOT / 'frontend/.node-version').read_text().strip())
        package = json.loads((ROOT / 'frontend/package.json').read_text())
        self.assertEqual('npm@11.16.0', package['packageManager'])
        lock = json.loads((ROOT / 'frontend/package-lock.json').read_text())
        self.assertEqual(package['dependencies'], lock['packages']['']['dependencies'])
        setup = next(s for s in self.workflow['jobs']['frontend']['steps'] if s.get('uses', '').startswith('actions/setup-node@'))
        self.assertEqual('frontend/package-lock.json', setup['with']['cache-dependency-path'])
        self.assertEqual('frontend/.node-version', setup['with']['node-version-file'])

    def test_http_gate_reuses_postgres_without_aws(self):
        job = self.workflow['jobs']['postgres-r5-reliability']
        self.assertEqual('postgres:15.18', job['services']['postgres']['image'])
        self.assertTrue(any('npm run test:api:ci' in s.get('run', '') for s in job['steps']))
        source = (ROOT / 'frontend/scripts/local-backend.mjs').read_text()
        self.assertIn('if (!ci)', source)
        self.assertIn('platform_ui_ci', source)
        self.assertIn('ShipmentConsumer__Enabled: "false"', source)
        self.assertIn('Outbox__Enabled: "false"', source)

    def test_artifacts_exclude_configuration_and_real_api_traces(self):
        job = self.workflow['jobs']['postgres-r5-reliability']
        artifact = next(s for s in job['steps'] if s.get('with', {}).get('name') == 'frontend-http-integration')
        self.assertEqual({'.validation-results/frontend-api/http.json', '.validation-results/frontend-api/browser.xml'}, set(artifact['with']['path'].splitlines()))
        self.assertEqual('7', artifact['with']['retention-days'])
        config = (ROOT / 'frontend/playwright.config.ts').read_text()
        self.assertIn('process.env.UI_TEST_MODE !== "local"', config)
        self.assertIn('"retain-on-failure"', config)


if __name__ == '__main__': unittest.main()
