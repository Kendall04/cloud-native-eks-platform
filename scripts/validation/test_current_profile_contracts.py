"""Regression detectors for the exact ADR-005 source approval; no AWS or containers."""
from copy import deepcopy
import os
import unittest
from validate_current_profile import validate_network, validate_cache, cache_snapshot, peer
from validate_r3 import platform_render


class CurrentProfileCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.base = cache_snapshot()

    def test_result_cache_is_disabled_without_changing_identity_source(self):
        validate_cache(*self.base)

    def test_nonzero_default_live_override_or_hardcoded_result_cache_is_rejected(self):
        for change in ('default', 'live', 'hardcoded', 'missing'):
            with self.subTest(change=change):
                variables, core, live = deepcopy(self.base)
                ttl = next(row['jwt_authorizer_result_ttl_in_seconds'] for row in variables['variable'] if 'jwt_authorizer_result_ttl_in_seconds' in row)
                authorizer = next(row['aws_apigatewayv2_authorizer']['jwt'] for row in core['resource'] if 'aws_apigatewayv2_authorizer' in row)
                if change == 'default': ttl['default'] = 60
                if change == 'live': live['inputs']['jwt_authorizer_result_ttl_in_seconds'] = 60
                if change == 'hardcoded': authorizer['authorizer_result_ttl_in_seconds'] = 60
                if change == 'missing': authorizer.pop('authorizer_result_ttl_in_seconds')
                with self.assertRaises((ValueError, KeyError)): validate_cache(variables, core, live)


class CurrentProfileNetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, fixture = platform_render(os.environ.get('HELM_BIN', 'helm'))
        cls.cidrs = fixture['network']['privateSubnetCidrs']

    def test_exact_new_edges_preserve_old_network_ownership_and_rules(self):
        validate_network(self.base, self.cidrs)

    def test_missing_or_broadened_profile_edges_and_unrelated_drift_are_rejected(self):
        for change in ('missing-egress', 'missing-ingress', 'namespace-wide', 'all-namespaces',
                       'migration-target', 'wrong-port', 'extra-target', 'auth-lateral',
                       'lost-internal-lookup', 'broad-db', 'new-policy'):
            with self.subTest(change=change):
                documents = deepcopy(self.base)
                objects = {d['metadata']['name']: d for d in documents if d['kind'] == 'NetworkPolicy'}
                shipment = objects['shipment-runtime-boundary']['spec']
                tracking = objects['tracking-runtime-boundary']['spec']
                auth = objects['auth-runtime-boundary']['spec']
                rule = shipment['egress'][-1]
                if change == 'missing-egress': shipment['egress'].pop()
                if change == 'missing-ingress': auth['ingress'].pop()
                if change == 'namespace-wide': rule['to'][0].pop('podSelector')
                if change == 'all-namespaces': rule['to'][0].pop('namespaceSelector')
                if change == 'migration-target': rule['to'][0]['podSelector']['matchLabels']['platform.cloud-native.io/workload'] = 'migration'
                if change == 'wrong-port': rule['ports'][0]['port'] = 8443
                if change == 'extra-target': rule['to'].append(peer('tracking'))
                if change == 'auth-lateral': auth['egress'].append(deepcopy(rule))
                if change == 'lost-internal-lookup': tracking['egress'].pop()
                if change == 'broad-db': shipment['egress'][1]['to'] = [{'ipBlock': {'cidr': '0.0.0.0/0'}}]
                if change == 'new-policy': documents.append(deepcopy(objects['shipment-runtime-boundary']))
                with self.assertRaises((ValueError, KeyError)): validate_network(documents, self.cidrs)



class FixtureCleanupTests(unittest.TestCase):
    def test_unknown_owner_or_daemon_error_never_counts_as_absence(self):
        import subprocess
        from unittest.mock import patch
        from current_profile_http_gate import fixture_state, GateFailure
        cases = [(0, '{"com.codex.validation":"another-owner"}', ''),
                 (1, '', 'Cannot connect to the Docker daemon'),
                 (1, '', 'permission denied')]
        for code, stdout, stderr in cases:
            with self.subTest(stderr=stderr), patch('current_profile_http_gate.subprocess.run',
                    return_value=subprocess.CompletedProcess([], code, stdout, stderr)):
                with self.assertRaises(GateFailure): fixture_state('cnp-auth-profile-fixture', 'this-run')

    def test_matching_run_and_exact_missing_container_are_distinguished(self):
        import subprocess
        from unittest.mock import patch
        from current_profile_http_gate import fixture_state
        for code, stdout, stderr, expected in (
            (0, '{"com.codex.validation":"eks-current-profile","com.codex.run":"this-run"}', '', 'owned'),
            (1, '', 'Error: No such object: cnp-auth-profile-fixture', 'absent')):
            with self.subTest(expected=expected), patch('current_profile_http_gate.subprocess.run',
                    return_value=subprocess.CompletedProcess([], code, stdout, stderr)):
                self.assertEqual(expected, fixture_state('cnp-auth-profile-fixture', 'this-run'))


if __name__ == '__main__': unittest.main()
