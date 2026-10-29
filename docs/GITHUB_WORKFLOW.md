# Panduan GitHub Workflow Sederhana

Panduan kolaborasi untuk repo [fpga_road_sign_cnn](https://github.com/saufik-ramadhan/fpga_road_sign_cnn), menggunakan alur [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow).

**Alur kerja:** ambil `main` terbaru → buat branch → edit dan uji → commit → push → pull request → review → merge ke `main`.

## 1. Persiapan awal

Pastikan Git sudah terpasang dan akun GitHub memiliki akses tulis ke repo. Saat push, selesaikan autentikasi GitHub jika diminta.

Jika belum memiliki repo di komputer, jalankan:

```powershell
git clone https://github.com/saufik-ramadhan/fpga_road_sign_cnn.git
cd fpga_road_sign_cnn
```

Jika repo sudah ada, cukup buka terminal di folder repo tersebut. Semua perintah berikut dijalankan dari folder utama repo.

Atur identitas commit sekali untuk repo ini; ganti contoh dengan identitas sendiri:

```powershell
git config user.name "Nama Anda"
git config user.email "email-anda@example.com"
```

## 2. Mulai pekerjaan dari branch baru

Periksa `git status` terlebih dahulu. Jika masih ada pekerjaan sebelumnya, simpan melalui commit pada branch pekerjaan tersebut sebelum berpindah branch.

```powershell
git status
git switch main
git pull --ff-only origin main
git switch -c codex/rtl-convolution
```

Ganti `codex/rtl-convolution` sesuai tugas. Gunakan satu branch untuk satu pekerjaan yang jelas, misalnya `codex/reference-model`, `codex/fix-uart`, atau `codex/docs-setup`. Untuk alur tim ini, usulkan perubahan ke `main` melalui pull request.

## 3. Edit, periksa, dan commit

Letakkan perubahan sesuai struktur repo:

| Folder | Isi yang disarankan |
| --- | --- |
| `reference_model/` | Model referensi dan evaluasi perangkat lunak |
| `rtl/` | Modul RTL dan testbench FPGA |
| `docs/` | Panduan, diagram, dan catatan pengujian |
| `build/` | Hasil build lokal; sudah diabaikan oleh Git |

Uji bagian yang diubah sebelum commit. Contoh: simulasi testbench untuk RTL atau evaluasi model untuk perubahan model referensi. Saat panduan ini dibuat, repo belum menyediakan kode maupun perintah pengujian otomatis; catat cara dan hasil pengujian yang benar-benar dilakukan.

```powershell
git status
git diff
```

Tambahkan hanya file terkait. Contoh berikut untuk pekerjaan pada `rtl/`; sesuaikan jalurnya dengan file atau folder yang diubah:

```powershell
git add rtl/
git diff --cached
git commit -m "feat: tambahkan modul convolution"
git push -u origin codex/rtl-convolution
```

Pesan commit sebaiknya menjelaskan hasil perubahan. Awalan sederhana yang dapat dipakai: `feat:` untuk fitur, `fix:` untuk perbaikan, dan `docs:` untuk dokumentasi.

## 4. Buka pull request dan lakukan review

1. Buka repo di GitHub, lalu pilih **Compare & pull request** untuk branch yang baru dikirim. Alternatifnya, gunakan tab **Pull requests** → **New pull request**.
2. Pilih **base: `main`** dan **compare: `codex/rtl-convolution`** sesuai nama branch pekerjaan.
3. Isi judul, ringkasan perubahan, serta cara dan hasil pengujian. Jika belum diuji, tulis alasannya.
4. Buat pull request dan minta anggota tim terkait melakukan review. Untuk perubahan integrasi, libatkan penanggung jawab integrasi sistem.
5. Jika ada revisi, edit pada branch yang sama, lalu ulangi `git add`, `git commit`, dan `git push`. Pull request akan ikut diperbarui.
6. Setelah review selesai dan konflik terselesaikan, anggota yang memiliki izin dapat melakukan merge. Hapus branch di GitHub setelah merge jika sudah tidak dipakai.

Contoh deskripsi pull request:

```text
Perubahan:
- Menambahkan modul convolution pada rtl/.

Pengujian:
- [Isi perintah atau langkah yang dijalankan dan hasilnya.]

Catatan integrasi:
- [Isi perubahan antarmuka, format data, atau keterbatasan jika ada.]
```

## 5. Ambil hasil merge

Setelah pekerjaan lokal tersimpan dan pull request sudah di-merge:

```powershell
git switch main
git pull --ff-only origin main
```

Untuk tugas berikutnya, buat branch baru dari `main` yang sudah diperbarui.

## Kebiasaan tim

- Buat pull request dengan perubahan kecil agar mudah diperiksa.
- Sertakan perubahan antarmuka RTL dan format data dalam deskripsi agar anggota lain bisa menyesuaikan modulnya.
- Periksa daftar file sebelum commit. Jangan sertakan kredensial, dataset besar, atau hasil build; tambahkan aturan `.gitignore` bila diperlukan. Saat ini hanya folder `build/` di root yang diabaikan.
- Jika `git pull --ff-only` gagal atau ada konflik, baca pesan Git dan koordinasikan penyelesaiannya dengan pemilik perubahan. Hindari force push pada branch bersama.

Panduan ini membahas alur kolaborasi Git dan GitHub. Otomatisasi GitHub Actions dapat ditambahkan setelah perintah build dan pengujian proyek tersedia.
