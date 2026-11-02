# Document status

## Current references

- ../../docs/references/Traffic_Sign_Recognition_Plan_in_Pictures.docx: main user-adopted reference.
- ../DOCUMENT_BASELINE.md: reference requirements and migration history.
- ../document_v2/README.md: actual resolved preprocessing, augmentation and numerical choices.
- ../results/document_v2.md: measured new results and per-epoch log links.
- ../models/p2-doc-int-v2/: current shared review package and exact contract.

## Historical artifacts

P2_Model_and_Software_Approach.docx, its .pptx, the
P2_Implementation_and_Verification_Report.docx, P2_to_RTL_Handoff.docx and
CNN_System_Diagram.md describe the earlier p2-int-v1 experiment. Keep them as
records; do not use their no-equalization preprocessing, old class order,
int32 widths, M=34172 or 97.50% result for the new candidate.

New candidate: histogram equalization, document-listed class order, int24 MACs,
48-bit rescale, M=43980, S=25, 96.63% integer validation accuracy. It is not a
team-approved hardware release and has not been tested on the board.
