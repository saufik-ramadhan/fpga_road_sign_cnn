#!/usr/bin/env python3
"""Bangkitkan vektor dummy untuk menguji rantai P4: fmap -> maxpool -> fc_engine -> argmax.

Tiap vektor berisi aktivasi dummy (uint8 0..127) PLUS kunci jawabannya yang dihitung
di Python (pool, scores, prediction), memakai fc_weight.mem & fc_bias.mem yang asli.
Hasilnya langsung bisa dipakai run_p4_vectors.py.

    python gen_chain_vectors.py <folder keluaran> [--size 14|30] [--mem .]
"""
import argparse
from pathlib import Path
import numpy as np


def rd(path, bits, signed):
    vals = [int(t, 16) for t in Path(path).read_text().split()]
    if signed:
        vals = [v - (1 << bits) if v >= 1 << (bits - 1) else v for v in vals]
    return np.array(vals, dtype=np.int64)


def wr(path, values, bits):
    mask = (1 << bits) - 1
    Path(path).write_text('\n'.join(format(int(v) & mask, '0%dx' % (bits // 4))
                                     for v in np.asarray(values).ravel()) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--size', type=int, default=14, help='IN_W: 14 (16x16) atau 30 (32x32)')
    ap.add_argument('--mem', default='.', help='folder berisi fc_weight.mem dan fc_bias.mem')
    args = ap.parse_args()
    NF, IN_W = 8, args.size
    OUT_W = IN_W // 2
    N_IN = NF * OUT_W * OUT_W
    mem = Path(args.mem)
    fw = rd(mem / 'fc_weight.mem', 8, True).reshape(8, -1)
    fb = rd(mem / 'fc_bias.mem', 32, True)
    assert fw.shape[1] == N_IN, f'fc_weight.mem {fw.shape[1]} input, tapi size butuh {N_IN}'

    rng = np.random.default_rng(2026)
    cases = {}
    cases['nol'] = np.zeros((NF, IN_W, IN_W), dtype=np.int64)
    cases['penuh'] = np.full((NF, IN_W, IN_W), 127, dtype=np.int64)
    hot = np.zeros((NF, IN_W, IN_W), dtype=np.int64); hot[:, 1, 1] = 127; cases['satu_titik'] = hot
    ramp = np.tile(np.arange(IN_W * IN_W).reshape(IN_W, IN_W) % 128, (NF, 1, 1)); cases['ramp'] = ramp
    for i in range(12):
        cases[f'acak_{i:02d}'] = rng.integers(0, 128, (NF, IN_W, IN_W), dtype=np.int64)

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    for name, act in cases.items():
        pool = act.reshape(NF, OUT_W, 2, OUT_W, 2).max(axis=(2, 4))      # maxpool 2x2 s2
        pflat = pool.reshape(-1)                                          # CHW: f, r, c
        scores = fw @ pflat + fb                                         # fc
        assert scores.min() >= -2**31 and scores.max() <= 2**31 - 1, f'{name}: skor lewat int32'
        pred = int(scores.argmax())                                      # argmax, seri -> indeks kecil
        d = out / name; d.mkdir(exist_ok=True)
        wr(d / 'activation.mem', act.reshape(-1), 8)
        wr(d / 'pool.mem', pflat, 8)
        wr(d / 'scores.mem', scores, 32)
        wr(d / 'prediction.mem', [pred], 8)
    print(f'{len(cases)} vektor dummy ditulis ke {out} (IN_W={IN_W}, N_IN={N_IN})')


if __name__ == '__main__':
    main()