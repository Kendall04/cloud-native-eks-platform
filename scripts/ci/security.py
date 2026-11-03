"""Trivy reports, CycloneDX and an explicit expiring adoption gate. No AWS calls."""
import argparse
from datetime import datetime, timezone, date, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
VERSION = '0.71.2'
BASELINE = ROOT / 'scripts/ci/security-baseline.json'


def run(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def findings(report, scope):
    """Version/resource-specific keys: no global CVE/check suppressions."""
    if report.get('SchemaVersion') != 2 or not isinstance(report.get('Results'), list):
        raise ValueError('Missing/unsupported Trivy results')
    result = []
    for target in report['Results']:
        target_name = target['Target']
        if scope.startswith('image/') and target.get('Class') == 'os-pkgs':
            # Image tags contain the commit; OS exceptions must remain scoped to
            # distro/package/version rather than expire at every new commit.
            target_name = 'os/' + target['Type'] + '/' + report['Metadata']['OS']['Name']
        for category, key in (('vulnerability', 'Vulnerabilities'), ('misconfiguration', 'Misconfigurations')):
            for item in target.get(key) or []:
                identity = {
                    'scope': scope, 'kind': category, 'target': target_name,
                    'id': item.get('VulnerabilityID') or item['ID'],
                    'package': item.get('PkgName', ''),
                    'installed': item.get('InstalledVersion', ''),
                    # Kubernetes reports identify the object/container in Message;
                    # unlike line numbers, that survives unrelated YAML changes.
                    'resource': item.get('CauseMetadata', {}).get('Resource') or item.get('Message', ''),
                    'severity': item['Severity'],
                }
                if category == 'misconfiguration':
                    code = '\n'.join(line['Content'] for line in item.get('CauseMetadata', {}).get('Code', {}).get('Lines', []))
                    identity['evidenceSha256'] = hashlib.sha256(code.encode()).hexdigest()
                fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
                result.append({**identity, 'fingerprint': fingerprint,
                               'fixedVersion': item.get('FixedVersion', ''),
                               'title': item.get('Title', '')})
    return result


def evaluate(items, baseline, today=None):
    today = today or datetime.now(timezone.utc).date()
    if baseline.get('schemaVersion') != 1:
        raise ValueError('Unsupported security baseline')
    exceptions = {}
    for entry in baseline['exceptions']:
        if not entry.get('reason') or entry['fingerprint'] in exceptions:
            raise ValueError('Missing rationale or duplicate exception')
        expiry = date.fromisoformat(entry['expires'])
        if expiry > date.fromisoformat(baseline['reviewedOn']) + timedelta(days=90):
            raise ValueError('Exception exceeds 90-day adoption window')
        exceptions[entry['fingerprint']] = (entry, expiry)
    summary = {'newBlocking': [], 'expiredBlocking': [], 'acceptedExisting': [], 'advisory': []}
    for item in items:
        if item['severity'] not in ('HIGH', 'CRITICAL'):
            summary['advisory'].append(item)
        elif item['fingerprint'] not in exceptions:
            summary['newBlocking'].append(item)
        elif exceptions[item['fingerprint']][1] <= today:
            summary['expiredBlocking'].append(item)
        else:
            summary['acceptedExisting'].append(item)
    return summary


def execute_trivy(arguments, output):
    try:
        subprocess.run(['trivy', *arguments, '--output', str(output), '--timeout', '15m'], cwd=ROOT, check=True)
    except (subprocess.CalledProcessError, OSError) as error:
        # Persist a useful bounded artifact even when the first scan fails.
        # Do not persist exception text, command arguments, URLs or credentials.
        dump(output.with_suffix('.error.json'), {'status': 'SCANNER_FAILED',
             'exceptionType': type(error).__name__, 'exitCode': getattr(error, 'returncode', None)})
        raise
    return json.loads(output.read_text())


def scan(arguments, output):
    # Trivy gathers the complete report; evaluate() below owns the exit policy.
    return execute_trivy([*arguments, '--format', 'json', '--exit-code', '0'], output)


def validate_sbom(path):
    from jsonschema import Draft7Validator
    from referencing import Registry, Resource
    document = json.loads(path.read_text())
    schema_root = ROOT / 'scripts/ci/schemas'
    version = document.get('specVersion')
    if version != '1.7':
        raise ValueError('Reviewed CycloneDX schema version must be 1.7')
    schema = json.loads((schema_root / 'bom-1.7.schema.json').read_text())
    resources = []
    for name in ('bom-1.7.schema.json', 'spdx.schema.json', 'jsf-0.82.schema.json'):
        value = json.loads((schema_root / name).read_text())
        resources.append((value['$id'], Resource.from_contents(value)))
    Draft7Validator(schema, registry=Registry().with_resources(resources)).validate(document)
    if not document.get('metadata', {}).get('component') or not document.get('components'):
        raise ValueError('SBOM must identify its image and contain components')
    return {'format': document['bomFormat'], 'version': version,
            'components': len(document['components'])}


def identify_local_sbom(document, image_id):
    """Trivy can synthesize an OCI RepoDigest from a local config ID. Label it
    as a local image instead; only the publisher may record a registry digest.
    """
    component = document['metadata']['component']
    old = component['bom-ref']
    new = 'urn:cnp:local-image:' + image_id
    component['bom-ref'] = new
    component.pop('purl', None)
    component['properties'] = [p for p in component.get('properties', [])
                               if p['name'] != 'aquasecurity:trivy:RepoDigest']
    for dependency in document.get('dependencies', []):
        if dependency['ref'] == old:
            dependency['ref'] = new
        dependency['dependsOn'] = [new if value == old else value for value in dependency.get('dependsOn', [])]
    return document


def verify_registry_identity(image, digest):
    import re
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest) or not image.endswith('@' + digest):
        raise ValueError('Registry evidence requires an exact digest reference')
    repo_digests = json.loads(run('docker', 'image', 'inspect', image, '--format', '{{json .RepoDigests}}'))
    if image not in (repo_digests or []):
        raise ValueError('Registry digest was not resolved by Docker')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['image', 'source', 'gate', 'validate-sbom'])
    parser.add_argument('--service', choices=['auth', 'shipment', 'tracking'])
    parser.add_argument('--image')
    parser.add_argument('--registry-digest', help='Only a digest actually resolved after registry publication')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / '.validation-results/security-private')
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.mode == 'validate-sbom':
        print(json.dumps(validate_sbom(args.report)))
        return
    if args.mode == 'gate':
        report = json.loads(args.report.read_text())
        result = evaluate(report['findings'], json.loads(BASELINE.read_text()))
        dump(args.report.with_name(args.report.stem + '-gate.json'), result)
        print(json.dumps({key: len(value) for key, value in result.items()}))
        raise SystemExit(bool(result['newBlocking'] or result['expiredBlocking']))
    # GitHub's initial PR run observed a stale layer/404 in the default GCR
    # pull-through cache. Prefer the official upstream registry directly.
    os.environ.setdefault('TRIVY_DB_REPOSITORY', 'ghcr.io/aquasecurity/trivy-db:2')
    version = json.loads(run('trivy', '--version', '--format', 'json'))
    if version['Version'] != VERSION:
        raise ValueError(f'Trivy {VERSION} required')
    args.output.mkdir(parents=True, exist_ok=True)
    items = []
    metadata = {'schemaVersion': 1, 'tool': version, 'commit': run('git', 'rev-parse', 'HEAD'),
                'workflowRunId': os.environ.get('GITHUB_RUN_ID'),
                'workflowRunAttempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
                'event': os.environ.get('GITHUB_EVENT_NAME', 'local'),
                'workingTreeDirty': bool(run('git', 'status', '--porcelain')),
                'scannedAt': datetime.now(timezone.utc).isoformat()}
    if args.mode == 'image':
        if not args.service or not args.image:
            parser.error('image requires --service and --image')
        scope = 'image/' + args.service
        image_id = run('docker', 'image', 'inspect', args.image, '--format', '{{.Id}}')
        metadata.update(service=args.service, image=args.image, localImageId=image_id,
                        registryDigest=args.registry_digest)
        if args.registry_digest:
            verify_registry_identity(args.image, args.registry_digest)
        report = scan(['image', '--image-src', 'docker', '--scanners', 'vuln', args.image],
                      args.output / 'vulnerabilities.json')
        items.extend(findings(report, scope))
        sbom = args.output / 'sbom.cdx.json'
        document = execute_trivy(['image', '--image-src', 'docker', '--format', 'cyclonedx', args.image], sbom)
        dump(sbom, identify_local_sbom(document, image_id))
        metadata['sbom'] = {**validate_sbom(sbom), 'sha256': hashlib.sha256(sbom.read_bytes()).hexdigest()}
    else:
        # Only source dependency manifests, owned modules/charts and three Docker contexts.
        for target in ('microservices', 'tests/EventReliability.Tests', 'scripts/bootstrap', 'scripts/ci'):
            report = scan(['fs', '--scanners', 'vuln', '--skip-dirs', '**/bin', '--skip-dirs', '**/obj', target],
                          args.output / (target.replace('/', '-') + '-dependencies.json'))
            items.extend(findings(report, 'source/' + target))
        for target in ('infra/modules', 'microservices'):
            report = scan(['config', '--skip-dirs', '**/.terraform', '--skip-dirs', '**/bin', '--skip-dirs', '**/obj', target],
                          args.output / (target.replace('/', '-') + '-config.json'))
            items.extend(findings(report, 'config/' + target))
        # Render all four charts with existing offline fixtures; required values
        # must not make the scanner silently skip a chart.
        import yaml
        sys.path.insert(0, str(ROOT / 'scripts/validation'))
        from validate_r3 import platform_render
        from validate_r1 import render
        rendered = args.output / 'rendered'
        rendered.mkdir(exist_ok=True)
        platform, _ = platform_render('helm')
        (rendered / 'platform.yaml').write_text(yaml.safe_dump_all(platform))
        (rendered / 'services.yaml').write_text(yaml.safe_dump_all(render('helm', ROOT / 'k8s/environments/dev/platform-services.values.yaml')))
        (rendered / 'addons.yaml').write_text(run('helm', 'template', 'cluster-addons', 'k8s/charts/cluster-addons', '-n', 'kube-system'))
        report = scan(['config', str(rendered.relative_to(ROOT))], args.output / 'kubernetes-config.json')
        items.extend(findings(report, 'config/kubernetes'))
    # A cold runner downloads the DB during scanning, after the version check.
    metadata['tool'] = json.loads(run('trivy', '--version', '--format', 'json'))
    dump(args.output / 'metadata.json', metadata)
    report = args.output / 'findings.json'
    dump(report, {'schemaVersion': 1, 'findings': items})
    result = evaluate(items, json.loads(BASELINE.read_text()))
    dump(args.output / 'policy-result.json', result)
    print(json.dumps({key: len(value) for key, value in result.items()}))
    raise SystemExit(bool(result['newBlocking'] or result['expiredBlocking']))


if __name__ == '__main__':
    main()
