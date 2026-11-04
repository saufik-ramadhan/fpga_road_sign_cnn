# Panduan proyek

Dokumentasi dikelompokkan per kategori:
[hardware](HARDWARE.md), [model](../reference_model/README.md),
[hasil eksperimen](../reference_model/results/README.md), [aplikasi](../apps/README.md),
[eksperimen](../experiments/README.md), [pengujian](../tests/README.md),
dan [GitHub workflow](GITHUB_WORKFLOW.md).

Untuk mulai bekerja sebagai anggota tim, ikuti [panduan pengembangan](GITHUB_WORKFLOW.md)
dari setup, pembagian tugas, brief AI dan testing sampai PR. [AGENTS.md](../AGENTS.md)
menjadi sumber instruksi bersama; CLAUDE.md hanya pengarah. Jalankan
`python scripts/check_workspace.py` dari environment tugas untuk memeriksa konteks/tool.

## Struktur folder

```text
apps/
  board_hmi/                  # HMI, UART client, aset/settings lokal
  model_studio/               # training A–D dan deployment Basys 3
  traffic_sign_visualizer/    # inspector CNN software, UI, tes
experiments/
  traffic_sign_d42/models/    # paket golden integer D42 tersegel
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
  classification/           # pooling, FC dan argmax P4
  control/                  # controller/core P1
  board/                    # debounce/display
  top/                      # top_basys3
  files.f                    # manifest source produksi
constraints/                # pin/clock Basys 3
scripts/                    # build Vivado board top
tests/
  rtl/p3/                    # conv/requant/fmap, vectors, sintesis
  rtl/p5/                    # UART/input, dummy top dan tes komunikasi
  rtl/integration/           # CNN golden dan board top/UART nyata
docs/                        # navigasi, desain, status, dokumen sumber
build/                       # seluruh output lokal, tidak di-commit
```

Model release berada di `reference_model/models/p2-doc-int-v2/`. Paket v1 tetap
tersedia untuk pembandingan historis; jangan menaruh eksperimen 28×28/32×32 ke
folder model RTL. Simpan paket utuh agar checksum dan metadata dapat diverifikasi.

### Menjalankan aplikasi

| Aplikasi | Perintah dari root |
|---|---|
| Board HMI | `python apps/board_hmi/hmi_live.py` |
| Model Studio | `python apps/model_studio/studio.py` |
| UART CLI/selftest | `python apps/board_hmi/tsr_link.py --selftest` |
| Inspector rambu | `python apps/traffic_sign_visualizer/visualizer.py` atau `apps/traffic_sign_visualizer/start_visualizer.cmd` |
| MNIST | `python experiments/mnist_digit/visualizer.py` atau `experiments/mnist_digit/start_mnist.cmd` |

### Menjalankan tes

```powershell
python -m pytest reference_model/tests -q
python -m unittest discover -s tests/rtl/p3 -p test_run_p3_tests.py
python tests/rtl/p3/run_p3_tests.py
python tests/rtl/p5/run_p5_tests.py
python tests/run_rtl_tests.py --suite integration
python -m unittest discover -s apps/traffic_sign_visualizer/tests -v
python -m unittest discover -s experiments/mnist_digit/tests -v
python apps/board_hmi/tsr_link.py --selftest
```

Dependency aplikasi ada di `apps/*/requirements.txt`; training/reference model
memakai `reference_model/requirements.txt`. Entrypoint dan launcher berada di
folder aplikasi masing-masing; pintasan kompatibilitas HMI/serial di root sudah
dihapus. Kedua launcher Windows tetap memakai `.venv` di root repo.

## Status proyek

Snapshot 3 November 2026. Model Studio, profil D42, dan kontrak UART final
masuk ke `main` lewat [PR #7](https://github.com/saufik-ramadhan/fpga_road_sign_cnn/pull/7)
pada commit `29c4abc2`. [CI main](https://github.com/saufik-ramadhan/fpga_road_sign_cnn/actions/runs/41572364178)
lulus untuk preflight, regresi RTL, dan tes aplikasi. Regresi model terpisah
lulus 32 tes. Build Vivado 2026.1 untuk A dan D42 memenuhi timing 100 MHz
dengan nol error DRC.

| Bagian | Status |
|---|---|
| Baseline A (`p2-doc-int-v2`) | Default produksi. Input grayscale 16×16, delapan kelas, skor signed24. LIVE dan 16 pilihan stored terverifikasi pada board. |
| D42 (`p2-doc-d42-int24-v1`) | Profil FPGA opsional dengan Conv kedua setelah pooling. LIVE terverifikasi pada board. Mode stored lulus simulasi. [Detail RTL dan bitstream](HARDWARE.md#profil-rtl-d42). |
| UART dan Board HMI | Kontrak final 115200 8N1, request 259 byte, reply 32 byte dengan counter siklus unsigned32. [Detail frame](HARDWARE.md#kontrak-uart-final-basys-3). |
| Model Studio | Training A–D memakai satu split per track. Tab Program Basys 3 memilih arsip bitstream A atau D42 yang diverifikasi dengan checksum. [Panduan penggunaan](../apps/README.md#model-studio). |
| Eksperimen software | B memakai input 32×32, C memakai 16 filter, dan D menambah Conv kedua. C meraih rata-rata akurasi integer 97,43% pada validasi tiga seed. D42 meraih 97,25% dengan recall Speed Limit 30 sebesar 93,11%. [Hasil kuantisasi C/D](../reference_model/results/README.md#kuantisasi-arsitektur-cd). |

### Bukti hardware yang tersedia

Pada 3 November 2026, `top_basys3` produksi dari source `3a3074cc` diprogram
ke Basys 3 dan diuji melalui UART 115200. Sebanyak 304 inferensi valid
(25 golden × 10, 16 bank stored sebagai live, 32 acak, 3 preprocessing RGB,
3 recovery) cocok pada seluruh 2.432 skor dan prediksi. Dua reply error
checksum/command sesuai; frame terputus pulih tanpa reply. Latensi CNN tetap
23.542 siklus (235,42 us pada 100 MHz). Pengulangan bukan sampel independen
atau bukti akurasi official test. Uji ini tidak mengukur tensor internal atau
jalur stored lewat switch/BTNC. Secara terpisah, pengguna mengonfirmasi uji
manual seluruh 16 pilihan stored: digit kelas sesuai golden dan LED13 tetap
mati. Skor stored tidak dibaca lewat UART pada uji manual tersebut.
[Metode dan batas bukti](HARDWARE.md#uji-fisik-full-cnn-live-3-november-2026).

Pada hari yang sama, bitstream D42 dari source `c6902cae` menghasilkan
253 inferensi valid melalui UART LIVE. Seluruh 2.024 skor signed24 dan
prediksi cocok bit-exact, dengan 81.168 siklus per inferensi
(811,68 µs pada 100 MHz). Dua reply error sesuai ekspektasi. Bukti fisik
ini mencakup jalur LIVE. [Metode uji D42](HARDWARE.md#profil-rtl-d42).

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

1. Uji fisik 16 pilihan stored D42 melalui switch dan BTNC. Cocokkan digit
   kelas dengan `stored_manifest.json` paket D42 dan pastikan LED13 tetap mati.
2. Uji fisik pergantian pilihan dan penekanan tombol saat CNN sibuk, termasuk
   permintaan LIVE UART yang masuk berdekatan dengan permintaan stored.
   Simulasi top sudah mencakup antrean stored/LIVE.
3. Tetapkan paket integer dan preprocessing sebelum evaluasi official test.
   Gunakan set yang sama untuk kandidat yang dipilih, lalu laporkan akurasi,
   recall per kelas, dan confusion matrix, terutama untuk Speed Limit 30.
   Hasil saat ini berasal dari validasi. Tunda eksperimen arsitektur baru
   sampai hasil uji menunjukkan kebutuhan yang spesifik.

Lihat [baseline P2](../reference_model/README.md),
[perencanaan model](../reference_model/README.md#baseline-dan-keputusan), dan
[peta folder](README.md#struktur-folder).

## Laporan proyek LaTeX

[Sumber laporan](laporan-basys3/laporan.tex) mencatat arsitektur, hasil
validasi dan official test, serta sweep MAC pada snapshot `ceb5ea86`.
Grafik vektor yang dipakai naskah ada di `laporan-basys3/figures/`.
Data matriks dan metadata bitstream ada di `laporan-basys3/data/`.

Kompilasi dari root repo dengan pdfLaTeX. Jalankan tiga kali untuk
memperbarui daftar isi, daftar gambar, dan referensi silang.

```powershell
New-Item -ItemType Directory -Force build/laporan-basys3 | Out-Null
$reportOutput = (Resolve-Path build/laporan-basys3).Path
Push-Location docs/laporan-basys3
try {
    1..3 | ForEach-Object {
        pdflatex -interaction=nonstopmode -halt-on-error "--output-directory=$reportOutput" laporan.tex
        if ($LASTEXITCODE) { throw 'Kompilasi laporan gagal' }
    }
} finally { Pop-Location }
```

Buka PDF hasil kompilasi di `build/laporan-basys3/laporan.pdf`.

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
| P5 HMI/serial | Implementasi di `apps/board_hmi/`; pintasan root dihapus pada penataan 3 November |
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
