#!/usr/bin/env python3
"""Hasilkan vektor golden ASLI dari paket P2 (parameters.npz + contract.json + golden.py).

Berbeda dari gen_chain_vectors.py (yang menghitung ulang dengan NumPy sendiri),
skrip ini memanggil golden.infer() milik P2 langsung, jadi jawaban yang dihasilkan
adalah golden reference yang otoritatif.

Untuk tiap input, tulis 4 file yang dibutuhkan testbench P4:
    activation.mem  (8x14x14 uint8)  -> input maxpool
    pool.mem        (8x7x7  uint8)  -> output maxpool yg diharapkan
    scores.mem      (8       int32) -> output fc yg diharapkan
    prediction.mem  (1       uint8) -> output argmax yg diharapkan

Pakai:
    python -I gen_golden_vectors.py <folder_paket_p2> <folder_keluaran> [--mem .]
"""
import argparse
import sys
from pathlib import Path
import numpy as np


def write_mem(path, values, bits):
    # Format identik dengan quantize.py milik P2: hex huruf kecil, two's complement.
    mask = (1 << bits) - 1
    encoded = [format(int(v) & mask, f'0{bits//4}x') for v in np.asarray(values).ravel()]
    path.write_text('\n'.join(encoded) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pkg', type=Path, help='folder berisi parameters.npz, contract.json, golden.py')
    ap.add_argument('out', type=Path, help='folder keluaran vektor')
    ap.add_argument('--mem', type=Path, default=Path('.'),
                    help='folder berisi fc_weight.mem/fc_bias.mem untuk diverifikasi')
    args = ap.parse_args()

    # Impor golden.py milik P2
    sys.path.insert(0, str(args.pkg.resolve()))
    import golden

    params, contract = golden.load_model(args.pkg)
    side = contract['image_size']
    print(f"Kontrak: {contract['version']}, image_size={side}, filters={contract['filters']}")

    # --- Verifikasi fc_weight.mem/fc_bias.mem yang dipakai RTL == parameters.npz ---
    for name, bits in (('fc_weight', 8), ('fc_bias', 32)):
        mem_path = args.mem / f'{name}.mem'
        if mem_path.exists():
            tmp = args.out / f'_check_{name}.mem'
            args.out.mkdir(parents=True, exist_ok=True)
            write_mem(tmp, params[name], bits)
            same = tmp.read_text().split() == mem_path.read_text().split()
            tmp.unlink()
            print(f"  {name}.mem {'COCOK' if same else 'BEDA!!'} dengan parameters.npz")
            if not same:
                sys.exit(f'FATAL: {name}.mem tidak cocok dengan parameters.npz')
        else:
            print(f"  (lewati verifikasi {name}.mem — tidak ditemukan di {args.mem})")

    # --- Daftar input: 5 sintetis terarah (sama seperti suite P2) + beberapa acak ---
    cases = []
    cases.append(('zeros', np.zeros((1, side, side), dtype=np.uint8)))
    cases.append(('maximum', np.full((1, side, side), 255, dtype=np.uint8)))
    cases.append(('checkerboard', ((np.indices((side, side)).sum(0) % 2) * 255).astype(np.uint8)[None]))
    cases.append(('ramp', (np.arange(side * side, dtype=np.int64) % 256).astype(np.uint8).reshape(1, side, side)))
    impulse = np.zeros((1, side, side), dtype=np.uint8); impulse[0, side // 2, side // 2] = 255
    cases.append(('impulse', impulse))
    for s in range(10):
        rng = np.random.default_rng(1000 + s)
        cases.append((f'acak_{s:02d}', rng.integers(0, 256, (1, side, side), dtype=np.uint8)))

    args.out.mkdir(parents=True, exist_ok=True)
    for name, img in cases:
        trace = golden.infer(img[None], params, contract)   # batch 1
        folder = args.out / name
        folder.mkdir(exist_ok=True)
        write_mem(folder / 'activation.mem', trace['activation'][0], 8)
        write_mem(folder / 'pool.mem',       trace['pool'][0],       8)
        write_mem(folder / 'scores.mem',     trace['scores'][0],     32)
        write_mem(folder / 'prediction.mem', trace['prediction'][0], 8)

    print(f"{len(cases)} vektor golden ditulis ke {args.out} "
          f"(5 sintetis + 10 acak, dari golden.infer asli P2)")


if __name__ == '__main__':
    main()