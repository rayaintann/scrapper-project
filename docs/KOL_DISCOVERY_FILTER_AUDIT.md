# KOL Discovery — Audit Filter (Prototype vs Database)

**Scope:** Semua filter yang dirancang di prototype UI, dibandingkan dengan kondisi data aktual.
**Tanggal audit:** 2026-09-02
**Sumber UI:** `app/AUTOME~1.HTMl` (354 KB, 2.046 baris)
**Database:** `kol` @ 10.100.14.216:5432 — sesi read-only (`set_session(readonly=True)`)

> Semua angka di dokumen ini hasil query langsung ke database pada 2026-09-02.
> Angka di `L0_L1_L2_FLOW.md` dan `AUTOMETRIC_METRICS_DATA_DICTIONARY.md`
> **tidak** dipakai sebagai sumber — semuanya diverifikasi ulang.
> Yang tidak ditemukan ditulis **tidak ditemukan**, bukan diperkirakan.

**Status singkat:** dari 20 filter yang dirancang di prototype, **4 siap pakai**,
**11 ada datanya tapi belum lengkap**, **5 tidak ada datanya sama sekali**, dan
**3 filter punya state di kode tapi kontrol UI-nya tidak pernah dirender**.

| Basis | Jumlah |
|---|---:|
| `public.kol_directory` | 7.720 |
| `public.kol_social_account` / `social_account` | 7.496 |
| `l2_gold.kol_profile_card` | 1.976 akun |
| `l2_gold.post_metric` / `kol_metric_daily` / `content_format_daily` | **30 akun** |
| `l2_gold.audience_*` / `feature.*_audience_analysis` | **23 akun** |

---

## 1. Filter dari Prototype

Dibaca dari `ADV_DEFAULT`, `filterModalHTML()`, dan `filterKols()` (baris 757–853).

### 1.1 Modal Advanced Filters — 17 kontrol dirender

| Filter | Bentuk UI | Value/Range di UI | Keterangan |
|---|---|---|---|
| Tier | Chip row | All · Nano · Micro · Mid · Macro · Mega | Cocok ke `k.tier`, dihitung client-side oleh `TIER()` |
| Format | Chip row | All · Reels · Feed · Carousel · Story | Satu format dominan per kreator (`k.format`), bukan per post |
| Platform | Chip row | All · instagram · tiktok | Data `k.plat` array; facebook ada di data tapi tidak ada chip-nya |
| Min. followers | Range slider | 0–3000, step 50, satuan K (≥1000 → M) | Plafon efektif 3 juta follower |
| Min. est. reach | Range slider | 0–1000, step 20, satuan K | `k.estReach` = turunan client-side dari reach × auth × postFreq |
| Min. avg. views | Range slider | 0–500, step 10, satuan K | Rata-rata views per konten |
| Min. engagement | Range slider | 0–10, step 0.1, satuan % | Dibandingkan sebagai persen, bukan fraksi |
| Min. posting freq. | Range slider | 0–10, step 0.2, satuan /minggu | Frekuensi posting mingguan |
| Max. rate card | Range slider | 0–5000, step 100, satuan USD (`$`) | Label pakai `$` dan `toLocaleString()` |
| Age (top audience group) | Chip row | All · 13-17 · 18-24 · 25-34 · 35-44 · 45-54 · 55+ | Satu bucket umur dominan per kreator |
| Major Female (%) | Range slider | 0–100, step 5, "≥ N%" | Cek `k.gF < a.femaleMin` |
| Major Male (%) | Range slider | 0–100, step 5, "≥ N%" | Diturunkan sebagai `100 − k.gF`, bukan kolom sendiri |
| Min. audience authenticity | Range slider | 0–100, satuan % | Skor 0–100 |
| Min. brand fit score | Range slider | 0–100 | Dipetakan ke `k.match` |
| Max. paid content ratio | Range slider | 0–100, satuan % | Porsi konten bersponsor |
| Min. campaigns run | Range slider | 0–15 | Jumlah campaign yang pernah dijalankan |
| Verified creators only | Toggle switch | on / off | Boolean `k.ver` |

### 1.2 Dead state — dipakai `filterKols()`, kontrolnya tidak pernah dirender

| Filter | Bentuk UI | Value/Range di UI | Keterangan |
|---|---|---|---|
| Creator domicile | **tidak ada** | state `domicile:'all'` | Dipakai `filterKols()` via `k.loc` |
| Audience domicile | **tidak ada** | state `audDomicile:'all'` | Dipakai `filterKols()` via `k.audLoc` |
| Audience interest | **tidak ada** | state `interest:'all'` | Dipakai `filterKols()` via `k.interests` |

`wireFilterModal()` (baris 849) mencari elemen `#fDom`, `#fAudDom`, `#fInterest`,
tapi `filterModalHTML()` tidak pernah menghasilkan ketiganya. `activeFilterCount()`
tetap menghitungnya dan `saveCurrentList()` tetap menyimpannya — pengguna hanya
tidak punya cara mengubahnya.

### 1.3 Filter di luar modal (halaman Directory)

| Filter | Bentuk UI | Value/Range di UI | Keterangan |
|---|---|---|---|
| Category | Chip row di header | all · Fitness · Lifestyle · Beauty · Food · Tech | Hardcoded di `const cats` (baris 868 & 1584) |
| Keyword search | Text input | free text | Match ke `name`, `niche`, `cat` |
| Sort | Dropdown | Best match · Followers · Engagement · Authenticity · Growth · EMV | Bukan filter, tapi butuh kolom yang sama |

### 1.4 Permukaan filter kedua — halaman Audience Insights (`state.ai2`)

Terpisah dari modal Directory (baris 1634–1712). Menambah tiga kebutuhan yang
tidak ada di modal: **Province**, **Audience quality score**, dan gender sebagai
*kategori* (bukan slider).

| Filter | Bentuk UI | Value/Range di UI | Keterangan |
|---|---|---|---|
| Province | Pill + popover | 6 provinsi dari `PROVMAP` | DKI Jakarta, West Java, East Java, North Sumatra, Bali, DI Yogyakarta |
| City | Pill + popover | Distinct `k.audLoc` | Anak dari Province; reset saat Province berubah |
| Country | Pill (statis) | "Indonesia" | Hardcoded, tidak interaktif |
| Audience quality | Pill + popover | Quality ≥ N | Skor `k.q`, tidak ada padanannya di modal Directory |
| Gender | Pill + popover | all · female · male | Threshold `gF≥60` / `gF≤40`, bukan slider |

---

## 2. Perbandingan UI vs Database

Kolom "Data di DB" berisi nilai yang benar-benar ada saat query dijalankan,
bukan definisi kolom.

| Filter | Kebutuhan UI | Table | Column | Data di DB | Sesuai/Tidak | Catatan |
|---|---|---|---|---|---|---|
| Tier | 5 label tier | `l2_gold.kol_profile_card` | `tier` | Macro 1.123 · Mid-tier 342 · Mega 321 · Micro 123 · Nano 63 · NULL 4 | Sebagian | Label DB `Mid-tier`, UI kirim `Mid` → tidak akan match |
| Platform | instagram / tiktok | `l2_gold.kol_profile_card` | `platform` | instagram 935 · tiktok 1.041 | **Sesuai** | Facebook di data prototype tidak ada di DB (`platforms` hanya 2 baris) |
| Min. followers | 0–3.000K | `l2_gold.kol_profile_card` | `followers_count` | 1.972/1.976 terisi · 0 – 685.896.635 | Sebagian | Plafon UI 3M < max DB 686M; 321 akun Mega di luar jangkauan slider |
| Verified only | boolean | `l2_gold.kol_profile_card` | `is_verified` | False 1.976 · **True 0** | **Tidak** | Nilai hilang di transform — lihat §6.3 |
| Format | Reels/Feed/Carousel/Story | `l2_gold.post_metric` | `media_type` | clips 89 · carousel_container 67 · feed 22 · NULL 8 · VIDEO 289 · CAROUSEL 2 | Sebagian | Butuh mapping; **Story tidak ada** |
| Min. engagement | persen 0–10 | `l2_gold.kol_metric_daily` | `er_followers_daily` | 73/280 terisi · 0,0000164 – 0,1615 (**fraksi**) | **Tidak** | DB fraksi, UI persen → butuh ×100. Cakupan 30 akun |
| Min. engagement *(alt)* | persen 0–10 | `public.kol_directory` | `engagement_rate` | 1.756/7.720 terisi · 0 – 223,41 · median 0,60 | Sebagian | Sudah persen. 83 baris >10% keluar range slider; max 223% outlier |
| Min. avg. views | 0–500K | `l2_gold.post_metric` | `views` | 393/477 terisi · max 12.663.900 | Sebagian | Cakupan 30 akun; perlu agregasi rata-rata per akun |
| Min. est. reach | 0–1.000K | `l2_gold.kol_metric_daily` | `reach_sum` | **0/280 terisi** | **Tidak** | NULL 100%. `feature.*_audience_analysis.avg_reach` juga 0/23 |
| Min. est. reach *(alt)* | 0–1.000K | `l0_raw.kol_roster_import` | `estimated_reach` | 7.494 terisi · 0 – 277.851.253 · median 11.678 | Sebagian | Ada di L0 cakupan penuh, tidak pernah naik ke L1/L2. Bertipe `text` |
| Min. posting freq. | 0–10 /minggu | `l2_gold.post_metric` | `post_date` + `social_account_id` | Turunan: 0,05 – 70,0 /minggu · rata-rata 7,78 | **Tidak** | Bisa dihitung tapi tidak stabil: 13 dari 30 akun rentangnya <30 hari |
| Max. rate card | 0–5.000 USD | `l1_silver.unified_rate_card` | `fee` | **0 baris** | **Tidak** | `l0_harmonization.*_rate_card` dan `l0_extra.*_rate_card` juga 0 |
| Max. rate card *(alt)* | 0–5.000 USD | `l0_raw.kol_roster_import` | `reel_price`, `feed_photo_price`, `story_price`, … | 7.229 akun punya ≥1 harga >0 · reel_price 0 – 1.000.000.000 | **Tidak** | Nilai **IDR**, UI **USD**. 4.598 dari 7.496 `reel_price` bernilai 0 |
| Age (top audience) | 6 bucket umur | `l2_gold.audience_demographics_daily` | `audience_type='age'` | **0 baris** | **Tidak** | `audience_type` hanya `gender`. `age_gender_breakdown` juga 0/23 |
| Major Female / Male % | 0–100% | `l2_gold.audience_demographics_daily` | `dimension_key`, `audience_count` | 23 akun · female rata-rata 14,0% · male max 29% · **unknown rata-rata 71,3%** | **Tidak** | 0 akun punya female ≥50% atau male ≥50% |
| Min. audience authenticity | 0–100 | `feature.ig_audience_analysis` + `tt_` | `authenticity_score` | 23 akun · IG 29–77 · TT 56–92 | Sebagian | Skala & rentang cocok, cakupan 0,31% roster |
| Audience quality *(Insights)* | 0–100 | `feature.ig_audience_analysis` + `tt_` | `audience_quality_score` | 23 akun · IG 54–72 · TT 67–88 | Sebagian | Sama seperti di atas |
| Min. brand fit | 0–100 | `feature.brand_fit_analysis` | `partnership_score` | **0 baris** | **Tidak** | Tabel ada, tidak ada asset Dagster yang mengisinya |
| Max. paid content ratio | 0–100% | `l2_gold.post_metric` | `is_sponsored` | true 27 · false 440 · NULL 10 · 30 akun | Sebagian | Rasio bisa dihitung, cakupan 30 akun |
| Min. campaigns run | 0–15 | `public.campaigns`, `campaign_kols` | `id` / `kol_id` | **0 baris di kedua tabel** | **Tidak** | Seluruh subsistem campaign kosong (11 tabel, semua 0) |
| Creator domicile | list kota | `public.kol_directory` | `creator_city` | **0/7.720 terisi** | **Tidak** | Kolom ada, tidak pernah diisi. `influencer_address` hanya 137/7.718 |
| Audience domicile | list kota | `l2_gold.audience_geo_daily` | `geo_key` (`geo_level='city'`) | 68 baris · 33 key unik · 15 akun | Sebagian | Granularitas campur: "Bali", "Sulawesi", "Jawa", "Banten" bukan kota |
| Province *(Insights)* | 6 provinsi | `l2_gold.audience_geo_daily` | `geo_level` | Hanya `country` dan `city` | **Tidak** | Tidak ada level province di DB |
| Audience interest | list minat | `l2_gold.audience_interest_daily` | `interest_key` | 214 baris · 23 akun · 19 key | Sebagian | Taksonomi beda dari UI; `unknown` = 2.021 dari ±2.371 bobot |
| Category | 5 kategori hardcoded | `public.kol_categories` ← `kol_directory` | `name` ← `category_id` | 28 kategori · 4.174/7.720 baris punya kategori | Sebagian | Hanya Lifestyle, Beauty, Food, Fitness yang beririsan |
| Sort: Growth | angka pertumbuhan | `l2_gold.kol_profile_card` | `followers_growth` | 25/1.976 terisi · −0,051 – 0,917 | **Tidak** | 1,3% terisi |
| Sort: EMV | nilai uang | `feature.*_audience_analysis` | `emv`, `cpe` | **0/23 terisi** | **Tidak** | NULL 100% |
| Keyword search | nama / niche / kategori | `l2_gold.kol_profile_card` | `username`, `display_name`, `bio` | username 1.976 · display_name ±99% · bio ±94% | **Sesuai** | Tidak ada kolom "niche"; kategori harus diambil dari `kol_directory` |

---

## 3. Kelengkapan Data

NULL dihitung terhadap jumlah baris tabelnya sendiri. Kolom **Status** menilai
satu hal: apakah kolom ini bisa dipakai memfilter **7.496 akun** di roster.

| Filter | Table/Column | Total Data | NULL | Duplicate | Value/Range | Status |
|---|---|---:|---|---|---|---|
| Tier | `kol_profile_card.tier` | 1.976 | 4 (0,2%) | 0 | Nano, Micro, Mid-tier, Macro, Mega | Cukup |
| Platform | `kol_profile_card.platform` | 1.976 | 0 | 0 | instagram, tiktok | Cukup |
| Followers | `kol_profile_card.followers_count` | 1.976 | 4 (0,2%) | 0 | 0 – 685.896.635 · median IG 116.843 / TT 285.900 | Cukup |
| Verified | `kol_profile_card.is_verified` | 1.976 | 0 | 0 | hanya `false` — **1 nilai unik** | **Tidak cukup** |
| Growth | `kol_profile_card.followers_growth` | 1.976 | 1.951 (98,7%) | 0 | −0,051 – 0,917 | **Tidak cukup** |
| Rate card (L2) | `kol_profile_card.rate_card_min_fee` | 1.976 | 1.976 (100%) | — | tidak ditemukan | **Tidak cukup** |
| Engagement (L2) | `kol_metric_daily.er_followers_daily` | 280 | 207 (73,9%) | 0 | 0,0000164 – 0,1615 · median 0,00256 (**fraksi**) | **Tidak cukup** |
| Views (L2) | `kol_metric_daily.views_sum` | 280 | 79 (28,2%) | 0 | 0 – 12.663.900 | Terbatas |
| Reach | `kol_metric_daily.reach_sum` | 280 | 280 (100%) | — | tidak ditemukan | **Tidak cukup** |
| Format | `post_metric.media_type` | 477 | 8 (1,7%) | 0 per `content_id` | clips, carousel_container, feed, VIDEO, CAROUSEL | Terbatas |
| Paid ratio | `post_metric.is_sponsored` | 477 | 10 (2,1%) | 0 | true 27 · false 440 | Terbatas |
| ER per post | `post_metric.er_followers` | 477 | 337 (70,6%) | 0 | fraksi | Terbatas |
| Gender audiens | `audience_demographics_daily.dimension_key` | 69 | 0 | 0 | female, male, **unknown (71,3% bobot)** | **Tidak cukup** |
| Age audiens | `audience_demographics_daily` `audience_type='age'` | 0 | — | — | tidak ditemukan | **Tidak cukup** |
| Geo audiens (city) | `audience_geo_daily.geo_key` | 68 | 0 | 33 key unik dari 68 baris | Bandung 8, Bali 7, Jakarta 6, Lampung 6, Surabaya 5 … | Terbatas |
| Geo audiens (country) | `audience_geo_daily.geo_key` | 113 | 0 | 32 key unik dari 113 baris | 32 negara | Terbatas |
| Interest audiens | `audience_interest_daily.interest_key` | 214 | 0 | 19 key unik | unknown 2.021 · religion 65 · business 50 · parenting 45 · food 23 … | Terbatas |
| Authenticity | `feature.{ig,tt}_audience_analysis.authenticity_score` | 23 | 0 | 0 | 29 – 92 (integer) | Terbatas |
| Brand fit | `feature.brand_fit_analysis.partnership_score` | 0 | — | — | tidak ditemukan | **Tidak cukup** |
| Campaigns run | `public.campaign_kols` | 0 | — | — | tidak ditemukan | **Tidak cukup** |
| Category | `kol_directory.category_id` | 7.720 | 3.546 (45,9%) | 28 kategori | Lifestyle 1.915 · Beauty 1.018 · Entertainment 436 · Moms 378 … | Terbatas |
| Creator city | `kol_directory.creator_city` | 7.720 | 7.720 (100%) | — | tidak ditemukan | **Tidak cukup** |
| ER roster | `kol_directory.engagement_rate` | 7.720 | 5.964 (77,3%) | — | 0 – 223,41 · median 0,60 · 83 baris >10 · 6 baris = 0 | Terbatas |
| Identitas roster | `kol_directory.username_normalized` | 7.720 | 223 (2,9%) | **277 grup duplikat** (±277 baris ekstra) | — | Terbatas |
| Platform roster | `kol_directory.platform_id` | 7.720 | 224 (2,9%) | 2 platform | instagram 3.409 · tiktok 4.087 | Cukup |
| Rate card (L0) | `kol_roster_import.reel_price` dkk | 7.718 | 222 (2,9%) | — | 7.229 akun ≥1 harga >0 · reel_price 0 – 1e9 IDR · 4.598 bernilai 0 | Terbatas |
| Est. reach (L0) | `kol_roster_import.estimated_reach` | 7.718 | 224 (2,9%) | — | 0 – 277.851.253 · median 11.678 · 68 bernilai 0 | Terbatas |
| Est. ER (L0) | `kol_roster_import.estimated_engagement_rate` | 7.718 | 226 (2,9%) | — | 400 non-numerik (385 = `00:00:00`) · **6.099 dari 7.092 bernilai >100** | **Tidak cukup** |
| Size roster | `kol_roster_import.size_category` | 7.718 | 20 (0,3%) | — | micro 3.712 · nano 2.229 · macro 1.246 · mega 307 · unknown 202 · 2 baris rusak | Terbatas |

Duplicate untuk tabel L2 diukur sebagai `count(*) − count(distinct social_account_id)`
pada grain per-akun, dan per `content_id` untuk `post_metric`. Semuanya **0** —
tidak ada duplikasi di layer Gold.

### 3.1 Cakupan terhadap roster 7.496 akun

Ini angka yang paling menentukan. Sebagian besar filter bukan gagal karena
kolomnya kosong, tapi karena kolomnya hanya terisi untuk 30 akun.

| Kelompok filter | Sumber | Akun | % roster |
|---|---|---:|---:|
| Est. reach / est. views | `l0_raw.kol_roster_import` | 7.494 | 99,9% |
| Rate card (≥1 harga >0) | `l0_raw.kol_roster_import` | 7.229 | 96,4% |
| Category | `public.kol_directory.category_id` | 4.174 | 54,1% |
| Followers · tier · platform | `l2_gold.kol_profile_card` | 1.976 | 26,4% |
| ER roster | `public.kol_directory.engagement_rate` | 1.756 | 22,7% |
| Format · views · paid ratio · posting freq | `l2_gold.post_metric` / `kol_metric_daily` / `content_format_daily` | **30** | **0,40%** |
| Gender · geo · interest · authenticity | `l2_gold.audience_*` / `feature.*_audience_analysis` | **23** | **0,31%** |
| Brand fit · campaigns run · age · creator city | `feature.brand_fit_analysis` / `public.campaign_*` / `audience_type='age'` | **0** | **0%** |

5.520 dari 7.496 akun roster tidak punya `kol_profile_card` sama sekali.

---

## 4. Mapping Filter → Data

Source layer yang *seharusnya* dipakai UI, bukan sekadar layer tempat datanya
kebetulan ada. Semuanya di database `kol` — tidak ada TSDB atau warehouse yang dipakai.

| Filter | Source Layer | Table | Column | Kondisi Data | Perlu gabungan/transformasi? |
|---|---|---|---|---|---|
| Tier | L2 | `l2_gold.kol_profile_card` | `tier` | 1.972/1.976 | Ya — remap label `Mid-tier` → `Mid`, atau ubah value chip UI |
| Platform | L2 | `l2_gold.kol_profile_card` | `platform` | 1.976/1.976 | Tidak |
| Min. followers | L2 | `l2_gold.kol_profile_card` | `followers_count` | 1.972/1.976 | Tidak — tapi plafon slider perlu dinaikkan di atas 3M |
| Category | public | `kol_directory` ⋈ `kol_categories` | `category_id` → `name` | 4.174/7.720 | Ya — join, lalu join ke `kol_social_account` untuk sampai ke L2 |
| Keyword search | L2 | `l2_gold.kol_profile_card` | `username`, `display_name` | ≥99% | Ya — index trigram kalau mau ILIKE cepat |
| Verified | L0 → L1 | `l0_raw.ig_profile_apify.raw_payload`, `l0_harmonization.tiktok_profile` | `verified` / `is_verified` | IG 470/953 true · TT 124/1.051 true | Ya — **perbaikan pipeline**: tambah kolom di harmonization IG, teruskan di `sp_build_unified_profile` |
| Min. engagement | L2 | `l2_gold.kol_metric_daily` | `er_followers_daily` | 73/280 · 30 akun | Ya — agregasi ke per-akun + konversi fraksi→persen (×100) |
| Min. avg. views | L2 | `l2_gold.post_metric` | `views` | 393/477 · 30 akun | Ya — `avg(views)` per `social_account_id` |
| Format | L2 | `l2_gold.content_format_daily` | `media_type`, `post_count` | 300 baris · 30 akun | Ya — mapping ke label UI + pilih format dominan per akun |
| Max. paid content ratio | L2 | `l2_gold.post_metric` | `is_sponsored` | 467/477 · 30 akun | Ya — count sponsored / count total per akun |
| Min. posting freq. | L2 | `l2_gold.kol_metric_daily` | `metric_date`, `post_count` | 280 baris · 30 akun | Ya — dan **tetapkan jendela tetap** (mis. 90 hari) supaya tidak bias rentang pendek |
| Min. audience authenticity | Feature | `feature.{ig,tt}_audience_analysis` | `authenticity_score` | 23/23 | Ya — UNION dua tabel platform; belum ada padanan di L2 |
| Audience quality | Feature | `feature.{ig,tt}_audience_analysis` | `audience_quality_score` | 23/23 | Ya — sama seperti di atas |
| Major Female / Male % | L2 | `l2_gold.audience_demographics_daily` | `dimension_key`, `audience_count` | 23 akun · unknown 71,3% | Ya — pivot ke share, dan **renormalisasi tanpa `unknown`** |
| Audience domicile | L2 | `l2_gold.audience_geo_daily` | `geo_key` where `geo_level='city'` | 15 akun | Ya — top-1 per akun + normalisasi nama kota |
| Audience interest | L2 | `l2_gold.audience_interest_daily` | `interest_key` | 23 akun | Ya — buang/tandai `unknown`, selaraskan taksonomi dengan `kol_categories` |
| Max. rate card | L0 → L1 | `l0_raw.kol_roster_import` → `l1_silver.unified_rate_card` | `reel_price`, `feed_photo_price`, `story_price`, `feed_video_price`, `live_price`, … | 7.229 akun di L0 · 0 di L1 | Ya — **pipeline belum ada**: cast text→numeric, unpivot ke `post_type`+`fee`, set `currency='IDR'` |
| Min. est. reach | L0 → L1 | `l0_raw.kol_roster_import` | `estimated_reach`, `est_views` | 7.494 di L0 · 0 di L2 | Ya — cast + validasi; `kol_metric_daily.reach_sum` NULL 100% |
| Age (top audience) | — | tidak ditemukan | — | 0 baris | Perlu sumber data baru — inferensi umur belum diimplementasi |
| Min. brand fit | — | `feature.brand_fit_analysis` (kosong) | `partnership_score` | 0 baris | Perlu asset Dagster baru + konteks brand |
| Min. campaigns run | — | `public.campaign_kols` (kosong) | `kol_id` | 0 baris | Perlu modul campaign dipakai lebih dulu |
| Creator domicile | — | `kol_directory.creator_city` (kosong) | `creator_city` | 0/7.720 | Perlu jalur pengisian; `influencer_address` hanya 137 baris |
| Province | — | tidak ditemukan | — | `geo_level` hanya country/city | Perlu tabel referensi kota → provinsi |

---

## 5. Struktur Data Filter

UI filter butuh **dua** bentuk data yang berbeda, dan keduanya belum ada.
Menyajikan L2 apa adanya memaksa frontend melakukan agregasi lintas tabel setiap request.

### 5.1 Facet catalog — mengisi pilihan kontrol

```
GET /discover/kol-directory/facets
{
  "tier":      [{ "value": "Nano", "label": "Nano", "count": 63 }, ...],
  "platform":  [{ "value": "instagram", "label": "Instagram", "count": 935 }, ...],
  "category":  [{ "id": "<uuid>", "label": "Lifestyle", "count": 1915 }, ...],
  "format":    [{ "value": "reels", "label": "Reels", "count": 18,
                  "source_types": ["clips","VIDEO"] }, ...],
  "interest":  [{ "value": "beauty", "label": "Beauty", "count": 11 }, ...],
  "geo_city":  [{ "value": "bandung", "label": "Bandung", "count": 5 }, ...],
  "ranges": {
    "followers":  { "min": 0, "max": 685896635, "unit": "count" },
    "engagement": { "min": 0.0016, "max": 16.15, "unit": "percent" },
    "rate_card":  { "min": 0, "max": 1000000000, "currency": "IDR" }
  }
}
```

**Kenapa perlu.** Prototype menghardcode setiap pilihan — 5 kategori, 5 label
tier, 6 bucket umur. DB punya 28 kategori, label tier yang berbeda (`Mid-tier`),
dan nol bucket umur. Facet catalog membuat kontrol UI mengikuti data, dan `count`
mencegah pengguna memilih filter yang pasti menghasilkan nol baris. Blok `ranges`
menjawab tiga mismatch satuan sekaligus: slider follower 3M vs data 686M, ER
fraksi vs persen, dan rate card USD vs IDR.

### 5.2 Filterable projection — satu baris per akun, siap di-`WHERE`

```
l2_gold.kol_filter_profile   grain: social_account_id

social_account_id     uuid      PK        1.976 tersedia
platform              text      not null  100%
username              text      not null  100%
display_name          text                99%
category_id           uuid                54% (via kol_directory)
tier                  text                99,8%
followers_count       bigint              99,8%
is_verified           boolean             0% — menunggu perbaikan pipeline

er_percent            numeric(6,3)        30 akun — sudah ×100
avg_views             bigint              30 akun
post_freq_weekly      numeric(5,2)        30 akun — jendela 90 hari
paid_ratio_pct        numeric(5,2)        30 akun
dominant_format       text                30 akun — label UI

audience_female_pct   numeric(5,2)        23 akun — exclude unknown
audience_male_pct     numeric(5,2)        23 akun — exclude unknown
audience_unknown_pct  numeric(5,2)        23 akun — untuk badge confidence
authenticity_score    smallint            23 akun
audience_quality      smallint            23 akun
top_city              text                15 akun
top_country           text                23 akun
interest_keys         text[]              23 akun — unknown dibuang

rate_card_min_idr     numeric             0 — menunggu jalur L0→L1
est_reach             bigint              0 — menunggu jalur L0→L1
metrics_confidence    text                'measured' | 'partial' | 'none'
metrics_updated_at    timestamptz
```

**Kenapa perlu.** Memfilter satu kreator sekarang menyentuh **tujuh tabel di tiga
schema dengan tiga grain berbeda** (per-akun, per-hari, per-post). Tanpa proyeksi
ini setiap request harus mengagregasi `post_metric` dan mem-pivot
`audience_demographics_daily` secara live.

Kolom `*_pct` memakai persen supaya cocok dengan slider UI, bukan fraksi seperti
`er_followers_daily`. Kolom `metrics_confidence` penting karena 98% akun tidak
punya metrik apa pun — UI perlu membedakan "ER rendah" dari "ER tidak diketahui",
dan setiap filter numerik harus punya kebijakan eksplisit apakah akun tanpa data
disembunyikan atau ditampilkan.

### 5.3 Apakah struktur sekarang sudah cukup?

- **Belum.** Tidak ada satu pun tabel yang bisa langsung di-`WHERE` untuk daftar
  filter di prototype. `kol_profile_card` yang terdekat, tapi hanya mencakup
  4 dari 20 filter.
- **Perlu data preparation, bukan sekadar query baru.** Tiga hal harus
  diselesaikan di pipeline lebih dulu: kolom `is_verified` yang hilang di
  harmonization Instagram, jalur rate card L0→L1 yang belum ada, dan asset
  `audience_feature` yang belum masuk `transform_chain_job`.
- **Normalisasi satuan harus terjadi di layer data, bukan di frontend.** Sekarang
  ER hidup sebagai fraksi di `kol_metric_daily` dan sebagai persen di
  `kol_directory` — dua satuan berbeda untuk metrik yang sama di satu database.
- **Cakupan adalah keputusan produk, bukan bug yang bisa di-query.** Dengan 30
  dari 7.496 akun punya data performa, filter ER/views/format akan menyembunyikan
  99,6% roster kecuali kebijakan "akun tanpa data" ditetapkan lebih dulu.

---

## 6. Gap UI vs Database

### 6.1 Filter UI yang datanya sudah tersedia

- **Platform** — `kol_profile_card.platform`, 1.976/1.976, dua nilai bersih.
- **Min. followers** — `followers_count`, 1.972/1.976. Hanya perlu plafon slider dinaikkan.
- **Tier** — `tier`, 1.972/1.976. Perlu satu remap label.
- **Keyword search** — `username` / `display_name`, ≥99%.

### 6.2 Filter UI yang datanya belum tersedia

- **Age (top audience group)** — `audience_type` hanya berisi `gender`; 0 baris `age`.
  `age_gender_breakdown` di feature juga NULL 100%.
- **Min. brand fit score** — `feature.brand_fit_analysis` 0 baris, tidak ada asset yang mengisinya.
- **Min. campaigns run** — 11 tabel `campaign_*` semuanya 0 baris.
- **Creator domicile** — `creator_city` 0/7.720.
- **Format "Story"** — `l0_raw.ig_stories_apify` dan `l1_silver.unified_story`: 0 baris.
  Tiga format lainnya ada.

### 6.3 Filter yang datanya ada tapi belum lengkap

Yang pertama bukan soal cakupan, tapi **bug transformasi** — sumbernya ada,
hasilnya hilang di tengah jalan:

```
Instagram
  l0_raw.ig_profile_apify.raw_payload->'verified'     953 baris, 470 true   ✅
    └─ sp_sync_instagram_profile
       l0_harmonization.instagram_profile             kolom is_verified TIDAK ADA   ❌
         └─ sp_build_unified_profile
            l1_silver.unified_profile.is_verified     2.001 baris, 0 true   ❌
              └─ asset kol_profile_card
                 l2_gold.kol_profile_card.is_verified 1.976 baris, 0 true   ❌

TikTok
  l0_harmonization.tiktok_profile.is_verified         1.051 baris, 124 true ✅
    └─ sp_build_unified_profile
       l1_silver.unified_profile.is_verified          nilai true hilang     ❌

Alternatif yang belum dipakai
  public.kol_directory.verified_status                454 verified / 477 unverified / 6.789 NULL
```

- **Major Female / Male %** — 23 akun, dan `unknown` rata-rata **71,3%** dari
  bobot audiens. Share female tertinggi di seluruh database adalah **28%**, male
  **29%**. Artinya slider "Major Female ≥ 50%" mengembalikan **nol** kreator, dan
  bahkan ≥30% pun nol. Filter ini tidak bisa dipakai tanpa renormalisasi yang
  mengeluarkan `unknown`.
- **Min. engagement** — dua sumber, dua masalah. `kol_metric_daily.er_followers_daily`
  hanya 30 akun dan bersatuan fraksi. `kol_directory.engagement_rate` mencakup
  1.756 akun dan sudah persen, tapi 83 baris >10% dengan maksimum 223,41% —
  di luar batas fisik.
- **Format, avg views, paid ratio, posting freq** — semuanya bergantung pada
  30 akun yang sama (0,40% roster).
- **Audience interest** — 23 akun, dan `unknown` menyumbang 2.021 dari ±2.371
  bobot. Taksonomi DB (religion, parenting, business) juga tidak sejajar dengan
  kategori UI (Fitness, Wellness, Running).
- **Audience domicile** — 15 akun untuk level city, dan key-nya campur: "Bali",
  "Sulawesi", "Jawa", "Banten", "Lampung" bukan kota.
- **Category** — 4.174/7.720 punya kategori, tapi hanya 4 dari 5 chip UI punya
  padanan. "Tech" di UI vs "Technology and gadgets" (2 baris) di DB.
- **Roster identity** — 277 grup `username_normalized` duplikat dan 224 baris
  tanpa `platform_id`. Perlu dedup sebelum roster dipakai sebagai basis hitung filter.

### 6.4 Data yang tersedia di DB tapi belum dimanfaatkan prototype

**Rate card lengkap ada di L0 dan tidak pernah naik.**
`l0_raw.kol_roster_import` berisi 7.718 baris dengan **14 kolom harga**:
`story_price`, `story_session_price`, `feed_photo_price`, `feed_video_price`,
`reel_price`, `live_price`, `owning_asset_price`, `tap_link_price`,
`link_in_bio_price`, `live_attendance_price`, `host_price`, `comment_price`,
`photoshoot_price`, `other_price`. **7.229 akun (96,4%) punya setidaknya satu
harga > 0.** Sementara itu `l1_silver.unified_rate_card` dan kedua tabel
`l0_harmonization.*_rate_card` berisi 0 baris. Ini sumber data terbesar yang
tersedia dan belum tersentuh pipeline. Harganya **IDR** (maksimum `reel_price`
= 1.000.000.000), sedangkan slider UI berlabel USD dengan plafon $5.000.

- **`est_views`, `estimated_reach`, `est_erb`, `size`, `size_category`** — semua
  ada di roster import dengan cakupan ±99,9%, tidak ada yang naik ke L1.
  `estimated_reach` nilainya wajar (median 11.678); `estimated_engagement_rate`
  **tidak** (6.099 dari 7.092 bernilai >100, dan 385 baris berisi `00:00:00` —
  artefak format waktu Excel).
- **`kol_directory.verified_status`** — 454 verified, tidak dipakai di mana pun
  sepanjang rantai L1/L2.
- **`feature.{ig,tt}_engagement_analysis`** — 30 baris berisi
  `best_posting_time_heatmap` dan `format_performance` (jsonb, ±89–100% terisi).
  Prototype tidak punya filter apa pun untuk waktu posting terbaik.
- **`post_metric.top_hashtags`** — 307/477 terisi. Bisa jadi filter hashtag;
  tidak ada padanannya di prototype.
- **`kol_profile_card.is_private`, `media_count`, `following_count`, `website`** —
  terisi 58–100%, tidak dipakai sebagai filter. `is_private` khususnya relevan:
  akun private tidak bisa dijadikan target campaign.
- **`audience_*.confidence`** — 100% terisi (`inferred_low` 44, `inferred_high` 23,
  `inferred_medium` 2). Prototype punya konsep badge `conf` tapi tidak
  menjadikannya filter, padahal semua data audiens adalah hasil inferensi.

---

## 7. Rekomendasi Subtask

Lima subtask yang ada sudah menutup alurnya dan urutannya benar. Dua masalah:
subtask 2 dan 3 tumpang tindih di praktiknya, dan tidak ada satu pun subtask yang
menampung temuan terbesar audit ini — bahwa sebagian filter terblokir oleh
*pipeline*, bukan oleh keputusan desain filter.

| Subtask sekarang | Penilaian | Alasan |
|---|---|---|
| 1 · List kebutuhan filter | Tepat | Perlu diperluas: prototype punya **dua** permukaan filter (modal Directory + Audience Insights) dan 3 filter dead-state yang mudah terlewat |
| 2 · Cek prototype dan data di database | Tumpang tindih | Tidak bisa dipisah dari subtask 3 — menentukan "kolom mana" dan "datanya cukup atau tidak" adalah query yang sama |
| 3 · Cek kelengkapan data filter | Tumpang tindih | Sama seperti di atas. Digabung lebih efisien, dan mencegah kesimpulan yang cuma berdasarkan nama kolom |
| 4 · Tentukan data untuk setiap filter | Tepat | Tapi harus menghasilkan **keputusan**, termasuk "filter ini tidak dikerjakan dulu", bukan cuma tabel mapping |
| 5 · Buat struktur data filter | Tepat | Perlu dipisah dua: facet catalog (mengisi kontrol) dan filterable projection (mengeksekusi filter) |
| *tidak ada* | **Kurang** | Tidak ada subtask untuk **perbaikan pipeline** (verified, rate card, cakupan audience) — padahal ini yang memblokir mayoritas filter |
| *tidak ada* | **Kurang** | Tidak ada subtask untuk **kebijakan cakupan dan satuan** — keputusan produk yang harus diambil sebelum struktur data dikunci |

### Versi subtask yang disarankan

1. **Inventarisasi kebutuhan filter dari seluruh permukaan UI.**
   Bukan hanya modal Advanced Filters. Sertakan chip kategori, sort options,
   filter Audience Insights, dan tiga state tanpa kontrol (`domicile`,
   `audDomicile`, `interest`). Catat bentuk kontrol, range, satuan, dan label
   value persis seperti yang akan dikirim ke backend.

2. **Telusuri setiap filter sampai kolom sumber, sekaligus ukur kelengkapannya.**
   Gabungan subtask 2 dan 3. Untuk tiap filter, dalam satu langkah: temukan
   tabel/kolom, hitung total, NULL, duplicate, distinct value, dan range — lalu
   ukur cakupannya terhadap roster 7.496 akun. Cakupan adalah angka yang
   menentukan, bukan persentase NULL per tabel.

3. **Pisahkan blocker pipeline dari blocker desain filter.** *(subtask baru)*
   Tiga temuan audit ini tidak bisa diselesaikan di layer filter: `is_verified`
   hilang di `sp_sync_instagram_profile`, rate card 7.229 akun berhenti di L0,
   dan asset `audience_feature` berada di luar `transform_chain_job`. Estimasi
   dan jadwalkan terpisah dari pekerjaan filter.

4. **Tetapkan kebijakan cakupan dan satuan.** *(subtask baru, keputusan produk)*
   Apakah akun tanpa metrik disembunyikan atau ditampilkan saat filter numerik
   aktif? ER disajikan dalam fraksi atau persen? Rate card dalam IDR atau USD,
   dan kalau USD siapa yang menyimpan kursnya? Apakah `unknown` dikeluarkan dari
   share gender? Kunci ini dulu — semuanya mengubah bentuk struktur data.

5. **Tentukan filter yang masuk rilis pertama.**
   Berdasarkan hasil 2–4. Rekomendasi audit:
   - **Rilis:** platform, followers, tier, category, keyword (cakupan 26–54%)
   - **Tahan:** ER, views, format, paid ratio, posting freq, gender, geo,
     interest, authenticity — sampai cakupan naik dari 30 akun
   - **Tunda:** age, brand fit, campaigns run, creator domicile, Story — sampai
     sumber datanya ada

6. **Rancang facet catalog.**
   Endpoint yang mengisi pilihan kontrol dari data — value, label, count, dan
   range aktual per field. Menghapus semua nilai hardcoded di prototype dan
   mencegah pengguna memilih kombinasi yang pasti nol hasil.

7. **Rancang filterable projection dan validasi ulang.**
   Satu baris per `social_account_id` dengan seluruh field filter sudah
   dinormalisasi satuannya, plus penanda `metrics_confidence`. Setelah jadi,
   jalankan ulang kombinasi filter dari subtask 1 terhadap tabel ini dan pastikan
   jumlah hasilnya cocok dengan query manual ke tabel sumber.

### Perubahan intinya

Lima subtask menjadi tujuh: dua digabung (2+3), tiga ditambahkan (blocker
pipeline, kebijakan cakupan dan satuan, penentuan scope rilis), dan subtask
struktur data dipecah menjadi facet catalog dan filterable projection. Yang
paling menentukan adalah subtask 4 — tanpa kebijakan cakupan dan satuan, struktur
data apa pun yang dibuat akan salah bentuk begitu keputusannya diambil.

---

## Catatan metode

Audit ini **read-only**. Tidak ada file kode, migration, atau baris database yang
diubah; sesi Postgres dibuka dengan `set_session(readonly=True, autocommit=True)`.

Yang **tidak** dipakai sebagai sumber: angka di `docs/L0_L1_L2_FLOW.md` dan
`docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md`. Keduanya dibaca untuk memahami
rantai transformasi, tapi setiap angka volume, persentase NULL, dan daftar
distinct value diverifikasi ulang lewat query pada 2026-09-02.
