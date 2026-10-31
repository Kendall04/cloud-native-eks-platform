"""Run every active platform regression; an empty or entirely skipped suite fails."""
import argparse
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / 'scripts/validation'


def files(group):
    if group not in {'platform', 'all'}:
        raise ValueError('Unknown active regression group: ' + group)
    return sorted(DIRECTORY.glob('test_*.py'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('family', choices=['platform', 'all'])
    args = parser.parse_args()
    sys.path.insert(0, str(DIRECTORY))
    suite = unittest.TestSuite()
    for path in files(args.family):
        suite.addTests(unittest.defaultTestLoader.discover(str(DIRECTORY), pattern=path.name))
    if suite.countTestCases() == 0:
        raise SystemExit('No active regression tests were discovered')
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    print(f'{args.family}: {result.testsRun} tests, {len(result.skipped)} skipped, {time.monotonic() - started:.1f}s')
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun > len(result.skipped) else 1)


if __name__ == '__main__':
    main()
