"""Behavioral Q3 regressions, using the actual host adapter and engine."""
import io
import json
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest.mock import Mock, patch
from test_r4 import FakeHost, request
from executor import Host
from engine import execute
from diagnostics import CommandFailure, diagnostic

class SmokeTests(unittest.TestCase):
    def test_current_release_uses_helm4_default_all_statuses(self):
        host=Host({'region':'us-east-1','bucket':'artifacts','environment':'dev'},'.','.')
        host.run=Mock(side_effect=[json.dumps([{'revision':'2','status':'deployed'}]),'manifest','{}',json.dumps({})])
        result=host.current()
        self.assertEqual(2,result['revision'])
        self.assertNotIn('--all',host.run.call_args_list[0].args[0])

    def host(self):
        host = Host({'region':'us-east-1','apiEndpoint':'https://example.invalid'},'.','.')
        def kubectl(*args):
            if args[0] == 'rollout': return ''
            if args[1] == 'ingress': return json.dumps({'status':{'loadBalancer':{'ingress':[{'hostname':'alb'}]}}})
            return json.dumps({'items':[{'endpoints':[{'conditions':{'ready':True}}]}]})
        host.kubectl = kubectl
        return host

    def response(self, code, body, application=True):
        headers = Message()
        if application:
            headers['Content-Type']='application/problem+json'
            headers['X-Request-Id']='server-generated'
        return urllib.error.HTTPError('https://example.invalid',code,'',headers,io.BytesIO(json.dumps(body).encode()))

    def test_application_validation_and_edge_policy_are_distinct(self):
        evidence={}
        opener=Mock()
        opener.open.side_effect=[self.response(400,{'status':400,'errors':{'RefreshToken':['required']}}), self.response(401,{})]
        with patch('executor.urllib.request.build_opener',return_value=opener): self.host().smoke(evidence)
        self.assertEqual({'KUBERNETES_READY':'PASS','AUTH_BACKEND_REACHABLE':'PASS','EDGE_ANONYMOUS_REJECTED':'PASS'},evidence)
        self.assertEqual(b'{}',opener.open.call_args_list[0].args[0].data)

    def test_healthy_pods_and_edge_rejection_do_not_prove_backend(self):
        for code,body in [(401,{}),(502,{}),(400,{'message':'edge failure'}),(400,{'status':400,'errors':{'Other':['required']}})]:
            evidence={}; opener=Mock()
            opener.open.side_effect=self.response(code,body)
            with self.subTest(code=code,body=body), patch('executor.urllib.request.build_opener',return_value=opener), self.assertRaises(ValueError):
                self.host().smoke(evidence)
            self.assertEqual('PASS',evidence['KUBERNETES_READY'])
            self.assertEqual('FAILED',evidence['AUTH_BACKEND_REACHABLE'])

class ProvenanceTests(unittest.TestCase):
    def test_historical_replay_and_restart_never_move_marker(self):
        # Real filesystem receipts and Host.publish/activate; only AWS/Helm IO simulated.
        with tempfile.TemporaryDirectory() as directory:
            objects={}
            def aws(*args):
                key=args[args.index('--key')+1] if '--key' in args else None
                if args[1]=='put-object': objects[key]=Path(args[args.index('--body')+1]).read_bytes(); return {}
                if args[1]=='list-objects-v2': return {'Contents':[{'Key':k} for k in objects if k.startswith(args[args.index('--prefix')+1])]}
                if args[1]=='get-object': Path(args[-1]).write_bytes(objects[key]); return {}
                raise AssertionError(args)
            host=FakeHost(); real=Host(dict(region='us-east-1',bucket='test',environment='dev',accountId='test',clusterName='test',namespace='apps',helmRelease='platform-services'),directory,directory)
            real.aws=aws
            host.save=real.save; host.load=real.load; host.publish=real.publish
            original_current=host.current
            def current():
                value=original_current(); marker=json.loads(objects.get('deployment-receipts/dev/_state/active.json',b'{}'))
                value['artifact']=marker.get('artifact') if marker.get('revision')==value['revision'] else None
                return value
            host.current=current; real.current=current; host.activate=real.activate
            a=request(); a['DeploymentId']='A'
            first=execute(a,host)
            self.assertEqual('SUCCESS',first['status'],first)
            self.assertEqual(4,first['activeRevision'])
            b={**a,'DeploymentId':'B','ExpectedPreviousRevision':'4','ArtifactVersionId':'B'}
            self.assertEqual(5,execute(b,host)['activeRevision'])
            marker=objects['deployment-receipts/dev/_state/active.json']
            # Evict local receipt: restart fetches durable historical result.
            Path(directory,'A.json').unlink()
            self.assertEqual(4,execute(a,host)['activeRevision'])
            self.assertEqual(marker,objects['deployment-receipts/dev/_state/active.json'])
            self.assertEqual(2,host.upgrades)
            host.active='B'; host.smoke_fail=True
            host.rollback=lambda revision: (setattr(host,'revision',host.revision+1),setattr(host,'active','B'))
            c={**b,'DeploymentId':'C','ExpectedPreviousRevision':'5','ArtifactVersionId':'C'}
            result=execute(c,host)
            self.assertEqual('VERIFIED',result['rollbackResult'])
            restored=json.loads(objects['deployment-receipts/dev/_state/active.json'])
            self.assertEqual(7,restored['revision'])
            self.assertEqual('B',restored['artifact']['ArtifactVersionId'])
            Path(directory,'C.json').unlink()
            self.assertEqual(result,execute(c,host))
            self.assertEqual(restored,json.loads(objects['deployment-receipts/dev/_state/active.json']))

    def test_verified_noop_recovery_does_not_rewrite_marker(self):
        host=FakeHost()
        host.upgrade=Mock(side_effect=TimeoutError('failed before mutation'))
        host.activate=Mock()
        result=execute(request(),host)
        self.assertEqual('VERIFIED',result['rollbackResult'])
        host.activate.assert_not_called()

    def test_marker_failure_leaves_running_and_cannot_replay_activation(self):
        host=FakeHost(); host.activate=Mock(side_effect=OSError('SECRET'))
        with self.assertRaises(OSError): execute(request(),host)
        self.assertEqual('RUNNING',host.receipts[request()['DeploymentId']]['status'])
        with self.assertRaisesRegex(ValueError,'Interrupted'): execute(request(),host)
        self.assertEqual(1,host.upgrades)
        self.assertEqual(1,host.activate.call_count)

class DiagnosticsTests(unittest.TestCase):
    def test_codes_are_distinct_and_raw_messages_excluded(self):
        for code,category in [('AccessDeniedException','Authorization'),('ThrottlingException','Throttling'),('RequestTimeout','Timeout')]:
            error=CommandFailure('aws',254,'An error occurred ('+code+') when calling SecretOperation: password=SECRET')
            result=diagnostic(error)
            self.assertEqual(category,result['errorCategory'])
            self.assertEqual(code,result['awsErrorCode'])
            self.assertNotIn('SECRET',json.dumps(result))
        self.assertEqual('Timeout',diagnostic(TimeoutError('SECRET'))['errorCategory'])
        self.assertEqual('Network',diagnostic(ConnectionError('SECRET'))['errorCategory'])
        self.assertNotIn('SECRET',json.dumps(diagnostic(ValueError('SECRET'))))

    def test_receipt_keeps_stage_and_safe_cause(self):
        host=FakeHost(); host.preflight=Mock(side_effect=TimeoutError('SECRET'))
        result=execute(request(),host)
        self.assertEqual('preflight',result['failureStage'])
        self.assertEqual('Timeout',result['diagnostic']['errorCategory'])
        self.assertNotIn('SECRET',json.dumps(result))
