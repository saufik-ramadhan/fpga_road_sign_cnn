# Document based experiment v2

Completed on 2 November 2026. Implements the pictured document with explicit choices in document_v2/README.md. This is a review candidate, not team-approved RTL or final test evidence.

## Training log

| Run | Epochs run | Best epoch | Validation accuracy | Training accuracy (no augmentation at evaluation) |
|---|---:|---:|---:|---:|
| Seed 42 | 60 | 54 | 96.92% | 98.34% |
| Seed 43 | 60 | 54 | 96.81% | 98.22% |
| Seed 44 | 60 | 59 | 96.16% | 97.92% |

Per-epoch histories/configs/metrics: training_logs/document_v2/. Three seeds share the original physical-sign split: 11,130 training images and 2,760 validation images. Class indices changed to the document-listed order. All runs used equalization and training-only augmentation; see saved configs.

## Integer simulation

Selected float accuracy: 96.92%; int24 accuracy: 96.63%; decrease: 0.290 percentage points.
Prediction agreement: 99.53%; 13 changed predictions. Activation saturation count: 0 / 4,327,680.

| Class | Float recall | Integer recall |
|---|---:|---:|
| Stop | 98.00% | 98.00% |
| Yield | 99.52% | 99.52% |
| No entry | 98.10% | 98.57% |
| Priority road | 98.81% | 98.57% |
| General caution | 99.17% | 99.17% |
| Keep right | 98.81% | 98.81% |
| Speed limit 30 | 87.33% | 85.56% |
| Speed limit 50 | 98.44% | 98.44% |

## Interpretation and feedback

The document 95% overall threshold is met on validation. The official test gate is still pending. The old additional 90%-recall-per-class working criterion is not met: speed-limit 30 integer recall is 85.56%. This weakness must remain visible; the overall accuracy does not establish good performance on every class.
The new pipeline changes equalization, augmentation, class-row order and training budget, so differences from the historical 97.50% result cannot be attributed to equalization alone. Do not restore the old model as compliant or silently drop equalization.
Recommendation: review speed-limit confusion and the numerical/memory contract with the team. Keep the current candidate versioned. Any augmentation or optimizer improvement should be a new experiment on validation data before official-test evaluation; do not tune against the final test set.

## Arithmetic and exports

Contract p2-doc-int-v2: signed 24-bit biases/accumulators/scores, weights -127..127, uint8 pixels, activation 0..127 in uint8 storage, signed 48-bit rescale. M=43980, S=25.
Bounds: conv 167,442; FC 752,322; widened rescale 7,380,876,376.
Calibration uses only training images. Parameter rounding is nearest ties to even; positive activation rescaling rounds nearest with halfway upward. MAC overflow is forbidden.
25 vectors (20 real, five synthetic) matched the independent serial oracle at all stages. Eleven automated checks passed initially; additional published-export validation is in tests/test_document_v2.py.

Shared package: reference_model/models/p2-doc-int-v2/. Contains 156 .mem files, six .coe files, params.vh, numerical contract, parameters.npz, metrics, 25 vector folders, 16-image stored bank, labels, source manifest and checksums.
24-bit memory words have six hex digits in two's complement. The .npz container may use a wider NumPy dtype; checked logical widths remain 24-bit. Model parameters and source scripts are Git-visible, not committed/pushed by this work.

## Remaining work

P1/P3/P4 contract review; P5 31-byte protocol and UI migration; model/ROM integration; RTL numerical simulation; board tests; final official-test accuracy. params.vh compilation checks syntax/constants only and is not CNN RTL verification. No board cycles or 0.2 ms latency are claimed.
