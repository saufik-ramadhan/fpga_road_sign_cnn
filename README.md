# FPGA Road Sign CNN — Basys 3

Proyek pengenalan delapan kelas rambu menggunakan CNN integer pada Digilent Basys 3.
Baseline RTL saat ini: **16×16 grayscale, satu conv 3×3/8 filter, aktivasi 0–127,
accumulator signed24**, paket parameter `p2-doc-int-v2`.

[Status proyek dan pekerjaan berikutnya](docs/PROJECT_STATE.md) ·
[Peta folder](docs/REPOSITORY_GUIDE.md) · [Aturan commit](docs/COMMIT_POLICY.md) ·
[Workflow GitHub](docs/GITHUB_WORKFLOW.md)

## Mulai dari sini

| Kebutuhan | Folder / panduan |
|---|---|
| Model referensi, training dan parameter RTL 16×16 | [reference_model/](reference_model/README.md) |
| Modul Verilog dan pemilik subsistem | [rtl/](rtl/README.md) |
| Tes convolution/requantization dan sintesis P3 | [rtl/tb/](rtl/tb/README.md) |
| Tes UART, frame controller dan dummy CNN P5 | [tb/](tb/README.md) |
| HMI laptop dan koneksi UART ke board | [apps/board_hmi/](apps/board_hmi/README.md) |
| Inspector tensor CNN rambu (software) | [apps/traffic_sign_visualizer/](apps/traffic_sign_visualizer/README.md) |
| Kandidat rambu 32×32 | [experiments/traffic_sign_32/](experiments/traffic_sign_32/README.md) |
| Demo digit MNIST | [experiments/mnist_digit/](experiments/mnist_digit/README.md) |
| Dokumen sumber, desain dan bukti verifikasi | [docs/](docs/README.md) |

Windows: `start_visualizer.cmd` membuka server inspector rambu, `start_mnist.cmd`
untuk demo digit. Perintah lama `python hmi_live.py` dan `python tsr_link.py`
tetap tersedia sebagai pintasan ke aplikasi board.

## Pemeriksaan utama

```powershell
python -m pip install -r reference_model/requirements.txt
python -m pytest reference_model/tests -q
python -m unittest discover -s rtl/tb -p test_run_p3_tests.py
python rtl/tb/run_p3_tests.py
python tb/run_p5_tests.py
```

Simulasi RTL membutuhkan `iverilog` dan `vvp` pada PATH. Petunjuk dependency dan
pengujian aplikasi ada di README masing-masing. Hasil proses disimpan di `build/`
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
