# Task 2 — Cek Prototype dan Cek Data di Database

**Tugas:** memeriksa dua hal. Pertama, prototype-nya sebenarnya bekerja bagaimana.
Kedua, untuk tiap kebutuhan filter di Task 1, datanya ada atau tidak di database.

**Yang belum dikerjakan di sini:** menentukan sumber final tiap filter — itu Task 4.
Di sini cuma dicek **ada atau tidak ada**.

**Terakhir diperbarui:** 2026-09-07 · **Jumlah KOL:** 7.720

> **UPDATE 2026-09-07 — tiga temuan di dokumen ini sudah ditindaklanjuti.**
>
> | Temuan Task 2 | Tindak lanjut |
> |---|---|
> | `kol_tiers` batasnya beda dari UI | **diperbaiki** — migration 033 |
> | Connected kolomnya ada, isi kosong | **dipakai apa adanya** — aturan bisnis dipasang, hasilnya 0 dan itu benar |
> | Growth 30 hari tidak ada | **tetap tidak ada.** Yang dipakai growth *sejak snapshot terakhir* dari `kol_profile_card` |
>
> Baris yang terdampak di tabel bawah sudah ditandai.

---

## Bagian 1 — Hasil cek prototype

### Temuan utama: prototype tidak pernah menyentuh database

File `app/AUTOME_2.html` isinya **8 KOL palsu yang ditulis langsung di kode**, dan
**tidak ada satu pun panggilan ke server** (tidak ada `fetch`, `XMLHttpRequest`, maupun `axios`).

Artinya semua angka yang muncul di prototype itu karangan, bukan data asli.
Prototype tetap berguna sebagai gambaran rancangan, tapi **tidak bisa dipakai sebagai
patokan kebutuhan data**.

### Ada nilai yang dibuat dari hash ID, bukan dari data

Beberapa filter di prototype nilainya dihitung dari `hsh(k.id)` — yaitu diacak dari ID kreator.
Angkanya kelihatan meyakinkan padahal tidak berarti apa-apa:

| Filter | Cara prototype menghasilkan angkanya |
|---|---|
| Performance Stability | dari `k.cons`, yaitu hasil acak dari ID |
| Viral Frequency | sama, dari nilai acak |
| Reliability | sama |

**Akibatnya:** batas "Stable di bawah 28" dan "viral di atas 55" tidak punya rumus asli.
Kalau mau dibuat betulan, rumusnya harus dibuat dari nol.

### Batas angka yang ditulis langsung di prototype

Semua batas ini dari prototype, belum tentu disetujui produk:

| Filter | Batas di prototype |
|---|---|
| Engagement rate | Bagus ≥3% · Tinggi ≥5,5% |
| Save rate | ≥5% |
| Share rate | ≥1,8% |
| Views | 150.000 · 300.000 |
| Kualitas audiens | 85+ · 75+ · di bawah 75 |
| Gender | Mayoritas perempuan ≥60% · mayoritas laki-laki ≥55% |
| Growth 30 hari | Exploding ≥8% · Rising ≥4,5% · Stable ≥1% |
| Tier | Nano 1rb–10rb · Micro 10rb–50rb · Mid 50rb–500rb · Macro 500rb–1jt · Mega di atas 1jt |

### Dua pengelompokan yang bukan format asli

Di prototype, "Video" dan "Photo" bukan format tersendiri melainkan gabungan:
Video = Reels, Photo = Feed + Carousel.

### Kategori di prototype cuma 5

Fitness, Lifestyle, Beauty, Food, Tech — ditulis langsung di kode.
Di database sebenarnya ada 28 nama kategori. Ini tidak nyambung.

---

## Bagian 2 — Hasil cek data di database

### Jalur data yang tersedia

Untuk filter sederhana, cukup satu tabel:

```
public.kol_directory        ← 7.720 baris, satu baris = satu KOL
```

Untuk filter yang lebih dalam, harus lewat tiga tabel berurutan:

```
kol_directory  →  kol_social_account  →  social_account  →  tabel data detail
   (KOL)          (tabel penghubung)      (akun IG/TikTok)
```

Jalur ini **sudah ada dan sambungannya benar**, menjangkau 7.496 dari 7.720 KOL (97,1%).
**224 KOL tidak punya akun sosial sama sekali**, jadi tidak terjangkau jalur ini.

### Ada / tidak ada — per kebutuhan filter

| Kebutuhan filter | Ada di database? | Bukti |
|---|---|---|
| Cari nama | ✅ Ada | `username` 7.497 · `bio` 902 · `display_name` 1.958 |
| Platform | ⚠️ Ada sebagian | Tabel `platforms` cuma punya instagram (3.409) dan tiktok (4.087). **YouTube dan Facebook tidak ada barisnya** |
| Kategori | ✅ Ada | 28 nama kategori, dikelompokkan jadi 9 lewat `kol_categories.taxonomy_key` |
| Tier | ✅ Ada | `followers_count` terisi 7.498. **UPDATE 2026-09-07:** batas `kol_tiers` yang dulu beda dari UI **sudah dibetulkan** (migration 033) — Mid-tier jadi 50rb–499.999, Macro jadi 500rb–999.999. Sekarang `kol_tiers` dan UI memakai ambang yang sama |
| Minimum follower | ✅ Ada | sama seperti di atas |
| Engagement rate | ⚠️ Ada, kotor | `engagement_rate` terisi 1.756, tapi **83 nilai mustahil** (tertinggi 223%) |
| Format konten | ⚠️ Ada, tipis | `content_format_daily` cuma 30 KOL. Nilainya: `clips`, `carousel_container`, `CAROUSEL`, `feed`, `VIDEO`, `unknown` |
| Story | ❌ Tidak ada | Tidak ada satu pun baris untuk Story |
| Connected | ⚠️ Kolom ada, isi kosong | `social_account.oauth_token` 0 dari 7.496 · `platform_user_id` 0 dari 7.496. Ada juga kolom `connected`, semuanya `false` |
| ~~Verified~~ | ✅ Ada | `verified_status`: 454 verified · 477 unverified · 6.789 kosong. **UPDATE 2026-09-07: dihapus dari Discovery** — datanya tetap ada di kolom itu, tapi tidak lagi jadi filter/field |
| Gender audiens | ⚠️ Ada, tipis | `audience_demographics_daily` 23 KOL. Rata-rata 71,3% audiens tidak diketahui gendernya |
| Lokasi audiens | ⚠️ Ada, tipis | `audience_geo_daily` 15 KOL. Isinya campur kota dan provinsi |
| Minat audiens | ⚠️ Ada, tipis | `audience_interest_daily` 23 KOL |
| Kualitas audiens | ⚠️ Ada, tipis | `feature.ig_audience_analysis` + `tt_audience_analysis` 23 KOL |
| Views · Save · Share · Rasio berbayar | ⚠️ Ada, tipis | `post_metric` 30 KOL. Save/Share cuma 11 KOL, **semuanya TikTok** |
| Umur audiens | ❌ Tidak ada | Baris `audience_type='age'` tidak pernah ditulis pipeline |
| Kota kreator | ❌ Kolom ada, isi 0 | `creator_city` 0 dari 7.720 |
| Profiling Status | ❌ Tidak ada | `scrape_status` cuma punya: kosong 7.621 · `failed` 72 · `success` 27. Tidak ada nilai "sedang diproses" |
| Jadwal update per KOL | ❌ Kolom ada, isi 0 | `refresh_tier` 0 dari 7.720 · tabel `scheduler_config` 0 baris |
| Last Updated | ⚠️ Ada, artinya cacat | `last_refreshed_at` terisi 97,1%, tapi **73,6% bukan jejak scraping** — warisan impor Excel |
| Growth 30 hari | ❌ Tidak ada | Belum ada satu akun pun yang punya 2 data berjarak 30 hari — **masih benar** |
| Growth (sejak snapshot terakhir) | ⚠️ Ada, tipis | **UPDATE 2026-09-07:** `l2_gold.kol_profile_card.followers_growth` terisi **25 dari 7.720** (0,32%). Jaraknya 10 hari (22 akun) dan 13 hari (3 akun). Butuh dua snapshot profil; 1.951 dari 1.976 akun ber-kartu baru di-scrape sekali |
| Rate card | ❌ Tabel kosong | 5 tabel rate card, semuanya 0 baris |
| Data campaign | ❌ Tabel kosong | 14 tabel campaign, 13 kosong |
| Reliability · Topik konten · Gaya konten | ❌ Kolomnya tidak ada | Sudah disapu seluruh database, tidak ketemu |
| Collections / shortlist | ❌ Tabelnya tidak ada | Perlu tabel baru |

### Rekap

| Keadaan | Jumlah kebutuhan |
|---|---:|
| Ada dan cukup | 5 |
| Ada tapi datanya tipis atau kotor | 9 |
| Kolom/tabel ada tapi isinya kosong | 5 |
| Tidak ada sama sekali | 7 |

---

## Kesimpulan Task 2

**1. Prototype tidak bisa dipakai sebagai patokan.** Isinya data palsu, dan sebagian
angkanya diacak dari ID. Kebutuhan filter yang benar harus diambil dari aplikasi asli.

**2. Struktur database sudah benar, isinya yang kurang.** Jalur antar tabel sudah tersambung
rapi dan menjangkau 97,1% KOL. Yang jadi penghambat hampir selalu **barisnya masih sedikit**,
bukan tabel atau kolomnya tidak ada.

**3. Dua tabel jadi penyebab utama.** Data konten (30 KOL) dan data audiens (23 KOL)
sama-sama menopang belasan filter sekaligus.

**4. Satu gap yang benar-benar struktural:** jadwal update per KOL. Kolomnya ada tapi kosong,
dan tabel pengaturannya juga kosong. Ini bukan soal menambah data, tapi soal keputusan
yang belum pernah diambil.

**5. Satu tabel yang memang perlu dibuat baru:** Collections / shortlist.

**6. UPDATE 2026-09-07 — dua dari temuan di atas sudah selesai.** Batas `kol_tiers`
sudah dibetulkan (migration 033) sehingga tidak ada lagi dua versi ambang tier yang
hidup bersamaan, dan aturan Connected sudah dipasang memakai `platform_user_id` +
`oauth_token`. Keduanya tidak menambah tabel maupun kolom baru — cuma membetulkan isi
dan definisi yang sudah ada.

---

Kelengkapan datanya diukur di **Task 3**.
Sumber final tiap filter ditentukan di **Task 4**.
Semua pengecekan **read-only** — tidak ada data, tabel, atau kode yang diubah.
