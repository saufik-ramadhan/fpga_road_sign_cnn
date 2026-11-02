# Kandidat rambu 32×32

Paket `models/p2-int-32-v1/` digunakan oleh
[Traffic Sign Visual Lab](../../apps/traffic_sign_visualizer/README.md).
Ini eksperimen dari pipeline historis v1: input 32×32, satu conv, bobot int8,
accumulator/bias/skor int32. Baseline board tetap `p2-doc-int-v2` 16×16/int24.

Paket model disimpan utuh: `parameters.npz`, `contract.json`, `metrics.json`,
`MEMORY_LAYOUT.md`, `mem/`, README, `.gitattributes`, dan `checksums.json`.
Perpindahan folder mempertahankan byte paket dan checksum aslinya.

Reproduksi dan metrik yang tercatat ada pada README aplikasi dan paket model.
Kuantisasi/publisher historis mendukung ukuran 16 dan 32; document-v2 memakai
entry point sendiri. Model 32×32 belum diuji pada RTL, UART atau FPGA. Akurasinya
tidak bisa langsung dibandingkan dengan document-v2 karena preprocessing dan
pengaturan eksperimen berbeda.
