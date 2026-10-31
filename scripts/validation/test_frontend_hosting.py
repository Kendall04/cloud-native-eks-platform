"""Small offline retained-DEMO plan checks; no SDK, build or network."""
import copy,json,pathlib,re,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'frontend/scripts'))
import package_static as static
import hosting_plan as host

def fixture(mode='demo'):
 files={'index.html':b'<html><script src="/assets/app-test.js"></script><link href="/assets/app-test.css"></html>',
        'assets/app-test.js':b'window.fixture="DEMO";', 'assets/app-test.css':b'body{}'}
 for name in static.ARCHITECTURE:
  data=('fixture '+name).encode();files['architecture-assets/'+static.sha(data)+'/'+name]=data
 receipt={'schemaVersion':1,'configuration':{'mode':mode,'apiBase':'/api'},'toolchain':{'node':'22.22.0'},
          'files':{n:{'sha256':static.sha(b),'bytes':len(b)} for n,b in files.items()}}
 files['frontend-build.json']=static.canonical(receipt)
 return static.package_site(files,mode,'a'*40)[0]
class Hosting(unittest.TestCase):
 def setUp(self):self.data=fixture();self.sha=static.sha(self.data)
 def test_prepare_is_review_only_disabled_then_verified_enable(self):
  p=host.review_plan(self.data,self.sha)
  self.assertEqual(p['mode'],'demo');self.assertIn('NO_DEPLOYMENT',p['classification'])
  self.assertEqual(len(p['orderedPersistentEffects'][0]['resources']),10)
  self.assertFalse(p['orderedPersistentEffects'][0]['terraformInputs']['distribution_enabled'])
  self.assertFalse(p['retentionProposal']['approved']);self.assertIsNone(p['retentionProposal']['startAt'])
  self.assertFalse(p['retirementPreparation']['automaticDeletion'])
 def test_versioned_keys_keep_old_tab_assets_independent(self):
  rows=host.review_plan(self.data,self.sha)['orderedPersistentEffects'][1]['objects']
  self.assertEqual(next(r['key'] for r in rows if r['key'].endswith('index.html')),'releases/'+self.sha+'/index.html')
  for r in rows:
   self.assertEqual(r['ifNoneMatch'],'*')
   if r['key'].startswith(('assets/','architecture-assets/')):self.assertIn('immutable',r['cacheControl'])
   else:self.assertEqual(r['cacheControl'],'no-cache')
  self.assertEqual(len({r['key'] for r in rows}),len(rows))
 def test_aws_and_mixed_mode_are_rejected(self):
  aws=fixture('aws')
  with self.assertRaises(ValueError):host.review_plan(aws,static.sha(aws))
  files=static.read_tar(self.data)
  manifest=json.loads(files['manifest.json']);manifest['configuration']['mode']='aws'
  files['manifest.json']=static.canonical(manifest)
  files['checksums.sha256']=static.checksums({n:b for n,b in files.items() if n!='checksums.sha256'})
  mixed=static.archive(files)
  with self.assertRaises(ValueError):host.review_plan(mixed,static.sha(mixed))
 def test_explicit_aws_package_uses_only_existing_regional_api(self):
  raw=fixture('aws');sha=static.sha(raw);domain='abc123def4.execute-api.us-east-1.amazonaws.com'
  p=host.review_plan(raw,sha,mode='aws',api_domain=domain)
  self.assertEqual(len(p['persistentConfiguration']['resourceAddresses']),12)
  self.assertEqual(p['persistentConfiguration']['api']['existingOrigin'],domain)
  self.assertEqual(p['persistentConfiguration']['api']['originPath'],'')
  promote=host.review_plan(raw,sha,'promote',self.sha,mode='aws',api_domain=domain)
  self.assertEqual(len(promote['orderedPersistentEffects'][-1]['conditionalCreationsWhenApiWasDisabled']),2)
  for bad in ('https://'+domain,domain+'/stage','evil.example.invalid','abc123def4.execute-api.us-west-2.amazonaws.com'):
   with self.subTest(bad=bad),self.assertRaises(ValueError):host.review_plan(raw,sha,mode='aws',api_domain=bad)
  with self.assertRaises(ValueError):host.review_plan(self.data,self.sha,api_domain=domain)
 def test_aws_offline_and_reviewed_rollback_to_demo_remove_api(self):
  raw=fixture('aws');sha=static.sha(raw)
  offline=host.review_plan(raw,sha,mode='aws')
  self.assertIsNone(offline['persistentConfiguration']['api'])
  self.assertFalse(offline['orderedPersistentEffects'][-1]['terraformInputs']['api_enabled'])
  p=host.review_plan(self.data,self.sha,'rollback',sha)
  self.assertEqual(p['mode'],'demo');self.assertIsNone(p['persistentConfiguration']['api'])
  self.assertEqual(p['expectedCurrentReleaseSha256'],sha)
  self.assertEqual(len(p['orderedPersistentEffects'][-1]['conditionalRemovalsWhenPreviousApiWasEnabled']),3)
  self.assertEqual(p['owner'],'Kendall');self.assertEqual(p['proposedExecutor']['arn'],host.EXECUTOR)
 def test_api_binding_reuses_final_environment_contract_and_rejects_foreign(self):
  sys.path.insert(0,str(ROOT/'scripts/bootstrap'))
  from test_r2 import contract_fixture
  c=json.loads(json.dumps(contract_fixture()).replace('999988887777','341936017254').replace('r2-fixture','cloud-native-platform'))
  c['clusterName']='logistics-platform-dev'
  c['alb']['discoveryTags']['elbv2.k8s.aws/cluster']=c['clusterName']
  c['alb']['arn']='arn:aws:elasticloadbalancing:us-east-1:341936017254:loadbalancer/app/offline/abcdef123456789a'
  c['alb']['listenerArn']='arn:aws:elasticloadbalancing:us-east-1:341936017254:listener/app/offline/abcdef123456789a/abcdef123456789b'
  c['apiGateway']['apiId']='abc123def4';c['apiGateway']['endpoint']='https://abc123def4.execute-api.us-east-1.amazonaws.com'
  self.assertEqual(host.api_from_environment(c),'abc123def4.execute-api.us-east-1.amazonaws.com')
  for key,value in (('accountId','999988887777'),('region','us-west-2'),('clusterName','foreign-cluster')):
   bad=copy.deepcopy(c);bad[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):host.api_from_environment(bad)
  c['alb']['arn']=None;c['alb']['listenerArn']=None
  with self.assertRaises(ValueError):host.api_from_environment(c)
 def test_tamper_and_wrong_expected_hash_rejected(self):
  for data,h in ((self.data+b'tamper',self.sha),(self.data,'0'*64)):
   with self.subTest(hash=h),self.assertRaises(ValueError):host.review_plan(data,h)
  for missing in ('site/index.html','site/frontend-build.json','site/assets/app-test.js'):
   files=static.read_tar(self.data);del files[missing]
   files['checksums.sha256']=static.checksums({n:b for n,b in files.items() if n!='checksums.sha256'})
   raw=static.archive(files)
   with self.subTest(missing=missing),self.assertRaises(ValueError):host.review_plan(raw,static.sha(raw))
 def test_promote_and_rollback_require_exact_distinct_expected_current(self):
  for op in ('promote','rollback'):
   p=host.review_plan(self.data,self.sha,op,'b'*64)
   self.assertEqual(p['expectedCurrentReleaseSha256'],'b'*64)
   self.assertEqual(p['targetReleaseSha256'],self.sha)
   self.assertTrue(p['freshBindingsRequired'])
   for current in (None,'bad',self.sha):
    with self.subTest(op=op,current=current),self.assertRaises(ValueError):host.review_plan(self.data,self.sha,op,current)
 def test_initial_adoption_or_unknown_operation_rejected(self):
  with self.assertRaises(ValueError):host.review_plan(self.data,self.sha,'prepare','b'*64)
  with self.assertRaises(ValueError):host.review_plan(self.data,self.sha,'apply')
 def test_malicious_package_member_is_not_admitted(self):
  files=static.read_tar(self.data);files['site/../../escape']=b'bad'
  raw=static.archive(files)
  with self.assertRaises(ValueError):host.review_plan(raw,static.sha(raw))
 def test_origin_error_passthrough_has_no_status_or_spa_replacement(self):
  source=(host.INFRA/'main.tf').read_text()
  blocks=re.findall(r'custom_error_response"?\s*\{([^}]+)\}',source)
  self.assertEqual(len(blocks),2)
  self.assertRegex(blocks[0],r'error_code\s*=\s*403\b')
  self.assertRegex(blocks[0],r'error_caching_min_ttl\s*=\s*0\b')
  # AWS requires ResponsePagePath whenever ResponseCode is supplied. Preserve
  # the origin error instead of inventing a custom page or using the SPA index.
  for block in blocks:
   self.assertNotRegex(block,r'\bresponse_code\s*=')
   self.assertNotRegex(block,r'\bresponse_page_path\s*=')
 def test_infra_has_no_backend_origin_secret_key_or_force_purge(self):
  source=(host.INFRA/'main.tf').read_text()
  for token in ('aws_kms_key','aws_iam_role','aws_acm_certificate','aws_route53','force_destroy = true'):
   self.assertNotIn(token,source)
  self.assertIn('signing_behavior                  = "always"',source)
  self.assertIn('cloudfront_default_certificate = true',source)
  self.assertIn('default = false',source)
  self.assertNotIn('response_page_path',source)
if __name__=='__main__':unittest.main()
