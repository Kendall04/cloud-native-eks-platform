"""Bounded ECR BASIC scan gate. No image promotion on unknown/failed scanning.
Called only during authorized release publication; tests use fake clients.
"""
import time
from botocore.exceptions import ClientError


def require_clean_scan(ecr, repository, digest, timeout=600, clock=time.monotonic, sleep=time.sleep):
    deadline=clock()+timeout
    while clock()<deadline:
        try:
            result=ecr.describe_image_scan_findings(repositoryName=repository,imageId={'imageDigest':digest})
        except ClientError as error:
            if error.response['Error']['Code']!='ScanNotFoundException': raise
            sleep(5); continue
        status=result.get('imageScanStatus',{}).get('status')
        if status=='COMPLETE':
            findings=result.get('imageScanFindings',{})
            if not findings.get('imageScanCompletedAt') or 'findingSeverityCounts' not in findings:
                raise ValueError('Incomplete ECR scan evidence')
            counts=findings['findingSeverityCounts']
            if any(counts.get(s,0)>0 for s in ('HIGH','CRITICAL')):
                raise ValueError('ECR HIGH/CRITICAL findings block release publication')
            return
        if status not in ('IN_PROGRESS','PENDING'):
            raise ValueError('ECR basic scan not successful: '+str(status))
        sleep(5)
    raise TimeoutError('ECR scan did not finish; no release artifact published')
