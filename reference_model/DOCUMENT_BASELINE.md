# Document based project baseline

Decision date: 2 November 2026. Status: document-based Python implementation,
retraining, int24 simulation and exports completed as a review candidate.
See document_v2/README.md and results/document_v2.md. Selected float validation
accuracy is 96.92%; integer accuracy is 96.63%. These are not final test results.
Speed-limit 30 integer recall is 85.56%. P5/RTL/board integration is pending.

The matrix and reset boundary below record the starting differences. The
implementation choices are now explicit in document_v2/README.md. The current
package is models/p2-doc-int-v2; final team interface approval is still pending.

## Reference authority

The user now adopts **Traffic_Sign_Recognition_Plan_in_Pictures.docx** as the
main implementation reference. This supersedes the earlier instruction to use
the teammate plan as context only. The lecturer's required deliverables still
apply. Subsequent explicit user decisions take precedence.

The versioned source copy is
[docs/references/Traffic_Sign_Recognition_Plan_in_Pictures.docx](../docs/references/Traffic_Sign_Recognition_Plan_in_Pictures.docx).
SHA256: `807689de946692b2718a564c66b325d581741e9d2ece305bd51155ac7f4b87ec`.

The pictured document calls itself a simplified version of the full project
plan. Consult the full plan for missing exact rules, but flag contradictions
rather than silently overriding the pictured document, particularly its updated
section 8 ownership split. Parameters not specified by either source remain
explicit implementation decisions to review before coding.

## Reset boundary

- Preserve existing code, checkpoints, logs, exported parameters and reports.
- Existing `baseline_v1` experiments and `p2-int-v1` are **historical baselines**,
  not the release target under this document decision.
- Their measured results remain valid for their own pipeline, which omitted
  equalisation and augmentation. The 97.50% accuracy does not transfer to a
  changed preprocessing/training pipeline.
- Existing top-level source scripts still implement that historical pipeline.
  New implementation lives separately in document_v2/ and preserves v1 behavior.
- Use a new experiment directory and new contract/model version for compliant
  training, numerical conversion, reports and hardware exports.
- Do not alter the sealed p2-int-v1 package: its checksums identify the historical
  snapshot. The new p2-doc-int-v2 package is a review candidate, not final release.
- Preserve unrelated working-tree changes. No destructive Git reset, deletion,
  branch switch, model overwrite or retraining is part of this planning reset.

## Target requirements and current differences

| Reference section | Target under the document | Current status / necessary migration |
|---|---|---|
| 1 System | Laptop prepares/checks; FPGA recognizes; display shows result | Retain this boundary; Python golden inference supplies verification only |
| 2 CNN | 16x16 grayscale, Conv 3x3 with eight filters, ReLU/rescale, 2x2 pool, FC 392 to 8, argmax | Architecture already matches; preserve it unless the documented accuracy gate requires fallback |
| 3 Preprocessing | Crop ROI, grayscale, histogram equalisation, resize 16x16; one shared function | Add equalisation before resizing and retrain; historical P2 and P5 preprocessing are not compliant |
| 3 Training | Small shifts, rotations and brightness changes during training only | Define ranges/order/seed explicitly and add augmentation; no random transforms during evaluation or transmission |
| 4 Model files | Offline training, integer golden reference, .coe/.mem and params.vh | Reuse framework; produce new parameters and complete the documented exports |
| 5 Accuracy gate | At least 95%: retain 16x16; 90..95%: class replacement and retest; below 90%: 32x32 fallback | Re-measure the new 8-bit candidate; historical results do not complete this gate |
| 6 Number formats | uint8 pixels, int8 weights -127..127, signed 24-bit running sums and scores, activations 0..127 | Revise int32 bias/accumulator/score/export contract; verify biases and every partial sum fit int24 |
| 6 Rescale | Multiply by M, add rounding, shift S, clamp 0..127 | Derive M/S from the new checkpoint; use a sufficiently wide intermediate, not a 24-bit rescale product |
| 7 Stored mode | 16 images inside FPGA, switches select, BTNC starts CNN, board displays result | Export exact stored-image bank and labels; UI answer-key viewing is only a reference function |
| 7 Live mode | Laptop sends prepared image; board returns class, cycles and eight scores | Integrate shared preprocessing and golden comparison with P5 transport |
| 8 Ownership | P2 software/model; P5 input/comms; P3 conv/requant; P4 pool/FC/display; P1 integration | Follow this split rather than older role assignments |
| 9 UART | 115200 baud; one request at a time; 259-byte classify request; 31-byte reply with 3-byte cycles and eight signed 3-byte scores | P5 currently replies with 32 bytes/four-byte cycles; migration must update both endpoints and regressions |
| 10 Speed | Approximately 0.2ms CNN and about 40 live images/sec | Targets/estimates until actual cycle, link and board measurements exist |
| 11 Verification | Layer tests, 20-image CNN simulation, UART/full-top simulation, then 16 stored and 500 live board checks | Regenerate vectors after migration; require exact integer score/layer match, not only class match |
| 12..14 Gates and hand-in | Evidence-based milestones, fallback simulation, RTL/memory/build artifacts, reports, slides and logs | Keep measured completion separate from planned dates and targets |

## Numerical details requiring explicit resolution

The picture specifies accumulator and score width, not every bias or multiplier
detail. The previously supplied full-plan text describes signed 24-bit biases;
verify that detail against the team copy before freezing the new parameter ABI.
Store 0..127 activations in seven logical bits; eight-bit memory words may carry
the same values if their top bit is zero. This is storage padding, not a changed
activation range.

Choose and document multiplier width, shift range, rounding at halfway cases,
signed shift semantics, widened product width, bias-first MAC order, CHW order,
and overflow failure behavior. Reuse existing implementation choices only when
they are consistent with the reference. Derive bounds from the **new** weights
and biases before promising safe int24 arithmetic. Do not reuse old M=34172,
S=25 or old bounds as constants for a retrained model.

## Class index proposal

The picture lists sign names/display codes but does not explicitly number
classes. Proposed numbering follows its listed order. This is a proposal to
confirm with P1/P5/P4, not an already frozen mapping:

| Proposed index | GTSRB ID | Meaning | Display code |
|---|---|---|---|
| 0 | 14 | Stop | StOP |
| 1 | 13 | Yield | yLd |
| 2 | 17 | No entry | no E |
| 3 | 12 | Priority road | PrIo |
| 4 | 18 | General caution | CAUt |
| 5 | 38 | Keep right | rIGt |
| 6 | 1 | Speed limit 30 | 30 |
| 7 | 2 | Speed limit 50 | 50 |

This differs from the historical model order. Label encoding, FC output rows,
biases, all golden scores, UART names, display codes and stored labels must use
the same agreed order. Do not relabel old scores without the matching parameter
and metadata permutation. New training should encode the agreed map directly.

## Recommended new implementation sequence

1. Review this compliance matrix and confirm unresolved details: exact
   equalisation implementation, interpolation, augmentation ranges/order, class
   numbering, 24-bit bias format and rounding/intermediate-width rules.
2. Implement and test one deterministic base preprocessing function. Add a
   separate training-only augmentation path. Use the same prepared uint8 bytes
   for previews, golden inference, memory files and UART payloads.
3. Train a new 16x16 float baseline with track-grouped splits and saved seeds,
   configuration, epochs and selected checkpoints. Calibrate quantization on
   training only. Keep the official test set reserved during tuning.
4. Implement a new int24 golden contract, prove partial-sum/product bounds,
   compare float/integer validation accuracy and independent integer oracles.
   Apply the documented accuracy gate with clearly named evaluation splits;
   final official-test evidence remains separate from tuning results.
5. Export a versioned .mem/.coe/params.vh package, model identity and checksums,
   per-layer real/edge vectors, plus a shared bank of 16 stored images and labels.
6. Integrate the P5 UI/transport after its pixel preparation, class names and
   31-byte reply are aligned. Require real-image and score comparisons; keep
   placeholder/demo data clearly labeled. Preserve hardware-owned stored mode.
7. Run module/full-CNN/full-UART simulation, then board bring-up and fixed-batch
   tests. Publish actual accuracy, exact-match rates, latency and resource use.

## Feedback before implementation

The architecture does not need a wholesale rewrite. The high-risk changes are
the image distribution from equalisation, numerical/file widths, class order
and the P5 protocol. Change them in a new version and test each boundary.
Adding equalisation only in the UI would make input disagree with training.
Narrowing only .mem words would leave the arithmetic contract inconsistent.

The document's early gate says unseen test photos; repeated tuning on the final
test set would make its estimate optimistic. Record a separate tuning/validation
role and a frozen-model official-test measurement. Report measured outcomes
honestly even when a planned gate or latency target has not been achieved.

User preference remains: evaluate plans and provide feedback before each new
implementation stage. The approved Python stage has now run; its evidence is
in results/document_v2.md. This does not imply the P5/RTL integration has run.
