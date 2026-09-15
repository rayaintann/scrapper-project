# Apify Actor Mapping

**Ditelusuri dari source code sampai pemanggilan actor sebenarnya, lalu
diverifikasi terhadap data yang benar-benar masuk DB `kol` (10.100.14.216)
pada 2026-09-13.** Sesi read-only. Nol perubahan code, DB, pipeline, migration,
maupun logic scraping.

Tidak ada satu pun actor ID di dokumen ini yang ditebak. Semuanya diambil dari
literal string di kode, lalu dicocokkan dengan kolom `source_actor` di
`l0_raw.*_apify` dan `public.scheduler_logs`.

---

## Summary

**5 actor unik, dipakai untuk 8 fungsi berbeda.** Semuanya ACTIVE — tidak ada
actor LEGACY yang masih terpanggil, dan tidak ada actor khusus testing.

| Actor | Owner | Fungsi yang dilayani |
|---|---|---:|
| `apify/instagram-profile-scraper` | Apify resmi | 2 |
| `apify/instagram-scraper` | Apify resmi | 2 |
| `clockworks/tiktok-scraper` | Clockworks | 2 |
| `apify/instagram-followers-following-scraper` | Apify resmi | 1 |
| `clockworks/tiktok-followers-scraper` | Clockworks | 1 |

Tiga actor melayani lebih dari satu fungsi, dan itu **bukan duplikasi** —
input yang dikirim berbeda, sehingga bentuk data yang kembali juga berbeda:

- `clockworks/tiktok-scraper` dipakai untuk profil **dan** video. Bedanya
  `resultsPerPage`: 1 untuk profil (data profil menempel di `authorMeta` tiap
  video, jadi satu video sudah cukup), N untuk scraping video.
- `apify/instagram-scraper` dipakai dengan `resultsType: "posts"` untuk post,
  dan `resultsType: "details"` untuk profil+post sekaligus.
- `apify/instagram-profile-scraper` dipakai untuk profil **KOL** dan untuk
  profil **follower** (bahan inferensi audiens). Dua populasi berbeda, dua
  tabel tujuan berbeda.

---

## Actor Mapping

| Platform | Data | Actor Apify | Actor ID/Slug | Dipanggil dari | Output yang Dipakai | Status |
|---|---|---|---|---|---|---|
| Instagram | Profile | instagram-profile-scraper | `apify/instagram-profile-scraper` | `pipeline.py:246` → `apify_ig.InstagramProfileScraper` | username, followers, following, bio, verified, posts count | **ACTIVE** |
| Instagram | Profile + Post (satu run) | instagram-scraper | `apify/instagram-scraper` | `scheduler_engine.py:355` → `apify_posts.InstagramDetailsScraper` | objek profil + `latestPosts` | **ACTIVE** |
| Instagram | Post | instagram-scraper | `apify/instagram-scraper` | `post_pipeline.py:93` → `apify_posts.InstagramPostScraper` | likes, comments, caption, hashtags, timestamp, type, videoViewCount | **ACTIVE** |
| Instagram | Followers (daftar) | instagram-followers-following-scraper | `apify/instagram-followers-following-scraper` | `scrape_followers.py:361` → `apify_followers.scrape_instagram_followers` | username follower, id, full_name | **ACTIVE** |
| Instagram | Follower profile (audience enrichment) | instagram-profile-scraper | `apify/instagram-profile-scraper` | `enrich_follower_profiles.py:168` | bio, nama, followers follower — bahan inferensi gender/lokasi/minat | **ACTIVE** |
| TikTok | Profile | tiktok-scraper | `clockworks/tiktok-scraper` | `tiktok_pipeline.py:382` → `apify_tiktok.TikTokProfileScraper` | `authorMeta`: nickName, fans, heart, video count, signature, verified | **ACTIVE** |
| TikTok | Post / Video | tiktok-scraper | `clockworks/tiktok-scraper` | `post_pipeline.py:96` dan `scheduler_engine.py:359` → `apify_posts.TikTokVideoScraper` | diggCount, commentCount, shareCount, playCount, createTimeISO, text | **ACTIVE** |
| TikTok | Followers (daftar) | tiktok-followers-scraper | `clockworks/tiktok-followers-scraper` | `scrape_followers.py:362` → `apify_followers.scrape_tiktok_followers` | username follower, id, nickname | **ACTIVE** |
| Instagram | Comments | — | **UNKNOWN** | — | — | **TIDAK ADA** |
| TikTok | Comments | — | **UNKNOWN** | — | — | **TIDAK ADA** |
| Instagram | Stories | — | **UNKNOWN** | — | — | **TIDAK ADA** |
| Instagram | Tagged posts | — | **UNKNOWN** | — | — | **TIDAK ADA** |
| Keduanya | Discovery (cari KOL baru) | — | **UNKNOWN** | — | — | **TIDAK ADA** |
| Keduanya | Audience demographics (umur/gender native) | — | **UNKNOWN** | — | — | **TIDAK ADA** |

---

## Bukti dari data yang benar-benar masuk

`l0_raw.*_apify.source_actor` — ini bukan pembacaan kode, ini catatan run yang
sudah terjadi:

| Tabel L0 | `source_actor` | Baris | Run pertama | Run terakhir |
|---|---|---:|---|---|
| `ig_profile_apify` | `apify/instagram-profile-scraper` | 953 | 2026-08-14 | 2026-09-08 |
| `ig_profile_apify` | `apify/instagram-scraper` | 6 | 2026-08-27 | 2026-08-28 |
| `ig_media_snapshots_apify` | `apify/instagram-scraper` | 287 | 2026-08-20 | 2026-09-08 |
| `ig_followers_apify` | `apify/instagram-followers-following-scraper` | 1.448 | 2026-08-26 | 2026-09-08 |
| `ig_followers_apify` | `apify/instagram-profile-scraper` | 1.263 | 2026-08-26 | 2026-08-26 |
| `tt_profile_apify` | `clockworks/tiktok-scraper` | 1.064 | 2026-08-14 | 2026-09-08 |
| `tt_video_apify` | `clockworks/tiktok-scraper` | 291 | 2026-08-20 | 2026-08-27 |
| `tt_followers_apify` | `clockworks/tiktok-followers-scraper` | 1.110 | 2026-08-26 | 2026-09-09 |
| `ig_comments_apify` | — | **0** | — | — |
| `tt_comments_apify` | — | **0** | — | — |
| `ig_stories_apify` | — | **0** | — | — |
| `ig_tagged_posts_apify` | — | **0** | — | — |

Perhatikan `ig_followers_apify`: **dua actor menulis ke tabel yang sama**, dan
itu disengaja. 1.448 baris dari actor daftar-follower (siapa saja follower-nya),
1.263 baris dari profile-scraper (seperti apa follower itu). `source_actor`
adalah yang membedakannya — `enrich_follower_profiles.py:217` menghapus hanya
barisnya sendiri saat dijalankan ulang, memakai `WHERE source_actor = %s`.

Bukti kedua, `public.scheduler_logs` — kolom `actor` diisi jalur scheduler:

| job_name | platform | category | actor | n | terakhir |
|---|---|---|---|---:|---|
| `scheduled_scrape` | instagram | profile | `apify/instagram-scraper` | 2 | 2026-08-28 |
| `scheduled_scrape` | instagram | post | `apify/instagram-scraper` | 2 | 2026-08-28 |
| `scheduled_scrape` | tiktok | profile | `clockworks/tiktok-scraper` | 2 | 2026-08-28 |
| `scheduled_scrape` | tiktok | post | `clockworks/tiktok-scraper` | 2 | 2026-08-28 |
| `profile_scrape` | instagram | profile | NULL | 1 | 2026-09-09 |
| `post_scrape` | instagram | post | NULL | 28 | 2026-09-09 |
| `followers_scrape` | tiktok | followers | NULL | 2 | 2026-09-09 |

Bukti ketiga, `public.add_kol_scrape_log` (21 baris) — ditulis di luar repo
Python ini, jadi ia saksi independen. Ketiga actor yang dicatatnya persis sama
dengan yang ditelusuri dari kode:

| platform | step | actor | status | n |
|---|---|---|---|---:|
| instagram | profile | `apify/instagram-profile-scraper` | success | 7 |
| instagram | posts | `apify/instagram-scraper` | success | 7 |
| instagram | followers | `apify/instagram-followers-following-scraper` | success | 7 |

---

## Detail per Actor

### 1. `apify/instagram-profile-scraper`

**Platform** Instagram · **Status ACTIVE** · melayani **2 fungsi**

#### Fungsi A — Profil KOL

| | |
|---|---|
| Pemanggil | `pipeline.py:246` → `InstagramProfileScraper(cfg.apify, max_charge_usd=...)` |
| Wrapper | `apify_ig.py:23` `class InstagramProfileScraper(ProfileScraper)` |
| Sumber actor ID | `config.py:14` `DEFAULT_ACTOR_ID`, dapat dioverride env `APIFY_ACTOR_ID` (`config.py:143`) |
| Input | `{"usernames": [...], "includeAboutSection": bool}` — `apify_ig.py:30` |
| Output dipakai | username, followers, following, bio, verified, jumlah post |
| Tabel tujuan | `l0_raw.ig_profile_apify` |
| Catatan perilaku | `empty_is_failure = False` — actor mengembalikan item `not_found` untuk username yang tidak ada, jadi dataset kosong memang berarti tidak ada hasil, bukan diblokir |

#### Fungsi B — Profil follower (bahan inferensi audiens)

| | |
|---|---|
| Pemanggil | `enrich_follower_profiles.py:168` |
| Actor ID | hardcoded `enrich_follower_profiles.py:90` `ACTOR_IG = "apify/instagram-profile-scraper"` — **tidak** membaca env |
| Input | sama, `{"usernames": [...]}` — memakai kelas wrapper yang sama |
| Output dipakai | bio, nama, jumlah follower dari **follower**, sebagai bahan `audience_inference.py` |
| Tabel tujuan | `l0_raw.ig_followers_apify` (dibedakan lewat `source_actor`) |
| Kenapa terpisah | Populasinya berbeda: yang di-scrape adalah follower KOL, bukan KOL-nya. Plafon biayanya juga diturunkan dari plafon total yang disetujui, bukan dari rumus di `pipeline.py` |

---

### 2. `apify/instagram-scraper`

**Platform** Instagram · **Status ACTIVE** · melayani **2 fungsi**

#### Fungsi A — Post (`resultsType: "posts"`)

| | |
|---|---|
| Pemanggil | `post_pipeline.py:93` `_build_scraper()` → `InstagramPostScraper(cfg.apify, results_limit=...)` |
| Wrapper | `apify_posts.py:50` `class InstagramPostScraper(ProfileScraper)` |
| Sumber actor ID | `apify_posts.py:27` `DEFAULT_IG_POST_ACTOR`. **Meng-override** `cfg.apify.actor_id` di `apify_posts.py:63` — jadi env `APIFY_ACTOR_ID` tidak berlaku di jalur post |
| Input | `{"directUrls": ["https://www.instagram.com/<u>/"], "resultsType": "posts", "resultsLimit": N, "searchType": "user", "addParentData": false}` |
| Output dipakai | likes, comments count, caption, hashtags, timestamp, type, videoViewCount |
| Tabel tujuan | `l0_raw.ig_media_snapshots_apify` |

#### Fungsi B — Profil + post sekaligus (`resultsType: "details"`)

| | |
|---|---|
| Pemanggil | `scheduler_engine.py:355` → `InstagramDetailsScraper(cfg.apify, results_limit=POSTS_PER_TARGET)` |
| Wrapper | `apify_posts.py:90` `class InstagramDetailsScraper(ProfileScraper)` |
| Sumber actor ID | `scheduler_engine.py:117` `PLATFORM_TABLES["instagram"]["actor"] = DEFAULT_IG_POST_ACTOR` |
| Input | sama seperti di atas kecuali `"resultsType": "details"` |
| Output dipakai | objek profil lengkap + array `latestPosts` |
| Tabel tujuan | `l0_raw.ig_profile_apify` **dan** `l0_raw.ig_media_snapshots_apify` dari satu run |
| Catatan penting | `scheduler_engine.actor_for()` (baris 129–140) **sengaja tidak membaca** `APIFY_ACTOR_ID`/`TIKTOK_ACTOR_ID`. Docstring-nya menyebut alasannya: *"bentuk data yang masuk l0_raw tidak boleh berubah diam-diam"*, dan menyatakan eksplisit bahwa `apify/instagram-profile-scraper` **tidak** dipakai di jalur ini |

---

### 3. `clockworks/tiktok-scraper`

**Platform** TikTok · **Status ACTIVE** · melayani **2 fungsi**

#### Fungsi A — Profil

| | |
|---|---|
| Pemanggil | `tiktok_pipeline.py:382` → `TikTokProfileScraper(cfg.tiktok, max_charge_usd=...)` |
| Wrapper | `apify_tiktok.py:11` `class TikTokProfileScraper(ProfileScraper)` |
| Sumber actor ID | `config.py:15` `DEFAULT_TIKTOK_ACTOR_ID`, override env `TIKTOK_ACTOR_ID` (`config.py:150`) |
| Input | `{"profiles": [...], "profileScrapeSections": ["videos"], "resultsPerPage": 1, "excludePinnedPosts": false, shouldDownload*: false}` + `proxyCountryCode` bila diset |
| Output dipakai | `authorMeta`: nickName, fans, heart, jumlah video, signature, verified |
| Tabel tujuan | `l0_raw.tt_profile_apify` |
| Kenapa `resultsPerPage: 1` | Data profil menempel di `authorMeta` tiap video, jadi satu video sudah cukup — dan tiap video dihitung satu hasil berbayar. Default env `TIKTOK_RESULTS_PER_PAGE` = 1 (`config.py:152`) |
| Catatan perilaku | `empty_is_failure = True` — actor tetap melaporkan SUCCEEDED walau seluruh request diblokir TikTok, jadi dataset kosong diperlakukan sebagai kegagalan yang layak retry. `min_charge_usd = 0.50` karena actor menolak plafon di bawah itu. Tanpa residential proxy, hampir semua request diblokir |

#### Fungsi B — Video / post

| | |
|---|---|
| Pemanggil | `post_pipeline.py:96` dan `scheduler_engine.py:359` → `TikTokVideoScraper(cfg.tiktok, results_per_page=N)` |
| Wrapper | `apify_posts.py:169` `class TikTokVideoScraper(ProfileScraper)` |
| Sumber actor ID | `apify_posts.py:183` — `cfg.actor_id` dulu, fallback `DEFAULT_TT_VIDEO_ACTOR`; `scheduler_engine.py:123` memakai `DEFAULT_TT_VIDEO_ACTOR` langsung |
| Input | sama, tapi `resultsPerPage` = N video per profil |
| Output dipakai | diggCount, commentCount, shareCount, playCount, createTimeISO, text |
| Tabel tujuan | `l0_raw.tt_video_apify` |

**Actor-nya sama persis dengan Fungsi A; yang membedakan hanya `resultsPerPage`
dan tabel tujuan.** Karena itu keduanya ditulis terpisah di sini.

---

### 4. `apify/instagram-followers-following-scraper`

| | |
|---|---|
| **Platform** | Instagram · **Fungsi** daftar follower · **Status ACTIVE** |
| Pemanggil | `scrape_followers.py:361` → `apify_followers.scrape_instagram_followers()` |
| Sumber actor ID | `apify_followers.py:73` `DEFAULT_IG_FOLLOWERS_ACTOR`; dapat dioverride lewat CLI `--ig-actor` atau env `IG_FOLLOWERS_ACTOR_ID` (`.env.example:27`) |
| Input | `{"usernames": [<satu username>], "dataToScrape": "followers", "resultsLimit": N}` — `apify_followers.py:231` |
| Output dipakai | username follower, id, full_name |
| Tabel tujuan | `l0_raw.ig_followers_apify` |
| Catatan penting | **Satu run per username**, bukan satu run untuk semua. Alasannya di docstring `apify_followers.py:212`: `resultsLimit` berlaku per username, tapi kalau satu username gagal di tengah run gabungan, tidak bisa diketahui username mana yang hasilnya utuh. Biayanya sama karena ditagih per item |

---

### 5. `clockworks/tiktok-followers-scraper`

| | |
|---|---|
| **Platform** | TikTok · **Fungsi** daftar follower · **Status ACTIVE** |
| Pemanggil | `scrape_followers.py:362` → `apify_followers.scrape_tiktok_followers()` |
| Sumber actor ID | `apify_followers.py:74` `DEFAULT_TT_FOLLOWERS_ACTOR`; override CLI `--tt-actor` atau env `TT_FOLLOWERS_ACTOR_ID` (`.env.example:28`) |
| Input | `{"profiles": [<satu username>], "maxFollowersPerProfile": N, "maxFollowingPerProfile": 0}` — `apify_followers.py:282` |
| Output dipakai | username follower, id, nickname |
| Tabel tujuan | `l0_raw.tt_followers_apify` |
| Catatan penting | `maxFollowingPerProfile = 0` disetel eksplisit: actor mewajibkan field itu, dan following yang ikut terambil akan ditagih padahal tidak dipakai |

---

## Dua jalur pemanggilan yang hidup berdampingan

Ini yang paling mudah salah dibaca, jadi ditulis terpisah.

| | Jalur pipeline mandiri | Jalur Scheduler Engine |
|---|---|---|
| Entry point | `pipeline.py`, `tiktok_pipeline.py`, `post_pipeline.py`, `scrape_followers.py` | `scheduler_engine.py`, dipanggil `orchestration/kol_orchestration/one_shot.py:77` dan `run_e2e_once.py:47` |
| Actor IG profil | `apify/instagram-profile-scraper` | `apify/instagram-scraper` (mode details) |
| Actor IG post | `apify/instagram-scraper` (mode posts) | `apify/instagram-scraper` (mode details, satu run untuk profil+post) |
| Actor TikTok | `clockworks/tiktok-scraper` | `clockworks/tiktok-scraper` |
| Baca env actor? | **Ya** — `APIFY_ACTOR_ID` / `TIKTOK_ACTOR_ID` | **Tidak**, sengaja (`actor_for()` docstring) |
| Run terakhir | 2026-09-08 / 09 | 2026-08-27 / 28 |

`scheduler_engine.actor_for()` menyebut `apify/instagram-profile-scraper`
sebagai *"jalur lama"*. **Itu bukan berarti actor-nya mati** — jalur mandiri
justru yang paling baru dipakai (2026-09-08, 953 baris), sedangkan jalur
scheduler baru dijalankan 2 kali per platform pada Agustus. Keduanya ACTIVE;
yang membedakan hanya siapa yang memanggilnya.

---

## Override lewat environment

| Env var | Default | Dibaca oleh | Diabaikan oleh |
|---|---|---|---|
| `APIFY_ACTOR_ID` | `apify/instagram-profile-scraper` | `config.py:143` → `pipeline.py` | `scheduler_engine`, `apify_posts` (override di `apify_posts.py:63`), `enrich_follower_profiles` (hardcoded) |
| `TIKTOK_ACTOR_ID` | `clockworks/tiktok-scraper` | `config.py:150` → `tiktok_pipeline.py`, `TikTokVideoScraper` | `scheduler_engine` |
| `IG_FOLLOWERS_ACTOR_ID` | `apify/instagram-followers-following-scraper` | `scrape_followers.py --ig-actor` | — |
| `TT_FOLLOWERS_ACTOR_ID` | `clockworks/tiktok-followers-scraper` | `scrape_followers.py --tt-actor` | — |

Artinya: mengganti `APIFY_ACTOR_ID` **tidak** mengubah actor yang dipakai untuk
post maupun untuk jalur scheduler. Hanya jalur profil `pipeline.py` yang ikut.

---

## Gaps

Enam kebutuhan data tidak punya actor. Semuanya ditandai **UNKNOWN**, bukan
ditebak — untuk keempat yang pertama, tabel tujuannya sudah ada di L0 tapi
**tidak ada satu baris kode pun yang memanggil actor untuk mengisinya**
(dicari dengan grep `comment.*scraper|stories.*scraper|tagged.*scraper` dan
nama tabelnya: nol hasil di luar definisi tabel).

| # | Data | Tabel tujuan | Baris | Actor |
|---|---|---|---:|---|
| 1 | Instagram Comments | `l0_raw.ig_comments_apify` | 0 | **UNKNOWN** — tidak ada kode |
| 2 | TikTok Comments | `l0_raw.tt_comments_apify` | 0 | **UNKNOWN** — tidak ada kode |
| 3 | Instagram Stories | `l0_raw.ig_stories_apify` | 0 | **UNKNOWN** — tidak ada kode |
| 4 | Instagram Tagged posts | `l0_raw.ig_tagged_posts_apify` | 0 | **UNKNOWN** — tidak ada kode |
| 5 | **Discovery** (menemukan KOL baru) | — tidak ada tabel | — | **UNKNOWN** — tidak ada actor discovery sama sekali. Semua scraping berangkat dari daftar username yang **sudah ada** di roster/directory |
| 6 | Audience demographics native (umur/gender dari platform) | `l2_gold.audience_demographics_daily` | 113 | **UNKNOWN** — tidak di-scrape. Yang ada sekarang hasil **inferensi** `audience_inference.py` atas profil follower, bukan data demografi dari Apify |

Catatan untuk #6: tidak ada actor Apify mana pun di project ini yang
mengembalikan demografi audiens. Instagram hanya menyediakannya lewat Insights
API resmi (butuh OAuth), dan TikTok belum punya sumber demografi sama sekali.

Catatan untuk #5: **tidak ada actor discovery.** Pencarian
`discovery|search.*hashtag|searchType.*hashtag|keyword.*scrape` di seluruh
modul Apify, scheduler, dan pipeline mengembalikan nol hasil. `searchType:
"user"` yang muncul di input `apify/instagram-scraper` bukan discovery — ia
menegaskan bahwa `directUrls` yang dikirim adalah URL profil, bukan URL post.

---

## Rekapitulasi

| | Jumlah |
|---|---:|
| Actor **ACTIVE** (ID unik) | **5** |
| Fungsi yang dilayani kelima actor itu | **8** |
| Actor **LEGACY** | **0** |
| Actor **TEST** | **0** |
| Kebutuhan data tanpa actor jelas | **6** |

**Tidak ada actor LEGACY.** Kelima actor terpanggil dari kode yang hidup, dan
keempat-empatnya (kecuali kombinasi scheduler+IG) punya baris di L0 dengan
`scraped_at` pada September 2026. Istilah *"jalur lama"* di
`scheduler_engine.py:134` merujuk pada **jalur pemanggilan**, bukan pada actor
yang usang.

**Tidak ada actor TEST.** Test memakai slug yang sama persis dengan produksi
(`tests/test_apify_runner.py:19`, `tests/test_scheduler_engine.py:294–319`)
sebagai nilai yang di-assert terhadap client palsu — tidak ada actor Apify
terpisah untuk testing, dan tidak ada test yang memanggil Apify sungguhan.
`tests/test_scheduler_engine.py:305–319` justru menjaga hal sebaliknya: ia gagal
kalau `apify/instagram-profile-scraper` muncul di jalur scheduler, dan kalau
`APIFY_ACTOR_ID`/`TIKTOK_ACTOR_ID` berhasil mengubah `actor_for()`.

### Data yang belum punya actor yang jelas

1. Instagram Comments
2. TikTok Comments
3. Instagram Stories
4. Instagram Tagged posts
5. Discovery KOL baru
6. Audience demographics native
