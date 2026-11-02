"""Run P5 UART and communication regressions with Icarus (no board needed).

    python tests/rtl/p5/run_p5_tests.py

Runs fast and nominal 115200-baud configurations. Logs and generated
simulator files are kept in the ignored build/p5_sim directory.
"""
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "build" / "p5_sim"
# Nominal-baud simulation takes about two minutes on Windows; allow host load.
PROCESS_TIMEOUT_S = 300
SOURCES = [REPO / line.strip() for line in (REPO / "rtl" / "files.f").read_text().splitlines()
           if line.strip() and not line.lstrip().startswith("#")]
SOURCES.append(REPO / "tests" / "rtl" / "p5" / "dummy_cnn.v")


def run(name, cmd, marker):
    try:
        result = subprocess.run([str(x) for x in cmd], cwd=OUT,
                                capture_output=True, text=True, timeout=PROCESS_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        print("FAIL %s: process timeout" % name)
        return False
    log = result.stdout + result.stderr
    (OUT / (name + ".log")).write_text(log)
    # Older Windows vvp builds can return zero even after $fatal.
    bad_log = any(token in log for token in ("FAIL", "FATAL:", "ERROR:"))
    ok = result.returncode == 0 and not bad_log and (marker is None or marker in log)
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        print(log)
    return ok


def main():
    iverilog, vvp = shutil.which("iverilog"), shutil.which("vvp")
    if not (iverilog and vvp):
        sys.exit("iverilog and vvp must be on PATH")
    OUT.mkdir(parents=True, exist_ok=True)
    ok = True
    for cpb, timeout in ((16, 3000), (868, 1_000_000)):
        for top, flags, marker in (
            ("tb_uart_rx", ["-Ptb_uart_rx.CPB=%d" % cpb], "PASS tb_uart_rx"),
            ("tb_comm", ["-DTEST_CPB=%d" % cpb, "-DTEST_TIMEOUT=%d" % timeout],
             "ALL TESTS PASSED"),
        ):
            name = "%s_%d" % (top, cpb)
            exe = OUT / (name + ".vvp")
            compiled = run(name + "_compile", [iverilog, "-g2005", "-s", top,
                           "-o", exe] + flags + SOURCES + [REPO / "tests" / "rtl" / "p5" / (top + ".v")], None)
            ok = compiled and ok
            if compiled:
                ok = run(name, [vvp, "-n", exe], marker) and ok
    ok = run("tsr_link_selftest", [sys.executable, REPO / "tsr_link.py", "--selftest"],
             "selftest passed") and ok
    print("Logs: %s" % OUT)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
