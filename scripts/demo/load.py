"""Bounded HTTP load for an explicitly authorized future runtime certification demo; default is dry-run.
Tokens come only from DEMO_JWT; never print response bodies or authorization.
For event mode use existing disposable shipment IDs and a repeatable valid status.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import threading
import time
import urllib.request
import urllib.error
import urllib.parse
import uuid

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args): return None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--environment-contract',type=Path,required=True)
    p.add_argument('--mode',choices=['auth','tracking','events'],required=True)
    p.add_argument('--shipment-ids',nargs='*',default=[])
    p.add_argument('--count',type=int,default=500)
    p.add_argument('--concurrency',type=int,default=8)
    p.add_argument('--seconds',type=int,default=120)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if not 1<=a.count<=5000 or not 1<=a.concurrency<=16 or not 1<=a.seconds<=600: p.error('Limits: count<=5000, concurrency<=16, seconds<=600')
    if a.mode!='auth' and not a.shipment_ids: p.error('Use existing disposable shipment IDs')
    ids=[str(uuid.UUID(i)) for i in a.shipment_ids]
    c=json.loads(a.environment_contract.read_text()); endpoint=c['apiGateway']['endpoint'].rstrip('/')
    parsed=urllib.parse.urlsplit(endpoint)
    expected=f"{c['apiGateway']['apiId']}.execute-api.{c['region']}.amazonaws.com"
    if parsed.scheme!='https' or parsed.netloc!=expected or parsed.query or parsed.fragment: p.error('Unexpected API endpoint')
    print(f'Bounded {a.mode} load: <= {a.count} requests, {a.concurrency} concurrent, <= {a.seconds}s. Events mode writes demo data.')
    if not a.execute: print('PLAN ONLY; no requests sent'); return
    token=os.environ.get('DEMO_JWT')
    if not token: p.error('DEMO_JWT required; admin JWT for events')
    end=time.monotonic()+a.seconds; results={}; lock=threading.Lock()
    def send(i):
        if time.monotonic()>=end: return
        path='/auth/me' if a.mode=='auth' else '/tracking/by-shipment/'+ids[i%len(ids)]
        data=None
        if a.mode=='events':
            path='/admin/tracking-events'
            data=json.dumps({'shipmentId':ids[i%len(ids)],'status':'PICKED_UP','location':'R6 bounded demo','occurredAt':datetime.now(timezone.utc).isoformat(),'sourceType':'ADMIN'}).encode()
        request=urllib.request.Request(endpoint+path,data=data,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:
            with urllib.request.build_opener(NoRedirect).open(request,timeout=10) as response: code=response.status
        except urllib.error.HTTPError as error: code=error.code
        except (urllib.error.URLError,TimeoutError): code=0
        with lock: results[code]=results.get(code,0)+1
    with ThreadPoolExecutor(max_workers=a.concurrency) as pool: list(pool.map(send,range(a.count)))
    print(json.dumps({'statuses':results,'sent':sum(results.values())}))
    if not results or any(code<200 or code>=300 for code in results): raise SystemExit('FAIL: HTTP errors or no traffic; inspect sanitized application logs')

if __name__=='__main__': main()
