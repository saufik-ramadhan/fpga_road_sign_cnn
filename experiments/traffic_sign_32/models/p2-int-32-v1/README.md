# Integer model p2-int-32-v1

Trained 32x32 GTSRB eight-class candidate for CNN Visual Lab.
Architecture: Conv 3x3, 8 filters, ReLU/rescale, MaxPool 2x2, FC.
FC: 1800 inputs per class; 14400 weights total.

Float validation: 97.2101%.
Integer validation: 97.3188%.
Scalar oracle: 25 full-network vectors.
Calibration uses training only; official test remains unused.
This is a separate experimental candidate, not a replacement for the 16x16 RTL release.
No RTL, timing, UART, or board validation is claimed.

Keep contract.json, parameters.npz, MEMORY_LAYOUT.md, metrics.json and mem/ together.
Weights: int8; biases and scores: int32; rescale intermediate: int64.
Memory: one hex word per line, two's complement, zero-based addresses.
Class order, rounding, scales and hashes are defined in the package.
Golden vectors remain local at build/reference_model/integer32_v1/vectors/.
