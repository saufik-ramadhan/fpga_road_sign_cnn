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
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PACKAGE = REPO / 'reference_model/models/p2-int-v1'
NEEDED = ['activation.mem', 'pool.mem', 'scores.mem', 'prediction.mem']


def validate_mem(path, count, bits, maximum=None):
    words = path.read_text().split()
    if len(words) != count or any(not re.fullmatch('[0-9a-fA-F]+', w) for w in words):
        raise ValueError(f'{path}: expected {count} known hexadecimal words')
    limit = (1 << bits) - 1 if maximum is None else maximum
    if any(int(w, 16) > limit for w in words):
        raise ValueError(f'{path}: value outside 0..{limit}')


def simulate(sim, directory, name):
    run = subprocess.run(['vvp', '-n', str(sim)], cwd=directory, capture_output=True,
                         text=True, timeout=60)
    out = run.stdout + run.stderr
    (directory / f'{name}.log').write_text(out, encoding='utf-8')
    ok = (run.returncode == 0 and any(l.startswith('PASS') for l in run.stdout.splitlines())
          and not re.search(r'FAIL|ERROR|FATAL|WARNING', out, re.IGNORECASE))
    return ok, out


def build(rtl, work):
    sims = {}
    cmds = {
        'maxpool': ['-P', 'tb_maxpool.IN_W=14', '-P', 'tb_maxpool.FA_W=11', '-P', 'tb_maxpool.PA_W=9',
                    'tb_maxpool.v', 'maxpool.v'],
        'fc': ['tb_fc_engine.v', 'fc_engine.v'],
        'rantai': ['tb_p4_chain.v', 'maxpool.v', 'fc_engine.v', 'argmax.v'],
        'argmax': ['tb_argmax.v', 'argmax.v'],
        'display': ['tb_sign_display.v', 'sign_display.v'],
    }
    for name, parts in cmds.items():
        sim = work / f'sim_{name}'
        flags = [p for p in parts if not p.endswith('.v')]
        files = [str(rtl / p) for p in parts if p.endswith('.v')]
        top = {'maxpool': 'tb_maxpool', 'fc': 'tb_fc_engine', 'rantai': 'tb_p4_chain',
               'argmax': 'tb_argmax', 'display': 'tb_sign_display'}[name]
        run = subprocess.run(['iverilog', '-g2001', '-s', top, *flags, '-o', str(sim), *files],
                             capture_output=True, text=True, timeout=60)
        (work / f'{name}_compile.log').write_text(run.stdout + run.stderr, encoding='utf-8')
        run.check_returncode()
        sims[name] = sim
    return sims


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--vectors', help='custom vectors; default generates 15 P2 v1 vectors')
    ap.add_argument('--mem', default=str(PACKAGE / 'mem'))
    ap.add_argument('--rtl', default=str(HERE))
    ap.add_argument('--work', default=str(REPO / 'build/p4_sim'))
    args = ap.parse_args()
    mem, rtl, work = (Path(a).resolve() for a in (args.mem, args.rtl, args.work))
    work.mkdir(parents=True, exist_ok=True)
    vec = Path(args.vectors).resolve() if args.vectors else work / 'vectors'
    if not args.vectors:
        subprocess.run([sys.executable, '-I', str(HERE / 'gen_golden_vectors.py'),
                        str(PACKAGE), str(vec), '--mem', str(mem)], check=True, timeout=60)
    validate_mem(mem / 'fc_weight.mem', 3136, 8)
    validate_mem(mem / 'fc_bias.mem', 8, 32)
    vectors = sorted(p for p in vec.iterdir() if p.is_dir())
    if not vectors:
        raise ValueError(f'No vectors in {vec}')
    for v in vectors:
        for name, count, bits, maximum in [('activation.mem', 1568, 8, 127),
                ('pool.mem', 392, 8, 127), ('scores.mem', 8, 32, None),
                ('prediction.mem', 1, 8, 7)]:
            validate_mem(v / name, count, bits, maximum)
    sims = build(rtl, work)
    totals = {k: [0, 0] for k in ('maxpool', 'fc', 'rantai')}
    failed, last_ok = [], {}
    for name in ('argmax', 'display'):
        ok, out = simulate(sims[name], work, name)
        print(f'{name}: {"PASS" if ok else "FAIL"}')
        if not ok:
            failed.append(('standalone', name, out[:500]))
    for v in vectors:
        d = work / v.name
        d.mkdir(exist_ok=True)
        for n in NEEDED:
            shutil.copyfile(v / n, d / n)
        shutil.copyfile(v / 'activation.mem', d / 'fmap.mem')       # nama yang dibaca tb_maxpool
        shutil.copyfile(v / 'pool.mem', d / 'pool_expected.mem')
        for n in ('fc_weight.mem', 'fc_bias.mem'):
            shutil.copyfile(mem / n, d / n)
        for name in totals:
            ok, out = simulate(sims[name], d, name)
            totals[name][1] += 1
            if ok:
                totals[name][0] += 1
                last_ok[name] = next(l for l in out.splitlines() if l.startswith('PASS'))
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
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        sys.exit(f'FAIL P4: {exc}')
