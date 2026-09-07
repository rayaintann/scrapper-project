# Task 5 — Struktur Data Filter untuk Dikembangkan

**Status:** Rev 2 · siap direview
**Terakhir diperbarui:** 2026-09-07
**Jumlah KOL:** 7.720 (`public.kol_directory`)

**Tugas:** menyusun struktur data filter yang akan dipakai developer — daftar kolom,
tipenya, diambil dari mana, dan cara menghitungnya.

**Dasar:** Task 4 (sumber tiap filter) dan hasil pengecekan langsung ke database.

> Dokumen ini **rancangan**, bukan hasil kerja. Tidak ada tabel, kolom, atau kode yang dibuat di sini.
> Semua angka sudah dicek langsung ke database pada 2026-09-07 dengan sambungan **read-only**.

---

## 1. Ringkasan status

| | Jumlah | Isi |
|---|---:|---|
| **Sudah diputuskan** | 6 | Tier · Format konten · Connected · sumber jumlah follower **(P-02)** · perlakuan 526 KOL di luar tier **(P-01)** · sumber & label Growth |
| **Menunggu keputusan produk** | 0 | — |
| **Sengaja ditunda** | 1 | Jadwal update |
| **Datanya tidak ada** | 1 | Profiling Status — dikeluarkan dari rencana |

**Empat filter siap dikerjakan:** Cari nama · Platform · Kategori · Tier.

> **STATUS 2026-09-07 — sudah diimplementasikan dan diverifikasi.**
>
> Yang di dokumen ini masih berupa rancangan, sekarang sudah jalan:
>
> | Hal | Status | Bukti |
> |---|---|---|
> | Ambang Tier | sudah dibetulkan di database | migration 033 — 1.103 KOL pindah Macro ke Mid-Tier |
> | **P-01** (526 KOL di luar tier) | **DIPUTUSKAN & selesai** | migration 034 — di bawah 1rb dan follower kosong **tidak dapat tier**, tanpa kelompok `Unclassified` |
> | Connected | dipakai di Discovery | `platform_user_id` + `oauth_token`; hasil 0, dan itu benar |
> | Verified | **dihapus dari Discovery** | badge platform tidak lagi jadi field terpisah |
> | Growth | tampil, bisa di-sort, di-filter, ikut CSV | sumber `kol_profile_card.followers_growth`, 25 KOL |
>
> Bagian yang berubah ditandai **UPDATE 2026-09-07**.

---

## 2. Struktur data filter

Inilah bentuk data yang dipegang backend: **satu baris = satu KOL**, dengan daftar kolom
yang boleh dipakai untuk menyaring.

Kolomnya dibagi dua kelompok, bedanya cuma satu: apakah bisa dibaca langsung, atau harus
dikumpulkan dulu dari beberapa baris.

### Kelompok A — bisa dibaca langsung dari tabel utama

Diambil dari `public.kol_directory` dan tabel yang tersambung langsung ke situ.
Tidak perlu dijumlahkan atau dirata-rata dulu.

| Nama kolom | Tipe | Diambil dari | Terisi | Dipakai filter |
|---|---|---|---|---|
| `kol_id` | uuid | `kol_directory.id` | 7.720 · 100% | kunci — penanda satu baris satu KOL |
| `username` | teks | `kol_directory.username` | 7.497 · 97,1% | Cari nama |
| `bio` | teks | `kol_directory.bio` | 902 · 11,7% | Cari nama |
| `followers_count` | angka | `kol_directory.followers_count` | 7.498 · 97,1% | **Tier** (sumber resmi) · Minimum follower |
| `tier` | teks | **dihitung** dari `followers_count` | ikut kolom di atas | Tier |
| `er_pct` | angka | `kol_directory.engagement_rate` | 1.756 · 22,7% | Engagement rate |
| `er_is_outlier` | ya/tidak | **dihitung**: `er_pct > 10` | 83 baris | penanda nilai mustahil |
| `platform_key` | teks | `platforms.key` | 7.496 · 97,1% | Platform |
| `discovery_category[]` | daftar teks | `kol_categories.taxonomy_key` lewat `category_ids` | **4.155 · 53,82%** | **Kategori** |
| ~~`verified_status_raw`~~ | ~~teks~~ | ~~`kol_directory.verified_status`~~ | ~~931 · 12,1%~~ | **DIHAPUS 2026-09-07** — Verified tidak lagi jadi field Discovery |
| `growth_pct` | angka (persen) | `l2_gold.kol_profile_card.followers_growth` lewat `kol_social_account` | 25 · 0,32% | **Growth — sejak snapshot terakhir, bukan 30 hari** |
| `creator_city` | teks | `kol_directory.creator_city` | 0 · 0% | Kota kreator (belum bisa dipakai) |
| `last_refreshed_at` | tanggal | `kol_directory.last_refreshed_at` | 7.496 · 97,1% — **artinya cacat** | Last Updated |
| `created_at` | tanggal | `kol_directory.created_at` | 7.698 · 99,7% | Newly Added |

**Dikeluarkan dari struktur:** `scrape_status`. Isinya cuma kosong (7.621) · `failed` (72) ·
`success` (27), dan tidak ada nilai yang berarti "sedang diproses". Lihat bagian 8.

### Kelompok B — harus dikumpulkan dulu

Kolom-kolom ini datanya tersebar di banyak baris, jadi harus dijumlahkan atau dirata-rata dulu
supaya jadi satu baris per KOL. Semuanya lewat jalur yang sama:

```
kol_directory → kol_social_account → social_account → tabel data detail
```

Karena jalur ini dipakai berulang, semua kolom di bawah dikumpulkan dalam **satu query
tersimpan** bernama `discovery.kol_filter_base`.

| Nama kolom | Tipe | Diambil dari | Terisi | Dipakai filter |
|---|---|---|---|---|
| `kol_id` | uuid | penghubung ke Kelompok A | 7.720 · 100% | kunci |
| `social_account_n` | angka | jumlah akun sosial per KOL | 7.496 punya ≥1 — **224 KOL tidak punya** | pengaman |
| `is_connected` | ya/tidak | `oauth_token` **dan** `platform_user_id` terisi di baris yang sama | **0 · 0%** | **Connected** |
| `sa_connected_flag` | ya/tidak | `social_account.connected` — kolom yang sudah ada | `true` 0 · `false` 7.496 | **tidak dipakai menyaring** — dicatat saja |
| `display_name` | teks | `kol_profile_card.display_name` | 1.958 · 25,4% | Cari nama |
| `bio_l2` | teks | `kol_profile_card.bio` | 1.873 · 24,3% | Cari nama |
| `er_pct_l2` | angka | `kol_metric_daily.er_followers_daily` × 100 | 22 · 0,28% | Engagement rate (pembanding) |
| `format_set[]` | daftar teks | `content_format_daily.media_type` | **30 · 0,39%** | **Format konten** |
| `format_dominant` | teks | format dengan baris terbanyak | 30 · 0,39% | **tampilan saja** — bukan filter |
| `pct_female` / `pct_male` | angka | `audience_demographics_daily` | 23 · 0,30% | Gender audiens |
| `known_gender_ratio` | angka | 1 − porsi `unknown` | rata-rata 28,7% | pengaman gender |
| `audience_city_top1` | teks | `audience_geo_daily` (kota) | 15 · 0,19% | Lokasi audiens |
| `audience_interest_top[]` | daftar teks | `audience_interest_daily` | 23 · 0,30% | Minat audiens |
| `authenticity_score` | angka | `feature.ig_` + `tt_audience_analysis` | 23 · 0,30% | Authenticity |
| `audience_quality_score` | angka | sama seperti di atas | 23 · 0,30% | Kualitas audiens |
| `audience_quality_avg` | angka | rata-rata dua skor di atas | 23 · rentang 43,5–90,0 | Kualitas audiens |
| `avg_views` | angka | `post_metric.views` | 30 · 0,39% | Views |
| `save_rate` / `share_rate` | angka | `post_metric.saves` / `.shares` | 11 · 0,14% (TikTok saja) | Save / Share rate |
| `sponsored_ratio` | angka | `post_metric.is_sponsored` | 30 · 0,39% | Rasio konten berbayar |
| `post_sample_n` | angka | jumlah postingan yang dipakai | paling sedikit 1 · rata-rata 15,9 · paling banyak 200 | pengaman semua rasio |
| `monthly_points_n` | angka | jumlah titik data bulanan | 30 punya ≥1 · 5 punya ≥4 | pengaman Stability |
| `er_monthly_avg` / `_stddev` / `_max` | angka | deret `kol_metric_monthly` | 5 · 0,06% | bahan mentah Stability |

Totalnya sekitar **21 kolom**, bukan 40. Satu filter tidak selalu butuh satu kolom sendiri —
banyak filter memakai kolom yang sama dengan ambang berbeda.

### Kolom pengaman — jangan dihilangkan

Empat kolom di atas tidak dipakai menyaring, tapi wajib ikut dikirim:

| Kolom | Gunanya |
|---|---|
| `social_account_n` | Membedakan "tidak terhubung" dari "belum punya akun sama sekali" (224 KOL) |
| `known_gender_ratio` | Menandai gender yang dihitung dari sampel terlalu tipis (rata-rata cuma 28,7% audiens yang diketahui) |
| `post_sample_n` | Menandai rasio yang berasal dari 1 postingan saja |
| `er_is_outlier` | Menandai 83 nilai engagement rate yang mustahil (sampai 223%) |

Tanpa keempatnya, angka yang lemah akan terlihat sama meyakinkannya dengan angka yang kuat.

### Tiga hal yang sengaja tidak masuk struktur

| Tidak masuk | Alasan |
|---|---|
| `growth_30d` | Ini perbandingan antara dua waktu, bukan satu angka tetap. Harus dihitung saat diminta, dan **wajib** ikut mengirim jarak hari sebenarnya — kalau tidak, angkanya tidak bisa diperiksa. **UPDATE 2026-09-07:** growth 30 hari memang masih tidak ada. Yang sekarang dikirim adalah `growth_pct` — selisih sejak snapshot sebelumnya (10–13 hari), sudah masuk struktur di atas dan **wajib berlabel "Sejak Snapshot Terakhir"** |
| `campaign_count` | Jalur tabelnya beda sendiri, tidak lewat akun sosial. Nanti jadi query terpisah, bukan kolom tambahan |
| Umur audiens · rate card · brand fit · reliability · topik konten · gaya konten | Barisnya nol atau kolomnya memang tidak ada di database |

---

## 3. Aturan yang berlaku untuk semua filter

### Tiga jawaban, bukan dua

Setiap filter yang datanya di bawah 90% harus bisa menjawab:

1. Cocok
2. Tidak cocok
3. **Belum ada datanya**

Jawaban ketiga **tidak boleh** digabung ke jawaban kedua. Untuk 22 dari 40 filter, inilah
satu-satunya yang membedakan hasil jujur dari hasil menyesatkan.

Halaman harus menampilkan jumlahnya terpisah, misalnya:
*"12 cocok · 7.500 belum ada datanya · dari 7.720"*

### Satu tempat untuk jalur data yang dipakai berulang

15 filter mengambil data lewat jalur yang sama:

```
kol_directory → kol_social_account → social_account → tabel data detail
```

Jalur ini dibuatkan **satu query yang disimpan dengan nama** (`discovery.kol_filter_base`),
supaya tidak ditulis ulang di 15 tempat. Alasannya bukan kecepatan, tapi supaya definisinya
tidak melenceng — dan itu **sudah pernah terjadi** pada filter Verified.

---

## 4. Keputusan yang sudah final

### Tier — dihitung dari jumlah follower

| Tier | Batas |
|---|---|
| Nano | 1.000 sampai di bawah 10.000 |
| Micro | 10.000 sampai di bawah 50.000 |
| Mid-Tier | 50.000 sampai di bawah 500.000 |
| Macro | 500.000 sampai di bawah 1.000.000 |
| Mega / Celebrity | 1.000.000 ke atas |

Batas bawah ikut, batas atas tidak. Contoh: follower tepat 500.000 masuk **Macro**,
follower 499.999 masuk **Mid-Tier**.

**UPDATE 2026-09-07 — `kol_tiers` sudah dibetulkan, dan implementasinya memakai tabel itu.**

Larangan lama ("jangan ambil dari `kol_tiers`, batasnya kedaluwarsa") **sudah tidak berlaku**.
Migration 033 memperbaiki dua baris yang salah:

| Tier | Batas lama (salah) | Batas sekarang |
|---|---|---|
| **Mid-tier** | 50.000 – **99.999** | 50.000 – **499.999** |
| **Macro** | **100.000** – 999.999 | **500.000** – 999.999 |

Nano, Micro, dan Mega tidak berubah. Diperbaiki lewat `UPDATE` (bukan hapus-lalu-isi)
karena `agency_kol_accounts.tier_id` punya foreign key ke `kol_tiers.id`.

**Catatan penyimpangan dari rancangan:** dokumen ini merancang ambang disimpan di file
config. Yang benar-benar dikerjakan **membaca `public.kol_tiers`** — satu tabel dipakai
bersama oleh query Discovery dan `l1_silver.sp_build_unified_profile()`, sehingga satu
perbaikan langsung membetulkan UI dan L1/L2 sekaligus. Kalau ambang mau dipindah ke config,
itu perubahan tersendiri dan harus ikut memindahkan L1 juga — jangan setengah-setengah,
karena dua sumber ambang yang hidup bersamaan persis masalah yang bikin bug ini.

Nama di database masih `Mid-tier` (huruf kecil t), sedangkan dokumen produk menulis
`Mid-Tier`. **Sengaja belum diganti** — nilainya sudah tersimpan sebagai teks di
`l1_silver.unified_profile.tier` dan `l2_gold.kol_profile_card.tier`, dan dipakai Saved List.

**Sumber jumlah follower: `kol_directory.followers_count`.** — **P-02 · APPROVED/CLOSED.**
Perhitungan Tier juga memakai kolom yang sama.
`l2_gold.kol_profile_card` **bukan** sumber resmi untuk Followers maupun Tier.

### Format konten — pakai daftar, bukan satu nilai

Filter format artinya **"pernah memposting format ini"**, bukan "format utamanya ini".
Jadi satu KOL bisa punya beberapa format sekaligus.

Nama di database diterjemahkan jadi:

| Di database | Ditampilkan |
|---|---|
| `clips` | Reels |
| `carousel_container` atau `CAROUSEL` | Carousel |
| `feed` | Feed |
| `VIDEO` | Video |
| `unknown` (3 KOL) | dibiarkan, tidak diterjemahkan |

**Story tidak ada sumbernya** — jangan dibuat-buat.

Sebaran sekarang: Reels 18 · Carousel 16 · Feed 11 · Video 11 KOL.

### Connected — dari OAuth token dan platform user ID

Sebuah KOL dianggap **Connected** kalau proses menghubungkan akun sudah benar-benar terjadi:

```
social_account.oauth_token IS NOT NULL
DAN
social_account.platform_user_id IS NOT NULL
```

**Keduanya harus dari baris `social_account` yang sama.**

Tiga hal yang harus dijaga:

1. **Jangan pakai `kol_directory.platform_user_id`.** Kolom itu terisi 930 KOL, tapi isinya
   hasil scraping — bukan bukti kreatornya menghubungkan akun.

2. **Jangan pakai kolom `social_account.connected`.** Kolom itu memang ada dan boleh dicatat
   sebagai kolom yang tersedia, tapi **bukan patokan resmi**. Hari ini kebetulan hasilnya
   sama-sama 0, jadi bedanya belum kelihatan — justru itu alasan perlu ditulis sekarang.

3. **224 KOL tidak punya akun sosial sama sekali.** Untuk mereka jawabannya *belum diketahui*,
   bukan *tidak terhubung*.

Kondisi sekarang: **0 akun · 0 KOL** (`oauth_token` 0 dari 7.496, `platform_user_id` 0 dari 7.496).

**Catatan penting:** Connected berbeda dari **Verified**. Verified punya kolom sendiri
(`verified_status`: 454 verified · 477 unverified · 6.789 kosong) dan tidak boleh dicampur.

**UPDATE 2026-09-07 — Verified dihapus dari Discovery.** Keputusan produk: badge verified
platform **tidak dipertahankan** sebagai field terpisah. Discovery sekarang hanya punya
Connected, dan 454 centang biru yang dulu tampil di kartu dan tabel sudah dilepas.
Semantik lama dibersihkan tuntas — `verifiedOnly` jadi `connectedOnly`, `?verified=1` jadi
`?connected=1`, label "Verified creators only" jadi "Connected creators only".

Hasil Connected hari ini **0 dari 7.720**, dan itu benar: belum ada kreator yang
menghubungkan akun. Chip-nya akan selalu kosong sampai connect flow berjalan — bukan bug.

---

## 5. Dasar angka: hasil pengecekan database

Empat hal ini sebelumnya masih ragu-ragu, sekarang sudah dipastikan.

### Kategori — pakai `category_ids`

Ada dua kolom mirip di `kol_directory`. Keduanya terisi 4.174 KOL, tapi isinya beda:

| Kolom | Isi |
|---|---|
| `category_id` | **satu** kategori |
| `category_ids` | **daftar** kategori |

**1.183 KOL punya lebih dari satu kategori**, dan `category_id` cuma menyimpan salah satunya
secara acak. Contoh nyata: `tasyakamila` sebenarnya Fashion + Food + Lifestyle, tapi di
`category_id` cuma tertulis "Food" — dia tidak akan muncul saat orang cari kreator Fashion.

**Yang dipakai: `category_ids`.**

### Kategori — 4.155 KOL punya kategori resmi

Dari 7.720 KOL:

- **4.174** punya kategori apa pun (54,07%)
- **4.155** punya kategori yang masuk 9 kategori resmi (**53,82%**)
- Selisih **19** adalah KOL yang kategorinya belum dikelompokkan (Medical, Spirituality, dll)

Sebarannya (satu KOL bisa masuk beberapa kategori):

| Lifestyle | Beauty | Moms | Entertainment | Gen Z | Food | Fashion | Fitness | Tech |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2.592 | 1.271 | 589 | 501 | 150 | 123 | 75 | 52 | 4 |

### Tier — jumlah KOL per tier

Dihitung langsung dari `followers_count`, memakai batas dari tim produk:

| Tier | Batas | Jumlah KOL |
|---|---|---:|
| Nano | 1rb – 10rb | 1.943 |
| Micro | 10rb – 50rb | 2.942 |
| Mid-Tier | 50rb – 500rb | 1.809 |
| Macro | 500rb – 1jt | **187** |
| Mega / Celebrity | di atas 1jt | 313 |
| *Di bawah 1rb* | | *304* |
| *Tidak ada data follower* | | *222* |

**Dulu ada dua angka Macro yang bertentangan: 1.123 dan 1.290. Ternyata dua-duanya benar.**
Keduanya memakai batas lama (100rb–1jt), bedanya cuma dihitung dari populasi yang berbeda:
1.290 dari seluruh direktori, 1.123 dari 1.976 KOL yang punya kartu profil.

Dengan batas baru dari produk, **1.103 KOL pindah dari Macro ke Mid-Tier**, dan Macro
menyusut dari 1.290 jadi 187.

### Profiling Status — datanya tidak ada

Kolom `scrape_status` cuma punya tiga nilai:

| Nilai | Jumlah |
|---|---:|
| kosong | 7.621 (98,72%) |
| `failed` | 72 |
| `success` | 27 |

**Tidak ada nilai apa pun yang berarti "sedang diproses".** Kami juga sudah cek 23 kolom
lain yang namanya mengandung "status", termasuk tabel log Add KOL — semuanya cuma pernah
berisi `success`, dan barisnya ditulis setelah proses selesai.

Di halaman, animasi "Profiling" itu ternyata cuma efek tampilan di browser, tidak pernah
menyentuh database.

**"Ready" juga tidak punya definisi yang layak.** Kalau dipakai `scrape_status = success`,
hasilnya cuma 27 KOL, padahal 7.399 KOL sudah punya data follower. Artinya 99,6% direktori
akan hilang dari layar.

---

## 6. Keputusan produk — semuanya sudah tutup

**Tidak ada lagi yang menunggu keputusan produk.**

**P-01 — APPROVED / CLOSED (2026-09-07).** 526 KOL di luar tier (304 follower di bawah
1.000 + 222 tanpa data follower).

Keputusan: **follower di bawah 1rb dan follower kosong tidak mendapat tier** (`tier: null`),
dan **tidak** dibuatkan kelompok `Unclassified` maupun `Unknown`.

Yang dikerjakan: migration 034 membuang fallback di `sp_build_unified_profile()` yang
selama ini menjatuhkan follower di bawah ambang terendah ke tier terbawah.

| | Sebelum | Sesudah |
|---|---:|---:|
| L1 di bawah 1rb bertier `Nano` | 54 | **0** |
| L2 di bawah 1rb bertier `Nano` | 54 | **0** |
| L1 di bawah 1rb tier NULL | 0 | **54** |
| Tier `Unclassified`/`Unknown` dibuat | — | **0** |

Populasi 526 tetap 526 — tidak ada yang hilang, cuma tidak diberi label. Kekhawatiran di
rancangan ("hasil filter tidak akan pernah berjumlah 7.720") tetap berlaku dan harus
dijawab di sisi tampilan: hitung mereka sebagai kelompok tanpa tier, jangan dibuang diam-diam.

Menariknya, perbaikan ini justru **mengembalikan** kesetaraan L1 dengan UI. Fallback tadi
dulu dibuat (migration 009) supaya L1 sama dengan fungsi `TIER()` di UI lama. UI sekarang
memakai `LEFT JOIN kol_tiers` tanpa fallback, jadi UI sudah lebih dulu benar dan justru
L1/L2 yang tertinggal.

**P-02 — APPROVED / CLOSED.** Sumber jumlah follower untuk Tier: **`kol_directory.followers_count`**. `l2_gold.kol_profile_card` bukan sumber resmi untuk Followers maupun Tier.

---

## 7. Yang sengaja ditunda

| Hal | Alasan |
|---|---|
| **Jadwal update per KOL** | Belum ada aturan seberapa sering tiap KOL diperbarui. Jawabannya menentukan apakah perlu menambah kolom baru di database atau cukup di config. **Jangan dipaksakan.** Empat filter (Data Status, Update Frequency, Next Update, Monitoring Priority) ikut ditunda |
| ~~**Batas Growth & Rising Creator**~~ | **DIPUTUSKAN 2026-09-07 — tidak lagi ditunda.** Growth 30 hari memang masih tidak ada, tapi produk menerima **growth sejak snapshot terakhir** (10–13 hari) untuk sementara. Sumbernya `kol_profile_card.followers_growth`, **tanpa rumus baru**, dan **dilarang** dilabeli "Monthly" atau "30 hari". Filter memakai preset (Naik / Datar / Turun / di atas 0,5% / di atas 1%), bukan slider — karena 0% adalah nilai sah, bukan "tanpa batas". Rising Creator dengan ambang 5,5% **tetap ditunda**: nol KOL memenuhinya |

---

## 8. Data yang belum ada

| Yang kurang | Kondisi sekarang | Jenis pekerjaan |
|---|---|---|
| Data konten | 30 KOL · 0,39% — menopang 10 filter | Perluas scraping postingan |
| Data audiens | 23 KOL · 0,30% — menopang 5 filter | Perluas analisis audiens |
| **Profiling Status** | Tidak ada nilai apa pun di database | **Dikeluarkan dari rencana.** Butuh keputusan produk + perubahan pipeline |
| **Definisi "Ready"** | `success` = 27 KOL, menyembunyikan 99,6% direktori | Belum ada definisi yang layak |
| **Connected** | 0 dari 7.496 akun | Menunggu ada kreator yang menghubungkan akun |
| Riwayat follower | Belum ada akun yang punya 2 data berjarak 30 hari | Menunggu waktu, tidak bisa dipercepat |
| Arti `last_refreshed_at` | Terisi 97,1% tapi 73,6% bukan jejak scraping | Perbaiki penulisnya di pipeline |
| Kota kreator | Kolom ada, isi 0 | Diisi saat pendaftaran |
| Data campaign | 14 tabel, 13 kosong | Adopsi produk — bukan pekerjaan teknis |
| Rate card | 5 tabel, semuanya kosong | Adopsi produk |
| Collections / shortlist | Tabelnya belum ada | **Satu-satunya tabel baru yang perlu dibuat** |

---

## 9. Yang tidak perlu dibuat

Ditulis supaya tidak ada yang mengerjakannya karena mengira perlu.

| Jangan buat | Alasan |
|---|---|
| Kolom `growth_30d` / `growth_90d` | Bisa dihitung dari data yang sudah ada. Menyimpannya berarti ada dua kebenaran |
| Kolom `next_refresh_at` | Cukup dihitung: waktu terakhir + jarak update |
| Kolom `monitoring_priority` | `refresh_tier` sudah ada dan masih kosong |
| Tabel riwayat follower baru | `l1_silver.unified_profile` sudah berfungsi begitu |
| Tabel campaign baru | 14 tabel sudah ada dan sambungannya benar — yang kurang datanya |
| Tabel log akses baru | `public.audit_log` bentuknya sudah tepat, tinggal diisi |

---

## 10. Dua hal yang masih terbuka

- **Chip yang hasilnya selalu kosong** (Connected, Tech 4 KOL, Story, YouTube):
  disembunyikan, atau ditampilkan dengan keterangan "belum ada datanya"?
- **277 username kembar:** dibersihkan di data, atau disaring saat query?
  Ini memengaruhi **semua** angka hasil filter.

---

Rencana pengerjaannya ada di `KOL_DISCOVERY_BACKEND_IMPLEMENTATION_PLAN.md`.
