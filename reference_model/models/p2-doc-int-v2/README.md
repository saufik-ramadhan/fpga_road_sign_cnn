# p2-doc-int-v2 review package

Document-based 16x16 eight-class candidate. This package supersedes p2-int-v1
as the current review candidate, not a team-approved hardware release.

- Preprocessing: crop ROI, grayscale, Pillow histogram equalization, bilinear resize.
- Class indices: Stop, Yield, No entry, Priority road, General caution, Keep right, 30, 50.
- Signed weights: int8; biases, MAC accumulators and scores: logical int24.
- Activation: 0..127 in uint8 storage. Rescale intermediate: signed 48-bit.
- Actual multiplier and shift are in contract.json and params.vh. Never reuse v1 constants.
- Float validation accuracy 96.92%; integer 96.63%. Speed-limit 30 integer recall 85.56%.
- 95% overall threshold met on validation; official test and hardware results are pending.

mem/: weight and bias files for readmemh, plus matching .coe files.
params.vh: include inside the consuming module; contains dimensions, rescale and biases.
vectors/: 20 real and five synthetic input/layer-output packages with a source manifest.
signs.mem / signs.coe: 16 stored pictures, 256 bytes each, stored_index*256+pixel_address.
labels.mem / labels.coe: 16 ground-truth class indices, not golden predictions.
stored_manifest.json: picture indices, source IDs, labels, predictions and golden scores.
Synthetic vectors have no semantic label. Golden scores and labels are distinct.

All .mem files contain one hexadecimal word per line. Signed int24 uses six hex
digits in two's complement. Activations/pixels use two digits. C/CHW flattening
and memory addresses are described in MEMORY_LAYOUT.md and contract.json.
Parameters.npz uses wider NumPy containers for logical int24 data.

checksums.json covers this package except itself. The local .gitattributes
preserves exact bytes across checkouts. No real FPGA cycle counts are provided.
The 31-byte reply metadata is a protocol target: P5 has not been migrated here.
No RTL/board test is claimed. Python scalar/vectorized arithmetic matched 25 vectors.
