"""Test vectors for P3's testbenches: conv_engine_tb and requant_relu_tb.

Holds an integer reference of the convolution layer, written straight from
the plan's number formats, so the RTL can be tested before P2's golden model
exists. When golden.py lands, the two must agree on the same images.

    python rtl/tb/p3_vectors.py OUTDIR     # writes every vector set into OUTDIR
"""
import random
import sys
from pathlib import Path

IMG = 16                    # input is IMG x IMG, unsigned 8-bit
K = 3                       # kernel size
N_F = 8                     # filters
OUT = IMG - K + 1           # 14
N_OUT = N_F * OUT * OUT     # 1,568
ACC_MIN, ACC_MAX = -(1 << 23), (1 << 23) - 1

# Biases that bring an all-255 image under all +127 (or all -127) weights
# exactly to the edge of the 24-bit accumulator: 9 * 255 * 127 = 291,465.
BIAS_EDGE_POS = ACC_MAX - 9 * 255 * 127     # 8,097,142
BIAS_EDGE_NEG = ACC_MIN + 9 * 255 * 127     # -8,097,143


def requant(acc, m, s):
    """(acc * M + 2^(S-1)) >> S, clamped to 0..127. Python's >> is a floor shift."""
    return min(max((acc * m + (1 << (s - 1))) >> s, 0), 127)


def wrap24(x):
    return ((x - ACC_MIN) & 0xFFFFFF) + ACC_MIN


def conv_acc(pix, w, bias):
    """Accumulator of every output in fmap_ram order, plus an overflow flag.

    Adds the bias and then the 9 products in the RTL's order, and wraps at 24
    bits as the RTL does, so even overflowing cases match bit for bit."""
    accs = [0] * N_OUT
    ovf = False
    for f in range(N_F):
        for r in range(OUT):
            for c in range(OUT):
                acc = bias[f]
                for kr in range(K):
                    for kc in range(K):
                        acc += pix[(r + kr) * IMG + c + kc] * w[f * 9 + kr * 3 + kc]
                        if not ACC_MIN <= acc <= ACC_MAX:
                            ovf = True
                            acc = wrap24(acc)
                accs[f * OUT * OUT + r * OUT + c] = acc
    return accs, ovf


def conv_layer(pix, w, bias, m, s):
    """Activations in fmap_ram order (filter*196 + row*14 + col), and the overflow flag."""
    accs, ovf = conv_acc(pix, w, bias)
    return [requant(a, m, s) for a in accs], ovf


# ---- file writers -----------------------------------------------------------

def write_mem(path, values, digits):
    mask = (1 << (4 * digits)) - 1
    Path(path).write_text("".join(f"{v & mask:0{digits}x}\n" for v in values))


def write_params(path, m, s, bias):
    assert 1 <= m <= 0xFFFF and 1 <= s <= 40
    assert len(bias) == N_F and all(ACC_MIN <= b <= ACC_MAX for b in bias)
    lits = ", ".join(f"24'h{b & 0xFFFFFF:06x}" for b in reversed(bias))
    Path(path).write_text(
        "// params.vh for a P3 test set: rescale constants and conv biases only\n"
        f"localparam [15:0]     CONV_M    = 16'd{m};\n"
        f"localparam integer    CONV_S    = {s};\n"
        f"localparam [8*24-1:0] CONV_BIAS = {{{lits}}};  // filter 7 first, filter 0 last\n")


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


def write_conv_set(outdir, images, w, bias, m, s):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    acts, flags = [], []
    for pix in images:
        a, ovf = conv_layer(pix, w, bias, m, s)
        acts += a
        flags.append(ovf)
    write_mem(outdir / "pixels.mem", [p for img in images for p in img], 2)
    write_mem(outdir / "conv_weights.mem", w, 2)
    write_mem(outdir / "conv_out.mem", acts, 2)
    write_params(outdir / "params.vh", m, s, bias)
    zeros = sum(a == 0 for a in acts) / len(acts)
    tops = sum(a == 127 for a in acts) / len(acts)
    return {"images": len(images), "ovf": flags, "zeros": zeros, "clamped127": tops}


def conv_model(outdir, n=20, seed=2026):
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
    positive = sorted(a for pix in images for a in conv_acc(pix, w, bias)[0] if a > 0)
    p90 = positive[int(0.9 * (len(positive) - 1))]
    m = max(1, min(0xFFFF, round(110 * (1 << s) / p90)))
    return write_conv_set(outdir, images, w, bias, m, s)


def extreme_weights(rng):
    w = [127] * 9 + [-127] * 9                                    # filters 0, 1
    w += [127 if i % 2 == 0 else -127 for i in range(9)]           # filter 2
    w += [-127, 0, 127] * 3                                        # filter 3: vertical edge
    w += [-127] * 3 + [0] * 3 + [127] * 3                          # filter 4: horizontal edge
    w += [rng.choice((-127, 127)) for _ in range(9)]               # filter 5
    w += [rng.randint(-127, 127) for _ in range(9)]                # filter 6
    w += [0] * 4 + [127] + [0] * 4                                 # filter 7: centre only
    return w


def conv_extremes(outdir, seed=7):
    """The overflow test: an all-255 image with +-127 weights, and biases that take
    filters 0 and 1 exactly to the 24-bit limits without crossing them."""
    rng = random.Random(seed)
    images = pattern_images()[:3] + [[rng.randrange(256) for _ in range(256)]]
    w = extreme_weights(rng)
    bias = [BIAS_EDGE_POS, BIAS_EDGE_NEG, 0, 1000, -1000, 50000, -50000, 12345]
    s = 24
    m = round(127 * (1 << s) / (9 * 255 * 127))
    info = write_conv_set(outdir, images, w, bias, m, s)
    assert not any(info["ovf"])
    return info


def conv_ovf_flag(outdir, seed=7):
    """One past the limit: filter 0's bias is 1 higher, so the all-255 image
    overflows and the RTL must raise ovf (the expected outputs wrap, as the RTL does)."""
    rng = random.Random(seed)
    w = extreme_weights(rng)
    bias = [BIAS_EDGE_POS + 1, BIAS_EDGE_NEG, 0, 1000, -1000, 50000, -50000, 12345]
    s = 24
    m = round(127 * (1 << s) / (9 * 255 * 127))
    info = write_conv_set(outdir, [[255] * 256], w, bias, m, s)
    assert all(info["ovf"])
    return info


def requant_set(outdir, m, s, n=10000, seed=11):
    """n accumulator values for one (M, S): every boundary where the output steps,
    the 24-bit limits, values spread over the range that reaches 0..127, and
    values spread over the whole 24-bit range."""
    rng = random.Random(seed * 65599 + m * 64 + s)
    edges = [0, 1, -1, 2, -2, ACC_MAX, ACC_MIN, ACC_MAX - 1, ACC_MIN + 1]
    for y in (1, 2, 64, 126, 127, 128):
        t = -((-((y << s) - (1 << (s - 1)))) // m)      # smallest acc giving >= y
        edges += [t - 1, t, t + 1]
    lo = max(ACC_MIN, -(1 << s) // m - 2)
    hi = min(ACC_MAX, (128 << s) // m + 2)
    vals = [e for e in edges if ACC_MIN <= e <= ACC_MAX]
    while len(vals) < n:
        if len(vals) % 2:
            vals.append(rng.randint(lo, hi))
        else:
            vals.append(rng.randint(ACC_MIN, ACC_MAX))
    vals = vals[:n]
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    write_mem(outdir / "rq_acc.mem", vals, 6)
    write_mem(outdir / "rq_q.mem", [requant(v, m, s) for v in vals], 2)
    write_params(outdir / "params.vh", m, s, [0] * N_F)
    return {"vectors": n}


# (M, S) pairs for the requant_relu sweep: the smallest and largest M, shifts
# from 1 to 31, and the kind of values a trained model gives (S near 20).
REQUANT_SWEEP = [(1, 1), (3, 2), (1, 23), (2055, 20), (12345, 16),
                 (40000, 30), (65535, 24), (65535, 31)]


def write_all(outdir):
    outdir = Path(outdir)
    sets = {
        "conv_model": conv_model(outdir / "conv_model"),
        "conv_extremes": conv_extremes(outdir / "conv_extremes"),
        "conv_ovf_flag": conv_ovf_flag(outdir / "conv_ovf_flag"),
    }
    for m, s in REQUANT_SWEEP:
        sets[f"requant_M{m}_S{s}"] = requant_set(outdir / f"requant_M{m}_S{s}", m, s)
    return sets


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    for name, info in write_all(sys.argv[1]).items():
        print(name, info)
