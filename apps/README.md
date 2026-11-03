# Aplikasi laptop

Dua aplikasi berikut memakai dependency manifest masing-masing dan tetap
terpisah dari model referensi serta RTL.

## Board HMI

GUI board dan kode komunikasi UART berada bersama di `apps/board_hmi/`.
Jalankan dari root repo:

```powershell
python -m pip install -r apps/board_hmi/requirements.txt
python apps/board_hmi/hmi_live.py
python apps/board_hmi/tsr_link.py --selftest
python apps/board_hmi/tsr_link.py COM8 --image sign.png
python apps/board_hmi/tsr_link.py COM8 --image scene.png --roi 20 30 119 129
python apps/board_hmi/tsr_link.py COM8 --image prepared.png --prepared-input
python -m unittest discover -s apps/board_hmi/tests -v
```

Ganti COM8 sesuai board. `hmi_live.py` menyediakan GUI; `tsr_link.py` menangani
serialisasi frame, komunikasi USB-UART, CLI dan selftest tanpa board. HMI
mengimpor modul tsr_link di folder yang sama. Tkinter disertakan oleh instalasi
Python Windows yang umum. Pintasan kompatibilitas di root sudah dihapus.

Input LIVE memakai preprocessing bersama P2 document-v2: RGB → crop ROI
inklusif → grayscale L → histogram equalization → resize bilinear 16×16.
Tanpa ROI, seluruh gambar dianggap sudah dipotong ke rambu; aplikasi tidak
mendeteksi lokasi rambu. Koordinat mengacu pada piksel file yang didekode tanpa
rotasi EXIF, sama dengan pipeline dataset P2. ROI minimal 2×2 piksel.
Di HMI, isi `ROI x1,y1,x2,y2` lalu tekan `Apply image options`. Preview adalah
256 byte yang dikirim ke UART; mengubah opsi membatalkan preview lama dan
menonaktifkan pengiriman sampai opsi diterapkan lagi.

Untuk piksel golden atau gambar yang telah diproses, gunakan `--prepared-input`
atau centang `Already prepared 16 x 16 grayscale`. File wajib grayscale L
16×16; byte diteruskan persis tanpa crop/equalization/resize. Opsi ini tidak
bisa digabung ROI. Preview stored opsional juga memakai format prepared tersebut.
Pemrosesan input gambar hanya membutuhkan Pillow, tanpa PyTorch.

- LIVE memakai UART dan selalu memilih live RAM pada top_basys3; SW15 hanya
  mengizinkan/menonaktifkan tombol stored lokal. Pengujian `--dummy` hanya
  cocok dengan dummy CNN pada top P5, bukan classifier rambu lengkap.
- STORED pada HMI saat ini menampilkan answer key/placeholder lokal; ini bukan
  hasil baru dari FPGA. Lihat label peringatan pada aplikasi.
- Letakkan aset opsional `logos/`, `stored/` dan `stored_answers.json` di folder
  `apps/board_hmi/`. `hmi_settings.json` bersifat lokal dan diabaikan Git.
- UART saat ini menggunakan reply 32 byte/four-byte cycles. Target metadata P2
  document-v2 menyebut 31 byte/three-byte cycles; keputusan penyelarasan metadata
  protokol masih outstanding. Preprocessing LIVE sudah mengikuti document-v2.
  Jangan mengubah satu endpoint saja.

[Tes dan protokol P5](../docs/HARDWARE.md#p5-komunikasi).

## Traffic Sign Visual Lab

GUI lokal untuk membedah inference model integer **p2-int-32-v1 (32×32)**. Aplikasi memakai
`golden.infer` dan parameter asli dari `experiments/traffic_sign_32/models/p2-int-32-v1`, dengan pemeriksaan
SHA256 saat startup. Tidak memerlukan checkpoint PyTorch atau dataset lengkap.

Bagian atas GUI menampilkan diagram CNN dengan ukuran tensor sesuai model.
Sorotan mengikuti tahap inspector. Bidang, lingkaran dan garis hanya ilustrasi
arsitektur; tidak menggambarkan nilai aktivasi atau bobot aktual.

### Menjalankan

Dari root repository, gunakan Python 3.11 atau lebih baru:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r apps/traffic_sign_visualizer/requirements.txt
.\.venv\Scripts\python apps/traffic_sign_visualizer/visualizer.py
```

Buka http://127.0.0.1:8765 di browser. Jika port sedang dipakai, tambahkan
`--port 8766`. Hentikan server dengan Ctrl+C. Server hanya mendengarkan localhost.
Gambar diproses di memori, tidak disimpan atau diunggah ke layanan luar.

Setelah environment tersedia, klik dua kali
`apps/traffic_sign_visualizer/start_visualizer.cmd` untuk menjalankan server
lagi, kemudian buka alamat di atas. Launcher memakai `.venv` di root repo
dan dapat dipanggil dari folder kerja mana saja.

### Cara menggunakan

1. Unggah PNG, JPEG, WebP atau BMP, maksimal 12 MB / 16 megapixel.
2. Pakai gambar rambu yang sudah dipotong, atau isi empat koordinat ROI.
   Batas kanan/bawah **inklusif**, sesuai fungsi training. Koordinat mengikuti
   orientasi gambar setelah EXIF diterapkan. Model tidak mendeteksi lokasi rambu.
3. Tekan **Proses gambar**, lalu gunakan tombol tahap atau **Berikutnya**.
4. Pada convolution, activation dan pooling, klik sel pada peta atau geser
   channel/baris/kolom untuk melihat hitungan sebenarnya.
5. Pada fully connected, pilih kelas dan indeks fitur untuk membedah kontribusi.
6. Unduh seluruh tensor JSON untuk perbandingan offline.

Tahap yang tersedia: ROI RGB dan grayscale → input 32×32 → 8 convolution
accumulators 30×30 → ReLU/rescale/clamp → 8 maxpool maps 15×15 → flatten CHW
1.800 fitur → fully connected beserta 1.800 kontribusi per kelas → argmax.

Convolution menampilkan sembilan produk dan bias. Activation menampilkan
intermediate int64, multiplier/shift dari contract.json, rounding dan clamp. Pooling menyorot maksimum
pada window 2×2. FC menampilkan bobot dan kontribusi untuk semua fitur.

### Interpretasi

- Warna peta memakai skala bersama pada tahap itu; angka asli ada pada inspector
  dan JSON. Warna antartahap tidak memiliki skala yang sama.
- Panjang batang skor memakai min–max untuk tampilan, **bukan confidence**.
- Model selalu memilih satu dari delapan kelas, termasuk untuk gambar yang
  bukan rambu. Belum ada deteksi out-of-distribution.
- Gambar sintetis bawaan hanya demonstrasi alur; bukan bukti kualitas model.
- Aplikasi memperlihatkan golden inference integer software, belum RTL/board.
- Foto besar yang dikecilkan di preview tidak mengubah ROI/tensor perhitungan.

### Verifikasi

```powershell
.\.venv\Scripts\python -m unittest discover -s apps/traffic_sign_visualizer/tests -p test_visualizer.py -v
```

Pemeriksaan mencakup setiap tensor terhadap scalar oracle independen, rekonstruksi
skor dari kontribusi FC, upload HTTP, crop inklusif, input rusak dan ROI invalid.

### Kandidat 32×32

Default GUI adalah p2-int-32-v1, dilatih pada Train.csv GTSRB dengan seed 44,
40 epoch dan checkpoint terbaik epoch 39. Split memakai seed 2026 dan pemisahan
track yang sama dengan eksperimen baseline. Official test tidak digunakan.
Akurasi validation float 97,21%; integer 97,32%; 25/25 scalar oracle cocok.
Ini kandidat terpisah untuk eksplorasi, belum rilis RTL pengganti.

Untuk membuka kembali versi 16×16:

```powershell
.\.venv\Scripts\python apps/traffic_sign_visualizer/visualizer.py --model reference_model/models/p2-int-v1
```

Dimensi peta, alamat flatten, slider dan FC otomatis mengikuti contract model.
Training: build/reference_model/visualizer32_v1.
Kuantisasi dan golden vectors: build/reference_model/integer32_v1.

Reproduksi memerlukan dependency training di `reference_model/requirements.txt`. Gunakan direktori
output baru agar hasil lama tidak ditimpa:

```powershell
python reference_model/train.py --dataset <folder-GTSRB> --output build/reference_model/visualizer32_v1 --sizes 32 --seeds 44 --epochs 40
python reference_model/quantize.py --baseline build/reference_model/visualizer32_v1 --checkpoint build/reference_model/visualizer32_v1/size_32_seed_44/best.pt --output build/reference_model/integer32_v1
python reference_model/publish_parameters.py --source build/reference_model/integer32_v1 --destination experiments/traffic_sign_32/models/p2-int-32-v1
```
