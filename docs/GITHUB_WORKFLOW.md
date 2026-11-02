# Pengembangan tim: workspace, AI agent, testing dan PR

Satu tugas memiliki satu pemilik, satu branch dan satu workspace. Anggota tim
mengembangkan bagian internalnya secara independen dengan kontrak integrasi
yang sama. Keputusan yang perlu diketahui tim masuk ke repo/Issue/PR agar tidak
bergantung pada riwayat chat pribadi.

## 1. Pembagian kerja dan batas modul

| Peran / pemilik | Area utama | Kontrak yang dipakai anggota lain | Reviewer terkait |
|---|---|---|---|
| P1 / Saufik | rtl/control/, rtl/top/, constraints/, build board | cnn_core, urutan start/done, clock/reset dan pin | Pemilik subsistem yang disambungkan |
| P2 / Rubi | reference_model/, parameter dan golden vectors | paket model, preprocessing, layout memori dan lebar numerik | P3/P4; P5 jika preprocessing berubah |
| P3 / Mahardika | rtl/feature_extraction/, tests/rtl/p3/ | feature_extraction: pixel read dan fmap read satu clock | P4 serta P1 |
| P4 / Kania | rtl/classification/, display di rtl/board/ | classifier: fmap -> scores/class; CHW dan signed24 | P3 serta P1 |
| P5 / Dika | rtl/communication/, rtl/input/, apps/board_hmi/, tests/rtl/p5/ | comm_top, input gambar, frame dan balasan UART | P1; P2 jika input/preprocessing berubah |

`rtl/files.f`, `tests/rtl/integration/`, top/core, dokumentasi dan konfigurasi CI
adalah titik bersama: ubah hanya yang diperlukan tugas dan jelaskan dampaknya
pada PR. Tabel ini menetapkan tanggung jawab review, bukan melarang perbaikan
lintas folder. Visualizer/eksperimen software berada di apps/ dan experiments/;
perubahannya tidak otomatis mengganti baseline FPGA.

Sebelum mulai, tulis di Issue atau draft PR: tujuan, pemilik, folder yang disentuh,
kriteria selesai, reviewer dan dependensi. Satu tugas harus dapat diverifikasi
sendiri. Contoh: optimasi internal FC dengan port/output tetap, bukan sekaligus
mengganti model, protokol UART dan tampilan HMI.

## 2. Konteks bersama untuk manusia dan AI

Buka workspace pada root repo dan baca berurutan:

1. [AGENTS.md](../AGENTS.md): aturan kerja dan invariant bersama.
2. [README proyek](../README.md) dan [status/struktur](README.md): navigasi dan kondisi baseline.
3. [Hardware](HARDWARE.md) atau panduan kategori tugas; untuk model baca juga
   contract.json, params.vh, MEMORY_LAYOUT.md dan checksums.json paket terpilih.
4. [Testing](../tests/README.md): perintah yang benar dan cakupan buktinya.
5. Issue/PR tugas serta diff terhadap base yang digunakan.

AGENTS.md menjadi satu sumber instruksi proyek. CLAUDE.md hanya mengarahkan ke
file itu. Untuk agent lain, minta eksplisit membaca AGENTS.md; jangan menganggap
semua produk otomatis memuat nama file yang sama. Aturan pribadi/global agent
juga dapat memengaruhi sesi: minta agent menyebut instruksi yang aktif dan
laporkan jika bertentangan dengan aturan proyek. Instruksi pengguna tetap berlaku.

Codex membaca AGENTS.md sebagai instruksi repo saat memulai pekerjaan; setelah
mengubah instruksi atau berpindah workspace, mulai sesi baru atau minta agent
membacanya ulang. Rujukan: [official OpenAI documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

Konteks yang harus sama adalah **commit dasar, kontrak dan kriteria selesai**.
Model AI yang sama tidak menjamin penafsiran yang sama. Setiap agent perlu
memeriksa source dan hasil tes pada checkout-nya, bukan mengandalkan chat lama.
Status historis di dokumentasi hanya bukti untuk commit/metode yang disebut.

## 3. Inisialisasi workspace

Pasang Git, Python **3.11**, serta Icarus Verilog (`iverilog` dan `vvp` pada PATH).
Gunakan versi tool yang sama dengan tim jika membandingkan resource/timing.
Referensi build board saat ini adalah **Vivado 2026.1**, Basys 3
**xc7a35tcpg236-1**, clock **100 MHz**. Vivado tidak dibutuhkan untuk simulasi.
GitHub CLI (`gh`) opsional; PR juga bisa dibuat lewat browser.

```powershell
git clone https://github.com/saufik-ramadhan/fpga_road_sign_cnn.git
cd fpga_road_sign_cnn
git config user.name "Nama Anda"
git config user.email "email-anda@example.com"
git fetch origin
git switch main
git pull --ff-only origin main
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python scripts/check_workspace.py
```

Jalankan dari root repo. Perintah Python pada bagian selanjutnya boleh diganti
`.\.venv\Scripts\python` agar interpreter selalu benar tanpa aktivasi shell.
Di Linux, gunakan `python3.11 -m venv .venv` dan `.venv/bin/python`.
requirements-dev.txt mencakup dependency verifikasi RTL dan aplikasi; training
serta pytest model penuh memerlukan tambahan:

```powershell
.\.venv\Scripts\python -m pip install -r reference_model/requirements.txt
.\.venv\Scripts\python scripts/check_workspace.py --full-model
```

Untuk pekerjaan top/board, tambahkan folder bin Vivado ke PATH pada terminal
tersebut, lalu jalankan `python scripts/check_workspace.py --vivado`. Alternatif
build adalah menjalankan script Tcl dari Vivado Tcl Shell. Jangan menyalin path
instalasi/COM pribadi ke source. Dataset dibutuhkan untuk training/evaluasi yang
memang memakainya; golden vectors terpublikasi cukup untuk simulasi baseline.

Pemeriksa workspace melaporkan root, HEAD, branch, origin/main, versi dependency,
ketersediaan tool, manifest RTL dan SHA256 empat paket model. Ini pemeriksaan
read-only, bukan instalasi atau tes fungsional. Working tree yang berubah hanya
dilaporkan agar pekerjaan pengguna terjaga. Versi dependency menggunakan rentang
pada manifest, belum lockfile lintas OS; catat versi aktual dalam bukti PR.

Sebelum onboarding, pastikan main sudah memuat baseline yang disepakati. Jika
fitur integrasi masih di branch/PR lain, nyatakan base sementara tersebut dan
SHA-nya. Jangan menganggap clone main sudah memuat commit lokal rekan tim.

## 4. Mulai tugas dan isolasi pekerjaan

Untuk satu tugas dalam checkout ini, simpan pekerjaan yang masih aktif pada
branch-nya sebelum berpindah. Jangan reset/stash/membuang perubahan rekan diam-diam.

```powershell
git status --short
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c codex/p4-fc-optimization
git rev-parse HEAD
```

Jika beberapa tugas/agent berjalan bersamaan di satu komputer, gunakan worktree
terpisah agar branch, file edit, simulator dan output build tidak saling menimpa:

```powershell
git fetch origin
git worktree add ../fpga-p4-fc -b codex/p4-fc-optimization origin/main
cd ../fpga-p4-fc
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

Pilih salah satu cara di atas, bukan menjalankan keduanya untuk nama branch yang
sama. Setiap worktree mempunyai .venv dan build/ sendiri; jangan menjalankan dua
runner yang menulis folder output yang sama dalam satu worktree. Gunakan nama
branch yang unik per tugas. Perbedaan komputer anggota tim sudah memberi isolasi
filesystem, tetapi tetap perlu branch sendiri. Jangan memodifikasi main langsung.

## 5. Brief yang diberikan ke AI agent

Salin brief berikut ke sesi baru dan isi bagian dalam tanda kurung siku. Teks
ini cukup menjadi prompt/Issue; tidak perlu membuat Markdown per sesi di repo.

```text
Baca AGENTS.md, docs/GITHUB_WORKFLOW.md dan panduan kategori tugas.
Peran/pemilik: [P1..P5 / nama].
Tugas dan masalah konkret: [...].
Base branch/commit serta PR dependensi: [...].
Area perubahan: [...].
Kontrak yang harus dipertahankan: [port, latency, layout, model/protokol].
Kriteria selesai yang dapat diuji: [...].
Tes yang perlu dijalankan: [...].
Izin remote: [lokal saja / push branch tertentu / buat draft PR tertentu].

Sebelum edit, laporkan branch/HEAD, perubahan lokal yang sudah ada, instruksi
aktif, kontrak terkait dan rencana tes. Kerjakan sampai hasil bisa direview.
Jika antarmuka perlu berubah, jelaskan dampak dan perbarui consumer/test/docs
sesuai scope. Pada akhir tugas, laporkan commit, hasil tes, batas bukti dan
pekerjaan tersisa. Jangan menganggap chat sebelumnya sebagai status checkout.
```

Contoh kriteria P4: seluruh skor/prediksi golden tetap identik, signed overflow
tetap diperiksa, port classifier tetap sama; perubahan latency dicatat dan tes
yang mengunci latency diperbarui hanya bila perubahan itu bagian dari tugas.

## 6. Pengembangan independen dan perubahan kontrak

Implementasi internal dapat diubah tanpa menunggu anggota lain selama kontrak
publik tetap dipenuhi. Gunakan golden vectors/testbench sebagai lawan uji;
jangan mengubah golden agar mengikuti RTL yang salah. Dummy CNN hanya harness
komunikasi; top_basys3 memakai CNN nyata.

Jika port, reset, latency memori, ukuran gambar, skala/bias, class order atau
frame UART berubah, tulis kontrak sebelum/bersama implementasi: nilai lama/baru,
pemakai terdampak, strategi kompatibilitas dan tes. Libatkan pemilik serta
consumer pada review. Pilih satu PR lengkap yang memperbarui kedua sisi, atau
PR kontrak/adaptor terlebih dahulu lalu PR consumer yang jelas dependensinya.
Untuk baseline model baru, buat paket versi baru; pertahankan paket tersegel.

Urutan dependensi normal: **P2 kontrak/golden -> P3/P4/P5 boundary -> P1 integrasi**.
Kontrak yang sudah dibekukan memungkinkan implementasi P3, P4 dan P5 berjalan
bersamaan. Jika tugas membutuhkan PR belum merge, tunggu merge atau buat branch
turunan dengan base PR tersebut, tulis dependensinya, dan ubah base ke main
setelah parent merge. Hindari menyalin file acak dari branch rekan.

## 7. Matriks pengujian

Jalankan pemeriksaan workspace lebih dahulu. Perintah di tabel memakai `python`
dari environment tugas. Detail suite: [tests/README.md](../tests/README.md).

| Area perubahan | Pemeriksaan minimal sebelum meminta review |
|---|---|
| P3 | python tests/run_rtl_tests.py --suite p3; --suite integration |
| P4 / controller | python tests/run_rtl_tests.py --suite integration; seluruh RTL jika boundary berubah |
| P5 / input / protokol | python tests/run_rtl_tests.py --suite p5; --suite integration; selftest client |
| P2 / preprocessing / parameter | python -m pytest reference_model/tests -q; seluruh RTL bila memengaruhi baseline board |
| Top / XDC / manifest / boundary bersama | python tests/run_rtl_tests.py; build Vivado di bawah |
| HMI / UART client | python apps/board_hmi/tsr_link.py --selftest; uji GUI terkait; tes P5/integrasi jika protokol berubah |
| Inspector rambu | python -m unittest discover -s apps/traffic_sign_visualizer/tests -v |
| MNIST | python -m unittest discover -s experiments/mnist_digit/tests -v |
| Dokumentasi / launcher / workflow | periksa path dan perintah yang berubah; jalankan preflight/launcher terkait, tidak perlu ulang sintesis tanpa perubahan hardware |

```powershell
python tests/run_rtl_tests.py
vivado -mode batch -source scripts/build_basys3.tcl
git diff --check
```

Build memeriksa timing dan pin, menghasilkan bitstream di build/basys3/, tetapi
tidak memprogram board. Jika Vivado/board tidak tersedia, tulis belum diuji;
reviewer P1 dapat menjalankan pemeriksaan yang kurang sebelum status ready.
Catat commit, versi tool/model, metode, jumlah input/run dan hasil sebenarnya.
Tes yang skip tidak berarti lulus. PASS golden, akurasi validation/test model,
metrik synthesis dan hasil board fisik harus dilaporkan terpisah.

Workflow [.github/workflows/checks.yml](../.github/workflows/checks.yml) menjalankan
preflight, seluruh RTL dan kedua tes inspector pada PR ke main serta push main,
dengan Python 3.11 dan Icarus pada Linux. Log tersedia sebagai artifact CI.
CI ini tidak memasang PyTorch, menjalankan training/pytest model penuh, menjalankan
Vivado, membuka GUI atau menguji board. Untuk perubahan tersebut, sertakan bukti
sesuai tabel. Konfigurasi baru perlu dipush agar GitHub benar-benar menjalankannya.

## 8. Commit, push dan pembuatan PR

Periksa diff dan stage hanya file terkait; jangan memasukkan build/, environment,
dataset atau konfigurasi COM pribadi. Contoh berikut untuk tugas RTL:

```powershell
git status --short
git diff
git diff --check
git add rtl/classification/ tests/rtl/integration/ docs/HARDWARE.md
git diff --cached
git commit -m "perf: simplify FC datapath while preserving golden scores"
git push -u origin codex/p4-fc-optimization
```

Buka GitHub -> Pull requests -> New pull request, pilih base main dan branch tugas.
Gunakan draft jika masih ada dependensi/tes yang kurang. Template PR otomatis
meminta tujuan, dampak integrasi, bukti tes dan reviewer. Untuk gh, tulis isi PR
ke file lokal dengan newline yang benar, lalu:

```powershell
gh pr create --draft --base main --head codex/p4-fc-optimization --title "Optimize FC datapath" --body-file build/pr-body.txt
```

AI hanya push/membuat PR jika diizinkan pada tugas; pembuatan panduan ini tidak
berarti ada PR yang dikirim otomatis. Bukti lokal tidak sama dengan hasil CI.
Template PR dirujuk dari [GitHub Docs](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository).

## 9. Review, sinkronisasi dan merge

Reviewer utama adalah pemilik modul/consumer pada tabel pembagian kerja. Penulis
memperbaiki temuan di branch yang sama lalu push commit tambahan. Pemeriksaan
harus dilakukan pada HEAD terbaru; komentar lama diselesaikan setelah perbaikannya
diverifikasi, bukan hanya karena ada commit baru.

Sebelum ready/merge, ambil main terbaru dan gabungkan ke branch tugas dengan
working tree yang tersimpan. Hindari rewrite history branch yang sudah dibagikan:

```powershell
git fetch origin
git merge origin/main
```

Jika konflik muncul, cocokkan maksud kedua perubahan dan libatkan pemilik bila
kontraknya bertentangan. Ulangi tes yang terdampak dan commit resolusi. Merge
hanya setelah review terkait, CI dan bukti tambahan yang diwajibkan selesai.
Setelah merge, pull main terbaru dan buat branch baru untuk tugas berikutnya.
Hapus branch/worktree hanya setelah memastikan perubahan sudah masuk dan tidak
ada pekerjaan lokal yang tertinggal.

Admin dapat mengaktifkan proteksi main: PR wajib, satu approval independen,
status `rtl-and-apps` wajib dan review untuk perubahan terakhir. Ini rekomendasi
pengaturan GitHub; file workflow/template tidak otomatis mengaktifkan proteksi
atau reviewer assignment. Username GitHub pemilik belum dipetakan sehingga
CODEOWNERS belum dibuat.

## 10. Definisi selesai dan handoff

Tugas selesai ketika perilaku sesuai kriteria, consumer/kontrak konsisten, tes
relevan lulus, kategori docs mutakhir, diff fokus dan PR dapat direview dengan
bukti yang cukup. Jangan memakai jumlah commit atau jawaban AI sebagai bukti.

Handoff cukup berisi: tujuan, branch/commit/base, file/kontrak yang berubah,
perintah dan hasil tes, keterbatasan, dependensi serta langkah berikutnya.
Letakkan pada PR/Issue dan perbarui panduan kategori untuk keputusan permanen.
Agent berikutnya membaca handoff lalu memeriksa ulang checkout-nya sendiri.
