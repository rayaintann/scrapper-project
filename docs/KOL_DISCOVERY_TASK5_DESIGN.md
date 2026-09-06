# KOL Discovery — Struktur Data Filter

**Task 5 · Technical design · siap direview**
Populasi / denominator: `public.kol_directory` = **7.720 KOL**
Baseline UI: app produksi `autometric` @ `discover/data-terukur-kol` (bukan prototype)
Input: Task 1–4 · `KOL_DISCOVERY_AUDIT.md` · `KOL_DISCOVERY_MONITORING_PRIORITY_AUDIT.md` ·
`KOL_DISCOVERY_FILTER_BACKEND_PLAN.md` · `deliv.xlsx` · migration 006/011/020/025/029 · `db.py`

> **Design only.** Tidak ada migration, VIEW, tabel, index, atau perubahan source code yang dibuat.
> Database tidak bisa dijangkau saat dokumen ini ditulis (TCP timeout ke `10.100.14.216:5432`) —
> seluruh angka berasal dari audit Task 2–4 dan silang-baca repo, **bukan query baru**. Yang perlu
> diverifikasi ulang ada di §9.

**Kosakata status** — satu filter bisa kena beberapa kondisi; yang ditulis adalah **yang memblokir lebih dulu**.

| Status | Artinya |
|---|---|
| `DIRECT` | Bisa langsung dipakai dari data existing, tanpa agregasi dan tanpa keputusan tertunda |
| `DERIVED` | Data ada, rumus jelas, tinggal dihitung |
| `PARTIAL` | Sumber & rumus jalan, tapi coverage belum cukup untuk menyaring populasi |
| `MISSING` | Tidak ada sumber terpakai — 0 baris, 0 kolom, atau 0 nilai berguna |
| `DECISION` | Secara teknis bisa dibangun; rule produknya belum final (§8) |

Singkatan `[SA]` = jalur JOIN `kol_directory → kol_social_account → social_account`.

---

## 1. Scope

Task 5 menetapkan **bentuk data** yang dipakai backend untuk menjalankan filter KOL Discovery:
daftar field yang boleh difilter, asalnya, cara menghitungnya, dan di lapisan mana ia hidup.

Di luar scope (= Task 6): migration, VIEW, tabel, index, perubahan kode, pengisian data.
Tiga di antaranya tidak boleh dimulai sebelum keputusan §8 keluar.

**Surface yang dicakup:** Creator Database (utama), My Creators, Smart Discovery — ketiganya
menyaring populasi `kol_directory` dan berbagi satu projection.
**Tracked Accounts dikecualikan:** populasinya akun brand & kompetitor, bukan KOL.

### 1.1 Perubahan baseline dari Task 1–4

Task 1–4 memakai prototype `app/AUTOME_2.html` sebagai satu-satunya acuan UI. Prototype itu
berjalan di **8 KOL mock** dengan **0 network call** — tidak pernah menyentuh database. Memindahkan
baseline ke app produksi mengubah empat hal:

| | Perubahan |
|---|---|
| **B1** | **7 filter yang dicoret Task 1 sebagai "legacy" ternyata hidup di app.** Minimum Followers, Minimum ER, Max Rate Card berstatus DONE; Min Authenticity, Min Brand Fit, Max Paid Ratio, Min Campaigns dirender `disabled`. Pertanyaan terbuka Task 1 §4 terjawab sendiri: bukan dihapus |
| **B2** | **2 filter baru** yang tidak ada di prototype: Profiling Status (My Creators) dan Lower Price than Reference (Smart Discovery) |
| **B3** | **Kategori naik satu lapis.** Migration `029` menambah `kol_categories.taxonomy_key` — 9 Discovery Category di atas 28 kategori mentah. Task 2–4 dan kedua Excel masih memetakan ke `kol_categories.name` lewat `category_id` skalar |
| **B4** | **Last Updated turun status.** Terisi 97,1%, tapi 5.520 dari 7.496 nilai (73,6%) tidak punya baris apa pun di `l0_raw` — timestamp warisan excel import, bukan jejak scrape. Field-nya ada; artinya yang tidak bisa dipercaya |

Total inventaris: **40 filter** (20 hidup di app, 20 roadmap dari prototype), bukan 32.

---

## 2. Final filter inventory

Kolom **Transformation** merujuk kode `T-xx` di §5; **Dependency** merujuk `D-xx` (§8) dan `V-xx` (§9).

### 2.1 App · Creator Database — 18 kontrol

| # | Filter | Final Field | Source Table | Source Column | Transform | Status | Dependency |
|---|---|---|---|---|---|---|---|
| CD-01 | Search Creator | `search_text` | `kol_directory` · `kol_profile_card` · `kol_categories` | `username`, `bio` / `display_name`, `bio` / `name` | ILIKE berjenjang | `DIRECT` | Pola sudah ada di `db.py` (uncommitted) |
| CD-02 | Platform | `platform_key` | `platforms` ← `platform_id` | `key` | equality | `DIRECT` | Chip YouTube & Facebook tanpa baris |
| CD-03 | Tier | `followers_count` | `kol_directory` | `followers_count` | T-01 | `DECISION` | D-01 |
| CD-04 | Category / Niche | `discovery_category[]` | `kol_categories` ← `category_ids` | `taxonomy_key` | EXISTS atas array | `DIRECT` | V-01 |
| CD-05 | Minimum Followers | `followers_count` | `kol_directory` | `followers_count` | `>= ?` | `DIRECT` | — |
| CD-06 | Minimum ER | `er_pct`, `er_is_outlier` | `kol_directory` (utama) · `kol_metric_daily` (alt) | `engagement_rate` / `er_followers_daily` | T-03 | `DERIVED` | D-02 |
| CD-07 | Max Rate Card | `rate_card_fee` | `l1_silver.unified_rate_card` | `fee` | `<= ?` | `MISSING` | 5 tabel rate card, semuanya 0 baris |
| CD-08 | Verified only | `is_connected` / `verified_status_raw` | `social_account` `[SA]` / `kol_directory` | `oauth_token` / `verified_status` | `oauth_token IS NOT NULL` (ANY) | `DECISION` | D-07 |
| CD-09 | Content Format | `format_dominant` / `format_set[]` | `content_format_daily` `[SA]` | `media_type` | T-05 | `DECISION` | D-03 · 29 KOL |
| CD-10 | Audience Age | `age_band_dominant` | `audience_demographics_daily` `[SA]` | `audience_type='age'` | — | `MISSING` | 0 baris ber-type `age` |
| CD-11 | Audience Gender | `pct_female`, `pct_male`, `known_gender_ratio` | `audience_demographics_daily` `[SA]` | `dimension_key`, `audience_count` | T-02 | `PARTIAL` | 23 KOL · D-05 |
| CD-12 | Creator Location | `creator_city` | `kol_directory` | `creator_city` | normalisasi kota | `MISSING` | Kolom ada, 0/7.720 terisi |
| CD-13 | Audience Location | `audience_city_top1` | `audience_geo_daily` `[SA]` | `geo_key`, `geo_level` | T-06 | `PARTIAL` | 15 KOL · 9 dari 33 key bukan kota |
| CD-14 | Min Authenticity | `authenticity_score` | `feature.ig_` ∪ `tt_audience_analysis` `[SA]` | `authenticity_score` | T-04 | `PARTIAL` | 23 KOL (IG 13 + TT 10) |
| CD-15 | Min Brand Fit | `brand_fit_score` | `feature.brand_fit_analysis` | — | `>= ?` | `MISSING` | 0 baris |
| CD-16 | Max Paid Ratio | `sponsored_ratio`, `post_sample_n` | `l2_gold.post_metric` `[SA]` | `is_sponsored` | T-07 | `PARTIAL` | 29 KOL punya data, 0 lolos >35% |
| CD-17 | Min Campaigns | `campaign_count` | `campaign_kols` ← `agency_kol_accounts` | — | COUNT per KOL | `MISSING` | 0 baris · jalur JOIN **beda** dari `[SA]` |
| CD-18 | Smart Preset ×8 | komposit | gabungan | — | set filter + reorder | `PARTIAL` | 4 dari 8 preset bertumpu field 0 baris |

### 2.2 App · My Creators & Smart Discovery — filter yang tidak ada di prototype

| # | Filter | Final Field | Source Table | Source Column | Transform | Status | Dependency |
|---|---|---|---|---|---|---|---|
| MC-01 | Profiling Status | `scrape_status` | `kol_directory` | `scrape_status` | equality → Ready/Profiling/Failed | `PARTIAL` | 99 KOL (1,28%) · V-04 |
| SD-01 | Lower Price than Ref. | `rate_card_fee` | `l1_silver.unified_rate_card` | `fee` | `fee < fee_reference` | `MISSING` | Sama dengan CD-07 |

### 2.3 Roadmap · ada di prototype, belum di app

Masuk kontrak, di luar build Task 6 tahap 1.

| # | Filter | Final Field | Source Table | Source Column | Transform | Status | Dependency |
|---|---|---|---|---|---|---|---|
| RM-01 | Last Updated | `last_refreshed_at` | `kol_directory` | `last_refreshed_at` | `now() − last_refreshed_at` → bucket | `PARTIAL` | Semantik cacat (B4). Di app: sort saja |
| RM-02 | Audience Interest | `audience_interest_top[]` | `audience_interest_daily` `[SA]` | `interest_key`, `audience_count` | T-04 | `PARTIAL` | 23 KOL · 85,2% bobot `unknown` |
| RM-03 | Audience Quality | `audience_quality_avg` | `feature.ig_` ∪ `tt_audience_analysis` `[SA]` | `authenticity_score`, `audience_quality_score` | T-04 | `PARTIAL` | 23 KOL · bucket High (85+) = 1 KOL |
| RM-04 | Save Rate | `save_rate` | `l2_gold.post_metric` `[SA]` | `saves`, `likes`, `comments` | T-07 | `PARTIAL` | 11 KOL, TikTok saja · D-06 |
| RM-05 | Share Rate | `share_rate` | `l2_gold.post_metric` `[SA]` | `shares`, `likes`, `comments` | T-07 | `PARTIAL` | 11 KOL, TikTok saja · D-06 |
| RM-06 | Views | `avg_views` | `l2_gold.post_metric` `[SA]` | `views` | T-07 | `PARTIAL` | 29 KOL · 3 outlier >10 juta |
| RM-07 | Reliability | — | — | — | — | `MISSING` | 0 kolom di seluruh database |
| RM-08 | Performance Stability | `er_volatility`, `monthly_points_n` | `kol_metric_monthly` `[SA]` | `er_followers_monthly` (deret) | T-08 | `DECISION` | D-08 |
| RM-09 | Viral Frequency | `viral_dependency`, `monthly_points_n` | `kol_metric_monthly` `[SA]` | deret bulanan | T-08 | `DECISION` | D-08 · 5 KOL punya ≥4 titik |
| RM-10 | Growth Classification | `growth_30d_pct`, `actual_window_days` | `l1_silver.unified_profile` `[SA]` | `date`, `followers_count` | T-09 | `MISSING` | 0 akun punya 2 snapshot ≥30 hari |
| RM-11 | Rising Creator | growth + `er_pct` + `followers_count` | gabungan RM-10, CD-06, CD-05 | — | AND 3–4 syarat | `MISSING` | Momentum butuh ≥3 snapshot = 0 akun |
| RM-12 | Data Status | `data_age_hours` ÷ `refresh_interval_hours` | `kol_directory` + config aplikasi | `last_refreshed_at` + peta interval | T-10 | `DECISION` | D-04 · pembilangnya cacat (B4) |
| RM-13 | Update Frequency | `refresh_tier` | `kol_directory` | `refresh_tier` | label → interval | `MISSING` | 0 terisi · tanpa CHECK/enum/comment |
| RM-14 | Next Update | `next_update_at` | turunan RM-01 + RM-13 | — | `last_refreshed_at + interval` | `MISSING` | Penyebut sama dengan RM-12 |
| RM-15 | Monitoring Priority | `monitoring_level` | `campaigns` · `agency_kol_accounts` · `audit_log` · growth | — | rule-based (Product Rev 2) | `MISSING` | 0 dari 6 sinyal bisa dipakai |
| RM-16 | Content Category / Topic | — | — | — | — | `MISSING` | Tidak ada kolom topik konten |
| RM-17 | Content Style | — | — | — | — | `MISSING` | Tidak ada kolom gaya konten |
| RM-18 | Exclude (7 opsi) | campuran | `campaign_kols` · `feature.*` · `post_metric` | — | per opsi | `MISSING` | 5 dari 7 opsi terblokir |
| RM-19 | Collections / Shortlist | `collection_id` | — (tabel baru) | — | membership | `MISSING` | 0 tabel shortlist di seluruh DB |
| RM-20 | Smart Criteria (NL) | mewarisi filter lain | beragam | — | parser pola → set filter | `PARTIAL` | 6 dari 29 aturan berbasis hash prototype |

---

## 3. Filterable projection fields

Kontrak yang dipegang API: **satu baris per KOL**, satu daftar kolom yang boleh muncul di `WHERE`.
Dua tier, dibedakan oleh apakah nilainya bisa dibaca tanpa agregasi.

### 3.1 Tier 1 — query layer, langsung dari `public.kol_directory` + FK

| Field | Tipe | Asal | Coverage | Dipakai |
|---|---|---|---|---|
| `kol_id` | uuid | `kol_directory.id` | 7.720 · 100% | kunci grain |
| `username` | text | `kol_directory.username` | 7.497 · 97,1% | CD-01 |
| `bio` | text | `kol_directory.bio` | 902 · 11,7% | CD-01 |
| `followers_count` | bigint | `kol_directory` | 7.498 · 97,1% | CD-03, CD-05, RM-11 |
| `er_pct` | numeric | `kol_directory.engagement_rate` | 1.756 · 22,7% | CD-06, RM-11 |
| `er_is_outlier` | boolean | turunan: `er_pct > 10` | 83 baris | CD-06 (guard) |
| `platform_key` | text | `platforms.key` ← `platform_id` | 7.496 · 97,1% | CD-02 |
| `discovery_category[]` | text[] | `kol_categories.taxonomy_key` ← `category_ids` | ±4.155 · ~53,8% (V-01) | CD-04 |
| `verified_status_raw` | text | `kol_directory.verified_status` | 931 · 12,1% | CD-08 opsi B · D-07 |
| `creator_city` | varchar | `kol_directory.creator_city` | 0 · 0% | CD-12 |
| `scrape_status` | text | `kol_directory.scrape_status` | 99 · 1,28% | MC-01 |
| `last_refreshed_at` | timestamptz | `kol_directory` | 7.496 · 97,1% — **semantik cacat (B4)** | RM-01, RM-12, RM-14 |
| `created_at` | timestamptz | `kol_directory` | 7.698 · 99,7% | CD-18 (Newly Added) |

### 3.2 Tier 2 — `discovery.kol_filter_base`, hasil jembatan `[SA]` + agregasi

| Field | Tipe | Asal | Coverage | Dipakai |
|---|---|---|---|---|
| `kol_id` | uuid | LEFT JOIN dari `kol_directory` | 7.720 · 100% | join key |
| `social_account_n` | int | count `kol_social_account` | 7.496 punya ≥1 | guard grain |
| `is_connected` | boolean | `social_account.oauth_token IS NOT NULL` (ANY) | 0 true · 0% | CD-08 opsi A |
| `display_name` | text | `kol_profile_card.display_name` | 1.958 · 25,4% | CD-01 |
| `bio_l2` | text | `kol_profile_card.bio` | 1.873 · 24,3% | CD-01 (union bio) |
| `er_pct_l2` | numeric | `kol_metric_daily.er_followers_daily` × 100 | 22 · 0,28% | CD-06 (rekonsiliasi) |
| `pct_female` / `pct_male` | numeric | `audience_demographics_daily` | 23 · 0,30% | CD-11 |
| `known_gender_ratio` | numeric | 1 − porsi `unknown` | rata-rata 28,7% | CD-11 guard · D-05 |
| `audience_city_top1` | text | `audience_geo_daily` `geo_level='city'` | 15 · 0,19% | CD-13 |
| `audience_interest_top[]` | text[] | `audience_interest_daily`, `unknown` dibuang | 23 · 0,30% | RM-02 |
| `authenticity_score` | numeric | `feature.ig_` ∪ `tt_audience_analysis` | 23 · 0,30% | CD-14, RM-03 |
| `audience_quality_score` | numeric | idem | 23 · 0,30% | RM-03 |
| `audience_quality_avg` | numeric | `(auth + quality) / 2` | 23 · rentang 43,5–90,0 | RM-03, CD-18 |
| `format_dominant` / `format_set[]` | text / text[] | `content_format_daily.media_type` | 29 · 0,38% | CD-09 · D-03 |
| `avg_views` | numeric | `post_metric.views` | 29 · 0,38% | RM-06, CD-18 |
| `save_rate` / `share_rate` | numeric | `post_metric.saves` / `.shares` | 11 · 0,14% (TikTok) | RM-04, RM-05 |
| `sponsored_ratio` | numeric | `post_metric.is_sponsored` | 29 · 0,38% | CD-16, RM-18 |
| `post_sample_n` | int | count `post_metric` | min 1 · avg 15,9 · max 200 | guard semua rasio · D-06 |
| `monthly_points_n` | int | count `kol_metric_monthly` | 30 punya ≥1 · 5 punya ≥4 | RM-08, RM-09 guard |
| `er_monthly_avg` / `_stddev` / `_max` | numeric | deret `kol_metric_monthly` | 5 · 0,06% usable | RM-08, RM-09 (input mentah) |

### 3.3 Aturan lintas-filter yang wajib

Setiap filter dengan coverage <90% harus **tri-state**: cocok / tidak cocok / **tidak diketahui**,
dengan parameter `include_unknown` (default `false`) yang bisa dibalik dari UI.

Tanpa itu, menyalakan satu filter audiens menyembunyikan >99% populasi dan pengguna menyimpulkan
"tidak ada kreator yang cocok", padahal yang benar adalah "nilainya belum diketahui". Untuk
**22 dari 40 filter**, ini satu-satunya yang membedakan hasil jujur dari hasil menyesatkan.

---

## 4. Source mapping — pengelompokan A–E

Satu filter bisa muncul di dua kelompok kalau memang butuh dua hal sekaligus; jumlah per kelompok
karena itu tidak menjumlah 40. Yang menjumlah 40 adalah §2.

**A · Direct source (6)** — CD-01 Search · CD-02 Platform · CD-04 Category · CD-05 Min Followers ·
MC-01 Profiling Status · CD-18 preset *Newly Added*.

**B · Derived / calculated (11)** — CD-03 Tier · CD-06 ER · CD-09 Format · CD-11 Gender ·
CD-13 Aud. Location · CD-14 Authenticity · CD-16 Paid Ratio · RM-03 Aud. Quality ·
RM-04 Save · RM-05 Share · RM-06 Views.

**C · Partial coverage (12)** — semuanya bertumpu pada dua tabel yang sama:

| Sumber penghambat | Filter |
|---|---|
| Data audiens · 23 KOL · 0,30% | CD-11, CD-13, CD-14, RM-02, RM-03 |
| Data konten · 30 KOL · 0,39% | CD-09, CD-16, RM-04, RM-05, RM-06 |
| Lain | MC-01 (1,28%) · RM-01 (terisi 97,1% tapi semantik cacat) |

**D · Missing (14)** — dipisah per sebab, karena pemiliknya berbeda:

| Sebab | Filter | Yang sebenarnya kurang |
|---|---|---|
| Tabel kosong | CD-07, SD-01, CD-15, CD-17, RM-15, RM-18 | `unified_rate_card`, `brand_fit_analysis`, `campaigns`/`campaign_kols` — **schema lengkap, FK utuh** |
| Kolom ada, data 0 | CD-12, RM-13 | `creator_city`, `refresh_tier` — butuh jalur pengisian, bukan schema |
| Tidak ada barisnya | CD-10 | `audience_type='age'` tidak pernah ditulis pipeline |
| Tidak ada kolomnya | RM-07, RM-16, RM-17 | Sapuan katalog: 0 kolom consistency, topik konten, gaya konten |
| Kedalaman history | RM-10, RM-11 | 0 akun punya 2 snapshot ≥30 hari; 0 punya 3 |
| Turunan penyebut kosong | RM-14 | Interval update |
| Tidak ada tabelnya | RM-19 | Collections/shortlist — **satu-satunya tabel baru yang perlu** |

**E · Needs decision (8)** — CD-03 · CD-06 · CD-08 · CD-09 · CD-11 · CD-16/RM-04/RM-05 ·
RM-08/RM-09 · RM-12. Detail di §8.

---

## 5. Transformation / calculation

| # | Nama | Rumus / rule | Guard wajib | Kesiapan |
|---|---|---|---|---|
| T-01 | Tier bucket | Bucket dari `followers_count` saat query, batas dari config — **bukan** membaca kolom `tier`. Coverage 93,2% vs 25,5% lewat L2 | `<1K` di luar semua chip (304 KOL); NULL = unknown (222) | D-01 |
| T-02 | Gender renormalisasi | `pct_female = female / (total − unknown)`. Female-skewed ≥60%, Male-skewed ≥55% | `known_gender_ratio` diekspos; ambang minimumnya D-05 | Rumus final |
| T-03 | ER normalisasi | Satuan **persen**. `kol_directory.engagement_rate` apa adanya; L2 `er_followers_daily` **×100** | `er_is_outlier = er_pct > 10` (83 baris, maks 223,41%) | D-02 |
| T-04 | Audience UNION + skor | UNION `feature.ig_audience_analysis` + `tt_audience_analysis`; `audience_quality_avg = (authenticity + quality)/2`. Interest: buang `unknown` lalu rank by `audience_count` | Satu akun tidak boleh muncul di dua tabel sekaligus | Rumus final |
| T-05 | Format mapping | `clips→Reels` · `carousel_container`/`CAROUSEL→Carousel` · `feed→Feed` · Video = `clips`+`VIDEO` · Photo = `feed`+Carousel · **Story tidak punya sumber** | `unknown` (3 KOL) tidak dipetakan, bukan dibuang | D-03 |
| T-06 | Geo normalisasi | Top-1 `geo_key` pada `geo_level='city'`, dengan peta koreksi granularitas | 9 dari 33 key sebenarnya provinsi/pulau (Bali, Sulawesi, Jawa, Banten, Lampung) — menyentuh 10 dari 15 KOL | Peta koreksi belum ditulis |
| T-07 | Rasio post | `save_rate = Σsaves / Σ(likes+comments)`; `share_rate` idem dengan `shares`; `sponsored_ratio = Σis_sponsored / n`; `avg_views = avg(views)` | `post_sample_n` diekspos — satu KOL rasionya berasal dari **1 post** | D-06 |
| T-08 | Volatilitas & viral | **Belum ada rumus yang bisa dieksekusi.** Prototype memakai `k.cons` (hash), bukan perhitungan. View hanya mengekspos input mentah | Minimum 4 titik bulanan; 0 KOL punya 6 bulan, maksimum 5 | D-08 |
| T-09 | `growth_30d` | Bandingkan snapshot terbaru dengan snapshot terdekat yang ≥30 hari lebih tua, dari `l1_silver.unified_profile` (grain dijamin `uq_unified_profile`). **Wajib mengembalikan `actual_window_days`** | `f_prev > 0` (19 akun bermasalah) · `DISTINCT ON` di kedua CTE | 0 akun memenuhi |
| T-10 | Freshness ratio | `ratio = age_hours / interval_hours` → Fresh <0,5 · Aging <0,85 · Due <1,2 · Outdated ≥1,2. Interval dari label `refresh_tier` lewat peta di config | Pembilang harus diperbaiki dulu — 73,6% `last_refreshed_at` tidak berasal dari scrape | D-04 |

> **Jangan dipakai.** `l2_gold.kol_profile_card.followers_growth` **bukan** growth 30 hari.
> Ekspresi hidupnya `LAG()` antar-snapshot berapa pun jaraknya; jarak nyata sekarang **10 hari**
> (22 akun) dan **13 hari** (3 akun). Sah sebagai "perubahan sejak snapshot terakhir", dan hanya itu.
> Growth 30D **harus** lewat T-09.

---

## 6. VIEW & query-layer design

### 6.1 Empat lapis

| | Lapis | Isi |
|---|---|---|
| **L1** | **Query layer — tanpa objek DB** | SQL builder berparameter untuk semua field Tier 1. Populasi 7.720 baris dengan dua JOIN FK; VIEW di sini tidak membeli apa pun dan menambah satu migration untuk dirawat. Polanya sudah dimulai di `db.search_kol_directory()` |
| **L2** | **`discovery.kol_filter_base` — satu VIEW biasa** | Meratakan field Tier 2 menjadi satu baris per KOL. Alasannya **bukan performa** melainkan satu sumber kebenaran: 15 filter memakai jembatan `[SA]` yang sama, dan menulis ulang jembatan itu 15 kali di kode aplikasi persis cara dua definisi mulai menyimpang — yang **sudah terjadi** pada *Verified* |
| **L3** | **`growth_30d` — CTE** | Bukan kolom, bukan tabel. Dihitung on-demand dari `unified_profile`, mengembalikan `growth_pct` **dan** `actual_window_days`. Jendela nyata tidak akan pas 30 hari, dan menyembunyikannya membuat angka tidak bisa diaudit |
| **L4** | **Interval refresh — konstanta di config** | Peta `refresh_tier` → jam berisi empat nilai; itu tidak pantas jadi tabel. Kolom `refresh_tier` yang sudah ada dipakai untuk labelnya. **Berlaku hanya jika interval seragam per tier** — lihat D-04 |

**Kenapa VIEW biasa, bukan MATERIALIZED.** Tabel dasarnya menyentuh 23–30 KOL. Matview menambah
kontrak refresh (siapa menjalankan, kapan, seberapa basi boleh) untuk keuntungan performa yang hari
ini nol. Naikkan ke MATERIALIZED dengan pemicu eksplisit, bukan firasat: saat `post_metric` menutup
>1.000 KOL, **atau** saat view ini melewati ~200 ms pada query filter penuh.

### 6.2 Aturan masuk VIEW

Field masuk `kol_filter_base` hanya kalau **ketiganya** benar:

- **R1** — butuh jembatan `[SA]` **atau** UNION lintas tabel platform; tidak cukup dibaca dari
  `kol_directory` + satu JOIN FK.
- **R2** — butuh agregasi (`GROUP BY`, ranking, rasio) untuk turun ke grain **satu baris per KOL**.
- **R3** — sumbernya punya **minimal satu baris hari ini**. Kolom yang selalu `NULL` adalah
  kebohongan yang harganya satu JOIN.

| Kandidat | R1 | R2 | R3 | Putusan |
|---|---|---|---|---|
| `platform_key`, `followers_count`, `er_pct`, `last_refreshed_at`, `creator_city`, `scrape_status`, `created_at` | ✗ | ✗ | ✓ | Query layer |
| `discovery_category[]` | ✗ (array di `kol_directory`) | EXISTS, bukan GROUP BY | ✓ | Query layer |
| `is_connected` | ✓ | ✓ (ANY atas >1 akun) | ✓ | **Masuk VIEW** |
| `display_name`, `bio_l2`, `er_pct_l2` | ✓ | ✓ (1:1 hari ini, tidak dijamin) | ✓ | **Masuk VIEW** |
| `pct_female`, `pct_male`, `known_gender_ratio` | ✓ | ✓ renormalisasi | ✓ (23) | **Masuk VIEW** |
| `audience_city_top1`, `audience_interest_top[]` | ✓ | ✓ ranking | ✓ (15 / 23) | **Masuk VIEW** |
| `authenticity_score`, `audience_quality_*` | ✓ **UNION 2 tabel** | ✓ | ✓ (23) | **Masuk VIEW** |
| `format_dominant` / `format_set[]` | ✓ | ✓ mapping + ranking | ✓ (29) | **Masuk VIEW** |
| `avg_views`, `save_rate`, `share_rate`, `sponsored_ratio`, `post_sample_n` | ✓ | ✓ | ✓ (11–30) | **Masuk VIEW** |
| `monthly_points_n`, `er_monthly_avg`/`_stddev`/`_max` | ✓ | ✓ | ✓ (30 punya ≥1) | **Masuk VIEW — input mentah saja**, bukan verdict (D-08) |
| `growth_30d_pct` | ✓ | ✓ tapi **berjendela waktu** | **0 akun memenuhi** | **CTE terpisah** |
| `age_band`, `brand_fit_score`, `rate_card_fee`, `campaign_count`, `reliability`, `content_topic`, `content_style` | — | — | **0 baris / 0 kolom** | **Tidak masuk** |

Hasilnya **±21 kolom**, bukan 40. Dua pengecualian punya alasan kedua yang tetap berlaku setelah
datanya ada:

- `growth_30d` adalah perbandingan **antar dua titik waktu**, sementara view ini proyeksi datar.
  Meratakannya ke satu kolom menyembunyikan `actual_window_days`, dan angka growth tanpa jendelanya
  tidak bisa diaudit.
- `campaign_count` jalur JOIN-nya **bukan** `[SA]` melainkan
  `kol_directory ← agency_kol_accounts ← campaign_kols`. Begitu data campaign masuk, ia jadi view
  kedua, bukan kolom tambahan di view ini.

### 6.3 Grain & jalur JOIN

```
public.kol_directory.id                          7.720 — populasi & grain
  ← public.kol_social_account.kol_id             7.496 · 97,1%
      .social_account_id → public.social_account.id
                            ├─ l2_gold.kol_profile_card          1.976
                            ├─ l2_gold.post_metric                  30
                            ├─ l2_gold.kol_metric_daily / _monthly
                            ├─ l2_gold.content_format_daily         30
                            ├─ l2_gold.audience_*_daily             23
                            └─ feature.{ig,tt}_audience_analysis 13 + 10

jalur terpisah — jangan dicampur:
  kol_directory.id ← agency_kol_accounts.kol_account_id           7.719
                       ← campaign_kols.agency_kol_account_id       0 baris
```

### 6.4 Tiga guard yang harus ada di definisi VIEW

1. **`LEFT JOIN` dari `kol_directory`** — supaya 224 KOL tanpa `social_account` tetap ada di
   populasi dan tidak diam-diam hilang dari hasil.
2. **Grain dijaga eksplisit.** Hari ini 1 KOL = 1 `social_account` (7.496 baris, tidak ada yang
   ganda), tapi itu **tidak dijamin constraint** — begitu satu KOL punya akun di dua platform,
   agregasi harus tetap menghasilkan satu baris.
3. **View ini tidak menyelesaikan 277 grup `username_normalized` duplikat.** Dedup adalah pekerjaan
   terpisah dan harus diputuskan (D-12) sebelum angka hasil filter dipakai sebagai laporan.

---

## 7. Data gap

| Gap | Menopang | Kondisi sekarang | Jenis pekerjaan |
|---|---|---|---|
| Data konten | 10 filter | `post_metric` / `content_format_daily` = **30 KOL · 0,39%** | Perluas scraping post |
| Data audiens | 5 filter | `audience_*` / `feature.*` = **23 KOL · 0,30%** | Perluas inferensi audiens |
| Kedalaman snapshot profil | 2 filter | 0 akun punya 2 snapshot ≥30 hari; 25 akun punya 2 snapshot berjarak 10–13 hari | Re-scrape ~17 Sep 2026 membuka 1.971 akun |
| Kedalaman deret bulanan | 2 filter | 5 KOL punya ≥4 titik; **0 KOL punya 6 bulan** | Waktu — tidak bisa dipercepat dengan volume |
| Interval update per KOL | 3 filter | `refresh_tier` 0/7.720 · `scheduler_config` 0 baris | Keputusan (D-04), lalu pengisian |
| Semantik `last_refreshed_at` | 4 filter | 5.520 dari 7.496 (73,6%) tanpa jejak `l0_raw`; umur median 847 hari | Perbaiki penulis field-nya di pipeline |
| Kota kreator | 1 filter | Kolom ada, 0 terisi. `influencer_address` ditolak (118 KOL, 43 nilai `Jalan jalan`) | Isi saat registrasi/onboarding |
| Data campaign | 4 filter | 14 tabel, 13 kosong, FK utuh sampai `kol_directory` | Adopsi produk — **bukan engineering** |
| Rate card | 3 filter | 5 tabel rate card, semuanya 0 baris | Adopsi produk |
| OAuth connection | 1 filter | 0 dari 7.496 akun connect; pipeline sudah benar | Adopsi — **bukan engineering** |
| Kolom yang memang tidak ada | 3 filter | Reliability, topik konten, gaya konten — 0 kolom di seluruh DB | Feature baru + definisi produk |
| Tabel Collections | 1 filter | 0 tabel shortlist | **Satu-satunya tabel baru yang perlu** |

---

## 8. NEEDS DECISION

Tidak ada satu pun yang diputuskan sendiri di dokumen ini. Kolom terakhir membedakan dua hal yang
sering tercampur: **memblokir desain Task 5** (bentuk kolom atau arsitektur berubah tergantung
jawabannya) versus memblokir implementasi Task 6 (angkanya tinggal dimasukkan ke config).

| # | Item | Current finding | Decision needed | Blocking Task 5? |
|---|---|---|---|---|
| D-01 | Tier boundaries | UI: Mid 50K–500K, Macro 500K–1M. `public.kol_tiers`: Mid 50K–100K, Macro 100K–1M. App nyata memakai batas DB. Macro = 191 KOL (batas UI) vs 1.290 KOL (batas DB, seluruh direktori) | Batas mana yang berlaku, dan apakah `kol_tiers` ikut diubah supaya tidak ada dua kebenaran | **No** — desain menaruh batas di config; keputusan memblokir Task 6 |
| D-02 | ER cleaning | 1.756 nilai terisi, **83 di atas 10%**, maksimum 223,41% — mustahil untuk metrik ini | Buang barisnya, atau NULL-kan nilainya dan tandai `er_is_outlier`? Membuang berarti 83 KOL hilang dari **semua** hasil, bukan cuma dari filter ER | **No** — desain mengekspos nilai + flag |
| D-03 | Format: dominant vs set | Prototype memakai format **dominan** (1 nilai). App merender **chip** yang implikasinya keanggotaan (banyak nilai) | "Format dominannya X" atau "pernah memposting X"? Menentukan tipe kolom: `text` atau `text[]` | **Yes** — bentuk projection berubah |
| D-04 | Refresh tier & interval | `refresh_tier` ada tapi 0% terisi, tanpa CHECK, enum, comment, atau satu pun kode yang menulisnya. `scheduler_config` 0 baris dan bentuknya jam absolut global | Daftar level final, peta level→jam, dan yang paling menentukan: **interval seragam per tier (config) atau bisa diatur per KOL (harus kolom DB)?** | **Yes** — menentukan ada tidaknya perubahan schema |
| D-05 | Gender minimum sample | `unknown` rata-rata **71,3%** per KOL. Tanpa renormalisasi: 0 KOL lolos. Setelah renormalisasi: 17 KOL — dihitung dari 28,7% audiens yang gendernya diketahui | Ambang minimum `known_gender_ratio` supaya satu KOL tidak dinilai dari sampel terlalu tipis | **No** — `known_gender_ratio` sudah diekspos |
| D-06 | Post minimum sample | 30 KOL punya `post_metric`. Paling sedikit **1 post**, rata-rata 15,9, terbanyak 200. Save/Share hanya TikTok (11 KOL, 0 Instagram) | Minimum post untuk sebuah rasio boleh ditampilkan; dan apakah Save/Share Rate boleh tayang sebagai filter yang diam-diam khusus TikTok | **No** — `post_sample_n` sudah diekspos |
| D-07 | Verified semantics | Dua definisi hidup bersamaan. Pipeline (migration 006/011/020): `oauth_token IS NOT NULL` → **0 KOL**. App (`kolDirectory.ts:157`): `verified_status IN ('verified','true','yes')` → **454 KOL**. Keduanya tidak bisa benar bersamaan; app saat ini menampilkan yang kedua | Mana yang dimaksud "Verified" di UI. Kalau keduanya dipertahankan, keduanya butuh **nama yang berbeda** di UI dan projection | **Yes** — menentukan field mana yang jadi filter, dan keduanya hidup di lapisan berbeda |
| D-08 | Stability / Viral formula | Prototype menghitungnya dari `k.cons` — **hash ID, bukan data**. Ambang "Stable <28" dan "viral ≥55" tidak punya rumus yang menghasilkannya. Sapuan katalog: 0 kolom consistency di seluruh DB | Rumus volatilitas dan ketergantungan viral dalam bentuk yang bisa dieksekusi, plus minimum titik deret | **No** — view mengekspos input mentah. **Tapi filternya sendiri tidak bisa dispesifikasi sampai ini keluar** |
| D-09 | Perlakuan nilai unknown | 22 dari 40 filter coverage <90%; 12 di bawah 1% | Default `include_unknown`, dan apakah UI menandai filter coverage rendah secara eksplisit | **No** — tri-state sudah jadi aturan desain (§3.3) |
| D-10 | Chip tanpa data | YouTube & Facebook (0 baris `platforms`), Story (0 baris `unified_story`), Tech (2 KOL), Audience Quality High 85+ (1 KOL) | Sembunyikan, atau tampilkan dengan penanda "belum ada datanya" | **No** |
| D-11 | Threshold Growth & Rising | Belum ada **satu pun** sampel 30D nyata di database | Ambang bucket — **ditunda sampai T-09 hidup.** Menetapkannya sekarang berarti menebak | **No** — tapi jangan diputuskan sekarang |
| D-12 | Dedup 277 username | 277 grup `username_normalized` duplikat = 277 baris ekstra. Satu kreator bisa muncul dua kali di hasil filter | Apakah Discovery mendedup di query, atau menunggu pembersihan di roster | **No** — tapi memengaruhi setiap angka hasil filter |

### Putusan

**Desain Task 5 bisa difinalisasi sekarang kecuali tiga item: D-03, D-04, dan D-07.**

D-03 dan D-07 bisa di-*unblock* dengan membawa kedua bentuk sekaligus ke projection —
`format_dominant` **dan** `format_set[]`, `is_connected` **dan** `verified_status_raw`. Itu murah
secara teknis, tapi bukan default yang aman: membawa dua field "verified" yang saling bertentangan
ke dalam satu kontrak adalah persis kondisi yang membuat app hari ini menampilkan definisi yang
salah. Kalau ditempuh, tempuh sebagai keputusan sadar dengan penamaan yang memaksa perbedaannya
terlihat.

**D-04 tidak bisa di-unblock** — jawabannya menentukan ada atau tidaknya perubahan schema.

---

## 9. NEEDS VERIFICATION

Database tidak bisa dijangkau saat dokumen ini ditulis (TCP timeout ke `10.100.14.216:5432`,
kemungkinan butuh VPN). Angka di dokumen ini berasal dari audit Task 2–4 dan silang-baca repo,
**bukan query baru**.

| # | Yang harus diverifikasi | Kenapa penting | Memblokir |
|---|---|---|---|
| V-01 | `category_id` vs `category_ids` — mana yang benar-benar terisi | Task 2–4 dan kedua Excel memakai `category_id` skalar. App dan `db.py` yang baru memakai `category_ids` array. Coverage berbeda: 3.070 (5 chip via skalar) vs 3.376 (5 chip via array) vs ±4.155 (taxonomy) | **Ya** — projection CD-04 |
| V-02 | Coverage `taxonomy_key` = 4.155 KOL unik | Angka ini berasal dari *commit message* migration 029, bukan dari query yang dijalankan ulang | Tidak — angka, bukan bentuk |
| V-03 | Macro: 1.123 atau 1.290 KOL | Task 3 §5.5 dan `KOL_DISCOVERY_AUDIT` §3.3 menyebut dua angka berbeda dengan denominator yang tidak dinyatakan (kartu L2 vs seluruh direktori). Ini bahan D-01 | Tidak — tapi D-01 butuh angka yang benar |
| V-04 | Nilai `scrape_status` yang ada & petanya ke Ready / Profiling / Failed | Yang diketahui hanya 72 `failed` + 27 `success` = 99 baris. Tidak ada nilai yang berpadanan dengan "Profiling" | **Ya** — projection MC-01 |

---

## 10. Yang tidak perlu dibuat

Ditulis eksplisit supaya tidak ada yang mengerjakannya karena mengira perlu.

| Jangan buat | Alasan |
|---|---|
| Kolom `growth_30d` / `growth_90d` | Turunan murni dari deret snapshot; menyimpannya berarti dua kebenaran dan satu pekerjaan refresh |
| Kolom `next_refresh_at` | `last_refreshed_at + interval` — dihitung, bukan disimpan |
| Kolom `monitoring_priority` | `refresh_tier` sudah ada, kosong, dan tipenya cukup |
| Tabel history followers baru | `l1_silver.unified_profile` sudah menjadi itu, grain dijamin `uq_unified_profile` |
| Tabel campaign apa pun | 14 tabel sudah ada dan FK-nya utuh sampai `kol_directory`; yang kurang datanya |
| Tabel log akses baru | `public.audit_log` bentuknya sudah tepat (`actor_id`, `action`, `entity_type`, `entity_id`, `created_at`) — mengisinya lebih murah |
| Tabel antrean refresh baru | Periksa `campaign_tracking_jobs` dulu — 0 baris, tapi bentuknya sudah job-queue |
| Index di `last_refreshed_at` / `refresh_tier` | 7.720 baris; seq scan murah. *(Yang justru terbukti perlu: index di `kol_social_account.kol_id` — ketiadaannya membuat versi LATERAL query search berjalan 2.080 ms vs 11 ms dengan hash join.)* |
| MATERIALIZED VIEW | Tabel dasarnya 23–30 KOL. Naikkan hanya kalau salah satu pemicu di §6.1 terpenuhi |
| Mengisi `kol_metric_daily/monthly.followers_growth` | Grain-nya tanggal **posting**, bukan tanggal snapshot — salah tempat secara konseptual |
| Perbaikan transform `is_verified` | **Akan merusak business rule.** Badge platform dibuang dengan sengaja di migration 006 sesuai keputusan mentor; kode sudah benar dan konsisten 100% dengan data |
| `kol_directory.verified_status` sebagai pengganti Verified | 454 baris yang tidak ada hubungannya dengan OAuth. Memakainya menampilkan 454 KOL yang justru **tidak** connect — kecuali D-07 memutuskan sebaliknya, dengan nama filter yang berbeda |
| `audience_geo_daily` sebagai lokasi kreator | Menjawab pertanyaan berbeda: "penonton ada di mana", bukan "kreator tinggal di mana". Di UI keduanya filter terpisah |

---

**Audit trail.** Task 5 = design only. Tidak ada perubahan pada database, schema, migration, source
code, config, Excel, atau dokumen Task 1–4; tidak ada commit/push dari penyusunan dokumen ini.
