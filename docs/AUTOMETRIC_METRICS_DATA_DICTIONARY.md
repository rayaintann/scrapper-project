# Autometric — Metrics Data Dictionary

**Scope:** PROFILE dan POST, dari `l0_raw` sampai `feature` (L2).
**Tanggal audit:** 2026-08-20
**Diperbarui:** 2026-08-21 — angka schema `feature` disesuaikan setelah migration 014;
audit penelusuran akun ditambahkan di §13; kolom metrik L1 ditambahkan di §14;
audit `postFreq` di §15; audit kesiapan kolom Feature/L2 di §16
**Database:** `kol` @ 10.100.14.216

---

## ⚠️ Perubahan sejak audit — 2026-08-24

Sebagian besar **angka volume** di dokumen ini (1.971 baris `unified_profile`,
931 profil Instagram, 1.040 TikTok, dan seterusnya) berasal dari audit
2026-08-20/21 dan **sengaja tidak disapu ulang** supaya pernyataan historisnya
tetap utuh. Yang berubah sejak itu:

### 1. Formula engagement diselaraskan dengan definisi bisnis

Definisi yang berlaku: **`Engagement = Likes + Comments + Shares/Reposts/Quotes`**.
Save/Collect **bukan** bagian Engagement dan tetap disimpan terpisah di `saves_sum`.

| Perubahan | Berkas | Dampak |
|---|---|---|
| `saves_sum` dikeluarkan dari `engagement_sum` | `assets/gold.py` | TikTok harian 53.509.374 → **50.869.811** (−2.639.563, tepat sebesar Save) di 60/60 baris; Instagram tidak bergerak |
| Penyebut ER → follower **pada tanggal post**; Share masuk pembilang | **migration 024** — `sp_build_unified_post()` | ER L1: IG 115 → **53**, TT 90 → **55** |
| Pola yang sama diterapkan ke ER per akun | `assets/feature_engagement.py` | `*_post_analysis`: IG 82 → **37**, TT 90 → **55**. `*_engagement_analysis`: IG 11 → **9** akun, TT tetap 9 |

Cakupan ER turun karena nilai yang penyebutnya tidak diketahui kini dikosongkan,
bukan ditebak. Konsistensi lintas layer diuji: ER akun cocok dengan agregat per
post di **18 dari 18** akun.

### 2. `followers_growth` sudah terisi

Scraping profil kedua (2026-08-24) untuk 23 akun yang punya post: **22/1.994**
baris terisi — sebelumnya 0/1.971. Rincian di §14.2.

### 3. Volume terkini

| Tabel | Di dokumen (20–21 Agu) | Sekarang (24 Agu) |
|---|---:|---:|
| `l0_raw.ig_profile_apify` | 931 | 944 |
| `l0_raw.tt_profile_apify` | 1.047 | 1.057 |
| `l0_harmonization.instagram_profile` | 931 | 944 |
| `l0_harmonization.tiktok_profile` | 1.040 | 1.050 |
| `l1_silver.unified_profile` | 1.971 | 1.994 |

Volume POST tidak berubah: 221 baris `unified_post` (IG 130, TT 91), 41 post
kolaborasi, 15 like disembunyikan.

### 4. Yang TIDAK berubah

`l2_gold.kol_metric_daily` dan `kol_metric_monthly` di luar perbaikan
`engagement_sum` di atas — grain, cakupan, dan seluruh kolom lain tetap.
`post_metric` dan lima tabel L2 lain masih 0 baris; itu backlog SCRUM-514/515/517–521
yang **belum dikerjakan**, bukan cacat.

Dokumen ini menjawab, untuk setiap metric:

> Asalnya dari mana, awalnya sudah ada atau baru ditambahkan, sekarang di
> schema/tabel mana, tersedia untuk platform apa, apakah public / Insights /
> derived, dan kalau derived bagaimana formulanya?

Semua angka di dokumen ini diverifikasi langsung terhadap database, bukan
diperkirakan. Tidak ada perubahan database, migration, atau actor run yang
dilakukan saat menyusun dokumen ini (audit 2026-08-20).

**Pengecualian — pembaruan 2026-08-21.** Angka schema `feature` di dokumen ini
diperbarui setelah `migrations/014_merge_brand_fit_analysis.sql` dijalankan.
Migrasi itu menggabungkan `feature.ig_brand_fit_analysis` +
`feature.tt_brand_fit_analysis` menjadi satu tabel `feature.brand_fit_analysis`,
sehingga schema `feature` turun dari **10 tabel / 146 kolom** menjadi
**9 tabel / 135 kolom**. Seluruh angka di luar schema `feature` masih berasal
dari audit 2026-08-20 dan tidak diubah.

---

## 0. Ringkasan eksekutif

### 0.1 Peta layer

| Layer | Schema | Tabel | Status isi |
|---|---|---|---|
| L0 Raw | `l0_raw` | 20 | terisi (apify), `*_official` semua 0 baris |
| L0 Raw tambahan | `l0_extra` | 2 | 0 baris (`ig_rate_card`, `tt_rate_card`) |
| L0 Harmonization | `l0_harmonization` | 14 tabel, 15 procedure | terisi untuk profile, post, rate card |
| L1 Silver | `l1_silver` | 8 tabel, 9 procedure | terisi untuk profile, post, rate card |
| L2 Feature | `feature` | 9 tabel, **0 procedure** | **4 dari 9 terisi** — engagement 13+10, post 130+91; 5 sisanya 0 baris |
| L2 Gold | `l2_gold` | **8 tabel**, 0 procedure | 2 terisi (`kol_metric_daily` 160, `kol_metric_monthly` 53); 6 lainnya dibuat kosong (§17.13) |
| Serving | `public` | 38 | `kol_directory` 7.718 baris |

### 0.2 Tiga temuan yang menentukan isi dokumen ini

1. **Layer L2 sekarang BERJALAN — temuan ini sudah tidak berlaku lagi.**
   Ditulis saat `feature` masih 0 baris dan `l2_gold` belum ada. Kondisi
   sekarang:

   | | Dulu | Sekarang |
   |---|---|---|
   | `feature` | 9 tabel, 0 baris | 4 dari 9 terisi (13, 10, 130, 91 baris) |
   | `l2_gold` | tidak ada | **8 tabel** — `kol_metric_daily` 160, `kol_metric_monthly` 53, 6 lainnya kosong |
   | Pengisi | tidak ada | **6 asset Dagster** (4 `feature` + 2 `l2_gold`) |

   Schema `feature` dan `l2_gold` tetap **0 procedure**: perhitungannya ada di
   SQL di dalam asset Dagster, bukan di stored procedure. Jadi kalimat "tidak
   ada procedure" masih benar, tapi kesimpulannya ("tidak ada metric L2 yang
   dihitung") **tidak lagi benar**.

   Entri yang masih berstatus `L2 METRIC (planned)` di dokumen ini adalah kolom
   yang memang belum diisi — bukan seluruh layer. Dokumentasi lengkap kedua
   tabel `l2_gold` ada di **§17**.

2. **Satu-satunya formula yang benar-benar berjalan di project adalah
   `compute_engagement_rate()`** di `transform.py:71`, dan ia menulis ke
   `public.kol_directory.engagement_rate` lewat `db.py:update_profiles()` —
   jalur serving layer, bukan L2. `migrations/FEATURE_METRICS_BACKLOG.md:118`
   secara eksplisit melarang menjadikan kolom itu sumber untuk L1/feature
   karena arah layernya terbalik.

3. **`engagement_rate` NULL 100% di seluruh pipeline scraping.** Kolom
   `engagement_rate` ada di `l0_raw.ig_media_snapshots_apify`,
   `l0_raw.tt_video_apify`, kedua tabel harmonization post, dan
   `l1_silver.unified_post` — dan **0 dari 221 baris terisi** di semua layer.
   Actor tidak mengembalikannya dan tidak ada procedure yang menghitungnya.

### 0.3 Konvensi status

| Status | Arti |
|---|---|
| `EXISTING` | Kolom sudah ada sebelum migration 007. Tidak muncul di `ADD COLUMN` mana pun. |
| `ADDED` | Ditambahkan oleh migration bernomor. Nomor migration dicantumkan. |
| `DERIVED` | Dihitung di dalam pipeline dari kolom lain (bukan field mentah actor). |
| `UNAVAILABLE` | Kolom ada, tapi source tidak menyediakan datanya. Tetap NULL. |
| `L2 METRIC` | Milik layer feature. Rumah kolom ada, belum dihitung. |

Basis penentuan `EXISTING` vs `ADDED`: file di `migrations/`. Repo ini
**bukan git repository** (`git log` tidak tersedia), jadi migration file adalah
satu-satunya schema history yang otoritatif. Seluruh `ADD COLUMN` di migration
diekstrak dan dipetakan; kolom yang tidak muncul di sana = `EXISTING`.

Migration yang mengubah schema:

| Migration | Perubahan |
|---|---|
| 001, 002 | Perbaikan FK, tidak menambah kolom |
| 003–006 | Hanya procedure |
| **007** | `l0_harmonization.instagram_profile.avatar_url`, `l0_harmonization.tiktok_profile.website` |
| 008 | Hanya procedure (mengalirkan avatar/website) |
| **009** | harmonization IG+TT: `platform_user_id`, `profile_url`, `is_private`; `l1_silver.unified_profile`: `platform_user_id`, `profile_url`, `is_private`, `tier` |
| 010, 011 | Hanya procedure |
| **012** | 17 kolom post (rincian di §2) |
| 013 | Hanya procedure (mengalirkan 12 dari 17 kolom itu + fix media_type TikTok) |
| **014** | Gabung `feature.ig_brand_fit_analysis` + `feature.tt_brand_fit_analysis` → `feature.brand_fit_analysis`; schema `feature` 10→9 tabel, 146→135 kolom |

---

# 1. PROFILE

## 1.1 Volume data

| Layer | Tabel | Baris |
|---|---|---|
| L0 Raw | `l0_raw.ig_profile_apify` | 931 |
| L0 Raw | `l0_raw.tt_profile_apify` | 1.047 |
| L0 Raw | `l0_raw.ig_profile_official` | **0** |
| L0 Raw | `l0_raw.tt_profile_official` | **0** |
| L0 Harmonization | `l0_harmonization.instagram_profile` | 931 |
| L0 Harmonization | `l0_harmonization.tiktok_profile` | 1.040 |
| L1 Silver | `l1_silver.unified_profile` | **1.971** (931 IG + 1.040 TT) |
| Serving | `public.kol_directory` | 7.718 (7.494 punya `platform_id`; 224 NULL) |
| L2 Feature | `feature.ig_audience_analysis` | **0** |
| L2 Feature | `feature.tt_audience_analysis` | **0** |
| L2 Feature | `feature.ig_engagement_analysis` | **0** |
| L2 Feature | `feature.tt_engagement_analysis` | **0** |
| L2 Feature | `feature.brand_fit_analysis` | **0** |

Selisih TikTok 1.047 raw → 1.040 harmonization: 7 baris raw tidak lolos filter
`social_account_id IS NOT NULL AND username IS NOT NULL` di
`sp_sync_tiktok_profile()`.

## 1.2 Kamus field PROFILE

### L0 Raw — `l0_raw.ig_profile_apify` (14 kolom)

| Schema | Table | Column/Metric | Type | Status | Platform | Source | Description |
|---|---|---|---|---|---|---|---|
| l0_raw | ig_profile_apify | id | uuid | EXISTING | IG | generated | PK |
| l0_raw | ig_profile_apify | social_account_id | uuid | EXISTING | IG | FK `public.social_account` | Akun yang di-scrape |
| l0_raw | ig_profile_apify | fetched_at | timestamptz | EXISTING | IG | ingest | Waktu ambil |
| l0_raw | ig_profile_apify | username | varchar | EXISTING | IG | actor `username` | Handle |
| l0_raw | ig_profile_apify | name | varchar | EXISTING | IG | actor `fullName` | Nama tampilan |
| l0_raw | ig_profile_apify | biography | text | EXISTING | IG | actor `biography` | Bio |
| l0_raw | ig_profile_apify | website | text | EXISTING | IG | actor `externalUrl` | Link bio |
| l0_raw | ig_profile_apify | followers_count | integer | EXISTING | IG | actor `followersCount` | Jumlah follower |
| l0_raw | ig_profile_apify | follows_count | integer | EXISTING | IG | actor `followsCount` | Jumlah yang diikuti (**bukan** metric Insights `follows`) |
| l0_raw | ig_profile_apify | media_count | integer | EXISTING | IG | actor `postsCount` | Jumlah post |
| l0_raw | ig_profile_apify | scrape_run_id | uuid | EXISTING | IG | ingest | Batch run |
| l0_raw | ig_profile_apify | source_actor | varchar | EXISTING | IG | ingest | `apify/instagram-profile-scraper` |
| l0_raw | ig_profile_apify | raw_payload | jsonb | EXISTING | IG | actor | Payload utuh — sumber `id`, `url`, `private`, `verified`, `profilePicUrl` |
| l0_raw | ig_profile_apify | scraped_at | timestamptz | EXISTING | IG | ingest | Timestamp scrape |

### L0 Raw — `l0_raw.tt_profile_apify` (16 kolom)

| Schema | Table | Column/Metric | Type | Status | Platform | Source | Description |
|---|---|---|---|---|---|---|---|
| l0_raw | tt_profile_apify | id | uuid | EXISTING | TT | generated | PK |
| l0_raw | tt_profile_apify | social_account_id | uuid | EXISTING | TT | FK | Akun |
| l0_raw | tt_profile_apify | username | varchar | EXISTING | TT | `authorMeta.name` | Handle |
| l0_raw | tt_profile_apify | display_name | varchar | EXISTING | TT | `authorMeta.nickName` | Nama tampilan |
| l0_raw | tt_profile_apify | bio_description | text | EXISTING | TT | `authorMeta.signature` | Bio |
| l0_raw | tt_profile_apify | avatar_url | text | EXISTING | TT | `authorMeta.avatar` | Foto profil |
| l0_raw | tt_profile_apify | is_verified | boolean | EXISTING | TT | `authorMeta.verified` | Centang biru |
| l0_raw | tt_profile_apify | follower_count | integer | EXISTING | TT | `authorMeta.fans` | Follower |
| l0_raw | tt_profile_apify | following_count | integer | EXISTING | TT | `authorMeta.following` | Yang diikuti |
| l0_raw | tt_profile_apify | likes_count | bigint | EXISTING | TT | `authorMeta.heart` | Total like akun |
| l0_raw | tt_profile_apify | video_count | integer | EXISTING | TT | `authorMeta.video` | Jumlah video |
| l0_raw | tt_profile_apify | fetched_at / scraped_at | timestamptz | EXISTING | TT | ingest | Timestamp |
| l0_raw | tt_profile_apify | scrape_run_id | uuid | EXISTING | TT | ingest | Batch |
| l0_raw | tt_profile_apify | source_actor | varchar | EXISTING | TT | ingest | `clockworks/tiktok-scraper` |
| l0_raw | tt_profile_apify | raw_payload | jsonb | EXISTING | TT | actor | Payload utuh — sumber `authorMeta.id`, `profileUrl`, `privateAccount`, `bioLink` |

### L0 Harmonization — `l0_harmonization.instagram_profile` (30 kolom aktif)

| Schema | Table | Column/Metric | Type | Status | Platform | Source | Description |
|---|---|---|---|---|---|---|---|
| l0_harmonization | instagram_profile | username | varchar | EXISTING | IG | raw `username` | Handle |
| l0_harmonization | instagram_profile | name | varchar | EXISTING | IG | raw `name` | Nama tampilan |
| l0_harmonization | instagram_profile | biography | text | EXISTING | IG | raw `biography` | Bio |
| l0_harmonization | instagram_profile | website | text | EXISTING | IG | raw `website` | Link bio |
| l0_harmonization | instagram_profile | followers_count | bigint | EXISTING | IG | raw | Follower |
| l0_harmonization | instagram_profile | follows_count | bigint | EXISTING | IG | raw | Yang diikuti |
| l0_harmonization | instagram_profile | media_count | integer | EXISTING | IG | raw | Jumlah post |
| l0_harmonization | instagram_profile | **avatar_url** | text | **ADDED (007)** | IG | `raw_payload->>'profilePicUrl'` | Foto profil |
| l0_harmonization | instagram_profile | **platform_user_id** | varchar | **ADDED (009)** | IG | `raw_payload->>'id'` | ID numerik IG |
| l0_harmonization | instagram_profile | **profile_url** | text | **ADDED (009)** | IG | `raw_payload->>'url'` | URL profil |
| l0_harmonization | instagram_profile | **is_private** | boolean | **ADDED (009)** | IG | `raw_payload->>'private'` | Akun privat |
| l0_harmonization | instagram_profile | reach | bigint | UNAVAILABLE | IG | Insights only | Selalu NULL dari apify |
| l0_harmonization | instagram_profile | profile_views | bigint | UNAVAILABLE | IG | Insights only | Selalu NULL |
| l0_harmonization | instagram_profile | accounts_engaged | bigint | UNAVAILABLE | IG | Insights only | Selalu NULL |
| l0_harmonization | instagram_profile | profile_links_taps | bigint | UNAVAILABLE | IG | Insights only | Selalu NULL |
| l0_harmonization | instagram_profile | total_interactions | bigint | UNAVAILABLE | IG | Insights only | Selalu NULL |
| l0_harmonization | instagram_profile | likes / comments / shares / saves / replies / reposts | bigint | UNAVAILABLE | IG | Insights only | Metric level-akun, Insights API |
| l0_harmonization | instagram_profile | has_insights | boolean | EXISTING | IG | pipeline | `false` untuk apify, `true` untuk official |
| l0_harmonization | instagram_profile | source / source_table / source_id / processed_at | — | EXISTING | IG | pipeline | Lineage |

> Ordinal 22–25 kosong di `information_schema` → ada kolom yang pernah di-drop
> sebelum migration history dimulai. Tidak ada `DROP COLUMN` di file migration
> mana pun, jadi drop itu terjadi di luar jalur migration yang tercatat.

### L0 Harmonization — `l0_harmonization.tiktok_profile` (21 kolom aktif)

| Schema | Table | Column/Metric | Type | Status | Platform | Source | Description |
|---|---|---|---|---|---|---|---|
| l0_harmonization | tiktok_profile | username | varchar | EXISTING | TT | raw | Handle |
| l0_harmonization | tiktok_profile | display_name | varchar | EXISTING | TT | raw | Nama tampilan |
| l0_harmonization | tiktok_profile | bio_description | text | EXISTING | TT | raw | Bio |
| l0_harmonization | tiktok_profile | avatar_url | text | EXISTING | TT | raw | Foto profil |
| l0_harmonization | tiktok_profile | is_verified | boolean | EXISTING | TT | raw | Centang |
| l0_harmonization | tiktok_profile | follower_count | bigint | EXISTING | TT | raw | Follower |
| l0_harmonization | tiktok_profile | following_count | bigint | EXISTING | TT | raw | Yang diikuti |
| l0_harmonization | tiktok_profile | likes_count | bigint | EXISTING | TT | raw | Total like akun |
| l0_harmonization | tiktok_profile | video_count | integer | EXISTING | TT | raw | Jumlah video |
| l0_harmonization | tiktok_profile | open_id | varchar | EXISTING | TT | official API | 0 terisi — official 0 baris |
| l0_harmonization | tiktok_profile | **website** | text | **ADDED (007)** | TT | `authorMeta.bioLink` | Link bio |
| l0_harmonization | tiktok_profile | **platform_user_id** | varchar | **ADDED (009)** | TT | `authorMeta.id` | ID numerik TikTok |
| l0_harmonization | tiktok_profile | **profile_url** | text | **ADDED (009)** | TT | `authorMeta.profileUrl` | URL profil |
| l0_harmonization | tiktok_profile | **is_private** | boolean | **ADDED (009)** | TT | `authorMeta.privateAccount` | Akun privat |

### L1 Silver — `l1_silver.unified_profile` (37 kolom)

Terisi 1.971 baris. Kolom fill-rate diverifikasi per platform.

| Schema | Table | Column/Metric | Type | Status | Platform | Source | Description | IG terisi | TT terisi |
|---|---|---|---|---|---|---|---|---|---|
| l1_silver | unified_profile | social_account_id | uuid | EXISTING | IG+TT | harmonization | FK akun | 931 | 1040 |
| l1_silver | unified_profile | platform_id | uuid | EXISTING | IG+TT | `social_account.platform_id` | FK platform | 931 | 1040 |
| l1_silver | unified_profile | username | varchar | EXISTING | IG+TT | harmonization | Handle | 931 | 1040 |
| l1_silver | unified_profile | display_name | varchar | EXISTING | IG+TT | IG `name` / TT `display_name` | Nama | 913 | 1040 |
| l1_silver | unified_profile | bio | text | EXISTING | IG+TT | IG `biography` / TT `bio_description` | Bio | 902 | 966 |
| l1_silver | unified_profile | avatar_url | text | EXISTING (diisi sejak 008) | IG+TT | harmonization | Foto profil | 931 | 1040 |
| l1_silver | unified_profile | website | text | EXISTING (diisi sejak 008) | IG+TT | harmonization | Link bio | 668 | 488 |
| l1_silver | unified_profile | **platform_user_id** | varchar | **ADDED (009)** | IG+TT | harmonization | ID numerik platform | 931 | 1040 |
| l1_silver | unified_profile | **profile_url** | text | **ADDED (009)** | IG+TT | harmonization | URL profil | 931 | 1040 |
| l1_silver | unified_profile | **is_private** | boolean | **ADDED (009)** | IG+TT | harmonization | Akun privat | 931 | 1040 |
| l1_silver | unified_profile | **tier** | varchar(20) | **ADDED (009) — DERIVED** | IG+TT | dihitung di L1 dari `followers_count` × `public.kol_tiers` | Nano/Micro/Mid-tier/Macro/Mega | 927 | 1040 |
| l1_silver | unified_profile | is_verified | boolean | EXISTING | IG+TT | IG `raw_payload->>'verified'` / TT `authorMeta.verified` | Centang | 931 | 1040 |
| l1_silver | unified_profile | followers_count | bigint | EXISTING | IG+TT | harmonization | Follower | 927 | 1040 |
| l1_silver | unified_profile | following_count | bigint | EXISTING | IG+TT | IG `follows_count` / TT `following_count` | Yang diikuti | 927 | 1040 |
| l1_silver | unified_profile | media_count | integer | EXISTING | IG+TT | IG `media_count` / TT `video_count` | Jumlah konten | 905 | 1040 |
| l1_silver | unified_profile | likes_count | bigint | EXISTING | TT saja | TT `likes_count` | Total like akun — konsep TikTok, IG tidak punya | **0** | 1040 |
| l1_silver | unified_profile | open_id | varchar | UNAVAILABLE | TT | official API | Official 0 baris | 0 | **0** |
| l1_silver | unified_profile | reach | bigint | UNAVAILABLE | IG+TT | Insights/Analytics | Tetap NULL | 0 | 0 |
| l1_silver | unified_profile | profile_views | bigint | UNAVAILABLE | IG+TT | Insights | Tetap NULL | 0 | 0 |
| l1_silver | unified_profile | accounts_engaged | bigint | UNAVAILABLE | IG | Insights | Tetap NULL | 0 | 0 |
| l1_silver | unified_profile | profile_links_taps | bigint | UNAVAILABLE | IG | Insights | Tetap NULL | 0 | 0 |
| l1_silver | unified_profile | total_interactions | bigint | UNAVAILABLE | IG+TT | Insights | Tetap NULL | 0 | 0 |
| l1_silver | unified_profile | likes / comments / shares / saves / replies / reposts | bigint | UNAVAILABLE | IG+TT | Insights | Metric akun level-Insights | 0 | 0 |
| l1_silver | unified_profile | has_insights | boolean | EXISTING | IG+TT | pipeline | Semua `false` (apify) | 931 | 1040 |
| l1_silver | unified_profile | date / source / source_table / source_id / processed_at / created_at / updated_at | — | EXISTING | IG+TT | pipeline | Lineage | ✓ | ✓ |

### Serving — `public.kol_directory` (22 kolom, 7.718 baris)

Bukan bagian jalur L0→L1→L2, tapi **secara historis diisi oleh scraper** lewat
`db.py:update_profiles()`. Didokumentasikan karena satu-satunya tempat di
database yang punya `engagement_rate` terisi.

| Schema | Table | Column/Metric | Type | Status | Platform | Source | Description |
|---|---|---|---|---|---|---|---|
| public | kol_directory | followers_count | bigint | EXISTING | IG+TT | `db.py:update_profiles()` | Follower, ditimpa tiap scrape |
| public | kol_directory | **engagement_rate** | numeric | **DERIVED** | IG+TT | `transform.py:71 compute_engagement_rate()` | Lihat formula §5.1. IG 1.179/3.407 (34,6%), TT 575/4.087 (14,1%) |
| public | kol_directory | avatar_url / profile_url / bio / username / platform_user_id | — | EXISTING | IG+TT | `db.py` | Identitas |
| public | kol_directory | directory_status / scrape_status / refresh_tier / last_refreshed_at | — | EXISTING | IG+TT | orkestrasi | Status scraping |

> `FEATURE_METRICS_BACKLOG.md:118` — **jangan** memakai
> `public.kol_directory.engagement_rate` sebagai sumber L1/feature: arah layer
> terbalik (public = serving, bukan source), dan coverage-nya timpang.

## 1.3 Feature/L2 untuk PROFILE

Semua rumah kolom di bawah **ada tapi kosong (0 baris)**, dan **tidak ada
procedure** yang mengisinya.

| Schema | Table | Column/Metric | Type | Status | Platform | Source (rencana) | Description |
|---|---|---|---|---|---|---|---|
| feature | ig/tt_audience_analysis | audience_quality_score | integer | L2 METRIC (planned) | IG+TT | belum ditentukan | UI `k.q` |
| feature | ig/tt_audience_analysis | authenticity_score | integer | L2 METRIC (planned) | IG+TT | belum ditentukan | UI `k.auth` |
| feature | ig/tt_audience_analysis | follower_quality_score | integer | L2 METRIC (planned) | IG+TT | belum ditentukan | — |
| feature | ig/tt_audience_analysis | gender_breakdown | jsonb | L2 METRIC (planned) | IG+TT | butuh Insights audience | UI `k.gF` |
| feature | ig/tt_audience_analysis | age_gender_breakdown | jsonb | L2 METRIC (planned) | IG+TT | butuh Insights audience | UI `k.ageTop` |
| feature | ig/tt_audience_analysis | top_interest | jsonb | L2 METRIC (planned) | IG+TT | butuh Insights audience | UI `k.interests` |
| feature | ig/tt_audience_analysis | geo_distribution | jsonb | L2 METRIC (planned) | IG+TT | butuh Insights audience | UI `k.audLoc` |
| feature | ig/tt_audience_analysis | active_hours_heatmap | jsonb | L2 METRIC (planned) | IG+TT | butuh Insights | — |
| feature | ig/tt_audience_analysis | avg_reach | integer | L2 METRIC (planned) | IG+TT | `AVG(unified_post.reach)` — **BLOCKED**, reach NULL | UI `k.reach` |
| feature | ig/tt_audience_analysis | cpe | numeric | L2 METRIC (planned) | IG+TT | `fee ÷ total_engagement` | UI `k.cpe` |
| feature | ig/tt_audience_analysis | emv | numeric | L2 METRIC (planned) | IG+TT | `reach × CPM ÷ 1000 × multiplier` — konstanta CPM tidak ada di DB | UI `k.emv` |
| feature | ig_engagement_analysis | posts_analyzed_count | integer | L2 METRIC (planned) | IG | `COUNT(unified_post)` | Ukuran sampel |
| feature | tt_engagement_analysis | videos_analyzed_count | integer | L2 METRIC (planned) | TT | `COUNT(unified_post)` | Ukuran sampel |
| feature | ig/tt_engagement_analysis | total_likes / total_comments / total_shares / total_saves | bigint | L2 METRIC (planned) | IG+TT | `SUM(unified_post.*)` | Agregat |
| feature | tt_engagement_analysis | total_views | bigint | L2 METRIC (planned) | TT | `SUM(unified_post.views)` | Agregat |
| feature | ig/tt_engagement_analysis | engagement_rate | numeric | L2 METRIC (planned) | IG+TT | lihat §5 | UI `k.er` |
| feature | ig/tt_engagement_analysis | engagement_trend | jsonb | L2 METRIC (planned) | IG+TT | time-series dari `posted_at` | — |
| feature | ig/tt_engagement_analysis | best_posting_time_heatmap | jsonb | L2 METRIC (planned) | IG+TT | dari `posted_at` | — |
| feature | ig_engagement_analysis | format_performance | jsonb | L2 METRIC (planned) | IG | group by `media_type` | UI `k.format` |
| feature | ig_engagement_analysis | reel_plays | bigint | L2 METRIC (planned) | IG | `SUM(views)` untuk `media_type='clips'` | — |
| feature | ig_engagement_analysis | reel_shares / story_replies / story_exits_rate | — | UNAVAILABLE | IG | Insights only | Tidak ada dari public scraping |
| feature | brand_fit_analysis | partnership_score / sub_scores / audience_overlap_pct / category_fit_tags / recommendations / overlap_summary | — | L2 METRIC (planned) | IG+TT | butuh audience data + brand data | UI `k.aff`, `k.match` |

---

# 2. POST

## 2.1 Volume data

| Layer | Tabel | Baris | Akun unik |
|---|---|---|---|
| L0 Raw | `l0_raw.ig_media_snapshots_apify` | **130** | 13 |
| L0 Raw | `l0_raw.tt_video_apify` | **91** | 10 |
| L0 Raw | `l0_raw.ig_media_snapshots_official` | **0** | — |
| L0 Raw | `l0_raw.tt_video_official` | **0** | — |
| L0 Harmonization | `l0_harmonization.instagram_post` | **130** | 13 |
| L0 Harmonization | `l0_harmonization.tiktok_post` | **91** | 10 |
| L1 Silver | `l1_silver.unified_post` | **221** | 23 |
| L2 Feature | `feature.ig_post_analysis` | **0** | — |
| L2 Feature | `feature.tt_post_analysis` | **0** | — |
| L2 Feature | `feature.ig_comments_analysis` | **0** | — |
| L2 Feature | `feature.tt_comments_analysis` | **0** | — |

Actor: `apify/instagram-scraper` (IG), `clockworks/tiktok-scraper` (TT).
Semua di-scrape 2026-08-20 08:01:15 UTC.

> **23 akun unik = 13 Instagram + 10 TikTok**, dihitung berdasarkan
> `kol_directory.id`. **Jangan memakai username sebagai identity key** —
> `iben_ma`, `inul.d`, dan `saalhaerid` masing-masing punya akun di kedua
> platform, sehingga hitungan berbasis username menghasilkan 20, bukan 23.
> Rincian di §13.1.

## 2.2 Kamus field POST — L0 Raw

### `l0_raw.ig_media_snapshots_apify` (20 kolom, 130 baris)

| Schema | Table | Column/Metric | Type | Status | IG | TikTok | Source | Formula/Logic | Description |
|---|---|---|---|---|---|---|---|---|---|
| l0_raw | ig_media_snapshots_apify | media_id | varchar | EXISTING | ✅ 130 | — | actor `id` | direct | ID media IG |
| l0_raw | ig_media_snapshots_apify | posted_at | timestamptz | EXISTING | ✅ 130 | — | actor `timestamp` | direct | Waktu publish |
| l0_raw | ig_media_snapshots_apify | caption | text | EXISTING | ✅ 130 | — | actor `caption` | direct | Caption |
| l0_raw | ig_media_snapshots_apify | media_type | varchar | EXISTING | ✅ 130 | — | actor `productType` | direct | `feed` / `clips` / `carousel_container` |
| l0_raw | ig_media_snapshots_apify | permalink | text | EXISTING | ✅ 130 | — | actor `url` | direct | Link post |
| l0_raw | ig_media_snapshots_apify | cover_image | text | EXISTING | ✅ 130 | — | actor `displayUrl` | direct | Thumbnail |
| l0_raw | ig_media_snapshots_apify | likes | integer | EXISTING | ✅ 130 | — | actor `likesCount` | direct | **15 baris = -1**, lihat §9 |
| l0_raw | ig_media_snapshots_apify | comments | integer | EXISTING | ✅ 130 | — | actor `commentsCount` | direct | Jumlah komentar |
| l0_raw | ig_media_snapshots_apify | views | integer | EXISTING | ⚠️ 54 | — | actor `videoPlayCount` (fallback `videoViewCount`) | direct | Hanya video/clips |
| l0_raw | ig_media_snapshots_apify | video_duration | numeric | EXISTING | ⚠️ 54 | — | actor `videoDuration` | direct | Detik |
| l0_raw | ig_media_snapshots_apify | carousel_media_count | integer | EXISTING | ⚠️ 57 | — | `len(childPosts)` | derived saat ingest | Jumlah slide |
| l0_raw | ig_media_snapshots_apify | is_sponsored | boolean | EXISTING | ✅ 130 | — | actor `paidPartnership` | direct | 3 baris `true` |
| l0_raw | ig_media_snapshots_apify | engagement_rate | numeric | UNAVAILABLE | ❌ 0 | — | — | — | Actor tidak mengembalikannya |
| l0_raw | ig_media_snapshots_apify | raw_payload | jsonb | EXISTING | ✅ 130 | — | actor | — | 37 key; sumber `shortCode`, `hashtags`, `mentions`, `ownerUsername`, `ownerId`, `coauthorProducers` |
| l0_raw | ig_media_snapshots_apify | social_account_id / scrape_run_id / source_actor / scraped_at / fetched_at / id | — | EXISTING | ✅ | — | ingest | — | Lineage |

**Key `raw_payload` IG yang TIDAK dipakai** (tetap tertelusuri di L0): `alt`,
`audioUrl`, `dimensionsHeight/Width`, `originalHeight/Width`, `images`,
`videoUrl`, `inputUrl`, `firstComment`, `latestComments`, `isCommentsDisabled`,
`locationId`, `locationName`, `musicInfo`, `taggedUsers`, `ownerFullName`,
`isPinned`, `videoViewCount`, `childPosts` (detail), `coauthorProducers` (isi).

### `l0_raw.tt_video_apify` (19 kolom, 91 baris)

| Schema | Table | Column/Metric | Type | Status | IG | TikTok | Source | Formula/Logic | Description |
|---|---|---|---|---|---|---|---|---|---|
| l0_raw | tt_video_apify | video_id | varchar | EXISTING | — | ✅ 91 | actor `id` | direct | ID video |
| l0_raw | tt_video_apify | posted_at | timestamptz | EXISTING | — | ✅ 91 | actor `createTimeISO` | direct | Waktu publish |
| l0_raw | tt_video_apify | description | text | EXISTING | — | ✅ 91 | actor `text` | direct | Caption |
| l0_raw | tt_video_apify | title | text | UNAVAILABLE | — | ❌ 0 | — | — | Actor tidak mengembalikan `title` |
| l0_raw | tt_video_apify | share_url | text | EXISTING | — | ✅ 91 | actor `webVideoUrl` | direct | Link video |
| l0_raw | tt_video_apify | cover_image_url | text | EXISTING | — | ✅ 91 | `videoMeta.coverUrl` | direct | Thumbnail (URL bertanda tangan, ada `x-expires`) |
| l0_raw | tt_video_apify | duration | integer | EXISTING | — | ✅ 91 | `videoMeta.duration` | direct | Detik |
| l0_raw | tt_video_apify | like_count | bigint | EXISTING | — | ✅ 91 | actor `diggCount` | direct | Like |
| l0_raw | tt_video_apify | comment_count | bigint | EXISTING | — | ✅ 91 | actor `commentCount` | direct | Komentar |
| l0_raw | tt_video_apify | share_count | bigint | EXISTING | — | ✅ 91 | actor `shareCount` | direct | Share |
| l0_raw | tt_video_apify | view_count | bigint | EXISTING | — | ✅ 91 | actor `playCount` | direct | View |
| l0_raw | tt_video_apify | engagement_rate | numeric | UNAVAILABLE | — | ❌ 0 | — | — | Actor tidak mengembalikannya |
| l0_raw | tt_video_apify | raw_payload | jsonb | EXISTING | — | ✅ 91 | actor | — | 29 key; sumber `collectCount`, `isSponsored`, `isAd`, `hashtags`, `mentions`, `isSlideshow`, `slideshowImageLinks`, `authorMeta` |
| l0_raw | tt_video_apify | social_account_id / scrape_run_id / source_actor / scraped_at / fetched_at / id | — | EXISTING | — | ✅ | ingest | — | Lineage |

**Key `raw_payload` TikTok yang TIDAK dipakai:** `musicMeta`, `effectStickers`,
`videoMeta.subtitleLinks`, `mediaUrls`, `textLanguage`, `detailedMentions`,
`commentsDatasetUrl`, `shortDramaSeriesInfo`, `fromProfileSection`, `input`,
`isPinned`, `createTime`, `repostCount` (0 di semua baris), `authorMeta.*`
selain `id`/`name` (itu domain profile).

## 2.3 Kamus field POST — L0 Harmonization

### `l0_harmonization.instagram_post` (35 kolom)

| Schema | Table | Column/Metric | Type | Status | IG | TikTok | Source | Formula/Logic | Description |
|---|---|---|---|---|---|---|---|---|---|
| l0_harmonization | instagram_post | media_id | varchar | EXISTING | ✅ 130 | — | raw `media_id` | direct | ID media |
| l0_harmonization | instagram_post | date | date | EXISTING | ✅ 130 | — | `COALESCE(scraped_at, fetched_at, now())::date` | derived | Bagian dari conflict key |
| l0_harmonization | instagram_post | posted_at / media_type / caption / permalink / cover_image / video_duration / carousel_media_count / is_sponsored / likes / comments / views | — | EXISTING | ✅ | — | raw kolom senama | direct | — |
| l0_harmonization | instagram_post | **shortcode** | varchar(64) | **ADDED (012)** | ✅ 130 | — | `raw_payload->>'shortCode'` | `NULLIF(…,'')` | Shortcode IG |
| l0_harmonization | instagram_post | **owner_username** | varchar(255) | **ADDED (012)** | ✅ 130 | — | `raw_payload->>'ownerUsername'` | `NULLIF(…,'')` | Pemilik post (bisa ≠ akun, lihat §10) |
| l0_harmonization | instagram_post | **platform_user_id** | varchar(64) | **ADDED (012)** | ✅ 130 | — | `raw_payload->>'ownerId'` | `NULLIF(…,'')` | ID numerik pemilik |
| l0_harmonization | instagram_post | **hashtags** | text[] | **ADDED (012)** | ⚠️ 39 | — | `raw_payload->'hashtags'` | `array_agg` string non-kosong, urut ordinality | Tanpa `#` |
| l0_harmonization | instagram_post | **mentions** | text[] | **ADDED (012)** | ⚠️ 45 | — | `raw_payload->'mentions'` | `array_agg(ltrim(t,'@'))` non-kosong | Tanpa `@` |
| l0_harmonization | instagram_post | shares / reach / saved / total_interactions / reposts / follows / profile_visits / reel_avg_watch_time / reel_video_view_total_time | — | UNAVAILABLE | ❌ 0 | — | Insights only | `NULL` hardcoded di cabang apify | Tidak diisi 0 |
| l0_harmonization | instagram_post | engagement_rate | numeric | UNAVAILABLE | ❌ 0 | — | raw (kosong) | — | Tidak dihitung di layer ini |
| l0_harmonization | instagram_post | has_insights | boolean | EXISTING | ✅ 130 | — | pipeline | `false` untuk apify | Penanda sumber |

### `l0_harmonization.tiktok_post` (27 kolom)

| Schema | Table | Column/Metric | Type | Status | IG | TikTok | Source | Formula/Logic | Description |
|---|---|---|---|---|---|---|---|---|---|
| l0_harmonization | tiktok_post | video_id | varchar | EXISTING | — | ✅ 91 | raw `video_id` | direct | ID video |
| l0_harmonization | tiktok_post | date | date | EXISTING | — | ✅ 91 | `COALESCE(scraped_at, fetched_at, now())::date` | derived | Conflict key |
| l0_harmonization | tiktok_post | **media_type** | varchar | EXISTING (logic diubah 013) | — | ✅ 91 | `raw_payload->>'isSlideshow'` | `CASE WHEN isSlideshow THEN 'CAROUSEL' ELSE 'VIDEO' END` | Sebelum 013 di-hardcode `'VIDEO'`. Kini: VIDEO 89, CAROUSEL 2 |
| l0_harmonization | tiktok_post | caption | text | EXISTING | — | ✅ 91 | raw `description` | direct | Caption |
| l0_harmonization | tiktok_post | title | text | UNAVAILABLE | — | ❌ 0 | raw `title` (kosong) | direct | Actor tidak mengembalikannya |
| l0_harmonization | tiktok_post | permalink / cover_image / video_duration / likes / comments / shares / views | — | EXISTING | — | ✅ 91 | raw | direct | — |
| l0_harmonization | tiktok_post | **owner_username** | varchar(255) | **ADDED (012)** | — | ✅ 91 | `raw_payload->'authorMeta'->>'name'` | `NULLIF(…,'')` | Selalu = akun (0 mismatch) |
| l0_harmonization | tiktok_post | **platform_user_id** | varchar(64) | **ADDED (012)** | — | ✅ 91 | `raw_payload->'authorMeta'->>'id'` | `NULLIF(…,'')` | ID numerik |
| l0_harmonization | tiktok_post | **hashtags** | text[] | **ADDED (012)** | — | ⚠️ 39 | `raw_payload->'hashtags'` | `array_agg(h->>'name')` non-kosong | 58 baris punya array, 19 hanya `{"name":""}` → NULL |
| l0_harmonization | tiktok_post | **mentions** | text[] | **ADDED (012)** | — | ⚠️ 26 | `raw_payload->'mentions'` | `array_agg(ltrim(t,'@'))` | Sebagian berisi display name, bukan handle |
| l0_harmonization | tiktok_post | **saved** | bigint | **ADDED (012)** | — | ✅ 91 | `raw_payload->>'collectCount'` | `::bigint` | **Satu-satunya saves dari public scraping** |
| l0_harmonization | tiktok_post | **is_sponsored** | boolean | **ADDED (012)** | — | ✅ 91 | `isSponsored`, `isAd` | `CASE WHEN payload ? 'isSponsored' OR payload ? 'isAd' THEN COALESCE(isSponsored,false) OR COALESCE(isAd,false) END` | 8 baris `true` |
| l0_harmonization | tiktok_post | **carousel_media_count** | integer | **ADDED (012)** | — | ⚠️ 2 | `slideshowImageLinks` | `jsonb_array_length(…)` bila array | Jumlah slide |
| l0_harmonization | tiktok_post | engagement_rate | numeric | UNAVAILABLE | — | ❌ 0 | raw (kosong) | — | Tidak dihitung |

## 2.4 Kamus field POST — L1 `l1_silver.unified_post` (39 kolom, 221 baris)

| Schema | Table | Column/Metric | Type | Status | IG | TikTok | Source | Formula/Logic | Description |
|---|---|---|---|---|---|---|---|---|---|
| l1_silver | unified_post | id | uuid | EXISTING | ✅ | ✅ | `gen_random_uuid()` | — | PK |
| l1_silver | unified_post | social_account_id | uuid NOT NULL | EXISTING | ✅ 130 | ✅ 91 | harmonization | JOIN `public.social_account` | Tidak pernah dibuat baru |
| l1_silver | unified_post | platform_id | uuid NOT NULL | EXISTING | ✅ 130 | ✅ 91 | `social_account.platform_id` | direct dari JOIN | 0 mismatch |
| l1_silver | unified_post | content_id | varchar NOT NULL | EXISTING | ✅ 130 | ✅ 91 | IG `media_id` / TT `video_id` | UNION ALL | Unique bersama `social_account_id` |
| l1_silver | unified_post | date | date | EXISTING | ✅ 130 | ✅ 91 | harmonization | direct | Tanggal snapshot |
| l1_silver | unified_post | posted_at | timestamptz | EXISTING | ✅ 130 | ✅ 91 | harmonization | direct | Waktu publish |
| l1_silver | unified_post | media_type | varchar | EXISTING | ✅ 130 | ✅ 91 | harmonization | direct | IG: `carousel_container` 57 / `clips` 54 / `feed` 19. TT: `VIDEO` 89 / `CAROUSEL` 2 |
| l1_silver | unified_post | title | text | UNAVAILABLE | ❌ 0 | ❌ 0 | TT `title` | IG dipaksa `NULL::text` | Tidak ada source |
| l1_silver | unified_post | caption | text | EXISTING | ✅ 130 | ✅ 91 | harmonization | direct | Caption |
| l1_silver | unified_post | permalink | text | EXISTING | ✅ 130 | ✅ 91 | harmonization | direct | Link |
| l1_silver | unified_post | cover_image | text | EXISTING | ✅ 130 | ✅ 91 | harmonization | direct | Thumbnail |
| l1_silver | unified_post | video_duration | numeric | EXISTING | ⚠️ 54 | ✅ 91 | harmonization | direct | Detik |
| l1_silver | unified_post | carousel_media_count | integer | EXISTING (TT diisi sejak 013) | ⚠️ 57 | ⚠️ 2 | harmonization | direct | Slide count |
| l1_silver | unified_post | is_sponsored | boolean | EXISTING (TT diisi sejak 013) | ✅ 130 | ✅ 91 | harmonization | direct | IG 3 true, TT 8 true |
| l1_silver | unified_post | likes | bigint | EXISTING | ✅ 130 | ✅ 91 | harmonization | direct | **15 baris IG = -1**, §9 |
| l1_silver | unified_post | comments | bigint | EXISTING | ✅ 130 | ✅ 91 | harmonization | direct | — |
| l1_silver | unified_post | views | bigint | EXISTING | ⚠️ 54 | ✅ 91 | harmonization | direct | IG hanya `clips` |
| l1_silver | unified_post | shares | bigint | EXISTING | ❌ 0 | ✅ 91 | TT `shareCount` | direct | **IG UNAVAILABLE** |
| l1_silver | unified_post | saved | bigint | EXISTING (TT diisi sejak 013) | ❌ 0 | ✅ 91 | TT `collectCount` | direct | **IG UNAVAILABLE** |
| l1_silver | unified_post | reach | bigint | UNAVAILABLE | ❌ 0 | ❌ 0 | Insights/Analytics | — | Tetap NULL |
| l1_silver | unified_post | total_interactions | bigint | UNAVAILABLE | ❌ 0 | ❌ 0 | Insights | — | Tetap NULL |
| l1_silver | unified_post | reposts | bigint | UNAVAILABLE | ❌ 0 | ❌ 0 | Insights | — | TT `repostCount` ada tapi 0 di semua baris; tidak dipetakan |
| l1_silver | unified_post | follows | bigint | UNAVAILABLE | ❌ 0 | ❌ 0 | Insights | — | **≠ followers**, §6 |
| l1_silver | unified_post | profile_visits | bigint | UNAVAILABLE | ❌ 0 | ❌ 0 | Insights | — | Tetap NULL |
| l1_silver | unified_post | reel_avg_watch_time | numeric | UNAVAILABLE | ❌ 0 | ❌ 0 | Insights | — | Tetap NULL |
| l1_silver | unified_post | reel_video_view_total_time | bigint | UNAVAILABLE | ❌ 0 | ❌ 0 | Insights | — | Tetap NULL |
| l1_silver | unified_post | engagement_rate | numeric | UNAVAILABLE di L1 / L2 METRIC | ❌ 0 | ❌ 0 | — | **tidak dihitung di L1 — milik L2** | §5 |
| l1_silver | unified_post | has_insights | boolean | EXISTING | ✅ 130 (`false`) | ❌ 0 | pipeline | TT dipaksa `NULL::boolean` | Penanda sumber |
| l1_silver | unified_post | **username** | varchar(255) | **ADDED (012)** | ✅ 130 | ✅ 91 | harmonization `owner_username` | direct | 180 = akun, 41 kolaborasi (§10) |
| l1_silver | unified_post | **platform_user_id** | varchar(64) | **ADDED (012)** | ✅ 130 | ✅ 91 | harmonization | direct | ID numerik pemilik |
| l1_silver | unified_post | **shortcode** | varchar(64) | **ADDED (012)** | ✅ 130 | ❌ 0 | harmonization | TT dipaksa `NULL::varchar` | TikTok tidak punya konsep shortcode |
| l1_silver | unified_post | **hashtags** | text[] | **ADDED (012)** | ⚠️ 39 | ⚠️ 39 | harmonization | direct | Index GIN `ix_unified_post_hashtags` |
| l1_silver | unified_post | **mentions** | text[] | **ADDED (012)** | ⚠️ 45 | ⚠️ 26 | harmonization | direct | — |
| l1_silver | unified_post | source / source_table / source_id / processed_at / created_at / updated_at | — | EXISTING | ✅ | ✅ | pipeline | — | Lineage |

**Constraint:** `PRIMARY KEY (id)`, `UNIQUE (social_account_id, content_id)`,
FK ke `social_account` dan `platforms`.
**Index tambahan (012):** GIN `hashtags`, btree `(social_account_id, posted_at DESC)`.

## 2.5 Feature/L2 untuk POST

Semua **0 baris, 0 procedure**.

| Schema | Table | Column/Metric | Type | Status | IG | TikTok | Source (rencana) | Formula/Logic | Description |
|---|---|---|---|---|---|---|---|---|---|
| feature | ig_post_analysis | media_id | varchar | L2 METRIC (planned) | — | — | `unified_post.content_id` | join key | — |
| feature | ig/tt_post_analysis | content_category | varchar | L2 METRIC (planned) | — | — | klasifikasi caption/hashtag | belum ada | UI `c.cat` |
| feature | ig_post_analysis | category_percentage | numeric | L2 METRIC (planned) | — | — | — | belum ada | — |
| feature | ig/tt_post_analysis | top_hashtags | jsonb | L2 METRIC (planned) | — | — | **`unified_post.hashtags`** ✅ siap | agregasi | Source sudah tersedia sejak 012 |
| feature | tt_post_analysis | top_sound | jsonb | L2 METRIC (planned) | — | — | `raw_payload->'musicMeta'` (belum di-flatten) | belum ada | Perlu kolom baru bila dipakai |
| feature | ig/tt_post_analysis | avg_watch_time_seconds | numeric | UNAVAILABLE | — | — | Insights/Analytics | — | Tidak ada dari public scraping |
| feature | tt_post_analysis | completion_rate | numeric | UNAVAILABLE | — | — | TikTok Analytics | — | Tidak tersedia |
| feature | tt_post_analysis | traffic_source | jsonb | UNAVAILABLE | — | — | TikTok Analytics | — | Tidak tersedia |
| feature | ig_post_analysis | click_through_rate | numeric | UNAVAILABLE | — | — | Insights | — | Tidak tersedia |
| feature | ig_post_analysis | reach | integer | UNAVAILABLE | — | — | Insights | — | `unified_post.reach` NULL |
| feature | ig/tt_post_analysis | is_sponsored | boolean | L2 METRIC (planned) | — | — | **`unified_post.is_sponsored`** ✅ siap | direct copy | Source siap kedua platform |
| feature | ig_post_analysis | engagement_rate | numeric | L2 METRIC (planned) | — | — | `unified_post` | §5 | — |
| feature | ig_post_analysis | media_type / posted_at | — | L2 METRIC (planned) | — | — | **`unified_post`** ✅ siap | direct copy | — |
| feature | ig/tt_post_analysis | rank | integer | L2 METRIC (planned) | — | — | urut `engagement_rate` | belum ada | UI top/lowest 10 |
| feature | ig/tt_post_analysis | sentiment_breakdown | jsonb | L2 METRIC (planned) | — | — | butuh comment data (**0 baris**) + NLP | belum ada | UI `p.sent` |
| feature | ig/tt_post_analysis | ai_recommendation | text | L2 METRIC (planned) | — | — | LLM | belum ada | UI `p.ai` |
| feature | ig/tt_comments_analysis | comments_analyzed_count, sentiment_*_pct, spam_detected_pct, toxicity_pct, word_cloud, emoji_analysis, top_topics, ai_comment_summary | — | L2 METRIC (planned) | — | — | `l1_silver.unified_comment` (**0 baris**) | belum ada | UI `p.topic`, `p.sent` — BLOCKED, pipeline comment belum jalan |

---

# 3. EXISTING VS ADDED

Dihitung dari `ADD COLUMN` di `migrations/`, bukan dari tampilan schema saat ini.

## 3.1 PROFILE

| Schema | Table | Existing | Added | Derived/L2 | Unavailable |
|---|---|---:|---:|---:|---:|
| l0_raw | ig_profile_apify | 14 | 0 | 0 | 0 |
| l0_raw | tt_profile_apify | 16 | 0 | 0 | 0 |
| l0_raw | ig_profile_official | 26 | 0 | 0 | 26 *(0 baris)* |
| l0_raw | tt_profile_official | 12 | 0 | 0 | 12 *(0 baris)* |
| l0_harmonization | instagram_profile | 26 | **4** *(007: avatar_url; 009: platform_user_id, profile_url, is_private)* | 0 | 12 |
| l0_harmonization | tiktok_profile | 17 | **4** *(007: website; 009: platform_user_id, profile_url, is_private)* | 0 | 1 |
| l1_silver | unified_profile | 33 | **4** *(009: platform_user_id, profile_url, is_private, tier)* | 1 *(tier)* | 13 |
| public | kol_directory | 22 | 0 | 1 *(engagement_rate)* | 0 |
| feature | ig_audience_analysis | 0 | 0 | **15** | 5 |
| feature | tt_audience_analysis | 0 | 0 | **15** | 5 |
| feature | ig_engagement_analysis | 0 | 0 | **18** | 3 |
| feature | tt_engagement_analysis | 0 | 0 | **13** | 0 |
| feature | brand_fit_analysis | 0 | 0 | **11** | 0 |

**Total profile ADDED: 12 kolom** (4 di migration 007+009 per tabel harmonization,
4 di L1). Tidak ada kolom profile yang ditambahkan oleh pekerjaan post ini.

## 3.2 POST

| Schema | Table | Existing | Added | Derived/L2 | Unavailable |
|---|---|---:|---:|---:|---:|
| l0_raw | ig_media_snapshots_apify | 20 | 0 | 1 *(carousel_media_count saat ingest)* | 1 *(engagement_rate)* |
| l0_raw | tt_video_apify | 19 | 0 | 0 | 2 *(title, engagement_rate)* |
| l0_raw | ig_media_snapshots_official | 25 | 0 | 0 | 25 *(0 baris)* |
| l0_raw | tt_video_official | 15 | 0 | 0 | 15 *(0 baris)* |
| l0_harmonization | instagram_post | 30 | **5** *(012)* | 1 *(date)* | 10 |
| l0_harmonization | tiktok_post | 20 | **7** *(012)* | 2 *(date, media_type)* | 2 |
| l1_silver | unified_post | 34 | **5** *(012)* | 0 | 9 |
| feature | ig_post_analysis | 0 | 0 | **18** | 4 |
| feature | tt_post_analysis | 0 | 0 | **15** | 3 |
| feature | ig_comments_analysis | 0 | 0 | **15** | 0 |
| feature | tt_comments_analysis | 0 | 0 | **15** | 0 |

**Total post ADDED: 17 kolom**, semuanya oleh migration 012:

| Tabel | Kolom |
|---|---|
| `l0_harmonization.instagram_post` (5) | `shortcode`, `owner_username`, `platform_user_id`, `hashtags`, `mentions` |
| `l0_harmonization.tiktok_post` (7) | `owner_username`, `platform_user_id`, `hashtags`, `mentions`, `saved`, `is_sponsored`, `carousel_media_count` |
| `l1_silver.unified_post` (5) | `username`, `platform_user_id`, `shortcode`, `hashtags`, `mentions` |

Migration 013 **tidak menambah kolom** — hanya memperbaiki 3 procedure existing
(`sp_sync_instagram_post`, `sp_sync_tiktok_post`, `sp_build_unified_post`) agar
kolom itu terisi, plus memperbaiki `media_type` TikTok dan mengubah penjaga
`processed_at <` menjadi `<=` supaya rerun bersifat refresh idempoten.

---

# 4. RAW → L1 → L2 TRACEABILITY

Notasi: `✅` sudah mengalir, `⛔` terhenti, `○` rumah kolom ada tapi belum diisi.

## 4.1 Metric POST

### Instagram `likesCount`
```
actor apify/instagram-scraper  .likesCount
  → l0_raw.ig_media_snapshots_apify.likes            ✅ 130/130 (15 baris = -1)
  → l0_harmonization.instagram_post.likes            ✅ 130/130 (sentinel dipertahankan)
  → l1_silver.unified_post.likes                     ✅ 130/130 (sentinel dipertahankan)
  → feature.ig_engagement_analysis.total_likes       ○ 0 baris, belum ada procedure
```

### TikTok `collectCount` → saves
```
actor clockworks/tiktok-scraper .collectCount
  → l0_raw.tt_video_apify.raw_payload->>'collectCount'  ✅ 91/91
  → l0_harmonization.tiktok_post.saved                  ✅ 91/91   [ADDED 012, diisi 013]
  → l1_silver.unified_post.saved                        ✅ 91/91
  → feature.tt_engagement_analysis.total_saves          ○ belum diisi
```

### TikTok `shareCount` → shares
```
.shareCount → l0_raw.tt_video_apify.share_count       ✅ 91/91
  → l0_harmonization.tiktok_post.shares               ✅ 91/91
  → l1_silver.unified_post.shares                     ✅ 91/91
  → feature.tt_engagement_analysis.total_shares       ○
```

### Instagram shares / saved
```
actor  → tidak mengembalikan field apa pun untuk shares & saves
  → l0_raw                     ⛔ tidak ada kolom sumber
  → l0_harmonization.instagram_post.shares / .saved   ⛔ NULL hardcoded
  → l1_silver.unified_post.shares / .saved            ⛔ NULL (0/130)
  → feature.ig_engagement_analysis.total_shares/_saves ○ akan tetap kosong
```
**UNAVAILABLE dari public scraping.** Hanya bisa lewat Instagram Insights API
(butuh OAuth pemilik akun, tabel `*_official` masih 0 baris).

### comments
```
IG .commentsCount / TT .commentCount
  → l0_raw.*.comments / .comment_count               ✅ 130 / 91
  → l0_harmonization.*.comments                      ✅ 130 / 91
  → l1_silver.unified_post.comments                  ✅ 221/221
  → feature.*_engagement_analysis.total_comments     ○
```

### views
```
IG .videoPlayCount (fallback .videoViewCount) / TT .playCount
  → l0_raw.*.views / .view_count                     ⚠️ IG 54/130 (hanya clips), TT 91/91
  → l0_harmonization.*.views                         ⚠️ 54 / ✅ 91
  → l1_silver.unified_post.views                     ⚠️ 54 / ✅ 91
  → feature.tt_engagement_analysis.total_views       ○
  → feature.ig_engagement_analysis.reel_plays        ○
```
IG feed & carousel memang tidak punya view count publik.

### reach & impressions
```
actor  → tidak mengembalikan reach maupun impressions
  → l0_raw                          ⛔ tidak ada kolom (impressions tidak ada sama sekali)
  → l0_harmonization.instagram_post.reach    ⛔ NULL 0/130
  → l1_silver.unified_post.reach             ⛔ NULL 0/221
  → feature.*_audience_analysis.avg_reach    ○ BLOCKED — sumber kosong
```
**`impressions` tidak punya kolom di seluruh jalur scraping.** Yang ada hanya
`public.campaign_content_performance.impressions` dan `public.campaign_kols.impressions`
— itu data campaign yang diinput manual, bukan hasil scraping.

### follows & profile_visits
```
actor  → tidak mengembalikan
  → l0_harmonization.instagram_post.follows / .profile_visits   ⛔ NULL hardcoded
  → l1_silver.unified_post.follows / .profile_visits            ⛔ NULL 0/221
  → feature                                                     ○ tidak ada rumah kolom
```

### reposts
```
TT .repostCount ada di raw_payload tapi 0 di semua 91 baris; TIDAK dipetakan
IG  → tidak ada
  → l1_silver.unified_post.reposts   ⛔ NULL 0/221
```

### hashtags
```
IG .hashtags (array string)  /  TT .hashtags (array objek {name})
  → l0_raw.*.raw_payload                             ✅ IG 39, TT 58 (19 hanya {"name":""})
  → l0_harmonization.*.hashtags (text[])             ✅ IG 39, TT 39   [ADDED 012]
  → l1_silver.unified_post.hashtags                  ✅ IG 39, TT 39
  → feature.*_post_analysis.top_hashtags             ○ source SIAP, tinggal agregasi
```

### mentions
```
IG .mentions ('username')  /  TT .mentions ('@username')
  → l0_harmonization.*.mentions (ltrim '@')          ✅ IG 45, TT 26   [ADDED 012]
  → l1_silver.unified_post.mentions                  ✅ IG 45, TT 26
  → feature                                          ⛔ tidak ada rumah kolom
```

### sponsored
```
IG .paidPartnership  /  TT .isSponsored OR .isAd
  → l0_raw.ig_media_snapshots_apify.is_sponsored     ✅ 130/130 (3 true)
  → l0_harmonization.instagram_post.is_sponsored     ✅ 130/130
  → l0_harmonization.tiktok_post.is_sponsored        ✅ 91/91 (8 true)   [ADDED 012]
  → l1_silver.unified_post.is_sponsored              ✅ 221/221
  → feature.*_post_analysis.is_sponsored             ○ source SIAP
```

### engagement_rate (post level)
```
actor  → TIDAK mengembalikan engagement_rate
  → l0_raw.*.engagement_rate            ⛔ 0/221  (kolom ada, kosong)
  → l0_harmonization.*.engagement_rate  ⛔ 0/221
  → l1_silver.unified_post.engagement_rate ⛔ 0/221 — SENGAJA tidak dihitung di L1
  → feature.*_engagement_analysis.engagement_rate  ○ belum ada procedure
  → feature.ig_post_analysis.engagement_rate       ○ belum ada procedure
```

### growth / sentiment / topic / AI summary
```
growth          → l1_silver.unified_profile.followers_growth   ✅ kolom ada,
                  dihitung otomatis oleh sp_build_unified_profile().
                  Rumus: (followers_kini − followers_snapshot_sebelumnya)
                         ÷ followers_snapshot_sebelumnya × 100
                  Snapshot sebelumnya = baris `date` terdekat yang lebih kecil
                  untuk social_account_id yang sama. Lihat §14.
                  Terisi 22/1.994 sejak snapshot kedua 2026-08-24 (IG 13, TT 9).
sentiment       → feature.{ig,tt}_post_analysis.sentiment_breakdown  ○
                  feature.{ig,tt}_comments_analysis.sentiment_*_pct  ○
                  BLOCKED: l1_silver.unified_comment 0 baris.
topic           → feature.{ig,tt}_comments_analysis.top_topics       ○ BLOCKED sama
AI summary      → feature.{ig,tt}_post_analysis.ai_recommendation    ○
                  feature.{ig,tt}_comments_analysis.ai_comment_summary ○
posting freq    → TIDAK ADA kolom. Sumber `unified_post.posted_at` LENGKAP
                  (221/221), tapi metriknya tetap tidak bisa dihitung dengan
                  benar: scraping mengambil "10 post terakhir", bukan "semua
                  post dalam N hari". Penghambatnya STRATEGI SCRAPING, bukan
                  kolom maupun rumus. Lihat §15.
```

## 4.2 Metric PROFILE

### followers
```
IG .followersCount  /  TT authorMeta.fans
  → l0_raw.ig_profile_apify.followers_count / tt_profile_apify.follower_count  ✅ 931 / 1047
  → l0_harmonization.instagram_profile.followers_count / tiktok_profile.follower_count  ✅ 931 / 1040
  → l1_silver.unified_profile.followers_count       ✅ IG 927, TT 1040
  → public.kol_directory.followers_count            ✅ (jalur terpisah via db.py)
  → feature (denominator engagement_rate)           ○
```

### following
```
IG .followsCount  /  TT authorMeta.following
  → l0_harmonization.instagram_profile.follows_count / tiktok_profile.following_count  ✅
  → l1_silver.unified_profile.following_count       ✅ IG 927, TT 1040
  → feature                                          ⛔ tidak ada rumah kolom
```
⚠️ `follows_count` (profile: jumlah akun yang diikuti) **berbeda** dari
`follows` (post Insights: jumlah follow baru dari post). Lihat §6.

### post/video count
```
IG .postsCount  /  TT authorMeta.video
  → l1_silver.unified_profile.media_count           ✅ IG 905, TT 1040
```

### likes_count (total like akun)
```
TT authorMeta.heart → l1_silver.unified_profile.likes_count  ✅ TT 1040, IG 0
```
Konsep khusus TikTok. Instagram tidak punya padanannya.

### tier (DERIVED)
```
l1_silver.unified_profile.followers_count
  × public.kol_tiers (min_followers / max_followers)
  → l1_silver.unified_profile.tier    ✅ IG 927, TT 1040   [ADDED 009, DERIVED di L1]
```
Ambang dibaca dari `public.kol_tiers`, tidak di-hardcode. `followers_count IS NULL`
→ `tier` NULL; `followers_count < 1.000` → fallback ke tier terkecil (`Nano`),
mengikuti fungsi `TIER()` di UI.

### audience metrics (gender, age, geo, interest)
```
actor  → TIDAK mengembalikan data audience apa pun
  → l0_harmonization.instagram_audience   ⛔ 0 baris
  → l1_silver.unified_audience            ⛔ 0 baris
  → feature.*_audience_analysis.*         ○ 0 baris
```
Butuh Instagram Insights / TikTok Analytics (data audience agregat pemilik akun).

---

# 5. FORMULA L2

## 5.1 Satu-satunya formula yang benar-benar berjalan di project

**Bukan di L2.** Berada di `transform.py:71` dan menulis ke serving layer.

| L2 Metric | Source Columns | Formula | Platform | Notes |
|---|---|---|---|---|
| `public.kol_directory.engagement_rate` | `latestPosts[].likesCount`, `latestPosts[].commentsCount`, `followersCount` — **semua dari raw_payload profile scraping**, bukan dari `unified_post` | `AVG(likes + comments) ÷ followers × 100`, dibulatkan 4 desimal | IG + TT (formula sama) | Ditulis lewat `db.py:update_profiles()` |

Kode persisnya (`transform.py:71–99`):

```python
def compute_engagement_rate(item: dict) -> float | None:
    followers = _as_int(_first(item, _FOLLOWERS_KEYS))
    posts = item.get("latestPosts")
    if not followers or followers <= 0 or not isinstance(posts, list) or not posts:
        return None                       # -> None, TIDAK menimpa nilai lama di DB

    interactions = []
    for post in posts:
        likes = _as_int(post.get("likesCount")) or 0
        comments = _as_int(post.get("commentsCount")) or 0
        if likes < 0:                     # likesCount -1 = IG menyembunyikan like
            likes = 0                     # <-- diperlakukan 0, BUKAN excluded
        if likes or comments:
            interactions.append(likes + comments)

    if not interactions:
        return None
    avg = sum(interactions) / len(interactions)
    return round(avg / followers * 100, 4)
```

Jawaban atas pertanyaan spesifik yang diminta:

| Pertanyaan | Jawaban |
|---|---|
| **Formula** | `AVG(likes + comments) ÷ followers × 100` |
| **Denominator** | `followers_count` (profile), **bukan** views |
| **Treatment `likes = -1`** | Dikonversi menjadi **0**, lalu tetap ikut rata-rata bila `comments > 0` |
| **Treatment NULL** | Followers NULL/≤0 → return `None`; post tanpa `latestPosts` → `None`; `None` **tidak menimpa** nilai lama di DB (`COALESCE(v.engagement_rate, k.engagement_rate)`) |
| **Pakai followers / views / lainnya?** | **followers** |
| **IG vs TikTok berbeda?** | **Tidak** — satu fungsi dipakai untuk kedua platform |
| **Post dengan interaksi 0** | Dikeluarkan dari sampel (`if likes or comments`) |
| **Post kolaborasi** | **Tidak difilter** — engagement akun lain ikut terhitung (§10) |

⚠️ Dua catatan penting tentang formula ini:
1. Sumbernya `latestPosts` dari **profile scraping**, bukan `l1_silver.unified_post`.
   `FEATURE_METRICS_BACKLOG.md:29` menandai `latestPosts` sebagai **ditahan,
   jangan dipakai sebagai source**.
2. Perlakuan `likes = -1 → 0` **bertentangan** dengan keputusan yang diambil
   untuk pipeline post (harus diperlakukan NULL/excluded, §9).
   `FEATURE_METRICS_BACKLOG.md:137` sudah menandai ini sebagai risiko:
   "Formula menghitungnya 0 → ER akun tersebut turun tidak wajar."

## 5.2 Formula L2 yang direncanakan tapi BELUM diimplementasikan

Diambil apa adanya dari `migrations/FEATURE_METRICS_BACKLOG.md`. **Belum ada
satu pun yang jadi kode.** Tidak ada formula baru yang dibuat di dokumen ini.

| L2 Metric | Source Columns | Formula | Platform | Status | Notes |
|---|---|---|---|---|---|
| `feature.*_engagement_analysis.engagement_rate` | `unified_post.likes`, `.comments`, `.shares`, `.saved` + `unified_profile.followers_count` | `AVG(likes + comments) ÷ followers_count × 100` atas N post terakhir | IG + TT | **BLOCKED → kini UNBLOCKED** | Backlog menandai BLOCKED karena post 0 baris. Sejak 221 post masuk L1, sumbernya sudah tersedia. |
| `feature.*_audience_analysis.avg_reach` | `unified_post.reach` | `AVG(reach)` atas N post terakhir | IG + TT | **BLOCKED** | `reach` NULL 0/221. Butuh Insights API. ⚠️ Backlog:157 — `videoViewCount`/`playCount` **bukan** reach. |
| `feature.*_audience_analysis.emv` | `avg_reach` + konstanta CPM | `reach × CPM ÷ 1000 × multiplier` | IG + TT | **BLOCKED + NEED CONFIRMATION** | `avg_reach` belum ada, **dan konstanta CPM tidak ada di database** (pencarian `%cpm%`, `%benchmark%`, `%multiplier%` di 7 schema: 0 hasil). Perlu keputusan bisnis. |
| `feature.*_audience_analysis.cpe` | `l1_silver.unified_rate_card.fee` ÷ total engagement per post | `fee ÷ total_engagement` | IG + TT | **PARTIAL** | Pembilang siap: 9.210 baris rate card, `fee` 100% terisi. Penyebut kini tersedia dari `unified_post`. Dua hal perlu dikonfirmasi: `post_type` mana yang jadi basis fee, dan 14 rate card IG ber-`fee = 1.000.000.000` (sentinel/placeholder) perlu dibersihkan. |
| `feature.*_audience_analysis.authenticity_score` / `audience_quality_score` / `follower_quality_score` | belum ditentukan | **belum ada** | IG + TT | **NEED DEFINITION** | Backlog:211 — algoritma belum didefinisikan |
| `feature.brand_fit_analysis.partnership_score` | audience + brand data | **belum ada** | IG + TT | **NEED DEFINITION** | Backlog:229 |
| `feature.*_post_analysis.top_hashtags` | **`unified_post.hashtags`** | agregasi frekuensi | IG + TT | **UNBLOCKED** | Source siap sejak migration 012 |
| `avgViews` | `unified_post.views` | `AVG(views)` | IG (clips) + TT | **UNBLOCKED sebagian** | IG hanya 54/130 punya views |
| `paidRatio` | `unified_post.is_sponsored` | `COUNT(is_sponsored) ÷ COUNT(*) × 100` | IG + TT | **UNBLOCKED** | Source siap kedua platform sejak 012/013 |
| `growth` (pertumbuhan followers) | `l1_silver.unified_profile.followers_count` pada 2 `date` | `(followers_kini − followers_sebelumnya) ÷ followers_sebelumnya × 100` | IG + TT | **✅ TERISI** | Kolom `followers_growth` ada dan dihitung otomatis sejak 2026-08-21. **22/1.994 terisi** sejak snapshot kedua 2026-08-24 (IG 13, TT 9). Lihat §14.2. |
| `postFreq` | `unified_post.posted_at` — **lengkap 221/221** | `COUNT(post dalam jendela) ÷ (jendela ÷ 7)` | IG + TT | **BLOCKED — strategi scraping** | Bukan soal kolom: sampel "10 post terakhir" membuat akun aktif tersensor dari atas. Lihat §15 |
| `estReach` (UI) | `reach`, `authenticity_score`, `postFreq` | `reach × (1 + auth/400 + postFreq/40)` | IG + TT | **BLOCKED** | Formula ada di UI JavaScript; ketiga inputnya belum tersedia |
| `feature.*_comments_analysis.*` | `l1_silver.unified_comment` | NLP | IG + TT | **BLOCKED** | `unified_comment` 0 baris |

---

# 6. PUBLIC VS OFFICIAL/INSIGHTS VS DERIVED

| Metric | IG Public (apify) | IG Insights/API | TikTok Public (apify) | TikTok Analytics | Derived L2 |
|---|---|---|---|---|---|
| **Followers** | ✅ `followersCount` | ✅ | ✅ `authorMeta.fans` | ✅ | denominator ER |
| **Following** | ✅ `followsCount` | ✅ | ✅ `authorMeta.following` | ✅ | — |
| **Likes** (post) | ✅ `likesCount` *(bisa `-1`)* | ✅ | ✅ `diggCount` | ✅ | `total_likes` |
| **Comments** (post) | ✅ `commentsCount` | ✅ | ✅ `commentCount` | ✅ | `total_comments` |
| **Views** (post) | ⚠️ `videoPlayCount` — video saja | ✅ | ✅ `playCount` | ✅ | `total_views`, `avgViews` |
| **Shares** (post) | ❌ **tidak tersedia** | ✅ | ✅ `shareCount` | ✅ | `total_shares` |
| **Saves** (post) | ❌ **tidak tersedia** | ✅ | ✅ **`collectCount`** | ✅ | `total_saves` |
| **Reach** | ❌ | ✅ | ❌ | ✅ | `avg_reach`, `emv` |
| **Impressions** | ❌ | ✅ | ❌ | ✅ | — *(tidak ada kolom di pipeline)* |
| **Follows** (dari post) | ❌ | ✅ | ❌ | ✅ | — |
| **Profile Visits** | ❌ | ✅ | ❌ | ✅ | — |
| **Engagement Rate** | ❌ **bukan field actor** | ❌ | ❌ **bukan field actor** | ❌ | ✅ **selalu derived** |
| **Reposts** | ❌ | ✅ | ⚠️ `repostCount` ada tapi 0 di 91/91 baris, tidak dipetakan | ✅ | — |
| **Growth** | ❌ | ❌ | ❌ | ❌ | ✅ butuh snapshot deret waktu — **belum ada kolom** |

## Penjelasan yang wajib dipahami

**`followers` ≠ `follows`.**
`followers` / `followers_count` = jumlah akun yang mengikuti KOL (metric profile,
tersedia publik di kedua platform). `follows` = metric **Instagram Insights level
post**: berapa akun baru yang mulai mengikuti *gara-gara* post itu. Keduanya
berbeda konsep dan berbeda layer. Di database, kolom profile bernama
`followers_count`/`follower_count` sedangkan kolom post bernama `follows` —
`l1_silver.unified_post.follows` NULL 0/221 dan memang tidak akan pernah terisi
dari public scraping. Jangan menyamakan keduanya. Perhatikan juga
`instagram_profile.follows_count` = jumlah akun yang *diikuti* KOL (following),
yang lagi-lagi berbeda dari `unified_post.follows`.

**`shares` Instagram unavailable dari public scraping.**
Actor `apify/instagram-scraper` tidak mengembalikan field share sama sekali.
`l1_silver.unified_post.shares` = NULL untuk 130/130 post IG. TikTok punya
`shareCount` dan terisi 91/91.

**`saved` Instagram unavailable dari public scraping.**
Sama seperti shares. `l1_silver.unified_post.saved` = NULL untuk 130/130 post IG.
TikTok punya `collectCount` dan terisi 91/91.

**`reach` dan `impressions` membutuhkan Insights/Analytics.**
Keduanya adalah metric pemilik akun, bukan data publik. `reach` punya kolom di
harmonization dan L1 tapi NULL 0/221. `impressions` bahkan tidak punya kolom di
seluruh jalur scraping — yang ada hanya di `public.campaign_*` (input manual
campaign, bukan hasil scraping). Backlog:157 memperingatkan: **views ≠ reach** —
views adalah jumlah pemutaran (bisa berulang dari orang yang sama), reach adalah
jumlah akun unik. Jangan disamakan meski views lebih mudah didapat.

**`engagement_rate` adalah calculated metric, bukan field langsung dari actor.**
Baik `apify/instagram-scraper` maupun `clockworks/tiktok-scraper` tidak
mengembalikan engagement rate. Kolom `engagement_rate` yang ada di L0 raw,
harmonization, dan L1 adalah rumah kolom kosong — 0/221 terisi di semua layer.
Satu-satunya nilai ER yang ada di database adalah
`public.kol_directory.engagement_rate`, dihitung oleh `transform.py` (§5.1).

**TikTok `collectCount` → `saved`.**
`raw_payload->>'collectCount'` → `l0_harmonization.tiktok_post.saved` →
`l1_silver.unified_post.saved`. Terisi 91/91. Ditambahkan oleh migration 012 dan
dialirkan oleh 013 — sebelumnya `tiktok_post` tidak punya kolom `saved` sama
sekali sehingga data ini berhenti di `raw_payload`.

**TikTok `shareCount` → `shares`.**
`l0_raw.tt_video_apify.share_count` → `l0_harmonization.tiktok_post.shares` →
`l1_silver.unified_post.shares`. Terisi 91/91. Jalur ini sudah ada sejak awal.

---

# 7. PLATFORM AVAILABILITY

Layer terakhir = layer terjauh di mana metric benar-benar **punya nilai**, bukan
sekadar punya kolom.

| Metric | Instagram | TikTok | Source | Layer terakhir tersedia |
|---|---|---|---|---|
| followers_count | AVAILABLE | AVAILABLE | apify profile | `l1_silver.unified_profile` (IG 927, TT 1040) |
| following_count | AVAILABLE | AVAILABLE | apify profile | `l1_silver.unified_profile` |
| media_count / video_count | AVAILABLE | AVAILABLE | apify profile | `l1_silver.unified_profile` |
| likes_count (akun) | UNAVAILABLE | AVAILABLE | `authorMeta.heart` | `l1_silver.unified_profile` (TT 1040) |
| is_verified | AVAILABLE | AVAILABLE | raw_payload | `l1_silver.unified_profile` |
| is_private | AVAILABLE | AVAILABLE | raw_payload | `l1_silver.unified_profile` |
| avatar_url | AVAILABLE | AVAILABLE | raw_payload | `l1_silver.unified_profile` |
| website | PARTIAL (668/931) | PARTIAL (488/1040) | IG `externalUrl` / TT `bioLink` | `l1_silver.unified_profile` |
| tier | AVAILABLE (derived) | AVAILABLE (derived) | `followers_count` × `kol_tiers` | `l1_silver.unified_profile` |
| open_id | UNAVAILABLE | UNAVAILABLE | official API (0 baris) | — |
| **content_id** | AVAILABLE | AVAILABLE | actor `id` | `l1_silver.unified_post` (221) |
| **username** (post) | AVAILABLE | AVAILABLE | IG `ownerUsername` / TT `authorMeta.name` | `l1_silver.unified_post` (221) |
| **platform_user_id** (post) | AVAILABLE | AVAILABLE | IG `ownerId` / TT `authorMeta.id` | `l1_silver.unified_post` (221) |
| **shortcode** | AVAILABLE | UNAVAILABLE *(konsep tidak ada)* | IG `shortCode` | `l1_silver.unified_post` (IG 130) |
| **permalink** | AVAILABLE | AVAILABLE | IG `url` / TT `webVideoUrl` | `l1_silver.unified_post` (221) |
| **caption** | AVAILABLE | AVAILABLE | IG `caption` / TT `text` | `l1_silver.unified_post` (221) |
| **posted_at** | AVAILABLE | AVAILABLE | IG `timestamp` / TT `createTimeISO` | `l1_silver.unified_post` (221) |
| **media_type** | AVAILABLE | AVAILABLE | IG `productType` / TT `isSlideshow` | `l1_silver.unified_post` (221) |
| **cover_image** | AVAILABLE | AVAILABLE | IG `displayUrl` / TT `videoMeta.coverUrl` | `l1_silver.unified_post` (221) |
| **title** (post) | UNAVAILABLE | UNAVAILABLE | — | — |
| **likes** (post) | AVAILABLE *(15 baris `-1`)* | AVAILABLE | IG `likesCount` / TT `diggCount` | `l1_silver.unified_post` (221) |
| **comments** (post) | AVAILABLE | AVAILABLE | IG `commentsCount` / TT `commentCount` | `l1_silver.unified_post` (221) |
| **views** (post) | PARTIAL (54/130, clips saja) | AVAILABLE (91/91) | IG `videoPlayCount` / TT `playCount` | `l1_silver.unified_post` |
| **video_duration** | PARTIAL (54/130) | AVAILABLE (91/91) | actor | `l1_silver.unified_post` |
| **carousel_media_count** | PARTIAL (57/130) | PARTIAL (2/91) | IG `childPosts` / TT `slideshowImageLinks` | `l1_silver.unified_post` |
| **is_sponsored** | AVAILABLE (130/130) | AVAILABLE (91/91) | IG `paidPartnership` / TT `isSponsored\|isAd` | `l1_silver.unified_post` |
| **shares** (post) | **UNAVAILABLE** | AVAILABLE (91/91) | TT `shareCount` | `l1_silver.unified_post` (TT saja) |
| **saved** (post) | **UNAVAILABLE** | AVAILABLE (91/91) | TT `collectCount` | `l1_silver.unified_post` (TT saja) |
| **hashtags** | PARTIAL (39/130) | PARTIAL (39/91) | raw_payload | `l1_silver.unified_post` |
| **mentions** | PARTIAL (45/130) | PARTIAL (26/91) | raw_payload | `l1_silver.unified_post` |
| **reach** | UNAVAILABLE | UNAVAILABLE | Insights/Analytics | — *(kolom ada, NULL)* |
| **impressions** | UNAVAILABLE | UNAVAILABLE | Insights/Analytics | — *(tidak ada kolom)* |
| **follows** (post) | UNAVAILABLE | UNAVAILABLE | Insights | — |
| **profile_visits** | UNAVAILABLE | UNAVAILABLE | Insights | — |
| **total_interactions** | UNAVAILABLE | UNAVAILABLE | Insights | — |
| **reposts** | UNAVAILABLE | UNAVAILABLE | Insights *(TT `repostCount` 0/91)* | — |
| **reel_avg_watch_time** | UNAVAILABLE | UNAVAILABLE | Insights | — |
| **reel_video_view_total_time** | UNAVAILABLE | UNAVAILABLE | Insights | — |
| **engagement_rate** (post) | UNAVAILABLE dari source | UNAVAILABLE dari source | derived | belum ada — L2 belum jalan |
| audience demographics | UNAVAILABLE | UNAVAILABLE | Insights/Analytics | — |
| comments detail | UNAVAILABLE | UNAVAILABLE | belum di-scrape | `unified_comment` 0 baris |
| sentiment / topic / AI summary | UNAVAILABLE | UNAVAILABLE | NLP di L2 | — |
| growth | AVAILABLE | AVAILABLE | ✅ terisi | `unified_profile.followers_growth` — **22/1.994 terisi** sejak snapshot kedua 2026-08-24 (IG 13, TT 9) |

> **NULL bukan 0.** Setiap `UNAVAILABLE` di tabel ini berarti kolomnya NULL, dan
> itu disengaja. Tidak ada satu pun metric unavailable yang diisi 0 di pipeline
> ini. `0` berarti "nilainya nol", `NULL` berarti "tidak diketahui".

---

# 8. POST — CURRENT DATA STATUS

## 8.1 Volume

| | Jumlah | Akun unik |
|---|---:|---:|
| Instagram post (L0 raw = harmonization = L1) | **130** | 13 |
| TikTok video (L0 raw = harmonization = L1) | **91** | 10 |
| **`l1_silver.unified_post`** | **221** | **23** |

Integritas terverifikasi:

| Cek | Hasil |
|---|---|
| duplicate `(social_account_id, content_id)` | **0** |
| FK orphan → `public.social_account` | **0** |
| FK orphan → `public.platforms` | **0** |
| `unified_post.platform_id <> social_account.platform_id` | **0** |
| post IG memakai social account IG | **130/130** |
| post TikTok memakai social account TikTok | **91/91** |
| `public.social_account` sebelum → sesudah migration | 7.494 → **7.494** (tidak ada yang dibuat) |
| identity hash `md5(social_account_id\|platform_id\|content_id)` seluruh 221 baris | `ce26f56f4da618bccdb9bc976b2351ae` — **identik sebelum & sesudah** |

Rerun ketiga procedure setelah commit menghasilkan hitungan dan hash yang sama →
pipeline **idempoten**.

## 8.2 Field yang berhasil dipropagasikan ke L1 (hasil migration 012 + 013)

| Field | IG | TikTok | Sumber | Verifikasi |
|---|---|---|---|---|
| `username` | ✅ 130/130 | ✅ 91/91 | IG `ownerUsername` / TT `authorMeta.name` | 180 = akun, 41 kolaborasi (§10); 0 NULL |
| `platform_user_id` | ✅ 130/130 | ✅ 91/91 | IG `ownerId` / TT `authorMeta.id` | 0 NULL; cocok 100% dengan raw_payload |
| `shortcode` | ✅ 130/130 | — *(TikTok tidak punya)* | IG `shortCode` | cocok 100% dengan raw_payload |
| `hashtags` | ⚠️ 39/130 | ⚠️ 39/91 | raw_payload | Yang kosong disimpan NULL, bukan `{}` |
| `mentions` | ⚠️ 45/130 | ⚠️ 26/91 | raw_payload | Prefiks `@` dibuang agar seragam dengan IG |
| **TikTok `saved`** | — *(unavailable)* | ✅ 91/91 | `collectCount` | cocok 100%; sebelumnya kolomnya tidak ada |
| **TikTok `is_sponsored`** | — *(sudah ada)* | ✅ 91/91 | `isSponsored OR isAd` | 8 baris `true` (5 hanya `isAd`, 1 hanya `isSponsored`, 2 keduanya) |
| **TikTok `carousel_media_count`** | — *(sudah ada)* | ⚠️ 2/91 | `len(slideshowImageLinks)` | 7 slide dan 2 slide |
| **TikTok `media_type`** | — | ✅ 91/91 | `isSlideshow` | `VIDEO` 89 + `CAROUSEL` 2 (sebelumnya hardcode `VIDEO` 91) |

## 8.3 Metric yang sengaja masih NULL / unavailable

Terverifikasi **0 baris terisi** untuk masing-masing, dan itu memang benar:

| Field | IG | TikTok | Alasan |
|---|---|---|---|
| `shares` | **NULL 0/130** | terisi 91/91 | Actor IG tidak mengembalikan share |
| `saved` | **NULL 0/130** | terisi 91/91 | Actor IG tidak mengembalikan saves |
| `reach` | NULL 0/130 | NULL 0/91 | Butuh Insights/Analytics |
| impressions | *(tidak ada kolom)* | *(tidak ada kolom)* | Butuh Insights/Analytics |
| `follows` | NULL 0/130 | NULL 0/91 | Metric Insights level-post |
| `profile_visits` | NULL 0/130 | NULL 0/91 | Metric Insights |
| `reposts` | NULL 0/130 | NULL 0/91 | Insights; TT `repostCount` 0 di 91/91 |
| `total_interactions` | NULL 0/130 | NULL 0/91 | Metric Insights |
| `reel_avg_watch_time` | NULL 0/130 | NULL 0/91 | Metric Insights |
| `reel_video_view_total_time` | NULL 0/130 | NULL 0/91 | Metric Insights |
| **`engagement_rate` di L1** | NULL 0/130 | NULL 0/91 | **Sengaja** — metric L2, bukan L1. Actor juga tidak mengembalikannya. |
| `title` | NULL 0/130 | NULL 0/91 | Tidak ada di source |
| `views` (IG feed/carousel) | 76 dari 130 NULL | — | IG tidak expose view count untuk foto/carousel |

---

# 9. `likes = -1`

## 9.1 Fakta

| | |
|---|---|
| **Jumlah baris terkena** | **15** post Instagram (11,5% dari 130) |
| **Platform** | Instagram saja. TikTok: 0 baris. |
| **Layer yang menyimpan `-1`** | `l0_raw.ig_media_snapshots_apify.likes` → 15<br>`l0_harmonization.instagram_post.likes` → 15<br>`l1_silver.unified_post.likes` → 15 |
| **Arti** | Instagram menyembunyikan jumlah like pada post tersebut (fitur "hide like count"). Actor mengembalikan `likesCount: -1` sebagai sentinel "tidak diketahui", **bukan** "nol like". |
| **Sebaran per media_type** | `clips` 7, `carousel_container` 6, `feed` 2 |

## 9.2 Apakah L2 sudah menangani?

**Sudah — sejak 2026-08-21.** Sentinel ini ditangani di dua tempat:

| Layer | Cara |
|---|---|
| **L1** | `unified_post.likes_hidden` (`boolean`, 221/221) menandai `likes = -1`. Diisi migration 015 dan `sp_build_unified_post()`. |
| **Feature & L2 Gold** | Seluruh asset mengecualikan post ber-`likes_hidden` dari agregasi metrik lewat `FILTER (WHERE likes_hidden IS NOT TRUE AND is_collaboration IS NOT TRUE)`. |

Aturannya dijadikan **kolom** di L1, bukan diturunkan ulang di tiap konsumen —
satu definisi, dipakai semua. 15 post Instagram terdampak.

Catatan historis di bawah tetap dipertahankan karena `transform.py` memang masih
memakai jalur terpisah (lihat §9.4).

Satu-satunya kode di project yang menyentuh sentinel ini adalah
`transform.py:88-89`, dan **itu bukan L2** — itu jalur profile scraping menuju
`public.kol_directory`:

```python
# likesCount -1 artinya Instagram menyembunyikan jumlah like.
if likes < 0:
    likes = 0
```

Jadi pada jalur yang sudah berjalan, `-1` **diperlakukan sebagai 0**.

## 9.3 Keputusan yang berlaku untuk pipeline post

| Layer | Perlakuan |
|---|---|
| `l0_raw` | Simpan `-1` apa adanya — fakta dari source |
| `l0_harmonization` | Simpan `-1` apa adanya |
| `l1_silver` | Simpan `-1` apa adanya |
| **L2 / feature** | **Perlakukan sebagai NULL / excluded dari perhitungan metric — jangan hitung sebagai 0** |

Data tidak diubah untuk keperluan dokumentasi ini. Tidak ada `UPDATE` yang
dijalankan. Migration 012 dan 013 juga tidak menyentuh nilai `likes`.

## 9.4 ⚠️ OPEN ISSUE — inkonsistensi antar jalur

`transform.py:compute_engagement_rate()` memakai `-1 → 0`, sedangkan keputusan
untuk pipeline post adalah `-1 → NULL/excluded`. Kedua perlakuan ini
**bertentangan** dan saat ini hidup berdampingan di project yang sama:

| Jalur | Perlakuan `-1` | Menghasilkan |
|---|---|---|
| `transform.py` → `public.kol_directory.engagement_rate` | `-1 → 0` | ER akun turun tidak wajar |
| Pipeline post → `feature.*` (belum ada) | `-1 → NULL/excluded` | ER lebih akurat |

`FEATURE_METRICS_BACKLOG.md:137` sudah mencatat risikonya: *"Formula
menghitungnya 0 → ER akun tersebut turun tidak wajar."*

**Perlu keputusan** apakah `transform.py` diselaraskan dengan aturan L2 sebelum
procedure feature ditulis. Tidak diubah dalam pekerjaan ini.

---

# 10. COLLABORATION POST

## 10.1 Fakta

**41 dari 130 post Instagram (31,5%) adalah post kolaborasi.**

| | |
|---|---|
| **Owner username** | `raw_payload->>'ownerUsername'` — akun yang mem-*posting* |
| **Tracked account** | `public.social_account.username` — akun yang di-scrape |
| **Kondisi** | Pada 41 baris ini, `ownerUsername ≠ social_account.username` |
| **Verifikasi atribusi** | **41 dari 41** baris punya akun yang di-track di dalam `raw_payload->'coauthorProducers'` |
| **TikTok** | **0 mismatch** — `authorMeta.name` = `social_account.username` pada 91/91 baris |

Contoh:

| Tracked account | Owner username | Post |
|---|---|---:|
| `irwansyah_15` | `zaskiasungkar15` | 6 |
| `fadiljaidi` | `juansennnnn` | 3 |
| `isyanasarasvati` | `sarasvatistage` | 3 |
| `raffinagita1717` | `newsrans` | 2 |
| `raffinagita1717` | `rans.entertainment` | 2 |
| `lunamaya` | `bazaarindonesia` | 2 |
| `cristiano` | `voguemagazine` | 1 |
| `leomessi` | `adidasfootball` | 1 |

## 10.2 Bagaimana post itu masuk ke feed akun

Instagram punya fitur **Collab**: satu post bisa punya beberapa co-author. Post
muncul di grid/feed **semua** co-author, meski hanya satu akun yang secara teknis
menjadi `owner`. Ketika actor men-scrape profil `irwansyah_15`, post Collab yang
di-*post* oleh `zaskiasungkar15` ikut terambil karena memang tampil di profil
`irwansyah_15`.

**Atribusi di pipeline sudah benar** — post ini memang milik feed akun yang
di-track, bukan salah tarik. Sudah diverifikasi 41/41 lewat `coauthorProducers`.

## 10.3 Bagaimana L1 menyimpannya

| Kolom | Isi |
|---|---|
| `social_account_id` | akun yang **di-track** (`irwansyah_15`) — tidak berubah |
| `platform_id` | platform akun yang di-track (Instagram) — tidak berubah |
| `content_id` | `media_id` post |
| **`username`** | **`ownerUsername`** (`zaskiasungkar15`) — pemilik post, bukan akun yang di-track |
| **`platform_user_id`** | **`ownerId`** — ID numerik pemilik post |

Jadi satu baris L1 membawa kedua identitas sekaligus: `social_account_id`
menunjuk akun yang di-track, `username` menunjuk pemilik post. Post kolaborasi
bisa dideteksi dengan:

```sql
SELECT count(*)
FROM l1_silver.unified_post up
JOIN public.social_account sa ON sa.id = up.social_account_id
WHERE lower(up.username) <> lower(sa.username);
-- 41
```

Sebelum migration 012, informasi ini **tidak terlihat di L1** — hanya terkubur di
`raw_payload`. Kolom `username` dan `platform_user_id` membuatnya bisa dipakai L2
tanpa membongkar JSON.

## 10.4 ✅ SUDAH DIPUTUSKAN — post kolaborasi DIKECUALIKAN dari metrik

**Keputusan: opsi "Kecualikan post kolaborasi".** Berlaku sejak 2026-08-21 di
seluruh layer feature dan L2 Gold.

- `unified_post.is_collaboration` (`boolean`, 221/221) menandainya di L1; 41 post
  Instagram bernilai TRUE.
- Seluruh asset memfilter `is_collaboration IS NOT TRUE` saat mengagregasi
  metrik, **tapi post-nya tetap dihitung** di `post_count` / `posts_analyzed_count`.
  Itu sebabnya `kol_metric_daily` memisahkan `post_count` dari
  `posts_in_sample` — lihat §17.
- Konsekuensi yang diterima: sampel Instagram turun 130 → 82 post.

Riwayat pertimbangannya dipertahankan di bawah sebagai konteks keputusan.

### Catatan historis (sebelum keputusan)

- `transform.py:compute_engagement_rate()` — satu-satunya formula yang berjalan —
  **tidak memfilter owner**, sehingga engagement akun lain ikut terhitung.
  `FEATURE_METRICS_BACKLOG.md:137` sudah menandai ini: *"Post kolaborasi:
  `ownerUsername` ≠ pemilik profil (7,9% sampel). Formula existing tidak
  memfilter owner → engagement akun lain ikut terhitung."*
- Pada data post yang sebenarnya, proporsinya **jauh lebih tinggi dari sampel
  backlog**: 31,5% (41/130), bukan 7,9%.

Tiga opsi yang perlu diputuskan sebelum procedure feature ditulis:

| Opsi | Konsekuensi |
|---|---|
| **Sertakan semua** | ER naik tidak wajar untuk akun yang sering Collab dengan akun besar. Sampel IG tinggal 130. |
| **Kecualikan post kolaborasi** | Sampel IG turun dari 130 → 89 (−31,5%). Beberapa akun bisa kehilangan hampir semua post-nya. |
| **Beri bobot / tandai terpisah** | Paling akurat, paling rumit. Perlu definisi bobot. |

**Status: CLOSED** — diputuskan "kecualikan", diimplementasikan di L1 sebagai
kolom `is_collaboration` dan dipakai seluruh asset feature/L2 Gold.

---

# 11. FEATURE/L2 AUDIT

> Bab ini mencatat **keberadaan** objek di schema `feature` (berapa tabel,
> berapa kolom, berapa baris). Untuk **kesiapan tiap kolom** — mana yang sudah
> bisa diisi dari L1 hari ini dan mana yang masih terkunci beserta
> penghambatnya — lihat **§16**.

## 11.1 Kondisi keseluruhan

| | |
|---|---|
| Schema | `feature` |
| Tabel | 9 |
| **Procedure / function** | **0** |
| **View / materialized view** | **0** |
| **Baris data** | `ig_engagement_analysis` 13 · `tt_engagement_analysis` 10 · `ig_post_analysis` 130 · `tt_post_analysis` 91 · 5 tabel lain **0** |
| Pengisi `feature.*` | **4 asset Dagster** (`orchestration/kol_orchestration/assets/feature_*.py`) — SQL di dalam asset, bukan procedure |
| Schema `l2_gold` | **8 tabel** — 2 terisi (`kol_metric_daily` 160, `kol_metric_monthly` 53), 6 dibuat kosong migration 023 (§17.13) |

**Kesimpulan (diperbarui): scaffolding sudah sebagian terisi.** Empat tabel
`feature` dan dua tabel `l2_gold` berjalan lewat Dagster. Yang masih kosong:
`ig/tt_audience_analysis`, `ig/tt_comments_analysis`, `brand_fit_analysis` —
ketiganya menunggu sumber yang belum ada (audience, komentar, definisi brand fit).

Angka "0 baris" di §11.2–§11.6 di bawah adalah kondisi **saat audit ditulis**;
untuk kesiapan kolom terkini lihat §16, dan untuk L2 Gold lihat §17.

## 11.2 Existing L2 metrics

Metric yang **sudah ada sebelum** pekerjaan post ini — dalam arti kolomnya sudah
ada di database sebelum migration 012:

Seluruh **135 kolom** di 9 tabel `feature` sudah ada sebelumnya. **Tidak ada
satu pun yang terisi**, dan tidak satu pun ditambahkan atau diubah oleh
migration 007–013.

> Angka di bawah adalah kondisi setelah migration 014. Sebelum 014 jumlahnya
> 146 kolom di 10 tabel; migrasi itu tidak menambah atau mengubah kolom mana pun,
> hanya menghapus 11 kolom duplikat dengan menggabungkan `ig_brand_fit_analysis`
> dan `tt_brand_fit_analysis` yang strukturnya identik.

| Tabel | Kolom | Baris |
|---|---:|---:|
| `feature.ig_audience_analysis` | 15 | 0 |
| `feature.tt_audience_analysis` | 15 | 0 |
| `feature.ig_engagement_analysis` | 18 | 0 |
| `feature.tt_engagement_analysis` | 13 | 0 |
| `feature.ig_post_analysis` | 18 | 0 |
| `feature.tt_post_analysis` | 15 | 0 |
| `feature.ig_comments_analysis` | 15 | 0 |
| `feature.tt_comments_analysis` | 15 | 0 |
| `feature.brand_fit_analysis` | 11 | 0 |
| **Total** | **135** | **0** |

## 11.3 New L2 metrics

**Tidak ada.** Pekerjaan post (migration 012 + 013) tidak menambah kolom,
tabel, procedure, atau metric apa pun di schema `feature`. Seluruh 17 kolom yang
ditambahkan berada di `l0_harmonization` dan `l1_silver`.

Yang berubah adalah **ketersediaan source** untuk metric L2 yang tadinya BLOCKED:

| Metric L2 | Status sebelum | Status sesudah | Yang membukanya |
|---|---|---|---|
| `*_engagement_analysis.engagement_rate` | BLOCKED (post 0 baris) | **source siap** | 221 post di L1 |
| `*_engagement_analysis.total_likes/comments` | BLOCKED | **source siap** | 221 post |
| `tt_engagement_analysis.total_shares` | BLOCKED | **source siap** | `unified_post.shares` TT 91 |
| `tt_engagement_analysis.total_saves` | BLOCKED | **source siap** | `unified_post.saved` TT 91 — **kolomnya baru ada sejak 012** |
| `tt_engagement_analysis.total_views` | BLOCKED | **source siap** | `unified_post.views` TT 91 |
| `*_post_analysis.top_hashtags` | BLOCKED | **source siap** | `unified_post.hashtags` — **kolom baru sejak 012** |
| `*_post_analysis.is_sponsored` | BLOCKED (TT NULL) | **source siap** | TT `is_sponsored` — **baru terisi sejak 013** |
| `ig_engagement_analysis.reel_plays` | BLOCKED | **source siap** | `views` untuk `media_type='clips'` (54) |
| `ig_engagement_analysis.format_performance` | BLOCKED | **source siap** | `media_type` |
| `*_engagement_analysis.best_posting_time_heatmap` | BLOCKED | **source siap** | `posted_at` |
| `paidRatio` | BLOCKED | **source siap** | `is_sponsored` kedua platform |
| `*_audience_analysis.cpe` | PARTIAL | **penyebut siap** | engagement per post dari L1 |
| `*_audience_analysis.avg_reach` | BLOCKED | **tetap BLOCKED** | `reach` NULL 0/221 |
| `*_audience_analysis.emv` | BLOCKED | **tetap BLOCKED** | butuh `avg_reach` + konstanta CPM |
| `*_comments_analysis.*` | BLOCKED | **tetap BLOCKED** | `unified_comment` 0 baris |
| `*_audience_analysis` demografi | BLOCKED | **tetap BLOCKED** | butuh Insights audience |

## 11.4 Profile-derived L2 metrics

Metric L2 yang sumbernya dari profile:

| Metric | Tabel | Source | Formula | Status |
|---|---|---|---|---|
| `audience_quality_score` | `{ig,tt}_audience_analysis` | belum ditentukan | belum ada | NEED DEFINITION |
| `authenticity_score` | `{ig,tt}_audience_analysis` | belum ditentukan | belum ada | NEED DEFINITION |
| `follower_quality_score` | `{ig,tt}_audience_analysis` | belum ditentukan | belum ada | NEED DEFINITION |
| `gender_breakdown` | `{ig,tt}_audience_analysis` | Insights audience | — | UNAVAILABLE |
| `age_gender_breakdown` | `{ig,tt}_audience_analysis` | Insights audience | — | UNAVAILABLE |
| `top_interest` | `{ig,tt}_audience_analysis` | Insights audience | — | UNAVAILABLE |
| `geo_distribution` | `{ig,tt}_audience_analysis` | Insights audience | — | UNAVAILABLE |
| `active_hours_heatmap` | `{ig,tt}_audience_analysis` | Insights | — | UNAVAILABLE |
| **denominator ER** | `{ig,tt}_engagement_analysis.engagement_rate` | `unified_profile.followers_count` | `÷ followers × 100` | source SIAP |
| `tier` *(sudah di L1)* | `unified_profile.tier` | `followers_count` × `kol_tiers` | klasifikasi ambang | ✅ **sudah terisi di L1** |

## 11.5 Post-derived L2 metrics

| Metric | Tabel | Source (L1) | Formula | Status |
|---|---|---|---|---|
| `posts_analyzed_count` | `ig_engagement_analysis` | `COUNT(unified_post)` | agregasi | source SIAP |
| `videos_analyzed_count` | `tt_engagement_analysis` | `COUNT(unified_post)` | agregasi | source SIAP |
| `total_likes` | `{ig,tt}_engagement_analysis` | `SUM(unified_post.likes)` | agregasi | source SIAP ⚠️ perlu handle `-1` |
| `total_comments` | `{ig,tt}_engagement_analysis` | `SUM(unified_post.comments)` | agregasi | source SIAP |
| `total_shares` | `{ig,tt}_engagement_analysis` | `SUM(unified_post.shares)` | agregasi | TT SIAP, **IG UNAVAILABLE** |
| `total_saves` | `{ig,tt}_engagement_analysis` | `SUM(unified_post.saved)` | agregasi | TT SIAP, **IG UNAVAILABLE** |
| `total_views` | `tt_engagement_analysis` | `SUM(unified_post.views)` | agregasi | TT SIAP |
| `engagement_rate` | `{ig,tt}_engagement_analysis` | `unified_post` + `unified_profile.followers_count` | `AVG(likes+comments) ÷ followers × 100` | source SIAP |
| `engagement_trend` | `{ig,tt}_engagement_analysis` | `unified_post.posted_at` + metric | time-series | source SIAP |
| `best_posting_time_heatmap` | `{ig,tt}_engagement_analysis` | `unified_post.posted_at` | histogram jam×hari | source SIAP |
| `format_performance` | `ig_engagement_analysis` | `unified_post.media_type` | group by | source SIAP |
| `reel_plays` | `ig_engagement_analysis` | `SUM(views) WHERE media_type='clips'` | agregasi | source SIAP (54 post) |
| `reel_shares` | `ig_engagement_analysis` | — | — | **UNAVAILABLE** |
| `story_replies`, `story_exits_rate` | `ig_engagement_analysis` | `unified_story` (0 baris) | — | **BLOCKED** |
| `top_hashtags` | `{ig,tt}_post_analysis` | **`unified_post.hashtags`** | frekuensi | source SIAP *(kolom baru 012)* |
| `is_sponsored` | `{ig,tt}_post_analysis` | `unified_post.is_sponsored` | copy | source SIAP |
| `media_type`, `posted_at`, `engagement_rate` | `ig_post_analysis` | `unified_post` | copy / hitung | source SIAP |
| `rank` | `{ig,tt}_post_analysis` | urut `engagement_rate` | ranking | tergantung ER |
| `content_category`, `category_percentage` | `{ig,tt}_post_analysis` | klasifikasi caption/hashtag | belum ada | NEED DEFINITION |
| `top_sound` | `tt_post_analysis` | `raw_payload->'musicMeta'` | — | **belum di-flatten ke L1** |
| `avg_watch_time_seconds` | `{ig,tt}_post_analysis` | Insights | — | **UNAVAILABLE** |
| `completion_rate`, `traffic_source` | `tt_post_analysis` | TikTok Analytics | — | **UNAVAILABLE** |
| `click_through_rate`, `reach` | `ig_post_analysis` | Insights | — | **UNAVAILABLE** |
| `sentiment_breakdown`, `ai_recommendation` | `{ig,tt}_post_analysis` | NLP/LLM | belum ada | **BLOCKED** (butuh comment) |
| seluruh `{ig,tt}_comments_analysis` | — | `unified_comment` (0 baris) | — | **BLOCKED** |

## 11.6 Cross-platform metrics

**Tidak ada tabel feature yang menggabungkan Instagram + TikTok.** Seluruh 10
tabel dipisah dengan prefiks `ig_` / `tt_`.

Penggabungan lintas platform terjadi lebih awal, di **L1**:

| Tabel L1 | Menggabungkan | Kunci penyatuan |
|---|---|---|
| `l1_silver.unified_post` | `instagram_post` + `tiktok_post` | `UNION ALL` → `content_id`, dibedakan `platform_id` |
| `l1_silver.unified_profile` | `instagram_profile` + `tiktok_profile` | idem |
| `l1_silver.unified_rate_card` | IG + TT rate card | idem |

Aturan penyatuan yang dipakai (terlihat di `sp_build_unified_post`): kolom
disatukan hanya bila **maknanya identik** di kedua platform. Yang khas satu
platform diisi `NULL` untuk platform lain — contoh `shortcode` (IG saja),
`likes_count` akun (TT saja), `carousel_media_count` (IG `childPosts` vs TT
`slideshowImageLinks`).

Metric lintas platform yang dibutuhkan UI tapi **belum punya rumah kolom di
mana pun**: `postFreq`, `estReach`, `paidRatio`.

`growth` **sudah punya rumah** sejak 2026-08-21:
`l1_silver.unified_profile.followers_growth`, dihitung otomatis oleh
`sp_build_unified_profile()`. Lihat §14.

---

# 12. FINAL SUMMARY

## 12.1 PROFILE

| Kategori | Jumlah | Rincian |
|---|---:|---|
| **Existing metrics** | ~33 di L1 | `username`, `display_name`, `bio`, `avatar_url`, `website`, `followers_count`, `following_count`, `media_count`, `likes_count` (TT), `is_verified`, `date`, lineage, dll. Sudah ada sebelum migration 007. |
| **Added metrics** | **12** | **007** (2): `instagram_profile.avatar_url`, `tiktok_profile.website`.<br>**009** (10): `platform_user_id`, `profile_url`, `is_private` × 2 tabel harmonization + `platform_user_id`, `profile_url`, `is_private`, `tier` di `unified_profile`. |
| **Derived metrics** | **2** | `unified_profile.tier` (L1, dari `followers_count` × `kol_tiers`) — **terisi**.<br>`public.kol_directory.engagement_rate` (serving, dari `transform.py`) — terisi IG 34,6% / TT 14,1%. |
| **L2 metrics** | **83** kolom di 6 tabel feature profile | Semua **0 baris, 0 procedure**. |
| **Unavailable metrics** | 13 di `unified_profile` | `reach`, `profile_views`, `accounts_engaged`, `profile_links_taps`, `total_interactions`, `likes`, `comments`, `shares`, `saves`, `replies`, `reposts`, `open_id`, + seluruh demografi audience. Butuh Insights/Analytics. |

**Volume:** 1.971 baris di `l1_silver.unified_profile` (931 IG + 1.040 TT).

## 12.2 POST

| Kategori | Jumlah | Rincian |
|---|---:|---|
| **Existing metrics** | 34 di `unified_post` | `content_id`, `posted_at`, `date`, `media_type`, `caption`, `permalink`, `cover_image`, `video_duration`, `carousel_media_count`, `is_sponsored`, `likes`, `comments`, `views`, `shares`, `has_insights`, lineage, dll. |
| **Added metrics** | **17** *(semua migration 012)* | harmonization IG (5): `shortcode`, `owner_username`, `platform_user_id`, `hashtags`, `mentions`.<br>harmonization TT (7): `owner_username`, `platform_user_id`, `hashtags`, `mentions`, `saved`, `is_sponsored`, `carousel_media_count`.<br>L1 (5): `username`, `platform_user_id`, `shortcode`, `hashtags`, `mentions`. |
| **Derived metrics** | **3** | `harmonization.*.date` (`COALESCE(scraped_at, fetched_at, now())::date`), `tiktok_post.media_type` (`isSlideshow → CAROUSEL/VIDEO`, sejak 013), `ig raw carousel_media_count` (`len(childPosts)` saat ingest). |
| **L2 metrics** | **63** kolom di 4 tabel feature post | Semua **0 baris, 0 procedure**. |
| **Unavailable metrics** | 9 di `unified_post` + 2 IG-only | `reach`, `total_interactions`, `reposts`, `follows`, `profile_visits`, `reel_avg_watch_time`, `reel_video_view_total_time`, `engagement_rate`, `title`; plus `shares` & `saved` untuk Instagram. `impressions` bahkan tidak punya kolom. |

**Volume:** 221 baris di `l1_silver.unified_post` (130 IG + 91 TT, 23 akun).
Duplicate 0, FK orphan 0, platform mismatch 0.

## 12.3 FEATURE / L2

| Aspek | Kondisi |
|---|---|
| **Existing metrics** | **135 kolom** di 9 tabel — semua sudah ada sebelum pekerjaan post |
| **Added metrics** | **0** — tidak ada kolom, tabel, atau procedure feature yang ditambahkan |
| **Baris data** | **0** di seluruh 9 tabel |
| **Procedure** | **0** — tidak ada satu pun function/procedure/view di schema `feature` |
| **Formula terimplementasi** | **0 di L2.** Satu-satunya formula yang berjalan di project adalah `transform.py:compute_engagement_rate()` yang menulis ke `public.kol_directory` (serving layer, bukan L2) |
| **Source layer** | `l1_silver.unified_post` (221 baris) dan `l1_silver.unified_profile` (1.971 baris) — keduanya siap dikonsumsi |
| **Platform availability** | Metric agregat dasar siap untuk kedua platform. `total_shares` & `total_saves` hanya TikTok. `avg_reach`, `emv`, demografi audience, dan seluruh comments analysis tetap BLOCKED. |

### Metric L2 yang sekarang UNBLOCKED oleh pekerjaan post

11 metric: `engagement_rate`, `total_likes`, `total_comments`, `total_shares` (TT),
`total_saves` (TT), `total_views` (TT), `top_hashtags`, `is_sponsored`,
`reel_plays`, `format_performance`, `best_posting_time_heatmap`, `paidRatio`,
dan penyebut `cpe`.

### Metric L2 yang tetap BLOCKED

`avg_reach` & `emv` (butuh `reach` dari Insights + konstanta CPM yang tidak ada
di DB), seluruh `*_comments_analysis` (butuh `unified_comment`, 0 baris),
demografi audience (butuh Insights), `growth` & `postFreq` (belum punya rumah
kolom di schema mana pun).

## 12.4 OPEN ISSUES

| # | Isu | Ref |
|---|---|---|
| 1 | **`likes = -1`**: `transform.py` memakai `-1 → 0`, keputusan pipeline post memakai `-1 → NULL/excluded`. Dua perlakuan bertentangan hidup berdampingan. Perlu diselaraskan sebelum procedure feature ditulis. | §9.4 |
| 2 | **Post kolaborasi**: 41/130 post IG (31,5%). Belum ada keputusan apakah L2 memasukkan, mengecualikan, atau memberi bobot. Formula existing tidak memfilter owner. | §10.4 |
| 3 | **Konstanta CPM untuk `emv` tidak ada di database.** Pencarian `%cpm%`, `%benchmark%`, `%multiplier%`, `%coefficient%`, `%formula%` di 7 schema: 0 hasil. Perlu keputusan bisnis. | §5.2 |
| 4 | **`post_type` basis fee untuk `cpe` belum ditentukan**, dan 14 rate card IG ber-`fee = 1.000.000.000` (sentinel) perlu dibersihkan. | §5.2 |
| 5 | **`postFreq` terhambat strategi scraping, bukan kolom.** Sampel "10 post terakhir" menyensor akun aktif dari atas; 3/13 akun IG dan 5/10 TT sudah tersensor pada jendela 30 hari. Perlu scraping berbasis rentang tanggal. | §15 |
| 6 | **`cover_image` TikTok adalah URL CDN bertanda tangan** dengan `x-expires`. Akan mati sendiri. Perlu strategi re-fetch atau mirror. | §2.2 |
| 7 | **`media_type` belum dinormalisasi ke label UI.** L1 menyimpan nilai platform (`carousel_container`/`clips`/`feed`/`VIDEO`/`CAROUSEL`), UI memakai `Reel`/`Carousel`/`Image`/`Story`/`TikTok Video`. Pemetaan lebih tepat di serving layer. | §2.4 |
| 8 | **Ordinal gap** di `instagram_profile` (22–25) dan `tiktok_profile` (14) menandakan ada kolom yang di-drop di luar jalur migration yang tercatat. | §1.2 |
| 9 | **`inul.d` TikTok kemungkinan besar bukan Inul Daratista** — identity mismatch di roster/`kol_directory`, bukan error pipeline. Perlu verifikasi source sebelum dipakai untuk metric apa pun. | §13.2 |
| 10 | **Kegagalan scrape post belum punya error log tersendiri di database.** `bbrightvc` gagal `not_found` pada scrape post 2026-08-20, tapi satu-satunya jejak di DB adalah `kol_directory.scrape_status='failed'` yang berasal dari scrape **profil** 2026-08-14. | §13.3 |
| 11 | **Username bukan identity key.** Tiga username (`iben_ma`, `inul.d`, `saalhaerid`) ada di kedua platform dengan `kol_directory.id` berbeda; agregasi berbasis username menghilangkan sisi TikTok-nya. | §13.1 |

---

# 13. DATA QUALITY / KNOWN ISSUES — LEVEL AKUN

Hasil audit penelusuran akun **2026-08-21**. Seluruh angka diverifikasi langsung
ke database dan dibandingkan baris-per-baris dengan file hasil scraping
(`output/ig_posts_20260820T075621Z.jsonl`, `output/tt_videos_20260820T075904Z.jsonl`).
Tidak ada perubahan database yang dilakukan saat audit ini.

## 13.1 Angka final audit akun

| Metrik | Nilai |
|---|---:|
| Akun Instagram unik sampai L1 | **13** |
| Akun TikTok unik sampai L1 | **10** |
| **Total akun unik** | **23** |
| Post Instagram di L1 | **130** |
| Post TikTok di L1 | **91** |
| **Total post di L1** | **221** |

Akun unik dihitung berdasarkan **`kol_directory.id`**. Menghitung dengan
`social_account.id` memberi angka yang sama (23) — keduanya sah.

### ⚠️ Username BUKAN identity key

Tiga username muncul di **kedua** platform dengan `kol_directory.id` berbeda:

| Username | `kol_directory.id` Instagram | `kol_directory.id` TikTok |
|---|---|---|
| `iben_ma` | `de7b3261-7d29-45c2-bd45-afb68a980420` | `3f8232fc-ac7f-447f-b0ec-5cee130ee3c6` |
| `inul.d` | `e8658a17-1a19-47cc-af37-cd77b51a5683` | `740a0e98-6283-4053-81ab-484173df7bd6` |
| `saalhaerid` | `6ce42ec0-2a7c-4642-8a3d-f445d1fe7e2b` | `9af7e5b8-8967-46ea-9ace-7f84b7e879ca` |

Agregasi berbasis username membuat 23 akun runtuh menjadi **20**, dan sisi
TikTok dari ketiga username itu tampak "hilang" padahal datanya **lengkap di L0
maupun L1**. Ketiganya tidak boleh dihapus atau digabung — mapping-nya sudah
benar per `kol_directory.id` + platform.

## 13.2 `inul.d` TikTok — identity mismatch di source/roster

| | |
|---|---|
| `kol_directory.id` | **`740a0e98-6283-4053-81ab-484173df7bd6`** |
| Platform | TikTok |
| Status data | ✅ L0 1 video → L0h 1 → L1 1 post. **Pipeline bersih** |
| Klasifikasi | **Data-quality issue di source/roster**, BUKAN error L0→L1 |
| Tindakan | **Jangan ubah/hapus.** Perlu verifikasi source lebih dulu |

Akun TikTok `@inul.d` hasil scraping **hampir pasti bukan Inul Daratista**.
Bukti dari `l0_raw.tt_video_apify.raw_payload->'authorMeta'`:

| Field | Nilai |
|---|---|
| `authorMeta.id` | `6780898295374136321` |
| `authorMeta.name` | `inul.d` |
| `authorMeta.nickName` | `user34976328345` — nickname default, tidak pernah diubah |
| `authorMeta.fans` | **1.201** |
| `authorMeta.heart` | **22** total like seumur akun |
| `authorMeta.video` | 1 |
| `authorMeta.verified` | `false` |
| `authorMeta.signature` | `"No bio yet"` — placeholder default |
| URL | `https://www.tiktok.com/@inul.d/video/6930552342521597186` |
| Tanggal post | 2021-02-18 |

Bandingkan: `inul.d` **Instagram** (`e8658a17-1a19-47cc-af37-cd77b51a5683`) punya
**±20 juta followers** (`followers_count` = 20.046.665).

**Kesimpulan.** Database merepresentasikan hasil scraping dengan benar — handle
`@inul.d` di TikTok memang akun ini. Kesalahannya ada di **hulu**: roster
(`kol_directory.source = 'excel_import'`) mengasumsikan handle TikTok tersebut
milik Inul Daratista. Ini **identity mismatch di source**, bukan kegagalan
pipeline L0→L1.

Catatan tambahan: akun ini adalah **satu-satunya** di seluruh database yang punya
data video tapi **tidak punya baris profil** (`l0_raw.tt_profile_apify` = 0,
`l1_silver.unified_profile` = 0). `kol_directory.followers_count` = 1.256
berasal dari `excel_import`, bukan dari scraping profil — yang memang tidak
pernah dijalankan untuk akun ini.

## 13.3 `bbrightvc` — berhenti di tahap scraping

| | |
|---|---|
| `kol_directory.id` | **`de2ea37e-11c1-4da3-8fd9-181196c41fba`** |
| Platform | Instagram |
| `kol_directory.scrape_status` | **`failed`** |
| Error dari actor | `{"error": "not_found", "errorDescription": "Post does not exist"}` |
| Tahap berhenti | **L0 ingestion / scraping** |

Jejak di seluruh layer — semuanya **0 baris**, dan itu **memang benar**:

```
kol_directory                        ada (scrape_status='failed')
      |
l0_raw.ig_profile_apify              0 baris   <- berhenti di sini
l0_raw.ig_media_snapshots_apify      0 baris
l0_harmonization.instagram_profile   0 baris
l0_harmonization.instagram_post      0 baris
l1_silver.unified_profile            0 baris
l1_silver.unified_post               0 baris
```

Actor mengembalikan `not_found`, jadi tidak pernah ada baris L0 yang bisa
mengalir ke harmonisasi maupun L1. **Akun ini memang tidak boleh muncul di L1** —
kondisi sekarang sudah benar dan tidak perlu diperbaiki.

### ⚠️ Kegagalan scrape post belum punya error log di database

Satu-satunya jejak kegagalan yang tersimpan adalah
`kol_directory.scrape_status = 'failed'` (satu dari **72** akun berstatus itu;
928 `success`, 6.718 `NULL`) — dan nilai itu berasal dari scrape **profil**
2026-08-14, bukan dari scrape **post** 2026-08-20. Kegagalan scrape post
20 Agustus **tidak tercatat sama sekali di database**; buktinya hanya ada di file
JSONL di disk yang tidak ter-versioning.

Konsekuensinya: dari database saja, tidak mungkin membedakan akun yang **gagal**
di-scrape post dari akun yang **belum pernah dicoba**. Dari 931 akun Instagram di
`unified_profile`, hanya **13** yang punya post; status 918 sisanya tidak
diketahui.

## 13.4 Status integritas L0 → L1: bersih

Diverifikasi 2026-08-21, tidak ada ketidaksesuaian yang ditemukan:

| Yang diuji | Hasil |
|---|---|
| L0 vs file hasil scraping (130 IG + 91 TT, per baris) | **0 selisih** — tidak ada item hilang, ekstra, atau nilai berbeda |
| Jumlah baris L0 → harmonization → L1, per akun | **Identik di ketiga layer** untuk semua 23 akun |
| Kesetiaan nilai L0 → L1 (9 kolom IG, 8 kolom TT, termasuk `source_id`) | **0 beda** dari 221 baris |
| Konsistensi `platform_id` lintas `kol_directory` / `kol_social_account` / `social_account` / `unified_post` | **0 mismatch** dari 23 akun |
| Konsistensi `username` antara `kol_directory` dan `social_account` | **0 mismatch** |

Tidak ada `UPDATE`/`DELETE`/`INSERT` yang diperlukan maupun dijalankan.

### Temuan sistemik yang sengaja TIDAK diperbaiki

Ketiganya berlaku untuk seluruh database, bukan khusus 23 akun ini, sehingga
memperbaiki sebagian justru menciptakan inkonsistensi:

| Tabel / kolom | Kondisi | Kenapa dibiarkan |
|---|---|---|
| `public.social_account.platform_user_id` | NULL di **7.494 dari 7.494** baris | Sistemik, bukan khusus 23 akun ini |
| `public.kol_directory.platform_user_id` (TikTok) | NULL di **4.087 dari 4.087** baris TikTok | Pipeline profil TikTok memang tidak pernah menulis kolom ini |
| `public.kol_directory.followers_count` untuk `inul.d` TikTok | 1.256 (dari `excel_import`) vs `authorMeta.fans` 1.201 | Tidak ada jalur di pipeline yang memakai `authorMeta` video untuk meng-update `followers_count`. Menerapkannya untuk 1 akun = membuat aturan baru |

---

# 14. KOLOM METRIK DI LAYER L1

Sejak **2026-08-21**, sebagian metrik turunan dihitung dan disimpan langsung di
`l1_silver`, bukan menunggu layer `feature`. Yang masuk ke sini hanya metrik
**row-level** — yang bisa diturunkan dari kolom di baris yang sama plus lookup,
sesuai grain tabelnya. Metrik agregat lintas baris tetap milik layer `feature`.

Preseden pola ini sudah ada sebelumnya: `unified_profile.tier`, turunan
`followers_count`, sudah lama hidup di L1.

**Tidak ada tabel, function, atau procedure baru yang dibuat** untuk seluruh
pekerjaan ini. Yang ada hanya kolom tambahan dan perubahan pada dua function
`sp_build_*` yang sudah ada.

## 14.1 Daftar kolom

| Tabel | Kolom | Tipe | Terisi | Diisi oleh |
|---|---|---|---|---|
| `unified_post` | `likes_hidden` | `boolean` | **221/221** | migrasi + `sp_build_unified_post()` |
| `unified_post` | `is_collaboration` | `boolean` | **221/221** | idem |
| `unified_post` | `engagement_rate` | `numeric` | **205/221** | idem *(kolom sudah ada sebelumnya, 0/221)* |
| `unified_profile` | **`followers_growth`** | `numeric` | **22/1.994** | migrasi + `sp_build_unified_profile()` |

### Tersedia di L1 ≠ dikonsumsi L2

Dua hal yang berbeda dan sering tertukar. Status per 2026-08-21:

| Kolom L1 | Tersedia di L1 | Dikonsumsi L2 | Dipakai sebagai |
|---|---|---|---|
| `unified_post.likes_hidden` | ✅ 221/221 | ✅ | filter sampel di seluruh asset feature + `kol_metric_daily` |
| `unified_post.is_collaboration` | ✅ 221/221 | ✅ | filter sampel yang sama |
| `unified_post.engagement_rate` | ✅ 205/221 | ✅ **sebagian** | diteruskan apa adanya ke `feature.ig_post_analysis.engagement_rate`. **Tidak** dipakai `l2_gold` — di sana ER dihitung ulang dari komponen (§17.6) |
| `unified_profile.followers_growth` | ✅ **22/1.994** sejak 2026-08-24 | ❌ | kolom `followers_growth` ada di kedua tabel `l2_gold` tapi tidak pernah ditulis. Sekarang sumbernya SUDAH ada di L1 — yang belum, pengisinya di L2. Perhatikan beda tipe: L1 `numeric` berisi **persen**, L2 `bigint` menyiratkan **jumlah orang** |
| `unified_profile.tier` | ✅ 1.967/1.971 | ❌ | belum ada konsumen L2 |
| `unified_post.hashtags` | ⚠️ 78/221 | ✅ | `feature.*_post_analysis.top_hashtags`. Tidak dipakai `l2_gold` |
| `unified_post.is_sponsored` | ✅ 221/221 | ✅ | `feature.*_post_analysis.is_sponsored`. Tidak dipakai `l2_gold` |
| `unified_post.media_type` | ✅ 221/221 | ✅ | `feature.*_post_analysis.media_type` + `format_performance` |

**Kolom L1 yang belum dikonsumsi L2 sama sekali:** `title`, `caption`,
`permalink`, `cover_image`, `video_duration`, `carousel_media_count`,
`shortcode`, `mentions`, `has_insights`, `platform_user_id`, `username`,
dan seluruh kolom Insights yang masih 0 baris (`reach`, `total_interactions`,
`follows`, `profile_visits`, `reel_avg_watch_time`,
`reel_video_view_total_time`, `reposts`).

Prinsipnya: **kolom tidak ditambahkan ke L2 hanya karena sekarang tersedia di
L1.** Penambahan menunggu kebutuhan UI yang nyata.

## 14.2 `followers_growth`

| | |
|---|---|
| Tabel | `l1_silver.unified_profile` |
| Tipe | `numeric` — tanpa presisi, disengaja: akun kecil yang melonjak bisa menghasilkan persentase sangat besar, dan tipe berpresisi akan menggagalkan seluruh perhitungan |
| Grain | `(social_account_id, date)` — sama dengan grain tabelnya, `uq_unified_profile` |
| Status | **dihitung otomatis** oleh `sp_build_unified_profile()` |

### Rumus

```sql
CASE
    WHEN prev_followers_count IS NULL      -- belum ada snapshot pembanding
      OR prev_followers_count = 0          -- pembagian tidak terdefinisi
      OR followers_count IS NULL           -- nilai sekarang tidak diketahui
    THEN NULL
    ELSE round((followers_count - prev_followers_count)::numeric
               / prev_followers_count * 100, 4)
END
```

Dibulatkan 4 desimal, konsisten dengan `engagement_rate` dan
`transform.py:compute_engagement_rate()`.

### Cara menentukan snapshot sebelumnya

```sql
LAG(followers_count) OVER (PARTITION BY social_account_id ORDER BY date)
```

Yaitu baris dengan `date` **terdekat yang lebih kecil**, milik
`social_account_id` yang sama. Perbandingannya **snapshot ke snapshot**, bukan
jendela waktu tetap — jarak antar snapshot mengikuti jarak scraping.

Window ini dijalankan atas **layer harmonization**
(`l0_harmonization.instagram_profile` + `tiktok_profile`), bukan atas
`unified_profile`. Dua alasannya:

1. Riwayatnya sama lengkapnya — ketiga tabel bergrain
   `(social_account_id, date)` dengan UNIQUE dan `ON CONFLICT` yang sama.
2. **Satu statement `INSERT` tidak bisa melihat baris yang sedang dimasukkannya
   sendiri.** Kalau pembanding dicari lewat lookup ke `unified_profile`,
   hasilnya berbeda antara backfill sekali jalan (semua tanggal masuk
   bersamaan → semua NULL) dan pengisian bertahap. Memakai sumber harmonization
   membuat hasilnya deterministik.

### Kapan hasilnya `NULL`

Tiga kondisi, dan **tidak ada tebakan maupun nilai 0 pengganti**:

- belum ada snapshot sebelumnya untuk akun tersebut;
- `followers_count` snapshot sebelumnya `NULL` atau `0`;
- `followers_count` snapshot sekarang `NULL`.

### Perilaku saat UPSERT

```sql
followers_growth = EXCLUDED.followers_growth,   -- penugasan LANGSUNG
```

Bukan `COALESCE(EXCLUDED.x, existing.x)` seperti 25 kolom lain di klausa
`ON CONFLICT`. Kolom turunan harus selalu mengikuti hasil hitung terbaru: dengan
`COALESCE`, hasil hitung `NULL` akan mempertahankan nilai lama dan metriknya jadi
basi. Pola yang sama sudah dipakai `tier` (`tier = EXCLUDED.tier`) dan
`is_verified`.

### Kondisi data saat ini — diperbarui 2026-08-24

**22 dari 1.994 baris terisi** (Instagram 13, TikTok 9). Kolom ini sebelumnya
0/1.971 karena tiap akun baru punya satu snapshot; scraping profil kedua pada
2026-08-24 untuk 23 akun yang punya post menutup kekurangan itu — **tanpa
migrasi, tanpa backfill, tanpa perubahan kode**, persis seperti yang diperkirakan.

Rentang snapshot sekarang 2026-08-14 s.d. 2026-08-24, dan 22 akun punya ≥2 baris.
Nilai yang dihasilkan (pertumbuhan 10 hari, dalam persen):

| Akun | Growth | | Akun | Growth |
|---|---:|---|---|---:|
| `pojoksatu.id` (TT) | +0,9174 | | `lunamaya` | −0,0301 |
| `hesfinatia` (TT) | +0,6711 | | `irwansyah_15` | −0,0281 |
| `ibnuwardani` (TT) | +0,2865 | | `anyageraldine` | −0,0271 |
| `iben_ma` (IG) | +0,2351 | | `raffinagita1717` | −0,0261 |
| `cristiano` | +0,0637 | | `pevpearce` | −0,0220 |
| `lambe_turah` | +0,0343 | | `inul.d` (IG) | −0,0202 |
| `leomessi` | +0,0191 | | `isyanasarasvati` | −0,0510 |
| `fadiljaidi` | +0,0038 | | 5 akun lain | 0,0000 |

Empat akun TikTok tercatat 0,0000 karena platform membulatkan follower ke
ratusan ribu — pergerakan di bawah itu tidak terlihat, bukan berarti stagnan.

Yang masih kosong: `inul.d` TikTok (baru punya satu snapshot, sebelumnya tidak
punya baris profil sama sekali) dan 1.972 baris akun tanpa post yang memang tidak
ikut di-scrape ulang.

Verifikasi rumusnya sudah dilakukan dengan simulasi snapshot kedua di dalam
transaksi yang di-rollback: tiga akun dengan followers sebelumnya 80% dari nilai
sekarang menghasilkan `followers_growth = 25.0000`, dan rekonsiliasi atas 1.974
baris menghasilkan 0 selisih.

## 14.3 `likes_hidden`, `is_collaboration`, `engagement_rate`

Ketiganya di `unified_post`, bergrain `(social_account_id, content_id)`.

| Kolom | Rumus | Terisi |
|---|---|---|
| `likes_hidden` | `likes = -1` — sentinel Instagram untuk jumlah like yang disembunyikan. `NULL` bila `likes` sendiri `NULL` | 15 TRUE (IG), 0 (TT) |
| `is_collaboration` | username pemilik post `IS DISTINCT FROM` username pemilik akun, keduanya dinormalisasi seperti `db.py:_SQL_NORMALIZED_USERNAME`. `NULL` bila salah satu sisi tidak diketahui | 41 TRUE (IG), 0 (TT) |
| `engagement_rate` | `(likes + comments + shares) ÷ followers_pada_tanggal_post × 100`, 4 desimal. `NULL` bila `likes_hidden`, atau tidak ada snapshot profil pada/sebelum tanggal tayang. **Diperbaiki migration 024 (2026-08-24)** — sebelumnya `(likes + comments) ÷ followers_terbaru` | 53/130 IG, 55/91 TT |

Ketiganya juga memakai **penugasan langsung** di `ON CONFLICT`, dengan alasan
yang sama seperti `followers_growth`.

`likes_hidden` dan `is_collaboration` menjadikan dua aturan yang sudah disepakati
— kecualikan post ber-`likes = -1`, kecualikan post kolaborasi dari engagement
rate — sebagai **data yang bisa di-query dan diaudit**, bukan logika yang harus
ditulis ulang di tiap konsumen hilir.

---

# 15. AUDIT `postFreq` (FREKUENSI POSTING)

Audit **2026-08-21**, read-only. Tidak diimplementasikan — audit ini mencatat
kenapa.

## 15.1 Kebutuhan UI

Satuan: **post per minggu**, satu desimal.

| Tempat | Pemakaian |
|---|---|
| Data KOL | `postFreq: 5.2` |
| Filter | `if (k.postFreq < a.postFreqMin) return false` (`app/Autometric-KOL-Module.html:885`) |
| Slider | "Min. posting freq." 0–10, label `/wk` (`:1020`) |
| Bullet insight | *"Publishes **5,2× per week** with high consistency"* (`:1538`) |
| **Input metrik lain** | `estReach = reach × (1 + auth/400 + postFreq/40)` (`:632`) |

Yang terakhir penting: `postFreq` bukan metrik terminal. Ia ikut menentukan
`estReach`, yang dipakai untuk filter dan kolom tabel — kesalahan di sini
menjalar.

## 15.2 Sumber: lengkap

| | Instagram | TikTok |
|---|---|---|
| `unified_post.posted_at` terisi | **130/130** | **91/91** |
| Akun | 13 | 10 |
| Rentang tertua–terbaru | 2022-12-17 → 2026-08-20 | 2021-02-18 → 2026-08-20 |

Nol NULL. **Masalahnya bukan ketersediaan sumber.**

## 15.3 Rumah kolom: belum ada

Pencarian `%post%freq%`, `%frequency%`, `%posting%` di seluruh database hanya
menemukan `best_posting_time_heatmap` (metrik berbeda) dan
`campaign_brief.posting_schedule` (domain campaign).

## 15.4 ⚠️ Rumus naif tidak bisa dipakai

`COUNT(post) ÷ rentang_minggu` atas sampel yang ada:

| Akun | Post | Rentang | posts/minggu |
|---|---:|---:|---:|
| `lambe_turah` | 10 | **1 hari** | **70,00** |
| `inul.d` (IG) | 10 | 2 hari | 35,00 |
| `iben_ma` (IG) | 10 | 7 hari | 10,00 |
| `cristiano` | 10 | 27 hari | 2,59 |
| `leomessi` | 10 | 275 hari | 0,25 |
| `raffinagita1717` | 10 | 667 hari | 0,10 |
| `irwansyah_15` | 10 | **1.339 hari** | **0,05** |

Sebaran **0,05–70** dari sampel berukuran sama persis (10 post) — rentang 1.400×
yang mengukur **seberapa rapat 10 post terakhir**, bukan seberapa sering akun
posting. Dua akun TikTok punya rentang **0 hari**, sehingga rumusnya membagi nol.

## 15.5 ⚠️ Jendela tetap lebih baik, tapi tersensor dari atas

Dengan `COUNT(post dalam 30 hari) ÷ (30/7)`, sebarannya masuk akal (0,93–2,33).
Tapi `resultsLimit = 10` memasang plafon:

| | Instagram | TikTok |
|---|---:|---:|
| Sampel **menutupi penuh** jendela 30 hari | **10 / 13** | **5 / 10** |
| **Tersensor** (10 post semuanya di dalam jendela) | 3 | 5 |
| Menutupi penuh jendela **90 hari** | 6 / 13 | 4 / 10 |
| **Tersensor** pada 90 hari | **7** | **6** |

Plafonnya terlihat: 10 ÷ (30/7) = **2,33**, dan tepat akun-akun tersensor yang
mendarat di angka itu. Untuk mereka 2,33 adalah **batas bawah**: akun yang
posting 30× sebulan dan yang posting 11× sebulan tercatat sama.

Uji validitasnya sederhana — sampel menutupi jendela hanya kalau **post tertua di
sampel lebih tua dari awal jendela**. Makin panjang jendelanya, makin banyak yang
tersensor: di 90 hari lebih dari separuh akun tidak bisa dipercaya.

## 15.6 Status

| Penghambat | Status |
|---|---|
| Sumber `posted_at` | ✅ lengkap 221/221 |
| Rumus | ✅ jelas, tinggal pilih jendela |
| Kolom | ⚠️ belum ada, tapi mudah dibuat |
| **Strategi scraping** | ⛔ **penghambat sebenarnya** |

Berbeda dari `followers_growth` yang hanya menunggu waktu, `postFreq` menunggu
**perubahan cara scraping**: ambil semua post dalam jendela waktu, bukan N post
terakhir. Selama masih "10 post terakhir", metrik ini **tidak akan pernah benar
untuk akun paling aktif** — justru akun yang paling menarik untuk campaign.

## 15.7 Rancangan yang disiapkan (belum diimplementasikan)

Kalau nanti dilanjutkan, pendekatan yang disarankan: hitung **hanya** untuk akun
yang sampelnya menutupi jendela, `NULL` untuk yang tersensor — konsisten dengan
`engagement_rate` dan `followers_growth`.

```sql
CASE
    WHEN post_tertua >= (acuan - <jendela>) THEN NULL   -- tersensor, hanya batas bawah
    WHEN <tidak ada post di jendela>        THEN NULL
    ELSE round(jumlah_post_dalam_jendela::numeric / (<jendela> / 7.0), 4)
END
```

Hasilnya hari ini: 10/13 akun Instagram (0,93–1,87 post/minggu) dan 5/10 TikTok
mendapat nilai yang bisa dipertanggungjawabkan; sisanya NULL.

Rumah kolom yang disarankan: **`l1_silver.unified_profile.post_frequency`**,
bergrain `(social_account_id, date)` seperti `tier` dan `followers_growth`.
Acuan jendelanya jadi `date` baris itu sendiri — "frekuensi posting dalam N hari
sebelum snapshot ini" — sehingga tidak butuh acuan `now()` yang ambigu.

### Empat keputusan yang masih terbuka

| # | Keputusan | Catatan |
|---|---|---|
| 1 | Panjang jendela: **30 atau 90 hari** | 30 hari: 15/23 akun dapat nilai. 90 hari: hanya 10/23 |
| 2 | Tersensor → **NULL** atau tulis batas bawahnya | Menulis 2,33 untuk akun yang posting 30×/bulan akan membuat filter `postFreqMin` menyaring akun yang salah |
| 3 | **Post kolaborasi ikut dihitung?** | `is_collaboration` sudah tersedia; 41/130 post IG terdampak |
| 4 | Rumah kolom: `unified_profile` atau tunggu layer `feature` | §15.7 |

---

# 16. AUDIT KESIAPAN KOLOM FEATURE/L2

Audit **2026-08-21**, read-only. Menjawab satu pertanyaan untuk **setiap kolom**
di schema `feature`: apakah sudah bisa diisi dari `l1_silver.unified_post` /
`l1_silver.unified_profile` hari ini, atau masih terkunci — dan kalau terkunci,
oleh apa.

Basis: **9 tabel · 135 kolom · 0 baris · 0 procedure.** Dari 135 kolom,
**41 struktural** (kunci, FK, timestamp) dan **94 kolom metrik**.

## 16.1 Ringkasan

| Status | Kolom metrik | Arti |
|---|---:|---|
| ✅ **READY** | **26** | Sumbernya lengkap di L1 hari ini |
| 🟡 **READY sebagian** | **5** | Bisa dihitung, cakupan/kualitas terbatas |
| 🟠 **PARTIAL** | **2** | Sebagian input siap, sisanya butuh keputusan bisnis |
| ⛔ **BLOCKED** | **61** | Sumber 0 baris, atau tidak ada sama sekali |

Seluruh 26 kolom READY bersumber dari **`unified_post`**. Tidak satu pun berasal
dari `unified_profile`, kecuali `followers_count` sebagai penyebut
`engagement_rate`.

## 16.2 `ig_engagement_analysis` — 18 kolom, grain per akun

| Kolom | Sumber | Status |
|---|---|---|
| `posts_analyzed_count` | `COUNT(unified_post)` | ✅ READY |
| `total_likes` | `SUM(likes)` | ✅ READY |
| `total_comments` | `SUM(comments)` | ✅ READY |
| `engagement_rate` | `SUM(likes+comments+shares) ÷ SUM(followers_pada_tanggal_post) × 100`, pembilang diselaraskan dengan penyebut. **Diperbaiki 2026-08-24** | ✅ READY — 9/13 akun |
| `reel_plays` | `SUM(views)` where `media_type='clips'` | ✅ READY — 54 post |
| `format_performance` | group by `media_type` | ✅ READY |
| `best_posting_time_heatmap` | `posted_at` + engagement | ✅ READY |
| `engagement_trend` | deret waktu `posted_at` | 🟡 sampel jarang — 10 post/akun tersebar rata-rata 297 hari |
| `total_shares` | `unified_post.shares` | ⛔ **0/130** — actor IG tidak menyediakan |
| `total_saves` | `unified_post.saved` | ⛔ **0/130** — idem |
| `reel_shares`, `story_replies`, `story_exits_rate` | Insights API | ⛔ Insights-only; `unified_story` 0 baris |

**7 READY · 1 lemah · 5 BLOCKED**

⚠️ `engagement_rate` bertipe `numeric(5,2)` (maks 999,99). Nilai IG maks 4,45 —
aman, tapi ini tipe yang sama yang pernah memicu bug `LEAST`/NULL (§14 dan
riwayat migrasi 015 lama).

## 16.3 `tt_engagement_analysis` — 13 kolom, grain per akun

| Kolom | Status |
|---|---|
| `videos_analyzed_count`, `total_views`, `total_likes`, `total_comments`, **`total_shares`**, **`total_saves`**, `engagement_rate`, `best_posting_time_heatmap` | ✅ **READY** — semua 91/91 |
| `engagement_trend` | 🟡 sampel jarang |

**8 READY · 1 lemah · 0 BLOCKED — tabel dengan kesiapan tertinggi di seluruh
schema.** TikTok punya `shares` dan `saved` yang Instagram tidak punya.

⚠️ `engagement_rate` `numeric(5,2)`, dan `jharnabhagwani` bernilai **29,78**.
Masih aman, tapi satu akun kecil dengan video viral bisa melewati 999,99.

## 16.4 `ig_audience_analysis` / `tt_audience_analysis` — 15 kolom masing-masing

| Kolom | Sumber | IG | TT |
|---|---|---|---|
| `active_hours_heatmap` | `posted_at` + engagement | ✅ READY | ✅ READY |
| `cpe` | `unified_rate_card.fee` ÷ engagement | 🟠 PARTIAL | 🟠 PARTIAL |
| `avg_reach` | `unified_post.reach` | ⛔ **0/130** | ⛔ **0/91** |
| `emv` | `avg_reach` × CPM | ⛔ | ⛔ |
| `authenticity_score`, `audience_quality_score`, `follower_quality_score` | `unified_follower` | ⛔ **0 baris + algoritma belum ada** | ⛔ |
| `gender_breakdown`, `age_gender_breakdown`, `geo_distribution` | `ig_profile_official.demographics_*` | ⛔ **0 baris** | ⛔ **tidak ada kolom sumber sama sekali** |
| `top_interest` | — | ⛔ **nol jalur data di layer mana pun** | ⛔ |

**1 READY · 1 PARTIAL · 9 BLOCKED** per tabel.

`cpe` PARTIAL: pembilang siap (rate card 9.210 baris, `fee` 100% terisi),
penyebut siap dari `unified_post`. Yang kurang: keputusan **`post_type` mana**
yang jadi basis fee (14 jenis tersedia) dan pembersihan 14 sentinel
`fee = 1.000.000.000`.

⚠️ Ketiga kolom demografi TikTok **permanen BLOCKED**: `tt_profile_official`
hanya 12 kolom, nol `demographics_*`, sementara `ig_profile_official` punya 4.

## 16.5 `ig_post_analysis` — 18 kolom, grain per post

| Kolom | Sumber | Status |
|---|---|---|
| `posted_at`, `media_type`, `is_sponsored` | pass-through `unified_post` | ✅ READY 130/130 |
| **`engagement_rate`** | `unified_post.engagement_rate` | ✅ **READY** — terisi **37/130** setelah migration 024 (sebelumnya 115/130 dengan penyebut yang salah) |
| `rank` | ranking by engagement | ✅ READY |
| `top_hashtags` | `unified_post.hashtags` | 🟡 hanya 39/130 post punya hashtag |
| `reach` | `unified_post.reach` | ⛔ 0/130 |
| `avg_watch_time_seconds`, `click_through_rate` | Insights | ⛔ |
| `content_category`, `category_percentage` | klasifikasi konten | ⛔ **algoritma belum ada** |
| `sentiment_breakdown` | `unified_comment` | ⛔ 0 baris |
| `ai_recommendation` | LLM | ⛔ belum didefinisikan |

**5 READY · 1 lemah · 7 BLOCKED**

## 16.6 `tt_post_analysis` — 15 kolom, grain per video

| Kolom | Status |
|---|---|
| `is_sponsored`, `rank` | ✅ READY |
| `top_hashtags` | 🟡 39/91 |
| `top_sound` | ⛔ `musicMeta` **ada di `raw_payload` L0** tapi tidak dipropagasi ke `unified_post` |
| `avg_watch_time_seconds`, `completion_rate`, `traffic_source` | ⛔ TikTok Analytics |
| `content_category`, `sentiment_breakdown`, `ai_recommendation` | ⛔ |

**2 READY · 1 lemah · 6 BLOCKED**

## 16.7 `ig_comments_analysis` / `tt_comments_analysis` — 15 kolom masing-masing

**Seluruh 10 kolom metrik BLOCKED** di kedua tabel: `comments_analyzed_count`,
`sentiment_positive_pct`, `sentiment_neutral_pct`, `sentiment_negative_pct`,
`spam_detected_pct`, `toxicity_pct`, `word_cloud`, `emoji_analysis`,
`top_topics`, `ai_comment_summary`.

Penyebab tunggal: **`l1_silver.unified_comment` = 0 baris**, dan seluruh tabel
komentar di L0 juga kosong. Ditambah sentiment/toxicity butuh model NLP yang
belum ditentukan.

## 16.8 `brand_fit_analysis` — 11 kolom, grain KOL × brand

**Seluruh 6 kolom metrik BLOCKED**: `partnership_score`, `sub_scores`,
`audience_overlap_pct`, `overlap_summary`, `category_fit_tags`,
`recommendations`.

Dua penghambat sekaligus: **`public.brand` = 0 baris** (tidak ada brand untuk
dicocokkan) dan algoritma brand-fit belum didefinisikan. `audience_overlap_pct`
juga butuh data follower kedua sisi, yang sama-sama 0.

## 16.9 Yang bisa diisi hari ini

**26 kolom metrik, dari 4 tabel**, untuk 23 akun / 221 post:

| Tabel | READY / total metrik |
|---|---|
| `tt_engagement_analysis` | **8 / 9** — paling siap |
| `ig_engagement_analysis` | 7 / 13 |
| `ig_post_analysis` | 5 / 13 |
| `tt_post_analysis` | 2 / 9 |
| `ig_audience_analysis` | 1 / 11 |
| `tt_audience_analysis` | 1 / 11 |
| `ig_comments_analysis` | 0 / 10 |
| `tt_comments_analysis` | 0 / 10 |
| `brand_fit_analysis` | 0 / 6 |

## 16.10 Penghambat, diurutkan berdasarkan jumlah kolom yang dibuka

| Penghambat | Kolom terkunci | Sifat |
|---|---:|---|
| `unified_comment` 0 baris | **20** | Butuh scraping komentar |
| Insights API belum tersambung | **11** | Butuh OAuth pemilik akun |
| Algoritma belum didefinisikan (authenticity, quality, brand fit, content category, AI) | **17** | **Keputusan bisnis**, bukan data |
| Demografi audiens | **6** | `ig_profile_official` 0 baris; TikTok tidak punya sumber sama sekali |
| `public.brand` 0 baris | **6** | Butuh onboarding brand |
| `unified_follower` 0 baris | **6** | Butuh scraping follower |
| `top_interest` tanpa sumber | **2** | Butuh keputusan sumber |
| `unified_post.shares`/`saved` Instagram kosong | **2** | Batasan actor Instagram |

Penghambat terbesar kedua bukan data, melainkan **keputusan**: 17 kolom terkunci
semata-mata karena algoritmanya belum didefinisikan, bukan karena sumbernya tidak
ada.

## 16.11 Tiga temuan struktural

1. **`active_hours_heatmap` duplikat `best_posting_time_heatmap`.** Sumber
   (`posted_at` + engagement) dan bentuk (jsonb jam × hari) sama persis, hanya
   beda tabel — `*_audience_analysis` vs `*_engagement_analysis`.

2. **`tt_post_analysis` kekurangan 4 kolom** yang ada di `ig_post_analysis` dan
   datanya tersedia untuk TikTok: `posted_at`, `engagement_rate`, `media_type`,
   `reach`. Empat metrik READY tanpa rumah di sisi TikTok.

3. **`top_sound` tidak bisa diisi meski datanya ada.** `musicMeta` tersimpan utuh
   di `l0_raw.tt_video_apify.raw_payload`, tapi tidak pernah dipropagasi ke
   `unified_post`. Ini satu-satunya kolom BLOCKED yang penghambatnya murni
   propagasi L0→L1, bukan ketiadaan data — dan karenanya paling murah dibuka.

---

# 17. L2 GOLD — `kol_metric_daily` & `kol_metric_monthly`

Ditulis **2026-08-21**, setelah SCRUM-513 dan SCRUM-516 di-commit dan
di-materialize. Isi bagian ini diverifikasi langsung terhadap schema dan data
aktual, bukan terhadap rancangan.

## 17.1 Status backlog L2

Backlog "L2 Database" (SCRUM-490) berisi **10 subtask → 8 tabel distinct**.
Seluruh 8 tabel kini **punya schema**; 2 di antaranya sudah terisi.

| Item | Tabel | Schema | Data |
|---|---|---|---|
| **SCRUM-513** | `kol_metric_daily` | ✅ migration 021 | ✅ **160 baris** |
| **SCRUM-516** | `kol_metric_monthly` | ✅ migration 022 | ✅ **53 baris** |
| **SCRUM-515** | `post_metric` | ✅ migration 023 | ⬜ kosong — sumber siap, asset belum ada |
| **SCRUM-514** | `kol_profile_card` | ✅ migration 023 | ⬜ kosong — sumber siap, asset belum ada |
| **SCRUM-517/518** | `content_format_daily` | ✅ migration 023 | ⬜ kosong — sumber siap, asset belum ada |
| **SCRUM-519** | `audience_demographics_daily` | ✅ migration 023 | ⬜ kosong — sumber 0 baris |
| **SCRUM-520** | `audience_geo_daily` | ✅ migration 023 | ⬜ kosong — sumber 0 baris |
| **SCRUM-521** | `audience_interest_daily` | ✅ migration 023 | ⬜ kosong — **tidak ada sumber** |

SCRUM-491 ("hasil dari skema feature") bukan tabel; tidak dibuatkan apa pun.

Rincian keenam tabel baru ada di **§17.13**.

## 17.2 Aliran data aktual

```
l0_raw → l0_harmonization → l1_silver.unified_post
                            l1_silver.unified_profile
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
              feature.*                    l2_gold.kol_metric_daily
       (4 tabel terisi, per akun /                    │
        per post — cabang terpisah)                   ▼
                                          l2_gold.kol_metric_monthly
```

Dua hal yang sering salah dipahami:

- **`l2_gold` TIDAK membaca `feature`.** Keduanya cabang paralel di atas L1.
- **`kol_metric_monthly` TIDAK membaca L1.** Sumbernya hanya `kol_metric_daily`,
  supaya rumus metriknya hanya ditulis sekali.

## 17.3 `l2_gold.kol_metric_daily`

**Tujuan** — rekap harian per KOL per platform: satu baris merangkum seluruh
konten yang tayang pada satu hari.

| | |
|---|---|
| **Grain** | `(social_account_id, platform, metric_date)` |
| **Source** | `l1_silver.unified_post` (metrik konten) + `l1_silver.unified_profile` (follower) |
| **PK** | `kol_metric_daily_pkey` — `PRIMARY KEY (id)` |
| **UNIQUE** | `uq_kol_metric_daily` — `(social_account_id, platform, metric_date)` |
| **FK** | `fk_kol_metric_daily_social_account` → `public.social_account(id)` |
| **Index** | `ix_kmd_account_date`, `ix_kmd_account_platform_date` |
| **Pengisi** | asset Dagster `kol_metric_daily` (`assets/gold.py`) — SQL langsung, bukan procedure |
| **Duplicate handling** | UPSERT `ON CONFLICT ... DO UPDATE` dengan guard `IS DISTINCT FROM` |
| **Isi saat ini** | 160 baris, 23 akun, 2 platform, 2021-02-18 s.d. 2026-08-20 |

### Kolom (22)

| # | Kolom | Tipe | Null | Arti | Sumber / rumus | Terisi |
|---|---|---|---|---|---|---|
| 1 | `id` | `uuid` | NOT NULL | kunci teknis | `gen_random_uuid()` | 160 |
| 2 | `social_account_id` | `uuid` | NOT NULL | KOL | `unified_post.social_account_id` | 160 |
| 3 | `platform` | `varchar(30)` | NOT NULL | platform | `platforms.key` via `platform_id` | 160 |
| 4 | `metric_date` | `date` | NOT NULL | tanggal konten TAYANG (WIB) | `(posted_at AT TIME ZONE 'Asia/Jakarta')::date` | 160 |
| 5 | `post_count` | `bigint` | NOT NULL `0` | semua konten hari itu | `COUNT(*)` | 160 |
| 6 | `posts_in_sample` | `bigint` | NOT NULL `0` | konten yang layak dihitung | `COUNT(*) FILTER (lolos)` | 160 |
| 7 | `likes_sum` | `bigint` | null | total suka | `SUM(likes) FILTER (lolos)` | 124 |
| 8 | `comments_sum` | `bigint` | null | total komentar | `SUM(comments) FILTER (lolos)` | 124 |
| 9 | `shares_sum` | `bigint` | null | total dibagikan | `SUM(shares) FILTER (lolos)` | **60 — TikTok saja** |
| 10 | `saves_sum` | `bigint` | null | total disimpan | `SUM(saved) FILTER (lolos)` | **60 — TikTok saja** |
| 11 | `views_sum` | `bigint` | null | total tayangan | `SUM(views) FILTER (lolos)` | 88 |
| 12 | `engagement_sum` | `bigint` | null | total interaksi | `likes+comments+shares` sesuai definisi bisnis (Save TIDAK ikut, diperbaiki 2026-08-24); komponen NULL→0; **NULL bila `posts_in_sample = 0`** | 124 |
| 13 | `engagement_public_sum` | `bigint` | null | interaksi publik | `likes + comments` | 124 |
| 14 | `followers_at_post_date` | `bigint` | null | follower saat konten tayang | **carry-forward**: snapshot `unified_profile` terakhir dengan `date <= metric_date` | 61 |
| 15 | `followers_denom_sum` | `bigint` | null | penyebut ER additive | `followers_at_post_date × posts_in_sample` | 52 |
| 16 | `er_followers_daily` | `numeric(12,8)` | null | ER harian, **fraksi 0–1** | `engagement_sum / followers_denom_sum` | 52 |
| 17 | `reach_sum` | `bigint` | null | jangkauan | **BLOCKED** | **0** |
| 18 | `er_reach_daily` | `numeric(12,8)` | null | ER jangkauan | **BLOCKED** | **0** |
| 19 | `reposts_sum` | `bigint` | null | repost | **BLOCKED** | **0** |
| 20 | `followers_growth` | `bigint` | null | pertumbuhan follower | **BLOCKED** | **0** |
| 21 | `created_at` | `timestamptz` | NOT NULL `now()` | jejak | | 160 |
| 22 | `updated_at` | `timestamptz` | NOT NULL `now()` | jejak | | 160 |

## 17.4 Aturan DAILY

**Grain** — 1 KOL + 1 platform + 1 tanggal.

**Tanggal** — `metric_date` dari `posted_at`, dikonversi ke `Asia/Jakarta` lebih
dulu. **Bukan** `unified_post.date`: kolom itu tanggal *scrape*, seluruh 221
baris bernilai `2026-08-20`. `posted_at` punya 68 tanggal berbeda. Konversi WIB
bukan formalitas — ia memindahkan 2 baris Instagram ke tanggal berbeda.

**Sampling** — post dengan `likes_hidden IS TRUE` **atau** `is_collaboration IS
TRUE` tidak masuk sampel metrik, tapi **tetap dihitung** di `post_count`.
Karena itu:

```
post_count  ≠  posts_in_sample
```

Contoh nyata: `raffinagita1717` pada 2026-08-19 punya `post_count = 6` tapi
`posts_in_sample = 2`.

**Engagement** — `likes + comments + shares`, komponen NULL dianggap 0.
Mengikuti definisi bisnis `Engagement = Likes + Comments + Shares/Reposts/Quotes`.
**Save/Collect TIDAK termasuk** — menyimpan post adalah tindakan pribadi, bukan
penyebaran ulang. `saves_sum` tetap disimpan sebagai metrik tersendiri.

> **Diperbaiki 2026-08-24.** Sebelumnya rumusnya `likes + comments + shares + saves`,
> disalin dari referensi `sp_build_brand_metric_daily()`. TikTok kelebihan 2.639.563
> di 60/60 baris (rata-rata +3,73%, maksimum +12,41%); Instagram tidak terdampak
> karena `shares` dan `saves`-nya kosong. Setelah perbaikan: TikTok harian
> 53.509.374 → 50.869.811, `er_followers_daily` rata-rata 0,00448813 → 0,00434868.

Konsekuensi yang tetap berlaku: untuk Instagram, `shares`/`saves`/`reposts`
semuanya NULL, jadi `engagement_sum` Instagram efektif hanya `likes + comments`
dan **understated** terhadap definisi sampai Insights API tersedia.

#### Ketersediaan komponen per platform

Rumusnya **sama untuk semua platform**. Yang berbeda adalah komponen mana yang
datanya tersedia — ditentukan oleh sumber, bukan oleh pilihan desain.

| Komponen | Instagram | TikTok | Masuk Engagement? |
|---|---|---|---|
| Like | ✅ `likesCount` 130/130 | ✅ `diggCount` 91/91 | ya |
| Comment | ✅ `commentsCount` 130/130 | ✅ `commentCount` 91/91 | ya |
| Share | ⏳ belum tersedia 0/130 | ✅ `shareCount` 91/91 | ya |
| Repost | ⏳ belum tersedia 0/130 | ⚠️ `repostCount` ada, nilai nol 0/91 | ya, kalau nanti bernilai |
| Quote | — tidak ada konsepnya | — tidak ada konsepnya | ya, kalau nanti ada |
| **Save / Collect** | ⏳ belum tersedia 0/130 | ✅ `collectCount` 91/91 | **TIDAK** — disimpan di `saves_sum` |

**Rumus efektif hari ini:**

```
Instagram : Engagement = Like + Comment              (Share belum ada sumbernya)
            engagement_sum = engagement_public_sum   -> dua kolom bernilai sama
            saves_sum      = kosong

TikTok    : Engagement = Like + Comment + Share
            engagement_sum - engagement_public_sum = Share
            saves_sum      = Save (terpisah, di luar Engagement)
```

**Nilai aktual pasca perbaikan 2026-08-24** (`l2_gold.kol_metric_daily`):

| Kolom | Instagram | TikTok |
|---|---:|---:|
| `engagement_sum` | 283.725.952 | 50.869.811 |
| `engagement_public_sum` | 283.725.952 | 49.813.596 |
| `saves_sum` | *kosong* | 2.639.563 |

Kontribusi Share pada TikTok: **1.056.215** atau **+2,12%** di atas angka
permukaan. Instagram: nol, karena komponennya belum ada.

**Aturan pakai:**

* `engagement_sum` Instagram **benar menurut rumus** tapi **belum lengkap
  menurut definisi** — bukan bug, dan bukan nol; statusnya "belum diketahui".
* Perbandingan Engagement lintas platform **perlu diberi catatan**: TikTok punya
  satu komponen lebih banyak yang datanya tersedia. Ini kesenjangan sumber data,
  bukan kesenjangan performa.
* Butuh angka yang benar-benar setara antar platform? Pakai
  `engagement_public_sum` — tapi **jangan menyebutnya "Engagement"**, karena
  menurut definisi Share seharusnya ikut.
* Butuh angka Save? Baca `saves_sum` langsung.
* Kolom kosong ditampilkan sebagai "belum tersedia", **bukan "0"**.

Begitu Instagram Insights API tersambung, `l0_raw.ig_media_snapshots_official`
mengisi `shares` dan `reposts`; jalur INSERT-nya sudah ada di
`sp_sync_instagram_post()`. `engagement_sum` Instagram otomatis lengkap **tanpa
ubah rumus**, karena rumusnya sudah menyebut Share sejak sekarang.

**Follower** — carry-forward: snapshot terakhir dengan `date <= metric_date`.
Snapshot tanggal-sama hanya menghasilkan 10 dari 160 baris (6%); carry-forward
menghasilkan 61 (38%). NULL bila post lebih tua dari snapshot pertama.

**ER** — `er_followers_daily = engagement_sum / followers_denom_sum`, NULL bila
penyebut NULL atau 0. Disimpan sebagai **fraksi 0–1**, bukan persen. Rentang
aktual 0,0000197–0,0457.

> Untuk rentang N hari: `SUM(engagement_sum) / SUM(followers_denom_sum)`.
> **Jangan** merata-rata `er_followers_daily` — rasio tidak additive.

## 17.5 `l2_gold.kol_metric_monthly`

| | |
|---|---|
| **Grain** | `(social_account_id, platform, month_start)` |
| **Source** | **`l2_gold.kol_metric_daily` saja** — tidak pernah membaca L1 |
| **PK** | `kol_metric_monthly_pkey` — `PRIMARY KEY (id)` |
| **UNIQUE** | `uq_kol_metric_monthly` — `(social_account_id, platform, month_start)` |
| **FK** | `fk_kol_metric_monthly_social_account` → `public.social_account(id)` |
| **Index** | `ix_kmm_account_month`, `ix_kmm_account_platform_month` |
| **Pengisi** | asset Dagster `kol_metric_monthly` (`assets/gold.py`) |
| **Duplicate handling** | UPSERT dengan guard `IS DISTINCT FROM` |
| **Isi saat ini** | 53 baris, 23 akun, 2 platform, 2021-02 s.d. 2026-08 |

### Kolom (29)

| # | Kolom | Tipe | Null | Agregasi dari daily | Terisi |
|---|---|---|---|---|---|
| 1 | `id` | `uuid` | NOT NULL | `gen_random_uuid()` | 53 |
| 2 | `social_account_id` | `uuid` | NOT NULL | grain | 53 |
| 3 | `platform` | `varchar(30)` | NOT NULL | grain | 53 |
| 4 | `month_start` | `date` | NOT NULL | `date_trunc('month', metric_date)::date` | 53 |
| 5 | `year` | `integer` | NOT NULL | `EXTRACT(YEAR FROM month_start)` | 53 |
| 6 | `month` | `integer` | NOT NULL | `EXTRACT(MONTH FROM month_start)` | 53 |
| 7 | `month_year` | `varchar(7)` | NOT NULL | `to_char(month_start,'YYYY-MM')` | 53 |
| 8 | `quarter` | `integer` | NOT NULL | `EXTRACT(QUARTER FROM month_start)` | 53 |
| 9 | `year_quarter` | `varchar(6)` | NOT NULL | `'YYYY' || 'Q' || Q` | 53 |
| 10 | `active_days` | `bigint` | NOT NULL `0` | **`COUNT(*)` baris daily** | 53 |
| 11 | `post_count` | `bigint` | NOT NULL `0` | SUM | 53 |
| 12 | `posts_in_sample` | `bigint` | NOT NULL `0` | SUM | 53 |
| 13 | `likes_sum` | `bigint` | null | SUM | 42 |
| 14 | `comments_sum` | `bigint` | null | SUM | 42 |
| 15 | `shares_sum` | `bigint` | null | SUM | **18 — TikTok saja** |
| 16 | `saves_sum` | `bigint` | null | SUM | **18 — TikTok saja** |
| 17 | `views_sum` | `bigint` | null | SUM | 29 |
| 18 | `engagement_sum` | `bigint` | null | SUM — **total sebenarnya** | 42 |
| 19 | `engagement_public_sum` | `bigint` | null | SUM | 42 |
| 20 | `followers_eom` | `bigint` | null | **snapshot hari terakhir**, bukan rata-rata | 21 |
| 21 | `followers_denom_sum` | `bigint` | null | SUM | 18 |
| 22 | `engagement_for_er_sum` | `bigint` | null | **`SUM(engagement_sum) FILTER (WHERE followers_denom_sum IS NOT NULL)`** | 18 |
| 23 | `er_followers_monthly` | `numeric(12,8)` | null | `engagement_for_er_sum / followers_denom_sum` | 18 |
| 24 | `reach_sum` | `bigint` | null | **BLOCKED** | **0** |
| 25 | `er_reach_monthly` | `numeric(12,8)` | null | **BLOCKED** | **0** |
| 26 | `reposts_sum` | `bigint` | null | **BLOCKED** | **0** |
| 27 | `followers_growth` | `bigint` | null | **BLOCKED** | **0** |
| 28 | `created_at` | `timestamptz` | NOT NULL `now()` | | 53 |
| 29 | `updated_at` | `timestamptz` | NOT NULL `now()` | | 53 |

## 17.6 Aturan MONTHLY

**Dimensi kalender** — `month_start`, `year`, `month`, `month_year`, `quarter`,
`year_quarter`. Disimpan agar dashboard tidak perlu menurunkannya ulang; pola
ini diambil dari kedua referensi monthly di `socmed_report`.

**Metrik additive** — `SUM` dari daily untuk `post_count`, `posts_in_sample`,
`likes_sum`, `comments_sum`, `shares_sum`, `saves_sum`, `views_sum`,
`engagement_sum`, `engagement_public_sum`, `followers_denom_sum`.

**`active_days`** — jumlah baris daily dalam bulan itu. Rata-rata 2,9 (IG) dan
3,3 (TT) hari aktif per bulan.

**`followers_eom`** — follower snapshot **terakhir** dalam bulan tersebut,
lewat `DISTINCT ON (...) ORDER BY metric_date DESC`. **Bukan rata-rata.**

### ER monthly — aturan wajib

`er_followers_monthly` **BUKAN** `AVG(er_followers_daily)`, dan **bukan pula**
`SUM(engagement_sum) / SUM(followers_denom_sum)` secara naif.

```sql
engagement_for_er_sum = SUM(engagement_sum)
                        FILTER (WHERE followers_denom_sum IS NOT NULL)

er_followers_monthly  = engagement_for_er_sum / followers_denom_sum
```

**Alasan** — pembilang dan penyebut harus berasal dari hari yang sama-sama
punya penyebut. Kalau tidak, engagement dari hari yang follower-nya tidak
diketahui ikut dibagi dengan penyebut hari lain.

**Contoh `cristiano`, Agustus 2026:**

| tanggal | `posts_in_sample` | `engagement_sum` | `followers_denom_sum` |
|---|---|---|---|
| 2026-08-05 | 1 | 24.368.955 | **NULL** |
| 2026-08-12 | 1 | 31.144.645 | **NULL** |
| 2026-08-14 | 1 | 12.267.307 | 679.264.838 |
| 2026-08-16 | 0 | NULL | NULL |

| Cara | Perhitungan | Hasil |
|---|---|---|
| Naif | 67.780.907 / 679.264.838 | **0,0998** (≈10%) |
| **Selaras (dipakai)** | 12.267.307 / 679.264.838 | **0,0181** (≈1,8%) |

Cara naif menghasilkan angka **≈5,5× lebih besar**. **11 dari 18** bulan ber-ER
terdampak pola ini.

Dua referensi di `socmed_report` saling bertentangan soal ini:
`syn_twitter_monthly_profile_metric()` memakai `AVG(er_daily)`, sedangkan
`syn_tiktok_profile_monthly()` menghitung ulang dari komponen. Diuji pada data
kita, **18 dari 18** bulan menghasilkan angka berbeda antara kedua cara — selisih
rata-rata 0,88 poin persen, terbesar 8,17. Yang dipakai di sini adalah cara
hitung-ulang.

## 17.7 NULL vs 0 — semantik

```
NULL = tidak diketahui / tidak tersedia
0    = diketahui, dan nilainya nol
```

Konsekuensi praktis:

- **Jangan** memakai `COALESCE(..., 0)` sembarangan. Referensi
  `sp_build_brand_metric_daily()` memakainya karena L1-nya memang terisi; di sini
  itu akan mengubah "tidak diketahui" menjadi "nol".
- `shares_sum` dan `saves_sum` **NULL untuk seluruh baris Instagram** — bukan 0.
  Actor Instagram tidak menyediakan kedua metrik itu.
- Kolom BLOCKED tetap NULL, tidak pernah ditulis.
- Bulan/hari yang seluruh sampelnya tidak valid (`posts_in_sample = 0`)
  menghasilkan metrik **NULL**, bukan 0. Di daily ada 36 baris seperti ini, di
  monthly 11 baris.
- **`followers_eom` tetap bisa terisi walaupun seluruh metrik post NULL** —
  follower adalah fakta profil, bukan hasil agregasi post. 3 baris monthly
  seperti ini.
- ER NULL bila penyebutnya tidak tersedia.

`SUM()` PostgreSQL sudah berperilaku benar tanpa bantuan: mengembalikan NULL
kalau semua input NULL. Itulah sebabnya `COALESCE` sengaja tidak dipakai.

## 17.8 Metrik BLOCKED

Kolomnya sudah ada di schema tetapi **100% NULL** di kedua tabel:

| Kolom | Daily | Monthly | Kenapa NULL | Sumber yang dibutuhkan |
|---|---|---|---|---|
| `reach_sum` | ✅ | ✅ | `unified_post.reach` 0/221 | Instagram Insights API / TikTok Analytics |
| `er_reach_daily` / `er_reach_monthly` | ✅ | ✅ | butuh `reach_sum` | idem |
| `reposts_sum` | ✅ | ✅ | `unified_post.reposts` 0/221 | Insights API (IG-only) |
| `followers_growth` | ✅ | ✅ | `unified_profile.followers_growth` **22/1.994** sejak 2026-08-24 | **sumber L1 sudah tersedia**; yang belum adalah pengisi di L2. Catatan: L1 menyimpan persen (`numeric`), kolom L2 bertipe `bigint` yang menyiratkan jumlah orang — perlu diselaraskan sebelum diisi |

Kolomnya dibuat lebih dulu supaya skema tidak perlu di-`ALTER` saat sumbernya
menyala. **Jangan diperlakukan sebagai nol.** Tidak ada tanggal implementasi yang
dijanjikan — ketiga penghambat di atas adalah keputusan akses API dan strategi
scraping, bukan pekerjaan pipeline.

## 17.9 UPSERT & idempotensi

Kedua tabel memakai pola yang sama:

```sql
ON CONFLICT (<grain>) DO UPDATE SET
    ...,
    updated_at = now()
WHERE target.kolom IS DISTINCT FROM EXCLUDED.kolom
   OR ...
```

Tujuannya:

- **rerun aman** — jalankan berapa kali pun, jumlah baris tetap;
- **baris identik tidak ditulis ulang** — `rowcount` rerun kedua = 0;
- **`updated_at` hanya bergerak kalau datanya benar-benar berubah**, jadi kolom
  itu bisa dipercaya sebagai penanda perubahan;
- **tidak memakai `TRUNCATE + INSERT`** — kedua referensi monthly di
  `socmed_report` memakainya, tapi itu menghapus riwayat bulan yang kebetulan
  tidak ikut batch dan meninggalkan tabel kosong kalau gagal di tengah.

## 17.10 Migration & hasil aktual

| Migration | Isi | Status |
|---|---|---|
| `021_create_kol_metric_daily.sql` | `CREATE TABLE l2_gold.kol_metric_daily` (22 kolom) | **committed + materialized** |
| `022_create_kol_metric_monthly.sql` | `CREATE TABLE l2_gold.kol_metric_monthly` (29 kolom) | **committed + materialized** |
| `023_create_l2_gold_remaining_tables.sql` | `CREATE TABLE` 6 tabel sisa (`post_metric` 29, `kol_profile_card` 24, `content_format_daily` 20, `audience_demographics_daily` 10, `audience_geo_daily` 10, `audience_interest_daily` 9 kolom) | **committed** — tabel dibuat KOSONG, belum ada asset |

Ketiganya murni `CREATE TABLE` + UNIQUE + FK + index. Seluruh tabel dibuat
kosong; pengisian dilakukan asset Dagster, dan baru dua tabel yang punya asset.

**Hasil `kol_metric_daily`:** 160 baris · 23 akun · 221 post tercakup ·
2 platform · follower carry-forward 61/160 · ER terisi 52 baris.

**Hasil `kol_metric_monthly`:** 53 baris · 23 akun · 2 platform ·
rentang 2021-02 s.d. 2026-08 · ER terisi 18 baris.

## 17.11 Hasil validasi

Seluruh angka di bawah berasal dari validasi yang benar-benar dijalankan
sebelum commit, di dalam transaksi yang di-`ROLLBACK`.

**`kol_metric_daily`**

| Pemeriksaan | Hasil |
|---|---|
| Duplikat grain | **0** |
| Kunci grain NULL | **0** |
| Post tercakup | **221 / 221** |
| Rekonsiliasi ke `unified_post` (`posts_in_sample`, `likes_sum`) | **cocok persis** |
| ER dihitung ulang vs tersimpan | **0 selisih** |
| ER > 1 | **0** |
| Kolom BLOCKED | **100% NULL** |
| Idempotensi (UPSERT kedua) | `rowcount = 0`, `updated_at` tidak bergerak |

**`kol_metric_monthly`**

| Pemeriksaan | Hasil |
|---|---|
| Duplikat grain | **0** |
| Kunci grain NULL | **0** |
| `EXCEPT` daily ↔ monthly, dua arah | **0 / 0** |
| Rekonsiliasi 11 ukuran ke daily | **cocok semua** |
| ER dihitung ulang vs tersimpan | **0 selisih** |
| ER > 1 | **0** |
| Bulan yang pembilang ER-nya diselaraskan | **11** |
| Kolom BLOCKED | **100% NULL** |
| Idempotensi (UPSERT kedua) | `rowcount = 0`, `updated_at` tidak bergerak |

## 17.12 Asset Dagster

| Asset | Grup | Dependency | File |
|---|---|---|---|
| `kol_metric_daily` | `l2_gold` | `unified_post`, `unified_profile` | `assets/gold.py` |
| `kol_metric_monthly` | `l2_gold` | **`kol_metric_daily`** | `assets/gold.py` |

```
unified_post ────┐
                 ├──► kol_metric_daily ──► kol_metric_monthly
unified_profile ─┘
```

Total asset terdaftar: **12** — 4 `l0_harmonization`, 2 `l1_silver`,
4 `feature`, 2 `l2_gold`. Rinciannya di `orchestration/README.md`.

**Enam tabel `l2_gold` lain belum punya asset.** Schema-nya sudah ada (migration
023) tapi logic pengisiannya belum dirancang, jadi sengaja tidak dibuatkan asset
skeleton — asset tanpa logic hanya menghasilkan kotak hijau tanpa arti. Status
per tabel ada di §17.13.


## 17.13 L2 Gold Data Inventory — 8 tabel

Diverifikasi langsung ke database **2026-08-21**. Struktur di bawah diambil dari
`pg_attribute` / `pg_constraint`, bukan dari rancangan — **database adalah source
of truth**. Jumlah tabel aktual di `l2_gold`: **8**, tidak ada tabel lain.

### Istilah status

| Istilah | Arti |
|---|---|
| `POPULATED` | schema ada **dan** tabelnya berisi data |
| `SCHEMA READY` | schema ada, kolom lengkap, siap diisi |
| `EMPTY / WAITING FOR PIPELINE` | kosong karena **asset/ETL-nya belum dibuat** — sumbernya sendiri sudah ada |
| `NO SOURCE DATA YET` | kosong karena **sumbernya belum ada**, bukan karena ETL |

Perlu dibedakan tegas: **tabel sudah dibuat ≠ pipeline-nya sudah selesai.**
Keenam tabel kosong di bawah **bukan** "belum dibuat" — schema-nya sudah ada.

### Inventory

| Table | Grain | Menampung | Source | Status |
|---|---|---|---|---|
| `kol_metric_daily` | `(social_account_id, platform, metric_date)` | performa konten harian per KOL | `l1_silver.unified_post` + `unified_profile` | **POPULATED** — 160 baris |
| `kol_metric_monthly` | `(social_account_id, platform, month_start)` | rekap bulanan | **`l2_gold.kol_metric_daily`** | **POPULATED** — 53 baris |
| `post_metric` | `(social_account_id, platform, content_id)` | performa per konten | `l1_silver.unified_post` + `feature.*_post_analysis` | `SCHEMA READY` · **EMPTY / WAITING FOR PIPELINE** |
| `kol_profile_card` | `(social_account_id, platform)` | profil/snapshot KOL | `l1_silver.unified_profile` + `unified_rate_card` | `SCHEMA READY` · **EMPTY / WAITING FOR PIPELINE** |
| `content_format_daily` | `(social_account_id, platform, metric_date, media_type)` | performa per format konten | `l1_silver.unified_post` | `SCHEMA READY` · **EMPTY / WAITING FOR PIPELINE** |
| `audience_demographics_daily` | `(social_account_id, platform, audience_date, audience_type, dimension_key)` | demografi audiens | `l1_silver.unified_audience` (0 baris) | `SCHEMA READY` · **EMPTY / WAITING FOR PIPELINE** |
| `audience_geo_daily` | `(social_account_id, platform, audience_date, geo_level, geo_key)` | geografi audiens | `l1_silver.unified_audience` (0 baris) | `SCHEMA READY` · **EMPTY / WAITING FOR PIPELINE** |
| `audience_interest_daily` | `(social_account_id, platform, audience_date, interest_key)` | minat audiens | **belum ada** | `SCHEMA READY` · **NO SOURCE DATA YET** |

Setiap tabel punya pola yang sama: kolom teknis **`id uuid`** sebagai
`PRIMARY KEY` (default `gen_random_uuid()`), satu `UNIQUE` pada grain, satu FK
`social_account_id → public.social_account(id)`, dua timestamp
`created_at`/`updated_at`, dan 4 index (pkey + uq + 2 index baca). Kolom `id`
tidak diulang di daftar kolom tiap tabel di bawah.

### Aliran data L2

```
l1_silver.unified_post ──┬─► kol_metric_daily ──► kol_metric_monthly
l1_silver.unified_profile┘         │
                                   └─(satu-satunya rantai L2→L2)
l1_silver.unified_post ────────────► content_format_daily
l1_silver.unified_post   ──┬───────► post_metric
feature.ig/tt_post_analysis┘
l1_silver.unified_profile ─┬───────► kol_profile_card
l1_silver.unified_rate_card┘
l1_silver.unified_audience ─┬──────► audience_demographics_daily
                            ├──────► audience_geo_daily
                            └──────► audience_interest_daily  (sumber belum ada)
```

Dua hal yang wajib dipegang:

- **`kol_metric_monthly` hanya membaca `l2_gold.kol_metric_daily`.** Monthly
  TIDAK mengagregasi ulang langsung dari L1, supaya rumus metriknya hanya
  ditulis sekali.
- **L2 Gold tidak membaca layer `feature` sebagai sumber utama.** Satu-satunya
  pengecualian yang tercatat di schema adalah `post_metric`, yang mengambil
  `rank_in_account` dan `top_hashtags` dari `feature.*_post_analysis` sesuai
  SCRUM-515. Selebihnya `feature` dan `l2_gold` adalah dua cabang paralel di
  atas L1.

---

### A. `kol_metric_daily` — 22 kolom · **POPULATED, 160 baris**

Menampung **metrik performa konten yang sudah diagregasi per akun, per platform,
per hari**. Satu baris menjawab: "pada tanggal ini, akun ini di platform ini
memposting berapa konten dan mendapat interaksi berapa?"

**Grain** `(social_account_id, platform, metric_date)`.
**Sumber** `l1_silver.unified_post` (metrik konten) + `l1_silver.unified_profile`
(follower).

| Kelompok | Kolom | Isi |
|---|---|---|
| Grain | `social_account_id`, `platform`, `metric_date` | `metric_date` = tanggal konten **TAYANG** (`posted_at` di WIB), bukan tanggal scrape |
| Hitungan konten | `post_count`, `posts_in_sample` | semua post hari itu vs post yang layak dihitung |
| Metrik interaksi | `likes_sum`, `comments_sum`, `shares_sum`, `saves_sum`, `views_sum` | `SUM` per hari dari post yang lolos sampel |
| Engagement | `engagement_sum`, `engagement_public_sum` | total interaksi dan interaksi publik |
| Follower | `followers_at_post_date`, `followers_denom_sum` | snapshot carry-forward, dan penyebut ER additive |
| ER | `er_followers_daily` | fraksi 0–1 |
| BLOCKED | `reach_sum`, `er_reach_daily`, `reposts_sum`, `followers_growth` | kolom ada, isinya selalu NULL |
| Jejak | `created_at`, `updated_at` | |

**Aturan sampling.** Post dengan `likes_hidden IS TRUE` **atau**
`is_collaboration IS TRUE` dikeluarkan dari seluruh `*_sum`, tapi **tetap
dihitung** di `post_count`. Karena itu `post_count ≠ posts_in_sample`.

**Rumus ER.** `er_followers_daily = engagement_sum / followers_denom_sum`, NULL
bila penyebut NULL atau 0. Untuk rentang N hari: `SUM(engagement_sum) /
SUM(followers_denom_sum)` — jangan merata-rata kolom harian.

**NULL vs 0.** NULL = tidak diketahui, 0 = diketahui bernilai nol. Keterisian
aktual: `likes_sum`/`comments_sum` 124 dari 160, `shares_sum`/`saves_sum` **60
(TikTok saja — Instagram NULL)**, `views_sum` 88, `engagement_sum` 124,
`followers_at_post_date` 61, `er_followers_daily` 52. Keempat kolom BLOCKED
**0 terisi**.

---

### B. `kol_metric_monthly` — 29 kolom · **POPULATED, 53 baris**

Menampung **rekap performa bulanan yang berasal dari `kol_metric_daily`**.
Tabel ini **tidak membaca L1 secara langsung**.

**Grain** `(social_account_id, platform, month_start)`.

| Kelompok | Kolom |
|---|---|
| Grain | `social_account_id`, `platform`, `month_start` |
| Kalender | `year`, `month`, `month_year` (`YYYY-MM`), `quarter`, `year_quarter` (`YYYYQn`) |
| Cakupan | `active_days` — jumlah baris harian dalam bulan itu |
| Hitungan konten | `post_count`, `posts_in_sample` |
| Interaksi | `likes_sum`, `comments_sum`, `shares_sum`, `saves_sum`, `views_sum` |
| Engagement | `engagement_sum`, `engagement_public_sum` |
| Follower | `followers_eom`, `followers_denom_sum` |
| ER | `engagement_for_er_sum`, `er_followers_monthly` |
| BLOCKED | `reach_sum`, `er_reach_monthly`, `reposts_sum`, `followers_growth` |
| Jejak | `created_at`, `updated_at` |

**`followers_eom`** adalah follower snapshot **hari terakhir** dalam bulan itu,
bukan rata-rata.

**ER bulanan dihitung ULANG dari komponen bulanan.** Bukan `AVG` dari ER harian:

```
engagement_for_er_sum = SUM(engagement_sum) FILTER (WHERE followers_denom_sum IS NOT NULL)
er_followers_monthly  = engagement_for_er_sum / followers_denom_sum
```

**Kenapa pembilangnya dibatasi.** Engagement ada untuk semua hari bersampel,
tapi penyebut follower hanya ada untuk hari yang follower-nya diketahui. Kalau
seluruh engagement dibagi penyebut sebagian hari, hasilnya membesar palsu.
Contoh `cristiano` Agustus 2026: cara naif 0,0998 vs cara selaras 0,0181 —
**≈5,5× lebih besar**, dan 11 dari 18 bulan ber-ER terdampak. Rinciannya di
§17.6.

Keterisian aktual: `likes_sum` 42 dari 53, `shares_sum` **18 (TikTok saja)**,
`engagement_sum` 42, `followers_eom` 21, `followers_denom_sum` 18,
`engagement_for_er_sum` 18, `er_followers_monthly` 18. BLOCKED **0 terisi**.

---

### C. `post_metric` — 29 kolom · `SCHEMA READY` · **EMPTY, 0 baris**

Level **konten**, bukan agregasi harian atau bulanan. Satu baris = **satu
konten** milik satu akun di satu platform.

**Grain** `(social_account_id, platform, content_id)`.
**Sumber** `l1_silver.unified_post` + `feature.ig_post_analysis` /
`feature.tt_post_analysis`.

| Kelompok | Kolom |
|---|---|
| Grain | `social_account_id`, `platform`, `content_id` |
| Metadata konten | `posted_at`, `post_date`, `media_type`, `is_sponsored`, `permalink` |
| Penanda sampel | `likes_hidden`, `is_collaboration` |
| Metrik mentah | `likes`, `comments`, `shares`, `saves`, `views` |
| Turunan | `engagement_owned`, `engagement_public`, `followers_at_post_date`, `er_followers` |
| Dari layer feature | `rank_in_account`, `top_hashtags` |
| BLOCKED | `reach`, `er_reach`, `reposts`, `avg_watch_time_seconds`, `completion_rate` |
| Jejak | `created_at`, `updated_at` |

`likes_hidden` dan `is_collaboration` disimpan di tabel ini supaya konsumen bisa
menyaring sendiri dengan aturan yang sama seperti `kol_metric_daily`, tanpa
kembali ke L1.

Bedanya dengan `feature.*_post_analysis` yang sudah terisi: yang di `feature`
terpisah per platform dan berorientasi analisis konten; `post_metric`
lintas-platform dan berorientasi metrik.

**Sumbernya sudah siap** (221 post di L1, 221 baris di feature) — yang belum ada
adalah asset Dagster pengisinya.

---

### D. `kol_profile_card` — 24 kolom · `SCHEMA READY` · **EMPTY, 0 baris**

Menampung **snapshot profil KOL per akun dan platform** — bukan performa tiap
post. Satu baris = satu kartu profil, **tanpa dimensi tanggal**.

**Grain** `(social_account_id, platform)`.
**Sumber** `l1_silver.unified_profile` (snapshot terbaru) +
`l1_silver.unified_rate_card` (ringkasan harga).

| Kelompok | Kolom |
|---|---|
| Grain | `social_account_id`, `platform` |
| Identitas | `username`, `display_name`, `avatar_url`, `profile_url`, `bio`, `website`, `is_verified`, `is_private` |
| Ukuran akun | `followers_count`, `following_count`, `media_count`, `tier` |
| Kesegaran | `profile_snapshot_date` — snapshot mana yang dipakai |
| Rate card | `rate_card` (jsonb, peta `post_type → fee`), `rate_card_currency`, `rate_card_min_fee`, `rate_card_max_fee`, `rate_card_post_types` |
| BLOCKED | `followers_growth` |
| Jejak | `created_at`, `updated_at` |

`profile_snapshot_date` ada supaya kartu yang basi masih bisa dikenali. Rate card
disimpan sebagai **ringkasan** (jsonb + min/maks), bukan salinan 9.210 baris.

Enam kolom `unified_rate_card` lain (`location`, `segmentasi`, `quantity`,
`duration_days`, `is_owning`, `link_file`) **tidak dibawa** — semuanya 0 terisi.

**Sumbernya sudah siap** (1.971 profil + 9.210 rate card).

---

### E. `content_format_daily` — 20 kolom · `SCHEMA READY` · **EMPTY, 0 baris**

Menampung **performa konten yang dikelompokkan berdasarkan format/media type per
hari**. Satu baris menjawab: "pada tanggal ini, konten berformat X milik akun ini
performanya berapa?"

**Grain** `(social_account_id, platform, metric_date, media_type)`.
**Sumber** `l1_silver.unified_post`.

| Kelompok | Kolom |
|---|---|
| Grain | `social_account_id`, `platform`, `metric_date`, `media_type` |
| Hitungan | `post_count`, `posts_in_sample` |
| Interaksi | `likes_sum`, `comments_sum`, `shares_sum`, `saves_sum`, `views_sum` |
| Engagement | `engagement_sum`, `engagement_public_sum` |
| ER | `followers_denom_sum`, `er_followers_daily` |
| BLOCKED | `reach_sum`, `er_reach_daily` |
| Jejak | `created_at`, `updated_at` |

Nilai `media_type` dipakai **apa adanya** dari `unified_post`: Instagram
`carousel_container` / `clips` / `feed`, TikTok `VIDEO` / `CAROUSEL`. Sengaja
tidak dinormalisasi jadi label bersama — pemetaannya keputusan produk yang belum
diambil.

Komponen additive-nya sengaja sama dengan `kol_metric_daily` supaya ER per format
dihitung dengan cara yang sama dan hasilnya bisa direkonsiliasi.

---

### F. `audience_demographics_daily` — 10 kolom · `SCHEMA READY` · **EMPTY, 0 baris**

Menampung **demografi audiens per akun, platform, dan hari**.

**Grain** `(social_account_id, platform, audience_date, audience_type,
dimension_key)`.
**Sumber** `l1_silver.unified_audience`, disaring `audience_type IN ('age',
'gender')`.

**Seluruh 10 kolom:**

| Kolom | Tipe | Null | Isi |
|---|---|---|---|
| `id` | `uuid` | NOT NULL | kunci teknis |
| `social_account_id` | `uuid` | NOT NULL | KOL |
| `platform` | `varchar(30)` | NOT NULL | platform |
| `audience_date` | `date` | NOT NULL | tanggal snapshot audiens |
| `audience_type` | `varchar(30)` | NOT NULL | jenis demografi — `age` atau `gender` |
| `dimension_key` | `varchar(100)` | NOT NULL | bucket-nya, mis. `18-24`, `F` |
| `audience_count` | `numeric` | null | nilai dari `unified_audience.value` |
| `confidence` | `varchar(30)` | null | `measured` / `estimated` |
| `created_at` | `timestamptz` | NOT NULL | jejak |
| `updated_at` | `timestamptz` | NOT NULL | jejak |

**Kenapa EAV, bukan kolom tetap.** Bucket demografi ditentukan Instagram, bukan
kita, dan bisa berubah. Mem-pivot jadi kolom tetap (`age_18_24`, `gender_female`,
…) akan mengunci nama bucket di DDL. Sumber kita (`unified_audience`) memang
sudah ternormalisasi `audience_type`/`dimension_key`/`value`, jadi bentuk EAV
mengikuti sumber apa adanya.

Hanya `age` dan `gender` yang didokumentasikan di sini karena hanya keduanya yang
dihasilkan pipeline — lihat H.

---

### G. `audience_geo_daily` — 10 kolom · `SCHEMA READY` · **EMPTY, 0 baris**

Menampung **distribusi geografis audiens**.

**Grain** `(social_account_id, platform, audience_date, geo_level, geo_key)`.
**Sumber** `l1_silver.unified_audience`, disaring `audience_type IN ('country',
'city')`.

**Seluruh 10 kolom:**

| Kolom | Tipe | Null | Isi |
|---|---|---|---|
| `id` | `uuid` | NOT NULL | kunci teknis |
| `social_account_id` | `uuid` | NOT NULL | KOL |
| `platform` | `varchar(30)` | NOT NULL | platform |
| `audience_date` | `date` | NOT NULL | tanggal snapshot audiens |
| `geo_level` | `varchar(30)` | NOT NULL | `country` atau `city` — dari `audience_type` |
| `geo_key` | `varchar(255)` | NOT NULL | nilai lokasinya, mis. `ID`, `Jakarta` — dari `dimension_key` |
| `audience_count` | `numeric` | null | nilai dari `unified_audience.value` |
| `confidence` | `varchar(30)` | null | `measured` / `estimated` |
| `created_at` | `timestamptz` | NOT NULL | jejak |
| `updated_at` | `timestamptz` | NOT NULL | jejak |

Bentuk EAV dipakai dengan alasan yang sama seperti demografi: daftar kota dan
negara ditentukan Instagram dan panjangnya tidak terbatas, jadi tidak bisa
dijadikan kolom tetap.

---

### H. `audience_interest_daily` — 9 kolom · `SCHEMA READY` · **NO SOURCE DATA YET**

Disiapkan untuk **distribusi minat audiens per akun, platform, dan hari**.

**Grain** `(social_account_id, platform, audience_date, interest_key)`.

**Seluruh 9 kolom:**

| Kolom | Tipe | Null | Isi |
|---|---|---|---|
| `id` | `uuid` | NOT NULL | kunci teknis |
| `social_account_id` | `uuid` | NOT NULL | KOL |
| `platform` | `varchar(30)` | NOT NULL | platform |
| `audience_date` | `date` | NOT NULL | tanggal snapshot audiens |
| `interest_key` | `varchar(255)` | NOT NULL | label minat |
| `audience_count` | `numeric` | null | jumlah/bobot audiens untuk minat itu |
| `confidence` | `varchar(30)` | null | `measured` / `estimated` |
| `created_at` | `timestamptz` | NOT NULL | jejak |
| `updated_at` | `timestamptz` | NOT NULL | jejak |

> **Schema sudah tersedia sebagai requirement L2, tetapi source data interest
> belum tersedia pada pipeline L0/L1 saat ini.**

Ini **bukan** kasus "ETL-nya belum dibuat". Jalur audience yang ada:

```
l0_raw.ig_profile_official.demographics_{age,city,country,gender}   (4 kolom jsonb)
   → sp_sync_instagram_audience() menghasilkan audience_type:
     'age', 'gender', 'country', 'city'        ← HANYA EMPAT NILAI INI
   → l0_harmonization.instagram_audience → l1_silver.unified_audience
```

Pencarian kolom bernama `%interest%` di seluruh `l0_raw`, `l0_harmonization`, dan
`l1_silver` mengembalikan **0 kolom**. Jadi berapa kali pun pipeline dijalankan,
tabel ini tidak akan terisi.

Tabelnya tetap dibuat karena SCRUM-521 memintanya dan UI menyebut `interests`,
supaya begitu sumber minat audiens tersedia, datanya punya rumah dan pola
pengisiannya sudah sejajar dengan dua tabel audience lain.

---

### Status backlog — schema vs data pipeline

Dibedakan sengaja: **tabel/schema sudah dibuat ≠ ETL/data pipeline sudah selesai.**

| Ticket | Tabel | Schema | Data pipeline |
|---|---|---|---|
| SCRUM-513 | `kol_metric_daily` | **DONE** | **DONE** — asset Dagster aktif, 160 baris |
| SCRUM-516 | `kol_metric_monthly` | **DONE** | **DONE** — asset Dagster aktif, 53 baris |
| SCRUM-515 | `post_metric` | **DONE** | **NOT STARTED** — sumber siap, asset belum ada |
| SCRUM-514 | `kol_profile_card` | **DONE** | **NOT STARTED** — sumber siap, asset belum ada |
| SCRUM-517/518 | `content_format_daily` | **DONE** | **NOT STARTED** — sumber siap, asset belum ada |
| SCRUM-519 | `audience_demographics_daily` | **DONE** | **WAITING FOR SOURCE** — `unified_audience` 0 baris |
| SCRUM-520 | `audience_geo_daily` | **DONE** | **WAITING FOR SOURCE** — `unified_audience` 0 baris |
| SCRUM-521 | `audience_interest_daily` | **DONE** | **BLOCKED** — sumber interest tidak ada di L0/L1 mana pun |

SCRUM-491 ("hasil dari skema feature") bukan tabel; tidak dibuatkan apa pun.

### Tabel yang SENGAJA tidak dibuat

Database referensi punya tabel Gold lain — `posting_time_heatmap`,
`post_wordcloud`, `ugc_tagged_posts`, `pillar_performance_daily`, `story_*`,
`comment_*`, `competitor_*`. **Tidak satu pun muncul di backlog project ini**,
jadi tidak dibuat. Menambahkannya berarti mengarang requirement.

---

## Lampiran — Cara memverifikasi ulang dokumen ini

```sql
-- Volume post
SELECT (SELECT count(*) FROM l0_raw.ig_media_snapshots_apify) ig_raw,
       (SELECT count(*) FROM l0_raw.tt_video_apify)           tt_raw,
       (SELECT count(*) FROM l0_harmonization.instagram_post) ig_harm,
       (SELECT count(*) FROM l0_harmonization.tiktok_post)    tt_harm,
       (SELECT count(*) FROM l1_silver.unified_post)          l1;

-- Integritas L1
SELECT count(*) FILTER (WHERE sa.id IS NULL)                    fk_orphan,
       count(*) FILTER (WHERE up.platform_id <> sa.platform_id) platform_mismatch
FROM l1_silver.unified_post up
LEFT JOIN public.social_account sa ON sa.id = up.social_account_id;

-- L2 benar-benar kosong
SELECT count(*) AS procedure_di_schema_feature
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'feature';   -- 0

-- Sentinel likes = -1
SELECT count(*) FILTER (WHERE likes = -1) FROM l1_silver.unified_post;  -- 15

-- Post kolaborasi
SELECT count(*) FROM l1_silver.unified_post up
JOIN public.social_account sa ON sa.id = up.social_account_id
WHERE lower(up.username) <> lower(sa.username);  -- 41
```
