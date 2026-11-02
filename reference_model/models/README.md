# Model package status

The user adopted the pictured project document as the main implementation
reference on 2 November 2026. See ../DOCUMENT_BASELINE.md.

| Package | Status |
|---|---|
| p2-int-v1 | Historical no-equalisation experiment with int32 accumulators/scores; retained for reproducibility, not the new document-compliant release target |
| p2-doc-int-v2 | Current document-based review candidate: equalization, augmentation, document-listed class order and checked int24 arithmetic; includes .coe/.mem, params.vh, golden vectors and stored-image bank |

Neither package represents a team-approved hardware release. Preserve both
versioned packages and checksums unchanged. Use p2-doc-int-v2 for current review;
its validation accuracy is 96.63% and speed-limit 30 recall is 85.56%.
Official testing, P5 integration and RTL/board checks remain pending.
