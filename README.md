# FPGA Road Sign CNN — Basys 3

Proyek pengenalan delapan kelas rambu menggunakan CNN integer pada Digilent Basys 3.
Baseline RTL saat ini: **16×16 grayscale, conv 3×3/8 filter → maxpool 2×2 → FC 8 → argmax, aktivasi 0–127,
accumulator signed24**, paket parameter `p2-doc-int-v2`.

[Status proyek dan pekerjaan berikutnya](docs/README.md#status-proyek) ·
[Peta folder](docs/README.md#struktur-folder) · [Aturan commit](docs/README.md#aturan-commit) ·
[Workflow GitHub](docs/GITHUB_WORKFLOW.md)

Anggota tim dan AI agent mulai dari [AGENTS.md](AGENTS.md), lalu ikuti
[setup workspace sampai PR](docs/GITHUB_WORKFLOW.md). Aturan proyek dipusatkan
di AGENTS.md; CLAUDE.md mengarah ke file yang sama.

## Mulai dari sini

| Kebutuhan | Folder / panduan |
|---|---|
| Model referensi, training dan parameter RTL 16×16 | [reference_model/](reference_model/README.md) |
| Modul Verilog dan pemilik subsistem | [rtl/](docs/HARDWARE.md#modul-rtl) |
| Tes convolution/requantization dan sintesis P3 | [tests/rtl/p3/](tests/README.md#p3-feature-extraction) |
| Top Basys 3, pin/clock dan build | [top dan XDC](docs/HARDWARE.md#top-basys-3-dan-implementasi-awal-p1p4) |
| Tes UART, frame controller dan dummy CNN P5 | [tests/rtl/p5/](tests/README.md#p5-komunikasi) |
| Training A–D dan pemrograman Basys 3 | [Model Studio](apps/README.md#model-studio) |
| HMI laptop dan koneksi UART ke board | [apps/board_hmi/](apps/README.md#board-hmi) |
| Inspector tensor CNN rambu (software) | [apps/traffic_sign_visualizer/](apps/README.md#traffic-sign-visual-lab) |
| Kandidat rambu 32×32 | [experiments/traffic_sign_32/](experiments/README.md#traffic-sign-32x32) |
| Demo digit MNIST | [experiments/mnist_digit/](experiments/README.md#mnist-visual-lab) |
| Dokumen sumber, desain dan bukti verifikasi | [docs/](docs/README.md) |

Entrypoint disimpan bersama aplikasinya: GUI board dan CLI UART di
`apps/board_hmi/`, launcher rambu di
`apps/traffic_sign_visualizer/start_visualizer.cmd`, dan launcher digit di
`experiments/mnist_digit/start_mnist.cmd`. Lihat [cara menjalankan](docs/README.md#menjalankan-aplikasi).

## Pemeriksaan utama

```powershell
python -m pip install -r requirements-dev.txt
python scripts/check_workspace.py
python tests/run_rtl_tests.py
```

Tes model penuh/training juga membutuhkan `reference_model/requirements.txt`.
Simulasi RTL membutuhkan `iverilog` dan `vvp` pada PATH. Petunjuk dependency dan
pengujian aplikasi ada di panduan kategori apps/ dan experiments/. Hasil proses disimpan di `build/`
dan tidak dimasukkan Git. Paket model terkurasi di `models/` tiap kategori tetap
versioned bersama kontrak, metrik, berkas memori dan checksum.

## Tim

| Anggota | Bagian |
|---|---|
| Rubi Naufaul | Reference model / P2 |
| Mahardika | Feature extraction / P3 |
| Dika | Input dan komunikasi / P5 |
| Kania Ika | Pooling, FC dan output / P4 |
| Saufik Ramadhan | Integrasi sistem / P1 |
