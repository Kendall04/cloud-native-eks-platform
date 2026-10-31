"""Current-tree secret baseline. Reports locations only, never secret values.
Detects provider tokens/private keys/JWT literals and non-placeholder JSON secrets.
This is not a history scan or a guarantee that arbitrary secrets are detectable.
"""
import json
from pathlib import Path
import re
import subprocess
ROOT=Path(__file__).resolve().parents[2]
PATTERNS=[r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',r'\bgh[pousr]_[A-Za-z0-9]{30,}\b',r'github_pat_[A-Za-z0-9_]{30,}',r'\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b']
SYNTHETIC={'','postgres','replace-with-a-32-byte-or-longer-secret','replace-with-your-shared-secret','replace-with-your-proxy-secret'}

def inspect_text(path,text):
    issues=[]
    for number,line in enumerate(text.splitlines(),1):
        if any(re.search(pattern,line) for pattern in PATTERNS): issues.append(f'{path}:{number}: token/private-key pattern')
    if str(path).endswith('.json') and 'appsettings' in str(path):
        def walk(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if isinstance(item,str) and re.search(r'^(password|secret|sharedsecret|proxysecret|token|accesskey|secretkey)$',key,re.I):
                        if item not in SYNTHETIC and not item.startswith('replace-'): issues.append(f'{path}: non-placeholder sensitive configuration field')
                    if isinstance(item,str) and 'Password=' in item:
                        password=re.search(r'Password=([^;]*)',item,re.I)
                        if password and password[1] not in SYNTHETIC and not password[1].startswith('replace-'):issues.append(f'{path}: non-placeholder connection password')
                    walk(item)
            elif isinstance(value,list):
                for item in value:walk(item)
        walk(json.loads(text))
    return issues

def main():
    paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    issues=[]; count=0
    for path in sorted(set(paths)-{''}):
        p=ROOT/path
        if not p.is_file():continue
        try:text=p.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:continue
        issues.extend(inspect_text(path,text));count+=1
    if issues: raise SystemExit('\n'.join(issues))
    print(f'PASS: current-tree secret baseline ({count} text files); development placeholders are not production credentials; history not scanned')
if __name__=='__main__':main()
