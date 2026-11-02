"""Check the real CNN and Basys 3 top against the sealed P2 v2 vectors."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PACKAGE = REPO / 'reference_model/models/p2-doc-int-v2'
OUT = REPO / 'build/integration_sim'


def concat_vectors(entries, source_name, target):
    target.write_text(''.join((PACKAGE / 'vectors' / e['name'] / source_name).read_text(encoding='utf-8')
                              for e in entries), encoding='utf-8')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ('conv_weight', 'conv_bias', 'fc_weight', 'fc_bias'):
        shutil.copyfile(PACKAGE / 'mem' / f'{name}.mem', OUT / f'{name}.mem')
    shutil.copyfile(PACKAGE / 'signs.mem', OUT / 'signs.mem')
    entries = json.loads((PACKAGE / 'vectors/manifest.json').read_text(encoding='utf-8'))
    for source, target in (('input.mem', 'pixels.mem'), ('pool.mem', 'pool.mem'),
                           ('scores.mem', 'scores.mem'), ('prediction.mem', 'prediction.mem')):
        concat_vectors(entries, source, OUT / target)
    by_source = {e['source']: e for e in entries if 'label' in e}
    stored = json.loads((PACKAGE / 'stored_manifest.json').read_text(encoding='utf-8'))
    if [e['index'] for e in stored] != list(range(16)):
        raise ValueError('Expected sixteen ordered stored images')
    stored_entries = [by_source[e['source']] for e in stored]
    concat_vectors(stored_entries, 'scores.mem', OUT / 'stored_scores.mem')
    concat_vectors(stored_entries, 'prediction.mem', OUT / 'stored_prediction.mem')
    for source, target in (('input.mem', 'live_pixels.mem'), ('scores.mem', 'live_scores.mem'),
                           ('prediction.mem', 'live_prediction.mem')):
        concat_vectors(entries[:1], source, OUT / target)
    weights = [0] * 3136
    weights[:2] = [1, 255]
    (OUT / 'edge_weight.mem').write_text(''.join(f'{v:02x}\n' for v in weights), encoding='utf-8')
    (OUT / 'edge_bias.mem').write_text('7ffff0\n' + '000000\n' * 7, encoding='utf-8')
    sources = [REPO / line.strip() for line in (REPO / 'rtl/files.f').read_text(encoding='utf-8').splitlines()
               if line.strip() and not line.lstrip().startswith('#')]
    for top in ('classification_edges_tb', 'cnn_core_tb', 'top_basys3_tb'):
        binary = OUT / f'{top}.vvp'
        compiled = subprocess.run(['iverilog', '-g2005', '-Wall', f'-DN_IMG={len(entries)}',
                                   '-s', top, '-o', str(binary), *map(str, sources), str(HERE / f'{top}.v')],
                                  cwd=OUT, capture_output=True, text=True, timeout=60)
        log = compiled.stdout + compiled.stderr
        if compiled.returncode == 0:
            simulated = subprocess.run(['vvp', '-n', str(binary)], cwd=OUT, capture_output=True,
                                       text=True, timeout=120)
            log += simulated.stdout + simulated.stderr
        (OUT / f'{top}.log').write_text(log, encoding='utf-8')
        passed = compiled.returncode == 0 and simulated.returncode == 0 and log.count('PASS ') == 1 and 'FAIL' not in log and 'ERROR' not in log
        print(log.strip())
        if not passed:
            return 1
    print(f'3 of 3 integration tests passed; logs in {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
