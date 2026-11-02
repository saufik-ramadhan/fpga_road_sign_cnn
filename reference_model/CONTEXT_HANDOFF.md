# P2 context handoff

Updated: 2 November 2026. Compact record for continuing this project.

## Latest decision superseding historical sections below

The user has reset the planning baseline: Traffic_Sign_Recognition_Plan_in_Pictures.docx
is now the main implementation reference. Read DOCUMENT_BASELINE.md first.
Existing baseline_v1/p2-int-v1 code, weights and measurements remain historical.
The approved Python migration is now implemented in document_v2/: Pillow
equalisation before bilinear resizing, training-only +/-5 degree rotation,
+/-1 pixel shifts and brightness 0.9..1.1, applied after base preprocessing.
The class order is Stop, Yield, No entry, Priority road, General caution,
Keep right, 30, 50. It preserves old physical-sign split assignments.
Three seeds ran 60 epochs; best epochs 54/54/59, accuracies 96.92/96.81/96.16%.
Selected seed 42 quantizes to logical signed int24 with 96.63% validation accuracy
(0.290 percentage-point drop); speed-limit 30 recall is 85.56%, an unresolved
weakness. M=43980, S=25, signed 48-bit rescale intermediates. No v1 constants apply.
Thirteen checks passed, including memory/COE integrity and Verilog-header syntax.
Independent scalar and vectorized integers match 25 complete vectors.
Review package: models/p2-doc-int-v2 (Git-visible .mem/.coe, params.vh, vectors,
16-image bank/labels/manifest and hashes). New results/logs: results/document_v2.md
and results/training_logs/document_v2/. Data/run caches: build/reference_model/document_v2;
final checked integer outputs: build/reference_model/document_integer_v2_checked.
The earlier build/reference_model/document_integer_v2 is a preliminary export
with a legacy per-class gate field; use the checked output/package instead.
P5 31-byte reply metadata is declared but its source/UI is not migrated here.
Official test evaluation and real CNN RTL/board verification remain pending.
Preserve historical artifacts and user edits; review the next integration plan.
The rest of this handoff records historical v1 behavior unless stated otherwise.

## User and scope

- User owns P2, the model and laptop software, in a Korean engineering course Basys3 FPGA team project.
- Work directory: `C:/Users/rubin/Documents/Kullyeah/Korea/FPGA/Tubes/fpga_road_sign_cnn/reference_model/`.
- Repository root is its parent. Dataset: `C:/Users/rubin/Documents/Kullyeah/Korea/FPGA/Tubes/dataset/`.
- P2 owns preprocessing, offline training, quantization, the integer golden model, parameter/memory exports, verification vectors and software comparison tools.
- Other teammates implement RTL and board I/O. Our CNN classifies an already selected sign crop; automatic sign detection is outside the baseline.
- The lecturer guide defines required deliverables. The pictured teammate plan is now the main implementation reference; this supersedes the original context-only decision. Timing estimates still require measurement.
- **User preference: review plans first, evaluate weaknesses/trade-offs, and give feedback before implementation.** Execute after approval. Do not silently expand scope or freeze interfaces.
- Korean signs were preferred, not required. AI Hub was investigated but access/label suitability remained unresolved. User selected Kaggle GTSRB instead.
- User appreciates explanations of terminology and presenter-friendly language, plus real dataset examples in documents.

## Dataset and preprocessing

Source: https://www.kaggle.com/datasets/meowmeowmeowmeowmeow/gtsrb-german-traffic-sign/data

- Full inventory: 39,209 Train images, 12,630 Test images, 43 Meta images/classes. All CSV paths exist; no duplicate CSV paths or unlisted images were found.
- `Test/GT-final_test.csv` is empty. Main `Test.csv` contains labels. **Official Test images and labels remain unused by model experiments.**
- Eight-class order, also the provisional hardware indices:

| Index | GTSRB ID | Meaning |
|---|---|---|
| 0 | 1 | Speed limit 30 |
| 1 | 2 | Speed limit 50 |
| 2 | 12 | Priority road |
| 3 | 13 | Yield |
| 4 | 14 | Stop |
| 5 | 17 | No entry |
| 6 | 18 | General caution |
| 7 | 38 | Keep right |

- Selected 13,890 images passed decoding, CSV dimensions and ROI checks. This full decoding claim applies only to the selected classes.
- Split seed 2026; approximately 80/20 **physical-sign track groups per class**, not random individual frames. Filename contains class/track/frame; group key includes class.
- Actual split: 11,130 training images / 371 tracks; 2,760 validation images / 92 tracks. No shared tracks.
- Base preprocessing: inclusive CSV ROI (Pillow crop uses x2+1/y2+1), RGB to Pillow grayscale, bilinear resize, uint8 pixels. Float model gets pixels/255.
- No augmentation, histogram equalization or mean/std normalization in the actual trained baseline. Do not introduce these at deployment without a new experiment.

## Architecture and float experiment

`16x16 grayscale -> Conv2d(1,8,3,bias), no padding -> ReLU -> MaxPool2d(2) -> CHW flatten -> Linear(392,8,bias) -> argmax`

- Shapes: 1x16x16, 8x14x14, 8x7x7, 392, eight logits.
- 3,208 weights + 16 biases; 17,248 MACs/image. These counts are not measured latency.
- 32x32 comparison: 1,800 pooled features, 14,472 weights + 16 biases, 79,200 MACs.
- Training: CPU PyTorch 2.0.1, Adam lr 0.001, batch 128, inverse-frequency class-weighted loss from training labels, max 40 epochs, patience 12, best validation accuracy checkpoint, deterministic seeds 42/43/44.

| Input | Seed 42 | Seed 43 | Seed 44 | Mean validation accuracy |
|---|---|---|---|---|
| 16x16 | 97.50% | 97.32% | 96.34% | 97.05% |
| 32x32 | 96.74% | 96.38% | 97.21% | 96.78% |

All six runs passed proposed 95% accuracy / 90% recall-per-class targets. These targets are team proposals, not lecturer requirements. Keep 16x16 as the working candidate: larger design showed no clear benefit. One split and three seeds do not prove statistical superiority. Larger input also enlarges FC capacity. Some runs still improved near epoch 40.

Selected float checkpoint: `build/reference_model/baseline_v1/size_16_seed_42/best.pt`, epoch 39. Selection uses validation only.

## Integer contract and simulation

Two executable representations of the **same trained network**, not two independently trained models:

- Float PyTorch model for training/baseline.
- Integer-only NumPy golden model for exact future RTL comparisons.

Contract `p2-int-v1`:

- Input uint8 0..255, scale 1/255, zero point 0.
- Weights int8 -127..127, symmetric scale per layer.
- Biases int32, in layer accumulator units. Parameter rounding: nearest, ties to even.
- Conv/FC accumulators int32, bias first then serial products. Overflow forbidden, checked by conservative bounds.
- Activation uint8 restricted to 0..127. Calibration: full float convolution ReLU maximum over **training only** (7.78406143), activation scale 0.0612918223.
- Rescale: `min(127, (max(0,A)*34172 + 16777216) >> 25)`. Multiplier unsigned 16-bit, shift 25, int64 intermediate. Nearest rounding, halfway upward after ReLU.
- Exact 2x2 max-pool; CHW flatten index `(channel*7+row)*7+column`.
- Eight int32 scores, no output rescale, shared real scale 0.000798104393. First argmax wins ties.
- Bound magnitudes: conv 181,902; FC 610,764; rescale including rounding 6,232,732,360. Int64 is conservative; 34 signed bits cover the proven rescale bound for these fixed parameters, but narrowing requires a reviewed contract revision.

Measured on 2,760 validation images:

- Float accuracy 97.50%; integer accuracy 97.50%; drop 0.00 percentage points.
- 9 changed predictions; 99.67% prediction agreement. Equal accuracy does not imply identical predictions/logits.
- Lowest integer class recall: speed limit 30, 93.56% (float 92.89%).
- Zero activation clipping above 127 among 4,327,680 values.
- Eight automated tests passed (four baseline plus four integer cases).
- 25 full-network vectors match an independent Python serial integer MAC oracle at every stage: 20 real validation images and zeros/maximum/checkerboard/ramp/impulse.
- Exported memory words round-trip exactly.
- **This is Python numerical simulation. No RTL simulator, synthesis, timing or board verification has run.**

## Files and commands

All paths below are relative to the repository root unless prefixed otherwise.

| Source under reference_model/ | Role |
|---|---|
| data.py | Shared preprocessing, grouped split, selected-image audit/cache |
| model.py | Float CNN and arithmetic cost calculations |
| train.py | Six-run float experiment/checkpoints |
| report.py | Metrics aggregation, learning curves, confusion/mistake plots |
| quantize.py | Calibration, conversion, validation comparison, vectors and .mem export |
| golden.py | Integer inference, serial oracle, prepared-input CLI |
| tests/ | Eight test cases across baseline and integer modules |
| INTEGER_CONTRACT.md | Exact arithmetic and memory conventions |
| DELIVERABLES.md | Scope/status/finishing checklist |
| results/baseline_v1.md, results/integer_v1.md | Measured results and feedback |
| README.md, requirements.txt | Setup and reproduction |

```powershell
# Run from repository root
python -m pytest reference_model/tests -q
python reference_model/train.py --sizes 16 32 --seeds 42 43 44 --epochs 40
python reference_model/report.py build/reference_model/baseline_v1
python reference_model/quantize.py
python reference_model/golden.py build/reference_model/integer_v1 prepared_pixels.npy layers.npz
```

- Runs refuse to overwrite existing output folders; choose a fresh `--output` directory when repeating training/quantization. Checkpoints must be trusted local files.
- Float artifacts: `build/reference_model/baseline_v1/` (split manifest, audit, pixel caches, six run folders, summary and plots).
- Integer artifacts: `build/reference_model/integer_v1/` (parameters.npz, contract.json, metrics.json, validation_outputs.npz, predictions.csv, split_manifest.json, checksums.json, MEMORY_LAYOUT.md, mem/, vectors/).
- 154 .mem files: four parameter files plus six stages for each of 25 vectors. One hex word per line, two's complement for signed values, arrays flattened C order. Conv OIHW, FC [output,input]. No UART byte-order contract yet.
- Build outputs are **ignored by Git**. Teammates will not receive them through source commits alone. Final packaging is pending.
- Repo has modified/untracked source/docs; no commits/pushes were made by this work. Git requires per-command `-c safe.directory=C:/Users/rubin/Documents/Kullyeah/Korea/FPGA/Tubes/fpga_road_sign_cnn` in this environment due ownership.

## Documents already created

Under `reference_model/docs/`:

- `P2_Model_and_Software_Approach.docx` — 8-page planning report, including labeled dataset gallery and RGB/16x16/32x32 comparisons.
- `P2_Model_and_Software_Approach.pptx` — 14-slide planning deck with those examples.
- `P2_Implementation_and_Verification_Report.docx` — 7-page completed-work report dated 2 November 2026, covering training, quantization, verification, artifact inventory and remaining work.
- `assets/` — original examples, illustrative transforms and examples_manifest.json.

Planning docs predate training; do not mistake their pending status for current results. The implementation report and measured JSON files capture current evidence. Documents were rendered and visually checked using installed Word PDF export because LibreOffice was unavailable. Builders/previews live under ignored `build/approach/`.

## Remaining work and suggested next plan

1. Review numeric contract and memory layout with RTL owners; agree any width changes before claiming a frozen interface.
2. Create a standalone laptop preprocessing/export entry point (base function exists) and final RTL parameter include definitions.
3. Connect exported vectors to RTL testbenches and build a first-mismatch dump comparator. Require exact layer/score equality, not just class agreement.
4. Package a versioned handoff containing checkpoint identity, integer parameters, layouts, vectors, scripts and checksums in a shared location.
5. Freeze model/preprocessing and then evaluate the held-out test set. Keep validation results labeled as validation until then.
6. UART batch checker depends on P5 protocol. Board matching, latency, timing closure and utilization require the team hardware flow.

Do not claim integer-to-RTL agreement, final test accuracy, Korean sign generalization, board performance or project completion from current software evidence. Review this proposed next plan with the user before starting another implementation stage.
