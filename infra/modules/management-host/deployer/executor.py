"""Fixed root-owned entry point. Artifacts supply data, never Python/shell code."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
import yaml
from contract import HELM, MAX_BYTES, require, validate_bundle, validate_render, sha, target_environment
from engine import execute
from diagnostics import CommandFailure

PATTERNS = {
    'ArtifactKey': r'deploy-artifacts/dev/[0-9a-f]{40}/[0-9a-f]{64}\.tar\.gz',
    'ArtifactVersionId': r'[A-Za-z0-9._~+/-]{1,1024}',
    'ArtifactSha256': r'[0-9a-f]{64}',
    'DeploymentId': r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',
    'ExpectedPreviousRevision': r'0|[1-9][0-9]{0,8}',
}


def validate_request(request, target=None):
    patterns = dict(PATTERNS)
    if target is not None:
        selected = target_environment(target)
        patterns['ArtifactKey'] = r'deploy-artifacts/' + re.escape(selected) + r'/[0-9a-f]{40}/[0-9a-f]{64}\.tar\.gz'
    require(set(request) == set(PATTERNS), 'Unexpected deployment inputs')
    for key, pattern in patterns.items():
        require(isinstance(request[key],str) and re.fullmatch(pattern, request[key]), 'Invalid '+key)
    require(request['ArtifactVersionId'] != 'null', 'Versioned S3 object required')
    require(request['ArtifactKey'].endswith('/'+request['ArtifactSha256']+'.tar.gz'), 'Key/digest mismatch')


class Host:
    def __init__(self, config, state, work):
        self.config, self.state, self.work = config, Path(state), Path(work)
        self.env = {**os.environ, 'KUBECONFIG': str(self.work/'kubeconfig'), 'AWS_DEFAULT_REGION': config['region'],
                    'AWS_PAGER': '', 'HELM_CACHE_HOME': str(self.work/'helm-cache'),
                    'HELM_CONFIG_HOME': str(self.work/'helm-config'), 'HELM_DATA_HOME': str(self.work/'helm-data')}
        for name in ('AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN','AWS_PROFILE','AWS_ROLE_ARN','AWS_WEB_IDENTITY_TOKEN_FILE','AWS_ENDPOINT_URL','AWS_ENDPOINT_URL_S3','AWS_ENDPOINT_URL_EKS'):
            self.env.pop(name,None)
        self.env.update(PATH='/usr/local/bin:/usr/bin:/bin', AWS_SHARED_CREDENTIALS_FILE=str(self.work/'no-credentials'), AWS_CONFIG_FILE=str(self.work/'no-config'))

    def run(self, args, timeout=900):
        result = subprocess.run(args, env=self.env, text=True, capture_output=True, timeout=timeout)
        if result.returncode != 0:
            raise CommandFailure(args[0], result.returncode, result.stderr)
        return result.stdout

    def aws(self, *args):
        return json.loads(self.run(['aws', *args, '--output','json']))

    def kubectl(self, *args):
        return self.run(['kubectl','-n','apps',*args],timeout=660)

    def receipt_key(self, suffix):
        return 'deployment-receipts/' + target_environment(self.config) + '/' + suffix

    def receipt_scope(self, receipt):
        if 'dataScope' in self.config:
            require(receipt.get('target', {}).get('dataScope') == self.config['dataScope'], 'Synthetic receipt scope mismatch')
        return receipt

    def load(self, deployment_id):
        local = self.state/(deployment_id+'.json')
        if local.exists(): return self.receipt_scope(json.loads(local.read_text()))
        # Host replacement must not erase replay protection. Check the durable receipt.
        key=self.receipt_key(deployment_id+'.json')
        listing=self.aws('s3api','list-objects-v2','--bucket',self.config['bucket'],'--prefix',key,'--max-keys','2')
        if not any(item['Key']==key for item in listing.get('Contents',[])): return None
        self.aws('s3api','get-object','--bucket',self.config['bucket'],'--key',key,str(local))
        return self.receipt_scope(json.loads(local.read_text()))

    def save(self, receipt):
        receipt['bucket'] = self.config['bucket']
        receipt['target'] = {k:self.config[k] for k in ('environment','accountId','region','clusterName','namespace','helmRelease')}
        if 'dataScope' in self.config: receipt['target']['dataScope'] = self.config['dataScope']
        path = self.state/(receipt['deploymentId']+'.json')
        temporary = path.with_suffix('.tmp')
        with temporary.open('w') as stream:
            json.dump(receipt,stream,sort_keys=True); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(path)

    def publish(self, receipt):
        path = self.state/(receipt['deploymentId']+'.json')
        self.aws('s3api','put-object','--bucket',self.config['bucket'],'--key',self.receipt_key(receipt['deploymentId']+'.json'),'--body',str(path),'--content-type','application/json')

    def activate(self, receipt):
        current = self.current()
        require(current['status'] == 'deployed' and current['revision'] == receipt['activeRevision'], 'Active revision changed before provenance update')
        active_artifact=receipt['artifact'] if receipt['status']=='SUCCESS' else receipt.get('previousArtifact') if receipt.get('rollbackResult')=='VERIFIED' else None
        if active_artifact:
            marker={'revision':receipt['activeRevision'],'artifact':active_artifact,'deploymentId':receipt['deploymentId']}
            path=self.state/'.active-state.json'; path.write_text(json.dumps(marker))
            self.aws('s3api','put-object','--bucket',self.config['bucket'],'--key',self.receipt_key('_state/active.json'),'--body',str(path),'--content-type','application/json')

    def preflight(self, request):
        validate_request(request, self.config)
        require(self.run(['helm','version','--template','{{.Version}}']).strip()==HELM,'Unexpected Helm version')
        path=self.work/'artifact.tar.gz'
        header=self.aws('s3api','head-object','--bucket',self.config['bucket'],'--key',request['ArtifactKey'],'--version-id',request['ArtifactVersionId'])
        require(header['ContentLength']<=MAX_BYTES,'Artifact exceeds download limit')
        meta=self.aws('s3api','get-object','--bucket',self.config['bucket'],'--key',request['ArtifactKey'],'--version-id',request['ArtifactVersionId'],str(path))
        require(meta.get('VersionId')==request['ArtifactVersionId'],'S3 version mismatch')
        files,self.manifest=validate_bundle(path.read_bytes(),request['ArtifactSha256'],self.config)
        require(request['ArtifactKey'].split('/')[2]==self.manifest['applicationSourceCommit'],'Key/source mismatch')
        # validate_bundle returns normalized declarative values. Persist once;
        # template and upgrade use this same file, not the artifact's raw YAML.
        for name, content in files.items(): (self.work/name).write_bytes(content)
        rendered=self.run(['helm','template','platform-services',str(self.work/'platform-services.tgz'),'-n','apps','-f',str(self.work/'values.resolved.yaml')])
        validate_render(yaml.safe_load_all(rendered),self.manifest,self.config)
        cluster=self.aws('eks','describe-cluster','--name',self.config['clusterName'])['cluster']
        require(cluster['arn']==f"arn:aws:eks:{self.config['region']}:{self.config['accountId']}:cluster/{self.config['clusterName']}",'Cluster identity mismatch')
        require(cluster['resourcesVpcConfig']['endpointPrivateAccess'] and not cluster['resourcesVpcConfig']['endpointPublicAccess'],'Private EKS required')
        self.run(['aws','eks','update-kubeconfig','--name',self.config['clusterName'],'--kubeconfig',self.env['KUBECONFIG']])
        auth=json.loads(self.kubectl("get","triggerauthentication","shipment-sqs-metrics","-o","json"))
        require(auth["spec"]=={"podIdentity":{"provider":"aws","identityOwner":"keda"}},"KEDA platform authentication not ready")
        return self.manifest

    def current(self):
        # Helm 4 lists every status by default; the removed Helm 3 --all flag
        # otherwise prevents even a read-only preflight of an existing release.
        releases=json.loads(self.run(['helm','list','-n','apps','--filter','^platform-services$','-o','json']))
        if not releases: return {'revision':0,'status':'absent'}
        require(len(releases)==1,'Ambiguous Helm release')
        revision=int(releases[0]['revision'])
        manifest=self.run(['helm','get','manifest','platform-services','-n','apps','--revision',str(revision)])
        values=self.run(['helm','get','values','platform-services','-n','apps','--revision',str(revision),'-o','json'])
        key=self.receipt_key('_state/active.json')
        listing=self.aws('s3api','list-objects-v2','--bucket',self.config['bucket'],'--prefix',key,'--max-keys','2')
        artifact=None
        if any(item['Key']==key for item in listing.get('Contents',[])):
            marker_path=self.work/'active-receipt.json'
            self.aws('s3api','get-object','--bucket',self.config['bucket'],'--key',key,str(marker_path))
            marker=json.loads(marker_path.read_text())
            if marker['revision']==revision: artifact=marker['artifact']
        return {'revision':revision,'status':releases[0]['status'],'manifestHash':sha(manifest.encode()),'valuesHash':sha(values.encode()),'release':json.loads(values).get('release',{}),'artifact':artifact}

    def matches(self, before):
        current=self.current()
        return current['status']=='deployed' and all(current.get(k)==before.get(k) for k in ('manifestHash','valuesHash'))

    def secret_gate(self):
        started=datetime.now(timezone.utc).replace(microsecond=0)
        names=[f'{s}-{p}-db' for s in ('auth','shipment','tracking') for p in ('runtime','migration')]+['auth-jwt','gateway-trust','internal-trust','bootstrap-admin']
        deadline=time.monotonic()+300
        remaining=set(names)
        while remaining and time.monotonic()<deadline:
            for name in list(remaining):
                status=json.loads(self.kubectl('get','externalsecret',name,'-o','json')).get('status',{})
                fresh=status.get('refreshTime')
                if fresh and datetime.fromisoformat(fresh.replace('Z','+00:00'))>=started and any(c.get('type')=='Ready' and c.get('status')=='True' for c in status.get('conditions',[])): remaining.remove(name)
            if remaining: time.sleep(5)
        require(not remaining,'Fresh ESO reconciliation required')
        versions={}
        for name in names:
            keys=self.kubectl('get','secret',name,'-o','go-template={{range $k,$v := .data}}{{$k}}{{"\\n"}}{{end}}').splitlines()
            expected={'username','password'} if name.endswith('-db') else ({'email','password'} if name=='bootstrap-admin' else {'value'})
            require(expected.issubset(keys),'Secret keys missing')
            versions[name]=self.kubectl('get','secret',name,'-o','jsonpath={.metadata.resourceVersion}').strip()
        marker=json.loads(self.kubectl('get','configmap','platform-db-bootstrap','-o','json'))['data']
        require(versions==marker,'R3 DB bootstrap marker stale; platform reconciliation required')

    def upgrade(self):
        self.run(['helm','upgrade','--install','platform-services',str(self.work/'platform-services.tgz'),'-n','apps','-f',str(self.work/'values.resolved.yaml'),
                  '--rollback-on-failure','--wait=legacy','--wait-for-jobs','--timeout','10m','--history-max','10'],timeout=1500)

    def rollback(self, revision):
        self.run(['helm','rollback','platform-services',str(revision),'-n','apps','--no-hooks','--wait=legacy','--timeout','10m'],timeout=660)

    def smoke(self, evidence):
        evidence['KUBERNETES_READY'] = 'FAILED'
        ingress=json.loads(self.kubectl('get','ingress','platform-services','-o','json'))
        require(ingress.get('status',{}).get('loadBalancer',{}).get('ingress'),'Ingress has no ALB address')
        for service in ('auth','shipment','tracking'):
            self.kubectl('rollout','status','deployment/'+service+'-service','--timeout=120s')
            slices=json.loads(self.kubectl('get','endpointslices','-l','kubernetes.io/service-name='+service+'-service','-o','json'))
            require(any(e.get('conditions',{}).get('ready') for s in slices['items'] for e in s.get('endpoints',[])),'No ready Service targets')
        evidence['KUBERNETES_READY'] = 'PASS'
        # Empty refresh input fails MVC validation before any token/database action.
        # Require application-specific evidence, not just a status generated by the edge.
        evidence['AUTH_BACKEND_REACHABLE'] = 'FAILED'
        request = urllib.request.Request(self.config['apiEndpoint']+'/auth/refresh', data=b'{}',
                                         headers={'Content-Type':'application/json'}, method='POST')
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(request, timeout=20):
                raise ValueError('Empty refresh unexpectedly accepted')
        except urllib.error.HTTPError as error:
            with error:
                require(error.code == 400, 'Unexpected backend validation status')
                require(error.headers.get_content_type() == 'application/problem+json', 'Missing backend problem response')
                problem = json.loads(error.read(8193))
                require(problem.get('status') == 400 and
                        isinstance(problem.get('errors',{}).get('RefreshToken'),list) and
                        bool(problem['errors']['RefreshToken']) and bool(error.headers.get('X-Request-Id')),
                        'Missing Auth validation evidence')
        evidence['AUTH_BACKEND_REACHABLE'] = 'PASS'
        evidence['EDGE_ANONYMOUS_REJECTED'] = 'FAILED'
        try:
            with opener.open(self.config['apiEndpoint']+'/shipments',timeout=20):
                raise ValueError('Protected edge accepted anonymous request')
        except urllib.error.HTTPError as error:
            with error:
                require(error.code==401,'Unexpected protected edge response')
        evidence['EDGE_ANONYMOUS_REJECTED'] = 'PASS'


def main():
    parser=argparse.ArgumentParser()
    for key in PATTERNS: parser.add_argument('--'+key,required=True)
    request=vars(parser.parse_args())
    os.umask(0o077)
    import fcntl
    require(Path('/opt/platform-deployer/READY').is_file(),'Platform bootstrap incomplete')
    config=json.loads(Path('/opt/platform-deployer/config.json').read_text())
    validate_request(request, config)
    state=Path('/var/lib/platform-deployer')
    with (state/'deploy.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix='run-',dir=state) as work:
            receipt=execute(request,Host(config,state,work))
    print(json.dumps(receipt,sort_keys=True))
    return 0 if receipt['status']=='SUCCESS' else 1


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception:
        print('Deployment failed or indeterminate; consult durable receipt and SSM status. No automatic resend.')
        raise SystemExit(1)
