# Alur Data L0 → L1 → Feature → L2 → UI

Database: **`kol`**. Disusun dari kode aktual — repo scraper/Dagster ini dan
branch [`devsekata/autometric@engkol_v1`](https://github.com/devsekata/autometric/tree/engkol_v1)
(aplikasi Next.js yang jadi UI-nya). Angka baris per 28 Agustus 2026, setelah run sensor pukul 14:08.

> ⚠️ **Dua database berbeda punya nama schema yang sama.**
> UI `engkol_v1` memakai dua pool:
> - `@/lib/kolDb` → database **`kol`** (`PG_*_KOL`) — inilah yang diisi pipeline ini
> - `@/lib/db` → warehouse analytics — **database lain**, kebetulan juga punya
>   schema `l1_silver` dan `l2_gold`
>
> Dokumen ini hanya soal database `kol`. Query di `postAnalytics.ts`,
> `account.ts`, `profile.ts`, `summary.ts` memakai `@/lib/db`, jadi **bukan**
> tabel yang dijelaskan di sini — walau nama schema-nya mirip.

---

## Alur Data

```
Scraping → scheduler_logs → l0_raw → Dagster Sensor → L1 → Feature → L2 → UI
```

Terurai:

```
                  ┌──────────────────────────────────────────┐
   kol_directory  │  siapa yang di-scrape (roster)           │
                  └───────────────────┬──────────────────────┘
                                      ▼
        ┌─────────────────────────────────────────────────────┐
        │  SCRAPING — dua produsen, keduanya menulis l0_raw    │
        ├─────────────────────────────────────────────────────┤
        │ A. scheduler_engine.py (repo ini)                    │
        │    log → public.scheduler_logs                       │
        │ B. "Add New KOL" di UI (engkol_v1)                   │
        │    src/lib/kolDirectory/addKolScrape.ts              │
        │    log → public.add_kol_scrape_log                   │
        │          public.add_kol_pipeline_log                 │
        └───────────────────────┬─────────────────────────────┘
                                ▼
                     l0_raw.*_apify / *_official
                                │
                                ▼
   l0_raw_new_data_sensor  ── mendeteksi baris baru lewat
   (Dagster, event-based)     (count(*), max(fetched_at)) atas 8 tabel sumber
                                │
                                ▼
                     transform_chain_job  (13 asset)
                                │
        l0_harmonization ──► l1_silver ──► feature ──► l2_gold
                                │
                                ▼
                      UI engkol_v1 (Next.js)
```

**Sensor tidak pernah memanggil Apify.** Ia hanya membaca `count(*)` dan
`max(fetched_at)`, lalu menjalankan `transform_chain_job` yang isinya SQL murni.
Scraping tetap jalur terpisah. Detail: `orchestration/kol_orchestration/sensors.py`.

### Tabel log — masing-masing punya penulis sendiri

| Tabel | Penulis | Isi | Baris |
|---|---|---|---|
| `public.scheduler_logs` | `scrape_log.py` (repo ini) | 1 baris per pekerjaan (`profile`, `post`) per run scraping, sukses maupun gagal | 6 |
| `public.add_kol_scrape_log` | `stepLog.ts` (engkol_v1) | langkah scraping "Add New KOL" dari UI | 9 |
| `public.add_kol_pipeline_log` | `stepLog.ts` (engkol_v1) | langkah pipeline "Add New KOL" dari UI | 18 |

Dagster **tidak menulis** ke satu pun tabel ini. State sensor disimpan di cursor
bawaan Dagster, bukan tabel database.

### 8 tabel `l0_raw` yang dipantau sensor

| Instagram | TikTok |
|---|---|
| `ig_profile_apify` / `ig_profile_official` | `tt_profile_apify` / `tt_profile_official` |
| `ig_media_snapshots_apify` / `ig_media_snapshots_official` | `tt_video_apify` / `tt_video_official` |

Hanya ini karena hanya inilah yang dibaca keempat procedure
`l0_harmonization.sp_sync_*` di dalam `transform_chain_job`.

---

## L1 Silver

Database `kol`, schema `l1_silver`. Kolom **Lokasi/UI** menyebut route dan file
query yang benar-benar membacanya di `engkol_v1`.

| Tabel | Menampilkan apa di UI | Lokasi/UI | Sumber |
|---|---|---|---|
| `unified_profile` (2.001) | Identitas & metrik profil kreator: follower, verified, bio, avatar | Discover → KOL Directory → detail creator. `/organizations/[orgSlug]/discover/kol-directory/[kolId]` — `src/lib/discover/creatorProfiling.ts` (`LEFT JOIN l1_silver.unified_profile up ON up.social_account_id = ksa.social_account_id`) | `l1_silver.sp_build_unified_profile()` ← `l0_harmonization.instagram_profile` + `tiktok_profile` |
| `unified_post` (477) | Grid konten, jumlah post, total & rata-rata engagement, format, tanggal tayang, hashtag, jumlah post sponsored | Discover → KOL Directory → detail creator. `/…/kol-directory/[kolId]` — `kolMeasured.ts` (`getKolMeasured`), `creatorProfiling.ts`, dan `kolPostCover.ts` untuk cover image | `l1_silver.sp_build_unified_post()` ← `l0_harmonization.instagram_post` + `tiktok_post` |
| `unified_rate_card` (9.210) | Harga minimum & jumlah deliverable pada kartu listing dan halaman detail | `/…/discover/kol-directory` (listing) dan `[kolId]` — `kolDirectory.ts` (`listKolDirectory`, `getKolCreator`), `kolMeasured.ts` | `l1_silver.sp_build_unified_rate_card()` ← `l0_harmonization.*_rate_card` ← `l0_raw.kol_roster_import` |
| `unified_follower` (2.548) | **Belum dibaca UI.** UI mengecek keberadaan follower langsung ke `l0_raw.ig_followers_apify` / `tt_followers_apify` (`addKolCheck.ts`) | — | `l1_silver.sp_build_unified_follower()` ← `l0_harmonization.instagram_follower` + `tiktok_follower` |
| `unified_audience` (0) | Belum ada data, belum dibaca UI | — | `l1_silver.sp_build_unified_audience()` — sumber `l0_raw` masih kosong |
| `unified_comment` (0) | Belum ada data, belum dibaca UI | — | `l1_silver.sp_build_unified_comment()` — sumber `l0_raw` masih kosong |
| `unified_story` (0) | Belum ada data, belum dibaca UI | — | `l1_silver.sp_build_unified_story()` — sumber `l0_raw` masih kosong |
| `unified_tagged_post` (0) | Belum ada data, belum dibaca UI | — | `l1_silver.sp_build_unified_tagged_post()` — sumber `l0_raw` masih kosong |

**Catatan `unified_rate_card`:** tabel ini **tidak** ikut di `transform_chain_job`.
Sumbernya `l0_raw.kol_roster_import` (impor roster), bukan hasil scraping, jadi
sensor `l0_raw` tidak memicunya. Pengisiannya lewat `sp_sync_roster_rate_card` +
`sp_build_unified_rate_card` yang dijalankan terpisah.

**Catatan `unified_competitor_post` — BUKAN tabel database `kol`.**
`l1_silver.unified_competitor_post` memang dibaca UI (`profile.ts`, `account.ts`,
`postAnalytics.ts`), tapi lewat `pool` dari `@/lib/db` — **warehouse analytics**,
bukan `kolDb()`. Di database `kol` tabel itu **tidak ada**: schema `l1_silver`
di sini hanya berisi 8 tabel di atas. Jangan dimasukkan ke daftar L1 pipeline
ini; keduanya kebetulan bernama schema sama.

---

## L2 Gold

Database `kol`, schema `l2_gold`.

> **Status 28 Agustus 2026: 6 dari 8 tabel L2 sudah tersambung ke UI.**
> Sebelumnya nol — semua query `kolDb()` berhenti di `l1_silver` dan `public`.
> Sambungannya lewat service baru `src/lib/discover/kolGold.ts` di repo UI, yang
> masuk `KolCreatorPayload.gold` dan dibaca tiga section di halaman
> `/…/discover/kol-directory/[kolId]`.
>
> ⚠️ **Perubahan itu masih UNCOMMITTED** di clone lokal
> `D:\intern\autometric` (branch `engkol_v1`, HEAD `24d76b6`). Belum di-commit,
> belum di-push, jadi belum ada di branch remote. Bagian di bawah menjelaskan
> keadaan clone itu, bukan keadaan branch di GitHub.
>
> Dua tabel sisanya (`content_format_daily`, `post_metric`) sengaja TIDAK
> disambungkan: keduanya 0 baris, jadi query-nya hanya menambah round-trip untuk
> selalu mengembalikan kosong.
>
> Yang tetap berlaku: `postAnalytics.ts` menyebut
> `l2_gold.comment_sentiment_post`, tapi itu lewat `@/lib/db` (warehouse) dan
> tabel itu **tidak ada** di database `kol`.

Kolom "Data/kolom yang ditampilkan" hanya memuat kolom yang **benar-benar
terisi** di database per 28 Agustus 2026 — persentasenya diukur langsung, bukan
diperkirakan. Kolom yang NULL 100% ditulis terpisah, dan UI memang **tidak
merender tile untuk kolom NULL** supaya tidak ada angka yang mengaku terukur.

| Tabel | Menampilkan apa di UI | Lokasi/UI (✅ = sudah tersambung) | Data/kolom yang ditampilkan | Sumber |
|---|---|---|---|---|
| `kol_profile_card` (1.976) | **Kartu ringkasan profil KOL** — dipakai sebagai header halaman detail dan sebagai kartu di grid listing. Paling siap pakai dari semua tabel L2: hampir semua kolomnya terisi | ✅ **Tersambung.** `[kolId]` → tab **Profile**, kartu "Profile Snapshot (terukur, L2 Gold)" di `KolCreatorProfile.tsx`. Satu blok per akun yang dimiliki creator. *Belum dipakai di grid listing — itu langkah berikutnya.* | `username` 100%, `avatar_url` 100%, `profile_url` 100%, `is_verified` 100%, `is_private` 100%, `profile_snapshot_date` 100%, `display_name` 99%, `followers_count` 99%, `following_count` 99%, `tier` 99%, `media_count` 98%, `bio` 94%, `website` 58%.<br>**NULL 100%:** `rate_card`, `rate_card_currency`, `rate_card_min_fee`, `rate_card_max_fee`, `rate_card_post_types` — harga tetap harus diambil dari `l1_silver.unified_rate_card`. `followers_growth` hanya 1% (25/1.976) | asset `kol_profile_card` ← `l1_silver.unified_profile` |
| `kol_metric_daily` (280) | **Grafik time-series performa harian** per KOL: garis engagement dan bar jumlah post terhadap `metric_date`, plus kartu ringkasan (total post, total engagement, ER rata-rata). `metric_date` = tanggal TAYANG, bukan tanggal scrape | ✅ **Tersambung.** `[kolId]` → tab **Analytics**, kartu "Performance (terukur, L2 Gold)" grain **Harian** di `KolCreatorSections.tsx`. Tile total + `TrendChart`. *`/…/discover/compare` belum.* | `metric_date`, `post_count`, `posts_in_sample` 100%; `likes_sum`, `comments_sum`, `engagement_sum`, `engagement_public_sum` 85%; `views_sum` 71%; `shares_sum`, `saves_sum` 47%; `er_followers_daily`, `followers_denom_sum` 26%; `followers_at_post_date` 29%.<br>**NULL 100%:** `reach_sum`, `er_reach_daily` (butuh Insights API), `reposts_sum`, `followers_growth` | asset `kol_metric_daily` ← `l1_silver.unified_post` + `unified_profile` |
| `kol_metric_monthly` (68) | **Ringkasan & grafik bulanan** — bar per bulan, plus tabel per `month_year`. Sudah punya kolom kalender siap-pakai sehingga UI tidak perlu meng-`GROUP BY` tanggal sendiri. ER bulanan dihitung ulang, bukan rata-rata harian | ✅ **Tersambung.** Kartu yang sama, selector grain **Bulanan**. *`/…/discover/reports` belum.* | `month_start`, `year`, `month`, `month_year`, `quarter`, `year_quarter`, `active_days`, `post_count`, `posts_in_sample` 100%; `likes_sum`, `comments_sum`, `engagement_sum`, `engagement_public_sum` 83%; `views_sum` 64%; `followers_eom` 36%; `er_followers_monthly`, `followers_denom_sum`, `engagement_for_er_sum` 32%; `shares_sum`, `saves_sum` 30%.<br>**NULL 100%:** `reach_sum`, `er_reach_monthly`, `reposts_sum`, `followers_growth` | asset `kol_metric_monthly` ← `l2_gold.kol_metric_daily` |
| `audience_demographics_daily` (69) | **Chart demografi audiens** — donut/bar proporsi audiens per `dimension_key`, dengan badge `confidence` karena angkanya hasil inferensi, bukan Insights resmi. **Gender dan umur satu tabel**, dibedakan `audience_type` | ✅ **Tersambung.** `[kolId]` → tab **Audience**, donut **Gender** di kartu "Audience Insights (terukur)". Chart **Age** sudah dikodekan tapi tidak dirender karena `audience_type='age'` masih 0 baris. *`/…/discover/audience` belum.* | Semua kolom 100% terisi: `audience_date`, `audience_type`, `dimension_key`, `audience_count`, `confidence`.<br>**Nilai yang benar-benar ada:** `audience_type` hanya `gender`; `dimension_key` hanya `female`, `male`, `unknown`. **Chart umur belum bisa dibuat** — `audience_type='age'` belum ada satu baris pun | asset `audience_gold` ← `feature.{ig,tt}_audience_analysis` |
| `audience_geo_daily` (181) | **Peta / bar sebaran lokasi audiens.** Dua tingkat dalam satu tabel lewat `geo_level`: peta choropleth untuk `country`, bar Top-N untuk `city` | ✅ **Tersambung.** Kartu yang sama → bar **Top Countries** (`geo_level='country'`) dan **Top Cities** (`'city'`). *Peta choropleth dan `/…/discover/audience` belum.* | Semua kolom 100%: `audience_date`, `geo_level`, `geo_key`, `audience_count`, `confidence`.<br>**Cakupan nyata:** `country` 113 baris / 32 negara unik; `city` 68 baris / 33 kota unik | asset `audience_gold` ← `feature.{ig,tt}_audience_analysis` |
| `audience_interest_daily` (214) | **Daftar / bar chart minat audiens** per `interest_key`, diurut `audience_count`. Cocok juga jadi tag cloud atau chip filter di pencarian KOL | ✅ **Tersambung.** Kartu yang sama → chips **Audience Interests** dengan persentase. *Filter minat di listing belum.* | Semua kolom 100%: `audience_date`, `interest_key`, `audience_count`, `confidence`.<br>**Nilai terbanyak:** `unknown` (23), `religion` (22), `parenting` (21), `business` (17), `food` (14), `music` (13), `entertainment` (12), `beauty` (11). Perhatikan `unknown` justru teratas — UI sebaiknya menyembunyikannya atau menandainya "tidak terklasifikasi" | asset `audience_gold` ← `feature.{ig,tt}_audience_analysis` |
| `content_format_daily` (0) | **Breakdown format konten per hari** — stacked bar `post_count` per `media_type` terhadap `metric_date`, plus perbandingan ER antar format ("Reels vs Carousel mana yang lebih perform"). Kolomnya cermin `kol_metric_daily`, hanya ditambah dimensi `media_type` | ❌ **Sengaja tidak disambungkan** — 0 baris. Rekomendasi kalau nanti terisi: tab **Content** di `[kolId]` dan `/…/discover/content` | **BELUM ADA DATA (0 baris).** Kolom yang tersedia kalau nanti diisi: `metric_date`, `media_type`, `post_count`, `posts_in_sample`, `likes_sum`, `comments_sum`, `shares_sum`, `saves_sum`, `views_sum`, `engagement_sum`, `engagement_public_sum`, `followers_denom_sum`, `er_followers_daily`, `reach_sum`, `er_reach_daily` | **belum diisi asset mana pun** — tidak ada asset Dagster yang menulis ke sini |
| `post_metric` (0) | **Tabel detail performa per post** — satu baris per konten, bisa diurut `rank_in_account` atau `er_followers`, dengan link `permalink` dan chip `top_hashtags`. Ini yang paling cocok jadi tabel "Top Posts" yang bisa di-sort | ❌ **Sengaja tidak disambungkan** — 0 baris. Rekomendasi kalau nanti terisi: tab **Content** di `[kolId]` (tabel di bawah grid) | **BELUM ADA DATA (0 baris).** Kolom yang tersedia kalau nanti diisi: `content_id`, `posted_at`, `post_date`, `media_type`, `is_sponsored`, `permalink`, `likes_hidden`, `is_collaboration`, `likes`, `comments`, `shares`, `saves`, `views`, `engagement_owned`, `engagement_public`, `followers_at_post_date`, `er_followers`, `rank_in_account`, `top_hashtags`, `reach`, `er_reach`, `reposts`, `avg_watch_time_seconds`, `completion_rate` | **belum diisi asset mana pun.** Sementara ini `feature.{ig,tt}_post_analysis` yang memegang peran serupa |

### Jalur L2 → Backend → UI

```
l2_gold.*  ──►  src/lib/discover/kolGold.ts        getKolGold(kolId)
                     │  7 query paralel, join lewat public.kol_social_account
                     ▼
                src/lib/discover/kolDirectory.ts   KolCreatorPayload.gold
                     ▼
                GET /api/organizations/[id]/discover/kol-directory/[kolId]
                     ▼
                KolCreatorWorkspace  ──►  SectionProps.gold
                     ├─ ProfileSection    (KolCreatorProfile.tsx)   kol_profile_card
                     ├─ PerformanceSection(KolCreatorSections.tsx)  kol_metric_daily/_monthly
                     └─ AudienceSection   (KolCreatorSections.tsx)  audience_*_daily
```

Tidak ada route API baru — L2 menumpang payload yang sudah ada, sama seperti
`measured` (L1). File yang disentuh di repo UI:

| File | Perubahan |
|---|---|
| `src/lib/discover/kolGold.ts` | **baru** — service L2 |
| `src/lib/discover/kolDirectory.ts` | `getKolGold()` masuk `Promise.all`, field `gold` di payload |
| `src/components/discover/KolCreatorSections.tsx` | `gold` di `SectionProps`; Performance + Audience |
| `src/components/discover/KolCreatorProfile.tsx` | kartu Profile Snapshot |
| `src/components/discover/KolCreatorWorkspace.tsx` | meneruskan `gold` ke `sectionProps` |


**Tiga keputusan yang lahir dari data nyata, bukan dari asumsi:**

1. **`confidence` adalah LABEL, bukan angka.** Kolomnya `character varying` berisi
   `inferred_high` / `inferred_medium` / `inferred_low`. `AVG()` atasnya gagal di
   Postgres; dipakai `MODE() WITHIN GROUP`. UI menampilkannya sebagai kata
   ("keyakinan rendah") — mengubahnya jadi "83%" akan mengarang presisi.

2. **Kolom `date` jangan lewat `toIso().slice(0,10)`.** node-pg mem-parse `date`
   jadi Date tengah-malam **lokal**; konversi ke UTC memundurkannya sehari di
   zona timur Greenwich (`2026-07-13` sempat jadi `2026-07-12`). Dipakai helper
   `toDateOnly()` yang membaca komponen lokal.

3. **`unknown` dipisahkan dari chart.** Ia bucket TERBESAR hampir di mana-mana —
   61% gender, 90% country, 78% interest. Irisan dihitung dari audiens
   **terklasifikasi**, dan cakupannya ditulis di bawah chart ("Hanya 10% audiens
   yang bisa diklasifikasi"). Tanpa itu, "ID 70%" menyembunyikan bahwa 70% itu
   dari 10%.

Selain itu: tile untuk kolom yang NULL 100% **tidak dirender sama sekali**, dan
`reach` tidak ditawarkan sebagai pilihan metrik grafik karena `reach_sum` NULL di
seluruh baris. Harga tetap dari `l1_silver.unified_rate_card`, bukan dari kolom
`rate_card*` di `kol_profile_card` yang NULL semua — satu angka, satu sumber.

**Nama tabel L2 yang sering salah tulis.** Beberapa nama yang terdengar wajar
TIDAK ada di database `kol` — kalau muncul di dokumen lain, ini padanan yang benar:

| Sering ditulis | Yang sebenarnya ada |
|---|---|
| `audience_gender_daily` | `audience_demographics_daily` dengan `audience_type='gender'` |
| `audience_age_daily` | `audience_demographics_daily` dengan `audience_type='age'` (belum terisi) |
| `audience_location_daily` | `audience_geo_daily` (kolom `geo_level`) |
| `kol_engagement_summary` | **tidak ada.** Yang paling dekat: `feature.{ig,tt}_engagement_analysis` (layer Feature, bukan L2) dan `l2_gold.kol_metric_monthly` |
| `comment_sentiment_post` | ada di **warehouse** (`@/lib/db`), bukan di `kol` |

---

---

## Feature Layer

Lapisan antara L1 dan L2, schema `feature` di database `kol`. **Tidak satu pun
dibaca langsung oleh UI `engkol_v1`** — semua query UI berhenti di `l1_silver`
dan `public`. Jadi kolom "Menampilkan apa di UI" di sini juga berisi rancangan.

Statusnya dibedakan tiga:

| Status | Tabel |
|---|---|
| 🟢 **Sudah dipakai UI** | *(tidak ada)* |
| 🟡 **Belum dipakai UI, datanya ADA** | `ig_engagement_analysis`, `tt_engagement_analysis`, `ig_post_analysis`, `tt_post_analysis`, `ig_audience_analysis`, `tt_audience_analysis` |
| 🔴 **Belum dipakai UI, datanya KOSONG** | `brand_fit_analysis`, `ig_comments_analysis`, `tt_comments_analysis` |

### 🟡 Datanya sudah ada

| Tabel | Menampilkan apa di UI (rancangan) | Rekomendasi lokasi/UI | Data/kolom yang ditampilkan | Sumber |
|---|---|---|---|---|
| `ig_engagement_analysis` (19) | **Kartu ringkasan engagement per akun Instagram** — angka besar ER, total likes/comments, jumlah post yang dianalisis, plus heatmap jam posting terbaik dan breakdown performa per format | Panel ringkasan di atas tab **Performance**, `/…/discover/kol-directory/[kolId]` | `posts_analyzed_count`, `analyzed_at` 100%; `total_likes`, `total_comments`, `format_performance` (jsonb), `best_posting_time_heatmap` (jsonb) 89%; `reel_plays` 84%; `engagement_rate` 63%.<br>**NULL 100%:** `total_shares`, `total_saves`, `engagement_trend`, `reel_shares`, `story_replies`, `story_exits_rate` — semuanya butuh Insights API | `l1_silver.unified_post` + `unified_profile` (asset `ig_engagement_analysis`) |
| `tt_engagement_analysis` (11) | Sama seperti di atas untuk TikTok, dan **lebih lengkap** — shares/saves/views terisi penuh karena data publik TikTok memuatnya | Panel yang sama, untuk KOL berplatform TikTok | `videos_analyzed_count`, `total_views`, `total_likes`, `total_comments`, `total_shares`, `total_saves`, `best_posting_time_heatmap` **100%**; `engagement_rate` 90%.<br>**NULL 100%:** `engagement_trend` | `l1_silver.unified_post` + `unified_profile` (asset `tt_engagement_analysis`) |
| `ig_post_analysis` (186) | **Tabel/grid per post Instagram** — daftar konten dengan chip hashtag, penanda sponsored, tipe media, dan peringkat. Peran ini yang seharusnya diambil `l2_gold.post_metric`, tapi sementara tabel inilah satu-satunya yang berisi | Tab **Content** di `[kolId]`, di bawah grid konten | `media_id`, `posted_at` 100%; `media_type` 95%; `is_sponsored` 94%; `top_hashtags` (jsonb) 37%; `engagement_rate` dan `rank` 24%.<br>**NULL 100%:** `content_category`, `category_percentage`, `avg_watch_time_seconds`, `click_through_rate`, `sentiment_breakdown`, `ai_recommendation`, `reach`.<br>⚠️ `engagement_rate` hanya 24% — kalau ditampilkan sebagai kolom tabel, mayoritas barisnya kosong | `l1_silver.unified_post` (asset `ig_post_analysis`) |
| `tt_post_analysis` (291) | Sama untuk TikTok. Hashtag jauh lebih lengkap daripada Instagram, jadi tag cloud per KOL paling layak dibangun dari sini | Tab **Content** di `[kolId]` | `video_id`, `posted_at`, `media_type`, `is_sponsored` 100%; `top_hashtags` **81%**; `engagement_rate` dan `rank` 32%.<br>**NULL 100%:** `content_category`, `top_sound`, `avg_watch_time_seconds`, `completion_rate`, `traffic_source`, `sentiment_breakdown`, `ai_recommendation` | `l1_silver.unified_post` (asset `tt_post_analysis`) |
| `ig_audience_analysis` (13) | **Panel kualitas audiens** — tiga skor (quality / authenticity / follower quality) sebagai gauge, plus donut gender, daftar minat, dan sebaran geo. Ini sumber hulu tiga tabel `l2_gold.audience_*`; untuk chart, baca versi L2-nya yang sudah dinormalisasi per baris | Tab **Audience** di `[kolId]`. Untuk chart pakai `l2_gold.audience_*`; tabel ini untuk skor agregat yang tidak ada di L2 | `audience_quality_score`, `authenticity_score`, `follower_quality_score`, `gender_breakdown` (jsonb), `top_interest` (jsonb), `geo_distribution` (jsonb) — semuanya **100%**.<br>**NULL 100%:** `age_gender_breakdown`, `active_hours_heatmap`, `avg_reach`, `cpe`, `emv` | `audience_inference.py` (asset `audience_feature`) ← `l0_raw.ig_followers_apify` |
| `tt_audience_analysis` (10) | Sama untuk TikTok | Tab **Audience** di `[kolId]` | Kolom dan tingkat isian identik dengan versi Instagram: 6 kolom 100%, 5 kolom NULL | `audience_inference.py` (asset `audience_feature`) ← `l0_raw.tt_followers_apify` |

### 🔴 Datanya masih kosong

| Tabel | Menampilkan apa di UI (rancangan) | Rekomendasi lokasi/UI | Data/kolom yang tersedia | Sumber |
|---|---|---|---|---|
| `brand_fit_analysis` (0) | **Skor kecocokan KOL dengan brand** — kartu skor kemitraan, radar sub-skor, persen irisan audiens, dan daftar rekomendasi. Satu-satunya tabel yang grain-nya *pasangan* KOL×brand, bukan per akun | `/…/discover/campaign-management` atau panel "Fit" di `[kolId]` saat sedang melihat konteks brand tertentu | **BELUM ADA DATA.** Kolom: `agency_kol_account_id`, `brand_id`, `partnership_score`, `sub_scores` (jsonb), `audience_overlap_pct`, `overlap_summary`, `category_fit_tags`, `recommendations` | **belum diisi asset mana pun** |
| `ig_comments_analysis` (0) | **Analisis komentar per post** — donut sentimen (positif/netral/negatif), indikator spam & toksisitas, word cloud, emoji teratas, topik, dan ringkasan AI | Panel di dalam detail post pada tab **Content** `[kolId]` | **BELUM ADA DATA.** Kolom: `media_id`, `comments_analyzed_count`, `sentiment_positive_pct`, `sentiment_neutral_pct`, `sentiment_negative_pct`, `spam_detected_pct`, `toxicity_pct`, `word_cloud`, `emoji_analysis`, `top_topics`, `ai_comment_summary` | **belum diisi asset mana pun.** Sumber hulunya `l0_raw.ig_comments_apify` juga masih 0 baris |
| `tt_comments_analysis` (0) | Sama untuk TikTok (grain `video_id`) | Panel yang sama untuk konten TikTok | **BELUM ADA DATA.** Kolom sama dengan versi Instagram, dengan `video_id` menggantikan `media_id` | **belum diisi asset mana pun.** `l0_raw.tt_comments_apify` juga 0 baris |

**Catatan penting soal cakupan asset.** Dari 9 tabel `feature`, hanya **4** yang
ikut di `transform_chain_job`: `ig/tt_engagement_analysis` dan
`ig/tt_post_analysis`. Dua tabel audiens diisi asset `audience_feature` yang
terdaftar di Dagster tapi **di luar** rantai sensor, dan tiga tabel sisanya tidak
punya asset sama sekali. Jadi data baru dari scraping **tidak** otomatis
memperbarui tabel audiens — itu harus dijalankan terpisah.

**Run sensor menutup backlog, bukan cuma mengolah data baru.** Run 28 Agustus
14:08 dipicu oleh 11 baris baru milik satu akun Instagram, tapi karena
`transform_chain_job` menghitung ulang seluruh tabel, `tt_post_analysis` ikut
naik **91 → 291** — 200 post TikTok yang sudah lama ada di L1 tapi belum pernah
masuk layer Feature. Sesudah run, cakupannya pas 1:1 per platform:

| | `l1_silver.unified_post` | `feature.*_post_analysis` |
|---|---:|---:|
| Instagram | 186 | 186 |
| TikTok | 291 | 291 |

Jadi jangan membaca delta total sebagai "dampak akun baru". Untuk itu, lihat
kolom per-akun di tabel L1/L2 di atas.

---

## Isi `transform_chain_job` (13 asset)

Urutan dijaga Dagster lewat `deps` antar-asset, bukan urutan daftar.

```
l0_harmonization   instagram_profile   tiktok_profile   instagram_post   tiktok_post
                          │                 │                │              │
l1_silver          unified_profile ─────────┘                │              │
                          └──────► unified_post ◄────────────┴──────────────┘
                                        │
feature            ig/tt_engagement_analysis   ig/tt_post_analysis
l2_gold            kol_profile_card   kol_metric_daily ──► kol_metric_monthly
```

Asset follower (`instagram_follower`, `tiktok_follower`, `unified_follower`) dan
audiens (`audience_feature`, `audience_gold`) terdaftar di Dagster tapi **tidak**
termasuk 13 asset `transform_chain_job` — dijalankan terpisah.

---

## Status verifikasi end-to-end

| Segmen | Status | Bukti |
|---|---|---|
| `kol_directory` → scraping | ✅ terverifikasi | `select_profile_target()` lewat `kol_directory → kol_social_account → social_account`; 3 run scraping tercatat |
| scraping → `scheduler_logs` | ✅ terverifikasi | 6 baris, termasuk 2 kegagalan lengkap dengan `error_message` |
| scraping → `l0_raw` | ✅ terverifikasi (positif & negatif) | `niacnofitasari` 27 Ags: 1 profil + 10 post masuk. Dua run TikTok 28 Ags gagal: 0 baris masuk, tidak ada data sampah |
| `l0_raw` → sensor | ✅ terverifikasi (negatif) | L0 tidak berubah ⇒ sensor tetap `SKIPPED`, `runIds=[]`, run Dagster tetap 7 |
| sensor → L1 → Feature → L2 | ⚠️ belum diuji dengan data baru | Butuh satu scraping yang benar-benar mendarat di L0. Tabel L1/Feature/L2 sudah terisi dari muatan awal, tapi belum pernah diisi lewat pemicu sensor |
| L1 → UI | ✅ terverifikasi lewat kode | `unified_profile`, `unified_post`, `unified_rate_card` dibaca `kolDirectory.ts`, `kolMeasured.ts`, `creatorProfiling.ts`, `kolPostCover.ts` |
| L2 → UI | ✅ terverifikasi di browser | 6 tabel dibaca `src/lib/discover/kolGold.ts`, dirender 3 section di `[kolId]`. Diverifikasi dengan screenshot headless Chrome pada data nyata: kartu profil `@irwansyah_15` 14.9M followers, grafik harian `mel_josh_claire` 2026-07-13…08-28 (Post 8, Engagement 13K, Views 350,9K), donut gender female 71,8%/male 28,2%. **Masih uncommitted di clone lokal** |

### Kenapa dua scraping 28 Agustus gagal

Dibaca read-only dari dataset run Apify yang sudah selesai (tanpa menjalankan
actor):

```
shabiraalulaadnan → error: "This profile/hashtag does not exist."
riekemeilanis23   → error: "This profile/hashtag does not exist."
```

Bukan masalah pipeline dan bukan masalah actor — `clockworks/tiktok-scraper`
sudah menghasilkan 1.058 baris profil, terakhir 27 Agustus. **Handle-nya yang
tidak ada di TikTok.** Keduanya berasal dari satu file impor roster,
`list URL_influencer Mediarumu (1)_cleaned.xlsx`, dan dari 4.087 baris TikTok di
roster itu baru 1.041 (25%) yang terbukti punya handle hidup.

Konsekuensi untuk pemilihan kandidat berikutnya: `scrape_status = NULL` hanya
berarti "belum pernah dicoba", **bukan** "handle-nya valid".
