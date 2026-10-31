import copy
import unittest
from validate_r6 import snapshot, validate

class R6RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.base=snapshot()
    def test_valid(self): validate(self.base)
    def test_negative_matrix(self):
        def remove_kind(data,group,kind,name): data[group]=[d for d in data[group] if (d['kind'],d['metadata']['name'])!=(kind,name)]
        def obj(data,group,kind,name): return next(d for d in data[group] if (d['kind'],d['metadata']['name'])==(kind,name))
        mutations={
            'missing metrics':lambda d: remove_kind(d,'addons','Deployment','metrics-server'),
            'insecure TLS':lambda d: obj(d,'addons','Deployment','metrics-server')['spec']['template']['spec']['containers'][0]['args'].append('--kubelet-insecure-tls'),
            'missing auth HPA':lambda d: remove_kind(d,'apps','HorizontalPodAutoscaler','auth-service-hpa'),
            'missing tracking HPA':lambda d: remove_kind(d,'apps','HorizontalPodAutoscaler','tracking-service-hpa'),
            'competing Shipment HPA':lambda d: d['apps'].append({'kind':'HorizontalPodAutoscaler','metadata':{'name':'shipment-service-hpa'}}),
            'missing KEDA':lambda d: remove_kind(d,'apps','ScaledObject','shipment-service-sqs'),
            'scale zero':lambda d: obj(d,'apps','ScaledObject','shipment-service-sqs')['spec'].update(minReplicaCount=0),
            'static credential':lambda d: obj(d,'platform','TriggerAuthentication','shipment-sqs-metrics')['spec'].update(secretTargetRef=[{'parameter':'awsAccessKeyID','name':'bad','key':'key'}]),
            'CNI disabled':lambda d: d.update(eks=d['eks'].replace('enableNetworkPolicy = "true"','enableNetworkPolicy = "false"')),
            'spread missing':lambda d: obj(d,'apps','Deployment','tracking-service')['spec']['template']['spec'].pop('topologySpreadConstraints'),
            'ClusterRole allowed':lambda d: d.update(deployer=d['deployer'].replace("allowed={'Deployment'", "allowed={'ClusterRole','Deployment'")),
            'EventId dimension':lambda d: d['telemetry'].__setitem__(0,d['telemetry'][0].replace('"Environment", "Service"','"Environment", "EventId"')),
            'DLQ alarm missing':lambda d: d.update(alarms=d['alarms'].replace('consumer-dlq','renamed-dlq')),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                data=copy.deepcopy(self.base); mutate(data)
                with self.assertRaises((ValueError,KeyError)): validate(data)


class ScalingEvidenceTests(unittest.TestCase):
    def test_requires_ready_up_then_down_and_queue_drained(self):
        import sys
        from pathlib import Path
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'demo'))
        from observe_scaling import progressed
        sample=lambda ready,desired: {'ready':ready,'desired':desired}
        self.assertFalse(progressed([sample(2,2)]*3))
        self.assertFalse(progressed([sample(2,2),sample(2,4),sample(2,2)]))
        self.assertFalse(progressed([sample(2,2),sample(4,4),sample(4,4)]))
        samples=[sample(2,2),sample(4,4),sample(2,2)]
        self.assertTrue(progressed(samples))
        for s in samples: s['queue']={'ApproximateNumberOfMessages':'1'}
        self.assertFalse(progressed(samples))
        samples[-1]['queue']['ApproximateNumberOfMessages']='0'
        self.assertTrue(progressed(samples))
