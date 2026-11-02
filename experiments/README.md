# Eksperimen software

- [Traffic sign 32×32](traffic_sign_32/README.md): kandidat riset/visualisasi.
- [MNIST](mnist_digit/README.md): demo digit 0–9 untuk belajar CNN.

Paket model eksperimen tidak ditempatkan di `reference_model/models/`, karena
runner P3 memindai folder tersebut untuk model yang didukung RTL 16×16.
Training cache, checkpoint dan output per-run tetap di `build/`.
