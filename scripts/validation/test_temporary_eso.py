"""Approved temporary ESO regressions. Offline; IAM source stays on Windows."""
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

import hcl2
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bootstrap'))
from environment import retained_secret_arns, temporary_eso_role, validate_contract
from bootstrap import phase, CORE
from test_r2 import contract_fixture
from validate_r2 import snapshot, decode_policy

ROOT=Path(__file__).resolve().parents[2]
SETTINGS={'project_name':'cloud-native-platform','environment':'dev','region':'us-east-1'}
ACCOUNT='341936017254'
NAME='cloud-native-platform-dev-external-secrets-cert-irsa'
ARN=f'arn:aws:iam::{ACCOUNT}:role/{NAME}'

def retained():
    evidence=json.loads((ROOT/'docs/evidence/eks-readonly-preflight-20261021.json').read_text())
    arns={r['nameMetadata'].rsplit('/',1)[-1]:r['arn'] for r in evidence['retentions']['existingManagedObjects'] if r['type']=='aws_secretsmanager_secret'}
    arns['auth-jwt']=arns.pop('auth-service-jwt-secret')
    arns['gateway-trust']=arns.pop('platform-trusted-proxy-secret')
    return {'secret_arns':arns,'eso_role_arn':f'arn:aws:iam::{ACCOUNT}:role/cloud-native-platform-dev-external-secrets'}

class TemporaryEso(unittest.TestCase):
    def test_exact_owner_output_is_selected(self):
        self.assertEqual(ARN,temporary_eso_role(SETTINGS,ACCOUNT,retained(),{'role_arns':{NAME:ARN}}))

    def test_missing_output_never_falls_back_to_original(self):
        for iam in ({},{'role_arns':{}},{'role_arns':{NAME:retained()['eso_role_arn']}}):
            with self.subTest(iam=iam),self.assertRaises(ValueError):
                temporary_eso_role(SETTINGS,ACCOUNT,retained(),iam)

    def test_wrong_role_or_account_rejected(self):
        for value in (ARN+'-other',ARN.replace(ACCOUNT,'999988887777'),ARN.replace(':role/',':user/')):
            with self.subTest(value=value),self.assertRaises(ValueError):
                temporary_eso_role(SETTINGS,ACCOUNT,retained(),{'role_arns':{NAME:value}})

    def test_retained_missing_extra_duplicate_or_foreign_secret_rejected(self):
        changes=[]
        d=retained();d['secret_arns'].pop('bootstrap-admin');changes.append(d)
        d=retained();d['secret_arns']['master']=f'arn:aws:secretsmanager:us-east-1:{ACCOUNT}:secret:rds-master-ABC123';changes.append(d)
        d=retained();d['secret_arns']['bootstrap-admin']=d['secret_arns']['internal-trust'];changes.append(d)
        d=retained();d['secret_arns']['bootstrap-admin']=d['secret_arns']['bootstrap-admin'].replace(ACCOUNT,'999988887777');changes.append(d)
        d=retained();d['secret_arns']['bootstrap-admin']+='*';changes.append(d)
        for d in changes:
            with self.subTest(d=d),self.assertRaises(ValueError):retained_secret_arns(SETTINGS,ACCOUNT,d)

    def test_wrong_retained_role_rejected(self):
        d=retained();d['eso_role_arn']=ARN
        with self.assertRaises(ValueError):retained_secret_arns(SETTINGS,ACCOUNT,d)

    def test_generated_contract_uses_temporary_owner_output(self):
        c=contract_fixture();validate_contract(c,'dev')
        self.assertTrue(c['esoRoleArn'].endswith('-external-secrets-cert-irsa'))
        c['esoRoleArn']=c['esoRoleArn'].replace('-cert-irsa','')
        with self.assertRaises(ValueError):validate_contract(c,'dev')

    def test_phase_one_never_applies_retained_owner(self):
        def read(args,*_):return json.dumps({'Account':ACCOUNT})
        settings={**SETTINGS,'nat_mode':'instance','nat_recovery_enabled':True}
        with patch('bootstrap.environment_settings',return_value=settings),patch('bootstrap.command',side_effect=read),patch('bootstrap.output',return_value=retained()) as output,patch('bootstrap.run') as run,patch('bootstrap.generate'):
            phase(1,'dev',None)
        output.assert_called_once_with('runtime-secrets','dev')
        self.assertNotIn('runtime-secrets',CORE)
        self.assertEqual(len(CORE)*2,run.call_count)
        self.assertFalse(any('runtime-secrets' in str(c.args) for c in run.call_args_list))

    def test_retained_state_unavailable_blocks_before_first_mutation(self):
        with patch('bootstrap.environment_settings',return_value=SETTINGS),patch('bootstrap.command',return_value=json.dumps({'Account':ACCOUNT})),patch('bootstrap.output',side_effect=ValueError('unreadable')),patch('bootstrap.run') as run,patch('bootstrap.generate'):
            with self.assertRaises(ValueError):phase(1,'dev',None)
        run.assert_not_called()

    def test_incomplete_retained_coverage_blocks_before_first_mutation(self):
        d=retained();d['secret_arns'].pop('auth-jwt')
        with patch('bootstrap.environment_settings',return_value=SETTINGS),patch('bootstrap.command',return_value=json.dumps({'Account':ACCOUNT})),patch('bootstrap.output',return_value=d),patch('bootstrap.run') as run,patch('bootstrap.generate'):
            with self.assertRaises(ValueError):phase(1,'dev',None)
        run.assert_not_called()

    def test_iam_policy_has_only_ten_retained_reads_and_fresh_trust(self):
        roles=snapshot()['live/iam']['inputs']['roles']
        self.assertEqual(4,len(roles))
        role=roles['${local.project_name}-${local.environment}-external-secrets-cert-irsa']
        self.assertEqual('arn:aws:iam::${get_aws_account_id()}:policy/cnp-cert-app-workload-boundary',role['permissions_boundary'])
        self.assertEqual(3600,role['max_session_duration'])
        self.assertNotIn('managed_policy_arns',role)
        policy=decode_policy(role['inline_policies']['eso-retained-ten-read'])
        self.assertEqual(1,len(policy['Statement']))
        statement=policy['Statement'][0]
        self.assertEqual({'secretsmanager:GetSecretValue','secretsmanager:DescribeSecret'},set(statement['Action']))
        resource=statement['Resource']
        names=re.findall(r'\$\{([a-z-]+)\}',resource)
        self.assertEqual(set(retained()['secret_arns']),set(names));self.assertEqual(10,len(names))
        self.assertIn('dependency.retained_runtime.outputs.secret_arns[name]',resource)
        expression=role['assume_role_policy']
        # hcl2 serializes quoted interpolated object keys with doubled quotes.
        # Check the exact fresh-issuer key before normalizing only those two keys.
        for claim in ('aud','sub'):
            key='\"\"${replace(dependency.eks.outputs.oidc_provider_url, \"https://\", \"\")}:'+claim+'\"\"'
            self.assertEqual(1,expression.count(key))
            expression=expression.replace(key,'\"FRESH:'+claim+'\"')
        trust=decode_policy(expression)['Statement']
        self.assertEqual(1,len(trust));t=trust[0]
        self.assertEqual('sts:AssumeRoleWithWebIdentity',t['Action'])
        self.assertEqual({'Federated':'${dependency.eks.outputs.oidc_provider_arn}'},t['Principal'])
        self.assertEqual({'sts.amazonaws.com','system:serviceaccount:kube-system:external-secrets'},set(t['Condition']['StringEquals'].values()))
        self.assertEqual({'FRESH:aud','FRESH:sub'},set(t['Condition']['StringEquals']))

    def test_new_iam_dependency_keeps_retained_owner_until_temporary_role_is_gone(self):
        live=hcl2.loads((ROOT/'infra/live/dev/iam/terragrunt.hcl').read_text())
        dependencies={name:value for block in live['dependency'] for name,value in block.items()}
        self.assertEqual('../runtime-secrets',dependencies['retained_runtime']['config_path'])

    def test_iam_module_keeps_temporary_and_retained_owners_separate(self):
        module=hcl2.loads((ROOT/'infra/modules/iam/main.tf').read_text())
        resources={k:v for block in module['resource'] for k,v in block.items()}
        self.assertEqual('${var.roles}',resources['aws_iam_role']['this']['for_each'])
        self.assertEqual('${local.inline_policies}',resources['aws_iam_role_policy']['this']['for_each'])
        self.assertNotIn('runtime-secrets',(ROOT/'infra/modules/iam/main.tf').read_text())

if __name__=='__main__':unittest.main()
