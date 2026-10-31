"""Portable, AWS-free release candidate validation orchestrator.
Exit0=all selected checks pass; exit1=failure; exit2=external prerequisites missing.
--allow-external-skips is local-only and preserves explicit skipped status in JSON.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
SOLUTIONS=['microservices/auth-service/AuthService.sln','microservices/shipment-service/ShipmentService.sln','microservices/tracking-service/TrackingService.sln','tests/EventReliability.Tests/EventReliability.Tests.csproj']
MODULES=sorted(p.name for p in (ROOT/'infra/modules').iterdir() if (p/'versions.tf').exists())


def inventory():
    return {'dotnet':SOLUTIONS,'node':['lambdas/api-gateway-jwt-authorizer/src/index.test.mjs'],
            'python':[p.relative_to(ROOT).as_posix() for p in (ROOT/'scripts/validation').glob('test_*.py')],
            'validators':[f'validate_r{i}.py' for i in range(1,8)],'terraform':MODULES,
            'terraform_tests':[p.relative_to(ROOT).as_posix() for p in (ROOT/'infra/modules').rglob('*.tftest.hcl')],
            'helm':['cluster-addons','platform-services','platform-bootstrap','platform-secret-sync']}


def result_exit_code(failed,external,mode,allow_external_skips):
    return 1 if failed else 2 if external and (mode=='ci' or not allow_external_skips) else 0


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=['local','ci'],default='local');p.add_argument('--allow-external-skips',action='store_true');p.add_argument('--inventory',action='store_true')
    a=p.parse_args()
    if a.inventory: print(json.dumps(inventory(),indent=2));return
    if a.mode=='ci' and a.allow_external_skips:p.error('CI cannot allow external skips')
    result_dir=ROOT/'.validation-results';result_dir.mkdir(exist_ok=True)
    results=[]
    def run(name,args,cwd=ROOT):
        print('RUN '+name,flush=True)
        with (result_dir/(re.sub('[^a-zA-Z0-9_-]','_',name)+'.log')).open('w',encoding='utf-8') as log:
            try:r=subprocess.run(args,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,timeout=900);status='PASS' if r.returncode==0 else 'FAIL'
            except (OSError,subprocess.TimeoutExpired):status='FAIL'
        results.append({'check':name,'status':status});print(status+' '+name,flush=True);return status=='PASS'
    tools=['dotnet','node','helm','terraform','terragrunt','actionlint','shellcheck']
    missing=[t for t in tools if not shutil.which(t)]
    if missing:raise SystemExit('Missing REQUIRED tools: '+', '.join(missing))
    external=[v for v in ('R3_POSTGRES_TEST_DSN','R5_POSTGRES_DSN') if not os.environ.get(v)]
    for name in external:results.append({'check':name,'status':'SKIPPED_EXTERNAL_PREREQUISITE'})
    run('helm-dependencies',[sys.executable,'scripts/validation/helm_dependencies.py'])
    for i,solution in enumerate(SOLUTIONS):
        run(f'dotnet-{i}-restore',['dotnet','restore',solution,'--locked-mode'])
        run(f'dotnet-{i}-build',['dotnet','build',solution,'--configuration','Release','--no-restore'])
        trx=result_dir/f'dotnet-{i}.trx'
        if run(f'dotnet-{i}-tests',['dotnet','test',solution,'--configuration','Release','--no-build','--logger',f'trx;LogFileName={trx}']):
            counts=ET.parse(trx).find('.//{*}Counters').attrib;results[-1]['counts']=counts
            if int(counts['total'])==0 or (int(counts.get('notExecuted',0)) and (i!=3 or 'R5_POSTGRES_DSN' not in external)):results[-1]['status']='FAIL'
    run('node-authorizer',['node','--test','lambdas/api-gateway-jwt-authorizer/src/index.test.mjs'])
    run('python-tests',[sys.executable,'-B','-m','unittest','discover','-s','scripts/validation','-p','test_*.py'])
    if 'R3_POSTGRES_TEST_DSN' not in external:run('postgres-r3-required',[sys.executable,'scripts/validation/postgres_gate.py','r3'])
    for i in range(1,8):run(f'validator-r{i}',[sys.executable,f'scripts/validation/validate_r{i}.py'])
    run('secret-scan',[sys.executable,'scripts/validation/secret_scan.py'])
    for chart in ('cluster-addons','platform-services'):
        args=['helm','lint',f'k8s/charts/{chart}']
        if chart=='platform-services':args+=['-f','k8s/environments/dev/platform-services.values.yaml','-f','scripts/validation/fixtures/helm-infra.values.yaml']
        run('helm-lint-'+chart,args)
    run('terraform-format',['terraform','fmt','-check','-recursive'])
    run('terragrunt-format',['terragrunt','hcl','fmt','--check'])
    run('workflow-lint',['actionlint','-pyflakes='])
    provider=re.search(r'contents\s*=\s*<<EOF\n(.*?)\nEOF',(ROOT/'infra/live/root.hcl').read_text(),re.S)[1]
    live_modules={re.search(r'source\s*=\s*"[^"]*/modules/+([^"/]+)"',s.read_text())[1] for s in (ROOT/'infra/live/dev').glob('*/terragrunt.hcl')}
    with tempfile.TemporaryDirectory(prefix='eks-rc-') as directory:
        shutil.copytree(ROOT/'infra/modules',Path(directory)/'modules',ignore=shutil.ignore_patterns('.terraform','__pycache__','*.tfstate*'))
        for module in MODULES:
            target=Path(directory)/'modules'/module
            if module in live_modules:(target/'provider.tf').write_text(provider)
            if run('terraform-init-'+module,['terraform','init','-backend=false','-input=false','-lockfile=readonly'],target):
                run('terraform-validate-'+module,['terraform','validate'],target)
                if list((target/'tests').glob('*.tftest.hcl')):run('terraform-test-'+module,['terraform','test'],target)
    run('diff-check',['git','diff','--check'])
    failed=any(r['status']=='FAIL' for r in results)
    status='FAIL' if failed else 'LOCAL_ONLY_EXTERNAL_PREREQUISITES_SKIPPED' if external else 'PASS'
    report={'mode':a.mode,'status':status,'inventory':inventory(),'results':results,'awsRuntimeCertification':'NOT_PERFORMED'}
    (result_dir/'release-candidate.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':status,'report':str(result_dir/'release-candidate.json')},indent=2))
    raise SystemExit(result_exit_code(failed,external,a.mode,a.allow_external_skips))

if __name__=='__main__':main()
