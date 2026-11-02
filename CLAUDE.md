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
| Conv 3×3, 8 filters, no padding | 14×14×8 | Weights signed 8-bit −127..127, address `f*9 + kr*3 + kc`; biases signed 24-bit; 24-bit accumulator, bias first, overflow forbidden |
| Rescale and ReLU | 14×14×8, 0..127 | `q = min(127, (max(0, acc)*M + 2^(S-1)) >> S)` in 48 bits, M unsigned 16-bit, S 0..47 (no rounding term when S = 0); `fmap_ram` address `f*196 + r*14 + c` |
| Max-pool 2×2 | 7×7×8 = 392 | `pool_ram` address `f*49 + r*7 + c` (PyTorch's flatten order) |
| Fully connected 392→8 | 8 scores | Signed 24-bit, not rescaled; weights at `class*392 + f*49 + r*7 + c` |
| Argmax | Class 0..7 | A tie goes to the lower index |

These are P2's integer contract for the current model, p2-doc-int-v2 (`reference_model/INTEGER_CONTRACT.md`; golden model `reference_model/document_v2/golden.py`). Its package, `reference_model/models/p2-doc-int-v2/`, holds:
- `mem/`: `conv_weight.mem`, `conv_bias.mem`, `fc_weight.mem` and `fc_bias.mem`, plus matching `.coe` files. Biases are 6-hex-digit words.
- `params.vh`: M = 43980, S = 25 and the biases.
- `vectors/`: 25 golden vectors.
- `signs.mem` and `labels.mem`: the 16 stored pictures and their labels.

Its preprocessing is crop, grayscale, histogram equalization, then a bilinear resize to 16×16. The older p2-int-v1 (int32 biases and accumulators, M = 34172, no equalization) is kept for reference. Neither package is team-approved yet.

Classes, by output index (display code, GTSRB id), as in the plan: 0 = StOP (14), 1 = yLd (13), 2 = no E (17), 3 = PrIo (12), 4 = CAUt (18), 5 = rIGt (38), 6 = 30 (1), 7 = 50 (2). p2-int-v1 used another order.

Interface rules: every engine takes a one-cycle `start` pulse and gives a one-cycle `done` pulse plus `busy`. Every memory read takes exactly 1 cycle. A valid bit travels with the data. Weights and biases load from P2's `mem/` files with `$readmemh`. P2's `params.vh` names its constants `P2_RESCALE_M`, `P2_RESCALE_S`, `P2_ACC_BITS` and so on. It has an include guard, so include it once, in `cnn_core`, and pass the values down as parameters; a second module that includes it gets nothing. `conv_engine`'s parameter defaults are p2-doc-int-v2's. UART is 115,200 baud 8N1: the frame is `0xA5`, command, 256 pixels, checksum, and the reply is 31 bytes starting with `0x5A`.

## Team

| Role | Person | Owns |
| --- | --- | --- |
| P1 Integration | Saufik Ramadhan (repo owner) | `top`, `controller`, XDC, Vivado project, `build.tcl`, timing closure, `cnn_core_tb`, `top_tb` |
| P2 Model | Rubi Naufaul | Dataset, training, quantization, golden model (`reference_model/`), the model package (`.mem` and `.coe` files, `params.vh`, `contract.json`), `batch_check.py` |
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
python rtl/tb/run_p3_tests.py --vectors <folder>                      # conv_engine_tb on one P2 package outside the repo
python rtl/tb/run_p3_tests.py --wave                                  # also save waveforms (.vcd)
gtkwave build/p3_sim/iverilog/p2-doc-int-v2/conv_engine_tb.vcd rtl/tb/conv_engine_tb.gtkw
vivado -mode batch -nojournal -log build/p3_synth/vivado.log -source rtl/tb/synth_p3.tcl
```

The default run tests every package in `reference_model/models/`. p2-doc-int-v2 runs on its own 25 golden vectors, compiled with `P2_DEFAULTS` so the engine gets no parameters. p2-int-v1, which has no vectors, runs on 20 pictures checked against its `golden.py`, with `ACC_W` = 32. `conv_engine`'s `ACC_W` parameter (default 24) sets both the accumulator width and the width of each `conv_bias.mem` word.

`synth_p3.tcl` runs out-of-context synthesis, place and route of `conv_engine` plus `fmap_ram`, using p2-doc-int-v2's weights by default, with I/O delays standing in for P5's block RAM, and prints WNS, LUTs, FFs, BRAM and DSPs.

`rtl/tb/p3_vectors.py` holds P3's own integer reference of conv and rescale. `rtl/tb/p2_vectors.py` checks that it agrees with P2's golden vectors and golden models on every accumulator and activation.

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

### 2026-10-30, session 2

- Pushed `p3/feature-extraction` to GitHub (two commits). The user decided not to open a pull request or merge yet.
- Published a private line-by-line walkthrough of all P3 code for Mahardika: https://claude.ai/artifact/2mRX9Wn3iMjR5vw1CQjZ2k (built by a scratchpad script from the repo files; rebuild it when the code changes).
- Added waveforms: `--wave` in `run_p3_tests.py` compiles the testbenches with `DUMP`; `conv_engine_tb` records picture `DUMP_IMG` (default 3); `rtl/tb/conv_engine_tb.gtkw` is the GTKWave layout. The waveform confirms the timing: first result stored at the end of tick 14, `done` at tick 14,117. Pictures of it are in `build/p3_waves/` (not in Git).
- `run_p3_tests.py` now stops with a clear message if its work folder is in use (Windows locks a folder that GTKWave or a terminal has open).
- All tests still use P3's own random test data, not P2's model.
- The waveform work is committed and pushed to `p3/feature-extraction`; still no pull request.

### 2026-11-02, session 3

- P2 (Rubi) pushed the branch `reference_model`. It has the integer contract (`reference_model/INTEGER_CONTRACT.md`, `docs/P2_to_RTL_Handoff.docx`), the golden model `golden.py` and the model package p2-int-v1: int8 weights, int32 biases, M = 34172, S = 25, and 97.50% validation accuracy in both float and integer. Merged it into `p3/feature-extraction`; the only conflict was `.gitignore`, where both sides were kept.
- Moved P3's RTL to the contract. `conv_wrom` also holds the 8 biases, as int32 words read from `conv_bias.mem`. The accumulator is 32 bits. `requant_relu` applies the ReLU before the multiply and accepts S from 0 to 47; it works in 64 bits as the contract says, of which at most 48 are ever non-zero. `conv_engine`'s defaults are p2-int-v1's M, S and file names, so the RTL no longer uses `params.vh` (P2 does not supply one).
- `conv_engine_tb` now also checks all 1,568 accumulators before the rescale, as P2's handoff asks. The new `p2_vectors.py` checks P2's checksums and the `.mem` files against `parameters.npz`. It then takes expected values from `golden.py` for 20 pictures (P2's 8 class examples, P2's 5 synthetic inputs and 7 random ones) and checks P3's reference against them. `--vectors` now reads the folder layout P2's `quantize.py` writes.
- 14 of 14 tests pass on Icarus and on the Vivado 2019.1 simulator. That includes P2's model with the engine's default parameters: 20 pictures × 1,568 accumulators and activations, bit-exact. `golden.py` classifies all 8 class examples correctly. All 13 planted bugs were caught.
- Synthesis with P2's weights: timing met at 100 MHz with 1.12 ns of slack (3.53 ns before); 263 LUTs, 132 FFs, 1 RAMB18, 1 DSP48E1, about 8 mW dynamic. Vivado now builds the rescale's multiply by the constant M from LUTs (165 LUTs), and it is the slowest path (8.9 ns, `acc` to `prod`). A `use_dsp` attribute on `prod` would move it into DSP slices.
- On p2-int-v1, filter 2 can never fire: its positive weights times 255 add up to 4,845, less than its bias of −5,297. Filter 3 fires only on synthetic and random pictures, never on the 8 class examples. Worth telling Rubi.
- Figures, not in Git, in `build/p3_figures/`. All are drawn by scratchpad scripts adapted from session 2's:
  - `wave_start.png` and `wave_end.png`: the v2 run on a Yield sign from P2's vectors (redrawn after the v2 adaptation below).
  - `p2v2_feature_maps.png`: v2's 8 output maps for one validation picture per class.
  - `p2_feature_maps.png`: the same for v1's class examples.
- Committed as a merge of `reference_model` plus one `feat:` commit, and pushed to `p3/feature-extraction`; still no pull request. Once P2's branch reaches `main` through its own pull request, P3's pull request shows only P3's changes.
- Later the same day P2 pushed p2-doc-int-v2, which replaces p2-int-v1 as the model under review and follows the team plan document. Changes:
  - histogram equalization in preprocessing;
  - 24-bit biases, accumulators and scores, and a 48-bit rescale;
  - M = 43980, S = 25, and the plan's class order;
  - a `params.vh`, 25 golden vectors in Git, and the 16 stored pictures.

  Merged it in as well. P5's pull request had also reached `main` (not merged here).
- Adapted P3 to v2:
  - A new parameter, `ACC_W` (default 24; 32 for p2-int-v1), sets the accumulator width and the width of the `conv_bias.mem` words, since both contracts give biases the accumulator's type. With 32-bit memory words, `$readmemh` would have loaded v2's 6-digit biases unsigned: −15,479 as +16,761,737.
  - `requant_relu` works in 48 bits, as v2's contract says; that is also exact for v1's 32-bit accumulator.
  - `conv_engine`'s defaults are now p2-doc-int-v2's.
- The runner now tests every package in `reference_model/models/`: p2-doc-int-v2 on its own 25 golden vectors with the engine's defaults, and p2-int-v1 on 20 pictures with `ACC_W` = 32. The limit and overflow tests run at both 24 and 32 bits, and `requant_relu_tb` covers 13 (M, S, width) cases.
- 20 of 20 tests pass on Icarus and on the Vivado 2019.1 simulator. That includes all 25 of P2's v2 golden vectors with the engine's default parameters, bit-exact in every accumulator and activation, and p2-int-v1 with `ACC_W` = 32. All 7 new planted bugs were caught, among them a 32-bit default reading v2's biases (29,400 wrong accumulators).
- Synthesis with v2's weights: timing met at 100 MHz with 3.62 ns of slack (about 157 MHz); 123 LUTs, 99 FFs, 1 RAMB18, 2 DSP48E1, about 6 mW dynamic. The rescale's multiply is now 23 × 16 bits, which fits one DSP48E1, and Vivado put it there without a `use_dsp` attribute. The slowest path is now `pix_addr` leaving the block, which depends on the 2.5 ns assumed for `input_mux`.
- On v2, filter 2 still can never fire: even with 255 under every positive weight it reaches only −538. Filter 3 now fires (74% of outputs on the real pictures). No activation reaches the 127 clamp, and the largest accumulator is 95,531.

Next:
1. With P1: in `cnn_core`, include P2's `params.vh` once and pass `P2_RESCALE_M`, `P2_RESCALE_S` and `P2_ACC_BITS` to `conv_engine`, or pass nothing. Add P2's two conv `.mem` files to the Vivado project. Warn P1 and P4 about the include guard.
2. Tell P5 that v2's preprocessing adds histogram equalization, which the laptop side must match, and that `signs.mem` holds the 16 stored pictures for `image_input`. Scores are 24-bit again, which fits P5's 3-byte reply fields.
3. Tell Rubi that filter 2 is dead in both models.
4. Day 3: the 3- and 9-multiplier versions (as in session 1's list). Day 5: the multiplier sweep.
