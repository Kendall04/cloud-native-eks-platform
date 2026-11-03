"""Closed publication boundary for offline Trivy evidence; never publishes renders."""
import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
import sys

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_FILE = 'security-evidence.json'
CATEGORIES = ('newBlocking', 'expiredBlocking', 'acceptedExisting', 'advisory')
MAX_BYTES = 8 * 1024 * 1024
TEXT = {'type': 'string', 'maxLength': 8192}
DIGEST = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}


def record(properties, required=None):
    return {'type': 'object', 'properties': properties, 'additionalProperties': False,
            'required': list(properties) if required is None else required}


FINDING_FIELDS = ('scope', 'kind', 'target', 'id', 'package', 'installed',
                  'severity', 'fingerprint', 'fixedVersion', 'title')
FINDING = record({**{k: TEXT for k in FINDING_FIELDS},
                  'fingerprint': DIGEST, 'resourceSha256': DIGEST,
                  'evidenceSha256': DIGEST,
                  'severity': {'enum': ['UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']},
                  'kind': {'enum': ['vulnerability', 'misconfiguration']}},
                 [*FINDING_FIELDS, 'resourceSha256'])
SCHEMA = record({
    'schemaVersion': {'const': 1},
    'status': {'enum': ['SCANNED', 'SCAN_FAILED', 'SCAN_NOT_RUN']},
    'scanOutcome': {'enum': ['success', 'failure', 'skipped', 'cancelled']},
    'metadata': record({
        'commit': {'type': 'string', 'pattern': '^[0-9a-f]{40}$'},
        'scannerVersion': TEXT, 'event': TEXT, 'scannedAt': TEXT,
        'workflowRunId': {'type': ['string', 'null']},
        'workflowRunAttempt': {'type': ['string', 'null']},
        'service': {'enum': ['auth', 'shipment', 'tracking']},
        'sbomSha256': DIGEST, 'sbomComponents': {'type': 'integer', 'minimum': 1},
    }, []),
    'findings': {'type': 'array', 'maxItems': 10000, 'items': FINDING},
    'policy': record({k: {'type': 'array', 'items': DIGEST} for k in CATEGORIES}),
    'exceptions': {'type': 'array', 'items': record({
        'fingerprint': DIGEST, 'reason': TEXT,
        'expires': {'type': 'string', 'pattern': '^20[0-9]{2}-[0-9]{2}-[0-9]{2}$'},
    })},
    'diagnostics': {'type': 'array', 'items': {'enum': [
        'SCANNER_OR_POLICY_STEP_FAILED', 'SCAN_STEP_NOT_RUN', 'INCOMPLETE_SCAN_OUTPUT']}},
})


class UnsafeEvidence(ValueError):
    """Category only: never embed a scanner payload in an exception."""


def reject(category):
    raise UnsafeEvidence(category)


class Inspector:
    """Inspect structured content, embedded manifests and bounded Base64 layers."""
    def __init__(self):
        self.nodes = 0
        self.bytes = 0

    def inspect(self, value, depth=0, ancestors=frozenset()):
        self.nodes += 1
        if depth > 24 or self.nodes > 200000:
            reject('CONTENT_LIMIT')
        if isinstance(value, (dict, list)):
            if id(value) in ancestors:
                reject('CYCLIC_CONTENT')
            ancestors = ancestors | {id(value)}
        if isinstance(value, dict):
            if value.get('kind') == 'Secret' and (value.get('data') or value.get('stringData')):
                reject('KUBERNETES_SECRET')
            for key, item in value.items():
                if not isinstance(key, str):
                    reject('NON_STRING_KEY')
                normalized = re.sub('[^a-z0-9]', '', key.lower())
                if normalized in {'tlskey', 'privatekey', 'stringdata', 'password',
                                  'clientsecret', 'awssecretaccesskey', 'awssessiontoken'} and item:
                    reject('PRIVATE_FIELD')
                self.inspect(key, depth + 1, ancestors)
                self.inspect(item, depth + 1, ancestors)
        elif isinstance(value, list):
            for item in value:
                self.inspect(item, depth + 1, ancestors)
        elif isinstance(value, str):
            self.text(value, depth, ancestors)
        elif value is not None and not isinstance(value, (bool, int, float)):
            reject('UNSUPPORTED_VALUE')

    def text(self, text, depth=0, ancestors=frozenset()):
        self.bytes += len(text.encode('utf-8'))
        if depth > 24 or self.bytes > MAX_BYTES * 4:
            reject('CONTENT_LIMIT')
        if re.search(r'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----', text):
            reject('PRIVATE_KEY')
        patterns = (r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
                    r'\bgh[pousr]_[A-Za-z0-9]{30,}\b',
                    r'github_pat_[A-Za-z0-9_]{30,}',
                    r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b',
                    r'(?i)X-Amz-(?:Signature|Credential)=')
        if any(re.search(p, text) for p in patterns):
            reject('CREDENTIAL_PATTERN')
        # Scanner code excerpts can contain a whole manifest or individual fields.
        if re.search(r'(?i)(?:kind\s*:\s*Secret\b|tls\.key\s*[:=]|stringData\s*:)', text):
            reject('SECRET_MANIFEST_FRAGMENT')
        if text.lstrip().startswith(('{', '[')):
            try:
                embedded = json.loads(text)
            except (ValueError, RecursionError):
                embedded = None
            if isinstance(embedded, (dict, list)):
                self.inspect(embedded, depth + 1, ancestors)
        # Decode complete Base64 values and long tokens embedded in scanner strings.
        compact = re.sub(r'\s+', '', text)
        candidates = set(re.findall(r'[A-Za-z0-9+/_-]{32,}={0,2}', text))
        if len(compact) >= 16 and re.fullmatch(r'[A-Za-z0-9+/_-]+={0,2}', compact):
            candidates.add(compact)
        for token in candidates:
            if len(token) > MAX_BYTES:
                reject('CONTENT_LIMIT')
            try:
                decoded = base64.b64decode(token + '=' * (-len(token) % 4),
                                           altchars=b'-_', validate=True).decode('utf-8')
            except (ValueError, UnicodeError, binascii.Error):
                continue
            if decoded and decoded != text:
                self.text(decoded, depth + 1, ancestors)


def inspect_document(text):
    """For tests/reviewed JSON or YAML, including manifests embedded in strings."""
    inspector = Inspector()
    inspector.text(text)
    try:
        documents = list(yaml.safe_load_all(text))
    except (yaml.YAMLError, RecursionError):
        reject('MALFORMED_DOCUMENT')
    for doc in documents:
        inspector.inspect(doc)


def unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            reject('DUPLICATE_JSON_KEY')
        value[key] = item
    return value


def load_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        reject('UNEXPECTED_INPUT_FILE')
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeError, RecursionError):
        reject('MALFORMED_JSON')


def validate_report(report):
    if list(Draft202012Validator(SCHEMA).iter_errors(report)):
        reject('PUBLIC_SCHEMA')
    Inspector().inspect(report)
    fingerprints = [f['fingerprint'] for f in report['findings']]
    classified = [f for category in CATEGORIES for f in report['policy'][category]]
    if sorted(fingerprints) != sorted(classified):
        reject('POLICY_FINDING_MISMATCH')
    known = {}
    for finding in report['findings']:
        fp = finding['fingerprint']
        if fp in known and known[fp] != finding:
            reject('FINGERPRINT_COLLISION')
        known[fp] = finding
    accepted = set(report['policy']['acceptedExisting'] + report['policy']['expiredBlocking'])
    exceptions = [e['fingerprint'] for e in report['exceptions']]
    if len(set(exceptions)) != len(exceptions) or set(exceptions) != accepted:
        reject('EXCEPTION_MISMATCH')
    if report['status'] != 'SCANNED' and (fingerprints or report['metadata']):
        reject('INCOMPLETE_SCAN_CLAIM')
    if report['status'] == 'SCANNED':
        if not {'commit', 'scannerVersion', 'event', 'scannedAt'} <= report['metadata'].keys():
            reject('MISSING_PROVENANCE')
        if report['scanOutcome'] == 'success' and (report['policy']['newBlocking'] or report['policy']['expiredBlocking']):
            reject('POLICY_OUTCOME_MISMATCH')


def verify_staging(directory):
    if directory.is_symlink() or not directory.is_dir():
        reject('STAGING_DIRECTORY')
    entries = list(directory.iterdir())
    if len(entries) != 1 or entries[0].name != PUBLIC_FILE or entries[0].is_symlink() or not entries[0].is_file():
        reject('UNEXPECTED_STAGING_FILE')
    report = load_json(entries[0])
    validate_report(report)
    return hashlib.sha256(entries[0].read_bytes()).hexdigest()


def project(private, outcome, baseline):
    if outcome not in {'success', 'failure', 'skipped', 'cancelled'}:
        reject('SCAN_OUTCOME')
    result = {'schemaVersion': 1, 'status': 'SCAN_FAILED', 'scanOutcome': outcome,
              'metadata': {}, 'findings': [], 'policy': {k: [] for k in CATEGORIES},
              'exceptions': [], 'diagnostics': []}
    required = [private / f for f in ('findings.json', 'policy-result.json', 'metadata.json')]
    if not all(p.is_file() for p in required):
        if outcome == 'success':
            reject('MISSING_SCAN_OUTPUT')
        result['status'] = 'SCAN_NOT_RUN' if outcome in {'skipped', 'cancelled'} else 'SCAN_FAILED'
        result['diagnostics'] = ['SCAN_STEP_NOT_RUN' if result['status'] == 'SCAN_NOT_RUN'
                                 else 'SCANNER_OR_POLICY_STEP_FAILED', 'INCOMPLETE_SCAN_OUTPUT']
        return result
    raw_findings, policy, metadata = [load_json(p) for p in required]
    if not isinstance(raw_findings, dict) or raw_findings.get('schemaVersion') != 1 or not isinstance(raw_findings.get('findings'), list):
        reject('PRIVATE_REPORT_SCHEMA')
    if not isinstance(policy, dict) or set(policy) != set(CATEGORIES):
        reject('PRIVATE_POLICY_SCHEMA')
    items = raw_findings['findings']
    for item in items:
        if not isinstance(item, dict) or not set(FINDING_FIELDS) <= item.keys():
            reject('PRIVATE_FINDING_SCHEMA')
        # Never copy scanner Message/Code/Resource excerpts or arbitrary metadata.
        public = {k: item[k] for k in FINDING_FIELDS}
        public['resourceSha256'] = hashlib.sha256(str(item.get('resource', '')).encode()).hexdigest()
        if 'evidenceSha256' in item:
            public['evidenceSha256'] = item['evidenceSha256']
        result['findings'].append(public)
    by_id = {item['fingerprint']: item for item in items}
    for category in CATEGORIES:
        if not isinstance(policy[category], list):
            reject('PRIVATE_POLICY_SCHEMA')
        for item in policy[category]:
            if not isinstance(item, dict) or by_id.get(item.get('fingerprint')) != item:
                reject('PRIVATE_POLICY_MISMATCH')
            result['policy'][category].append(item['fingerprint'])
    exceptions = {e['fingerprint']: e for e in baseline['exceptions']}
    for fp in sorted(set(result['policy']['acceptedExisting'] + result['policy']['expiredBlocking'])):
        if fp not in exceptions:
            reject('MISSING_EXCEPTION')
        result['exceptions'].append({k: exceptions[fp][k] for k in ('fingerprint', 'reason', 'expires')})
    if not isinstance(metadata, dict) or not isinstance(metadata.get('tool'), dict):
        reject('PRIVATE_METADATA_SCHEMA')
    result['metadata'] = {k: metadata[k] for k in ('commit', 'event', 'scannedAt', 'workflowRunId', 'workflowRunAttempt') if k in metadata}
    result['metadata']['scannerVersion'] = metadata['tool'].get('Version')
    if 'service' in metadata:
        result['metadata']['service'] = metadata['service']
    if 'sbom' in metadata:
        # The complete CycloneDX document remains private, including arbitrary properties.
        result['metadata']['sbomSha256'] = metadata['sbom']['sha256']
        result['metadata']['sbomComponents'] = metadata['sbom']['components']
    result['status'] = 'SCANNED'
    if outcome != 'success':
        result['diagnostics'] = ['SCANNER_OR_POLICY_STEP_FAILED']
    return result


def stage(private, public, outcome, baseline):
    private, public = Path(private), Path(public)
    if private.is_symlink() or public.exists() or public.is_symlink():
        reject('NON_FRESH_STAGING')
    if private.resolve() in public.resolve().parents or public.resolve() in private.resolve().parents:
        reject('STAGING_OVERLAP')
    report = project(private, outcome, baseline)
    validate_report(report)
    public.mkdir(parents=True, exist_ok=False)
    (public / PUBLIC_FILE).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return verify_staging(public)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['stage', 'verify'])
    parser.add_argument('--private', type=Path)
    parser.add_argument('--public', type=Path, required=True)
    parser.add_argument('--scan-outcome', choices=['success', 'failure', 'skipped', 'cancelled'])
    args = parser.parse_args()
    try:
        if args.mode == 'stage':
            if args.private is None or args.scan_outcome is None:
                parser.error('stage requires --private and --scan-outcome')
            digest = stage(args.private, args.public, args.scan_outcome, load_json(ROOT / 'scripts/ci/security-baseline.json'))
        else:
            digest = verify_staging(args.public)
    except UnsafeEvidence as error:
        print(f'{PUBLIC_FILE}: BLOCKED category={error}', file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print(f'{PUBLIC_FILE}: BLOCKED category=INVALID_EVIDENCE', file=sys.stderr)
        raise SystemExit(1) from None
    print(f'{PUBLIC_FILE}: PASS sha256={digest}')


if __name__ == '__main__':
    main()
