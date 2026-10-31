"""Disposable local Docker/PostgreSQL upgrade gate; never contacts AWS.

Requires three baseline .NET8 images and three candidate images already built.
Credentials and TLS fixture material remain in ignored validation output only.
"""
import argparse
import os,pathlib,subprocess,secrets,time,json,urllib.request,urllib.error
import psycopg
from psycopg import sql
root=pathlib.Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-tag',default='sdk426')
parser.add_argument('--candidate-tag',default='dotnet10')
parser.add_argument('--output',default='.validation-results/dotnet10')
settings=parser.parse_args()
out=(root/settings.output).resolve()
if not out.is_relative_to((root/'.validation-results').resolve()):raise ValueError('Output must stay in ignored .validation-results')
out.mkdir(parents=True,exist_ok=True)
prefix='cnp-dotnet10-'+secrets.token_hex(4)
cert=out/('tls-'+secrets.token_hex(4));cert.mkdir(exist_ok=True)
def run(*args,**kw):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,**kw).strip()
# Private fixture material stays ignored and is never printed.
run('openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(cert/'server.key'),'-out',str(cert/'server.crt'),'-days','1','-subj','/CN='+prefix+'-pg','-addext','subjectAltName=DNS:'+prefix+'-pg')
run('docker','run','--rm','--user','0','--entrypoint','sh','-v',str(cert)+':/tls','postgres:15.18','-c','chown 999:999 /tls/server.key && chmod 600 /tls/server.key')
network=prefix+'-network';created=[];passwords={};summary=[];network_created=False
try:
 run('docker','network','create',network);network_created=True
 pgpass=secrets.token_hex(24); env={**os.environ,'POSTGRES_PASSWORD':pgpass}
 run('docker','run','-d','--name',prefix+'-pg','--network',network,'-e','POSTGRES_PASSWORD','-p','127.0.0.1:55434:5432','-v',str(cert)+':/tls:ro','postgres:15.18','-c','ssl=on','-c','ssl_cert_file=/tls/server.crt','-c','ssl_key_file=/tls/server.key',env=env);created.append(prefix+'-pg')
 for _ in range(40):
  try:
   conn=psycopg.connect(host='127.0.0.1',port=55434,user='postgres',password=pgpass,dbname='postgres',autocommit=True);break
  except psycopg.OperationalError:time.sleep(1)
 else:raise RuntimeError('local PostgreSQL readiness timeout')
 conn.execute('CREATE DATABASE platform');conn.close()
 conn=psycopg.connect(host='127.0.0.1',port=55434,user='postgres',password=pgpass,dbname='platform',autocommit=True)
 for service in ['auth','shipment','tracking']:
  for kind in ['migrator','runtime']:
   user=service+'_'+kind;passwords[user]=secrets.token_hex(24)
   conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(user),sql.Literal(passwords[user])))
  conn.execute(sql.SQL('CREATE SCHEMA {} AUTHORIZATION {}').format(sql.Identifier(service),sql.Identifier(service+'_migrator')))
  conn.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(service),sql.Identifier(service+'_runtime')))
  conn.execute(sql.SQL('ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO {}').format(sql.Identifier(service+'_migrator'),sql.Identifier(service),sql.Identifier(service+'_runtime')))
  conn.execute(sql.SQL('ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT USAGE,SELECT ON SEQUENCES TO {}').format(sql.Identifier(service+'_migrator'),sql.Identifier(service),sql.Identifier(service+'_runtime')))
 jwt=secrets.token_hex(32);proxy=secrets.token_hex(32);internal=secrets.token_hex(32)
 def options(service,kind,name):
  e={'ASPNETCORE_ENVIRONMENT':'Production','ASPNETCORE_URLS':'http://+:8080','Database__Host':prefix+'-pg','Database__Name':'platform','Database__Schema':service,'Database__Username':service+'_'+kind,'Database__Password':passwords[service+'_'+kind],'Database__SslMode':'VerifyFull','Database__RootCertificate':'/etc/platform-ca/server.crt','Jwt__Secret':jwt,'PlatformAuth__TrustedProxySecret':proxy,'PlatformAuth__InternalServiceSecret':internal,'ShipmentService__BaseUrl':'http://'+prefix+'-shipment:8080','ShipmentConsumer__Enabled':'false','Outbox__Enabled':'false','AWS_EC2_METADATA_DISABLED':'true'}
  args=['docker','run','--name',name,'--network',network,'--read-only','--cap-drop=ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777','-v',str(cert/'server.crt')+':/etc/platform-ca/server.crt:ro']
  for k in e:args+=['-e',k]
  return args,{**os.environ,**e}
 def migrate(service,tag):
  name=prefix+'-'+service+'-migrate-'+tag;args,env=options(service,'migrator',name);created.append(name)
  with (out/(service+'-migration-'+tag+'.log')).open('w') as log:
   r=subprocess.run([*args,'cnp-ci/'+service+':'+tag,'--migrate'],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90)
  if r.returncode:raise RuntimeError(service+' '+tag+' migration failed; inspect ignored log')
 def schema_state():
  statements=["SELECT table_schema,table_name,column_name,data_type,udt_name,is_nullable,column_default,character_maximum_length,numeric_precision,numeric_scale FROM information_schema.columns WHERE table_schema IN ('auth','shipment','tracking') ORDER BY 1,2,3", "SELECT n.nspname,c.relname,k.conname,pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON k.conrelid=c.oid JOIN pg_namespace n ON c.relnamespace=n.oid WHERE n.nspname IN ('auth','shipment','tracking') ORDER BY 1,2,3", "SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes WHERE schemaname IN ('auth','shipment','tracking') ORDER BY 1,2,3"]
  return [conn.execute(q).fetchall() for q in statements]+[conn.execute('SELECT * FROM '+service+'."__EFMigrationsHistory" ORDER BY 1').fetchall() for service in ['auth','shipment','tracking']]
 for service in ['auth','shipment','tracking']:migrate(service,settings.baseline_tag)
 before=schema_state()
 # Seed a real .NET8 user/token before upgrading the same PostgreSQL DB.
 name=prefix+'-auth-old';args,env=options('auth','runtime',name);created.append(name)
 run(*args,'-d','-p','127.0.0.1:18083:8080','cnp-ci/auth:'+settings.baseline_tag,env=env)
 for _ in range(40):
  try:
   with urllib.request.urlopen('http://127.0.0.1:18083/health/ready',timeout=2) as response:
    if response.status==200:break
  except (urllib.error.URLError,TimeoutError,OSError):time.sleep(1)
 else:raise RuntimeError('NET8 fixture readiness failed')
 def old_request(path,payload):
  request=urllib.request.Request('http://127.0.0.1:18083'+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(request,timeout=8) as response:return json.load(response)
 oldpass=secrets.token_hex(16)+'Aa1!';oldemail='net8-upgrade@example.invalid'
 old_request('/auth/register',{'email':oldemail,'password':oldpass,'firstName':'Before','lastName':'Upgrade'})
 oldtokens=old_request('/auth/login',{'email':oldemail,'password':oldpass})
 run('docker','rm','-fv',name)
 for service in ['auth','shipment','tracking']:migrate(service,settings.candidate_tag)
 assert before==schema_state(), 'Upgrade changed schema or migration history'
 summary.append({'test':'NET8-created PostgreSQL schemas upgraded by NET10; columns, indexes, constraints and histories unchanged','result':'PASS'})
 for service in ['auth','shipment','tracking']:
  name=prefix+'-'+service;args,env=options(service,'runtime',name);created.append(name)
  port=18080+['auth','shipment','tracking'].index(service)
  run(*args,'-d','-p','127.0.0.1:'+str(port)+':8080','cnp-ci/'+service+':'+settings.candidate_tag,env=env)
  for _ in range(40):
   try:
    with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health/ready',timeout=2) as response:
     if response.status==200:break
   except (urllib.error.URLError,TimeoutError,OSError):time.sleep(1)
  else:raise RuntimeError(service+' readiness failed')
  summary.append({'service':service,'test':'production runtime readiness; VerifyFull PostgreSQL TLS; readonly root; UID1654; bounded tmp','result':'PASS'})
 def req(path,payload=None,token=None):
  headers={'Content-Type':'application/json'}
  if token:headers['Authorization']='Bearer '+token
  request=urllib.request.Request('http://127.0.0.1:18080'+path,data=json.dumps(payload).encode() if payload else None,headers=headers)
  with urllib.request.urlopen(request,timeout=8) as response:return json.load(response)
 req('/auth/me',token=oldtokens['accessToken'])
 req('/auth/refresh',{'refreshToken':oldtokens['refreshToken']})
 req('/auth/login',{'email':oldemail,'password':oldpass})
 summary.append({'test':'Existing NET8 PostgreSQL user/password/access token/refresh token accepted by NET10 runtime','result':'PASS'})
 testpass=secrets.token_hex(16)+'Aa1!';email='readonly-test@example.invalid'
 req('/auth/register',{'email':email,'password':testpass,'firstName':'Local','lastName':'Fixture'})
 tokens=req('/auth/login',{'email':email,'password':testpass});req('/auth/me',token=tokens['accessToken']);req('/auth/refresh',{'refreshToken':tokens['refreshToken']})
 summary.append({'service':'auth','test':'register/login/me/refresh against PostgreSQL with readonly root','result':'PASS'})
 def http(port,path,payload=None,headers=None,expected=200,raw=None):
  body=raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
  request=urllib.request.Request('http://127.0.0.1:'+str(port)+path,data=body,headers={'Content-Type':'application/json',**(headers or {})})
  try:
   with urllib.request.urlopen(request,timeout=10) as response:status=response.status;data=response.read()
  except urllib.error.HTTPError as error:status=error.code;data=error.read()
  assert status==expected, f'{port} {path}: expected {expected}, got {status}'
  return json.loads(data) if data else None
 import base64,hmac,hashlib,uuid
 def segment(v):return base64.urlsafe_b64encode(json.dumps(v).encode()).rstrip(b'=').decode()
 def invalid_token(**overrides):
  payload={'iss':'logistics-platform','aud':'logistics-platform-clients','exp':int(time.time())+300,'sub':str(uuid.uuid4()),**overrides}
  value=segment({'alg':'HS256','typ':'JWT'})+'.'+segment(payload)
  return value+'.'+base64.urlsafe_b64encode(hmac.new(jwt.encode(),value.encode(),hashlib.sha256).digest()).rstrip(b'=').decode()
 for token in ['not-a-jwt',invalid_token(exp=int(time.time())-120),invalid_token(iss='wrong'),invalid_token(aud='wrong'),tokens['accessToken'][:-12]+'AAAAAAAAAAAA']:
  http(18080,'/auth/me',headers={'Authorization':'Bearer '+token},expected=401)
 http(18080,'/auth/register',raw=b'{broken',expected=400)
 http(18081,'/shipments',expected=401)
 http(18081,'/shipments',headers={'X-Platform-User-Id':'fixture','X-Platform-Roles':'ADMIN','X-Platform-Proxy-Secret':'wrong'},expected=401)
 gateway={'X-Platform-User-Id':str(uuid.uuid4()),'X-Platform-Roles':'ADMIN','X-Platform-Proxy-Secret':proxy}
 shipment=http(18081,'/shipments',{'customerId':'fixture','origin':'A','destination':'B','weight':1.25},gateway,201)
 http(18081,'/shipments/by-id/'+shipment['id'],headers=gateway)
 payload={'shipmentId':shipment['id'],'status':'PICKED_UP','location':'hub','occurredAt':'2026-10-15T08:00:00Z','sourceType':'ADMIN'}
 event=http(18082,'/admin/tracking-events',payload,gateway,201)
 timeline=http(18082,'/tracking/by-shipment/'+shipment['id'],headers=gateway)
 assert len(timeline)==1 and timeline[0]['id']==event['id']
 assert conn.execute('SELECT count(*) FROM tracking."OutboxMessages"').fetchone()[0]==1
 payload['status']='NOT_A_STATUS';http(18082,'/admin/tracking-events',payload,gateway,400)
 summary.append({'test':'JWT invalid/expired/wrong issuer/audience/signature rejected; malformed JSON and forged gateway identity rejected','result':'PASS'})
 summary.append({'test':'Shipment create/read; Tracking create/timeline/internal HTTP lookup; PostgreSQL transactional outbox; JSON enums and UTC timestamps','result':'PASS'})
 # Prove writes to application root fail under the actual running UID.
 for service in ['auth','shipment','tracking']:
  name=prefix+'-'+service
  info=json.loads(run('docker','inspect',name))[0]
  assert info['HostConfig']['ReadonlyRootfs'] and info['Config']['User']=='1654'
  marker=out/'readonly-negative.txt';marker.write_text('disposable readonly probe')
  result=subprocess.run(['docker','cp',str(marker),name+':/app/.readonly-negative'],capture_output=True,text=True)
  assert result.returncode!=0 and 'read-only' in (result.stdout+result.stderr).lower(), 'Root filesystem accepted a write'
  summary.append({'service':service,'test':'negative write to /app rejected by read-only filesystem','result':'PASS'})
  (out/(service+'-runtime.log')).write_text(run('docker','logs',name))
 print(json.dumps(summary));(out/'runtime-results.json').write_text(json.dumps(summary,indent=2)+'\n')
finally:
 conn.close() if 'conn' in locals() else None
 for name in reversed(created):subprocess.run(['docker','rm','-fv',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if network_created:subprocess.run(['docker','network','rm',network],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
