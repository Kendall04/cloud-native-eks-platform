"""R3 invariants over parsed HCL and rendered Helm. No AWS access."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import yaml
import hcl2
from validate_r1 import ROOT, render, require
from validate_r2 import blocks

NAMES = [f'{s}-{p}-db' for s in ('auth','shipment','tracking') for p in ('runtime','migration')] + ['internal-trust','bootstrap-admin','auth-jwt','gateway-trust']
CA_SHA256 = 'e5bb2084ccf45087bda1c9bffdea0eb15ee67f0b91646106e466714f9de3c7e3'

def validate_values(values):
    for service in values['services'].values():
        for key,value in service.get('env',{}).items():
            require(not re.search(r'password|secret|connectionstrings',key,re.I), 'Sensitive material must be a Secret reference, never config')
        for item in service.get('secretEnv',[]):
            require(set(item)=={'name','secretName','secretKey'}, 'Only Kubernetes references allowed')

def platform_render(helm):
    fixture={'region':'us-east-1','workloadRoles':{s:'arn:aws:iam::999988887777:role/test-'+s for s in ('shipment','tracking')},'secretArns':{n:'arn:aws:secretsmanager:us-east-1:999988887777:secret:fixture/'+n for n in NAMES}}
    fixture['network'] = {'privateSubnetCidrs': ['10.0.128.0/20','10.0.144.0/20','10.0.160.0/20']}
    documents=[]
    with tempfile.TemporaryDirectory() as temp:
        values=Path(temp)/'values.yaml'; values.write_text(yaml.safe_dump(fixture))
        for chart in ('platform-bootstrap','platform-secret-sync'):
            path=ROOT/'k8s/charts'/chart
            subprocess.run([helm,'lint',str(path),'-f',str(values)],check=True,capture_output=True)
            result=subprocess.run([helm,'template',chart,str(path),'-n','apps','-f',str(values)],check=True,capture_output=True,text=True)
            documents.extend(d for d in yaml.safe_load_all(result.stdout) if d)
    return documents,fixture

def validate_platform(documents,fixture):
    role=next(d for d in documents if d['kind']=='Role')
    require(role['metadata']['namespace']=='apps', 'RBAC must be namespace scoped')
    forbidden={'*','serviceaccounts','serviceaccounts/token','pods/exec','namespaces','nodes','clusterroles','clusterrolebindings','roles','rolebindings','secretstores'}
    for rule in role['rules']:
        require(not forbidden.intersection(rule['resources']) and '*' not in rule['verbs'] and '*' not in rule['apiGroups'], 'Deployer privileges exceed application boundary')
        if 'externalsecrets' in rule['resources']: require(set(rule['verbs']) <= {'get','list','watch'}, 'Deployer may only observe secret readiness')
    binding=next(d for d in documents if d['kind']=='RoleBinding')
    require(binding['subjects'][0]['name']=='platform:deployer:apps','Wrong deployer group')
    stores=[d for d in documents if d['kind']=='SecretStore']
    require(len(stores)==1 and stores[0]['metadata']['namespace']=='apps','Namespaced SecretStore required')
    require(stores[0]['spec']['provider']['aws']=={'service':'SecretsManager','region':fixture['region']},'Store must use controller IRSA')
    external=[d for d in documents if d['kind']=='ExternalSecret']
    require({d['metadata']['name'] for d in external}==set(NAMES),'Incomplete sync inventory')
    for d in external:
        n=d['metadata']['name']; spec=d['spec']
        ref=spec['dataFrom'][0]['extract']['key'] if 'dataFrom' in spec else spec['data'][0]['remoteRef']['key']
        require(ref==fixture['secretArns'][n], 'ExternalSecret source mismatch')
        require(spec['target']['name']==n and spec['secretStoreRef']['kind']=='SecretStore','Wrong secret boundary')
    require(not any(d['kind'] in ('Secret','ClusterSecretStore') for d in documents),'No values or global store in Helm')

def validate_apps(documents):
    require(not any(d['kind'] in ('Namespace','ServiceAccount','Role','RoleBinding','ExternalSecret','SecretStore') for d in documents if d),'Platform resources leaked into app release')
    for d in documents:
        if not d or d['kind'] not in ('Deployment','Job'): continue
        pod=d['spec']['template']['spec']; container=pod['containers'][0]
        service=d['metadata']['name'].split('-')[0]
        refs={v['name']:v['valueFrom']['secretKeyRef']['name'] for v in container.get('env',[]) if 'valueFrom' in v}
        purpose='migration' if d['kind']=='Job' else 'runtime'
        require(refs.get('Database__Password')==f'{service}-{purpose}-db','Runtime/migrator credentials crossed')
        require('ConnectionStrings__Postgres' not in refs,'Legacy master connection reference')
        require(any(v.get('configMap',{}).get('name')=='platform-db-ca' for v in pod['volumes']),'CA mount missing')
        if purpose=='migration': require(pod['serviceAccountName']=='platform-migrator' and not pod['automountServiceAccountToken'],'Migration must not inherit AWS identity')
        if service=='auth' and purpose=='runtime': require('BootstrapAdmin__Password' not in refs,'Seed credential leaked into runtime')

def validate_iac():
    with (ROOT/'infra/modules/management-host/main.tf').open() as f: management=blocks(hcl2.load(f),'resource')
    access=management['aws_eks_access_entry','management']
    require(access['type']=='STANDARD' and access['kubernetes_groups']==['platform:deployer:apps'],'Wrong EKS identity mapping')
    require(not any(k[0]=='aws_eks_access_policy_association' for k in management),'Broad EKS managed access policy remains')
    with (ROOT/'infra/modules/runtime-secrets/main.tf').open() as f: module=hcl2.load(f)
    resources=blocks(module,'resource')
    require(not any(k[0]=='aws_secretsmanager_secret_version' for k in resources),'Secret values must stay outside Terraform')
    policy=resources['aws_iam_role_policy','eso_read']['policy']
    require('GetSecretValue' in policy and 'DescribeSecret' in policy and 'secretsmanager:*' not in policy and 'master' not in policy,'ESO permissions too broad')
    trust=resources['aws_iam_role','eso']['assume_role_policy']
    require('system:serviceaccount:kube-system:external-secrets' in trust and 'sts.amazonaws.com' in trust,'IRSA trust not constrained')
    shared=(ROOT/'infra/live/dev/runtime-secrets/terragrunt.hcl').read_text()
    require('dependency.shared.outputs.secret_arns["auth-service-jwt-secret"]' in shared and 'dependency.shared.outputs.secret_arns["platform-trusted-proxy-secret"]' in shared,'Authorizer and ESO sources drifted')

def main():
    helm=os.environ.get('HELM_BIN','helm')
    for env in ('dev','prod'):
        path=ROOT/f'k8s/environments/{env}/platform-services.values.yaml'
        validate_values(yaml.safe_load(path.read_text()))
        validate_apps(render(helm,path))
    documents,fixture=platform_render(helm); validate_platform(documents,fixture)
    validate_iac()
    require(hashlib.sha256((ROOT/'k8s/charts/platform-bootstrap/files/rds-global-bundle.pem').read_bytes()).hexdigest()==CA_SHA256,'CA changed without reviewed checksum update')
    print('R3 secret, identity, ownership, RBAC, CA and Helm contracts: PASS')

def validate_addons(path):
    docs=[d for d in yaml.safe_load_all(Path(path).read_text(encoding='utf-8-sig')) if d]
    deployment=next(d for d in docs if d['kind']=='Deployment' and d['metadata']['name']=='external-secrets')
    args=deployment['spec']['template']['spec']['containers'][0]['args']
    require(any('apps' in a for a in args),'ESO is not scoped to apps')
    require(deployment['spec']['template']['spec']['serviceAccountName']=='external-secrets','Unexpected ESO identity')
    for d in docs:
        if d['kind'] not in ('Role','ClusterRole') or not d['metadata']['name'].startswith('external-secrets'): continue
        for rule in d.get('rules',[]):
            require('serviceaccounts/token' not in rule['resources'],'ESO does not need to mint other service account tokens')
            if 'secrets' in rule['resources']:
                require(d['kind']=='Role' and (d['metadata']['namespace']=='apps' or (d['metadata']['namespace']=='kube-system' and rule.get('resourceNames')==['external-secrets-webhook'] and set(rule['verbs']) <= {'get','update','patch'})), 'ESO secret access exceeds namespace boundary')
    print('Rendered ESO namespace and token RBAC: PASS')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--addons')
    args=parser.parse_args()
    if args.addons: validate_addons(args.addons)
    else: main()
