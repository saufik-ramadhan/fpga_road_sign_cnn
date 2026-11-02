# Verifikasi P5 — komunikasi dan input

```powershell
python tb/run_p5_tests.py
```

- `tb_uart_rx.v`: framing, break, glitch dan recovery UART.
- `tb_comm.v`: frame, error, timeout, stored/live dan dummy CNN.
- `comm_top.v`: penghubung blok input/komunikasi untuk integrasi.
- `dummy_cnn.v`: placeholder checksum piksel, bukan classifier rambu.
- `top_p5_test.v`: top sementara untuk demonstrasi komunikasi.

Output di `build/p5_sim/`. [Panduan pengujian](../docs/p5_communication.md).
Tes P3 berada di [rtl/tb/](../rtl/tb/README.md).
