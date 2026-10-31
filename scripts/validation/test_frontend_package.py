"""Offline static packaging contract; real Vite builds are validated separately."""
import copy
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'frontend/scripts'))
from package_static import (ARCHITECTURE, archive, canonical, checksums, package_site,
                              read_site, read_tar, sha, validate_package, validate_site)

BASE = 'a3e9a324e9cc06ffdcfea9849f16021dfa968a15'


def fixture(mode='demo'):
    files = {'index.html': b'<script src="/assets/index-abcdef.js"></script><link href="/assets/index-abcdef.css">',
             'assets/index-abcdef.js': ('/* synthetic ' + mode + ' bundle */').encode(),
             'assets/index-abcdef.css': b'body{}'}
    for name in ARCHITECTURE:
        data = (b'license fixture' if name.endswith('.txt') else b'{"fixture":true}')
        files[f'architecture-assets/{sha(data)}/{name}'] = data
    return receipt(files, mode)


def receipt(files, mode):
    files['frontend-build.json'] = canonical({
        'schemaVersion': 1, 'configuration': {'mode': mode, 'apiBase': '/api'},
        'toolchain': {'node': '24.18.0'},
        'files': {n: {'sha256': sha(b), 'bytes': len(b)} for n, b in files.items() if n != 'frontend-build.json'},
    })
    return files


def repack(files):
    files['checksums.sha256'] = checksums({n: b for n, b in files.items() if n != 'checksums.sha256'})
    return archive(files)


class FrontendPackageTests(unittest.TestCase):
    def test_reproducible_bytes_and_closed_manifest(self):
        files = fixture()
        a, manifest = package_site(files, 'demo', BASE)
        b, _ = package_site(dict(reversed(list(files.items()))), 'demo', BASE)
        self.assertEqual(a, b)
        self.assertEqual(validate_package(a, sha(a), 'demo'), manifest)
        self.assertEqual(len(manifest['files']), 11)
        self.assertTrue(all(row['cacheControl'].endswith('immutable') for row in manifest['files'] if row['path'].startswith('architecture-assets/')))

    def test_file_mtime_and_permissions_do_not_change_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in fixture().items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            first, _ = package_site(read_site(root), 'demo', BASE)
            for path in root.rglob('*'):
                if path.is_file():
                    os.utime(path, (100000, 100000))
            second, _ = package_site(read_site(root), 'demo', BASE)
            self.assertEqual(first, second)

    def test_whole_wrong_mode_and_mixed_javascript_fail(self):
        demo, aws = fixture('demo'), fixture('aws')
        with self.assertRaisesRegex(ValueError, 'mode'):
            package_site(demo, 'aws', BASE)
        mixed = copy.deepcopy(aws)
        mixed['assets/index-abcdef.js'] = demo['assets/index-abcdef.js']
        with self.assertRaisesRegex(ValueError, 'integrity'):
            package_site(mixed, 'aws', BASE)
        data, _ = package_site(aws, 'aws', BASE)
        with self.assertRaisesRegex(ValueError, 'mode'):
            validate_package(data, sha(data), 'demo')

    def test_every_missing_or_modified_file_fails(self):
        for name in fixture():
            for mutation in ('missing', 'modified'):
                with self.subTest(name=name, mutation=mutation):
                    files = fixture()
                    if mutation == 'missing': del files[name]
                    else: files[name] += b'altered'
                    with self.assertRaises((ValueError, json.JSONDecodeError)):
                        package_site(files, 'demo', BASE)

    def test_version_path_is_checked_even_with_updated_receipt(self):
        files = fixture()
        name = next(n for n in files if n.startswith('architecture-assets/'))
        files[name] += b'changed'
        receipt(files, 'demo')
        with self.assertRaisesRegex(ValueError, 'path digest'):
            validate_site(files, 'demo')

    def test_unknown_secret_and_outside_paths_fail(self):
        for path in ('.env', 'source.map', '../outside.js', '/absolute.js', 'C:/outside.js',
                     'assets/../outside.js', 'assets\\outside.js', 'assets/%2e%2e.js'):
            with self.subTest(path=path):
                files = fixture(); files[path] = b'not shipped'
                receipt(files, 'demo')
                with self.assertRaises(ValueError): validate_site(files, 'demo')

    def test_unexpected_configuration_and_duplicate_json_fail(self):
        for key, value in (('mode', 'local'), ('apiBase', '//outside.invalid'), ('secret', 'not allowed')):
            files = fixture(); build = json.loads(files['frontend-build.json'])
            build['configuration'][key] = value
            files['frontend-build.json'] = canonical(build)
            with self.assertRaises(ValueError): validate_site(files, 'demo')
        files = fixture()
        files['frontend-build.json'] = files['frontend-build.json'].replace(b'"schemaVersion": 1', b'"schemaVersion": 1, "schemaVersion": 1')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'): validate_site(files, 'demo')

    def test_credential_pattern_is_rejected_without_printing_it(self):
        files = fixture()
        files['assets/index-abcdef.js'] += b'ASIA' + b'A' * 16
        receipt(files, 'demo')
        with self.assertRaisesRegex(ValueError, '^Credential pattern in static content$'):
            validate_site(files, 'demo')

    def test_symlinks_are_not_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'outside').write_text('do not read')
            (root / 'input').mkdir()
            try:
                (root / 'input' / 'link').symlink_to(root / 'outside')
            except OSError as error:
                if os.name == 'nt' and getattr(error, 'winerror', None) == 1314:
                    self.skipTest('Windows token lacks symlink privilege; execute this test on Linux')
                raise
            with self.assertRaisesRegex(ValueError, 'symlinks'): read_site(root / 'input')

    def test_manifest_tampering_and_stale_external_digest_fail(self):
        data, _ = package_site(fixture(), 'demo', BASE)
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'): validate_package(data + b'x', sha(data), 'demo')
        for field, value in (('configuration', {'mode': 'aws', 'apiBase': '/api'}), ('files', []), ('artifactType', 'OTHER')):
            content = read_tar(data); manifest = json.loads(content['manifest.json'])
            manifest[field] = value; content['manifest.json'] = canonical(manifest)
            altered = repack(content)
            with self.subTest(field=field), self.assertRaises(ValueError): validate_package(altered, sha(altered), 'demo')

    def test_entrypoint_cannot_reference_outside_package(self):
        for url in ('https://outside.invalid/a.js', '/missing.js', '/assets/missing.js'):
            for quote in ('"', "'", ''):
                files = fixture(); files['index.html'] = f'<script src={quote}{url}{quote}></script>'.encode()
                receipt(files, 'demo')
                with self.assertRaisesRegex(ValueError, 'outside package'): validate_site(files, 'demo')

    def test_archive_paths_links_duplicates_and_executables_fail(self):
        for name, kind in (('../escape', 'file'), ('/absolute', 'file'), ('site/a', 'symlink'), ('site/a', 'exec'), ('site/a', 'duplicate')):
            raw = io.BytesIO()
            with tarfile.open(fileobj=raw, mode='w:gz') as out:
                item = tarfile.TarInfo(name); item.size = 1; item.mode = 0o755 if kind == 'exec' else 0o644
                if kind == 'symlink': item.type = tarfile.SYMTYPE; item.linkname = '/outside'; item.size = 0
                out.addfile(item, io.BytesIO(b'x'))
                if kind == 'duplicate': out.addfile(item, io.BytesIO(b'x'))
            data = raw.getvalue()
            with self.subTest(kind=kind, name=name), self.assertRaises(ValueError): validate_package(data, sha(data), 'demo')


if __name__ == '__main__':
    unittest.main()
