# AUTOME_2 — Development Readiness Audit

**Read-only · 8 September 2026 · tidak ada perubahan kode / migration / endpoint / commit / scraping**

| Sumber | Detail |
|---|---|
| Requirement UI | `app/AUTOME_2.html` — 5.736 baris, 41 modul JS |
| Backend/API | `D:/intern/autometric` branch `engkol_v1` @ `19e2616` |
| Pipeline | `scrapper-project` @ `4903965` — 34 migration, 19 Dagster asset |
| Database | `kol` @ `10.100.14.216` — **diverifikasi langsung 2026-09-08 05:58**, sesi `set_session(readonly=True)` |
| Jendela harvest | **2026-08-14 s.d. 2026-08-28** |

Seluruh angka di dokumen ini **terukur**, bukan dikutip. Script verifikasi: `scratchpad/audit_verify.py` (28 query) + `scratchpad/q2.py` (10 query lanjutan). Keduanya read-only.

---

## ⚠ Dua koreksi terhadap laporan saya sebelumnya

### K-1 — Rate card KOSONG. Saya salah di sesi lalu.

Sesi lalu saya bilang F-3 sudah terjawab dan `unified_rate_card` berisi **9.210 baris / 7.230 akun**. **Itu salah.** Angka tersebut saya ambil dari docstring `gold_profile.py` dan `kolMeasured.ts` — dan docstring itu sendiri tidak akurat.

Hasil pengukuran:

| Tabel | Baris |
|---|---:|
| `l0_extra.ig_rate_card` | **0** |
| `l0_extra.tt_rate_card` | **0** |
| `l0_harmonization.instagram_rate_card` | **0** |
| `l0_harmonization.tiktok_rate_card` | **0** |
| `l1_silver.unified_rate_card` | **0** |

Kosong di **seluruh lima tabel, di semua layer**. Yang benar adalah `docs/KOL_DISCOVERY_AUDIT.md` (3 Sep).

**Konsekuensi yang harus lo tahu:** filter `?maxRate=` memakai `EXISTS (… u.fee IS NOT NULL AND u.fee <= $11)`. Diukur langsung — **0 dari 7.720 KOL lolos**. Begitu slider "Max. rate card" digeser dari nilai maksimum, direktori jadi kosong total. Ini bukan filter yang belum ada; ini filter yang aktif dan selalu mengembalikan nol. Rate card, CPV, CPE, dan seluruh alur Ordering/checkout ikut kehilangan dasarnya.

### K-2 — Endpoint detail memang selengkap yang saya bilang.

Ini yang benar dan tetap berlaku: `getKolCreator()` memanggil `getKolGold()` + `getKolMeasured()`, sehingga `GET /discover/kol-directory/[kolId]` sudah mengembalikan profile card, daily, monthly, audience, posts, dan formats dari L2. Gap endpoint yang sebenarnya ada di **list endpoint** dan **layer feature**, bukan di detail.

---

# 1. Executive Summary

**87 requirement aktif** (dead code sudah dibuang — lihat §1.3).

| Status | Jumlah |
|---|---:|
| **READY** | **15** |
| **NEED CALCULATION** | **13** |
| **NEED PIPELINE** | **4** |
| **NEED ENDPOINT** | **4** |
| **NEED FILTER** | **13** |
| **NEED SOURCE/SCRAPING** | **29** |
| **BLOCKED** | **8** |
| **AMBIGUOUS** | **1** |

## 1.1 Lima angka yang menentukan segalanya

| # | Fakta terukur | Dampak |
|---|---|---|
| **1** | **Rate card 0 baris** di 5 tabel, semua layer | Filter `maxRate` mengembalikan 0 KOL. CPV, CPE, EMV, Ordering tanpa dasar harga |
| **2** | **Snapshot profil hanya 2 tanggal per akun, span 10–13 hari.** 1.947 akun cuma punya 1 snapshot; **25 akun** punya 2; **0 akun** punya span ≥25 hari | Growth 30D tidak bisa dihitung. Memblokir 4 requirement + 2 filter + 4 sort key |
| **3** | **Metrik post hanya menjangkau 30 dari 7.720 KOL (0,39%).** Audiens 23 KOL (0,30%) | Setiap metrik turunan post & audiens mewarisi cakupan ini |
| **4** | **Data status badge: Estimated 7.693 · Calculated 27 · Live 0** | Rumusnya benar, tapi ambang "≤7 hari" vs scrape terakhir 28 Agu (11 hari lalu) membuat badge praktis konstan |
| **5** | **3.546 dari 7.720 KOL (46%) tanpa kategori**; taxonomy_key valid hanya untuk **4.155 (53,8%)** | Filter kategori membuang hampir separuh roster |

## 1.2 Dampak klarifikasi lo

| Klarifikasi | Hasil setelah verifikasi |
|---|---|
| Category: DB = source of truth, alias UI→DB | **Berhasil, tapi sebarannya bermasalah.** 9 taxonomy_key ada. Chip prototype: Lifestyle **2.592**, Beauty **1.271**, Food **123**, Fitness **52**, Tech **4**. Sementara Moms (589) & Entertainment (501) tidak punya chip. 6 nama mentah ber-`taxonomy_key` NULL |
| `interests` vs `mainTopic/subTopic` dipisah | Audience interest **ada** (214 baris / 23 KOL, inferred). Content topic **belum** — `content_category` masih blocked. Proxy sementara valid sesuai aturan lo |
| Content format mapping | Nilai mentah terukur **persis 6**: `clips`, `carousel_container`, `feed`, `unknown` (IG) · `VIDEO`, `CAROUSEL` (TT). **Tidak ada satu pun story type** → bucket Story akan selalu kosong |
| Growth 30D formula CAGR | Formula benar; **datanya tidak memenuhi**. Detail & bukti di §3.1 |
| Threshold ke config | Tetap direkomendasikan; belum bisa dikalibrasi karena sampelnya 25 akun |
| Currency IDR + `currency_code` | **Tidak bisa dijalankan sekarang** — tidak ada satu pun baris fee |
| Creator city / niche nullable | Terkonfirmasi `creator_city` = **0 dari 7.720**. Tetap P2 |

## 1.3 Dead code yang tidak dihitung

`directory-filters2.js` mendefinisikan ulang `filterPanelHTML()` dan `activeFilterCount()`. Yang dirender adalah `FPG` (6 grup / 28 filter). Panel lama — slider **Min. est. reach, Min. posting freq, Min. authenticity, Min. brand fit, Max. paid ratio, Min. campaigns** dan `filterModalHTML()` — tidak pernah tampil, walaupun state-nya masih dibaca `filterKols()`.

Ambang tier panel mati (`Mid-tier 50K–100K`) juga diabaikan. Yang berlaku `TIER_TIP` panel hidup, dan **terbukti cocok** dengan `public.kol_tiers`.

---

# 2. Full Requirement Matrix

## 2.1 Identitas & roster

| Requirement AUTOME_2 | Source DB | Column | Data tersedia? | Pipeline | Calculation | L2 | Endpoint | Filter | Status |
|---|---|---|---|---|---|---|---|---|---|
| Username | `kol_directory` | `username` | **7.497 / 7.720 (97,1%)** | roster | — | — | list + detail | `q` | **READY** |
| Display name | `kol_profile_card` | `display_name` | **1.976 kartu** | ✅ | — | ✅ | **detail saja** | tidak dicari | **NEED ENDPOINT** |
| Avatar | `kol_directory` | `avatar_url` | **931 (12,1%)** | roster | — | — | list + detail | — | **READY** |
| Bio | `kol_directory` | `bio` | **902 (11,7%)** | roster | — | — | list + detail | tidak dicari | **NEED FILTER** |
| Profile URL | `kol_directory` | `profile_url` | ✓ | roster | — | — | list + detail | — | **READY** |
| Platform | `platforms.key` | — | **tiktok 4.087 · instagram 3.409** | roster | — | — | list | `platform` | **READY** (YouTube tidak ada baris) |
| Kategori | `kol_categories` | `taxonomy_key` (9) / `name` (28) | **4.155 (53,8%)** | roster | alias UI→DB | — | list pakai `name` | `category` | **NEED FILTER** |
| Tier | `kol_tiers` | `name` + band | **7.194 / 7.720 (93,2%)** | ✅ L1→L2 | band lookup | ✅ | list | `tier[]` | **READY** |
| Followers | `kol_directory` | `followers_count` | **7.498 (97,1%)** | roster | — | — | list + detail | `follMin` | **READY** |
| Agency | `agency_kol_accounts` + `agencies` | `name` | ✓ | roster | — | — | list + detail | — | **READY** |
| Verified / Connected | `social_account` | `platform_user_id` + `oauth_token` | **Connected = 0** · badge `verified_status` = 454 · TikTok L0 = 124 | ✅ | boolean EXISTS | ✅ | list | `connected` | **NEED SOURCE** |
| Data status badge | `kol_directory` | `last_refreshed_at` + `scrape_status` | **Estimated 7.693 · Calculated 27 · Live 0** | roster | CASE 3 cabang | — | list + detail | — | **NEED CALCULATION** |
| Last synced | `kol_directory` | `last_refreshed_at` | **7.496** | roster | — | — | list + detail | **tidak ada param** | **NEED FILTER** |
| Creator city | `kol_directory` | `creator_city` | **0 / 7.720** | tidak diisi | — | — | list (`city`) | — | **NEED SOURCE** |
| Niche / sub-label | — | — | ✗ | — | — | — | — | — | **NEED SOURCE** |

## 2.2 Performa

| Requirement AUTOME_2 | Source DB | Column | Data tersedia? | Pipeline | Calculation | L2 | Endpoint | Filter | Status |
|---|---|---|---|---|---|---|---|---|---|
| Engagement rate | 3 sumber (§3.2) | `engagement_rate` / `er_followers_daily` | roster **1.756** · feature **22 akun** · L2 **73 / 280 baris** | ✅ | ada, **3 versi beda satuan** | ✅ | list (roster) + detail (L2) | `minEr` (roster) | **NEED CALCULATION** |
| Avg views | `kol_metric_daily` | `views_sum`, `posts_in_sample` | **30 akun** | ✅ | **belum ada** | ✅ | detail (mentah) | — | **NEED CALCULATION** |
| Median views | `post_metric` | `views` | **477 post / 30 akun** | ✅ | **belum ada** | ✅ | detail (mentah) | — | **NEED CALCULATION** |
| Avg likes | `feature.*_engagement_analysis` | `total_likes / posts_analyzed_count` | **30 akun** (IG 19 · TT 11) | ✅ | ✅ ada | — | **tidak** | — | **NEED ENDPOINT** |
| Avg comments | idem | `total_comments / …` | idem | ✅ | ✅ ada | — | **tidak** | — | **NEED ENDPOINT** |
| Avg shares | `post_metric` | `shares` | **IG 0/186 · TT 291/291** | ✅ | belum | ✅ | detail | — | **NEED SOURCE** (IG) |
| Avg saves | `post_metric` | `saves` | **IG 0/186 · TT 291/291** | ✅ | belum | ✅ | detail | — | **NEED SOURCE** (IG) |
| Save rate | `post_metric` | `saves`/`views` | TikTok saja | ✅ | belum | ✅ | — | — | **NEED SOURCE** |
| Share rate | `post_metric` | `shares`/`views` | TikTok saja | ✅ | belum | ✅ | — | — | **NEED SOURCE** |
| View-to-follower | `post_metric` + `kol_profile_card` | `views`/`followers` | **IG 102/186 · TT 291/291** | ✅ | **belum ada** | ✅ | — | — | **NEED CALCULATION** |
| Like-to-view | `post_metric` | `likes`/`views` | idem | ✅ | **belum ada** | ✅ | — | — | **NEED CALCULATION** |
| Reach / Est. reach | — | `reach` | **0 / 477** | *blocked* | — | kolom ada | — | — | **NEED SOURCE** |
| Impressions | — | — | ✗ | — | — | — | — | — | **NEED SOURCE** |
| Posting frequency | `kol_metric_monthly` | `post_count`, `active_days` | **68 baris / 30 akun** | ✅ | **belum ada** | ✅ | detail (mentah) | — | **NEED CALCULATION** |
| Paid / sponsored ratio | `post_metric` | `is_sponsored` | **IG 176/186 · TT 291/291** flag terisi; 9 dari 30 akun punya sponsored | ✅ | **belum ada** | ✅ | detail (mentah) | — | **NEED CALCULATION** |

## 2.3 Growth

| Requirement AUTOME_2 | Source DB | Column | Data tersedia? | Pipeline | Calculation | L2 | Endpoint | Filter | Status |
|---|---|---|---|---|---|---|---|---|---|
| Growth 30D | `unified_profile` | `followers_count` + `date` | **25 / 1.972 akun · span 10–13 hari · 0 akun ≥25 hari** | `sp_build_unified_profile` | **basis waktu salah** (§3.1) | `kol_profile_card.followers_growth` (25 terisi) | list + detail | `growthMin`/`growthMax` | **BLOCKED** |
| Growth classification | turunan | — | ✗ | — | threshold placeholder | — | — | — | **BLOCKED** |
| Rising Creator | growth + ER + followers | — | ✗ | — | ambang jauh di atas data | — | — | — | **BLOCKED** |
| Growth 7D / 90D | butuh deret snapshot | — | ✗ | — | — | — | — | — | **BLOCKED** |
| Growth acceleration / stability | butuh ≥4 snapshot | — | **0 akun** | — | — | — | — | — | **NEED SOURCE** (waktu) |
| Momentum | butuh ≥3 snapshot | — | **0 akun** | — | — | — | — | — | **NEED SOURCE** (waktu) |

## 2.4 Audiens

| Requirement AUTOME_2 | Source DB | Column | Data tersedia? | Pipeline | Calculation | L2 | Endpoint | Filter | Status |
|---|---|---|---|---|---|---|---|---|---|
| Gender % | `audience_demographics_daily` | `dimension_key` | **69 baris / 23 KOL · coverage 31–40%** · `inferred_*` | `audience_gold` | share + coverage | ✅ | **detail** | ❌ | **NEED FILTER** |
| Age band | idem (`='age'`) | — | **0 baris** | wired, kosong | — | kolom ada | detail (kosong) | ❌ | **NEED SOURCE** |
| Generasi | turunan age | — | ✗ | — | — | — | — | ❌ | **NEED SOURCE** |
| Audience location | `audience_geo_daily` | `geo_level`, `geo_key` | **181 baris / 23 KOL** · inferred | `audience_gold` | share + coverage | ✅ | **detail** | ❌ | **NEED FILTER** |
| Audience interest | `audience_interest_daily` | `interest_key` | **214 baris / 23 KOL** · inferred | `audience_gold` | share + coverage | ✅ | **detail** | ❌ | **NEED FILTER** |
| Audience quality | turunan | — | ✗ (input mock) | — | **belum ada** | — | — | ❌ | **NEED CALCULATION** |
| Authenticity | `unified_follower` | seluruh kolom | **2.548 baris / 27 akun** | ✅ | **belum ada** | — | — | ❌ | **NEED CALCULATION** |
| Audience overlap | `unified_follower` | `username` follower | idem | ✅ | **belum ada** | — | — | ❌ | **NEED CALCULATION** |
| Purchase / brand / category affinity | — | — | ✗ | — | tak ada definisi | — | — | ❌ | **AMBIGUOUS** |
| Active hours heatmap | `feature.*_engagement_analysis` | `best_posting_time_heatmap` | **IG 17 · TT 11 akun** | ✅ | ✅ ada | — | **tidak** | ❌ | **NEED ENDPOINT** |

## 2.5 Konten

| Requirement AUTOME_2 | Source DB | Column | Data tersedia? | Pipeline | Calculation | L2 | Endpoint | Filter | Status |
|---|---|---|---|---|---|---|---|---|---|
| Post likes / comments | `post_metric` | `likes`, `comments` | **477 / 477** | L0→L2 lengkap | disalin | ✅ | detail | — | **READY** |
| Post views | `post_metric` | `views` | **IG 102/186 · TT 291/291** | ✅ | disalin | ✅ | detail | — | **READY** (IG hanya video) |
| Post shares / saves | `post_metric` | `shares`, `saves` | **IG 0 · TT 291** | ✅ | disalin | ✅ | detail | — | **NEED SOURCE** (IG) |
| Post ER + rank | `post_metric` | `er_followers`, `rank_in_account` | **140 / 477 (29%)** | `feature_post` → L2 | ✅ ada | ✅ | detail | — | **READY** |
| Format raw (`format_set[]`) | `content_format_daily` / `post_metric` | `media_type` | **300 baris / 30 akun** — 6 nilai mentah | ✅ | disimpan mentah ✅ | ✅ | detail | — | **READY** |
| Format display mapping | turunan | — | ✓ raw ada | — | **belum ada** | — | — | — | **NEED CALCULATION** |
| `format_dominant` | `content_format_daily` | share per format | **26 dari 30 akun punya ≥10 post** (rata-rata 15,9; maks 200) | — | **belum ada** | — | — | ❌ | **NEED CALCULATION** |
| Hashtags | `post_metric` | `top_hashtags` | **IG 70/186 · TT 237/291** | `feature_post` | ✅ ada | ✅ | detail | — | **READY** |
| Sponsored flag | `post_metric` | `is_sponsored` | **467 / 477 terisi** | ✅ | flag asli platform | ✅ | detail | ❌ | **NEED FILTER** |
| Cover image / permalink | `post_metric` / `unified_post` | `permalink`, `cover_image` | ✓ (CDN expired) | ✅ | — | ✅ | detail + proxy | — | **READY** |
| Sentiment | `feature.*_post_analysis` | `sentiment_breakdown` | **0 / 477** · raw ada di `raw_payload.latestComments` | **belum mengalir** | **belum ada** | — | — | ❌ | **NEED PIPELINE** |
| Content topic | caption + `top_hashtags` | `content_category` | **0** · raw ada | **belum mengalir** | **belum ada** | — | — | ❌ | **NEED PIPELINE** |
| Content persona / style | — | — | ✗ | — | tak ada definisi | — | — | ❌ | **NEED SOURCE** |
| Watch time / completion | `post_metric` | *blocked* | **0** | — | — | kolom ada | — | ❌ | **NEED SOURCE** |

## 2.6 Komersial

| Requirement AUTOME_2 | Source DB | Column | Data tersedia? | Pipeline | Calculation | L2 | Endpoint | Filter | Status |
|---|---|---|---|---|---|---|---|---|---|
| Rate card | `l1_silver.unified_rate_card` | `fee`, `currency`, `post_type` | **0 baris** — dan 0 juga di 4 tabel L0/harmonisasi | ❌ tidak mengalir | — | ❌ | detail + `/discover/rates` | `maxRate` → **0 hasil** | **NEED SOURCE** |
| Rate card ringkas L2 | `kol_profile_card` | `rate_card*` | sumber kosong | ❌ | — | ❌ | — | — | **NEED SOURCE** |
| CPV | fee + `post_metric.views` | — | views ✓, **fee ✗** | — | **belum ada** | — | — | ❌ | **BLOCKED** |
| CPE | fee + `engagement_sum` | — | eng ✓, **fee ✗** | — | **belum ada** | — | — | ❌ | **BLOCKED** |
| CPM | fee + reach | — | keduanya ✗ | — | — | — | — | ❌ | **NEED SOURCE** |
| EMV | reach + benchmark CPM | — | ✗ | — | — | — | — | ❌ | **NEED SOURCE** |
| Commercial efficiency | turunan CPV + ER | — | ✗ | — | — | — | — | ❌ | **BLOCKED** |
| Brand Fit | `feature.brand_fit_analysis` | — | **0 baris, tidak ada asset** | ❌ | 4/6 input mock | — | — | ❌ | **NEED PIPELINE** |
| Opportunity score | komposit | — | ✗ | — | input blocked | — | — | ❌ | **BLOCKED** |
| Competitor saturation | `raw_payload.taggedUsers`/`mentions` | — | raw ada | **belum mengalir** | **belum ada** | — | — | ❌ | **NEED PIPELINE** |
| Worked with my brand | tabel order + negotiation (app) | — | ✓ | app | EXISTS | — | ada | ❌ | **NEED FILTER** |

## 2.7 Konsistensi & data freshness

| Requirement AUTOME_2 | Source DB | Data tersedia? | Calculation | Endpoint | Filter | Status |
|---|---|---|---|---|---|---|
| Performance consistency | `kol_metric_monthly` | **68 baris / 30 akun**, butuh ≥4 titik/akun | belum | detail | ❌ | **NEED SOURCE** (waktu) |
| Performance stability | idem | idem | belum | — | ❌ | **NEED SOURCE** (waktu) |
| Viral frequency | idem | idem | belum | — | ❌ | **NEED SOURCE** (waktu) |
| Last Updated (filter) | `kol_directory.last_refreshed_at` | **7.496** | — | field ada | **tidak ada param** | **NEED FILTER** |
| Data Status (6 status) | butuh frekuensi per KOL | ✗ | — | — | ❌ | **NEED SOURCE** |
| Update Frequency | — | ✗ | — | — | ❌ | **NEED SOURCE** |
| Next Update | — | ✗ | — | — | ❌ | **NEED SOURCE** |
| Monitoring Priority | order/nego aktif (sebagian) | sebagian ✓ | belum | — | ❌ | **NEED CALCULATION** |
| Request Update Now | — | ✗ | — | ❌ | — | **NEED SOURCE** |

## 2.8 Mekanik direktori

| Requirement AUTOME_2 | Data tersedia? | Endpoint | Filter | Status |
|---|---|---|---|---|
| Search multi-field (14 field, AND multi-token) | `display_name` 1.976 · `bio` 902 tersedia | list `q` | **`username` saja** | **NEED FILTER** |
| Sort (34 key, 8 grup) | sebagian | `sort` + `dir` | **6 key** | **NEED FILTER** |
| Pagination | ✓ | `page`, `pageSize` (maks 60) | ✅ | **READY** |
| Facets | ✓ | `facets=1` | ✅ | **READY** |
| Compare multi-KOL | ✓ | `ids` (maks 50, UUID) | ✅ | **READY** |
| Exclusions (7 toggle) | 1 dari 7 bisa sekarang | ❌ | ❌ | **NEED FILTER** |
| Sections (7 chip) | 3 dari 7 bisa sekarang | ❌ | ❌ | **NEED FILTER** |
| Saved search / collection / shortlist | tidak ada tabel | ❌ | ❌ | **NEED SOURCE** |

---

# 3. Calculation Gap

## 3.1 Growth 30D — audit historical snapshot

**Formula lo benar. Datanya yang tidak memenuhi syarat.**

### Sebaran snapshot (terukur)

| Jumlah snapshot per akun | Akun |
|---:|---:|
| 1 | **1.947** |
| 2 | **25** |
| ≥3 | **0** |

| Metrik span | Nilai |
|---|---|
| Akun dengan ≥2 snapshot | **25** |
| Span minimum | **10 hari** |
| Span rata-rata | **10,4 hari** |
| Span maksimum | **13 hari** |
| Akun dengan span ≥25 hari | **0** |
| Akun dengan span ≥30 hari | **0** |

### Tanggal snapshot yang ada

| Tanggal | Akun |
|---|---:|
| 2026-08-14 | 1.013 |
| 2026-08-17 | 256 |
| 2026-08-18 | 698 |
| 2026-08-24 | 23 |
| 2026-08-27 | 5 |
| 2026-08-28 | 2 |

Tiga tanggal pertama adalah scrape awal. Hanya 30 akun yang pernah di-scrape ulang, dan 25 di antaranya menghasilkan pasangan snapshot yang bisa dibandingkan.

### Formula existing vs requirement

`l1_silver.sp_build_unified_profile()` (migration 031/034):

```sql
CASE WHEN prev_followers_count IS NULL OR prev_followers_count = 0 THEN NULL
     ELSE ((followers_count - prev_followers_count)::numeric / prev_followers_count) * 100 END
```

Tidak ada normalisasi terhadap `days_between`, dan `days_between` **tidak disimpan**.

Requirement: `growth_30d = ((f_now / f_prev) ^ (30 / days_between)) - 1`

### Efek ekstrapolasi pada data nyata

Dihitung langsung terhadap 25 pasangan snapshot yang ada:

| `days_between` | `pct_mentah` | `growth_30d` setara | Faktor |
|---:|---:|---:|---:|
| 10 | +0,9174% | **+2,7776%** | 3,03× |
| 10 | +0,6711% | **+2,0270%** | 3,02× |
| 13 | +0,6007% | **+1,3916%** | 2,32× |
| 10 | +0,2865% | +0,8621% | 3,01× |
| 10 | −0,0510% | −0,1531% | 3,00× |

Seluruh 25 nilai mentah ada di rentang **−0,051% s.d. +0,917%**. Setelah dinormalisasi ke 30 hari, rentangnya jadi **−0,153% s.d. +2,778%**.

Bandingkan dengan threshold placeholder prototype (Exploding ≥8%, Rising ≥4,5%, Stable ≥1%):

| Bucket | Akun yang masuk |
|---|---:|
| Exploding (≥8%) | **0** |
| Rising (≥4,5%) | **0** |
| Stable (≥1%) | **3** |
| Declining (<1%) | **22** |

Tiga dari empat bucket praktis kosong — dan 22 "declining" itu sebagian besar adalah akun yang followers-nya turun **0,02%**, yang di dalam margin noise scrape.

### Rekomendasi

1. **Simpan `days_between` + kedua tanggal snapshot sebagai kolom.** Tanpa itu konsumen tidak bisa menilai apakah angkanya layak dipakai. Ini yang paling penting dari seluruh rekomendasi growth.
2. **Pasang span guard.** Di bawah ambang → NULL + alasan `insufficient_span`, bukan hasil ekstrapolasi. Dengan data sekarang, ambang wajar mana pun (≥21 hari) membuat **seluruh 25 akun** jadi `needs data` — dan itu jawaban yang benar.
3. **Normalisasi di L2, bukan L1.** `unified_profile.followers_growth` adalah fakta tentang sepasang snapshot; biarkan. `growth_30d`, `days_between`, `snapshot_prev_date`, `snapshot_curr_date` masuk ke `kol_profile_card` — mengikuti pola "L2 meringkas, L1 mencatat" yang sudah dipakai `kol_metric_monthly` terhadap `kol_metric_daily`.
4. **Jangan sentuh `followers_growth` di `kol_metric_daily` / `kol_metric_monthly`.** Grain-nya (`metric_date` dari `posted_at`) memang salah untuk metrik ini.
5. **Threshold ke config, dan jangan dikalibrasi sekarang.** Sampel 25 akun dengan span 10 hari tidak cukup untuk menetapkan ambang apa pun. Kalibrasi setelah ada ≥2 bulan snapshot berkala.

## 3.2 Engagement Rate — tiga sumber, tiga satuan, tidak sepakat

| Sumber | Satuan | Definisi engagement | Terisi | Rentang |
|---|---|---|---:|---|
| `kol_directory.engagement_rate` | poin persen | tidak terdokumentasi | **1.756 / 7.720** | 0 – **223,41%** · 83 nilai >10% |
| `feature.ig_engagement_analysis` | poin persen, clamp 999,99 | `likes + comments` | **12 / 19** | 0 – 16,15% · 1 nilai >10% |
| `feature.tt_engagement_analysis` | poin persen | `likes + comments + shares + saves` | **10 / 11** | 0,02 – 1,81% |
| `l2_gold.kol_metric_daily.er_followers_daily` | **fraksi 0..1** | `like + comment + share` (saves sengaja tidak ikut) | **73 / 280** | 0,000016 – 0,161499 |

Untuk 11 akun yang punya angka di roster **dan** di feature, rata-rata selisihnya **1,03 poin persen**, dengan 1 akun berbeda >1 poin. Keduanya tidak sepakat.

Filter `?minEr=` sekarang membaca **roster** — satu-satunya sumber yang punya nilai mustahil (maks 223,41%) dan tanpa definisi terdokumentasi.

**Rekomendasi:** jadikan `er_followers_daily` kanonik (definisinya jelas, aturan sampelnya eksplisit, satuannya konsisten). Roster dan feature jadi turunan atau ditandai legacy. Ingat: rentang N hari **wajib** `SUM(engagement_sum) / SUM(followers_denom_sum)` — rasio tidak additive.

## 3.3 Calculation audit — 24 metrik

| Metric | Formula existing | Source | Benar thd AUTOME_2? | Layer sekarang | Layer seharusnya |
|---|---|---|---|---|---|
| Growth 30D | pct mentah tanpa normalisasi | `unified_profile` | ❌ basis waktu salah | L1 procedure | L1 catat · **L2 normalisasi** |
| Growth classification | tidak ada | turunan | ❌ threshold placeholder | — | **L2 + config** |
| Engagement Rate | 3 versi beda satuan | `unified_post` + `unified_profile` | ⚠ tidak sepakat | roster + feature + L2 | **L2 kanonik** |
| Average Views | tidak ada | `kol_metric_daily` | — | — | **L2 agregat/akun** |
| Median Views | tidak ada (prototype `views×0,82`) | `post_metric` | ❌ aproksimasi | — | **L2** `percentile_cont(0.5)` |
| Average Likes | `total_likes / posts_analyzed_count` | feature | ✅ | Feature | Feature (cukup) |
| Average Comments | `total_comments / …` | feature | ✅ | Feature | Feature (cukup) |
| Posting Frequency | tidak ada | `kol_metric_monthly` | — | — | **L2**; tetapkan penyebut |
| Paid/Sponsored Ratio | tidak ada | `post_metric.is_sponsored` | — | — | **L2 agregat/akun** |
| Audience Quality | tidak ada | — | ❌ input mock | — | **Feature**, setelah authenticity |
| Authenticity | tidak ada | `unified_follower` (27 akun) | — | — | **Feature** |
| Audience Gender % | share, `unknown` disimpan | `audience_demographics_daily` | ✅ benar, inferred | L2 | L2 (cukup) |
| Audience Location % | share per `geo_key` | `audience_geo_daily` | ✅ benar, inferred | L2 | L2 (cukup) |
| Audience Interest | share per `interest_key` | `audience_interest_daily` | ✅ benar, inferred | L2 | L2 (cukup) |
| Content Format Dominant | tidak ada | `content_format_daily` | — | — | **L2**; raw tetap disimpan |
| Content Performance | ER + rank per post | `post_metric` | ✅ | Feature → L2 | L2 (cukup) |
| CPV | tidak ada | fee **kosong** | ❌ | — | menunggu rate card |
| CPE | tidak ada | fee **kosong** | ❌ | — | menunggu rate card |
| CPM | tidak ada | fee + reach, keduanya kosong | ❌ | — | menunggu source |
| Brand Fit | tidak ada | `brand_fit_analysis` 0 baris | ❌ | — | **Feature** |
| Opportunity Score | tidak ada | komposit | ❌ | — | terakhir |
| Performance Trend | deret `followers_eom` | `kol_metric_monthly` 68 baris | ⚠ butuh ≥4 titik | L2 | L2 (tunggu data) |
| Consistency | tidak ada | idem | ⚠ blocked volume | — | **L2** (tunggu data) |
| Momentum | tidak ada | butuh ≥3 snapshot, **0 akun** | ❌ | — | **L2** (tunggu data) |

## 3.4 Content format — mapping terhadap nilai yang benar-benar ada

Nilai mentah terukur (`content_format_daily` / `post_metric`), **persis 6**:

| Platform | `media_type` | Baris | Post | Mapping display (spec lo) |
|---|---|---:|---:|---|
| instagram | `clips` | 81 | 89 | **Reels** |
| instagram | `carousel_container` | 56 | 67 | **Carousel** |
| instagram | `feed` | 22 | 22 | **Feed / Static Post** |
| instagram | `unknown` (NULL di `post_metric`) | 8 | 8 | **Other** |
| tiktok | `VIDEO` | 131 | 289 | **Video** |
| tiktok | `CAROUSEL` | 2 | 2 | **Carousel** |

**Tidak ada satu pun story type.** Bucket "Story" di mapping lo akan selalu kosong sampai ada scraping Story. Tidak ada juga Live maupun Long-form. Saran: render chip Story/Live/Long-form sebagai `disabled` dengan alasan, bukan sebagai opsi yang mengembalikan nol.

`format_dominant` dari share N post terakhir **bisa dihitung sekarang** untuk **26 dari 30 akun** yang punya ≥10 post (rata-rata 15,9 post/akun, maksimum 200).

---

# 4. Pipeline Gap

## 4.1 Aliran yang terbukti mengalir sampai UI

```
Profil:   ig_profile_apify 953 · tt_profile_apify 1.058      [14–28 Agu]
       → instagram_profile 950 · tiktok_profile 1.051
       → unified_profile 2.001 baris / 1.976 akun
       → kol_profile_card 1.976
       → GET /discover/kol-directory/[kolId]                  ✅ SAMPAI UI

Post:     ig_media_snapshots_apify 188 · tt_video_apify 291   [20–28 Agu]
       → instagram_post 186 · tiktok_post 291
       → unified_post 477 baris / 30 akun
       → feature.{ig,tt}_post_analysis 186 + 291
       → post_metric 477 · kol_metric_daily 280
       → kol_metric_monthly 68 · content_format_daily 300
       → GET /discover/kol-directory/[kolId]                  ✅ SAMPAI UI

Follower: ig_followers_apify 2.711                            [26–28 Agu]
       → instagram_follower 1.448
       → unified_follower 2.548 baris / 27 akun
       → feature.{ig,tt}_audience_analysis 13 + 10
       → audience_{demographics,geo,interest}_daily 69/181/214 (23 akun)
       → GET /discover/kol-directory/[kolId]                  ✅ SAMPAI UI
```

## 4.2 Aliran yang terputus

| # | Data | Berhenti di | Bukti | Action |
|---|---|---|---|---|
| **P1** | **Rate card** | seluruh 5 tabel 0 baris | `l0_extra.*`, `l0_harmonization.*`, `l1_silver.unified_rate_card` semuanya 0 | Cari source-nya. Ini bukan ETL gap — **tidak ada data masuk di L0 sekalipun** |
| **P2** | Komentar post | `raw_payload.latestComments` | `sentiment_breakdown` 0/477 | Asset sentiment L0→Feature. Nol biaya Apify |
| **P3** | Badge verified IG | `raw_payload.verified` | `l0_harmonization.instagram_profile` **tidak punya kolom `is_verified`** (TikTok punya, 124 terisi) | Kolom L0 + harmonisasi + L1 |
| **P4** | Tag & mention | `raw_payload.taggedUsers`, `.mentions` | tidak diekstrak | Asset → competitor saturation |
| **P5** | Caption → topik | `unified_post.caption` ada | `content_category` 0 | Asset topik Feature |
| **P6** | Brand fit | `feature.brand_fit_analysis` | **0 baris, tidak ada asset** | Asset, setelah input nyata ada |

## 4.3 Yang TIDAK boleh disebut pipeline gap

- `followers_growth` di `kol_metric_daily`/`kol_metric_monthly` — grain-nya memang salah.
- `reach`, `er_reach_daily`, `reposts_sum`, `avg_watch_time_seconds`, `completion_rate` — *blocked column*, menunggu source.
- `l1_silver.unified_audience` **0 baris** — itu jalur A (Insights terukur). Jalur B (inferensi) yang aktif dan sudah sampai L2. Mencampurnya merusak pembedaan `inferred_` vs terukur.

---

# 5. Endpoint Gap

| Requirement | Endpoint existing? | Parameter | DB query | Return field | Status |
|---|---|---|---|---|---|
| KOL Directory (list) | ✅ `GET /api/organizations/[id]/discover/kol-directory` | `q, platform, category, tier, follMin, minEr, maxRate, growthMin, growthMax, connected, sort, dir, page, pageSize, ids, facets` | `kolDirectory.ts` `BASE`+`filtered` | 18 field + `total` + `facets` | **ADA** |
| KOL Detail | ✅ `GET /.../kol-directory/[kolId]` | — | `getKolCreator()` | `creator, identity, rank, platforms[], similar[], measured, gold` | **ADA** |
| Growth | ✅ via list & detail | `growthMin/Max`, `sort=growth` | `kol_profile_card.followers_growth` | angka mentah, **tanpa `days_between`** | **ADA, kurang field** |
| Audience | ✅ via detail | — | `kolGold.ts` 4 query | gender, age, countries, cities, interests, coverage, confidence, asOf | **ADA** |
| Content | ✅ via detail | — | `kolGold.ts` | `gold.posts[]`, `gold.formats[]` | **ADA** |
| Performance | ✅ via detail | — | `kolGold.ts` | `gold.daily[]`, `gold.monthly[]` | **ADA** |
| Rate Card | ✅ via detail + `/discover/rates` | — | `unified_rate_card` **0 baris** | selalu kosong | **ADA, sumber kosong** |
| Compare | ✅ list `?ids=` | maks 50 UUID | idem | idem | **ADA** |
| Commercial (CPV/CPE/CPM/EMV) | ❌ | — | — | — | **NEED ENDPOINT** |
| Feature layer | ❌ | — | — | — | **NEED ENDPOINT** |

### Gap spesifik

| # | Gap | Bukti |
|---|---|---|
| **E1** | **Layer feature tidak pernah di-expose** | `best_posting_time_heatmap` (28 akun), `format_performance` (17), `total_*` + `posts_analyzed_count` (30) — sudah dihitung, tidak ada route membacanya |
| **E2** | **`display_name` tidak ada di list** | Ada 1.976 di `kol_profile_card`, dikembalikan di detail, hilang di list. Komentar `KolDirectoryRow` ("roster has no display-name column") sudah tidak akurat |
| **E3** | **List tidak mengembalikan metrik L2** | Prototype butuh kolom Est. Reach, EMV, Authenticity, Growth, Rate card + 5 kolom freshness. List cuma punya followers, ER, tier, growth, rateFrom |
| **E4** | **Growth tanpa konteks span** | UI tidak bisa membedakan "+0,9% dalam 10 hari" dari "+0,9% dalam 30 hari" |
| **E5** | **Tidak ada endpoint agregat per akun** | Avg/median views, posting freq, paid ratio — UI harus menghitung sendiri dari `gold.daily[]` |
| **E6** | **Tidak ada refresh on-demand untuk roster** | `/discover/creators/[id]/refresh` melayani `discover_creators` milik org, bukan roster KOL |
| **E7** | **Tidak ada endpoint saved list / collection** | Tabelnya juga belum ada |

---

# 6. Filter Gap

Live surface prototype: **28 filter** (`FPG`) + **7 exclusion** + **7 section** + **34 sort key**.
Backend: **10 parameter filter**, **6 sort key**, search 1 field.

## 6.1 Creator Profile

| Filter | Source | Query logic | Join | Calculation | Param | Status |
|---|---|---|---|---|---|---|
| Platform | `platforms.key` | `b.platform = $2` | `kol_directory.platform_id → platforms.id` | — | `platform` | **READY** |
| Kategori KOL | `kol_categories` | `$3 = ANY(b.categories)` pakai **`name`** | `kc.id = ANY(COALESCE(category_ids, ARRAY[category_id]))` | alias UI→DB | `category` | **NEED FILTER** |
| KOL Tier | `kol_tiers` | `b.tier = ANY($4)` | band `followers BETWEEN min AND max` | band lookup | `tier` | **READY** |
| Female-skewed ≥60% | `audience_demographics_daily` | share gender F ≥ 60 | roster→`ksa`→L2 | share + coverage | ❌ | **NEED FILTER** |
| Male-skewed ≥55% | idem | share gender M ≥ 55 | idem | idem | ❌ | **NEED FILTER** |
| Verified only | `social_account` | `EXISTS(platform_user_id AND oauth_token)` | roster→`ksa`→`social_account` | boolean | `connected` | **NEED SOURCE** (0 KOL) |
| Age | `audience_demographics_daily` (`='age'`) | share age band | idem | — | ❌ | **NEED SOURCE** (0 baris) |
| Location kreator | `kol_directory.creator_city` | equality | — | — | ❌ | **NEED SOURCE** (0 terisi) |

## 6.2 Audience

| Filter | Source | Query logic | Join | Calculation | Param | Status |
|---|---|---|---|---|---|---|
| Audience location | `audience_geo_daily` | `geo_key = $` pada tanggal terbaru | roster→`ksa`→L2 | share + coverage | ❌ | **NEED FILTER** |
| Audience interest | `audience_interest_daily` | `interest_key = $` tanggal terbaru | idem | share + coverage | ❌ | **NEED FILTER** |
| Audience Quality | turunan | ≥85 / ≥75 / <75 | — | **belum ada** | ❌ | **NEED CALCULATION** |

## 6.3 Content

| Filter | Source | Query logic | Join | Calculation | Param | Status |
|---|---|---|---|---|---|---|
| Content Category / Topic | `feature.*_post_analysis.content_category` | equality | roster→`ksa`→feature | **belum ada** | ❌ | **NEED PIPELINE** |
| Content Format | `content_format_daily.media_type` | `format_dominant = $` | roster→`ksa`→L2 | mapping + share N post | ❌ | **NEED CALCULATION** |
| Content Style / Personality | — | — | — | tak ada definisi | ❌ | **NEED SOURCE** |

## 6.4 Performance

| Filter | Source | Query logic | Join | Calculation | Param | Status |
|---|---|---|---|---|---|---|
| ER ≥3% / ≥5,5% | `kol_metric_daily.er_followers_daily` | `>=` (**fraksi**, bukan persen) | roster→`ksa`→L2 | ER kanonik | `minEr` (baca **roster**) | **NEED CALCULATION** |
| High Save Rate | `post_metric.saves` | `saves/views ≥ 0,05` | idem | belum | ❌ | **NEED SOURCE** (IG 0) |
| High Share Rate | `post_metric.shares` | `shares/views ≥ 0,018` | idem | belum | ❌ | **NEED SOURCE** (IG 0) |
| Views 150K+/300K+ | `kol_metric_daily.views_sum` | avg views `>=` | idem | **belum ada** | ❌ | **NEED CALCULATION** |
| Reliability | `kol_metric_monthly` | ≥78 / ≥88 | idem | belum | ❌ | **NEED SOURCE** (waktu) |
| Performance Stability | idem | stable/volatile | idem | belum | ❌ | **NEED SOURCE** (waktu) |
| Viral Frequency | idem | frequent/occasional/rare | idem | belum | ❌ | **NEED SOURCE** (waktu) |

## 6.5 Growth

| Filter | Source | Query logic | Join | Calculation | Param | Status |
|---|---|---|---|---|---|---|
| Growth Classification | `kol_profile_card.followers_growth` | bucket by threshold | roster→`ksa`→`kol_profile_card` | **growth_30d + config** | ❌ (ada `growthMin/Max` mentah) | **BLOCKED** |
| Rising Creator | growth + ER + followers | AND 3 kondisi | idem | idem | ❌ | **BLOCKED** |

## 6.6 Data Freshness

| Filter | Source | Query logic | Param | Status |
|---|---|---|---|---|
| Last Updated (5 bucket) | `kol_directory.last_refreshed_at` | `now() - last_refreshed_at <= interval` | ❌ | **NEED FILTER** ← paling murah |
| Data Status (6 status) | butuh frekuensi per KOL | ratio umur/frekuensi | ❌ | **NEED SOURCE** |
| Update Frequency | — | — | ❌ | **NEED SOURCE** |
| Next Update | — | — | ❌ | **NEED SOURCE** |
| Monitoring Priority | order/nego aktif | — | ❌ | **NEED CALCULATION** |

## 6.7 Filter yang aktif tapi RUSAK

| Filter | Param | Perilaku terukur |
|---|---|---|
| **Max. rate card** | `maxRate` | `EXISTS(… fee IS NOT NULL AND fee <= $)` → **0 dari 7.720 KOL lolos**. Begitu slider digeser, direktori kosong |
| **Min. engagement** | `minEr` | Membaca `kol_directory.engagement_rate` — 1.756 terisi, sisanya NULL dan **langsung terbuang**. Nilai maksimum 223,41% |
| **Growth min/max** | `growthMin/Max` | Membaca `followers_growth` — hanya **25 dari 7.720** terisi. Menggeser slider membuang 99,7% roster |

Ketiganya perlu diputuskan: sembunyikan/disable di UI, atau ubah semantiknya jadi "NULL ikut lolos".

## 6.8 Exclusions & Sections

| Kontrol | Bisa sekarang? |
|---|---|
| Exclude: sudah dipilih | ✅ (data order/nego ada) |
| Exclude: partner · competitor tinggi · risk tinggi · aud quality <75 · declining · sponsored >35% | ❌ 6 dari 7 menunggu calculation |
| Section: New (`created_at`) · Updated (`last_refreshed_at`) · Recently viewed (client) | ✅ 3 dari 7 |
| Section: Trending · Hidden Gems · High ROI · High Match | ❌ menunggu calculation |

## 6.9 Search & Sort

| Aspek | Prototype | Backend | Gap |
|---|---|---|---|
| Search | 14 field, AND multi-token | `username ILIKE '%q%'` | `display_name` (1.976) dan `bio` (902) tersedia tapi tidak dicari. Logic berjenjang + ranking **sudah ditulis** di `db.py::search_kol_directory`, belum diport |
| Sort key | **34** dalam 8 grup | **6** (`followers, engagement, recent, created, name, growth`) | 28 belum ada |
| Sort prefix | tidak ada | `SCRAPED_FIRST` (Live→Calculated→Estimated) **selalu** kunci pertama | Dengan Live=0 dan Calculated=27, efeknya: **27 KOL selalu di atas**, apa pun sort-nya. Prototype tidak punya perilaku ini |

---

# 7. Scraping / Source Gap

### 7.1 Sudah ada dari harvest 14–28 Agu

Profil 1.976 akun · followers_count · username/bio/avatar/profile_url · post 477 (30 akun) · likes & comments 477/477 · views (IG 102, TT 291) · shares & saves (TT 291) · `is_sponsored` 467/477 · hashtag (IG 70, TT 237) · caption · daftar follower 2.548 (27 akun) · kategori 4.155 · agency · tier 7.194.

Di `raw_payload` tapi **belum diekstrak**: `verified` (IG), `private`, `businessCategoryName`, `latestComments`, `taggedUsers`, `mentions`, `locationName`, `musicInfo`, `videoDuration`.

### 7.2 Perlu calculation (raw ada — **bukan** scraping gap)

Avg views · median views · view-to-follower · like-to-view · posting frequency · paid ratio · format display mapping · `format_dominant` · authenticity · audience quality · audience overlap · monitoring priority (sebagian) · ER kanonik · growth_30d normalisasi.

### 7.3 Perlu endpoint (metrik ada, belum sampai UI)

`best_posting_time_heatmap` · `format_performance` · agregat `total_*` per akun · `display_name` di list · metrik L2 di list · `days_between` growth.

### 7.4 Perlu pipeline (data di layer bawah, belum mengalir)

Sentiment dari `latestComments` · badge verified IG · tag/mention → competitor saturation · content topic dari caption+hashtag · asset brand fit.

### 7.5 Benar-benar perlu source / scraping / API baru

| Kebutuhan | Bukti |
|---|---|
| **Rate card** | 0 baris di 5 tabel, semua layer. Tidak ada data masuk di L0 sekalipun — bukan ETL gap |
| **Instagram/TikTok Insights API** | reach 0/477 · shares & saves IG 0/186 · watch time 0 · demografi umur 0 baris |
| **Scraping Story** | 0 story type di 6 nilai `media_type` yang ada |
| **Platform YouTube** | `platforms` hanya berisi tiktok + instagram |
| **Kota kreator** | `creator_city` 0 dari 7.720 |
| **Data operasional kampanye** | `campaigns` & `campaign_kols` 0 baris. **Bukan scraping** |
| **Snapshot berulang** | Bukan source baru — **scheduler yang sudah ada dijalankan berkala** |

---

# 8. Development Priority

## P0 — Wajib sebelum AUTOME_2 bisa dianggap siap

| # | Task | Alasan | File / table / layer | Dependency |
|---|---|---|---|---|
| **P0-1** | **Perbaiki 3 filter yang rusak** | `maxRate` mengembalikan 0 dari 7.720; `minEr` membuang 77% roster; `growthMin/Max` membuang 99,7%. Ini bukan fitur yang kurang — ini fitur yang salah hasilnya | `kolDirectory.ts` `filtered` CTE, `route.ts` | — |
| **P0-2** | **Lacak source rate card** | 0 baris di **5 tabel, semua layer**. Rate card, CPV, CPE, EMV, dan seluruh Ordering bergantung padanya. Perlu diketahui: apakah pernah ada source-nya, atau memang belum pernah dibangun | `l0_extra.*_rate_card`, `l0_harmonization.*_rate_card`, `l1_silver.unified_rate_card` | — |
| **P0-3** | **Jadwalkan scraping profil berkala** | 1.947 akun cuma punya 1 snapshot; span maks 13 hari. Satu-satunya jalan membuka Growth 30D, momentum, consistency, stability, viral frequency, dan seluruh grup freshness | `scheduler_engine.py` (one-shot, `MAX_RETRIES=0`) | — |
| **P0-4** | **Tetapkan ER kanonik + konversi satuan** | 3 sumber, 3 satuan, selisih rata-rata 1,03 poin. Filter membaca sumber terlemah (maks 223,41%) | `kolDirectory.ts` `BASE`; `er_followers_daily` | P0-1 |
| **P0-5** | **`growth_30d` + `days_between` + span guard di L2** | Tanpa `days_between` angka growth tidak bisa dinilai. Dengan data sekarang, span guard mana pun membuat semua jadi `needs data` — dan itu benar | `l2_gold.kol_profile_card` (kolom baru), `gold_profile.py` | P0-3 |
| **P0-6** | **Threshold growth ke config** | Placeholder prototype menghasilkan Exploding 0, Rising 0, Stable 3, Declining 22. Jangan dikalibrasi sekarang — sampelnya 25 akun | tabel config / lookup | P0-5 |
| **P0-7** | **Alias kategori UI→DB + filter pakai `taxonomy_key`** | Taxonomy DB = source of truth. App filter pakai `name` mentah, `db.py` pakai `taxonomy_key`. **Catatan:** chip Tech hanya menjangkau 4 KOL dan Fitness 52 — perlu keputusan produk apakah chip prototype dipertahankan | `kolDirectory.ts`, alias map UI | — |
| **P0-8** | **Agregat per akun di L2** | avg views, median views, posting freq, paid ratio, v2f, l2v. Membuka 5 kolom tabel + 5 sort key + 2 filter, untuk 30 akun yang punya data | `l2_gold` view/tabel + asset | P0-4 |
| **P0-9** | **Mapping format display + `format_dominant`** | Raw tetap disimpan; mapping di layer turunan. Bisa untuk 26 dari 30 akun. Chip Story/Live/Long-form harus `disabled` — tidak ada datanya | agregat di atas `content_format_daily` | P0-8 |
| **P0-10** | **Filter murah di list** | Last Updated, sponsored ratio, `display_name`, search berjenjang. Semua query murni. Filter naik 10 → ~16 | `kolDirectory.ts`, `route.ts` | P0-7 |
| **P0-11** | **Join roster → `audience_*_daily` untuk 3 filter audiens** | Sudah terisi di L2 dan tampil di detail. **Join aman**: 0 kol_id punya >1 social_account, 0 social_account punya >1 profile_card. **Wajib LEFT JOIN** — 224 KOL tidak punya `kol_social_account` dan akan hilang kalau INNER | `kolDirectory.ts` `filtered` CTE | — |
| **P0-12** | **Putuskan nasib `SCRAPED_FIRST`** | Live=0, Calculated=27 → 27 KOL selalu di puncak apa pun sort-nya. Prototype tidak punya perilaku ini | `orderBy()` | — |

## P1 — Penting, setelah P0

| # | Task | Alasan | Dependency |
|---|---|---|---|
| P1-1 | Expose layer feature (heatmap 28 akun, format_performance 17, agregat 30) | Sudah dihitung, tidak dipakai siapa pun | — |
| P1-2 | Asset sentiment dari `latestComments` | Raw ada, kolom tujuan ada dan blocked (0/477). **Nol biaya Apify** | — |
| P1-3 | Asset content topic dari caption + hashtag | Membuka filter Content Category/Topic. Boleh jadi proxy audience interest **dengan confidence lebih rendah + ditandai** | P1-2 |
| P1-4 | Authenticity & audience quality dari `unified_follower` (27 akun) | Menggantikan 2 angka mock yang menopang Audience Quality, Brand Fit, Opportunity Score, 2 exclusion | — |
| P1-5 | Badge verified Instagram L0→L1 | `verified` ada di raw; harmonisasi IG belum punya kolomnya (TikTok punya, 124 terisi) | keputusan badge vs Connected |
| P1-6 | Perbaiki ambang badge Data Status | Live=0 karena ambang 7 hari vs scrape terakhir 11 hari lalu. Ambangnya harus mengikuti kadens scrape nyata | P0-3 |
| P1-7 | Sort key tambahan | 34 diminta, 6 ada. Prioritaskan yang datanya sudah ada setelah P0-8 | P0-8 |
| P1-8 | Tampilkan coverage & confidence audiens di UI | Coverage gender **31–40%** — sisanya `unknown`. Menampilkan share tanpa coverage adalah salah baca | — |

## P2 — Future / enrichment

| # | Task | Dependency |
|---|---|---|
| P2-1 | Ajukan akses Insights API (reach, impressions, shares/saves IG, watch time, umur) — **lead time panjang, ajukan awal** | — |
| P2-2 | Tabel monitoring per KOL (frekuensi, prioritas, next run) | P0-3 |
| P2-3 | Saved list / collection / shortlist | — |
| P2-4 | Asset brand fit | P1-4 |
| P2-5 | Competitor saturation dari tag/mention | P1-3 |
| P2-6 | Creator city & niche (tetap nullable, UI graceful) | source |
| P2-7 | Exclusions & sections (14 kontrol) | P0-8, P1-4 |
| P2-8 | CPV / CPE / CPM / EMV | P0-2 (rate card) |

---

# 9. Recommended Next Action

1. **Perbaiki tiga filter yang rusak dulu (P0-1).** Ini satu-satunya kategori yang membuat produk *salah*, bukan sekadar kurang. `maxRate` mengosongkan direktori, `minEr` membuang 77% roster, `growthMin/Max` membuang 99,7%. Perbaikannya kecil — putuskan apakah NULL ikut lolos, atau kontrolnya di-disable sampai datanya ada.

2. **Kejar source rate card (P0-2), paralel dengan nomor 1.** Kosong di lima tabel dan semua layer berarti masalahnya di hulu, bukan di ETL. Sampai ini terjawab, seluruh sisi komersial AUTOME_2 — rate card, CPV, CPE, EMV, Ordering — tidak punya dasar. Ini pertanyaan yang cuma lo/tim yang bisa jawab: pernah ada source-nya atau memang belum pernah dibangun?

3. **Nyalakan scheduler profil berkala (P0-3) sebelum menulis kode growth apa pun.** Menulis `growth_30d` hari ini menghasilkan fungsi benar di atas data yang tidak bisa membuktikannya. Kalau scraping berkala mulai minggu ini, span 30 hari tersedia awal Oktober. Sampai itu `growth_30d` **harus** mengembalikan `needs data`.

4. **Putuskan tiga hal yang memblokir banyak task sekaligus** — bisa paralel:
   - ER mana yang kanonik dan satuannya
   - Ambang span minimum untuk growth
   - Apakah chip kategori prototype dipertahankan (Tech hanya 4 KOL, Fitness 52, sementara Moms 589 dan Entertainment 501 tidak punya chip)

5. **Batch P0-7 sampai P0-12.** Semuanya perubahan query/agregasi tanpa pipeline baru, dan bersama-sama menaikkan filter ter-expose dari 10 ke sekitar 19 dari 28. Rasio hasil-per-usaha tertinggi.

6. **Baru P1.** Dua asset baru (sentiment, content topic) memakai pola yang persis sama dengan asset yang sudah ada dan **tidak butuh panggilan Apify tambahan**.

### Yang jangan dikerjakan dulu

- **Jangan** mengisi `followers_growth` di `kol_metric_daily`/`kol_metric_monthly` — grain-nya memang salah.
- **Jangan** pakai INNER JOIN dari roster ke `kol_social_account`: **224 KOL** tidak punya pasangan dan akan hilang diam-diam.
- **Jangan** menormalkan `media_type` di `content_format_daily` — pipeline sengaja menyimpannya mentah, dan spec lo juga bilang raw `format_set[]` tetap disimpan.
- **Jangan** menghitung ulang growth di aplikasi. Satu rumus, satu tempat.
- **Jangan** membuat layer/tabel baru untuk agregat per akun sebelum mengecek apakah view di atas `l2_gold` sudah cukup. Arsitektur L0→Harmonization→L1→Feature→L2 masih memadai untuk seluruh P0.

---

*Audit read-only. Tidak ada perubahan pada kode, database, schema, migration, pipeline, endpoint, atau UI. Tidak ada commit, push, atau scraping baru. Seluruh angka diverifikasi langsung ke database 2026-09-08 lewat sesi `set_session(readonly=True)`.*
