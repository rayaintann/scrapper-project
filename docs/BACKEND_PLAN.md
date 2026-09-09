# Backend Plan — KOL Discovery

**Bukan rencana membangun backend baru.** Dokumen ini memetakan backend yang **sudah ada**:
tabel apa yang dipakai, endpoint mana yang membacanya, filter mana yang benar-benar
diproses, dan sampai mana tiap fitur berhenti.

**Disusun:** 2026-09-09 · **dokumentasi saja** — tidak ada kode, database, migration,
atau scraping yang disentuh saat menulis ini.

| Repo | Branch | Commit | Peran |
|---|---|---|---|
| `scrapper-project` | `main` | `fa3af27` | scraper, migration, orchestration Dagster, CLI read-only |
| `autometric` | `engkol_v1` | `232da34` | endpoint Next.js + UI KOL Discovery |

**Sumber angka:** pengukuran read-only database `kol` pada 8 September 2026, terekam di
`AUTOME_2_FULL_TRACE_AUDIT.md`, `AUTOME_2_DEVELOPMENT_AUDIT.md`,
`AUTOME_2_FULL_ENDPOINT_COVERAGE_AUDIT.md`, dan `AUTOME_2_STEP2B_FOLLOWERS_INVESTIGATION.md`.
Struktur endpoint dan filter dibaca langsung dari kode yang **sudah ter-commit**, bukan
working tree.

**Denominator:** `public.kol_directory` = **7.720 baris**. Endpoint hanya melihat
`directory_status = 'active'`, yang terukur **7.721 baris** pada 8 September — selisihnya
karena kedua angka diukur di waktu yang berbeda. Angka yang dipakai di tiap baris ditulis
apa adanya, tidak diseragamkan.

---

## 1. Backend Architecture

### 1.1 Rantai penuh

```
public.kol_directory  (roster — siapa yang di-scrape, 7.720 baris)
        │
        ▼
SCRAPING — dua produsen, keduanya menulis ke l0_raw
  A. scheduler_engine.py (repo ini)        → log: public.scheduler_logs
  B. "Add New KOL" di UI (autometric)      → log: public.add_kol_scrape_log
                                                  public.add_kol_pipeline_log
        │
        ▼
l0_raw.*            20 tabel, 7 berisi
        │
        ▼   l0_raw_new_data_sensor (Dagster, event-based:
        │   membaca count(*) + max(fetched_at) atas 8 tabel sumber)
        ▼
transform_chain_job  — 15 asset, isinya SQL murni. Sensor TIDAK pernah memanggil Apify.
        │
        ├── l0_harmonization.*   14 tabel, 9 berisi   (sp_sync_*)
        ├── l1_silver.*           8 tabel, 4 berisi   (sp_build_*)
        ├── feature.*             9 tabel, 6 berisi
        └── l2_gold.*             8 tabel, 6 berisi
        │
        ▼
BACKEND / DATA ACCESS
  autometric:  src/lib/discover/kolDirectory.ts   (list + detail, roster & filter)
               src/lib/discover/kolGold.ts        (L2 + heatmap dari Feature)
               src/lib/discover/kolMeasured.ts    (L1 post + rate card)
               src/lib/kolDb.ts                   (pool terpisah, kredensial PG_*_KOL)
  repo ini:    db.search_kol_directory()          (CLI read-only search_kol.py)
        │
        ▼
UI  /organizations/[orgSlug]/discover/kol-directory        (listing)
    /organizations/[orgSlug]/discover/kol-directory/[kolId] (detail)
```

### 1.2 Dua database, jangan dicampur

Seluruh L0 → L2 berjalan di database **`kol`**. Yang menentukan bukan nama tabel melainkan
pool yang menjalankan query:

| Jalur | Pool | Kredensial |
|---|---|---|
| Pipeline (repo ini) | `psycopg2` | `PG_*` / `KOL_DB_URL` |
| Backend Discovery (autometric) | `kolDb()` | `PG_*_KOL` |
| Warehouse analytics (autometric, **bukan** Discovery) | `pool` dari `@/lib/db` | kredensial lain |

Beberapa nama tabel ada di kedua database. `l1_silver.unified_competitor_post` dan
`l2_gold.comment_sentiment_post` **tidak ada** di database `kol` — keduanya di warehouse.

### 1.3 Tiga catatan arsitektur yang menentukan hasil

1. **Semua JOIN di jalur listing memakai `LEFT JOIN` atau `EXISTS`.** Tidak ada KOL yang
   hilang diam-diam. `LATERAL` selalu di-`LIMIT 1`, sehingga satu KOL tetap satu baris
   walau punya lebih dari satu akun sosial. Diverifikasi: 0 `kol_id` punya lebih dari satu
   `kol_social_account`.
2. **`agency` dan `rateFrom` diambil SESUDAH paging**, lewat `attachRosterExtras()`.
   Sebagai `LATERAL` mereka dievaluasi sebelum `LIMIT` — terukur 4,2 detik (agency) dan
   2,7 detik (rate card) atas seluruh roster, melawan 15–23 ms saat ditanyakan hanya untuk
   12 id yang lolos paging.
3. **Layer Feature sudah dibaca endpoint.** Pernyataan lama di `L0_L1_L2_FLOW.md` bahwa
   *"tidak satu pun tabel feature dibaca UI"* **sudah tidak berlaku** sejak `232da34`:
   `engagement_rate` dan `best_posting_time_heatmap` dibaca langsung dari
   `feature.{ig,tt}_engagement_analysis`.

---

## 2. Existing Tables

### 2.1 `public` — roster dan lookup (source of truth untuk listing)

| Tabel | Fungsi | Baris / cakupan | Source of truth untuk |
|---|---|---|---|
| `kol_directory` | Satu baris = satu KOL. Roster yang dipakai listing | **7.720** (aktif 7.721 saat diukur) | **Followers, Tier, username, profile_url, city, status, last_refreshed_at, created_at** |
| `kol_social_account` | Penghubung KOL ↔ akun sosial | menjangkau 7.496 KOL (97,1%) | jalur ke semua data pipeline |
| `social_account` | Akun IG/TikTok | 7.496 | **Connected** (`platform_user_id` + `oauth_token`) |
| `platforms` | Kunci platform | instagram 3.409 · tiktok 4.087 | **Platform**. Tidak ada baris YouTube/Facebook |
| `kol_categories` | 28 nama kategori + `taxonomy_key` (9 taksonomi resmi) | 4.174 KOL punya kategori · 4.155 masuk 9 taksonomi | **Kategori** |
| `kol_tiers` | Ambang tier | 5 baris | **Ambang Tier** — dipakai bersama UI dan `sp_build_unified_profile()` |
| `agencies` + `agency_kol_accounts` | Agency + label nama asli kreator | **7.684 dari 7.718** | **Agency** |
| `scheduler_logs` | 1 baris per pekerjaan scraping | 6 | log scraping repo ini |
| `add_kol_scrape_log` / `add_kol_pipeline_log` | Langkah "Add New KOL" dari UI | 9 / 18 | log intake dari aplikasi |
| `scheduler_config` | Jadwal refresh per KOL | **0 baris** | — (belum diputuskan) |
| `audit_log` | Log akses | bentuknya sudah tepat, belum diisi | — |

### 2.2 `l0_raw` — 20 tabel, 7 berisi

Yang relevan untuk Discovery:

| Tabel | Isi | Catatan |
|---|---|---|
| `ig_profile_apify` | 953 baris | `raw_payload->>'verified'` berisi badge IG — **470 true** |
| `tt_profile_apify` | 1.058 baris | `is_verified` — **131 true** (124 setelah dedup akun) |
| `ig_media_snapshots_apify` / `tt_video_apify` | post IG/TikTok | dipantau sensor |
| `ig_followers_apify` / `tt_followers_apify` | daftar follower | dasar inferensi audiens |
| **`kol_roster_import`** | **7.718 baris · 7.496 KOL** | **7 kolom harga terisi** — sumber rate card yang belum pernah diproses |

Delapan tabel yang dipantau sensor: `ig/tt_profile_apify`, `ig/tt_profile_official`,
`ig_media_snapshots_apify/_official`, `tt_video_apify/_official`.

### 2.3 `l0_harmonization` — 14 tabel, 9 berisi

`instagram_profile`, `tiktok_profile`, `instagram_post`, `tiktok_post`,
`instagram_follower`, `tiktok_follower`, dan turunannya. Diisi procedure `sp_sync_*`.
`{instagram,tiktok}_rate_card` **0 baris** — procedure `sp_sync_roster_rate_card()` ada
tapi tidak pernah dipanggil.

### 2.4 `l1_silver` — 8 tabel, 4 berisi

| Tabel | Baris | Fungsi | Dibaca backend? |
|---|---:|---|---|
| `unified_profile` | 2.001 | Identitas & metrik profil, **dan tempat `followers_growth` dihitung** | ✅ `creatorProfiling.ts` |
| `unified_post` | 477 | Post terpadu IG + TikTok | ✅ `kolMeasured.ts` |
| `unified_rate_card` | **0** | Harga per deliverable | ✅ dibaca `kolDirectory.ts` + `kolMeasured.ts` — **tabelnya kosong** |
| `unified_follower` | 2.548 | Daftar follower terpadu | ❌ belum dibaca UI |
| `unified_audience` · `unified_comment` · `unified_story` · `unified_tagged_post` | 0 | — | ❌ sumber L0 masih kosong |

> `unified_rate_card` **tidak** ikut `transform_chain_job` — sumbernya impor roster, bukan
> hasil scraping, jadi sensor `l0_raw` tidak memicunya.

### 2.5 `feature` — 9 tabel, 6 berisi

| Tabel | Baris | Dipakai backend |
|---|---:|---|
| `ig_engagement_analysis` | 19 | ✅ `engagement_rate` (ER) + `best_posting_time_heatmap` |
| `tt_engagement_analysis` | 11 | ✅ sama |
| `ig_post_analysis` | 186 | ⚠ dipakai asset L2 (`rank_in_account`, `top_hashtags`), tidak dibaca endpoint langsung |
| `tt_post_analysis` | 291 | ⚠ sama |
| `ig_audience_analysis` | 13 | ❌ skor authenticity/quality **belum** diekspos endpoint |
| `tt_audience_analysis` | 10 | ❌ sama |
| `brand_fit_analysis` · `ig_comments_analysis` · `tt_comments_analysis` | 0 | ❌ belum ada asset yang mengisinya |

Hanya **4** dari 9 yang ikut `transform_chain_job` (`ig/tt_engagement_analysis`,
`ig/tt_post_analysis`). Dua tabel audiens diisi asset `audience_feature` yang terdaftar di
Dagster tapi **di luar rantai sensor** — jadi data scraping baru **tidak** otomatis
memperbarui audiens.

### 2.6 `l2_gold` — 8 tabel, 6 berisi

| Tabel | Baris | Fungsi | Source of truth untuk |
|---|---:|---|---|
| `kol_profile_card` | 1.976 | Kartu profil per akun | **Growth** (`followers_growth`), **Verified** (`is_verified`), avatar/bio/display_name |
| `kol_metric_daily` | 280 | Rollup harian (grain = tanggal tayang post) | grafik performa harian |
| `kol_metric_monthly` | 68 | Rollup bulanan | grafik performa bulanan |
| `audience_demographics_daily` | 69 | Gender (dan umur, masih 0 baris) | donut gender |
| `audience_geo_daily` | 181 | `geo_level` country/city | Top Countries / Top Cities |
| `audience_interest_daily` | 214 | Minat audiens | chips minat |
| `content_format_daily` | 300 (30 akun) | Post & ER per format per hari | **Content Format**, dan `dominantFormat` |
| `post_metric` | 477 (30 akun) | Satu baris per post | tabel Top Posts |

**Kolom `rate_card*` di `kol_profile_card` NULL 100%** — harga tetap harus dari
`l1_silver.unified_rate_card`. Satu angka, satu sumber.

**Tidak ada tabel L2 untuk heatmap jam posting** di database `kol`.

---

## 3. Existing Features

Legenda status: **JALAN** = terukur, terpakai · **JALAN-TIPIS** = benar tapi cakupan kecil ·
**JALAN-KOSONG** = implementasinya benar, sumbernya kosong · **PARSIAL** = ada di detail,
tidak ada di listing/filter · **BELUM** = tidak ada implementasinya.

### Followers — **JALAN**

* Sumber resmi: `kol_directory.followers_count` — **7.498 · 97,1%** (P-02, APPROVED/CLOSED).
* Field endpoint `followers`; filter `?follMin=`; sort `followers` (default); kolom tabel;
  kolom CSV/Excel.
* **Peringatan yang harus dibawa:** `l2_gold.kol_profile_card.followers_count` berbeda
  untuk **1.024 dari 1.972** akun (rata-rata selisih 252.320). Dua penyebab berlawanan —
  ~970 roster basi (L2 benar) dan **54 scrape TikTok rusak** (roster benar). Roster tetap
  source of truth; **rekonsiliasinya belum diputuskan**.

### Historical Followers — **BELUM**

* `l1_silver.unified_profile` memang menyimpan snapshot berurutan, dan itu memang tempat
  yang benar (§9 Task 5: jangan buat tabel riwayat baru).
* **Tapi kedalamannya belum cukup jadi deret waktu:** gudang menyimpan paling banyak
  **2 snapshot per akun**, dan **0 akun punya 3 snapshot**.
* Tidak ada endpoint yang mengembalikan deret follower. Kurva enam bulan di halaman detail
  masih **model**, bukan data — dan ditandai demikian.

### Growth — **JALAN-TIPIS**

* Sumber: `l2_gold.kol_profile_card.followers_growth`, diambil lewat
  `kol_directory → kol_social_account → kol_profile_card` dengan `LEFT JOIN LATERAL … LIMIT 1`
  yang diurut `followers_count DESC` (akun terbesar, sama dengan yang memasok avatar/bio).
* Rumus dibawa apa adanya dari `l1_silver.sp_build_unified_profile()`:
  `round((followers − followers_sebelumnya) / followers_sebelumnya × 100, 4)`.
  **Tidak ada rumus baru di backend.**
* Cakupan **25 dari 7.720 (0,32%)**. Jarak antar snapshot **10 hari (22 akun) · 13 hari (3 akun)**.
  Sebaran: naik 10 · datar tepat 0% 8 · turun 7.
* **Label wajib "Sejak Snapshot Terakhir".** Dilarang disebut "Monthly" atau "30 hari" —
  larangan ini juga tertulis sebagai komentar di kode.
* Field `growthPct`; filter `?growthMin=`/`?growthMax=`; sort `growth`; kolom tabel; kolom CSV.
* Filter memakai **preset**, bukan slider, karena 0% adalah nilai sah yang benar-benar muncul
  (8 dari 25 akun): `Any` · `Naik (>0%)` · `Datar (0%)` · `Turun (<0%)` · `≥0,5%` · `≥1%`.
  Preset dikalibrasi ke sebaran nyata — ambang prototype 4,5%/8% mengembalikan nol hasil.
* **Growth 30D tidak ada** dan tidak bisa dipercepat kode.

### Tier — **JALAN**

* Dihitung saat query: `LEFT JOIN public.kol_tiers ON followers_count BETWEEN min AND max`.
  Ambang di tabel, bukan di config — satu tabel dipakai bersama Discovery dan
  `sp_build_unified_profile()`.
* Migration **033** membetulkan dua baris yang salah (Mid-tier 50rb–499.999, Macro
  500rb–999.999). Dampak: **1.103 KOL pindah Macro → Mid-Tier**.
* Migration **034** (P-01) membuang fallback di L1 yang menjatuhkan follower di bawah
  ambang terendah ke tier terbawah. Follower <1.000 dan follower kosong **tidak dapat
  tier** (`NULL`), tanpa kelompok `Unclassified`.

  | Tier | KOL |
  |---|---:|
  | Nano (1rb–10rb) | 1.943 |
  | Micro (10rb–50rb) | 2.942 |
  | Mid-tier (50rb–500rb) | 1.809 |
  | Macro (500rb–1jt) | 187 |
  | Mega (1jt+) | 313 |
  | *Tanpa tier* (304 di bawah 1rb + 222 tanpa data) | *526* |

* Field `tier`; filter `?tier=a,b` (multi); facet ber-count dengan `min`/`max`;
  kolom tabel; kolom CSV.
* Nama di database masih `Mid-tier` (t kecil) — **sengaja belum diganti**, karena nilainya
  sudah tersimpan sebagai teks di L1/L2 dan dipakai Saved List.

### Verified — **JALAN** *(dihapus 7 Sep, dikembalikan 9 Sep dengan sumber berbeda)*

* Sumber: **`l2_gold.kol_profile_card.is_verified`** — **572 KOL**.
* Diisi asset `gold_profile.py` (keputusan #7) dari badge platform asli:
  `l0_raw.ig_profile_apify.raw_payload->>'verified'` (470 true) dan
  `l0_harmonization.tiktok_profile.is_verified` (124 true).
* Sebelum `fa3af27`, `l1_silver.unified_profile.is_verified` diisi **ekspresi Connected**
  (migration 031), sehingga 2.010 baris L1 dan 1.979 kartu L2 semuanya `false` — badge
  platform hilang di tengah jalan. Sekarang diambil dari sumbernya; diverifikasi **0 beda**.
* `kol_directory.verified_status` (454 verified) **tidak dipakai**.
* Field `verified`; filter `?verified=1`; badge centang di kartu dan tabel.

### Connected — **JALAN-KOSONG** *(dan itu benar)*

* Definisi bisnis (migration 031): `social_account.platform_user_id IS NOT NULL`
  **DAN** `oauth_token IS NOT NULL`, **di baris `social_account` yang sama**.
  Diterapkan sebagai `EXISTS`, jadi satu KOL tetap satu baris.
* Hasil **0 dari 7.720**, dan itu benar — belum ada kreator yang menghubungkan akun.
* Tiga sumber yang **dilarang** dipakai sebagai patokan: `kol_directory.platform_user_id`
  (930 terisi, tapi hasil scraping bukan bukti connect), `social_account.connected`
  (legacy, selalu `false`), dan `verified_status` (badge platform).
* Field `connected`; filter `?connected=1`; ikon **rantai** — sengaja berbeda dari centang
  Verified.
* **224 KOL tidak punya akun sosial sama sekali** — untuk mereka jawabannya *belum
  diketahui*, bukan *tidak terhubung*.
* Karena Verified 572 dan Connected 0, **salah satu tidak akan pernah bisa mewakili yang lain**.

### Engagement Rate (ER) — **JALAN, dengan sumber berlapis**

```sql
COALESCE(
  feature.{ig,tt}_engagement_analysis.engagement_rate,  -- 38 nilai, rentang 0-16,15%
  kol_directory.engagement_rate                         -- 1.757 nilai, maks 223,41%
)
```

* Cakupan **1.757 → 1.767**, **nol KOL hilang**; 10 di antaranya hanya punya nilai feature.
* Feature didahulukan karena penyebutnya follower **pada tanggal post**, dijumlah aditif
  antar post, dengan post kolaborasi dan likes-hidden dikecualikan (`feature_engagement.py`).
  Aturan sampel itu terbukti menahan 43 baris salah-atribusi dari mencemari ER.
* Kolom roster tetap dipertahankan untuk 1.729 sisanya: angka lemah yang masih bisa
  disaring lebih baik daripada tidak ada angka.
* Field `erPct` (satuan persen); filter `?minEr=`; sort `engagement`; kolom tabel; kolom CSV.
* **Belum diputuskan:** memindahkan ER sepenuhnya ke L2 (`kol_metric_daily.er_followers_daily`,
  satuan fraksi) akan memangkas cakupan filter dari 1.756 ke **22 KOL**. Sengaja ditunda.
* Halaman detail memakai ER L2 (`gold.daily/monthly/posts[].erFollowers`) — **satuan berbeda**
  dari `erPct` di listing.

### Category — **JALAN**

* Sumber: `kol_directory.category_ids` (bukan `category_id`) → `kol_categories`.
  1.183 KOL punya lebih dari satu kategori; `category_id` cuma menyimpan salah satunya.
  Endpoint membaca `COALESCE(kd.category_ids, ARRAY[kd.category_id])` karena separuh roster
  masih hanya punya kolom lama.
* Filter dan facet memakai **`COALESCE(kc.taxonomy_key, kc.name)`** — ekspresi yang sama di
  keduanya, sehingga hitungan chip persis sama dengan panjang hasil filter.
  Sebelum `232da34` filter memakai `name`: "Food" menjawab 57 padahal Food punya 123,
  "Dance" 3 padahal Entertainment 501.
* **15 chip**, bukan 9: 9 taksonomi resmi + 6 nama mentah yang belum punya `taxonomy_key`.
  Tanpa `COALESCE`, 6 kategori itu dan 20 KOL yang memakainya tidak terjangkau chip mana pun.
* Nama sub-kategori **tetap diterima** sebagai nilai filter supaya link lama tidak mati.
* Yang **ditampilkan** kartu dan CSV tetap `kc.name` (spesifik), hanya filternya yang melebar.
* Cakupan: 4.174 KOL punya kategori · **4.155** masuk 9 taksonomi resmi (53,82%).

  | Lifestyle | Beauty | Moms | Entertainment | Gen Z | Food | Fashion | Fitness | Tech |
  |---:|---:|---:|---:|---:|---:|---:|---:|---:|
  | 2.592 | 1.271 | 589 | 501 | 150 | 123 | 75 | 52 | 4 |

### Platform — **JALAN**

* Sumber: `platforms.key` lewat `kol_directory.platform_id`. Instagram **3.409** ·
  TikTok **4.087**.
* Field `platform`; filter `?platform=`; facet ber-count; kolom tabel; kolom CSV.
* **Mismatch yang diketahui:** UI mengenali label untuk `instagram`, `tiktok`, `facebook`;
  prototype meminta YouTube. **Tidak ada baris** untuk Facebook maupun YouTube di database.

### Last Updated — **JALAN, dengan arti yang cacat**

* Sumber: `kol_directory.last_refreshed_at` — terisi **7.496 · 97,1%**.
* Field `lastRefreshedAt`; filter `?updatedWithin=<hari>`; sort `recent`; kolom tabel
  ("Updated"); kolom CSV.
* Baris ber-`last_refreshed_at` NULL **tidak pernah** memenuhi "dalam N hari" — 224 baris itu
  keluar selagi filter aktif dan kembali begitu dibersihkan, sama seperti perlakuan `follMin`.
* **73,6% nilainya bukan jejak scraping** — warisan impor Excel. Dan diverifikasi ia
  **selalu** lebih tua dari `profile_snapshot_date` L2: **1.024 dari 1.024** kasus, nol
  pengecualian. Labelnya harus dibaca *"kapan baris ini terakhir disentuh"*, bukan
  *"kapan di-scrape"*.
* Terkait: badge **Data Status** (`Live` / `Calculated` / `Estimated`) dihitung dari
  `last_refreshed_at >= now() − 7 hari` lalu `scrape_status = 'success'`. Sebarannya
  timpang: **Live 1 · Calculated 27 · Estimated 7.693**. Badge ini **tidak** bisa difilter.

### Agency — **JALAN**

* Sumber: `public.agency_kol_accounts` + `public.agencies` (dengan `deleted_at IS NULL`).
  Menamai **7.684 dari 7.718** KOL aktif.
* Field `agency` — diisi `attachRosterExtras()` **sesudah** paging, dengan
  `DISTINCT ON (kol_account_id) … ORDER BY created_at DESC`.
* Filter `?agency=<nama>` memakai **`EXISTS`**, bukan `JOIN`: kreator yang terdaftar di dua
  agency tetap satu baris dan tidak menggelembungkan hitungan.
* Facet ber-count dengan `COUNT(DISTINCT kd.id)`, dengan alasan yang sama.
* Kolom tabel opsional. **Tidak ada di kolom CSV/Excel.**
* `agency_kol_accounts.label` juga jadi sumber `identity.displayName` di halaman detail —
  satu-satunya nama asli di database `public`.

### Content Format — **PARSIAL** *(detail saja, tanpa filter)*

* Sumber: `l2_gold.content_format_daily` — **300 baris · 30 akun · 6 nilai `media_type`**
  (IG `clips` 89 / `carousel_container` 67 / `feed` 22 / `unknown` 8; TT `VIDEO` 289 / `CAROUSEL` 2).
* Endpoint detail mengembalikan `gold.formats[]` (deret harian) dan **`gold.dominantFormat`**
  — format dengan post terbanyak, tie-break total engagement lalu nama, diturunkan dari
  baris yang sudah diambil (tanpa query kedua). Cakupan **56 akun**.
* **`media_type` tidak dipetakan** ke kosakata prototype (Reels/Feed/Carousel). Pemetaan itu
  tidak terdefinisi di mana pun; mengarangnya berarti menaruh label yang tidak didukung data.
* **Tidak ada filter format di listing.** Story tidak punya sumber sama sekali.

### Heatmap jam posting — **PARSIAL** *(detail saja, dibaca dari Feature)*

* Sumber: `feature.{ig,tt}_engagement_analysis.best_posting_time_heatmap` (JSONB array
  `{dow, hour, posts, avg_engagement}`) — **50 akun**.
* **Dibaca langsung dari layer Feature**, bukan L2: `l2_gold` di database `kol` hanya punya
  8 tabel dan `posting_time_heatmap` bukan salah satunya. Menambahkannya berarti migration.
* `dow` = `EXTRACT(DOW)` (0 = Minggu), `hour` = 0..23, **keduanya sudah Asia/Jakarta**
  (`feature_engagement.py` mengekstraknya dengan `AT TIME ZONE 'Asia/Jakarta'`) —
  **jangan digeser lagi**.
* Sel yang bentuknya tidak sesuai dibuang, tidak ditebak.
* Field `gold.heatmap[]`. **Tidak ada filter maupun sort.**

### Rate Card — **JALAN-KOSONG** *(endpoint benar, tabel kosong)*

* Field `rateFrom` (fee termurah, IDR) dan `rateCount` (jumlah deliverable berharga), diisi
  `attachRosterExtras()` dari `l1_silver.unified_rate_card`.
* Filter `?maxRate=` memakai `EXISTS (… fee IS NOT NULL AND fee <= $)`. Kreator tanpa rate
  card **sengaja dikecualikan** saat filter aktif: pertanyaannya "harga di bawah N", dan
  "tidak punya harga" bukan jawabannya.
* **`l1_silver.unified_rate_card` = 0 baris** (diukur 8 Sep). Akibatnya filter ini
  **aktif dan selalu mengembalikan 0 dari 7.720** — begitu slider digeser dari maksimum,
  direktori kosong total.
* **Sumbernya ada dan lengkap:** `l0_raw.kol_roster_import` 7.718 baris / 7.496 KOL, tujuh
  kolom harga terisi (`story_price`, `story_session_price`, `feed_photo_price`,
  `feed_video_price`, `reel_price`, `live_price`, `owning_asset_price`).
  Procedure `l0_harmonization.sp_sync_roster_rate_card()` dan
  `l1_silver.sp_build_unified_rate_card()` **sudah ada dan matang**.
  Yang hilang: **asset Dagster yang memanggilnya** — `harmonization.py` sengaja tidak
  membuatkannya dengan alasan "sumber L0 0 baris", yang benar untuk `l0_extra.*_rate_card`
  tapi tidak berlaku untuk `kol_roster_import`.
* ⚠ Angka **"9.210 baris / 7.230 akun"** di `docs/L0_L1_L2_FLOW.md` dan di docstring
  `kolMeasured.ts` / `gold_profile.py` **tidak akurat** — itu hasil yang *akan* dihasilkan
  procedure, bukan isi tabel sekarang. Dikoreksi di `AUTOME_2_DEVELOPMENT_AUDIT.md` §K-1.

### Identitas (avatar · bio · display name) — **JALAN**

* `COALESCE(l2_gold.kol_profile_card.*, kol_directory.*)`, lewat LATERAL yang sama dengan Growth.
  L2 terbukti **superset ketat**: nol kasus roster punya nilai sementara L2 tidak.

  | Field | Roster | Sesudah COALESCE |
  |---|---:|---:|
  | avatar | 931 | **1.979** |
  | bio | 902 | **1.878** |
  | display name | *tidak ada kolomnya* | **1.961** |

* `COALESCE`, bukan penggantian, supaya baris roster yang lebih dulu terisi tidak mundur.
* Nama yang cuma mengulang handle disaring (`cleanDisplayName`) — mencetak "@budi budi"
  tidak menolong siapa pun.

### Audiens (gender · geo · minat · kualitas) — **PARSIAL**

* `l2_gold.audience_demographics_daily` (69) · `audience_geo_daily` (181) ·
  `audience_interest_daily` (214), semuanya dari `feature.{ig,tt}_audience_analysis`
  yang berbasis `l1_silver.unified_follower` — **inferensi**, bukan Insights resmi.
* Ter-wire penuh di halaman detail dengan label `inferred_high/medium/low` dan cakupan
  ditulis di bawah chart. **23 KOL.**
* `confidence` adalah **label** (`character varying`), bukan angka — dipakai
  `MODE() WITHIN GROUP`, bukan `AVG()`.
* `unknown` dipisahkan dari chart: ia bucket terbesar hampir di mana-mana (61% gender,
  90% country, 78% interest).
* **Tidak ada satu pun filter audiens di listing.** `audience_type='age'` masih **0 baris** —
  chart umur sudah dikodekan tapi tidak dirender.
* Skor `authenticity_score` / `audience_quality_score` **ada di Feature tapi belum diekspos
  endpoint**.

### Post & konten terukur — **JALAN-TIPIS**

* `l2_gold.post_metric` (477 baris · 30 akun) dan `kol_metric_daily/_monthly` — tabel Top Posts,
  grafik harian/bulanan di halaman detail.
* IG **tidak punya** `shares`/`saves` (0 dari 186 baris); TikTok punya (291 baris).
* `reach`, `er_reach`, `reposts`, `avg_watch_time_seconds`, `completion_rate` **NULL 100%** —
  UI **tidak merender tile** untuk kolom NULL.
* Post ownership: `116243e` menyaring item yang bukan milik akun roster sebelum `INSERT`,
  dan membatasi 10 post terbaru per `social_account_id`.

### "Est. Reach" di tabel listing — **turunan UI, bukan metrik backend**

`followers × erPct / 100`, dihitung di komponen React. Tidak ada di endpoint, tidak ada di
database, tidak bisa difilter maupun di-sort. Ditandai "Est." di header kolom.

---

## 4. Existing Endpoints / Data Access

### 4.1 `GET /api/organizations/[id]/discover/kol-directory` — listing

| | |
|---|---|
| **File route** | `src/app/api/organizations/[id]/discover/kol-directory/route.ts` |
| **Query layer** | `src/lib/discover/kolDirectory.ts` → `listKolDirectory()`, `listKolFacets()` |
| **Akses** | `requireOrgMemberById(orgId)` — roster-nya global, tapi tetap butuh keanggotaan org |
| **Query utama** | `WITH base AS (…) , filtered AS (…) SELECT *, COUNT(*) OVER() AS total_count FROM filtered ORDER BY … LIMIT … OFFSET …` |

**Tabel yang dibaca `BASE`:** `public.kol_directory` · `platforms` · `kol_tiers` ·
`kol_categories` · `kol_social_account` · `social_account` · `l2_gold.kol_profile_card` ·
`feature.ig_engagement_analysis` + `feature.tt_engagement_analysis`.
Sesudah paging: `agency_kol_accounts` + `agencies` + `l1_silver.unified_rate_card`.

**Parameter:**
`q` · `platform` · `category` · `tier` (koma) · `follMin` · `minEr` · `maxRate` ·
`growthMin` · `growthMax` · `connected=1` · `verified=1` · `updatedWithin` · `agency` ·
`sort` · `dir` · `page` · `pageSize` · `facets=1` · `ids` (koma, maks 50 UUID)

**Yang dikembalikan:**

```
{ rows: [ id, username, displayName, platform, profileUrl, avatarUrl, bio, city,
          categories[], followers, erPct, tier, growthPct, connected, verified,
          status, lastRefreshedAt, agency, rateFrom, rateCount ],
  total, page, pageSize,
  facets?: { categories[{name,count}], platforms[{key,count}],
             tiers[{name,count,min,max}], agencies[{name,count}], rosterTotal } }
```

**Empat keputusan di route yang menentukan hasil:**

1. **Parameter absen harus tetap absen.** `Number(null)` = 0, dan `minEr = 0` bukan
   "tanpa minimum" — `er_pct >= 0` membuang setiap kreator yang ER-nya tidak pernah
   terukur, yaitu mayoritas roster. Semua angka lewat helper `num()`.
2. **Batas Growth boleh negatif dan boleh tepat 0**, jadi ikut lewat `num()` — bukan cek
   truthiness.
3. **`ids` divalidasi bentuk UUID** dan dibatasi 50, karena nilai rusak akan menggagalkan
   statement, bukan mengembalikan kosong.
4. **Sort key di-whitelist** dan arah direduksi ke dua literal — keduanya diinterpolasi ke
   statement, tidak pernah diparameterkan.

### 4.2 `GET /api/organizations/[id]/discover/kol-directory/[kolId]` — detail

| | |
|---|---|
| **Query layer** | `kolDirectory.ts` → `getKolCreator()` |
| **Turunan** | `kolGold.ts` → `getKolGold()` · `kolMeasured.ts` → `getKolMeasured()` |

Mengembalikan `KolCreatorPayload`:

| Field | Isi | Sumber |
|---|---|---|
| `creator` | baris yang sama dengan listing | `BASE` |
| `identity` | `displayName`, `agency` | `agency_kol_accounts.label` + `agencies` |
| `rank` | peringkat & persentil followers/ER, di roster dan di dalam kategori | dihitung dari roster |
| `platforms[]` | akun saudara di platform lain (termasuk barisnya sendiri) | `kol_directory` |
| `similar[]` | tetangga roster — kategori sama, ukuran terdekat | `kol_directory` |
| `measured` | post & rate card terukur | **L1** `unified_post`, `unified_rate_card` |
| `gold` | `cards[]`, `daily[]`, `monthly[]`, `gender[]`, `age[]`, `geo[]`, `interest[]`, `posts[]`, `formats[]`, **`dominantFormat`**, **`heatmap[]`** | **L2** 8 tabel + **Feature** (heatmap) |

`getKolGold()` menjalankan **10 query paralel**, semuanya di-join lewat
`public.kol_social_account`. Mengembalikan `null` kalau L2 tidak punya apa pun; tiap field
di dalamnya tetap bisa kosong sendiri-sendiri, jadi pemanggil mengecek field, bukan objek.

Mengembalikan `null` (bukan melempar) untuk id yang tidak dikenal atau sudah diarsipkan,
supaya route menjawab 404 dan bukan 500.

### 4.3 `GET /api/organizations/[id]/discover/kol-directory/[kolId]/cover/[postId]`

Proxy gambar cover post. Tidak membaca metrik.

### 4.4 Data access di repo ini (Python, read-only)

| | |
|---|---|
| **Fungsi** | `db.search_kol_directory(conn, q, taxonomy_key, limit, offset)` |
| **CLI** | `python search_kol.py <keyword> [--category <Discovery Category>] [--limit] [--offset]` |
| **Mencari di** | `username` (7.497) · `kol_profile_card.display_name` (1.958) · `bio` (902) |
| **Menyaring** | `kol_categories.taxonomy_key` — 9 Discovery Category |
| **Mengembalikan** | `id, username, display_name, platform, followers_count, discovery_category` |
| **Batas** | `limit` dipaksa ke 1..200 |

Urutan hasil berjenjang: cocok di awal username > cocok di tengah username > cocok di bio.
Tanpa penjenjangan, `beauty` mengembalikan 135 baris tercampur rata.

> ⚠ **Dua implementasi pencarian belum sama.** `db.search_kol_directory()` mencari tiga
> kolom; endpoint Discovery (`kolDirectory.ts`) hanya `b.username ILIKE '%…%'`.

### 4.5 Endpoint `/discover/*` lain — di luar scope roster KOL

`content`, `summary`, `directory`, `creators`, `assistant`, `rates`, `orders`,
`inspirations`, `profiles`, `account` melayani korpus brand/kompetitor atau entitas lain.
Yang menyentuh roster hanya `/discover/rates` (membaca `unified_rate_card`, jadi ikut kosong)
dan alur `orders/*` (siap, tapi tanpa harga).

---

## 5. Existing Filters & Sorting

### 5.1 Filter yang benar-benar diproses backend — **12**

| # | Filter | Parameter | Sumber | Cakupan | Catatan |
|---:|---|---|---|---:|---|
| 1 | Cari nama | `q` | `kol_directory.username` | 7.497 | **hanya username** — bukan bio/display name |
| 2 | Platform | `platform` | `platforms.key` | 7.496 | IG 3.409 · TT 4.087 |
| 3 | Kategori | `category` | `COALESCE(taxonomy_key, name)` | 4.155 | 15 chip; nama sub-kategori tetap diterima |
| 4 | Tier | `tier` (multi) | `kol_tiers` band | 7.194 | 526 KOL tanpa tier |
| 5 | Minimum follower | `follMin` | `kol_directory.followers_count` | 7.498 | skala berjenjang 0 … 10jt |
| 6 | Minimum ER | `minEr` | `COALESCE(feature, roster)` | **1.767** | NULL tersaring keluar saat aktif |
| 7 | Maksimum rate card | `maxRate` | `l1_silver.unified_rate_card` | **0** | **aktif, selalu 0 hasil** |
| 8 | Growth | `growthMin` / `growthMax` | `kol_profile_card.followers_growth` | 25 | preset, bukan slider |
| 9 | Connected | `connected=1` | `platform_user_id` + `oauth_token` | **0** | benar, bukan bug |
| 10 | Verified | `verified=1` | `kol_profile_card.is_verified` | **572** | sumbu terpisah dari Connected |
| 11 | Last Updated | `updatedWithin=<hari>` | `kol_directory.last_refreshed_at` | 7.496 | NULL tersaring keluar saat aktif |
| 12 | Agency | `agency=<nama>` | `agency_kol_accounts` + `agencies` | 7.684 | `EXISTS`, facet ber-count |

Ditambah `ids` (bukan filter pengguna): mengambil himpunan id eksplisit untuk **Compare**,
mengabaikan paging, tetap tunduk pada seluruh filter lain. Array kosong berarti "tanpa
filter id", bukan "tanpa hasil".

**UI hanya merender kontrol untuk 12 filter ini.** Section prototype yang backend-nya belum
ada — demografi audiens, authenticity, brand fit, paid ratio, campaigns run, format konten —
**sengaja tidak digambar** daripada tampil sebagai kontrol yang tidak menyaring apa pun.
Gap-nya besar, tapi tidak ada filter palsu.

**NULL handling belum diseragamkan.** `minEr`, `maxRate`, `updatedWithin`, dan `follMin`
semuanya **membuang** baris tanpa nilai saat aktif. Untuk `minEr` itu berarti sampai 5.964
KOL keluar dari hasil. Apakah NULL harus dibuang, diloloskan, atau ditandai — **belum
diputuskan** (D3/Q2).

### 5.2 Sorting

`SORT_COLUMNS` di backend berisi **6 kunci**; UI menampilkan **5**.

| Kunci | Kolom | Di UI? |
|---|---|---|
| `followers` | `followers` | ✅ (default, `desc`) |
| `engagement` | `er_pct` | ✅ |
| `growth` | `growth_pct` | ✅ |
| `recent` | `last_refreshed_at` | ✅ "Last updated" |
| `name` | `username` | ✅ |
| `created` | `created_at` | ❌ dipakai shelf "Recently added", bukan kontrol sort |

Aturan urutan:

* **Pilihan user adalah kunci pertama. Tidak ada yang mendahuluinya.** Kunci lama
  `SCRAPED_FIRST` (`CASE status …`) sudah dibuang di `232da34`: dengan sebaran Live 1 ·
  Calculated 27 · Estimated 7.693, ia menaruh 28 creator di puncak apa pun sort-nya —
  `bobbykertanegara` (948.683) mengalahkan `cristiano` (679.264.838) saat menurun, dan
  tetap di atas `sekata_ai` (200) saat menaik.
* **`NULLS LAST` di kedua arah**, termasuk cabang `username` — Postgres default `NULLS FIRST`
  untuk `DESC`, yang dulu membuka daftar dengan baris kosong.
* **Tie-break berakhir di `id`** yang unik, karena username tidak unik: 7.721 baris aktif
  hanya punya 7.224 username. Tanpa kunci unik, sampai 497 baris berada dalam urutan yang
  bebas diubah planner — dua halaman bisa mengulang satu creator sambil menjatuhkan yang lain.
* Kolom `status` tetap dikembalikan dan tetap digambar sebagai chip; ia hanya tidak lagi
  menentukan urutan.

### 5.3 Pagination

| | |
|---|---|
| Ukuran halaman UI | **12** |
| Default route | 20 |
| Batas atas | **60** (`MAX_PAGE_SIZE`) |
| Total | `COUNT(*) OVER()` — dalam round trip yang sama; halaman di luar jangkauan mengembalikan 0 |
| `ids` | mengabaikan paging; `pageSize` = jumlah id |
| Navigasi | jendela halaman `1 … 4 5 [6] 7 8 … 644` |

### 5.4 Facets

Diminta sekali dengan `?facets=1` pada muat pertama, lalu dipakai ulang — supaya daftar
opsi tidak melompat-lompat saat orang mengetik. Dihitung atas **seluruh roster aktif**,
bukan hasil filter saat ini: kategori yang akan mengosongkan grid tetap layak ditampilkan
dengan hitungan sebenarnya.

`categories` · `platforms` · `tiers` (dengan `min`/`max`) · `agencies` · `rosterTotal`.

Kategori dan agency memakai `COUNT(DISTINCT kd.id)` supaya hitungan chip sama persis dengan
panjang hasil filter.

### 5.5 Export

| Format | Cara | Isi |
|---|---|---|
| **CSV** | tombol bulk, atas baris yang dicentang | 11 kolom |
| **Excel** | tombol bulk, atas baris yang dicentang | 11 kolom yang sama |

Kolom: `Username` · `Display name` · `Platform` · `Followers` · `Engagement rate (%)` ·
`Tier` · **`Growth % (sejak snapshot terakhir)`** · `Categories` · `Data status` ·
`Last refreshed` · `Profile URL`.

**Tidak ada di export:** `connected`, `verified`, `agency`, `rateFrom`, `city`, `bio`.
Export hanya mengambil **baris terpilih di halaman aktif**, bukan seluruh hasil filter.

### 5.6 Kolom tabel opsional

`tier` · `growth` · `reach` (Est., dihitung di UI) · `platform` · `category` · `updated` ·
`agency` · `rate`. Yang bisa diklik untuk sort hanya `growth` dan `updated`, ditambah
kolom tetap Creator / Followers / Engagement.

---

## 6. Feature Status

Legenda — **Source**: data mentahnya ada · **Pipeline**: ada asset/procedure yang mengolahnya ·
**L2**: tersedia di `l2_gold` · **Endpoint**: dikembalikan API · **UI**: dirender.

| Feature | Source | Pipeline | L2 | Endpoint | UI | Status | Notes |
|---|---|---|---|---|---|---|---|
| Followers | ✅ roster 7.498 | ✅ | ✅ 1.972 | ✅ list+detail | ✅ | **JALAN** | Roster = source of truth (P-02); beda dengan L2 di 1.024 akun, belum direkonsiliasi |
| Historical Followers | ⚠ maks 2 snapshot/akun | ✅ L1 | ⚠ | ❌ tidak ada deret | ⚠ kurva masih model | **BELUM** | 0 akun punya 3 snapshot |
| Growth (sejak snapshot terakhir) | ✅ 25 | ✅ L1 | ✅ | ✅ + filter + sort | ✅ kolom, tile, CSV | **JALAN-TIPIS** | 0,32%; jarak 10–13 hari; label wajib "Sejak Snapshot Terakhir" |
| Growth 30D / classification | ❌ span belum cukup | ❌ | ❌ | ❌ | ❌ | **BELUM** | Butuh snapshot ≥30 hari; butuh `days_between` |
| Tier | ✅ 7.194 | ✅ mig 033/034 | ✅ | ✅ + filter + facet | ✅ | **JALAN** | Ambang dari `kol_tiers`, dipakai bersama L1 |
| Verified | ✅ L0 IG 470 + TT 124 | ✅ `gold_profile.py` #7 | ✅ 572 | ✅ + filter | ✅ badge centang | **JALAN** | Dihapus 7 Sep, dikembalikan 9 Sep dengan sumber berbeda |
| Connected | ✅ kolomnya ada | ✅ mig 031 | — | ✅ + filter | ✅ ikon rantai | **JALAN-KOSONG** | 0 dari 7.720 — benar, bukan bug |
| Engagement Rate | ✅ 1.767 | ✅ Feature + roster | ⚠ 22 akun | ✅ + filter + sort | ✅ | **JALAN** | `COALESCE(feature, roster)`; ER kanonik ditunda |
| Category | ✅ 4.155 | — | — | ✅ + filter + facet | ✅ | **JALAN** | `COALESCE(taxonomy_key, name)`, 15 chip |
| Platform | ✅ 7.496 | ✅ | ✅ | ✅ + filter + facet | ✅ | **JALAN** | Tidak ada YouTube/Facebook di database |
| Last Updated | ✅ 7.496 | — | — | ✅ + filter + sort | ✅ | **JALAN** | 73,6% warisan Excel — arti kolomnya cacat |
| Agency | ✅ 7.684 | — | — | ✅ + filter + facet | ✅ kolom opsional | **JALAN** | Tidak ada di export |
| Content Format | ✅ 30 akun | ✅ `gold_post.py` | ✅ 300 baris | ✅ detail (`formats`, `dominantFormat` 56 akun) | ✅ tab Content | **PARSIAL** | Tidak ada filter di listing; `media_type` tidak diterjemahkan |
| Heatmap jam posting | ✅ 50 akun | ✅ Feature | ❌ **tidak ada tabel L2** | ✅ detail (`gold.heatmap`) | ✅ | **PARSIAL** | Dibaca langsung dari Feature; dow/hour sudah WIB |
| Rate Card | ✅ **7.496 KOL di L0** | ❌ **procedure tak dipanggil** | ❌ (kolom L2 NULL) | ✅ + filter `maxRate` | ✅ kolom + detail | **JALAN-KOSONG** | Filter aktif, selalu 0 hasil. Bukan gap data — gap asset |
| Identitas (avatar/bio/display name) | ✅ | ✅ | ✅ 1.976 | ✅ `COALESCE(L2, roster)` | ✅ | **JALAN** | avatar 1.979 · bio 1.878 · nama 1.961 |
| Post terukur (likes/comments/views/ER/rank/hashtag) | ✅ 477 baris | ✅ | ✅ | ✅ detail | ✅ Top Posts | **JALAN-TIPIS** | 30 akun |
| Save / Share rate | ❌ IG 0/186 · ✅ TT 291 | ✅ TT | ✅ | ✅ detail (mentah) | ⚠ | **PARSIAL** | IG tidak mengembalikan shares/saves |
| Audiens gender/geo/minat | ✅ inferensi 23 KOL | ✅ (di luar rantai sensor) | ✅ | ✅ detail | ✅ tab Audience | **PARSIAL** | **Tidak ada filter di listing** |
| Umur audiens | ❌ 0 baris | ❌ | kolom ada | ✅ (kosong) | chart siap, tidak dirender | **BELUM** | `audience_type='age'` tidak pernah ditulis |
| Authenticity / Audience Quality | ✅ Feature 23 KOL | ✅ | ❌ | ❌ | ❌ | **BELUM** | Skornya ada, belum diekspos |
| Avg/Median views · Posting frequency · Paid ratio · V2F · L2V | ✅ bahan di L2 | ✅ | ⚠ mentah | ⚠ mentah saja | ⚠ dihitung di UI | **BELUM** | Agregat per akun belum pernah dihitung |
| Data status badge | ✅ | — | — | ✅ `status` | ✅ chip | **JALAN, timpang** | Live 1 · Calculated 27 · Estimated 7.693; tidak bisa difilter |
| Est. Reach | — | — | — | ❌ | ✅ kolom | **turunan UI** | `followers × erPct / 100`, bukan metrik backend |
| Reach · Impressions · Watch time | ❌ 0 | — | kolom ada, NULL | ❌ | ⚠ sample | **BELUM** | Butuh Insights API |
| Sentiment · Content topic | ✅ raw di L0 | ❌ tidak ada asset | ❌ | ❌ | ❌ | **BELUM** | Nol biaya Apify, tinggal asset |
| Brand fit | ❌ 0 baris | ❌ | ❌ | ❌ | ⚠ sample | **BELUM** | Grain KOL×brand |
| Creator city | ❌ 0/7.720 | — | — | ✅ `city` | ✅ | **BELUM** | Kolom ada, isi kosong |
| Profiling Status | ❌ | — | — | ❌ | animasi klien | **BELUM** | Tidak ada nilai "sedang diproses" di database |
| Monitoring / Update Frequency / Next Update | ❌ `refresh_tier` 0 · `scheduler_config` 0 | — | — | ❌ | ❌ | **BELUM** | Keputusan jadwal belum diambil |
| Collections / Saved list | ❌ tabel tidak ada | — | — | ❌ | state klien | **BELUM** | Satu-satunya tabel baru yang perlu dibuat |
| Compare | ✅ | — | — | ✅ lewat `ids` | ✅ | **JALAN** | Maks 50 id |
| Ordering / Cart / Checkout | ✅ tabel app | ✅ | — | ✅ 7 route `orders/*` | ✅ | **JALAN, tanpa harga** | Bergantung rate card |

---

## 7. Known Gaps / Dependencies

Hanya gap yang benar-benar terukur pada audit 8–9 September. Diurutkan dari yang paling
murah dihilangkan.

### G1 — Rate Card: procedure ada, asset-nya tidak *(P0)*

* **Bukti:** `l0_raw.kol_roster_import` 7.718 baris / 7.496 KOL, 7 kolom harga terisi ·
  `sp_sync_roster_rate_card()` dan `sp_build_unified_rate_card()` ada dan lengkap ·
  `l1_silver.unified_rate_card` **0 baris** · `harmonization.py` tidak membuatkan asset.
* **Dampak sekarang:** filter `maxRate` aktif dan mengembalikan **0 dari 7.720**. CPV, CPE,
  EMV, dan seluruh alur Ordering ikut kehilangan dasar harga.
* **Butuh:** keputusan menjalankan procedure di produksi (menulis ~9.210 baris ke
  L0-harmonization + L1; idempoten, `ON CONFLICT`). **Tanpa kode baru, tanpa migration.**

### G2 — NULL handling di empat filter belum diputuskan *(P0)*

`minEr`, `maxRate`, `updatedWithin`, `follMin` semuanya membuang baris tanpa nilai saat
aktif. Untuk `minEr` itu sampai **5.964 KOL**. Tiga pilihan — buang, loloskan, atau tandai —
dan sampai dipilih, tampilan harus bisa menjawab tiga jawaban, bukan dua:
*cocok · tidak cocok · **belum ada datanya***. Perubahannya satu file, beberapa klausa `WHERE`.

### G3 — Followers roster vs L2 belum direkonsiliasi

* 1.024 dari 1.972 akun berbeda; ~970 karena roster basi, **54** karena scrape TikTok rusak.
* Risiko terburuknya sudah ditutup oleh **migration 035** (sanity guard, 51 baris → NULL),
  jadi nilai runtuh tidak lagi jadi penyebut growth.
* **Yang tersisa:** UI menampilkan follower roster sementara `growthPct` dihitung dari
  follower L2 — kedua angka tidak bisa direkonsiliasi pengguna. Butuh keputusan source of
  truth, bukan kode.

### G4 — Growth 30D menunggu waktu, dan waktunya tidak berjalan

* Butuh dua snapshot berjarak ≥30 hari. Sekarang jaraknya 10–13 hari, dan **0 akun punya
  3 snapshot**.
* **Scraping berhenti sejak 2026-08-28**, jadi angka 25 tidak bergerak sama sekali.
* Kalau scheduler profil berkala mulai minggu ini, span 30 hari paling cepat tercapai
  **awal Oktober**. Tidak bisa dipercepat kode.
* Ikut terblokir: Rising Creator, Performance Stability, Viral Frequency, Momentum,
  Consistency, dan **Historical Followers** sebagai deret waktu.

### G5 — Posting Frequency: requirement belum jelas

Bahannya ada (`kol_metric_monthly` 68 baris), tapi definisinya tidak: per minggu atau per
bulan, atas jendela berapa lama, dan bagaimana memperlakukan akun dengan satu bulan aktif.
`post_count` juga sempat menggelembung untuk akun yang post-nya banyak kolaborasi
(`irwansyah_15`: `post_count` 10, `posts_in_sample` 0) — konsumen metrik ini belum ada, jadi
belum pernah terasa.

### G6 — Avg/Median Views, Paid Ratio, V2F, L2V: agregat belum pernah dihitung

Bahannya lengkap di `l2_gold.post_metric` dan `kol_metric_daily/_monthly`, tapi tidak ada
kolom agregat per akun. Menyimpannya di L2 berarti **migration**; menghitungnya di endpoint
berarti query tambahan per baris. Sekarang UI menghitung sebagian sendiri dari data mentah,
yang berarti aturannya hidup di komponen React.

### G7 — Heatmap: Feature → Endpoint → UI ada, **L2 tidak**

`l2_gold` di database `kol` punya 8 tabel dan `posting_time_heatmap` bukan salah satunya.
Endpoint membacanya langsung dari `feature.{ig,tt}_engagement_analysis` (50 akun) supaya
tidak perlu migration. Berfungsi, tapi menyimpang dari pola "UI hanya membaca L2" — kalau
polanya mau ditegakkan, itu tabel + asset baru.

### G8 — Layer Feature sebagian besar belum diekspos

`ig/tt_audience_analysis` (23 KOL) memegang `authenticity_score`, `audience_quality_score`,
`follower_quality_score`, semuanya 100% terisi — **tidak ada endpoint yang membacanya**.
`format_performance` (17 akun) dan agregat engagement per akun (30 akun) juga sudah dihitung
dan tidak dipakai. Nol biaya scraping.

### G9 — Filter audiens tidak ada di listing

Data gender/geo/minat sudah sampai UI **detail**, tapi tidak ada satu pun filter audiens di
listing. Cakupannya 23 KOL, jadi filternya akan hampir selalu kosong — inilah alasan G2
(tiga jawaban, bukan dua) harus diputuskan lebih dulu.

### G10 — Sumber yang memang tidak ada

| Yang kurang | Kondisi | Jenis pekerjaan |
|---|---|---|
| Reach · Impressions · Watch time · Umur audiens | 0 baris; kolomnya ada | **Insights API** — lead time eksternal |
| Save/Share Instagram | 0 dari 186 baris IG | Keterbatasan actor |
| Story | tidak ada satu baris pun | Tidak ada sumber |
| YouTube · Facebook | tidak ada baris di `platforms` | Keputusan produk + scraper baru |
| Creator city | 0 dari 7.720 | Diisi saat pendaftaran |
| Sentiment · Content topic | raw ada di L0, asset belum ada | **Nol biaya Apify** — tinggal asset |
| Brand fit | 0 baris, grain KOL×brand | Belum pernah dibangun |
| Reliability · Content style | kolomnya tidak ada di database | Fitur baru |
| Data campaign | 14 tabel, 13 kosong | Adopsi produk |

### G11 — Keputusan yang belum diambil (bukan pekerjaan teknis)

| # | Keputusan | Memblokir |
|---|---|---|
| Jadwal refresh per KOL | `refresh_tier` 0 · `scheduler_config` 0 baris | Profiling Status, Data Status, Update Frequency, Next Update, Monitoring Priority — **dan G4** |
| ER kanonik | pindah ke L2 memangkas 1.756 → 22 KOL | Konsistensi ER listing vs detail |
| Budget Apify | ~1.942 akun untuk post; snapshot profil berkala | G4, cakupan ER & konten |
| 277 grup username kembar | dibersihkan di data, atau disaring saat query | **Semua** angka hasil filter (dampak paging sudah ditutup) |
| Chip yang selalu kosong | disembunyikan, atau ditampilkan dengan keterangan | Connected, Story, YouTube, Tech (4 KOL) |
| Collections | tabelnya belum ada | Saved list yang bertahan antar perangkat |

### G12 — Drift dokumentasi yang perlu dibereskan

| Dokumen/kode | Klaim | Kenyataan |
|---|---|---|
| `docs/L0_L1_L2_FLOW.md` tabel L1 | `unified_rate_card` **(9.210)** | **0 baris** (§Rate Card di dokumen yang sama sudah benar) |
| `docs/L0_L1_L2_FLOW.md` §Feature Layer | "tidak satu pun tabel feature dibaca UI" | ER dan heatmap **sudah** dibaca endpoint sejak `232da34` |
| docstring `kolMeasured.ts` / `gold_profile.py` | 9.210 rate card / 7.230 akun | angka *yang akan* dihasilkan procedure, bukan isi tabel |
| komentar `KolDirectoryFilters.tsx` | "badge verified dropped from Discovery" | badge **dikembalikan** di commit yang sama yang menambah `verifiedOnly` |
| Baseline roster | 7.720 · 7.721 · 7.718 dipakai bergantian | tiga pengukuran di waktu berbeda; belum pernah diseragamkan |

---

## 8. Recommended Next Steps

Diurutkan berdasarkan dependency. **Ini urutan, bukan penugasan** — tidak ada pekerjaan baru
yang dimulai dari dokumen ini.

### Tahap 0 — nol risiko, nol biaya, bisa sekarang

| # | Langkah | Kenapa duluan | Butuh |
|---|---|---|---|
| 1 | **Verifikasi read-only rate card** — simulasikan `sp_sync_roster_rate_card()` sebagai `SELECT`, hitung berapa baris yang akan dihasilkan | Mengubah G1 dari perdebatan jadi keputusan berangka. Tidak menulis apa pun | — |
| 2 | **Seragamkan baseline roster** dan bereskan drift dokumentasi G12 | Semua angka lain diukur terhadap baseline ini | — |
| 3 | **Susun daftar target post scraping** (query read-only) dan **dry-run** `post_pipeline.py` / `pipeline.py --order stale` | `--dry-run` tidak memanggil Apify. Menyiapkan langkah 7 tanpa mengeluarkan biaya | — |

### Tahap 1 — menulis data, tanpa kode baru

| # | Langkah | Membuka | Butuh |
|---|---|---|---|
| 4 | **Jalankan `sp_sync_roster_rate_card()` + `sp_build_unified_rate_card()`** | G1 — memperbaiki filter `maxRate` yang sekarang aktif-tapi-salah, dan membuka 7 requirement komersial (CPV, CPE, EMV, Ordering). Procedure idempoten, `ON CONFLICT` | Keputusan Q1 |

Sesudah langkah 4, buatkan asset Dagster-nya supaya tidak perlu dijalankan manual lagi.

### Tahap 2 — kode kecil, satu file, tanpa migration

| # | Langkah | Membuka | Butuh |
|---|---|---|---|
| 5 | **Putuskan lalu terapkan NULL handling** empat filter, dan tampilkan hitungan "belum ada datanya" secara terpisah di UI | G2 — dan menjadi prasyarat G9 | Keputusan Q2/D3 |
| 6 | **Samakan pencarian**: bawa `bio` + `display_name` ke `q` di `kolDirectory.ts` agar setara `db.search_kol_directory()` | §4.4 — dua implementasi menjawab beda | — |

### Tahap 3 — butuh budget, dan waktunya berjalan sejak dijalankan

| # | Langkah | Membuka | Butuh |
|---|---|---|---|
| 7 | **Perluas post scraping bertahap** — filter kepemilikan dan batas 10-terbaru sudah ter-commit (`116243e`) | Cakupan ER, konten, format, views | Q5 (biaya Apify) |
| 8 | **Nyalakan scheduler profil berkala** | **G4** — dan hanya ini yang bisa membuat Growth 30D, Historical Followers, Stability, dan Momentum menjadi mungkin. Setiap minggu penundaan adalah satu minggu penundaan langsung | Q5 + keputusan jadwal (G11) |

### Tahap 4 — sesudah cakupan naik

| # | Langkah | Kenapa sesudah | Butuh |
|---|---|---|---|
| 9 | **Ekspos layer Feature** — authenticity, audience quality, `format_performance`, agregat engagement per akun | Sudah dihitung, nol biaya. Ditaruh di sini karena tidak memblokir apa pun | — |
| 10 | **Asset sentiment & content topic** | Raw sudah ada di L0, nol biaya Apify | — |
| 11 | **Agregat per akun di L2** (avg/median views, posting frequency, paid ratio, V2F, L2V) | G5/G6. Butuh migration, jadi jangan sebelum requirement Posting Frequency jelas | Definisi produk |
| 12 | **Filter audiens di listing** | G9 — hanya masuk akal sesudah langkah 5 (tiga jawaban) dan langkah 7 (cakupan naik) | — |
| 13 | **ER kanonik** | Sengaja terakhir: keputusan 1.756 vs 22 KOL jauh lebih mudah sesudah langkah 7 | D4/Q3 |
| 14 | **Tabel Collections** | Satu-satunya tabel baru yang memang perlu dibuat | Keputusan produk |

**Langkah 1–3 tidak menyentuh apa pun. Langkah 4–6 tidak butuh scraping, tidak butuh
migration, dan tidak butuh menunggu waktu. Langkah 8 adalah satu-satunya yang jam-nya baru
mulai berdetak saat dijalankan** — menundanya menunda G4 satu-banding-satu.

---

## Rujukan

| Topik | Dokumen |
|---|---|
| Kebutuhan filter (Task 1) | `docs/FILTER_REQUIREMENTS 1.md` |
| Ada/tidak ada di database (Task 2) | `docs/FILTER_DB_MAPPING 2.md` |
| Kelengkapan data (Task 3) | `docs/FILTER_DATA_COMPLETENESS 3.md` |
| Sumber final per filter (Task 4) | `docs/FILTER_DATA_SOURCE 4.md` |
| Struktur data filter (Task 5) | `docs/KOL_DISCOVERY_TASK5_DESIGN.md` |
| Alur L0 → L2 → UI | `docs/L0_L1_L2_FLOW.md` |
| Kondisi scraping & pipeline | `docs/PIPELINE_STATUS.md` |
| Trace end-to-end 8 Sep | `docs/AUTOME_2_FULL_TRACE_AUDIT.md` |
| Coverage requirement → UI | `docs/AUTOME_2_FULL_ENDPOINT_COVERAGE_AUDIT.md` |
| Followers roster vs L2 | `docs/AUTOME_2_STEP2B_FOLLOWERS_INVESTIGATION.md` |
| Rancangan sanity guard | `docs/AUTOME_2_STEP3A_FOLLOWERS_GUARD_DESIGN.md` |
| Kamus metrik seluruh layer | `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md` |

---

*Dokumentasi saja. Tidak ada kode, database, migration, scraping, commit, atau push yang
dilakukan saat menyusun dokumen ini. Seluruh angka berasal dari audit read-only yang sudah
ada di `docs/`; struktur endpoint, filter, sorting, dan export dibaca dari kode ter-commit
di `scrapper-project` @ `fa3af27` dan `autometric` @ `232da34`.*
