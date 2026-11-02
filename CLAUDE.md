# Project context

Read [README.md](README.md) for navigation and
[docs/README.md](docs/README.md) for project state, commit policy and source authority.
Detailed category guides:

- [Hardware](docs/HARDWARE.md): RTL ports, P3 arithmetic and P5 protocol.
- [Reference model](reference_model/README.md): document-v2, legacy v1 and exports.
- [Experiment evidence](reference_model/results/README.md): measured results and logs.
- [Testbenches](tests/README.md): `tests/rtl/p3/`, `tests/rtl/p5/`, unified runner.
- [Laptop applications](apps/README.md) and [software experiments](experiments/README.md).

## Working rules

- Preserve user changes and sealed model packages/checksums. Keep generated
  data, training/simulation/Vivado output and caches under ignored `build/`.
- Use a task branch and PR; do not push directly to main or force-push.
- RTL uses Verilog-2001 and one-cycle memory reads. P3 reset is synchronous
  active-high; P5 retains power-up initialized state without reset ports.
  Engines accept one-cycle start and emit one-cycle done with busy.
- Model baseline is p2-doc-int-v2: 16×16 grayscale, 8 filters/classes,
  signed24 accumulators/scores, activation 0..127, M=43980/S=25 for this version.
  Read actual constants/contracts when changing a model.
- Header localparams are included once per consuming module, without a global guard.
- Current P5 transport has 32-byte replies/four-byte cycles; P2 metadata targets
  31 bytes/three-byte cycles. Align both endpoints before end-to-end claims.
- Require passing relevant tests and distinguish golden equivalence, model
  accuracy and physical hardware verification. Current board evidence covers conv/ReLU only.
- Compile production RTL from rtl/files.f (Vivado: rtl/read_sources.tcl).
  Use feature_extraction and comm_top as integration boundaries.
- Keep category guides current rather than adding per-session Markdown files.
