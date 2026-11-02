"""Run the categorized RTL suites from any working directory."""
import argparse
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('all', 'p3', 'p5', 'integration'), default='all')
    args = parser.parse_args()
    commands = []
    if args.suite in ('all', 'p3'):
        commands += [[sys.executable, '-m', 'unittest', 'discover', '-s',
                      'tests/rtl/p3', '-p', 'test_run_p3_tests.py'],
                     [sys.executable, '-u', 'tests/rtl/p3/run_p3_tests.py']]
    if args.suite in ('all', 'p5'):
        commands.append([sys.executable, '-u', 'tests/rtl/p5/run_p5_tests.py'])
    if args.suite in ('all', 'integration'):
        commands.append([sys.executable, '-u', 'tests/rtl/integration/run_integration_tests.py'])
    failed = False
    for command in commands:
        result = subprocess.run(command, cwd=REPO)
        failed = result.returncode != 0 or failed
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
