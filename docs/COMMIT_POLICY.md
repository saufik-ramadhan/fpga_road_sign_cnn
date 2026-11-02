# Kebijakan file proyek

## Masukkan ke Git

- Source Python, Verilog, UI HTML/JS, launcher dan dependency manifests.
- Testbench, tes, script build dan constraints yang memang menjadi sumber.
- Dokumen desain, diagram, README dan ringkasan bukti yang membantu review.
- Paket model terkurasi yang diperlukan untuk mereproduksi demo/RTL: parameter,
  kontrak, memori, metrik dan checksum. Paket harus disimpan utuh dan diverifikasi.
- Hasil eksperimen ringkas yang punya identitas konfigurasi/split, misalnya
  `reference_model/results/training_logs/` yang sudah versioned.

## Simpan lokal di build/ atau abaikan Git

- Dataset mentah/download, environment Python dan cache.
- Checkpoint/run training, tensor dump, gambar demo yang dihasilkan berulang.
- Waveform, hasil simulator/Vivado, bitstream, checkpoint implementation dan log.
- File sementara LaTeX (`aux`, `log`, `out`, `toc`).
- Pengaturan HMI per komputer dan port serial pengguna.

Jangan mengabaikan semua `.json`, `.csv`, `.npz` atau `.mem`: sebagian adalah
kontrak, bukti eksperimen atau parameter rilis yang perlu dibagikan.

## Keputusan pada penataan 2 November 2026

| Perubahan lokal | Keputusan dan lokasi |
|---|---|
| Visualizer rambu, UI, dependency dan tes | Commit ke `apps/traffic_sign_visualizer/` |
| Perluasan quantize/publish historis untuk 32×32 | Commit; entry point document-v2 tetap terpisah |
| Paket model 32×32 terkurasi | Commit ke `experiments/traffic_sign_32/models/` |
| Demo MNIST, training source, tes dan paket model kecil | Commit ke `experiments/mnist_digit/` |
| P5 HMI/serial | Implementasi di `apps/board_hmi/`; root menyimpan pintasan kompatibel |
| Gambar/tensor hasil demo lokal | Pindah ke `build/visualizer_artifacts/`, tidak di-commit |
| Enam file kompilasi lokal docs/system_design | Pindah ke `build/docs/system_design/`, tidak di-commit |
| build/, .venv/, cache | Tetap lokal, tidak di-commit |

Perubahan lokal sebelum penataan disimpan sebagai stash cadangan bernama
`codex backup before main sync and repository organization 2026-11-02`.
Branch penataan: `codex/organize-project`; review sebelum push/merge.
