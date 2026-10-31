"""AWS fake transports only; no Docker, credentials or live publication."""
import argparse
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cd'))
import image_oci as o
import publish as p
import orchestrate
from botocore.exceptions import ClientError
from test_image_oci import fixture,archive,COMMIT,SOURCE

ROLE='AROA'+'A'*17
IDENTITY={'Account':'341936017254','Arn':'arn:aws:sts::341936017254:assumed-role/cnp-cert-private-cd-executor/cnp-private-cd-operator','UserId':ROLE+':cnp-private-cd-operator'}
BASE={'Account':'341936017254','Arn':'arn:aws:iam::341936017254:user/cnp-cert-admin','UserId':'AIDAU7HHZR5TGLGKSTEKJ'}
ENV={'AWS_ACCOUNT_ID':'341936017254','AWS_REGION':'us-east-1','ARTIFACT_BUCKET':'cloud-native-platform-341936017254-dev-us-east-1-artifacts'}


def error(code):return ClientError({'Error':{'Code':code}},'Synthetic')


class FakeECR:
    def __init__(self,available=False,existing=None,part_size=5*1024**2):self.calls=[];self.uploads={};self.available=available;self.existing=existing;self.part_size=part_size
    def describe_images(self,**kw):
        self.calls.append(('describe_images',kw))
        if self.existing:return {'imageDetails':[{'imageDigest':self.existing}]}
        raise error('ImageNotFoundException')
    def batch_check_layer_availability(self,**kw):
        self.calls.append(('batch_check_layer_availability',kw))
        return {'layers':[{'layerDigest':d,'layerAvailability':'AVAILABLE' if self.available else 'UNAVAILABLE'} for d in kw['layerDigests']]}
    def initiate_layer_upload(self,**kw):
        upload='00000000-0000-0000-0000-'+str(len(self.uploads)+1).zfill(12);self.uploads[upload]=bytearray();self.calls.append(('initiate_layer_upload',kw));return {'uploadId':upload,'partSize':self.part_size}
    def upload_layer_part(self,**kw):
        self.calls.append(('upload_layer_part',{k:v for k,v in kw.items() if k!='layerPartBlob'}));data=self.uploads[kw['uploadId']]
        assert len(data)==kw['partFirstByte'];data.extend(kw['layerPartBlob']);assert len(data)-1==kw['partLastByte']
        return {'lastByteReceived':len(data)-1}
    def complete_layer_upload(self,**kw):
        self.calls.append(('complete_layer_upload',kw));assert kw['layerDigests']==['sha256:'+o.digest(self.uploads[kw['uploadId']])]
        return {'layerDigest':kw['layerDigests'][0]}
    def put_image(self,**kw):
        self.calls.append(('put_image',kw));assert 'sha256:'+o.digest(kw['imageManifest'].encode())==kw['imageDigest']
        return {'image':{'imageId':{'imageDigest':kw['imageDigest']}}}


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.path=self.root/'image.oci.tar';self.h=archive(self.path,fixture());self.events=[]
    def note(self,state,**values):self.events.append({'state':state,**values})
    def run_import(self,ecr=None):
        with o.Image(self.path,self.h,'auth',COMMIT,SOURCE) as image:return p.import_oci(ecr or FakeECR(),image,IDENTITY,ROLE,self.note)

    def test_streamed_blobs_and_exact_ecr_digest(self):
        ecr=FakeECR();actual=self.run_import(ecr)
        self.assertEqual(2,len(ecr.uploads));self.assertEqual('put_image',ecr.calls[-1][0]);self.assertEqual(actual,ecr.calls[-1][1]['imageDigest'])
        self.assertTrue(all(kw['registryId']=='341936017254' and kw['repositoryName']=='auth-service' for _,kw in ecr.calls))
        self.assertNotIn('layerPartBlob',json.dumps(self.events));self.assertNotIn('imageManifest',json.dumps(self.events))

    def test_available_blobs_skip_upload_and_existing_exact_tag_is_idempotent(self):
        ecr=FakeECR(available=True);digest=self.run_import(ecr);self.assertEqual(0,len(ecr.uploads))
        ecr=FakeECR(existing=digest);self.assertEqual(digest,self.run_import(ecr));self.assertEqual(1,len(ecr.calls))
        with self.assertRaisesRegex(ValueError,'collision'):self.run_import(FakeECR(existing='sha256:'+'f'*64))

    def test_multipart_offsets_and_digest_for_incompressible_synthetic_bytes(self):
        self.h=archive(self.path,fixture(payload=os.urandom(6*1024**2)))
        for size,expected in ((5*1024**2,3),(20*1024**2,2)):
            ecr=FakeECR(part_size=size);self.run_import(ecr)
            parts=[kw for op,kw in ecr.calls if op=='upload_layer_part']
            self.assertEqual(expected,len(parts));self.assertEqual(size if expected==3 else 0,parts[-1]['partFirstByte'])

    def test_identity_missing_foreign_or_wrong_generation_has_zero_ecr_calls(self):
        for identity,role in [({},ROLE),(BASE,ROLE),(IDENTITY,None),({**IDENTITY,'UserId':'AROA'+'B'*17+':cnp-private-cd-operator'},ROLE),({**IDENTITY,'Account':'000000000000'},ROLE)]:
            ecr=FakeECR()
            with self.subTest(identity=identity),o.Image(self.path,self.h,'auth',COMMIT,SOURCE) as image,self.assertRaises(ValueError):p.import_oci(ecr,image,identity,role,self.note)
            self.assertEqual([],ecr.calls)

    def test_incomplete_availability_partial_upload_digest_mismatch_and_denial_stop(self):
        for mode in ('coverage','duplicate','partial','complete','put','denied','unknown','upload-id','part-size'):
            ecr=FakeECR()
            if mode=='coverage':ecr.batch_check_layer_availability=Mock(return_value={'layers':[]})
            if mode=='duplicate':ecr.batch_check_layer_availability=Mock(return_value={'layers':[{'layerDigest':'sha256:'+'f'*64,'layerAvailability':'AVAILABLE'}]*2})
            if mode=='partial':ecr.upload_layer_part=Mock(return_value={'lastByteReceived':-1})
            if mode=='complete':ecr.complete_layer_upload=Mock(return_value={'layerDigest':'sha256:'+'f'*64})
            if mode=='put':ecr.put_image=Mock(return_value={'image':{'imageId':{'imageDigest':'sha256:'+'f'*64}}})
            if mode=='denied':ecr.initiate_layer_upload=Mock(side_effect=error('AccessDeniedException'))
            if mode=='unknown':ecr.initiate_layer_upload=Mock(side_effect=TimeoutError('synthetic'))
            if mode=='upload-id':ecr.initiate_layer_upload=Mock(return_value={'uploadId':'wrong','partSize':5*1024**2})
            if mode=='part-size':ecr.part_size=21*1024**2
            with self.subTest(mode=mode),self.assertRaises((ValueError,ClientError,TimeoutError)):self.run_import(ecr)
            if mode in ('coverage','duplicate','partial','complete','denied','unknown','upload-id','part-size'):self.assertFalse(any(op=='put_image' for op,_ in ecr.calls))
            if mode in ('denied','unknown'):
                self.assertEqual(1,ecr.initiate_layer_upload.call_count)
                self.assertEqual('REJECTED' if mode=='denied' else 'UNKNOWN',self.events[-1]['state'])

    def test_changed_archive_and_cached_manifest_block_writes(self):
        for mode in ('file','manifest'):
            self.h=archive(self.path,fixture());ecr=FakeECR()
            with o.Image(self.path,self.h,'auth',COMMIT,SOURCE) as image:
                if mode=='file':
                    with self.path.open('ab') as f:f.write(b'bad')
                else:image.manifest_bytes+=b'bad'
                with self.assertRaises(ValueError):p.import_oci(ecr,image,IDENTITY,ROLE,self.note)
            self.assertEqual([],ecr.calls)

    def test_missing_imported_record_never_falls_back_to_docker_or_registry_login(self):
        s3=Mock();s3.get_object.side_effect=error('NoSuchKey');ecr=Mock();ecr.exceptions.ImageNotFoundException=type('Missing',(Exception,),{})
        ecr.describe_images.side_effect=ecr.exceptions.ImageNotFoundException()
        with patch.object(p.subprocess,'run') as docker,self.assertRaisesRegex(ValueError,'no Docker fallback'):
            p.build('auth',s3,ecr,ENV['ARTIFACT_BUCKET'],'341936017254','us-east-1',COMMIT,'123',operator=True,existing_only=True)
        docker.assert_not_called();ecr.get_authorization_token.assert_not_called()

    def inputs(self,bad=False):
        manifest={'schemaVersion':1,'service':'auth','sourceCommit':COMMIT,'platform':'linux/amd64','files':{'Dockerfile':{'sha256':'c'*64,'bytes':1},'app.txt':{'sha256':'d'*64,'bytes':1}}}
        rows=[];sources={}
        for service in o.SERVICES:
            sources[service]={**manifest,'service':service};path=self.root/(service+'.oci.tar')
            h=archive(path,fixture(service=service,source=o.digest(o.canonical(sources[service]))));rows.append({'service':service,'archive':str(path),'sha256':h})
        if bad:rows[-1]['sha256']='0'*64
        path=self.root/'inputs.json';path.write_text(json.dumps(rows),encoding='utf-8')
        return argparse.Namespace(image_inputs=path,import_receipt=self.root/'private-receipt.jsonl',expected_role_id=ROLE),sources

    def test_all_three_validate_before_any_identity_call(self):
        args,sources=self.inputs(bad=True)
        with patch.dict(os.environ,ENV),patch.object(p.subprocess,'check_output',return_value=COMMIT),patch.object(p,'validate_local_source'), \
             patch.object(o,'source_manifest',side_effect=lambda root,s,c:sources[s]),patch.object(p,'operator_session') as session,self.assertRaises(ValueError):p.operator_import(args)
        session.assert_not_called();self.assertFalse(args.import_receipt.exists())

    def test_three_import_records_are_scan_gated_immutable_operator_only_and_no_deploy(self):
        args,sources=self.inputs();s3=Mock();s3.put_object.return_value={'VersionId':'synthetic-v1'};ecr=FakeECR();session=Mock();session.client.side_effect=lambda service,**_:ecr if service=='ecr' else s3
        with patch.dict(os.environ,ENV),patch.object(p.subprocess,'check_output',return_value=COMMIT),patch.object(p,'validate_local_source'), \
             patch.object(o,'source_manifest',side_effect=lambda root,s,c:sources[s]),patch.object(p,'operator_session',return_value=(session,IDENTITY,None)), \
             patch.object(p,'require_clean_scan') as scan,patch.object(orchestrate,'main') as deploy:
            p.operator_import(args)
        self.assertEqual(3,scan.call_count);self.assertEqual(3,s3.put_object.call_count);deploy.assert_not_called()
        for call in s3.put_object.call_args_list:
            self.assertTrue(call.kwargs['Key'].startswith('operator-image-records/dev/'+COMMIT+'/'));self.assertEqual('*',call.kwargs['IfNoneMatch'])
            row=json.loads(call.kwargs['Body']);self.assertEqual({'name','sourceCommit','imageRepository','imageDigest','buildRunId'},set(row));self.assertTrue(row['buildRunId'].isdigit())
        receipt=[json.loads(x) for x in args.import_receipt.read_text().splitlines()]
        self.assertEqual('COMPLETE',receipt[-1]['state']);self.assertFalse(receipt[-1]['githubActionsVerified']);self.assertFalse(receipt[-1]['deploymentStarted'])

    def test_scan_failure_has_no_records_or_delivery_and_stops_for_reconciliation(self):
        args,sources=self.inputs();session=Mock();s3=Mock();session.client.side_effect=lambda service,**_:FakeECR() if service=='ecr' else s3
        with patch.dict(os.environ,ENV),patch.object(p.subprocess,'check_output',return_value=COMMIT),patch.object(p,'validate_local_source'), \
             patch.object(o,'source_manifest',side_effect=lambda root,s,c:sources[s]),patch.object(p,'operator_session',return_value=(session,IDENTITY,None)), \
             patch.object(p,'require_clean_scan',side_effect=ValueError('HIGH')),self.assertRaises(ValueError):p.operator_import(args)
        s3.put_object.assert_not_called();self.assertIn('STOPPED_RECONCILE_BEFORE_REPLAY',args.import_receipt.read_text())


class SessionTests(unittest.TestCase):
    def test_existing_redeploy_uses_same_in_memory_session_for_fixed_ssm_path(self):
        receipt=Mock();receipt.read_text.return_value=json.dumps({'bucket':ENV['ARTIFACT_BUCKET'],'key':'key','versionId':'version','sha256':'c'*64})
        args=argparse.Namespace(operation='operator-redeploy',deployment_id='test-operator',expected_previous_revision='1',expected_role_id=ROLE,publication_receipt=receipt)
        session=Mock()
        with patch.dict(os.environ,ENV),patch.object(p,'operator_session',return_value=(session,IDENTITY,None)),patch.object(orchestrate,'main') as deploy,patch.object(p.boto3,'client') as default:
            p.operator_delivery(args)
        deploy.assert_called_once_with(client_factory=session.client);default.assert_not_called()

    def test_assumed_role_generation_is_checked_before_clients_are_returned(self):
        base=Mock();role=Mock();base.client.return_value.get_caller_identity.return_value=BASE
        base.client.return_value.assume_role.return_value={'Credentials':{'AccessKeyId':'synthetic','SecretAccessKey':'synthetic','SessionToken':'synthetic'}}
        role.client.return_value.get_caller_identity.return_value={**IDENTITY,'UserId':'AROA'+'B'*17+':cnp-private-cd-operator'}
        with self.assertRaises(ValueError):p.operator_session(ROLE,Mock(),Mock(side_effect=[base,role]))

    def test_missing_role_id_has_no_credential_provider_calls(self):
        factory=Mock()
        with self.assertRaises(ValueError):p.operator_session(None,Mock(),factory)
        factory.assert_not_called()

    def test_wrong_base_identity_cannot_assume_another_principal(self):
        base=Mock();base.client.return_value.get_caller_identity.return_value={**BASE,'UserId':'wrong'}
        with self.assertRaises(ValueError):p.operator_session(ROLE,Mock(),Mock(return_value=base))
        base.client.return_value.assume_role.assert_not_called()

    def test_only_existing_profile_then_fixed_delivery_role_in_memory_and_no_token_log(self):
        base=Mock();role=Mock();base.client.return_value.get_caller_identity.return_value=BASE
        base.client.return_value.assume_role.return_value={'Credentials':{'AccessKeyId':'synthetic-id','SecretAccessKey':'synthetic-secret','SessionToken':'synthetic-token'}}
        role.client.return_value.get_caller_identity.return_value=IDENTITY
        factory=Mock(side_effect=[base,role]);note=Mock();environment=dict(os.environ)
        result=p.operator_session(ROLE,note,factory)
        self.assertIs(role,result[0]);self.assertEqual(environment,dict(os.environ))
        self.assertEqual({'profile_name':'cnp-cert-dev','region_name':'us-east-1'},factory.call_args_list[0].kwargs)
        self.assertEqual('synthetic-token',factory.call_args_list[1].kwargs['aws_session_token'])
        self.assertEqual(1,result[2].retries['total_max_attempts']);self.assertNotIn('synthetic',str(note.call_args_list))
        base.client.return_value.assume_role.assert_called_once_with(RoleArn='arn:aws:iam::341936017254:role/cnp-cert-private-cd-executor',RoleSessionName='cnp-private-cd-operator',DurationSeconds=3600)


if __name__=='__main__':unittest.main()
