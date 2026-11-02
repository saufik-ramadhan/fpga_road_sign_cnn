# Peta repository

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
rtl/                         # modul hardware P3/P5
  tb/                        # tes dan flow sintesis P3
tb/                          # tes komunikasi dan top sementara P5
docs/                        # navigasi, desain, status, dokumen sumber
build/                       # seluruh output lokal, tidak di-commit
```

Model release berada di `reference_model/models/p2-doc-int-v2/`. Paket v1 tetap
tersedia untuk pembandingan historis; jangan menaruh eksperimen 28×28/32×32 ke
folder model RTL. Simpan paket utuh agar checksum dan metadata dapat diverifikasi.

## Menjalankan aplikasi

| Aplikasi | Perintah dari root |
|---|---|
| Board HMI | `python hmi_live.py` |
| UART CLI/selftest | `python tsr_link.py --selftest` |
| Inspector rambu | `python apps/traffic_sign_visualizer/visualizer.py` atau `start_visualizer.cmd` |
| MNIST | `python experiments/mnist_digit/visualizer.py` atau `start_mnist.cmd` |

## Menjalankan tes

```powershell
python -m pytest reference_model/tests -q
python -m unittest discover -s rtl/tb -p test_run_p3_tests.py
python rtl/tb/run_p3_tests.py
python tb/run_p5_tests.py
python -m unittest discover -s apps/traffic_sign_visualizer/tests -v
python -m unittest discover -s experiments/mnist_digit/tests -v
python tsr_link.py --selftest
```

Dependency aplikasi ada di `apps/*/requirements.txt`; training/reference model
memakai `reference_model/requirements.txt`. Perintah lama HMI/serial dipertahankan
melalui file root yang mengarahkan ke implementasi dalam `apps/board_hmi/`.
