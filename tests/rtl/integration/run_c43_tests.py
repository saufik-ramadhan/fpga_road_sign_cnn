"""Run C-43 RTL integration on vectors exported by evaluate_c43.py."""
import argparse
import json
from pathlib import Path
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('vectors', type=Path)
    parser.add_argument('--board-package', type=Path)
    args = parser.parse_args()
    out = args.vectors.resolve()
    metadata = json.loads((out / 'rtl_vectors.json').read_text())
    top = 'c43_datapath_tb'
    parameters = [f'-P{top}.N_IMG={len(metadata["sources"])}',
                  f'-P{top}.M={metadata["multiplier"]}', f'-P{top}.S={metadata["shift"]}']
    if args.board_package:
        package = args.board_package
        top = 'c43_board_tb'
        parameters = []
        out = out / 'board_sim'
        out.mkdir(exist_ok=True)
        shutil.copyfile(package / 'signs.mem', out / 'signs.mem')
        for memory in (package / 'mem').glob('*.mem'):
            shutil.copyfile(memory, out / memory.name)
        entries = json.loads((package / 'stored_manifest.json').read_text())
        (out / 'stored_classes.mem').write_text(''.join(f'{entry["golden_class"]:02x}\n' for entry in entries))
    sources = [ROOT / line.strip() for line in (ROOT / 'rtl/files.f').read_text().splitlines()
               if line.strip() and not line.lstrip().startswith('#')]
    commands = [
        ['iverilog', '-g2001', '-Wall', '-s', top, '-o', top+'.vvp',
         *parameters, *map(str, sources), str(Path(__file__).with_name(top+'.v').resolve())],
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
