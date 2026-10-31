"""Failure-oriented local contract tests; never contacts AWS."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import validate_current_profile_iam as gate


class IamPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.documents = gate.validate()
    def doc(self, kind): return copy.deepcopy(self.documents[f'cnp-cert-{kind}-workload-boundary'])
    def allowed(self, kind, action, resource, **context):
        return gate.boundary_allows(self.doc(kind), action, resource, context)

    def test_exact_three_documents_validate(self): self.assertEqual(len(gate.validate()), 3)

    def test_wildcard_actions_and_alternative_grammar_fail(self):
        for action in ('*', 'iam:*', 'ec2:Describe*'):
            doc = self.doc('eks'); doc['Statement'][0]['Action'] = action
            with self.assertRaises(ValueError): gate.validate_shape(doc)
        for key in ('Principal', 'NotAction', 'NotResource'):
            doc = self.doc('app'); doc['Statement'][0][key] = '*'
            with self.assertRaises(ValueError): gate.validate_shape(doc)

    def test_managed_policy_size_ceiling(self):
        doc = self.doc('eks'); doc['Statement'][0]['Sid'] = 'a' * 6144
        with self.assertRaises(ValueError): gate.validate_shape(doc)

    def test_no_operator_or_key_recovery_permissions(self):
        for kind in ('eks', 'app', 'management'):
            for action in ('iam:CreateRole', 'iam:PassRole', 'iam:CreatePolicy', 'kms:CancelKeyDeletion',
                           'secretsmanager:RestoreSecret', 'sts:AssumeRole'):
                self.assertFalse(self.allowed(kind, action, '*'))

    def test_only_elb_service_linked_role_can_be_created(self):
        arn = f'arn:aws:iam::{gate.ACCOUNT}:role/aws-service-role/elasticloadbalancing.amazonaws.com/AWSServiceRoleForElasticLoadBalancing'
        self.assertTrue(self.allowed('eks', 'iam:CreateServiceLinkedRole', arn,
                                    **{'iam:AWSServiceName': 'elasticloadbalancing.amazonaws.com'}))
        self.assertFalse(self.allowed('eks', 'iam:CreateServiceLinkedRole', arn,
                                     **{'iam:AWSServiceName': 'eks.amazonaws.com'}))
        self.assertFalse(self.allowed('eks', 'iam:CreateServiceLinkedRole', 'arn:aws:iam::999999999999:role/unrelated',
                                     **{'iam:AWSServiceName': 'elasticloadbalancing.amazonaws.com'}))

    def test_app_queue_account_region_and_event_bus_are_bounded(self):
        queue = f'arn:aws:sqs:us-east-1:{gate.ACCOUNT}:cloud-native-platform-dev-shipment-events-queue'
        context = {'aws:RequestedRegion': 'us-east-1'}
        self.assertTrue(self.allowed('app', 'sqs:ReceiveMessage', queue, **context))
        self.assertFalse(self.allowed('app', 'sqs:ReceiveMessage', queue+'-other', **context))
        self.assertFalse(self.allowed('app', 'sqs:ReceiveMessage', queue, **{'aws:RequestedRegion': 'us-west-2'}))
        self.assertFalse(self.allowed('app', 'sqs:PurgeQueue', queue, **context))
        bus = f'arn:aws:events:us-east-1:{gate.ACCOUNT}:event-bus/cloud-native-platform-dev-bus'
        self.assertTrue(self.allowed('app', 'events:PutEvents', bus, **context))
        self.assertFalse(self.allowed('app', 'events:PutEvents', bus+'-other', **context))

    def test_kms_decrypt_requires_module_tag_and_region(self):
        key = f'arn:aws:kms:us-east-1:{gate.ACCOUNT}:key/new-runtime-key'
        good = {'aws:RequestedRegion': 'us-east-1', 'aws:ResourceTag/Module': 'event-encryption'}
        self.assertTrue(self.allowed('app', 'kms:Decrypt', key, **good))
        self.assertFalse(self.allowed('app', 'kms:Decrypt', key, **{'aws:RequestedRegion': 'us-east-1'}))
        self.assertFalse(self.allowed('app', 'kms:Decrypt', key.replace(gate.ACCOUNT, '999999999999'), **good))
        self.assertFalse(self.allowed('app', 'kms:GenerateDataKey', key, **good))

    def test_eso_current_paths_pass_legacy_and_unrelated_secrets_fail(self):
        prefix = f'arn:aws:secretsmanager:us-east-1:{gate.ACCOUNT}:secret:'
        context = {'aws:RequestedRegion': 'us-east-1'}
        for name in ('cloud-native-platform/dev/runtime/auth-runtime-db-Ab1234',
                     'cloud-native-platform/dev/api-gateway-authorizer/auth-service-jwt-secret-Ab1234',
                     'cloud-native-platform/dev/api-gateway-authorizer/platform-trusted-proxy-secret-Ab1234'):
            self.assertTrue(self.allowed('app', 'secretsmanager:GetSecretValue', prefix+name, **context))
        for name in ('cloud-native-platform-dev-auth-service-jwt-secret-Ab1234', 'other-project/password-Ab1234'):
            self.assertFalse(self.allowed('app', 'secretsmanager:GetSecretValue', prefix+name, **context))

    def test_management_artifacts_receipts_require_correct_prefix_and_principal(self):
        bucket = f'arn:aws:s3:::cloud-native-platform-{gate.ACCOUNT}-dev-us-east-1-artifacts'
        self.assertTrue(self.allowed('management', 's3:GetObject', bucket+'/cluster-addons/dev/config.json'))
        self.assertFalse(self.allowed('management', 's3:GetObject', bucket+'/unrelated/config.json'))
        receipt = bucket+'/deployment-receipts/dev/run.json'
        self.assertFalse(self.allowed('management', 's3:PutObject', receipt))
        self.assertTrue(self.allowed('management', 's3:PutObject', receipt,
            **{'aws:PrincipalArn': f'arn:aws:iam::{gate.ACCOUNT}:role/cloud-native-platform-dev-management-role'}))

    def test_unknown_condition_operator_is_not_silently_accepted(self):
        doc = self.doc('app'); doc['Statement'][0]['Condition'] = {'Unsupported': {'key': 'value'}}
        with self.assertRaises(ValueError): gate.boundary_allows(doc, 'sqs:ReceiveMessage', '*', {})

    def test_modified_documents_and_wrong_identity_manifest_fail(self):
        for mutation in ('policy', 'account', 'target', 'tags'):
            with tempfile.TemporaryDirectory() as folder:
                directory = Path(folder)
                for source in gate.DIRECTORY.glob('*.json'): (directory/source.name).write_bytes(source.read_bytes())
                manifest = json.loads((directory/'manifest.json').read_text())
                if mutation == 'policy':
                    path = directory/manifest['policies'][0]['document']
                    doc = json.loads(path.read_text()); doc['Statement'][0]['Action'].append('iam:DeleteUser')
                    path.write_text(json.dumps(doc))
                elif mutation == 'account': manifest['accountId'] = '999999999999'
                elif mutation == 'target': manifest['policies'][0]['path'] = '/unreviewed/'
                else: manifest['policies'][0]['tags']['Project'] = 'unrelated'
                (directory/'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises(ValueError): gate.validate(directory)


if __name__ == '__main__': unittest.main()
