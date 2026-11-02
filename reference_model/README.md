# Traffic sign float training baseline

This experiment compares 16x16 and 32x32 grayscale input for a small CNN before
quantization or RTL implementation. It uses **Train.csv only**. The official
test split remains reserved. Python 3.11 with CPU PyTorch is sufficient.

Measured baseline results and feedback: [baseline_v1.md](results/baseline_v1.md).
Remaining scope and finishing checklist: [DELIVERABLES.md](DELIVERABLES.md).
Integer simulation and exact arithmetic: [INTEGER_CONTRACT.md](INTEGER_CONTRACT.md).
Measured float versus integer results: [integer_v1.md](results/integer_v1.md).

## Scope and architecture

Eight selected GTSRB IDs: 1 (30), 2 (50), 12 (priority road), 13 (yield), 14 (stop),
17 (no entry), 18 (general caution), 38 (keep right). Hardware indices are 0..7
in this order. This selection is an experiment, not a frozen hardware interface.

`input -> Conv2d(1,8,3) -> ReLU -> MaxPool2d(2) -> flatten(CHW) -> Linear(...,8)`

The 16x16 version has 3,208 weights plus 16 biases and 17,248 MACs. The 32x32
version has 14,472 weights plus 16 biases and 79,200 MACs. These are arithmetic
counts, not measured latency. The larger fully connected layer is a confound:
this experiment compares practical designs, not resolution alone.

## Data and preprocessing

Default data location: `Tubes/dataset`, beside this repository. Crop the CSV ROI
with inclusive maximum coordinates, convert RGB to Pillow grayscale, bilinear
resize to the target size, and normalize uint8 pixels by 255 for float training.
Every selected image is decoded and checked against CSV dimensions and ROI.
The original dataset is read-only. Training currently uses no augmentation or
histogram equalization so the first comparison has fewer variables.

All frames from one physical sign track stay in one split. The filename encodes
class/track/frame; the key includes class because track numbers repeat across
classes. An approximately 80/20 split is stratified over track groups, with seed
2026. The generated manifest defines the actual split. It cannot be silently
replaced with a different split in the same output directory.

## Run from the repository root

```powershell
python -m pip install -r reference_model/requirements.txt
python -m pytest reference_model/tests -q
python reference_model/train.py --sizes 16 32 --seeds 42 43 44 --epochs 40
```

The default output is `build/reference_model/baseline_v1`, ignored by Git.
Use `--output build/reference_model/another_experiment` for a new run. Existing
run folders are not overwritten. For a short pipeline check, use a new output
folder, one seed and `--epochs 2`; this does not establish model quality.

Training uses Adam (lr 0.001), training-only inverse-frequency class weights,
batch size 128, four CPU threads, and early stopping after 12 epochs without
improved validation accuracy. Each run reloads the best validation checkpoint.
The configuration records installed library versions and the split checksum.

## Outputs and interpretation

- `split_manifest.json`: sample paths, tracks, split labels and class mapping.
- `data_audit.json`: decoding checks, counts and selected-source checksum.
- `pixels_16.npz`, `pixels_32.npz`: prepared uint8 images before normalization.
- `size_*_seed_*/best.pt`: float weights, configuration and selected epoch.
- `metrics.json`: best-checkpoint training/validation metrics and per-class recall.
- `history.csv`, `learning_curves.png`, `confusion_matrix.png`,
  `validation_predictions.csv`, `validation_mistakes.png`: evaluation evidence.
- `SUMMARY.md`, `summary.json`: comparison across completed runs.

Rebuild plots and summary for completed runs, even during a longer experiment:

```powershell
python reference_model/report.py build/reference_model/baseline_v1
```

Working targets are 95% validation accuracy and 90% recall per class. They are
proposed project targets, not lecturer requirements. Three seeds measure
optimization variability on a single split, not uncertainty over new tracks.
Review mistakes and float-to-integer degradation before freezing the design.
Load only trusted checkpoints: these files are ordinary PyTorch checkpoints.
