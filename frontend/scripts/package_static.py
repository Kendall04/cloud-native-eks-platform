"""Local static frontend bundle. No publication, extraction, promotion or AWS calls."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/cd"))
from common import read_tar, require, sha
from package import archive, canonical

sys.path.insert(0, str(ROOT / 'scripts/validation'))
from secret_scan import inspect_text

HEX = r'[0-9a-f]{64}'
ARCHITECTURE = set(json.loads((ROOT / 'frontend/architecture-pins.json').read_text()))
ARCHITECTURE = {name + '.json' for name in ARCHITECTURE} | {'evidence.json', 'ARCHIFY-LICENSE.txt'}
MAX_BYTES = 20 * 1024 * 1024  # Same bound as the reused CD archive reader.


class EntrypointUrls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        self.urls.extend(value for key, value in attrs if key in ('src', 'href'))


def parse_json(data):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'Duplicate JSON field')
            value[key] = item
        return value
    return json.loads(data, object_pairs_hook=unique)


def file_policy(name, data):
    require(type(name) is str and len(name) < 200, 'Invalid static path')
    if name in ('index.html', 'frontend-build.json'):
        return ('text/html' if name.endswith('.html') else 'application/json', 'no-cache')
    if re.fullmatch(r'assets/[A-Za-z0-9_-]+-[A-Za-z0-9_-]+\.(js|css)', name):
        return ('text/javascript' if name.endswith('.js') else 'text/css', 'public, max-age=31536000, immutable')
    match = re.fullmatch(r'architecture-assets/(' + HEX + r')/([A-Za-z0-9_.-]+)', name)
    require(match and match[2] in ARCHITECTURE, 'Unexpected static path')
    require(sha(data) == match[1], 'Versioned asset path digest mismatch')
    return ('application/json' if name.endswith('.json') else 'text/plain', 'public, max-age=31536000, immutable')


def validate_site(files, mode):
    require(mode in ('demo', 'aws'), 'Explicit demo/aws mode required')
    require(type(files) is dict and 1 <= len(files) <= 100, 'Invalid static inventory')
    require({'index.html', 'frontend-build.json'} <= set(files), 'Missing static entrypoint/receipt')
    require(sum(map(len, files.values())) <= MAX_BYTES, 'Static content too large')
    assets = []
    for name, data in files.items():
        file_policy(name, data)
        require(not inspect_text(name, data.decode('utf-8')), 'Credential pattern in static content')
        if name.startswith('architecture-assets/'):
            assets.append(name.split('/')[-1])
    require(len(assets) == len(ARCHITECTURE) and set(assets) == ARCHITECTURE, 'Missing/duplicate architecture assets')
    require(any(n.startswith('assets/') and n.endswith('.js') for n in files), 'Missing application JavaScript')
    require(any(n.startswith('assets/') and n.endswith('.css') for n in files), 'Missing application CSS')
    receipt = parse_json(files['frontend-build.json'])
    require(set(receipt) == {'schemaVersion', 'configuration', 'toolchain', 'files'}, 'Build receipt fields mismatch')
    require(type(receipt['schemaVersion']) is int and receipt['schemaVersion'] == 1, 'Build receipt version mismatch')
    require(receipt['configuration'] == {'mode': mode, 'apiBase': '/api'}, 'Build configuration/mode mismatch')
    tools = receipt['toolchain']
    require(type(tools) is dict and set(tools) == {'node'} and re.fullmatch(r'\d+\.\d+\.\d+', tools['node']), 'Build toolchain mismatch')
    expected = {n: {'sha256': sha(b), 'bytes': len(b)} for n, b in files.items() if n != 'frontend-build.json'}
    require(canonical(receipt['files']) == canonical(expected), 'Build receipt integrity/inventory mismatch')
    # Every entrypoint URL is local and names a bundled asset; inline SVG icon is inert.
    entrypoint = EntrypointUrls()
    entrypoint.feed(files['index.html'].decode())
    for url in entrypoint.urls:
        require(type(url) is str, 'Invalid entrypoint URL')
        if url.startswith('data:image/svg+xml,'):
            require(not re.search(r'<script|\bon\w+=|foreignObject', unquote(url), re.I), 'Unexpected inline icon')
        else:
            require(url.startswith('/assets/') and url[1:] in files, 'Entrypoint references outside package')
    return receipt


def read_site(directory):
    require(directory.is_dir() and not directory.is_symlink(), 'Static input must be a regular directory')
    files = {}
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink(), 'Static symlinks forbidden')
        if path.is_dir():
            continue
        require(path.is_file(), 'Only regular static files allowed')
        require(path.stat().st_size <= MAX_BYTES, 'Static file too large')
        files[path.relative_to(directory).as_posix()] = path.read_bytes()
        require(len(files) <= 100 and sum(map(len, files.values())) <= MAX_BYTES, 'Static content too large')
    return files


def checksums(files):
    return ''.join(f'{sha(data)}  {name}\n' for name, data in sorted(files.items())).encode()


def package_site(files, mode, source_base):
    require(re.fullmatch(r'[0-9a-f]{40}', source_base), 'Invalid source base commit')
    receipt = validate_site(files, mode)
    manifest = {
        'artifactSchemaVersion': 1,
        'artifactType': 'CNP_STATIC_FRONTEND_LOCAL',
        'sourceBaseCommit': source_base,
        'configuration': receipt['configuration'],
        'files': [dict(path=name, sha256=sha(data), bytes=len(data),
                       mediaType=file_policy(name, data)[0], cacheControl=file_policy(name, data)[1])
                  for name, data in sorted(files.items())],
    }
    content = {'site/' + name: data for name, data in files.items()}
    content['manifest.json'] = canonical(manifest)
    content['checksums.sha256'] = checksums(content)
    data = archive(content)  # Existing sorted USTAR/gzip with fixed metadata/time.
    validate_package(data, sha(data), mode)
    return data, manifest


def validate_package(data, expected_sha, mode):
    require(type(expected_sha) is str and re.fullmatch(HEX, expected_sha), 'Expected SHA256 required')
    require(sha(data) == expected_sha, 'Artifact SHA256 mismatch')
    files = read_tar(data)  # Existing bounded reader rejects traversal, links and duplicates.
    require({'manifest.json', 'checksums.sha256'} <= set(files), 'Missing package metadata')
    require(all(n in ('manifest.json', 'checksums.sha256') or n.startswith('site/') for n in files), 'Unexpected package member')
    content = {n: b for n, b in files.items() if n != 'checksums.sha256'}
    require(files['checksums.sha256'] == checksums(content), 'Package checksums mismatch')
    manifest = parse_json(files['manifest.json'])
    require(set(manifest) == {'artifactSchemaVersion', 'artifactType', 'sourceBaseCommit', 'configuration', 'files'}, 'Manifest fields mismatch')
    site = {n[5:]: b for n, b in files.items() if n.startswith('site/')}
    receipt = validate_site(site, mode)
    require(type(manifest['artifactSchemaVersion']) is int and manifest['artifactSchemaVersion'] == 1, 'Manifest version mismatch')
    require(manifest['artifactType'] == 'CNP_STATIC_FRONTEND_LOCAL', 'Artifact type mismatch')
    require(re.fullmatch(r'[0-9a-f]{40}', manifest['sourceBaseCommit']), 'Invalid source base commit')
    require(manifest['configuration'] == receipt['configuration'], 'Manifest configuration mismatch')
    expected = [dict(path=n, sha256=sha(b), bytes=len(b), mediaType=file_policy(n, b)[0], cacheControl=file_policy(n, b)[1])
                for n, b in sorted(site.items())]
    require(canonical(manifest['files']) == canonical(expected), 'Manifest inventory/integrity mismatch')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build')
    build.add_argument('--dist', required=True, type=Path)
    build.add_argument('--source-base', required=True)
    build.add_argument('--output', required=True, type=Path)
    verify = sub.add_parser('verify')
    verify.add_argument('--artifact', required=True, type=Path)
    verify.add_argument('--sha256', required=True)
    for command in (build, verify):
        command.add_argument('--mode', required=True, choices=('demo', 'aws'))
    args = parser.parse_args()
    if args.command == 'build':
        require(not args.output.resolve().is_relative_to(args.dist.resolve()), 'Output must be outside static input')
        data, manifest = package_site(read_site(args.dist), args.mode, args.source_base)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('xb') as output:
            output.write(data)  # Never overwrite an existing artifact.
    else:
        require(args.artifact.stat().st_size <= MAX_BYTES, 'Artifact too large')
        data = args.artifact.read_bytes()
        manifest = validate_package(data, args.sha256, args.mode)
    print(json.dumps({'status': 'PASS', 'sha256': sha(data), 'mode': args.mode,
                      'files': len(manifest['files']), 'scope': 'LOCAL_ONLY_NO_PUBLICATION'}))


if __name__ == '__main__':
    main()
