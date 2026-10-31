"""Exercise the production archive_file block against clean and dirty source trees.
Requires Terraform/archive provider; no AWS provider, credentials or API calls.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[2]

def verify():
    module=ROOT/'infra/modules/lambda'
    archive=re.search(r'data "archive_file" "package" \{.*?^\}',(module/'main.tf').read_text(),re.S|re.M)[0]
    with tempfile.TemporaryDirectory(prefix='eks-lambda-package-') as directory:
        work=Path(directory)
        lock=re.search(r'provider "registry.terraform.io/hashicorp/archive" \{.*?^\}',(module/'.terraform.lock.hcl').read_text(),re.S|re.M)[0]
        (work/'.terraform.lock.hcl').write_text(lock+'\n')
        (work/'main.tf').write_text(
            'terraform {\n required_providers {\n'
            ' archive = { source = "hashicorp/archive", version = "~> 2.4" }\n }\n}\n'
            'variable "source_dir" { type = string }\n'
            'variable "function_name" { default = "package" }\n'+archive)
        def run(*args):
            result=subprocess.run(['terraform',*args],cwd=work,capture_output=True,text=True,timeout=180)
            if result.returncode: raise RuntimeError(result.stdout+result.stderr)
        run('init','-backend=false','-input=false','-lockfile=readonly')
        manifests=[]
        for name in ('clean','contaminated'):
            source=work/name
            (source/'src').mkdir(parents=True)
            shutil.copyfile(ROOT/'lambdas/api-gateway-jwt-authorizer/src/index.mjs',source/'src/index.mjs')
            if name=='contaminated':
                for extra in ('node_modules/unrelated/index.js','.env','.git/config','coverage/result.json','src/index.test.mjs','README.md','temporary'):
                    path=source/extra; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('not part of the package')
            run('apply','-auto-approve','-input=false','-var=source_dir='+source.as_posix())
            with zipfile.ZipFile(work/'package.zip') as bundle:
                manifests.append({entry.filename:hashlib.sha256(bundle.read(entry)).hexdigest() for entry in bundle.infolist()})
        assert manifests[0]==manifests[1] and set(manifests[0])=={'src/index.mjs'},manifests
        print(json.dumps({'clean':manifests[0],'contaminated':manifests[1],'equivalent':True}))

if __name__=='__main__': verify()
