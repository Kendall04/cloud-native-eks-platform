// Tests execute the exact CloudFront function text; no npm install or AWS.
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {dirname,resolve} from 'node:path';
const file=process.argv[2];
const release='a'.repeat(64);
const source=readFileSync(file,'utf8').replaceAll('${release_sha256}',release);
const context=vm.createContext({});vm.runInContext(source,context);
let count=0;
const run=(uri,method='GET')=>context.handler({request:{uri,method,headers:{},querystring:{}}});
for(const uri of ['/','/demo','/demo/shipments','/demo/shipments/new','/demo/shipments/demo-1','/demo/tracking','/architecture','/architecture/platform','/architecture/networking','/architecture/event-processing','/architecture/private-cd','/architecture/lifecycle','/architecture/scaling','/architecture/security','/architecture/evidence']){
 assert.equal(run(uri).uri,'/releases/'+release+'/index.html',uri);count++;
}
for(const uri of ['/assets/app-abc.js','/assets/app-abc.css','/architecture-assets/'+'b'.repeat(64)+'/platform.json']){assert.equal(run(uri).uri,uri);count++;}
for(const method of ['GET','HEAD','OPTIONS','POST','PUT','PATCH','DELETE']){
 const r=run('/api/shipments',method);assert.equal(r.statusCode,503);assert.equal(r.headers['cache-control'].value,'no-store');count++;
}
for(const uri of ['/missing','/architecture/not-a-page','/releases/other/index.html','/not.js']){assert.equal(run(uri).statusCode,404);count++;}
for(const uri of ['//evil','/assets/../index.html','/assets/%2e%2e/x','/assets/a\\b','/demo/..']){assert.equal(run(uri).statusCode,400,uri);count++;}
for(const method of ['OPTIONS','POST','PUT','DELETE']){assert.equal(run('/assets/app-abc.js',method).statusCode,405);count++;}
assert.equal(run('/frontend-build.json').uri,'/releases/'+release+'/frontend-build.json');count++;
assert.equal(run('/api','HEAD').body,undefined);count++;
console.log(JSON.stringify({status:'PASS',checks:count,source:'exact CloudFront function rendered with synthetic release',scope:'OFFLINE_NO_AWS'}));
const api=vm.createContext({});vm.runInContext(readFileSync(resolve(dirname(file),'api-routes.js'),'utf8'),api);
let apiChecks=0;
for(const method of ['GET','POST','OPTIONS']){
 const request={uri:'/api/shipments',method,headers:{authorization:{value:'Bearer synthetic-memory-access-token'},cookie:{value:'synthetic'},'x-platform-user-id':{value:'forged'},'x-platform-proxy-secret':{value:'forged'},accept:{value:'application/json'}},cookies:{session:{value:'synthetic'}},querystring:{PageNumber:{value:'2'}}};
 const out=api.handler({request});assert.equal(out.uri,'/shipments');assert.equal(out.headers.authorization.value,'Bearer synthetic-memory-access-token');assert.equal(out.querystring.PageNumber.value,'2');assert.deepEqual(Object.keys(out.cookies),[]);assert(!out.headers.cookie);assert(!out.headers['x-platform-user-id']);assert(!out.headers['x-platform-proxy-secret']);apiChecks+=7;
}
for(const uri of ['/api','/api//shipments','/api/../auth/me','/api/%2fsecret','/apix/me','/api/a\\b']){const r=api.handler({request:{uri,method:'GET',headers:{}}});assert.equal(r.statusCode,400);assert.equal(r.headers['cache-control'].value,'no-store');apiChecks+=2;}
for(const method of ['PUT','PATCH','DELETE','HEAD']){assert.equal(api.handler({request:{uri:'/api/shipments',method,headers:{}}}).statusCode,405);apiChecks++;}
assert.equal(api.handler({request:{uri:'/api/api/auth/me',method:'GET',headers:{}}}).uri,'/api/auth/me');apiChecks++;
console.log(JSON.stringify({status:'PASS',apiChecks,source:'exact API edge function; no gateway identity claims',scope:'OFFLINE_NO_AWS'}));
