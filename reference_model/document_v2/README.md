# Document based implementation v2

Implements the pictured plan's CNN/model preparation. Historical scripts remain
unchanged. This version adds histogram equalization, training-only augmentation,
the document-listed class order, checked int24 arithmetic and complete exports.

## Resolved choices

- Base: inclusive ROI crop; RGB to Pillow L; ImageOps.equalize; bilinear resize 16x16.
- Training only: rotate uniformly within +/-5 degrees, translate within +/-1
  pixel on each axis, brightness factor uniformly 0.9..1.1. Apply after base
  preprocessing with bilinear grid sampling, zero padding, align_corners=False.
- No flips. Augmentation never affects validation, golden/UART inputs or stored images.
- Map: 0 Stop (14), 1 Yield (13), 2 No entry (17), 3 Priority road (12),
  4 General caution (18), 5 Keep right (38), 6 Speed limit 30 (1), 7 Speed limit 50 (2).
- Preserve historical track assignments; relabel class indices only. Split seed 2026.
- Train: Adam lr 0.001, batch 128, training-derived class weights, 60-epoch cap,
  patience 12, initialization seeds 42/43/44, best validation checkpoint.
- Parameters: nearest rounding, ties to even. Bias/accumulators/scores logical
  signed 24-bit; overflow forbidden. Activation range 0..127, uint8 storage.
- Rescale: uint16 multiplier, shift 0..47, positive nearest rounding halfway
  upward, signed 48-bit product/rounding intermediate. Wide NumPy containers do
  not change the checked logical contract. Derive constants from each checkpoint.
- Protocol metadata follows the picture: request 259 bytes, reply 31 bytes,
  cycles unsigned 24-bit and eight signed 24-bit scores. No P5 code is changed here.

## Reproduction from repository root

```powershell
python -m pytest reference_model/tests -q
python reference_model/document_v2/train.py
python reference_model/document_v2/quantize.py --output build/reference_model/document_integer_v2_checked
python reference_model/document_v2/publish.py
```

Use fresh --output/--destination directories to repeat; existing runs/packages
are not overwritten. Training defaults to build/reference_model/document_v2.
Quantization picks the completed run with highest float validation accuracy
(ties resolve in sorted run order), or accepts --checkpoint explicitly. It
calibrates the activation range on training only and evaluates validation only.

The shared review package is models/p2-doc-int-v2. It contains .mem, .coe,
params.vh, golden vectors, a 16-image stored bank and labels, numerical metadata
and checksums. No inference timing is invented. Stored manifest predictions
and ground-truth labels are separate.

The old report.py/export_training_log.py/publish_parameters.py are v1 utilities;
their wording, parameter widths and selected-checkpoint assumptions do not apply
to this version. Use this folder's entry points and results/document_v2.md.

Official test evaluation, the pictured test-data gate, P1/P3/P4 contract review,
P5 protocol/UI integration and actual RTL/board validation remain pending.
Passing 95% on validation is preliminary evidence, not a final test result.

## PR review corrections

The golden reference checks the initial bias and every serial MAC partial sum
for both convolution and FC. An overflowing intermediate is rejected even when
later products would cancel it. Valid inputs at either exact signed-24 limit
remain accepted; the 25 published vectors keep identical stage outputs.

`params.vh` contains module-local constants without a global include guard.
Include it once inside each consuming module. Tests compile both the generated
and published header in two modules within one compilation. The review
correction regenerates this header and its checksum without changing weights,
biases, rescale constants, metrics or stored/vector images.
