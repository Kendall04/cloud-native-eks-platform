"""R6 contracts: actual Helm objects plus parsed IaC. Never contacts AWS."""
import ast
import json
import os
from pathlib import Path
import subprocess
import hcl2
import yaml
from validate_r1 import ROOT, render, require
from validate_r3 import platform_render
from validate_current_profile import validate_network


def snapshot():
    helm = os.environ.get('HELM_BIN', 'helm')
    apps = [d for d in render(helm, ROOT/'k8s/environments/dev/platform-services.values.yaml') if d]
    platform, fixture = platform_render(helm)
    addons = list(yaml.safe_load_all(subprocess.check_output([helm,'template','cluster-addons',str(ROOT/'k8s/charts/cluster-addons'),'-n','kube-system'],text=True)))
    paths = {'eks':'infra/modules/eks/main.tf','iam':'infra/live/dev/iam/terragrunt.hcl',
             'cw':'infra/modules/observability/main.tf','dashboard':'infra/modules/observability/dashboard.tf',
             'alarms':'infra/modules/observability/alarms.tf','deployer':'infra/modules/management-host/deployer/contract.py'}
    return dict(apps=apps,platform=platform,networkPrivateSubnetCidrs=fixture['network']['privateSubnetCidrs'],addons=[d for d in addons if d],
                telemetry=[p.read_text() for p in (ROOT/'microservices').glob('*/src/*.Infrastructure/Observability/OperationalMetrics.cs')],
                **{k:(ROOT/v).read_text() for k,v in paths.items()})


def validate(data):
    apps = {(d['kind'],d['metadata']['name']):d for d in data['apps']}
    addons = {(d['kind'],d['metadata']['name']):d for d in data['addons']}
    require(('Deployment','metrics-server') in addons, 'Metrics Server missing')
    require('--kubelet-insecure-tls' not in json.dumps(data['addons']), 'Kubelet TLS must be verified')
    require(('Deployment','keda-operator') in addons, 'KEDA operator missing')
    require(('HorizontalPodAutoscaler','shipment-service-hpa') not in apps, 'Shipment cannot have competing HPA')
    for service in ('auth','tracking','shipment'):
        dep = apps['Deployment',service+'-service']; pod = dep['spec']['template']['spec']
        require('replicas' not in dep['spec'], 'Helm must not reset autoscaler replicas')
        spread = pod.get('topologySpreadConstraints',[])
        require({s['topologyKey'] for s in spread} == {'kubernetes.io/hostname','topology.kubernetes.io/zone'}, 'Missing distribution')
        require(all(s['maxSkew']==1 and s['whenUnsatisfiable']=='ScheduleAnyway' and s['labelSelector']['matchLabels'].get('platform.cloud-native.io/workload')=='runtime' for s in spread),'Wrong spread semantics')
        require(pod['containers'][0]['resources']['requests']['cpu'], 'HPA denominator missing')
        require(apps['PodDisruptionBudget',service+'-service-pdb']['spec']['maxUnavailable']==1, 'PDB budget changed')
    for service in ('auth','tracking'):
        require(('HorizontalPodAutoscaler',service+'-service-hpa') in apps, 'HPA missing')
        s=apps['HorizontalPodAutoscaler',service+'-service-hpa']['spec']
        require(s['minReplicas']==2 and s['maxReplicas']==4, 'HTTP replica bounds')
        require(s['metrics']==[{'type':'Resource','resource':{'name':'cpu','target':{'type':'Utilization','averageUtilization':70}}}], 'HPA CPU contract')
        require(s['behavior']['scaleDown']['stabilizationWindowSeconds']==300,'HPA scale-down budget')
    require(('ScaledObject','shipment-service-sqs') in apps, 'Shipment KEDA missing')
    s=apps['ScaledObject','shipment-service-sqs']['spec']
    require(s['minReplicaCount']==2 and s['maxReplicaCount']==6,'Shipment capacity bounds')
    require(s['pollingInterval']==30 and s['advanced']['horizontalPodAutoscalerConfig']['behavior']['scaleDown']['stabilizationWindowSeconds']==300,'KEDA damping')
    trigger=s['triggers'][0]
    require(len(s['triggers'])==1 and trigger['authenticationRef']=={'name':'shipment-sqs-metrics'},'Platform KEDA auth')
    require(trigger['type']=='aws-sqs-queue' and set(trigger['metadata'])=={'queueURL','awsRegion','queueLength','activationQueueLength','scaleOnInFlight','scaleOnDelayed'},'Static/deprecated scaler auth forbidden')
    require({k:trigger['metadata'][k] for k in ('queueLength','scaleOnInFlight','scaleOnDelayed')}=={'queueLength':'10','scaleOnInFlight':'true','scaleOnDelayed':'false'},'Visibility semantics changed')
    auth=[d for d in data['platform'] if d['kind']=='TriggerAuthentication']
    require(len(auth)==1 and auth[0]['spec']=={'podIdentity':{'provider':'aws','identityOwner':'keda'}},'Static/deprecated KEDA authentication')
    policies=[d for d in data['platform'] if d['kind']=='NetworkPolicy']
    require(len(policies)==3 and all(set(p['spec']['policyTypes'])=={'Ingress','Egress'} for p in policies),'Runtime segmentation missing')
    validate_network(policies, data['networkPrivateSubnetCidrs'])
    for key in ('eks','iam','cw','dashboard','alarms'): hcl2.loads(data[key])
    require('enableNetworkPolicy = "true"' in data['eks'] and 'NETWORK_POLICY_ENFORCING_MODE' in data['eks'] and '"standard"' in data['eks'],'VPC CNI enforcement disabled')
    roles=hcl2.loads(data['iam'])['inputs']['roles']
    keda=next(v for k,v in roles.items() if 'keda-irsa' in k)
    policy=json.dumps(keda)
    require('sqs:GetQueueAttributes' in policy and not any(x in policy for x in ('sqs:*','ReceiveMessage','DeleteMessage','kms:')),'KEDA least privilege')
    require('system:serviceaccount:kube-system:keda-operator' in policy and 'sts.amazonaws.com' in policy,'KEDA identity trust')
    tree=ast.parse(data['deployer'])
    allowed=next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='allowed' for t in n.targets))
    require(allowed=={'Deployment','Service','ConfigMap','Job','PodDisruptionBudget','Ingress','HorizontalPodAutoscaler','ScaledObject'},'Application artifact boundary')
    require(not any(d['kind'] in ('NetworkPolicy','TriggerAuthentication','CustomResourceDefinition','ClusterRole') for d in data['apps']),'Platform ownership violated')
    role=next(d for d in data['platform'] if d['kind']=='Role')
    for rule in role['rules']:
        if 'triggerauthentications' in rule['resources']: require(rule['verbs']==['get'] and rule['resourceNames']==['shipment-sqs-metrics'],'CD cannot write TriggerAuthentication')
    require('retention_in_days = 14' in data['cw'] and 'otelContainerInsights' in data['cw'] and 'log_key log' in data['cw'],'Telemetry transport/retention')
    for category in ('AWS/ApiGateway','AWS/SQS','AWS/RDS','Platform/Operations','kube_deployment','container_cpu','container_memory','restarts','kube_node'):
        require(category in data['dashboard'],'Missing dashboard category '+category)
    alarms=hcl2.loads(data['alarms'])['locals'][0]['alarms']
    require({'consumer-dlq','delivery-dlq','queue-age','outbox-failed','outbox-age','rds-cpu'}<=set(alarms),'Missing operational/DLQ alarm')
    require(len(data['telemetry'])==3,'All services require EMF emitter')
    for source in data['telemetry']:
        require('Dimensions = new[] { new[] { "Environment", "Service" } }' in source,'Unbounded metric dimensions')
        require('"EventId"' not in source and '"ShipmentId"' not in source,'High-cardinality metrics')
    print('R6 Helm/IaC/telemetry boundaries: PASS')

if __name__=='__main__':
    validate(snapshot())
