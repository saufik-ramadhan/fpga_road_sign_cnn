#!/usr/bin/env python3
"""Uji subsistem P4 (maxpool, fc_engine, dan rantainya) pada vektor reference model P2.

Tiap subfolder di --vectors harus berisi (format P2, satu kata hex per baris):
    activation.mem  pool.mem  scores.mem  prediction.mem
Bobot FC diambil dari --mem (fc_weight.mem dan fc_bias.mem).

Tiga uji per vektor:
    maxpool   activation.mem -> maxpool -> harus sama dengan pool.mem
    fc        pool.mem -> fc_engine -> harus sama dengan scores.mem
    rantai    activation.mem -> maxpool -> pool_ram -> fc_engine -> argmax:
              pool, 8 skor, dan class harus sama dengan pool.mem, scores.mem, prediction.mem

Folder --rtl harus berisi: maxpool.v fc_engine.v argmax.v tb_maxpool.v tb_fc_engine.v tb_p4_chain.v

    python run_p4_vectors.py --vectors <folder vectors> --mem <folder .mem P2>
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEEDED = ['activation.mem', 'pool.mem', 'scores.mem', 'prediction.mem']


def build(rtl, work):
    sims = {}
    cmds = {
        'maxpool': ['-P', 'tb_maxpool.IN_W=14', '-P', 'tb_maxpool.FA_W=11', '-P', 'tb_maxpool.PA_W=9',
                    'tb_maxpool.v', 'maxpool.v'],
        'fc': ['tb_fc_engine.v', 'fc_engine.v'],
        'rantai': ['tb_p4_chain.v', 'maxpool.v', 'fc_engine.v', 'argmax.v'],
    }
    for name, parts in cmds.items():
        sim = work / f'sim_{name}'
        flags = [p for p in parts if not p.endswith('.v')]
        files = [str(rtl / p) for p in parts if p.endswith('.v')]
        subprocess.run(['iverilog', '-g2005', *flags, '-o', str(sim), *files], check=True,
                       capture_output=True)
        sims[name] = sim
    return sims


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--vectors', required=True)
    ap.add_argument('--mem', default=str(HERE))
    ap.add_argument('--rtl', default=str(HERE))
    ap.add_argument('--work', default=str(HERE / 'p4_work'))
    args = ap.parse_args()
    mem, rtl, work, vec = (Path(a).resolve() for a in (args.mem, args.rtl, args.work, args.vectors))
    work.mkdir(parents=True, exist_ok=True)
    sims = build(rtl, work)

    vectors = sorted(p for p in vec.iterdir() if p.is_dir() and all((p / n).exists() for n in NEEDED))
    if not vectors:
        sys.exit(f'Tidak ada subfolder vektor lengkap di {vec} (butuh {", ".join(NEEDED)})')
    totals = {k: [0, 0] for k in sims}
    failed, last_ok = [], {}
    for v in vectors:
        d = work / v.name
        d.mkdir(exist_ok=True)
        for n in NEEDED:
            shutil.copyfile(v / n, d / n)
        shutil.copyfile(v / 'activation.mem', d / 'fmap.mem')       # nama yang dibaca tb_maxpool
        shutil.copyfile(v / 'pool.mem', d / 'pool_expected.mem')
        for n in ('fc_weight.mem', 'fc_bias.mem'):
            shutil.copyfile(mem / n, d / n)
        for name, sim in sims.items():
            run = subprocess.run(['vvp', '-n', str(sim)], cwd=d, capture_output=True, text=True)
            out = run.stdout + run.stderr
            ok = any(l.startswith('PASS') for l in run.stdout.splitlines()) and 'FAIL' not in out
            totals[name][1] += 1
            if ok:
                totals[name][0] += 1
                last_ok[name] = next(l for l in run.stdout.splitlines() if l.startswith('PASS'))
            else:
                failed.append((v.name, name, ' | '.join(l for l in out.splitlines() if 'FAIL' in l)[:250] or out[:250]))
    print(f'{len(vectors)} vektor dari {vec}')
    for name, (ok, n) in totals.items():
        print(f'{name:8s}: {ok}/{n} PASS')
    for f in failed:
        print('GAGAL', *f)
    for name, line in last_ok.items():
        print(f'contoh {name}: {line}')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()