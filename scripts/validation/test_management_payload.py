"""Exact source extraction and default dev runtime imports; no host install/AWS."""
import base64
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / 'infra/modules/management-host'
RUNTIME = {'contract.py', 'diagnostics.py', 'engine.py', 'executor.py',
           'manifest.schema.json', 'chart-template-hashes.json'}


class DefaultManagementPayload(unittest.TestCase):
    def decoder(self, members, target):
        encoded = base64.b64encode(gzip.compress(json.dumps(members).encode()))
        data = target / 'bundle.json'
        data.write_bytes(gzip.decompress(base64.b64decode(encoded)))
        source = (MODULE / 'user_data.sh.tftpl').read_text()
        decoder = re.search(r"<<'PY'\n(.*?)\nPY", source, re.S)[1]
        with patch.object(sys, 'argv', ['decoder', str(data), str(target)]):
            exec(compile(decoder, 'userdata-decoder-fixture', 'exec'), {})

    def test_decode_preserves_every_runtime_source_byte(self):
        expected = {name: (MODULE / 'deployer' / name).read_bytes() for name in RUNTIME}
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self.decoder({name: data.decode('utf-8') for name, data in expected.items()}, target)
            self.assertEqual({name: (target / name).read_bytes() for name in RUNTIME}, expected)

    def test_decoder_rejects_traversal_and_non_source_members(self):
        for name in ('../escape.py', '/absolute.json', 'nested/file.py', 'executable.sh'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError): self.decoder({name: 'fixture'}, Path(tmp))

    def test_default_runtime_imports_without_synthetic_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self.decoder({name: (MODULE / 'deployer' / name).read_bytes().decode('utf-8') for name in RUNTIME}, target)
            subprocess.run([sys.executable, '-B', '-c',
                "import contract,executor,importlib.util; assert contract.VERSION=='1.4.0'; assert importlib.util.find_spec('synthetic_contract') is None; assert contract.target_environment({'environment':'dev'})=='dev'"],
                cwd=target, env={**os.environ, 'PYTHONPATH': str(target)}, check=True)


if __name__ == '__main__': unittest.main()
