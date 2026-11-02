"""Test vectors for P3's testbenches: conv_engine_tb and requant_relu_tb.

Holds an integer reference of the convolution layer, written from P2's
contract (reference_model/README.md#historical-integer-contract-v1): unsigned 8-bit pixels, signed
8-bit weights, an accumulator of acc_w bits (24 in p2-doc-int-v2, 32 in
p2-int-v1) that starts at the bias, and the rescale
min(127, (max(0, acc)*M + R) >> S). p2_vectors.py checks that it gives the
same numbers as P2's golden models.

    python tests/rtl/p3/p3_vectors.py OUTDIR     # writes every vector set into OUTDIR
"""
import random
import sys
from pathlib import Path

IMG = 16                    # input is IMG x IMG, unsigned 8-bit
K = 3                       # kernel size
N_F = 8                     # filters
OUT = IMG - K + 1           # 14
N_OUT = N_F * OUT * OUT     # 1,568
MAX_SUM = 9 * 255 * 127     # 291,465: an all-255 image under all +-127 weights


def acc_range(acc_w):
    return -(1 << (acc_w - 1)), (1 << (acc_w - 1)) - 1


def requant(acc, m, s):
    """The contract's rescale: ReLU first, then round half up, then at most 127."""
    r = (1 << (s - 1)) if s else 0
    return min(127, (max(0, acc) * m + r) >> s)


def wrap(x, acc_w):
    lo = acc_range(acc_w)[0]
    return ((x - lo) & ((1 << acc_w) - 1)) + lo


def conv_acc(pix, w, bias, acc_w):
    """Accumulator of every output in fmap_ram order, plus an overflow flag.

    Adds the bias and then the 9 products in the RTL's order, and wraps at
    acc_w bits as the RTL does, so even overflowing cases match bit for bit
    (the contract forbids overflow; the RTL flags it)."""
    lo, hi = acc_range(acc_w)
    accs = [0] * N_OUT
    ovf = False
    for f in range(N_F):
        for r in range(OUT):
            for c in range(OUT):
                acc = bias[f]
                for kr in range(K):
                    for kc in range(K):
                        acc += pix[(r + kr) * IMG + c + kc] * w[f * 9 + kr * 3 + kc]
                        if not lo <= acc <= hi:
                            ovf = True
                            acc = wrap(acc, acc_w)
                accs[f * OUT * OUT + r * OUT + c] = acc
    return accs, ovf


def conv_layer(pix, w, bias, m, s, acc_w):
    """Activations in fmap_ram order (filter*196 + row*14 + col), and the overflow flag."""
    accs, ovf = conv_acc(pix, w, bias, acc_w)
    return [requant(a, m, s) for a in accs], ovf


# ---- file writers -----------------------------------------------------------

def write_mem(path, values, digits):
    mask = (1 << (4 * digits)) - 1
    Path(path).write_text("".join(f"{v & mask:0{digits}x}\n" for v in values))


def write_params(path, m, s, acc_w):
    assert 1 <= m <= 0xFFFF and 0 <= s <= 47 and acc_w % 4 == 0
    Path(path).write_text(
        "// params.vh for a P3 test set: the rescale constants and accumulator width\n"
        f"localparam [15:0]  CONV_M     = 16'd{m};\n"
        f"localparam integer CONV_S     = {s};\n"
        f"localparam integer CONV_ACC_W = {acc_w};\n")


# ---- vector sets --------------------------------------------------------------

def pattern_images():
    rows = range(IMG)
    cols = range(IMG)
    disc = [255 if (r - 7.5) ** 2 + (c - 7.5) ** 2 <= 36 else 30 for r in rows for c in cols]
    return [
        [0] * 256,
        [255] * 256,
        [255 * ((r + c) % 2) for r in rows for c in cols],             # checkerboard
        [17 * r for r in rows for c in cols],                          # vertical ramp
        [17 * c for r in rows for c in cols],                          # horizontal ramp
        [255 if (r, c) == (7, 7) else 0 for r in rows for c in cols],  # one bright pixel
        disc,                                                          # a round sign
    ]


def write_conv_set(outdir, images, w, bias, m, s, acc_w):
    """pixels.mem, conv_weight.mem, conv_bias.mem (acc_w-bit words), conv_acc.mem
    (32-bit words), conv_out.mem and params.vh."""
    lo, hi = acc_range(acc_w)
    assert len(bias) == N_F and all(lo <= b <= hi for b in bias)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    accs, acts, flags = [], [], []
    for pix in images:
        a, ovf = conv_acc(pix, w, bias, acc_w)
        accs += a
        acts += [requant(v, m, s) for v in a]
        flags.append(ovf)
    write_mem(outdir / "pixels.mem", [p for img in images for p in img], 2)
    write_mem(outdir / "conv_weight.mem", w, 2)
    write_mem(outdir / "conv_bias.mem", bias, acc_w // 4)
    write_mem(outdir / "conv_acc.mem", accs, 8)
    write_mem(outdir / "conv_out.mem", acts, 2)
    write_params(outdir / "params.vh", m, s, acc_w)
    zeros = sum(a == 0 for a in acts) / len(acts)
    tops = sum(a == 127 for a in acts) / len(acts)
    return {"images": len(images), "ovf": flags, "zeros": zeros, "clamped127": tops}


def conv_model(outdir, n=20, seed=2026, acc_w=24):
    """A random model on n images: weights -127..127, mid-size biases, and M chosen
    so the outputs spread over 0..127 instead of sitting on the clamps."""
    rng = random.Random(seed)
    images = pattern_images()
    while len(images) < n:
        images.append([rng.randrange(256) for _ in range(256)])
    images = images[:n]
    w = [rng.randint(-127, 127) for _ in range(N_F * 9)]
    bias = [rng.randint(-40000, 40000) for _ in range(N_F)]
    s = 20
    positive = sorted(a for pix in images for a in conv_acc(pix, w, bias, acc_w)[0] if a > 0)
    p90 = positive[int(0.9 * (len(positive) - 1))]
    m = max(1, min(0xFFFF, round(110 * (1 << s) / p90)))
    return write_conv_set(outdir, images, w, bias, m, s, acc_w)


def extreme_weights(rng):
    w = [127] * 9 + [-127] * 9                                    # filters 0, 1
    w += [127 if i % 2 == 0 else -127 for i in range(9)]           # filter 2
    w += [-127, 0, 127] * 3                                        # filter 3: vertical edge
    w += [-127] * 3 + [0] * 3 + [127] * 3                          # filter 4: horizontal edge
    w += [rng.choice((-127, 127)) for _ in range(9)]               # filter 5
    w += [rng.randint(-127, 127) for _ in range(9)]                # filter 6
    w += [0] * 4 + [127] + [0] * 4                                 # filter 7: centre only
    return w


def conv_extremes(outdir, acc_w, seed=7):
    """The overflow test: an all-255 image with +-127 weights, and biases that take
    filters 0 and 1 exactly to the acc_w-bit limits without crossing them."""
    rng = random.Random(seed)
    lo, hi = acc_range(acc_w)
    images = pattern_images()[:3] + [[rng.randrange(256) for _ in range(256)]]
    w = extreme_weights(rng)
    bias = [hi - MAX_SUM, lo + MAX_SUM, 0, 1000, -1000, 50000, -50000, 12345]
    s = 24
    m = round(127 * (1 << s) / MAX_SUM)
    info = write_conv_set(outdir, images, w, bias, m, s, acc_w)
    assert not any(info["ovf"])
    return info


def conv_ovf_flag(outdir, acc_w, seed=7):
    """One past the limit: filter 0's bias is 1 higher, so the all-255 image
    overflows and the RTL must raise ovf (the expected outputs wrap, as the RTL does)."""
    rng = random.Random(seed)
    lo, hi = acc_range(acc_w)
    w = extreme_weights(rng)
    bias = [hi - MAX_SUM + 1, lo + MAX_SUM, 0, 1000, -1000, 50000, -50000, 12345]
    s = 24
    m = round(127 * (1 << s) / MAX_SUM)
    info = write_conv_set(outdir, [[255] * 256], w, bias, m, s, acc_w)
    assert all(info["ovf"])
    return info


def requant_set(outdir, m, s, acc_w, n=10000, seed=11):
    """n accumulator values for one (M, S, acc_w): every boundary where the output
    steps, the accumulator limits, values spread over the range that reaches
    0..127, and values spread over the whole accumulator range."""
    rng = random.Random(seed * 65599 + m * 64 + s)
    lo, hi = acc_range(acc_w)
    r = (1 << (s - 1)) if s else 0
    edges = [0, 1, -1, 2, -2, hi, lo, hi - 1, lo + 1]
    for y in (1, 2, 64, 126, 127, 128):
        t = -((-((y << s) - r)) // m)       # smallest acc giving >= y
        edges += [t - 1, t, t + 1]
    near_lo = max(lo, -(1 << s) // m - 2)
    near_hi = min(hi, (128 << s) // m + 2)
    vals = [e for e in edges if lo <= e <= hi]
    while len(vals) < n:
        if len(vals) % 2:
            vals.append(rng.randint(near_lo, near_hi))
        else:
            vals.append(rng.randint(lo, hi))
    vals = vals[:n]
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    write_mem(outdir / "rq_acc.mem", vals, acc_w // 4)
    write_mem(outdir / "rq_q.mem", [requant(v, m, s) for v in vals], 2)
    write_params(outdir / "params.vh", m, s, acc_w)
    return {"vectors": n}


# (M, S) pairs for the requant_relu sweep at the default 24-bit accumulator:
# the smallest and largest M, shifts over the contract's whole range 0..47,
# and P2's pairs (34172, 25) and (43980, 25). Two more at 32 bits: p2-int-v1's
# pair, and (65535, 47), which needs every bit of the 48-bit rescale sum.
REQUANT_SWEEP = [(1, 0), (65535, 0), (3, 2), (1, 23), (2055, 20), (12345, 16),
                 (34172, 25), (43980, 25), (40000, 30), (65535, 31), (65535, 47)]
REQUANT_SWEEP_32 = [(34172, 25), (65535, 47)]

# conv_engine_tb sets: (folder, number of images, overflow expected)
CONV_SETS = [("conv_model", 20, False), ("conv_extremes", 4, False), ("conv_ovf_flag", 1, True),
             ("conv_extremes_acc32", 4, False), ("conv_ovf_flag_acc32", 1, True)]


def requant_names():
    return ([f"requant_M{m}_S{s}" for m, s in REQUANT_SWEEP]
            + [f"requant_M{m}_S{s}_acc32" for m, s in REQUANT_SWEEP_32])


def write_all(outdir):
    outdir = Path(outdir)
    sets = {
        "conv_model": conv_model(outdir / "conv_model"),
        "conv_extremes": conv_extremes(outdir / "conv_extremes", 24),
        "conv_ovf_flag": conv_ovf_flag(outdir / "conv_ovf_flag", 24),
        "conv_extremes_acc32": conv_extremes(outdir / "conv_extremes_acc32", 32),
        "conv_ovf_flag_acc32": conv_ovf_flag(outdir / "conv_ovf_flag_acc32", 32),
    }
    for m, s in REQUANT_SWEEP:
        sets[f"requant_M{m}_S{s}"] = requant_set(outdir / f"requant_M{m}_S{s}", m, s, 24)
    for m, s in REQUANT_SWEEP_32:
        sets[f"requant_M{m}_S{s}_acc32"] = requant_set(outdir / f"requant_M{m}_S{s}_acc32", m, s, 32)
    return sets


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    for name, info in write_all(sys.argv[1]).items():
        print(name, info)
