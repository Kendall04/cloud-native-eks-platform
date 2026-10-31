"""Build a deterministic, data-only release bundle. No AWS calls."""
import copy
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import yaml
from common import ROOT, HELM, VERSION, sha, validate_bundle, validate_render, require
from synthetic_contract import SYNTHETIC_VERSION


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def archive(files):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w', format=tarfile.USTAR_FORMAT) as out:
        for name, data in sorted(files.items()):
            item = tarfile.TarInfo(name)
            item.size, item.mode, item.mtime = len(data), 0o644, 0
            out.addfile(item, io.BytesIO(data))
    return gzip.compress(raw.getvalue(), mtime=0)


def merge(base, overlay):
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
    return result


def target_from_environment(c):
    return {**{k: c[k] for k in ('environment', 'accountId', 'region', 'clusterName', 'namespace', 'repositories')},
            **({'dataScope': c['dataScope']} if c['schemaVersion'] == 3 else {}),
            'helmRelease': 'platform-services', 'shipmentQueueUrl': c['shipmentQueue']['url'],
            'alb': {'groupName': c['dataScope']['namespace'] if c['schemaVersion'] == 3 else c['project'], 'frontendSecurityGroupId': c['alb']['frontendSecurityGroupId'],
                    'discoveryTags': {'Project': c['project'], 'Environment': c['environment']}}}


def package(environment_bytes, records, commit, version, helm=None, *, expected_environment='dev', expected_data_scope=None):
    helm = helm or os.environ.get('HELM_BIN', 'helm')
    require(subprocess.check_output([helm, 'version', '--template', '{{.Version}}'], text=True).strip() == HELM, 'Wrong Helm version')
    c = json.loads(environment_bytes)
    # Reuse R3's closed contract instead of accepting an invented inventory.
    import sys
    sys.path.insert(0, str(ROOT / 'scripts/bootstrap'))
    from environment import validate_contract, overlay
    validate_contract(c, expected_environment, ready=True)
    synthetic = c['schemaVersion'] == 3
    require((c.get('dataScope') if synthetic else None) == expected_data_scope, 'Explicit trusted synthetic publication scope mismatch')
    infra = overlay(c)
    chart = ROOT / 'k8s/charts/platform-services'
    values = merge(yaml.safe_load((chart / 'values.yaml').read_text()), yaml.safe_load((ROOT / 'k8s/environments/dev/platform-services.values.yaml').read_text()))
    values = merge(values, infra)
    values['release'] = {'version': version, 'gitTag': version, 'commitSha': commit}
    for s in records:
        values['services'][s['name']]['image'].update(repository=s['imageRepository'], digest=s['imageDigest'], tag='')
    resolved = yaml.safe_dump(values, sort_keys=True).encode()
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run([helm, 'package', str(chart), '--destination', directory], check=True, capture_output=True)
        # Helm metadata timestamps are normalized; same inputs yield the same outer hash.
        from common import read_tar
        packaged_chart = archive({name:content.replace(b'\r\n',b'\n') for name,content in read_tar(next(Path(directory).glob('*.tgz')).read_bytes()).items()})
        files = {'platform-services.tgz': packaged_chart, 'values.resolved.yaml': resolved, 'environment.contract.json': environment_bytes}
        m = {**target_from_environment(c), 'artifactSchemaVersion': 2 if synthetic else 1, 'releaseVersion': version,
             'applicationSourceCommit': commit, 'deploymentConfigCommit': commit,
             'chartSha256': sha(packaged_chart), 'valuesSha256': sha(resolved), 'environmentContractSha256': sha(environment_bytes),
             'requiredDeployerVersion': SYNTHETIC_VERSION if synthetic else VERSION, 'requiredHelmVersion': HELM, 'services': records,
             'migrationCompatibility': 'previous-release-compatible'}
        del m['repositories']; del m['shipmentQueueUrl']; del m['alb']
        files['manifest.json'] = canonical(m)
        files['checksums.sha256'] = ''.join(f'{sha(data)}  {name}\n' for name, data in sorted(files.items())).encode()
        data = archive(files)
        target = target_from_environment(c)
        validated,_ = validate_bundle(data, sha(data), target)
        for name in ('platform-services.tgz', 'values.resolved.yaml'):
            (Path(directory) / name).write_bytes(validated[name])
        rendered = subprocess.check_output([helm, 'template', 'platform-services', str(Path(directory) / 'platform-services.tgz'), '-n', 'apps', '-f', str(Path(directory) / 'values.resolved.yaml')], text=True)
        validate_render(yaml.safe_load_all(rendered), m, target)
    return data, m
