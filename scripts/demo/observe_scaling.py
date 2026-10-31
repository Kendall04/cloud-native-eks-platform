"""Read-only future runtime certification scaling observer. Requires private-network kubectl and AWS read access.
Start before load. Exit nonzero unless ready replicas grow above baseline then return
at or below baseline. No scaling, deleting pods or changing queue visibility here.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path


def command(args):
    return json.loads(subprocess.check_output(args,text=True,timeout=30))


def progressed(samples):
    if len(samples)<3: return False
    baseline=samples[0]['ready']
    peak=max(s['ready'] for s in samples)
    scaled = baseline>=2 and peak>baseline and samples[-1]['ready']<=baseline and samples[-1]['desired']<=baseline
    if 'queue' in samples[-1]:
        backlog=lambda s: sum(int(s['queue'].get(k,0)) for k in ('ApproximateNumberOfMessages','ApproximateNumberOfMessagesNotVisible'))
        scaled = scaled and max(backlog(s) for s in samples)>0 and backlog(samples[-1])==0
    return scaled


def collect(service,region,queue):
    deployment=command(['kubectl','-n','apps','get','deployment',service+'-service','-o','json'])
    pods=command(['kubectl','-n','apps','get','pods','-l','platform.cloud-native.io/workload=runtime','-o','json'])
    nodes=command(['kubectl','get','nodes','-o','json'])
    sample={'timestamp':int(time.time()),'desired':deployment['spec'].get('replicas',1),'ready':deployment.get('status',{}).get('readyReplicas',0),
            'nodes':len(nodes['items']),'pending':[p['metadata']['name'] for p in pods['items'] if p['status']['phase']=='Pending']}
    hpas=command(['kubectl','-n','apps','get','hpa','-o','json'])
    sample['scaler']=[{'name':h['metadata']['name'],'conditions':h.get('status',{}).get('conditions',[]),'metrics':h.get('status',{}).get('currentMetrics',[])} for h in hpas['items'] if h['spec']['scaleTargetRef']['name']==service+'-service']
    if queue:
        sample['queue']=command(['aws','--region',region,'sqs','get-queue-attributes','--queue-url',queue,'--attribute-names','ApproximateNumberOfMessages','ApproximateNumberOfMessagesNotVisible','ApproximateNumberOfMessagesDelayed','--output','json'])['Attributes']
    return sample


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--service',choices=['auth','tracking','shipment'],required=True)
    p.add_argument('--environment-contract',type=Path,required=True)
    p.add_argument('--seconds',type=int,default=1200)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not 60<=a.seconds<=3600: p.error('seconds must be 60..3600')
    c=json.loads(a.environment_contract.read_text())
    cluster=command(['aws','--region',c['region'],'eks','describe-cluster','--name',c['clusterName'],'--output','json'])['cluster']
    context=command(['kubectl','config','view','--minify','-o','json'])
    if context['clusters'][0]['cluster']['server']!=cluster['endpoint']: raise SystemExit('Wrong kubectl endpoint')
    samples=[]; deadline=time.monotonic()+a.seconds
    while time.monotonic()<deadline:
        samples.append(collect(a.service,c['region'],c['shipmentQueue']['url'] if a.service=='shipment' else None))
        a.output.write_text(json.dumps({'service':a.service,'samples':samples,'passed':progressed(samples)},indent=2)+'\n')
        print(json.dumps(samples[-1]))
        if progressed(samples): print('PASS: ready scale-up and scale-down observed'); return
        time.sleep(15)
    raise SystemExit('FAIL: no complete scale-up/down. Inspect recorded HPA conditions, CPU/request ratio or SQS backlog, Pending pods, node count; insufficient load is NOT a pass.')

if __name__=='__main__': main()
