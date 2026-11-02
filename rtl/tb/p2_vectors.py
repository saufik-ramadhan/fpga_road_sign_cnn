"""conv_engine_tb vectors from P2's model packages.

    python rtl/tb/p2_vectors.py OUTDIR [PACKAGE_DIR]

Every package (reference_model/models/<version>/) is checked first: P2's
checksums, and that the conv .mem files hold the same integers as
parameters.npz. Word widths come from the files: biases and accumulators are
24-bit (6 hex digits) in p2-doc-int-v2 and 32-bit (8 digits) in p2-int-v1,
matching each contract's accumulator type.

package_set() uses a package's own golden vectors (vectors/<name>/input.mem,
conv_acc.mem and activation.mem, in the manifest's order), as p2-doc-int-v2
ships them. model_set() is for a package without vectors, such as p2-int-v1:
it runs the package's P2 golden model on 20 pictures (P2's 16x16 example of
each class, the five synthetic inputs of P2's vector export and seven random
pictures). Either way, P3's own reference (p3_vectors.py) must give the same
accumulators and activations.

Needs NumPy and Pillow, like P2's reference_model/requirements.txt.
"""
import hashlib
import importlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MODELS = REPO / "reference_model" / "models"
DEFAULT_MODEL = MODELS / "p2-doc-int-v2"
ASSETS = REPO / "reference_model" / "docs" / "assets"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "reference_model"))
import p3_vectors as p3  # noqa: E402


def read_mem(path, signed):
    """One hex word per line, all of one width; returns the values and that width in bits."""
    text = Path(path).read_text().split()
    bits = 4 * len(text[0])
    words = [int(w, 16) for w in text]
    if signed:
        words = [w - (1 << bits) if w >> (bits - 1) else w for w in words]
    return words, bits


def acc_width(contract):
    """The contract's accumulator type, int24 or int32, as a number of bits."""
    return int(contract["accumulator"]["dtype"].removeprefix("int"))


def golden_for(contract):
    """P2's golden model for a contract: document_v2/golden.py checks int24, golden.py int32."""
    return importlib.import_module("document_v2.golden" if acc_width(contract) == 24 else "golden")


def check_package(pkg):
    """P2's checksums, then the conv .mem files against parameters.npz."""
    sums = json.loads((pkg / "checksums.json").read_text())
    bad = [k for k, v in sums.items() if hashlib.sha256((pkg / k).read_bytes()).hexdigest() != v]
    if bad:
        raise ValueError(f"{pkg.name}: checksum mismatch in {', '.join(bad[:3])}")
    contract = json.loads((pkg / "contract.json").read_text())
    acc_w = acc_width(contract)
    w, _ = read_mem(pkg / "mem" / "conv_weight.mem", True)
    b, b_bits = read_mem(pkg / "mem" / "conv_bias.mem", True)
    if b_bits != acc_w:
        raise ValueError(f"{pkg.name}: conv_bias.mem has {b_bits}-bit words, the contract says int{acc_w}")
    with np.load(pkg / "parameters.npz", allow_pickle=False) as npz:
        if w != npz["conv_weight"].ravel().tolist() or b != npz["conv_bias"].ravel().tolist():
            raise ValueError(f"{pkg.name}: mem/ and parameters.npz hold different conv parameters")
    q = contract["requantization"]
    return contract, w, b, q["multiplier"], q["shift"], acc_w


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


def check_p3(name, pix, acc, act, w, b, m, s, acc_w):
    """P3's own reference must give the same accumulators and activations."""
    acc_p, ovf = p3.conv_acc(pix, w, b, acc_w)
    if ovf or acc_p != acc or [p3.requant(a, m, s) for a in acc_p] != act:
        raise AssertionError(f"p3_vectors.py disagrees with P2 on '{name}'")


def write_set(outdir, pkg, m, s, acc_w, pixels, accs, acts, lines):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    p3.write_mem(outdir / "pixels.mem", pixels, 2)
    for name in ("conv_weight.mem", "conv_bias.mem"):
        shutil.copy(pkg / "mem" / name, outdir / name)      # the exact files the RTL loads
    p3.write_mem(outdir / "conv_acc.mem", accs, 8)
    p3.write_mem(outdir / "conv_out.mem", acts, 2)
    p3.write_params(outdir / "params.vh", m, s, acc_w)
    (outdir / "pictures.txt").write_text("".join(f"{i:2d}  {ln}\n" for i, ln in enumerate(lines)))


def package_set(pkg, outdir):
    """Every golden vector of a P2 package, in its manifest's order."""
    pkg = Path(pkg)
    contract, w, b, m, s, acc_w = check_package(pkg)
    manifest = json.loads((pkg / "vectors" / "manifest.json").read_text())
    pixels, accs, acts, lines = [], [], [], []
    for v in manifest:
        vec = pkg / "vectors" / v["name"]
        pix, _ = read_mem(vec / "input.mem", False)
        acc, a_bits = read_mem(vec / "conv_acc.mem", True)
        act, _ = read_mem(vec / "activation.mem", False)
        if a_bits != acc_w or (len(pix), len(acc), len(act)) != (256, p3.N_OUT, p3.N_OUT):
            raise ValueError(f"{pkg.name}: vector {v['name']} has the wrong word width or count")
        check_p3(v["name"], pix, acc, act, w, b, m, s, acc_w)
        pixels += pix
        accs += acc
        acts += act
        label = f"label {v['label']}" if "label" in v else "no label"
        lines.append(f"{v['name']:14s} {label:9s} golden class {v['integer_prediction']}  {v['source']}")
    write_set(outdir, pkg, m, s, acc_w, pixels, accs, acts, lines)
    real = [v for v in manifest if "label" in v]
    right = sum(v["integer_prediction"] == v["label"] for v in real)
    return {"images": len(manifest), "summary":
            f"P2 {contract['version']}: checksums OK, M={m}, S={s}, int{acc_w}; P3's reference agrees with "
            f"all {len(manifest)} of P2's golden vectors; P2's model gets {right} of the {len(real)} real ones right"}


def model_set(pkg, outdir, n_random=7, seed=2026):
    """The package's P2 golden model on 20 pictures, for a package without vectors."""
    pkg = Path(pkg)
    contract, w, b, m, s, acc_w = check_package(pkg)
    golden = golden_for(contract)
    params, _ = golden.load_model(pkg)
    rng = np.random.default_rng(seed)
    pictures = class_examples(contract) + synthetic()
    pictures += [(f"random {i}", rng.integers(0, 256, (16, 16), dtype=np.uint8))
                 for i in range(n_random)]
    batch = np.stack([pix for _, pix in pictures])[:, None]        # N, C=1, H, W
    trace = golden.infer(batch, params, contract)
    accs = trace["conv_acc"].reshape(len(pictures), -1).tolist()
    acts = trace["activation"].reshape(len(pictures), -1).tolist()
    for (name, pix), acc, act in zip(pictures, accs, acts):
        check_p3(name, pix.ravel().tolist(), acc, act, w, b, m, s, acc_w)
    pred = trace["prediction"].tolist()
    lines = [f"{name:22s} golden class {p}" for (name, _), p in zip(pictures, pred)]
    write_set(outdir, pkg, m, s, acc_w, batch.ravel().tolist(), sum(accs, []), sum(acts, []), lines)
    right = sum(pred[c["index"]] == c["index"] for c in contract["classes"])
    return {"images": len(pictures), "summary":
            f"P2 {contract['version']}: checksums OK, M={m}, S={s}, int{acc_w}; P3's reference and "
            f"{golden.__name__.replace('.', '/')}.py agree on all {len(pictures)} pictures; it gets {right} of the "
            f"{len(contract['classes'])} class examples right"}


def any_set(pkg, outdir):
    """package_set when the package has golden vectors, model_set when it has none."""
    has_vectors = (Path(pkg) / "vectors" / "manifest.json").exists()
    return (package_set if has_vectors else model_set)(pkg, outdir)


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    print(any_set(sys.argv[2] if len(sys.argv) == 3 else DEFAULT_MODEL, sys.argv[1])["summary"])
