"""Run C-43 RTL integration on vectors exported by evaluate_c43.py."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('vectors', type=Path)
    args = parser.parse_args()
    out = args.vectors.resolve()
    metadata = json.loads((out / 'rtl_vectors.json').read_text())
    top = 'c43_datapath_tb'
    sources = [ROOT / line.strip() for line in (ROOT / 'rtl/files.f').read_text().splitlines()
               if line.strip() and not line.lstrip().startswith('#')]
    commands = [
        ['iverilog', '-g2001', '-Wall', '-s', top, '-o', top+'.vvp',
         f'-P{top}.N_IMG={len(metadata["sources"])}', f'-P{top}.M={metadata["multiplier"]}',
         f'-P{top}.S={metadata["shift"]}', *map(str, sources), str(Path(__file__).with_name(top+'.v').resolve())],
        ['vvp', '-n', top+'.vvp'],
    ]
    logs = []
    for command in commands:
        result = subprocess.run(command, cwd=out, capture_output=True, text=True, timeout=180)
        logs.append(result.stdout + result.stderr)
        if result.returncode:
            break
    log = ''.join(logs)
    (out / 'rtl.log').write_text(log)
    print(log.strip())
    return int(result.returncode != 0 or log.count('PASS ') != 1 or 'FAIL' in log or 'ERROR' in log)


if __name__ == '__main__':
    raise SystemExit(main())
