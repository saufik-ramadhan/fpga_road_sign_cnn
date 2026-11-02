# Pengujian komunikasi P5

Jalankan dari root repo dengan Python dan Icarus Verilog pada PATH:

```powershell
python tb/run_p5_tests.py
```

Runner menjalankan tes UART dan komunikasi lengkap dengan dummy CNN pada
16 clocks/bit serta 868 clocks/bit (100 MHz / 115200 baud), kemudian selftest
`tsr_link.py`. Log dan hasil kompilasi disimpan di `build/p5_sim/`.
Runner memberi exit code nonzero jika kompilasi/simulasi gagal, timeout,
atau penanda kelulusan tidak ditemukan.

Cakupan tes:

- UART: byte berurutan tanpa jeda tambahan, stop bit LOW, break panjang,
  glitch saat break, pemulihan setelah idle, glitch start pendek, dan
  pulsa valid sepanjang satu clock.
- Komunikasi: gambar live, checksum salah, command tidak dikenal,
  timeout dan pemulihan, 16 gambar tersimpan, serta checksum dengan stop
  bit invalid. Frame terakhir harus tidak memulai CNN atau mengirim balasan;
  setelah timeout, frame valid berikutnya harus berhasil.
- Kegagalan pemeriksaan (termasuk nilai X/Z) dan watchdog testbench memakai
  `$fatal(1, ...)`. Runner juga memeriksa penanda lulus dan pesan kegagalan,
  karena beberapa versi lama `vvp` Windows tetap memberi exit code 0 setelah
  `$fatal`. Gunakan runner ini untuk pemeriksaan otomatis.

UART membuang byte dengan stop bit LOW dan menunggu satu bit penuh HIGH
sebelum menerima start berikutnya. Tidak ada balasan khusus framing-error;
frame yang kekurangan byte dibuang oleh timeout `frame_ctrl`, lalu laptop
mengulang permintaan sesuai mekanisme yang sudah ada.

Waveform komunikasi bersifat opsional: tambahkan `-DDUMP` saat mengompilasi
`tb_comm` untuk menghasilkan `tb_comm.vcd` pada direktori kerja simulator.
Tes ini belum menggantikan pengujian board fisik atau integrasi CNN nyata.
