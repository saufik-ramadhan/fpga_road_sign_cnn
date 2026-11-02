# P2 finishing plan and hardware handoff

Status reviewed on 2 November 2026. This checklist distinguishes existing float
baseline work from the integer artifacts still needed for RTL verification.

## Scope

P2 owns laptop image preparation, offline model training, quantization, the
integer golden reference, parameter export and software comparison tools.
The RTL team owns the hardware implementation. Crop selection for new full-scene
photos requires supplied ROI coordinates or a manually selected sign region;
automatic traffic sign detection is outside the baseline.

## Deliverables

| Deliverable | Contents and acceptance evidence | Current status |
|---|---|---|
| Shared preprocessing | ROI crop, grayscale, fixed resize and byte layout; identical prepared pixels for training, golden inference and laptop transmission | Base function exists in data.py; standalone inference/export entry point pending |
| Trained float model | Architecture, class mapping, checkpoint, split manifest and experiment configuration | Seed 42 selected for the provisional integer experiment; final team release pending |
| Integer model parameters | Quantized weights and biases, activation scales, multiplier/shift parameters and width bounds | p2-int-v1 generated and simulated; see results/integer_v1.md |
| Integer golden model | Hardware-equivalent convolution, rescale/ReLU, pooling, FC and deterministic argmax; optional layer dumps | Implemented in golden.py; independent scalar oracle agrees on 25 vectors; RTL agreement pending |
| Hardware interface specification | Tensor shapes, CHW flatten order, address equations, signedness, arithmetic widths, rounding, saturation, file encoding and class order | INTEGER_CONTRACT.md plus generated contract.json and MEMORY_LAYOUT.md; team approval pending |
| Memory export tool | Reproducible .mem and/or .coe weights, biases, input images, labels, RTL parameter definitions and manifest/checksums | quantize.py generates .mem files, JSON parameters and checksums; final RTL include definitions pending |
| Verification vectors | Per-layer expected integers and final scores for diverse images plus directed arithmetic cases | 20 real and five synthetic full-network vectors exported; arithmetic boundary unit tests pass |
| Evaluation evidence | Float and integer validation comparison, confusion matrices, per-class recall and final held-out test results | Float and integer validation complete; final held-out test evaluation pending |
| RTL comparison utility | Compare simulator dumps with golden arrays, fail on mismatch, report first wrong layer/address/value | Pending; depends on agreed dump format |
| Board batch checker | Send prepared pixels and compare returned classes/scores; distinguish accuracy from golden agreement | Pending; UART integration depends on P5 protocol and hardware availability |
| Reproducible handoff | Setup/run instructions, model identity, source hashes, final parameter files and short limitations report | Baseline README exists; final release package pending |

## Recommended finishing sequence

Steps 1 through 3 and the provisional vector export in step 5 have now been
executed for p2-int-v1. The remaining gates are team review, any RTL integration
adjustments, a final release and held-out evaluation. The sequence below remains
the rationale and reproducible order; it is not a claim that all steps are pending.

1. Keep 16x16 with eight filters and the current eight classes as the working
   candidate. Review speed-limit errors and select a float checkpoint using
   validation only. Seed 42 is the highest-scoring current 16x16 candidate,
   not yet an integer-qualified release.
2. Draft the numeric and memory contract for RTL owners. Begin with signed
   8-bit weights, uint8 pixels and nonnegative integer activations. Determine
   bias units, accumulator and rescale-product widths from actual parameters
   and worst-case bounds. Do not promise a 24-bit accumulator before checking.
3. Implement quantization and a separate integer golden path. Calibrate
   activation ranges using training data only. Evaluate float-to-integer
   degradation on validation data. Keep test data reserved.
4. Review measured quantized results and agree the contract with the team before
   generating the final hardware handoff. Revisit scaling or training if needed.
5. Generate a versioned export package and module-level vectors. Include zero,
   maximum-valued and patterned inputs; directed rounding, saturation and tie
   cases; and representative real images. Verify files round-trip to the exact
   same parameter and image arrays.
6. Freeze the model and preprocessing, then evaluate the held-out test set.
   Report the selected eight-class task explicitly. Export RTL comparisons and
   later run board batches once those interfaces are available.

## Feedback and completion criteria

The float results support trying 16x16 first: mean validation accuracy is 97.05%
versus 96.78% for 32x32 across three seeds. This is one grouped split and does
not establish statistical superiority or quantized accuracy. The 32x32 model
also has more classifier weights, so this is a practical design comparison.

The proposed working quality targets remain at least 95% validation accuracy
and 90% recall per class. Quantization accuracy loss should be reported in
percentage points; its acceptable limit still needs agreement. An integer
model must meet the agreed quality criteria before deployment.

RTL verification requires exact intermediate and score agreement with the
integer golden reference on the agreed vector suite. Prediction agreement
alone can hide arithmetic errors. Hardware-versus-golden agreement and model
accuracy against dataset labels must appear as separate metrics.

Normalization by 255 is for float training. Integer FPGA input retains pixel
bytes, with scale accounted for in quantization. Histogram equalization is
not part of the trained baseline and must not be silently added at deployment.

Checkpoints currently live under ignored build/reference_model/baseline_v1/.
The final release must provide access to the chosen checkpoint and exports,
or a documented release artifact location, rather than relying on local build
files being present on a teammate's machine. Large datasets stay outside Git.

P2 can complete its software handoff before the board is available. End-to-end
RTL and board verification remains pending until the team can execute those
checks; it must not be reported as already passed.
