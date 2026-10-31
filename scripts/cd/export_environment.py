"""Operator-only publication of R3 output metadata; CI cannot write this prefix.

This command writes S3 when explicitly invoked. It is not a validation command.
"""
import argparse
import json
from pathlib import Path
import sys
import boto3
from common import ROOT, sha, require
from publish import put_once
sys.path.insert(0,str(ROOT/'scripts/bootstrap'))
from environment import validate_contract
from synthetic_contract import scope_identity


def export_key(data, expected_environment='dev', expected_data_scope=None):
    contract = json.loads(data)
    validate_contract(contract, expected_environment, ready=True)
    scope = contract.get('dataScope')
    if scope is not None:
        scope_identity(expected_data_scope)
    require(scope == expected_data_scope, 'Explicit export scope mismatch')
    return f'environment-contracts/{expected_environment}/' + sha(data) + '.json'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--environment-file',type=Path,required=True)
    parser.add_argument('--bucket',required=True)
    parser.add_argument('--environment')
    parser.add_argument('--synthetic-scope',type=Path)
    args=parser.parse_args()
    data=args.environment_file.read_bytes(); contract=json.loads(data)
    if args.synthetic_scope:
        require(args.environment is not None, 'Explicit synthetic export environment required')
    key=export_key(data,args.environment or 'dev',json.loads(args.synthetic_scope.read_text()) if args.synthetic_scope else None)
    client=boto3.client('s3',region_name=contract['region'])
    print(json.dumps(put_once(client,args.bucket,key,data),indent=2))


if __name__=='__main__': main()
