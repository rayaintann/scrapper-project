# AUDIT & MATCHING — 3 Excel × Database `kol`

**Tanggal audit:** 13 September 2026
**Sifat:** READ-ONLY. Tidak ada INSERT/UPDATE/DELETE, tidak ada migration,
tidak ada tabel/kolom baru, tidak ada data Excel yang dimasukkan ke DB.
**Sumber Excel:** `docs/taksonomi_kol.xlsx` (7 sheet) ·
`docs/brand_match_master.xlsx` (38 sheet) · `docs/brand_style_personality.xlsx`
(6 sheet). **Total 51 sheet, seluruhnya dibaca.**

> ## ⚠️ REVISI — 13 September 2026, 00:22 UTC
>
> Seluruh angka DB di dokumen ini berasal dari sumber turunan (E1/E2/E3) karena
> saat ditulis server `kol` tidak bisa dijangkau. **Verifikasi langsung sudah
> dilakukan** — hasilnya di **`KOL_DB_VERIFICATION_TAHAP0.md`**, dan dokumen itu
> **menggantikan setiap angka DB di sini**.
>
> **18 temuan CHANGED.** Yang paling mengubah desain:
> 1. Kolom **`emv` ADA di 4 tempat**, dua di antaranya bergrain campaign
>    (`campaign_kols`, `campaign_content_performance`) — §4.1 di bawah keliru
>    menyimpulkan "tidak ada kolom". Yang tetap benar: konstanta CPM/multiplier
>    memang tidak ada.
> 2. **`campaign_kols` punya 36 kolom** termasuk `deal_price`, `reach`,
>    `impressions`, `total_engagement`, `roas`, `performance_score` → **H15
>    terjawab** oleh skema.
> 3. **Migration 036–044 semua sudah jalan**; `l2_gold.kol_profile_card`
>    **1.978 baris / 71 kolom**, bukan 0.
> 4. **`median_views` & `view_to_follower_ratio` ADA dan berisi** — status "NEW"
>    di Excel memang kedaluwarsa.
> 5. **`tsdb` tidak ada** di `10.100.14.216` → H2 berubah bentuk.
>
> Bagian yang **tidak berubah**: §5 (Style/Personality nol representasi),
> §7 (7 kriteria tidak berasal dari Excel ini), §8 (tiga taxonomy bertabrakan),
> dan seluruh rekomendasi "jangan bikin tabel baru".

---

## 0. METODE DAN KETERBATASAN — baca ini dulu

### 0.1 Koneksi ke DB `kol` GAGAL pada sesi ini

```
PG_HOST = 10.100.14.216 : 5432   -> Connection timed out (10060)
localhost : 5432                 -> port terbuka, tapi kredensial .env ditolak
                                    (instance Postgres lain, bukan kol)
```

Server `kol` ada di jaringan kantor dan **butuh VPN**. Karena itu audit ini
**tidak memuat `SELECT` langsung** — tidak ada row count dan sample value yang
gue ambil sendiri sesi ini.

### 0.2 Sumber bukti DB yang dipakai sebagai pengganti

Ketiganya *bukan* tebakan; ketiganya turunan langsung dari DB `kol`:

| # | Sumber | Kenapa sah dipakai | Batasnya |
|---|---|---|---|
| **E1** | `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md` (2.903 baris) | Kamus kolom + row count per tabel, hasil audit langsung ke `kol` | Snapshot 24 Agu 2026 |
| **E2** | `migrations/001–044/*.sql` | DDL authoritative repo ini; 037–044 belum ter-commit | Tidak menjamin sudah dijalankan di server |
| **E3** | `brand_match_master.xlsx` sheet `CMP_*` dan `DIST_*` | **Sheet-nya sendiri hasil baca `10.100.14.216/kol`** — CMP 10 Sep 2026 04:48 UTC (24 akun), DIST 10 Sep 2026 06:25 UTC (6.991 akun). Menyebut nama tabel + kolom + row count | Hanya menyentuh tabel yang dibacanya |

Setiap baris di laporan ini yang menyebut kondisi DB gue tandai sumbernya.
**Semua angka DB wajib di-reverify dengan VPN aktif sebelum dipakai untuk
keputusan.**

### 0.3 Dua temuan struktural yang mengubah cara baca seluruh laporan

**(a) Ada DUA repo dan (kemungkinan) DUA database.**
Repo ini (`scrapper-project`) Python-only — tidak ada `package.json`, tidak ada
`scripts/`, tidak ada `.mjs`. Tapi Excel berkali-kali merujuk
`scripts/brand-match/vocabulary.mjs`, `scripts/brand-match/scoring.mjs`,
`@/lib/discover/vocab`, `@/lib/discover/creatorMatch`, dan
**`discover_creator_links (migrasi 053)`** — sedangkan migration repo ini baru
sampai **044**. Artinya ada repo aplikasi Next.js terpisah dengan seri migration
sendiri. Beberapa "sumber DB" yang disebut Excel ada di sana, bukan di sini.

**(b) Excel tidak sepakat sendiri soal di mana BRAND disimpan.**

| Excel | Klaim | Isi |
|---|---|---|
| `brand_style_personality.xlsx` → Summary | `tsdb.public.brands.name` | 38 baris / 33 unik case-insensitive |
| `brand_match_master.xlsx` → CMP_Brand_Profile | `public.brand.name`, `.brand_keywords`, `.brand_hashtags` | — |
| E1 §16.10 (DB `kol`) | `public.brand` | **0 baris** |

`tsdb` ≠ `kol`. Ini **NEED PRODUCT DECISION**, bukan sesuatu yang boleh gue
putuskan — detail di §6.

---

## 1. EXECUTIVE SUMMARY

### 1.1 Vonis per file

| File | Sheet | Sifat isi | Vonis terhadap DB `kol` |
|---|---:|---|---|
| `taksonomi_kol.xlsx` | 7 | Reference/vocabulary murni. Tidak ada data KOL, tidak ada formula scoring kecuali 2 arketipe | **PARTIAL** — 4 dari 7 sheet sudah punya rumah kolom, 3 belum |
| `brand_match_master.xlsx` | 38 | Spesifikasi engine + hasil eksekusi atas data `kol` nyata | **PARTIAL/NO MATCH** — struktur input ada, *scoring layer*-nya belum ada sama sekali di DB |
| `brand_style_personality.xlsx` | 6 | Laporan audit ketersediaan Brand/Style/Personality | **NO MATCH untuk Style & Personality**, **DUPLICATE/OVERLAP untuk Brand** |

### 1.2 Yang SUDAH ADA di DB `kol`

| Konsep Excel | Rumah DB | Bukti |
|---|---|---|
| Follower Size Tier (5 tier) | `public.kol_tiers` (5 baris) | E1, migration 033 |
| Demografi — age band kreator `13-17…45+` | `l2_gold.kol_profile_card.creator_age_band` | migration 042 + **043 (persis 5 bucket yang sama)** |
| Demografi — audience age band | `l2_gold.audience_demographics_daily.dimension_key` | migration 043 |
| Demografi — gender kreator/audience | `feature.*_audience_analysis.female_pct/male_pct/gender_known_pct` | migration 037 |
| Content Format | `feature.*_engagement_analysis.format_dominant` | migration 039 |
| Posting Cadence | `post_frequency_monthly/daily/count/reliability` + `observation_days` | migration 037, 038 |
| Industry (sisi kreator) | `public.kol_categories` + `taxonomy_key` | migration 029, E3 §11a |
| Semua HARD FILTER "DONE" (14 filter) | `kol_directory`, `kol_tiers`, `platforms`, `agency_kol_accounts` | E3 Discovery_Filters |
| Struktur campaign (±15 tabel) | `public.campaigns`, `campaign_kols`, `campaign_brief`, `campaign_content_performance`, `campaign_tracking_jobs`, dst. | E1, E2-plan |
| Rumah kolom Brand Fit | `feature.brand_fit_analysis` (11 kolom, grain KOL × brand) | E1 §16.8 |
| Rumah kolom EMV / CPE | `feature.ig/tt_audience_analysis.emv` / `.cpe` | E1 §1.3, §5.2 |

### 1.3 Yang PARTIAL

| Konsep | Kenapa partial |
|---|---|
| Industry taxonomy | DB punya **28 baris mentah / 9 canonical key**; Excel punya **14 L1 / 42 L2 / 87 L3** dan **12 industry / 24 niche brand**. Beda ukuran, beda sumbu, dan Excel sendiri hanya memetakan **5 dari 28** baris DB |
| Campaign | Seluruh ±15 tabel **0 baris**. Struktur ada, isi tidak ada |
| Brand Fit | Tabel ada, **0 baris**, algoritma belum didefinisikan, dan `public.brand` juga 0 baris |
| CPE | Kolom ada; pembilang (`unified_rate_card.fee`) **0 baris** menurut audit terbaru |
| Performance Archetype | Reach Driver & Engagement Driver punya semua input; Niche Authority **tidak** (butuh sentiment) |

### 1.4 Yang BENAR-BENAR BELUM ADA

| Konsep | Status |
|---|---|
| **Style** (10 Content + 8 Communication) | **NO MATCH** — tidak ada kolom/tabel di mana pun; hardcode di `vocabulary.mjs` repo lain |
| **Personality** (12 Creator + 10 Brand + 8 Tone) | **NO MATCH** — idem |
| Sub Category (L2) | **NO MATCH** — tidak ada `kol_sub_categories`, tidak ada `sub_category_ids` |
| Content Topic (L3, 87 node) | **NO MATCH sebagai taxonomy** — `content_topic` migration 039 memakai kosakata `audience_inference.INTEREST` (18 key), **bukan** 87 node Excel |
| Brand Niche (24) + crosswalk (183 baris) | **NO MATCH** |
| Sentiment Archetype | **NO MATCH** — `*_comments_analysis` 0 baris |
| CPV, CPM, Cost Efficiency, Estimated ROI, Opportunity, Hidden Gem, Competitor Saturation, Purchase Intent, Excluded-creator list | **NO MATCH** — tidak ada kolom |
| **Seluruh scoring layer Brand Match** (6 komponen, 22 sub-skor, 9 matriks, 30 preset) | **NO MATCH** — tidak ada satu pun konstanta bobot/matriks/band tersimpan di DB |
| **EMV** | **NO MATCH secara definisi** — lihat §4, ini temuan paling penting |

---

## 2. SHEET-BY-SHEET MAPPING

Legenda status: **MATCH** · **PARTIAL** · **NO MATCH** · **DUPLICATE/OVERLAP** ·
**NEED PRODUCT DECISION (NPD)**. Kolom *Evidence* menunjuk sumber di §0.2.

### 2.1 `taksonomi_kol.xlsx` — 7 sheet

Seluruh 7 sheet bersifat **master/reference**. Tidak ada satu pun data KOL,
brand, atau campaign di file ini.

| File | Sheet | Excel Field | DB Schema.Table.Column | Status | Evidence | Notes |
|---|---|---|---|---|---|---|
| taksonomi_kol | Demografi | `kol_age` — 13-17/18-24/25-34/35-44/45+ | `l2_gold.kol_profile_card.creator_age_band` varchar(10) | **MATCH** | E2 mig 042+043 | 043 merapikan jadi **persis 5 bucket yang sama**. Pendamping: `creator_age`, `creator_birth_year`, `creator_age_source` (bio_self_declared / manual / roster_ktp), `creator_age_confidence` |
| taksonomi_kol | Demografi | `kol_gender` — Female/Male/Other | — tidak ada kolom gender kreator | **NO MATCH** | E1, E2 | Yang ada hanya gender **audience**. Nilai "Other" tidak punya padanan di mana pun |
| taksonomi_kol | Demografi | `kol_city` — "Master city list" | `public.kol_directory.creator_city` | **PARTIAL** | E3 CMP_Validation r64 | Kolom ada, **0% terisi**; dan **tidak ada master city table**. Excel menulis "Master city list" tanpa melampirkan listnya |
| taksonomi_kol | Demografi | `kol_content_language` — Indonesian/English/Regional/Mixed | — | **NO MATCH** | E1 | Tidak ada kolom bahasa di seluruh DB. CMP_README r32 justru menyebut dampaknya: sebagian kreator caption berbahasa Inggris/Spanyol sehingga keyword Indonesia tidak pernah kena |
| taksonomi_kol | Demografi | `audience_age` — 5 band | `l2_gold.audience_demographics_daily.dimension_key` (audience_type='age') | **PARTIAL** | E3 CMP_Validation r58 | Band cocok setelah mig 043, tapi **0 baris**; `SELECT DISTINCT audience_type` hanya mengembalikan `{gender}` |
| taksonomi_kol | Demografi | `audience_gender` — Female/Male | `audience_demographics_daily` (gender) + `feature.*_audience_analysis.female_pct` / `male_pct` / `gender_known_pct` | **PARTIAL** | E2 mig 037, E3 | 23 kreator (0,30%). Catatan penting: mig 037 **mengeluarkan `unknown` dari penyebut**; Excel tidak menyatakan perlakuan `unknown` sama sekali |
| taksonomi_kol | Demografi | `audience_city` — top 30 array | `l2_gold.audience_geo_daily` (geo_level='city') | **PARTIAL** | E3 Discovery_Filters r20 | 15 kreator usable; `geo_level` salah level untuk 9 dari 33 key (header mig 039) |
| taksonomi_kol | Industry | `Category` (10 nilai) + `Subcategory` (36 nilai) | `public.kol_categories.name` (28 baris) + `.taxonomy_key` (9 canonical) | **PARTIAL + DUPLICATE/OVERLAP** | E3 §11a | **Tiga taxonomy berbeda untuk satu gagasan** — lihat §8. Sheet ini BUKAN taxonomy yang sama dengan `brand_match_master.Taxonomy` |
| taksonomi_kol | Follower Size Tier | Nano/Micro/Mid-tier/Macro/Mega + batas follower | `public.kol_tiers` (5 baris) | **PARTIAL — batas berbeda** | E2 mig 033, E3 §3 | **Tiga versi batas yang tidak sama** — tabel di bawah |
| taksonomi_kol | Performance Archetype | Reach Driver · `View Rate = Avg Views per Post / Follower Count` | `feature.*_engagement_analysis.view_to_follower_ratio` | **MATCH (formula)** | E2 mig 036 | Rumus identik. Label arketipe-nya sendiri belum punya kolom |
| taksonomi_kol | Performance Archetype | Engagement Driver · `ER = (Avg Likes + Avg Comments + Avg Shares) / Followers` | `public.kol_directory.engagement_rate` | **PARTIAL — formula BEDA** | E1 §5.1 | DB memakai `AVG(likes + comments) ÷ followers × 100` — **tanpa shares**. Ini beda definisi, bukan beda coverage. **NPD** |
| taksonomi_kol | Performance Archetype | Niche Authority `= Category Consistency % × 0,6 + Positive Sentiment % × 0,4` | — | **NO MATCH** | E1 §16 | Kedua input tidak ada: tidak ada kolom consistency kategori, dan `*_comments_analysis` 0 baris. Excel sendiri menandai 0,6/0,4 sebagai *starting estimate, not empirically derived* → **NPD** |
| taksonomi_kol | Sentiment Archetype | Beloved/Fan Favorite · Backlash-Prone · Polarizing — aturan persentil **dalam tier** | `feature.ig/tt_comments_analysis.*` | **NO MATCH** | E1 §16.10 | 0 baris; `l1_silver.unified_comment` juga 0 baris. Aturan "kalau tidak memenuhi ambang mana pun, biarkan NULL" sudah eksplisit dan bisa dipakai apa adanya nanti |
| taksonomi_kol | Content Format | Short-video/Reels · Static Post/Carousel · Live Streaming · Long-form Video | `feature.*_engagement_analysis.format_dominant` varchar(16) | **PARTIAL — vocabulary BEDA** | E2 mig 039 | DB menormalkan ke **Video / Carousel / Image** (3 nilai). Excel punya **4 nilai** dan memisahkan Live Streaming + Long-form yang DB tidak punya → **NPD** |
| taksonomi_kol | Posting Cadence | Highly Active (harian) · Regular (mingguan) · Occasional (bulanan) · Dormant (>2 bulan) | `kol_profile_card.post_frequency_daily` / `_monthly` / `_count` / `_reliability`, `observation_days` | **PARTIAL — label belum ada** | E2 mig 037+038, `metrics_thresholds.py` | Angkanya ada; **label 4-level Excel belum punya kolom**. `metrics_thresholds.py` hanya punya *reliability* High/Medium/Low (ambang 30 hari/10 post, 14 hari/5 post) — bukan cadence. Ambang "Dormant >2 bulan" tidak ada di kode → **NPD** |

**Tiga versi batas tier yang saling bertabrakan:**

| Tier | `taksonomi_kol` | `Lookup_Lists` §3 | `public.kol_tiers` (mig 033) |
|---|---|---|---|
| Nano | < 10K | 0 – 9.999 | 1.000 – 9.999 |
| Micro | 10K – 100K | 10.000 – 49.999 | 10.000 – 49.999 |
| Mid-tier | 100K – 500K | 50.000 – 99.999 | **50.000 – 499.999** |
| Macro | 500K – 1M | 100.000 – 999.999 | **500.000 – 999.999** |
| Mega | > 1M | ≥ 1.000.000 | ≥ 1.000.000 |

Ketiganya sepakat untuk Mega saja. `kol_tiers` sudah dirujuk
`agency_kol_accounts.tier_id` (7.207 baris terisi) — itu yang paling mahal
diubah. **NPD.**

### 2.2 `brand_style_personality.xlsx` — 6 sheet

File ini bukan spesifikasi; ia **laporan audit** atas pertanyaan "apakah Brand,
Style, Personality ada di DB". Jawabannya sudah tertulis di dalamnya sendiri.

| File | Sheet | Excel Field | DB Schema.Table.Column | Status | Evidence | Notes |
|---|---|---|---|---|---|---|
| brand_style_personality | Summary | Brand — "33 unik case-insensitive dari 38 baris" | `tsdb.public.brands.name` | **DUPLICATE/OVERLAP + NPD** | E1 §16.10 | Excel menunjuk **`tsdb`**, bukan `kol`. Di `kol`, `public.brand` = **0 baris**. Dua tabel brand di dua database |
| brand_style_personality | Summary | Style — 10 Content + 8 Communication | — | **NO MATCH** | E3 CMP_Validation r61 | "no column on kol_directory, kol_profile_card or any feature table" |
| brand_style_personality | Summary | Personality — 12 Creator + 10 Brand + 8 Tone | — | **NO MATCH** | E3 CMP_Validation r61 | idem |
| brand_style_personality | Brand List | 38 baris: `No`, `Brand`, `Posts`, `Catatan` | `tsdb.public.brands` | **DUPLICATE/OVERLAP** | file itu sendiri | **19 dari 38 adalah data test/kotor**: `tes ×5`, `TES`, `Tes ×2`, `tes1`, `tes2`, `tes3`, `TES123`, `e`, `h`, `j`, `ww`, `zj`, `demo`, `arces`. Brand nyata efektif ±17 (Paseo 694 post, MineralQUA 246, Nice 63, Fitbar 62, …) |
| brand_style_personality | Brand List | kolom `Posts` per brand | join brand ↔ post di `tsdb` | **NO MATCH di `kol`** | sheet Anomalies | Angka post ini dari `tsdb`, bukan dari `l1_silver.unified_post` (221 baris) |
| brand_style_personality | Style List | 18 nilai, 2 grup, `Count in DB` = **0** untuk seluruh baris | — | **NO MATCH** | sheet itu sendiri | Kolom `Source` menyebut `scripts/brand-match/vocabulary.mjs` — **repo lain**, bukan DB |
| brand_style_personality | Personality List | 30 nilai, 3 grup, `Count in DB` = **0** untuk seluruh baris | — | **NO MATCH** | sheet itu sendiri | `Professional`, `Educational`, `Premium` muncul di dua grup (Creator + Brand) — bukan duplikat, memang dua sumbu berbeda |
| brand_style_personality | DB vs Hardcode | Brand · Database · Available · **"Can support brand-level EMV/CPV"** | — | **NPD** | sheet itu sendiri | **Satu-satunya penyebutan EMV di seluruh 3 file — dan ia bukan definisi.** Lihat §4 |
| brand_style_personality | DB vs Hardcode | Style/Personality · Hardcoded · "Not DB-backed; Needs creator/brand assignment" | — | **NO MATCH** | sheet itu sendiri | Excel sendiri yang menyimpulkan |
| brand_style_personality | Anomalies | `unified_post.brand_id` **tidak berisi `brands.id`**; join harus lewat `social_accounts.id → brand_social_accounts → brands.id` | `tsdb` | **NPD — severity Critical** | sheet itu sendiri | Cacat integritas di `tsdb`. Tidak menyentuh `kol`, tapi memblokir agregasi per-brand apa pun |
| brand_style_personality | Anomalies | 6 akun / 528 post tidak ter-link | `tsdb` | **PARTIAL** | idem | Post bisa hilang dari agregasi per-brand |
| brand_style_personality | Anomalies | Duplicate brand: `tes ×5`, `Fibonacci ×2`, `Fitbar ×2`, `Giv Body Wash ×2` | `tsdb` | **PARTIAL** | idem | Harus dibereskan **sebelum** brand dipakai sebagai dimensi |
| brand_style_personality | Anomalies | NULL/empty name: none found | `tsdb` | **MATCH (clean)** | idem | Satu-satunya baris berstatus bersih |

### 2.3 `brand_match_master.xlsx` — 38 sheet

File ini sebenarnya **tiga workbook yang digabung**:

| Blok | Sheet | Apa isinya | Data yang dipakai |
|---|---:|---|---|
| **ENGINE** (tanpa prefix) | 17 | Spesifikasi logika Brand Match. Setiap skor adalah formula Excel, bukan angka ketikan | Roster contoh buatan tangan, 30 kreator |
| **CMP_** | 12 | Logika yang sama dijalankan atas **data `kol` nyata** | 24 akun, dibaca `10.100.14.216/kol` 10 Sep 2026 04:48 UTC |
| **DIST_** | 9 | Uji distribusi skor atas populasi penuh | 6.991 akun aktif, dibaca `10.100.14.216/kol` 10 Sep 2026 06:25 UTC |

Blok CMP dan DIST adalah **bukti DB terkuat yang gue punya sesi ini** (E3):
keduanya menyebut nama tabel, nama kolom, dan row count apa adanya.

#### 2.3.1 Blok ENGINE — 17 sheet

| File | Sheet | Excel Field | DB Schema.Table.Column | Status | Evidence | Notes |
|---|---|---|---|---|---|---|
| brand_match_master | Unified_Spec | 4 layer: BRAND / CAMPAIGN / CONTENT STYLE / PERSONALITY + UNIFIED SCORE | — | **NO MATCH** | E1 | Dokumen arsitektur. Tidak ada padanan tabel |
| brand_match_master | Unified_Spec | `UNIFIED SCORE = 70% Brand Match + 30% Campaign Fit` | — | **NO MATCH** | E1 | Konstanta bobot tidak tersimpan di DB mana pun |
| brand_match_master | Unified_Spec | Campaign Fit internals = 30% Audience / 30% Style / 25% Personality / 15% Comm. Style | — | **NO MATCH** | E1 | Style & Personality = 40% dari Campaign Fit, dan keduanya **tidak ada di DB** |
| brand_match_master | README | `FINAL MATCH = 20% Brand&Business + 30% Target Audience + 20% Content&Category + 10% Personality + 10% Performance + 10% Brand Safety` | — | **NO MATCH** | E1 | Master formula. Tidak ada tabel konfigurasi bobot |
| brand_match_master | README | "feature.brand_fit_analysis holds 0 rows, which is why four of the eight Smart Preset chips are disabled" | `feature.brand_fit_analysis` | **PARTIAL** | E1 §16.8 | **Excel dan kamus DB sepakat: 11 kolom, grain KOL × brand, 0 baris** |
| brand_match_master | README | "What to build first": isi `brand_fit_analysis` · isi `audience_demographics_daily` (age) · perlebar `feature.{ig,tt}_audience_analysis` dari 23 kreator · isi `creator_city` · isi `l1_silver.unified_rate_card` | 5 tabel | **PARTIAL** | E1, E3 | Daftar ini konsisten dengan kamus DB. Bisa dipakai langsung sebagai backlog |
| brand_match_master | Brand_Profile | 39 field brand dalam 5 seksi (A Company · B Target Audience · C Brand Identification · D Ideal Creator · E Matching Config), tiap field punya `Field Key` | `public.brand` (name, category, brand_keywords, brand_hashtags, is_competitor_tracked) | **PARTIAL — 4 dari 39 field punya kolom** | E1 §16.10, E3 CMP_Brand_Profile | 35 field lain tidak ada kolomnya. CMP_README r16 menyatakan hal ini terang-terangan: "There is no Industry field, because there is no industry column" |
| brand_match_master | Brand_Profile | `brand_id`, `brand_name` | `public.brand.name` | **PARTIAL** | E1 | Tabel 0 baris |
| brand_match_master | Brand_Profile | `industry`, `product_category`, `brand_niche`, `company_description`, `brand_positioning` | — | **NO MATCH** | E3 CMP_README r16 | Dibuang dari workbook CMP karena tidak ada kolomnya |
| brand_match_master | Brand_Profile | `business_keywords`, `brand_keywords` (max 5, comma-separated) | `public.brand.brand_keywords` | **PARTIAL** | E3 | Kolom ada. Sisi kreatornya (`kol_directory.bio`) hanya ~12% terisi |
| brand_match_master | Brand_Profile | `primary_age_range`, `secondary_age_range` | `audience_demographics_daily` (audience_type='age') | **NO MATCH (data)** | E3 CMP_Validation r58 | **0 baris** — "no age signal anywhere on this server" |
| brand_match_master | Brand_Profile | `gender_majority` | `audience_demographics_daily` (gender) + `female_pct` | **PARTIAL** | E2 mig 037 | 23 kreator |
| brand_match_master | Brand_Profile | `target_country`, `target_region`, `target_city` | `l2_gold.audience_geo_daily.geo_level` | **PARTIAL** | E3 r18–20 | country 23 kreator · region 9/33 key salah level · city 15 kreator |
| brand_match_master | Brand_Profile | `audience_interests` (max 5) | `l2_gold.audience_interest_daily.interest_key` | **PARTIAL** | E3 §12 | 18 key valid; 85,2% baris ber-key `unknown` |
| brand_match_master | Brand_Profile | `audience_priority` (Age/Gender/Location/Interest) + bonus 12 poin | — | **NO MATCH** | E1 | Mekanisme pembobotan, bukan data |
| brand_match_master | Brand_Profile | `brand_personality`, `brand_tone`, `communication_style`, `brand_values` | — | **NO MATCH** | E3 CMP_Validation r61 | Lihat §5 |
| brand_match_master | Brand_Profile | `preferred_platform` | `kol_directory.platform_id → platforms.key` | **MATCH** | E3 r9–10 | 97,1% |
| brand_match_master | Brand_Profile | `preferred_category` | `kol_directory.category_ids → kol_categories` | **PARTIAL** | E3 r11 | 54,1% (3.547 kreator tanpa kategori) |
| brand_match_master | Brand_Profile | `preferred_subcategory` | — tidak ada kolom | **NO MATCH** | E3 CMP_Validation r60 | "no kol_sub_categories table, no sub_category_ids column" |
| brand_match_master | Brand_Profile | `preferred_tier`, `preferred_followers_min/_max` | `kol_tiers`, `kol_directory.followers_count` | **MATCH** | E3 r13–14 | 97,1% |
| brand_match_master | Brand_Profile | `min_engagement_rate` | `kol_directory.engagement_rate` | **PARTIAL** | E3 r15 | 1.744 terpakai (22,6%) |
| brand_match_master | Brand_Profile | `preferred_content_style`, `preferred_creator_personality`, `preferred_creator_values` | — | **NO MATCH** | E3 | Lihat §5 |
| brand_match_master | Brand_Profile | `min_audience_quality` | `feature.*_audience_analysis.audience_quality_score` | **PARTIAL** | E3 r24 | 23 kreator; algoritma skornya sendiri **belum didefinisikan** (E1 §5.2 NEED DEFINITION) |
| brand_match_master | Brand_Profile | `min_brand_safety` | — tidak ada kolom risk-level | **NO MATCH** | E3 r48 | 0% |
| brand_match_master | Brand_Profile | `category_hard_filter`, `country_hard_filter`, `max_competitor_saturation`, `min_brand_match`, 4 toggle exclusion | — | **NO MATCH** | E1 | Konfigurasi per-brand; tidak ada tabel penyimpan |
| brand_match_master | Brand_Profile | TOKEN HELPER — tiap list dipecah 5 slot + `*_count` sebagai penyebut | — | **N/A** | — | Mekanisme Excel (SUBSTITUTE/REPT/MID). Di backend cukup array; **aturan bisnisnya yang penting**: "brand yang menyebut 3 keyword dinilai dari 3, bukan dari 5" |
| brand_match_master | Brand_Profile | AUDIENCE SUB-WEIGHTS — base 25/15/30/30, priority bonus 12, sisanya dipotong sepertiga | — | **NO MATCH** | E1 | Contoh terhitung: prioritas Interest → 21/11/26/42 |
| brand_match_master | Campaign_Profile | 16 field: `Campaign ID`, `Brand ID`, `Campaign Name`, `Objective`, `Platform`, `Target Age`, `Gender`, `Target Country`, `Campaign Category`, `Key Topics`, `Content Style`, `Creator Personality`, `Campaign Tone`, `Communication Style`, `CTA`, `Campaign Type` | `public.campaigns` + `campaign_brief` | **PARTIAL — struktur ada, isi 0** | E1, E3 r57 | Lihat §2.4 dan §7 |
| brand_match_master | Campaign_Profile | `Objective` = Awareness / Engagement / Conversion | — | **NO MATCH** | E1 | Excel sendiri: "Objective remains a campaign descriptor and can later become a dedicated signal if backend data supports it" |
| brand_match_master | Campaign_Profile | Default: Campaign Weight 30% / Base Brand Match 70% | — | **NO MATCH** | E1 | Konstanta tidak tersimpan |
| brand_match_master | Campaign_Match | 16 kolom, grain **campaign × KOL** (90 baris = 3 campaign × 30 KOL): `Brand Match`, `Audience Fit`, `Style Fit`, `Personality Fit`, `Tone Fit`, `Comm. Style Fit`, `Campaign Fit`, `Unified Match`, `Match Level`, `Campaign Reason` | `public.campaign_kols` | **NO MATCH (kolom skor)** | E1, E3 r57 | Grain-nya cocok dengan `campaign_kols`, tapi tidak satu pun kolom skor ini ada. `campaign_kols` 0 baris |
| brand_match_master | Unified_Match | 16 kolom, grain campaign × KOL: `Brand Match (70%)`, `Campaign Fit (30%)`, `Unified Match`, `Brand Style Fit`, `Brand Personality Fit`, `Campaign Style Fit`, `Campaign Personality Fit`, `Campaign Objective` | `public.campaign_kols` | **NO MATCH** | E1 | Idem. 4 dari 16 kolom bergantung Style/Personality yang tidak ada |
| brand_match_master | KOL_Database | 58 kolom dalam 8 blok: IDENTITY (9) · PERFORMANCE (13) · AUDIENCE (12) · CONTENT (5) · COMMERCIAL (6) · SAFETY (3) · EXCLUSION STATE (4) · FRESHNESS (2) · DERIVED (4) | lihat §2.3.4 | **PARTIAL** | E3 | **Ini "creator payload shape" yang dituju backend.** Rincian per kolom di §2.3.4 |
| brand_match_master | Matching_Engine | 59 kolom × 90 baris (3 brand × 30 KOL). 6 komponen, 22 sub-skor, `Final Match Score`, `Match Level`, `Confidence`, `Brand Fit Index`, `Opportunity Score`, `Hard Filter Result`, `Exclusion Reason`, `Recommendation`, `Match Key`, 6 kolom HELPERS | — | **NO MATCH** | E1 | **Tidak ada satu pun kolom ini di DB.** Grain-nya (brand × KOL) sama dengan `feature.brand_fit_analysis`, yang punya `partnership_score` + `sub_scores` jsonb — rumah potensial, tapi 0 baris dan algoritmanya belum didefinisikan |
| brand_match_master | Match_Explanation | 29 kolom: 3 Strength + 3 Consideration (dibaca LARGE/SMALL atas komponen yang sama), 5 reason line per komponen, `Risk`, `Recommendation`, 6 kolom `adj` | `feature.brand_fit_analysis.recommendations`, `.overlap_summary` | **NO MATCH (data)** | E1 §16.8 | Rumah kolom bertipe teks/jsonb ada; 0 baris. Aturannya jelas: penjelasan **di-generate dari skor**, tidak ditulis tangan |
| brand_match_master | Discovery_Filters | 56 filter × 10 kolom, termasuk `KOL database source` + `Coverage (8 Sep 2026)` | seluruh DB | **PARTIAL** | E3 | **Sheet paling berguna di seluruh file** — ia sudah berupa peta Excel→DB. Roll-up: 21 HARD / 35 SOFT · DONE 14 · PARTIAL 5 · BLOCKED BY DATA 29 · NEW 8 |
| brand_match_master | Discovery_Ranking | 53 kolom; `Default Sort Key` (Brand Match → Audience → Content → Performance → Safety), `Preset Rank`, `Preset Metric Value`, + 30 kolom metrik preset | — | **NO MATCH** | E1 | Ranking dihitung di aplikasi. Excel eksplisit: "Apply after ranking, never inside the SQL" |
| brand_match_master | Filter_Logic | 15 HARD + 8 SOFT, masing-masing: Rule, Condition, implementasi Excel, akibat gagal, catatan backend (sudah berbentuk `WHERE ...`) | seluruh DB | **PARTIAL** | E3 | Catatan backend-nya sudah SQL-ready untuk yang DONE |
| brand_match_master | Filter_Logic | MATCH LEVEL LADDER: 90–100 Excellent · 80–89 Strong · 70–79 Good · 60–69 Moderate · 0–59 Low | — | **NO MATCH** | E1 | Band tidak tersimpan di DB |
| brand_match_master | Taxonomy | 143 node kreator (14 L1 / 42 L2 / 87 L3) + 12 industry + 24 niche + 183 baris crosswalk + alias table + aturan klasifikasi | `public.kol_categories` (28 baris, 9 key) | **PARTIAL** | E3 §11a | Rincian di §8 |
| brand_match_master | Sample_Brands | 30 kolom: 24 mirror Brand_Profile + 6 outcome (`Eligible Creators`, `Excluded Creators`, `Average Match`, `Highest Match`, `Best-Matched Creator`, `Excellent + Strong`) | — | **NO MATCH** | E1 | Sheet uji. BRAND-A: 24 eligible / 6 excluded / avg 57,7 / max 93 |
| brand_match_master | Sample_Output | 17 kolom: skor+level+rank untuk 3 brand, `Score Spread`, `Best-Fit Brand`, `Same score for all three?` | — | **NO MATCH** | E1 | Sheet pembuktian bahwa skor = fungsi (brand, kreator). Spread KOL-01 = 32, KOL-02 = 48 |
| brand_match_master | Lookup_Lists | 30 dropdown list · sub→parent category (42) · tier band (5) · **46 konstanta berkunci** · 5 matriks relevansi · 30 ranking preset | — | **NO MATCH** | E1 | **Ini yang paling penting diselamatkan.** Rincian di §6.2 |

#### 2.3.2 Blok CMP_ — 12 sheet (dijalankan atas data `kol` nyata)

| File | Sheet | Excel Field | DB Schema.Table.Column | Status | Evidence | Notes |
|---|---|---|---|---|---|---|
| brand_match_master | CMP_README | Daftar tabel yang dibaca: `public.kol_directory`, `public.kol_social_account`, `public.kol_categories`, `feature.ig/tt_audience_analysis`, `feature.ig_engagement_analysis`, `l2_gold.kol_profile_card`, `l2_gold.audience_interest_daily`, `l2_gold.audience_geo_daily`, `l2_gold.audience_demographics_daily`, `l1_silver.unified_post` | **10 tabel `kol`** | **MATCH (inventaris)** | E3 | **Ini daftar tabel `kol` yang terverifikasi ada dan terbaca.** Dipakai sebagai tulang punggung §0.2 |
| brand_match_master | CMP_README | "the record shape follows `public.brand`: name, category, brand_keywords, brand_hashtags" | `public.brand` | **PARTIAL** | E1 §16.10 | Kolomnya ada; tabelnya 0 baris |
| brand_match_master | CMP_README | "6 inputs do not exist on this server": audience age · sub category · creator personality/tone/values/content style · community · comment sentiment/toxicity · rate card | 6 area | **NO MATCH** | E3 CMP_Validation r58–65 | Tiap baris disertai cara verifikasinya. **Ini gap list yang sudah terverifikasi, bukan dugaan** |
| brand_match_master | CMP_README | Sub-bobot yang **berbeda dari blok ENGINE**: Brand&Business = Category 60 / Keyword 25 / Hashtag 15; Content = Content Category 60 / Topic 40; Brand Safety = Authenticity 40 / Follower Quality 30 / Verification 15 / Paid Ratio 15 | — | **NO MATCH + konflik internal** | E3 §11 | **Dua set sub-bobot untuk komponen yang sama** di satu file. CMP menyebutnya "supersedes section 4" karena DB tidak punya kolom industry. **NPD** |
| brand_match_master | CMP_KOL_Source_Data | 77 kolom, 24 akun. Termasuk `Category Basis`, `Classification Evidence`, `Interest Known %`, `Country Known %`, `City Known %`, `Gender Known %`, `Posts Analyzed`, `Observation Days`, `Cadence Usable`, `Data Note` | `kol_directory`, `kol_categories`, `feature.*`, `l2_gold.*` | **PARTIAL** | E3 | **Semua 5 kolom Audience Age = N/A untuk 24 akun** |
| brand_match_master | CMP_KOL_Source_Data | `Category Basis` = live / calculated / estimated | — tidak ada kolom | **NO MATCH** | E3 CMP_README r30 | 12 live · 3 diklasifikasi dari caption · 9 tanpa kategori. **Konsep provenance ini yang paling layak diadopsi** |
| brand_match_master | CMP_KOL_Source_Data | `Paid Ratio %` | `feature.*_engagement_analysis.paid_ratio` | **MATCH (kolom)** | E2 mig 037 | Sumber `unified_post.is_sponsored` — sudah ada |
| brand_match_master | CMP_KOL_Source_Data | `Community Score` | — tidak ada kolom | **NO MATCH** | E3 CMP_Validation r65 | "no column anywhere in public, feature or l2_gold" |
| brand_match_master | CMP_Brand_Profile | Kolom `Source in the database` per field — 9 kolom × 60 baris | berbagai | **MATCH (sebagai peta)** | E3 | **Peta Excel→DB paling eksplisit di seluruh file.** Menyatakan terang: `primary_age_range` = "NO COLUMN", personality = "NO CREATOR COLUMN" |
| brand_match_master | CMP_Brand_Profile | 18 baris `interest_<key>` sebagai flag 0/1 | `l2_gold.audience_interest_daily.interest_key` | **MATCH** | E3 §12 | Key-nya dieja persis seperti DB; build-nya meng-assert dan berhenti kalau brand menarget key yang tidak ada |
| brand_match_master | CMP_Matching_Engine | 59 kolom × 120 baris (5 brand × 24 KOL). Tambahan penting: `*_Available` per komponen + `Available Weight` | — | **NO MATCH** | E1 | Mekanisme **renormalisasi bobot saat input hilang** — nilai hilang jadi N/A dan keluar dari rata-rata tertimbang, **tidak pernah jadi 0**. Ini aturan yang layak dibawa ke backend apa adanya |
| brand_match_master | CMP_Score_Breakdown | 18 kolom: 4 sub-skor audience + 6 komponen + `Available Weight` + hasil | — | **NO MATCH** | E1 | View murni |
| brand_match_master | CMP_Match_Explanation | 27 kolom; 120 penjelasan + kolom kerja `max:`/`min:` per komponen | — | **NO MATCH** | E1 | Contoh: "BRAND-C\|KOL-24 — 50/100 … weakest Brand Safety at 29" |
| brand_match_master | CMP_Brand_Comparison | 13 kolom, 1 baris per kreator × 5 kolom brand + `Best Brand`, `Best Score`, `Spread (max-min)` | — | **NO MATCH** | E1 | Bentuk output "1 kreator × N brand" |
| brand_match_master | CMP_Brand_Ranking | 5 blok × 24 baris, diurut `Rank Key` | — | **NO MATCH** | E1 | — |
| brand_match_master | CMP_Top_Matches | Top 5 + bottom 5 per brand: `Band`, `Reason`, `Strength`, `Concern` | — | **NO MATCH** | E1 | — |
| brand_match_master | CMP_Hard_vs_Soft_Filter | 21 HARD + 35 SOFT dengan **efek terukur pada roster nyata** | seluruh DB | **PARTIAL** | E3 | Tambahan yang tidak ada di `Discovery_Filters`: filter **`Connected`** — "removes all 24 — no creator on this server has completed the OAuth connect flow" |
| brand_match_master | CMP_Validation | 15 check + resolusi handle + **"WHAT THE DATABASE DOES NOT HAVE"** (8 baris, tiap baris disertai cara verifikasi) | seluruh DB | **MATCH (sebagai audit)** | E3 | **Sumber gap list §9.** Beberapa cell menampilkan `#VALUE!`/`#REF!` — rumusnya rusak saat file disimpan, jadi *angka* check-nya tidak bisa dipercaya; *teks* temuannya tetap sah |
| brand_match_master | CMP_Lookup_Lists | §11a: **28 baris `public.kol_categories` lengkap dengan jumlah kreator dan `taxonomy_key`** | `public.kol_categories` | **MATCH** | E3 §11a | **Ini isi tabel `kol_categories` yang sebenarnya.** Lihat §8.2 |
| brand_match_master | CMP_Lookup_Lists | §11b: ER target per tier — Nano 8 / Micro 6 / Mid-tier 4,5 / Macro 3 / Mega 2 (%) | — | **NO MATCH** | E1 | Menggantikan `CAL_ER_TARGET` global. Alasannya kuat: ER turun seiring ukuran akun |
| brand_match_master | CMP_Lookup_Lists | §11d: matriks 9×9 canonical category | — | **NO MATCH** | E1 | **Satu-satunya matriks yang kedua sumbunya nilai DB nyata** (`taxonomy_key`) |
| brand_match_master | CMP_Lookup_Lists | §11: `CAL_COUNTRY_TARGET` 60 · `CAL_CITY_TARGET` 25 · `CAL_INTEREST_TARGET` 45 · `CAL_CONSISTENCY_TARGET` 12 · `CAL_MIN_OBS_DAYS` 21 · `CAL_VFR_TARGET_ROSTER` 1,5 | — | **NO MATCH** | E1 | `CAL_MIN_OBS_DAYS`=21 menjawab masalah yang sama dengan `post_frequency_reliability` (mig 038) tapi **dengan ambang berbeda** (21 vs 30/14) → **NPD** |
| brand_match_master | CMP_Lookup_Lists | BRAND SAFETY SCREEN: Authenticity 40 / Follower Quality 30 / Verification 15 / Paid Ratio 15; `CAL_VERIFIED_YES` 100, `CAL_VERIFIED_NO` **50** (bukan 0), `CAL_PAID_CEILING` 40; band 80/65/50 | `feature.*_audience_analysis.authenticity_score`, `follower_quality_score`, `kol_directory.verified_status`, `paid_ratio` | **PARTIAL** | E3 | **Ini versi Brand Safety yang bisa dihitung hari ini** — 3 dari 4 input punya kolom. Excel menandainya *integrity screen*, **bukan** brand safety sesungguhnya |
| brand_match_master | CMP_Lookup_Lists | §12: 18 `interest_key` + `unknown` | `l2_gold.audience_interest_daily.interest_key` | **MATCH** | E3 | `unknown` = bagian audiens yang gagal diklasifikasi (80–89%), **masuk penyebut, tidak pernah ditarget** |

#### 2.3.3 Blok DIST_ — 9 sheet (populasi penuh 6.991 kreator)

| File | Sheet | Excel Field | DB Schema.Table.Column | Status | Evidence | Notes |
|---|---|---|---|---|---|---|
| brand_match_master | DIST_README | `Normalized = Absolute ÷ MAX(populasi) × 100` | — | **NO MATCH** | E1 | Temuan: normalisasi afin → **tidak mengubah bentuk distribusi**, hanya presentasi |
| brand_match_master | DIST_README | Distribusi terkompresi: Pref A 25–80 (IQR 44–50) · Pref B 18–80 (IQR 41–50) · Pref C 18–67 (IQR 36–48) | — | **NO MATCH** | E1 | **33,7% / 45,0% / 10,0% populasi mendapat skor identik** karena `CAL_NEUTRAL`=50 |
| brand_match_master | DIST_Population | `6991 active creators from public.kol_directory` · `directory_status='active'` | `public.kol_directory` | **MATCH** | E3 | Dibaca 10 Sep 2026 06:25 UTC |
| brand_match_master | DIST_Population | **TABEL COVERAGE SINYAL** | berbagai | **MATCH** | E3 | Tabel di bawah — **angka kesiapan DB paling mutakhir yang gue punya** |
| brand_match_master | DIST_Preference_Profiles | 3 profil dengan kolom `Source in the database` + `Kind` (HARD/SOFT) per kriteria | berbagai | **MATCH (sebagai peta)** | E3 | Catatan: "Tech adalah kategori canonical TERKECIL — 4 kreator" |
| brand_match_master | DIST_Absolute_Scores | 15 kolom × 5.120 baris, 3 blok bersebelahan | — | **NO MATCH** | E1 | Output skor; bukan struktur |
| brand_match_master | DIST_Normalized_Scores | idem, + divisor per populasi (80 / 80 / 67) | — | **NO MATCH** | E1 | Sebagian cell `#REF!` |
| brand_match_master | DIST_Distribution_Summary | N, Min, Max, Mean, Median, StdDev, P25, P75, SKEW | — | **NO MATCH** | E1 | **Seluruh cell `#REF!`** — angkanya harus dibaca dari DIST_README, bukan dari sheet ini |
| brand_match_master | DIST_Histogram_Data | 20 bin × 6 seri | — | **NO MATCH** | E1 | **Seluruh cell `#VALUE!`** |
| brand_match_master | DIST_Histograms | 6 chart | — | **NO MATCH** | E1 | Sheet chart, praktis kosong (2 baris teks) |
| brand_match_master | DIST_Preference_Comparison | 12 kolom × 194 kreator yang lolos ketiga preferensi; `Rank spread (max-min)` | — | **NO MATCH** | E1 | Median rank spread 2.409; terlebar 5.082; 78,4% bergeser >10 persentil |
| brand_match_master | DIST_Validation | 15 check, termasuk "No fabricated metrics — PASS" dan satu bug fix yang dinamai | — | **MATCH (sebagai audit)** | E3 | Bug: guard `LEN(TRIM(haystack))=0` tidak pernah menyala karena haystack digabung `" \| "` |

**Coverage sinyal atas 6.991 kreator aktif (DIST_Population, 10 Sep 2026) — angka
paling mutakhir untuk menilai kesiapan DB:**

| Input | Kreator punya | Share | Komponen yang disuapi | Akibat kalau kosong |
|---|---:|---:|---|---|
| Followers | 6.991 | 100% | Tier + semua aturan eligibility | — |
| Canonical category (`kol_categories.taxonomy_key`) | 3.888 | **55,6%** | Brand & Business (60%) | Category Match jatuh ke `CAL_NEUTRAL`=50 |
| — di antaranya live dari `kol_categories` | 3.847 | 55,0% | idem | — |
| Engagement rate | 1.728 | **24,7%** | Performance (35%) | ER Score N/A |
| Bio text | 897 | **12,8%** | Keyword Match | Keyword Match N/A |
| Platform-verified | 559 | **8,0%** | Brand Safety (15%) | skor `CAL_VERIFIED_NO`=50, bukan 0 |
| Harvested captions | 50 | **0,72%** | Content Relevance + Keyword | Topic Match N/A; kategori tak bisa diklasifikasi |
| Audience analysis (quality/authenticity) | 24 | **0,34%** | Performance + Brand Safety | Safety jatuh ke verifikasi saja |
| Audience interests | 24 | **0,34%** | Target Audience (30%) | Interest Score N/A |
| View-to-follower ratio | 20 | **0,29%** | Performance (10%) | Average Views Score N/A |

> Baca baris ini dengan serius: **6 dari 10 sinyal yang dibaca engine tersedia
> untuk kurang dari 1% populasi.** Itulah kenapa 33–45% kreator mendapat skor
> yang persis sama.

#### 2.3.4 `KOL_Database` — 58 kolom, dipetakan satu per satu

Sheet ini adalah *creator payload shape* yang dituju backend (README r46:
"the KOL_Database headers are the creator shape"). Karena itu ia dipetakan
per kolom, bukan per blok.

| Blok | Excel column | DB Schema.Table.Column | Status | Coverage / catatan |
|---|---|---|---|---|
| IDENTITY | KOL ID | `public.kol_directory.id` | **MATCH** | — |
| IDENTITY | Creator Name | `kol_directory.username` + `agency_kol_accounts.label` | **MATCH** | 97,1% |
| IDENTITY | Handle | `kol_directory.username_normalized` | **MATCH** | 97,1% |
| IDENTITY | Platform | `kol_directory.platform_id → platforms.key` | **MATCH** | 97,1% |
| IDENTITY | Category | `kol_directory.category_ids → kol_categories` | **PARTIAL** | 54,1% · 3.547 tanpa kategori |
| IDENTITY | Sub Category | — | **NO MATCH** | tidak ada kolom |
| IDENTITY | Tier | derived: `followers_count` vs `kol_tiers` | **MATCH** | 7.195 bertier + 526 untiered |
| IDENTITY | Verified | `kol_directory.verified_status` | **PARTIAL** | 455 verified dari 932 bernilai (DIST: 559/6.991) |
| IDENTITY | Creator City | `kol_directory.creator_city` | **PARTIAL** | kolom ada, **0% terisi** |
| PERFORMANCE | Followers | `kol_directory.followers_count` | **MATCH** | 97,1% / 100% populasi aktif |
| PERFORMANCE | Engagement Rate (%) | `kol_directory.engagement_rate` | **PARTIAL — formula beda** | 22,6–24,7%. DB tanpa `shares` |
| PERFORMANCE | Average Views | `feature.*_engagement_analysis.avg_views` (mig 036) · `l2_gold.post_metric.views` | **PARTIAL** | 21 kreator |
| PERFORMANCE | Median Views | `feature.*_engagement_analysis.median_views` (mig 036) | **PARTIAL** | Discovery_Filters menandai "NEW — belum ada agregat median"; **mig 036 sudah menambahkannya** → sheet lebih tua dari migration |
| PERFORMANCE | 30D Growth (%) | `l2_gold.kol_profile_card.followers_growth`, `daily_growth`, `projected_30d` | **PARTIAL** | 25 kreator (0,3%). Mig 040 mengubah arti `projected_30d` menjadi **selisih**, bukan total |
| PERFORMANCE | 90D Growth (%) | `l2_gold.kol_metric_monthly` (deret) | **PARTIAL** | 5 kreator ≥4 titik |
| PERFORMANCE | Consistency Score | — | **NO MATCH** | proksi terdekat `performance_stability` (mig 039, ER stddev) — **bukan** konsep yang sama |
| PERFORMANCE | Community Score | — | **NO MATCH** | "no column anywhere" (CMP_Validation r65) |
| PERFORMANCE | Audience Quality | `feature.*_audience_analysis.audience_quality_score` + `audience_quality_tier` (mig 039) | **PARTIAL** | 23–24 kreator; algoritma **belum didefinisikan** |
| PERFORMANCE | Audience Authenticity | `feature.*_audience_analysis.authenticity_score` | **PARTIAL** | 23 kreator; algoritma belum didefinisikan |
| PERFORMANCE | Share Rate (%) | `feature.*_engagement_analysis.share_rate` (mig 037) | **PARTIAL** | 11 kreator, **TikTok saja** (IG tidak mengembalikan shares) |
| PERFORMANCE | Save Rate (%) | `feature.*_engagement_analysis.save_rate` (mig 039) | **PARTIAL** | 11 kreator, **TikTok saja** |
| PERFORMANCE | Recent Performance | `l2_gold.kol_metric_monthly` (deret) | **NO MATCH** | 5 kreator; tidak ada kolom skor |
| AUDIENCE | Audience Age 13–17 % … 45+ % (5 kolom) | `l2_gold.audience_demographics_daily` (audience_type='age') | **NO MATCH (data)** | **0 baris.** "no age signal anywhere on this server" |
| AUDIENCE | Female % / Male % | `feature.*_audience_analysis.female_pct` / `male_pct` (mig 037) | **PARTIAL** | 23 kreator (0,30%) |
| AUDIENCE | Audience Country / Region / City | `l2_gold.audience_geo_daily.geo_level` | **PARTIAL** | 23 / 9-dari-33-salah-level / 15 kreator |
| AUDIENCE | Audience Interests | `l2_gold.audience_interest_daily.interest_key` + `interest_top`/`interest_source` (mig 039) | **PARTIAL** | 24 kreator; 85,2% `unknown` |
| AUDIENCE | Purchase Intent | — | **NO MATCH** | "belum ada kolom" |
| CONTENT | Content Topics | `feature.*_engagement_analysis.content_topic` + `content_topic_source` (mig 039) | **PARTIAL — vocabulary beda** | Mig 039 memakai 18 key `audience_inference.INTEREST`; Excel memaksudkan 87 node L3. **Bukan hal yang sama** |
| CONTENT | Content Style | — | **NO MATCH** | lihat §5 |
| CONTENT | Creator Personality | — | **NO MATCH** | lihat §5 |
| CONTENT | Creator Values | — | **NO MATCH** | lihat §5 |
| CONTENT | Content Quality | — | **NO MATCH** | tidak ada kolom; **tidak ada definisi di Excel juga** |
| COMMERCIAL | Rate Card (IDR) | `l1_silver.unified_rate_card.fee` · `kol_profile_card.rate_card_*` | **NO MATCH (data)** | **0 baris; `rate_card_min_fee` NULL di seluruh 1.978 kartu** |
| COMMERCIAL | CPV | — (derived) | **NO MATCH** | formula ada di Excel; lihat §4 |
| COMMERCIAL | CPE | `feature.*_audience_analysis.cpe` | **PARTIAL (kolom) / NO MATCH (data)** | lihat §4 |
| COMMERCIAL | CPM | — (derived) | **NO MATCH** | lihat §4 |
| COMMERCIAL | Estimated Reach | — (derived) | **NO MATCH** | `feature.*_audience_analysis.avg_reach` ada tapi `unified_post.reach` NULL 0/221 |
| COMMERCIAL | Estimated ROI | — (derived) | **NO MATCH** | lihat §4 |
| SAFETY | Brand Safety Score | — | **NO MATCH** | tidak ada kolom risk-level |
| SAFETY | Competitor Saturation | — | **NO MATCH** | tidak ada kolom |
| SAFETY | Risk Flag | — | **NO MATCH** | tidak ada kolom |
| EXCLUSION | Already Selected | `discover_creator_links` (migrasi **053** — repo lain) | **NPD** | di luar repo/DB ini |
| EXCLUSION | In Cart | state aplikasi | **NO MATCH** | bukan DB |
| EXCLUSION | Existing Partner | `public.campaign_kols` | **PARTIAL** | tabel ada, **0 baris** |
| EXCLUSION | Excluded Creator | — | **NO MATCH** | "belum ada daftar exclusion" |
| FRESHNESS | Added Date | `kol_directory.created_at` | **MATCH** | 99,7% |
| FRESHNESS | Last Updated | `kol_directory.last_refreshed_at` | **MATCH** | 97,1% |
| DERIVED | View-to-Follower Ratio | `feature.*_engagement_analysis.view_to_follower_ratio` (mig 036) | **PARTIAL** | 20–21 kreator |
| DERIVED | Cost Efficiency | — | **NO MATCH** | `CAL_MEDIAN_CPE ÷ CPE × 100`, butuh rate card |
| DERIVED | Data Completeness % | — | **NO MATCH** | formula Excel: 12 field dicek, dibagi 12 × 100 |
| DERIVED | Data Status | — | **NO MATCH** | Live ≥100 · Calculated ≥84 · Estimated di bawahnya |

**Rekap 58 kolom:** MATCH **11** · PARTIAL **20** · NO MATCH **26** · NPD **1**.

> Perhatikan `Median Views` dan `View-to-Follower Ratio`: `Discovery_Filters`
> menandainya "NEW — belum ada kolom", padahal **migration 036 sudah
> menambahkannya**. Sheet Excel bertanggal 8 Sep 2026, migration 036 lebih baru.
> Artinya beberapa status "NEW"/"BLOCKED" di Excel sudah kedaluwarsa — wajib
> diperiksa ulang terhadap DB hidup sebelum dijadikan backlog.

### 2.4 FOKUS A & B — BRAND dan CAMPAIGN di DB `kol`

#### A. BRAND — **JANGAN bikin tabel brand baru**

| Pertanyaan | Jawaban | Bukti |
|---|---|---|
| Apakah ada tabel brand di `kol`? | **Ya — `public.brand`** | E1 §16.10, E3 CMP_Brand_Profile |
| Kolomnya apa saja? | `name`, `category`, `brand_keywords`, `brand_hashtags`, `is_competitor_tracked` (+ kolom lain belum terinventaris) | E3, `KOL_DISCOVERY_FILTER_BACKEND_PLAN.md` |
| Berapa barisnya? | **0** | E1 §16.10 — "`public.brand` 0 baris, membuka 6 kolom terkunci, butuh onboarding brand" |
| Apakah brand di Excel sudah ada di DB? | **Tidak di `kol`.** 38 baris brand ada di **`tsdb.public.brands`** | `brand_style_personality` Summary |
| Brand di Excel mana yang cocok? | **Tidak satu pun**, karena `kol.public.brand` kosong. Brand contoh workbook (Nusatech Cloud, Lumaya Skin, Rasa Nusantara, NovaTech, LumiSkin, DailyBite, MoveFit, UrbanMuse) semuanya **fiktif untuk pengujian** — bukan brand nyata | CMP_README r14 |
| Tabel pendamping | `feature.brand_fit_analysis` (grain KOL × brand, 11 kolom, 0 baris) | E1 §16.8 |

**Kesimpulan A:** struktur brand sudah ada di `kol` dan **tidak boleh
diduplikasi**. Yang belum ada adalah **isinya** dan **keputusan** apakah
`kol.public.brand` atau `tsdb.public.brands` yang jadi sumber kebenaran. Kalau
`tsdb` yang dipilih, 19 dari 38 barisnya data test dan `unified_post.brand_id`
di sana tidak menunjuk `brands.id` — dua hal itu harus dibereskan lebih dulu.

#### B. CAMPAIGN — **struktur lengkap, isi nol**

| Konsep Excel | Tabel `kol` | Baris | Status |
|---|---|---:|---|
| Campaign (header) | `public.campaigns` — punya `tracking_status` | **0** | **PARTIAL** |
| Campaign × KOL | `public.campaign_kols` — punya `impressions`, `last_tracked_at`, FK `campaign_id` + `agency_kol_account_id` | **0** | **PARTIAL** |
| Campaign performance | `public.campaign_content_performance` — punya `impressions` | **0** | **PARTIAL** |
| Brief / jadwal posting | `public.campaign_brief` — punya `posting_schedule` | **0** | **PARTIAL** |
| Status / tahapan campaign | `public.campaign_stages`, `campaign_milestones`, `campaign_activities`, `campaign_activity_attachments` | **0** | **PARTIAL** |
| Deliverable | `public.campaign_kol_deliverables` — punya `first_tracked_at` | **0** | **PARTIAL** |
| Cost / rate campaign | `public.campaign_kol_payments`, `campaign_orders` | **0** | **PARTIAL** |
| Antrean tracking | `public.campaign_tracking_jobs` — `job_type`, `status`, `scheduled_at`, `attempt_count` | **0** | **PARTIAL** |
| Lain-lain | `campaign_targets`, `campaign_tag`, `campaign_kol_progress_logs` | **0** | **PARTIAL** |

Total **±15 tabel domain campaign, semuanya 0 baris** (E1, `KOL_DISCOVERY_FILTER_BACKEND_PLAN.md` §"12 tabel campaign lain").

**Yang Excel minta tapi campaign di DB tidak punya:**

| Field Excel (Campaign_Profile / Campaign_Match) | Ada di `campaigns`/`campaign_brief`? |
|---|---|
| `Objective` (Awareness/Engagement/Conversion) | **belum terverifikasi** — perlu `SELECT` |
| `Content Style`, `Creator Personality`, `Campaign Tone`, `Communication Style` | **tidak** — tidak ada kolom ini di seluruh DB (§5) |
| `Campaign Fit`, `Unified Match`, `Style Fit`, `Personality Fit`, `Tone Fit`, `Comm. Style Fit` | **tidak** — seluruh kolom skor |
| `CTA`, `Campaign Type`, `Key Topics` | **belum terverifikasi** |

**Kesimpulan B:** grain `campaign_kols` **persis** grain yang dibutuhkan
`Campaign_Match`/`Unified_Match`. Jadi rumah barisnya sudah ada; yang tidak ada
adalah **kolom skor** dan **4 field brief bertipe style/personality**. Jangan
bikin tabel campaign baru — inventarisasi kolom ±15 tabel itu dulu dengan VPN
aktif.

---

## 3. PROPOSED DATA MODEL

> Rekomendasi, **bukan migration**. Prinsipnya: reuse dulu, tabel baru terakhir.
> Rincian pembenarannya ada di §4–§8.

### 3.1 Kolom existing yang CUKUP dipakai — tidak perlu apa pun

| Kebutuhan Excel | Pakai ini | Kenapa cukup |
|---|---|---|
| Age band kreator (5 bucket) | `l2_gold.kol_profile_card.creator_age_band` | Migration 043 sudah menyamakan bucket-nya **persis** dengan `taksonomi_kol.Demografi` |
| Follower tier | `public.kol_tiers` + `agency_kol_accounts.tier_id` | 5 baris, sudah dirujuk 7.207 akun. **Yang perlu diselesaikan cuma sengketa batas Mid-tier/Macro (§2.1) — lewat `UPDATE`, bukan tabel baru** |
| View-to-Follower Ratio, Avg/Median Views | `feature.*_engagement_analysis.*` (mig 036) | Sudah ada; Excel menandainya "NEW" karena sheet-nya lebih tua |
| Share Rate, Save Rate, Paid Ratio, Post Frequency | mig 037 + 039 | Sudah ada |
| Growth 30D + proyeksi | `kol_profile_card.followers_growth`, `daily_growth`, `projected_30d`, `projected_followers_30d` | Sudah ada (mig 037, 040) |
| Audience gender | `feature.*_audience_analysis.female_pct` / `male_pct` / `gender_known_pct` | Sudah ada (mig 037) |
| Audience interest | `l2_gold.audience_interest_daily.interest_key` + `interest_top`/`interest_source` | Sudah ada; **18 key ini yang jadi vocabulary, bukan daftar Excel** |
| Semua 14 filter "DONE" | `kol_directory`, `platforms`, `kol_tiers`, `agency_kol_accounts` | Sudah jalan end-to-end |

### 3.2 Tabel existing yang CUKUP dipakai

| Kebutuhan | Tabel existing | Catatan |
|---|---|---|
| Brand master | **`public.brand`** | 0 baris. **JANGAN bikin `brands` baru.** Yang dibutuhkan onboarding data + keputusan `kol` vs `tsdb` (§6.4) |
| Skor Brand Match per (brand, KOL) | **`feature.brand_fit_analysis`** | Grain-nya **persis** `Matching_Engine`. Sudah punya `partnership_score` (skor akhir), `sub_scores` **jsonb** (22 sub-skor), `category_fit_tags`, `recommendations`, `overlap_summary`, `audience_overlap_pct`. **Ini rumah yang tepat — tidak perlu tabel skor baru** |
| Campaign header + campaign × KOL | **`public.campaigns`**, **`public.campaign_kols`** | Grain `campaign_kols` = grain `Campaign_Match`/`Unified_Match` |
| Antrean job | **`public.campaign_tracking_jobs`** | Sudah berbentuk job-queue; cek dulu sebelum bikin antrean baru |
| Category master | **`public.kol_categories`** (+ `taxonomy_key`, mig 029) | **JANGAN bikin category master kedua** (§8) |

### 3.3 Kolom baru yang benar-benar diperlukan (aditif, nullable)

Pola yang sama dengan mig 036–039: hanya `ADD COLUMN`, nullable, tanpa DEFAULT.

| Kolom | Tabel usulan | Untuk apa | Prasyarat |
|---|---|---|---|
| `posting_cadence` varchar(16) | `l2_gold.kol_profile_card` | Label 4-level `taksonomi_kol.Posting Cadence` | **Ambang Dormant ">2 bulan" harus diputuskan** (§9 HOLD) |
| `performance_archetype` varchar(32) | `l2_gold.kol_profile_card` | Reach Driver / Engagement Driver | Aman — kedua input sudah ada |
| `sentiment_archetype` varchar(32) | `l2_gold.kol_profile_card` | Beloved / Backlash-Prone / Polarizing | **Blocked** — `*_comments_analysis` 0 baris |
| `category_basis` varchar(16) | `l2_gold.kol_profile_card` | live / calculated / estimated — **provenance** | Aman. **Paling tinggi nilainya per biaya**: inilah yang mencegah kategori hasil model dipakai sebagai hard filter |
| `sub_category_ids` (array) | `public.kol_directory` | L2 Sub Category | Butuh master L2 dulu (§3.5) |
| Kolom skor campaign × KOL | `public.campaign_kols` | `campaign_fit`, `unified_match`, `style_fit`, `personality_fit`, `tone_fit`, `comm_style_fit` | **HOLD** — 4 dari 6 bergantung Style/Personality yang belum ada |

### 3.4 Junction / mapping table yang diperlukan

| Tabel usulan | Grain | Kenapa junction, bukan kolom |
|---|---|---|
| `kol_content_style` | (kol, style) | Satu kreator bisa punya >1 content style; Excel memakai `Content Style × Content Style` sebagai matriks, bukan kesetaraan. **HOLD sampai §5 diputuskan** |
| `kol_personality` | (kol, personality) | idem, many-to-many. **HOLD** |
| `brand_niche_subcategory_crosswalk` | (niche, sub_category) | 183 baris crosswalk Excel dengan `Score` per baris. **HOLD — butuh L2 dulu** |
| `kol_category_alias` | (raw `kol_categories.name`, kode taxonomy) | Memetakan 28 baris mentah ke kode. **Excel sendiri menandai ini "the alias table the backend plan is waiting on, owner: Product"** dan baru memetakan 5 dari 28 → **HOLD** |

### 3.5 Reference / master table yang diperlukan

| Tabel usulan | Isi | Status |
|---|---|---|
| `kol_sub_categories` | 42 node L2 dengan kode ber-namespace (`BEA.SKN`, `FOD.CUL`, …) + parent | **Paling jelas dibutuhkan.** Excel: "Needs `public.kol_sub_categories` plus `kol_directory.sub_category_ids`" |
| `content_style_master` | 10 Content + 8 Communication | **HOLD** (§5) |
| `personality_master` | 12 Creator + 10 Brand + 8 Tone | **HOLD** (§5) |
| `brand_industry` / `brand_niche` | 12 industry + 24 niche | **HOLD** — CMP_README r16 justru **membuang** Industry karena DB tidak punya konsepnya |
| **`match_config`** (key → value) | 46 konstanta + 9 matriks relevansi + 5 band | **Rekomendasi kuat.** README r47: "Load the Lookup_Lists blocks from configuration, not from constants in the source. A redeploy is the wrong unit of change" |
| `city_master` | daftar kota | **HOLD** — Excel menulis "Master city list" tanpa melampirkan listnya |

### 3.6 Yang SENGAJA tidak gue usulkan

| Ditolak | Alasan |
|---|---|
| Tabel `brands` baru | `public.brand` sudah ada. Dua tabel brand = dua sumber kebenaran |
| Tabel category master baru | `kol_categories` sudah ada + `taxonomy_key`. Menambah yang kedua mengulangi kesalahan yang sudah didokumentasikan |
| Tabel skor brand-match baru | `feature.brand_fit_analysis` sudah punya grain dan `sub_scores` jsonb |
| Kolom `emv` baru | `feature.*_audience_analysis.emv` sudah ada — yang tidak ada **definisinya** (§4) |
| Menyimpan `Final Match Score` sebagai kolom yang di-query | Filter_Logic r19: "Computed, not stored. Apply after ranking, never inside the SQL" |
| Mengisi kolom mana pun dengan default/tebakan | Pola yang sudah ditetapkan mig 037/038: kolom kosong yang menunggu keputusan bisnis hanya mengundang orang mengisinya dengan tebakan |

---

## 4. KHUSUS EMV / CPV / CPE

### 4.1 Temuan utama — **EMV tidak terdefinisi di ketiga Excel**

Gue memindai seluruh 51 sheet untuk string `EMV`, `earned media`, `earned value`.
Hasilnya **hanya 3 kemunculan, dan tidak satu pun berisi definisi**:

| # | Lokasi | Teks apa adanya | Ini definisi? |
|---|---|---|---|
| 1 | `brand_style_personality` → DB vs Hardcode | "Brand · Database · … · **Can support brand-level EMV/CPV**" | **Bukan.** Hanya pernyataan kelayakan |
| 2 | `brand_match_master` → Discovery_Filters r42 | Estimated ROI · sumber DB: "**EMV ÷ rate**" | **Bukan.** EMV dipakai sebagai input tanpa pernah dijelaskan |
| 3 | `brand_match_master` → CMP_Hard_vs_Soft_Filter r54 | "not measurable on this roster — **EMV ÷ rate** (0%)" | **Bukan.** Idem |

Yang ada sebagai gantinya adalah **`Estimated ROI`**, dan *itu* punya formula
penuh. Jadi: **Excel tidak pernah mendefinisikan EMV.** Gue tidak mengarang
satu pun.

**Satu-satunya definisi EMV yang ada di lingkungan ini justru dari DB, bukan
dari Excel** — dan ia berstatus butuh konfirmasi:

```
feature.ig/tt_audience_analysis.emv  (numeric, L2 METRIC planned)
  formula rencana : reach × CPM ÷ 1000 × multiplier
  status          : BLOCKED + NEED CONFIRMATION
  penghambat 1    : avg_reach belum ada — unified_post.reach NULL 0/221
  penghambat 2    : konstanta CPM TIDAK ADA di database
                    (pencarian %cpm%, %benchmark%, %multiplier%,
                     %coefficient%, %formula% di 7 schema: 0 hasil)
  penghambat 3    : nilai "multiplier" tidak pernah dinyatakan
```
*(E1 §1.3, §5.2, §12.4 butir 3)*

**Dua definisi ini tidak sama.** DB: `reach × CPM ÷ 1000 × multiplier`.
Excel (untuk ROI): `Estimated Reach × ER% × 9.000 IDR ÷ Rate`. Yang kedua
memakai **value-per-engagement**, bukan CPM. **NEED PRODUCT DECISION.**

### 4.2 Mapping lengkap: Excel → DB → formula → grain → readiness

| Metric | Excel source | Formula **apa adanya dari Excel** | DB source | Grain | Readiness |
|---|---|---|---|---|---|
| **CPV** | `KOL_Database.AO` (formula) · Discovery_Filters r38 · Lookup §10 #17 | `= Rate Card ÷ Average Views`, dibulatkan 2 desimal. Guard: kalau Rate atau Avg Views kosong/0 → `""` (bukan 0) | Excel: "rate ÷ views". **Tidak ada kolom `cpv` di DB** | **per KOL (akun)** | **MISSING** — tidak ada kolom, dan `unified_rate_card` 0 baris |
| **CPE** | `KOL_Database.AP` (formula) · Discovery_Filters r39 · Lookup §10 #18 | `= Rate Card ÷ (Average Views × ER% ÷ 100)`, bulat 0 desimal. Penyebutnya **engagement hasil estimasi dari views × ER**, bukan engagement terukur | `feature.ig/tt_audience_analysis.cpe`. **Formula DB BEDA**: `unified_rate_card.fee ÷ total_engagement` (engagement nyata) | **per KOL (akun)** | **PARTIAL (kolom) / MISSING (data)** — kolom ada; `unified_rate_card` **0 baris**. **Dua formula berbeda → NPD** |
| **CPM** | `KOL_Database.AQ` (formula) · Discovery_Filters r40 · Lookup §10 #19 | `= Rate Card ÷ Followers × 1000`, bulat 0 desimal | Excel: "rate ÷ followers × 1.000". **Tidak ada kolom** | **per KOL (akun)** | **MISSING**. Catatan: ini CPM *harga kreator*, **beda** dari "konstanta CPM" yang dibutuhkan EMV — **jangan dicampur** |
| **EMV** | 3 kemunculan, **0 definisi** | **tidak ada** | `feature.*_audience_analysis.emv` — `reach × CPM ÷ 1000 × multiplier` | **per KOL (akun)** | **HOLD — NEED PRODUCT DECISION.** Butuh: (1) definisi resmi, (2) konstanta CPM, (3) nilai multiplier, (4) `reach` dari Insights API |
| **Estimated Reach** | `KOL_Database.AR` (formula) | `= Average Views × 1,15 + Followers × 0,12` (`CAL_REACH_VIEWS`, `CAL_REACH_FOLL`) | `feature.*_audience_analysis.avg_reach` = `AVG(unified_post.reach)` | **per KOL** | **MISSING (DB)** — `reach` NULL 0/221, butuh Insights. **Formula Excel adalah proksi tanpa reach — layak dipertimbangkan sebagai jalan pintas, dan wajib ditandai `estimated`** |
| **Estimated ROI** | `KOL_Database.AS` (formula) · Filter_Logic r26 · Lookup §10 #21 | `= Estimated Reach × ER% ÷ 100 × 9.000 ÷ Rate Card` (`CAL_VALUE_PER_ENG`=9000 IDR) | Discovery_Filters r42: "EMV ÷ rate" | **per KOL** | **MISSING**. **Dua rumus untuk satu kolom, di file yang sama** → NPD |
| **Cost Efficiency** | `KOL_Database.BD` (formula) | `= MIN(100, CAL_MEDIAN_CPE ÷ CPE × 100)`; `CAL_MEDIAN_CPE = 1.472,5` — **turunan roster 30 contoh, bukan angka bisnis** | — | **per KOL, relatif ke populasi** | **MISSING**. Median harus dihitung ulang atas populasi nyata |
| **Rate Card (IDR)** | `KOL_Database.AN` (input) | input manual | `l1_silver.unified_rate_card.fee` · `kol_profile_card.rate_card_*` | **per KOL × post_type** | **MISSING** — **0 baris di 5 tabel sekaligus** (l0_extra, l0_harmonization, l1_silver). Bukan gap ETL: **tidak ada data masuk di L0 sekalipun** |
| **reach** | `Estimated Reach` (proksi) | — | `unified_post.reach` | **per post** | **MISSING** — NULL 0/221, butuh Insights API (metric pemilik akun) |
| **impressions** | tidak ada di Excel | — | `public.campaign_content_performance.impressions` · `public.campaign_kols.impressions` | **per campaign-content / campaign-KOL** | **MISSING (data)** — tabelnya 0 baris. **Ini input manual campaign, bukan hasil scraping** |
| **views** | `Average Views`, `Median Views` | `AVG`/`MEDIAN(views)` | `unified_post.views` → `feature.*_engagement_analysis.avg_views`/`median_views` · `l2_gold.post_metric.views` | post → agregat per KOL | **PARTIAL** — 21 kreator; IG hanya 54/130 post punya views |
| **engagement** | `ER (%)` | Excel: `(Likes+Comments+Shares) ÷ Followers` | `kol_directory.engagement_rate` = `AVG(likes+comments) ÷ followers × 100` | post → per KOL | **PARTIAL — formula beda (shares)** → NPD |
| **Campaign performance** | tidak ada sheet khusus | — | `public.campaign_content_performance` | per campaign-content | **MISSING (data)** — 0 baris |

### 4.3 Klasifikasi grain — jawaban eksplisit

| Metric | Atribut KOL | Metric campaign | Metric campaign×KOL | Metric post | Derived |
|---|:-:|:-:|:-:|:-:|:-:|
| CPV, CPE, CPM | ✅ | | | | ✅ |
| EMV | ✅ *(sesuai kolom DB)* | | | | ✅ |
| Estimated Reach, Estimated ROI, Cost Efficiency | ✅ | | | | ✅ |
| Rate Card | ✅ *(× post_type)* | | | | |
| reach, views, engagement | | | | ✅ | |
| impressions | | | ✅ | | |
| Campaign performance | | ✅ | ✅ | | |

**Catatan penting soal grain:** seluruh metric biaya di Excel bergrain **KOL**,
bukan campaign. Padahal CPV/CPE/CPM yang dipakai orang marketing biasanya
**per campaign** (biaya nyata yang dibayar ÷ hasil nyata). Excel memodelkan
**harga rate-card**, bukan **biaya campaign**. Keduanya sah, tapi bukan hal yang
sama — dan `campaign_kols` + `campaign_content_performance` adalah tempat versi
campaign-nya akan hidup. **Perbedaan ini harus disepakati sebelum kolom mana pun
diisi.**

---

## 5. KHUSUS STYLE / PERSONALITY

Tiga hal ini **sengaja gue pisah** dan tidak dicampur, sesuai instruksi — dan
kebetulan Excel juga memisahkannya (Unified_Spec r16: "Style and personality are
NOT merged into generic category labels").

### 5.1 CATEGORY — sumbu "apa yang kreator buat"

Ada di DB. Bukan bagian dari Style/Personality. Dibahas terpisah di §8.
Excel menegaskan tiga sumbu yang tidak boleh dicampur (Taxonomy §A):

| Sumbu | Pertanyaan | Disimpan di DB |
|---|---|---|
| **CONTENT** | Apa yang kreator buat? | `kol_directory.category_ids → kol_categories` (L1 saja) |
| **AUDIENCE** | Siapa yang menonton? | `audience_demographics_daily`, `audience_geo_daily`, `audience_interest_daily` |
| **FORMAT** | Bagaimana dibuatnya? — **inilah Content Style + Communication Style** | **tidak ada kolom** |

### 5.2 STYLE — 18 nilai, 2 grup, **NOL representasi di DB**

Sumber: `brand_style_personality.Style List` (kolom `Count in DB` = 0 untuk
seluruh 18 baris) + `Lookup_Lists` kolom `ContentStyle` dan `CommStyle`.

| Grup | Nilai | Ada di DB? |
|---|---|:-:|
| **Content Style** (10) | Educational · Tutorial · Review · Storytelling · Aesthetic · Entertaining · Vlog · Demo · Talking Head · Comedy | ❌ semuanya |
| **Communication Style** (8) | Educational · Storytelling · Demonstrative · Conversational · Data-driven · Visual-first · Humorous · Testimonial | ❌ semuanya |

Catatan: `Educational` dan `Storytelling` muncul di **kedua** grup. Itu bukan
duplikat — dua sumbu berbeda yang berbagi label, dan Excel memakai matriks
terpisah untuk masing-masing (matriks 9 untuk Content×Content, matriks 8b untuk
Comm×Content).

**Bukti ketiadaannya, apa adanya dari CMP_Validation r61:**
> "Creator personality / tone / values / content style — **no column exists** —
> never built — Brand Personality Fit is N/A on all 120 rows. Its full 10% is
> redistributed across the other five components. Verified how: *no column on
> `kol_directory`, `kol_profile_card` or any feature table*."

**Di mana Style dipakai oleh engine** (jadi ini biaya ketiadaannya):

| Pemakai | Bobot |
|---|---|
| Content & Category Relevance → `Content Style Match` (matriks 9) | 20% dari komponen 20% = **4% skor akhir** |
| Brand Personality Fit → `Tone vs Content Style` (matriks 8) | 25% dari komponen 10% = **2,5%** |
| Brand Personality Fit → `Communication Style Match` (matriks 8b) | 15% dari komponen 10% = **1,5%** |
| Campaign Fit → `Style Fit` | **30% dari Campaign Fit** |
| Campaign Fit → `Communication Style Fit` | **15% dari Campaign Fit** |

### 5.3 PERSONALITY — 30 nilai, 3 grup, **NOL representasi di DB**

Sumber: `brand_style_personality.Personality List` (`Count in DB` = 0 untuk
seluruh 30 baris) + `Lookup_Lists` kolom `CreatorPersonality`,
`BrandPersonality`, `BrandTone`.

| Grup | Nilai | Ada di DB? |
|---|---|:-:|
| **Creator Personality** (12) | Professional · Educational · Creative · Tech-savvy · Reviewer · Relatable · Casual · Premium · Luxury · Entertaining · Humorous · Inspirational | ❌ semuanya |
| **Brand Personality** (10) | Professional · Innovative · Friendly · Premium · Playful · Educational · Authentic · Bold · Caring · Modern | ❌ semuanya |
| **Brand Tone** (8) | Formal · Informative · Warm · Aspirational · Playful · Inspiring · Straightforward · Conversational | ❌ semuanya |

Tambahan yang **tidak** ada di `brand_style_personality` tapi ada di
`Lookup_Lists` — dan ikut dipakai komponen Personality:

| Vocabulary | Nilai | Ada di DB? |
|---|---|:-:|
| `Value` (Brand Values / Creator Values) | Trust · Innovation · Quality · Transparency · Sustainability · Affordability · Community · Empowerment · Authenticity · Craftsmanship · Health · Family · Fun · Performance | ❌ |
| `Positioning` | Value · Mass · Mid-market · Premium · Luxury | ❌ |

`Brand Positioning` menarik: Excel **sengaja tidak memberinya bobot**, dan
alasannya layak dicatat (README r29) — "yang jujur untuk menimbang positioning
Premium/Luxury adalah kualitas produksi, dan tidak ada sinyal kualitas produksi
terukur di roster. Mengarangnya = kesalahan yang sama dengan 4 preset chip yang
me-ranking berdasarkan hash creator id. Beri bobot pada hari sinyal nyatanya
ada."

### 5.4 Rekomendasi bentuk penyimpanan — dengan alasannya

| Opsi | Cocok untuk | Kenapa / kenapa tidak |
|---|---|---|
| **Kolom langsung** (satu nilai per KOL) | ❌ **tidak direkomendasikan** | Tiga bukti bahwa ini many-to-many: (1) `Creator Values` di `KOL_Database.AL` berisi **list** ("Quality, Trust, Innovation, …") dengan 5 slot token; (2) matriks 7/8/8b/9 menilai **kedekatan**, bukan kesetaraan — artinya satu kreator wajar punya beberapa label dengan derajat berbeda; (3) `Content Style` dan `Communication Style` adalah **dua pertanyaan berbeda** atas objek yang sama |
| **Master/reference table** | ✅ **wajib, sebagai fondasi** | `content_style_master` (10+8, dengan kolom `group`) dan `personality_master` (12+10+8, dengan kolom `group`). Alasannya: nilainya **dipakai di dua sisi** (brand dan kreator) — dan tanpa satu master, sisi brand dan sisi kreator akan mengeja hal yang sama secara berbeda, yang persis kesalahan yang sudah didokumentasikan untuk `kol_categories` |
| **Many-to-many attribute** | ✅ **bentuk yang benar untuk sisi KOL** | `kol_content_style(kol_id, style_id, group, basis, confidence)` dan `kol_personality(kol_id, personality_id, group, basis, confidence)`. Kolom `basis` **tidak opsional**: label ini akan datang dari klasifikasi model, dan Excel sudah menetapkan aturannya — sinyal hasil model boleh me-ranking, **tidak boleh jadi hard filter** |
| **jsonb pada `kol_profile_card`** | ⚠️ alternatif murah | Cukup untuk membaca, tapi tidak bisa di-join ke master, tidak bisa di-index per-nilai, dan tidak bisa membawa `basis` per label dengan rapi. Pakai hanya kalau targetnya sekadar menampilkan |

**Tapi keputusan bentuk BUKAN yang menghambat.** Yang menghambat ada di
`brand_style_personality.DB vs Hardcode` sendiri: *"Needs creator/brand
assignment"*. Struktur apa pun akan kosong sampai ada yang menjawab:

| Pertanyaan yang harus dijawab Product | Kenapa penting |
|---|---|
| Siapa/apa yang menetapkan style & personality seorang kreator? | Manual oleh tim, atau klasifikasi otomatis dari caption? |
| Kalau otomatis — dari sinyal apa? | Caption tersedia hanya untuk **50 dari 6.991 kreator (0,72%)**. Klasifikasi otomatis hari ini akan menghasilkan label untuk <1% roster |
| Berapa banyak label per kreator? | Excel memakai **satu** nilai `Content Style` per kreator di `KOL_Database.AJ` tapi **list** untuk `Creator Values` — tidak konsisten |
| 18 + 30 nilai ini final, atau masih bisa berubah? | Kalau masih cair, master table dulu, junction belakangan |

**Rekomendasi gue: JANGAN bikin tabelnya sekarang.** Bikin master + junction
tanpa cara mengisinya menghasilkan 4 tabel kosong yang mengundang orang
mengisinya dengan tebakan — pola yang sudah ditolak eksplisit di header
migration 037/038. Yang paling berguna dikerjakan lebih dulu adalah **menaikkan
coverage caption** (0,72%), karena tanpa itu tidak ada jalan untuk mengisi
label ini selain input manual 7.000 baris.

---

## 6. KHUSUS BRAND MATCH / BRAND FIT

### 6.1 Rule dan bobot — **apa adanya dari Excel, tidak ada yang gue karang**

**Formula utama** (README r21, Lookup_Lists §4, dikonfirmasi CMP_Validation #7):

```
FINAL MATCH = ( Brand&Business × 20
              + TargetAudience × 30
              + Content&Category × 20
              + BrandPersonality × 10
              + Performance × 10
              + BrandSafety × 10 ) ÷ Σbobot
```

Engine membagi dengan **Σbobot**, bukan literal 100, supaya workbook yang
bobotnya diedit tetap menghasilkan 0–100. `CHECK_WEIGHT_TOTAL` = 100 (OK).

**Sub-bobot — 22 angka:**

| Komponen | Sub-skor (key · bobot) |
|---|---|
| Brand & Business 20% | `W_BB_INDUSTRY` 40 · `W_BB_CATEGORY` 30 · `W_BB_KEYWORD` 30 |
| Target Audience 30% | `W_TA_AGE` 25 · `W_TA_GENDER` 15 · `W_TA_LOCATION` 30 · `W_TA_INTEREST` 30 · `W_TA_PRIORITY_BONUS` **12** |
| — Location dipecah lagi | `W_LOC_COUNTRY` 50 · `W_LOC_REGION` 25 · `W_LOC_CITY` 25 |
| Content & Category 20% | `W_CC_CATEGORY` 30 · `W_CC_SUBCATEGORY` 20 · `W_CC_TOPIC` 30 · `W_CC_STYLE` 20 |
| Brand Personality 10% | `W_BP_PERSONALITY` 35 · `W_BP_TONE` 25 · `W_BP_VALUES` 25 · `W_BP_COMM` 15 |
| Performance 10% | `W_PQ_ER` 35 · `W_PQ_AUDIENCE` 20 · `W_PQ_CONSISTENCY` 20 · `W_PQ_COMMUNITY` 10 · `W_PQ_VIEWS` 10 · `W_PQ_GROWTH` 5 |
| Brand Safety 10% | `W_BS_BASE` 80 · `W_BS_SATURATION` 20 |

**Aturan priority bonus:** dimensi yang dinamai `audience_priority` dapat
+12 poin; tiga dimensi lain masing-masing **dipotong sepertiga bonus** (−4), jadi
totalnya tetap 100. Contoh terhitung di sheet: prioritas Interest →
21 / 11 / 26 / 42.

### 6.2 Konstanta, band, dan threshold — 46 angka, dikutip persis

| Blok | Key | Nilai | Arti |
|---|---|---:|---|
| RISK MULTIPLIER | `RISK_HIGH` | **0,6** | pengali atas Brand Safety |
| | `RISK_MEDIUM` | **0,85** | |
| | `RISK_LOW` | **0,95** | |
| | `RISK_NONE` | **1** | |
| NORMALISASI | `CAL_ER_TARGET` | **6** | ER (%) yang bernilai 100 |
| | `CAL_AGE_TARGET` | **45** | share band primer (+½ sekunder) yang bernilai 100 |
| | `CAL_GENDER_TARGET` | **65** | share gender mayoritas yang bernilai 100 |
| | `CAL_VFR_TARGET` | **0,5** | views-per-follower yang bernilai 100 |
| | `CAL_GROWTH_TARGET` | **8** | growth bulanan (%) yang bernilai 100; **−2% bernilai 0** |
| | `CAL_VALUE_PER_ENG` | **9.000 IDR** | earned value 1 engagement — dipakai Estimated ROI |
| | `CAL_REACH_VIEWS` | **1,15** | faktor views pada Estimated Reach |
| | `CAL_REACH_FOLL` | **0,12** | faktor follower pada Estimated Reach |
| | `CAL_MEDIAN_CPE` | **1.472,5** | **turunan roster contoh 30 KOL — bukan angka bisnis** |
| | `CAL_NEUTRAL` | **50** | skor saat **brand** mengosongkan preferensi |
| | `CAL_UNRELATED` | **20** | dasar tangga relevansi |
| MATCH LEVEL | `BAND_EXCELLENT` / `STRONG` / `GOOD` / `MODERATE` | **90 / 80 / 70 / 60** | di bawah 60 = Low Match |
| RECOMMENDATION | `REC_HIGH` / `REC_MID` / `REC_LOW` | **85 / 72 / 60** | di bawah 60 = Low Priority |
| CONFIDENCE | `CONF_HIGH` / `CONF_MEDIUM` | **100 / 84** | atas Data Completeness % dari **12 field** |
| EXPLANATION | `EXP_CONSIDERATION` | **75** | komponen di bawah ini ditulis sebagai *consideration* |
| OPPORTUNITY | `W_OP_HEADROOM` / `COST` / `GROWTH` / `ER` | **35 / 25 / 25 / 15** | headroom = 100 − saturation |

**Aturan missing-data — ini yang paling penting dan paling mudah salah
diterjemahkan** (README r28):

| Situasi | Skor | Kenapa |
|---|---|---|
| **Brand** mengosongkan preferensi | **50** (`CAL_NEUTRAL`) | bukan hadiah, bukan hukuman |
| **Kreator** tidak punya pengukuran | **0** | "sudah dicari, tidak ada" |
| Blok CMP: input tidak ada di server | **N/A → keluar dari rata-rata tertimbang, bobot direnormalisasi** | "0 adalah pengukuran. Memakainya untuk 'tidak ada yang mengukur' akan menempatkan kreator tak terukur di bawah kreator yang buruk" |

Tiga perlakuan berbeda untuk tiga situasi berbeda. **Jangan disamakan.**

### 6.3 Sembilan matriks relevansi — tangga 100/80/60/40/20

| # | Matriks | Ukuran | Menggerakkan | Ada di DB? |
|---|---|---|---|:-:|
| 5 | Industry × Creator Category | 12 × 14 | Industry Match | ❌ |
| 6 | Category × Category | 14 × 14 | Content Category Match + fallback | ❌ |
| 7 | Brand Personality × Creator Personality | 10 × 12 | Personality Match | ❌ |
| 8 | Brand Tone × Content Style | 8 × 10 | Tone vs Content Style | ❌ |
| 8b | Communication Style × Content Style | 8 × 10 | Communication Style Match | ❌ |
| 9 | Content Style × Content Style | 10 × 10 | Content Style Match | ❌ |
| 11d | **Canonical Category × Canonical Category** | **9 × 9** | Category Match (blok CMP) | ❌ tapi **kedua sumbunya nilai DB nyata (`taxonomy_key`)** |
| 2 | Sub Category → Parent Category | 42 baris | tangga Category/SubCategory | ❌ |
| 11b | ER target per tier | 5 baris | ER Score | ❌ |

Matriks 7 tidak simetris dan itu disengaja — "Innovative dijawab oleh kreator
Tech-savvy (100) atau Creative (95), bukan hanya oleh yang menyebut dirinya
Innovative (70)".

**Matriks 11d adalah satu-satunya yang bisa dipakai hari ini** karena kedua
sumbunya `kol_categories.taxonomy_key`, dan `taxonomy_key` sudah ada di DB
(migration 029). Delapan lainnya memerlukan vocabulary yang tidak ada di DB.

### 6.4 Brand Fit vs Brand Match — **dua hal berbeda, jangan disatukan**

| | Brand Match | Brand Fit |
|---|---|---|
| Asal | **Didefinisikan oleh workbook ini** | Sudah ada di DB sebelum workbook |
| DB | tidak ada kolom | `feature.brand_fit_analysis.partnership_score` |
| Status | Discovery_Filters r43: **"NEW — didefinisikan workbook ini"** | Discovery_Filters r44: **"BLOCKED BY DATA — 0 baris"** |
| Algoritma | lengkap: 6 komponen, 22 sub-skor, 9 matriks | **belum didefinisikan** (E1 §5.2 NEED DEFINITION) |
| Di UI | `minBrandMatch` | `minBrandFit`, field `k.aff`/`k.match` |
| Grain | brand × KOL | brand × KOL |

Grain-nya sama. `feature.brand_fit_analysis` punya `partnership_score` +
`sub_scores` **jsonb** + `category_fit_tags` + `recommendations` +
`overlap_summary`. Itu **persis** bentuk output yang dihasilkan
`Matching_Engine` + `Match_Explanation`.

**Rekomendasi:** pakai `feature.brand_fit_analysis` sebagai rumah hasil Brand
Match, **bukan** tabel baru. Tapi ini **NEED PRODUCT DECISION**, karena kolom
itu dinamai untuk konsep lain dan memakainya ulang berarti memutuskan bahwa
"Brand Fit" dan "Brand Match" adalah satu hal. Kalau Product memutuskan keduanya
memang berbeda, dua rumah diperlukan — dan itu keputusan bisnis, bukan teknis.

### 6.5 Hard filter vs soft match — 21 vs 35

Aturan yang **wajib** dibawa ke backend (Filter_Logic r2, Taxonomy §G rule 6,
README r49):

> Angka hasil model boleh **me-ranking**, tidak boleh **menggerbang**.
> Kategori sebagai HARD FILTER sah hanya terhadap basis `live`. Diterapkan pada
> basis `estimated`, ia menghapus kreator atas dasar tebakan.

> Jangan pernah melipat hard filter ke dalam SQL kalau ia bersandar pada nilai
> terhitung — roster dipaginasi di server, dan memfilter halaman yang sudah
> diambil menghasilkan jumlah hasil yang tidak bermakna.

**Urutan operasi yang ditetapkan Excel** (README r48): hitung 6 komponen →
Final Match Score → evaluasi hard filter (`Minimum Brand Match` butuh skornya) →
ranking.

### 6.6 Yang TIDAK ada score/threshold-nya di Excel — jangan diarang

| Konsep | Kenapa tidak bisa ditentukan |
|---|---|
| **EMV** | tidak ada definisi (§4.1) |
| `Brand Fit Index` | muncul sebagai kolom output `Matching_Engine`, **formulanya tidak dijelaskan** di sheet mana pun |
| `Hidden Gem Score` | Discovery_Filters r53 hanya menulis "butuh ER + audience quality + saturation" — **tanpa bobot** |
| `Trending Score`, `Rising Score`, `Relevance Score` | dinamai di Lookup §10, **tanpa formula**. `Relevance Score` disebut "Final Match Score × Confidence" di Discovery_Filters r54 — tapi Confidence itu label (High/Medium/Limited Data), bukan angka |
| `Engagement Quality Index` | Lookup §10 #4, tanpa definisi |
| `Content Quality` | kolom `KOL_Database.AM` berisi angka (86, …) tapi **tidak ada sumber maupun formula** |
| `Purchase Intent` | dropdown Low/Medium/High, **tanpa aturan penentuan** |
| `Competitor Saturation` | dipakai di 4 tempat, **tidak dijelaskan cara menghitungnya** |
| Ambang Dormant ">2 bulan" | ada kalimatnya di `taksonomi_kol`, tidak ada di kode/DB |

---

## 7. KHUSUS 7 "WHAT MATTERS MOST WHEN EVALUATING CREATORS?"

### 7.1 Temuan pertama: **ketujuh item itu TIDAK berasal dari ketiga Excel ini**

Gue memindai seluruh 51 sheet — dan juga `filter.xlsx`, `deliv.xlsx`,
`mapping filter database.xlsx`, `KOL_DISCOVERY_AUDIT.xlsx`, serta seluruh
`docs/*.md` — untuk frasa `what matters`, `Strong Engagement`, `High Reach`,
`Consistent Performance`, `Strong Company/Community`.

| Yang dicari | Hasil di 3 Excel | Hasil di file lain |
|---|---|---|
| "What matters most" | **0 hit** | 0 hit |
| "Strong Engagement" | **0 hit** | 0 hit |
| "High Reach" | **0 hit** | 0 hit |
| "Consistent Performance" | **0 hit** | 0 hit |
| "Strong Company/Community" | **0 hit** | 0 hit |
| "High Audience Quality" | 0 hit *(tapi "Audience Quality" ada)* | ada di 4 file |
| "Content Quality" | **ada** — 1 kolom `KOL_Database.AM` | 0 hit |
| "Brand Safety" | **ada** — komponen ke-6 | 0 hit |

**Kesimpulan: 5 dari 7 label itu tidak ada sumbernya di ketiga Excel ini.**
Kemungkinan besar berasal dari UI/survei/deck di luar scope audit ini. Gue
**tidak** mengarang definisinya.

### 7.2 Temuan kedua: strukturnya ada, cuma namanya lain

Meski labelnya tidak ada, **6 dari 7 kriteria punya padanan yang nyaris
satu-lawan-satu** dengan sub-skor `Performance Quality` + komponen
`Brand Safety`. Ini pemetaan yang paling masuk akal — tapi **tetap dugaan gue,
bukan klaim dari Excel**:

| # | Kriteria (dari luar Excel) | Padanan di Excel | Bobot Excel | DB Schema.Table.Column | Coverage | Status |
|---|---|---|---|---|---:|---|
| 1 | **Strong Engagement** | `Engagement Rate Score` (`W_PQ_ER`) | **35%** dari Performance | `public.kol_directory.engagement_rate` | 24,7% | **PARTIAL** — formula beda (tanpa shares) |
| 2 | **High Audience Quality** | `Audience Quality Score` (`W_PQ_AUDIENCE`) | **20%** | `feature.ig/tt_audience_analysis.audience_quality_score` + `audience_quality_tier` (mig 039) | **0,34%** | **PARTIAL** — kolom ada, algoritma **NEED DEFINITION** |
| 3 | **Consistent Performance** | `Consistency Score` (`W_PQ_CONSISTENCY`) | **20%** | — tidak ada kolom. Proksi: `performance_stability` (mig 039, stddev ER) + `post_frequency_*` | 0% | **MISSING** — Discovery_Filters r32: "nol kolom consistency/cadence" |
| 4 | **Strong Company/Community** | `Community Score` (`W_PQ_COMMUNITY`) | **10%** | — | 0% | **MISSING** — "no column anywhere in public, feature or l2_gold" |
| 5 | **High Reach** | `Average Views Score` (`W_PQ_VIEWS`, dinormalisasi sebagai views-per-follower) | **10%** | `feature.*_engagement_analysis.avg_views` · `view_to_follower_ratio` | 0,29% | **PARTIAL**. ⚠️ **`reach` ≠ `views`** — E1 Backlog:157 memperingatkan eksplisit. `unified_post.reach` NULL 0/221 |
| 6 | **Content Quality** | `KOL_Database.AM` `Content Quality` | **0%** — **tidak dipakai formula mana pun** | — | 0% | **MISSING + NPD**. Kolomnya ada isinya di Excel (86, …) tapi tanpa sumber, tanpa formula, dan **tidak masuk skor** |
| 7 | **Brand Safety** | Komponen ke-6 penuh: `W_BS_BASE` 80 + `W_BS_SATURATION` 20 × risk multiplier | **10% skor akhir** | — tidak ada kolom risk-level. Versi CMP bisa dihitung dari `authenticity_score` 40 / `follower_quality_score` 30 / `verified_status` 15 / `paid_ratio` 15 | 0,34% (3 dari 4 input punya kolom) | **PARTIAL** — dan Excel menandai versi CMP sebagai *integrity screen*, **bukan** brand safety |

Yang tersisa satu: **`Recent Growth`** (`W_PQ_GROWTH` 5%) ada di Excel tapi tidak
ada di daftar 7 kriteria. Jadi kedua daftar itu **hampir** sama, bukan sama.

### 7.3 Kalau 6 dari 7 dipetakan ke Performance Quality, konsekuensinya

Performance Quality hanya **10% dari Final Match Score**. Artinya kalau daftar 7
kriteria itu mewakili apa yang paling penting bagi pengguna, maka **model Excel
memberi bobot 10% pada hal-hal yang pengguna sebut paling penting**, sementara
`Target Audience Relevance` sendirian dapat 30%. Ini ketidakselarasan yang
nyata dan **perlu dibawa ke Product** — bukan bug, tapi juga bukan hal yang
boleh dilewatkan diam-diam.

### 7.4 Klasifikasi ketujuhnya

| Kriteria | reference/config | attribute KOL | scoring criteria | filter | derived metric |
|---|:-:|:-:|:-:|:-:|:-:|
| Strong Engagement | | ✅ | ✅ | ✅ HARD (`minErPct`) | ✅ |
| High Audience Quality | | ✅ | ✅ | ✅ HARD (`minAudienceQuality`) | ✅ |
| Consistent Performance | | | ✅ | ✅ SOFT (`minConsistency`) | ✅ |
| Strong Company/Community | | | ✅ | ✅ SOFT (Lookup §10 #16) | ✅ |
| High Reach | | ✅ | ✅ | ✅ SOFT (`minAvgViews`) | ✅ |
| Content Quality | | ✅ | ❌ **tidak dipakai** | ❌ | ❓ |
| Brand Safety | | | ✅ | ✅ HARD (`minBrandSafety`) | ✅ |

Bobot ketujuhnya sendiri bersifat **reference/config** — dan §3.5 mengusulkan
`match_config` sebagai rumahnya, bukan konstanta di source.

---

## 8. KHUSUS TAXONOMY — `taksonomi_kol` vs `Taxonomy` vs `kol_categories`

### 8.1 Temuan utama: **ADA TIGA TAXONOMY BERBEDA UNTUK SATU GAGASAN**

Ini overlap paling serius di seluruh audit, dan ia **di dalam Excel itu sendiri**
— bukan antara Excel dan DB.

| | `taksonomi_kol.Industry` | `brand_match_master.Taxonomy` | `public.kol_categories` |
|---|---|---|---|
| Level 1 | **10** Category | **14** L1 Category | **28** nama mentah → **9** `taxonomy_key` |
| Level 2 | **36** Subcategory | **42** L2 Sub Category (kode ber-namespace) | — tidak ada |
| Level 3 | — | **87** L3 Content Topic | — tidak ada |
| Sisi brand | — | **12** Industry + **24** Niche | — |
| Kode | tidak ada | ada (`BEA.SKN.ROUT`) | `taxonomy_key` (teks) |
| Keyword pencocok | tidak ada | ada, per node | tidak ada |
| Bahasa | EN | EN + ID | EN |

**Ketiganya tidak kompatibel.** Contoh konkret: `taksonomi_kol` punya
"Automotive → Motorcycles"; `Taxonomy` punya `AUT.MTR` "Motorcycle";
`kol_categories` punya "Automotive and motorsports" dengan `taxonomy_key`
**NULL** — jadi kreator yang hanya membawa baris itu **tetap tak berkategori**.

Dan `Taxonomy` sendiri (r42) mengkritik `kol_categories`:
> "`public.kol_categories` mencampur ketiga sumbu: 'Moms' adalah audiens dan
> 'Gen Z' adalah kelompok umur, keduanya duduk di kolom content. Hanya sumbu
> content yang boleh menyuapi tangga Category dan Sub Category."

Sebaliknya, CMP_README (r16) mengkritik `Taxonomy`:
> "taxonomy itu adalah vocabulary kedua yang **tidak sepakat dengan database di
> dua tempat** — ia memfilekan Moms di bawah Parenting dan membuang Gen Z,
> padahal `kol_categories` memberi keduanya key sendiri. **Mereka dibuang.**"

**Jadi Excel yang sama membuang taxonomy-nya sendiri di blok CMP dan kembali
memakai `kol_categories.taxonomy_key`.** Itu sinyal terkuat soal mana yang
menang.

### 8.2 Isi sebenarnya `public.kol_categories` — 28 baris, dari E3 §11a

| # | Nama mentah | Kreator | `taxonomy_key` | Catatan |
|---:|---|---:|---|---|
| 1 | Lifestyle | 2.442 | Lifestyle | canonical |
| 2 | Beauty | 1.206 | Beauty | canonical |
| 3 | Moms | 542 | Moms | canonical |
| 4 | Entertainment | 458 | Entertainment | canonical |
| 5 | Gen Z | 145 | Gen Z | canonical |
| 6 | Fashion | 73 | Fashion | canonical |
| 7 | Foodies | 63 | Food | melipat ke Food |
| 8 | Home Decor | 58 | Lifestyle | melipat ke Lifestyle |
| 9 | Food | 55 | Food | canonical |
| 10 | Fitness | 24 | Fitness | canonical |
| 11 | Sports | 24 | Fitness | melipat ke Fitness |
| 12 | Humor | 12 | Entertainment | melipat |
| 13 | Travel | 12 | Lifestyle | melipat |
| 14 | Automotive and motorsports | 9 | **(null)** | **tetap tak berkategori** |
| 15 | Cooking | 9 | Food | melipat |
| 16 | Parenting and family | 8 | Moms | melipat |
| 17 | Musicians | 7 | Entertainment | melipat |
| 18 | Medical | 6 | **(null)** | **tak berkategori** |
| 19 | Dance | 3 | Entertainment | melipat |
| 20 | Gym Enthusiast | 3 | Fitness | melipat |
| 21 | Story Teller | 3 | Entertainment | melipat |
| 22 | Gaming | 2 | Tech | melipat |
| 23 | Spirituality and religion | 2 | **(null)** | **tak berkategori** |
| 24 | Technology and gadgets | 2 | Tech | melipat |
| 25 | Animal Lovers | 1 | **(null)** | **tak berkategori** |
| 26 | Business and entrepreneurship | 1 | **(null)** | **tak berkategori** |
| 27 | Cyclist | 1 | Fitness | melipat |
| 28 | Environmentalism and sustainability | 1 | **(null)** | **tak berkategori** |

**9 canonical key:** Beauty · Entertainment · Fashion · Fitness · Food ·
Gen Z · Lifestyle · Moms · Tech.

Fakta yang perlu dicerna: **Lifestyle + Beauty = 3.648 dari 3.888 kreator
berkategori (93,8%)**, dan `Tech` — kategori yang paling dibutuhkan brand SaaS —
hanya **4 kreator** (DIST_Preference_Profiles r29). **6 baris ber-`taxonomy_key`
NULL**, jadi 20 kreator punya kategori yang tidak bisa dipakai apa-apa.

### 8.3 `kol_categories` sekarang **belum** mencakup taxonomy Excel

| Kebutuhan | Tercakup? |
|---|---|
| L1 Category | **Sebagian** — 9 key vs 10 (taksonomi_kol) vs 14 (Taxonomy). Tidak ada Tech/Finance/Education/Travel/Parenting/Gaming/Automotive/Home&Living sebagai key tersendiri yang lengkap |
| L2 Sub Category | **Tidak** — nol kolom |
| L3 Content Topic | **Tidak** sebagai taxonomy. `content_topic` (mig 039) memakai 18 key `audience_inference.INTEREST`, bukan 87 node |
| Brand Industry / Niche | **Tidak** |
| Alias 28 baris → kode | **Tidak** — Excel sendiri baru memetakan **5 dari 28**, sisanya "not read, left blank rather than guessed" |
| Hierarki berkode | **Tidak** — `taxonomy_key` teks datar, bukan pohon |

### 8.4 Rekomendasi taxonomy

| Langkah | Isi | Kenapa |
|---|---|---|
| 1 | **Jangan bikin category master baru.** `kol_categories` + `taxonomy_key` adalah sumber kebenaran | Blok CMP Excel sendiri membuang taxonomy alternatifnya dan kembali ke kolom ini |
| 2 | Isi **6 `taxonomy_key` yang NULL** | 20 kreator langsung dapat kategori. Paling murah, paling aman. **Tapi ini keputusan Product** — memberi key berarti memutuskan "Medical" masuk mana |
| 3 | Lengkapi alias 28 baris → kode | Excel memetakan 5; **23 sisanya butuh Product**. Excel menandai owner-nya: Product |
| 4 | Baru setelah itu: `kol_sub_categories` (42 node) + `kol_directory.sub_category_ids` | Ini yang membuka `Sub Category Match` (20% dari Content Relevance) dan filter `subCategories` |
| 5 | L3 Content Topic (87 node) **terakhir** | Excel benar: "topik adalah properti sebuah post, bukan akun". Rumahnya `feature.*_post_analysis.content_category` — yang **NULL di seluruh 212 baris**. Dan `content_topic` (mig 039) sudah menempati ruang konseptual yang sama dengan vocabulary berbeda → **NPD soal mana yang menang** |
| 6 | Bawa aturan `Taxonomy §G` apa adanya | 6 langkah klasifikasi: kategori existing selalu menang · bio ×2, caption ×1, interest hanya tie-break · L3 hit = 3 poin, L2 = 2, L1 = 1, di-roll-up ke induk · leader ≥6 & unggul ≥2 → L2+L1; ≥3 → L1; sisanya Uncategorized · maks 3 kategori/kreator · bawa `basis` (live/calculated/estimated) · **kategori hasil model me-ranking, tidak menggerbang** |

---

## 9. GAP LIST

### 9.1 READY — bisa langsung dipakai backend

| # | Item | Sumber DB | Catatan |
|---|---|---|---|
| 1 | 14 filter berstatus DONE | `kol_directory`, `platforms`, `kol_tiers`, `agency_kol_accounts` | Search, Handle, Platform ×2, Category, Tier, Followers, ER, Verified, Newly Added, Recently Updated + 2 exclusion berbasis state app |
| 2 | Age band kreator (5 bucket) | `kol_profile_card.creator_age_band` | **Identik** dengan `taksonomi_kol.Demografi` setelah mig 043 |
| 3 | Tier 5 level | `kol_tiers` | Siap; hanya sengketa batas yang perlu diputuskan |
| 4 | View-to-Follower Ratio, Avg Views, Median Views | `feature.*_engagement_analysis` (mig 036) | Excel menandainya "NEW" — **sudah kedaluwarsa** |
| 5 | Share Rate, Save Rate, Paid Ratio | mig 037 + 039 | TikTok saja untuk share/save |
| 6 | Post Frequency (angka) | mig 037 + 038 | Label cadence belum ada |
| 7 | Growth 30D + proyeksi | mig 037 + 040 | 25 kreator |
| 8 | `taxonomy_key` 9 canonical + **matriks 11d (9×9)** | `kol_categories` + Lookup CMP §11d | **Satu-satunya matriks relevansi yang bisa dipakai hari ini** |
| 9 | 18 `interest_key` sebagai vocabulary | `audience_interest_daily` | Dieja persis seperti DB |
| 10 | Aturan-aturan desain Excel (tanpa butuh data) | — | Hard vs soft · renormalisasi bobot vs nol vs neutral-50 · provenance basis · "modelled ranks, never gates" · urutan operasi |
| 11 | ER target per tier (§11b) | Lookup CMP | Argumennya kuat dan angkanya lengkap |
| 12 | Brand Safety versi *integrity screen* | `authenticity_score` 40 / `follower_quality_score` 30 / `verified_status` 15 / `paid_ratio` 15 | 3 dari 4 input punya kolom. **Wajib diberi label "integrity screen", bukan "brand safety"** |

### 9.2 PARTIAL — perlu tambahan data atau struktur

| # | Item | Yang sudah ada | Yang kurang |
|---|---|---|---|
| 1 | Category | `kol_categories` 28 baris, 9 key | 6 key NULL · 44,4% kreator tanpa kategori · 93,8% menumpuk di 2 key · Tech cuma 4 kreator |
| 2 | Audience gender | `female_pct`/`male_pct`/`gender_known_pct` | 0,30% coverage |
| 3 | Audience geo | `audience_geo_daily` | 23 country / 15 city usable; `geo_level` salah level 9 dari 33 key |
| 4 | Audience interest | `interest_key` + `interest_top` | 24 kreator; **85,2% `unknown`** |
| 5 | Audience quality & authenticity | kolom + tier (mig 039) | 0,34% coverage; **algoritma belum didefinisikan** |
| 6 | Engagement Rate | `kol_directory.engagement_rate` | 24,7%; **formula beda dari Excel (shares)** |
| 7 | Content Format | `format_dominant` | 3 nilai vs 4 nilai Excel; Live Streaming & Long-form tak terwakili |
| 8 | Content Topic | `content_topic` + `_source` | Vocabulary 18 key vs 87 node Excel — **bukan hal yang sama** |
| 9 | Brand master | `public.brand` + 5 kolom | **0 baris** |
| 10 | Brand Fit | `feature.brand_fit_analysis` 11 kolom | **0 baris** + algoritma belum ada + `public.brand` kosong |
| 11 | Campaign (±15 tabel) | struktur lengkap | **semuanya 0 baris**; 4 field brief style/personality tidak ada kolomnya |
| 12 | CPE | `feature.*_audience_analysis.cpe` | `unified_rate_card` **0 baris**; **formula beda dari Excel** |
| 13 | Bio (untuk Keyword Match) | `kol_directory.bio` | **12,8%** terisi — ini plafon skor keyword |
| 14 | Caption (untuk Topic Match & klasifikasi) | `l1_silver.unified_post.caption` | **50 dari 6.991 kreator = 0,72%** |
| 15 | Creator City | `kol_directory.creator_city` | kolom ada, **0% terisi**, dan tidak ada master city |
| 16 | Performance Archetype | input Reach/Engagement Driver siap | kolom label belum ada; Niche Authority blocked |
| 17 | Posting Cadence | angka siap | label 4-level belum ada; ambang Dormant belum diputuskan |

### 9.3 HOLD — perlu keputusan Product/mentor sebelum disentuh

| # | Keputusan yang dibutuhkan | Kenapa tidak bisa gue putuskan | Rujukan |
|---|---|---|---|
| **H1** | **Definisi EMV resmi** + konstanta CPM + nilai multiplier | Excel tidak pernah mendefinisikan EMV; DB punya rumus yang berbeda dan tidak lengkap | §4.1 |
| **H2** | **`kol.public.brand` atau `tsdb.public.brands`** sebagai sumber kebenaran brand | Dua tabel, dua database, keduanya diklaim Excel | §2.4 A, §0.3 |
| **H3** | **Batas tier Mid-tier/Macro** — versi mana yang menang | 3 versi berbeda; `kol_tiers` sudah dirujuk 7.207 akun | §2.1 |
| **H4** | **Formula ER** — pakai shares atau tidak | Excel pakai, DB tidak. Mengubahnya mengubah 1.728 nilai existing | §2.1, §4.2 |
| **H5** | **Formula CPE** — `rate ÷ (views × ER)` (Excel) atau `fee ÷ engagement_nyata` (DB) | Dua definisi berbeda untuk satu kolom | §4.2 |
| **H6** | **Formula Estimated ROI** — `Reach × ER × 9.000 ÷ Rate` atau `EMV ÷ rate` | Dua rumus di file yang sama | §4.2 |
| **H7** | **`CAL_VALUE_PER_ENG` = 9.000 IDR** — sah sebagai angka bisnis? | Tidak ada sumbernya; menentukan seluruh ROI | §6.2 |
| **H8** | **Brand Fit = Brand Match, atau dua hal berbeda** | Menentukan apakah `brand_fit_analysis` dipakai ulang atau perlu rumah kedua | §6.4 |
| **H9** | **Taxonomy mana yang menang**: 9 key DB, 10+36 `taksonomi_kol`, atau 14+42+87 `Taxonomy` | Tiga vocabulary tak kompatibel; Excel sendiri tidak konsisten | §8.1 |
| **H10** | **Alias 23 baris `kol_categories` sisanya** + 6 `taxonomy_key` NULL | Excel: owner = Product, sengaja dikosongkan daripada ditebak | §8.4 |
| **H11** | **Cara style & personality ditetapkan** ke kreator | Caption cuma 0,72% — otomatis tidak mungkin hari ini | §5.4 |
| **H12** | **Content Format** — 3 nilai DB atau 4 nilai Excel | Live Streaming & Long-form tidak punya sumber data | §2.1 |
| **H13** | **Ambang Dormant** ">2 bulan" dan `CAL_MIN_OBS_DAYS` 21 vs 30/14 di kode | Dua ambang berbeda untuk pertanyaan yang sama | §2.1, §2.3.2 |
| **H14** | **Dua set sub-bobot** (ENGINE vs CMP) untuk komponen yang sama | CMP "supersedes", tapi keduanya masih dikirim bersama | §2.3.2 |
| **H15** | **Grain metric biaya**: per-KOL (harga rate card) atau per-campaign (biaya nyata) | Excel memodelkan yang pertama; `campaign_kols` menyiratkan yang kedua | §4.3 |
| **H16** | **`Content Quality`** — apa sumbernya, dan apakah masuk skor | Angkanya ada di Excel, definisinya tidak, dan bobotnya 0 | §6.6, §7.2 |
| **H17** | **Bobot 7 kriteria vs bobot Excel** — Performance cuma 10% | Kalau 7 kriteria itu "what matters most", modelnya tidak selaras | §7.3 |
| **H18** | `discover_creator_links` (migrasi 053) — DB mana | Bukan repo/seri migration ini | §0.3 |
| **H19** | **Membereskan `tsdb`** sebelum brand dipakai: 19 baris test, 4 duplikat, `unified_post.brand_id` tidak menunjuk `brands.id` | Hanya relevan kalau H2 memilih `tsdb` | §2.2 |

### 9.4 MISSING — belum ada di DB sama sekali

| # | Item | Konsekuensi pada skor |
|---|---|---|
| 1 | **Content Style** (10) + **Communication Style** (8) | 4% + 1,5% skor akhir, dan **45% Campaign Fit** |
| 2 | **Creator Personality** (12) + **Brand Personality** (10) + **Brand Tone** (8) + **Values** (14) + **Positioning** (5) | **Seluruh komponen Brand Personality Fit N/A pada 120 dari 120 baris** — 10 poin hilang |
| 3 | **Sub Category** — tidak ada tabel, tidak ada kolom | 20% dari Content Relevance |
| 4 | **Brand Industry** (12) + **Brand Niche** (24) + crosswalk (183 baris) | Industry Match = 40% dari Brand & Business |
| 5 | **Audience Age** — `audience_demographics_daily` 0 baris untuk `audience_type='age'` | 25% dari Target Audience (komponen terberat, 30%) |
| 6 | **Rate Card** — 0 baris di 5 tabel; **tidak ada data masuk di L0 sekalipun** | Seluruh CPV/CPE/CPM/ROI/Cost Efficiency |
| 7 | **reach** — `unified_post.reach` NULL 0/221, butuh Insights API | Estimated Reach, EMV, avg_reach |
| 8 | **Comment sentiment / spam / toxicity** — `*_comments_analysis` 0 baris, `unified_comment` 0 baris | Sentiment Archetype, Content Risk, Brand Safety sesungguhnya |
| 9 | **Consistency Score** | 20% dari Performance |
| 10 | **Community Score** | 10% dari Performance |
| 11 | **Brand Safety Score / Risk Flag** — tidak ada kolom risk-level | Komponen 10% penuh |
| 12 | **Competitor Saturation** | 20% dari Brand Safety + filter `maxCompetitorSaturation` |
| 13 | **Purchase Intent** | filter `purchaseIntent` |
| 14 | **Daftar excluded creator** | filter `exclude_excluded_creator` |
| 15 | **Seluruh 46 konstanta + 9 matriks + 5 band** | Tidak ada satu pun tersimpan di DB |
| 16 | **Semua kolom output `Matching_Engine`** (Final Match Score, Match Level, Confidence, Brand Fit Index, Opportunity Score, Hard Filter Result, Exclusion Reason, Recommendation) | — |
| 17 | **Semua kolom skor campaign × KOL** (Campaign Fit, Unified Match, Style/Personality/Tone/Comm Fit) | — |
| 18 | **Gender kreator** (Female/Male/Other) | `taksonomi_kol.Demografi` |
| 19 | **Content language** kreator | `taksonomi_kol.Demografi`; juga menjelaskan kenapa keyword Indonesia tidak kena kreator berbahasa Inggris |
| 20 | **Master city list** | `kol_city` + `audience_city top-30` |
| 21 | **Filter `Connected`** (OAuth) | CMP: "removes all 24 — no creator has completed the OAuth connect flow" |

### 9.5 Rekap angka

| Status | Jumlah item |
|---|---:|
| READY | 12 |
| PARTIAL | 17 |
| HOLD (butuh keputusan) | **19** |
| MISSING | 21 |

Dari 58 kolom `KOL_Database`: MATCH 11 · PARTIAL 20 · NO MATCH 26 · NPD 1.
Dari 56 filter Discovery (klaim Excel sendiri): DONE 14 · PARTIAL 5 ·
BLOCKED BY DATA 29 · NEW 8.

> **Penghambat terbesar bukan data, melainkan keputusan.** E1 §16.10 sudah
> menyimpulkan hal yang sama untuk lingkup lebih kecil: "17 kolom terkunci
> semata-mata karena algoritmanya belum didefinisikan, bukan karena sumbernya
> tidak ada." Audit ini menemukan **19 keputusan** yang menghalangi pekerjaan
> yang secara teknis sudah bisa jalan.

---

## 10. IMPLEMENTATION RECOMMENDATION

Diurutkan dari paling aman ke paling berisiko. **Prinsip: reuse dulu, dan tidak
satu langkah pun dimulai sebelum DB diverifikasi ulang dengan VPN aktif.**

### Tahap 0 — Verifikasi (WAJIB, sebelum apa pun)

| # | Pekerjaan | Kenapa duluan |
|---|---|---|
| 0.1 | Sambungkan VPN, jalankan audit read-only ke `kol`: `information_schema` untuk **seluruh** tabel `campaign_*`, `public.brand`, `feature.brand_fit_analysis` | Audit ini bersandar pada dokumen bertanggal 24 Agu / 8 Sep / 10 Sep 2026. **Angka apa pun bisa sudah berubah** |
| 0.2 | Cek apakah migration **037–044 sudah dijalankan** di server | Kedelapan migration itu belum ter-commit; kalau belum jalan, semua item READY #4–#7 batal |
| 0.3 | Verifikasi keberadaan `tsdb` dan `discover_creator_links` | Menentukan H2 dan H18 |
| 0.4 | Hitung ulang coverage 10 sinyal DIST_Population | Menentukan urutan Tahap 2 |

**Tidak ada perubahan DB di tahap ini.**

### Tahap 1 — Kemenangan gratis (tanpa migration, tanpa keputusan)

| # | Pekerjaan | Risiko |
|---|---|---|
| 1.1 | Pakai `Discovery_Filters` + `Filter_Logic` + `CMP_Hard_vs_Soft_Filter` sebagai **spesifikasi filter resmi** — catatan backend-nya sudah SQL-ready | Nol |
| 1.2 | Terapkan 14 filter DONE apa adanya | Nol |
| 1.3 | Kodekan aturan **hard vs soft** dan **urutan operasi** (komponen → skor → hard filter → ranking) | Nol |
| 1.4 | Kodekan aturan missing-data 3 arah: brand kosong → 50 · kreator tak terukur → 0 atau N/A · N/A → renormalisasi bobot | Nol. **Ini yang paling mudah salah dan paling mahal salahnya** |
| 1.5 | Perbaiki status usang di Excel (`Median Views`, `View-to-Follower Ratio` sudah ada sejak mig 036) | Nol |

### Tahap 2 — Reuse struktur existing (migration aditif, pola 036–039)

| # | Pekerjaan | Prasyarat |
|---|---|---|
| 2.1 | `category_basis` varchar(16) pada `kol_profile_card` | Tidak ada. **Nilai tertinggi per biaya di seluruh laporan** — inilah yang mencegah kategori hasil model dipakai sebagai gerbang |
| 2.2 | `performance_archetype` varchar(32) | Tidak ada; kedua input siap |
| 2.3 | Tabel **`match_config`** (key → value) + isi 46 konstanta, 9 matriks, 5 band dari `Lookup_Lists` | Tidak ada. README r47 meminta ini eksplisit. **Menyelamatkan aset paling berharga di workbook dari file Excel yang rumus-rumusnya sudah mulai rusak** (`#REF!`/`#VALUE!` di 4 sheet) |
| 2.4 | Isi `public.brand` untuk ±17 brand nyata | **H2** |
| 2.5 | Isi 6 `taxonomy_key` yang NULL | **H10** |

### Tahap 3 — Naikkan coverage (pekerjaan data, bukan schema)

Urutan berdasarkan berapa banyak yang dibuka per satuan usaha:

| # | Pekerjaan | Membuka |
|---|---|---|
| 3.1 | **Caption harvest** — dari 50 ke sebanyak mungkin dari 6.991 kreator | Topic Match · klasifikasi kategori untuk 3.547 kreator tanpa kategori · satu-satunya jalan realistis mengisi style/personality otomatis. **Prasyarat de-facto untuk H11** |
| 3.2 | **Bio** — dari 12,8% | Keyword Match (plafonnya sekarang 12,8%) |
| 3.3 | **Perlebar `feature.*_audience_analysis`** dari 24 ke seluruh roster | Audience Quality · Authenticity · gender · Brand Safety integrity screen — 4 item sekaligus |
| 3.4 | **Cari sumber rate card** | CPV · CPE · CPM · Cost Efficiency · Estimated ROI. ⚠️ **Bukan gap ETL** — 0 baris di L0 juga, jadi ini pekerjaan mencari sumber, bukan memperbaiki pipeline |
| 3.5 | **Audience age** (`audience_demographics_daily` `audience_type='age'`) | 25% dari komponen terberat. Butuh Insights API |
| 3.6 | **Comment scraping** → `unified_comment` | Sentiment Archetype · Content Risk · Brand Safety sesungguhnya · 20 kolom terkunci (penghambat tunggal terbesar menurut E1) |

### Tahap 4 — Struktur baru (hanya setelah keputusan ada)

| # | Pekerjaan | Diblokir oleh |
|---|---|---|
| 4.1 | `kol_sub_categories` (42 node) + `kol_directory.sub_category_ids` | **H9** |
| 4.2 | `kol_category_alias` (28 baris → kode) | **H9, H10** |
| 4.3 | `content_style_master` + `personality_master` + 2 junction | **H11** — dan **jangan** dibikin sebelum ada cara mengisinya |
| 4.4 | Kolom skor pada `campaign_kols` | **H8, H11** |
| 4.5 | Pakai `feature.brand_fit_analysis` sebagai rumah hasil Brand Match | **H8** |
| 4.6 | Kolom EMV | **H1** |

### Yang gue sarankan JANGAN dikerjakan sekarang

| Jangan | Kenapa |
|---|---|
| Bikin tabel brand / category / brand-match-score baru | Ketiganya sudah ada rumahnya (§3.6) |
| Bikin master + junction style/personality | 4 tabel kosong tanpa cara mengisinya = undangan untuk menebak |
| Isi kolom mana pun dengan default atau tebakan | Pola yang sudah ditolak eksplisit di header mig 037/038 |
| Menjadikan Category sebagai hard filter | Sah hanya terhadap basis `live`. 44,4% roster tanpa kategori, dan 9 dari 24 di roster CMP |
| Menyebut *integrity screen* sebagai "Brand Safety" | Tidak ada content-risk reading untuk satu akun pun |
| Mengambil angka dari `DIST_Distribution_Summary` / `DIST_Histogram_Data` / beberapa cell `CMP_Validation` | Rumusnya rusak (`#REF!`, `#VALUE!`). Pakai narasi `DIST_README` |
| Menyimpan `Final Match Score` sebagai kolom yang difilter di SQL | Filter_Logic r19: "Computed, not stored" |

---

## 11. STATUS SESI INI

| | |
|---|---|
| Excel dibaca | **51 / 51 sheet** |
| Perubahan DB | **NOL** — tidak ada koneksi berhasil, jadi tidak ada query apa pun yang dieksekusi |
| Migration dibuat | **NOL** |
| Data Excel masuk DB | **NOL** |
| File yang gue tulis | `docs/KOL_EXCEL_DB_MATCHING_AUDIT.md` (dokumen ini) — **satu-satunya perubahan di working tree** |
| Keputusan yang gue ambil | **NOL** — 19 item HOLD sengaja dibiarkan terbuka |

**Menunggu approval sebelum development.**
