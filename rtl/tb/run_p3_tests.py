"""Runs P3's testbenches and prints one PASS/FAIL line per test.

    python rtl/tb/run_p3_tests.py                  # Icarus Verilog
    python rtl/tb/run_p3_tests.py --sim xsim       # Vivado simulator
    python rtl/tb/run_p3_tests.py --vectors DIR    # conv_engine_tb on a P2 vector package
    python rtl/tb/run_p3_tests.py --wave           # also save waveforms (.vcd) for GTKWave

The default run generates P3's own vectors (p3_vectors.py) and runs
conv_engine_tb on three sets (a random model on 20 images, the 32-bit
accumulator limits, and an overflow that must be flagged) and requant_relu_tb
over 10 (M, S) pairs. It also runs conv_engine_tb on P2's model
(p2_vectors.py): the package given by --model, by default
reference_model/models/p2-int-v1, on 20 pictures checked against P2's
golden.py. With the default package the engine gets no parameters, so that
test also checks that its defaults are P2's model.

--vectors DIR runs conv_engine_tb on every vector of one of P2's full vector
packages: the folder P2's quantize.py writes, with contract.json, mem/ and
vectors/.

Vectors, logs and simulator files go to build/p3_sim/, which Git ignores.
For xsim, Vivado's bin folder is found on PATH, from XILINX_VIVADO, or from
--vivado-bin. The P2 tests need NumPy and Pillow.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import p3_vectors  # noqa: E402

RTL_FILES = [REPO / "rtl" / n for n in
             ("conv_wrom.v", "requant_relu.v", "conv_engine.v", "fmap_ram.v")]
CONV_TB = HERE / "conv_engine_tb.v"
REQUANT_TB = HERE / "requant_relu_tb.v"
DEFAULT_MODEL = REPO / "reference_model" / "models" / "p2-int-v1"


def sh(cmd, cwd):
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def rel(path, start):
    """Relative path with forward slashes (no spaces from the user's home folder)."""
    try:
        return Path(os.path.relpath(path, start)).as_posix()
    except ValueError:          # another drive
        return Path(path).as_posix()


class Icarus:
    def __init__(self, _):
        self.iverilog = shutil.which("iverilog")
        self.vvp = shutil.which("vvp")
        if not (self.iverilog and self.vvp):
            sys.exit("iverilog and vvp are not on PATH")

    def run(self, top, tb, workdir, defines):
        out = workdir / f"{top}.vvp"
        cmd = [self.iverilog, "-g2005", "-Wall", "-I", workdir, "-s", top, "-o", out]
        cmd += [f"-D{k}" if v is None else f"-D{k}={v}" for k, v in defines.items()]
        cmd += RTL_FILES + [tb]
        code, log = sh(cmd, workdir)
        if code:
            return log
        return log + sh([self.vvp, "-n", out], workdir)[1]


class Xsim:
    def __init__(self, vivado_bin):
        bins = [Path(vivado_bin)] if vivado_bin else []
        if os.environ.get("XILINX_VIVADO"):
            bins.append(Path(os.environ["XILINX_VIVADO"]) / "bin")
        found = shutil.which("xvlog")
        if found:
            bins.append(Path(found).parent)
        for b in bins:
            if (b / "xvlog.bat").exists() or (b / "xvlog").exists():
                ext = ".bat" if os.name == "nt" else ""
                self.xvlog, self.xelab, self.xsim = (b / f"{t}{ext}" for t in ("xvlog", "xelab", "xsim"))
                return
        sys.exit("Vivado simulator not found: use --vivado-bin, PATH or XILINX_VIVADO")

    def run(self, top, tb, workdir, defines):
        # Options go through a file: Windows batch files split "-d N_IMG=20" at the "="
        opts = ["-i ."]
        opts += [f"-d {k}" if v is None else f"-d {k}={v}" for k, v in defines.items()]
        opts += [rel(f, workdir) for f in RTL_FILES + [tb]]
        (workdir / "xvlog.f").write_text("\n".join(opts) + "\n")
        log = ""
        for step in ([self.xvlog, "-f", "xvlog.f"],
                     [self.xelab, "-debug", "off", "-s", f"{top}_snap", top],
                     [self.xsim, f"{top}_snap", "-R"]):
            code, out = sh(step, workdir)
            log += out
            if code:
                break
        return log


def verdict(log):
    lines = log.splitlines()
    result = [ln for ln in lines if ln.startswith(("PASS", "FAIL"))]
    if len(result) == 1 and result[0].startswith("PASS") and "FAIL" not in log:
        return True, result[0]
    detail = result[0] if result else "no PASS line (compile error or crash, see the log)"
    return False, detail


def p2_model_test(out, model):
    """conv_engine_tb on a P2 model package: (a line to print, the test or None)."""
    if not model.exists():
        return f"skip  P2 model: no package at {model}", None
    try:
        import p2_vectors
    except ImportError as e:
        return f"skip  P2 model: {e} (needs NumPy, Pillow and reference_model/golden.py)", None
    try:
        info = p2_vectors.model_set(out / "p2_model", model)
    except (ValueError, AssertionError, OSError, OverflowError, KeyError) as e:
        return f"FAIL  P2 model: {e}", None
    defines = {"N_IMG": info["images"]}
    name = f"conv_engine_tb {info['version']}"
    if model == DEFAULT_MODEL.resolve():
        defines["P2_DEFAULTS"] = None           # the DUT gets no parameters
        name += " defaults"
    line = (f"P2 model {info['version']}: checksums OK, M={info['M']}, S={info['S']}; "
            f"p3_vectors.py and golden.py agree on all {info['images']} pictures; golden.py "
            f"classifies {info['examples_right']} of the {info['examples']} class examples correctly")
    return line, (name, "conv_engine_tb", CONV_TB, out / "p2_model", defines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", choices=("iverilog", "xsim"), default="iverilog")
    ap.add_argument("--vivado-bin", help="Vivado bin folder, for --sim xsim")
    ap.add_argument("--model", default=str(DEFAULT_MODEL), help="P2 model package for the P2 test")
    ap.add_argument("--vectors", help="P2 vector package: run conv_engine_tb on it only")
    ap.add_argument("--out", default=str(REPO / "build" / "p3_sim"), help="work folder")
    ap.add_argument("--wave", action="store_true", help="also save a waveform (.vcd) for each test")
    args = ap.parse_args()

    sim = (Icarus if args.sim == "iverilog" else Xsim)(args.vivado_bin)
    out = Path(args.out).resolve() / args.sim
    if out.exists():
        try:
            shutil.rmtree(out)
        except PermissionError as e:
            sys.exit(f"Cannot clear {e.filename}: it is in use. Close GTKWave, editors or terminals "
                     "using that folder, then run again.")
    out.mkdir(parents=True)

    tests = []      # (name, top, tb, folder, defines)
    prep_failed = 0
    if args.vectors:
        import p2_vectors
        work = out / "golden"
        info = p2_vectors.package_set(args.vectors, work)
        print(f"P2 package {info['version']}: checksums OK, M={info['M']}, S={info['S']}, "
              f"{info['images']} vectors")
        tests.append((f"conv_engine_tb on {Path(args.vectors).name}", "conv_engine_tb", CONV_TB, work,
                      {"N_IMG": info["images"]}))
    else:
        print(f"Writing vectors to {out}")
        p3_vectors.write_all(out)
        tests += [
            ("conv_engine_tb conv_model", "conv_engine_tb", CONV_TB, out / "conv_model", {"N_IMG": 20}),
            ("conv_engine_tb conv_extremes", "conv_engine_tb", CONV_TB, out / "conv_extremes", {"N_IMG": 4}),
            ("conv_engine_tb conv_ovf_flag", "conv_engine_tb", CONV_TB, out / "conv_ovf_flag",
             {"N_IMG": 1, "EXPECT_OVF": None}),
        ]
        line, test = p2_model_test(out, Path(args.model).resolve())
        print(line)
        if test:
            tests.append(test)
        else:
            prep_failed += line.startswith("FAIL")
        for m, s in p3_vectors.REQUANT_SWEEP:
            name = f"requant_M{m}_S{s}"
            tests.append((f"requant_relu_tb {name}", "requant_relu_tb", REQUANT_TB, out / name,
                          {"N_VEC": 10000}))

    if args.wave:
        for test in tests:
            test[4]["DUMP"] = None

    failed = prep_failed
    for name, top, tb, work, defines in tests:
        log = sim.run(top, tb, work, defines)
        (work / "sim.log").write_text(log)
        ok, detail = verdict(log)
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:34s} {detail}")
        if not ok:
            for ln in log.splitlines()[:25]:
                print("        " + ln)
    n = len(tests) + prep_failed
    print(f"\n{n - failed} of {n} passed ({args.sim}); logs in {out}")
    if args.wave:
        vcds = [work / f"{top}.vcd" for _, top, _, work, _ in tests if (work / f"{top}.vcd").exists()]
        print(f"{len(vcds)} waveforms saved next to the logs. To open the first one:")
        print(f"  gtkwave {vcds[0]} {HERE / (vcds[0].stem + '.gtkw')}" if vcds else "  (none found)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
