# Board HMI dan UART P5

Implementasi aplikasi laptop: `hmi_live.py` dan `tsr_link.py` dalam folder ini.
Perintah lama dari root repo tetap bekerja:

```powershell
python -m pip install -r apps/board_hmi/requirements.txt
python hmi_live.py
python tsr_link.py --selftest
python tsr_link.py COM8 --image sign.png
```

Ganti COM8 sesuai board. Implementasi juga dapat dijalankan langsung dengan
`python apps/board_hmi/hmi_live.py` atau `python apps/board_hmi/tsr_link.py`.
Tkinter disertakan oleh instalasi Python Windows yang umum.

- LIVE memakai UART; SW15 harus sesuai mode board. Pengujian `--dummy` hanya
  cocok dengan dummy CNN pada top P5, bukan classifier rambu lengkap.
- STORED pada HMI saat ini menampilkan answer key/placeholder lokal; ini bukan
  hasil baru dari FPGA. Lihat label peringatan pada aplikasi.
- Letakkan aset opsional `logos/`, `stored/` dan `stored_answers.json` di folder
  aplikasi ini. `hmi_settings.json` bersifat lokal dan diabaikan Git.
- UART saat ini menggunakan reply 32 byte/four-byte cycles. Target metadata P2
  document-v2 menyebut 31 byte/three-byte cycles; sinkronisasi protokol dan
  preprocessing tetap pekerjaan integrasi. Jangan mengubah satu endpoint saja.

[Tes dan protokol P5](../../docs/p5_communication.md).
