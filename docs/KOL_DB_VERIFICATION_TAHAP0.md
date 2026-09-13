# TAHAP 0 — VERIFIKASI LANGSUNG DB `kol`

Lanjutan dari `KOL_EXCEL_DB_MATCHING_AUDIT.md`. Dokumen ini **menggantikan**
seluruh angka DB di audit itu yang bersumber E1/E2/E3.

---

## 0. IDENTITAS SESI AUDIT

| | |
|---|---|
| **Timestamp audit** | **2026-09-13 00:22:06 UTC** (`now()` dari server) |
| **Host** | `10.100.14.216:5432` (`inet_server_addr()` = `10.100.14.216/32`) |
| **Database** | **`kol`** (`current_database()`) — **bukan** `tsdb` |
| **User** | `postgres` |
| **Versi server** | PostgreSQL **16.15** (Ubuntu 16.15-0ubuntu0.24.04.1) |
| **Mode sesi** | `transaction_read_only` = **`on`** |
| **Schema dipakai** | `public` (40 tabel) · `feature` (9) · `l0_raw` (20) · `l0_harmonization` (14) · `l0_extra` (2) · `l1_silver` (8) · `l2_gold` (8) — **total 101 tabel, 0 view** |

**Pengaman yang dipakai** (`scratchpad/q.py`):
1. `set_session(readonly=True)` + `default_transaction_read_only=on` — Postgres
   sendiri yang menolak tulisan, bukan cuma niat gue.
2. Blocklist regex menolak `INSERT/UPDATE/DELETE/TRUNCATE/DROP/ALTER/CREATE/
   GRANT/REVOKE/COMMENT ON/COPY/VACUUM/REINDEX/REFRESH/CALL/DO` **sebelum**
   query dikirim.
3. `statement_timeout=120000`.

**Yang dieksekusi:** hanya `SELECT` terhadap `information_schema`,
`pg_catalog`, dan tabel data. **Nol** DDL, **nol** DML, **nol** migration.

> ⚠️ `reltuples` di `pg_class` bernilai `-1` untuk hampir seluruh tabel `public`
> — tabel-tabel itu belum pernah di-`ANALYZE`. Semua angka baris di bawah adalah
> **`COUNT(*)` eksak**, bukan perkiraan planner.

---

## 1. RINGKASAN — apa yang berubah

| | Jumlah |
|---|---:|
| **CONFIRMED** — temuan lama benar | **31** |
| **CHANGED** — temuan lama sudah tidak akurat | **18** |
| **NOT FOUND** — dicari, memang tidak ada | **9** |

### 1.1 Tiga perubahan yang paling mengubah desain

**(1) EMV punya kolom — dan justru di grain campaign.**
Audit lama menyimpulkan "EMV: NO MATCH secara definisi". Kolomnya ternyata ada
di **empat** tempat, dua di antaranya bergrain campaign:

| Kolom | Grain | Terisi |
|---|---|---:|
| `feature.ig_audience_analysis.emv` | per akun | 0 / 16 |
| `feature.tt_audience_analysis.emv` | per akun | 0 / 11 |
| **`public.campaign_kols.emv`** | **campaign × KOL** | 0 / 0 |
| **`public.campaign_content_performance.emv`** | **campaign-content × snapshot** | 0 / 0 |

Yang **tetap benar**: tidak ada satu pun kolom `cpm`, `cpv`, `multiplier`,
`benchmark`, atau `coefficient` di seluruh 101 tabel. Jadi rumah EMV ada,
konstanta penyusunnya tidak — dan H1 tetap terbuka.

**(2) Grain biaya campaign sudah punya rumah lengkap.**
H15 di audit lama ("per-KOL atau per-campaign?") ternyata sudah dijawab oleh
skema. `campaign_kols` punya **36 kolom**, termasuk `deal_price`, `currency`,
`reach`, `impressions`, `total_engagement`, `engagement_rate`, `emv`, `roas`,
`performance_score`, `objective`. Dan `campaign_content_performance` punya
`views`, `likes`, `comments_count`, `shares`, `saves`, `reach`, `impressions`,
`total_engagement`, `engagement_rate`, `emv`, `delta_views`, `delta_engagement`,
plus `source` / `raw_ref_table` / `raw_ref_id` / `is_final` untuk provenance.

Artinya CPV/CPE/CPM **versi campaign** bisa dihitung dari kolom yang sudah ada
(`deal_price ÷ reach|impressions|total_engagement`) begitu ada barisnya —
tanpa kolom baru. Yang dimodelkan Excel (harga rate-card per KOL) adalah hal
yang **berbeda**, dan sekarang jelas keduanya punya rumah terpisah.

**(3) Delapan migration (036–044) sudah jalan, dan L2 sudah berisi.**
Audit lama menandai ini "belum ter-commit, tidak menjamin sudah dijalankan".
Sudah dijalankan semua. `l2_gold.kol_profile_card` yang dulu **0 baris**
sekarang **1.978 baris / 71 kolom**, dan lima tabel L2 lain yang dulu kosong
sekarang berisi.

### 1.2 Satu temuan yang menutup pertanyaan lama

**`tsdb` tidak ada di server ini.** `pg_database` memuat 21 database:
`autometric_v2`, `db_historical_data_dump`, `db_historikal_data`,
`db_historikal_data1`, `db_mart_socmed`, `db_report_phase_2_test`,
`db_scraping_socmed`, `fpkarma`, **`kol`**, `l0_crawling`, `l0_csv_dashboard`,
`l2_testing`, `postgres`, `request`, `request_crawling`, `socmed_report`,
`socmed_report26`, `socmed_report_development`, `tester`, `testing`,
`testing_import`. **Tidak ada `tsdb`.**

Jadi `tsdb.public.brands` yang diklaim `brand_style_personality.xlsx` **tidak
bisa diverifikasi dari host ini**. Kandidat paling mungkin `autometric_v2`,
tapi gue **tidak menyentuhnya** — lo bilang target hanya `kol`.

---

## 2. VERIFIKASI #1 — `public.brand`

**Temuan audit lama:** ada, 11 kolom, 0 baris; kolom `name`, `category`,
`brand_keywords`, `brand_hashtags`, `is_competitor_tracked`.

**Hasil SELECT:**

| pos | kolom | tipe | nullable | default |
|---:|---|---|---|---|
| 1 | `id` | uuid | NO | `gen_random_uuid()` |
| 2 | `agency_id` | uuid | YES | |
| 3 | `name` | varchar(255) | YES | |
| 4 | `category` | varchar(255) | YES | |
| 5 | `logo_url` | text | YES | |
| 6 | `is_competitor_tracked` | boolean | YES | |
| 7 | `is_active` | boolean | YES | |
| 8 | `brand_keywords` | **jsonb** | YES | |
| 9 | `brand_hashtags` | **jsonb** | YES | |
| 10 | `created_at` | timestamptz | YES | |
| 11 | `updated_at` | timestamptz | YES | |

`COUNT(*)` = **0**. `public.brand_members` juga **0**.

**Status: CONFIRMED** (11 kolom, 0 baris — tepat).

**Detail baru:** `brand_keywords` dan `brand_hashtags` bertipe **jsonb**, bukan
array/teks. Dan yang **tidak ada** di tabel ini: `industry`,
`brand_personality`, `brand_tone`, `communication_style`, `positioning`,
`brand_niche`, `brand_values`, `company_description`.

**Implikasi desain:** dari **39 field** `Brand_Profile` Excel, hanya **4** punya
kolom (`name`, `category`, `brand_keywords`, `brand_hashtags`) — persis seperti
pengakuan CMP_README r16. Rekomendasi §3.2 audit lama (jangan bikin tabel brand
baru) **tetap berlaku**, dan sekarang jelas bahwa menampung `Brand_Profile`
berarti menambah ~35 kolom atau satu tabel `brand_profile` terpisah — keputusan
yang tetap menunggu H2.

---

## 3. VERIFIKASI #2 & #3 — tabel `campaign_*`

**Temuan audit lama:** ±15 tabel, **semuanya 0 baris**.

**Hasil SELECT — `COUNT(*)` eksak untuk 14 tabel campaign:**

| Tabel | Baris | Status |
|---|---:|---|
| `campaigns` | 0 | CONFIRMED |
| `campaign_kols` | 0 | CONFIRMED |
| `campaign_brief` | 0 | CONFIRMED |
| `campaign_content_performance` | 0 | CONFIRMED |
| `campaign_kol_deliverables` | 0 | CONFIRMED |
| `campaign_kol_payments` | 0 | CONFIRMED |
| `campaign_kol_progress_logs` | 0 | CONFIRMED |
| `campaign_activities` | 0 | CONFIRMED |
| `campaign_activity_attachments` | 0 | CONFIRMED |
| `campaign_milestones` | 0 | CONFIRMED |
| `campaign_orders` | 0 | CONFIRMED |
| `campaign_targets` | 0 | CONFIRMED |
| `campaign_tracking_jobs` | 0 | CONFIRMED |
| **`campaign_stages`** | **12** | **CHANGED** |

**Status: CHANGED** — 13 dari 14 kosong, bukan 14 dari 14.

`campaign_stages` berisi **master workflow 12 tahap**, dengan `owner_role`:

| seq | `stage_key` | label | owner_role |
|---:|---|---|---|
| 1 | `campaign_confirmed` | Campaign confirmed | brand |
| 2 | `creator_confirmation` | Creator confirmation | creator |
| 3 | `briefing_completed` | Briefing completed | brand |
| 4 | `content_ideation` | Content ideation | creator |
| 5 | `content_production` | Content production | creator |
| 6 | `editing` | Editing | creator |
| 7 | `revision` | Revision | brand |
| 8 | `approval` | Approval | brand |
| 9 | `scheduled` | Scheduled | system |
| 10 | `published` | Published | creator |
| 11 | `performance_update` | Performance update | system |
| 12 | `completed` | Completed | system |

**Implikasi desain:** DB punya model **status campaign** yang jauh lebih kaya
daripada Excel. `Campaign_Profile` Excel tidak punya konsep tahapan sama sekali
— field `Objective`/`Campaign Type`-nya adalah deskriptor, bukan workflow.
Jadi untuk "status campaign", **DB yang harus jadi acuan, bukan Excel.**

### 3.1 `campaign_kols` — 36 kolom

```
id, campaign_id, agency_kol_account_id, status, deal_price, currency,
deliverable_notes, content_url, confirmed_at, completed_at, reach,
engagement_rate, emv, roas, created_at, updated_at, collaboration_type,
is_lead, approval_status, progress_stage, progress_pct, impressions,
total_engagement, performance_score, contents_agreed_count,
contents_delivered_count, contents_tracked_count, last_tracked_at,
current_stage_id, milestones_completed, last_activity_at,
campaign_order_id, objective, workflow_started_at,
workflow_duration_days, stage_updated_at
```

**Status: CHANGED** — audit lama hanya menyebut `impressions` dan
`last_tracked_at`. Ternyata tabel ini sudah memuat **seluruh blok komersial dan
performa**: `deal_price`, `currency`, `reach`, `engagement_rate`, `emv`, `roas`,
`impressions`, `total_engagement`, `performance_score`.

**Implikasi desain — ini membatalkan sebagian §3.3 audit lama.** Usulan
"kolom skor campaign × KOL" tetap perlu untuk `campaign_fit` / `unified_match` /
`style_fit` / `personality_fit` / `tone_fit` / `comm_style_fit`, **tapi**
`performance_score` sudah ada dan mungkin cukup untuk sebagian kebutuhan.
Pemetaan Excel→DB untuk `campaign_kols` jadi:

| Field Excel `Campaign_Match` | Kolom `campaign_kols` | Status |
|---|---|---|
| `Campaign ID` | `campaign_id` | MATCH |
| `KOL ID` | `agency_kol_account_id` | MATCH *(via agency, bukan kol_directory)* |
| `Brand Match` .. `Unified Match` | — | **MISSING** (6 kolom skor) |
| `Match Level` | — | MISSING |
| `Campaign Reason` | `deliverable_notes` (?) | **NPD** — bukan hal yang sama |
| — | `deal_price`, `currency` | **ada di DB, tidak ada di Excel** |
| — | `emv`, `roas`, `performance_score` | **ada di DB, tidak ada di Excel** |
| — | `progress_stage`, `progress_pct`, `current_stage_id` | **ada di DB, tidak ada di Excel** |

### 3.2 `campaign_content_performance` — 23 kolom

```
id, campaign_kol_deliverable_id, campaign_id, campaign_order_id,
snapshot_date, views, likes, comments_count, shares, saves, reach,
impressions, total_engagement, engagement_rate, emv, delta_views,
delta_engagement, source, raw_ref_table, raw_ref_id, is_final,
fetched_at, created_at
```

**Status: CHANGED** — audit lama hanya menyebut `impressions`.

**Implikasi desain:** seluruh metric yang audit lama tandai MISSING untuk
"campaign performance" (`reach`, `impressions`, `views`, `engagement`) **punya
kolom di sini**, bergrain **per-deliverable per-snapshot_date** — jadi ini tabel
time-series, bukan snapshot tunggal. Kolom `source` + `raw_ref_table` +
`raw_ref_id` + `is_final` menunjukkan skema ini **sudah dirancang membawa
provenance** — pola yang §3.3 audit lama usulkan untuk `category_basis` ternyata
sudah dipakai di tempat lain.

### 3.3 `campaign_brief` — 12 kolom

```
id, campaign_id, content_type, deliverables, posting_schedule, caption,
hashtag, cta, attachment_url, created_at, updated_at, inspiration_id
```

**Status: CHANGED** — `cta` **ada** (audit lama menandainya "belum
terverifikasi"). Yang **tidak ada**: `Content Style`, `Creator Personality`,
`Campaign Tone`, `Communication Style` → keempatnya **CONFIRMED MISSING**,
sesuai audit lama.

---

## 4. VERIFIKASI #4 — `feature.brand_fit_analysis`

**Temuan audit lama:** 11 kolom, grain KOL × brand, 0 baris.

**Hasil SELECT:**

| pos | kolom | tipe |
|---:|---|---|
| 1 | `id` | uuid |
| 2 | `agency_kol_account_id` | uuid |
| 3 | `brand_id` | uuid |
| 4 | `partnership_score` | numeric |
| 5 | `sub_scores` | **jsonb** |
| 6 | `audience_overlap_pct` | numeric |
| 7 | `overlap_summary` | text |
| 8 | `category_fit_tags` | **jsonb** |
| 9 | `recommendations` | **jsonb** |
| 10 | `created_at` | timestamptz |
| 11 | `updated_at` | timestamptz |

`COUNT(*)` = **0**.

**Grain — dibuktikan constraint, bukan ditebak:**

```
uq_brand_fit_analysis                    UNIQUE (agency_kol_account_id, brand_id)
brand_fit_analysis_pkey                  PRIMARY KEY (id)
fk_brand_fit_analysis_agency_kol_account FOREIGN KEY (agency_kol_account_id)
                                           REFERENCES agency_kol_accounts(id)
fk_brand_fit_analysis_brand              FOREIGN KEY (brand_id) REFERENCES brand(id)
```

**Status: CONFIRMED** — 11 kolom, 0 baris, grain terbukti.

**Detail penting yang audit lama tidak sebut:** grain-nya
**(`agency_kol_account_id`, `brand_id`)** — bukan `kol_directory.id`, bukan
`social_account_id`. Jadi kalau hasil Brand Match ditulis ke sini, kuncinya
harus lewat `agency_kol_accounts`, dan itu tabel yang **7.431 baris** (vs
`kol_directory` 7.432) — ada 1 baris yang tidak punya pasangan.

**Implikasi desain:** rekomendasi §3.2 audit lama (pakai tabel ini sebagai rumah
hasil Brand Match) **tetap valid dan sekarang lebih kuat** — `sub_scores` jsonb
cukup untuk 22 sub-skor, `recommendations` jsonb untuk output
`Match_Explanation`, `category_fit_tags` untuk tag kategori. Tapi H8 (apakah
Brand Fit = Brand Match) **tetap terbuka**, dan sekarang ada kendala tambahan:
FK ke `brand(id)` berarti **tidak ada satu baris pun bisa ditulis sampai
`public.brand` terisi**.

---

## 5. VERIFIKASI #5 — EMV: reach, CPM, multiplier, emv

### 5.1 Sapuan global seluruh 101 tabel

Query: `column_name ~* '(emv|cpm|cpv|cpe|multiplier|benchmark|coefficient|earned)'`

| Lokasi | Kolom | Tipe |
|---|---|---|
| `feature.ig_audience_analysis` | `cpe` | numeric |
| `feature.ig_audience_analysis` | `emv` | numeric |
| `feature.tt_audience_analysis` | `cpe` | numeric |
| `feature.tt_audience_analysis` | `emv` | numeric |
| `public.campaign_content_performance` | `emv` | numeric |
| `public.campaign_kols` | `emv` | numeric |

| Yang dicari | Hasil |
|---|---|
| `emv` | **4 kolom** |
| `cpe` | **2 kolom** |
| `cpm` | **NOT FOUND — 0 kolom** |
| `cpv` | **NOT FOUND — 0 kolom** |
| `multiplier` | **NOT FOUND — 0 kolom** |
| `benchmark` | **NOT FOUND — 0 kolom** |
| `coefficient` | **NOT FOUND — 0 kolom** |

**Status: CHANGED** untuk `emv` (audit lama menyimpulkan "NO MATCH");
**CONFIRMED** untuk absennya CPM/CPV/multiplier/benchmark.

### 5.2 `feature.ig_audience_analysis` — struktur 21 kolom

```
id, social_account_id, audience_quality_score, authenticity_score,
follower_quality_score, gender_breakdown, age_gender_breakdown, top_interest,
geo_distribution, active_hours_heatmap, avg_reach, cpe, emv,
created_at, updated_at, female_pct, male_pct, gender_known_pct,
audience_quality_tier, interest_top, interest_source
```

Grain = `social_account_id`. Kolom 16–18 dari migration **037**, kolom 19–21 dari
migration **039** → **kedua migration terbukti sudah dijalankan.**

### 5.3 Isi aktual

| Tabel | Baris | `avg_reach` | `cpe` | `emv` | `audience_quality_score` | `authenticity_score` | `follower_quality_score` | `female_pct` | `audience_quality_tier` | `interest_top` | `age_gender_breakdown` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `ig_audience_analysis` | 16 | **0** | **0** | **0** | **16** | **16** | **16** | 16 | 16 | 16 | 16 |
| `tt_audience_analysis` | 11 | **0** | **0** | **0** | **11** | **11** | **11** | 11 | 11 | 11 | 11 |

**Status EMV/CPE/reach: CONFIRMED** — ketiganya 0 terisi. Rumahnya ada, isinya
kosong, dan konstanta penyusun EMV tidak ada di DB. **H1 tetap terbuka.**

**Status skor kualitas: CHANGED.** Audit lama (E1) menandai
`audience_quality_score` / `authenticity_score` / `follower_quality_score`
sebagai *"L2 METRIC (planned), belum ditentukan, NEED DEFINITION"* dan E3
mencatat 23–24 kreator. Ketiganya sekarang **100% terisi untuk 27 baris yang
ada** — algoritmanya sudah diimplementasikan.

Sample nyata (`ig_audience_analysis`, 6 baris teratas):

| aq | auth | fq | tier | female% | male% | gender_known% | interest_top | interest_source |
|---:|---:|---:|---|---:|---:|---:|---|---|
| 94 | 100 | 88 | High | 27,27 | 72,73 | 22,45 | religion | `audience` |
| 78 | 100 | 56 | High | 57,14 | 42,86 | 28,0 | gaming | `audience` |
| 76 | 100 | 51 | High | 92,86 | 7,14 | 28,57 | religion | **`content_inferred`** |
| 72 | 73 | 71 | Medium | 51,52 | 48,48 | 33,0 | business | `audience` |
| 68 | 69 | 68 | Medium | 18,18 | 81,82 | 22,0 | religion | `audience` |
| 65 | 67 | 63 | Medium | 20,0 | 80,0 | 25,0 | religion | `audience` |

**Implikasi desain:** dua dari empat input Brand Safety versi CMP
(`authenticity_score` 40% + `follower_quality_score` 30%) **sudah terisi nyata**,
bukan lagi "NEED DEFINITION". Ditambah `verified_status` (15%) dan `paid_ratio`
(15%) yang juga ada, **Brand Safety versi *integrity screen* sekarang bisa
dihitung 100% dari kolom yang terisi** — untuk 27 akun. Naik dari "3 dari 4
input" menjadi "4 dari 4 input", dengan catatan cakupan tetap 0,36%.

Dan `interest_source` sudah membawa nilai **`audience`** vs
**`content_inferred`** — konsep *basis/provenance* yang §3.3 audit lama usulkan
**sudah ada di DB**, setidaknya untuk interest.

### 5.4 `age_gender_breakdown` — terisi bentuknya, kosong isinya

**Temuan audit lama (E3 CMP_Validation r58):** "`age_gender_breakdown` NULL in
all 27 audience-analysis rows".

**Hasil SELECT:** kolomnya **terisi 27/27**. Tapi isinya:

```json
{"age": {"45+": 0, "13-17": 0, "18-24": 0, "25-34": 0, "35-44": 0,
         "unknown": 49}, "source": ...}
```

Lima bucket umur bernilai **0**, seluruh populasi jatuh ke `unknown` (49, 50,
99, 100 per baris).

**Status: CHANGED secara struktur, CONFIRMED secara fungsi.** Kolomnya tidak
lagi NULL, tapi datanya tetap tidak bisa dipakai. **Ini jenis perubahan yang
paling mudah disalahbaca** — pembacaan sekilas akan menyimpulkan "umur audiens
sudah tersedia", dan itu salah.

---

## 6. VERIFIKASI #6 — `public.kol_directory`

**Temuan audit lama:** 22 kolom, 7.718–7.721 baris; ER 1.744 (22,6%);
bio ~12%; `creator_city` 0%; kategori 4.174 (54,1%); verified 455 dari 932.

**Hasil SELECT — 22 kolom** (posisi 22 hilang → ada kolom yang pernah di-drop):

```
id, platform_id, platform_user_id, username, username_normalized,
followers_count (integer), engagement_rate (numeric), category_id (uuid),
avatar_url, profile_url, bio, creator_city, source, directory_status,
verified_status, refresh_tier, scrape_status, last_refreshed_at,
created_by, created_at, updated_at, category_ids (ARRAY)
```

**Isi aktual:**

| Metric | Audit lama | **Sekarang** | Status |
|---|---:|---:|---|
| Total baris | 7.718 | **7.432** | **CHANGED** |
| `directory_status='active'` | 6.991 (E3) | **7.432 (100%)** | **CHANGED** |
| `followers_count` terisi | 97,1% | **7.210 (97,0%)** | CONFIRMED |
| `engagement_rate` terisi | 1.744 (22,6%) | **1.736 (23,4%)** | CONFIRMED |
| `bio` terisi | ~897 (12,8%) | **902 (12,1%)** | CONFIRMED |
| `creator_city` terisi | **0%** | **0** | **CONFIRMED** |
| `category_ids` non-empty | 4.174 (54,1%) | **4.002 (53,8%)** | CONFIRMED |
| `verified_status='verified'` | 455 dari 932 bernilai | **455 dari 931 bernilai** | CONFIRMED |
| `refresh_tier` terisi | butuh keputusan | **0 (100% NULL)** | **CONFIRMED** |
| `directory_status` nilai unik | 1 (`active`) | **1 (`active`)** | CONFIRMED |

**Style / personality di `kol_directory`: NOT FOUND** — tidak ada kolom
`content_style`, `communication_style`, `creator_personality`, `tone`,
`values`, `positioning`.

**Detail teknis baru:**
- `followers_count` bertipe **`integer`**, bukan `bigint`. Nilai maksimum saat
  ini **685.896.635** (`@instagram`) — masih aman di bawah batas int4
  (2.147.483.647), tapi ini plafon yang perlu diketahui.
- Ada **dua** kolom kategori: `category_id` (uuid tunggal) **dan** `category_ids`
  (array). Keduanya terisi 4.002 — kandidat duplikasi yang perlu diperiksa.
- **ER punya outlier serius:** min 0 · **max 223,41** · avg 2,83 · median 0,60.
  `CAL_ER_TARGET`=6 di Excel akan memberi skor 100 pada nilai 223,41% yang jelas
  bukan ER nyata. **Ini temuan baru yang tidak ada di audit lama** dan ia
  merusak asumsi normalisasi Performance Quality.

---

## 7. VERIFIKASI #7 — `public.kol_categories`

**Temuan audit lama (E3 §11a):** 28 baris, 9 canonical key, 6 baris
`taxonomy_key` NULL, Lifestyle 2.442 + Beauty 1.206, Tech 4 kreator.

**Hasil SELECT — struktur:** 5 kolom saja —
`id`, `name`, `created_at`, `updated_at`, `taxonomy_key (text)`.
**Tidak ada** kolom parent, level, kode, atau hierarki.

**Hasil SELECT — 28 baris lengkap dengan hitungan kreator dari
`kol_directory.category_ids`:**

| Nama mentah | `taxonomy_key` | Kreator | | Nama mentah | `taxonomy_key` | Kreator |
|---|---|---:|---|---|---|---:|
| Lifestyle | Lifestyle | 2.442 | | Parenting and family | Moms | 8 |
| Beauty | Beauty | 1.206 | | Musicians | Entertainment | 7 |
| Moms | Moms | 542 | | Medical | **NULL** | 6 |
| Entertainment | Entertainment | 458 | | Dance | Entertainment | 3 |
| Gen Z | Gen Z | 145 | | Gym Enthusiast | Fitness | 3 |
| Fashion | Fashion | 73 | | Story Teller | Entertainment | 3 |
| Foodies | Food | 63 | | Gaming | Tech | 2 |
| Home Decor | Lifestyle | 58 | | Spirituality and religion | **NULL** | 2 |
| Food | Food | 55 | | Technology and gadgets | Tech | 2 |
| Fitness | Fitness | 24 | | Animal Lovers | **NULL** | 1 |
| Sports | Fitness | 24 | | Business and entrepreneurship | **NULL** | 1 |
| Humor | Entertainment | 12 | | Cyclist | Fitness | 1 |
| Travel | Lifestyle | 12 | | Environmentalism and sustainability | **NULL** | 1 |
| Automotive and motorsports | **NULL** | 9 | | Cooking | Food | 9 |

**Status: CONFIRMED — identik baris per baris dengan E3 §11a.** Nama, hitungan,
`taxonomy_key`, dan keenam NULL-nya sama persis. Ini sekaligus membuktikan blok
CMP di Excel memang membaca server ini apa adanya.

**Rollup canonical key:**

| `taxonomy_key` | Kreator |
|---|---:|
| Lifestyle | 2.511 |
| Beauty | 1.206 |
| Moms | 550 |
| Entertainment | 483 |
| Gen Z | 145 |
| Food | 118 |
| Fashion | 73 |
| Fitness | 52 |
| **Tech** | **4** |

| Metric | Audit lama | **Sekarang** | Status |
|---|---:|---:|---|
| Kreator punya `category_ids` | 4.174 | **4.002** | CONFIRMED |
| Punya minimal 1 `taxonomy_key` non-NULL | 3.888 | **3.983** | CONFIRMED |
| `category_ids` ada tapi semua key NULL | ~20 | **19** | CONFIRMED |
| Kreator >1 kategori | 1.183 | **1.130** | CONFIRMED |
| Lifestyle+Beauty share | 93,8% | **93,3%** (3.717/3.983) | CONFIRMED |
| Tech | 4 | **4** | CONFIRMED |
| Tanpa kategori | 3.547 | **3.430** (+19 key-NULL = 3.449) | CONFIRMED |

Distribusi jumlah kategori per kreator: 1 → 2.863 · 2 → 1.110 · 3 → 28 ·
**5 → 1**. Jadi klaim "DB mengizinkan 5" **CONFIRMED** — satu kreator memang
membawa 5.

**Sub category / L2 / hierarki: NOT FOUND.** Tidak ada tabel `kol_sub_categories`,
tidak ada kolom `sub_category_ids`, tidak ada kolom parent di `kol_categories`.

**Implikasi desain:** §8.4 audit lama (jangan bikin category master baru, isi 6
key NULL, baru bikin L2) **tetap berlaku tanpa perubahan**. Yang menguat: karena
`kol_categories` benar-benar hanya 5 kolom tanpa hierarki, menambahkan L2 berarti
tabel baru — bukan kolom tambahan di tabel ini.

---

## 8. VERIFIKASI #8 — `l2_gold.kol_profile_card`

**Temuan audit lama:** E1 §17.13 menandainya `SCHEMA READY` · **EMPTY, 0 baris**,
24 kolom. Dokumen lain menyebut 42 kolom / 1.976–1.978 baris.

**Hasil SELECT: 71 kolom · 1.978 baris.**

**Status: CHANGED besar.**

Seluruh kolom dari migration 036–044 **ada**, jadi kedelapan migration itu
terbukti sudah dijalankan di server:

| Migration | Kolom yang ditambahkan | Ada? |
|---|---|:-:|
| 036 | `views_analyzed_count`, `avg_views`, `median_views`, `view_to_follower_ratio`, `like_to_view_ratio` | ✅ pos 25–29 |
| 037 | `previous_snapshot_date`, `previous_followers`, `days_between`, `daily_growth`, `projected_30d`, `paid_ratio`, `paid_signal_count`, `share_rate`, `post_frequency_monthly`, `observation_days`, `female_pct`, `male_pct`, `gender_known_pct` | ✅ pos 30–42 |
| 038 | `growth_class`, `gender_reliability`, `post_frequency_daily`, `post_frequency_count`, `post_frequency_reliability`, `monitoring_er_pct`, `monitoring_priority` | ✅ pos 43–49 |
| 039 | `save_rate`, `viral_frequency`, `viral_post_count`, `viral_threshold_views`, `content_topic`, `content_topic_source`, `format_dominant`, `audience_quality_score`, `authenticity_score`, `audience_quality_tier`, `audience_interest_top`, `audience_interest_source`, `er_stddev_pp`, `er_periods`, `performance_stability`, `rising_creator` | ✅ pos 50–65 |
| 040 | `projected_followers_30d` | ✅ pos 66 |
| 042–044 | `creator_age`, `creator_birth_year`, `creator_age_band`, `creator_age_source`, `creator_age_confidence` | ✅ pos 67–71 |

### 8.1 Style / personality di `kol_profile_card`: NOT FOUND

Tidak ada `content_style`, `communication_style`, `creator_personality`,
`brand_personality`, `tone`, `values`, `positioning`. Juga tidak ada
`community_score`, `consistency_score`, `brand_safety_score`,
`competitor_saturation`, `risk_flag`, `content_quality`, `purchase_intent`,
`sub_category`. **CONFIRMED.**

### 8.2 Isi aktual — 1.978 baris

| Kolom | Terisi | | Kolom | Terisi |
|---|---:|---|---|---:|
| `tier` | **1.913** | | `content_topic` | 42 |
| `monitoring_priority` | **1.012** | | `format_dominant` | 49 |
| `post_frequency_reliability` | 49 | | `observation_days` | 49 |
| `paid_ratio` | 48 | | `post_frequency_monthly` / `_daily` | 26 |
| `avg_views` | 30 | | **`median_views`** | **30** |
| `like_to_view_ratio` | 30 | | `viral_frequency` | 30 |
| `audience_quality_score` | 27 | | `authenticity_score` | 27 |
| `audience_quality_tier` | 27 | | `female_pct` | 27 |
| `creator_age` / `creator_age_band` | **27** | | `followers_growth` | 25 |
| `daily_growth` | 25 | | `projected_followers_30d` | 25 |
| `growth_class` | 25 | | `rising_creator` | 25 |
| **`view_to_follower_ratio`** | **22** | | `share_rate` / `save_rate` | 11 |
| `performance_stability` | 11 | | `rate_card` | **0** |
| `rate_card_min_fee` | **0** | | `rate_card_max_fee` | **0** |

`rate_card*` **0 terisi dari 1.978** → **CONFIRMED** (audit lama: "rate_card_min_fee
NULL in all 1.978 card rows" — angkanya tepat).

### 8.3 Vocabulary nyata — dibandingkan Excel

**`format_dominant`** (49 terisi):

| Nilai DB | Jumlah | Padanan `taksonomi_kol.Content Format` |
|---|---:|---|
| `Carousel` | 24 | Static Post/Carousel |
| `Video` | 20 | Short-video/Reels **atau** Long-form Video — ambigu |
| `Image` | 5 | Static Post/Carousel |

**Status: CONFIRMED** — 3 nilai DB vs 4 nilai Excel. `Live Streaming` dan
`Long-form Video` tidak terwakili, dan `Video` tidak bisa dipisah jadi
short/long. **H12 tetap terbuka.**

**`content_topic`** (42 terisi) — dan di sini ada masalah baru:

| `content_topic` | `content_topic_source` | Jumlah |
|---|---|---:|
| religion | `content` | 8 |
| fitness | `content` | 7 |
| beauty | `content` | 6 |
| music | `content` | 5 |
| food | `content` | 4 |
| parenting | `content` | 4 |
| travel | `content` | 2 |
| **Fashion** | **`creator_category_fallback`** | 1 |
| **Entertainment** | **`creator_category_fallback`** | 1 |
| photography / business / sports | `content` | 1 masing-masing |

**Status: CONFIRMED + temuan baru.** Vocabulary-nya memang 18 `interest_key`
(huruf kecil), **bukan** 87 node L3 Excel — sesuai audit lama. Tapi ada
**inkonsistensi casing dan vocabulary dalam satu kolom**: baris ber-source
`content` memakai interest_key huruf kecil, baris ber-source
`creator_category_fallback` memakai `taxonomy_key` huruf kapital
(`Fashion`, `Entertainment`). Satu kolom, dua kosakata.

**`creator_age_band`** (27 terisi) — migration 043 + 044 bekerja:

| Band | `creator_age_source` | Confidence | Jumlah |
|---|---|---|---:|
| 18-24 | `roster_ktp` | high | 4 |
| 25-34 | `roster_ktp` | high | 16 |
| 25-34 | `bio_self_declared` | high | 1 |
| 35-44 | `roster_ktp` | high | 4 |
| 35-44 | `bio_self_declared` | high | 1 |
| 45+ | `roster_ktp` | high | 1 |

**Status: CONFIRMED** — 4 dari 5 band muncul (13-17 belum ada), semuanya
confidence `high`, dan `roster_ktp` (migration 044) terpakai untuk 25 dari 27.
Band-nya **persis** `taksonomi_kol.Demografi`.

**Label klasifikasi lain:**

| Kolom | Nilai nyata |
|---|---|
| `growth_class` | `Low Growth` 18 · `Negative Growth` 7 — **tidak ada High/Medium** |
| `monitoring_priority` | `Low` 699 · `Medium` 166 · `High` 147 (total 1.012) |
| `performance_stability` | `High Stability` 9 · `Medium Stability` 2 |
| `rising_creator` | `false` 25 · NULL 1.953 — **tidak ada satu pun `true`** |

**Status `rising_creator`: CONFIRMED** — audit lama menyebut "followers_growth
maks 0,917% vs rule ≥5,5%", jadi nol kreator rising. Terbukti.

---

## 9. VERIFIKASI #9 — sumber "What Matters Most" / Performance Quality / Brand Safety

Sapuan global 101 tabel untuk tiap konsep:

| # | Kriteria | Kolom dicari | Hasil | Status |
|---:|---|---|---|---|
| 1 | Strong Engagement | ER | `kol_directory.engagement_rate` 1.736 · `feature.*_engagement_analysis.engagement_rate` **38** · `campaign_kols.engagement_rate` 0 · `campaign_content_performance.engagement_rate` 0 | **CONFIRMED** |
| 2 | High Audience Quality | `audience_quality*` | `feature.*.audience_quality_score` **27 terisi** + `audience_quality_tier` 27 · `kol_profile_card` idem | **CHANGED** — dulu "NEED DEFINITION", sekarang terisi |
| 3 | Consistent Performance | `consisten%`, `cadence%` | **NOT FOUND — 0 kolom.** Proksi: `performance_stability` 11 · `post_frequency_*` 26–49 | **CONFIRMED MISSING** |
| 4 | Strong Company/Community | `community%` | **NOT FOUND — 0 kolom di seluruh DB** | **CONFIRMED MISSING** |
| 5 | High Reach | `reach%` | `feature.*_audience_analysis.avg_reach` **0 terisi** · `feature.ig_post_analysis.reach` · `l1_silver.unified_post.reach` **0 dari 503** · `campaign_kols.reach` 0 · `campaign_content_performance.reach` 0 | **CONFIRMED MISSING (data)** |
| 6 | Content Quality | `content_quality%` | **NOT FOUND — 0 kolom** | **CONFIRMED MISSING** |
| 7 | Brand Safety | `safety%`, `risk%`, `saturation%` | **NOT FOUND — 0 kolom** untuk ketiganya. Proksi 4 input: `authenticity_score` 27 ✅ · `follower_quality_score` 27 ✅ · `verified_status` 931 ✅ · `paid_ratio` 48 ✅ | **CHANGED** — keempat input proksi sekarang terisi |

**Satu-satunya kemunculan `competitor`:** `public.brand.is_competitor_tracked`
(boolean) — menandai **brand pesaing**, bukan saturasi kompetitor per KOL.
**CONFIRMED** sesuai peringatan audit lama.

**Implikasi desain:** dari 7 kriteria, **2 naik status** (Audience Quality dan
Brand Safety-proksi kini punya data nyata), **4 tetap MISSING** (Consistency,
Community, Reach, Content Quality), **1 tetap PARTIAL** (Engagement). Kesimpulan
§7.3 audit lama — bahwa 6 dari 7 memetakan ke komponen yang bobotnya cuma 10% —
**tidak berubah**, dan **H17 tetap terbuka**.

---

## 10. VERIFIKASI #10 — Median Views & View-to-Follower Ratio

**Temuan audit lama:** Excel `Discovery_Filters` menandai `Median Views` sebagai
*"NEW — belum ada agregat median"* dan `View-to-Follower Ratio` sebagai
*"PARTIAL"*; audit gue menduga migration 036 sudah menambahkannya tapi belum bisa
memastikan migration-nya sudah jalan.

**Hasil SELECT:**

| Tabel | Baris | `avg_views` | **`median_views`** | **`view_to_follower_ratio`** | `like_to_view_ratio` |
|---|---:|---:|---:|---:|---:|
| `feature.ig_engagement_analysis` | 44 | 19 | **19** | **12** | 19 |
| `feature.tt_engagement_analysis` | 11 | 11 | **11** | **10** | 11 |
| `l2_gold.kol_profile_card` | 1.978 | 30 | **30** | **22** | 30 |

**Status: CHANGED — keduanya ADA dan sudah BERISI.**

Jadi status "NEW / belum ada kolom" di Excel memang **sudah kedaluwarsa**, persis
seperti dugaan audit lama. Ini mengonfirmasi peringatan di §2.3.4: beberapa
status Excel lebih tua dari migration dan tidak boleh dipakai sebagai backlog
tanpa dicek ulang.

**Implikasi desain:** preset ranking `Highest Median Views` (Lookup §10 #3) dan
`Highest View-to-Follower Ratio` (#8) bisa langsung dibangun untuk 30 dan 22
kreator — naik dari "tidak bisa sama sekali" menjadi "bisa, cakupan kecil".

---

## 11. VERIFIKASI #11 — yang sebelumnya dinyatakan tidak ada atau kosong

### 11.1 Tabel yang dicari — NOT FOUND semua

| Yang dicari | Hasil |
|---|---|
| `%discover%` (mis. `discover_creator_links`) | **NOT FOUND** |
| `%sub_categor%` / `%subcategor%` | **NOT FOUND** |
| `%style%` | **NOT FOUND** |
| `%personality%` | **NOT FOUND** |
| `%match_config%` | **NOT FOUND** |
| `%taxonomy%` (sebagai tabel) | **NOT FOUND** |
| `%city%` (master kota) | **NOT FOUND** |
| `%niche%` | **NOT FOUND** |
| `%industry%` | **NOT FOUND** |
| `%vocab%` | **NOT FOUND** |
| `%exclusion%` | **NOT FOUND** |
| `%brands%` (plural) | **NOT FOUND** |

**`discover_creator_links` tidak ada di `kol`** → **H18 terjawab sebagian**:
tabel itu memang bukan milik DB ini. Ia ada di DB aplikasi (seri migration 053),
yang bukan `kol`.

### 11.2 Kolom yang dicari — NOT FOUND semua

`style` · `personality` · `persona` · `tone`\* · `brand_value` · `positioning` ·
`community` · `consisten` · `cadence` · `safety` · `risk` · `saturation` ·
`content_quality` · `intent` · `sub_categ` · `subcateg` · `niche` · `industry` ·
`opportunity` · `hidden`\*\* · `trending` · `brand_match` · `match_score` ·
`brand_fit`\*\*\* · `exclu`

\* `tone` hanya cocok dengan `miles**tone**s_completed` — positif palsu.
\*\* `hidden` hanya cocok dengan `instagram_comment.hidden` — bukan Hidden Gem.
\*\*\* `brand_fit` sebagai nama kolom tidak ada; yang ada
`feature.brand_fit_analysis.partnership_score`.

**Status: CONFIRMED** untuk seluruh 25 konsep. Kesimpulan §9.4 audit lama
(MISSING 21 item) **tidak berubah**.

### 11.3 Tabel yang dinyatakan kosong — hasil `COUNT(*)` eksak

| Tabel | Audit lama | **Sekarang** | Status |
|---|---:|---:|---|
| `public.brand` | 0 | **0** | CONFIRMED |
| `public.brand_members` | — | **0** | — |
| `public.audit_log` | 0 | **0** | CONFIRMED |
| `public.scheduler_config` | 0 | **0** | CONFIRMED |
| `feature.brand_fit_analysis` | 0 | **0** | CONFIRMED |
| `feature.ig_comments_analysis` | 0 | **0** | CONFIRMED |
| `feature.tt_comments_analysis` | 0 | **0** | CONFIRMED |
| `l1_silver.unified_comment` | 0 | **0** | CONFIRMED |
| `l1_silver.unified_rate_card` | 0 | **0** | CONFIRMED |
| `l1_silver.unified_follower` | 0 | **2.568** | **CHANGED** |
| `l1_silver.unified_post` | 221 | **503** | **CHANGED** |
| `l1_silver.unified_profile` | ~1.994 | **2.009** | CHANGED (minor) |
| `l2_gold.kol_profile_card` | **0** | **1.978** | **CHANGED** |
| `l2_gold.post_metric` | **0** | **503** | **CHANGED** |
| `l2_gold.content_format_daily` | **0** | **325** | **CHANGED** |
| `l2_gold.audience_demographics_daily` | **0** | **113** | **CHANGED** |
| `l2_gold.audience_geo_daily` | — | **196** | — |
| `l2_gold.audience_interest_daily` | "NO SOURCE DATA" | **229** | **CHANGED** |
| `l2_gold.kol_metric_daily` | 160 | **306** | CHANGED |
| `l2_gold.kol_metric_monthly` | 53 | **94** | CHANGED |
| `feature.ig_engagement_analysis` | 38 akun | **44** | CHANGED |
| `feature.tt_engagement_analysis` | — | **11** | — |
| `feature.ig_post_analysis` | 212 | **212** | CONFIRMED |
| `feature.tt_post_analysis` | — | **291** | — |
| `public.kol_categories` | 28 | **28** | CONFIRMED |
| `public.kol_tiers` | 5 | **5** | CONFIRMED |
| `public.platforms` | — | **2** | — |
| `public.agency_kol_accounts` | 7.719 | **7.431** | CHANGED |
| `public.kol_social_account` | 7.494 | **7.208** | CHANGED |
| `public.social_account` | — | **7.208** | — |

`l1_silver.unified_follower` = **2.568** baris, dan itu **persis** total
`audience_count` di `audience_demographics_daily` (2.568). Jadi seluruh inferensi
demografi audiens berdiri di atas 2.568 follower yang sudah di-scrape — dan itu
sebabnya umur hampir seluruhnya `unknown`.

### 11.4 Klaim spesifik yang diverifikasi ulang

| Klaim audit lama | Hasil SELECT | Status |
|---|---|---|
| `content_category` NULL di seluruh 212 baris | `ig_post_analysis` **0/212** · `tt_post_analysis` **0/291** | **CONFIRMED** (dan populasinya kini 503) |
| `unified_post.reach` NULL 0/221 | **0 terisi dari 503** | **CONFIRMED** |
| `shares`/`saved` IG kosong, TikTok saja | `unified_post`: shares 291, saved 291 — sama dengan jumlah baris TT · `ig_engagement_analysis.share_rate`/`save_rate` **0/44** · `tt` **11/11** | **CONFIRMED** |
| `feature.*_engagement_analysis.engagement_rate` hanya 38 akun | **28 (IG) + 10 (TT) = 38** | **CONFIRMED tepat** |
| `audience_interest_daily` didominasi `unknown` 85,2% | **86,3%** dari total `audience_count`; 19 `interest_key` distinct (18 nyata + `unknown`); 27 akun | **CONFIRMED** |
| `geo_level` menulis `city` untuk semua tebakan; Bali & Lampung sejajar Bandung | **4 level: `country` 27 akun · `city` 17 akun · `province` 10 akun · `island` 2 akun.** Bali & Lampung sekarang `province`; Bandung/Jakarta/Surabaya `city` | **CHANGED — sudah diperbaiki** |
| `agency_kol_accounts.campaign_tag` dan `notes` kosong, `status` seragam | `campaign_tag` **0** · `notes` **0** · `status` **1 nilai unik** · `is_active` true untuk 7.431/7.431 · `tier_id` **7.207** | **CONFIRMED tepat** (`tier_id` 7.207 sama persis) |
| `kol_tiers` batas hasil migration 033 | Nano 1.000–9.999 · Micro 10.000–49.999 · **Mid-tier 50.000–499.999** · **Macro 500.000–999.999** · Mega ≥1.000.000 | **CONFIRMED** |
| `platforms` = instagram + tiktok | 2 baris: `instagram`, `tiktok` | **CONFIRMED** |
| `audience_demographics_daily` hanya `{gender}` | **`{age, gender}`** — age 29 baris/27 akun, gender 84 baris/27 akun | **CHANGED** |

### 11.5 Umur audiens — CHANGED struktur, CONFIRMED fungsi

| `audience_type` | `dimension_key` | Baris | Akun | `sum(audience_count)` | `confidence` |
|---|---|---:|---:|---:|---|
| age | **`unknown`** | 28 | 27 | **2.567** | `inferred_low` |
| age | `18-24` | 1 | 1 | **1** | `inferred_high` |
| gender | `unknown` | 28 | 27 | 1.828 | `inferred_high` |
| gender | `female` | 28 | 27 | 374 | `inferred_low` |
| gender | `male` | 28 | 27 | 366 | `inferred_low`, `inferred_medium` |

**2.567 dari 2.568 audiens ber-umur `unknown`. Satu follower saja** di seluruh DB
punya band umur diketahui.

**Status: CHANGED** (tabel tidak lagi 0 baris, dan `audience_type='age'` sudah
ada) **tapi CONFIRMED secara fungsi** (umur audiens tetap tidak bisa dipakai).

**Implikasi desain:** `Age Match` = 25% dari `Target Audience Relevance` (komponen
terberat, 30%) **tetap tidak bisa dihitung**. Yang berubah: rumahnya sudah
terbukti bekerja, jadi hambatan murni cakupan sumber — bukan schema.

**Catatan tambahan:** kolom `confidence` di `audience_demographics_daily` dan
`audience_geo_daily` sudah membawa nilai `inferred_low`/`_medium`/`_high`. Jadi
konsep *basis/provenance* yang §3.3 audit lama usulkan sebagai kolom baru
`category_basis` **sudah punya preseden di DB** — polanya bisa diikuti, bukan
ditemukan dari nol.

---

## 12. DAFTAR PERUBAHAN — ringkas, untuk review

### 12.1 CHANGED — 18 temuan

| # | Temuan audit lama | Hasil SELECT 2026-09-13 | Implikasi desain |
|---:|---|---|---|
| C1 | "EMV: NO MATCH secara definisi, tidak ada kolom" | **4 kolom `emv`**: `feature.ig/tt_audience_analysis`, `campaign_kols`, `campaign_content_performance` | Rumah EMV ada di 2 grain. **Tidak perlu kolom EMV baru.** H1 (definisi + CPM + multiplier) tetap terbuka |
| C2 | "H15: grain metric biaya belum diputuskan" | `campaign_kols` punya `deal_price`, `currency`, `reach`, `impressions`, `total_engagement`, `engagement_rate`, `roas`, `performance_score` | **Skema sudah menjawab H15**: biaya campaign punya rumah sendiri, terpisah dari rate-card per-KOL. CPV/CPE/CPM versi campaign bisa dihitung tanpa kolom baru |
| C3 | "±15 tabel campaign, semuanya 0 baris" | 13 dari 14 kosong; **`campaign_stages` = 12 baris** master workflow | DB punya model status campaign 12 tahap ber-`owner_role`. Excel tidak punya konsep ini → **DB jadi acuan status campaign** |
| C4 | "migration 037–044 belum tentu jalan" | **Kedelapan sudah jalan** — dibuktikan 71 kolom `kol_profile_card` + 21 kolom `ig_audience_analysis` | Item READY #4–#7 audit lama **valid**, bukan asumsi |
| C5 | "`kol_profile_card` EMPTY 0 baris (E1)" | **1.978 baris / 71 kolom** | Tabel kartu sudah jadi sumber serving nyata |
| C6 | "`audience_demographics_daily` 0 baris, hanya `{gender}`" | **113 baris**; `audience_type` = `{age, gender}`; age 29 baris / 27 akun | Struktur age terbukti bekerja. **Tapi 2.567/2.568 = `unknown`** → Age Match tetap tak terhitung |
| C7 | "`age_gender_breakdown` NULL di 27 baris" | **Terisi 27/27**, tapi semua bucket umur = 0, semua di `unknown` | **Jangan salah baca sebagai "umur sudah ada"** |
| C8 | "`audience_quality_score`/`authenticity_score`/`follower_quality_score` NEED DEFINITION" | **Terisi 27/27 (16 IG + 11 TT)**, nilai nyata 65–94 | Algoritma sudah diimplementasikan. **Brand Safety versi integrity screen kini 4-dari-4 input terisi**, naik dari 3-dari-4 |
| C9 | "`median_views` & `view_to_follower_ratio` — Excel bilang NEW/belum ada" | **Keduanya ADA dan BERISI**: median_views 30, v2f 22 | Preset `Highest Median Views` & `Highest V2F` bisa dibangun. **Status Excel terbukti kedaluwarsa** |
| C10 | "`geo_level` menulis `city` untuk semua tebakan" | **4 level**: country/province/city/island. Bali & Lampung kini `province` | Perbaikan `audience_inference.tingkat_geo()` sudah live. Audience Region punya sumber sah |
| C11 | "`unified_post` 221 baris" | **503 baris** | Basis post naik 2,3×; `views` 397, `shares`/`saved` 291 |
| C12 | "`l2_gold.post_metric` 0 baris" | **503 baris** | Average Views / Share Rate / Save Rate punya sumber nyata |
| C13 | "`l2_gold.content_format_daily` 0 baris" | **325 baris** | Content Format punya sumber |
| C14 | "`audience_interest_daily` NO SOURCE DATA" | **229 baris**, 19 key, 27 akun | Interest punya sumber, dengan 86,3% `unknown` |
| C15 | "`unified_follower` 0 baris" | **2.568 baris** | Ini fondasi seluruh inferensi audiens — dan penyebab umur `unknown` |
| C16 | "`kol_directory` 7.718 baris, 6.991 aktif" | **7.432 baris, 7.432 aktif (100%)** | Populasi berubah. Semua rasio cakupan harus dihitung ulang atas 7.432 |
| C17 | "`kol_metric_daily` 160 / `monthly` 53" | **306 / 94** | Deret waktu tumbuh; 90D Growth & Recent Performance masih tipis |
| C18 | "`campaign_brief.cta` belum terverifikasi" | **`cta` ada** (varchar) | Field CTA Excel punya rumah |

### 12.2 NOT FOUND — 9 temuan

| # | Dicari | Hasil | Implikasi |
|---:|---|---|---|
| N1 | Database **`tsdb`** | **Tidak ada** di 21 database `10.100.14.216` | **H2 berubah bentuk**: `tsdb.public.brands` tak bisa diverifikasi dari host ini. Kandidat `autometric_v2` — tidak gue sentuh |
| N2 | `discover_creator_links` | Tidak ada di `kol` | **H18 terjawab**: bukan DB ini |
| N3 | `kol_sub_categories` / kolom `sub_category_ids` | Tidak ada | §3.5 (master L2 diperlukan) **tetap berlaku** |
| N4 | Tabel/kolom `style`, `personality`, `persona`, `tone`, `positioning`, `brand_value` | Tidak ada satu pun | §5 audit lama **tidak berubah** |
| N5 | Kolom `cpm`, `cpv`, `multiplier`, `benchmark`, `coefficient` | Tidak ada satu pun di 101 tabel | **H1 tetap terbuka** — konstanta EMV memang tidak ada |
| N6 | Kolom `community`, `consisten`, `cadence` | Tidak ada | Kriteria #3 & #4 "What Matters Most" tetap MISSING |
| N7 | Kolom `safety`, `risk`, `saturation` | Tidak ada | Brand Safety sesungguhnya tetap MISSING; `brand.is_competitor_tracked` bukan saturasi per-KOL |
| N8 | Kolom `content_quality`, `intent`, `opportunity`, `trending`, `brand_match`, `match_score` | Tidak ada | Seluruh output `Matching_Engine` tetap tanpa rumah |
| N9 | `match_config` / `taxonomy` / `city` / `niche` / `industry` / `vocab` / `exclusion` sebagai tabel | Tidak ada | §3.5 (`match_config`) **tetap jadi rekomendasi kuat** |

### 12.3 CONFIRMED — 31 temuan (ringkas)

`public.brand` 11 kolom / 0 baris · `brand_fit_analysis` 11 kolom / 0 baris /
grain `UNIQUE(agency_kol_account_id, brand_id)` · `avg_reach` 0 terisi ·
`cpe` 0 terisi · `emv` 0 terisi · `unified_rate_card` 0 baris ·
`rate_card_min_fee` 0 dari 1.978 · `unified_comment` 0 baris ·
`ig/tt_comments_analysis` 0 baris · `content_category` 0 terisi dari 503 ·
`unified_post.reach` 0 terisi dari 503 · `creator_city` 0 terisi ·
`refresh_tier` 100% NULL · `directory_status` 1 nilai · verified 455 ·
ER 1.736 (23,4%) · bio 902 (12,1%) · kategori 4.002 (53,8%) ·
`kol_categories` 28 baris identik baris-per-baris dengan E3 §11a ·
9 canonical key · 6 key NULL · **Tech 4 kreator** · Lifestyle+Beauty 93,3% ·
multi-kategori 1.130 · maks 5 kategori (1 kreator) · `kol_tiers` batas mig 033 ·
`platforms` 2 baris · `agency_kol_accounts` `campaign_tag` 0 / `notes` 0 /
`status` 1 nilai / `tier_id` 7.207 · share/save rate IG 0 & TT 11 ·
`feature.*_engagement_analysis.engagement_rate` **38 akun tepat** ·
interest `unknown` 86,3% · `rising_creator` nol `true` · tidak ada view di DB.

---

## 13. TEMUAN BARU yang tidak ada di audit lama

| # | Temuan | Kenapa penting |
|---:|---|---|
| B1 | **`kol_directory.engagement_rate` punya outlier: max 223,41%** (min 0 · avg 2,83 · median 0,60) | `CAL_ER_TARGET`=6 akan memberi skor 100 pada nilai yang jelas bukan ER nyata. **Normalisasi Performance Quality perlu clamp atau pembersihan sumber lebih dulu** |
| B2 | **`kol_directory.followers_count` bertipe `integer`, bukan `bigint`** | Nilai maks sekarang 685.896.635 — aman, tapi plafon int4 (2,1 miliar) perlu diketahui. `kol_profile_card.followers_count` sudah `bigint` → **dua tipe untuk satu gagasan** |
| B3 | **`kol_directory` punya `category_id` (uuid) DAN `category_ids` (array)**, keduanya terisi 4.002 | Kandidat duplikasi. Perlu dipastikan mana yang jadi acuan sebelum join apa pun dibangun |
| B4 | **`content_topic` memuat dua kosakata dalam satu kolom** — interest_key huruf kecil (`religion`, `fitness`) saat `source='content'`, `taxonomy_key` huruf kapital (`Fashion`, `Entertainment`) saat `source='creator_category_fallback'` | Query `WHERE content_topic='fashion'` akan melewatkan baris `Fashion`. **Perlu normalisasi casing atau pemisahan kolom** |
| B5 | **Konsep provenance sudah ada di DB di 3 tempat**: `audience_demographics_daily.confidence` & `audience_geo_daily.confidence` (`inferred_low/medium/high`) · `interest_source` (`audience`/`content_inferred`) · `content_topic_source` (`content`/`creator_category_fallback`) · `campaign_content_performance.source`+`raw_ref_table`+`raw_ref_id`+`is_final` | Usulan `category_basis` di §3.3 audit lama **bukan pola baru** — ia mengikuti preseden yang sudah dipakai. Memperkuat rekomendasi, dan sebaiknya **pakai nama/nilai yang konsisten dengan yang sudah ada**, bukan vocabulary ketiga |
| B6 | **`brand_fit_analysis` ber-FK ke `brand(id)`** | Tidak ada satu baris hasil Brand Match bisa ditulis **sampai `public.brand` terisi**. Jadi mengisi brand adalah prasyarat teknis, bukan cuma prasyarat bisnis |
| B7 | **`growth_class` cuma menghasilkan `Low Growth` (18) dan `Negative Growth` (7)** | Tidak ada satu kreator pun High/Medium Growth. Filter growth akan terlihat bekerja tapi tidak membedakan apa pun di ujung atas |
| B8 | **`campaign_content_performance` bergrain per-deliverable per-`snapshot_date` dengan `delta_views`/`delta_engagement`** | Ini tabel **time-series**, bukan snapshot. Excel tidak punya konsep delta/snapshot sama sekali → model campaign performance DB lebih maju daripada Excel |
| B9 | **`reltuples = -1` untuk hampir seluruh tabel `public`** | Tabel-tabel itu belum pernah di-`ANALYZE`. Planner jalan tanpa statistik — relevan untuk performa query nanti, dan artinya angka baris apa pun dari `pg_class` tidak bisa dipercaya |

---

## 14. DAMPAK KE GAP LIST §9 AUDIT LAMA

| Status lama | Jumlah lama | Perubahan | Jumlah baru |
|---|---:|---|---:|
| READY | 12 | **+3** — `median_views`/`v2f` terbukti berisi (C9) · Brand Safety integrity screen 4-dari-4 input (C8) · `campaign_stages` master 12 tahap (C3) | **15** |
| PARTIAL | 17 | **−2** naik ke READY, **+2** turun dari MISSING (Audience Quality punya data; umur punya struktur) | **17** |
| HOLD | **19** | **−2 terjawab** (H15 oleh C2 · H18 oleh N2) · **1 berubah bentuk** (H2 → `tsdb` tidak ada di host ini) · **+4 baru** dari B1, B3, B4, B6 | **21** |
| MISSING | 21 | **−3** (umur: struktur ada · audience quality: terisi · reach campaign: kolom ada) | **18** |

**Empat HOLD baru:**

| # | Keputusan | Dari |
|---|---|---|
| **H20** | Outlier ER sampai 223,41% — clamp, buang, atau perbaiki sumbernya? | B1 |
| **H21** | `category_id` vs `category_ids` — mana acuan? | B3 |
| **H22** | `content_topic` dua kosakata dalam satu kolom — normalisasi casing atau pisah kolom? | B4 |
| **H23** | Tipe `followers_count`: `integer` di `kol_directory` vs `bigint` di `kol_profile_card` | B2 |

**Dua HOLD yang terjawab:**
- **H15** (grain metric biaya) → skema sudah memisahkan: rate-card per-KOL vs
  `deal_price`/`emv`/`roas` per campaign × KOL.
- **H18** (`discover_creator_links` di DB mana) → bukan `kol`.

**Satu HOLD yang berubah bentuk:**
- **H2** (`kol.public.brand` vs `tsdb.public.brands`) → `tsdb` tidak ada di
  `10.100.14.216`. Pertanyaannya sekarang: **di host mana `tsdb` itu, atau apakah
  yang dimaksud `autometric_v2`?** Sampai itu terjawab, `kol.public.brand`
  adalah satu-satunya tabel brand yang terbukti ada.

---

## 15. STATUS SESI

| | |
|---|---|
| Query dijalankan | **~30 `SELECT`**, seluruhnya read-only |
| INSERT / UPDATE / DELETE | **0** |
| DDL (CREATE/ALTER/DROP/COMMENT) | **0** |
| Migration dibuat | **0** |
| Data Excel masuk DB | **0** |
| Database disentuh | **`kol` saja.** `tsdb`/`autometric_v2` **tidak** dibuka |
| Sesi Postgres | `transaction_read_only = on` sepanjang sesi |
| File ditulis | `docs/KOL_DB_VERIFICATION_TAHAP0.md` (dokumen ini) |

**Tahap 0 selesai. Menunggu review lo sebelum lanjut ke desain atau migration.**
