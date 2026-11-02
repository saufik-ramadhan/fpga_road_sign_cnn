"""Read-only workspace preflight; no installation, fetch, generation or tests.

python scripts/check_workspace.py [--full-model] [--vivado]
"""
import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]


def run(command):
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or f'command failed: {command[0]}')
    return result.stdout.strip()


def check_sources():
    sources = []
    for line in (REPO / 'rtl/files.f').read_text(encoding='utf-8').splitlines():
        entry = line.strip()
        if not entry or entry.startswith('#'):
            continue
        path = (REPO / entry).resolve()
        if Path(entry).is_absolute() or not path.is_relative_to(REPO / 'rtl') or not path.is_file() or path.suffix != '.v':
            raise ValueError(f'invalid/missing production source: {entry}')
        sources.append(path)
    if not sources or len(set(sources)) != len(sources):
        raise ValueError('production source manifest is empty or has duplicates')
    omitted = set((REPO / 'rtl').rglob('*.v')) - set(sources)
    if omitted:
        raise ValueError('production files missing from rtl/files.f: ' +
                         ', '.join(str(p.relative_to(REPO)) for p in sorted(omitted)))
    return f'{len(sources)} production Verilog sources'


def check_package(package):
    checksums = json.loads((package / 'checksums.json').read_text(encoding='utf-8'))
    if not isinstance(checksums, dict) or not checksums:
        raise ValueError('empty/invalid checksum manifest')
    for name, digest in checksums.items():
        path = (package / name).resolve()
        if not path.is_relative_to(package) or not path.is_file():
            raise ValueError(f'invalid/missing package file: {name}')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'checksum mismatch: {name}; restore the published package')
    return f'{package.name}: {len(checksums)} file hashes match'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full-model', action='store_true', help='also require torch and matplotlib')
    parser.add_argument('--vivado', action='store_true', help='also require Vivado on PATH')
    args = parser.parse_args()
    failed = 0

    def check(name, function):
        nonlocal failed
        try:
            print(f'PASS {name}: {function()}')
        except (OSError, ValueError, TypeError, subprocess.SubprocessError, metadata.PackageNotFoundError) as error:
            failed += 1
            print(f'FAIL {name}: {error}')

    def python_version():
        if sys.version_info < (3, 11):
            raise ValueError('Python >=3.11 required; shared setup uses 3.11')
        return f'{sys.version.split()[0]} ({sys.executable})'

    def tool(name, version_args):
        path = shutil.which(name)
        if not path:
            raise ValueError(f'{name} not on PATH; see docs/GITHUB_WORKFLOW.md')
        result = subprocess.run([path, *version_args], cwd=REPO,
                                capture_output=True, text=True, timeout=30)
        output = (result.stdout + result.stderr).strip()
        # Vivado 2026.1 on Windows returns 1 for a successful -version banner.
        version_only = name == 'vivado' and result.returncode == 1 and output.lower().startswith('vivado v')
        if result.returncode and not version_only:
            raise ValueError(output or f'version check failed: {path}')
        version = output.splitlines()
        return f'{path}; {version[0] if version else "available"}'

    print(f'Workspace: {REPO}')
    check('Python', python_version)
    check('Git', lambda: tool('git', ['--version']))
    if shutil.which('git'):
        check('HEAD', lambda: run(['git', 'rev-parse', 'HEAD']))
        check('branch', lambda: run(['git', 'rev-parse', '--abbrev-ref', 'HEAD']))
        check('base origin/main', lambda: run(['git', 'rev-parse', 'origin/main']))
        check('working tree', lambda: 'has local changes; preserve them' if run(['git', 'status', '--short']) else 'clean')
        print('INFO fetch origin before a task; this check does not contact the remote.')
    for name in ('numpy', 'Pillow', 'pyserial', 'pytest') + (('torch', 'matplotlib') if args.full_model else ()):
        check(name, lambda name=name: metadata.version(name))
    check('Icarus', lambda: tool('iverilog', ['-V']))
    check('VVP', lambda: tool('vvp', ['-V']))
    if args.vivado:
        check('Vivado', lambda: tool('vivado', ['-version']))
    else:
        print('INFO Vivado not checked; use --vivado for board/top work.')
    check('RTL manifest', check_sources)
    packages = (
        REPO / 'reference_model/models/p2-doc-int-v2',
        REPO / 'reference_model/models/p2-int-v1',
        REPO / 'experiments/traffic_sign_32/models/p2-int-32-v1',
        REPO / 'experiments/mnist_digit/models/mnist-int-v1',
    )
    for package in packages:
        check('model package', lambda package=package: check_package(package))
    print(f'Preflight: {failed} failure(s). This is not a simulation or board test.')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
