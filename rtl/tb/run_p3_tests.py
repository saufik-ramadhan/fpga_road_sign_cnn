"""Runs P3's testbenches and prints one PASS/FAIL line per test.

    python rtl/tb/run_p3_tests.py                  # Icarus Verilog
    python rtl/tb/run_p3_tests.py --sim xsim       # Vivado simulator
    python rtl/tb/run_p3_tests.py --vectors DIR    # conv_engine_tb on P2's golden dump

The default run generates P3's own vectors (p3_vectors.py) and runs
conv_engine_tb on three sets (a random model on 20 images, the 24-bit limits,
and an overflow that must be flagged) and requant_relu_tb over 8 (M, S) pairs.

--vectors DIR runs conv_engine_tb on a folder holding pixels.mem,
conv_weights.mem, conv_out.mem and params.vh; N_IMG is read from pixels.mem.

Vectors, logs and simulator files go to build/p3_sim/, which Git ignores.
For xsim, Vivado's bin folder is found on PATH, from XILINX_VIVADO, or from
--vivado-bin.
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


def count_words(mem):
    return sum(1 for ln in Path(mem).read_text().splitlines()
               if ln.strip() and not ln.strip().startswith(("//", "@")))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", choices=("iverilog", "xsim"), default="iverilog")
    ap.add_argument("--vivado-bin", help="Vivado bin folder, for --sim xsim")
    ap.add_argument("--vectors", help="folder with P2's dump: run conv_engine_tb on it only")
    ap.add_argument("--out", default=str(REPO / "build" / "p3_sim"), help="work folder")
    args = ap.parse_args()

    sim = (Icarus if args.sim == "iverilog" else Xsim)(args.vivado_bin)
    out = Path(args.out).resolve() / args.sim
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    tests = []      # (name, top, tb, folder, defines)
    if args.vectors:
        src = Path(args.vectors).resolve()
        work = out / "golden"
        work.mkdir()
        for name in ("pixels.mem", "conv_weights.mem", "conv_out.mem", "params.vh"):
            shutil.copy(src / name, work / name)
        n_img = count_words(work / "pixels.mem") // 256
        tests.append((f"conv_engine_tb on {src.name}", "conv_engine_tb", CONV_TB, work,
                      {"N_IMG": n_img}))
    else:
        print(f"Writing vectors to {out}")
        p3_vectors.write_all(out)
        tests += [
            ("conv_engine_tb conv_model", "conv_engine_tb", CONV_TB, out / "conv_model", {"N_IMG": 20}),
            ("conv_engine_tb conv_extremes", "conv_engine_tb", CONV_TB, out / "conv_extremes", {"N_IMG": 4}),
            ("conv_engine_tb conv_ovf_flag", "conv_engine_tb", CONV_TB, out / "conv_ovf_flag",
             {"N_IMG": 1, "EXPECT_OVF": None}),
        ]
        for m, s in p3_vectors.REQUANT_SWEEP:
            name = f"requant_M{m}_S{s}"
            tests.append((f"requant_relu_tb {name}", "requant_relu_tb", REQUANT_TB, out / name,
                          {"N_VEC": 10000}))

    failed = 0
    for name, top, tb, work, defines in tests:
        log = sim.run(top, tb, work, defines)
        (work / "sim.log").write_text(log)
        ok, detail = verdict(log)
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:34s} {detail}")
        if not ok:
            for ln in log.splitlines()[:25]:
                print("        " + ln)
    print(f"\n{len(tests) - failed} of {len(tests)} passed ({args.sim}); logs in {out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
