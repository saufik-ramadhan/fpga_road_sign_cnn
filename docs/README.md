# Panduan proyek

Dokumentasi dikelompokkan per kategori:
[hardware](HARDWARE.md), [model](../reference_model/README.md),
[hasil eksperimen](../reference_model/results/README.md), [aplikasi](../apps/README.md),
[eksperimen](../experiments/README.md), [pengujian](../tests/README.md),
dan [GitHub workflow](GITHUB_WORKFLOW.md).

## Struktur folder

```text
apps/
  board_hmi/                  # HMI, UART client, aset/settings lokal
  traffic_sign_visualizer/    # inspector CNN software, UI, tes
experiments/
  traffic_sign_32/models/     # kandidat 32×32 terkurasi
  mnist_digit/               # training/demo digit, UI, tes, model terkurasi
reference_model/
  document_v2/               # pipeline utama 16×16/int24
  models/                    # paket 16×16 yang didukung runner RTL
  tests/                     # tes model referensi
  results/                   # metrik dan log eksperimen terpilih
  docs/                      # laporan, slide dan gambar sumber
rtl/
  feature_extraction/        # conv/requant/fmap + wrapper P3
  communication/             # UART/frame + comm_top P5
  input/                     # live RAM / stored ROM
  files.f                    # manifest source produksi
tests/
  rtl/p3/                    # conv/requant/fmap, vectors, sintesis
  rtl/p5/                    # UART/input, dummy top dan tes komunikasi
docs/                        # navigasi, desain, status, dokumen sumber
build/                       # seluruh output lokal, tidak di-commit
```

Model release berada di `reference_model/models/p2-doc-int-v2/`. Paket v1 tetap
tersedia untuk pembandingan historis; jangan menaruh eksperimen 28×28/32×32 ke
folder model RTL. Simpan paket utuh agar checksum dan metadata dapat diverifikasi.

### Menjalankan aplikasi

| Aplikasi | Perintah dari root |
|---|---|
| Board HMI | `python hmi_live.py` |
| UART CLI/selftest | `python tsr_link.py --selftest` |
| Inspector rambu | `python apps/traffic_sign_visualizer/visualizer.py` atau `start_visualizer.cmd` |
| MNIST | `python experiments/mnist_digit/visualizer.py` atau `start_mnist.cmd` |

### Menjalankan tes

```powershell
python -m pytest reference_model/tests -q
python -m unittest discover -s tests/rtl/p3 -p test_run_p3_tests.py
python tests/rtl/p3/run_p3_tests.py
python tests/rtl/p5/run_p5_tests.py
python -m unittest discover -s apps/traffic_sign_visualizer/tests -v
python -m unittest discover -s experiments/mnist_digit/tests -v
python tsr_link.py --selftest
```

Dependency aplikasi ada di `apps/*/requirements.txt`; training/reference model
memakai `reference_model/requirements.txt`. Perintah lama HMI/serial dipertahankan
melalui file root yang mengarahkan ke implementasi dalam `apps/board_hmi/`.

## Status proyek

Baseline main setelah PR #1, #2 dan #3: `6440c169`.

| Bagian | Kondisi |
|---|---|
| P2 document-v2 | Model 16×16/int24, delapan kelas, paket parameter dan golden vectors tersedia |
| P3 | Conv/requant/fmap RTL serta runner tersedia; 23 simulasi dan enam regresi runner lulus |
| P5 | UART, parser, image input, HMI dan tes tersedia; top tes masih memakai dummy CNN |
| P1/P4 integrasi | Full controller, pooling, FC, argmax, display dan top/XDC produksi belum tersedia |
| Aplikasi software | Inspector rambu 16/32 dan demo MNIST disimpan terpisah dari RTL |
| Kandidat 32×32 | Eksperimen software; belum menjadi kontrak board |

### Bukti hardware yang tersedia

Pada commit P3 `075da612`, conv_engine/conv_wrom/requant_relu diuji langsung di
Basys 3 melalui wrapper sementara dengan input/golden ROM P2. Sepuluh putaran
masing-masing memakai 25 input yang sama: 250 eksekusi dan 392.000 perbandingan
aktivasi, tanpa mismatch/overflow. Waktu conv 14.117 siklus atau 141,17 us pada
100 MHz; timing wrapper Vivado 2026.1 WNS +1,184 ns.

Ini bukan pengujian klasifikasi CNN lengkap atau 250 sampel independen. Physical
fmap RAM readback, pooling/FC/argmax dan upload live P5 tidak masuk wrapper itu.
[Bukti review hardware](https://github.com/saufik-ramadhan/fpga_road_sign_cnn/pull/1#pullrequestreview-5736855064).
Bitstream, capture dan log lengkap tetap artefak build lokal pada checkout review.

### Prioritas berikutnya

1. Selaraskan preprocessing P5 dengan document-v2 (ROI, grayscale, equalisation,
   resize) dan format reply: transport saat ini 32 byte, metadata P2 31 byte.
2. Implementasikan/integrasikan pooling, FC, argmax dan controller; bandingkan
   setiap layer dan skor dengan golden sebelum mengklaim klasifikasi board.
3. Buat top produksi, constraints, build reproducible dan uji stored/live penuh.
4. Evaluasi official test setelah konfigurasi model dibekukan; hasil validation
   belum menggantikan evaluasi test. Pantau recall speed-limit 30 yang lemah.

Lihat [baseline P2](../reference_model/README.md),
[perencanaan model](../reference_model/README.md#baseline-dan-keputusan), dan
[peta folder](README.md#struktur-folder).

## Aturan commit

### Masukkan ke Git

- Source Python, Verilog, UI HTML/JS, launcher dan dependency manifests.
- Testbench, tes, script build dan constraints yang memang menjadi sumber.
- Dokumen desain, diagram, README dan ringkasan bukti yang membantu review.
- Paket model terkurasi yang diperlukan untuk mereproduksi demo/RTL: parameter,
  kontrak, memori, metrik dan checksum. Paket harus disimpan utuh dan diverifikasi.
- Hasil eksperimen ringkas yang punya identitas konfigurasi/split, misalnya
  `reference_model/results/training_logs/` yang sudah versioned.

### Simpan lokal di build/ atau abaikan Git

- Dataset mentah/download, environment Python dan cache.
- Checkpoint/run training, tensor dump, gambar demo yang dihasilkan berulang.
- Waveform, hasil simulator/Vivado, bitstream, checkpoint implementation dan log.
- File sementara LaTeX (`aux`, `log`, `out`, `toc`).
- Pengaturan HMI per komputer dan port serial pengguna.

Jangan mengabaikan semua `.json`, `.csv`, `.npz` atau `.mem`: sebagian adalah
kontrak, bukti eksperimen atau parameter rilis yang perlu dibagikan.

### Keputusan pada penataan 2 November 2026

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

## Dokumen sumber

Traffic_Sign_Recognition_Plan_in_Pictures.docx is an unmodified copy of the
user-supplied source in Tubes/, alongside the fpga_road_sign_cnn repository.
Its source path from the repository root is
../Traffic_Sign_Recognition_Plan_in_Pictures.docx.

Adopted by the user as the main implementation reference on 2 November 2026.
Original title: Traffic-Sign Recognition on Basys3: The Plan in Pictures.
Document date: 29 October 2026.

SHA256: 807689de946692b2718a564c66b325d581741e9d2ece305bd51155ac7f4b87ec

See ../../reference_model/README.md#baseline-dan-keputusan for the migration plan and
unresolved interface details. The reference file has not been edited to match
the earlier experimental implementation.
