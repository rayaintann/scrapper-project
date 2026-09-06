# KOL Discovery — Filter to Database Mapping

**Task 2** · Prototype `app/AUTOME_2.html` · Database `kol` (read-only) · 2026-09-02
**Population / denominator:** `public.kol_directory` = **7.720**
**Input:** 32 kebutuhan filter dari `docs/KOL_DISCOVERY_FILTER_REQUIREMENTS.md`

> ### Status dokumen — direvisi 2026-09-06
>
> Dokumen ini memuat **dua koreksi yang berlaku surut**. Jangan berhenti di tabel §2:
>
> 1. **§3.1 "Verified only — bug transform" DICABUT SELURUHNYA.** `is_verified` = status
>    OAuth, bukan centang biru; tidak ada bug. Rekomendasi "perbaikan transform" di §7 no. 4
>    **akan merusak business rule migration 006** kalau dikerjakan. Koreksinya di §4.1.
> 2. **Mapping Kategori (§2 No. 2) sudah usang.** Kolom join yang benar `category_ids`
>    (array), bukan `category_id`, dan taxonomy-nya `kol_categories.taxonomy_key`
>    (9 Discovery Category, migration `029`). Lihat §Revisi 2026-09-06 di akhir dokumen.
>
> Mapping final: `docs/KOL_DISCOVERY_TASK5_DESIGN.md` §2–§3.

---

## 1. Scope & Source of Truth

| Pertanyaan | Sumber |
|---|---|
| Filter apa yang dibutuhkan UI? | `app/AUTOME_2.html` → `V.list` (KOL Directory) |
| Siapa populasinya? | `public.kol_directory` (7.720 baris) |
| Datanya ada nggak? | Query langsung ke DB `kol`, 2026-09-02 |

**Batasan yang dipatuhi:** `l0_raw.kol_roster_import` tidak dipakai sebagai source
maupun denominator, dan tidak dipakai sebagai fallback Rate Card. `l0_raw.*` hanya
ditelusuri untuk melacak asal `is_verified` (§3.1). Tidak ada perubahan apa pun
pada DB, kode, schema, atau config.

**Status:**

| Status | Artinya |
|---|---|
| **AVAILABLE** | Terisi memadai, bisa langsung dipakai |
| **PARTIAL** | Ada datanya, tapi coverage atau kualitas nilainya kurang |
| **MISSING** | Tidak ada sumber yang bisa dipakai (0 baris / 0 nilai berguna) |
| **DERIVED** | Perlu dihitung, **dan field dasarnya sudah memadai** |
| **SYNTHETIC** | Nilainya diciptakan prototype (hash ID / hardcoded), bukan data DB |

Kalau satu filter kena beberapa kondisi, yang dipakai adalah **kondisi yang memblokir**.

**Source Type:** `Direct` = kolom di `kol_directory` · `JOIN` = perlu join ·
`Calc` = perlu dihitung · `Synthetic` = tidak ada padanan DB.

---

## 2. Mapping Filter → Database

Coverage = jumlah KOL dari **7.720**.

| No | UI Filter | Group | DB Table → Field | Type | Coverage | Status |
|---:|---|---|---|---|---:|---|
| 1 | Platform | Creator Profile | `kol_directory.platform_id` → `platforms.key` | JOIN | 7.496 · 97,1% | **AVAILABLE** |
| 2 | Kategori KOL | Creator Profile | `kol_directory.category_id` → `kol_categories.name` | JOIN | 4.174 · 54,1% | **PARTIAL** |
| 3 | KOL Tier | Creator Profile | `l2_gold.kol_profile_card.tier` | JOIN | 1.972 · 25,5% | **PARTIAL** |
| 4 | Gender skew | Creator Profile | `l2_gold.audience_demographics_daily` | JOIN+Calc | 23 · 0,30% | **PARTIAL** |
| 5 | Verified only | Creator Profile | `l2_gold.kol_profile_card.is_verified` | JOIN | **0 · 0%** | **MISSING** |
| 5b | ↳ alternatif | Creator Profile | `kol_directory.verified_status` | Direct | 931 · 12,1% | **PARTIAL** |
| 6 | Age | Creator Profile | `audience_demographics_daily` `type='age'` | JOIN | **0 baris** | **MISSING** |
| 7 | Location (kreator) | Creator Profile | `kol_directory.creator_city` | Direct | **0 · 0%** | **MISSING** |
| 8 | Audience location | Audience | `audience_geo_daily.geo_key` (`level='city'`) | JOIN | 15 · 0,19% | **PARTIAL** |
| 9 | Audience interest | Audience | `audience_interest_daily.interest_key` | JOIN | 23 · 0,30% | **PARTIAL** |
| 10 | Audience Quality | Audience | `feature.{ig,tt}_audience_analysis` | JOIN+Calc | 23 · 0,30% | **PARTIAL** |
| 11 | Content Category/Topic | Content | — | Synthetic | — | **SYNTHETIC** |
| 12 | Content Format | Content | `content_format_daily.media_type` | JOIN | 30 · 0,39% | **PARTIAL** |
| 13 | Content Style & Personality | Content | — | Synthetic | — | **SYNTHETIC** |
| 14 | Engagement Rate | Performance | `kol_metric_daily.er_followers_daily` | JOIN+Calc | 22 · 0,28% | **PARTIAL** |
| 14b | ↳ alternatif | Performance | `kol_directory.engagement_rate` | Direct | 1.756 · 22,7% | **PARTIAL** |
| 15 | Save Rate | Performance | `post_metric.saves` | JOIN+Calc | **11 · 0,14%** | **PARTIAL** |
| 16 | Share Rate | Performance | `post_metric.shares` | JOIN+Calc | **11 · 0,14%** | **PARTIAL** |
| 17 | Views | Performance | `post_metric.views` | JOIN+Calc | 29 · 0,38% | **PARTIAL** |
| 18 | Reliability | Performance | — | Synthetic | — | **MISSING** |
| 19 | Performance Stability | Performance | `kol_metric_monthly` (deret) | JOIN+Calc | **5 · 0,06%** | **PARTIAL** |
| 20 | Viral Frequency | Performance | `kol_metric_monthly` (deret) | JOIN+Calc | **5 · 0,06%** | **PARTIAL** |
| 21 | Growth Classification | Growth | `kol_profile_card.followers_growth` | JOIN+Calc | 25 · 0,32% | **PARTIAL** |
| 22 | Rising Creator | Growth | `followers_growth` + ER + followers | JOIN+Calc | ≤25 · 0,32% | **PARTIAL** |
| 23 | Data Status | Data Freshness | `last_refreshed_at` ÷ interval | Direct+Calc | interval **tidak ada** | **MISSING** |
| 24 | Last Updated | Data Freshness | `kol_directory.last_refreshed_at` | Direct | 7.496 · 97,1% | **AVAILABLE** |
| 25 | Update Frequency | Data Freshness | `kol_directory.refresh_tier` | Direct | **0 · 0%** | **MISSING** |
| 26 | Next Update | Data Freshness | `last_refreshed_at` + interval | Calc | interval **tidak ada** | **MISSING** |
| 27 | Monitoring Priority | Data Freshness | campaign + growth + virality | Calc | input kosong | **MISSING** |
| 28 | Keyword search | Header | `kol_directory.username`, `bio` | Direct+JOIN | 7.497 · 97,1% | **PARTIAL** |
| 29 | Smart Criteria (NL) | Header | 29 aturan, beragam sumber | Calc+Synth | — | **PARTIAL** |
| 30 | Section tabs | Header | `created_at`, `last_refreshed_at`, dll | Direct+Calc | 2 dari 7 tab | **PARTIAL** |
| 31 | Exclude | Header | `campaigns`, `campaign_kols` | JOIN+Calc | **0 baris** | **MISSING** |
| 32 | Collections | Header | — (state browser) | Synthetic | — | **SYNTHETIC** |

> **5b** dan **14b** adalah sumber alternatif untuk filter yang sama, bukan filter
> tambahan — total tetap **32**.
>
> **Penomoran beda dari Task 1.** Di sana ada 33 kontrol (No. 28 = chip Kategori di
> header). Di sini chip itu digabung ke No. 2 karena menulis state yang sama, jadi
> No. 28–32 bergeser satu.

> **⚠️ Empat baris di tabel ini sudah tidak berlaku (2026-09-06):**
>
> | No | Isi lama | Yang berlaku |
> |---|---|---|
> | **2** Kategori | `category_id → kol_categories.name` · 54,1% | `category_ids` (array) → `taxonomy_key` · ±53,8% *(R1)* |
> | **3** KOL Tier | `kol_profile_card.tier` · 25,5% | `kol_directory.followers_count` · 93,2% *(Task 4 No. 3)* |
> | **5** Verified only | `kol_profile_card.is_verified` | `social_account.oauth_token` *(§4.1)* |
> | **24** Last Updated | AVAILABLE | **PARTIAL** — 73,6% nilainya bukan jejak scrape *(R2)* |
>
> Selain itu, **32 bukan lagi jumlah filternya.** Baseline berpindah ke app produksi:
> **40 filter** — lihat `FILTER_REQUIREMENTS 1.md` §Revisi.

---

## 3. Detail — hanya yang perlu penjelasan

### 3.1 Verified only — bug transform, bukan data hilang

> ### ❌ SECTION INI DICABUT — jangan dikerjakan
>
> **Tidak ada bug.** `is_verified` tidak pernah dimaksudkan menyimpan centang biru; ia
> **status OAuth** (`social_account.oauth_token IS NOT NULL`), dan badge platform dibuang
> **dengan sengaja** sesuai business rule di `migrations/006_fix_sp_build_unified_profile.sql:17–23`.
> Mengerjakan "perbaikan" di bawah justru **melanggar keputusan mentor**.
> Koreksi lengkap + bukti di **§4.1**. Isi di bawah dipertahankan hanya sebagai audit trail.

Sumbernya **ada**, tapi hilang di tengah jalan:

```
IG   l0_raw.ig_profile_apify.raw_payload->'verified'  →  470 dari 953 true   ✅
       └─ l0_harmonization.instagram_profile             KOLOM TIDAK ADA     ❌
TT   l0_harmonization.tiktok_profile.is_verified      →  124 dari 1.051 true ✅
       └─ l1_silver.unified_profile.is_verified          0 true              ❌
             └─ l2_gold.kol_profile_card.is_verified      0 true             ❌
```

Penyebab IG: `l0_harmonization.instagram_profile` tidak punya kolom `is_verified`,
jadi nilainya dibuang di `sp_sync_instagram_profile`. Untuk TikTok kolomnya ada dan
terisi, tapi nilainya hilang di `sp_build_unified_profile`.

Alternatif yang belum dipakai pipeline: `kol_directory.verified_status`
(454 `verified`, 477 `unverified`, 6.789 NULL).

### 3.2 Data Freshness — penyebut rumusnya tidak ada

Prototype menghitung `status = umur data ÷ interval update`.

| Komponen | Sumber | Kondisi |
|---|---|---|
| Umur data | `kol_directory.last_refreshed_at` | 7.496 · 97,1% ✅ |
| Interval update | `kol_directory.refresh_tier` | **0 · 0%** ❌ |
| Interval update *(alt)* | `public.scheduler_config` | **0 baris** ❌ |
| Penanda proses | `kol_directory.scrape_status` | 99 · 1,28% (72 `failed`, 27 `success`) |

Tanpa penyebut, **Data Status, Update Frequency, dan Next Update tidak bisa dihitung**.

`Update Frequency` **bukan kolom DB** — di prototype ia turunan Monitoring Priority
(High → 6 jam, Active → harian, Standard → mingguan, Low → bulanan). Kolom yang
namanya paling mendekati (`refresh_tier`) justru 0% terisi.

**Monitoring Priority** juga mati: keempat inputnya kosong — `campaign_kols` 0 baris,
`campaigns` 0 baris, growth 25 akun, virality 5 akun.

### 3.3 Last Updated — field bagus, sebaran ekstrem

Satu-satunya filter Data Freshness yang jalan, tapi 3 dari 5 bucket praktis kosong:

| Bucket UI | KOL |
|---|---:|
| Last 24 Hours | **0** |
| Last 3 Days | **0** |
| Last 7 Days | **4** |
| Last 30 Days | 1.003 |
| Older than 30 Days | **6.493** |

Per tahun: 2023 → 1.778 · 2024 → 4.543 · 2025 → 172 · 2026 → 1.003.
**86,6% roster belum di-refresh lebih dari 30 hari.**

### 3.4 Gender skew — datanya ada, tapi tidak ada yang lolos

| Ukuran | Nilai |
|---|---:|
| Rata-rata porsi `unknown` | **71,3%** |
| Porsi female tertinggi di seluruh DB | 28,0% |
| Porsi male tertinggi di seluruh DB | 29,0% |
| Lolos "Female-skewed" (≥60%) | **0** |
| Lolos "Male-skewed" (≥55%) | **0** |

Kedua chip mengembalikan nol hasil, bahkan seandainya coverage penuh — karena
`unknown` ikut masuk penyebut.

### 3.5 Save Rate & Share Rate — rumus prototype ≠ kolom DB

Prototype tidak memakai kolom `saves`/`shares` sama sekali:

```
saveRate  = (audience affinity × 0,5) + (engagement rate × 0,3)
shareRate = engagement rate × 0,35
```

`audience affinity` **tidak punya kolom padanan di DB**. Kolom terdekat
(`post_metric.saves`/`.shares`) hanya terisi untuk **11 KOL, TikTok saja** —
Instagram tidak menyediakannya lewat scraping publik.

### 3.6 Catatan singkat lainnya

| Filter | Masalah |
|---|---|
| **Platform** | `platforms` cuma punya `instagram` (3.409) + `tiktok` (4.087). Chip **YouTube** di UI tidak punya baris |
| **Kategori KOL** | DB punya 28 kategori, UI hardcode 5. Hanya Lifestyle, Beauty, Food, Fitness yang beririsan. Chip **Tech** tidak punya padanan (kategori terdekat 2 baris). Kategori terbesar ke-3 & ke-4 di DB (Entertainment 436, Moms 378) justru tidak punya chip |
| **KOL Tier** | Label cocok, **batasnya beda**: UI bilang Mid-tier 50K–500K & Macro 500K–1M; `kol_tiers` memakai 50K–100K & 100K–1M |
| **Audience location** | 33 `geo_key` campur kota & provinsi ("Bali", "Sulawesi", "Jawa", "Banten"). Tidak ada level `province`, padahal Audience Insights memerlukannya |
| **Audience interest** | `unknown` = 2.021 dari 2.371 bobot (**85,2%**) |
| **Audience Quality** | Rumus `(authenticity + quality)/2`. Nilai maks 88 (TT) dan 72 (IG) → bucket **"High (85+)" hampir tidak terisi**. Perlu UNION dua tabel platform |
| **Content Format** | Perlu mapping: `clips`→Reels, `carousel_container`/`CAROUSEL`→Carousel, `feed`→Feed, `VIDEO`→Video, Photo = grup. Opsi **Story tidak ada datanya** (`unified_story` 0 baris) |
| **Engagement Rate** | L2 bersatuan **fraksi**, UI **persen** → perlu ×100. Alternatif `kol_directory.engagement_rate` coverage 80× lebih luas tapi **nilainya rusak**: maks 223,41%, 83 baris >10% |
| **Reliability** | Prototype memakai `k.cons` — **tidak ada kolom padanan di seluruh database** |
| **Stability & Viral Freq** | Butuh deret ≥4 titik bulanan. Hanya **5 akun** yang punya |
| **Keyword search** | `username` 97,1% ✅, `bio` 11,7%. Field `niche`, `mainTopic`, `dna`, `brands` yang dicari prototype **tidak ada di DB** |
| **Smart Criteria** | 6 dari 29 aturan bertumpu nilai hash (Gen Z, Millennial, Indonesia, Jabodetabek, Brand Safe, Active community). 23 sisanya mewarisi status filter lain |
| **Section tabs** | Hanya 2 dari 7 punya sumber: Newly Added (`created_at` 99,7%) & Recently Updated (`last_refreshed_at` 97,1%). High Match butuh `brand_fit_analysis` (0 baris), High ROI butuh rate card (0 baris) |
| **Exclude** | 5 dari 7 opsi terblokir — `campaigns` & `campaign_kols` 0 baris |
| **Collections** | Shortlist disimpan di state browser, tidak ada tabel DB |

---

## 4. JOIN / Relationship Map

Jalur utama (FK terverifikasi lewat `pg_constraint`):

```
public.kol_directory.id
  ← public.kol_social_account.kol_id        FK: kol_social_account_kol_id_fkey
      .social_account_id →  public.social_account.id
                            l2_gold.kol_profile_card
                            l2_gold.post_metric
                            l2_gold.kol_metric_daily / _monthly
                            l2_gold.content_format_daily
                            l2_gold.audience_demographics_daily
                            l2_gold.audience_geo_daily
                            l2_gold.audience_interest_daily
                            feature.ig_audience_analysis
                            feature.tt_audience_analysis
```

**7.496 dari 7.720 (97,1%)** punya jalur ini. 224 sisanya tidak akan pernah
terjangkau filter berbasis L2.

JOIN langsung dari `kol_directory` (FK resmi):

```
kol_directory.category_id → kol_categories.id → name
kol_directory.platform_id → platforms.id      → key
```

**Tanpa JOIN** (kolom langsung di `kol_directory`): `followers_count` ·
`engagement_rate` · `verified_status` · `creator_city` · `username` · `bio` ·
`last_refreshed_at` · `scrape_status` · `refresh_tier` · `created_at`

**Perlu UNION:** `feature.ig_audience_analysis` + `feature.tt_audience_analysis`
(dua tabel, kolom identik) — untuk Audience Quality & Authenticity.

**Relasi yang tidak ada:** tabel jadwal/interval update per KOL, dan tabel
Collections/shortlist.

---

## 5. Data Coverage

Denominator `public.kol_directory` = 7.720. Seluruh angka dihitung lewat jalur §4 —
tidak ada yang penyebutnya belum dihitung.

| Sumber | KOL | % |
|---|---:|---:|
| `created_at` | 7.698 | 99,7% |
| `username` · `followers_count` · `platform_id` · `last_refreshed_at` | ±7.497 | 97,1% |
| Punya jalur ke `social_account` | 7.496 | 97,1% |
| `category_id` | 4.174 | 54,1% |
| `engagement_rate` | 1.756 | 22,7% |
| `l2_gold.kol_profile_card` | 1.976 | 25,6% |
| `verified_status` | 931 | 12,1% |
| `bio` | 902 | 11,7% |
| `scrape_status` | 99 | 1,28% |
| `post_metric` · `content_format_daily` · `kol_metric_monthly` | 30 | 0,39% |
| `audience_*` · `feature.*_audience_analysis` | 23 | 0,30% |
| `kol_metric_daily.er_followers_daily` | 22 | 0,28% |
| `audience_geo_daily` level `city` | 15 | 0,19% |
| `post_metric.saves` / `.shares` | 11 | 0,14% |
| `kol_metric_monthly` dengan ≥4 bulan | 5 | 0,06% |
| `creator_city` · `refresh_tier` · `is_verified=true` · `post_metric.reach` | **0** | **0%** |

**Tabel yang kosong sama sekali:** `campaigns` · `campaign_kols` ·
`brand_fit_analysis` · `ig/tt_comments_analysis` · `unified_story` ·
`unified_rate_card` · `scheduler_config` · `audience_type='age'`

**Kualitas data yang perlu dicatat:**

| Temuan | Angka |
|---|---|
| `unknown` pada gender audiens | rata-rata **71,3%** |
| `unknown` pada interest audiens | **85,2%** (2.021 dari 2.371) |
| `engagement_rate` di luar batas wajar | maks **223,41%**, 83 baris >10% |
| Duplikat `username_normalized` | **277 grup**, 277 baris ekstra |
| Baris tanpa `platform_id` | 224 |
| Belum di-refresh >30 hari | **6.493** (86,6%) |

---

## 6. Findings / Gap

**Siap didukung DB (2)** — Platform, Last Updated.
Keduanya tetap bercatat: Platform kekurangan baris YouTube; Last Updated punya
3 dari 5 bucket kosong.

**Perlu JOIN (14)** — semua filter berbasis L2/Feature lewat
`kol_directory → kol_social_account → social_account`, plus Platform & Kategori
yang join langsung.

**Perlu kalkulasi (11)** — Gender skew (renormalisasi tanpa `unknown`) ·
Audience Quality (rata-rata 2 skor + UNION) · Engagement Rate (×100 + agregasi) ·
Views · Save/Share Rate (rasio) · Content Format (mapping + format dominan) ·
Growth Classification (bucketing) · Rising Creator · Performance Stability ·
Viral Frequency · Data Status/Next Update.

**Datanya belum tersedia (9)** — Verified only *(bug transform, bukan data hilang)* ·
Age · Location kreator · Reliability · Data Status · Update Frequency ·
Next Update · Monitoring Priority · Exclude.

**Synthetic / prototype only (3)** — Content Category/Topic · Content Style &
Personality · Collections. Ditambah 6 dari 29 aturan Smart Criteria yang nilainya
dari `hsh(k.id)`.

---

## 7. Conclusion

**Struktur DB belum cukup mendukung filter KOL Discovery — tapi penyebabnya bukan schema.**

1. **Struktur & relasinya sudah benar.** Jalur `kol_directory → kol_social_account →
   social_account → l2_gold.*` ada, ber-FK resmi, menjangkau 97,1% populasi. Tabel
   dan kolom untuk mayoritas filter sudah tersedia.

2. **Penghambat utamanya coverage.** `kol_profile_card` menutup **25,6%** populasi,
   data konten **0,39%**, data audiens **0,30%**. Dua angka terakhir menopang
   12 filter — selama tidak naik, filter-filter itu menyembunyikan >99% populasi
   bukan karena kreatornya tidak memenuhi kriteria, tapi karena nilainya tidak diketahui.

3. **Data Freshness adalah satu-satunya gap struktural yang nyata.** Ia butuh
   sesuatu yang belum punya tempat di database: **interval update per KOL**.
   `refresh_tier` ada sebagai kolom tapi 0% terisi, `scheduler_config` 0 baris.
   Empat dari lima filter di grup ini mati sampai keputusan soal jadwal update
   dibuat dan disimpan.

4. **Ada satu bug yang bisa langsung diperbaiki:** `is_verified` punya 470 nilai
   `true` di L0 Instagram dan 124 di L0 TikTok, tapi 0 di L1/L2. Penyebabnya sudah
   teridentifikasi. Ini perbaikan transform, bukan kebutuhan data baru.

5. **Beberapa filter perlu keputusan produk, bukan pekerjaan teknis:** chip YouTube
   tanpa baris `platforms`, chip Story tanpa data, chip Tech tanpa kategori padanan,
   batas tier UI yang beda dari `kol_tiers`, serta threshold Gender dan Audience
   Quality yang tidak akan pernah terpenuhi oleh sebaran data sekarang.

---

## Ringkasan Status

| Status | Jumlah |
|---|---:|
| **AVAILABLE** | 2 |
| **PARTIAL** | 18 |
| **MISSING** | 9 |
| **DERIVED** | 0 |
| **SYNTHETIC / PROTOTYPE ONLY** | 3 |
| **Total** | **32** |

**DERIVED = 0 disengaja.** Sebelas filter memang *Calculated*, tapi status DERIVED
mensyaratkan field dasarnya sudah memadai — dan semuanya masih PARTIAL atau MISSING.
Begitu coverage naik, sebagian besar akan pindah ke DERIVED.

---

Audit read-only: sesi Postgres `set_session(readonly=True)`. Tidak ada file kode,
migration, schema, config, atau baris database yang diubah; tidak ada commit/push.

---

# Correction / Re-validation

**Tanggal:** 2026-09-03 · Audit read-only kedua, database `kol` @ 10.100.14.216
**Ruang lingkup:** hanya 2 filter — **Verified only** (No. 5) dan **Location (kreator)** (No. 7).
Mapping filter lain **tidak diubah**.

> Finding Task 2 di §1–§7 **sengaja dibiarkan apa adanya** sebagai audit trail.
> Section ini adalah koreksinya. Kalau ada pertentangan, **section inilah yang berlaku**.

---

## 4.1 Verified only — Correction

### Finding sebelumnya (SALAH)

Task 2 §2 No. 5 dan §3.1 menyatakan:

> `Verified only` → `l2_gold.kol_profile_card.is_verified`, 0 true.
> Penyebabnya **bug transform**: badge verified platform ada di L0
> (IG 470 true, TT 124 true) tapi hilang di L1/L2 karena
> `l0_harmonization.instagram_profile` tidak punya kolom `is_verified`
> dan `sp_build_unified_profile` membuang nilai TikTok.

**Status finding itu: INCORRECT.**

Yang salah bukan tabelnya — tabelnya benar. Yang salah adalah **arti field-nya**.
`is_verified` tidak pernah dimaksudkan menyimpan centang biru, jadi tidak ada
nilai yang "hilang". Badge dibuang **dengan sengaja**, sesuai business rule.

### Definisi yang benar

> **`is_verified` = status akun KOL sudah connect / OAuth ke sistem kita.**
> **Bukan** centang biru / verified badge Instagram atau TikTok.

Rumusnya, apa adanya di dalam pipeline:

```sql
is_verified = (public.social_account.oauth_token IS NOT NULL)
```

### Evidence

**1. Business rule tertulis eksplisit di migration** —
`migrations/006_fix_sp_build_unified_profile.sql:17-23`:

```
--   BUSINESS RULE (keputusan mentor):
--     is_verified = status akun KOL sudah terhubung/OAuth ke sistem kita
--                 = (public.social_account.oauth_token IS NOT NULL)
--   Badge platform TIDAK BOLEH dipakai sebagai is_verified L1. Karena itu
--   kolom is_verified dibuang seluruhnya dari subquery `src`, supaya tidak
--   ada jalan bagi nilai badge untuk bocor ke L1.
```

Migration yang sama juga menjelaskan kenapa `ON CONFLICT` memakai `EXCLUDED`
dan bukan `COALESCE`: connection status harus mengikuti kondisi terkini —
kalau akun di-*disconnect*, `COALESCE` akan mengunci nilainya di `true` selamanya.

**2. Rule itu diterapkan di 3 migration:**

| File | Baris | Ekspresi |
|---|---|---|
| `migrations/006_fix_sp_build_unified_profile.sql` | 74 | `(sa.oauth_token IS NOT NULL),  -- BUSINESS RULE: connection status` |
| `migrations/011_build_unified_profile_with_metrics.sql` | 48 | idem — header baris 27: "is_verified TIDAK diubah" |
| `migrations/020_fix_has_insights_l1_dan_dedup_roster.sql` | 321 | idem |

`migrations/003_sp_sync_unified_profile.sql:34-38` menandai versi lama sebagai
OBSOLETE justru karena memuat business rule `is_verified` versi lama.

**3. Bukan cuma di file migration — ini yang benar-benar hidup di database.**
`pg_get_functiondef('l1_silver.sp_build_unified_profile()')` mengembalikan:

```
(sa.oauth_token IS NOT NULL),          -- BUSINESS RULE: connection status
is_verified = EXCLUDED.is_verified,   -- connection status: selalu definit
```

Pencarian katalog: **`l1_silver.sp_build_unified_profile` adalah satu-satunya
routine di seluruh database yang menyentuh `oauth_token`**. Tidak ada view
yang memakainya.

**4. L2 hanya meneruskan, tidak menghitung ulang.**
`orchestration/kol_orchestration/assets/gold_profile.py:117` membaca
`p.is_verified` langsung dari `l1_silver.unified_profile`.

**5. Badge platform tidak hilang — masih tersimpan utuh di layer bawah**
(harmonization adalah salinan setia L0; business rule hanya berlaku dari L1 ke atas):

| Sumber badge | Nilai |
|---|---|
| `l0_harmonization.tiktok_profile.is_verified` | 124 true · 927 false |
| `l0_raw.ig_profile_apify.raw_payload->>'verified'` | 470 true · 483 false |

Jadi kalau nanti produk memang menginginkan filter **centang biru platform**,
itu **filter baru yang terpisah** dengan sumbernya sendiri — bukan "Verified only".

### Source of truth

`public.social_account` — bukan `l2_gold.kol_profile_card`. Tabel ini punya
**lima** kolom bertema koneksi, dan seluruhnya konsisten:

| Kolom | Tipe | NOT NULL / true |
|---|---|---:|
| `oauth_token` | text | **0** dari 7.496 |
| `connected` | boolean NOT NULL | **0 true** · 7.496 false |
| `connected_at` | timestamptz | **0** |
| `refresh_token` | text | **0** |
| `token_expires_at` | timestamptz | **0** |

`data_source`: `csv` 7.494 · `apify` 2 — **tidak ada satu pun baris ber-`data_source` OAuth.**

Konfirmasi silang: seluruh tabel jalur official (yang hanya bisa terisi lewat
OAuth pemilik akun) memang kosong — `ig_profile_official`, `tt_profile_official`,
`ig_followers_official`, `tt_followers_official`, `ig_media_snapshots_official`
= **0 baris**, dan `l1_silver.unified_profile.has_insights = true` → **0 baris**.

Kelima kolom + jalur official saling menguatkan satu kesimpulan yang sama:
**belum ada satu pun KOL yang connect ke sistem.**

### JOIN path

FK resmi, terverifikasi lewat `pg_constraint`:

```
public.kol_directory.id
  ← public.kol_social_account.kol_id              FK kol_social_account_kol_id_fkey
      public.kol_social_account.social_account_id
        → public.social_account.id                FK kol_social_account_social_account_id_fkey
            .oauth_token / .connected             ← SOURCE OF TRUTH
              └─(materialisasi)→ l1_silver.unified_profile.is_verified   FK fk_upr_social
                    └─→ l2_gold.kol_profile_card.is_verified             FK fk_kol_profile_card_social_account
```

### Filter logic

```sql
-- REKOMENDASI: evaluasi langsung di social_account — coverage 97,1%
SELECT k.*
FROM public.kol_directory k
JOIN public.kol_social_account ksa ON ksa.kol_id = k.id
JOIN public.social_account     sa  ON sa.id = ksa.social_account_id
WHERE sa.oauth_token IS NOT NULL;      -- ATAU: sa.connected IS TRUE
```

Lewat `kol_profile_card.is_verified` hasilnya identik, tapi **coverage-nya turun
ke 25,6%** karena kartu L2 hanya ada untuk 1.976 akun. Untuk filter boolean seperti
ini tidak ada gunanya lewat L2 — pakai `social_account` langsung.

> Satu KOL bisa punya lebih dari satu `social_account`. Semantik yang dipakai di
> atas adalah **ANY** (connect di salah satu platform = connected). Kalau produk
> memaksa **ALL**, logikanya perlu `NOT EXISTS (... oauth_token IS NULL)`.
> Keputusan produk.

### Coverage

Denominator: `public.kol_directory` = **7.720**.

| Ukuran | KOL | % dari 7.720 |
|---|---:|---:|
| Total populasi `kol_directory` | 7.720 | 100% |
| Punya baris `kol_social_account` | 7.496 | 97,1% |
| Punya baris `social_account` | 7.496 | 97,1% |
| **Connected** (`oauth_token IS NOT NULL`) | **0** | **0%** |
| **Not connected** (`oauth_token IS NULL`) | **7.496** | **97,1%** |
| Tidak punya relationship ke `social_account` | 224 | 2,90% |

Per platform (tidak ada yang menyimpang):

| Platform | Baris `social_account` | `oauth_token IS NOT NULL` |
|---|---:|---:|
| tiktok | 4.087 | **0** |
| instagram | 3.409 | **0** |

Nilai `is_verified` yang termaterialisasi:

| Tabel | true | false | akun |
|---|---:|---:|---:|
| `l1_silver.unified_profile` | **0** | 2.001 baris | 1.976 |
| `l2_gold.kol_profile_card` | **0** | 1.976 | 1.976 |

### Apakah `is_verified` konsisten dengan OAuth connection?

**Ya — 100%.** Cross-tab `kol_profile_card.is_verified` × `(social_account.oauth_token IS NOT NULL)`
menghasilkan **satu sel saja**: `false / false = 1.976 akun`. Nol baris yang tidak cocok.

Implementasi aktual **persis sama** dengan business rule di migration 006/011/020.
Tidak ada drift antara rule dan data.

### Status final

| | |
|---|---|
| **Source of truth** | `public.social_account.oauth_token` *(`connected` sebagai konfirmasi silang)* |
| **JOIN path** | `kol_directory → kol_social_account → social_account` |
| **Filter logic** | `sa.oauth_token IS NOT NULL` |
| **Coverage field** (bisa dievaluasi) | 7.496 / 7.720 = **97,1%** |
| **Coverage nilai** (lolos filter) | **0 / 7.720 = 0%** |
| **Status** | **MISSING** |

**Kenapa tetap MISSING padahal field-nya sehat?** Karena kalau toggle
"Verified only" dinyalakan, hasilnya **0 KOL** — filter itu mengosongkan layar.

Tapi **alasannya berubah total**:

| | Task 2 (salah) | Koreksi (benar) |
|---|---|---|
| Penyebab | Bug transform membuang badge platform | Belum ada KOL yang connect ke sistem |
| Jenis masalah | Defect pipeline | Kondisi adopsi / bisnis |
| Perbaikan | Tambah kolom di harmonization IG + teruskan badge di `sp_build_unified_profile` | **Tidak ada yang perlu diperbaiki di pipeline.** Butuh KOL benar-benar connect lewat OAuth |
| Urgensi engineering | Ada — "bug yang bisa langsung diperbaiki" | **Tidak ada.** Kode sudah benar |

Poin terakhir yang paling penting: **§7 no. 4 di Task 2 merekomendasikan
"perbaikan transform" yang kalau dikerjakan justru akan MERUSAK business rule
dan melanggar keputusan mentor** di migration 006. Rekomendasi itu dicabut.

### Catatan tambahan

**`kol_directory.verified_status` (No. 5b) BUKAN pengganti.** Isinya
454 `verified` · 477 `unverified` · 6.789 NULL. Artinya tidak terdokumentasi,
tidak dipakai pipeline mana pun, dan **tidak ada hubungannya dengan OAuth**.
Memakainya untuk "Verified only" akan menampilkan 454 KOL yang **tidak** connect —
salah secara definisi. Jangan dipakai sampai semantiknya diklarifikasi.

**Dokumentasi lama yang sudah usang:** `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md:287`
masih menulis `l1_silver.unified_profile.is_verified` = "Centang" dengan sumber
`raw_payload->>'verified'` / `authorMeta.verified`. Itu deskripsi **sebelum**
migration 006. Yang berlaku sekarang adalah business rule OAuth.
*(Dokumen itu tidak diubah di sesi ini — di luar scope.)*

---

## 4.2 Location (kreator) — Re-validation

### Finding sebelumnya

Task 2 §2 No. 7: `Location (kreator)` → `kol_directory.creator_city` → 0 · 0% → **MISSING**.

**Arah finding-nya benar, tapi kalimatnya kurang tepat dan sumber alternatifnya
belum pernah ditelusuri.** Keduanya diperbaiki di bawah.

### Apakah `creator_city` ada?

**Ada.** Terverifikasi di `information_schema.columns`:

| Schema | Tabel | Kolom | Posisi | Tipe | Nullable | Comment |
|---|---|---|---:|---|---|---|
| `public` | `kol_directory` | `creator_city` | 12 | `character varying` | YES | *(tidak ada)* |

| Ukuran | Nilai |
|---|---:|
| Total baris | 7.720 |
| `creator_city` NOT NULL | **0** |
| `creator_city` NULL | **7.720** |
| Non-empty (setelah `btrim`) | **0** |
| Distinct value | **0** |

> **Kalimat yang benar:**
> **Field tersedia secara struktural, tetapi data belum terisi.**
> Bukan "field tidak ada".

### Sweep seluruh sumber lokasi

Disapu **semua schema** untuk nama kolom yang mengandung
`city|kota|location|lokasi|domicile|domisili|address|alamat|region|province|provinsi|geo|country|negara|hometown|area|district|kecamatan|kabupaten`.
Hasil lengkapnya (di luar `pg_catalog` / `information_schema`):

| # | Schema.Tabel.Kolom | Arti | Creator location? | Baris terisi |
|---:|---|---|---|---:|
| 1 | `public.kol_directory.creator_city` | Kota kreator | ✅ **Ya** | **0** |
| 2 | `l0_raw.kol_roster_import.influencer_address` | Alamat surat kreator | ⚠️ Sebagian | 137 |
| 3 | `l0_extra.ig_rate_card.location` | Lokasi di rate card | ⚠️ Mungkin | **0 baris** |
| 4 | `l0_extra.tt_rate_card.location` | idem | ⚠️ Mungkin | **0 baris** |
| 5 | `l0_harmonization.instagram_rate_card.location` | idem | ⚠️ Mungkin | **0 baris** |
| 6 | `l0_harmonization.tiktok_rate_card.location` | idem | ⚠️ Mungkin | **0 baris** |
| 7 | `l1_silver.unified_rate_card.location` | idem | ⚠️ Mungkin | **0 baris** |
| 8 | `l2_gold.audience_geo_daily.geo_key` / `.geo_level` | Lokasi **audiens** | ❌ **Tidak** | 181 |
| 9 | `feature.ig_audience_analysis.geo_distribution` | Sebaran **audiens** | ❌ **Tidak** | — |
| 10 | `feature.tt_audience_analysis.geo_distribution` | Sebaran **audiens** | ❌ **Tidak** | — |
| 11 | `l0_raw.ig_profile_official.demographics_city` | Kota **audiens** (IG Insights) | ❌ **Tidak** | **0 baris** |
| 12 | `l0_raw.ig_profile_official.demographics_country` | Negara **audiens** | ❌ **Tidak** | **0 baris** |

**No. 8–12 dikecualikan secara eksplisit** — semuanya **Audience Location**,
bukan creator location. `audience_geo_daily` tetap menjadi sumber untuk filter
No. 8 (Audience location) dan **tidak boleh** dipakai untuk No. 7.
`geo_level` di sana hanya `country` (113 baris · 23 akun) dan `city`
(68 baris · 15 akun) — tidak ada level `province`.

**Tidak ada satu pun kolom creator location di `l2_gold` maupun `feature`.**
Satu-satunya kolom lokasi di seluruh L1/L2/Feature adalah audience geo dan
`unified_rate_card.location` yang tabelnya kosong.

### Kandidat 2 — `l0_raw.kol_roster_import.influencer_address`

Inilah tabel yang dicari (audit lama menyebut "137/7.718" tanpa menyebut tabelnya):
`l0_raw.kol_roster_import`, 7.718 baris, punya FK resmi
`kol_roster_import_kol_directory_id_fkey → kol_directory(id)`, jadi bisa dipetakan
ke populasi.

| Ukuran | Nilai | % dari 7.720 |
|---|---:|---:|
| Baris roster | 7.718 | — |
| `influencer_address` non-empty | 137 | — |
| **KOL unik yang punya alamat** | **118** | **1,53%** |
| Baris beralamat tapi tanpa link ke `kol_directory` | 19 | — |
| Distinct value | 71 | — |

**Kualitas datanya tidak layak pakai.** Dari 137 nilai non-empty:

| Kategori | Jumlah | % |
|---|---:|---:|
| Alamat surat panjang (>40 karakter) | 43 | 31,4% |
| Menyebut nama kota yang dikenal | 36 | 26,3% |
| Angka murni / sampah numerik | 13 | 9,5% |
| Terlalu pendek (<6 karakter) | 12 | 8,8% |
| **Nilai yang bentuknya benar-benar nama kota** | **2** | **1,5%** |

Contoh nilai apa adanya: `Jalan jalan` (**43 baris — nilai terbanyak**, jelas
placeholder), `ABCDEFG`, `0`, `1123131`, `jsjsjsjs`, `bca`, `755921509313000`,
`askjdhkajshdkjahsdkhaksuhc`, di samping alamat lengkap semacam
`Jalan Kulintang Blok RA No. 11, Pegangsaan Dua, Kelapa Gading, Jakarta Utara 14240`.

Hanya **2 nilai** yang berbentuk nama kota polos (`Bandung`, `jakarta`).

**Kesimpulan:** ini kolom **alamat surat** (kemungkinan untuk pengiriman produk),
**bukan kota domisili**. Untuk dropdown "Creator location" ia perlu parsing kota +
normalisasi + pembersihan sampah, dan setelah semua itu hasilnya tetap **≤36 KOL
(0,47%)**. **Tidak direkomendasikan sebagai sumber.**

### Kandidat 3 — `location` di rantai rate card

Kolom `location` konsisten ada di **kelima layer** rate card
(`l0_extra.ig_rate_card`, `l0_extra.tt_rate_card`,
`l0_harmonization.instagram_rate_card`, `l0_harmonization.tiktok_rate_card`,
`l1_silver.unified_rate_card`) — struktur sudah dirancang penuh.

**Kelima tabel = 0 baris.** Coverage terhadap `kol_directory`: **0 KOL (0%)**.

Karena kosong total, tidak ada satu nilai pun yang bisa dipakai untuk memastikan
apakah `location` di sini berarti lokasi kreator atau area layanan/syuting.
Tidak ada column comment di kelima tabel. **Semantiknya belum terverifikasi** —
jangan diasumsikan creator location sampai tabelnya terisi.

### Final recommendation

**Target mapping tetap `public.kol_directory.creator_city`.** Alasannya:

1. Satu-satunya kolom di seluruh database yang secara eksplisit bernama
   *creator* location — tidak ambigu dengan audience.
2. Ada di **tabel populasi itu sendiri** → `Direct`, tanpa JOIN, otomatis
   berdenominator 7.720.
3. Tipe `varchar` cocok untuk dropdown kota di prototype
   (`filterKols()` membandingkan `k.loc` dengan `a.domicile` — persis satu string kota).

Yang belum ada adalah **jalur pengisiannya**. Tiga opsi, berurut dari yang paling layak:

| Opsi | Sumber | Hasil realistis | Penilaian |
|---|---|---:|---|
| **A** | Diisi saat registrasi/onboarding KOL | sampai 100% | **Direkomendasikan.** Satu-satunya jalan ke coverage yang berguna |
| **B** | Isi `location` rate card, lalu turunkan ke `creator_city` | 0% hari ini | Tergantung subsistem rate card dipakai lebih dulu + semantik `location` diklarifikasi |
| **C** | Parse kota dari `influencer_address` | ≤36 KOL · 0,47% | **Tidak direkomendasikan.** Sumbernya alamat surat, 43 nilai teratas placeholder `Jalan jalan` |

**Yang tidak boleh dilakukan:** memakai `audience_geo_daily.geo_key` sebagai
pengganti creator location. Keduanya menjawab pertanyaan yang berbeda —
"kreator tinggal di mana" vs "penonton ada di mana" — dan di UI keduanya
memang filter terpisah (No. 7 `domicile` vs No. 8 `audDomicile`).

### Status final

| | |
|---|---|
| **Source** | `public.kol_directory.creator_city` — **kolom ada, tipe `varchar`, data 0** |
| **Alternatif dievaluasi** | `l0_raw.kol_roster_import.influencer_address` (118 KOL · 1,53%, kualitas tidak layak) · rate card `location` (5 tabel, 0 baris) |
| **Sumber lain yang valid** | **Tidak ada** |
| **Coverage** | **0 / 7.720 = 0%** |
| **Status** | **MISSING** *(tidak berubah)* |

Kalimat statusnya diperbaiki: bukan "field tidak ada", melainkan
**field tersedia secara struktural, data belum terisi, dan tidak ada
sumber alternatif yang layak menggantikannya.**

---

## 4.3 Impact to Task 2

| Lokasi di Task 2 | Isi lama | Setelah koreksi |
|---|---|---|
| §2 No. 5 — mapping | `l2_gold.kol_profile_card.is_verified` · 0 · MISSING | **Sumber diganti** ke `public.social_account.oauth_token` (coverage field 97,1% vs 25,6%). Status tetap MISSING, **alasan berubah** |
| §2 No. 5b — alternatif | `kol_directory.verified_status` sebagai alternatif | **Dicabut sebagai alternatif.** Tidak berhubungan dengan OAuth; memakainya menghasilkan 454 KOL yang salah |
| §3.1 — "bug transform" | Seluruh section: `is_verified` = badge platform yang hilang di transform | **DICABUT.** Badge dibuang dengan sengaja sesuai business rule migration 006. Tidak ada bug |
| §2 No. 7 — mapping | `kol_directory.creator_city` · 0 · MISSING | **Tidak berubah.** Ditambah: 2 kandidat alternatif sudah ditelusuri dan ditolak |
| §5 — coverage | `creator_city` · `is_verified=true` = 0 · 0% | **Tetap akurat.** Ditambah: `oauth_token`/`connected`/`connected_at`/`refresh_token`/`token_expires_at` semuanya 0 dari 7.496 |
| §6 — Findings | "Verified only *(bug transform, bukan data hilang)*" | **Diganti:** "Verified only *(belum ada KOL yang connect; pipeline sudah benar)*" |
| §7 no. 4 — Conclusion | "Ada satu bug yang bisa langsung diperbaiki: `is_verified`… Ini perbaikan transform" | **DICABUT SELURUHNYA.** Mengerjakannya justru merusak business rule dan melanggar keputusan mentor di migration 006 |
| §4 — JOIN map | Jalur `kol_directory → kol_social_account → social_account` | **Tidak berubah, dan kini terverifikasi ulang** lewat `pg_constraint` sebagai jalur resmi filter Verified only |

**Ringkasan status: tidak ada perubahan angka.** AVAILABLE 2 · PARTIAL 18 ·
MISSING 9 · SYNTHETIC 3. Kedua filter tetap **MISSING** —
yang berubah adalah **sumber, definisi, dan tindak lanjutnya**:

- **Verified only** — sebelumnya dikira utang engineering *(perbaiki transform)*.
  Sebenarnya kondisi adopsi *(belum ada KOL yang connect)*. **Tidak ada pekerjaan
  engineering yang perlu dilakukan** — dan pekerjaan yang tadinya direkomendasikan
  justru berbahaya.
- **Location (kreator)** — status tetap sama, tapi sekarang dengan bukti bahwa
  **tidak ada** sumber alternatif yang layak, dan target kolomnya sudah pasti.

---

**Audit trail:** sesi Postgres `set_session(readonly=True, autocommit=True)`,
seluruh statement `SELECT` / katalog. **Nilai `oauth_token` tidak pernah
di-SELECT** — hanya `IS NULL` / `IS NOT NULL`, `count()`, dan persentase.
Tidak ada perubahan pada database, schema, source code, migration, atau config;
tidak ada commit/push. Satu-satunya file yang diubah adalah dokumen ini.

---

# Revisi — 2026-09-06

Koreksi kedua, di luar §4.1–§4.3. Sumber: migration `029` + diff `db.py` (uncommitted) +
`KOL_DISCOVERY_MONITORING_PRIORITY_AUDIT.md` Lampiran C + `KOL_DISCOVERY_AUDIT.xlsx`.

> **Tidak ada query baru.** Database tidak bisa dijangkau saat revisi ini ditulis
> (TCP timeout ke `10.100.14.216:5432`). Yang diverifikasi adalah repo: migration, source
> code, dan silang-baca antar dokumen. Yang belum bisa dipastikan ditandai **NEEDS VERIFICATION**.

## R1 — Kategori: kolom join dan taxonomy-nya berubah

§2 No. 2 memetakan Kategori ke `kol_directory.category_id` (skalar) → `kol_categories.name`.
Dua hal berubah:

**(a) Kolom join.** App dan `db.search_kol_directory()` yang baru memakai **`category_ids`
(array)**, bukan `category_id`:

```sql
EXISTS (SELECT 1 FROM public.kol_categories c
         WHERE c.id = ANY(k.category_ids) AND c.taxonomy_key = %(taxonomy)s)
```

Migration `029` memperlakukan **keduanya** sebagai kolom yang ada dan menjaga keduanya lewat
checksum. Coverage-nya berbeda: **3.070** (5 chip via skalar, dokumen ini) vs **3.376**
(5 chip via array, `KOL_DISCOVERY_AUDIT.xlsx` baris 3).
→ **NEEDS VERIFICATION (V-01)**: mana yang benar-benar terisi.

**(b) Taxonomy.** Sejak migration `029` (2026-09-03 15:27, **sesudah** dokumen ini ditulis),
`kol_categories.taxonomy_key` memetakan 22 dari 28 kategori mentah ke **9 Discovery Category**
(6 sisanya NULL = Unmapped). Coverage menurut commit message: **4.155 KOL unik**.

Efeknya membatalkan temuan §3.6: keluhan *"DB punya 28 kategori, UI hardcode 5"* dan
*"Entertainment 436 dan Moms 378 tidak punya chip"* **sudah terselesaikan** — keduanya kini
Discovery Category tersendiri.

| | Isi lama | Setelah revisi |
|---|---|---|
| Join | `category_id` (skalar) | **`category_ids`** (array), lewat `= ANY()` |
| Nilai filter | `kol_categories.name` — 28 nilai mentah | **`taxonomy_key`** — 9 Discovery Category |
| Coverage | 4.174 · 54,1% *(punya kategori)* / 3.070 usable | **±4.155 · ~53,8%** usable |
| Status | PARTIAL | **PARTIAL** *(tidak berubah — yang berubah sumber & usable-nya)* |

## R2 — Last Updated (§2 No. 24): AVAILABLE tidak lagi bisa dipertahankan

Dokumen ini menandai `last_refreshed_at` **AVAILABLE** karena terisi 7.496 · 97,1%.
Field-nya memang terisi — tapi **artinya tidak seperti yang diasumsikan**:

| Pengujian | Hasil |
|---|---:|
| Punya `last_refreshed_at` | 7.496 · 97,1% |
| ↳ **dan** punya baris profil di `l0_raw` | **1.976** |
| ↳ **tapi tidak punya** data apa pun di `l0_raw` | **5.520 · 73,6%** |
| Umur median | **847 hari** (maks 1.306) |
| `kol_directory.source` | `excel_import` 7.718 · `manual_add` 2 |

Untuk 73,6% baris, timestamp itu **warisan excel import, bukan jejak scrape**. Satu-satunya
penulisnya adalah `db.update_profiles()` (`db.py:399`) lewat jalur Instagram lama.

Status turun ke **PARTIAL**, dan ini merambat ke tiga filter turunannya (Data Status, Next Update,
Freshness Score): **pembilang rumusnya sendiri cacat, bukan cuma penyebutnya.**
Sumber: `KOL_DISCOVERY_MONITORING_PRIORITY_AUDIT.md` Lampiran C.

## R3 — `followers_growth` (§2 No. 21) bukan pertumbuhan 30 hari

§2 memetakan Growth Classification ke `kol_profile_card.followers_growth` tanpa menyebut
periodenya. Ekspresi yang hidup di `l1_silver.sp_build_unified_profile()`:

```sql
(followers_count - prev_followers_count) / prev_followers_count * 100
-- prev = LAG(followers_count) OVER (PARTITION BY social_account_id ORDER BY date)
```

`LAG` mengambil snapshot sebelumnya **berapa pun jaraknya**. Jarak nyatanya sekarang **10 hari**
(22 akun) dan **13 hari** (3 akun) — bukan 30. Kolom ini sah sebagai *"perubahan sejak snapshot
terakhir"*, dan hanya itu. Growth 30D harus dihitung dari deret `l1_silver.unified_profile`
(`KOL_DISCOVERY_FILTER_BACKEND_PLAN.md` T1 / Task 5 `T-09`).

## R4 — §7 no. 1: "struktur & relasinya sudah benar" perlu satu catatan

Kesimpulannya tetap berlaku, tapi ada satu jalur JOIN yang **tidak** lewat
`kol_directory → kol_social_account → social_account` dan mudah tertukar:

```
kol_directory.id ← agency_kol_accounts.kol_account_id      7.719 cocok
                     ← campaign_kols.agency_kol_account_id  0 baris
```

Semua filter berbasis campaign (Exclude "existing brand partners", Min Campaigns, Monitoring
Priority) memakai jalur ini, **bukan** `[SA]`. Sumber: `KOL_DISCOVERY_MONITORING_PRIORITY_AUDIT.md` §2.3.

## Ringkasan dampak

| Bagian | Isi lama | Setelah revisi |
|---|---|---|
| §2 No. 2 | `category_id → name` · PARTIAL | `category_ids → taxonomy_key` · PARTIAL *(V-01)* |
| §2 No. 3 | `kol_profile_card.tier` · 25,5% | `followers_count` · 93,2% *(Task 4)* |
| §2 No. 5 | `kol_profile_card.is_verified` | `social_account.oauth_token` *(§4.1)* |
| §2 No. 21 | `followers_growth` | **Periode salah** — pakai deret `unified_profile` |
| §2 No. 24 | AVAILABLE | **PARTIAL** — semantik cacat |
| §3.1 | Bug transform | **DICABUT** *(§4.1)* |
| §3.6 Kategori | 28 vs 5 chip, Entertainment/Moms tanpa chip | **Terselesaikan** oleh taxonomy 9 kategori |
| §7 no. 4 | "Ada satu bug yang bisa langsung diperbaiki" | **DICABUT** *(§4.3)* |
| Total filter | 32 | **40** *(baseline app — Task 1 §Revisi)* |
| Ringkasan status | AVAILABLE 2 · PARTIAL 18 · MISSING 9 · SYNTHETIC 3 | **AVAILABLE 1 · PARTIAL 19** · sisanya tetap |

Mapping final: `docs/KOL_DISCOVERY_TASK5_DESIGN.md`.
