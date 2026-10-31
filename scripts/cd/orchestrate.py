"""Runner-side SSM orchestration. No Kubernetes client or deploy credentials."""
import json
import os
from pathlib import Path
import re
import time
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from common import MAX_BYTES, require, sha, validate_bundle
from executor import validate_request
from synthetic_contract import publication_scope, target_environment


def deployment_target(environment):
    selected, scope = publication_scope(environment)
    account=environment['AWS_ACCOUNT_ID'];region=environment['AWS_REGION']
    group=environment['PLATFORM_ALB_GROUP_NAME'];sg=environment['ALB_FRONTEND_SECURITY_GROUP_ID']
    queue=environment['SHIPMENT_QUEUE_URL']
    require(re.fullmatch('[0-9]{12}',account) and re.fullmatch(r'sg-[0-9a-f]{17}',sg),'Invalid fixed platform identity')
    require(re.fullmatch('[A-Za-z0-9-]+',group),'Invalid fixed ALB group')
    if scope is not None: require(group == scope['namespace'], 'Synthetic ALB namespace mismatch')
    require(queue.startswith(f'https://sqs.{region}.amazonaws.com/{account}/'),'Queue account/region mismatch')
    target = {'environment':selected, **({'dataScope':scope} if scope is not None else {}), 'accountId':account,'region':region,'clusterName':environment['EKS_CLUSTER_NAME'],'namespace':'apps','helmRelease':'platform-services',
            'repositories':{s:f'{account}.dkr.ecr.{region}.amazonaws.com/{s}-service' for s in ('auth','shipment','tracking')},
            'shipmentQueueUrl':queue,'alb':{'groupName':group,'frontendSecurityGroupId':sg,'discoveryTags':{'Project':'cnp' if scope is not None else group,'Environment':selected}}}
    target_environment(target)
    return target


def poll(ssm, command_id, instance, timeout=3900, sleep=time.sleep, clock=time.monotonic):
    deadline=clock()+timeout
    while clock()<deadline:
        try:
            response=ssm.get_command_invocation(CommandId=command_id,InstanceId=instance)
            if response['Status'] not in ('Pending','InProgress','Delayed'):
                return response['Status'],response.get('ResponseCode',-1)
        except ClientError as error:
            if error.response['Error']['Code']!='InvocationDoesNotExist': raise
        sleep(5)
    raise TimeoutError('Runner polling expired; host may still be running. Inspect this CommandId and receipt; do not resend.')


def main(client_factory=None):
    client_factory=client_factory or boto3.client
    request={k:os.environ[k] for k in ('ArtifactKey','ArtifactVersionId','ArtifactSha256','DeploymentId','ExpectedPreviousRevision')}
    bucket=os.environ['ARTIFACT_BUCKET']; region=os.environ['AWS_REGION']; account=os.environ['AWS_ACCOUNT_ID']
    # Platform-owned variables, never identities taken from the untrusted bundle.
    target=deployment_target(os.environ)
    validate_request(request, target)
    # This client only reads immutable artifacts and durable receipts. Bounded
    # transport retries are safe here; SendCommand below remains single-attempt.
    s3=client_factory('s3',region_name=region,
                    config=Config(retries={'mode':'standard','total_max_attempts':3}))
    # SendCommand has no client idempotency token. An uncertain transport failure
    # must not be automatically retried by botocore.
    ssm=client_factory('ssm',region_name=region,config=Config(retries={'total_max_attempts':1}))
    response=s3.get_object(Bucket=bucket,Key=request['ArtifactKey'],VersionId=request['ArtifactVersionId'])
    require(response.get('VersionId')==request['ArtifactVersionId'],'S3 version mismatch')
    require(response['ContentLength']<=MAX_BYTES,'Artifact exceeds download limit')
    validate_bundle(response['Body'].read(MAX_BYTES+1),request['ArtifactSha256'],target)
    version=os.environ['SSM_DOCUMENT_VERSION']; digest=os.environ['SSM_DOCUMENT_SHA256']
    require(re.fullmatch('[1-9][0-9]*',version) and re.fullmatch('[0-9a-f]{64}',digest),'Pin reviewed document version and hash')
    instance=os.environ['MANAGEMENT_INSTANCE_ID']
    command=ssm.send_command(InstanceIds=[instance],DocumentName=os.environ['SSM_DOCUMENT_NAME'],DocumentVersion=version,
                             DocumentHash=digest,DocumentHashType='Sha256',TimeoutSeconds=600,
                             Parameters={k:[v] for k,v in request.items()},Comment='Deployment '+request['DeploymentId'])
    command_id=command['Command']['CommandId']
    print('SSM CommandId: '+command_id,flush=True)
    Path('ssm-command.json').write_text(json.dumps({'commandId':command_id,'instanceId':instance,'deploymentId':request['DeploymentId']}))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as out: out.write(f'CommandId: `{command_id}`; DeploymentId: `{request["DeploymentId"]}`\n')
    status,code=poll(ssm,command_id,instance)
    Path('ssm-command.json').write_text(json.dumps({'commandId':command_id,'instanceId':instance,'deploymentId':request['DeploymentId'],'status':status,'responseCode':code}))
    print(f'SSM terminal status: {status}; responseCode: {code}',flush=True)
    receipt=json.loads(s3.get_object(Bucket=bucket,Key='deployment-receipts/'+target['environment']+'/'+request['DeploymentId']+'.json')['Body'].read())
    require(receipt['artifact']=={k:request[k] for k in ('ArtifactKey','ArtifactVersionId','ArtifactSha256')},'Receipt artifact mismatch')
    Path('deployment-receipt.json').write_text(json.dumps(receipt,sort_keys=True,indent=2))
    print(json.dumps(receipt))
    require(status=='Success' and code==0 and receipt['status']=='SUCCESS','Deployment failed; inspect receipt. No automatic resend.')


if __name__=='__main__': main()
