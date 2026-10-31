"""Untrusted artifact validation shared by publisher and fixed host executor."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import yaml
SYNTHETIC_VERSION='1.5.0'

# Preserve the legacy manifest capability; the separate synthetic schema names
# SYNTHETIC_VERSION explicitly and cannot be accepted by an installed old host.
VERSION='1.4.0'
HELM='v4.2.2'
SERVICES=('auth','shipment','tracking')
FILES={'manifest.json','platform-services.tgz','values.resolved.yaml','environment.contract.json','checksums.sha256'}
MAX_BYTES=20*1024*1024

# Installed platform policy, not supplied by an application bundle.
ALB_ANNOTATIONS={
    'alb.ingress.kubernetes.io/scheme':'internal',
    'alb.ingress.kubernetes.io/target-type':'ip',
    'alb.ingress.kubernetes.io/backend-protocol':'HTTP',
    'alb.ingress.kubernetes.io/listen-ports':'[{"HTTP":80}]',
    'alb.ingress.kubernetes.io/healthcheck-path':'/health/ready',
    'alb.ingress.kubernetes.io/healthcheck-protocol':'HTTP',
    'alb.ingress.kubernetes.io/healthcheck-port':'traffic-port',
    'alb.ingress.kubernetes.io/success-codes':'200',
}

def declarative(value, depth=0):
    require(depth <= 50,'Values nesting exceeds contract')
    if type(value) is dict:
        for key,item in value.items():
            require(type(key) is str,'Values keys must be strings')
            declarative(key,depth+1); declarative(item,depth+1)
    elif type(value) is list:
        for item in value: declarative(item,depth+1)
    elif type(value) is str:
        require('{{' not in value,'Values must be declarative, not Helm expressions')
    else:
        require(value is None or type(value) in (bool,int,float),'Unsupported values type')
        if type(value) is float:
            import math
            require(math.isfinite(value),'Non-finite values forbidden')

def platform_ingress(target):
    alb=target['alb']
    return {**ALB_ANNOTATIONS,'alb.ingress.kubernetes.io/group.name':alb['groupName']}

def validate_values(values,target):
    declarative(values); no_secrets(values)
    require(type(values) is dict,'Values must be an object')
    require(values['namespace']['name']=='apps' and values['namespace']['create'] is False,'Namespace fixed')
    ingress=values['global']['ingress']
    require(set(ingress)=={'enabled','className','frontendSecurityGroupId','discoveryTags','annotations','host','pathType'},'Unexpected Ingress values')
    require(ingress['enabled'] is True and ingress['className']=='alb','Platform Ingress required')
    require(ingress['frontendSecurityGroupId']==target['alb']['frontendSecurityGroupId'],'Platform frontend SG mismatch')
    require(ingress['discoveryTags']==target['alb']['discoveryTags'],'Platform discovery tags mismatch')
    require(ingress['annotations']==platform_ingress(target),'Platform ALB annotations mismatch')
    require(type(ingress['host']) is str and ingress['pathType']=='Prefix','Unsupported application routing')

def normalized_values(data,target):
    values=yaml.safe_load(data)
    validate_values(values,target)
    return (json.dumps(values,sort_keys=True,ensure_ascii=True,allow_nan=False)+'\n').encode()

def require(condition,message):
    if not condition: raise ValueError(message)

def target_environment(target):
    if 'dataScope' in target:
        from synthetic_contract import target_environment as validate_target
        return validate_target(target)
    require(target['environment']=='dev','Synthetic host capability is not installed')
    return 'dev'

def sha(data): return hashlib.sha256(data).hexdigest()

def schema_check(value,spec):
    types={'object':dict,'array':list,'string':str,'integer':int}
    if 'type' in spec: require(type(value) is types[spec['type']],'Invalid manifest field type')
    if 'const' in spec: require(value==spec['const'],'Invalid manifest constant')
    if 'enum' in spec: require(value in spec['enum'],'Invalid manifest enum')
    if 'pattern' in spec: require(re.fullmatch(spec['pattern'],value),'Invalid manifest identifier')
    if spec.get('type')=='object':
        require(set(value)==set(spec['required']),'Manifest fields mismatch')
        for key,item in value.items(): schema_check(item,spec['properties'][key])
    if spec.get('type')=='array':
        require(spec.get('minItems',0)<=len(value)<=spec.get('maxItems',len(value)),'Manifest array size mismatch')
        for item in value: schema_check(item,spec['items'])

def read_tar(data, outer=False):
    require(len(data)<=MAX_BYTES,'Archive too large')
    result={}; total=0
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        for index,item in enumerate(archive):
            require(index<1000,'Too many archive members')
            name=PurePosixPath(item.name)
            require(not name.is_absolute() and '..' not in name.parts and '\\' not in item.name,'Unsafe archive path')
            if item.isdir(): continue
            require(str(name)==item.name,'Non-canonical archive path')
            require(item.isfile() and not item.issym() and not item.islnk(),'Only regular files allowed')
            require(item.name not in result and not item.mode & 0o111,'Duplicate or executable archive member')
            total+=item.size; require(total<=MAX_BYTES,'Expanded archive too large')
            result[item.name]=archive.extractfile(item).read()
    if outer: require(set(result)==FILES,'Unexpected bundle files')
    return result

def no_secrets(value):
    if isinstance(value,dict):
        for key,item in value.items():
            normalized=re.sub(r'[_:-]','',str(key)).lower()
            require(not re.search(r'(password|jwtsecret|proxysecret|sharedsecret|accesskey|sessiontoken|connectionstrings)',normalized),'Secret value field forbidden')
            no_secrets(item)
    elif isinstance(value,list):
        for item in value: no_secrets(item)
    elif isinstance(value,str):
        require(not re.search(r'-----BEGIN .*PRIVATE KEY|AKIA[0-9A-Z]{16}|Password\s*=',value,re.I),'Secret material forbidden')

def validate_manifest(m,target):
    synthetic = m.get('artifactSchemaVersion') == 2
    schema_path=Path(__file__).with_name('manifest.synthetic.schema.json' if synthetic else 'manifest.schema.json')
    require(schema_path.is_file(),'Requested host capability is not installed')
    schema=json.loads(schema_path.read_text())
    schema_check(m,schema)
    if synthetic:
        from synthetic_contract import scope_identity
        require(m['dataScope'] == scope_identity(target.get('dataScope')), 'Synthetic manifest/trusted scope mismatch')
        require(m['environment'] == m['dataScope']['environment'], 'Synthetic manifest environment mismatch')
    else:
        require('dataScope' not in target, 'Synthetic target cannot accept legacy artifact downgrade')
    for key in ('environment','accountId','region','clusterName','namespace','helmRelease'):
        require(m[key]==target[key],'Artifact target mismatch: '+key)
    require(m['artifactSchemaVersion']==(2 if synthetic else 1),'Unsupported artifact schema')
    require(m['requiredDeployerVersion']==(SYNTHETIC_VERSION if synthetic else VERSION) and m['requiredHelmVersion']==HELM,'Executor/tool version mismatch')
    require(m['migrationCompatibility']=='previous-release-compatible','Automatic rollback requires compatible migrations')
    require(re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+',m['releaseVersion']),'Invalid release version')
    for key in ('applicationSourceCommit','deploymentConfigCommit'): require(re.fullmatch('[0-9a-f]{40}',m[key]),'Invalid commit')
    require(m['applicationSourceCommit']==m['deploymentConfigCommit'],'CV-ready requires a single validated source/config commit')
    require(len(m['services'])==3 and {s['name'] for s in m['services']}==set(SERVICES),'Exactly three services required')
    for s in m['services']:
        require(set(s)=={'name','sourceCommit','imageRepository','imageDigest','buildRunId'},'Service fields mismatch')
        require(s['sourceCommit']==m['applicationSourceCommit'],'Mixed service commits')
        require(s['imageRepository']==target['repositories'][s['name']],'Unexpected image repository')
        require(re.fullmatch('sha256:[0-9a-f]{64}',s['imageDigest']),'Immutable digest required')
        require(re.fullmatch('[1-9][0-9]*',str(s['buildRunId'])),'Build run evidence missing')
    no_secrets(m)

def validate_bundle(data,digest,target):
    require(sha(data)==digest,'Outer SHA256 mismatch')
    files=read_tar(data,outer=True)
    expected={name:sha(content) for name,content in files.items() if name!='checksums.sha256'}
    lines=files['checksums.sha256'].decode().splitlines()
    require(len(lines)==4,'Checksum tree incomplete')
    actual={}
    for line in lines:
        h,name=line.split('  ',1); require(name not in actual,'Duplicate checksum'); actual[name]=h
    require(actual==expected,'Inner checksum mismatch')
    m=json.loads(files['manifest.json']); validate_manifest(m,target)
    for field,name in (('chartSha256','platform-services.tgz'),('valuesSha256','values.resolved.yaml'),('environmentContractSha256','environment.contract.json')):
        require(m[field]==expected[name],'Manifest checksum mismatch')
    c=json.loads(files['environment.contract.json']); no_secrets(c)
    if m['artifactSchemaVersion'] == 2:
        from synthetic_contract import validate_environment as validate_synthetic_environment, validate_values as validate_synthetic_values
        validate_synthetic_environment(c, target['dataScope'])
        require(c['dataScope'] == m['dataScope'], 'Synthetic artifact/environment scope mismatch')
        validate_synthetic_values(yaml.safe_load(files['values.resolved.yaml']), c)
    else:
        require(c['schemaVersion']==2 and 'dataScope' not in c,'R3 environment contract required')
    for key in ('environment','accountId','region','clusterName','namespace','repositories'):
        require(c[key]==target[key],'Environment snapshot mismatch')
    files['values.resolved.yaml']=normalized_values(files['values.resolved.yaml'],target)
    chart=read_tar(files['platform-services.tgz'])
    approved=json.loads(Path(__file__).with_name('chart-template-hashes.json').read_text())
    require({name:sha(content) for name,content in chart.items() if '/templates/' in name}==approved,'Chart template logic differs from the installed platform contract')
    require('platform-services/Chart.yaml' in chart,'Unexpected chart root')
    require(set(chart)==set(approved)|{'platform-services/Chart.yaml','platform-services/values.yaml'},'Unexpected chart files')
    metadata=yaml.safe_load(chart['platform-services/Chart.yaml'])
    require(metadata['name']=='platform-services' and not metadata.get('dependencies'),'Application chart must be self-contained')
    declarative(yaml.safe_load(chart['platform-services/values.yaml']))
    for name, content in chart.items():
        if '/templates/' in name:
            require(not re.search(rb'\b(tpl|lookup|randAlpha|randNumeric|randBytes|genPrivateKey|now|uuidv4)\b|\.Capabilities|\.Release\.(IsUpgrade|IsInstall|Revision)',content),'Non-deterministic/server-dependent templates forbidden')
    return files,m

def validate_render(docs,m,target):
    allowed={'Deployment','Service','ConfigMap','Job','PodDisruptionBudget','Ingress','HorizontalPodAutoscaler','ScaledObject'}
    images={s['name']:s['imageRepository']+'@'+s['imageDigest'] for s in m['services']}
    seen=set()
    for d in docs:
        if not d: continue
        kind=d['kind']; meta=d['metadata']; name=meta['name']
        require(not any(k.startswith('helm.sh/hook') for k in meta.get('annotations',{})) or kind=='Job','Only migration hooks allowed')
        require(kind in allowed and meta.get('namespace')=='apps','Forbidden resource scope/kind')
        require((kind,name) not in seen,'Duplicate Kubernetes resource'); seen.add((kind,name))
        suffix={'Deployment':'','Service':'','ConfigMap':'-config','Job':'-migrate','PodDisruptionBudget':'-pdb','Ingress':'','HorizontalPodAutoscaler':'-hpa','ScaledObject':'-sqs'}[kind]
        names={'platform-services'} if kind=='Ingress' else {s+'-service'+suffix for s in SERVICES}
        require(name in names,'Unexpected resource name')
        if kind=='HorizontalPodAutoscaler':
            require(name in ('auth-service-hpa','tracking-service-hpa') and d['apiVersion']=='autoscaling/v2','Only Auth/Tracking resource HPAs allowed')
            spec=d['spec']
            require(spec['scaleTargetRef']=={'apiVersion':'apps/v1','kind':'Deployment','name':name.removesuffix('-hpa')},'Wrong HPA target')
            require(2 <= spec['minReplicas'] <= spec['maxReplicas'] <= 4,'HPA capacity boundary')
            require(spec['metrics']==[{'type':'Resource','resource':{'name':'cpu','target':{'type':'Utilization','averageUtilization':70}}}],'Only reviewed CPU metric allowed')
        if kind=='ScaledObject':
            spec=d['spec']
            require(name=='shipment-service-sqs' and d['apiVersion']=='keda.sh/v1alpha1','Only Shipment scaler allowed')
            require(spec['scaleTargetRef']=={'apiVersion':'apps/v1','kind':'Deployment','name':'shipment-service'},'Wrong KEDA target')
            require(2 <= spec['minReplicaCount'] <= spec['maxReplicaCount'] <= 6,'KEDA capacity boundary')
            require(len(spec['triggers'])==1,'Only SQS scaler allowed')
            trigger=spec['triggers'][0]
            require(trigger['type']=='aws-sqs-queue' and trigger['authenticationRef']=={'name':'shipment-sqs-metrics'},'Platform authentication required')
            metadata=trigger['metadata']
            require(set(metadata)=={'queueURL','awsRegion','queueLength','activationQueueLength','scaleOnInFlight','scaleOnDelayed'},'Unexpected KEDA credential/metadata field')
            require(metadata['awsRegion']==target['region'] and metadata['queueURL']==target['shipmentQueueUrl'],'Wrong scaler queue')
            require({k:metadata[k] for k in ('queueLength','activationQueueLength','scaleOnInFlight','scaleOnDelayed')}=={'queueLength':'10','activationQueueLength':'0','scaleOnInFlight':'true','scaleOnDelayed':'false'},'Unreviewed SQS scaling semantics')
        if kind=='ConfigMap': no_secrets(d.get('data',{}))
        if kind=='Service':
            require(d['spec'].get('type','ClusterIP')=='ClusterIP' and not d['spec'].get('externalIPs'),'Only internal Services allowed')
        if kind=='Ingress':
            annotations=meta.get('annotations',{})
            expected={**platform_ingress(target),
                'alb.ingress.kubernetes.io/security-groups':target['alb']['frontendSecurityGroupId'],
                'alb.ingress.kubernetes.io/manage-backend-security-group-rules':'true',
                'alb.ingress.kubernetes.io/tags':','.join(k+'='+v for k,v in sorted(target['alb']['discoveryTags'].items()))}
            require(annotations==expected,'Rendered platform ALB annotations mismatch')
            require(set(d['spec'])=={'ingressClassName','rules'} and d['spec']['ingressClassName']=='alb','Unexpected Ingress identity')
        if kind not in ('Deployment','Job'): continue
        service=name.split('-')[0]; pod=d['spec']['template']['spec']
        require(not any(pod.get(k) for k in ('hostNetwork','hostPID','hostIPC','initContainers','ephemeralContainers')),'Unsafe Pod specification')
        require(pod.get('serviceAccountName')==(service+'-service' if kind=='Deployment' else 'platform-migrator'),'Wrong ServiceAccount')
        require(len(pod['containers'])==1,'Unexpected containers')
        require(pod.get('volumes') == [
            {'name':'runtime-tmp','emptyDir':{'medium':'Memory','sizeLimit':'64Mi'}},
            {'name':'database-ca','configMap':{'name':'platform-db-ca'}}],
            'Unexpected volume')
        require(pod.get('securityContext') == {'fsGroup':1654,'seccompProfile':{'type':'RuntimeDefault'}},
                'Unexpected Pod security context')
        container=pod['containers'][0]
        require(container.get('volumeMounts') == [
            {'name':'runtime-tmp','mountPath':'/tmp'},
            {'name':'database-ca','mountPath':'/etc/platform-ca','readOnly':True}],
            'Unexpected volume')
        require(not container.get('lifecycle'),'Container lifecycle commands forbidden')
        require(all(set(e)=={'configMapRef'} and e['configMapRef']=={'name':service+'-service-config'} for e in container.get('envFrom',[])),'Unexpected envFrom')
        require(pod.get('automountServiceAccountToken') is (kind=='Deployment' and service in ('shipment','tracking')),'Unexpected token mount')
        if kind=='Deployment':
            for probe,path in (('livenessProbe','/health/live'),('startupProbe','/health/live'),('readinessProbe','/health/ready')):
                require(container.get(probe,{}).get('httpGet',{}).get('path')==path and 'exec' not in container[probe],'Unexpected probe')
        else:
            require(meta.get('annotations',{}).get('helm.sh/hook')=='pre-install,pre-upgrade','Unexpected migration hook')
        require(container['image']==images[service],'Image mismatch')
        require('command' not in container and container.get('args',[])==(['--migrate'] if kind=='Job' else []),'Unexpected entrypoint override')
        security=container.get('securityContext',{})
        require(not security.get('privileged') and security.get('allowPrivilegeEscalation') is False and security.get('runAsNonRoot') is True,'Unsafe container security')
        require(not security.get('capabilities',{}).get('add'),'Added capabilities forbidden')
        require(security == {'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']},
                'readOnlyRootFilesystem':True,'runAsNonRoot':True},'Unexpected container security context')
        for e in container.get('env',[]):
            if 'value' in e: no_secrets({e['name']:e['value']})
            elif 'valueFrom' in e:
                ref=e['valueFrom'].get('secretKeyRef',{})
                expected={service+('-runtime-db' if kind=='Deployment' else '-migration-db')}
                expected|=({'auth-jwt'} if service=='auth' else {'gateway-trust','internal-trust'})
                if service=='auth' and kind=='Job': expected.add('bootstrap-admin')
                require(ref.get('name') in expected,'Unexpected Secret reference')
    require(all(('Deployment',s+'-service') in seen and ('Job',s+'-service-migrate') in seen for s in SERVICES),'Incomplete application release')
    require(('Ingress','platform-services') in seen,'Platform Ingress missing')
    require({('HorizontalPodAutoscaler','auth-service-hpa'),('HorizontalPodAutoscaler','tracking-service-hpa'),('ScaledObject','shipment-service-sqs')} <= seen,'Incomplete autoscaling release')
