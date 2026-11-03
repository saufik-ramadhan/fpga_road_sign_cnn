# P4 — Classify and Output (RTL subsystem)

Traffic-sign CNN on Basys3 (Artix-7 XC7A35T). This package implements the **back
end** of the pipeline: max-pooling, the fully-connected classifier, argmax, and
the 7-segment/LED display.

It is verified bit-exact against the P2 integer golden reference model
(contract `p2-int-v1`). See **Verification** below.

This is a **historical test-only implementation**, isolated from the production
`rtl/classification/` v2/int24 classifier. Do not add these modules to `rtl/files.f`:
module names overlap while interfaces, widths and class order differ. No
production integration, overflow coverage or board validation is claimed here.

```
            P3 (conv + requant/ReLU)                 P4  (this package)
  pixels ─► conv2d ─► ReLU/requant ─► fmap_ram ─► maxpool ─► pool_ram ─► fc_engine ─► argmax ─► sign_display ─► 7-seg + LED
                                      (8x14x14)             (8x7x7)      8 scores     class 0-7
```

P4 starts at `fmap_ram` (the requantized activation produced by P3) and ends at
the board pins. Everything before `fmap_ram` is P3's responsibility.

---

## 1. Numeric contract (p2-int-v1)

All widths and conventions below come from P2's `contract.json` / `INTEGER_CONTRACT.md`.

| Quantity | Type | Range | Notes |
|---|---|---|---|
| Pixels (P3 input) | uint8 | 0..255 | not used inside P4 |
| Activation (fmap, maxpool in/out) | uint8 | **0..127** | ReLU-clamped |
| FC weights | int8 | -127..127 | two's complement |
| FC bias | int32 | — | accumulator units |
| MAC accumulator / scores | int32 | — | **no rescale**, overflow forbidden |
| argmax tie rule | — | — | **lowest index wins** |

Proven worst-case partial-sum bounds (fixed params): conv 181,902; FC 610,764 —
both well inside int32. FC product term is 17-bit signed (9-bit × 8-bit).

**Class mapping (index 0-7), identical to `contract.json`:**

| Index | GTSRB ID | Sign | 7-seg text |
|---|---|---|---|
| 0 | 1 | Speed limit 30 | `  30` |
| 1 | 2 | Speed limit 50 | `  50` |
| 2 | 12 | Priority road | `PrIo` |
| 3 | 13 | Yield | ` yLd` |
| 4 | 14 | Stop | `StOP` |
| 5 | 17 | No entry | `noE ` |
| 6 | 18 | General caution | `CAUt` |
| 7 | 38 | Keep right | `rIGt` |

---

## 2. Memory layout (critical shared invariant)

Three memories cross module boundaries. Addressing **must** match P2's export,
or scores will be wrong even when each module is internally correct.

| Memory | Address formula | Depth (16×16) | Word | Written by | Read by |
|---|---|---|---|---|---|
| `fmap_ram` | `f*IN_W*IN_W + row*IN_W + col` | 1568 | 8-bit uint8 | P3 | maxpool |
| `pool_ram` | `f*OUT_W*OUT_W + r*OUT_W + c` (CHW) | 392 | 8-bit uint8 | **maxpool** | **fc_engine** |
| `fc_weight` ROM | `WGT_BASE + class*N_IN + i` (sequential) | 3136 | 8-bit int8 | P2 (`fc_weight.mem`) | fc_engine |

`IN_W` = conv feature-map side (14 for 16×16 input), `OUT_W = IN_W/2` (7).
FC bias comes from `fc_bias.mem` (8 words × int32) on the `bias_flat` bus:
`bias_flat[j*32 +: 32]` = bias for class `j`.

**BRAM read-latency assumption:** every read port (`fmap_dout`, `pool_dout`,
`wgt_dout`) must return data **exactly 1 clock after** the address — i.e. BRAM
with **no** output register. Configure block RAM accordingly.

---

## 3. Modules

### 3.1 `maxpool.v` — 2×2 max-pool, stride 2

Reads `fmap_ram`, writes the per-channel 2×2 maximum to `pool_ram` in CHW order.

**Parameters**

| Param | 16×16 | 32×32 | Meaning |
|---|---|---|---|
| `NF` | 8 | 8 | number of channels/filters |
| `IN_W` | 14 | 30 | feature-map side |
| `FA_W` | 11 | 13 | fmap address width |
| `PA_W` | 9 | 11 | pool address width |

**Ports**

| Port | Dir | Width | Description |
|---|---|---|---|
| `clk` | in | 1 | 100 MHz |
| `rst` | in | 1 | **synchronous, active-high** |
| `start` | in | 1 | 1-clock pulse; ignored while `busy` |
| `busy` | out | 1 | high during operation |
| `done` | out | 1 | 1-clock pulse when all pool words written |
| `fmap_addr` | out | `FA_W` | read address → fmap_ram |
| `fmap_dout` | in | 8 | uint8, valid 1 clock after `fmap_addr` |
| `pool_addr` | out | `PA_W` | write address → pool_ram |
| `pool_din` | out | 8 | uint8 pooled value |
| `pool_we` | out | 1 | write enable (1 clock per word) |

**Timing:** start→done = **1571 clocks** (16×16), 7203 (32×32).

### 3.2 `fc_engine.v` — fully-connected classifier

`score[j] = bias[j] + Σ_i pool[i] * weight[j*N_IN + i]`, for `j = 0..7`.
3-stage pipeline (address → multiply → accumulate), one term per clock, bias-first.

**Parameters**

| Param | 16×16 | 32×32 | Meaning |
|---|---|---|---|
| `N_IN` | 392 | 1800 | inputs per class (NF·OUT_W²) |
| `N_CLS` | 8 | 8 | number of classes |
| `IA_W` | 9 | 11 | pool_ram address width |
| `WA_W` | 12 | 14 | weight ROM address width |
| `CLS_W` | 3 | 3 | class counter width |
| `WGT_BASE` | 0 | 0 | weight ROM start offset |
| `ACC_W` | 32 | 32 | accumulator / score width |

**Ports**

| Port | Dir | Width | Description |
|---|---|---|---|
| `clk` | in | 1 | 100 MHz |
| `rst` | in | 1 | **synchronous, active-high** |
| `start` | in | 1 | 1-clock pulse; ignored while `busy` |
| `busy` | out | 1 | high during operation |
| `done` | out | 1 | 1-clock pulse; scores valid and held |
| `pool_raddr` | out | `IA_W` | read address → pool_ram |
| `pool_dout` | in | 8 | uint8, valid 1 clock after addr |
| `wgt_raddr` | out | `WA_W` | read address → fc_weight ROM |
| `wgt_dout` | in | signed 8 | int8, valid 1 clock after addr |
| `bias_flat` | in | `N_CLS*ACC_W` (256) | int32 biases packed, `[j*32 +: 32]` |
| `scores_flat` | out | `N_CLS*ACC_W` (256) | int32 scores packed, `[j*32 +: 32]` |

**Timing:** start→done = **3139 clocks** (16×16), 14403 (32×32). Scores stay
valid on `scores_flat` until the next run.

### 3.3 `argmax.v` — class selection

Pure **combinational**. Reads `scores_flat`, outputs the index of the maximum.
Ties resolve to the **lowest index** (matches contract).

**Parameters:** `N_CLS=8`, `ACC_W=32`, `CLS_W=3`.

**Ports**

| Port | Dir | Width | Description |
|---|---|---|---|
| `scores_flat` | in | `N_CLS*ACC_W` (256) | int32 scores from fc_engine |
| `class_out` | out | `CLS_W` (3) | selected class 0-7 |

**Timing:** 0 clocks (combinational). Drive it directly from `fc_engine.scores_flat`.

### 3.4 `sign_display.v` — 7-segment + LED output

Maps `class_in` (0-7) to a 4-character 7-segment message and a one-hot LED.
Time-multiplexes the 4 digits (~763 Hz/digit from a 17-bit refresh counter).

**Polarity is already matched to Basys3:**

| Signal | Polarity |
|---|---|
| `seg[6:0]` | **active-LOW**, bit order `{g,f,e,d,c,b,a}` (so `seg[0]`=segment a) |
| `an[3:0]` | **active-LOW** (`an[3]`=left digit, `an[0]`=right digit) |
| `led[7:0]` | **active-HIGH**, one-hot (`led[class]`=1) |
| `rst` | **active-HIGH** (Basys3 push-button; no CPU_RESETN pin on this board) |

**Ports**

| Port | Dir | Width | Description |
|---|---|---|---|
| `clk` | in | 1 | 100 MHz |
| `rst` | in | 1 | synchronous, active-high |
| `class_in` | in | 3 | class 0-7 (from argmax) |
| `valid` | in | 1 | 1 = show result; 0 = display + LED blank |
| `seg` | out | 7 | 7-segment cathode (active-low) |
| `an` | out | 4 | digit anode (active-low) |
| `led` | out | 8 | LED one-hot (active-high) |

`.xdc` note: map `seg[0]`→CA … `seg[6]`→CG, `an[0..3]`→AN0..AN3. This ordering
matches the standard Basys3 constraints file.

---

## 4. Integration guide (for the P1 controller)

**Sequencing** (maxpool and fc_engine never run at the same time):

1. P3 fills `fmap_ram`.
2. Pulse `maxpool.start` (1 clock). Wait for `maxpool.done`.
3. Pulse `fc_engine.start` (1 clock). Wait for `fc_engine.done`.
4. `scores_flat` is now valid → `argmax` produces `class_out` combinationally.
5. Drive `sign_display.class_in = class_out` and `valid = 1` to show the result.

**pool_ram** is shared: write side (`pool_addr`/`pool_din`/`pool_we`) from
maxpool, read side (`pool_raddr`/`pool_dout`) to fc_engine. Because the two
modules are sequenced, a simple dual-port (or shared single-port) BRAM with
1-clock read latency is sufficient.

**bias_flat**: load `fc_bias.mem` (8 × int32) into 8 registers and concatenate
into the 256-bit bus, or drive from a small ROM.

**Wiring argmax → sign_display**: `argmax` is combinational, so register
`class_out` (or gate with a `result_valid` flag) before presenting it to
`sign_display.valid`, to avoid showing transient values while fc_engine runs.

### Robustness caveat (read before scaling up)

`maxpool.v` uses a few hardcoded counter widths: `f[2:0]`, `r[3:0]`, `c[3:0]`,
`in_row/in_col[4:0]`. These are sufficient for `NF≤8` and `IN_W≤32` (so both the
16×16 and 32×32 configs work), but they are **not** derived from the parameters.
If anyone changes `NF>8` or `IN_W>32`, widen these registers accordingly.

---

## 5. Bit-width summary

| Where | Width | Signed? |
|---|---|---|
| Pixels / activations / pooled values | 8-bit (values 0..127) | unsigned |
| FC weights | 8-bit | signed |
| FC product term | 17-bit | signed |
| FC bias / accumulator / scores | 32-bit | signed |
| Class index | 3-bit | unsigned |
| fmap address (16×16) | 11-bit | unsigned |
| pool address (16×16) | 9-bit | unsigned |
| weight address (16×16) | 12-bit | unsigned |

Storing 8-bit (vs 7-bit) activations costs no extra BRAM on Artix-7 (the ×9 width
slice includes a parity bit), so values are kept as full bytes. The whole chain
uses only ~3-4 of the 50 block-RAMs even for 32×32.

---

## 6. Verification

Reference: P2 integer golden model (`golden.py` + `parameters.npz` +
`contract.json`), contract `p2-int-v1`.

**What was checked and passed:**

| Test | Result |
|---|---|
| maxpool vs golden `pool` | 15/15 vectors, all 392 bytes |
| fc_engine vs golden `scores` | 15/15 vectors, all 8 int32 |
| chain (maxpool→fc→argmax) vs golden pool+scores+prediction | 15/15 |
| sign_display (8 classes × 4 digits + LED + blank) | 41/41 checks |
| fc_weight.mem / fc_bias.mem vs parameters.npz | byte-identical |

Vectors: 5 directed (zeros, maximum, checkerboard, ramp, impulse) + 10 random,
all produced by P2's own `golden.infer()`.

**Reproduce (Icarus Verilog + Python/NumPy):**

```powershell
# From repository root: generate checked P2 v1 vectors and run every P4 test
python tests/run_rtl_tests.py --suite p4

# Optional separate generator and custom-vector invocation
python -I tests/rtl/p4/gen_golden_vectors.py reference_model/models/p2-int-v1 build/p4_vectors
python tests/rtl/p4/run_p4_vectors.py --vectors build/p4_vectors
```

Expected: `maxpool/fc/rantai 15/15 PASS`, and `41 checks PASS` for the display.

The standard runner also executes the standalone signed/tie argmax test and
five runner regressions. It compiles Verilog-2001, checks simulator exit codes
and error output, applies process timeouts, and stores compile/simulation logs
under `build/p4_sim/`. Malformed, empty, incomplete or unknown X/Z golden data
fails rather than being skipped. The chain testbench rejects unknown predictions
even without Python validation. Generator imports the repository's P2 golden
module, verifies sealed-package checksums and requires both FC memory files;
only the `p2-int-v1` package is supported.

**Not covered here** (out of P4 scope): real-image classification accuracy
(needs P2's `val_*` image vectors — a model-quality metric, not RTL correctness);
synthesis/timing closure, UART byte order (P5 protocol), and board-level tests.

---

## 7. File inventory

| File | Role |
|---|---|
| `maxpool.v` | 2×2 max-pool module |
| `fc_engine.v` | fully-connected classifier |
| `argmax.v` | combinational argmax |
| `sign_display.v` | 7-segment + LED output (Basys3 polarity) |
| `tb_maxpool.v`, `tb_fc_engine.v`, `tb_argmax.v`, `tb_p4_chain.v`, `tb_sign_display.v` | testbenches |
| `gen_golden_vectors.py` | build golden vectors from the P2 package |
| `run_p4_vectors.py` | compile + run the three RTL tests over all vectors |
| `reference_model/models/p2-int-v1/mem/` | FC parameters, read from the sealed package |

Shared memories (`fmap_ram`, `pool_ram`, `fc_weight` ROM) are instantiated by the
integrator per the layout in Section 2. The testbenches include simple behavioral
BRAM models (1-clock read latency) that illustrate the required memory behavior.
