"""Runs P3's testbenches and prints one PASS/FAIL line per test.

    python tests/rtl/p3/run_p3_tests.py                  # Icarus Verilog
    python tests/rtl/p3/run_p3_tests.py --sim xsim       # Vivado simulator
    python tests/rtl/p3/run_p3_tests.py --vectors DIR    # conv_engine_tb on one P2 package folder
    python tests/rtl/p3/run_p3_tests.py --wave           # also save waveforms (.vcd) for GTKWave

The default run generates P3's own vectors (p3_vectors.py): conv_engine_tb on
a random model (20 images), on the accumulator limits and on an overflow that
must be flagged, at 24 and 32 bits, and requant_relu_tb over 13 (M, S,
width) cases. It also runs conv_engine_tb on every P2 package in
reference_model/models (p2_vectors.py): on the package's own golden vectors
when it has them, otherwise on 20 pictures checked against P2's golden model.
The current package, p2-doc-int-v2, is compiled with no engine parameters, so
that test also checks that the engine's defaults are its model.

--vectors DIR runs conv_engine_tb on one package folder outside the repository,
such as a new export from P2's quantize.py.

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
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
import p3_vectors  # noqa: E402

RTL_FILES = [REPO / "rtl" / n for n in
             ("conv_wrom.v", "requant_relu.v", "conv_engine.v", "fmap_ram.v")]
CONV_TB = HERE / "conv_engine_tb.v"
REQUANT_TB = HERE / "requant_relu_tb.v"
MODELS = REPO / "reference_model" / "models"
DEFAULT_MODEL = MODELS / "p2-doc-int-v2"     # conv_engine's parameter defaults


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


def p2_tests(out, packages):
    """conv_engine_tb on each P2 package: (lines to print, tests, packages that failed to load)."""
    if not packages:
        return ["FAIL  P2 models: no model packages selected"], [], 1
    try:
        import p2_vectors
    except ImportError as e:
        return [f"FAIL  P2 models: {e} (needs NumPy, Pillow and P2's reference_model/)"], [], len(packages)
    lines, tests, failed = [], [], 0
    for pkg in packages:
        work = out / pkg.name
        try:
            info = p2_vectors.any_set(pkg, work)
            if info["images"] < 1:
                raise ValueError("package contains no input images")
        except (ValueError, AssertionError, OSError, OverflowError, KeyError) as e:
            lines.append(f"FAIL  P2 model {pkg.name}: {e}")
            failed += 1
            continue
        lines.append(info["summary"])
        defines = {"N_IMG": info["images"]}
        name = f"conv_engine_tb {pkg.name}"
        if pkg.resolve() == DEFAULT_MODEL.resolve():
            defines["P2_DEFAULTS"] = None       # the DUT gets no parameters
            name += " defaults"
        tests.append((name, "conv_engine_tb", CONV_TB, work, defines))
    return lines, tests, failed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", choices=("iverilog", "xsim"), default="iverilog")
    ap.add_argument("--vivado-bin", help="Vivado bin folder, for --sim xsim")
    ap.add_argument("--vectors", help="one P2 package folder: run conv_engine_tb on it only")
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
    if args.vectors:
        lines, tests, prep_failed = p2_tests(out, [Path(args.vectors).resolve()])
    else:
        print(f"Writing vectors to {out}")
        p3_vectors.write_all(out)
        for name, n_img, ovf in p3_vectors.CONV_SETS:
            defines = {"N_IMG": n_img, **({"EXPECT_OVF": None} if ovf else {})}
            tests.append((f"conv_engine_tb {name}", "conv_engine_tb", CONV_TB, out / name, defines))
        packages = sorted(d for d in MODELS.glob("*") if (d / "contract.json").exists())
        lines, p2, prep_failed = p2_tests(out, packages)
        tests += p2
        for name in p3_vectors.requant_names():
            tests.append((f"requant_relu_tb {name}", "requant_relu_tb", REQUANT_TB, out / name,
                          {"N_VEC": 10000}))
    for line in lines:
        print(line)

    if not tests and not prep_failed:
        sys.exit("FAIL no tests selected; verification did not run")

    if args.wave:
        for test in tests:
            test[4]["DUMP"] = None

    failed = prep_failed
    for name, top, tb, work, defines in tests:
        log = sim.run(top, tb, work, defines)
        (work / "sim.log").write_text(log)
        ok, detail = verdict(log)
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:40s} {detail}")
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
