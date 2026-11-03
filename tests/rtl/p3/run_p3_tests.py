"""Runs P3's testbenches and prints one PASS/FAIL line per test.

    python tests/rtl/p3/run_p3_tests.py                  # Icarus Verilog
    python tests/rtl/p3/run_p3_tests.py --sim xsim       # Vivado simulator
    python tests/rtl/p3/run_p3_tests.py --vectors DIR    # core/wrapper tests on one P2 package folder
    python tests/rtl/p3/run_p3_tests.py --wave           # also save waveforms (.vcd) for GTKWave
    python tests/rtl/p3/run_p3_tests.py --mac 1          # only the default engine (N_MAC = 1)

The default run generates P3's own vectors (p3_vectors.py): conv_engine_tb on
a random model (20 images), on the accumulator limits, on an overflow that
must be flagged and on overflows that a later product cancels, at 24 and 32
bits, and requant_relu_tb over 13 (M, S, width) cases. It also runs
conv_engine_tb on every P2 package in reference_model/models (p2_vectors.py):
on the package's own golden vectors when it has them, otherwise on 20
pictures checked against P2's golden model.
The current package, p2-doc-int-v2, is compiled with no engine parameters, so
that test also checks that the engine's defaults are its model. Every P2 package
also runs through feature_extraction_tb; packages with a stored bank additionally
run subsystems_tb to check the P5 image-read interface feeding P3.

--vectors DIR runs the core/wrapper tests on one package folder outside the repository,
such as a new export from P2's quantize.py.

conv_engine_tb and feature_extraction_tb run once for each engine version in
--mac (default 1, 3 and 9 multipliers). N_MAC = 1 runs as it always has, with
no N_MAC define (the engine's default); the others run in a mac<N> subfolder
with a copy of the vectors, so each version keeps its own logs.

Vectors, logs and simulator files go to build/p3_sim/, which Git ignores.
For xsim, Vivado's bin folder is found on PATH, from XILINX_VIVADO, or from
--vivado-bin. The P2 tests need NumPy and Pillow.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
import p3_vectors  # noqa: E402

RTL_FILES = [REPO / line.strip() for line in (REPO / "rtl" / "files.f").read_text().splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
CONV_TB = HERE / "conv_engine_tb.v"
REQUANT_TB = HERE / "requant_relu_tb.v"
FEATURE_TB = HERE / "feature_extraction_tb.v"
INTEGRATION_TB = HERE.parent / "integration" / "subsystems_tb.v"
MODELS = REPO / "reference_model" / "models"
DEFAULT_MODEL = MODELS / "p2-doc-int-v2"     # conv_engine's parameter defaults
MACS = (1, 3, 9)                            # conv_engine versions, N_MAC; 1 is the default
MAC_TOPS = ("conv_engine_tb", "feature_extraction_tb")    # the testbenches that depend on N_MAC


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


def prepare_stored_vectors(pkg, work):
    """Pair P5's published stored bank with the matching P2 activation vectors."""
    if not (pkg / "stored_manifest.json").exists():
        return False
    stored = json.loads((pkg / "stored_manifest.json").read_text())
    vectors = json.loads((pkg / "vectors" / "manifest.json").read_text())
    if len(stored) != 16 or [v["index"] for v in stored] != list(range(16)):
        raise ValueError("stored bank must have 16 ordered images")
    by_source = {v["source"]: v["name"] for v in vectors if "label" in v}
    outputs = [(pkg / "vectors" / by_source[v["source"]] / "activation.mem").read_text()
               for v in stored]
    shutil.copyfile(pkg / "signs.mem", work / "signs.mem")
    (work / "stored_conv_out.mem").write_text("".join(outputs))
    return True


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
            stored_ready = prepare_stored_vectors(pkg, work)
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
        tests.append((f"feature_extraction_tb {pkg.name}", "feature_extraction_tb",
                      FEATURE_TB, work, defines.copy()))
        if stored_ready:
            tests.append((f"subsystems_tb {pkg.name}", "subsystems_tb",
                          INTEGRATION_TB, work, {}))
    return lines, tests, failed


def with_mac_variants(tests, macs):
    """The tests for the engine versions in macs, each N_MAC-dependent test
    followed by its variants: N_MAC = 1 as given, the others with an N_MAC
    define, in a mac<N> subfolder of the test's folder."""
    result = []
    for name, top, tb, work, defines in tests:
        if top not in MAC_TOPS:
            result.append((name, top, tb, work, defines))
            continue
        for n in macs:
            if n == 1:
                result.append((name, top, tb, work, defines))
            else:
                result.append((f"{name} mac{n}", top, tb, work / f"mac{n}", {**defines, "N_MAC": n}))
    return result


def copy_vectors(tests):
    """Give each mac<N> folder a copy of the vectors in the folder above it."""
    for _, _, _, work, defines in tests:
        if "N_MAC" in defines and not work.exists():
            work.mkdir()
            for f in work.parent.iterdir():
                if f.is_file():
                    shutil.copy(f, work / f.name)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", choices=("iverilog", "xsim"), default="iverilog")
    ap.add_argument("--vivado-bin", help="Vivado bin folder, for --sim xsim")
    ap.add_argument("--vectors", help="one P2 package folder: run its core/wrapper/integration tests")
    ap.add_argument("--out", default=str(REPO / "build" / "p3_sim"), help="work folder")
    ap.add_argument("--wave", action="store_true", help="also save a waveform (.vcd) for each test")
    ap.add_argument("--mac", type=int, nargs="+", choices=MACS, default=list(MACS),
                    help="conv_engine versions to test, by number of multipliers (default: 1 3 9)")
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
        for name, n_img in p3_vectors.CONV_SETS:
            tests.append((f"conv_engine_tb {name}", "conv_engine_tb", CONV_TB, out / name, {"N_IMG": n_img}))
        packages = sorted(d for d in MODELS.glob("*") if (d / "contract.json").exists())
        lines, p2, prep_failed = p2_tests(out, packages)
        tests += p2
        for name in p3_vectors.requant_names():
            tests.append((f"requant_relu_tb {name}", "requant_relu_tb", REQUANT_TB, out / name,
                          {"N_VEC": 10000}))
    for line in lines:
        print(line)

    tests = with_mac_variants(tests, args.mac)
    if not tests and not prep_failed:
        sys.exit("FAIL no tests selected; verification did not run")
    copy_vectors(tests)

    if args.wave:
        for test in tests:
            test[4]["DUMP"] = None

    failed = prep_failed
    for name, top, tb, work, defines in tests:
        log = sim.run(top, tb, work, defines)
        (work / f"{top}.log").write_text(log)
        ok, detail = verdict(log)
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:45s} {detail}")
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
