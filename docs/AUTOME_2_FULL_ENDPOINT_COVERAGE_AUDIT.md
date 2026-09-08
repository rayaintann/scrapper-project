# AUTOME_2 — Full Coverage Audit: Requirement → DB/L2 → Endpoint → UI

**Read-only · 8 September 2026 · tidak ada perubahan kode, migration, scraping, commit, atau push**

Konsolidasi seluruh audit sesi ini, ditambah dimensi yang belum pernah dipetakan menyeluruh: **apakah UI benar-benar mengonsumsi endpoint-nya.**

| Repo | Branch | Commit | Working tree |
|---|---|---|---|
| `scrapper-project` | `main` | `116243e` | 9 dokumen audit untracked |
| `autometric` | `engkol_v1` | `84ea2fc` | bersih |

**Baseline yang dipakai ulang, tidak diukur ulang:** `AUTOME_2_DEVELOPMENT_AUDIT.md` (87 requirement, diukur 8 Sep), `AUTOME_2_ER_AUDIT.md`, `AUTOME_2_ER_COVERAGE_AUDIT.md`, `AUTOME_2_ENDPOINT_GROWTH_ER_AUDIT.md`, `AUTOME_2_POST_OWNERSHIP_AUDIT.md`.

---

# Ringkasan eksekutif

| Status | Jumlah |
|---|---:|
| **READY** | **14** |
| **READY tapi ada mismatch** | **6** |
| **DB ada, endpoint missing** | **8** |
| **Endpoint ada, UI missing** | **3** |
| **Calculation missing** | **14** |
| **Source/data missing** | **31** |
| **Requirement ambiguous** | **4** |
| **Total** | **80** |

## Tiga angka yang membingkai semuanya

| Fakta | Angka |
|---|---|
| Filter AUTOME_2 di sidebar | **28** (+7 exclusion, +7 section, 34 sort key) |
| Filter yang benar-benar diproses backend | **8** |
| Filter yang ada kontrolnya di UI aplikasi | **8** — UI sengaja tidak merender kontrol yang tidak bisa disaring |

Yang penting: **tidak ada filter palsu.** `KolDirectoryFilters.tsx` hanya merender kontrol yang backend-nya benar-benar bekerja, dan komentarnya menyatakan alasannya. Gap-nya besar, tapi jujur.

---

# A. Tabel Coverage Seluruh Requirement AUTOME_2

Legenda kolom: **L2/DB** = data+calculation tersedia · **EP** = endpoint mengeluarkannya · **JSON** = field ada di response · **Filter BE** = filter diproses backend · **UI** = UI mengonsumsinya

## A.1 Identitas & profil (15)

| # | Requirement | Source of truth | L2/DB | EP | Route + file | JSON | Filter BE | Calc layer | UI | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Username | `kol_directory.username` | ✅ 97,1% | ✅ | list+detail · `kolDirectory.ts` | `username` | ✅ `q` | — | ✅ | **READY** |
| 2 | Display name | `kol_profile_card.display_name` | ✅ 1.976 | ⚠ detail saja | `kolGold.ts` | `gold.cards[].displayName` | ❌ | — | ⚠ | **Endpoint ada, UI missing** (list tak punya) |
| 3 | Avatar | `kol_directory.avatar_url` | ✅ 12,1% | ✅ | list+detail | `avatarUrl` | — | — | ✅ | **READY** |
| 4 | Bio | `kol_directory.bio` | ✅ 11,7% | ✅ | list+detail | `bio` | ❌ tak dicari | — | ✅ | **READY tapi mismatch** (search hanya username) |
| 5 | Profile URL | `kol_directory.profile_url` | ✅ | ✅ | list+detail | `profileUrl` | — | — | ✅ | **READY** |
| 6 | Platform | `platforms.key` | ✅ IG 3.409 · TT 4.087 | ✅ | list | `platform` | ✅ `platform` | — | ✅ | **READY tapi mismatch** (YouTube tak ada baris) |
| 7 | Kategori | `kol_categories.taxonomy_key`/`name` | ✅ 4.155 | ✅ | list | `categories[]` | ✅ `category` pakai `name` | — | ✅ | **READY tapi mismatch** (`name` vs `taxonomy_key`) |
| 8 | Tier | `kol_tiers` band | ✅ 93,2% | ✅ | list | `tier` | ✅ `tier[]` | band lookup | ✅ | **READY** |
| 9 | Followers | `kol_directory.followers_count` | ✅ 97,1% | ✅ | list+detail | `followers` | ✅ `follMin` | — | ✅ | **READY** |
| 10 | Agency | `agency_kol_accounts`+`agencies` | ✅ 7.684 | ✅ | `attachRosterExtras` | `agency` | ❌ | — | ✅ | **READY** |
| 11 | Verified / Connected | `social_account.platform_user_id`+`oauth_token` | ✅ = **0 KOL** | ✅ | list | `connected` | ✅ `connected=1` | boolean EXISTS | ✅ ikon `link` | **READY tapi mismatch** (prototype minta badge platform) |
| 12 | Data status badge | `last_refreshed_at`+`scrape_status` | ✅ | ✅ | list | `status` | ❌ | CASE 3 cabang | ✅ | **READY tapi mismatch** (Live 0 · Calculated 27 · Estimated 7.693) |
| 13 | Last synced | `kol_directory.last_refreshed_at` | ✅ 7.496 | ✅ | list | `lastRefreshedAt` | ❌ | — | ✅ | **DB ada, endpoint missing** (filter) |
| 14 | Creator city | `kol_directory.creator_city` | ❌ **0/7.720** | ✅ | list | `city` | ❌ | — | ✅ | **Source/data missing** |
| 15 | Niche / sub-label | — | ❌ | ❌ | — | — | ❌ | — | ❌ | **Source/data missing** |

## A.2 Performa (15)

| # | Requirement | Source of truth | L2/DB | EP | Route + file | JSON | Filter BE | Calc layer | UI | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 16 | Engagement rate | 3 sumber paralel | ⚠ roster 1.756 · L2 22 akun | ✅ | list (roster) + detail (L2) | `erPct` (%) · `gold.daily[].erFollowers` (fraksi) | ✅ `minEr` **baca roster** | ⚠ 3 versi beda satuan | ✅ keduanya | **READY tapi mismatch** |
| 17 | Avg views | `kol_metric_daily.views_sum` | ⚠ 30 akun, belum diagregasi | ⚠ mentah | detail `gold.daily[]` | `views` per hari | ❌ | **belum ada** | ⚠ dihitung di UI | **Calculation missing** |
| 18 | Median views | `post_metric.views` | ⚠ 477 baris | ⚠ mentah | detail `gold.posts[]` | `views` per post | ❌ | **belum ada** | ❌ | **Calculation missing** |
| 19 | Avg likes | `feature.*_engagement_analysis` | ✅ 30 akun | ❌ | — | — | ❌ | ✅ di feature | ❌ | **DB ada, endpoint missing** |
| 20 | Avg comments | idem | ✅ 30 akun | ❌ | — | — | ❌ | ✅ di feature | ❌ | **DB ada, endpoint missing** |
| 21 | Avg shares | `post_metric.shares` | ❌ IG 0/186 · TT 291 | ⚠ | detail | `gold.posts[].shares` | ❌ | — | ⚠ | **Source/data missing** (IG) |
| 22 | Avg saves | `post_metric.saves` | ❌ IG 0/186 | ⚠ | detail | `gold.posts[].saves` | ❌ | — | ⚠ | **Source/data missing** (IG) |
| 23 | Save rate | turunan saves | ❌ | ❌ | — | — | ❌ | — | ❌ | **Source/data missing** |
| 24 | Share rate | turunan shares | ❌ | ❌ | — | — | ❌ | — | ❌ | **Source/data missing** |
| 25 | View-to-follower | `post_metric.views`/followers | ⚠ bahan ada | ❌ | — | — | ❌ | **belum ada** | ❌ | **Calculation missing** |
| 26 | Like-to-view | `post_metric.likes`/`views` | ⚠ bahan ada | ❌ | — | — | ❌ | **belum ada** | ❌ | **Calculation missing** |
| 27 | Reach / Est. reach | `post_metric.reach` | ❌ **0/477** | ❌ | — | — | ❌ | — | ⚠ sample | **Source/data missing** |
| 28 | Impressions | — | ❌ | ❌ | — | — | ❌ | — | ⚠ sample | **Source/data missing** |
| 29 | Posting frequency | `kol_metric_monthly` | ⚠ 68 baris | ⚠ mentah | detail | `gold.monthly[]` | ❌ | **belum ada** | ❌ | **Calculation missing** |
| 30 | Paid/sponsored ratio | `post_metric.is_sponsored` | ⚠ 467/477 flag | ⚠ mentah | detail | `gold.posts[].isSponsored` | ❌ | **belum ada** | ⚠ | **Calculation missing** |

## A.3 Growth (6)

| # | Requirement | Source of truth | L2/DB | EP | Route + file | JSON | Filter BE | Calc layer | UI | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 31 | Growth (snapshot-ke-snapshot) | `kol_profile_card.followers_growth` | ✅ **25/7.720** | ✅ | list+detail · LATERAL | `growthPct` · `gold.cards[].followersGrowth` | ✅ `growthMin`/`growthMax` | ✅ L1 → L2 | ✅ kolom+sort+tile | **READY** |
| 32 | **Growth 30D** (CAGR) | butuh `days_between` | ❌ | ❌ | — | — | ❌ | **belum ada** | ❌ | **Calculation missing** |
| 33 | `days_between` + tgl snapshot sebelumnya | — | ❌ **tidak ada kolom** | ❌ | — | — | — | — | ❌ | **Source/data missing** |
| 34 | Growth classification | turunan #32 | ❌ | ❌ | — | — | ❌ | threshold placeholder | ❌ | **Calculation missing** |
| 35 | Rising Creator | growth+ER+followers | ❌ | ❌ | — | — | ❌ | — | ❌ | **Calculation missing** |
| 36 | g7 / g90 / accel / momentum | butuh ≥3–4 snapshot | ❌ **0 akun** | ❌ | — | — | ❌ | — | ⚠ sample | **Source/data missing** (waktu) |

## A.4 Audiens (10)

| # | Requirement | Source of truth | L2/DB | EP | Route + file | JSON | Filter BE | Calc layer | UI | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 37 | Gender % | `audience_demographics_daily` | ✅ 69 baris / 23 KOL · inferred | ✅ detail | `kolGold.ts` | `gold.audience.gender[]` + `coverage.gender` | ❌ | ✅ share+coverage | ✅ `GoldBreakdown` | **DB ada, endpoint missing** (filter) |
| 38 | Age band | idem `='age'` | ❌ **0 baris** | ✅ wired | `kolGold.ts` | `gold.audience.age[]` kosong | ❌ | — | ✅ siap | **Source/data missing** |
| 39 | Generasi | turunan age | ❌ | ❌ | — | — | ❌ | — | ❌ | **Source/data missing** |
| 40 | Audience location | `audience_geo_daily` | ✅ 181 / 23 KOL | ✅ detail | `kolGold.ts` | `gold.audience.countries[]`, `.cities[]` | ❌ | ✅ | ✅ | **DB ada, endpoint missing** (filter) |
| 41 | Audience interest | `audience_interest_daily` | ✅ 214 / 23 KOL | ✅ detail | `kolGold.ts` | `gold.audience.interests[]` | ❌ | ✅ | ✅ + peringatan coverage <50% | **DB ada, endpoint missing** (filter) |
| 42 | Confidence & coverage audiens | kolom `confidence` | ✅ | ✅ | `kolGold.ts` | `gold.audience.confidence`, `.coverage`, `.asOf` | — | `MODE()` | ✅ label eksplisit | **READY** |
| 43 | Audience quality | turunan | ❌ input mock | ❌ | — | — | ❌ | **belum ada** | ⚠ sample | **Calculation missing** |
| 44 | Authenticity | `unified_follower` (2.548/27 akun) | ⚠ bahan ada | ❌ | — | — | ❌ | **belum ada** | ⚠ sample | **Calculation missing** |
| 45 | Audience overlap | `unified_follower` | ⚠ bahan ada | ❌ | — | — | ❌ | **belum ada** | ⚠ sample | **Calculation missing** |
| 46 | Purchase/brand/category affinity | — | ❌ | ❌ | — | — | ❌ | tak ada definisi | ⚠ sample | **Requirement ambiguous** |

## A.5 Konten (13)

| # | Requirement | Source of truth | L2/DB | EP | Route + file | JSON | Filter BE | Calc layer | UI | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 47 | Post likes/comments | `post_metric` | ✅ 503 baris | ✅ detail | `kolGold.ts` | `gold.posts[].likes/.comments` | ❌ | L0→L2 | ✅ | **READY** (cakupan 30 KOL) |
| 48 | Post views | `post_metric.views` | ⚠ IG 102/186 | ✅ detail | idem | `gold.posts[].views` | ❌ | — | ✅ | **READY** (IG hanya video) |
| 49 | Post ER + rank | `post_metric.er_followers`, `rank_in_account` | ⚠ 140/503 | ✅ detail | idem | `gold.posts[].erFollowers`, `.rankInAccount` | ❌ | ✅ feature→L2 | ✅ | **READY** |
| 50 | Format raw | `content_format_daily.media_type` | ✅ 300 baris, 6 nilai | ✅ detail | `kolGold.ts` | `gold.formats[].mediaType` | ❌ | disimpan mentah | ✅ | **READY** |
| 51 | Format display mapping | turunan | ❌ | ❌ | — | — | ❌ | **belum ada** | ❌ | **Calculation missing** |
| 52 | `format_dominant` | share per format | ❌ (26/30 akun punya ≥10 post) | ❌ | — | — | ❌ | **belum ada** | ❌ | **Calculation missing** |
| 53 | Hashtags | `post_metric.top_hashtags` | ✅ IG 70 · TT 237 | ✅ detail | idem | `gold.posts[].hashtags` | ❌ | ✅ feature | ✅ | **READY** |
| 54 | Sponsored flag | `post_metric.is_sponsored` | ✅ 467/477 | ✅ detail | idem | `gold.posts[].isSponsored` | ❌ | flag platform | ✅ | **DB ada, endpoint missing** (filter) |
| 55 | Cover image / permalink | `unified_post` | ⚠ CDN expired | ✅ | `kolPostCover.ts` + route proxy | `coverImage` | — | — | ✅ | **READY** |
| 56 | Sentiment | `*_post_analysis.sentiment_breakdown` | ❌ **0/503** (raw ada) | ❌ | — | — | ❌ | **belum mengalir** | ⚠ sample | **Calculation missing** |
| 57 | Content topic | `content_category` | ❌ **0** (raw ada) | ❌ | — | — | ❌ | **belum mengalir** | ⚠ sample | **Calculation missing** |
| 58 | Content persona/style | — | ❌ | ❌ | — | — | ❌ | tak ada definisi | ⚠ sample | **Requirement ambiguous** |
| 59 | Watch time / completion | *blocked columns* | ❌ **0** | ❌ | — | — | ❌ | — | ❌ | **Source/data missing** |

## A.6 Komersial (11)

| # | Requirement | Source of truth | L2/DB | EP | Route + file | JSON | Filter BE | Calc layer | UI | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 60 | Rate card | `l1_silver.unified_rate_card` | ❌ **0 baris di 5 tabel** | ✅ | `kolMeasured.ts` + `/discover/rates` | `measured.rates[]`, `rateFrom`, `rateCount` | ✅ `maxRate` → **0 hasil** | — | ✅ kolom default on | **Source/data missing** |
| 61 | Rate card ringkas L2 | `kol_profile_card.rate_card*` | ❌ NULL sengaja | ❌ | — | — | ❌ | — | ❌ | **Source/data missing** |
| 62 | CPV | fee + views | ❌ fee kosong | ❌ | — | — | ❌ | — | ⚠ sample | **Source/data missing** |
| 63 | CPE | fee + engagement | ❌ | ❌ | — | — | ❌ | — | ⚠ sample | **Source/data missing** |
| 64 | CPM | fee + reach | ❌ keduanya | ❌ | — | — | ❌ | — | ⚠ sample | **Source/data missing** |
| 65 | EMV | reach + benchmark | ❌ | ❌ | — | — | ❌ | — | ⚠ sample | **Source/data missing** |
| 66 | Commercial efficiency | turunan CPV | ❌ | ❌ | — | — | ❌ | — | ⚠ sample | **Source/data missing** |
| 67 | Brand Fit | `feature.brand_fit_analysis` | ❌ **0 baris, tak ada asset** | ❌ | — | — | ❌ | 4/6 input mock | ⚠ `BrandFitSection` sample | **Source/data missing** |
| 68 | Opportunity score | komposit | ❌ | ❌ | — | — | ❌ | — | ⚠ sample | **Source/data missing** |
| 69 | Competitor saturation | raw `taggedUsers`/`mentions` | ❌ (raw ada) | ❌ | — | — | ❌ | **belum mengalir** | ⚠ sample | **Calculation missing** |
| 70 | Worked with my brand | tabel order+nego app | ✅ | ✅ | `/discover/orders`, negotiation | — | ❌ | EXISTS | ⚠ | **DB ada, endpoint missing** (filter) |

## A.7 Konsistensi & freshness (9)

| # | Requirement | Source of truth | L2/DB | EP | JSON | Filter BE | UI | Status |
|---|---|---|---|---|---|---|---|---|
| 71 | Performance consistency | `kol_metric_monthly` (butuh ≥4 titik) | ❌ ~5 KOL | ⚠ mentah | `gold.monthly[]` | ❌ | ⚠ sample | **Source/data missing** (waktu) |
| 72 | Performance stability | idem | ❌ | ❌ | — | ❌ | ⚠ sample | **Source/data missing** (waktu) |
| 73 | Viral frequency | idem | ❌ | ❌ | — | ❌ | ⚠ sample | **Source/data missing** (waktu) |
| 74 | Last Updated (filter) | `last_refreshed_at` | ✅ 7.496 | ✅ field | `lastRefreshedAt` | ❌ **tak ada param** | ✅ kolom | **DB ada, endpoint missing** |
| 75 | Data Status (6 status) | butuh frekuensi per KOL | ❌ | ❌ | — | ❌ | ❌ | **Source/data missing** |
| 76 | Update Frequency | — | ❌ | ❌ | — | ❌ | ❌ | **Source/data missing** |
| 77 | Next Update | — | ❌ | ❌ | — | ❌ | ❌ | **Source/data missing** |
| 78 | Monitoring Priority | sebagian dari order/nego | ⚠ | ❌ | — | ❌ | ❌ | **Calculation missing** |
| 79 | Request Update Now | — | ❌ | ❌ tak ada route untuk roster | — | ❌ | ❌ | **Source/data missing** |

## A.8 Mekanik direktori & modul lain (11)

| # | Requirement | Source of truth | L2/DB | EP | Route + file | Filter BE | UI | Status |
|---|---|---|---|---|---|---|---|---|
| 80 | Search multi-field | roster + turunan | ⚠ `display_name` 1.976 · `bio` 902 | ✅ | list `q` | ⚠ **`username` saja** | ✅ | **READY tapi mismatch** |
| 81 | Sort | berbagai | ⚠ | ✅ | `SORT_COLUMNS` | ✅ **6 dari 34** key | ✅ 5 opsi | **READY tapi mismatch** |
| 82 | Pagination | — | — | ✅ | `page`,`pageSize` (maks 60) | ✅ | ✅ | **READY** |
| 83 | Facets | lookup | ✅ | ✅ | `facets=1` | ✅ | ✅ | **READY** |
| 84 | Compare multi-KOL | roster | ✅ | ✅ | `?ids=` maks 50 | ✅ | ✅ `DiscoverCompare.tsx` | **READY** |
| 85 | Exclusions (7) | turunan intel | ❌ 6/7 blocked | ❌ | — | ❌ | ❌ | **Calculation missing** |
| 86 | Sections (7 chip) | turunan intel | ⚠ 3/7 bisa | ❌ | — | ❌ | ❌ | **Calculation missing** |
| 87 | Saved list / collection | **tak ada tabel** | ❌ | ❌ | — | ❌ | ❌ | **Source/data missing** |
| 88 | Ordering / Cart / Checkout | tabel order app + Midtrans | ✅ | ✅ | 7 route `/discover/orders/*` | — | ✅ `DiscoverCart/Orders` | **READY** (tanpa harga → rate card kosong) |
| 89 | Negotiation | tabel negotiation app | ✅ | ✅ | `negotiation.ts` 785 baris | — | ✅ 5 komponen | **READY** |
| 90 | AI Assistant | agregat org | ✅ | ✅ | `/discover/assistant` | — | ✅ | **READY** |

---

# B. Daftar Endpoint Existing (relevan AUTOME_2)

| # | Route | File | Mengeluarkan | Filter yang diproses |
|---|---|---|---|---|
| 1 | `GET /api/organizations/[id]/discover/kol-directory` | `route.ts` → `kolDirectory.listKolDirectory()` | 18 field `KolDirectoryRow` + `total` + `facets` | `q, platform, category, tier, follMin, minEr, maxRate, growthMin, growthMax, connected, sort, dir, page, pageSize, ids, facets` |
| 2 | `GET .../kol-directory/[kolId]` | `route.ts` → `getKolCreator()` | `creator, identity, rank, platforms[], similar[], measured, gold` | — |
| 3 | `GET .../kol-directory/[kolId]/cover/[postId]` | `kolPostCover.ts` | proxy gambar cover | — |
| 4 | `GET .../discover/rates` | `rates.ts` | katalog deliverable + harga | — |
| 5 | `GET/POST .../discover/orders/*` (7 route) | `orders.ts`, `payment.ts` | quotation, order, item, pay, campaign, dashboard | — |
| 6 | `.../discover/creators/*` (5 route) | `creatorStore.ts`, `creatorProfiling.ts` | **entitas lain** (`discover_creators` milik org) | — |
| 7 | `GET .../discover/content`, `/content/post` | `content.ts`, `postAnalytics.ts` | **korpus brand+kompetitor**, bukan roster KOL | lengkap |
| 8 | `GET .../discover/summary` | `summary.ts` | agregat korpus brand | — |
| 9 | `GET .../discover/assistant` | `assistant.ts` | konsep konten dari data org | — |
| 10 | `GET .../discover/inspirations` | `inspirations.ts` | shortlist post org | — |
| 11 | `GET .../discover/directory` | `directory.ts` | akun brand+kompetitor org | — |

**Catatan:** #6, #7, #8, #11 melayani entitas/korpus lain — bukan roster KOL. Ini sumber mismatch "Discovery Content" dan "Audience Insights" di prototype.

---

# C. Daftar Endpoint yang Missing

| # | Yang kurang | Tabel/file terkait | Perubahan minimum | Scraping? | Migration? | Endpoint baru? |
|---|---|---|---|---|---|---|
| **C1** | Filter **Last Updated** | `kol_directory.last_refreshed_at` · `kolDirectory.ts` | 1 param + 1 klausa WHERE | ❌ | ❌ | **modify existing** |
| **C2** | Filter **audiens** (gender / location / interest) | `audience_*_daily` · `kolDirectory.ts` `filtered` CTE | 3 param + join roster→`ksa`→L2. Cakupan 23 KOL | ❌ | ❌ | **modify existing** |
| **C3** | Filter **sponsored ratio** | `post_metric.is_sponsored` | butuh agregat per akun dulu (D3) | ❌ | ⚠ jika kolom agregat baru | **modify existing** |
| **C4** | `display_name` di **list** | `kol_profile_card.display_name` | tambah ke `BASE` + `KolDirectoryRow` | ❌ | ❌ | **modify existing** |
| **C5** | **Layer feature** tak pernah di-expose | `feature.*_engagement_analysis` (heatmap 28 akun, `format_performance` 17, agregat 30) | fungsi query baru + tambahkan ke payload detail | ❌ | ❌ | **modify existing** (detail) |
| **C6** | Metrik **L2 di list** | `kol_metric_daily`, `post_metric` | agregat per akun + kolom di `BASE` | ❌ | ⚠ jika view/tabel agregat | **modify existing** |
| **C7** | `days_between` growth di response | `kol_profile_card` | butuh kolom dulu (E-baru) | ❌ | **✅ ya** | **modify existing** |
| **C8** | **Refresh on-demand** roster KOL | — | route + antrean job | ❌ | ⚠ tabel antrean | **endpoint baru** |
| **C9** | **Saved list / collection** | tak ada tabel | tabel + 4 route CRUD | ❌ | **✅ ya** | **endpoint baru** |

---

# D. Daftar Calculation yang Missing

| # | Calculation | Layer yang seharusnya | Bahan sudah ada? | Perubahan minimum | Migration? |
|---|---|---|---|---|---|
| **D1** | **Growth 30D** `((f_now/f_prev)^(30/days))−1` | **L2** `kol_profile_card` | ⚠ hanya 25 akun, span 10–13 hari | kolom `growth_30d`, `days_between`, `snapshot_prev_date` + span guard | **✅ ya** |
| **D2** | Growth classification | L2 + config threshold | ❌ butuh D1 | tabel/konstanta threshold | ⚠ |
| **D3** | **Agregat per akun**: avg views, median views, posting freq, paid ratio, v2f, l2v | **L2** | ✅ `post_metric` 503, `kol_metric_*` | view/tabel agregat + asset | ⚠ jika tabel |
| **D4** | **ER kanonik** + konversi satuan | pilih `er_followers_daily` | ✅ | ganti sumber `er_pct` di `BASE` + `×100` | ❌ |
| **D5** | Format display mapping + `format_dominant` | L2 turunan | ✅ 6 nilai mentah, 26/30 akun ≥10 post | agregat share per akun | ⚠ |
| **D6** | **Sentiment** dari `latestComments` | **Feature** | ✅ raw di `raw_payload` | asset baru — **nol biaya Apify** | ❌ |
| **D7** | **Content topic** dari caption+hashtag | **Feature** | ✅ raw ada | asset baru | ❌ |
| **D8** | **Authenticity** & audience quality | **Feature** `*_audience_analysis` | ✅ `unified_follower` 2.548/27 akun | asset baru | ❌ |
| **D9** | Audience overlap (irisan follower nyata) | Feature | ✅ `unified_follower` | asset baru | ❌ |
| **D10** | Competitor saturation | Feature | ✅ `taggedUsers`/`mentions` di raw | asset baru | ❌ |
| **D11** | Brand Fit | Feature `brand_fit_analysis` | ❌ 4/6 input mock | butuh D8 dulu | ❌ (tabel sudah ada) |
| **D12** | Monitoring priority | L2/app | ⚠ sebagian (order/nego aktif) | aturan sederhana dulu | ❌ |
| **D13** | Exclusions (6 dari 7) | turunan | ❌ | menunggu D3, D8 | ❌ |
| **D14** | Sections (4 dari 7) | turunan | ❌ | menunggu D1, D3 | ❌ |

---

# E. Daftar Source / Scraping yang Missing

| # | Yang kurang | Bukti terukur | Cara satu-satunya |
|---|---|---|---|
| **E1** | **Rate card** | **0 baris di 5 tabel**, semua layer | Cari source-nya — bukan ETL gap, tidak ada data di L0 sekalipun |
| **E2** | **Reach & impressions** | `post_metric.reach` 0/503 | Insights API |
| **E3** | **Shares & saves Instagram** | IG 0/186 · TT 291/291 | Insights API |
| **E4** | **Demografi umur** | `audience_demographics_daily` age = **0 baris** | Insights API — tidak ada sinyal umur di data follower |
| **E5** | **Watch time / completion** | 0 | Insights API |
| **E6** | **Story** | 0 dari 6 nilai `media_type` | Scraping Story (belum pernah) |
| **E7** | **Platform YouTube** | `platforms` hanya IG+TikTok | Tambah platform |
| **E8** | **Kota kreator** | `creator_city` 0/7.720 | Source apa pun |
| **E9** | **Riwayat kampanye** | `campaigns`/`campaign_kols` 0 baris | Data operasional — **bukan scraping** |
| **E10** | **Benchmark CPM** | tak ada tabel | Untuk EMV |
| **E11** | **Snapshot berkala** | 1.947 akun cuma 1 snapshot; span maks 13 hari | **Bukan source baru** — jalankan scheduler yang ada secara berkala |
| **E12** | **Post untuk 7.466 KOL** | 30/7.720 punya post | **Bukan source baru** — `post_pipeline.py` dengan `--limit` besar |
| **E13** | Jadwal & prioritas monitoring per KOL | tak ada tabel | Tabel baru |
| **E14** | Saved list / collection | tak ada tabel | Tabel baru |

---

# F. Prioritas Development

## P0 — Wajib, dan tidak memblokir apa pun untuk dimulai

| # | Task | Kenapa paling dulu | Butuh |
|---|---|---|---|
| **P0-1** | **Lacak source rate card** | 0 baris di 5 tabel. Memblokir seluruh sisi komersial (#60–66) *dan* membuat filter `maxRate` mengembalikan 0 dari 7.720 — filter yang **aktif dan salah**, bukan sekadar kosong | jawaban tim |
| **P0-2** | **Perbaiki 3 filter yang hasilnya salah** | `maxRate` → 0 hasil · `minEr` membuang 77% roster (NULL) · `growthMin/Max` membuang 99,7%. Ini satu-satunya kategori yang membuat produk **salah**, bukan kurang | keputusan NULL-handling |
| **P0-3** | **Jalankan `post_pipeline.py` ke populasi lebih besar** | 1.942 akun sudah punya denominator follower, tinggal post-nya. Fix ownership sudah ter-commit (`116243e`). Membuka #16–30, #47–54 | biaya Apify |
| **P0-4** | **Scheduler profil berkala** | Prasyarat tunggal untuk #32–36, #71–73, #75–77. Tanpa ini, kode growth 30D benar di atas data yang tak bisa membuktikannya | operasional |
| **P0-5** | **ER kanonik + konversi satuan** (D4) | 3 sumber, 3 satuan, selisih rata-rata 1,03 poin. Filter membaca yang terlemah (maks 223,41%) | keputusan produk: cakupan turun 1.756 → 22 |

## P1 — Penting, sesudah P0

| # | Task | Membuka |
|---|---|---|
| **P1-1** | Agregat per akun di L2 (D3) | 5 kolom tabel + 5 sort key + 2 filter |
| **P1-2** | Filter audiens: join roster→`audience_*_daily` (C2) | 3 filter; data & UI sudah siap |
| **P1-3** | Filter murah: Last Updated, `display_name` di list, search berjenjang (C1, C4) | filter ter-expose 8 → ~13 |
| **P1-4** | Expose layer feature (C5) | heatmap, format_performance, agregat — sudah dihitung, tak dipakai siapa pun |
| **P1-5** | Asset sentiment (D6) + content topic (D7) | **nol biaya Apify** — raw sudah ada di `raw_payload` |
| **P1-6** | Authenticity & audience quality dari `unified_follower` (D8) | menggantikan 2 angka mock yang menopang 4 skor komposit |
| **P1-7** | `growth_30d` + `days_between` + span guard (D1) | butuh migration; **baru berguna setelah P0-4 jalan ~1 bulan** |
| **P1-8** | Format mapping + `format_dominant` (D5) | filter Content Format |

## P2 — Nice-to-have / menunggu source

| # | Task | Penghambat |
|---|---|---|
| **P2-1** | Ajukan akses Insights API | E2–E5. **Lead time panjang — ajukan awal, kerjakan belakangan** |
| **P2-2** | Saved list / collection (C9) | tabel baru; kecil, mandiri, tak memblokir apa pun |
| **P2-3** | Brand Fit (D11) | menunggu P1-6 |
| **P2-4** | Competitor saturation (D10) | menunggu P1-5 |
| **P2-5** | Tabel monitoring per KOL (E13) | membuka #75–79 |
| **P2-6** | Exclusions & sections (D13, D14) | menunggu P1-1, P1-6 |
| **P2-7** | Creator city, niche, YouTube, Story | source baru |
| **P2-8** | Refresh on-demand roster (C8) | butuh antrean job |

## Empat keputusan produk yang memblokir, bukan teknis

| # | Pertanyaan |
|---|---|
| 1 | **Rate card**: pernah ada source-nya, atau memang belum pernah dibangun? |
| 2 | **NULL di filter**: `minEr`/`maxRate`/`growth` — KOL tanpa nilai ikut lolos atau terbuang? Sekarang terbuang diam-diam |
| 3 | **ER kanonik**: pindah ke L2 memangkas cakupan filter dari 1.756 ke 22 KOL |
| 4 | **Kategori**: chip prototype (Tech 4 KOL, Fitness 52) vs sebaran nyata (Lifestyle 2.592, Moms 589, Entertainment 501 — dua terakhir tak punya chip) |

---

# Catatan tentang kejujuran UI

Satu hal yang layak dicatat karena mudah disalahpahami sebagai gap: **UI aplikasi tidak merender kontrol yang backend-nya tidak bisa melayani.** `KolDirectoryFilters.tsx` menyebutkan secara eksplisit di komentar file bahwa filter audiens, authenticity, brand fit, paid ratio, campaigns, dan format sengaja ditinggalkan *"rather than shipped as controls that filter nothing"*.

Begitu pula `AudienceSection`: kartu "Audience Insights (terukur)" hanya muncul kalau L2 punya barisnya, lengkap dengan label `Diinferensi dari sampel follower` dan peringatan saat coverage <50%. Kartu sampel untuk dimensi yang sama otomatis disembunyikan supaya tidak ada dua angka untuk satu ide.

Jadi gap 8-dari-28 filter itu **bukan** UI yang bohong — itu UI yang menolak menampilkan kontrol kosong. Ini perilaku yang benar dan sebaiknya dipertahankan saat filter-filter baru ditambahkan.

---

*Read-only. Tidak ada perubahan kode, migration, UPDATE/DELETE, scraping Apify, commit, push, maupun pipeline/layer baru. Angka DB dikutip dari pengukuran langsung 8 September 2026 yang tercatat di dokumen-dokumen baseline; struktur endpoint dan konsumsi UI dibaca langsung dari `D:/intern/autometric` @ `84ea2fc`.*
