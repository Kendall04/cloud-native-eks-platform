"""R4 negative contract tests and state-machine harness. No AWS credentials."""
import copy
import io
import json
import os
from pathlib import Path
import re
import sys
import tarfile
import unittest
from unittest.mock import Mock, patch
import yaml
from validate_r4 import ROOT, snapshot, validate
from test_r2 import contract_fixture
from common import sha, validate_bundle, validate_manifest, validate_render, read_tar
from package import package, canonical, archive, target_from_environment
from executor import validate_request, Host
from engine import execute
from publish import put_once
from orchestrate import poll
from botocore.exceptions import ClientError


class ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=contract_fixture()
        prefix='arn:aws:elasticloadbalancing:us-east-1:999988887777:'
        cls.environment['alb'].update(arn=prefix+'loadbalancer/app/test/abcdef1234567890',listenerArn=prefix+'listener/app/test/abcdef1234567890/abcdef1234567890')
        cls.target=target_from_environment(cls.environment)
        cls.records=[{'name':s,'sourceCommit':'a'*40,'imageRepository':cls.target['repositories'][s],'imageDigest':'sha256:'+'b'*64,'buildRunId':'123'} for s in ('auth','shipment','tracking')]
        cls.data,cls.manifest=package(canonical(cls.environment),cls.records,'a'*40,'v1.0.0')
        cls.files=read_tar(cls.data,outer=True)

    def test_bundle_roundtrip_and_determinism(self):
        validate_bundle(self.data,sha(self.data),self.target)
        repeated,_=package(canonical(self.environment),self.records,'a'*40,'v1.0.0')
        self.assertEqual(self.data,repeated)

    def test_outer_corruption(self):
        with self.assertRaises(ValueError): validate_bundle(self.data+b'bad',sha(self.data),self.target)

    def rebundle(self, values_bytes):
        files=dict(self.files)
        files['values.resolved.yaml']=values_bytes
        m=copy.deepcopy(self.manifest); m['valuesSha256']=sha(values_bytes)
        files['manifest.json']=canonical(m)
        files['checksums.sha256']=''.join(f'{sha(data)}  {name}\n' for name,data in sorted(files.items()) if name!='checksums.sha256').encode()
        return archive(files)

    def render_values(self, values_bytes, upgrade=False):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as directory:
            chart=Path(directory)/'chart.tgz'; chart.write_bytes(self.files['platform-services.tgz'])
            values=Path(directory)/'values.json'; values.write_bytes(values_bytes)
            result=subprocess.check_output([os.environ.get('HELM_BIN','helm'),'template','platform-services',str(chart),'-n','apps','-f',str(values),*(['--is-upgrade'] if upgrade else [])],text=True)
        return [d for d in yaml.safe_load_all(result) if d]

    def test_decoded_programs_rejected_in_every_structure(self):
        expressions=['{{', '{{ .Release.IsUpgrade }}', '{{ .Values.global }}',
                     '{{ lookup "v1" "Secret" "apps" "auth-jwt" }}',
                     '{{ include "platform-services.chart" . }}',
                     '{{ tpl "{{ .Release.IsUpgrade }}" . }}', 'first\n{{ .Release.IsUpgrade }}\nlast']
        for expression in expressions:
            for payload in (expression, {'nested':expression}, [expression], {expression:'key'}):
                values=yaml.safe_load(self.files['values.resolved.yaml'])
                values['services']['auth']['env']['Q1_PROBE']=payload
                encoded=json.dumps(values).replace('{{',r'\u007b\u007b').encode()
                for representation in (yaml.safe_dump(values).encode(),json.dumps(values).encode(),encoded):
                    with self.subTest(expression=expression,payload=payload,escaped=representation==encoded):
                        data=self.rebundle(representation)
                        with self.assertRaisesRegex(ValueError,'declarative'):
                            validate_bundle(data,sha(data),self.target)

    def test_yaml_escape_and_block_scalar_programs_rejected(self):
        for scalar in ('"\\x7b\\x7b .Release.IsUpgrade }}"',
                       '"\\u007b\\u007b .Release.IsUpgrade }}"',
                       "'{{ .Release.IsUpgrade }}'", '|\n  first\n  {{ .Release.IsUpgrade }}'):
            raw=self.files['values.resolved.yaml']+('\nq1: '+scalar+'\n').encode()
            data=self.rebundle(raw)
            with self.subTest(scalar=scalar), self.assertRaisesRegex(ValueError,'declarative'):
                validate_bundle(data,sha(data),self.target)

    def test_audit_install_upgrade_exploit_is_inert_even_without_filter(self):
        expression='{{ if .Release.IsUpgrade }}upgrade-only-logic{{ else }}preflight-safe{{ end }}'
        values=yaml.safe_load(self.files['values.resolved.yaml'])
        values['services']['auth']['env']['Q1_PROBE']=expression
        raw=json.dumps(values).replace('{{',r'\u007b\u007b').encode()
        data=self.rebundle(raw)
        with self.assertRaisesRegex(ValueError,'declarative'): validate_bundle(data,sha(data),self.target)
        # Bypass the Python filter deliberately: the approved chart itself must
        # never interpret the string, on either install or upgrade.
        install=self.render_values(raw); upgrade=self.render_values(raw,True)
        self.assertEqual(install,upgrade)
        config=next(d for d in install if d['kind']=='ConfigMap' and d['metadata']['name']=='auth-service-config')
        self.assertEqual(expression,config['data']['Q1_PROBE'])

    def test_unsupported_yaml_types_rejected(self):
        for scalar in ('!!binary aGVsbG8=', '2026-01-01', '.nan', '.inf', '{1: value}', '&cycle [*cycle]'):
            data=self.rebundle(self.files['values.resolved.yaml']+('\nq1: '+scalar+'\n').encode())
            with self.subTest(scalar=scalar), self.assertRaises(ValueError): validate_bundle(data,sha(data),self.target)

    def test_platform_ingress_values_mutations_rejected(self):
        mutations=[('requireFrontendSecurityGroup',False),('frontendSecurityGroupId','sg-0123456789abcdef0'),
                   ('enabled',False),('className','other'),('discoveryTags',{'Project':'other','Environment':'dev'})]
        annotations={'group.name':'another-platform', 'security-groups':'sg-0123456789abcdef0',
                     'scheme':'internet-facing','listen-ports':'[{"HTTPS":443}]','target-type':'instance',
                     'subnets':'subnet-0123456789abcdef0','load-balancer-name':'other',
                     'inbound-cidrs':'0.0.0.0/0','manage-backend-security-group-rules':'false',
                     'actions.custom':'{}'}
        for key,value in mutations+list(annotations.items()):
            values=yaml.safe_load(self.files['values.resolved.yaml']); ingress=values['global']['ingress']
            if key in annotations: ingress['annotations']['alb.ingress.kubernetes.io/'+key]=value
            else: ingress[key]=value
            data=self.rebundle(canonical(values))
            with self.subTest(key=key), self.assertRaises(ValueError): validate_bundle(data,sha(data),self.target)

    def test_audit_alb_exploit_rejected(self):
        values=yaml.safe_load(self.files['values.resolved.yaml'])
        ingress=values['global']['ingress']
        ingress['requireFrontendSecurityGroup']=False
        ingress['annotations']['alb.ingress.kubernetes.io/security-groups']='sg-0123456789abcdef0'
        ingress['annotations']['alb.ingress.kubernetes.io/group.name']='different-platform-group'
        data=self.rebundle(canonical(values))
        with self.assertRaises(ValueError): validate_bundle(data,sha(data),self.target)

    def test_rendered_platform_boundary_and_missing_ingress_rejected(self):
        docs=self.render_values(self.files['values.resolved.yaml'])
        for key in ('group.name','security-groups','scheme','listen-ports','target-type','subnets','tags'):
            changed=copy.deepcopy(docs)
            ingress=next(d for d in changed if d['kind']=='Ingress')
            ingress['metadata']['annotations']['alb.ingress.kubernetes.io/'+key]='unauthorized'
            with self.subTest(key=key), self.assertRaises(ValueError): validate_render(changed,self.manifest,self.target)
        with self.assertRaises(ValueError): validate_render([d for d in docs if d['kind']!='Ingress'],self.manifest,self.target)

    def test_valid_application_changes_and_normalized_upgrade(self):
        records=copy.deepcopy(self.records)
        for record in records: record['imageDigest']='sha256:'+'c'*64
        data,manifest=package(canonical(self.environment),records,'a'*40,'v1.0.1')
        files,_=validate_bundle(data,sha(data),self.target)
        values=json.loads(files['values.resolved.yaml'])
        values['services']['auth']['env']['Q1_PROBE']='approved literal'
        values['services']['auth']['hpa']['maxReplicas']=3
        values['services']['shipment']['keda']['maxReplicaCount']=5
        values['services']['auth']['ingressPaths'].append('/auth/additional')
        from contract import normalized_values
        normalized=normalized_values(yaml.safe_dump(values).encode(),self.target)
        self.assertEqual(values,json.loads(normalized))
        install=self.render_values(normalized); upgrade=self.render_values(normalized,True)
        self.assertEqual(install,upgrade)
        validate_render(install,manifest,self.target); validate_render(upgrade,manifest,self.target)

    def test_environment_snapshot_cannot_redefine_trusted_alb(self):
        changed=copy.deepcopy(self.environment)
        changed['alb']['frontendSecurityGroupId']='sg-0123456789abcdef0'
        data,_=package(canonical(changed),self.records,'a'*40,'v1.0.0')
        with self.assertRaises(ValueError): validate_bundle(data,sha(data),self.target)
        # The same intent is allowed only after a platform config transition.
        new_target=target_from_environment(changed)
        files,manifest=validate_bundle(data,sha(data),new_target)
        validate_render(self.render_values(files['values.resolved.yaml']),manifest,new_target)

    def test_inner_corruption(self):
        for file in ('platform-services.tgz','values.resolved.yaml','environment.contract.json','manifest.json'):
            with self.subTest(file=file):
                files=dict(self.files); files[file]+=b'\n'; data=archive(files)
                with self.assertRaises(ValueError): validate_bundle(data,sha(data),self.target)

    def test_manifest_negative_matrix(self):
        mutations=[('environment','prod'),('accountId','111122223333'),('region','eu-west-1'),('clusterName','other'),('namespace','kube-system'),('helmRelease','other'),
                   ('requiredDeployerVersion','9.0.0'),('requiredHelmVersion','v3.0.0'),('migrationCompatibility','breaking'),('deploymentConfigCommit','c'*40)]
        for key,value in mutations:
            with self.subTest(key=key):
                m=copy.deepcopy(self.manifest); m[key]=value
                with self.assertRaises(ValueError): validate_manifest(m,self.target)

    def test_service_negative_matrix(self):
        for key,value in [('sourceCommit','c'*40),('imageRepository','docker.io/example/auth'),('imageDigest','latest'),('buildRunId',''),('buildRunId',123)]:
            m=copy.deepcopy(self.manifest); m['services'][0][key]=value
            with self.assertRaises(ValueError): validate_manifest(m,self.target)

    def test_secret_and_executable_forbidden(self):
        m=copy.deepcopy(self.manifest); m['password']='TEST_ONLY'
        with self.assertRaises(ValueError): validate_manifest(m,self.target)
        files=dict(self.files); files['deploy.sh']=b'echo unsafe'; data=archive(files)
        with self.assertRaises(ValueError): validate_bundle(data,sha(data),self.target)

    def test_changed_template_even_with_recomputed_checksums_rejected(self):
        files=dict(self.files); chart=read_tar(files['platform-services.tgz'])
        name=next(n for n in chart if '/templates/' in n)
        chart[name]+=b'\n{{ lookup "v1" "Secret" "apps" "auth-jwt" }}'
        files['platform-services.tgz']=archive(chart)
        m=copy.deepcopy(self.manifest); m['chartSha256']=sha(files['platform-services.tgz'])
        files['manifest.json']=canonical(m)
        files['checksums.sha256']=''.join(f'{sha(data)}  {name}\n' for name,data in sorted(files.items()) if name!='checksums.sha256').encode()
        data=archive(files)
        with self.assertRaisesRegex(ValueError,'template logic'): validate_bundle(data,sha(data),self.target)

    def test_unapproved_template_set_or_content_rejected_with_valid_checksums(self):
        for change in ('comment','unknown','missing','crds'):
            files=dict(self.files); chart=read_tar(files['platform-services.tgz'])
            name='platform-services/templates/deployment.yaml'
            if change=='comment': chart[name]+=b'\n# Unreviewed change\n'
            if change=='unknown': chart['platform-services/templates/unreviewed.yaml']=b'---\n'
            if change=='missing': del chart[name]
            if change=='crds': chart['platform-services/crds/unreviewed.yaml']=b'apiVersion: v1\nkind: Secret\nmetadata:\n  name: unreviewed\n  namespace: apps\n'
            files['platform-services.tgz']=archive(chart)
            m=copy.deepcopy(self.manifest); m['chartSha256']=sha(files['platform-services.tgz'])
            files['manifest.json']=canonical(m)
            files['checksums.sha256']=''.join(f'{sha(data)}  {name}\n' for name,data in sorted(files.items()) if name!='checksums.sha256').encode()
            data=archive(files)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError,'template logic|chart files'):
                validate_bundle(data,sha(data),self.target)

    def test_incorrect_installed_template_pin_fails_closed(self):
        original=Path.read_text
        def wrong_pin(path,*args,**kwargs):
            text=original(path,*args,**kwargs)
            if path.name=='chart-template-hashes.json':
                pins=json.loads(text); pins['platform-services/templates/deployment.yaml']='0'*64
                return json.dumps(pins)
            return text
        with patch.object(Path,'read_text',wrong_pin), self.assertRaisesRegex(ValueError,'template logic'):
            validate_bundle(self.data,sha(self.data),self.target)

    def test_previous_executor_policy_version_is_not_interchangeable(self):
        changed=copy.deepcopy(self.manifest); changed['requiredDeployerVersion']='1.3.0'
        with self.assertRaises(ValueError): validate_manifest(changed,self.target)

    def test_valid_bundle_hashes_cannot_relax_security_contexts(self):
        for change in ('capabilities','pod-seccomp','container-seccomp'):
            values=yaml.safe_load(self.files['values.resolved.yaml'])
            if change=='capabilities': values['global']['containerSecurityContext']['capabilities']['drop']=[]
            if change=='pod-seccomp': values['global']['podSecurityContext']['seccompProfile']['type']='Unconfined'
            if change=='container-seccomp': values['global']['containerSecurityContext']['seccompProfile']={'type':'Unconfined'}
            data=self.rebundle(yaml.safe_dump(values).encode())
            files,m=validate_bundle(data,sha(data),self.target)
            docs=self.render_values(files['values.resolved.yaml'])
            with self.subTest(change=change), self.assertRaisesRegex(ValueError,'security context'):
                validate_render(docs,m,self.target)

    def test_archive_attacks(self):
        for name,kind,mode in [('../escape',tarfile.REGTYPE,0o644),('/absolute',tarfile.REGTYPE,0o644),('link',tarfile.SYMTYPE,0o644),('script',tarfile.REGTYPE,0o755)]:
            stream=io.BytesIO()
            with tarfile.open(fileobj=stream,mode='w:gz') as out:
                item=tarfile.TarInfo(name); item.type=kind; item.mode=mode; out.addfile(item)
            with self.assertRaises(ValueError): read_tar(stream.getvalue())

    def test_render_privilege_regressions(self):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as directory:
            for name in ('platform-services.tgz','values.resolved.yaml'): (Path(directory)/name).write_bytes(self.files[name])
            result=subprocess.check_output([os.environ.get('HELM_BIN','helm'),'template','platform-services',str(Path(directory)/'platform-services.tgz'),'-n','apps','-f',str(Path(directory)/'values.resolved.yaml')],text=True)
        docs=[d for d in yaml.safe_load_all(result) if d]
        validate_render(docs,self.manifest,self.target)
        for kind in ('Namespace','ServiceAccount','Secret','ExternalSecret','SecretStore','ClusterRole','CustomResourceDefinition','TriggerAuthentication','NetworkPolicy'):
            with self.assertRaises(ValueError): validate_render(docs+[{'kind':kind,'metadata':{'name':'injected','namespace':'apps'}}],self.manifest,self.target)
        for field,value in (('minReplicaCount',0),('maxReplicaCount',99)):
            changed=copy.deepcopy(docs)
            next(d for d in changed if d['kind']=='ScaledObject')['spec'][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError): validate_render(changed,self.manifest,self.target)
        changed=copy.deepcopy(docs)
        next(d for d in changed if d['kind']=='ScaledObject')['spec']['triggers'][0]['metadata']['queueURL']='https://sqs.us-east-1.amazonaws.com/111122223333/other'
        with self.assertRaises(ValueError): validate_render(changed,self.manifest,self.target)
        for change in ('image','namespace','command','secret','serviceAccount','privileged',
                       'writable-root','unbounded-tmp','disk-tmp','host-volume','tmp-mount','scratch-group'):
            changed=copy.deepcopy(docs); d=next(d for d in changed if d['kind']=='Deployment'); pod=d['spec']['template']['spec']; container=pod['containers'][0]
            if change=='image': container['image']='nginx:latest'
            if change=='namespace': d['metadata']['namespace']='kube-system'
            if change=='command': container['command']=['sh','-c','true']
            if change=='secret': container['envFrom']=[{'secretRef':{'name':'bootstrap-admin'}}]
            if change=='serviceAccount': pod['serviceAccountName']='platform-migrator'
            if change=='privileged': container['securityContext']['privileged']=True
            if change=='writable-root': container['securityContext']['readOnlyRootFilesystem']=False
            if change=='unbounded-tmp': pod['volumes'][0]['emptyDir'].pop('sizeLimit')
            if change=='disk-tmp': pod['volumes'][0]['emptyDir'].pop('medium')
            if change=='host-volume': pod['volumes'][0]={'name':'runtime-tmp','hostPath':{'path':'/'}}
            if change=='tmp-mount': container['volumeMounts'][0]['mountPath']='/app'
            if change=='scratch-group': pod['securityContext']['fsGroup']=0
            with self.subTest(change=change), self.assertRaises(ValueError): validate_render(changed,self.manifest,self.target)

    def test_host_preflight_download_and_real_render(self):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as directory:
            host=Host({**self.target,'bucket':'test-artifacts'},directory,directory)
            calls=[]
            def aws(*args):
                calls.append(args[:2])
                if args[:2]==('s3api','head-object'): return {'ContentLength':len(self.data)}
                if args[:2]==('s3api','get-object'):
                    Path(args[-1]).write_bytes(self.data); return {'VersionId':'real-version'}
                if args[:2]==('eks','describe-cluster'):
                    return {'cluster':{'arn':'arn:aws:eks:us-east-1:999988887777:cluster/'+self.target['clusterName'],'resourcesVpcConfig':{'endpointPrivateAccess':True,'endpointPublicAccess':False}}}
                raise AssertionError(args)
            def run(args,timeout=900):
                if args[:3]==['aws','eks','update-kubeconfig']: return ''
                if args[:4]==['kubectl','-n','apps','get']:
                    self.assertEqual(args[4:],['triggerauthentication','shipment-sqs-metrics','-o','json'])
                    return json.dumps({'spec':{'podIdentity':{'provider':'aws','identityOwner':'keda'}}})
                self.assertEqual('helm',args[0])
                return subprocess.check_output([os.environ.get('HELM_BIN','helm'),*args[1:]],text=True)
            host.aws=aws; host.run=run
            r=request(); r['ArtifactSha256']=sha(self.data); r['ArtifactKey']='deploy-artifacts/dev/'+'a'*40+'/'+sha(self.data)+'.tar.gz'
            self.assertEqual(self.manifest,host.preflight(r))
            normalized=Path(directory,'values.resolved.yaml').read_bytes()
            self.assertEqual(json.loads(normalized),yaml.safe_load(self.files['values.resolved.yaml']))
            commands=[]
            host.run=lambda args,timeout=900: commands.append(args)
            host.upgrade()
            self.assertEqual(normalized,Path(commands[0][commands[0].index('-f')+1]).read_bytes())
            host.run=run
            self.assertEqual([('s3api','head-object'),('s3api','get-object'),('eks','describe-cluster')],calls)
            r['ArtifactSha256']='0'*64
            with self.assertRaises(ValueError): host.preflight(r)
            self.assertEqual(1,calls.count(('eks','describe-cluster')))


def request():
    return {'ArtifactKey':'deploy-artifacts/dev/'+'a'*40+'/'+'b'*64+'.tar.gz','ArtifactVersionId':'real-version','ArtifactSha256':'b'*64,'DeploymentId':'run-123','ExpectedPreviousRevision':'3'}


class FakeHost:
    def __init__(self, revision=3, upgrade_fail=False, smoke_fail=False, rollback_fail=False):
        self.receipts={}; self.revision=revision; self.old=revision; self.upgrade_fail=upgrade_fail; self.smoke_fail=smoke_fail; self.rollback_fail=rollback_fail
        self.upgrades=0; self.rollbacks=0; self.active='old'; self.published=[]
    def load(self,key): return copy.deepcopy(self.receipts.get(key))
    def save(self,r): self.receipts[r['deploymentId']]=copy.deepcopy(r)
    def publish(self,r): self.published.append(copy.deepcopy(r))
    def activate(self,r): pass
    def preflight(self,r): return {'applicationSourceCommit':'a'*40,'deploymentConfigCommit':'a'*40,'releaseVersion':'v1.0.0','migrationCompatibility':'previous-release-compatible'}
    def current(self): return {'revision':self.revision,'status':'deployed' if self.revision else 'absent','manifestHash':self.active,'valuesHash':self.active}
    def secret_gate(self): pass
    def upgrade(self):
        self.upgrades+=1; self.revision+=1; self.active='new'
        if self.upgrade_fail: raise ValueError('SIMULATED')
    def smoke(self, evidence):
        if self.smoke_fail and self.active=='new': raise ValueError('SIMULATED')
    def matches(self,before): return self.active==before['manifestHash']
    def rollback(self,revision):
        self.rollbacks+=1
        if self.rollback_fail: raise ValueError('SIMULATED')
        self.revision+=1; self.active='old'


class EngineTests(unittest.TestCase):
    def test_success_and_replay(self):
        host=FakeHost(); first=execute(request(),host); second=execute(request(),host)
        self.assertEqual(first,second); self.assertEqual('SUCCESS',first['status']); self.assertEqual(1,host.upgrades)
    def test_deployment_id_collision(self):
        host=FakeHost(); execute(request(),host); changed=request(); changed['ExpectedPreviousRevision']='4'
        with self.assertRaises(ValueError): execute(changed,host)
    def test_interrupted_does_not_redeploy(self):
        host=FakeHost(); execute(request(),host); host.receipts['run-123']['status']='RUNNING'
        with self.assertRaises(ValueError): execute(request(),host)
        self.assertEqual(1,host.upgrades)
    def test_stale_revision(self):
        host=FakeHost(4); result=execute(request(),host)
        self.assertEqual('FAILED',result['status']); self.assertEqual(0,host.upgrades)
    def test_upgrade_failure_rollback(self):
        host=FakeHost(upgrade_fail=True); result=execute(request(),host)
        self.assertEqual(('FAILED','upgrade','VERIFIED'),(result['status'],result['failureStage'],result['rollbackResult']))
    def test_smoke_failure_rollback(self):
        host=FakeHost(smoke_fail=True); result=execute(request(),host)
        self.assertEqual('smoke',result['failureStage']); self.assertEqual('VERIFIED',result['rollbackResult'])
    def test_rollback_failure_not_success(self):
        result=execute(request(),FakeHost(smoke_fail=True,rollback_fail=True))
        self.assertEqual('FAILED_OR_UNKNOWN',result['rollbackResult']); self.assertIsNone(result['activeRevision'])
    def test_first_install_no_invented_rollback(self):
        r=request(); r['ExpectedPreviousRevision']='0'; host=FakeHost(0,upgrade_fail=True)
        result=execute(r,host)
        self.assertEqual('NO_PREVIOUS_RELEASE',result['rollbackResult']); self.assertEqual(0,host.rollbacks)
    def test_receipt_upload_failure_does_not_repeat_helm(self):
        host=FakeHost(); host.publish=Mock(side_effect=[None,None,ValueError('SIMULATED')])
        with self.assertRaises(ValueError): execute(request(),host)
        host.publish=Mock(); execute(request(),host); self.assertEqual(1,host.upgrades)
    def test_no_mutation_without_durable_start_receipt(self):
        host=FakeHost(); host.publish=Mock(side_effect=ValueError('SIMULATED'))
        with self.assertRaises(ValueError): execute(request(),host)
        self.assertEqual(0,host.upgrades)
    def test_stale_database_gate_blocks_upgrade(self):
        host=FakeHost(); host.secret_gate=Mock(side_effect=ValueError('SIMULATED'))
        self.assertEqual('FAILED',execute(request(),host)['status']); self.assertEqual(0,host.upgrades)


class TransportTests(unittest.TestCase):
    def test_input_injection_rejected(self):
        validate_request(request())
        for field in request():
            r=request(); r[field]+='; touch /tmp/injected'
            with self.assertRaises(ValueError): validate_request(r)
        r=request(); r['Commands']='anything'
        with self.assertRaises(ValueError): validate_request(r)
    def test_null_version_rejected(self):
        r=request(); r['ArtifactVersionId']='null'
        with self.assertRaises(ValueError): validate_request(r)
    def test_conditional_publish(self):
        client=Mock(); client.put_object.return_value={'VersionId':'v1'}
        self.assertEqual('v1',put_once(client,'bucket','key',b'data')['versionId'])
        self.assertEqual('*',client.put_object.call_args.kwargs['IfNoneMatch'])
    def test_existing_object_never_overwritten(self):
        client=Mock(); client.put_object.side_effect=ClientError({'Error':{'Code':'PreconditionFailed'}},'PutObject')
        client.get_object.return_value={'VersionId':'v1','Body':io.BytesIO(b'old')}
        with self.assertRaises(ValueError): put_once(client,'bucket','key',b'new')
    def test_poll_eventual_consistency(self):
        client=Mock(); client.get_command_invocation.side_effect=[ClientError({'Error':{'Code':'InvocationDoesNotExist'}},'GetCommandInvocation'),{'Status':'InProgress'},{'Status':'Success','ResponseCode':0}]
        self.assertEqual(('Success',0),poll(client,'command','instance',sleep=lambda _:None))
        client.send_command.assert_not_called()
    def test_poll_timeout_never_resends(self):
        client=Mock(); client.get_command_invocation.return_value={'Status':'InProgress'}
        with self.assertRaises(TimeoutError): poll(client,'command','instance',timeout=1,sleep=lambda _:None,clock=Mock(side_effect=[0,0,2]))
        client.send_command.assert_not_called()
    def test_terminal_failure(self):
        client=Mock(); client.get_command_invocation.return_value={'Status':'Failed','ResponseCode':1}
        self.assertEqual(('Failed',1),poll(client,'command','instance'))
    def test_fixed_helm_flags(self):
        host=Host({'region':'us-east-1'},'.','.'); host.run=Mock()
        host.upgrade(); args=host.run.call_args.args[0]
        self.assertEqual(['helm','upgrade','--install','platform-services','platform-services.tgz','-n','apps','-f','values.resolved.yaml','--rollback-on-failure','--wait=legacy','--wait-for-jobs','--timeout','10m','--history-max','10'],args)
        host.rollback(3)
        self.assertEqual(['helm','rollback','platform-services','3','-n','apps','--no-hooks','--wait=legacy','--timeout','10m'],host.run.call_args.args[0])


class StaticTests(unittest.TestCase):
    def test_baseline(self): validate(snapshot())

    def test_aws_delivery_triggers_must_remain_manual(self):
        for workflow in ('build','release','deploy'):
            data=snapshot()
            data[workflow]=data[workflow].replace('  workflow_dispatch:', '  push:')
            with self.subTest(workflow=workflow), self.assertRaisesRegex(ValueError,'manual-only'):
                validate(data)

    def test_aws_delivery_ref_gates_must_precede_oidc(self):
        for workflow in ('build','release','deploy'):
            for replacement in ("if: github.ref == 'refs/heads/feature'", 'if: always()'):
                data=snapshot()
                original=("if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/develop'"
                          if workflow=='build' else "if: github.ref == 'refs/heads/main'")
                self.assertIn(original,data[workflow])
                data[workflow]=data[workflow].replace(original,replacement)
                with self.subTest(workflow=workflow,replacement=replacement), self.assertRaisesRegex(ValueError,'ref gate'):
                    validate(data)

    def test_aws_delivery_permissions_are_closed(self):
        for workflow in ('build','release','deploy'):
            data=snapshot()
            data[workflow]=data[workflow].replace('id-token: write','id-token: read')
            with self.subTest(workflow=workflow), self.assertRaisesRegex(ValueError,'job permissions'):
                validate(data)
        data=snapshot()
        data['release']=data['release'].replace('permissions:\n  contents: read',
                                             'permissions:\n  contents: read\n  id-token: write')
        with self.assertRaisesRegex(ValueError,'workflow permissions'):
            validate(data)

    def test_unreviewed_oidc_job_cannot_bypass_existing_ref_gate(self):
        data=snapshot()
        release=yaml.load(data['release'],Loader=yaml.BaseLoader)
        release['jobs']['other']={'runs-on':'ubuntu-latest','permissions':{'id-token':'write'},'steps':[]}
        data['release']=yaml.safe_dump(release)
        with self.assertRaisesRegex(ValueError,'Unreviewed AWS delivery job'):
            validate(data)

    def test_publisher_cannot_gain_ssm(self):
        data=snapshot(); data['iam']=data['iam'].replace('"ecr:GetAuthorizationToken"','"ecr:GetAuthorizationToken", "ssm:SendCommand"')
        with self.assertRaises(ValueError): validate(data)
    def test_orchestrator_cannot_gain_artifact_write(self):
        data=snapshot(); marker='resource "aws_iam_role_policy" "orchestrator"'
        prefix,suffix=data['iam'].split(marker)
        suffix=suffix.replace('"s3:GetObject", "s3:GetObjectVersion"','"s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"',1)
        data['iam']=prefix+marker+suffix
        with self.assertRaises(ValueError): validate(data)
    def test_static_regressions(self):
        for field,old,new in [('iam','environment:dev','ref:refs/heads/*'),('iam','interpolationType = "ENV_VAR"','interpolationType = "TEXT"'),
                              ('build','needs: validate','needs: prepare'),('deploy','environment: dev','environment: prod'),
                              ('deploy','cancel-in-progress: false','cancel-in-progress: true'),('deploy','script','kubectl script')]:
            data=snapshot(); data[field]=data[field].replace(old,new)
            self.assertNotEqual(snapshot()[field], data[field], 'Negative fixture must mutate the source')
            with self.subTest(field=field,old=old), self.assertRaises(ValueError): validate(data)

    def test_unpinned_checkout_rejected_after_a_reviewed_pin_update(self):
        original = snapshot()
        pin = re.search(r'actions/checkout@([0-9a-f]{40})', original['build'])
        self.assertIsNotNone(pin, 'The fixture needs a real pinned checkout')
        # A valid replacement pin models a future Dependabot PR without
        # trusting or executing that synthetic action. Never rely on an old SHA.
        for reviewed_pin in (pin[1], 'a' * 40):
            data = copy.deepcopy(original)
            data['build'] = data['build'].replace('actions/checkout@' + pin[1], 'actions/checkout@' + reviewed_pin)
            validate(data)
            before = data['build']
            data['build'] = data['build'].replace('actions/checkout@' + reviewed_pin, 'actions/checkout@v4')
            self.assertNotEqual(before, data['build'])
            with self.subTest(pin=reviewed_pin), self.assertRaises(ValueError): validate(data)


if __name__=='__main__': unittest.main()
