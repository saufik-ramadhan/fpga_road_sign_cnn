# Model referensi dan handoff P2

Panduan tunggal untuk pipeline aktif, paket parameter, kontrak numerik dan
pipeline historis. [Hasil terukur/epoch log](results/README.md) ·
[Hardware dan UART](../docs/HARDWARE.md) · [Pengujian](../tests/README.md) ·
[Status proyek](../docs/README.md#status-proyek).

## Baseline dan keputusan

Dokumen utama yang diadopsi pada 2 November 2026 adalah
[Traffic Sign Recognition Plan in Pictures](../docs/references/Traffic_Sign_Recognition_Plan_in_Pictures.docx).
Deliverable dosen tetap berlaku; keputusan eksplisit pengguna berikutnya
mengambil prioritas. Dokumen gambar merupakan ringkasan, sehingga detail yang
hilang perlu dicocokkan dengan full plan; kontradiksi harus dinyatakan.

Baseline saat ini: **16×16 grayscale → Conv 3×3 VALID/8 filter → rescale/ReLU →
maxpool 2×2 → CHW flatten 392 → FC 8 → argmax**. Ada 3.208 bobot + 16 bias dan
17.248 MAC/gambar. Ini hitungan aritmetika, bukan pengukuran latency.

Paket `p2-doc-int-v2` memakai histogram equalization, augmentasi training,
class order dokumen dan checked int24. Pipeline v1 dipertahankan sebagai
histori dan tidak otomatis menjadi release yang sesuai dokumen baru.
Jangan mengubah model, preprocessing, bobot, class order atau skala sepihak.

Gate dokumen: ≥95% mempertahankan 16×16; 90–95% meninjau kelas yang tertukar;
<90% mengevaluasi fallback 32×32 sebelum freeze. Hasil validation dipakai untuk
tuning; official test hanya dievaluasi setelah model dibekukan. Validation ≥95%
belum menggantikan gate test. Working target historis recall ≥90% per kelas
adalah kriteria tambahan yang harus dilaporkan terpisah.

## Pipeline document v2

Kode utama ada di `document_v2/`; entry point top-level adalah pipeline historis.

1. Crop ROI dengan maksimum x/y **inklusif**, RGB → Pillow L grayscale.
2. `Pillow ImageOps.equalize`, lalu resize bilinear 16×16.
3. Simpan uint8 row-major 0–255; float training memakai `/255`. Exporter melipat
   skala ini ke parameter; hardware tidak menambah operasi `u-128`.
4. Training saja: rotasi uniform ±5°, translasi ±1 piksel tiap sumbu,
   brightness 0,9–1,1; sesudah preprocessing dasar, bilinear grid_sample,
   zero padding, align_corners=False. Tidak ada flip/augmentasi evaluation.

Operasi dasar Pillow dipusatkan di `document_v2/preprocessing.py`, dipakai
`document_v2.data.preprocess` dan input LIVE Board HMI/CLI. Jalur laptop dapat
memakai seluruh gambar rambu atau ROI inklusif; tidak ada deteksi rambu otomatis
atau rotasi EXIF. `--prepared-input` meneruskan file L 16×16 yang sudah diproses
tanpa mengubah byte. Model tersegel dan transport 32-byte P5 tetap sama.

Data GTSRB dipilih dari Train.csv: 13.890 gambar pada delapan kelas yang diperiksa
untuk decoding, dimensi dan ROI. Split seed 2026, stratified per physical-sign
track (class+track), bukan per frame: 11.130 gambar/371 track training dan
2.760 gambar/92 track validation. Track tidak boleh muncul pada dua split.
Official test tidak dipakai untuk training, pemilihan checkpoint atau kalibrasi.
Audit seluruh 43 kelas tidak diklaim oleh audit delapan kelas ini.

Training document-v2: Adam lr 0,001, batch 128, class weights dari training,
cap 60 epoch, patience 12, initialization seed 42/43/44, CPU empat thread,
deterministic algorithms. Pilih checkpoint dengan validation accuracy terbaik;
kalibrasi aktivasi memakai maksimum ReLU **training saja**, tanpa percentile
atau range yang dituning pada validation. Pemilihan run/default quantization
memakai float validation accuracy tertinggi; tie mengikuti urutan run terurut.

| Index | GTSRB | Label/display |
|---|---|---|
| 0 | 14 | Stop / StOP |
| 1 | 13 | Yield / yLd |
| 2 | 17 | No entry / no E |
| 3 | 12 | Priority road / PrIo |
| 4 | 18 | General caution / CAUt |
| 5 | 38 | Keep right / rIGt |
| 6 | 1 | Speed limit 30 / 30 |
| 7 | 2 | Speed limit 50 / 50 |

Class order harus sama pada FC rows, bias, skor golden, UART, display dan label
stored. Order historis v1 adalah GTSRB `[1,2,12,13,14,17,18,38]`; jangan relabel
skor lama tanpa permutasi parameter dan metadata yang sesuai.

### Kontrak numerik dan memori v2

| Kuantitas | Representasi |
|---|---|
| Input | uint8 0–255, real scale 1/255, zero point 0 |
| Bobot | symmetric int8 −127..127, satu positive scale per layer |
| Bias, MAC dan skor | signed24, bias-first serial MAC, overflow dilarang |
| Aktivasi/pool | 0–127 dalam uint8, zero point 0 |
| Rescale | uint16 M 1..65535, S 0..47, signed48 product/rounding |
| Conv layout | OIHW: `filter*9 + ky*3 + kx`; cross-correlation tanpa flip |
| Feature map | CHW: `filter*196 + row*14 + col` |
| Pool / FC input | CHW: `filter*49 + row*7 + col`, 392 fitur |
| Argmax | Skor tanpa output requantization; tie memilih index terkecil |

`s_w=max(abs(float_weights))/127` (1 jika bobot semua nol). Parameter dibulatkan
nearest ties-to-even dan diclip ke bobot legal. Bias memakai scale input×weight;
aktivasi memakai `s_a=max_training_relu/127` (1 jika nol). Pilih shift terbesar
0..47 yang membuat `M=round((s_x*s_conv_weight/s_a)*2^S)` berada pada 1..65535.
Semua FC logits memakai scale `s_a*s_fc_weight` yang sama, menjaga argmax.

```text
P = max(0, accumulator)
R = 0 jika S=0, selain itu 2^(S-1)
activation = min(127, (P*M + R) >> S)
```

Pembulatan aktivasi nonnegatif adalah nearest, halfway-up. Golden memeriksa bias
awal dan setiap partial sum convolution/FC; overflow yang dibatalkan produk
berikutnya tetap ditolak. Oracle serial memakai Python integer independen.
Exporter membuktikan `abs(bias)+max_input*sum(abs(weights))` muat signed24 dan
product+rounding muat signed48. NumPy int64 hanya container eksekusi.

Paket v2 saat ini: M=43980, S=25; bound conv 167.442, FC 752.322, widened rescale
7.380.876.376. Selalu baca ulang kontrak saat model berubah. `.mem` satu hex word
per baris, two's complement: bias/score 6 digit, piksel/aktivasi 2 digit.
`.coe` menyimpan nilai sama. Read latency hardware dan start/done ada pada
[panduan hardware](../docs/HARDWARE.md).

### Menjalankan dan mengekspor

Dari root repo, gunakan direktori output baru (run/paket tidak ditimpa):

```powershell
python -m pip install -r reference_model/requirements.txt
python -m pytest reference_model/tests -q
python reference_model/document_v2/train.py --dataset <folder-GTSRB> --output build/reference_model/document_v2_new
python reference_model/document_v2/quantize.py --baseline build/reference_model/document_v2_new --output build/reference_model/document_integer_v2_new
python reference_model/document_v2/publish.py --source build/reference_model/document_integer_v2_new --destination reference_model/models/<versi-baru>
python reference_model/document_v2/golden.py reference_model/models/p2-doc-int-v2 prepared_pixels.npy layers.npz
```

`prepared_pixels.npy` adalah nonempty NCHW uint8. `golden.load_model`, `infer`
dan `scalar_infer` dapat dipakai oleh simulator. Model memuat localparams lewat
`params.vh`, di-include sekali per modul konsumen, tanpa global include guard.

## Paket model

| Paket | Tujuan |
|---|---|
| [p2-doc-int-v2](models/p2-doc-int-v2/README.md) | Kandidat utama 16×16/int24, preprocessing document-v2 |
| [p2-int-v1](models/p2-int-v1/README.md) | Model historis 16×16/int32, tanpa equalization |
| [32×32](../experiments/README.md#traffic-sign-32x32) | Software experimental, bukan pengganti kontrak RTL |

Paket terkurasi disimpan utuh: parameter NPZ, contract, metrics, memory layout,
mem/, checksum dan README. V2 menambahkan .coe, params.vh, 25 vektor lengkap
(20 real + lima synthetic), 16 gambar stored serta label. `signs.mem` beralamat
`stored_index*256+pixel_address`; labels adalah ground truth, bukan prediksi.
Golden scores/labels/predictions dalam manifest disimpan terpisah.

Paket lama dan checksum tidak diubah ketika memperbaiki laporan. `.gitattributes`
menjaga byte lintas platform. Checkpoint, raw dataset, caches dan run outputs
berada di build/ atau lokasi eksternal. Jangan memindahkan eksperimen 28/32×32
ke models/ ini, karena runner RTL P3 hanya mendukung gambar 16×16.

## Historical integer contract v1

Top-level `data.py`, `train.py`, `quantize.py`, `golden.py` dan
`publish_parameters.py` mempertahankan pipeline lama: inclusive ROI, Pillow L,
bilinear resize, **tanpa equalization/augmentasi**. Training 40 epoch/patience 12,
Adam lr 0,001, seed 42/43/44 dan grouped split yang sama. Ukuran 16 dan 32
membandingkan konfigurasi utuh; FC lebih besar pada 32, sehingga bukan ablation
resolusi murni. 32×32 menghasilkan 1.800 fitur, 14.472 bobot + 16 bias dan
79.200 MAC/gambar. Jangan mengubah preprocessing deployment model lama sepihak.

Numerik v1 sama untuk bobot, aktivasi, CHW, tie dan rumus rescale, tetapi bias,
accumulator dan skor **int32**, rescale **int64** dengan range shift 0..47.
Bound serial `abs(bias)+max_input*sum(abs(weights))` wajib muat int32 dan rescale
muat int64; overflow dilarang. Kalibrasi hanya training. Paket 16×16 memakai
M=34172, S=25. Akurasi/model v1 tidak berlaku untuk pipeline v2.

```powershell
python reference_model/train.py --sizes 16 32 --seeds 42 43 44 --epochs 40
python reference_model/quantize.py --output build/reference_model/integer_v1_new
python reference_model/publish_parameters.py --source build/reference_model/integer_v1_new --destination reference_model/models/<versi-v1-baru>
python reference_model/export_training_log.py
```

Exporter epoch memperbarui bagian training log pada [hasil eksperimen](results/README.md)
serta CSV/config/metrics pada results/training_logs/. Official-test estimate harus
terpisah dari tuning. Hasil tiga seed satu split hanya menunjukkan variasi
optimisasi, bukan uncertainty pada track baru.

## Dokumen dan artefak

`docs/` di bawah reference_model menyimpan laporan Word, slide dan gambar asli
untuk presentasi. `P2_Model_and_Software_Approach.docx/.pptx`,
`P2_Implementation_and_Verification_Report.docx` dan `P2_to_RTL_Handoff.docx`
menggambarkan v1; gunakan kontrak v2 untuk integrasi terbaru. Diagram historis
ikut digabung ke [hasil eksperimen](results/README.md#historical-system-diagram-v1).
Inspector software dijelaskan di [panduan aplikasi](../apps/README.md).

## Handoff dan pekerjaan berikutnya

- P2: dataset/split identity, shared preprocessing, float checkpoint/config,
  parameter integer, bounds, mem/coe/header, bank stored dan golden vectors.
- P3: convolution/requant/fmap; P4: pooling/FC/argmax/display; P5: input/UART/UI;
  P1: controller/top, constraints, timing, end-to-end verification.
- Samakan prepared uint8 bytes antara training, golden, file memori dan UART;
  automatic traffic-sign detection bukan bagian baseline.
- Samakan metadata P2 reply 31 byte/24-bit cycles dengan P5 saat ini
  32 byte/32-bit cycles, dengan perubahan kedua endpoint sekaligus.
- Require exact match setiap layer/skor, bukan hanya kelas. Scalar agreement,
  RTL agreement dan akurasi terhadap ground truth adalah metrik berbeda.
- Lanjutkan integrasi CNN penuh, 16 stored dan batch live board, final test,
  pengukuran latency/throughput/resource/power dan laporan/video/slides.
  Bukti conv hardware sudah ada di panduan proyek; itu belum full CNN.
