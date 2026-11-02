# Provisional numerical contract p2-int-v1

**Historical experiment:** superseded as the implementation target by the
document-based planning reset on 2 November 2026. See DOCUMENT_BASELINE.md.
This preserved contract still describes the old package exactly; it does not
implement the new equalisation/int24 target.

This contract is a software simulation candidate for RTL review, not a claim
that hardware has implemented it. The architecture is the existing 16x16
eight-class CNN. Float training is unchanged; quantization derives a second
integer representation of the same learned parameters.

| Quantity | Representation |
|---|---|
| Input | uint8, 0..255, real scale 1/255, zero point 0 |
| Layer weights | int8, -127..127, symmetric, one positive scale per layer |
| Bias | int32, scale input_scale times weight_scale for its layer |
| Convolution and classifier MAC | int32, bias first, then serial products; overflow forbidden |
| Intermediate activation | uint8 restricted to 0..127, zero point 0 |
| Rescale multiplier | Unsigned 16-bit, 1..65535 |
| Rescale shift | Integer 0..47 |
| Rescale product and rounding add | Signed 64-bit, checked before arithmetic |
| Pool | Exact 2x2 maximum, stride 2 |
| Classifier output | Eight int32 logits, no output requantization |
| Argmax | First maximum wins ties |

## Derivation and exact rounding

For each layer, s_w = max(abs(float_weights))/127; quantized weights are
clip(rint(float_weights/s_w), -127, 127). Parameter rounding uses nearest,
ties to even. A zero-weight layer uses scale 1. Bias quantization uses
rint(float_bias/(input_scale*s_w)), with an int32 range check.

The activation scale s_a is the maximum float convolution ReLU activation
over **training images only**, divided by 127. An all-zero calibration uses
scale 1. No percentile or range is tuned on validation data.

Choose the largest shift S in 0..47 such that
M = round((s_x*s_conv_weight/s_a)*2^S) fits 1..65535.
For convolution accumulator A, define:

```text
P = max(0, A)
R = 0 if S == 0 else 2^(S-1)
activation = min(127, (P*M + R) >> S)
```

This rounds nonnegative values to nearest with halfway cases upward. ReLU
occurs before multiplication, so right shifting negative values is unnecessary.
The actual multiplier/shift, layer scales and conservative bounds appear in
the exported contract.json. FC uses activation scale s_a, so its score scale
is s_a*s_fc_weight. It is common to all eight logits, preserving argmax.

## Bounds and ordering

For each output channel, prove abs(bias) + max_input*sum(abs(weights)) fits
signed int32. This bounds every serial MAC partial sum, not only the final
result. Also prove positive_accumulator_bound*M+R fits signed int64. Runtime
checks reject accumulator overflow. No wrapping or saturation of accumulators
is permitted. Only post-rescale activations saturate.

Arrays use CHW and C flattening: channel first, last spatial coordinate changes
fastest. Pool index = (channel*7+row)*7+column. Convolution performs the standard
CNN cross-correlation (no kernel flipping). Weight arrays are OIHW for conv and
[output_class, input_index] for FC. Kernels traverse row then column.

## Run and inspect

From the repository root:

```powershell
python -m pytest reference_model/tests -q
python reference_model/quantize.py
```

Default checkpoint: build/reference_model/baseline_v1/size_16_seed_42/best.pt.
Default output: build/reference_model/integer_v1. Existing outputs are never
overwritten; use --output for a new experiment directory. Checkpoints must be
trusted local files. Prepared caches must correspond to the saved manifest.

Outputs include parameters.npz, contract.json, metrics.json, prediction CSV,
validation logits, memory-layout documentation, checksums, weight/bias .mem
files, and 20 real plus five synthetic per-layer vectors. Every vector is
compared against a separate Python serial MAC oracle. Exported .mem files are
checked by reading them back and recovering the exact integers.

Prepared input inference without PyTorch:

```powershell
python reference_model/golden.py build/reference_model/integer_v1 prepared_pixels.npy layers.npz
```

prepared_pixels.npy must contain a uint8 NCHW batch. Import infer and load_model
to call the same integer reference from a simulator integration script.

The official test set stays reserved. Float-versus-integer accuracy and changed
predictions measure quantization effects. A future RTL simulation must compare
every expected integer stage exactly. Scalar-oracle agreement establishes
software arithmetic consistency; it does not establish RTL or board agreement.
