# Integer simulation assessment on 2 November 2026

The provisional p2-int-v1 contract passes the proposed quality gates on the
existing validation split. It quantizes the 16x16 seed 42 float checkpoint
without retraining. Calibration uses 11,130 training images only; evaluation
uses 2,760 validation images. The official test set remains untouched.

| Metric | Result |
|---|---|
| Float accuracy | 97.50% |
| Integer accuracy | 97.50% |
| Accuracy drop | 0.00 percentage points |
| Prediction agreement | 99.67% |
| Changed predictions | 9 / 2,760 |
| Integer minimum class recall | 93.56% |
| Validation activation clipping above 127 | 0 / 4,327,680 values |
| Independent scalar oracle | 25 / 25 vectors matched at every stage |

## Per class validation recall

| Class | Float | Integer |
|---|---|---|
| Speed limit 30 | 92.89% | 93.56% |
| Speed limit 50 | 99.33% | 99.11% |
| Priority road | 96.67% | 96.67% |
| Yield | 97.38% | 97.14% |
| Stop | 96.67% | 96.67% |
| No entry | 100.00% | 100.00% |
| General caution | 99.17% | 99.17% |
| Keep right | 99.52% | 99.29% |

## Contract and feedback

Weights are symmetric signed 8-bit with one scale per layer. Inputs are uint8,
activations are restricted to 0..127, MAC accumulators and scores are int32,
and rescale intermediates are int64. Overflow is forbidden. Parameter rounding
uses nearest ties to even; positive activation rescaling rounds nearest with
halfway upward. Actual rescale multiplier M = 34,172 and shift S = 25.

Conservative absolute partial-sum bounds are 181,902 for convolution and
610,764 for the classifier. The rescale bound including rounding is
6,232,732,360. These bounds cover any valid input bytes and any allowed pooled
activations for these fixed parameters, rather than only observed images.

Recommendation: review this contract with the RTL owners. The int64 rescale is
deliberately conservative. These fixed weights require only 34 signed bits to
represent the proven nonnegative rescale bound, but narrowing the contract
requires a corresponding specification revision and verification. Retain the
documented widths until the team agrees a change.

Identical total accuracy does not mean identical predictions or logits. Nine
predictions changed. The remaining speed-limit confusion persists, so
quantization has not solved recognition errors. Float and integer scores are
not expected to match exactly; dequantized logit mean absolute error is 0.18536.

Eight automated tests pass for grouping, cropping, layer dimensions, cost
calculations and integer arithmetic. The arithmetic cases cover halfway
rounding, ReLU, clipping, zero shift, signed overflow rejection, CHW pooling/FC
ordering, ties and hexadecimal encoding. The vectorized golden model also
matches an independently looped Python integer MAC oracle on 20 real images
and five synthetic inputs. Exported memory words round-trip exactly.

These are validation results from one selected checkpoint on one grouped split,
not independent final test results or a guarantee of deployment performance.

## Reproduction and artifacts

See [the contract](../INTEGER_CONTRACT.md). From the repository root:

```powershell
python -m pytest reference_model/tests -q
python reference_model/quantize.py
```

Use a fresh --output directory to repeat without overwriting an existing run.
Checkpoints must be trusted local files.

Local output directory: build/reference_model/integer_v1/. It contains
contract.json, parameters.npz, metrics.json, validation_outputs.npz,
predictions.csv, MEMORY_LAYOUT.md, checksums.json, mem/ and vectors/. There are
154 .mem files: four parameter files and six files for each of 25 vectors.
All arrays have explicit layouts and word widths. A preserved split manifest
and hashes identify the source model and sample ordering.

The .mem files can feed readmemh subject to RTL interface agreement. They are
local build outputs, ignored by Git, and still need packaging for team delivery.

RTL simulation, board tests, UART integration, a final team-approved release,
and held-out test evaluation remain pending. Scalar oracle tests are software
arithmetic simulation, not RTL simulation.
