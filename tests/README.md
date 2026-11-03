# Pengujian dan testbench

Semua **testbench RTL** berada di satu kategori, `tests/rtl/`. Model dan aplikasi
mempertahankan tes Python di dekat implementasinya.

```text
tests/
  run_rtl_tests.py       # jalankan suite RTL P3, P5 dan integrasi
  rtl/
    p3/                 # conv, requant, fmap, vectors, sintesis
    p5/                 # UART, frame_ctrl, image input, dummy top
    integration/        # P5->P3, CNN golden dan top Basys 3
reference_model/tests/  # numerik, preprocessing, eksport parameter
apps/traffic_sign_visualizer/tests/
experiments/mnist_digit/tests/
```

## Menjalankan semua RTL

Dari root repo, dengan Icarus (`iverilog`, `vvp`), NumPy dan Pillow tersedia:

```powershell
python tests/run_rtl_tests.py
python tests/run_rtl_tests.py --suite p3
python tests/run_rtl_tests.py --suite p5
python tests/run_rtl_tests.py --suite integration
```

Runner mengembalikan status gagal jika salah satu suite gagal. Output lokal tetap
di `build/p3_sim/`, `build/p5_sim/` dan `build/integration_sim/`; model RTL dibaca dari reference_model/models/.
Missing dependency/package, paket tanpa input dan empty test selection gagal.

Sebelum menjalankan suite, gunakan environment dari `requirements-dev.txt` dan
`python scripts/check_workspace.py`. Matriks tes menurut perubahan, setup
workspace dan bukti yang perlu dicatat ada di
[panduan pengembangan](../docs/GITHUB_WORKFLOW.md#7-matriks-pengujian).

## P3 feature extraction

```powershell
python -m unittest discover -s tests/rtl/p3 -p test_run_p3_tests.py
python tests/rtl/p3/run_p3_tests.py
python tests/rtl/p3/run_p3_tests.py --vectors <paket-P2>
python tests/rtl/p3/run_p3_tests.py --sim xsim --vivado-bin <Vivado>/bin
python tests/rtl/p3/run_p3_tests.py --wave
vivado -mode batch -source tests/rtl/p3/synth_p3.tcl
```

- `conv_engine_tb.v`: accumulator, aktivasi, fmap RAM dan handshake.
- `requant_relu_tb.v`: rounding, range, rescale dan latency.
- `feature_extraction_tb.v`: public wrapper, one-cycle fmap readback dan handshake.
- `integration/subsystems_tb.v`: bank stored P5 menggerakkan P3, 16 gambar.
- `p2_vectors.py` / `p3_vectors.py`: adapter model dan directed/random data.
- `test_run_p3_tests.py`: enam regresi runner.
- `p3_synth_top.v` / `synth_p3.tcl`: sintesis out-of-context, bukan top board lengkap.
- `conv_engine_tb.gtkw`: layout waveform GTKWave.

Suite P3 memiliki 23 simulasi: 20 tes core semula, dua tes wrapper readback
(v2 int24 dan v1 int32), serta satu tes P5 stored-input -> P3 pada 16 gambar.
Total 136 eksekusi gambar dan 130.000 nilai requantization; gambar tertentu
diulang untuk boundary berbeda, bukan 136 sampel independen.
Log per testbench bernama `<top>.log`. Semua runner membaca `rtl/files.f`.
Periksa golden accumulator sebelum aktivasi agar clipping tidak menutupi error.

## P5 komunikasi

```powershell
python tests/rtl/p5/run_p5_tests.py
python apps/board_hmi/tsr_link.py --selftest
```

- `tb_uart_rx.v`: framing, break, glitch dan recovery.
- `tb_comm.v`: live/stored, checksum/command salah, timeout dan invalid stop bit.
- `rtl/communication/comm_top.v`: wrapper produksi input/komunikasi.
- `dummy_cnn.v`: placeholder pixel-sum, bukan classifier rambu.
- `top_p5_test.v`: top sementara untuk bring-up komunikasi.

Runner menguji 16 dan 868 clocks/bit, lalu selftest client. Simulasi nominal
dapat memerlukan sekitar dua menit di Windows; batas proses 300 detik memberi
ruang untuk beban host, sementara watchdog testbench tetap aktif. Selain exit code,
log/verdict diperiksa karena vvp Windows lama dapat memberi exit 0 setelah
$fatal. Waveform opsional menggunakan -DDUMP saat compile tb_comm.

## Integrasi CNN dan board top

```powershell
python tests/rtl/integration/run_integration_tests.py
vivado -mode batch -source scripts/build_basys3.tcl
```

- cnn_core_tb: 25 input golden P2 v2, seluruh 392 fitur pool, delapan scores dan prediction, handshake,
  latency 23.542 siklus, reset saat berjalan dan start saat busy.
- classification_edges_tb: signed argmax, tie ke indeks pertama, dan overflow
  partial FC meskipun produk berikutnya membatalkan overflow pada skor akhir.
- top_basys3_tb: 16 stored + satu stored/live overlap; golden scores, mode latch,
  debounce/busy gating, queue UART, frame32/cycles/checksum dan display scan.

Runner memakai manifest produksi dan paket v2 yang sama dengan build board.
Bitstream hasil build tidak otomatis diprogram. Pengujian ini belum mencakup
board fisik. Top lama top_p5_test tetap hanya harness komunikasi dengan dummy.

## Tes model dan aplikasi

```powershell
python -m pytest reference_model/tests -q
python -m unittest discover -s apps/board_hmi/tests -v
python -m unittest discover -s apps/traffic_sign_visualizer/tests -v
python -m unittest discover -s experiments/mnist_digit/tests -v
```

Dependency: reference_model/requirements.txt (training/model),
apps/traffic_sign_visualizer/requirements.txt (inspector), dan
apps/board_hmi/requirements.txt (serial/HMI).
Detail port/kontrak: [hardware](../docs/HARDWARE.md). Kondisi validasi fisik:
[panduan proyek](../docs/README.md#status-proyek).

Tes Board HMI mengunci byte preprocessing terhadap hasil fungsi P2 sebelum
ekstraksi bersama, payload/checksum UART, ROI invalid, handler HMI, serta 25
input golden yang dilewatkan tanpa pemrosesan ulang melalui prepared-input.
Tes tersebut tidak membuka GUI atau mengakses board. CI menjalankannya bersama
kedua inspector; tes model penuh tetap memerlukan dependency PyTorch.

`apps/board_hmi/verify_board.py` menjalankan verifikasi UART fisik terhadap
golden dan scalar oracle; membutuhkan board terprogram dan port eksplisit.
Metode dan bukti 3 November 2026 ada di [panduan hardware](../docs/HARDWARE.md#uji-fisik-full-cnn-live-3-november-2026).
Tiga regresi verifier memastikan seluruh vektor terpublikasi tersedia dan skor
yang salah tetap ditolak meskipun kelas benar. Tes unit tidak mengakses serial.

## CI pull request

`.github/workflows/checks.yml` menjalankan preflight, enam tes runner P3,
seluruh simulasi P3/P5/integrasi dan tes inspector rambu/MNIST pada Linux.
Log simulator dan konteks workspace disimpan sebagai artifact. Ini belum
menjalankan pytest model penuh, Vivado, GUI desktop atau board fisik; penulis PR
menyertakan hasil tambahan sesuai area perubahan. Workflow di GitHub baru dapat
dibuktikan setelah branch/PR dipush; hasil lokal bukan status CI hosted.
