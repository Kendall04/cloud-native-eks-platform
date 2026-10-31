"""Fail-closed R4 source policy checks. No cloud calls."""
import copy
from pathlib import Path
import re
import sys
import yaml
import hcl2
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/cd'))
from common import require


def snapshot():
    return {name:(ROOT/path).read_text() for name,path in {
        'iam':'infra/modules/private-cd/main.tf',
        'host':'infra/modules/management-host/main.tf',
        'bootstrap':'infra/modules/management-host/user_data.sh.tftpl',
        'build':'.github/workflows/build-sha-images.yml',
        'release':'.github/workflows/create-release.yml',
        'deploy':'.github/workflows/deploy-platform.yml',
        'validate':'.github/workflows/validate.yml',
    }.items()}


def validate(data):
    chart=ROOT/'k8s/charts/platform-services'
    hashes={'platform-services/'+p.relative_to(chart).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in (chart/'templates').rglob('*') if p.is_file()}
    approved=json.loads((ROOT/'infra/modules/management-host/deployer/chart-template-hashes.json').read_text())
    require(hashes==approved,'Chart logic changes require an explicit platform deployer contract review')
    hcl2.loads(data['iam']); hcl2.loads(data['host'])
    iam=data['iam']
    require('StringEquals' in iam and 'sts.amazonaws.com' in iam,'OIDC audience restriction missing')
    require('repo:${var.github_repository}:environment:dev' in iam,'Deploy must trust environment subject')
    require('repo:${var.github_repository}:ref:refs/heads/main' in iam and 'repo:${var.github_repository}:ref:refs/heads/develop' in iam,'Publisher branch subjects missing')
    require(not re.search(r'repo:[^"\n]*\*',iam),'Wildcard OIDC subject forbidden')
    require('"s3:if-none-match" = "*"' in iam,'Conditional publication required')
    require(not any(x in iam for x in ('AWS-RunShellScript','"Commands"','"GitRef"','"s3:Delete','"iam:*"','"ssm:*"','"ecr:*"','"secretsmanager:')),'Unsafe IAM/SSM contract')
    require('interpolationType = "ENV_VAR"' in iam and 'allowedPattern = pattern' in iam,'SSM input interpolation unsafe')
    orchestrator=iam.split('resource "aws_iam_role_policy" "orchestrator"')[1].split('resource "aws_iam_role_policy"')[0]
    publisher=iam.split('resource "aws_iam_role_policy" "publisher"')[1].split('resource "aws_ssm_document"')[0]
    require(not any(x in publisher for x in ('ssm:','eks:','iam:')),'Publisher cannot deploy')
    management=iam.split('resource "aws_iam_role_policy" "management_artifacts"')[1]
    require(not any(x in management for x in ('iam:','secretsmanager:','ecr:')),'Management permissions exceed application CD')
    require(not any(x in orchestrator for x in ('ecr:', 's3:Put', 'eks:', 'ssm:StartSession')),'Orchestrator must only read artifact/submit fixed command')
    require('aws_ssm_document.deploy.arn' in orchestrator and ':instance/${var.management_instance_id}' in orchestrator,'SSM resource restrictions missing')
    require('platform:deployer:apps' in data['host'] and 'AmazonEKSClusterAdminPolicy' not in data['host'],'Namespace EKS identity missing')
    require('chown -R root:root /opt/platform-deployer' in data['bootstrap'] and 'sha256sum --check' in data['bootstrap'],'Mutable/unverified executor installation')
    workflows={key:yaml.load(data[key],Loader=yaml.BaseLoader) for key in ('build','release','deploy','validate')}
    # These are source admission guards, not a claim about GitHub/IAM settings.
    # A removed job/ref gate must fail locally before a future OIDC workflow runs.
    expected_jobs={'build':{'validate','build'},'release':{'release'},'deploy':{'deploy'}}
    expected_permissions={
        'build':{'contents':'read','id-token':'write'},
        'release':{'contents':'read','actions':'read','id-token':'write'},
        'deploy':{'contents':'read','id-token':'write'},
    }
    for key in ('build','release','deploy'):
        workflow=workflows[key]
        require(set(workflow.get('on',{}))=={'workflow_dispatch'},'AWS delivery must remain manual-only')
        require(set(workflow.get('jobs',{}))==expected_jobs[key],'Unreviewed AWS delivery job')
        require(workflow.get('permissions')=={'contents':'read'},'AWS workflow permissions broadened')
        name='build' if key=='build' else ('release' if key=='release' else 'deploy')
        job=workflow['jobs'][name]
        ref_gate=("github.ref == 'refs/heads/main' || github.ref == 'refs/heads/develop'"
                  if key=='build' else "github.ref == 'refs/heads/main'")
        require(job.get('if')==ref_gate,'AWS delivery ref gate missing before OIDC')
        require(job.get('permissions')==expected_permissions[key],'AWS delivery job permissions changed')
    require(workflows['build']['jobs']['validate'].get('uses')=='./.github/workflows/validate.yml',
            'Build must reuse the reviewed local validation workflow')
    require('workflow_call' in workflows['validate']['on'],'Validation must be reusable')
    plan_tests=next(s for s in workflows['validate']['jobs']['r2-terraform-contracts']['steps'] if s.get('run')=='terraform test')
    require(plan_tests['working-directory']=='infra/modules/${{ matrix.module }}','Plan tests must run against their initialized matrix module')
    build=workflows['build']['jobs']['build']
    require(build.get('needs')=='validate','Images can bypass validation')
    deploy=workflows['deploy']['jobs']['deploy']
    require(deploy.get('environment')=='dev','Deployment must use GitHub environment')
    require(workflows['deploy']['concurrency']=={'group':'deploy-dev','cancel-in-progress':'false'},'Unsafe deployment concurrency')
    require(set(workflows['deploy']['on']['workflow_dispatch']['inputs'])=={'artifact_key','artifact_version_id','artifact_sha256','deployment_id','expected_previous_revision'},'Unexpected deployment inputs')
    require(not any(x in data['deploy'] for x in ('kubectl','helm upgrade','docker build','git_ref','secrets.','AWS_GITHUB_ACTIONS_ROLE_ARN')),'Runner cannot deploy directly or use legacy keys')
    for key in ('build','release','deploy'):
        for job in workflows[key]['jobs'].values():
            for step in job.get('steps',[]):
                if 'uses' in step: require(re.fullmatch(r'[\w./-]+@[0-9a-f]{40}',step['uses']),'Unpinned sensitive action')
    require('role-to-assume: ${{ vars.ARTIFACT_PUBLISHER_ROLE_ARN }}' in data['build'] and 'role-to-assume: ${{ vars.DEPLOYMENT_ORCHESTRATOR_ROLE_ARN }}' in data['deploy'],'Federated roles not separated')


if __name__=='__main__':
    validate(snapshot()); print('R4 static contracts: PASS')
