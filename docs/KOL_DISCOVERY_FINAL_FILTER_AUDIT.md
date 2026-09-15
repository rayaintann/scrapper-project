# KOL Discovery — Final Filter Audit

**Audit & planning saja · 2026-09-09 · tidak ada perubahan code, database, migration, atau scraping**

| Repo | Branch | Commit | Working tree |
|---|---|---|---|
| `scrapper-project` | `main` | `dd83e0f` | bersih |
| `autometric` | `engkol_v1` | `232da34` | bersih |

**Cara audit ini disusun.** Inventaris filter dibaca **langsung dari kode**, bukan dari
dokumen: `app/AUTOME_2.html` (prototype — `state.adv`, `filterKols()`, `fpGroups()`,
`dirExclPass()`, `dirSectionPass()`, `DSORT`), `src/components/discover/KolDirectoryFilters.tsx`
(UI), `src/lib/discover/kolDirectory.ts` (backend), dan `db.py` (data access Python).
Angka cakupan dipakai ulang dari audit read-only 8 September — **tidak ada query database
baru di sesi ini**.

---

# 0. Ringkasan eksekutif

| | Jumlah |
|---|---:|
| **Total dimensi filter teridentifikasi** | **46** |
| Dari prototype | 40 |
| Hanya ada di aplikasi nyata (tidak ada di prototype) | 6 |
| **DONE — lulus validasi** | **10** |
| **DONE dengan catatan** (jalan, tapi ada cacat semantik/konsistensi) | **2** |
| **CAN DEVELOP NOW** | **5** |
| **BLOCKED / WAITING** | **29** |

**Tiga temuan yang mengubah rencana:**

1. **Filter yang tidak bisa dipakai ternyata SUDAH digambar di UI** — dalam keadaan
   *disabled* dengan penjelasan "belum ada datanya". Ini kebalikan dari yang saya tulis di
   `docs/BACKEND_PLAN.md` §5.1 (*"sengaja tidak digambar"*). **Dokumen saya salah**, dan
   komentar header `KolDirectoryFilters.tsx` juga sudah basi terhadap kodenya sendiri.
2. **Tiga keterangan "belum ada datanya" di UI sudah tidak benar.** Format, Audience, dan
   Location ditulis "roster tidak menyimpan data ini" — padahal L2 sekarang punya
   `content_format_daily` (30 KOL) dan `audience_*_daily` (23 KOL). Datanya tipis, tapi
   ada. Keterangan itu menyesatkan.
3. **`Search` adalah satu-satunya filter DONE yang sumbernya salah**, dan sekaligus yang
   paling murah dibetulkan: kolomnya **sudah ada di `BASE`**, tinggal ditambahkan ke
   klausa `WHERE`. Nol join baru, nol migration, nol scraping.

---

# 1. Daftar Lengkap Semua Filter

Legenda — **Prototype**: ada di `AUTOME_2.html` · **UI**: dirender di aplikasi
(`✅ aktif` / `⛔ disabled` / `❌ tidak ada`) · **Backend**: diproses `kolDirectory.ts`.

## 1.1 Filter utama (panel + toolbar)

| # | Filter | Prototype | UI | Backend | Source | Perlu Calculation? | Calculation / Rule | Status | Blocker |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | **Search** | ✅ `q` (name, niche, cat) | ✅ aktif | ✅ `q` | `kol_directory.username` | ❌ | `username ILIKE '%q%'`, `%`/`_` di-escape | **DONE (sumber kurang)** | — |
| 2 | **Platform** | ✅ `platform` | ✅ aktif | ✅ `platform` | `platforms.key` | ❌ | `b.platform = $` | **DONE** | — |
| 3 | **Category** | ✅ `cat` (5 hardcoded) | ✅ aktif | ✅ `category` | `kol_categories` | ❌ | `$ = ANY(COALESCE(taxonomy_key,name)[]) OR $ = ANY(names[])` | **DONE** | — |
| 4 | **Tier** | ✅ `tier` | ✅ aktif | ✅ `tier[]` | `kol_tiers` band | ⚠ rule | `followers >= min AND (max IS NULL OR followers <= max)` | **DONE** | — |
| 5 | **Min followers** | ✅ `follMin` | ✅ aktif | ✅ `follMin` | `kol_directory.followers_count` | ⚠ rule | `followers >= $` · skala berjenjang 0…10jt | **DONE** | — |
| 6 | **Min engagement** | ✅ `erMin` | ✅ aktif | ✅ `minEr` | `feature.*_engagement_analysis` → roster | ✅ | `COALESCE(feature.er, roster.er) >= $` | **DONE** | — |
| 7 | **Max rate card** | ✅ `rateMax` (USD) | ✅ aktif | ✅ `maxRate` | `l1_silver.unified_rate_card` | ⚠ rule | `EXISTS(fee IS NOT NULL AND fee <= $)` | **DONE, 0 hasil** | tabel 0 baris — G1 |
| 8 | **Verified** | ✅ `verifiedOnly` | ✅ aktif | ✅ `verified=1` | `kol_profile_card.is_verified` | ❌ | `COALESCE(is_verified,false)` | **DONE (semantik NULL)** | — |
| 9 | **Connected** | ❌ | ✅ aktif | ✅ `connected=1` | `social_account` | ❌ | `EXISTS(platform_user_id IS NOT NULL AND oauth_token IS NOT NULL)` | **DONE** (0 KOL, benar) | — |
| 10 | **Growth** | ⚠ hanya kolom & sort | ✅ aktif | ✅ `growthMin`/`Max` | `kol_profile_card.followers_growth` | ✅ | `(foll − foll_prev)/foll_prev × 100`, dihitung L1 | **DONE** (25 KOL) | — |
| 11 | **Last Updated** | ❌ | ✅ aktif | ✅ `updatedWithin` | `kol_directory.last_refreshed_at` | ❌ | `last_refreshed_at >= now() − N hari` | **DONE** | — |
| 12 | **Agency** | ⚠ hanya kolom tabel | ✅ aktif | ✅ `agency` | `agency_kol_accounts`+`agencies` | ❌ | `EXISTS(kol_account_id = id AND ag.name = $)` | **DONE (tampilan beda)** | — |
| 13 | **Format konten** | ✅ `format` | ⛔ disabled | ❌ | `l2_gold.content_format_daily` (30 KOL) | ❌ | `EXISTS(media_type = $)` | **CAN DEVELOP** | label mapping |
| 14 | **Min avg views** | ✅ `viewsMin` | ⛔ (di section Reach) | ❌ | `post_metric.views` / `kol_metric_daily.views_sum` | ✅ | **belum ada** — `AVG(views)` per akun | BLOCKED | agregat belum ada |
| 15 | **Age audiens** | ✅ `age` | ⛔ disabled | ❌ | `audience_demographics_daily` | ❌ | `audience_type='age'` | BLOCKED | **0 baris** |
| 16 | **Major Female %** | ✅ `femaleMin` | ⛔ disabled | ❌ | `audience_demographics_daily` | ✅ | `female/(total−unknown) × 100 >= $` | BLOCKED | 23 KOL + G2 |
| 17 | **Major Male %** | ✅ `maleMin` | ⛔ disabled | ❌ | idem | ✅ | idem, sisi male | BLOCKED | 23 KOL + G2 |
| 18 | **Creator location** | ✅ `domicile` | ⛔ disabled | ❌ | `kol_directory.creator_city` | ❌ | `creator_city = $` | BLOCKED | **0/7.720** |
| 19 | **Audience location** | ✅ `audDomicile` | ⛔ disabled | ❌ | `audience_geo_daily` | ⚠ | `geo_level='city' AND geo_key = $` | BLOCKED | 15 KOL · `geo_key` campur kota/provinsi |
| 20 | **Min authenticity** | ✅ `authMin` | ⛔ disabled | ❌ | `feature.*_audience_analysis.authenticity_score` | ❌ | `authenticity_score >= $` | BLOCKED | endpoint belum ada · 23 KOL |
| 21 | **Min brand fit** | ✅ `brandFitMin` | ⛔ disabled | ❌ | `feature.brand_fit_analysis` | ✅ | `partnership_score >= $` | BLOCKED | **0 baris**, grain KOL×brand |
| 22 | **Max paid ratio** | ✅ `paidMax` | ⛔ disabled | ❌ | `post_metric.is_sponsored` | ✅ | **belum ada** — `sponsored/total × 100 <= $` | BLOCKED | agregat belum ada |
| 23 | **Min campaigns** | ✅ `campMin` | ⛔ disabled | ❌ | tabel campaign | ❌ | `COUNT(campaign) >= $` | BLOCKED | 13 dari 14 tabel kosong |
| 24 | **Audience interest** | ✅ `interest` (tanpa kontrol panel) | ❌ | ❌ | `audience_interest_daily` | ❌ | `interest_key = $` | BLOCKED | 23 KOL + G2 |
| 25 | **Min est. reach** | ✅ `estReachMin` (tanpa kontrol panel) | ❌ | ❌ | `post_metric.reach` | ✅ | — | BLOCKED | **reach 0/477** |
| 26 | **Min posting frequency** | ✅ `postFreqMin` (tanpa kontrol panel) | ❌ | ❌ | `kol_metric_monthly` | ✅ | **belum terdefinisi** | BLOCKED | requirement tidak jelas |
| — | ~~`follMax`~~ · ~~`reachMin`~~ | ⚠ ada di state, **tidak pernah dipakai** `filterKols()` | ❌ | ❌ | — | — | — | **kode mati di prototype** | bukan requirement |

## 1.2 Exclusions — 7 toggle di layer "KOL Intelligence" (`dirExclPass`)

| # | Exclusion | Prototype | UI | Backend | Source | Perlu Calculation? | Rule | Status | Blocker |
|---:|---|---|---|---|---|---|---|---|---|
| 27 | Exclude yang sudah dipilih | ✅ `selected` | ❌ | ❌ | state keranjang (klien) | ❌ | `id ∈ cart ∪ orderSel` | BLOCKED | UI-only, tidak butuh backend |
| 28 | Exclude yang pernah kerja sama | ✅ `partners` | ❌ | ❌ | riwayat campaign | ❌ | `workedMine` | BLOCKED | tabel campaign kosong |
| 29 | Exclude saturasi kompetitor tinggi | ✅ `comp` | ❌ | ❌ | — | ✅ | `compSat === 'high'` | BLOCKED | **tidak ada sumber** |
| 30 | Exclude risiko tinggi | ✅ `risk` | ❌ | ❌ | — | ✅ | `riskLevel === 'high'` | BLOCKED | **tidak ada sumber** (nilai prototype dari hash ID) |
| 31 | Exclude kualitas audiens rendah | ✅ `lowaud` | ❌ | ❌ | `feature.*_audience_analysis` | ✅ | `audQ < 75` | BLOCKED | 23 KOL, endpoint belum ada |
| 32 | Exclude growth menurun | ✅ `declining` | ❌ | ❌ | `followers_growth` | ✅ | `gClass === 'declining'` | BLOCKED | classification belum ada · 25 KOL |
| 33 | Exclude sponsored-heavy | ✅ `sponsored` | ❌ | ❌ | `post_metric.is_sponsored` | ✅ | `sponPct > 35` | BLOCKED | agregat belum ada |

## 1.3 Sections — 7 preset di layer "KOL Intelligence" (`dirSectionPass`)

| # | Section | Prototype | UI | Backend | Source | Rule di prototype | Status | Blocker |
|---:|---|---|---|---|---|---|---|---|
| 34 | Trending | ✅ | ❌ | ❌ | growth + viral freq | `gClass ∈ {exploding,rising}` atau `viralFreq='frequent'` | BLOCKED | butuh growth 30D |
| 35 | Hidden gems | ✅ | ❌ | ❌ | — | `oc.includes('hiddengem')` | BLOCKED | skor komposit tidak ada |
| 36 | **Newly added** | ✅ | ❌ | ❌ | `kol_directory.created_at` (7.698 · 99,7%) | prototype: **indeks array** — bukan rule nyata | **CAN DEVELOP** | ambang N hari belum diputuskan |
| 37 | Recently updated | ✅ | ✅ (sebagai `updatedWithin`) | ✅ | `last_refreshed_at` | prototype: regex `"Nh ago"` | **DONE** (via #11) | — |
| 38 | Recently viewed | ✅ | ❌ | ❌ | state klien | `id ∈ recent[8]` | BLOCKED | UI-only, tidak butuh backend |
| 39 | High ROI | ✅ | ❌ | ❌ | rate card + performa | `commEff >= 70` | BLOCKED | rate card kosong (G1) |
| 40 | High match | ✅ | ❌ | ❌ | skor komposit | `dirMatch(k) >= 85` | BLOCKED | rumus `dirMatch` memakai nilai hash ID |

## 1.4 Fitur pencarian lanjutan

| # | Fitur | Prototype | UI | Backend | Source | Status | Blocker |
|---:|---|---|---|---|---|---|---|
| 41 | Collections / shortlist | ✅ | ⚠ state klien | ❌ | — | BLOCKED | **tabel belum ada** — satu-satunya tabel baru yang memang perlu |
| 42 | Saved searches | ✅ | ⚠ state klien (`SavedList`) | ❌ | — | BLOCKED | tidak persisten antar perangkat |
| 43 | Kriteria bahasa alami (`nl`) | ✅ | ❌ | ❌ | — | BLOCKED | requirement tidak jelas |
| 44 | Similar creators | ✅ `simStrength` | ✅ | ✅ | `kol_directory` | **DONE** | endpoint `creators/similar` + `similar[]` di detail |
| 45 | Compare (`ids`) | ✅ | ✅ | ✅ `ids` | `kol_directory` | **DONE** | maks 50 UUID, mengabaikan paging |
| 46 | Profiling Status | ❌ (aplikasi: My Creators) | ❌ | ❌ | `scrape_status` | BLOCKED | tidak ada nilai "sedang diproses" |

## 1.5 Sort — untuk kelengkapan inventaris

Prototype punya **6** kunci sort dasar (`SORTOPTS`: match, foll, er, auth, growth, emv) dan
**31** kunci sort lanjutan (`DSORT`) — union ±34 kunci berbeda.
Backend menyediakan **6** (`followers`, `engagement`, `growth`, `recent`, `created`, `name`),
UI menampilkan **5** (`created` ada di backend tapi **belum diekspos** sebagai kontrol).

---

# 2. Pengelompokan Berdasarkan Kebutuhan Calculation

## A. Tidak perlu calculation — baca kolom, bandingkan

| Filter | Sumber | Ekspresi |
|---|---|---|
| Search | `kol_directory.username` | `ILIKE` |
| Platform | `platforms.key` | `=` |
| Category | `kol_categories` | `= ANY(array)` |
| Verified | `kol_profile_card.is_verified` | boolean |
| Connected | `social_account` | `EXISTS(2 kolom NOT NULL)` |
| Agency | `agency_kol_accounts`+`agencies` | `EXISTS(name =)` |
| Last Updated | `last_refreshed_at` | `>= now() − N hari` |
| Newly Added *(belum dibuat)* | `created_at` | `>= now() − N hari` |
| Format *(belum dibuat)* | `content_format_daily.media_type` | `EXISTS(media_type =)` |
| Audience interest *(belum dibuat)* | `audience_interest_daily.interest_key` | `EXISTS(interest_key =)` |
| Creator location *(0 baris)* | `creator_city` | `=` |
| Age audiens *(0 baris)* | `audience_demographics_daily` | `audience_type='age'` |
| Min campaigns *(tabel kosong)* | tabel campaign | `COUNT >=` |
| Min authenticity *(endpoint belum ada)* | `feature.*_audience_analysis` | `>=` |

**Delapan yang disebut di brief semuanya masuk sini** — Search, Platform, Category,
Verified, Connected, Agency, Last Updated — dan semuanya **sudah DONE** kecuali Search yang
sumbernya belum lengkap.

## B. Memakai hasil calculation

Yang penting: **calculation-nya harus sudah ada di pipeline**, bukan dibuat di endpoint.

| Filter | Calculation ada? | Di mana dihitung | Rumus |
|---|---|---|---|
| **Engagement Rate** | ✅ **ada** | `feature_engagement.py` → `feature.{ig,tt}_engagement_analysis` | Σ engagement per post ÷ follower **pada tanggal post**, dijumlah aditif; post kolaborasi & likes-hidden **dikecualikan**. Fallback `kol_directory.engagement_rate` |
| **Growth (sejak snapshot terakhir)** | ✅ **ada** | `l1_silver.sp_build_unified_profile()` → L2 apa adanya | `round((foll − foll_prev) / foll_prev × 100, 4)`. Snapshot yang di-NULL-kan guard dilewati, riwayat tidak putus |
| **Growth 30D** | ❌ | — | Butuh `days_between` + CAGR. **Belum ada rumus yang disepakati** |
| Growth classification | ❌ | — | Prototype: exploding ≥8% · rising ≥4,5% · stable ≥1% — **ambang prototype, 0 KOL lolos pada data nyata** |
| Major Female / Male % | ❌ | — | `female ÷ (total − unknown) × 100` — penyebut **harus** mengecualikan `unknown` (rata-rata 71,3% audiens tidak diketahui gendernya) |
| Avg views | ❌ | — | `AVG(post_metric.views)` per akun, dengan `post_sample_n` sebagai pengaman |
| Median views | ❌ | — | `PERCENTILE_CONT(0.5)` atas `post_metric.views` |
| Paid ratio | ❌ | — | `COUNT(is_sponsored) ÷ COUNT(*) × 100` |
| Posting frequency | ❌ | — | **belum terdefinisi** — per minggu/bulan? jendela berapa lama? |
| V2F / L2V | ❌ | — | `views ÷ followers` · `likes ÷ views` |
| Save / Share rate | ❌ | — | `saves ÷ views` · `shares ÷ views` — **Instagram 0/186 baris** |
| Authenticity / Audience quality | ✅ **ada** di Feature | `audience_inference.py` | Skor 0–100, 23 KOL. **Belum diekspos endpoint** |
| Brand fit | ❌ | — | `brand_fit_analysis` 0 baris |
| Est. Reach | ⚠ dihitung di **UI** | `KolDirectoryPage.tsx` | `followers × erPct ÷ 100` — bukan metrik backend, tidak bisa difilter |
| EMV / CPV / CPE / CPM | ❌ | — | Semua butuh `fee` — menunggu G1 |

## C. Memakai rule / range

| Filter | Rule | Catatan |
|---|---|---|
| **Followers** | `followers_count >= $` | Slider berjenjang `0, 1rb, 5rb, 10rb, 25rb, 50rb, 100rb, 250rb, 500rb, 1jt, 5jt, 10jt` — bukan linear, karena rentangnya 5 orde besaran |
| **Tier** | band dari `public.kol_tiers` | Nano 1rb–9.999 · Micro 10rb–49.999 · Mid-tier 50rb–499.999 · Macro 500rb–999.999 · Mega 1jt+. Batas bawah ikut, batas atas ikut (`<=`). Di bawah 1rb dan follower NULL → **tanpa tier** (P-01) |
| **Rate Card** | `EXISTS(fee <= $)` | Tangga `0 … Rp1 mlr`. Kreator tanpa rate card **dikecualikan** saat filter aktif |
| **Growth (band)** | preset, bukan slider | `>0%` (min 0,0001) · `=0%` · `<0%` (max −0,0001) · `≥0,5%` · `≥1%`. **0,0001 adalah batas yang benar** karena L1 membulatkan ke 4 desimal |
| **Last Updated** | `>= now() − N hari` | Preset jumlah hari |

## D. Belum bisa dibuat

| Sebab | Filter |
|---|---|
| **Source 0 baris** | Age audiens · Creator location · Brand fit · Min campaigns · Reach/Impressions · Save/Share rate (IG) |
| **Tidak ada sumber sama sekali** | Saturasi kompetitor · Risk level · Reliability · Content topic · Content style · Story · YouTube |
| **Historical belum cukup** | Growth 30D · Growth classification · Trending · Momentum · Stability · Viral frequency |
| **Calculation belum ada** | Avg/Median views · Paid ratio · V2F · L2V · Posting frequency · High ROI · High match · Hidden gems |
| **Endpoint belum ada** (data & calculation SUDAH ada) | Authenticity · Audience quality · `format_performance` · agregat engagement per akun |
| **Tabel belum ada** | Collections · Saved searches (persisten) |
| **Requirement belum jelas** | Posting frequency · Kriteria bahasa alami · ambang "Newly added" · pemetaan `media_type` → Reels/Feed/Carousel |

---

# 3. Validasi Filter yang Sudah DONE

Diperiksa dari kode, tanpa query database. Tujuh dimensi per filter sesuai brief.

## 3.1 Hasil ringkas

| Filter | Source benar | SQL benar | NULL behavior | 0 ≠ NULL | Tanpa JOIN dup | Facet = hasil | Kombinasi | Vonis |
|---|---|---|---|---|---|---|---|---|
| Platform | ✅ | ✅ | ✅ | n/a | ✅ | ✅ | ✅ | **PASS** |
| Category | ✅ | ✅ | ✅ | n/a | ✅ | ⚠ | ✅ | **PASS (1 risiko laten)** |
| Tier | ✅ | ✅ | ✅ | n/a | ⚠ | ✅ | ✅ | **PASS (1 risiko laten)** |
| Min followers | ✅ | ✅ | ✅ | ✅ | ✅ | n/a | ✅ | **PASS** |
| Min ER | ✅ | ✅ | ✅ | ⚠ | ✅ | n/a | ✅ | **PASS (1 catatan)** |
| Growth | ✅ | ✅ | ✅ | ✅ | ✅ | n/a | ✅ | **PASS — contoh terbaik** |
| Connected | ✅ | ✅ | ✅ | n/a | ✅ | n/a | ✅ | **PASS** |
| Last Updated | ✅ | ✅ | ✅ | ✅ | ✅ | n/a | ✅ | **PASS** |
| Compare (`ids`) | ✅ | ✅ | ✅ | n/a | ✅ | n/a | ✅ | **PASS (1 catatan)** |
| Similar creators | ✅ | ✅ | ✅ | n/a | ✅ | n/a | ✅ | **PASS** |
| **Search** | ⚠ **kurang 2 kolom** | ✅ | ✅ | n/a | ✅ | n/a | ✅ | **PASS FUNGSIONAL, sumber kurang** |
| **Verified** | ✅ | ✅ | ⚠ **konflasi** | n/a | ✅ | n/a | ✅ | **PASS, semantik cacat** |
| **Agency** | ✅ | ✅ | ✅ | n/a | ✅ | ✅ | ⚠ **tampilan** | **PASS, tampilan bisa beda** |
| **Max rate card** | ✅ | ✅ | ✅ | ✅ | ✅ | n/a | ✅ | **PASS, tapi 0 hasil** |

## 3.2 Yang terbukti benar dan sebaiknya tidak disentuh

**Growth adalah implementasi paling rapi di seluruh filter.** Semua aturan sulit dijawab benar:

* `0%` diperlakukan sebagai nilai nyata, bukan "tanpa batas" — 8 dari 25 KOL tepat di 0.
* Karena itu filternya **preset, bukan slider**; slider tidak bisa membedakan "tanpa batas"
  dari "tepat datar".
* Batas `>0%` memakai `0,0001` dan `<0%` memakai `−0,0001`. Ini **tepat**: L1 membulatkan
  ke 4 desimal, jadi 0,0001 adalah magnitudo bukan-nol terkecil yang mungkin. Tidak ada
  celah di antara ketiga preset.
* `num()` di route menjaga parameter yang absen tetap absen — `Number(null)` = 0 akan
  mengubah "tanpa batas" jadi "≥ 0".
* NULL `growth_pct` (7.695 KOL) tidak pernah lolos filter apa pun, dan `NULLS LAST` di
  kedua arah sort.

**Aman lainnya:** `LEFT JOIN LATERAL … LIMIT 1` untuk growth/identitas/ER menjamin satu KOL
tetap satu baris; `EXISTS` (bukan `JOIN`) untuk Connected, Agency, dan Rate Card menjamin
hal yang sama; sort di-whitelist dan arah direduksi ke dua literal; tie-break berakhir di
`id` yang unik; `page` di-reset ke 1 pada setiap perubahan filter, search, dan sort.

## 3.3 Empat temuan pada filter yang sudah DONE

### V-1 · Search hanya mencari `username` — sumbernya kurang dua kolom

```sql
WHERE ($1::text IS NULL OR b.username ILIKE '%' || $1 || '%')
```

`BASE` **sudah menyeleksi** `COALESCE(g.bio, kd.bio) AS bio` dan
`g.display_name AS card_display_name`. Keduanya ada di baris yang sama, tapi tidak ikut
dicari.

| Implementasi | Kolom yang dicari |
|---|---|
| `db.search_kol_directory()` (repo ini) | username + display_name + bio — **sesuai keputusan Task 4** |
| `kolDirectory.ts` (Discovery) | **username saja** |

**Dampak:** mencari "beauty" tidak menemukan kreator yang menulis "beauty" di bio (902–1.878
baris) maupun yang display name-nya mengandung kata itu (1.961 baris).
**Perbaikannya nol join baru** — tambahkan dua `OR` ke klausa yang sudah ada.

### V-2 · Verified mencampur "tidak verified" dengan "belum ada kartunya"

```sql
COALESCE(g.is_verified, false) AS verified
```

5.744 KOL tidak punya `kol_profile_card`, dan semuanya dilaporkan `verified: false` —
seolah sudah diukur dan hasilnya negatif. Untuk filter positif (`?verified=1`) ini tidak
berbahaya; yang salah adalah **field di response**, yang menyatakan fakta yang tidak pernah
diukur.

Ini persis pelanggaran aturan "tiga jawaban, bukan dua" dari Task 5 §3. Perbaikannya
sederhana (buang `COALESCE`, biarkan `null`), **tapi jangan dikerjakan sendirian** — ia satu
paket dengan keputusan NULL-handling (G2), supaya tidak ada dua konvensi NULL yang hidup
bersamaan.

### V-3 · Agency yang difilter bisa berbeda dari agency yang ditampilkan

Filter memakai `EXISTS` atas **semua** agency milik kreator. Tampilan memakai
`DISTINCT ON (kol_account_id) … ORDER BY created_at DESC` — **satu** agency, yang terbaru.

Untuk kreator yang terdaftar di dua agency: filter "Alpha Agency" bisa mengembalikan baris
yang kolom Agency-nya tertulis "Beta Partner". Barisnya benar (kreator itu memang di Alpha),
tapi tampilannya membingungkan.

Terukur: agency menamai 7.684 dari 7.718 KOL. **Berapa yang punya lebih dari satu agency
tidak pernah diukur** — kalau nol, temuan ini teoretis. Belum bisa diverifikasi tanpa query.

### V-4 · `minEr=0` yang ditulis manual membuang 5.954 KOL secara diam-diam

`($5::float8 IS NULL OR b.er_pct >= $5)` — dengan `$5 = 0`, `er_pct >= 0` membuang setiap
baris ber-`er_pct` NULL.

UI **tidak pernah** mengirim `minEr` saat slider di 0 (`if (f.erMin > 0)`), jadi lewat
aplikasi ini tidak bisa terjadi. Tapi URL yang di-bookmark atau ditulis tangan dengan
`?minEr=0` akan menyusutkan direktori dari 7.720 jadi 1.767 tanpa penjelasan. Perilaku ini
**disengaja dan didokumentasikan di kode**; yang belum ada adalah keputusan G2 tentang cara
menampilkannya.

## 3.4 Dua risiko laten — tidak salah hari ini, tapi tidak dijaga

### R-1 · Tier bergantung sepenuhnya pada band `kol_tiers` yang tidak boleh tumpang tindih

```sql
LEFT JOIN public.kol_tiers t
       ON kd.followers_count >= t.min_followers
      AND (t.max_followers IS NULL OR kd.followers_count <= t.max_followers)
```

Tidak ada `DISTINCT ON`, `LIMIT 1`, maupun constraint. Kalau suatu hari ada baris band yang
tumpang tindih — persis jenis kesalahan yang diperbaiki migration 033 — **setiap KOL di
irisan itu menjadi dua baris**, `total` menggelembung, dan paging bergeser. Diam-diam,
tanpa error.

Hari ini band-nya tidak tumpang tindih, jadi ini bukan bug. Tapi tidak ada yang menahannya
kalau berubah.

### R-2 · Cabang kedua filter kategori bisa melampaui hitungan chip

```sql
AND ($3 IS NULL OR $3 = ANY (b.category_keys) OR $3 = ANY (b.categories))
```

Facet menghitung dengan ekspresi pertama saja (`COALESCE(taxonomy_key, name)`). Komentar
kode beralasan bahwa baris yang cocok lewat `name` adalah **subset** dari yang cocok lewat
`key`-nya sendiri — itu benar **selama** tidak ada kategori mentah yang teksnya sama dengan
`taxonomy_key` kategori **lain**.

Contoh yang akan merusaknya: kategori mentah bernama `"Tech"` yang `taxonomy_key`-nya
`"Lifestyle"`. Chip `Tech` lalu mengembalikan KOL Tech-asli **plus** KOL Lifestyle itu,
sementara angka di chip hanya menghitung yang pertama.

**Tidak bisa diverifikasi tanpa query** ke `kol_categories`. Satu `SELECT` read-only
menjawabnya definitif — dan itu langkah pertama yang saya rekomendasikan.

## 3.5 Satu catatan kecil

`ids` yang **semuanya** gagal validasi UUID menghasilkan array kosong, yang diperlakukan
sebagai "tanpa filter id" — sehingga permintaan mengembalikan seluruh roster, bukan nol
hasil. Untuk *absennya* seleksi itu perilaku yang benar dan disengaja; untuk id yang
**rusak** ia menyembunyikan kesalahan pemanggil. Dampak praktis mendekati nol karena hanya
Compare yang memakainya.

---

# 4. Filter yang Belum DONE — Sebab per Filter

| Sebab | Jumlah | Filter |
|---|---:|---|
| **Source data belum ada** | 9 | Age audiens · Creator location · Brand fit · Min campaigns · Est. reach · Save/Share rate (IG) · Saturasi kompetitor · Risk level · Reliability |
| **Calculation belum ada** | 8 | Avg views · Median views · Paid ratio · Posting frequency · V2F · L2V · High ROI · High match |
| **Historical belum cukup** | 5 | Growth 30D · Growth classification · Trending · Momentum · Stability/Viral |
| **Endpoint belum ada** (data & calculation **sudah** ada) | 4 | Authenticity · Audience quality · `format_performance` · agregat engagement per akun |
| **UI belum ada** (backend **sudah** ada) | 2 | Sort `created` · Similar creators sebagai filter listing |
| **Requirement belum jelas** | 4 | Posting frequency · Kriteria bahasa alami · ambang "Newly added" · pemetaan `media_type` |
| **Tabel belum ada** | 2 | Collections · Saved searches persisten |
| **Sebenarnya sudah ada, dokumentasi/UI-nya yang basi** | 3 | Format · Audience · Location — lihat §4.1 |
| **UI-only, tidak butuh backend** | 2 | Exclude yang sudah dipilih · Recently viewed |

## 4.1 Tiga keterangan "belum ada datanya" di UI yang sudah tidak benar

Ini kategori tersendiri karena **bukan gap teknis, melainkan gap dokumentasi di dalam
produk** — yang dibaca pengguna langsung.

| Section | Yang tertulis di UI | Kenyataan 8 September |
|---|---|---|
| **Format** | *"Format konten belum ada datanya di roster KOL"* | `l2_gold.content_format_daily` — **300 baris · 30 akun · 6 `media_type`**. Bahkan sudah dipakai untuk `dominantFormat` (56 akun) di halaman detail |
| **Audience** | *"Roster KOL tidak menyimpan data audiens — umur, gender maupun lokasi pengikut"* | Umur memang **0 baris**. Tapi gender (69 baris), geo (181), dan minat (214) **ada** untuk 23 KOL, dan sudah dirender di tab Audience halaman detail |
| **Location** | *"Lokasi audiens tidak punya kolom sama sekali"* | `l2_gold.audience_geo_daily` **punya** — 15 KOL di level kota. Yang benar-benar kosong hanya **creator city** (0/7.720) |

Keterangannya benar saat ditulis (semuanya mengacu ke *roster*), tapi L2 sudah bergerak dan
teksnya tidak ikut. Konsekuensinya: pengguna diberi tahu data itu tidak ada, padahal ada —
dan pengembang berikutnya akan mempercayai teks itu.

Komentar header `KolDirectoryFilters.tsx` juga sudah basi terhadap kodenya sendiri: ia
menulis section-section ini *"left out rather than shipped as controls that filter nothing"*,
padahal kode di bawahnya **merender semuanya dalam keadaan disabled**. Pendekatan disabled
itu lebih baik — dan `docs/BACKEND_PLAN.md` §5.1 yang saya tulis kemarin **salah** karena
mengulang komentar basi itu alih-alih membaca kodenya. Perlu dikoreksi.

---

# 5. Prioritas

## 🟢 DONE — jangan disentuh

| Filter | Bukti |
|---|---|
| Platform · Category · Tier · Min followers · Min ER · **Growth** · Connected · Last Updated · Compare · Similar creators | Lulus tujuh dimensi validasi §3.1 |

**Growth secara khusus: jangan diutak-atik.** Preset, ambang 0,0001, dan penanganan
`num()`-nya semuanya benar dan saling bergantung. Mengubah satu bagian merusak yang lain.

## 🟡 CAN DEVELOP NOW — requirement dan source sudah jelas

Diurutkan dari yang paling murah. Semuanya **tanpa migration, tanpa scraping, tanpa
pipeline baru**.

| # | Pekerjaan | Kenapa siap | Ukuran | Dampak |
|---:|---|---|---|---|
| **N-1** | **Search multi-kolom** — tambahkan `bio` dan `card_display_name` ke klausa `q` | Kolomnya **sudah ada di `BASE`**. Keputusan sumbernya sudah diambil di Task 4, dan `db.search_kol_directory()` sudah melakukannya | 1 file · 2 baris `OR` | Pencarian menjangkau 1.878 bio + 1.961 nama yang sekarang tidak terlihat |
| **N-2** | **Koreksi tiga keterangan "belum ada datanya"** di panel filter + komentar header + `BACKEND_PLAN.md` §5.1 | Murni teks. Kenyataannya sudah diukur | 1 file UI + 1 dokumen | Berhenti memberi tahu pengguna dan developer bahwa data yang ada itu tidak ada |
| **N-3** | **Verifikasi read-only `kol_categories`** — apakah ada nama mentah yang teksnya sama dengan `taxonomy_key` kategori lain (R-2) | Satu `SELECT`, nol risiko | 1 query | Mengubah risiko laten jadi fakta: aman, atau harus dibetulkan |
| **N-4** | **Ekspos sort `created`** sebagai "Recently added" | `SORT_COLUMNS.created` **sudah ada di backend**, `created_at` terisi 99,7%. Hanya belum ada di `SORTOPTS` | 1 baris UI | Menjawab section "Newly added" prototype tanpa filter baru |
| **N-5** | **Filter Format** atas `media_type` mentah | `content_format_daily` ada (30 KOL); presedennya sudah dipakai `dominantFormat` — nilai mentah dipakai apa adanya karena pemetaan ke Reels/Feed/Carousel tidak terdefinisi | 1 `EXISTS` + chip | Filter format pertama yang benar-benar menyaring — tapi **cakupannya 30 KOL**, jadi harus menunggu N-6 dulu |

> **N-5 punya prasyarat.** Dengan 30 KOL, menyalakan filter ini akan mengosongkan direktori
> persis seperti `maxRate`. Ia **tidak boleh dikirim sebelum keputusan NULL-handling (G2)**
> dan tampilan "X cocok · Y belum ada datanya" ada. Saya menaruhnya di sini karena
> requirement dan source-nya jelas, **bukan** karena aman dikerjakan sekarang.

| # | Pekerjaan | Kenapa siap | Butuh |
|---:|---|---|---|
| **N-6** | **Putuskan NULL-handling** untuk `minEr`, `maxRate`, `updatedWithin`, `follMin`, `verified` — lalu terapkan | Perilakunya sudah dipetakan (V-2, V-4) dan konsisten; yang belum ada cuma keputusan produk | **Keputusan G2/Q2** |
| **N-7** | **Jalankan procedure rate card** | Source lengkap, procedure ada dan idempoten | **Keputusan G1/Q1** |
| **N-8** | **Perbaiki tampilan Agency** saat filter agency aktif (V-3) | Perbaikannya lokal di `attachRosterExtras` | Verifikasi berapa KOL punya >1 agency |

## 🔴 BLOCKED / WAITING — jangan dikerjakan

| Kelompok | Filter | Menunggu |
|---|---|---|
| **Menunggu waktu** | Growth 30D · classification · Trending · Momentum · Stability · Viral frequency | Snapshot berjarak ≥30 hari. **Scraping berhenti sejak 2026-08-28** — jam-nya belum berjalan |
| **Menunggu Insights API** | Reach · Impressions · Watch time · Age audiens · Save/Share rate IG | Lead time eksternal |
| **Menunggu keputusan produk** | Posting frequency · ambang "Newly added" · pemetaan `media_type` · kriteria bahasa alami | Requirement |
| **Menunggu tabel** | Collections · Saved searches persisten | Satu tabel baru (satu-satunya yang memang perlu) |
| **Menunggu adopsi produk** | Min campaigns · High ROI · exclude "pernah kerja sama" | Tabel campaign terisi |
| **Tidak ada sumber sama sekali** | Saturasi kompetitor · Risk level · Reliability · Content topic/style · Story · YouTube · Creator city | Nilai di prototype berasal dari **hash ID**, bukan data. Kalau mau dibuat, rumusnya harus dibuat dari nol |
| **Menunggu cakupan naik** | Audiens gender/geo/minat · Authenticity · Audience quality | Datanya ada (23 KOL) dan calculation-nya ada, tapi filter dengan cakupan 0,3% baru berguna sesudah N-6 |

---

# 6. Rekomendasi Urutan Development

**Prinsip:** yang membuat filter yang sudah jelas menjadi DONE didahulukan; tidak ada fitur
analytics baru; tidak ada scraping, migration, atau pipeline baru sampai benar-benar
terbukti perlu.

| Urutan | Pekerjaan | Sifat | Prasyarat |
|---:|---|---|---|
| **1** | **N-3** — verifikasi read-only `kol_categories` (R-2) | 1 query, nol risiko | — |
| **2** | **N-1** — Search multi-kolom | 2 baris, sumber sudah di `BASE` | — |
| **3** | **N-2** — koreksi tiga keterangan UI + komentar header + `BACKEND_PLAN.md` §5.1 | teks | — |
| **4** | **N-4** — ekspos sort "Recently added" | 1 baris | — |
| **5** | **N-6** — putuskan lalu terapkan NULL-handling, dan tampilkan "X cocok · Y belum ada datanya" | keputusan + 1 file | **G2/Q2** |
| **6** | **N-7** — jalankan procedure rate card, lalu buatkan asset-nya | menulis data, tanpa kode | **G1/Q1** |
| **7** | **N-5** — filter Format atas `media_type` mentah | 1 `EXISTS` + chip | **langkah 5** |
| **8** | **N-8** — perbaiki tampilan Agency saat filter aktif | lokal | ukur dulu >1 agency |
| **9** | Nyalakan scheduler profil berkala | operasional | **Q5** + keputusan jadwal |
| **10** | Ekspos layer Feature (authenticity, audience quality) lalu filternya | endpoint | langkah 5 |
| **11** | Filter audiens gender/geo/minat | endpoint + filter | langkah 5, 9 |
| **12** | Agregat per akun di L2 (avg/median views, paid ratio, V2F, L2V) | **migration** | requirement + langkah 9 |

**Langkah 1–4 tidak menyentuh database, tidak butuh keputusan siapa pun, dan bisa dikerjakan
hari ini.** Langkah 5 adalah gerbang: enam pekerjaan di bawahnya menunggu satu keputusan
yang sama.

**Langkah 9 adalah satu-satunya yang jam-nya baru mulai berdetak saat dijalankan.** Growth
30D, Trending, Momentum, Stability, dan Historical Followers semuanya di belakangnya —
menundanya menunda kelimanya satu-banding-satu.

---

# 7. Yang tidak bisa diverifikasi di audit ini

1. **Tidak ada query database.** Seluruh angka cakupan dipakai ulang dari audit read-only
   8 September. Kalau data bergerak sejak itu, angkanya bergeser — meski scraping dilaporkan
   berhenti sejak 2026-08-28.
2. **R-2 (tumpang tindih `name` vs `taxonomy_key`)** hanya bisa dijawab dengan satu
   `SELECT` ke `kol_categories`. Sampai itu dijalankan, statusnya **risiko, bukan bug**.
3. **V-3 (kreator dengan >1 agency)** belum pernah diukur. Kalau nol, temuannya teoretis.
4. **Cakupan `dominantFormat` (56 akun) dan heatmap (50 akun)** melebihi jumlah akun yang
   punya baris `content_format_daily` (30). Keduanya diambil dari commit message dan
   diukur pada populasi yang berbeda (akun vs KOL); **belum direkonsiliasi**.
5. **Baseline roster** masih dipakai bergantian: 7.718 · 7.720 · 7.721. Tiga pengukuran di
   waktu berbeda.

---

*Audit dan planning saja. Tidak ada perubahan code, database, migration, scraper, atau
pipeline. Inventaris filter dibaca dari kode ter-commit; angka cakupan dari audit read-only
yang sudah ada di `docs/`.*
