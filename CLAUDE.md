# CLAUDE.md

Context for Claude Code sessions in this repository. Read it first. **P3 status** at the end is P3's progress log: add a dated entry at the end of each P3 session.

## Project

A traffic-sign recogniser on a Digilent Basys3 (AMD Artix-7 XC7A35T, 100 MHz clock on W5). A CNN written in Verilog, with no processor, classifies a 16×16 grayscale sign picture in about 0.2 ms. The laptop preprocesses GTSRB images and sends them over UART, or the switches pick one of 16 stored signs. The board shows the class on the 7-segment display and replies over UART. Weights are trained offline in PyTorch; the board only runs inference. Five people, seven project days, a progress review every day at 14:00.

The full plan is not in Git. On Mahardika's laptop it is in the folder above this checkout:
- `Traffic_Sign_Recognition_Project_Plan.docx`: requirements, number formats, memory map, modules, testbenches, schedule, risks.
- `Traffic_Sign_Recognition_Plan_in_Pictures.docx`: the same plan as diagrams, with a glossary.
- `Final_Project_Guide_CNN_ADAS_Basys3.docx`: the lecturer's guide and rubric.
- `stats_to_analyze_reccomendation.jpeg`: the lecturer's whiteboard list of numbers to report (see below).

## Network and number formats

| Stage | Output | Format and memory layout |
| --- | --- | --- |
| Input | 16×16×1 | Unsigned 8-bit; address `row*16 + col` |
| Conv 3×3, 8 filters, no padding | 14×14×8 | Weights signed 8-bit −127..127, address `f*9 + kr*3 + kc`; biases signed 24-bit in accumulator units; 24-bit accumulator |
| Rescale and ReLU | 14×14×8, 0..127 | `q = clamp((acc*M + 2^(S-1)) >> S, 0, 127)`, M unsigned 16-bit; `fmap_ram` address `f*196 + r*14 + c` |
| Max-pool 2×2 | 7×7×8 = 392 | `pool_ram` address `f*49 + r*7 + c` (PyTorch's flatten order) |
| Fully connected 392→8 | 8 scores | Signed 24-bit, not rescaled; weights at `class*392 + f*49 + r*7 + c` |
| Argmax | Class 0..7 | A tie goes to the lower index |

Classes (display code, GTSRB id): StOP 14, yLd 13, no E 17, PrIo 12, CAUt 18, rIGt 38, 30 1, 50 2.

Interface rules: every engine takes a one-cycle `start` pulse and gives a one-cycle `done` pulse plus `busy`. Every memory read takes exactly 1 cycle. A valid bit travels with the data. M, S and the biases come from `params.vh`, written by P2's `make_mem.py`. UART is 115,200 baud 8N1: the frame is `0xA5`, command, 256 pixels, checksum, and the reply is 31 bytes starting with `0x5A`.

## Team

| Role | Person | Owns |
| --- | --- | --- |
| P1 Integration | Saufik Ramadhan (repo owner) | `top`, `controller`, XDC, Vivado project, `build.tcl`, timing closure, `cnn_core_tb`, `top_tb` |
| P2 Model | Rubi Naufaul | Dataset, training, golden model, `make_mem.py` (`.coe`, `.mem`, `params.vh`), `batch_check.py` |
| P3 Feature extraction | Mahardika | `conv_engine`, `requant_relu`, `fmap_ram`, `conv_wrom`, their testbenches |
| P4 Classify and output | Kania Ika, P3's buddy | `maxpool`, `fc_engine`, `argmax`, `fc_wrom`, `display`, LEDs |
| P5 I/O and UART | Dika | `uart_rx`, `uart_tx`, `frame_ctrl`, `img_buf`, `img_rom`, `input_mux`, `tsr_link.py` |

The README's role names map to these: System Integration = P1, Reference Model = P2, Feature Extraction = P3, CNN Implementation = P4, I/O Communication = P5.

## Repository conventions

- `rtl/` holds RTL modules and `rtl/tb/` their testbenches and scripts; `reference_model/` the Python model; `docs/` notes. `build/` is ignored by Git: generated vectors, logs and Vivado runs go there.
- GitHub Flow, as in `docs/GITHUB_WORKFLOW.md` (Indonesian): one branch per task from `main`, then a pull request, review and merge. Commit prefixes `feat:`, `fix:`, `docs:`. No direct pushes to `main`, no force-push. A module merges only with its testbench passing.
- Verilog-2001 for Vivado 2019.1 and Icarus Verilog 12: `` `timescale 1ns / 1ps`` and `` `default_nettype none`` at the top of each file, `` `default_nettype wire`` at the end; synchronous active-high `rst`.
- The team's own docs are in Indonesian; P3's notes are in English, like the plan.

## P3 work

The note for teammates is `docs/p3_feature_extraction.md`: ports, timing, file formats, and what P3 needs from whom.

```powershell
python rtl/tb/run_p3_tests.py                                         # Icarus Verilog
python rtl/tb/run_p3_tests.py --sim xsim --vivado-bin <Vivado>/bin    # Vivado simulator
python rtl/tb/run_p3_tests.py --vectors <folder>                      # conv_engine_tb on P2's golden dump
vivado -mode batch -nojournal -log build/p3_synth/vivado.log -source rtl/tb/synth_p3.tcl -tclargs build/p3_sim/iverilog/conv_model
```

`synth_p3.tcl` runs out-of-context synthesis, place and route of `conv_engine` plus `fmap_ram`, with I/O delays standing in for P5's block RAM, and prints WNS, LUTs, FFs, BRAM and DSPs.

`rtl/tb/p3_vectors.py` holds an integer reference of conv and rescale written from the plan. When P2's `golden.py` exists, the two must agree on the same images.

Xilinx `.bat` wrappers on Windows split arguments at `=`, so the runner passes `xvlog` its options with `-f xvlog.f`.

## Numbers to report

From the lecturer's whiteboard (2026-10-30): speed (frames per second, bit rate, latency), resources (LUT, BRAM, MACs, DSP), and power (mJ per frame, idle and active power in W). Throughput = bits per frame × frames per pixel × pixels per cycle × cycles per second. P3's Day-5 multiplier sweep should give cycles, LUT, FF, BRAM, DSP, top clock speed, power and energy per image for each version.

## P3 status

### 2026-10-30, session 1

- Cloned the repo; it held only the README and the GitHub workflow doc.
- Wrote `conv_wrom`, `requant_relu`, `fmap_ram`, `conv_engine`, `conv_engine_tb`, `requant_relu_tb`, `p3_vectors.py`, `run_p3_tests.py`, `synth_p3.tcl` with `p3_synth_top.v`, and `docs/p3_feature_extraction.md`.
- 11 of 11 tests pass on Icarus 12 and on the Vivado 2019.1 simulator. That is `conv_engine_tb` on 20 images of a random model, on the 24-bit accumulator limits, and on an overflow that must be flagged, plus `requant_relu_tb` with 10,000 values for each of 8 (M, S) pairs. All 21 bugs planted on purpose were caught.
- Measured: 14,117 cycles from `start` to `done`, which is 141 µs at 100 MHz.
- `synth_p3.tcl` after place and route: timing met at 100 MHz with 3.53 ns of slack; 116 LUTs, 88 FFs, 1 RAMB18, 2 DSP48E1. The conv multiply carries `(* use_dsp = "yes" *)`: without it Vivado used LUTs (190 LUTs, 2.44 ns of slack, slowest path from `pix_data`).
- Added `__pycache__/` to `.gitignore`.
- Committed on branch `p3/feature-extraction` for a pull request to `main`. There is no `gh` CLI on this laptop, so the pull request is opened on GitHub's web page.

Next:
1. Interface freeze: confirm the ports, `rst` and the `params.vh` names with P1, and the rescale formula, `conv_weights.mem` and the dump format with P2.
2. Run `--vectors` on P2's first golden dump.
3. Day 3: 3- and 9-multiplier versions behind a parameter. The image has one read port, so feed the extra multipliers from a 3×3 window of registers and two 16-pixel line buffers, with each pixel read once. The weights are in LUTs, so `conv_wrom` can return a whole kernel row or kernel at once. Keep the ports and the `fmap_ram` layout unchanged.
4. Day 5: the multiplier sweep with `synth_p3.tcl`, one row per version.
