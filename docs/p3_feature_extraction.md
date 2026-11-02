# P3 Feature extraction: interfaces and status

Owner: Mahardika (P3). Buddy: Kania Ika (P4). P3 owns the convolution layer, from the input-image read port to the 1,568 activations in `fmap_ram`.

The arithmetic is P2's integer contract (`reference_model/INTEGER_CONTRACT.md`), and the weights and biases are P2's files. The current model is p2-doc-int-v2, in `reference_model/models/p2-doc-int-v2/`, with its golden model in `reference_model/document_v2/golden.py`. The older p2-int-v1 still runs, with a 32-bit accumulator.

## Files

| File | What it is |
| --- | --- |
| `rtl/conv_engine.v` | 3×3 convolution, 8 filters, 1 multiply-accumulate per cycle, `ACC_W`-bit accumulator (24 by default); contains `conv_wrom` and `requant_relu` |
| `rtl/conv_wrom.v` | The 72 weights and 8 biases in LUTs, 1-cycle reads, loaded from P2's `conv_weight.mem` and `conv_bias.mem` |
| `rtl/requant_relu.v` | `q = min(127, (max(0, acc)*M + 2^(S-1)) >> S)` in 48 bits, 2-cycle pipeline |
| `rtl/fmap_ram.v` | 1,568-byte simple dual-port block RAM: `conv_engine` writes, `maxpool` reads |
| `rtl/tb/conv_engine_tb.v` | `conv_engine` + `fmap_ram`; checks all 1,568 accumulators and all 1,568 activations of each image bit-exact |
| `rtl/tb/requant_relu_tb.v` | 10,000 accumulator values per (M, S, width), checks the result, order and latency |
| `rtl/tb/p3_vectors.py` | P3's own integer reference of the conv layer, and P3's test vectors |
| `rtl/tb/p2_vectors.py` | Tests from P2's packages: their own golden vectors, or P2's golden model when a package has none |
| `rtl/tb/run_p3_tests.py` | Runs everything and prints PASS/FAIL |
| `rtl/tb/synth_p3.tcl`, `rtl/tb/p3_synth_top.v` | Out-of-context synthesis, place and route of the block, for timing, resources and power |
| `rtl/tb/conv_engine_tb.gtkw` | GTKWave layout for the engine's waveform: signals grouped by pipeline station |

## Running the tests

```powershell
python rtl/tb/run_p3_tests.py                                   # Icarus Verilog
python rtl/tb/run_p3_tests.py --sim xsim --vivado-bin C:/Xilinx/Vivado/2019.1/bin
python rtl/tb/run_p3_tests.py --vectors path/to/package          # on one P2 package outside the repository
python rtl/tb/run_p3_tests.py --wave                             # also save waveforms (.vcd)
gtkwave build/p3_sim/iverilog/p2-doc-int-v2/conv_engine_tb.vcd rtl/tb/conv_engine_tb.gtkw
```

Vectors, logs and simulator files go to `build/p3_sim/`, which Git ignores. The P2 tests need NumPy and Pillow, as in P2's `reference_model/requirements.txt`. Missing dependencies, missing model packages and packages without input images make the run fail; an empty test selection never counts as success.

Run the runner's regression checks with standard-library unittest:

```powershell
python -m unittest discover -s rtl/tb -p test_run_p3_tests.py
```

The default run has 20 tests. All pass on Icarus Verilog 12 and on the Vivado 2019.1 simulator:

- `conv_engine_tb` on p2-doc-int-v2's own 25 golden vectors: 20 validation pictures and P2's 5 synthetic inputs. The engine is compiled with no parameters (`P2_DEFAULTS`), as a top that passes none, so this test also checks that its defaults are P2's current model.
- `conv_engine_tb` on p2-int-v1, whose package has no vectors: 20 pictures (P2's example of each class, the 5 synthetic inputs and 7 random pictures) checked against v1's `golden.py`, with `ACC_W` = 32.
- `conv_engine_tb` on P3's random model (20 images), and on the accumulator limits and an overflow that must be flagged, each at 24 and 32 bits.
- `requant_relu_tb` with 10,000 values for each of 13 cases: 11 (M, S) pairs from S = 0 to 47 at 24 bits, including P2's (43980, 25) and (34172, 25), and 2 at 32 bits.

Before the P2 tests, the runner checks P2's checksums, that the `.mem` files hold the same numbers as `parameters.npz`, and that P3's own reference gives every accumulator and activation P2 expects.

What the tests show about p2-doc-int-v2: filter 2 can never fire. Even with 255 under each of its positive weights it reaches only −538, so its activations are always 0. The other 7 filters all fire on the real pictures; filter 3, which never fired on v1's class examples, now fires on 74% of its outputs. No activation is clipped (none of the 39,200 reaches 127), and the largest accumulator is 95,531, far inside 24 bits.

`conv_engine_tb` compares in the order P2's handoff asks for: each of the 1,568 accumulators as it finishes, then each activation read back from `fmap_ram`. The accumulators catch errors the rescale can hide: a planted bug that gave 7 outputs per picture the wrong bias changed 140 accumulators but only 67 activations. Every bug planted on purpose has been caught: 13 in the 32-bit version, then 7 more for the 24-bit version, including a 32-bit default reading v2's 6-digit biases (29,400 wrong accumulators).

`--vectors DIR` runs `conv_engine_tb` on one P2 package folder outside the repository, such as a new export: `contract.json`, `mem/`, and `vectors/<name>/` with `input.mem`, `conv_acc.mem` and `activation.mem`, as P2's export writes them.

With `--wave`, each test also saves a waveform next to its log. `conv_engine_tb` records one picture's run and read-back (picture 3 by default, about 6 MB; set `DUMP_IMG` to pick another). In p2-doc-int-v2's vectors, picture 3 is a Yield sign. GTKWave comes with Icarus Verilog; the `.gtkw` layout opens at the start of the run. The first result is stored at the end of tick 14, and `done` rises at tick 14,117.

## Synthesis

```powershell
vivado -mode batch -nojournal -log build/p3_synth/vivado.log -source rtl/tb/synth_p3.tcl
```

Run it from the repository root in the Vivado Tcl Shell, or with Vivado's `bin` folder on PATH. It uses p2-doc-int-v2's weights and biases unless you pass another 24-bit set with `-tclargs`. The results below are out of context on the XC7A35T (`xc7a35tcpg236-1`), from Vivado 2019.1 after place and route. The run assumes `pix_data` arrives 3 ns after the clock (P5's block RAM plus `input_mux`) and `pix_addr` must leave 2.5 ns before it:

| Version | Timing at 100 MHz | LUTs | Flip-flops | Block RAM | DSP48E1 | Dynamic power |
| --- | --- | --- | --- | --- | --- | --- |
| p2-doc-int-v2, 24-bit (2 November) | Met, 3.62 ns of slack (top speed about 157 MHz) | 123 | 99 | 1 RAMB18 (half a tile) | 2 | about 6 mW (estimate) |
| p2-int-v1, 32-bit (2 November) | Met, 1.12 ns of slack (about 113 MHz) | 263 | 132 | 1 RAMB18 | 1 | about 8 mW |
| P3's random model, 24-bit (30 October) | Met, 3.53 ns of slack (about 155 MHz) | 116 | 88 | 1 RAMB18 | 2 | about 5 mW |

Both multiplies are in DSP slices. One holds the conv multiply-accumulate. With a 24-bit accumulator, the rescale multiplies 23 bits by M's 16 bits, which fits one DSP48E1 (25 × 18 bits), and Vivado puts it there by itself: `requant_relu` takes 36 LUTs and 1 DSP. With v1's 32-bit accumulator the multiply was 31 × 16 bits, wider than one slice, and Vivado built it from LUTs instead, as shifts and adds: 165 LUTs, and the slowest path (8.9 ns from `acc` to `prod`).

The slowest path is now `pix_addr` leaving the block: 2.87 ns through one LUT after the `kr` counter, with 2.5 ns assumed for `input_mux` outside. Inside the block, the slowest is `acc` into the rescale's DSP, with 3.64 ns of slack. The conv multiply carries `(* use_dsp = "yes" *)`: without it, Vivado builds that small multiply from LUTs, and it becomes the slowest path from `pix_data`.

## `conv_engine` ports

Parameters, with defaults from p2-doc-int-v2's `params.vh`: `M` = 43980 and `S` = 25 (rescale), `ACC_W` = 24 (the accumulator, and the width of each `conv_bias.mem` word), `WEIGHT_FILE` = `"conv_weight.mem"`, `BIAS_FILE` = `"conv_bias.mem"`.

In `cnn_core`, either instantiate `conv_engine` with no parameters, or include P2's `params.vh` and pass `.M(P2_RESCALE_M), .S(P2_RESCALE_S), .ACC_W(P2_ACC_BITS)`, so that a new model version needs no RTL edit. The corrected P2 header in `main` has no global include guard: include it once inside each consuming module, or include it in `cnn_core` and pass the constants down. Add P2's `mem/conv_weight.mem` and `mem/conv_bias.mem` to the Vivado project (`read_mem` in a non-project Tcl flow) so `$readmemh` finds them. For p2-int-v1, pass `M` = 34172 and `ACC_W` = 32.

| Port | Dir | Width | Meaning |
| --- | --- | --- | --- |
| `clk` | in | 1 | 100 MHz |
| `rst` | in | 1 | Synchronous, active high, from `top`'s reset synchroniser |
| `start` | in | 1 | One-cycle pulse; ignored while `busy` |
| `busy` | out | 1 | High from the cycle after `start` until `done` |
| `done` | out | 1 | One-cycle pulse; all 1,568 values are in `fmap_ram` |
| `ovf` | out | 1 | An accumulator step left the `ACC_W`-bit range during this run. The contract forbids it; for p2-doc-int-v2 it cannot happen |
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
| Biases have the accumulator's type, int24 in v2 (int32 in v1); the accumulator starts at the bias and adds the products in kernel order | `ACC_W`-bit `acc` and bias words, 24 by default, starting at the filter's word of `conv_bias.mem` |
| Accumulator overflow is forbidden | `ovf` goes high if any step leaves the `ACC_W`-bit range. p2-doc-int-v2's bound is 167,442, far inside 24 bits |
| `P = max(0, A)`, then `min(127, (P*M + R) >> S)`, with `R = 2^(S-1)`, or 0 when S = 0, computed in 48 bits (v1 said 64) | `requant_relu`: the ReLU, a 23 × 16-bit multiply (`ACC_W` − 1 bits by 16), then a 48-bit round and shift. 48 bits hold every legal value even with a 32-bit accumulator, so the result also equals v1's 64-bit formula |
| Activations 0..127, address `(f*14 + y)*14 + x` | `fmap_ram`, address `filter*196 + row*14 + col` |

## What P3 needs from each person

| From | What |
| --- | --- |
| P1 Saufik | Instantiate `conv_engine` with no parameters, or with `P2_RESCALE_M`, `P2_RESCALE_S` and `P2_ACC_BITS` from P2's `params.vh`, included once; add P2's `conv_weight.mem` and `conv_bias.mem` to the Vivado project; review this code |
| P2 Rubi | A look at filter 2, which can never fire in v1 or v2; agreement that P3 follows the v2 contract |
| P4 Kania | Read `fmap_ram` with a 1-cycle read; start `maxpool` after `done`; review each other's code as buddies |
| P5 Dika | Already met: `image_input` gives the pixel 1 cycle after the address. The image must not change during a 141 µs run. v2's 16 stored pictures are P2's `signs.mem` |

## What P3 delivers

| When | Deliverable |
| --- | --- |
| Day 2 | `conv_engine` and `requant_relu` passing against P2's dumps, plus the overflow test; present at 14:00 |
| Day 3 | Help `cnn_core` integration; add 3- and 9-multiplier versions behind a parameter |
| Day 4 | Fix integration bugs; finish the multiplier versions; check the rescale path for timing |
| Day 5 | Multiplier sweep: cycles, DSPs, LUTs, BRAM, top clock speed, power and energy per image |
| Day 6 | Debug support; check the on-board latency (B5) |
| Day 7 | Slides on architecture, convolution and trade-offs |
