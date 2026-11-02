# Status proyek — 2 November 2026

Baseline main setelah PR #1, #2 dan #3: `6440c169`.

| Bagian | Kondisi |
|---|---|
| P2 document-v2 | Model 16×16/int24, delapan kelas, paket parameter dan golden vectors tersedia |
| P3 | Conv/requant/fmap RTL serta runner tersedia; 20 simulasi dan enam regresi runner lulus |
| P5 | UART, parser, image input, HMI dan tes tersedia; top tes masih memakai dummy CNN |
| P1/P4 integrasi | Full controller, pooling, FC, argmax, display dan top/XDC produksi belum tersedia |
| Aplikasi software | Inspector rambu 16/32 dan demo MNIST disimpan terpisah dari RTL |
| Kandidat 32×32 | Eksperimen software; belum menjadi kontrak board |

## Bukti hardware yang tersedia

Pada commit P3 `075da612`, conv_engine/conv_wrom/requant_relu diuji langsung di
Basys 3 melalui wrapper sementara dengan input/golden ROM P2. Sepuluh putaran
masing-masing memakai 25 input yang sama: 250 eksekusi dan 392.000 perbandingan
aktivasi, tanpa mismatch/overflow. Waktu conv 14.117 siklus atau 141,17 us pada
100 MHz; timing wrapper Vivado 2026.1 WNS +1,184 ns.

Ini bukan pengujian klasifikasi CNN lengkap atau 250 sampel independen. Physical
fmap RAM readback, pooling/FC/argmax dan upload live P5 tidak masuk wrapper itu.
[Bukti review hardware](https://github.com/saufik-ramadhan/fpga_road_sign_cnn/pull/1#pullrequestreview-5736855064).
Bitstream, capture dan log lengkap tetap artefak build lokal pada checkout review.

## Prioritas berikutnya

1. Selaraskan preprocessing P5 dengan document-v2 (ROI, grayscale, equalisation,
   resize) dan format reply: transport saat ini 32 byte, metadata P2 31 byte.
2. Implementasikan/integrasikan pooling, FC, argmax dan controller; bandingkan
   setiap layer dan skor dengan golden sebelum mengklaim klasifikasi board.
3. Buat top produksi, constraints, build reproducible dan uji stored/live penuh.
4. Evaluasi official test setelah konfigurasi model dibekukan; hasil validation
   belum menggantikan evaluasi test. Pantau recall speed-limit 30 yang lemah.

Lihat [baseline P2](../reference_model/README.md),
[perencanaan model](../reference_model/DOCUMENT_BASELINE.md), dan
[peta folder](REPOSITORY_GUIDE.md).
