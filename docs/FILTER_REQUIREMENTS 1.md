# Task 1 — Daftar Kebutuhan Filter

**Tugas:** mendaftar semua filter yang dibutuhkan halaman KOL Discovery, beserta bentuk kontrol dan pilihannya.

**Yang belum dikerjakan di sini:** mengecek datanya ada atau tidak — itu Task 2.
**Terakhir diperbarui:** 2026-09-07

> **STATUS 2026-09-07.** Daftar kebutuhan di dokumen ini tidak berubah. Yang berubah
> hanya dua hal setelah implementasi:
>
> * **Verified dihapus dari Discovery.** Badge verified platform tidak dipertahankan
>   sebagai filter/field terpisah — Discovery cuma punya **Connected**.
> * **Growth sudah tersedia**, tapi bukan "Growth 30 hari". Yang terkirim adalah
>   perubahan follower **sejak snapshot terakhir** (10–13 hari), berlabel
>   **"Sejak Snapshot Terakhir"**.
>
> Filter yang sudah benar-benar jalan di Discovery: Cari nama · Platform · Kategori ·
> Tier · Minimum follower · Minimum engagement rate · Maksimum rate card · Connected ·
> **Growth**. Sisanya masih menunggu data — lihat Task 3 dan Task 4.

---

## Kesimpulan singkat

Jumlah filter yang harus didukung: **40**.

Awalnya kami menghitung 32, karena yang dilihat adalah file contoh (`app/AUTOME_2.html`).
Ternyata file itu cuma **tiruan**: isinya 8 KOL palsu dan tidak pernah menghubungi database.
Setelah dicek ke **aplikasi yang sebenarnya**, daftarnya berbeda.

Jadi yang dipakai sekarang:

| Sumber | Jumlah filter | Status |
|---|---:|---|
| Aplikasi asli — halaman Creator Database | 18 | Dipakai sekarang |
| Aplikasi asli — halaman My Creators & Smart Discovery | 2 | Dipakai sekarang |
| File contoh, belum ada di aplikasi | 20 | Rencana ke depan |
| **Total** | **40** | |

---

## Filter yang ada di aplikasi sekarang

Dikelompokkan seperti tampilan di layar.

### Profil Kreator

| Filter | Bentuk kontrol | Pilihan |
|---|---|---|
| Cari nama | Kotak ketik | Teks bebas — dicari di username, nama, dan bio |
| Platform | Tombol pilihan | Instagram · TikTok · Facebook |
| Kategori | Tombol pilihan | 9 kategori (lihat catatan di bawah) |
| Tier / ukuran kreator | Tombol pilihan | Nano · Micro · Mid-Tier · Macro · Mega |
| Minimum follower | Penggeser | 0 sampai 10 juta |
| Minimum engagement rate | Penggeser | 0% sampai 10% |
| Maksimum rate card | Penggeser | Rp 500rb sampai Rp 1jt |
| Connected | Tombol nyala/mati | Kreator yang sudah menghubungkan akunnya — `platform_user_id` **dan** `oauth_token` terisi. Hasil hari ini 0, dan itu benar |
| Growth | Pilihan preset | Naik · Datar (0%) · Turun · di atas 0,5% · di atas 1% — **sejak snapshot terakhir**, bukan 30 hari |

### Audiens

| Filter | Pilihan |
|---|---|
| Gender audiens | Mayoritas perempuan · Mayoritas laki-laki |
| Lokasi audiens | Daftar kota, diambil dari data |
| Kualitas audiens | Tinggi (85+) · Bagus (75+) · Di bawah 75 |

### Konten

| Filter | Pilihan |
|---|---|
| Format konten | Reels · Carousel · Feed · Video |
| Rasio konten berbayar | Penggeser |

### Performa

| Filter | Pilihan |
|---|---|
| Engagement rate | Bagus (≥3%) · Tinggi (≥5,5%) |
| Rata-rata views | 150rb+ · 300rb+ |
| Save rate | Tinggi (≥5%) |
| Share rate | Tinggi (≥1,8%) |

### Lainnya

| Filter | Halaman | Catatan |
|---|---|---|
| Profiling Status | My Creators | Ready / Profiling / Failed — **datanya tidak ada di database**, lihat Task 5 |
| Harga lebih murah dari referensi | Smart Discovery | Butuh data rate card yang belum terisi |

---

## Empat hal yang berubah setelah cek ke aplikasi asli

**1. Baseline pindah dari file contoh ke aplikasi asli.**
File contoh tidak pernah membaca database, jadi daftar filternya cuma rancangan.

**2. Tujuh filter yang tadinya dianggap "sudah dibuang" ternyata masih dipakai.**
Minimum Followers, Minimum ER, dan Max Rate Card sudah jalan.
Min Authenticity, Min Brand Fit, Max Paid Ratio, dan Min Campaigns tampil di layar tapi masih dimatikan (abu-abu).

**3. Dua filter baru yang tidak ada di file contoh:**
Profiling Status (My Creators) dan Lower Price than Reference (Smart Discovery).

**4. Kategori bukan lagi 5, tapi 9.**
Dulu ada 5 pilihan yang ditulis langsung di kode (Fitness, Lifestyle, Beauty, Food, Tech).
Sekarang ada 9 kategori resmi: **Lifestyle · Beauty · Fashion · Food · Fitness · Entertainment · Moms · Gen Z · Tech**.
Kesembilan kategori ini dibuat dengan mengelompokkan 28 nama kategori mentah di database.

---

## Catatan tentang Platform

Ada tiga daftar yang isinya beda-beda, dan ini perlu diputuskan orang produk:

| Sumber | Isi |
|---|---|
| File contoh | Instagram · TikTok · **YouTube** |
| Aplikasi asli | Instagram · TikTok · **Facebook** |
| Database | Instagram (3.409) · TikTok (4.087) — **tidak ada YouTube maupun Facebook** |

---

## Lanjutannya ke mana

- Filter ini dipetakan ke tabel database di **Task 2**
- Dicek berapa KOL yang datanya benar-benar ada di **Task 3**
- Ditentukan sumber final tiap filter di **Task 4**
- Rancangan teknisnya di **Task 5** (`KOL_DISCOVERY_TASK5_DESIGN.md`)
