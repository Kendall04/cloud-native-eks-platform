"""Operator delivery reuses the CD boundary without fabricating GitHub evidence."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cd'))
import publish
import orchestrate
from orchestrate import deployment_target


class OperatorDeliveryTests(unittest.TestCase):
    def test_management_payload_excludes_terragrunt_binary_metadata(self):
        source=(publish.ROOT/'infra/modules/management-host/main.tf').read_text()
        self.assertIn('setunion(fileset("${path.module}/deployer", "*.py"), fileset("${path.module}/deployer", "*.json"))',source)
        self.assertNotIn('fileset("${path.module}/deployer", "*")',source)

    def test_every_github_delivery_checks_the_effective_aws_account(self):
        import yaml
        for filename in ('build-sha-images.yml', 'create-release.yml', 'deploy-platform.yml'):
            workflow=yaml.load((publish.ROOT/'.github/workflows'/filename).read_text(),Loader=yaml.BaseLoader)
            steps=next(job['steps'] for job in workflow['jobs'].values() if 'steps' in job)
            credential_index=next(i for i,s in enumerate(steps) if s.get('uses','').startswith('aws-actions/configure-aws-credentials@'))
            with self.subTest(workflow=filename):
                self.assertNotIn('allowed-account-ids',steps[credential_index].get('with',{}))
                guard=steps[credential_index+1]
                self.assertEqual('Verify AWS account',guard['name'])
                self.assertEqual('${{ vars.AWS_ACCOUNT_ID }}',guard['env']['EXPECTED_AWS_ACCOUNT_ID'])
                self.assertIn('aws sts get-caller-identity',guard['run'])
                self.assertIn("'.Account == $expected'",guard['run'])
                self.assertIn('jq -e',guard['run'])

    def test_push_uses_one_required_validation_path(self):
        import yaml
        workflows=publish.ROOT/'.github/workflows'
        validate=yaml.load((workflows/'validate.yml').read_text(),Loader=yaml.BaseLoader)
        build=yaml.load((workflows/'build-sha-images.yml').read_text(),Loader=yaml.BaseLoader)
        self.assertIn('workflow_call',validate['on'])
        self.assertIn('pull_request',validate['on'])
        self.assertEqual(['main','develop'],validate['on']['push']['branches'])
        self.assertNotIn('push',build['on'])
        self.assertEqual('true',build['jobs']['validate']['with']['skip_containers'])
        self.assertEqual('./.github/workflows/validate.yml',build['jobs']['validate']['uses'])
        self.assertEqual('validate',build['jobs']['build']['needs'])

    def test_read_retries_never_enable_send_command_retries(self):
        request={'ArtifactKey':'deploy-artifacts/dev/'+'a'*40+'/'+'b'*64+'.tar.gz',
                 'ArtifactVersionId':'version-1','ArtifactSha256':'b'*64,
                 'DeploymentId':'retry-test','ExpectedPreviousRevision':'3'}
        e={**request,'ARTIFACT_BUCKET':'artifacts','AWS_REGION':'us-east-1',
           'AWS_ACCOUNT_ID':'341936017254','EKS_CLUSTER_NAME':'logistics-platform-dev',
           'PLATFORM_ALB_GROUP_NAME':'cloud-native-platform',
           'ALB_FRONTEND_SECURITY_GROUP_ID':'sg-011cfe817cd7abd79',
           'SHIPMENT_QUEUE_URL':'https://sqs.us-east-1.amazonaws.com/341936017254/project-queue',
           'SSM_DOCUMENT_VERSION':'1','SSM_DOCUMENT_SHA256':'c'*64,
           'SSM_DOCUMENT_NAME':'fixed-document','MANAGEMENT_INSTANCE_ID':'i-031d7ef07d85316af'}
        s3=Mock();ssm=Mock()
        s3.get_object.side_effect=[{'VersionId':'version-1','ContentLength':2,'Body':Mock(read=Mock(return_value=b'{}'))},
                                  {'Body':Mock(read=Mock(return_value=json.dumps({'artifact':{k:request[k] for k in ('ArtifactKey','ArtifactVersionId','ArtifactSha256')},'status':'SUCCESS'}).encode()))}]
        ssm.send_command.return_value={'Command':{'CommandId':'test-command'}}
        with patch.dict(os.environ,e,clear=True), \
             patch.object(orchestrate.boto3,'client',side_effect=[s3,ssm]) as clients, \
             patch.object(orchestrate,'validate_bundle'),patch.object(orchestrate,'Path'), \
             patch.object(orchestrate,'poll',return_value=('Success',0)),patch('builtins.print'):
            orchestrate.main()
        self.assertEqual(3,clients.call_args_list[0].kwargs['config'].retries['total_max_attempts'])
        self.assertEqual(1,clients.call_args_list[1].kwargs['config'].retries['total_max_attempts'])
        ssm.send_command.assert_called_once()

    def test_runtime_files_are_owned_by_the_nonroot_image_user(self):
        for service in ('auth', 'shipment', 'tracking'):
            dockerfile = (publish.ROOT / 'microservices' / (service+'-service') / 'Dockerfile').read_text()
            with self.subTest(service=service):
                self.assertIn('COPY --from=build --chown=app:app /app/publish .', dockerfile)
                self.assertIn('USER $APP_UID', dockerfile)

    def test_orchestration_uses_fixed_platform_target(self):
        e={'AWS_ACCOUNT_ID':'341936017254','AWS_REGION':'us-east-1','EKS_CLUSTER_NAME':'logistics-platform-dev','PLATFORM_ALB_GROUP_NAME':'cloud-native-platform','ALB_FRONTEND_SECURITY_GROUP_ID':'sg-011cfe817cd7abd79','SHIPMENT_QUEUE_URL':'https://sqs.us-east-1.amazonaws.com/341936017254/cloud-native-platform-dev-shipment-events-queue'}
        t=deployment_target(e)
        self.assertEqual(e['ALB_FRONTEND_SECURITY_GROUP_ID'],t['alb']['frontendSecurityGroupId'])
        self.assertEqual(e['SHIPMENT_QUEUE_URL'],t['shipmentQueueUrl'])
        with self.assertRaises(ValueError):deployment_target({**e,'SHIPMENT_QUEUE_URL':'https://sqs.us-east-1.amazonaws.com/000000000000/foreign'})

    def args(self, operation='operator-deliver', **changes):
        args=dict(operation=operation, deployment_id='operator-test', expected_previous_revision='3',
                  environment_file=Mock(), version='v2.0.1', publication_receipt=None)
        args.update(changes)
        return argparse.Namespace(**args)

    def test_invalid_revision_fails_before_aws_or_build(self):
        with patch.object(publish.boto3,'client') as client:
            with self.assertRaises(ValueError):
                publish.operator_delivery(self.args(expected_previous_revision='-1'))
            client.assert_not_called()

    def test_scan_failure_blocks_package_and_ssm(self):
        sts=Mock();sts.get_caller_identity.return_value={'Account':'341936017254', 'Arn':'arn:aws:sts::341936017254:assumed-role/cnp-cert-private-cd-executor/cnp-private-cd-operator'}
        args=self.args();args.environment_file.read_bytes.return_value=json.dumps({'accountId':'341936017254','region':'us-east-1'}).encode()
        record={'name':'auth','imageDigest':'sha256:'+'a'*64}
        with patch.dict(os.environ,{'AWS_ACCOUNT_ID':'341936017254','AWS_REGION':'us-east-1','ARTIFACT_BUCKET':'artifacts'}), \
             patch.object(publish.boto3,'client',return_value=sts), \
             patch.object(publish.subprocess,'check_output',side_effect=['a'*40+'\n','']), \
             patch.object(publish,'build',return_value=record) as build, \
             patch.object(publish,'validate_local_source'), \
             patch.object(publish,'require_clean_scan',side_effect=ValueError('HIGH finding')), \
             patch.object(publish,'package') as package, patch('orchestrate.main') as deploy:
            with self.assertRaises(ValueError):publish.operator_delivery(args)
            self.assertEqual(3,build.call_count)
            self.assertTrue(all(c.kwargs['operator'] for c in build.call_args_list))
            package.assert_not_called();deploy.assert_not_called()

    def test_invalid_local_source_blocks_build_and_delivery(self):
        sts=Mock();sts.get_caller_identity.return_value={'Account':'341936017254','Arn':'arn:aws:sts::341936017254:assumed-role/cnp-cert-private-cd-executor/cnp-private-cd-operator'}
        args=self.args();args.environment_file.read_bytes.return_value=json.dumps({'accountId':'341936017254','region':'us-east-1'}).encode()
        with patch.dict(os.environ,{'AWS_ACCOUNT_ID':'341936017254','AWS_REGION':'us-east-1','ARTIFACT_BUCKET':'artifacts'}), \
             patch.object(publish.boto3,'client',return_value=sts), \
             patch.object(publish.subprocess,'check_output',side_effect=['a'*40+'\n','']), \
             patch.object(publish,'validate_local_source',side_effect=ValueError('Invalid source policy')), \
             patch.object(publish,'build') as build, patch.object(publish,'package') as package, patch('orchestrate.main') as deploy:
            with self.assertRaises(ValueError):publish.operator_delivery(args)
            build.assert_not_called();package.assert_not_called();deploy.assert_not_called()

    def test_operator_records_and_tags_cannot_be_adopted_by_ci(self):
        s3=Mock();ecr=Mock();commit='b'*40
        expected={'sourceCommit':commit,'imageDigest':'sha256:'+'c'*64}
        s3.get_object.return_value={'Body':Mock(read=Mock(return_value=json.dumps(expected).encode()))}
        ecr.describe_images.return_value={'imageDetails':[{'imageDigest':expected['imageDigest']}]}
        self.assertEqual(expected,publish.build('auth',s3,ecr,'artifacts','341936017254','us-east-1',commit,'123',operator=True))
        self.assertEqual('operator-image-records/dev/'+commit+'/auth.json',s3.get_object.call_args.kwargs['Key'])
        self.assertEqual([{'imageTag':'operator-sha-'+commit}],ecr.describe_images.call_args.kwargs['imageIds'])
        publish.build('auth',s3,ecr,'artifacts','341936017254','us-east-1',commit,'123')
        self.assertEqual('image-records/dev/'+commit+'/auth.json',s3.get_object.call_args.kwargs['Key'])
        self.assertEqual([{'imageTag':'sha-'+commit}],ecr.describe_images.call_args.kwargs['imageIds'])

    def test_foreign_bucket_receipt_is_not_deployed(self):
        sts=Mock();sts.get_caller_identity.return_value={'Account':'341936017254','Arn':'arn:aws:sts::341936017254:assumed-role/cnp-cert-private-cd-executor/cnp-private-cd-operator'}
        receipt=Mock();receipt.read_text.return_value=json.dumps({'bucket':'unrelated'})
        with patch.dict(os.environ,{'AWS_ACCOUNT_ID':'341936017254','AWS_REGION':'us-east-1','ARTIFACT_BUCKET':'artifacts'}), \
             patch.object(publish.boto3,'client',return_value=sts),patch('orchestrate.main') as deploy:
            with self.assertRaises(ValueError):publish.operator_delivery(self.args('operator-redeploy',publication_receipt=receipt))
            deploy.assert_not_called()


if __name__=='__main__':unittest.main()
