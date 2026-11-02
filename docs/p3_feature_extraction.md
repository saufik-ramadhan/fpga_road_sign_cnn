# P3 Feature extraction: interfaces and status

Owner: Mahardika (P3). Buddy: Kania Ika (P4). P3 owns the convolution layer, from the input-image read port to the 1,568 activations in `fmap_ram`.

## Files

| File | What it is |
| --- | --- |
| `rtl/conv_engine.v` | 3×3 convolution, 8 filters, 1 multiply-accumulate per cycle; contains `conv_wrom` and `requant_relu` |
| `rtl/conv_wrom.v` | The 72 convolution weights in LUTs, 1-cycle read, loaded from `conv_weights.mem` |
| `rtl/requant_relu.v` | `q = clamp((acc*M + 2^(S-1)) >> S, 0, 127)`, 2-cycle pipeline |
| `rtl/fmap_ram.v` | 1,568-byte simple dual-port block RAM: `conv_engine` writes, `maxpool` reads |
| `rtl/tb/conv_engine_tb.v` | `conv_engine` + `fmap_ram`, checks all 1,568 outputs per image bit-exact |
| `rtl/tb/requant_relu_tb.v` | 10,000 accumulator values per (M, S), checks the result, order and latency |
| `rtl/tb/p3_vectors.py` | Integer reference of the conv layer and the test vectors |
| `rtl/tb/run_p3_tests.py` | Runs everything and prints PASS/FAIL |
| `rtl/tb/synth_p3.tcl`, `rtl/tb/p3_synth_top.v` | Out-of-context synthesis, place and route of the block, for timing, resources and power |
| `rtl/tb/conv_engine_tb.gtkw` | GTKWave layout for the engine's waveform: signals grouped by pipeline station |

## Running the tests

```powershell
python rtl/tb/run_p3_tests.py                                   # Icarus Verilog
python rtl/tb/run_p3_tests.py --sim xsim --vivado-bin C:/Xilinx/Vivado/2019.1/bin
python rtl/tb/run_p3_tests.py --vectors path/to/golden_dump      # on P2's dump
python rtl/tb/run_p3_tests.py --wave                             # also save waveforms (.vcd)
gtkwave build/p3_sim/iverilog/conv_model/conv_engine_tb.vcd rtl/tb/conv_engine_tb.gtkw
```

Vectors, logs and simulator files go to `build/p3_sim/`, which Git ignores.

With `--wave`, each test also saves a waveform next to its log. `conv_engine_tb` records one picture's run and read-back (picture 3 by default, about 6 MB; set `DUMP_IMG` to pick another). GTKWave comes with Icarus Verilog; the `.gtkw` layout opens at the start of the run. The waveform shows the pipeline exactly as designed: the first result is stored at the end of tick 14, and `done` rises at tick 14,117.

All 11 tests pass on Icarus Verilog 12 and on the Vivado 2019.1 simulator. They are `conv_engine_tb` on 20 images of a random model, on the 24-bit accumulator limits, and on an overflow that must be flagged, plus `requant_relu_tb` with 10,000 values for each of 8 (M, S) pairs.

## Synthesis

```powershell
vivado -mode batch -nojournal -log build/p3_synth/vivado.log -source rtl/tb/synth_p3.tcl -tclargs build/p3_sim/iverilog/conv_model
```

Run it from the repository root in the Vivado Tcl Shell, or with Vivado's `bin` folder on PATH. The results below are out of context on the XC7A35T (`xc7a35tcpg236-1`), from Vivado 2019.1 after place and route. The run assumes `pix_data` arrives 3 ns after the clock (P5's block RAM plus `input_mux`) and `pix_addr` must leave 2.5 ns before it:

| Timing at 100 MHz | LUTs | Flip-flops | Block RAM | DSP48E1 | Dynamic power |
| --- | --- | --- | --- | --- | --- |
| Met, 3.53 ns of slack (top speed about 155 MHz) | 116 | 88 | 1 RAMB18 (half a tile) | 2 | about 5 mW (estimate) |

The two DSP slices hold the multiply-accumulate and the rescale. Without the `use_dsp` attribute, Vivado builds the 8-bit multiply from LUTs: 190 LUTs, 1 DSP, and only 2.44 ns of slack, with the slowest path running from `pix_data` through the multiplier.

## `conv_engine` ports

Parameters: `M` and `S` (rescale), `BIAS` (the 8 conv biases), `WEIGHT_FILE` (default `"conv_weights.mem"`). In `cnn_core`, pass `CONV_M`, `CONV_S` and `CONV_BIAS` from `params.vh`.

| Port | Dir | Width | Meaning |
| --- | --- | --- | --- |
| `clk` | in | 1 | 100 MHz |
| `rst` | in | 1 | Synchronous, active high, from `top`'s reset synchroniser |
| `start` | in | 1 | One-cycle pulse; ignored while `busy` |
| `busy` | out | 1 | High from the cycle after `start` until `done` |
| `done` | out | 1 | One-cycle pulse; all 1,568 values are in `fmap_ram` |
| `ovf` | out | 1 | An accumulator step left the 24-bit range during this run (should never happen) |
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

## Proposed formats for P2's files

To be confirmed at the interface freeze with P1 and P2.

**`params.vh`**: only `localparam` lines, so any module can `` `include `` it inside its body. P3 uses these three:

```verilog
localparam [15:0]     CONV_M    = 16'd1561;   // unsigned
localparam integer    CONV_S    = 20;         // 1..40
localparam [8*24-1:0] CONV_BIAS = {24'h000123, 24'hfffe10, /* ... */ 24'h0004d2};  // filter 7 first, filter 0 last
```

**`conv_weights.mem`**: 72 lines, two hex digits each, two's complement (`-1` is `ff`), in the order `filter*9 + kernel_row*3 + kernel_col`. Vivado's `$readmemh` reads `.mem`, not `.coe`, so please have `make_mem.py` write this file next to `conv_weights.coe`.

**Golden dump for `conv_engine_tb`**: one folder with

| File | Lines | Each line |
| --- | --- | --- |
| `pixels.mem` | N × 256 | Pixel, 2 hex digits, image after image, `row*16 + col` |
| `conv_out.mem` | N × 1,568 | Activation after rescale, 2 hex digits, `filter*196 + row*14 + col` |
| `conv_weights.mem`, `params.vh` | | As above |

**Arithmetic the golden model must match**: weights −127..127; biases inside ±8,097,142 (so 9 × 255 × 127 plus the bias still fits in 24 bits); `S ≥ 1`; compute `acc*M` in int64 (it needs up to 40 bits); `>>` is a floor shift, which NumPy and Python both do.

## What P3 needs from each person

| From | What | When |
| --- | --- | --- |
| P1 Saufik | Confirm these ports, the reset convention and the `params.vh` names; add `conv_weights.mem` to the Vivado project; review this code | Day 1, 13:00; review on Day 2 |
| P2 Rubi | The rescale formula as above; `conv_weights.mem` and `params.vh`; a 20-image dump in the format above | Day 1, 17:00 (first dump); Day 2 (20 images) |
| P4 Kania | Read `fmap_ram` with a 1-cycle read; start `maxpool` after `done`; review each other's code as buddies | Day 2 |
| P5 Dika | `input_mux` gives `pix_data` exactly 1 cycle after `pix_addr`, with no extra register; the image must not change during a 141 µs run | Day 2 |

## What P3 delivers

| When | Deliverable |
| --- | --- |
| Day 2 | `conv_engine` and `requant_relu` passing against P2's dumps, plus the overflow test; present at 14:00 |
| Day 3 | Help `cnn_core` integration; add 3- and 9-multiplier versions behind a parameter |
| Day 4 | Fix integration bugs; finish the multiplier versions; check the rescale path for timing |
| Day 5 | Multiplier sweep: cycles, DSPs, LUTs, BRAM, top clock speed, power and energy per image |
| Day 6 | Debug support; check the on-board latency (B5) |
| Day 7 | Slides on architecture, convolution and trade-offs |
