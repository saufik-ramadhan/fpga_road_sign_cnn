# Modul Verilog

| Kelompok | Modul | Pemilik |
|---|---|---|
| Feature extraction | `conv_engine.v`, `conv_wrom.v`, `requant_relu.v`, `fmap_ram.v` | P3 |
| Komunikasi dan input | `uart_rx.v`, `uart_tx.v`, `frame_ctrl.v`, `image_input.v` | P5 |

[Tes P3 dan sintesis](tb/README.md) · [Tes P5 dan dummy top](../tb/README.md).
Nama/path modul yang dipakai flow Vivado dan simulator dipertahankan.
Controller CNN lengkap, pooling, FC, argmax dan top/XDC produksi belum tersedia
di main pada peninjauan 2 November 2026.
