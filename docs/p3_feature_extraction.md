# P3 Feature extraction: interfaces and status

Owner: Mahardika (P3). Buddy: Kania Ika (P4). P3 owns the convolution layer, from the input-image read port to the 1,568 activations in `fmap_ram`.

The arithmetic is P2's integer contract (`reference_model/INTEGER_CONTRACT.md`), and the weights and biases are P2's files. The current model is p2-int-v1, in `reference_model/models/p2-int-v1/`.

## Files

| File | What it is |
| --- | --- |
| `rtl/conv_engine.v` | 3×3 convolution, 8 filters, 1 multiply-accumulate per cycle, 32-bit accumulator; contains `conv_wrom` and `requant_relu` |
| `rtl/conv_wrom.v` | The 72 weights and 8 biases in LUTs, 1-cycle reads, loaded from P2's `conv_weight.mem` and `conv_bias.mem` |
| `rtl/requant_relu.v` | `q = min(127, (max(0, acc)*M + 2^(S-1)) >> S)`, 2-cycle pipeline |
| `rtl/fmap_ram.v` | 1,568-byte simple dual-port block RAM: `conv_engine` writes, `maxpool` reads |
| `rtl/tb/conv_engine_tb.v` | `conv_engine` + `fmap_ram`; checks all 1,568 accumulators and all 1,568 activations of each image bit-exact |
| `rtl/tb/requant_relu_tb.v` | 10,000 accumulator values per (M, S), checks the result, order and latency |
| `rtl/tb/p3_vectors.py` | P3's own integer reference of the conv layer, and P3's test vectors |
| `rtl/tb/p2_vectors.py` | Vectors from P2's packages, with expected values from P2's `golden.py` |
| `rtl/tb/run_p3_tests.py` | Runs everything and prints PASS/FAIL |
| `rtl/tb/synth_p3.tcl`, `rtl/tb/p3_synth_top.v` | Out-of-context synthesis, place and route of the block, for timing, resources and power |
| `rtl/tb/conv_engine_tb.gtkw` | GTKWave layout for the engine's waveform: signals grouped by pipeline station |

## Running the tests

```powershell
python rtl/tb/run_p3_tests.py                                   # Icarus Verilog
python rtl/tb/run_p3_tests.py --sim xsim --vivado-bin C:/Xilinx/Vivado/2019.1/bin
python rtl/tb/run_p3_tests.py --vectors path/to/integer_v1       # on P2's full vector package
python rtl/tb/run_p3_tests.py --wave                             # also save waveforms (.vcd)
gtkwave build/p3_sim/iverilog/p2_model/conv_engine_tb.vcd rtl/tb/conv_engine_tb.gtkw
```

Vectors, logs and simulator files go to `build/p3_sim/`, which Git ignores. The P2 tests need NumPy and Pillow, as in P2's `reference_model/requirements.txt`.

The default run has 14 tests. All pass on Icarus Verilog 12 and on the Vivado 2019.1 simulator:

- `conv_engine_tb` on P2's model, 20 pictures: P2's example picture of each of the 8 classes, the 5 synthetic inputs of P2's vector export (zeros, maximum, checkerboard, ramp, impulse) and 7 random pictures. The expected values come from P2's `golden.py`, and P3's own reference must agree with it on every value. The engine is compiled with no parameters (`P2_DEFAULTS`), as a top that passes none, so this test also checks that its defaults are P2's model. Before the test, the runner checks P2's checksums and that the `.mem` files hold the same numbers as `parameters.npz`. `golden.py` classifies all 8 class examples correctly.
- `conv_engine_tb` on P3's random model (20 images), on the 32-bit accumulator limits, and on an overflow that must be flagged.
- `requant_relu_tb` with 10,000 values for each of 10 (M, S) pairs, from S = 0 to S = 47, including P2's M = 34172, S = 25.

What the P2 test shows about the model: filter 2 can never fire. Even with 255 under each of its positive weights it reaches 4,845, less than its bias of −5,297, so its activations are always 0. Filter 3 fires only on synthetic and random pictures (at most 4), never on the 8 class examples. No activation is clipped: 200 of the 31,360 values reach exactly 127.

`conv_engine_tb` compares in the order P2's handoff asks for: each of the 1,568 accumulators as it finishes, then each activation read back from `fmap_ram`. The accumulators catch errors the rescale can hide: a planted bug that gave 7 outputs per picture the wrong bias changed 140 accumulators but only 67 activations. All 13 bugs planted on purpose were caught.

`--vectors DIR` runs `conv_engine_tb` on every vector in the folder P2's `quantize.py` writes: `contract.json`, `mem/`, and `vectors/<name>/` with `input.mem`, `conv_acc.mem` and `activation.mem`. P2's folder (25 vectors) is not in Git yet. The reader passed on a stand-in folder in the same layout.

With `--wave`, each test also saves a waveform next to its log. `conv_engine_tb` records one picture's run and read-back (picture 3 by default, about 6 MB; set `DUMP_IMG` to pick another). GTKWave comes with Icarus Verilog; the `.gtkw` layout opens at the start of the run. The first result is stored at the end of tick 14, and `done` rises at tick 14,117.

## Synthesis

```powershell
vivado -mode batch -nojournal -log build/p3_synth/vivado.log -source rtl/tb/synth_p3.tcl
```

Run it from the repository root in the Vivado Tcl Shell, or with Vivado's `bin` folder on PATH. It uses P2's p2-int-v1 weights and biases unless you pass another folder with `-tclargs`. The results below are out of context on the XC7A35T (`xc7a35tcpg236-1`), from Vivado 2019.1 after place and route. The run assumes `pix_data` arrives 3 ns after the clock (P5's block RAM plus `input_mux`) and `pix_addr` must leave 2.5 ns before it:

| Version | Timing at 100 MHz | LUTs | Flip-flops | Block RAM | DSP48E1 | Dynamic power |
| --- | --- | --- | --- | --- | --- | --- |
| P2's model, 32-bit contract (2 November) | Met, 1.12 ns of slack (top speed about 113 MHz) | 263 | 132 | 1 RAMB18 (half a tile) | 1 | about 8 mW (estimate) |
| P3's random model, 24-bit (30 October) | Met, 3.53 ns of slack (about 155 MHz) | 116 | 88 | 1 RAMB18 | 2 | about 5 mW |

The DSP slice holds the conv multiply-accumulate. With M fixed at 34,172, Vivado builds the rescale's multiply by that constant from LUTs, as shifts and adds: 165 of the 263 LUTs are in `requant_relu`, and that multiply is now the slowest path (8.9 ns from `acc` to `prod`). A `use_dsp` attribute on `prod` would move it into DSP slices, as the conv multiply already is. Without the attribute on the conv multiply, Vivado also builds that one from LUTs, and it becomes the slowest path from `pix_data`.

## `conv_engine` ports

Parameters, with defaults from p2-int-v1's `contract.json`: `M` = 34172 and `S` = 25 (rescale), `WEIGHT_FILE` = `"conv_weight.mem"`, `BIAS_FILE` = `"conv_bias.mem"`. In `cnn_core`, instantiate `conv_engine` with no parameters and add P2's `mem/conv_weight.mem` and `mem/conv_bias.mem` to the Vivado project (`read_mem` in a non-project Tcl flow) so `$readmemh` finds them. For another model version, pass its `M` and `S` and use its `mem/` files.

| Port | Dir | Width | Meaning |
| --- | --- | --- | --- |
| `clk` | in | 1 | 100 MHz |
| `rst` | in | 1 | Synchronous, active high, from `top`'s reset synchroniser |
| `start` | in | 1 | One-cycle pulse; ignored while `busy` |
| `busy` | out | 1 | High from the cycle after `start` until `done` |
| `done` | out | 1 | One-cycle pulse; all 1,568 values are in `fmap_ram` |
| `ovf` | out | 1 | An accumulator step left the 32-bit range during this run. The contract forbids it; for p2-int-v1 it cannot happen |
| `pix_rd` | out | 1 | `pix_addr` is a real read this cycle |
| `pix_addr` | out | 8 | `row*16 + col` of the input image |
| `pix_data` | in | 8 | Unsigned pixel, exactly 1 cycle after `pix_addr` |
| `fm_we`, `fm_addr`, `fm_data` | out | 1, 11, 8 | Write port into `fmap_ram`: `filter*196 + row*14 + col`, value 0..127 |

Timing, measured in simulation: **14,117 cycles from `start` to `done`** (141 µs at 100 MHz): 1,568 outputs × 9 taps, plus 5 cycles of pipeline. Every image takes the same number of cycles.

## `fmap_ram` ports (for P4's `maxpool`)

| Port | Dir | Width | Meaning |
| --- | --- | --- | --- |
| `we`, `waddr`, `wdata` | in | 1, 11, 8 | From `conv_engine` |
| `raddr` | in | 11 | `filter*196 + row*14 + col` |
| `rdata` | out | 8 | 0..127, exactly 1 cycle after `raddr` (no output register) |

`maxpool` may start reading in the cycle after `conv_engine`'s `done`.

## How the RTL follows P2's contract

| Contract | P3's RTL |
| --- | --- |
| Pixels uint8, zero-extended before the multiply | `$signed({1'b0, pix_data}) * w_data`, a 17-bit product |
| Weights int8, OIHW, address `f*9 + ky*3 + kx` | `conv_wrom`, loaded from `conv_weight.mem` as delivered |
| Biases int32; an int32 accumulator that starts at the bias and adds the products in kernel order | 32-bit `acc`, starting at the filter's word of `conv_bias.mem` |
| Accumulator overflow is forbidden | `ovf` goes high if any step leaves the 32-bit range. p2-int-v1's bound is 181,902, far inside it |
| `P = max(0, A)`, then `min(127, (P*M + R) >> S)`, with `R = 2^(S-1)`, or 0 when S = 0, computed in 64 bits | `requant_relu`: the ReLU, a 31 × 16-bit multiply, then a 64-bit round and shift. With a 32-bit input the sum never needs more than 48 bits, so the result equals the 64-bit formula for every legal input, not only for these weights |
| Activations 0..127, address `(f*14 + y)*14 + x` | `fmap_ram`, address `filter*196 + row*14 + col` |

## What P3 needs from each person

| From | What |
| --- | --- |
| P1 Saufik | Instantiate `conv_engine` with no parameters; add P2's `conv_weight.mem` and `conv_bias.mem` to the Vivado project; review this code |
| P2 Rubi | The full vector package (`build/reference_model/integer_v1/`, 25 vectors) for `--vectors`; agreement that the 48-bit rescale sum meets the contract |
| P4 Kania | Read `fmap_ram` with a 1-cycle read; start `maxpool` after `done`; review each other's code as buddies |
| P5 Dika | Already met: `image_input` gives the pixel 1 cycle after the address. The image must not change during a 141 µs run |

## What P3 delivers

| When | Deliverable |
| --- | --- |
| Day 2 | `conv_engine` and `requant_relu` passing against P2's dumps, plus the overflow test; present at 14:00 |
| Day 3 | Help `cnn_core` integration; add 3- and 9-multiplier versions behind a parameter |
| Day 4 | Fix integration bugs; finish the multiplier versions; check the rescale path for timing |
| Day 5 | Multiplier sweep: cycles, DSPs, LUTs, BRAM, top clock speed, power and energy per image |
| Day 6 | Debug support; check the on-board latency (B5) |
| Day 7 | Slides on architecture, convolution and trade-offs |
