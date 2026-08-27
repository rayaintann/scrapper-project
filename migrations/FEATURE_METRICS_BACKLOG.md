# Feature / L2 Metrics Backlog

Metric analitik yang **sengaja TIDAK dimasukkan** ke `l1_silver.unified_profile`,
beserta rumah kolom, sumber data, formula, dan blocker-nya.

Dasar keputusan: `unified_profile` bergrain `(social_account_id, date)` dan berisi
hasil harmonisasi 1:1 dari L0. Metric di bawah ini adalah hasil **agregasi lintas
baris** atau **algoritma**, bergrain per-akun, sehingga rumahnya di schema `feature`.

Referensi kebutuhan UI: `app/Autometric-KOL-Module.html`.

Status per **2026-08-21**. **4 dari 9 tabel `feature` sudah terisi**
(`ig/tt_engagement_analysis` 13 dan 10 baris, `ig/tt_post_analysis` 130 dan 91),
dan schema `l2_gold` sudah punya **8 tabel** (2 terisi) — lihat bagian "Status L2 Gold"
di bawah. Lima tabel `feature` sisanya (`audience`, `comments`, `brand_fit`)
masih 0 row karena sumbernya belum ada.

> **Data quality level akun → `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md` §13.**
> Sebelum menulis procedure pengisi `feature`, baca dulu bab itu: identity key
> yang benar adalah `kol_directory.id` (**bukan username** — `iben_ma`, `inul.d`,
> `saalhaerid` ada di kedua platform), cakupan saat ini **23 akun / 221 post**
> (13 IG + 10 TT), dan dua akun bermasalah yang sudah terdokumentasi:
> `inul.d` TikTok (identity mismatch di roster) dan `bbrightvc` (gagal
> `not_found` di tahap scraping, benar tidak ada di L1).

---

## ⚠️ KEPUTUSAN SCOPE (2026-08-20)

**Scope saat ini baru profile scraping.** Pipeline post/video belum dijalankan.

Konsekuensinya, yang berlaku untuk seluruh dokumen ini:

1. **`l1_silver.unified_profile` tetap fokus ke profile metrics saja.**
   Tidak ada metric analitik yang dipaksakan masuk L1.
2. **Metric analitik tetap di layer `feature`, dan belum dihitung/diisi**
   sampai pipeline post benar-benar dijalankan.
3. **`latestPosts` di dalam `raw_payload` TIDAK dianggap sebagai hasil post
   scraping yang siap dipipeline.** Lihat bagian berikut.

### Soal `latestPosts` — ditahan, jangan dipakai sebagai source

Saat audit ditemukan bahwa `l0_raw.ig_profile_apify.raw_payload->'latestPosts'`
berisi 10.562 baris post (890 akun, rata-rata 11,79 post/akun), dan
`l0_raw.tt_profile_apify.raw_payload` berisi 1 video per akun (1.018 baris).

**Keputusan: TIDAK dipakai untuk mengisi pipeline post.** Alasannya:

- Itu **produk sampingan dari profile scraping**, bukan hasil post scraping.
  Cakupannya kebetulan, bukan hasil desain: Instagram dibatasi ~12 post terakhir,
  TikTok hanya 1 video per akun.
- Memperlakukannya sebagai sumber post akan membuat `unified_post` dan seluruh
  metric turunannya terlihat "sudah terisi" padahal sampelnya tidak memadai dan
  tidak bisa dipertanggungjawabkan.
- TikTok khususnya tidak layak: 1 video per akun menghasilkan engagement rate
  sampai 10.950% (satu video viral bisa dapat like jauh melebihi jumlah follower).

Temuan ini tetap dicatat di sini supaya tidak hilang, dan bisa dipertimbangkan
lagi **setelah** pipeline post yang sesungguhnya berjalan — misalnya sebagai
data pembanding atau backfill historis. Bukan sebagai sumber utama.

---

## Status L2 Gold (SCRUM-513 / SCRUM-516)

Schema `l2_gold` berisi **8 tabel** — seluruh backlog "L2 Database"
(SCRUM-490) sudah punya rumah. Rinciannya di
`docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md` §17.13.

**Tabel sudah dibuat ≠ pipeline sudah selesai.** Dua kolom di bawah dipisah
sengaja: `Schema` = tabelnya ada, `Data` = ada/tidaknya isi dan apa
penghambatnya.

| Item | Tabel | Schema | Data |
|---|---|---|---|
| **SCRUM-513** | `kol_metric_daily` | ✅ 021 | ✅ 160 baris · 23 akun · 2021-02-18 s.d. 2026-08-20 |
| **SCRUM-516** | `kol_metric_monthly` | ✅ 022 | ✅ 53 baris · 23 akun · 2021-02 s.d. 2026-08 |
| **SCRUM-515** | `post_metric` | ✅ 023 | ⬜ kosong — **sumber siap** (`unified_post` 221 + `feature.*_post_analysis` 221) |
| **SCRUM-514** | `kol_profile_card` | ✅ 023 | ⬜ kosong — **sumber siap** (`unified_profile` 1.971 + `unified_rate_card` 9.210) |
| **SCRUM-517/518** | `content_format_daily` | ✅ 023 | ⬜ kosong — **sumber siap** (`unified_post` 221). Dua tiket identik → satu tabel |
| **SCRUM-519** | `audience_demographics_daily` | ✅ 023 | ⬜ kosong — `unified_audience` 0 baris |
| **SCRUM-520** | `audience_geo_daily` | ✅ 023 | ⬜ kosong — `unified_audience` 0 baris |
| **SCRUM-521** | `audience_interest_daily` | ✅ 023 | ⬜ kosong — ⚠ **tidak ada sumber sama sekali** |

⚠ **`audience_interest_daily` bukan sekadar kosong.** `sp_sync_instagram_audience()`
hanya menghasilkan `audience_type` bernilai `age`, `gender`, `country`, `city`.
Pencarian kolom `%interest%` di seluruh `l0_raw` + `l0_harmonization` +
`l1_silver` mengembalikan **0 kolom**. Tabel ini menunggu **sumber data baru**,
bukan menunggu ETL.

Migration terkait: `021` dan `022` (**committed + materialized**),
`023_create_l2_gold_remaining_tables.sql` (**committed**, 6 tabel dibuat kosong,
belum ada asset).

### Status pipeline per ticket

| Ticket | Schema | Data pipeline |
|---|---|---|
| SCRUM-513 `kol_metric_daily` | **DONE** | **DONE** — asset aktif |
| SCRUM-516 `kol_metric_monthly` | **DONE** | **DONE** — asset aktif |
| SCRUM-515 `post_metric` | **DONE** | **NOT STARTED** |
| SCRUM-514 `kol_profile_card` | **DONE** | **NOT STARTED** |
| SCRUM-517/518 `content_format_daily` | **DONE** | **NOT STARTED** |
| SCRUM-519 `audience_demographics_daily` | **DONE** | **WAITING FOR SOURCE** |
| SCRUM-520 `audience_geo_daily` | **DONE** | **WAITING FOR SOURCE** |
| SCRUM-521 `audience_interest_daily` | **DONE** | **BLOCKED** — sumber tidak ada |

Empat kolom di kedua tabel L2 Gold yang sudah terisi sengaja dibuat tapi
**100% NULL**:
`reach_sum`, `er_reach_*`, `reposts_sum`, `followers_growth`. Penghambatnya sama
dengan yang tercatat di backlog ini — Insights API dan strategi scraping profil
harian. **Jangan diperlakukan sebagai nol.**

---

## Ringkasan status sumber data

| Sumber yang dibutuhkan | Tabel | Row | Catatan |
|---|---|---:|---|
| Post Instagram | `l0_raw.ig_media_snapshots_apify` | **0** | Tabel & procedure sudah ada, ingest belum jalan |
| Video TikTok | `l0_raw.tt_video_apify` | **0** | idem |
| Post harmonized | `l0_harmonization.{instagram,tiktok}_post` | **0** | |
| Post unified | `l1_silver.unified_post` | **0** | |
| Follower | `l1_silver.unified_follower`, `l0_raw.*_followers_*` | **0** | |
| Komentar | `l0_raw.{ig,tt}_comments_*` | **0** | |
| Demografi audiens | `l0_raw.ig_profile_official` (demographics_*) | **0** | Hanya dari official API |
| Rate card | `l1_silver.unified_rate_card` | **9.210** ✅ | Siap dipakai untuk CPE |
| Snapshot profil harian | `l1_silver.unified_profile` | 1.971 | **1 tanggal per akun** — belum ada time series |

**Blocker utama: pipeline post/video/follower belum dijalankan.** Sebagian besar
metric di bawah menunggu itu.

### Infrastruktur yang SUDAH siap

Ini penting supaya tidak dibangun ulang — begitu scraping post jalan, jalurnya
sudah lengkap:

| Layer | Objek | Status |
|---|---|---|
| L0 raw | `ig_media_snapshots_apify`, `tt_video_apify` | ✅ tabel ada |
| L0 harmonization | `instagram_post`, `tiktok_post` | ✅ tabel ada |
| L0 harmonization | `sp_sync_instagram_post()`, `sp_sync_tiktok_post()` | ✅ procedure ada |
| L1 silver | `unified_post` | ✅ tabel ada |
| L1 silver | `sp_build_unified_post()` | ✅ procedure ada |
| Feature | 9 tabel analisis | ✅ tabel ada, 0 row |

Yang belum ada: procedure pengisi layer `feature` (belum satu pun dibuat), dan
ingest post itu sendiri.

> **Kesiapan per kolom (audit 2026-08-21).** Dari **94 kolom metrik** di 9 tabel
> `feature`: **26 READY** (sumbernya lengkap di L1 hari ini), 5 READY-sebagian,
> 2 PARTIAL, **61 BLOCKED**. Yang paling siap `tt_engagement_analysis` (8/9
> kolom metrik). Seluruh kolom READY bersumber dari `l1_silver.unified_post`.
> Penghambat terbesar: `unified_comment` 0 baris (20 kolom), algoritma belum
> didefinisikan (17 kolom), Insights API belum tersambung (11 kolom).
> Rincian per kolom: `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md` §16.

> Catatan: procedure `sp_sync_instagram_post()` / `sp_sync_tiktok_post()` belum
> pernah diuji jalan. Procedure profile yang setara (`sp_sync_*_profile`) ternyata
> rusak karena mereferensi kolom yang sudah di-DROP, dan baru diperbaiki di
> migration 004/005. Procedure post kemungkinan punya masalah serupa — perlu
> dry run dulu sebelum dipakai.

---

## 1. `engagement_rate`

| | |
|---|---|
| UI | `k.er` — KPI card, filter `erMin`, sort |
| Rumah kolom | `feature.ig_engagement_analysis.engagement_rate` ✅ ada<br>`feature.tt_engagement_analysis.engagement_rate` ✅ ada |
| Sumber yang benar | `l1_silver.unified_post` (likes, comments, shares, saves) + `followers_count` dari `unified_profile` |
| Formula | `AVG(likes + comments) ÷ followers_count × 100` atas N post terakhir |
| Status | **BLOCKED — menunggu pipeline post** |
| Perlu migration | ❌ kolom sudah ada; nanti perlu procedure pengisi |

**Formula sudah ada di project** — `transform.py:69 compute_engagement_rate()`:

```python
avg(likesCount + commentsCount) ÷ followers × 100
# likesCount == -1 (Instagram menyembunyikan like) diperlakukan 0
# post dengan interaksi 0 dikeluarkan dari sampel
```

Kolom pendukung yang sudah tersedia di tabel feature:
`posts_analyzed_count` / `videos_analyzed_count`, `total_likes`, `total_comments`,
`total_shares`, `total_saves`, `engagement_trend`, `format_performance`,
`reel_plays`, `best_posting_time_heatmap`.

### JANGAN ambil dari `public.kol_directory.engagement_rate`

- **Arah layer terbalik.** `public` adalah serving layer, bukan sumber untuk L1/feature.
- **Coverage timpang.** Instagram 897/931 (96%), **TikTok hanya 113/1.040 (11%)**.
- **Provenance-nya sudah terkonfirmasi sama.** Saat audit, formula
  `compute_engagement_rate()` dihitung ulang langsung dari `raw_payload` dan
  menghasilkan nilai maksimum **223,4103** — identik dengan maksimum
  `kol_directory.engagement_rate` (**223,41**), dengan 52 vs 53 nilai di atas 20%.
  Jadi `kol_directory` memang diisi oleh formula ini lewat `db.py:update_profiles()`.
  Menyalinnya kembali ke feature tidak menambah informasi apa pun, hanya
  memindahkan angka lama melalui jalur yang salah.

### Catatan kualitas yang perlu diantisipasi saat pipeline post jalan

Ditemukan saat audit `latestPosts`, kemungkinan besar akan muncul lagi pada data
post yang sesungguhnya:

| temuan | dampak pada ER |
|---|---|
| `likesCount = -1` — Instagram menyembunyikan jumlah like (6,5% sampel) | Formula menghitungnya 0 → ER akun tersebut turun tidak wajar |
| Post kolaborasi: `ownerUsername` ≠ pemilik profil (7,9% sampel) | Formula existing tidak memfilter owner → engagement akun lain ikut terhitung |
| Nilai ekstrem > 20% | Perlu batas kewajaran / flag outlier sebelum dipakai UI |

Tiga hal ini sebaiknya diputuskan sebelum procedure feature ditulis.

---

## 2. `avg_reach`

| | |
|---|---|
| UI | `k.reach` — KPI "Avg. Reach"; `k.estReach` untuk filter & kolom tabel |
| Rumah kolom | `feature.{ig,tt}_audience_analysis.avg_reach` ✅ ada |
| Sumber | `reach` per post — **hanya dari official API** (Instagram Insights), tidak ada di Apify |
| Formula | `AVG(reach)` atas N post terakhir per akun |
| Status | **BLOCKED** — post 0 row, dan `ig_profile_official` juga 0 row |
| Perlu migration | ❌ kolom sudah ada |

⚠️ **`videoViewCount` / `playCount` bukan `reach`.** Views = jumlah pemutaran
(bisa berulang dari orang yang sama); reach = jumlah akun unik yang melihat.
Jangan disamakan, meskipun views lebih mudah didapat.

UI menurunkannya lagi jadi `estReach = reach × (1 + auth/400 + postFreq/40)` —
jelas algoritma yang bergantung `authenticity_score` dan `postFreq`, memperkuat
penempatannya di layer feature.

Proxy `l0_raw.kol_roster_import.estimated_reach` **tidak dipakai**: rasio
reach/followers rata-rata 325× (IG) dan 3.233× (TT), dan 560 baris TikTok punya
reach > followers. Terindikasi CSV column shift, perlu dibersihkan dulu.

---

## 3. `emv` (Earned Media Value)

| | |
|---|---|
| UI | `k.emv` — KPI hero "Est. Media Value", kolom tabel, sort |
| Rumah kolom | `feature.{ig,tt}_audience_analysis.emv` ✅ ada |
| Sumber | `avg_reach` (lihat #2) + konstanta CPM |
| Formula | `reach × CPM ÷ 1000 × multiplier` |
| Status | **BLOCKED + NEED CONFIRMATION** |
| Perlu migration | ❌ kolom sudah ada |

Dua blocker:
1. `avg_reach` belum tersedia.
2. **Konstanta CPM tidak ada di database.** Pencarian kolom `%cpm%`, `%benchmark%`,
   `%multiplier%`, `%coefficient%`, `%formula%` di seluruh 7 schema: 0 hasil.
   Perlu keputusan bisnis — CPM per platform, per tier, atau global.

---

## 4. `cpe` (Cost Per Engagement)

| | |
|---|---|
| UI | `k.cpe` — KPI hero "Cost / Engagement" |
| Rumah kolom | `feature.{ig,tt}_audience_analysis.cpe` ✅ ada |
| Sumber pembilang | `l1_silver.unified_rate_card.fee` ✅ **tersedia** |
| Sumber penyebut | total engagement per post — **menunggu pipeline post** |
| Formula | `fee ÷ total_engagement` |
| Status | **PARTIAL** — cost siap, penyebut belum |
| Perlu migration | ❌ kolom sudah ada |

Cost sudah siap: 9.210 baris rate card, `fee` 100% terisi, coverage akun
Instagram 877/931 (94%) dan TikTok 967/1.040 (93%).

Dua hal yang perlu dikonfirmasi sebelum implementasi:
- **`post_type` mana** yang jadi basis fee (reel? feed_video? median semua?).
- **14 rate card Instagram** ber-`fee = 1.000.000.000` — terlihat sentinel/placeholder,
  perlu dibersihkan agar tidak merusak rata-rata.

---

## 5. `authenticity_score`, `audience_quality_score`, `follower_quality_score`

| | |
|---|---|
| UI | `k.auth` — "Authenticity %", filter `authMin`; `k.q` — "Audience Quality /100" |
| Rumah kolom | `feature.{ig,tt}_audience_analysis.authenticity_score` ✅<br>`.audience_quality_score` ✅ · `.follower_quality_score` ✅ |
| Sumber | Data follower per akun — deteksi bot/fake |
| Formula | **Tidak ada di database** — perlu definisi algoritma |
| Status | **BLOCKED + NEED CONFIRMATION** |
| Perlu migration | ❌ kolom sudah ada |

Semua tabel follower 0 row: `l1_silver.unified_follower`,
`l0_harmonization.{instagram,tiktok}_follower`, `l0_raw.{ig,tt}_followers_{apify,official}`.

Ini murni LOGIC, bukan formula — perlu definisi bobot/kriteria dari tim bisnis.

---

## 6. `brand_affinity` / `brand_fit`

| | |
|---|---|
| UI | `k.aff` — "Brand Affinity /10"; `k.match` — filter `brandFitMin` |
| Rumah kolom | `feature.brand_fit_analysis.partnership_score` ✅ ada<br>plus `sub_scores`, `audience_overlap_pct`, `category_fit_tags`, `recommendations` |
| Sumber | Kategori KOL + audiens + data brand |
| Status | **BLOCKED** — LOGIC belum didefinisikan |
| Perlu migration | ❌ kolom sudah ada |

Catatan grain: tabel ini bergrain `(agency_kol_account_id, brand_id)` — skor
kecocokan bersifat **per pasangan KOL×brand**, bukan atribut profil. Ini alasan
struktural tambahan kenapa tidak mungkin masuk `unified_profile`.

Sejak **migration 014 (2026-08-21)** tabel IG dan TT yang terpisah sudah digabung
menjadi satu `feature.brand_fit_analysis`, dan grain itu kini **ditegakkan
constraint** `uq_brand_fit_analysis UNIQUE (agency_kol_account_id, brand_id)` —
sebelumnya tidak ada apa pun yang mencegah baris ganda. Platform ditentukan
`public.agency_kol_accounts.platform_id`, bukan nama tabel.

---

## 7. Demographic / audience metrics

| | |
|---|---|
| UI | `k.gF` (% female), `k.ageTop`, `k.gen`, `k.audLoc`, `k.interests` |
| Rumah kolom | `feature.{ig,tt}_audience_analysis.gender_breakdown` ✅<br>`.age_gender_breakdown` ✅ · `.top_interest` ✅ · `.geo_distribution` ✅ · `.active_hours_heatmap` ✅ |
| Sumber | `l0_raw.ig_profile_official.demographics_{gender,age,city,country}` (jsonb) |
| Status | **BLOCKED** — `ig_profile_official` 0 row |
| Perlu migration | ❌ kolom sudah ada |

Demografi audiens **hanya** tersedia lewat official API (Instagram Insights).
Apify tidak menyediakannya sama sekali. TikTok belum punya sumber demografi.

`k.gen` (Gen Z / Millennials / Gen X / Boomer+) adalah turunan `ageTop` — lookup
sederhana, tapi bergantung pada `age_gender_breakdown` yang belum ada.

---

## 8. `avgViews`

| | |
|---|---|
| UI | `k.avgViews` — filter `viewsMin`, perhitungan proyeksi campaign |
| Rumah kolom | IG → `feature.ig_engagement_analysis.reel_plays` ✅<br>TT → `feature.tt_engagement_analysis.total_views` ÷ `videos_analyzed_count` ✅ |
| Sumber | `unified_post.views` |
| Formula | `AVG(views)` per akun (post video saja) |
| Status | **BLOCKED** — menunggu pipeline post |
| Perlu migration | ❌ kolom sudah ada |

---

## 9. `paidRatio` (rasio konten berbayar)

| | |
|---|---|
| UI | `k.paidRatio` — filter `paidMax`, insight "audience masih punya headroom" |
| Rumah kolom | `feature.{ig,tt}_post_analysis.is_sponsored` ✅ ada — **tapi per-post**, belum ada kolom rasio level profil |
| Sumber | `unified_post.is_sponsored` |
| Formula | `COUNT(is_sponsored) ÷ COUNT(*) × 100` atas N post terakhir |
| Status | **BLOCKED** — menunggu pipeline post |
| Perlu migration | ⚠️ perlu kolom agregat level profil, atau dihitung saat query |

⚠️ Catatan dari audit: penanda sponsor tampak **under-report**. Pada sampel
`latestPosts`, hanya 35 dari 10.562 post (0,33%) ber-`paidPartnership = true`.
Kalau angka serupa muncul di data post sesungguhnya, `paidRatio` akan bias ke
bawah dan tidak bisa dipakai sebagai filter yang berarti.

---

## 10. `growth` (pertumbuhan followers) — ✅ SUDAH PUNYA RUMAH KOLOM

| | |
|---|---|
| UI | `k.growth` (+6,4%), `k.tr` (sparkline 6 titik), kolom tabel, sort |
| Rumah kolom | **`l1_silver.unified_profile.followers_growth`** `numeric` ✅ ada sejak 2026-08-21 |
| Sumber | `l1_silver.unified_profile.followers_count` — butuh ≥2 snapshot per akun |
| Formula | `(followers_kini − followers_snapshot_sebelumnya) ÷ followers_snapshot_sebelumnya × 100` |
| Snapshot sebelumnya | `LAG(followers_count) OVER (PARTITION BY social_account_id ORDER BY date)` |
| Dihitung oleh | `l1_silver.sp_build_unified_profile()` — **otomatis**, tanpa procedure baru |
| Status | **✅ TERISI** — 22/1.994 baris sejak snapshot kedua 2026-08-24 |
| Perlu migration | ❌ sudah dikerjakan |

Keputusan yang tadinya terbuka sudah diambil: rumahnya **bukan** di
`feature.*_audience_analysis` maupun tabel time-series tersendiri, melainkan di
`l1_silver.unified_profile` — grainnya `(social_account_id, date)` persis sama
dengan grain metriknya, dan `tier` sudah lebih dulu memakai pola yang sama di
tabel itu. Tidak ada tabel, function, atau procedure baru yang dibuat.

Perbandingannya **snapshot ke snapshot**, bukan jendela waktu tetap. Hasilnya
`NULL` kalau belum ada snapshot sebelumnya, kalau followers sebelumnya `NULL`/`0`,
atau kalau followers sekarang `NULL` — tanpa tebakan dan tanpa 0 pengganti.
Di klausa `ON CONFLICT`, kolom ini memakai **penugasan langsung**
(`followers_growth = EXCLUDED.followers_growth`), bukan `COALESCE`, supaya nilai
turunan tidak pernah basi.

**Diperbarui 2026-08-24: kolom ini sekarang TERISI.** Scraping profil kedua untuk
23 akun yang punya post menghasilkan **22/1.994 baris terisi** (Instagram 13,
TikTok 9) — tanpa migrasi, tanpa backfill, tanpa perubahan kode. Rentang snapshot
2026-08-14 s.d. 2026-08-24. Yang tersisa kosong hanya `inul.d` TikTok yang baru
punya satu snapshot.

Catatan sebelum diteruskan ke L2: kolom L1 bertipe `numeric` dan berisi **persen**,
sedangkan kolom `followers_growth` di tiga tabel `l2_gold` bertipe `bigint` yang
menyiratkan **jumlah orang**. Menyalin apa adanya akan memotong `5,2%` jadi `5`.

**Diperbarui 2026-08-26: sudah diteruskan ke L2 — rumahnya `l2_gold.kol_profile_card`.**
Peringatan tipe di atas terbukti lebih parah dari dugaan: ke-22 nilai yang ada
semuanya di antara `-0,051%` dan `+0,92%`, jadi cast ke `bigint` mengubah **20 dari
22 jadi `0`** dan menghapus tanda minus pada akun yang justru turun — metriknya
hilang sama sekali, bukan sekadar kehilangan desimal. `migrations/025_fix_followers_growth_type.sql`
mengubah kolom itu jadi `numeric` (tabel masih 0 baris, jadi gratis).

Rumahnya **`kol_profile_card`**, bukan `kol_metric_daily`/`kol_metric_monthly`:
grain kedua tabel itu digerakkan post (`metric_date` dari `posted_at`), sedangkan
growth milik akun. Dibuktikan sebelum dibangun — growth L1 hanya ada di
`2026-08-24` sementara `metric_date` tertinggi `2026-08-20`, sehingga aturan
carry-forward menghasilkan **0 pasangan akun-hari** yang memenuhi syarat. Tipe
`bigint` di dua tabel itu sengaja TIDAK diubah; kolomnya tetap tidak diisi.

Diisi asset `kol_profile_card` (`assets/gold_profile.py`): 1.972 kartu, **22 dapat
growth** (IG 13, TikTok 9), nilainya dibawa apa adanya dari snapshot yang sama
dengan `profile_snapshot_date` — direkonsiliasi 1.972/1.972 cocok persis terhadap
L1. Sisanya `NULL` karena snapshot terbarunya masih tanggal scrape pertama; angka
ini naik sendiri tiap scraping profil berikutnya, tanpa perubahan kode.

Catatan historis — kondisi sebelum 2026-08-24: 0 akun punya lebih dari 1 tanggal,
jadi 0/1.971 baris terisi. Instagram semuanya 2026-08-14; TikTok tersebar di 3
tanggal tapi tiap akun hanya muncul sekali. Kolomnya terisi sendiri begitu scraping profile berjalan
pada tanggal kedua — tanpa migrasi tambahan, tanpa backfill manual.

Ini satu-satunya metric di dokumen ini yang **tidak** bergantung pada pipeline
post, dan sekarang satu-satunya yang hanya menunggu waktu.

Rincian lengkap: `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md` §14.2.

Catatan sejarah: kolom `followers_growth` pernah ada di
`l0_harmonization.*_profile` tapi sudah di-DROP.

---

## 11. `postFreq` (frekuensi posting) — ⛔ TERHAMBAT STRATEGI SCRAPING

> **Diperbarui 2026-08-21 setelah audit.** Penghambatnya BUKAN kolom dan BUKAN
> rumus. Sumber `unified_post.posted_at` sudah lengkap 221/221. Masalahnya:
> scraping mengambil **"10 post terakhir"**, bukan "semua post dalam N hari",
> sehingga akun aktif tersensor dari atas — 10 post yang semuanya jatuh dalam
> 1 hari menghasilkan 70 post/minggu, sementara 10 post yang tersebar 1.339 hari
> menghasilkan 0,05. Dengan jendela 30 hari, 3/13 akun Instagram dan 5/10 TikTok
> sudah tersensor dan hanya menghasilkan batas bawah (2,33 = 10 ÷ 30/7).
> Selama scraping masih berbasis jumlah post, metrik ini tidak akan pernah benar
> untuk akun paling aktif. Rincian lengkap + rancangan yang sudah disiapkan:
> `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md` §15.

| | |
|---|---|
| UI | `k.postFreq` (5,2 post/minggu), filter `postFreqMin`, input `estReach` |
| Rumah kolom | **TIDAK ADA** di schema `feature` |
| Sumber | `unified_post.posted_at` |
| Formula | `COUNT(post) ÷ rentang_minggu` |
| Status | **BLOCKED** — menunggu pipeline post |
| Perlu migration | ✅ **ya** |

⚠️ Catatan: rentang waktu perlu ditentukan eksplisit (mis. 30/90 hari terakhir),
bukan dari post tertua yang kebetulan terambil. Pada sampel `latestPosts`, 12 post
tersebar rata-rata 492 hari — kalau dibagi rentang itu, hasilnya bias jauh ke bawah.

---

## 12. Sentiment / comments analysis

| | |
|---|---|
| Rumah kolom | `feature.{ig,tt}_comments_analysis.*` ✅ ada — `sentiment_*_pct`, `toxicity_pct`, `spam_detected_pct`, `word_cloud`, `emoji_analysis`, `top_topics`, `ai_comment_summary` |
| Sumber | `l1_silver.unified_comment` |
| Status | **BLOCKED** — tabel komentar 0 row di semua layer |
| Perlu migration | ❌ kolom sudah ada |

---

## Metric yang berada di luar domain Profile

| UI | Domain | Tabel |
|---|---|---|
| `k.succ`, `k.camps`, `k.collab` | Campaign | `public.campaign_kols`, `public.campaigns` |
| `k.rate` | Rate card | `l1_silver.unified_rate_card` ✅ terisi 9.210 |
| `k.cat`, `k.niche` | Kategori KOL | `public.kol_categories`, `kol_directory.category_id` (4.174/7.718) |
| `k.loc` | Lokasi kreator | `kol_directory.creator_city` — **0 terisi** |
| `k.agency` | Agency | `public.agencies` |
| `k.conf`, `k.synced` | Freshness data | Turunan `unified_profile.processed_at` ✅ sudah ada |
| `k.tier` | Tier KOL | ✅ **sudah di `unified_profile.tier`** (migration 009/011) |

---

## Urutan pengerjaan yang disarankan

1. **Jalankan scraping post/video yang sebenarnya** (actor terpisah, bukan
   `latestPosts` dari profile scraping) → isi `l0_raw.ig_media_snapshots_apify`
   dan `l0_raw.tt_video_apify`.
2. **Dry run `sp_sync_instagram_post()` / `sp_sync_tiktok_post()`** — kemungkinan
   punya bug kolom di-DROP seperti procedure profile dulu. Perbaiki bila perlu.
3. **Jalankan `sp_build_unified_post()`** → `l1_silver.unified_post` terisi.
   Ini membuka: `engagement_rate`, `avgViews`, `postFreq`, `paidRatio`,
   `format_performance`, `engagement_trend`, dan penyebut `cpe`.
4. **Isi pipeline follower** → membuka `authenticity_score`, `audience_quality_score`.
5. **Sambungkan official API Instagram** → membuka `avg_reach`, demografi audiens,
   dan insight metrics di `unified_profile` yang sekarang masih NULL
   (`reach`, `profile_views`, `accounts_engaged`, dll).
6. **Minta keputusan bisnis**: konstanta CPM (EMV), basis `post_type` (CPE),
   definisi algoritma authenticity & brand-fit, penanganan `likesCount = -1`
   dan post kolaborasi.
7. **Jalankan scraping profile beberapa periode** agar `growth` punya bahan.
   Ini bisa berjalan paralel, tidak menunggu pipeline post.
