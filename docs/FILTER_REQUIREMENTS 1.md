# Task 1 — Daftar Kebutuhan Filter

**Tugas:** mendaftar semua filter yang dibutuhkan halaman KOL Discovery, beserta bentuk kontrol dan pilihannya.

**Yang belum dikerjakan di sini:** mengecek datanya ada atau tidak — itu Task 2.
**Terakhir diperbarui:** 2026-09-09

> **STATUS 2026-09-07 — sebagian DIGANTIKAN oleh blok 2026-09-09 di bawah.**
> Poin "Verified dihapus" sudah tidak berlaku; sisanya masih benar.
>
> Daftar kebutuhan di dokumen ini tidak berubah. Yang berubah
> hanya dua hal setelah implementasi:
>
> * ~~**Verified dihapus dari Discovery.**~~ **DIBALIK 2026-09-09** — Verified kembali
>   sebagai sumbu terpisah dari Connected, dengan sumber baru
>   (`l2_gold.kol_profile_card.is_verified`, 572 KOL). Lihat blok 2026-09-09.
> * **Growth sudah tersedia**, tapi bukan "Growth 30 hari". Yang terkirim adalah
>   perubahan follower **sejak snapshot terakhir** (10–13 hari), berlabel
>   **"Sejak Snapshot Terakhir"**.
>
> Filter yang jalan per 7 September: Cari nama · Platform · Kategori · Tier ·
> Minimum follower · Minimum engagement rate · Maksimum rate card · Connected ·
> **Growth**. Daftar per 9 September bertambah **Verified · Last Updated · Agency** —
> lihat blok di bawah. Sisanya masih menunggu data — lihat Task 3 dan Task 4.

---

> ## STATUS 2026-09-09 — dua filter baru jalan, satu keputusan dibalik
>
> Diverifikasi terhadap kode yang **sudah ter-commit**, bukan working tree:
> `scrapper-project` @ `fa3af27` (main) dan `autometric` @ `232da34` (`engkol_v1`).
> Angka database berasal dari pengukuran read-only 8 September 2026.
>
> ### 1. Verified KEMBALI ke Discovery — keputusan 7 September dibalik
>
> Blok status di atas menulis *"Verified dihapus dari Discovery"*. **Itu tidak lagi
> berlaku.** Sejak `232da34`, Discovery punya **dua sumbu terpisah** dan keduanya
> dirender:
>
> | Sumbu | Arti | Sumber | Hasil terukur | Ikon |
> |---|---|---|---:|---|
> | **Connected** | kreator menghubungkan akun lewat OAuth | `social_account.platform_user_id` **dan** `oauth_token` | **0** | rantai (`link`) |
> | **Verified** | badge platform (centang biru) | `l2_gold.kol_profile_card.is_verified` | **572** | centang |
>
> Yang berubah bukan cuma keputusan produk, tapi **sumbernya**. Verified sekarang
> **tidak** memakai `kol_directory.verified_status` (454 baris — sumber yang dulu
> ditolak). Ia memakai badge asli dari platform yang baru diangkat ke L1/L2 oleh
> `fa3af27`: `raw_payload->>'verified'` untuk Instagram dan
> `l0_harmonization.tiktok_profile.is_verified` untuk TikTok.
>
> Karena 572 verified dan 0 connected, **salah satu tidak akan pernah bisa mewakili
> yang lain** — itu alasan keduanya dipertahankan terpisah.
>
> ### 2. Dua filter baru yang belum pernah tercatat di dokumen ini
>
> | Filter | Kontrol | Parameter | Sumber |
> |---|---|---|---|
> | **Last Updated** | preset jumlah hari | `?updatedWithin=<hari>` | `kol_directory.last_refreshed_at` |
> | **Agency** | daftar ber-count (facet) | `?agency=<nama>` | `agency_kol_accounts` + `agencies` (7.684 dari 7.718) |
>
> ### 3. Daftar filter yang benar-benar jalan hari ini — **12**
>
> Cari nama · Platform · Kategori · Tier · Minimum follower · Minimum engagement
> rate · Maksimum rate card · Connected · **Verified** · Growth · **Last Updated** ·
> **Agency**
>
> Dua catatan jujur tentang daftar itu:
>
> * **Maksimum rate card aktif tapi selalu mengembalikan 0 hasil.**
>   `l1_silver.unified_rate_card` masih 0 baris (diukur 8 Sep). Begitu slider
>   digeser dari maksimum, direktori jadi kosong total. Ini bukan filter yang belum
>   dibuat — ini filter yang bekerja di atas tabel kosong.
> * **Cari nama hanya mencari `username`.** Rancangan di tabel bawah menyebut
>   username + nama + bio; endpoint yang di-ship (`kolDirectory.ts`) hanya
>   `b.username ILIKE`. Pencarian tiga-field memang ada, tapi di implementasi lain:
>   `db.search_kol_directory()` di repo ini (CLI `search_kol.py`), bukan di halaman
>   Discovery.
>
> ### 4. Kategori: chip-nya 15, bukan 9
>
> Filter dan facet sekarang memakai `COALESCE(kol_categories.taxonomy_key, name)`.
> 6 dari 28 nama kategori mentah belum punya `taxonomy_key`, jadi mereka muncul apa
> adanya sebagai chip sendiri — **9 taksonomi resmi + 6 nama belum terpetakan = 15
> chip**. Ini disengaja: tanpa `COALESCE`, 6 kategori itu (dan 20 KOL yang
> memakainya) tidak akan bisa dijangkau chip mana pun.
>
> ### 5. Yang masih persis seperti tertulis
>
> Growth tetap **"Sejak Snapshot Terakhir"** (10–13 hari), bukan 30 hari, dan tetap
> 25 KOL. Growth 30 hari masih belum ada — scraping berhenti sejak 2026-08-28.
> Filter Audiens, Konten, dan Performa (selain ER) masih **belum ada kontrolnya di
> UI**, karena backend-nya memang belum bisa menyaringnya.
>
> Pemetaan lengkap filter → tabel → endpoint → UI ada di `docs/BACKEND_PLAN.md`.

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
| **Verified** *(kembali 2026-09-09)* | Tombol nyala/mati | Badge platform dari `l2_gold.kol_profile_card.is_verified` — **572 KOL**. Sumbu terpisah dari Connected, ikonnya berbeda |
| **Last Updated** *(baru 2026-09-09)* | Preset jumlah hari | `?updatedWithin=<hari>` atas `kol_directory.last_refreshed_at` |
| **Agency** *(baru 2026-09-09)* | Daftar ber-count | `?agency=<nama>` lewat `agency_kol_accounts` + `agencies` — 7.684 dari 7.718 |
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
