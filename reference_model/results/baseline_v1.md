# Assessment on 1 November 2026

The 16x16 model is a viable leading float candidate for these eight classes. Across three seeds it averages 97.05% validation accuracy, versus 96.78% for 32x32. The small difference does not establish statistical superiority. All six runs meet the proposed overall and per-class targets on this single grouped split.

Keep 16x16 as the working candidate because the larger model did not provide a clear benefit in this experiment. Do not freeze hardware yet: inspect the speed-limit errors and measure integer quantization degradation first. Some runs still improved near epoch 40, so these are baseline results rather than fully optimized models.

The selected subset passed all image readability, dimensions and ROI checks: 13,890 images, split into 11,130 training images from 371 tracks and 2,760 validation images from 92 tracks. Other classes have not undergone these checks. The official test set was not opened.

Four automated checks passed for grouping, cropping, dimensions and cost calculations. Checkpoints, split manifest, raw metrics and plots are local in build/reference_model/baseline_v1/. They are ignored by Git. Reproduction instructions are in reference_model/README.md.

# Float CNN validation experiment

Training data: eight selected GTSRB classes. Official test data was not used.
Split: stratified by class at physical-sign track level; split seed 2026.
Preprocessing: inclusive ROI crop, Pillow grayscale, bilinear resize, divide by 255.
Training: Adam, class-weighted cross entropy, no augmentation or histogram equalization.
Each run selects its best validation-accuracy checkpoint. Results are exploratory validation estimates.
The 32x32 model has more classifier parameters, so this is not a pure resolution-only ablation.

| Size | Seed | Epoch | Train accuracy | Validation accuracy | Macro recall | Minimum class recall | Proposed gate |
|---|---|---|---|---|---|---|---|
| 16 | 42 | 39 | 98.31% | 97.50% | 97.70% | 92.89% | Pass |
| 16 | 43 | 36 | 97.92% | 97.32% | 97.60% | 92.00% | Pass |
| 16 | 44 | 39 | 97.16% | 96.34% | 96.60% | 93.11% | Pass |
| 32 | 42 | 29 | 98.52% | 96.74% | 97.06% | 92.67% | Pass |
| 32 | 43 | 39 | 98.72% | 96.38% | 96.72% | 91.78% | Pass |
| 32 | 44 | 39 | 98.50% | 97.21% | 97.37% | 95.78% | Pass |

## Per class validation recall

| Class | 16 seed 42 | 16 seed 43 | 16 seed 44 | 32 seed 42 | 32 seed 43 | 32 seed 44 |
|---|---|---|---|---|---|---|
| Speed limit 30 | 92.89% | 92.00% | 93.11% | 92.67% | 91.78% | 95.78% |
| Speed limit 50 | 99.33% | 99.56% | 95.78% | 97.33% | 97.56% | 96.22% |
| Priority road | 96.67% | 97.62% | 96.43% | 97.38% | 95.24% | 96.43% |
| Yield | 97.38% | 96.43% | 95.71% | 94.76% | 95.48% | 96.90% |
| Stop | 96.67% | 98.00% | 96.67% | 97.33% | 96.67% | 96.00% |
| No entry | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% |
| General caution | 99.17% | 97.92% | 95.83% | 97.50% | 97.50% | 98.33% |
| Keep right | 99.52% | 99.29% | 99.29% | 99.52% | 99.52% | 99.29% |

## Repeated seed summary

16x16: 3 runs, mean accuracy 97.05%, population SD across seeds 0.51%.
32x32: 3 runs, mean accuracy 96.78%, population SD across seeds 0.34%.

Working targets: at least 95% validation accuracy and 90% recall in every selected class. These are proposed project criteria, not lecturer requirements.
Seed variation does not measure uncertainty across new sign tracks. No integer accuracy or FPGA latency has been measured.
Before architecture freeze, review mistakes and quantization degradation. Keep the official test split reserved until decisions are frozen.
