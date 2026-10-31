"""Restore locked Helm dependencies using isolated repository registration.
No cluster access and no changes to the operator's Helm repository configuration.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import yaml
ROOT=Path(__file__).resolve().parents[2]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--chart',type=Path,default=ROOT/'k8s/charts/cluster-addons');a=parser.parse_args()
    chart=a.chart.resolve();dependencies=yaml.safe_load((chart/'Chart.yaml').read_text()).get('dependencies',[])
    if not (chart/'Chart.lock').is_file():raise SystemExit('Reviewed Chart.lock required')
    helm=os.environ.get('HELM_BIN','helm')
    with tempfile.TemporaryDirectory(prefix='eks-helm-repos-') as directory:
        env={**os.environ,'HELM_REPOSITORY_CONFIG':str(Path(directory)/'repositories.yaml'),'HELM_REPOSITORY_CACHE':str(Path(directory)/'cache')}
        for i,url in enumerate(sorted({d['repository'] for d in dependencies})):
            if not url.startswith('https://'):raise SystemExit('Only reviewed HTTPS repositories supported')
            subprocess.run([helm,'repo','add',f'rc-{i}',url],env=env,check=True)
        subprocess.run([helm,'dependency','build',str(chart),'--skip-refresh'],env=env,check=True)
if __name__=='__main__':main()
