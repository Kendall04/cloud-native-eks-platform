"""Closure/integration invariants; R1-R6 retain ownership of detailed contracts."""
import json
from pathlib import Path
import re
import sys
import yaml
ROOT=Path(__file__).resolve().parents[2]


def require(value,message):
    if not value:raise ValueError(message)


def snapshot():
    return {'readme':(ROOT/'README.md').read_text(encoding='utf-8-sig'),
            'ci':(ROOT/'.github/workflows/validate.yml').read_text(),
            'gate':(ROOT/'scripts/validation/postgres_gate.py').read_text(),
            'deploy':(ROOT/'.github/workflows/deploy-platform.yml').read_text(),
            'candidate':json.loads((ROOT/'release/candidate.json').read_text())}


def validate(data):
    require('Lifecycle completed' in data['readme'] and 'final teardown' in data['readme'], 'README must describe the completed lifecycle')
    require('lab is offline' in data['readme'] and 'delivery workflows are disabled' in data['readme'], 'README must distinguish historical verification from current runtime')
    require(not re.search(r'(?im)^.*(?:AWS runtime verified|fully secure|production-ready|zero downtime guarantee).*$',data['readme']),'Unproven README claim')
    require(data['candidate']['runtimeCertified'] is False,'Construction tag cannot imply runtime certification')
    require(data['candidate']['candidate']=='portfolio-v2-rc1' and data['candidate']['tagCreated'] is True and data['candidate']['constructionFrozen'] is True,'Audited construction freeze metadata missing')
    require(data['candidate']['auditedImplementationCommit']=='cc4d298e4557a6741d0732e978df28d40e2a7af6','Audited implementation baseline drift')
    for i in range(1,7):require((ROOT/f'scripts/validation/validate_r{i}.py').exists(),'Missing earlier contract validator')
    for path in ('docs/results.md', 'docs/evidence/lifecycle-summary.json', 'docs/architecture/current-platform.md', 'docs/architecture/infrastructure.md', 'docs/operations/deployment.md', 'docs/operations/private-cd.md', 'docs/operations/lab-cleanup.md', 'docs/operations/teardown.md', 'docs/development.md'):
        require((ROOT/path).exists(),'Missing closure documentation '+path)
    for i in range(1,5):require(any((ROOT/'docs/adr').glob(f'{i:03d}-*.md')),'Missing ADR')
    require(json.loads((ROOT/'global.json').read_text())['sdk']=={'version':'10.0.403','rollForward':'disable','allowPrerelease':False},'SDK must match reviewed .NET10 pin')
    ci=yaml.safe_load(data['ci'])['jobs']
    for job in ('postgres-r3-permissions','postgres-r5-reliability'):
        require(ci[job]['services']['postgres']['image']=='postgres:15.18','Real PostgreSQL service required')
        require(not ci[job].get('continue-on-error',False),'Required PostgreSQL job cannot be optional')
    r3=json.dumps(ci['postgres-r3-permissions']['steps']);r5=json.dumps(ci['postgres-r5-reliability']['steps'])
    require('R3_POSTGRES_TEST_DSN' in r3 and 'postgres_gate.py r3' in r3,'R3 must reject skip-green')
    require('R5_POSTGRES_DSN' in r5 and 'postgres_gate.py trx' in r5 and 'dotnet test' in r5,'R5 must reject skip-green')
    require('notExecuted' in data['gate'] and 'result.skipped' in data['gate'],'Skip detection missing')
    require('format-and-workflow-lint' in ci and 'terraform fmt -check -recursive' in data['ci'] and 'terragrunt hcl fmt --check' in data['ci'] and 'actionlint' in data['ci'],'Required lint gates missing')
    for path in (ROOT/'.github/workflows').glob('*.yml'):
        workflow=yaml.safe_load(path.read_text())
        for job in workflow.get('jobs',{}).values():
            for step in job.get('steps',[]):
                if 'uses' in step:require(re.fullmatch(r'[\w./-]+@[0-9a-f]{40}',step['uses']),'Action SHA pin missing')
    require(not any(s in data['deploy'] for s in ('kubectl','helm upgrade','AWS_ACCESS_KEY_ID','aws-access-key-id')),'Old direct/private-key deployment path')
    for stack in (ROOT/'infra/live/dev').glob('*/terragrunt.hcl'):
        match=re.search(r'source\s*=\s*"[^"]*/modules/+([^"/]+)"',stack.read_text())
        require(match,'Unrecognized local module source')
        module=ROOT/'infra/modules'/match[1]
        content='\n'.join(p.read_text() for p in module.glob('*.tf'))
        for v in ('region','project_name','environment','tags'):require(re.search(r'variable\s+"'+v+'"',content),'Generated Terragrunt provider references missing '+match[1]+'.'+v)
        require((stack.parent/'.terraform.lock.hcl').read_bytes()==(module/'.terraform.lock.hcl').read_bytes(),'Stack/module provider locks drift')
    modules={p.name for p in (ROOT/'infra/modules').iterdir() if (p/'versions.tf').exists()}
    require(set(ci['r2-terraform-contracts']['strategy']['matrix']['module'])==modules,'CI module inventory incomplete')
    from validate_docs import validate as validate_documentation
    validate_documentation()
    require('require_clean_scan(ecr' in (ROOT/'scripts/cd/publish.py').read_text(),'ECR scan-on-push lacks promotion gate')
    print('R7 source integration/CI/docs: PASS (historical runtime evidence is separate)')

if __name__=='__main__':validate(snapshot())
