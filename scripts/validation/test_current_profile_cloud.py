"""Offline failure-oriented tests. No CLI, network, Docker or AWS is invoked."""
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import current_profile_cloud as gate


class CloudPreparationTests(unittest.TestCase):
    def test_wrong_identity_stops_before_resource_reads(self):
        calls = []
        def reader(*args):
            calls.append(args)
            return {'status': 'OBSERVED', 'value': {'Account': '999999999999'}}
        with self.assertRaises(ValueError): gate.observe(reader)
        self.assertEqual(len(calls), 1)

    def test_incomplete_identity_stops(self):
        with self.assertRaises(ValueError): gate.observe(lambda *args: {'status': 'INCOMPLETE'})

    def test_read_errors_are_not_absence(self):
        for code, expected in [('AccessDeniedException', 'INCOMPLETE'), ('ResourceNotFoundException', 'ABSENT'),
                               ('DBInstanceNotFound', 'ABSENT'), ('RepositoryNotFoundException', 'ABSENT'),
                               ('ThrottlingException', 'INCOMPLETE')]:
            result = gate.aws('eks', 'describe-cluster', runner=lambda *a, **k:
                SimpleNamespace(returncode=1, stderr=f'({code}) when calling operation', stdout=''))
            self.assertEqual(result['status'], expected)

    def test_cli_is_exclusive_and_strips_inherited_credentials(self):
        def run(command, **options):
            self.assertEqual(command[command.index('--profile') + 1], 'cnp-cert-dev')
            self.assertEqual(command[command.index('--region') + 1], 'us-east-1')
            self.assertNotIn('AWS_ACCESS_KEY_ID', options['env'])
            self.assertNotIn('AWS_PROFILE', options['env'])
            self.assertNotIn('AWS_ENDPOINT_URL', options['env'])
            return SimpleNamespace(returncode=0, stdout='{}')
        with patch.dict(os.environ, {'AWS_ACCESS_KEY_ID': 'synthetic', 'AWS_PROFILE': 'unrelated', 'AWS_ENDPOINT_URL': 'invalid'}):
            gate.aws('sts', 'get-caller-identity', runner=run)

    def test_no_resource_calls_outside_exact_catalog(self):
        calls = []
        def read(*args):
            calls.append(args)
            if args[0] == 'sts': return {'status': 'OBSERVED', 'value': {'Account': gate.ACCOUNT}}
            return {'status': 'ABSENT'}
        result = gate.observe(read)
        self.assertEqual(len(calls), 9)
        self.assertNotIn('authorizers', result['resources'])
        self.assertTrue(all(c[1].startswith(('get-', 'describe-', 'head-')) for c in calls))

    def test_probe_manifest_is_finite_and_cannot_join_production_services(self):
        with patch.object(gate, 'ROOT', Path(__file__).resolve().parents[2]), \
             patch.object(gate, 'PROBE', Path(__file__).parent / 'cloud_network_probe'):
            manifest = gate.manifests('a' * 24)
        self.assertEqual(len(manifest['items']), 4)
        for job in manifest['items'][1:]:
            self.assertEqual(job['spec']['backoffLimit'], 0)
            self.assertEqual(job['spec']['activeDeadlineSeconds'], 180)
            pod = job['spec']['template']
            self.assertNotIn('app.kubernetes.io/instance', pod['metadata']['labels'])
            self.assertFalse(pod['spec']['automountServiceAccountToken'])
            self.assertIn('@sha256:', pod['spec']['containers'][0]['image'])
            self.assertTrue(pod['spec']['containers'][0]['image'].startswith(
                'mcr.microsoft.com/dotnet/sdk:10.0.403-noble@sha256:'))
            self.assertTrue(pod['spec']['containers'][0]['securityContext']['readOnlyRootFilesystem'])
        with self.assertRaises(ValueError): gate.manifests('../invalid')

    def test_probe_rejects_the_previous_sdk_pin(self):
        dockerfile = gate.ROOT / 'microservices/auth-service/Dockerfile'
        previous = dockerfile.read_text().replace('sdk:10.0.403-noble', 'sdk:10.0.402-noble')
        with patch.object(Path, 'read_text', return_value=previous):
            with self.assertRaisesRegex(ValueError, 'Reviewed SDK image pin missing'):
                gate.manifests('a' * 24)

    def network(self):
        return [{'runId': 'a'*24, 'source': source, 'samples': [
            {'round': r, 'target': target, 'port': 8080, 'addresses': ['10.0.0.1'],
             'outcome': 'connected' if allowed else 'timeout'}
            for r in range(3) for (origin, target), allowed in gate.FLOW.items() if origin == source]}
            for source in ('auth', 'shipment', 'tracking')]

    def http(self):
        return [{'phase': phase, 'apiId': 'abc123def4', 'tokenSha256': 'b'*64, 'checks': [
            {'round': r, 'index': index, 'status': status, 'noStore': True, 'requestId': f'{phase}-{r}-{index}',
             'observedAt': f'2026-10-16T22:{phase_index:02d}:{r*3+index:02d}+00:00'}
            for r in range(3) for index, status in enumerate(expected)]}
            for phase_index, (phase, expected) in enumerate(gate.PHASES.items())]

    def test_complete_receipts_are_accepted_with_explicit_evidence_limits(self):
        self.assertIn('REQUIRES', gate.evaluate_network(self.network(), 'a'*24))
        self.assertIn('REQUIRES', gate.evaluate_http(self.http()))

    def authorizer(self):
        return [{'id': 'abc', 'type': 'REQUEST', 'ttl': 0, 'sources': ['$request.header.Authorization']}]

    def routes(self):
        return [{'route': key, 'type': 'CUSTOM', 'authorizer': 'abc'} for key in
                ('GET /shipments', 'GET /tracking/by-shipment/{shipmentId}', 'POST /admin/tracking-events')]

    def test_actual_authorizer_ttl_identity_and_routes_are_required(self):
        gate.validate_live_authorizer(self.authorizer(), self.routes())
        for field, value in [('ttl', 60), ('ttl', False), ('type', 'JWT'), ('sources', [])]:
            authorizer = self.authorizer(); authorizer[0][field] = value
            with self.assertRaises(ValueError): gate.validate_live_authorizer(authorizer, self.routes())
        for field, value in [('type', 'NONE'), ('authorizer', 'other')]:
            routes = self.routes(); routes[0][field] = value
            with self.assertRaises(ValueError): gate.validate_live_authorizer(self.authorizer(), routes)

    def test_http_uses_bearer_but_never_reads_or_records_response_body(self):
        class Response:
            headers = {'Cache-Control': 'no-store', 'apigw-requestid': 'synthetic-id'}
            def __init__(self, code): self.code = code
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): raise AssertionError('Response bodies must not be read')
        class Opener:
            def open(self, request, timeout):
                self.case.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-bearer')
                return Response(400 if request.method == 'POST' else 200)
        opener = Opener(); opener.case = self
        with patch.object(gate.urllib.request, 'build_opener', return_value=opener):
            result = gate.http_phase('abc123def4', 'baseline', {'token': 'synthetic-bearer',
                'trackingPath': '/tracking/by-shipment/11111111-1111-4111-8111-111111111111'}, guard=lambda api: None)
        self.assertNotIn('synthetic-bearer', json.dumps(result))
        self.assertEqual(len(result['checks']), 9)

    def test_network_false_denials_and_unexpected_allows_fail(self):
        for outcome in ('connected', 'dns-timeout', 'socket-error'):
            rows = self.network(); rows[0]['samples'][0]['outcome'] = outcome
            with self.assertRaises(ValueError): gate.evaluate_network(rows, 'a'*24)
        rows = self.network(); rows[1]['samples'][0]['addresses'] = []
        with self.assertRaises(ValueError): gate.evaluate_network(rows, 'a'*24)

    def test_mixed_or_incomplete_network_run_fails(self):
        for change in ('run', 'missing', 'duplicate', 'port'):
            rows = self.network()
            if change == 'run': rows[0]['runId'] = 'c'*24
            elif change == 'missing': rows[0]['samples'].pop()
            elif change == 'duplicate': rows[0]['samples'][1] = copy.deepcopy(rows[0]['samples'][0])
            else: rows[0]['samples'][0]['port'] = 443
            with self.assertRaises(ValueError): gate.evaluate_network(rows, 'a'*24)

    def test_http_stale_authority_cache_wrong_token_and_missing_phases_fail(self):
        for change in ('status', 'cache', 'token', 'sample', 'phase', 'request'):
            rows = self.http()
            if change == 'status': rows[1]['checks'][-1]['status'] = 400
            elif change == 'cache': rows[0]['checks'][0]['noStore'] = False
            elif change == 'token': rows[1]['tokenSha256'] = 'c'*64
            elif change == 'sample': rows[2]['checks'][0] = copy.deepcopy(rows[2]['checks'][1])
            elif change == 'phase': rows.pop()
            else: rows[0]['checks'][0]['requestId'] = ''
            with self.assertRaises(ValueError): gate.evaluate_http(rows)

    def test_stale_out_of_order_or_reused_http_receipts_fail(self):
        rows = self.http(); rows[-1]['checks'][-1]['observedAt'] = '2026-10-16T23:00:00+00:00'
        with self.assertRaises(ValueError): gate.evaluate_http(rows)
        rows = self.http(); rows[0], rows[1] = rows[1], rows[0]
        with self.assertRaises(ValueError): gate.evaluate_http(rows)
        rows = self.http(); rows[0]['checks'][0]['requestId'] = rows[0]['checks'][1]['requestId']
        with self.assertRaises(ValueError): gate.evaluate_http(rows)


class CapturedBindingsTests(unittest.TestCase):
    def fixture(self):
        run='a'*24;origins=('auth','shipment','tracking')
        pod={x:'192.0.2.'+str(10+i) for i,x in enumerate(origins)};dns={x:'192.0.2.'+str(100+i) for i,x in enumerate(origins)}
        policies=[];compiled=[];slices=[];uids={x+'-service':'service-'+x for x in origins}
        for x in origins:
            selector={'matchLabels':{'app.kubernetes.io/name':x+'-service','platform.cloud-native.io/workload':'runtime'}}
            name=x+'-runtime-boundary';policies.append({'kind':'NetworkPolicy','apiVersion':'networking.k8s.io/v1','metadata':{'name':name,'namespace':'apps','uid':'policy-'+x},'spec':{'podSelector':selector,'policyTypes':['Ingress','Egress']}})
            compiled.append({'kind':'PolicyEndpoint','apiVersion':'networking.k8s.aws/v1alpha1','metadata':{'namespace':'apps','uid':'compiled-'+x,'ownerReferences':[{'kind':'NetworkPolicy','name':name,'uid':'policy-'+x,'controller':True}]},'spec':{
                'policyRef':{'name':name,'namespace':'apps'},'podSelector':selector,'podIsolation':['Ingress','Egress'],
                'podSelectorEndpoints':[{'name':'pod-'+x,'namespace':'apps','podIP':pod[x]}],
                'egress':[{'cidr':ip,'ports':[{'port':8080,'protocol':'TCP'}]} for y in origins if gate.FLOW.get((x,y)) for ip in (pod[y],dns[y])]}})
            slices.append({'kind':'EndpointSlice','apiVersion':'discovery.k8s.io/v1','metadata':{'namespace':'apps','uid':'slice-'+x,'labels':{'kubernetes.io/service-name':x+'-service'},'ownerReferences':[{'kind':'Service','name':x+'-service','uid':uids[x+'-service']}]},'ports':[{'name':'http','port':8080,'protocol':'TCP'}],
                'endpoints':[{'targetRef':{'kind':'Pod','name':'pod-'+x,'namespace':'apps','uid':'pod-uid-'+x},'addresses':[pod[x]],'conditions':{'ready':True,'serving':True,'terminating':False}}]})
        jobs=[];cleanup=[]
        for x in origins:
            name='current-profile-probe-'+run+'-'+x;uid='job-'+x
            jobs.append({'kind':'Job','apiVersion':'batch/v1','metadata':{'name':name,'namespace':'apps','uid':uid,'labels':{'platform.cloud-native.io/validation-run':run}},'spec':{'backoffLimit':0,'activeDeadlineSeconds':180,'template':{'metadata':{'labels':{'app.kubernetes.io/name':x+'-service','platform.cloud-native.io/workload':'runtime'}},'spec':{'automountServiceAccountToken':False}}},'status':{'succeeded':1}})
            cleanup.append({'kind':'jobs','name':name,'uid':uid,'deletedNormally':True})
        receipts=CloudPreparationTests().network()
        for row in receipts:
            for sample in row['samples']:sample['addresses']=[dns[sample['target']]]
        receipt={'runId':run,'records':receipts,'cleanup':cleanup}
        ds={'apiVersion':'apps/v1','kind':'DaemonSet','metadata':{'namespace':'kube-system','name':'aws-node','uid':'agent','generation':2},'status':{'observedGeneration':2,'desiredNumberScheduled':3,'numberReady':3,'numberAvailable':3,'updatedNumberScheduled':3},'spec':{'template':{'spec':{'containers':[{'name':'aws-node','env':[{'name':'NETWORK_POLICY_ENFORCING_MODE','value':'standard'}]},{'name':'aws-eks-nodeagent','args':['--enable-network-policy=true']}]}}}}
        capture={'policies':policies,'policyEndpoints':compiled,'endpointSlices':slices,'jobs':jobs,'daemonset':ds,'addon':{'name':'vpc-cni','status':'ACTIVE','version':'v1.23.2-eksbuild.1','configuration':json.dumps({'enableNetworkPolicy':'true','env':{'NETWORK_POLICY_ENFORCING_MODE':'standard'}})}}
        return receipt,capture,{x['metadata']['name']:{'uid':x['metadata']['uid'],'spec':copy.deepcopy(x['spec'])} for x in policies},uids

    def test_captured_bindings_accept_without_mutating_or_claiming_live_certification(self):
        r,c,s,u=self.fixture();before=copy.deepcopy((r,c,s,u));result=gate.evaluate_network_bindings(r,c,s,u,'v1.23.2-eksbuild.1')
        self.assertEqual(result['status'],'CAPTURED_NETWORK_BINDINGS_ACCEPTED');self.assertFalse(result['liveCertification']);self.assertEqual(len(result['bindings']),3);self.assertEqual(before,(r,c,s,u))

    def test_wrong_generation_unready_stale_policy_disabled_cni_or_wrong_probe_refuse(self):
        def replace_both(r,c):
            c['policies'][0]['metadata']['uid']='replacement-policy'
            c['policyEndpoints'][0]['metadata']['ownerReferences'][0]['uid']='replacement-policy'
        mutations=[replace_both,lambda r,c:c['policyEndpoints'][0]['metadata']['ownerReferences'][0].update(uid='replaced'),
            lambda r,c:c['endpointSlices'][0]['metadata']['ownerReferences'][0].update(uid='foreign'),
            lambda r,c:c['endpointSlices'][0]['endpoints'][0]['conditions'].update(ready=False),
            lambda r,c:c['policyEndpoints'][0]['spec']['podSelectorEndpoints'][0].update(podIP='192.0.2.250'),
            lambda r,c:c['policies'][0]['spec'].update(ingress=[{}]),
            lambda r,c:c['addon'].update(version='latest'),lambda r,c:c['daemonset']['status'].update(numberReady=0),
            lambda r,c:c['daemonset']['spec']['template']['spec']['containers'][1].update(args=['--enable-network-policy=false']),
            lambda r,c:r['cleanup'][0].update(uid='other-job'),lambda r,c:c['jobs'][0]['spec']['template']['metadata']['labels'].update({'app.kubernetes.io/instance':'platform-services'}),
            lambda r,c:c['policyEndpoints'][0]['spec']['egress'].append({'cidr':'0.0.0.0/0','ports':[{'port':8080,'protocol':'TCP'}]}),
            lambda r,c:c['policyEndpoints'][0]['spec'].update(ingress=[{'cidr':'0.0.0.0/0','ports':[{'port':8080,'protocol':'TCP'}]}]),
            lambda r,c:c['policyEndpoints'][0].update(kind='NetworkPolicy'),
            lambda r,c:c['endpointSlices'][0].update(apiVersion='v1'),
            lambda r,c:c['policies'].append(copy.deepcopy(c['policies'][0]))]
        for i,mutation in enumerate(mutations):
            r,c,s,u=self.fixture();mutation(r,c)
            with self.subTest(case=i),self.assertRaises(ValueError):gate.evaluate_network_bindings(r,c,s,u,'v1.23.2-eksbuild.1')
        for how in ('empty','duplicate'):
            r,c,s,u=self.fixture();keys=list(s);s[keys[0]]['uid']='' if how=='empty' else s[keys[1]]['uid']
            with self.subTest(expected_generation=how),self.assertRaises(ValueError):gate.evaluate_network_bindings(r,c,s,u,'v1.23.2-eksbuild.1')


if __name__ == '__main__': unittest.main()
