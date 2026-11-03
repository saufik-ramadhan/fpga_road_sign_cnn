"""Check the real CNN and Basys 3 top against the sealed P2 v2 vectors."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PACKAGE = REPO / 'reference_model/models/p2-doc-int-v2'
OUT = REPO / 'build/integration_sim'


def concat_vectors(package, entries, source_name, target):
    target.write_text(''.join((package / 'vectors' / e['name'] / source_name).read_text(encoding='utf-8')
                              for e in entries), encoding='utf-8')


def main(package=PACKAGE, out=OUT, d42=False):
    for name, digest in json.loads((package / 'checksums.json').read_text()).items():
        if hashlib.sha256((package / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Model checksum mismatch: {name}')
    out.mkdir(parents=True, exist_ok=True)
    memories = ['conv_weight', 'conv_bias', 'fc_weight', 'fc_bias']
    if d42:
        memories += ['conv2_weight', 'conv2_bias']
    for name in memories:
        shutil.copyfile(package / 'mem' / f'{name}.mem', out / f'{name}.mem')
    shutil.copyfile(package / 'signs.mem', out / 'signs.mem')
    entries = json.loads((package / 'vectors/manifest.json').read_text(encoding='utf-8'))
    vectors = [('input.mem', 'pixels.mem'), ('pool.mem', 'pool.mem'),
               ('scores.mem', 'scores.mem'), ('prediction.mem', 'prediction.mem')]
    if d42:
        vectors.extend((name, name) for name in ('conv_acc.mem', 'activation.mem', 'conv2_acc.mem', 'activation2.mem'))
    for source, target in vectors:
        concat_vectors(package, entries, source, out / target)
    by_source = {e['source']: e for e in entries if 'label' in e}
    stored = json.loads((package / 'stored_manifest.json').read_text(encoding='utf-8'))
    if [e['index'] for e in stored] != list(range(16)):
        raise ValueError('Expected sixteen ordered stored images')
    stored_entries = stored if d42 else [by_source[e['source']] for e in stored]
    concat_vectors(package, stored_entries, 'scores.mem', out / 'stored_scores.mem')
    concat_vectors(package, stored_entries, 'prediction.mem', out / 'stored_prediction.mem')
    for source, target in (('input.mem', 'live_pixels.mem'), ('scores.mem', 'live_scores.mem'),
                           ('prediction.mem', 'live_prediction.mem')):
        concat_vectors(package, entries[:1], source, out / target)
    weights = [0] * 3136
    weights[:2] = [1, 255]
    (out / 'edge_weight.mem').write_text(''.join(f'{v:02x}\n' for v in weights), encoding='utf-8')
    (out / 'edge_bias.mem').write_text('7ffff0\n' + '000000\n' * 7, encoding='utf-8')
    sources = [REPO / line.strip() for line in (REPO / 'rtl/files.f').read_text(encoding='utf-8').splitlines()
               if line.strip() and not line.lstrip().startswith('#')]
    if d42:
        edge = [0] * 576
        edge[4:6] = [2, 254]
        (out / 'conv2_edge_weight.mem').write_text(''.join(f'{v:02x}\n' for v in edge), encoding='utf-8')
        (out / 'conv2_edge_bias.mem').write_text('7ffff0\n' + '000000\n' * 7, encoding='utf-8')
    tops = ('conv2_edges_tb', 'cnn_core_tb', 'top_basys3_tb') if d42 else ('classification_edges_tb', 'cnn_core_tb', 'top_basys3_tb')
    flags = ['-DTEST_D42', '-I', str(package)] if d42 else []
    for top in tops:
        binary = out / f'{top}.vvp'
        compiled = subprocess.run(['iverilog', '-g2005', '-Wall', f'-DN_IMG={len(entries)}',
                                   *flags, '-s', top, '-o', str(binary), *map(str, sources), str(HERE / f'{top}.v')],
                                  cwd=out, capture_output=True, text=True, timeout=60)
        log = compiled.stdout + compiled.stderr
        if compiled.returncode == 0:
            simulated = subprocess.run(['vvp', '-n', str(binary)], cwd=out, capture_output=True,
                                       text=True, timeout=120)
            log += simulated.stdout + simulated.stderr
        (out / f'{top}.log').write_text(log, encoding='utf-8')
        passed = compiled.returncode == 0 and simulated.returncode == 0 and log.count('PASS ') == 1 and 'FAIL' not in log and 'ERROR' not in log
        print(log.strip())
        if not passed:
            return 1
    print(f'{len(tops)} of {len(tops)} integration tests passed; logs in {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main() or main(REPO / 'experiments/traffic_sign_d42/models/p2-doc-d42-int24-v1',
                            REPO / 'build/integration_sim_d42', d42=True))
