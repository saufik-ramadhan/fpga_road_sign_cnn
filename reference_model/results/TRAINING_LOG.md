# Training log

Source experiment: baseline_v1. Records copied from actual saved run histories; no training was rerun.

An epoch is one pass over the training set. Each run saved the checkpoint with the highest validation accuracy, which can precede the final epoch.

| Model/run | Epochs run | Best checkpoint epoch | Validation accuracy | Run time (s) | Epoch history |
|---|---:|---:|---:|---:|---|
| size_16_seed_42 | 40 | 39 | 97.50% | 11.88 | [CSV](training_logs/baseline_v1/size_16_seed_42/history.csv) |
| size_16_seed_43 | 40 | 36 | 97.32% | 10.79 | [CSV](training_logs/baseline_v1/size_16_seed_43/history.csv) |
| size_16_seed_44 | 40 | 39 | 96.34% | 10.74 | [CSV](training_logs/baseline_v1/size_16_seed_44/history.csv) |
| size_32_seed_42 | 40 | 29 | 96.74% | 33.98 | [CSV](training_logs/baseline_v1/size_32_seed_42/history.csv) |
| size_32_seed_43 | 40 | 39 | 96.38% | 33.48 | [CSV](training_logs/baseline_v1/size_32_seed_43/history.csv) |
| size_32_seed_44 | 40 | 39 | 97.21% | 33.48 | [CSV](training_logs/baseline_v1/size_32_seed_44/history.csv) |

## Selected model supplied to RTL

The provisional p2-int-v1 integer package derives from **size_16_seed_42**, trained for **40 epochs**, using the best checkpoint at **epoch 39**.
Quantization used training-only calibration and **zero additional training epochs**. It did not train a second neural network or use quantization-aware training.
See the shared package contract.json for the selected checkpoint hash. All source checkpoint hashes are recorded in the summary CSV.

## What each per-epoch CSV contains

- epoch: completed training epoch number.
- train_online_accuracy: training predictions collected while optimizer updates were occurring; this is not a separate evaluation of the final checkpoint.
- validation_accuracy: accuracy after that epoch, with inference mode and no optimizer updates.
- validation_loss: unweighted validation cross entropy after that epoch.

Each run folder also contains the original config.json and metrics.json. The latter includes training-set evaluation and per-class validation recall for the selected checkpoint.

## Shared training settings

Adam, learning rate 0.001, batch size 128, maximum 40 epochs, patience 12 epochs without improved validation accuracy. All six runs reached epoch 40. Class-weighted training loss, no augmentation or histogram equalization. Same grouped sign-track split, split seed 2026, initialization seeds 42/43/44. See each config.json for exact environment and split identity.

Reported run time includes training plus selected-checkpoint evaluation; it excludes dataset decoding/preparation and is not FPGA inference latency.
The official test set was not used. Accuracy comparisons are validation results; selecting a best epoch uses validation information.

## Refresh the log

From repository root:

```powershell
python reference_model/export_training_log.py
```

Default source: build/reference_model/baseline_v1/. Default destination: reference_model/results/. The exported records are Git-visible; source checkpoints and caches remain ignored.
