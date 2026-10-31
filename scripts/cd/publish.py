"""Build-image records and immutable release publication. Invoked by publisher only."""
import argparse
import base64
from contextlib import ExitStack
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from common import ROOT, require, sha
from package import canonical, package
from scan_policy import require_clean_scan
from synthetic_contract import publication_scope


def put_once(s3, bucket, key, data):
    try:
        result=s3.put_object(Bucket=bucket,Key=key,Body=data,IfNoneMatch='*')
    except ClientError as error:
        if error.response['Error']['Code'] not in ('PreconditionFailed','412'): raise
        result=s3.get_object(Bucket=bucket,Key=key)
        require(result['Body'].read()==data,'Immutable object already exists with different bytes')
    require(result.get('VersionId') not in (None,'null'),'Versioned artifacts bucket required')
    return {'bucket':bucket,'key':key,'versionId':result['VersionId'],'sha256':sha(data)}


def build(service, s3, ecr, bucket, account, region, commit, run_id, *, operator=False, existing_only=False):
    metadata=json.loads((ROOT/'release/services.json').read_text())['services']
    spec=next(s for s in metadata if s['id']==service)
    repository=spec['ecrRepository']; tag=('operator-sha-' if operator else 'sha-')+commit
    record_prefix='operator-image-records' if operator else 'image-records'
    record_key=f'{record_prefix}/dev/{commit}/{service}.json'
    try:
        previous=json.loads(s3.get_object(Bucket=bucket,Key=record_key)['Body'].read())
    except ClientError as error:
        # Publisher cannot ListBucket; a missing record can be AccessDenied. ECR
        # proves whether this is a fresh build; an existing image without evidence
        # fails closed and requires explicit operator reconciliation.
        if error.response['Error']['Code'] not in ('NoSuchKey','AccessDenied','404'): raise
        previous=None
    try:
        images=ecr.describe_images(repositoryName=repository,imageIds=[{'imageTag':tag}])['imageDetails']
    except ecr.exceptions.ImageNotFoundException:
        images=[]
    if images:
        require(previous is not None,'Existing image lacks immutable build evidence; do not rebuild')
        require(previous['imageDigest']==images[0]['imageDigest'] and previous['sourceCommit']==commit,'Build record mismatch')
        return previous
    require(previous is None,'Build evidence exists but ECR digest is missing')
    require(not existing_only,'Imported image and immutable record required; no Docker fallback')
    registry=f'{account}.dkr.ecr.{region}.amazonaws.com'
    token=ecr.get_authorization_token()['authorizationData'][0]['authorizationToken']
    password=base64.b64decode(token).decode().split(':',1)[1]
    image=f'{registry}/{repository}:{tag}'
    # Registry authentication lives on Linux tmpfs, never in the user's Docker
    # config or a persisted credential file. AWS credentials are not build inputs.
    require(Path('/dev/shm').is_dir(), 'Linux tmpfs required for registry authentication')
    with tempfile.TemporaryDirectory(prefix='cnp-ecr-',dir='/dev/shm') as auth:
        docker_env={k:v for k,v in os.environ.items() if not k.startswith('AWS_')}
        docker_env['DOCKER_CONFIG']=auth
        subprocess.run(['docker','login','--username','AWS','--password-stdin',registry],input=password,text=True,check=True,capture_output=True,env=docker_env)
        password=None
        try:
            subprocess.run(['docker','build','--pull','--platform','linux/amd64','--provenance=false','--sbom=false','--label','org.opencontainers.image.revision='+commit,'--build-arg','SOURCE_COMMIT='+commit,'-f',spec['dockerfile'],'-t',image,spec['context']],cwd=ROOT,env=docker_env,check=True)
            subprocess.run(['docker','push',image],env=docker_env,check=True)
        finally:
            subprocess.run(['docker','logout',registry],env=docker_env,capture_output=True)
    digest=ecr.describe_images(repositoryName=repository,imageIds=[{'imageTag':tag}])['imageDetails'][0]['imageDigest']
    record={'name':service,'sourceCommit':commit,'imageRepository':registry+'/'+repository,'imageDigest':digest,'buildRunId':run_id}
    put_once(s3,bucket,record_key,canonical(record))
    return record


def verify_build_run(record, commit, repository, token):
    request=urllib.request.Request(f'https://api.github.com/repos/{repository}/actions/runs/{record["buildRunId"]}',headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=30) as response: run=json.load(response)
    require(run['head_sha']==commit and run['conclusion']=='success' and run['path']=='.github/workflows/build-sha-images.yml' and run['head_repository']['full_name']==repository,'Successful validated build evidence missing')


def validate_local_source():
    # The operator trigger must run the same source-policy gate as CI before
    # building or publishing. An unvalidated checkout is never a release input.
    subprocess.run([sys.executable, '-B', str(ROOT/'scripts/validation/validate_r4.py')],
                   cwd=ROOT, check=True)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('operation',choices=['build','release','operator-deliver','operator-redeploy','operator-import']); parser.add_argument('--service',choices=['auth','shipment','tracking'])
    parser.add_argument('--environment-file',type=Path)
    parser.add_argument('--version')
    parser.add_argument('--deployment-id')
    parser.add_argument('--expected-previous-revision')
    parser.add_argument('--publication-receipt',type=Path)
    parser.add_argument('--image-inputs',type=Path)
    parser.add_argument('--import-receipt',type=Path)
    parser.add_argument('--expected-role-id')
    args=parser.parse_args()
    if args.operation=='operator-import':
        try: operator_import(args)
        except Exception: raise SystemExit('Image import stopped; inspect the private receipt. No automatic replay or deployment.') from None
        return
    if args.operation.startswith('operator-'):
        operator_delivery(args)
        return
    deployment_environment, data_scope = publication_scope(os.environ)
    commit=os.environ['GITHUB_SHA']; require(re.fullmatch('[0-9a-f]{40}',commit),'Invalid source SHA')
    bucket=os.environ['ARTIFACT_BUCKET']; region=os.environ['AWS_REGION']; account=os.environ['AWS_ACCOUNT_ID']
    s3=boto3.client('s3',region_name=region); ecr=boto3.client('ecr',region_name=region)
    if args.operation=='build':
        record=build(args.service,s3,ecr,bucket,account,region,commit,os.environ['GITHUB_RUN_ID'])
        Path('image-'+args.service+'.json').write_bytes(canonical(record)); return
    require(os.environ['GITHUB_REF']=='refs/heads/main','Release publication requires main')
    records=[]
    for service in ('auth','shipment','tracking'):
        record=json.loads(s3.get_object(Bucket=bucket,Key=f'image-records/dev/{commit}/{service}.json')['Body'].read())
        verify_build_run(record,commit,os.environ['GITHUB_REPOSITORY'],os.environ['GH_TOKEN'])
        actual=ecr.describe_images(repositoryName=service+'-service',imageIds=[{'imageTag':'sha-'+commit}])['imageDetails'][0]['imageDigest']
        require(actual==record['imageDigest'],'ECR evidence mismatch')
        require_clean_scan(ecr,service+'-service',actual)
        records.append(record)
    # Snapshot was exported by the platform operator. Publisher can only read it.
    key=os.environ['ENVIRONMENT_CONTRACT_KEY']; version=os.environ['ENVIRONMENT_CONTRACT_VERSION']
    require(key.startswith(f'environment-contracts/{deployment_environment}/') and version and version!='null','Versioned environment snapshot required')
    environment=s3.get_object(Bucket=bucket,Key=key,VersionId=version)['Body'].read()
    require(sha(environment)==os.environ['ENVIRONMENT_CONTRACT_SHA256'],'Environment snapshot integrity failure')
    require(os.environ.get('MIGRATION_COMPATIBILITY')=='previous-release-compatible','Reviewer must declare migration compatibility')
    data,manifest=package(environment,records,commit,os.environ['RELEASE_VERSION'],
                          expected_environment=deployment_environment, expected_data_scope=data_scope)
    receipt=put_once(s3,bucket,f'deploy-artifacts/{deployment_environment}/{commit}/{sha(data)}.tar.gz',data)
    receipt.update(applicationSourceCommit=commit,releaseVersion=manifest['releaseVersion'])
    if data_scope is not None: receipt.update(environment=deployment_environment, dataScope=data_scope)
    Path('publication-receipt.json').write_bytes(canonical(receipt))
    Path('release-manifest.json').write_bytes(canonical(manifest))
    print(json.dumps(receipt))



def validate_operator_identity(identity,role_id):
    require(re.fullmatch(r'AROA[A-Z0-9]{17}',role_id or ''),'Fresh expected delivery RoleId required')
    arn=identity.get('Arn','');session=re.fullmatch(r'arn:aws:sts::341936017254:assumed-role/cnp-cert-private-cd-executor/([A-Za-z0-9+=,.@_-]{2,64})',arn)
    require(identity.get('Account')=='341936017254' and session and identity.get('UserId')==role_id+':'+session[1],'Wrong delivery identity/generation')


def operator_session(role_id,note,session_factory=None):
    """Existing profile -> approved STS role; temporary credentials remain in memory."""
    require(re.fullmatch(r'AROA[A-Z0-9]{17}',role_id or ''),'Fresh expected delivery RoleId required')
    factory=session_factory or boto3.Session;cfg=Config(retries={'total_max_attempts':1},connect_timeout=5,read_timeout=20)
    base=factory(profile_name='cnp-cert-dev',region_name='us-east-1');sts=base.client('sts',config=cfg)
    identity=sts.get_caller_identity()
    require(identity.get('Account')=='341936017254' and identity.get('Arn')=='arn:aws:iam::341936017254:user/cnp-cert-admin' and identity.get('UserId')=='AIDAU7HHZR5TGLGKSTEKJ','Wrong existing profile identity')
    note('INTENT',operation='sts:AssumeRole',target='arn:aws:iam::341936017254:role/cnp-cert-private-cd-executor')
    response=sts.assume_role(RoleArn='arn:aws:iam::341936017254:role/cnp-cert-private-cd-executor',RoleSessionName='cnp-private-cd-operator',DurationSeconds=3600)
    credentials=response['Credentials']
    session=factory(aws_access_key_id=credentials['AccessKeyId'],aws_secret_access_key=credentials['SecretAccessKey'],aws_session_token=credentials['SessionToken'],region_name='us-east-1')
    credentials=None;response=None
    assumed=session.client('sts',config=cfg).get_caller_identity();validate_operator_identity(assumed,role_id)
    note('OBSERVED',operation='sts:AssumeRole',principal=assumed['Arn'],roleId=role_id)
    return session,assumed,cfg


def import_oci(ecr,image,identity,role_id,note):
    """Single-attempt existing ECR APIs; unknown results stop for reconciliation."""
    from image_oci import MANIFEST,digest
    validate_operator_identity(identity,role_id);image.unchanged()
    require('sha256:'+digest(image.manifest_bytes)==image.manifest_digest,'Cached manifest integrity mismatch')
    repository=image.service+'-service';tag='operator-sha-'+image.commit;account='341936017254'
    try:existing=ecr.describe_images(registryId=account,repositoryName=repository,imageIds=[{'imageTag':tag}])['imageDetails']
    except ClientError as error:
        if error.response['Error']['Code']!='ImageNotFoundException':raise
        existing=[]
    if existing:
        require(len(existing)==1 and existing[0]['imageDigest']==image.manifest_digest,'Immutable image tag collision')
        note('OBSERVED',operation='ecr:DescribeImages',repository=repository,imageDigest=image.manifest_digest,reused=True)
        return image.manifest_digest
    def mutation(operation,**arguments):
        note('INTENT',operation='ecr:'+operation,repository=repository,**{k:v for k,v in arguments.items() if k in ('uploadId','layerDigests','partFirstByte','partLastByte','imageTag')})
        try:result=getattr(ecr,operation)(registryId=account,repositoryName=repository,**arguments)
        except Exception as error:
            code=error.response['Error']['Code'] if isinstance(error,ClientError) else type(error).__name__
            note('REJECTED' if isinstance(error,ClientError) else 'UNKNOWN',operation='ecr:'+operation,repository=repository,code=code)
            raise
        note('RETURNED',operation='ecr:'+operation,repository=repository,uploadId=result.get('uploadId'))
        return result
    blobs={d['digest']:d for d in image.blobs}
    result=ecr.batch_check_layer_availability(registryId=account,repositoryName=repository,layerDigests=list(blobs))
    require(not result.get('failures'),'ECR blob availability failure')
    observed=result.get('layers',[]);require(len(observed)==len(blobs) and {d.get('layerDigest') for d in observed}==set(blobs) and all(d.get('layerAvailability') in ('AVAILABLE','UNAVAILABLE') for d in observed),'Incomplete ECR blob availability')
    available={d['layerDigest'] for d in observed if d['layerAvailability']=='AVAILABLE'}
    for sha,descriptor in blobs.items():
        if sha in available:continue
        initiated=mutation('initiate_layer_upload');upload=initiated.get('uploadId');part_size=initiated.get('partSize')
        require(isinstance(upload,str) and re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',upload),'Invalid upload identity; reconcile before retry')
        require(type(part_size) is int and 5*1024**2<=part_size<=20*1024**2,'Unsupported ECR part size; reconcile before retry')
        h=hashlib.sha256();offset=0
        with image.open_blob(descriptor) as stream:
            while chunk:=stream.read(part_size):
                h.update(chunk);last=offset+len(chunk)-1
                part=mutation('upload_layer_part',uploadId=upload,partFirstByte=offset,partLastByte=last,layerPartBlob=chunk)
                require(part.get('lastByteReceived')==last,'Partial layer response; reconcile before retry');offset=last+1
        require(offset==descriptor['size'] and 'sha256:'+h.hexdigest()==sha,'Layer changed during upload')
        require(mutation('complete_layer_upload',uploadId=upload,layerDigests=[sha]).get('layerDigest')==sha,'Completed layer digest mismatch')
    response=mutation('put_image',imageManifest=image.manifest_bytes.decode(),imageManifestMediaType=MANIFEST,imageTag=tag,imageDigest=image.manifest_digest)
    require(response.get('image',{}).get('imageId',{}).get('imageDigest')==image.manifest_digest,'ECR image digest response mismatch')
    return image.manifest_digest


def operator_import(args):
    """Import exactly three reviewed images; no Docker, deployment or new IAM grant."""
    from image_oci import Image,SERVICES,source_manifest,canonical as source_bytes,digest,load
    require(args.image_inputs and args.import_receipt and args.expected_role_id,'Image inputs, private new receipt and fresh RoleId required')
    require(os.environ.get('AWS_ACCOUNT_ID')=='341936017254' and os.environ.get('AWS_REGION')=='us-east-1' and os.environ.get('ARTIFACT_BUCKET')=='cloud-native-platform-341936017254-dev-us-east-1-artifacts','Approved publisher scope required')
    target=args.import_receipt.resolve();require(not target.is_relative_to(ROOT.resolve()) and target.parent.is_dir() and not target.exists(),'New private receipt outside checkout required')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    validate_local_source()
    inputs=load(args.image_inputs.read_bytes());require(isinstance(inputs,list) and len(inputs)==3 and {x.get('service') for x in inputs}==set(SERVICES),'Exactly three image inputs required')
    with ExitStack() as stack:
        images=[]
        for spec in inputs:
            require(set(spec)=={'service','archive','sha256'},'Image input fields mismatch')
            source=source_manifest(ROOT,spec['service'],commit)
            images.append(stack.enter_context(Image(spec['archive'],spec['sha256'],spec['service'],commit,digest(source_bytes(source)))))
        # All three file/source/platform graphs pass before identity or writes.
        with target.open('x',encoding='utf-8') as journal:
            def note(state,**data):journal.write(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'state':state,**data},sort_keys=True)+'\n');journal.flush()
            try:
                session,identity,cfg=operator_session(args.expected_role_id,note)
                ecr=session.client('ecr',config=cfg);s3=session.client('s3',config=cfg);records=[]
                for image in images:
                    actual=import_oci(ecr,image,identity,args.expected_role_id,note)
                    require_clean_scan(ecr,image.service+'-service',actual)
                    record={'name':image.service,'sourceCommit':commit,'imageRepository':'341936017254.dkr.ecr.us-east-1.amazonaws.com/'+image.service+'-service','imageDigest':actual,'buildRunId':str(int(image.archive_sha,16)+1)}
                    key='operator-image-records/dev/'+commit+'/'+image.service+'.json'
                    note('INTENT',operation='s3:PutObject',key=key,archiveSha256=image.archive_sha,imageDigest=actual)
                    result=put_once(s3,'cloud-native-platform-341936017254-dev-us-east-1-artifacts',key,canonical(record))
                    note('CONFIRMED',operation='s3:PutObject',key=key,versionId=result['versionId'],record=record,producer='OPERATOR_LOCAL',githubActionsVerified=False)
                    records.append(record)
                note('COMPLETE',producer='OPERATOR_LOCAL',githubActionsVerified=False,images=records,deploymentStarted=False)
            except Exception as error:
                code=error.response['Error']['Code'] if isinstance(error,ClientError) else type(error).__name__
                note('STOPPED_RECONCILE_BEFORE_REPLAY',code=code);raise

def operator_delivery(args):
    """Explicit human-operated trigger of the same build/artifact/SSM pipeline.

    It never invents a GitHub Actions run. Operator image records/tags have their
    own namespace, so future CI builds cannot adopt unverified operator evidence.
    GitHub release publication retains its successful-run verification above.
    """
    from orchestrate import main as deploy
    _, data_scope = publication_scope(os.environ)
    require(data_scope is None, 'Synthetic operator effects are not admitted')
    require(args.deployment_id and args.expected_previous_revision is not None,'Deployment ID and expected revision required')
    require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.deployment_id),'Invalid deployment ID')
    require(re.fullmatch('0|[1-9][0-9]{0,8}',str(args.expected_previous_revision)),'Invalid expected revision')
    account=os.environ['AWS_ACCOUNT_ID'];region=os.environ['AWS_REGION'];bucket=os.environ['ARTIFACT_BUCKET']
    session=None
    if getattr(args,'expected_role_id',None):
        session,identity,cfg=operator_session(args.expected_role_id,lambda *_args,**_kwargs:None)
    else:
        identity=boto3.client('sts',region_name=region).get_caller_identity()
    client=(lambda service,**kwargs:session.client(service,config=cfg,**kwargs)) if session else boto3.client
    require(identity['Account']==account and identity['Arn'].startswith(f'arn:aws:sts::{account}:assumed-role/cnp-cert-private-cd-executor/'),'Use the dedicated temporary operator role')
    if args.operation=='operator-redeploy':
        require(args.publication_receipt is not None,'An immutable publication receipt is required')
        receipt=json.loads(args.publication_receipt.read_text())
        require(receipt['bucket']==bucket,'Wrong artifact bucket')
    else:
        require(args.environment_file is not None and args.version,'Environment snapshot and reviewed version required')
        require(re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+',args.version),'Invalid release version')
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        require(not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip(),'Build only a clean committed checkout')
        require(re.fullmatch('[0-9a-f]{40}',commit),'Invalid source SHA')
        environment=args.environment_file.read_bytes()
        require(json.loads(environment)['accountId']==account and json.loads(environment)['region']==region,'Wrong environment')
        validate_local_source()
        s3=client('s3',region_name=region);ecr=client('ecr',region_name=region)
        run_id=str(time.time_ns()) # Operator operation ID, explicitly NOT a GitHub run ID.
        records=[build(s,s3,ecr,bucket,account,region,commit,run_id,operator=True,existing_only=session is not None) for s in ('auth','shipment','tracking')]
        for record in records:require_clean_scan(ecr,record['name']+'-service',record['imageDigest'])
        data,manifest=package(environment,records,commit,args.version)
        receipt=put_once(s3,bucket,f'deploy-artifacts/dev/{commit}/{sha(data)}.tar.gz',data)
        receipt.update(applicationSourceCommit=commit,releaseVersion=manifest['releaseVersion'],producer='OPERATOR_LOCAL',githubActionsVerified=False,operatorPrincipal=identity['Arn'],images=records)
        Path('publication-receipt.json').write_bytes(canonical(receipt))
        Path('release-manifest.json').write_bytes(canonical(manifest))
    os.environ.update(ArtifactKey=receipt['key'],ArtifactVersionId=receipt['versionId'],ArtifactSha256=receipt['sha256'],DeploymentId=args.deployment_id,ExpectedPreviousRevision=str(args.expected_previous_revision))
    if session: deploy(client_factory=session.client)
    else: deploy()


if __name__=='__main__': main()
