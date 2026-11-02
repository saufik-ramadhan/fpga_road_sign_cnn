# Shared project instructions

## Start every task

- Read README.md, docs/README.md and docs/GITHUB_WORKFLOW.md, then the category
  guide for the files being changed. Report branch, HEAD, working-tree changes,
  task scope and relevant tests before editing. Do not assume another chat's
  memory or a status claim from a different commit applies to this checkout.
- Use one task branch/worktree per task. Default branch prefix: codex/.
  Preserve user changes; do not switch another active workspace's branch.
- Use docs/GITHUB_WORKFLOW.md for ownership, setup, interface changes and PRs.
  Stay within the task's agreed scope. Shared boundaries include rtl/files.f,
  top/core, model contracts and UART. Include affected consumers/tests/docs when
  the task changes a boundary; identify dependencies on unmerged PRs explicitly.

## Sources of context

- Hardware interfaces, reset, timing, arithmetic and board wiring: docs/HARDWARE.md.
- Model/export/preprocessing contract: reference_model/README.md and the selected
  package's contract.json, params.vh, MEMORY_LAYOUT.md and checksums.json.
- Test commands and evidence scope: tests/README.md.
- Laptop apps: apps/README.md. Software experiments: experiments/README.md.
- Measured model results: reference_model/results/README.md.
- If docs and implementation disagree, inspect the code, contract and a
  reproducing test; report the discrepancy and update the relevant guide.
  Never silently change a numeric/protocol contract to make a test pass.

## Invariants

- Baseline board model: p2-doc-int-v2, 16x16 grayscale, 8 filters/classes,
  signed24 accumulators/scores, activations 0..127, M=43980/S=25. Read actual
  package constants before changing a model. Keep sealed packages/checksums
  intact; publish an intentionally changed model as a new version.
- RTL is Verilog-2001. P3/P4/control reset is synchronous active-high; P5 retains
  FPGA power-up initialization without reset ports. Memory reads take one clock.
  Engines accept a one-cycle start while idle and pulse done when complete.
- Use rtl/files.f for production sources, rtl/read_sources.tcl for Vivado.
  Keep testbenches/dummy modules in tests/rtl/. Add new production files to the
  manifest. Integration boundaries: feature_extraction, classifier, comm_top;
  cnn_core/top_basys3 assemble them. Do not insert unnoticed memory latency.
- FC flatten is CHW; scores[k] uses scores[24*k +: 24], signed comparison,
  first index on argmax ties. Check every partial sum for overflow.
- Current P5 replies are 32 bytes/cycles32; P2 target metadata says 31/cycles24.
  Preserve the working transport until both endpoints and tests change together.
  UART requests use live RAM; button starts use latched stored selection.
- Include params.vh once inside each consumer module; no global include guard.
- Generated data, logs, Vivado/simulation output and caches belong in ignored
  build/. Keep dataset, environments, credentials and device settings out of Git.
- Update category guides rather than creating per-task Markdown reports.

## Verification and handoff

- Run python scripts/check_workspace.py using the task's virtual environment.
  Follow the test matrix in docs/GITHUB_WORKFLOW.md. Integration/boundary changes
  require python tests/run_rtl_tests.py; board/top/XDC changes also require
  vivado -mode batch -source scripts/build_basys3.tcl when Vivado is available.
- Report exact commands, results, skips and unavailable tools. Passing simulation,
  model accuracy and physical hardware verification are distinct evidence.
  Do not claim a board test from a generated bitstream or an old commit's run.
- Review git diff and git diff --check; stage only task-related source, tests,
  constraints and docs. Use a task branch and PR, not a direct push to main or a
  force-push. Push/create a remote PR only when requested or already authorized.
- PRs use .github/pull_request_template.md. Summarize resulting behavior, changed
  interfaces, base/dependent PRs and validation. Review findings must identify a
  reproducible defect and its effect; distinguish gaps from proven regressions.

## Code Review Rules

- Check signedness/width, overflow at intermediate sums, CHW/score ordering,
  one-clock memory alignment, start/done/busy and reset/power-up behavior.
- Check mode/input ownership while busy, UART error recovery, and full-CNN done
  versus convolution done. Verify model/package identity and real test coverage.
- Changes to ports, top, source manifest, clock or pins must include affected
  integration checks. Flag claims of hardware accuracy unsupported by evidence.
