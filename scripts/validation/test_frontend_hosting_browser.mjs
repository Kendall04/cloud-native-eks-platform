// Real cached DEMO bundle, exact edge function and proposed headers; loopback only.
import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const [objects,infra,release,playwrightIndex,mode='demo',apiMode='offline']=process.argv.slice(2);
assert(['demo','aws'].includes(mode));assert(['offline','online'].includes(apiMode));assert(mode==='aws'||apiMode==='offline');
assert.match(release,/^[a-f0-9]{64}$/);
const {chromium,expect}=await import(pathToFileURL(playwrightIndex).href);
const metadata=JSON.parse(readFileSync(resolve(objects,'object-metadata.json'),'utf8'));
const context=vm.createContext({});
vm.runInContext(readFileSync(resolve(infra,'routes.js.tftpl'),'utf8').replaceAll('${release_sha256}',release),context);
const apiContext=vm.createContext({});vm.runInContext(readFileSync(resolve(infra,'api-routes.js'),'utf8'),apiContext);
const bearer='synthetic-memory-access-token';
const upstream=[];
const hcl=readFileSync(resolve(infra,'main.tf'),'utf8');
const csp=JSON.parse(hcl.match(/content_security_policy = ("[^\n]+")/)[1]);
const server=createServer(async(req,res)=>{
 try{
  const url=new URL(req.url,'http://127.0.0.1');
  const isApi=apiMode==='online'&&(url.pathname==='/api'||url.pathname.startsWith('/api/'));
  const r=(isApi?apiContext:context).handler({request:{uri:url.pathname,method:req.method,headers:Object.fromEntries(Object.entries(req.headers).map(([k,v])=>[k,{value:String(v)}])),cookies:{},querystring:Object.fromEntries([...url.searchParams].map(([k,v])=>[k,{value:v}]))}});
  res.setHeader('Content-Security-Policy',csp);res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('X-Frame-Options','SAMEORIGIN');res.setHeader('Referrer-Policy','no-referrer');
  if(r.statusCode){res.statusCode=r.statusCode;for(const[k,v]of Object.entries(r.headers))res.setHeader(k,v.value);res.end(r.body);return;}
  if(isApi){
   res.setHeader('Cache-Control','no-store');res.setHeader('Content-Type','application/json');
   assert(!r.headers.cookie);assert.equal(Object.keys(r.cookies).length,0);assert(!Object.keys(r.headers).some(k=>k.startsWith('x-platform-')));
   upstream.push(r.uri);
   let value;
   if(r.uri==='/auth/login'&&r.method==='POST'){
    let body='';for await(const chunk of req){body+=chunk;assert(body.length<=16384);}
    const input=JSON.parse(body);assert.equal(input.email,'browser@example.invalid');assert.equal(input.password,'synthetic-input');
    value={accessToken:bearer,accessTokenExpiresAt:new Date(Date.now()+60000).toISOString(),refreshToken:'synthetic-unused-refresh-token',refreshTokenExpiresAt:new Date(Date.now()+120000).toISOString()};
   }else{
    assert.equal(r.headers.authorization?.value,'Bearer '+bearer);
    if(r.uri==='/auth/me')value={userId:'10000000-0000-4000-8000-000000000001',email:'browser@example.invalid',userName:'browser-fixture',firstName:'Browser',lastName:'Fixture',roles:['USER'],isActive:true,createdAt:'2026-10-01T08:00:00Z'};
    else if(r.uri==='/shipments'){assert.equal(r.querystring.PageNumber.value,'1');value={items:[],pageNumber:1,pageSize:20,totalCount:0};}
    else{res.statusCode=404;value={error:'No fixture route'};}
   }
   res.end(JSON.stringify(value));return;
  }
  const key=r.uri.slice(1);const info=metadata[key];
  // A private S3 origin without ListBucket may return 403 for a missing key.
  // Preserve that error rather than inventing a status rewrite or SPA page.
  if(!info){res.statusCode=403;res.setHeader('Content-Type','application/xml');res.end('<Error><Code>AccessDenied</Code></Error>');return;}
  res.setHeader('Content-Type',info.mediaType);res.setHeader('Cache-Control',info.cacheControl);
  res.end(req.method==='HEAD'?undefined:readFileSync(resolve(objects,key)));
 }catch{res.statusCode=500;res.end('Local fixture failed');}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const origin='http://127.0.0.1:'+server.address().port;
let browser;
try{
 browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 const api=[];const external=[];const errors=[];
 page.on('request',r=>{const u=new URL(r.url());if(u.pathname==='/api'||u.pathname.startsWith('/api/'))api.push(r.url());if(u.protocol.startsWith('http')&&u.origin!==origin)external.push(r.url());});
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(origin+'/demo');
 if(mode==='aws'){
  await expect(page.getByText('AWS API',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:/Enter demo/})).toHaveCount(0);
  await page.getByLabel('Email',{exact:true}).fill('browser@example.invalid');
  await page.getByLabel('Password',{exact:true}).fill('synthetic-input');
  await page.getByRole('button',{name:/^Sign in/}).click();
  if(apiMode==='offline'){
   await expect(page.getByRole('alert')).toContainText('A required service is unavailable.');
   await expect(page.getByText(/DEMO-2026|LOCAL API/)).toHaveCount(0);
   assert.equal(upstream.length,0);
  }else{
   await expect(page.getByText('No shipments yet',{exact:true})).toBeVisible();
   assert.deepEqual(upstream,['/auth/login','/auth/me','/shipments']);
   assert.deepEqual(await page.evaluate(()=>({...localStorage,...sessionStorage})),{});
   assert.deepEqual(await page.context().cookies(),[]);
   await page.reload();await expect(page.getByRole('button',{name:/^Sign in/})).toBeVisible();
   assert.equal(upstream.length,3,'Reload must lose memory bearer');
  }
  assert.deepEqual(external,[]);assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',scope:'LOCAL_CACHED_AWS_PACKAGE_EDGE_MODEL_NO_CLOUD',mode,apiMode,upstreamCalls:upstream.length,externalRequests:external.length,pageErrors:errors.length,noDemoFallback:true,apiSameOrigin:true}));
  await page.close();
 }else{
 await expect(page.getByText(/DEMO.*SYNTHETIC DATA/)).toBeVisible();
 await page.getByRole('button',{name:/Enter demo workspace/}).click();
 await expect(page.getByText('DEMO-2026-001',{exact:true})).toBeVisible();
 await page.getByText('DEMO-2026-001',{exact:true}).click();
 await expect(page.getByText('Regional hub')).toBeVisible();
 const diagrams=[['platform','Platform architecture'],['networking','Private networking'],['event-processing','Reliable event processing'],['private-cd','Private delivery'],['lifecycle','Infrastructure lifecycle']];
 for(const[id,title]of diagrams){
  await page.goto(origin+'/architecture/'+id);
  await expect(page.getByTitle(title+' interactive diagram')).toBeVisible();
  const frame=page.frameLocator('iframe');
  await frame.locator('[data-view=reset]').waitFor();
  await frame.getByRole('button',{name:'Zoom in',exact:true}).click();
 }
 assert.deepEqual(api,[],'DEMO must not request API');assert.deepEqual(external,[],'No external requests');assert.deepEqual(errors,[],'No runtime errors under proposed CSP');
 const missing=await fetch(origin+'/assets/missing.js');assert.equal(missing.status,403);assert(!((missing.headers.get('content-type')||'').includes('html')));assert((await missing.text()).includes('AccessDenied'));
 const unavailable=await fetch(origin+'/api/shipments',{method:'POST'});assert.equal(unavailable.status,503);assert.equal(unavailable.headers.get('cache-control'),'no-store');
 console.log(JSON.stringify({status:'PASS',scope:'LOCAL_CHROME_CACHED_ARTIFACT_NO_CLOUD',syntheticDemoFlow:true,interactiveDiagrams:5,apiRequests:api.length,externalRequests:external.length,pageErrors:errors.length,originMissingAsset403Preserved:true,apiUnavailable503:true,headersFromTerraform:true}));
 }
}finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
