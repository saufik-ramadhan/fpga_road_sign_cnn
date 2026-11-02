# MNIST Visual Lab

Model dan GUI khusus digit 0–9, terpisah dari model rambu. Jalankan
`start_mnist.cmd` dari root repository, lalu buka http://127.0.0.1:8766.
GUI rambu tetap berada di port 8765.

Diagram CNN di bagian atas menggambarkan layer, neuron dan koneksi secara ringkas,
dengan dimensi model yang sebenarnya. Sorotan mengikuti tahap inspector;
warna dan koneksinya merupakan ilustrasi, bukan nilai aktivasi atau bobot aktual.

## Setup

Inference hanya memerlukan NumPy dan Pillow:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r apps/traffic_sign_visualizer/requirements.txt
.\.venv\Scripts\python experiments/mnist_digit/visualizer.py
```

Tulis satu digit pada kanvas dan tekan **Kenali tulisan**, atau unggah gambar.
Gunakan **Muat contoh** untuk salah satu dari sepuluh gambar MNIST validation
berlabel. Contoh tersebut bukan bagian dari official test.

Telusuri input, convolution, ReLU/rescale, pooling, flatten CHW, fully connected
dan argmax. Klik sel peta atau gunakan slider untuk membedah angka asli.
Inspector FC menampilkan seluruh kontribusi setiap fitur ke neuron digit.
Seluruh tensor dapat diunduh sebagai JSON.

## Arsitektur dan hasil

`28×28×1 → Conv 3×3, 8 filter → 26×26×8 → ReLU/rescale → MaxPool 2×2 → 13×13×8 → 1.352 fitur → FC 10 → argmax`

- Bobot dan model float dilatih baru, bukan adaptasi bobot rambu.
- 54.999 gambar training dan 5.001 validation, stratified seed 2026.
- Adam, seed 42, batch 128, lr .001, 12 epoch; checkpoint terbaik epoch 11.
- Validation: float 97,4605%, integer 97,4805%.
- Official test (10.000 gambar): float 97,34%, integer 97,28%.
- Test dibuka setelah pemilihan checkpoint dan kalibrasi training-only.
- 13/13 full-network vectors cocok dengan scalar oracle independen.
- Inferensi integer memakai shared golden model, int8 weights, int32 bias,
  accumulator dan skor, serta int64 rescale. Rounding ties-to-even untuk
  parameter; halfway-up setelah ReLU untuk activation; clamp 0–127.

`models/mnist-int-v1/` berisi integer parameters, float weights, kontrak, metrik
termasuk confusion matrix, contoh validation, empat file `.mem`, dan checksum.
Checkpoint serta dataset cache berada di `build/mnist_digit/` (diabaikan Git).
Belum ada verifikasi RTL atau board.

Dataset diunduh dari mirror MNIST yang dipakai
[torchvision](https://github.com/pytorch/vision/blob/main/torchvision/datasets/mnist.py),
dengan MD5 resmi pada setiap arsip. Tidak memakai torchvision sebagai dependency.

## Praproses tulisan dan unggahan

Orientasi EXIF diterapkan, alpha dikompositkan di atas putih, lalu grayscale.
Latar terang dikenali dari median pixel tepi dan polaritas dibalik agar digit
terang di latar gelap. Kanvas kosong atau gambar tanpa kontras ditolak.

Untuk gambar selain 28×28: crop bounding box foreground (pixel >35), resize
bilinear dengan rasio tetap dalam 20×20, tempatkan di kanvas hitam 28×28,
lalu pusatkan berdasarkan pusat massa. Untuk gambar MNIST 28×28 yang sudah
siap, nilai pixel dipertahankan setelah pemeriksaan polaritas; tidak di-crop ulang.
Tampilan input menunjukkan pixel yang benar-benar dipakai inferensi.

Model selalu memilih satu dari sepuluh digit. Skor bukan probabilitas terkalibrasi.
Foto, tulisan yang tidak menyerupai MNIST, dan beberapa digit sekaligus dapat
salah diklasifikasikan. Hasil official test tidak menjamin akurasi pada kanvas.

## Reproduksi dan pengujian

Training memerlukan dependency `reference_model/requirements.txt`.
Gunakan folder output dan package baru saat mengulang training:

```powershell
python experiments/mnist_digit/train.py --output build/mnist_digit/v2 --package experiments/mnist_digit/models/mnist-int-v2
python -m unittest discover -s experiments/mnist_digit/tests -v
```

Tes meliputi semua sepuluh digit terhadap scalar oracle per layer, kontribusi
FC, preservasi input MNIST, polaritas, pusat massa, alpha, penolakan kanvas
kosong dan ROI manual, serta upload/sample/metrics HTTP.
