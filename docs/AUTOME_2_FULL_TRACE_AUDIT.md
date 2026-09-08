# AUTOME_2 — Full Trace Audit: Scraper → L0 → Harmonization → L1 → Feature → L2 → Endpoint → JOIN → Filter → UI

**Read-only · 8 September 2026 · tidak ada implementasi, migration, scraping, commit, atau push**

| Repo | Branch | Checkpoint | Working tree |
|---|---|---|---|
| `scrapper-project` | `main` | `116243e` | bersih |
| `autometric` | `engkol_v1` | `84ea2fc` | bersih |

Dokumen ini dimaksudkan sebagai **rujukan terakhir** — sesudah ini tidak perlu audit endpoint/filter/pipeline dari awal lagi.

---

# ⚠ Tiga temuan baru yang belum pernah muncul di audit mana pun

## T1 — Endpoint list memakai roster untuk identitas, padahal L2 jauh lebih lengkap

| Field | Roster (`kol_directory`) — **yang dipakai endpoint** | L2 (`kol_profile_card`) | Bisa ditambah |
|---|---:|---:|---:|
| **Avatar** | **931** | **1.976** | **+1.045** (2,1×) |
| **Bio** | **902** | **1.875** | **+973** (2,1×) |
| **Display name** | *kolom tidak ada* | **1.958** | **+1.958** |

Dan **nol kasus** di mana roster punya avatar tapi L2 tidak. L2 adalah superset.

Ini bukan gap data — ini **endpoint membaca sumber yang salah**, kelas yang sama persis dengan ER.

## T2 — Followers roster dan L2 berbeda untuk 52% akun, dan growth dihitung dari yang tidak ditampilkan

| Metrik | Nilai |
|---|---:|
| KOL punya followers di kedua sumber | 1.972 |
| **Sama persis** | 948 |
| **BERBEDA** | **1.024 (52%)** |
| Rata-rata selisih | **252.320** |

Sepuluh selisih terbesar:

| Username | Roster | L2 | Selisih |
|---|---:|---:|---:|
| `jennifer.coppen` | 4.100.000 | 17.200.000 | **+13.100.000** |
| `ibnuwardani` | 26.200.000 | 35.000.000 | +8.800.000 |
| `sptrakori_` | 13.100.000 | 20.200.000 | +7.100.000 |
| `soimah_pancawati` | 3.400.000 | 9.500.000 | +6.100.000 |
| `davinakaramoy` | 604.600 | 6.000.000 | +5.395.400 |
| `erickapineda09` | 11.800.000 | 16.800.000 | +5.000.000 |
| **`zeejkt48`** | 4.500.000 | **17** | **−4.499.983** ⚠ |
| `angelinawj` | 985.900 | 5.400.000 | +4.414.100 |
| `pandawaragroup` | 8.400.000 | 12.100.000 | +3.700.000 |
| `ardikatamps` | 349.000 | 4.000.000 | +3.651.000 |

Dua konsekuensi:

1. **UI menampilkan followers roster, tapi `growthPct` dihitung dari followers L2.** Angka growth tidak bisa direkonsiliasi dengan follower yang tampil — sudah terbukti di trace `pojoksatu.id` (10,5jt ditampilkan, growth dihitung dari 10,9jt→11,0jt).
2. **`zeejkt48` L2 = 17 followers** — nilai yang jelas rusak, dan ia lolos ke L2 tanpa penjaga. `NEEDS DECISION`: mana yang jadi source of truth, dan perlukah sanity guard.

## T3 — Badge verified Instagram ada 100% di L0, tidak pernah diekstrak

| Sumber | Terisi | Jadi kolom? |
|---|---:|---|
| `l0_raw.ig_profile_apify.raw_payload->>'verified'` | **953 / 953 baris** · **470 bertanda true** · 935 akun | **❌ TIDAK** |
| `l0_raw.tt_profile_apify.is_verified` | 1.058 baris · **131 true** | ✅ ya, sejak L0 |

Empat definisi "verified" yang hidup bersamaan:

| Definisi | Jumlah | Status |
|---|---:|---|
| Connected (OAuth) — **dipakai endpoint** | **0** | aktif |
| `kol_directory.verified_status` | 454 | dibuang 7 Sep |
| Badge platform TikTok (kolom L0) | 124 | tidak dipakai |
| **Badge platform Instagram (raw_payload)** | **470** | **tidak pernah diekstrak** |

Badge platform gabungan yang **bisa** tersedia: **594 KOL** (470 IG + 124 TT) — tanpa scraping baru.

---

# A. Data Profile — Inventaris Field End-to-End

Sumber: keluaran actor nyata (`output/instagram_profiles_*.jsonl`) + pengukuran DB 8 Sep.

## A.1 Instagram — dari actor sampai UI

| # | Field actor | L0 kolom | L0 fill | Harmoni­zation | L1 `unified_profile` | L1 fill | Attr/Derived | L2 `kol_profile_card` | Endpoint | Filter | UI | Status |
|---|---|---|---:|---|---|---:|---|---|---|---|---|---|
| 1 | `username` | `username` | 953 | `username` | `username` | 2.001 | attr | `username` | list+detail | `q` | ✅ | **READY** |
| 2 | `fullName` | `name` | 953 | `name` | `display_name` | 1.983 | attr | `display_name` **1.958** | **detail saja** | ❌ | detail | **ENDPOINT MISSING** (list) |
| 3 | `biography` | `biography` | 953 | `biography` | `bio` | 1.897 | attr | `bio` **1.875** | list pakai **roster 902** | ❌ | ✅ | **ENDPOINT WRONG SOURCE** |
| 4 | `profilePicUrl` | **raw_payload** | 953 | `avatar_url` (mig 007) | `avatar_url` | **2.001** | attr | `avatar_url` **1.976** | list pakai **roster 931** | — | ✅ | **ENDPOINT WRONG SOURCE** |
| 5 | `externalUrl` | `website` | 689 | `website` | `website` | 1.178 | attr | `website` **1.160** | detail | ❌ | ⚠ | **ENDPOINT MISSING** (list) |
| 6 | `followersCount` | `followers_count` | 949 | `followers_count` | `followers_count` | 1.997 | attr | `followers_count` 1.972 | list pakai **roster** | ✅ `follMin` | ✅ | **READY tapi mismatch** (T2) |
| 7 | `followsCount` | `follows_count` | 949 | `follows_count` | `following_count` | 1.997 | attr | `following_count` 1.972 | detail | ❌ | ⚠ | **ENDPOINT MISSING** (list) |
| 8 | `postsCount` | `media_count` | 927 | `media_count` | `media_count` | 1.975 | attr | `media_count` 1.950 | detail | ❌ | ⚠ | **ENDPOINT MISSING** (list) |
| 9 | **`verified`** | **❌ raw_payload saja** | **953** | ❌ | ❌ *(is_verified = Connected)* | — | attr | ❌ | ❌ | ❌ | ❌ | **PIPELINE MISSING** (T3) |
| 10 | `private` | **raw_payload** | 953 | ✅ | `is_private` | **2.001** | attr | `is_private` **1.976** | ❌ | ❌ | ❌ | **ENDPOINT MISSING** |
| 11 | `id` | **raw_payload** | 953 | ✅ | `platform_user_id` | **2.001** | attr | ❌ **tidak dibawa** | roster 1.031 | — | — | **L2 MISSING** |
| 12 | `url` | **raw_payload** | 953 | ✅ | `profile_url` | 2.001 | attr | `profile_url` 1.976 | list pakai roster | — | ✅ | **READY** |
| 13 | `businessCategoryName` | **raw_payload** | 754 | ❌ | ❌ | — | attr | ❌ | ❌ | ❌ | ❌ | **PIPELINE MISSING** |
| 14 | `isBusinessAccount` | **raw_payload** | 949 | ❌ | ❌ | — | attr | ❌ | ❌ | ❌ | ❌ | **PIPELINE MISSING** |
| 15 | `highlightReelCount` | **raw_payload** | 717 | ❌ | ❌ | — | attr | ❌ | ❌ | ❌ | ❌ | **PIPELINE MISSING** |
| 16 | `igtvVideoCount` | **raw_payload** | 717 | ❌ | ❌ | — | attr | ❌ | ❌ | ❌ | ❌ | **PIPELINE MISSING** |
| 17 | `relatedProfiles` | **raw_payload** | 717 | ❌ | ❌ | — | attr | ❌ | ❌ | ❌ | ❌ | **PIPELINE MISSING** |
| 18 | `latestPosts` | **raw_payload** | 953 | ❌ | ❌ | — | attr | ❌ | ❌ | ❌ | ❌ | dipakai `transform.py` untuk ER roster |

## A.2 TikTok — dari actor sampai UI

| # | Field actor | L0 kolom | L0 fill | L1 | L1 fill | L2 | Endpoint | Status |
|---|---|---|---:|---|---:|---|---|---|
| 1 | `authorMeta.name` | `username` | 1.058 | `username` | — | ✅ | list+detail | **READY** |
| 2 | `authorMeta.nickName` | `display_name` | 1.058 | `display_name` | — | ✅ | detail | **ENDPOINT MISSING** (list) |
| 3 | `authorMeta.signature` | `bio_description` | 983 | `bio` | — | ✅ | detail | idem |
| 4 | `authorMeta.avatar` | `avatar_url` | 1.058 | `avatar_url` | — | ✅ | roster | **ENDPOINT WRONG SOURCE** |
| 5 | **`authorMeta.verified`** | **`is_verified`** ✅ | 1.058 (**131 true**) | ❌ *ditimpa Connected* | — | ❌ | ❌ | **PIPELINE MISSING** |
| 6 | `authorMeta.fans` | `follower_count` | 1.058 | `followers_count` | — | ✅ | list roster | **READY tapi mismatch** |
| 7 | `authorMeta.following` | `following_count` | 1.058 | `following_count` | — | ✅ | detail | **ENDPOINT MISSING** (list) |
| 8 | `authorMeta.heart` | `likes_count` | 1.058 | `likes_count` | **1.051** | ❌ **tidak dibawa** | ❌ | **L2 MISSING** |
| 9 | `authorMeta.video` | `video_count` | 1.058 | `media_count` | — | ✅ | detail | **ENDPOINT MISSING** (list) |

---

# B. Pipeline — Di Mana Persisnya Gap Terjadi

## B.1 Berhenti di L0 (ada di `raw_payload`, tidak pernah jadi kolom)

| Field | Fill di L0 | Layer tempat berhenti |
|---|---:|---|
| `verified` (IG) | **953/953** | **L0 → tidak ada kolom, tidak ada mapping harmonization** |
| `businessCategoryName` | 754 | idem |
| `isBusinessAccount` | 949 | idem |
| `highlightReelCount` | 717 | idem |
| `igtvVideoCount` | 717 | idem |
| `relatedProfiles` | 717 | idem |
| `latestComments` (post) | ada | **L0 → tidak ada asset sentiment** |
| `taggedUsers`, `mentions` (post) | ada | **L0 → tidak ada asset kolaborasi** |

## B.2 Hilang saat harmonization

| Field | Bukti |
|---|---|
| **Badge platform TikTok** | `l0_harmonization.tiktok_profile.is_verified` = 1.051 terisi (131 true), **tapi `sp_build_unified_profile` menimpanya** dengan definisi Connected. Komentar migration 031 menyatakannya eksplisit: *"BUKAN Connected aplikasi. Tidak dibaca L1."* |

## B.3 Ada di L1, tidak masuk L2

15 kolom L1 tidak dibawa ke `kol_profile_card`. Yang **berisi** dan karena itu benar-benar hilang:

| Field | Fill di L1 | Kenapa penting |
|---|---:|---|
| **`platform_user_id`** | **2.001** | Anchor identitas; roster hanya punya 1.031 |
| **`likes_count`** | **1.051** (TikTok) | Total likes akun — metrik nyata yang hilang |

13 sisanya (`reach`, `profile_views`, `accounts_engaged`, `profile_links_taps`, `total_interactions`, `likes`, `comments`, `shares`, `saves`, `replies`, `reposts`, `open_id`, `has_insights`) semuanya **0 terisi** — memang menunggu Insights API, jadi tidak membawanya ke L2 adalah keputusan yang benar.

## B.4 Sudah tersedia tapi belum digunakan

| Field | Tersedia di | Dipakai? |
|---|---|---|
| Avatar, bio, display_name, website, following, media_count, is_private | **L2 `kol_profile_card`** | list endpoint pakai roster |
| `best_posting_time_heatmap` | `feature.*_engagement_analysis` (28 akun) | tidak di-expose |
| `format_performance` | `feature.ig_engagement_analysis` (17) | tidak di-expose |
| `total_likes/comments/views/shares/saves` per akun | feature (30 akun) | tidak di-expose |
| Rate card | `l0_raw.kol_roster_import` (7.496 KOL) + procedure | procedure tidak pernah dipanggil |

## B.5 Tertimpa / ter-dedup secara salah

| Kasus | Perilaku | Benar? |
|---|---|---|
| `is_verified` L1 | Ditimpa Connected, badge platform hilang | **Salah untuk requirement AUTOME_2** |
| `kol_directory.followers_count` | Ditimpa `db.update_profiles` tiap scrape | Benar — history hidup di `unified_profile` |
| `unified_profile` (akun, tanggal) | `ON CONFLICT DO UPDATE` di hari sama | Benar |
| L0 raw | Append-only, tanpa `ON CONFLICT` | Benar |
| `zeejkt48` followers = 17 di L2 | Lolos tanpa penjaga | **Perlu sanity guard** |

---

# C. Calculation — Attribute vs Metric

## C.1 Data attribute yang memang TIDAK butuh calculation

`username`, `display_name`, `bio`, `avatar_url`, `website`, `profile_url`, `platform_user_id`, `is_private`, `followers_count`, `following_count`, `media_count`, `likes_count`, `verified` badge, `category`, `agency`, `platform`.

Semua ini **atribut langsung**. Kalau kosong di UI, itu **pipeline/endpoint gap, bukan calculation gap**.

## C.2 Metric yang seharusnya dihitung

| Metric | Source | Formula | Layer seharusnya | Implementasi sekarang | Status | Sample hasil |
|---|---|---|---|---|---|---|
| **Tier** | `followers_count` | band lookup `kol_tiers` | L1 | ✅ `sp_build_unified_profile` | **READY** | Mega 313 · Macro 187 · Mid 1.809 · Micro 2.942 · Nano 1.943 |
| **ER (L2)** | `unified_post`+`unified_profile` | `engagement_sum / followers_denom_sum` | L2 | ✅ `gold.py` | **READY** (cakupan 22 akun) | `pojoksatu.id` = 0,00022143 |
| **ER (feature)** | idem | `Σeng / Σfollowers × 100` | Feature | ✅ | **READY** | `aamandazahra` = 16,15% |
| **ER (roster)** | `latestPosts` | `avg(like+comment)/followers×100` | Python | ⚠ ada tapi lemah | **CALCULATION WRONG** | maks **223,41%** |
| **Growth (snapshot)** | `unified_profile` 2 snapshot | `(now−prev)/prev×100` | L1 | ✅ `sp_build_unified_profile` | **READY** | `pojoksatu.id` = 0,9174% |
| **Growth 30D** | idem + `days_between` | `((f_now/f_prev)^(30/days))−1` | **L2** | ❌ | **CALCULATION MISSING** | — |
| **Post ER** | `post_metric` | `engagement_owned / followers_at_post_date` | L2 | ✅ `gold_post.py` | **READY** | maks 31,28% |
| Avg views / median views / posting freq / paid ratio / v2f / l2v | `post_metric`, `kol_metric_*` | agregat per akun | **L2** | ❌ | **CALCULATION MISSING** | — |
| `format_dominant` | `content_format_daily` | share per format | L2 | ❌ | **CALCULATION MISSING** | — |
| Authenticity / audience quality | `unified_follower` (2.548/27 akun) | belum didefinisikan | Feature | ❌ | **CALCULATION MISSING** | — |
| Sentiment | `raw_payload.latestComments` | belum ada | Feature | ❌ | **PIPELINE MISSING** | — |
| Content topic | caption + hashtag | belum ada | Feature | ❌ | **PIPELINE MISSING** | — |
| Brand fit / opportunity | komposit | 4/6 input mock | Feature | ❌ | **CALCULATION MISSING** | — |
| CPV / CPE / CPM / EMV | fee + views/reach | rasio | L2 | ❌ (fee kosong) | **SOURCE MISSING** → berubah setelah P0-1 | — |
| Consistency / momentum / stability / viral freq | `kol_metric_monthly` ≥4 titik | deret waktu | L2 | ❌ | **SOURCE MISSING** (waktu) | 0 akun memenuhi |

## C.3 Growth — trace snapshot sampai hasil

```
Apify profile actor  →  followersCount
   ↓  raw_store.insert_profiles (INSERT, append-only)
l0_raw.ig_profile_apify.followers_count            949/953
   ↓  sp_sync_instagram_profile()
l0_harmonization.instagram_profile.followers_count 946/950   (+ kolom `date`)
   ↓  sp_build_unified_profile()
l1_silver.unified_profile (grain: akun × date)     1.997 followers
   │   growth = (now − prev) / prev × 100
   │   prev  = baris dgn `date` terdekat lebih kecil, akun sama
   │   NULL kalau prev NULL / 0 / belum ada
   ↓
l1_silver.unified_profile.followers_growth         25 / 2.001
   ↓  gold_profile.py — DISTINCT ON (akun, platform) ORDER BY date DESC
l2_gold.kol_profile_card.followers_growth          25 / 1.976
   ↓  kolDirectory.ts BASE — LEFT JOIN LATERAL ... LIMIT 1
endpoint `growthPct`                                25 / 7.720
   ↓
UI kolom "Growth" + sort + tile "Sejak snapshot terakhir"
```

**Kondisi snapshot (terukur):** 1.947 akun punya **1** snapshot · 25 akun punya **2** · **0** akun punya ≥3. Span 10–13 hari, **0 akun ≥25 hari**.

Tanggal snapshot: 14 Agu (1.013) · 17 Agu (256) · 18 Agu (698) · 24 Agu (23) · 27 Agu (5) · 28 Agu (2).

---

# D. L2 — Grain, JOIN, NULL, Duplicate

| L2 table | Grain | Source | JOIN dari roster | Latest/snapshot logic | NULL handling | Duplicate risk |
|---|---|---|---|---|---|---|
| `kol_profile_card` | `(social_account_id, platform)` | `unified_profile` | `kd → ksa → c` | `DISTINCT ON` + `ORDER BY date DESC, updated_at DESC, id DESC` | NULL = tidak diketahui, tidak pernah 0 | **0** — diukur: 0 sid punya >1 card |
| `kol_metric_daily` | `(sid, platform, metric_date)` | `unified_post` + `unified_profile` | `kd → ksa → d` | `metric_date` = `posted_at` WIB | NULL kalau `posts_in_sample = 0` | **1:N — 28 dari 30 akun punya >1 tanggal. WAJIB agregat sebelum join** |
| `kol_metric_monthly` | `(sid, platform, month_start)` | `kol_metric_daily` | idem | `followers_eom` = hari terakhir ber-snapshot | `engagement_for_er_sum` diselaraskan penyebut | 1:N |
| `post_metric` | `(sid, platform, content_id)` | `unified_post` + feature | idem | — | `er_followers` NULL kalau tak lolos sampel / tanpa denominator | 1:N |
| `content_format_daily` | `(sid, platform, metric_date, media_type)` | `unified_post` | idem | — | idem `kol_metric_daily` | 1:N |
| `audience_demographics_daily` | `(sid, platform, audience_date, audience_type, dimension_key)` | `unified_follower` → feature | idem | `MAX(audience_date)` per akun | `unknown` disimpan sebagai baris | 1:N |
| `audience_geo_daily` | `+ geo_level, geo_key` | idem | idem | idem | idem | 1:N |
| `audience_interest_daily` | `+ interest_key` | idem | idem | idem | idem | 1:N |

## Feature → L2 gap

| Feature | Isi | Masuk L2? |
|---|---|---|
| `*_post_analysis.rank`, `.top_hashtags` | ✅ | ✅ ke `post_metric` |
| `*_post_analysis.engagement_rate` | ✅ | ❌ L2 hitung sendiri (konsisten <0,005 poin) |
| `*_post_analysis.sentiment_breakdown` | **0** | — |
| `*_engagement_analysis.engagement_rate` | 22 akun | ❌ tidak ke L2, tidak di-expose |
| `*_engagement_analysis.best_posting_time_heatmap` | 28 akun | **❌ tidak ke L2, tidak di-expose** |
| `*_engagement_analysis.format_performance` | 17 akun | **❌ tidak ke L2, tidak di-expose** |
| `*_audience_analysis` | 23 akun | ✅ ke `audience_*_daily` |
| `brand_fit_analysis` | **0** | tidak ada asset |

---

# E. Semua Endpoint

## E.1 `GET /api/organizations/[id]/discover/kol-directory` (LIST)

```text
UI  KolDirectoryPage.tsx
 → GET /api/organizations/[id]/discover/kol-directory?...
 → route.ts  (parse param, num() menjaga absen ≠ 0)
 → kolDirectory.listKolDirectory()
 → WITH base AS (BASE), filtered AS (...) SELECT *, COUNT(*) OVER()

 FROM  public.kol_directory kd                                    -- source utama
 LEFT JOIN public.platforms      pl ON pl.id = kd.platform_id     -- 1:1
 LEFT JOIN public.kol_tiers      t  ON kd.followers_count BETWEEN t.min AND t.max
 LEFT JOIN LATERAL (kol_categories WHERE id = ANY(category_ids)) cats
 LEFT JOIN LATERAL (
     kol_social_account ksa JOIN l2_gold.kol_profile_card c
     ORDER BY c.followers_count DESC NULLS LAST LIMIT 1) g        -- growth saja
 WHERE kd.directory_status = 'active'
 -- lalu di `filtered`: 10 klausa parameter
 ORDER BY  CASE status WHEN 'Live' THEN 0 WHEN 'Calculated' THEN 1 ELSE 2 END,
           <sort_column> <dir> NULLS LAST, username ASC
 LIMIT $7 OFFSET $8
 → attachRosterExtras()  -- agency + rate card, SESUDAH paging
```

| Aspek | Isi |
|---|---|
| Source table | `public.kol_directory` (7.720 aktif) |
| JOIN keys | `platform_id`, band followers, `category_ids`, `ksa.kol_id = kd.id` |
| Cardinality | semua 1:1 kecuali LATERAL yang di-`LIMIT 1` |
| Calculation di SQL | `connected` (EXISTS), `status` (CASE 3 cabang), `tier` (band) |
| Pagination | `page`, `pageSize` maks **60**, `COUNT(*) OVER()` |
| Returned fields | **18** — id, username, platform, profileUrl, avatarUrl, bio, city, categories, followers, erPct, tier, growthPct, connected, status, lastRefreshedAt, agency, rateFrom, rateCount |

## E.2 `GET .../kol-directory/[kolId]` (DETAIL)

```text
UI  KolCreatorWorkspace.tsx
 → getKolCreator(kolId)
 → base (sama dengan list) + LATERAL agency
 → Promise.all([ rank, platforms, similar, getKolMeasured(), getKolGold() ])
 → withProxiedCovers()
```

| Bagian | Source | Isi |
|---|---|---|
| `creator` | roster | `KolDirectoryRow` |
| `rank` | `kol_directory` | followers_rank, er_rank, category ranks — **semua pakai `kd.engagement_rate` roster** |
| `platforms[]` | roster | akun lain milik KOL yang sama |
| `similar[]` | roster | kategori+tier+ER |
| `measured` | **L1** `unified_post`, `unified_rate_card` | posts, rates, totals, averages, formats |
| `gold` | **L2** | `cards[]`, `daily[]`, `monthly[]`, `audience`, `posts[]`, `formats[]` |

## E.3 Endpoint lain

| Route | File | Source | Untuk roster KOL? |
|---|---|---|---|
| `.../[kolId]/cover/[postId]` | `kolPostCover.ts` | `unified_post.cover_image` | ✅ |
| `/discover/rates` | `rates.ts` | `unified_rate_card` (**0 baris**) | ✅ |
| `/discover/orders/*` (7) | `orders.ts`, `payment.ts` | tabel app + Midtrans | ✅ |
| `/discover/content`, `/content/post` | `content.ts`, `postAnalytics.ts` | `unified_post` + `unified_competitor_post` **brand** | ❌ korpus lain |
| `/discover/summary` | `summary.ts` | korpus brand | ❌ |
| `/discover/directory` | `directory.ts` | akun brand+kompetitor | ❌ |
| `/discover/creators/*` (5) | `creatorStore.ts` | `discover_creators` milik org | ❌ entitas lain |
| `/discover/assistant` | `assistant.ts` | agregat org | ✅ |
| `/discover/inspirations` | `inspirations.ts` | `discover_inspirations` | ✅ |

---

# F. JOIN Audit

| # | JOIN chain | Key | Kardinalitas | LEFT/INNER | Duplicate risk | Missing-row risk | Source of truth benar? |
|---|---|---|---|---|---|---|---|
| J1 | `kol_directory → platforms` | `platform_id` | 1:1 | LEFT | nol | **224 KOL tanpa `platform_id`** → `platform` NULL, baris tetap ada | ✅ |
| J2 | `kol_directory → kol_tiers` | band followers | 1:1 (band tidak tumpang tindih, diverifikasi mig 033) | LEFT | nol | 526 KOL tanpa tier (<1.000 / NULL) — **benar**, migration 034 | ✅ |
| J3 | `kol_directory → kol_categories` | `id = ANY(category_ids)` | 1:N → diagregasi `ARRAY_AGG` di LATERAL | LEFT LATERAL | **nol** (agregat) | 3.546 KOL tanpa kategori | ⚠ pakai `name`, bukan `taxonomy_key` |
| J4 | `kol_directory → ksa → kol_profile_card` (growth) | `ksa.kol_id = kd.id` | 1:1 terukur (**0** kol_id punya >1 ksa) | LEFT LATERAL **LIMIT 1** | **nol** | **224 KOL tanpa ksa** → growth NULL | ✅ |
| J5 | `kol_directory → ksa → social_account` (connected) | idem | 1:1 | **EXISTS** | nol | idem | ✅ |
| J6 | `kol_directory → ksa → unified_rate_card` (maxRate) | idem | 1:N | **EXISTS** | nol | **0 lolos** karena tabel kosong | ✅ pola benar |
| J7 | `kol_directory → agency_kol_accounts → agencies` | `kol_account_id = kd.id` | 1:N → `DISTINCT ON`/LATERAL LIMIT 1 | LEFT | nol | — | ✅ |
| J8 | roster → `kol_metric_daily` **(belum ada di endpoint)** | `sid` | **1:N — 28/30 akun punya >1 tanggal** | — | **TINGGI** | — | wajib agregat dulu |
| J9 | roster → `audience_*_daily` **(belum ada di endpoint)** | `sid` | 1:N | — | **TINGGI** | 23 akun saja | wajib `MAX(audience_date)` + agregat |

## Dampak JOIN terhadap coverage

| JOIN | Turun berapa | Sebab |
|---|---:|---|
| J1/J4/J5 (via `ksa`) | **−224 KOL** | Tidak punya `kol_social_account`. **Karena LEFT JOIN, barisnya tetap muncul** dengan field NULL — tidak hilang |
| J6 (`maxRate` aktif) | **−7.720** (semua) | `unified_rate_card` 0 baris |
| J2 | −526 dapat tier NULL | Benar sesuai migration 034 |

**Tidak ada satu pun INNER JOIN di jalur list.** Itu keputusan yang benar — tidak ada KOL yang hilang diam-diam.

---

# G. Filter Audit — SEMUA filter yang benar-benar ada

UI aplikasi punya **8 filter**. (Prototype AUTOME_2 minta 28; sisanya sengaja tidak dirender — lihat catatan di akhir.)

## G1 — `category`

```text
UI select Kategori → p.category → ?category=<name>
→ route.ts sp.get('category') → query.category || null → $3
→ WHERE ($3::text IS NULL OR $3 = ANY (b.categories))
→ b.categories = ARRAY_AGG(kol_categories.name) via LATERAL
```
| Aspek | Nilai |
|---|---|
| Type conversion | text, tanpa cast |
| NULL behavior | param absen → tanpa filter ✅ |
| Coverage | 4.174 KOL punya kategori; **3.546 tak punya → selalu terbuang** |
| Boundary | exact match, case-sensitive |
| **Status** | **FILTER BACKEND WRONG** — pakai `name` (28 nilai), bukan `taxonomy_key` (9). `db.py` di repo lain pakai `taxonomy_key` |

## G2 — `platform`

```text
UI chip → ?platform=instagram|tiktok → $2
→ WHERE ($2::text IS NULL OR b.platform = $2)
→ b.platform = platforms.key via kd.platform_id
```
| Aspek | Nilai |
|---|---|
| Coverage | IG 3.409 · TT 4.087 · 224 NULL |
| NULL | KOL tanpa platform selalu terbuang saat filter aktif |
| **Status** | **READY** (YouTube tidak ada barisnya) |

## G3 — `tier`

```text
UI select → ?tier=Mega,Macro → split(',') → $4 (text[])
→ WHERE ($4::text[] IS NULL OR b.tier = ANY ($4))
→ b.tier = kol_tiers.name via band followers
```
| Aspek | Nilai |
|---|---|
| Type | `text[]`, dari `split(',').filter(Boolean)` |
| Boundary | band diverifikasi tidak bercelah/tumpang tindih (mig 033) |
| Coverage | 7.194 punya tier; 526 NULL selalu terbuang |
| **Status** | **READY** |

## G4 — `follMin`

```text
UI slider (FOLLOWER_STEPS, skala non-linear) → ?follMin=100000
→ num('follMin') → Math.trunc() → $9 (bigint)
→ WHERE ($9::bigint IS NULL OR b.followers >= $9)
→ kol_directory.followers_count
```
| Aspek | Nilai |
|---|---|
| Type conversion | `Math.trunc`, bigint |
| NULL | 222 KOL tanpa followers terbuang saat aktif |
| Boundary | `>=` inklusif; slider `0` = tanpa batas (karena `if (f.follMin > 0)` di `filtersToParams`) |
| **Status** | **READY tapi mismatch** — memakai roster, sementara L2 berbeda untuk 1.024 KOL (T2) |

## G5 — `minEr`

```text
UI slider → ?minEr=3 → num('minEr') → $5 (float8)
→ WHERE ($5::float8 IS NULL OR b.er_pct >= $5)
→ kd.engagement_rate::float   ← ROSTER, bukan L2
```
| Aspek | Nilai |
|---|---|
| Satuan | **poin persen** |
| Coverage | 1.756 / 7.720 |
| **NULL behavior** | **5.964 KOL terbuang diam-diam** |
| Boundary terukur | `minEr=3` → 219 · `minEr=5,5` → 137 |
| Data quality | 83 nilai >10%, maks **223,41%** |
| **Status** | **FILTER BACKEND WRONG** — sumber terlemah dari tiga |

## G6 — `maxRate`

```text
UI slider (RATE_STEPS) → ?maxRate=5000000 → Math.trunc → $11 (bigint)
→ WHERE ($11::bigint IS NULL OR EXISTS (
     SELECT 1 FROM kol_social_account ksa
       JOIN l1_silver.unified_rate_card u ON u.social_account_id = ksa.social_account_id
      WHERE ksa.kol_id = b.id AND u.fee IS NOT NULL AND u.fee <= $11))
```
| Aspek | Nilai |
|---|---|
| Pola | EXISTS — benar, tidak menggandakan baris |
| **Hasil terukur** | **0 dari 7.720** |
| Sebab | `unified_rate_card` 0 baris — **source ada, procedure tidak dipanggil** |
| **Status** | **SOURCE MISSING** → berubah jadi READY setelah P0-1 |

## G7 — `connected`

```text
UI toggle → ?connected=1 → sp.get('connected') === '1' → $6 (boolean)
→ WHERE ($6::boolean IS NOT TRUE OR b.connected)
→ b.connected = EXISTS(social_account.platform_user_id AND oauth_token)
```
| Aspek | Nilai |
|---|---|
| Pola `IS NOT TRUE` | benar — false/null = tanpa filter |
| **Hasil** | **0 KOL** |
| **Status** | **READY tapi mismatch** — prototype minta badge platform (594 tersedia, T3) |

## G8 — `growth` (preset → `growthMin`/`growthMax`)

```text
UI select GROWTH_PRESETS → filtersToParams → ?growthMin=&growthMax=
→ num('growthMin'), num('growthMax') → $12, $13 (float8)
→ WHERE ($12::float8 IS NULL OR b.growth_pct >= $12)
  AND   ($13::float8 IS NULL OR b.growth_pct <= $13)
→ g.followers_growth::float via LATERAL ke l2_gold.kol_profile_card
```
| Aspek | Nilai |
|---|---|
| Preset | Any · >0% · =0% · <0% · ≥0,5% · ≥1% |
| `num()` | menjaga absen ≠ 0 — **penting, 0% nilai nyata** |
| Coverage | **25 / 7.720** |
| Boundary terukur | `≥0` → 18 · `≥0,5` → 3 · `≥4,5` → **0** · `≥8` → **0** · `≤0` → 15 |
| **Status** | **READY** (implementasi benar; datanya yang tipis) |

## Kombinasi filter

Seluruh klausa memakai pola `($n IS NULL OR ...)` dan digabung `AND` di satu CTE `filtered` — **tidak ada urutan yang bisa saling meniadakan**. Risiko nyata: kombinasi apa pun dengan `maxRate` → **0 hasil**, karena EXISTS-nya selalu false.

---

# H. Sort

```text
UI SORTOPTS → ?sort=<key>&dir=<asc|desc>
→ orderBy(key, dir)
→ SORT_COLUMNS whitelist (aman dari injection)
→ ORDER BY SCRAPED_FIRST, <col> <dir> NULLS LAST, username ASC
```

| UI sort | `SORT_COLUMNS` | Source column | NULL handling | Sama dgn yang ditampilkan? |
|---|---|---|---|---|
| Followers | `followers` | `kol_directory.followers_count` | NULLS LAST | ✅ |
| Engagement | `er_pct` | `kd.engagement_rate` | NULLS LAST | ✅ (tapi sumber roster) |
| **Growth** | `growth_pct` | `l2_gold.kol_profile_card.followers_growth` | NULLS LAST | ✅ |
| Last updated | `last_refreshed_at` | roster | NULLS LAST | ✅ |
| Name | `username` | roster | — | ✅ |
| *(tak di UI)* | `created_at` | roster | NULLS LAST | untuk shelf "Recently added" |

## ⚠ `SCRAPED_FIRST` selalu jadi kunci pertama

```sql
CASE status WHEN 'Live' THEN 0 WHEN 'Calculated' THEN 1 ELSE 2 END ASC
```

Dengan sebaran terukur **Live 0 · Calculated 27 · Estimated 7.693**, efeknya: **27 KOL selalu di puncak, apa pun sort yang dipilih user.** Prototype AUTOME_2 tidak punya perilaku ini. `NEEDS DECISION`.

---

# I. End-to-End Sample — 5 KOL

## I.1 `pojoksatu.id` (TikTok) — Growth berhasil, followers mismatch

| Layer | Nilai |
|---|---|
| L1 snapshot | 14 Agu **10.900.000** → 24 Agu **11.000.000** |
| L1 `followers_growth` | **0,9174** |
| L2 `kol_profile_card` | followers **11.000.000**, growth 0,9174, snapshot 2026-08-24 |
| L2 `kol_metric_daily` | 20 Agu: 10 post, eng 24.136, denom 109.000.000, ER **0,00022143** |
| Endpoint JSON | `followers` **10.500.000** ⚠ · `erPct` **0,01** ⚠ · `growthPct` 0,9174 ✅ · `lastRefreshedAt` **2023-08-16** ⚠ |
| UI | Followers 10,5jt · Growth +0,92% · ER 0,01% |

**Mismatch pertama terjadi di layer ENDPOINT** — bukan di scraper, L0, L1, maupun L2. Endpoint memilih roster untuk followers/ER/lastRefreshed, tapi L2 untuk growth.

## I.2 `aamandazahra` (Instagram) — ER dari 2 post

| Layer | Nilai |
|---|---|
| L2 `post_metric` | 10 post; hanya **2** punya `followers_at_post_date` (26 Agu) |
| Perhitungan | (373.699 + 12.179) / (1.194.675 × 2) = **16,1499%** |
| Feature ER | 16,15% ✅ konsisten |
| Endpoint | `creator.erPct` = **6,94** (roster) · `gold.daily[].erFollowers` = 0,16149915 (L2) |
| UI | Menampilkan keduanya di layar berbeda |

**Mismatch pertama di ENDPOINT** — dua ER berbeda satuan dalam satu response.

## I.3 `jennifer.coppen` — selisih followers terbesar

| Layer | Nilai |
|---|---|
| Roster | **4.100.000** |
| L2 | **17.200.000** |
| Selisih | **+13.100.000** |
| Endpoint | menampilkan **4.100.000** |

**Mismatch pertama di L0/roster vs L1** — `kol_directory.followers_count` tidak ikut ter-refresh saat L1 punya angka baru. `NEEDS DECISION` mana yang benar.

## I.4 `zeejkt48` — nilai L2 rusak

| Layer | Nilai |
|---|---|
| Roster | 4.500.000 |
| **L2** | **17** ⚠ |

**Mismatch pertama di L0 atau harmonization** — perlu ditelusuri satu tingkat lagi. Tidak ada sanity guard yang menahannya. `NEEDS DECISION`: perlukah penjaga nilai mustahil.

## I.5 `irwansyah_15` — post_count menggelembung

| Layer | Nilai |
|---|---|
| L0 (20 Agu) | 10 item dari URL-nya, **1** miliknya |
| L1 `unified_post` | 10 baris, 9 ber-`is_collaboration = true` |
| L2 `kol_metric_daily` | `post_count` **10**, `posts_in_sample` **0** |
| ER | **NULL** — benar, semua kena aturan sampel |

**Tidak ada mismatch** — pengaman `is_collaboration` bekerja. Yang menggelembung hanya `post_count`, dan konsumennya (posting frequency) belum ada.

---

# J. Final Gap Matrix

| Data/Metric | Source | Pipeline | Calculation | L2 | Endpoint | JOIN | Filter | UI | Status | Priority |
|---|---|---|---|---|---|---|---|---|---|---|
| Username | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | **READY** | — |
| Platform | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | **READY** | — |
| Tier | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **READY** | — |
| Followers | ✅ | ✅ | — | ✅ | ⚠ roster | ✅ | ✅ | ✅ | **ENDPOINT WRONG SOURCE** | **P0** |
| **Avatar** | ✅ | ✅ | — | **1.976** | ⚠ roster **931** | ✅ | — | ✅ | **ENDPOINT WRONG SOURCE** | **P0** |
| **Bio** | ✅ | ✅ | — | **1.875** | ⚠ roster **902** | ✅ | ❌ | ✅ | **ENDPOINT WRONG SOURCE** | **P0** |
| **Display name** | ✅ | ✅ | — | **1.958** | detail saja | ✅ | ❌ | detail | **ENDPOINT MISSING** | **P0** |
| Website / following / media_count / is_private | ✅ | ✅ | — | ✅ | detail saja | ✅ | ❌ | ⚠ | **ENDPOINT MISSING** | P1 |
| `platform_user_id` | ✅ | ✅ L1 | — | **❌** | roster 1.031 | — | — | — | **L2 MISSING** | P2 |
| `likes_count` (TikTok) | ✅ | ✅ L1 1.051 | — | **❌** | ❌ | — | — | ❌ | **L2 MISSING** | P2 |
| **Badge verified IG** | ✅ **raw 953** | **❌** | — | ❌ | ❌ | — | ❌ | ❌ | **PIPELINE MISSING** | **P0** |
| Badge verified TikTok | ✅ L0 kolom | ❌ ditimpa | — | ❌ | ❌ | — | ❌ | ❌ | **PIPELINE MISSING** | **P0** |
| Connected (OAuth) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **READY** (0 KOL) | — |
| Kategori | ✅ | ✅ | — | — | ✅ | ✅ | ⚠ `name` | ✅ | **FILTER BACKEND WRONG** | P1 |
| Agency | ✅ | ✅ | — | — | ✅ | ✅ | ❌ | ✅ | **READY** | — |
| Creator city | ❌ 0 | — | — | — | ✅ | — | ❌ | ✅ | **SOURCE MISSING** | P2 |
| **Rate card** | ✅ **7.496 KOL** | **❌ procedure tak dipanggil** | ✅ ada | ❌ | ✅ | ✅ | ⚠ 0 hasil | ✅ | **PIPELINE MISSING** | **P0** |
| ER (canonical) | ✅ | ✅ | ⚠ 3 versi | ✅ 22 akun | ⚠ roster | ✅ | ⚠ | ✅ | **FILTER BACKEND WRONG** | **P0** |
| Growth (snapshot) | ✅ 25 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **READY** | — |
| Growth 30D + `days_between` | ⚠ span 10–13h | — | **❌** | ❌ | ❌ | — | ❌ | ❌ | **CALCULATION MISSING** | P1 |
| Growth classification | — | — | ❌ | ❌ | ❌ | — | ❌ | ❌ | **CALCULATION MISSING** | P1 |
| Post likes/comments/views/ER/rank/hashtag | ✅ 503 | ✅ | ✅ | ✅ | ✅ detail | ✅ | ❌ | ✅ | **READY** (30 KOL) | — |
| Post shares/saves | ❌ IG | ✅ TT | — | ✅ | ✅ | ✅ | ❌ | ⚠ | **SOURCE MISSING** | P2 |
| Format raw | ✅ 300 | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | **READY** | — |
| Format mapping + dominant | ✅ | — | **❌** | ❌ | ❌ | — | ❌ | ❌ | **CALCULATION MISSING** | P1 |
| Avg/median views, posting freq, paid ratio, v2f, l2v | ✅ | ✅ | **❌** | ❌ | ⚠ mentah | — | ❌ | ⚠ | **CALCULATION MISSING** | P1 |
| Sentiment | ✅ raw | **❌** | ❌ | ❌ | ❌ | — | ❌ | ⚠ | **PIPELINE MISSING** | P1 |
| Content topic | ✅ raw | **❌** | ❌ | ❌ | ❌ | — | ❌ | ⚠ | **PIPELINE MISSING** | P1 |
| Audience gender/geo/interest | ✅ inferred | ✅ | ✅ | ✅ 23 KOL | ✅ detail | ⚠ 1:N | **❌** | ✅ | **FILTER MISSING** | P1 |
| Audience age | ❌ 0 | — | — | kolom ada | ✅ kosong | — | ❌ | ✅ siap | **SOURCE MISSING** | P2 |
| Authenticity / audience quality | ✅ `unified_follower` | ✅ | **❌** | ❌ | ❌ | — | ❌ | ⚠ | **CALCULATION MISSING** | P1 |
| Heatmap jam posting | ✅ 28 akun | ✅ Feature | ✅ | **❌** | **❌** | — | ❌ | ❌ | **ENDPOINT MISSING** | P1 |
| `format_performance` | ✅ 17 akun | ✅ Feature | ✅ | ❌ | **❌** | — | ❌ | ❌ | **ENDPOINT MISSING** | P1 |
| Agregat feature per akun | ✅ 30 akun | ✅ | ✅ | ❌ | **❌** | — | ❌ | ❌ | **ENDPOINT MISSING** | P1 |
| Reach / impressions / watch time | ❌ 0 | — | — | kolom ada | ❌ | — | ❌ | ⚠ | **SOURCE MISSING** | P2 |
| CPV/CPE/CPM/EMV | ⚠ menunggu fee | — | ❌ | ❌ | ❌ | — | ❌ | ⚠ | **SOURCE MISSING** | P1 (setelah rate card) |
| Brand fit / opportunity | ❌ 0 baris | ❌ no asset | ❌ | ❌ | ❌ | — | ❌ | ⚠ | **CALCULATION MISSING** | P2 |
| Consistency/momentum/stability/viral | ⚠ 0 akun ≥3 snapshot | ✅ | ❌ | ⚠ | ⚠ | — | ❌ | ⚠ | **SOURCE MISSING** (waktu) | P2 |
| Data status badge | ✅ | ✅ | ⚠ Live 0 | — | ✅ | — | ❌ | ✅ | **CALCULATION WRONG** | P1 |
| Last Updated filter | ✅ 7.496 | ✅ | — | — | field ✅ | — | **❌** | ✅ | **FILTER MISSING** | P1 |
| Monitoring/freshness (5 filter) | ❌ | — | ❌ | ❌ | ❌ | — | ❌ | ❌ | **SOURCE MISSING** | P2 |
| Search multi-field | ⚠ | — | — | — | ⚠ username | — | ⚠ | ✅ | **FILTER BACKEND WRONG** | P1 |
| Sort (34 diminta) | ⚠ | — | — | — | 6 key | — | ⚠ `SCRAPED_FIRST` | ✅ | **READY tapi mismatch** | P1 |
| Saved list / collection | ❌ tabel | — | — | — | ❌ | — | ❌ | ❌ | **SOURCE MISSING** | P2 |
| Compare / Ordering / Negotiation / Assistant | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | ✅ | **READY** | — |

---

# Kesimpulan

## 1. Apa yang sudah benar

- **Pipeline L0 → L1 tidak kehilangan apa pun**: profil 1.976→1.976, post 30→30, keduanya 0%.
- **Semua JOIN di jalur list memakai LEFT/EXISTS** — tidak ada KOL yang hilang diam-diam. LATERAL selalu di-`LIMIT 1`, duplikasi nol (diverifikasi: 0 `kol_id` punya >1 `ksa`).
- **Sort di-whitelist**, aman dari injection, `NULLS LAST` di kedua arah.
- **Growth mengalir utuh** L1 → L2 → endpoint → UI tanpa transformasi.
- **Audiens ter-wire penuh** di detail, dengan coverage dan label `inferred_*`.
- **Aturan sampel ER benar** — `is_collaboration` menyelamatkan 43 baris salah atribusi dari mencemari ER (0/43 masuk).
- **UI jujur** — hanya merender filter yang backend-nya bekerja.

## 2. Apa yang missing

| Kategori | Item |
|---|---|
| **Pipeline** | badge verified IG (953 di raw) & TikTok (131), sentiment, content topic, rate card (procedure tak dipanggil) |
| **Calculation** | Growth 30D, format_dominant, agregat per akun, authenticity, audience quality, brand fit |
| **L2** | `platform_user_id`, `likes_count` |
| **Endpoint** | identitas dari L2 di list, layer feature, filter audiens, filter Last Updated |
| **Source** | reach/impressions/watch time/umur (Insights API), Story, YouTube, creator city, campaign history, snapshot berkala |

## 3. Apa yang salah

| # | Salah | Bukti |
|---|---|---|
| 1 | Endpoint list ambil identitas dari roster, padahal L2 2,1× lebih lengkap | avatar 931 vs 1.976 · bio 902 vs 1.875 |
| 2 | Followers roster ≠ L2 untuk **1.024 KOL**, dan growth dihitung dari yang tidak ditampilkan | rata-rata selisih 252.320 |
| 3 | `minEr` pakai sumber terlemah | maks 223,41%, buang 5.964 KOL |
| 4 | `maxRate` selalu 0 hasil | tabel kosong padahal source ada |
| 5 | Kategori pakai `name`, bukan `taxonomy_key` | dua implementasi berbeda |
| 6 | `SCRAPED_FIRST` menaruh 27 KOL di puncak apa pun sort-nya | Live 0 · Calculated 27 |
| 7 | Badge verified hilang di L1 (ditimpa Connected) | 594 badge tersedia, 0 dipakai |
| 8 | `zeejkt48` followers = 17 di L2 | tanpa sanity guard |

## 4. Apa yang perlu development

Diurutkan pada bagian 6.

## 5. Dependency / decision yang benar-benar dibutuhkan

| # | Keputusan | Kenapa memblokir |
|---|---|---|
| **D1** | Jalankan `sp_sync_roster_rate_card`? | Membuka 7 requirement komersial + memperbaiki `maxRate` |
| **D2** | Source of truth identitas & followers: roster atau L2? | Menentukan #1 dan #2 di daftar "salah" |
| **D3** | NULL di filter: buang, ikut lolos, atau tandai? | 5.964 KOL pada `minEr` |
| **D4** | Canonical ER — **tunda sampai cakupan naik** | 1.756 → 22 |
| **D5** | Badge verified: platform (594) atau Connected (0)? | Prototype minta platform |
| **D6** | `SCRAPED_FIRST` dipertahankan? | Mengubah semua urutan |
| **D7** | Budget Apify | Post scraping + snapshot berkala |

## 6. Urutan development paling aman

| # | Langkah | Kenapa urutannya begini | Butuh |
|---|---|---|---|
| **1** | **Verifikasi read-only rate card** (simulasi procedure sebagai SELECT) | Nol risiko, nol biaya, mengubah D1 jadi keputusan berangka | — |
| **2** | **Jalankan procedure rate card** | Membuka 7 requirement + memperbaiki filter yang sekarang salah. Tanpa kode, tanpa migration | **D1** |
| **3** | **Pindahkan identitas list ke L2** (avatar, bio, display_name) | Satu file, satu LATERAL yang **sudah ada** untuk growth — tinggal ambil kolom lain dari `g`. Avatar +1.045, bio +973, display_name +1.958 | **D2** |
| **4** | **Perbaiki NULL handling 3 filter** | Satu file, tiga klausa WHERE | **D3** |
| **5** | **Perluas post scraping bertahap** | Menaikkan cakupan ER/konten. Ownership fix sudah ter-commit | **D7** |
| **6** | **Scheduler profil berkala** | Prasyarat Growth 30D & consistency. Mulai sekarang → span 30 hari awal Oktober | **D7** |
| **7** | **Angkat badge verified IG/TikTok ke L1** | Membuka filter Verified dengan 594 KOL | **D5** |
| **8** | **Agregat per akun di L2** | 5 kolom tabel + 5 sort key + 2 filter | — |
| **9** | **Expose layer feature** | Sudah dihitung, tidak dipakai | — |
| **10** | **Asset sentiment & content topic** | Nol biaya Apify | — |
| **11** | **Canonical ER** | Sengaja terakhir — keputusan D4 jauh lebih mudah setelah langkah 5 | **D4** |

**Langkah 1–4 tidak butuh scraping, tidak butuh migration, dan tidak butuh menunggu waktu.** Langkah 3 memakai LATERAL yang sudah ada di `BASE` untuk growth — tinggal menambah kolom yang di-SELECT.

---

*Read-only. Tidak ada implementasi, scraper baru, pipeline baru, endpoint baru, tabel baru, migration, maupun layer baru. Seluruh angka diukur langsung ke database 8 September 2026 lewat sesi `set_session(readonly=True)`; struktur endpoint, JOIN, filter, dan konsumsi UI dibaca dari `D:/intern/autometric` @ `84ea2fc`.*
