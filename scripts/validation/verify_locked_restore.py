"""Prove an unrecorded dependency change fails closed; disposable source copy only."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    with tempfile.TemporaryDirectory(prefix='cnp-negative-lock-') as directory:
        target = Path(directory) / 'auth-service'
        shutil.copytree(ROOT / 'microservices/auth-service', target,
                        ignore=shutil.ignore_patterns('bin', 'obj', 'TestResults'))
        project = target / 'src/AuthService.Domain/AuthService.Domain.csproj'
        before = project.read_text(encoding='utf-8')
        # Change the declared range while keeping the committed lock untouched.
        # The replacement is deliberately tied to the reviewed current version.
        changed = before.replace('Version="10.0.13"', 'Version="[10.0.13]"', 1)
        if changed == before:
            raise ValueError('Reviewed negative fixture no longer matches the project')
        project.write_text(changed, encoding='utf-8')
        result = subprocess.run(['dotnet', 'restore', str(target / 'AuthService.sln'),
                                 '--locked-mode'], cwd=ROOT, env=os.environ,
                                text=True, capture_output=True, timeout=180)
        if result.returncode == 0 or 'NU1004' not in result.stdout + result.stderr:
            raise ValueError('Expected NU1004 rejection of an unrecorded dependency change')
    print('Locked restore negative test: PASS (NU1004; source locks unchanged)')


if __name__ == '__main__':
    main()
