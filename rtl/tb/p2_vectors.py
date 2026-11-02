"""conv_engine_tb vectors from P2's model packages.

    python rtl/tb/p2_vectors.py OUTDIR [MODEL_DIR]     # model_set into OUTDIR

model_set() runs P2's integer golden model (reference_model/golden.py) with
the parameters of one package (default reference_model/models/p2-int-v1) on
20 pictures: P2's 16x16 example of each class, the five synthetic inputs of
P2's vector export, and seven random pictures. First it checks the package:
P2's checksums, and that the .mem files the RTL loads hold the same integers
as parameters.npz. Then it checks that P3's own reference (p3_vectors.py)
gives the same accumulators and activations as golden.py.

package_set() reads one of P2's full vector packages instead (the folder
quantize.py writes: contract.json, mem/, vectors/<name>/*.mem), for
run_p3_tests.py --vectors.

Needs NumPy and Pillow, like P2's reference_model/requirements.txt.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_MODEL = REPO / "reference_model" / "models" / "p2-int-v1"
ASSETS = REPO / "reference_model" / "docs" / "assets"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "reference_model"))
import p3_vectors as p3  # noqa: E402
import golden            # noqa: E402  P2's integer reference


def read_mem(path, bits, signed):
    """One hex word per line; signed words are two's complement."""
    words = [int(w, 16) for w in Path(path).read_text().split()]
    if signed:
        words = [w - (1 << bits) if w >> (bits - 1) else w for w in words]
    return words


def check_package(pkg):
    """P2's checksums, then the conv .mem files against parameters.npz."""
    sums = json.loads((pkg / "checksums.json").read_text())
    bad = [k for k, v in sums.items() if hashlib.sha256((pkg / k).read_bytes()).hexdigest() != v]
    if bad:
        raise ValueError(f"{pkg}: checksum mismatch in {', '.join(bad)}")
    contract = json.loads((pkg / "contract.json").read_text())
    w = read_mem(pkg / "mem" / "conv_weight.mem", 8, True)
    b = read_mem(pkg / "mem" / "conv_bias.mem", 32, True)
    with np.load(pkg / "parameters.npz", allow_pickle=False) as npz:
        if w != npz["conv_weight"].ravel().tolist() or b != npz["conv_bias"].tolist():
            raise ValueError(f"{pkg}: mem/ and parameters.npz hold different conv parameters")
    return contract, w, b


def class_examples(contract):
    """P2's 16x16 example picture of each class, in class-index order."""
    pictures = []
    for c in contract["classes"]:
        path = ASSETS / f"class_{c['gtsrb_id']:02d}_gray_16.png"
        with Image.open(path) as im:
            pix = np.asarray(im.convert("L"), dtype=np.uint8)
        if pix.shape != (16, 16):
            raise ValueError(f"{path} is {pix.shape}, not 16x16")
        pictures.append((f"class {c['index']} {c['name']}", pix))
    return pictures


def synthetic():
    """The five synthetic inputs of P2's vector export (quantize.py)."""
    impulse = np.zeros((16, 16), dtype=np.uint8)
    impulse[8, 8] = 255
    return [("zeros", np.zeros((16, 16), dtype=np.uint8)),
            ("maximum", np.full((16, 16), 255, dtype=np.uint8)),
            ("checkerboard", ((np.indices((16, 16)).sum(0) % 2) * 255).astype(np.uint8)),
            ("ramp", np.arange(256, dtype=np.uint8).reshape(16, 16)),
            ("impulse", impulse)]


def write_set(outdir, pkg, m, s, pixels, accs, acts):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    p3.write_mem(outdir / "pixels.mem", pixels, 2)
    for name in ("conv_weight.mem", "conv_bias.mem"):
        shutil.copy(pkg / "mem" / name, outdir / name)      # the exact files the RTL loads
    p3.write_mem(outdir / "conv_acc.mem", accs, 8)
    p3.write_mem(outdir / "conv_out.mem", acts, 2)
    p3.write_params(outdir / "params.vh", m, s)


def model_set(outdir, model=DEFAULT_MODEL, n_random=7, seed=2026):
    pkg = Path(model)
    contract, w, b = check_package(pkg)
    params, _ = golden.load_model(pkg)
    q = contract["requantization"]
    m, s = q["multiplier"], q["shift"]
    rng = np.random.default_rng(seed)
    pictures = class_examples(contract) + synthetic()
    pictures += [(f"random {i}", rng.integers(0, 256, (16, 16), dtype=np.uint8))
                 for i in range(n_random)]
    batch = np.stack([pix for _, pix in pictures])[:, None]        # N, C=1, H, W
    trace = golden.infer(batch, params, contract)
    accs = trace["conv_acc"].reshape(len(pictures), -1)
    acts = trace["activation"].reshape(len(pictures), -1)
    for (name, pix), acc_g, act_g in zip(pictures, accs, acts):
        acc_p, ovf = p3.conv_acc(pix.ravel().tolist(), w, b)
        if ovf or acc_p != acc_g.tolist() or [p3.requant(a, m, s) for a in acc_p] != act_g.tolist():
            raise AssertionError(f"p3_vectors.py and golden.py disagree on '{name}'")
    write_set(outdir, pkg, m, s, batch.ravel().tolist(), accs.ravel().tolist(), acts.ravel().tolist())
    pred = trace["prediction"].tolist()
    (Path(outdir) / "pictures.txt").write_text("".join(
        f"{i:2d}  {name:28s} golden class {p}\n" for i, ((name, _), p) in enumerate(zip(pictures, pred))))
    right = sum(pred[c["index"]] == c["index"] for c in contract["classes"])
    return {"version": contract["version"], "M": m, "S": s, "images": len(pictures),
            "examples_right": right, "examples": len(contract["classes"])}


def package_set(pkg, outdir):
    """Every vector of a full P2 vector package, in its manifest's order."""
    pkg = Path(pkg)
    contract, _, _ = check_package(pkg)
    q = contract["requantization"]
    names = [v["name"] for v in json.loads((pkg / "vectors" / "manifest.json").read_text())]
    pixels, accs, acts = [], [], []
    for name in names:
        vec = pkg / "vectors" / name
        pixels += read_mem(vec / "input.mem", 8, False)
        accs += read_mem(vec / "conv_acc.mem", 32, True)
        acts += read_mem(vec / "activation.mem", 8, False)
    n = len(names)
    if (len(pixels), len(accs), len(acts)) != (256 * n, p3.N_OUT * n, p3.N_OUT * n):
        raise ValueError(f"{pkg}: a vector has the wrong number of words")
    write_set(outdir, pkg, q["multiplier"], q["shift"], pixels, accs, acts)
    return {"version": contract["version"], "M": q["multiplier"], "S": q["shift"], "images": n}


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    print(model_set(sys.argv[1], *sys.argv[2:]))
