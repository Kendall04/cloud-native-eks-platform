"""Local review plans for verified DEMO/AWS packages. No AWS client/effects."""
import argparse
import json
from pathlib import Path
import re
import sys
import package_static as static

ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / 'infra/portfolio/frontend-static'
BUCKET = 'cloud-native-platform-341936017254-portfolio-demo'
EXECUTOR = 'arn:aws:iam::341936017254:user/cnp-cert-admin'
RESOURCES = ['aws_s3_bucket.site', 'aws_s3_bucket_public_access_block.site',
    'aws_s3_bucket_ownership_controls.site', 'aws_s3_bucket_server_side_encryption_configuration.site',
    'aws_s3_bucket_versioning.site', 'aws_s3_bucket_policy.site',
    'aws_cloudfront_origin_access_control.site', 'aws_cloudfront_function.routes',
    'aws_cloudfront_response_headers_policy.site', 'aws_cloudfront_distribution.site']

def digest(value):
    static.require(type(value) is str and re.fullmatch(static.HEX, value), 'Exact SHA256 required')
    return value

def object_key(path, release):
    return path if path.startswith(('assets/', 'architecture-assets/')) else 'releases/' + release + '/' + path

def api_from_environment(contract):
    # Validate only; never call environment.generate/output or read state/AWS.
    sys.path.insert(0, str(ROOT/'scripts/bootstrap'))
    from environment import validate_contract
    validate_contract(contract, 'dev', ready=True)
    static.require((contract['accountId'],contract['region'],contract['project'],contract['clusterName']) ==
                   ('341936017254','us-east-1','cloud-native-platform','logistics-platform-dev'), 'Wrong EKS environment')
    return contract['apiGateway']['endpoint'].removeprefix('https://')

def review_plan(data, expected_sha, operation='prepare', current_release=None, mode='demo', api_domain=None):
    digest(expected_sha)
    static.require(mode in ('demo', 'aws'), 'Explicit verified package mode required')
    static.require(api_domain is None or mode == 'aws' and type(api_domain) is str and
                   re.fullmatch(r'[a-z0-9]{10}\.execute-api\.us-east-1\.amazonaws\.com', api_domain),
                   'API routing requires AWS mode and exact existing us-east-1 HTTP API hostname')
    static.require(operation in ('prepare', 'promote', 'rollback'), 'Unknown local plan operation')
    if operation == 'prepare':
        static.require(current_release is None, 'Initial preparation cannot adopt an existing host')
    else:
        digest(current_release)
        static.require(current_release != expected_sha, 'Selection must change the expected current release')
    manifest = static.validate_package(data, expected_sha, mode)
    resources = RESOURCES + (['aws_cloudfront_function.api[0]', 'aws_cloudfront_response_headers_policy.api[0]'] if api_domain else [])
    inputs = dict(release_sha256=expected_sha, site_mode=mode, api_enabled=api_domain is not None,
                  api_domain_name=api_domain, execution_principal_arn=EXECUTOR)
    rows = [dict(key=object_key(f['path'], expected_sha), sha256=f['sha256'], bytes=f['bytes'],
                 mediaType=f['mediaType'], cacheControl=f['cacheControl'], ifNoneMatch='*') for f in manifest['files']]
    receipt = static.canonical(manifest)
    rows.append(dict(key='releases/'+expected_sha+'/manifest.json', sha256=static.sha(receipt), bytes=len(receipt),
                     mediaType='application/json', cacheControl='no-cache', ifNoneMatch='*'))
    static.require(len({r['key'] for r in rows}) == len(rows), 'Duplicate hosting key')
    return {
        'classification': 'LOCAL_REVIEW_ONLY_NO_DEPLOYMENT_OR_SPENDING_AUTHORITY',
        'operation': operation, 'mode': mode, 'accountId': '341936017254', 'region': 'us-east-1',
        'owner': 'Kendall', 'proposedExecutor': {'arn': EXECUTOR, 'profile': 'cnp-cert-dev',
            'status': 'PROPOSED_EXISTING_PRINCIPAL_NOT_ASSUMED_OR_AUTHORIZED',
            'limitation': 'Observed AdministratorAccess is broader than these operations. No grant/role/key is installed; exact normal-tool payload approval remains required.',
            'operationsReference': 'docs/operations/frontend-hosting-owner-proposal.json'},
        'bucket': BUCKET, 'ownership': 'NEW_SEPARATE_PORTFOLIO_OWNER_NOT_EKS_OR_EXISTING_BUCKET_ADOPTION',
        'artifact': {'sha256': expected_sha, 'bytes': len(data), 'sourceBaseCommit': manifest['sourceBaseCommit']},
        'expectedCurrentReleaseSha256': current_release, 'targetReleaseSha256': expected_sha,
        'freshBindingsRequired': ['Recheck the proposed existing caller ARN equals STS; Kendall must approve concrete effects. Required Terraform execution_principal_arn has no default; matching is not authority.',
            'Bucket ownership/generation and dedicated-name availability; do not adopt an existing bucket',
            'Actual distribution ARN/ID, function ARN and current ETag/state lineage/serial from this independent owner',
            'Observed current release equals expectedCurrentReleaseSha256 before promotion/rollback',
            'Every target object content/type/cache metadata and VersionId verified after immutable writes; byte conflict blocks',
            'Exact reviewed source/plan hashes, responsible principal and concrete human/platform effect approvals',
            'Existing retention owner/start/deadline must be bound unchanged on selection; promotion/rollback never renews retention or budget',
            'When API is enabled, hostname must equal the captured account/region HTTP API owner output and $default stage; regex alone never establishes ownership'],
        'orderedPersistentEffects': [
            {'step': 'prepare_disabled_infrastructure', 'onlyForInitialCreate': True, 'resources': resources,
             'terraformInputs': dict(inputs, distribution_enabled=False),
             'note': 'Create only these controls/functions/policies/disabled distribution; optional origin references existing HTTP API, never creates it. No IAM, domain, ACM, KMS or AWS backend'},
            {'step': 'immutable_object_publication', 'objects': rows,
             'precondition': 'Put with If-None-Match=*; on existing key verify bytes AND content/cache metadata, never overwrite or replace metadata silently. Retain old immutable keys/release entries.'},
            {'step': 'verify_before_selection', 'precondition': 'Complete target inventory/hash/mode verification; local validation is not evidence of cloud upload'},
            {'step': 'select_verified_release', 'terraformInputs': dict(inputs, distribution_enabled=True),
             'conditionalCreationsWhenApiWasDisabled': ['aws_cloudfront_function.api[0]', 'aws_cloudfront_response_headers_policy.api[0]'] if api_domain and operation != 'prepare' else [],
             'conditionalRemovalsWhenPreviousApiWasEnabled': [] if api_domain or operation == 'prepare' else ['existing-http-api origin and /api behaviors', 'aws_cloudfront_function.api[0]', 'aws_cloudfront_response_headers_policy.api[0]'],
             'precondition': 'Fresh expected-current release, prior API configuration, CloudFront ETag/state binding; update+publish selecting this SHA. Observe deployed configuration/health before success; edge propagation is not atomic. Before backend retirement select verified DEMO, remove API origin/behaviors and confirm deployed 503; old AWS tabs never become DEMO data.'}
        ],
        'persistentConfiguration': {
            'terraformRoot': 'infra/portfolio/frontend-static', 'resourceAddresses': resources, 'executionPrincipalArn': EXECUTOR,
            'bucket': {'name': BUCKET, 'newDedicatedOwner': True, 'versioning': 'Enabled', 'ownership': 'BucketOwnerEnforced', 'publicAccessBlockAll': True, 'encryption': 'AES256_SSE_S3', 'websiteEndpoint': False, 'forceDestroy': False},
            'origin': {'type': 'privateS3RegionalREST', 'oac': 'always_SigV4_HTTPS', 'principal': 'cloudfront.amazonaws.com', 'grant': 's3:GetObject', 'sourceArn': 'MUST_BE_FRESH_EXACT_DISTRIBUTION_ARN', 'objectNamespaces': ['releases/*','assets/*','architecture-assets/*']},
            'edge': {'oneDistribution': True, 'priceClass': 'PriceClass_100', 'customDomainOrACM': False, 'defaultCertificate': 'cloudfront.net', 'viewerPolicy': 'redirect-to-https', 'apiOrigin': api_domain, 'cookieForwarding': False, 'queryForwarding': False, 'minTTL': 0, 'function': 'viewer-request selects exactSHA and denies API/origin writes', 'functionCodeSha256': static.sha((INFRA/'routes.js.tftpl').read_bytes().replace(b'\r\n',b'\n')), 'responseHeaders': 'Exact CSP/HSTS/nosniff/SAMEORIGIN/no-referrer settings in the hash-bound main.tf', 'missingOrigin403': 'Preserve origin status/body; zero configured error TTL, no custom page or SPA HTML'},
            'api': None if api_domain is None else {'existingOrigin': api_domain, 'httpsOnly': True, 'originMinimumTls': 'TLSv1.2',
                'originPath': '', 'orderedPaths': ['/api','/api/*'], 'stripPrefixExactlyOnce': '/api',
                'cachePolicyId': '4135ea2d-6df8-44a3-9df3-4b5a84be39ad',
                'originRequestPolicyId': 'b689b0a8-53d0-40ab-baf2-68738e2966ac',
                'forward': 'Authorization/query/body; omit viewer Host, cookies and x-platform-*; Gateway remains authoritative',
                'responses': 'Preserve origin status/body; Cache-Control no-store; supported error-cache minima zero; no custom error page or SPA fallback'},
            'iamRolesOrCredentialsOrCustomKeys': []
        },
        'behavior': {'site': 'Explicit '+mode+' package; DEMO is synthetic, AWS never falls back to synthetic data',
            'routing': 'Known SPA routes -> releases/<selectedSHA>/index.html; versioned assets remain global immutable keys for old tabs; unknown paths/assets never become index HTML',
            'api': 'Existing HTTPS HTTP API with bearer/query preservation and no caching' if api_domain else 'No API origin/behaviors; default function returns 503, including old AWS tabs. DEMO client never requests API.',
            'cache': 'Static origin forwards no cookies/query; API forwards query/bearer, no cookies, caching disabled. HTML/build/manifest no-cache; fingerprinted assets one-year immutable. No invalidation or automatic pruning required.',
            'headers': 'HTTPS redirect/private S3 OAC; optional existing API HTTPS origin. CSP permits same-origin JSON/API; credentials remain runtime memory, never package/config',
            'viewerCertificateLimitation': 'Default cloudfront.net certificate requires AWS TLSv1 security policy despite modern browser TLS negotiation. No false TLS1.2 floor; DEMO and especially authenticated AWS mode require explicit TLS/CSP review before publication. A custom TLS floor needs a separately reviewed owned hostname/certificate.'},
        'retentionProposal': {'days': 30, 'startAt': None, 'reviewOrRetireAt': None, 'owner': 'Kendall',
            'clock': 'Starts only at observed activation in UTC; review/retire at activation+30 days, never at preparation or promotion',
            'scope': 'This host and all approved DEMO versions, independent of EKS; preserve old assets during the trial; no automatic lifecycle purge, deployment cleanup or renewal',
            'allowanceUsd': 1, 'approved': False, 'priceSource': 'docs/evidence/eks-readonly-preflight-20261021.json',
            'usageAssumptions': 'At most100MiB stored,1GB US-edge delivery,10000 HTTPS requests;aboutUSD0.10 before origin operations/other regions/tax; edge-function invocation charge still needs pricing review; no free-tier assumption or enforced cap'},
        'retirementPreparation': {'owner': 'Same separate hosting owner; existing EKS18-state executor does not own this root',
            'steps': ['Export exact identities/release manifests/object VersionIds and independent state/evidence outside the host',
                'Freshly review retirement inputs, disable distribution and verify deployed-disabled state; do not infer completion from timeout',
                'List all dedicated-bucket versions/delete markers/multipart uploads completely; any foreign/unexpected object blocks. Approve exact observed VersionIds/upload IDs; no blind prefix purge',
                'Remove only those reviewed owned versions/markers/uploads; force_destroy remains false',
                'Review/apply normal owner destroy for the ten captured resources; verify CloudFront/OAC/function/header-policy and bucket absence; AccessDenied remains UNKNOWN',
                'Preserve independent local state/receipts until owner-approved evidence expiry; no EKS/RDS/ECS/backend/old-secret/key deletion'],
            'freshIdsBeforeDelete': True, 'automaticDeletion': False},
        'effectPermissionsNotGranted': {
            'infrastructureOwner': 'Exact reviewed S3 bucket creation/configuration/policy and CloudFront distribution/OAC/function/headers lifecycle actions; new ARNs must be captured after create, creation APIs may need unscoped resources. Do not attach the Private CD delivery role or treat preflight AdministratorAccess as this design.',
            'publicationOwner': 's3:PutObject/GetObject/GetObjectVersion on only the exact planned keys; condition immutable Put with If-None-Match=*; no bucket-wide delete for publication',
            'removalOwner': 'Exact fresh dedicated bucket/version/upload and CloudFront resource cleanup only after complete identity/consumer review; policy JSON/saved plan and normal tool approvals required'},
        'sourceSha256': {str(p.relative_to(ROOT)).replace('\\','/'): static.sha(p.read_bytes().replace(b'\r\n',b'\n'))
                        for p in (INFRA/'main.tf', INFRA/'routes.js.tftpl', INFRA/'api-routes.js', INFRA/'.terraform.lock.hcl', ROOT/'frontend/scripts/package_static.py', ROOT/'scripts/bootstrap/environment.py', ROOT/'scripts/bootstrap/environment.schema.json', Path(__file__))},
        'limits': ['No AWS read/write/client, upload, plan-apply, provider installation or credentials in this command',
                   'No automatic release controller, hosting retention scheduler, live API proof, remote rollback guarantee or budget enforcement',
                   'ModeB preference is not IAM, security-exception, publication or USD approval']
    }

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--operation',choices=('prepare','promote','rollback'),default='prepare')
    parser.add_argument('--current-release')
    parser.add_argument('--mode',choices=('demo','aws'),default='demo')
    parser.add_argument('--api-domain')
    parser.add_argument('--environment-contract',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    static.require(args.artifact.stat().st_size <= static.MAX_BYTES, 'Package too large')
    if args.api_domain:
        static.require(args.environment_contract is not None, 'Existing final environment contract is required for API routing')
        contract=static.parse_json(args.environment_contract.read_bytes())
        static.require(api_from_environment(contract)==args.api_domain, 'API hostname differs from existing final contract')
    else:
        static.require(args.environment_contract is None, 'Offline hosting does not retain a runtime contract')
    plan=review_plan(args.artifact.read_bytes(),args.sha256,args.operation,args.current_release,args.mode,args.api_domain)
    if args.api_domain:
        plan['apiEnvironmentContractSha256']=static.sha(static.canonical(contract))
    with args.output.open('x',encoding='utf-8',newline='\n') as out:out.write(json.dumps(plan,indent=2)+'\n')
    print(json.dumps({'scope':'LOCAL_ONLY','mode':args.mode,'operation':args.operation,'objects':len(plan['orderedPersistentEffects'][1]['objects']),'artifactSha256':args.sha256}))
if __name__=='__main__':main()
