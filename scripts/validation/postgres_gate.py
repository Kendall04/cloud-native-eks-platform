"""Fail-closed PostgreSQL CI gates; does not provision or contact AWS."""
import os
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET


def check_trx(path):
    counters=ET.parse(path).find('.//{*}Counters')
    if counters is None or int(counters.attrib.get('total',0))==0 or int(counters.attrib.get('notExecuted',0))!=0 or int(counters.attrib.get('failed',0))!=0 or int(counters.attrib['passed'])!=int(counters.attrib['total']):
        raise ValueError('Required PostgreSQL suite incomplete, failed or skipped')


def main():
    if sys.argv[1]=='trx': check_trx(sys.argv[2]); return
    if not os.environ.get('R3_POSTGRES_TEST_DSN'): raise SystemExit('R3_POSTGRES_TEST_DSN required; skipping is forbidden')
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_postgres_r3.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped or result.testsRun==0: raise SystemExit('Required PostgreSQL permission tests did not all execute')

if __name__=='__main__': main()
