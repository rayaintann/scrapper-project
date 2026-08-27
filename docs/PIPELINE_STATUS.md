# Kondisi Scraping & Data Pipeline

> Diverifikasi terhadap kode dan database `kol`, **2026-08-26**.
> Semua nama tabel, actor, dan angka diambil langsung dari sumbernya.

**Status singkat:** Profile, Post, dan Followers→Audience sudah mengalir penuh
sampai L2. Story, Comment, Tagged Post, dan Brand Fit belum ada datanya.

| Layer | Schema | Tabel | Berisi |
|---|---|---:|---:|
| L0 Raw | `l0_raw` | 20 | 7 |
| Harmonization | `l0_harmonization` | 14 | 9 |
| L1 Silver | `l1_silver` | 8 | 4 |
| Feature | `feature` | 9 | 6 |
| L2 Gold | `l2_gold` | 8 | 6 |

---

## 1. Scraping menarik data apa saja

| Data | Baris | Field penting yang didapat | Yang TIDAK didapat |
|---|---:|---|---|
| **IG Profile** | 944 | `username`, `biography` (100%), `followers_count`, `follows_count`, `media_count`, `website` | — |
| **IG Post** | 130 | `media_id`, `posted_at`, `caption`, `media_type`, `likes`, `comments`, `views`, `is_sponsored` | `shares`, `saved`, `reach` |
| **IG Followers** | 1.300 | `followers_ig_id`, `username`, `full_name`, `is_private`, `is_verified` | `bio`, `followers_count`, `following_count` |
| **IG Followers** *(enrichment)* | 1.263 | `bio` (38,9%), `followers_count` (99,9%), `following_count` (99,9%) | — |
| **TikTok Profile** | 1.057 | `username`, `display_name`, `bio_description`, `follower_count`, `following_count`, `likes_count`, `video_count` | — |
| **TikTok Video** | 91 | `video_id`, `posted_at`, `description`, `like_count`, `comment_count`, **`share_count`**, `view_count` | `reach` |
| **TikTok Followers** | 1.000 | `username`, `display_name`, `followers_count` (100%), `following_count` (100%), `bio` (41%) | — |

**Dua catatan penting:**

- **Instagram followers butuh 2 kali scrape.** Actor daftar-follower IG tidak
  mengembalikan field `biography` sama sekali, jadi perlu enrichment dengan
  profile scraper. TikTok tidak perlu — actor-nya sudah mengembalikan profil lengkap.
- **Instagram tidak punya `shares`/`saved`, TikTok punya.** Akibatnya
  `engagement_sum` Instagram efektif hanya `likes + comments`.

---

## 2. Actor yang dipakai

| Data | Actor | Baris |
|---|---|---:|
| IG Profile | `apify/instagram-profile-scraper` | 944 |
| IG Post | `apify/instagram-scraper` | 130 |
| IG Followers | `apify/instagram-followers-following-scraper` | 1.300 |
| IG Followers (enrichment) | `apify/instagram-profile-scraper` | 1.263 |
| TikTok Profile | `clockworks/tiktok-scraper` | 1.057 |
| TikTok Video | `clockworks/tiktok-scraper` | 91 |
| TikTok Followers | `clockworks/tiktok-followers-scraper` | 1.000 |

> **Koreksi:** IG Profile memakai `apify/instagram-profile-scraper`, **bukan**
> `apify/instagram-scraper`. Dikonfirmasi di `config.py:14` dan di kolom
> `source_actor` seluruh 944 baris. `apify/instagram-scraper` dipakai untuk
> **Post** (`apify_posts.py:27`). Enam entri lain sudah sesuai.

**Biaya sejauh ini: $5,61** — $3,01 (2.300 follower) + $2,60 (1.221 profil enrichment).

---

## 3. Data hasil scraping masuk ke mana

### ✅ Sudah jalan

| Data | L0 Raw | Harmonization | L1 | Feature | L2 |
|---|---|---|---|---|---|
| IG Profile | `ig_profile_apify` | `instagram_profile` | `unified_profile` | — | `kol_profile_card` |
| TT Profile | `tt_profile_apify` | `tiktok_profile` | `unified_profile` | — | `kol_profile_card` |
| IG Post | `ig_media_snapshots_apify` | `instagram_post` | `unified_post` | `ig_post_analysis`, `ig_engagement_analysis` | `kol_metric_daily`, `kol_metric_monthly` |
| TT Video | `tt_video_apify` | `tiktok_post` | `unified_post` | `tt_post_analysis`, `tt_engagement_analysis` | `kol_metric_daily`, `kol_metric_monthly` |
| IG Followers | `ig_followers_apify` | `instagram_follower` | `unified_follower` | `ig_audience_analysis` | `audience_demographics/geo/interest_daily` |
| TT Followers | `tt_followers_apify` | `tiktok_follower` | `unified_follower` | `tt_audience_analysis` | `audience_demographics/geo/interest_daily` |
| Rate Card* | `kol_roster_import` | `instagram/tiktok_rate_card` | `unified_rate_card` | — | `kol_profile_card.rate_card_*` → **NULL** |

\* bukan hasil scraping, tapi impor roster.

### ❌ Belum ada

| Data | Kondisi | Yang kurang |
|---|---|---|
| **Story** | Tabel + procedure lengkap di semua layer, isi 0 | **Scraper** |
| **Comment** | Tabel + procedure lengkap, isi 0 | **Scraper**. ⚠️ 2 tabel feature belum punya UNIQUE |
| **Tagged Post** | Tabel ada, isi 0 | Scraper |
| **Audience terukur** | Jalur lengkap (`ig_profile_official` → `unified_audience`), isi 0 | **Instagram Insights API** (business account + token) |
| **Brand Fit** | Tabel ada, isi 0 | `public.brand` masih 0 baris |
| `content_format_daily` | Sumber **sudah siap** | Asset Dagster |
| `post_metric` | Sumber **sudah siap** | Asset Dagster |

---

## 4. Improvement untuk sprint berikutnya

Diurutkan dari yang paling berdampak. Tiap poin: **apa masalahnya**,
**kenapa penting**, dan **apa yang harus dikerjakan**.

### 1. Data baru diambil sekali, jadi belum bisa lihat perkembangan

**Masalahnya.** Sampai sekarang data baru diambil sebanyak ini:

| Data | Baru diambil |
|---|---|
| Profil | 4 kali |
| Post | 1 kali |
| Follower | 1 kali |

**Kenapa penting.** Semua pertanyaan "naik atau turun?" butuh minimal dua kali
pengambilan. Karena sekarang cuma satu, kita tidak bisa menjawab:

- Follower akun ini naik berapa persen minggu ini? → cuma **22 dari 1.994** akun
  yang bisa dijawab, karena hanya mereka yang punya dua kali pengambilan
- Engagement-nya membaik atau memburuk? → belum bisa dihitung sama sekali
- Audiens berubah tidak? → cuma punya potret satu hari

**Yang harus dikerjakan.** Jadwalkan scraping rutin (misalnya seminggu sekali).
Ini lebih berharga daripada menambah data baru apa pun — data yang sudah ada
otomatis jadi jauh lebih berguna hanya karena diambil berulang.

### 2. Ada 2 tabel yang tinggal diisi, gratis

**Masalahnya.** `content_format_daily` dan `post_metric` masih kosong.

**Kenapa penting.** Bahan-bahannya **sudah ada semua** di database. Yang belum
dibuat cuma kode pengisinya. Jadi ini pekerjaan yang hasilnya langsung terlihat
**tanpa keluar biaya scraping sepeser pun**.

### 3. Beberapa data memang tidak bisa didapat dari scraping biasa

| Data | Kondisi | Kenapa |
|---|---|---|
| Reach / jangkauan | kosong total | Hanya ada di Instagram Insights (butuh akun bisnis + izin resmi) |
| Share & Save (Instagram) | kosong total | Actor Instagram tidak menyediakannya |
| Umur audiens | tidak ada | Tidak ada sumbernya, dan **tidak bisa** ditebak dari data follower |
| Harga / rate card | ada 9.210 baris tapi belum dipakai | Aturannya belum diputuskan: bagaimana kalau satu akun punya beberapa mata uang? |

**Yang harus dikerjakan.** Tiga yang pertama butuh akses API resmi Instagram —
itu keputusan di luar teknis. Yang keempat cuma butuh keputusan aturan, lalu
bisa langsung dikerjakan.

### 4. Angka Instagram dan TikTok belum bisa dibandingkan langsung

**Masalahnya.** Engagement kita hitung dari `like + komentar + share`. Tapi
Instagram tidak memberi data share, TikTok memberi.

**Kenapa penting.** Kalau dibandingkan apa adanya, Instagram akan selalu terlihat
lebih rendah — padahal itu karena datanya kurang, bukan karena performanya jelek.

**Yang harus dikerjakan.** Untuk perbandingan antar platform, pakai kolom
`engagement_public_sum` (`like + komentar` saja). Kolomnya **sudah ada**, tinggal
dipakai di dashboard.

### 5. Scraping masih manual

**Masalahnya.** Pengolahan data (L0 → L2) sudah otomatis lewat 18 asset Dagster.
Tapi scraping-nya masih dijalankan manual satu per satu lewat script.

**Kenapa penting.** Selama masih manual, poin nomor 1 (scraping rutin) tidak akan
jalan konsisten.

**Yang harus dikerjakan.** Masukkan scraping ke Dagster, lalu pasang jadwal.

### 6. Kalau ada yang gagal, tidak ada yang memberi tahu

**Masalahnya.**

- Tabel `sync_log` sudah mencatat tiap proses berhasil/gagal — **tapi tidak ada
  yang memantau**
- Biaya Apify tidak tercatat di database, cuma muncul di layar saat script jalan
- Tidak ada pengecekan otomatis "data hari ini masuk tidak?"

**Yang harus dikerjakan.** Buat alert sederhana kalau `sync_log` berisi status
gagal, dan simpan biaya tiap scrape ke database supaya bisa ditelusuri.

### 7. Cakupannya masih sangat kecil

**Masalahnya.** Dari 1.972 akun yang punya profil, baru **23 akun** (1,2%) yang
punya data post dan follower.

**Kenapa penting.** Sebagian besar tabel analisis cuma berisi 10–13 baris.

**Yang harus dikerjakan.** Perlu keputusan bisnis dulu: akun mana yang perlu
diperdalam. Memperluas follower ke semua akun kira-kira **$345** — jadi bukan
sesuatu yang dijalankan tanpa perencanaan.

## 5. Flow L0 → L2 per data

### Profile

```
ig_profile_apify (944)  ─┐
                         ├─ sp_sync_*_profile() ─→ instagram/tiktok_profile
tt_profile_apify (1.057)─┘                              │
                                    sp_build_unified_profile()
                                                        ▼
                                    unified_profile (1.994 / 1.972 akun)
                                                        ▼
                                          kol_profile_card (1.972)
```

| Layer | Yang terjadi |
|---|---|
| L0 | Respons actor apa adanya + `raw_payload` utuh |
| Harmonization | Kolom diseragamkan per platform, dedup, dicatat ke `sync_log` |
| L1 | IG + TikTok digabung. `tier` dan `followers_growth` (persen) dihitung di sini |
| Feature | — tidak ada tabel khusus profile |
| L2 | Satu kartu per akun, snapshot **terbaru**. `rate_card_*` sengaja NULL |

### Post

```
ig_media_snapshots_apify (130) ─┐
                                ├─ sp_sync_*_post() ─→ instagram/tiktok_post
tt_video_apify (91) ────────────┘                            │
                                        sp_build_unified_post()
                                                             ▼
                                              unified_post (221 / 23 akun)
                                       ┌─────────────────────┴──────────┐
                                       ▼                                ▼
                            *_post_analysis (130/91)      *_engagement_analysis (13/10)
                                       └─────────────────┬──────────────┘
                                                         ▼
                                    kol_metric_daily (160) → kol_metric_monthly (53)
```

| Layer | Yang terjadi |
|---|---|
| L0 | Satu baris per konten per scrape |
| Harmonization | Diseragamkan + dedup `DISTINCT ON` |
| L1 | Grain per konten (**keadaan terkini**, bukan deret waktu). Aturan sampel `likes_hidden` & `is_collaboration` jadi kolom di sini |
| Feature | `*_post_analysis` per konten: semua post dapat baris, sampel diterapkan **per kolom**. `*_engagement_analysis` per akun: akun tanpa sampel tetap dapat baris (metrik NULL) |
| L2 | `metric_date` dari **`posted_at` WIB**, bukan tanggal scrape. Monthly baca **hanya** dari daily |

### Followers

```
ig_followers_apify (2.563)  ← 2 actor, dibedakan lewat source_actor
tt_followers_apify (1.000)
            │ sp_sync_*_follower()
            ▼
instagram_follower (1.300) + tiktok_follower (1.000)
            │ sp_build_unified_follower()
            ▼
     unified_follower (2.300 / 23 akun)  →  lanjut ke Audience
```

| Layer | Yang terjadi |
|---|---|
| L0 | Dua actor menulis ke tabel yang sama dengan `source_actor` berbeda → lineage tetap terpisah |
| Harmonization | **Gabung per kolom**: dua baris L0 dilebur, tiap kolom ambil nilai tidak-NULL dari sumber terbaru (migration 027) |
| L1 | Grain `(akun, follower_platform_id, date)`. `COALESCE` — nilai lama tidak pernah ditimpa NULL |

### Audience — ✅ jalan, tapi **diturunkan**

Ada **dua jalur** ke tabel L2 yang sama:

```
JALUR A — TERUKUR (belum jalan)
  ig_profile_official.demographics_* (0) → instagram_audience (0)
      → unified_audience (0) → audience_*_daily

JALUR B — DITURUNKAN (sedang jalan)
  unified_follower (2.300) → audience_inference.py
      → ig/tt_audience_analysis (13/10)
      → audience_demographics_daily (69)
        audience_geo_daily         (181)
        audience_interest_daily    (214)
```

Gender/lokasi/interest **tidak ada** di data follower — ketiganya diturunkan dari
`username`, `full_name`, `bio` lewat aturan deterministik (kamus nama,
partikel `bin`/`binti`, emoji bendera, pin lokasi 📍, kata kunci interest).
Bukti bertentangan → `unknown`, dan `unknown` **ikut disimpan** supaya
penyebutnya terlihat.

> Jalur B **tidak pernah** menulis ke `unified_audience`. Pembedanya di L2 adalah
> `confidence` yang selalu berawalan `inferred_` — saat ini **464/464 baris**
> berawalan itu, 0 terukur.

Kolom sengaja NULL: `age_gender_breakdown`, `active_hours_heatmap`, `avg_reach`,
`cpe`, `emv`.

### Story & Comment — ❌ belum ada

```
ig_stories_apify (0) → instagram_story (0) → unified_story (0) → (tidak ada feature/L2)
ig/tt_comments_apify (0) → *_comment (0) → unified_comment (0) → *_comments_analysis (0)
```

Tabel dan procedure **sudah lengkap di semua layer**. Yang belum ada hanya
scraper-nya. Untuk Story, tabel feature dan L2 juga belum dirancang.

### Engagement / metric

```
unified_post (221)
   ├─→ *_engagement_analysis   grain akun    (IG 82/130 post lolos sampel, TT 91/91)
   ├─→ *_post_analysis         grain konten
   └─→ kol_metric_daily (160) → kol_metric_monthly (53)
         engagement = likes + comments + shares   (saves SENGAJA tidak ikut)
```

Empat prinsip yang berlaku di seluruh rantai metrik:

1. **Aturan sampel jadi kolom di L1** — satu definisi untuk semua konsumen.
2. **NULL ≠ 0.** `shares_sum` NULL untuk Instagram, bukan 0.
3. **Rasio tidak additive.** Rentang N hari = `SUM(engagement) / SUM(denominator)`,
   bukan rata-rata ER harian.
4. **UPSERT dengan penjaga `IS DISTINCT FROM`** → rerun idempoten,
   `updated_at` menandai perubahan nyata.

---

## Lampiran — tabel yang berisi

| Layer | Tabel (baris) |
|---|---|
| **L0 Raw** | `ig_followers_apify` (2.563) · `tt_profile_apify` (1.057) · `tt_followers_apify` (1.000) · `ig_profile_apify` (944) · `ig_media_snapshots_apify` (130) · `tt_video_apify` (91) · `kol_roster_import` (7.718) |
| **Harmonization** | `tiktok_rate_card` (5.191) · `instagram_rate_card` (4.019) · `instagram_follower` (1.300) · `tiktok_profile` (1.050) · `tiktok_follower` (1.000) · `instagram_profile` (944) · `instagram_post` (130) · `tiktok_post` (91) · `sync_log` (68) |
| **L1 Silver** | `unified_rate_card` (9.210) · `unified_follower` (2.300) · `unified_profile` (1.994) · `unified_post` (221) |
| **Feature** | `ig_post_analysis` (130) · `tt_post_analysis` (91) · `ig_engagement_analysis` (13) · `ig_audience_analysis` (13) · `tt_engagement_analysis` (10) · `tt_audience_analysis` (10) |
| **L2 Gold** | `kol_profile_card` (1.972) · `audience_interest_daily` (214) · `audience_geo_daily` (181) · `kol_metric_daily` (160) · `audience_demographics_daily` (69) · `kol_metric_monthly` (53) |

**Kosong:** semua tabel `*_official` · `*_story` · `*_comment` · `*_tagged_post` ·
`unified_audience` · `brand_fit_analysis` · `content_format_daily` · `post_metric` ·
`l0_extra.*`

**18 asset Dagster terdaftar:** `instagram_profile` · `tiktok_profile` ·
`instagram_post` · `tiktok_post` · `instagram_follower` · `tiktok_follower` ·
`unified_profile` · `unified_post` · `unified_follower` ·
`ig/tt_engagement_analysis` · `ig/tt_post_analysis` · `audience_feature` ·
`audience_gold` · `kol_metric_daily` · `kol_metric_monthly` · `kol_profile_card`
