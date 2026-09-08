# AUTOME_2 — Audit Cara Menaikkan Coverage Engagement Rate

**Read-only · 8 September 2026 06:34 · sesi `set_session(readonly=True)`**
Tidak ada perubahan kode / migration / pipeline / scraping / commit. Tidak ada perbaikan apa pun.

Lanjutan dari `docs/AUTOME_2_ER_AUDIT.md`. Bukti: `scratchpad/cov.py` (14 query) + `scratchpad/cov2.py` (8 query), plus pembacaan langsung 9 file scraper dan `scheduler_engine.py`.

---

# A. Executive Summary

## Kenapa coverage ER cuma 22 KOL?

**Bukan karena pipeline-nya bermasalah. Pipeline tidak kehilangan apa pun.**

Diukur langsung:

| Sambungan | Masuk | Keluar | Kehilangan |
|---|---:|---:|---:|
| L0 profile → L1 snapshot | 1.976 | **1.976** | **0%** |
| L0 post → L1 post | 30 | **30** | **0%** |

Yang runtuh cuma satu langkah, dan itu langkah **scraping**, bukan transformasi:

| | Akun |
|---|---:|
| Punya L0 **profile** | **1.976** |
| Punya L0 **post** | **30** |

**Profile scraper sudah menjangkau 1.976 akun. Post scraper baru 30.** Selisih 98,5% itulah seluruh masalahnya.

Sebabnya ada di dua tempat di kode:

- `post_pipeline.py:196` — `--limit` **default 10**, sementara `pipeline.py:33` (profil) punya `MAX_LIMIT = 1000`. Post scraper memang tidak pernah dijalankan besar-besaran.
- `scheduler_engine.py:99` — `PROFILE_TARGET_LIMIT = 1`. Satu akun per eksekusi, dan syarat kandidatnya mewajibkan akun **belum punya baris L0 sama sekali** — jadi scheduler secara struktural tidak bisa menambah post untuk akun yang sudah pernah di-scrape, maupun membuat snapshot kedua.

## Apakah existing scraper/pipeline bisa dipakai menaikkan coverage?

**Bisa, dan tanpa satu pun komponen baru.** Actor Apify yang ada sudah menerima banyak username per run (`usernames[]`, `directUrls[]`, `profiles[]`), batching sudah ada (`chunked`), plafon biaya sudah ada (`max_charge_usd`), penulisan L0 append-only sehingga snapshot lama aman.

Dan yang paling menguntungkan: **1.942 akun sudah punya snapshot follower tetapi belum punya post sama sekali** (912 IG + 1.030 TikTok). Untuk akun-akun ini denominator ER **sudah tersedia** — tinggal post-nya yang belum ditarik.

## Perubahan minimum

Menjalankan **`post_pipeline.py` yang sudah ada** dengan `--limit` besar, diarahkan ke 1.942 akun yang sudah punya snapshot. Tidak perlu actor baru, pipeline baru, migration, maupun perubahan formula.

Satu-satunya yang mungkin perlu disentuh kodenya: `db.fetch_usernames()` belum punya cara memilih "akun yang sudah punya snapshot tapi belum punya post" — sekarang urutannya cuma `followers / stale / username / random`.

---

# B. Current Coverage Funnel

Angka aktual, diukur 2026-09-08.

```text
public.kol_directory (directory_status='active')            7.720
   │  224 KOL tanpa kol_social_account  ─────────────────────┐
   ▼                                                          ✗
punya kol_social_account                                    7.496   (IG 3.409 · TT 4.087)
   │
   ▼  Apify profile actor  ── pipeline.py (MAX_LIMIT 1000)
L0 profile (ig_profile_apify + tt_profile_apify)            1.976   (IG 935 · TT 1.041)   26,4%
   │
   ▼  Apify post actor  ── post_pipeline.py (--limit default 10)
L0 post (ig_media_snapshots_apify + tt_video_apify)            30   (IG 19 · TT 11)        0,4%  ← RUNTUH DI SINI
   │
   ▼  sp_sync_* → harmonization
l0_harmonization.*_post                                        30   (0% hilang)
   │
   ▼  sp_build_unified_post()
l1_silver.unified_post                                         30   (0% hilang)
   │
   ├─ denominator: l1_silver.unified_profile               1.972 akun punya snapshot
   │
   ▼  carry-forward  date <= post_date
punya post dengan denominator                                  25   (IG 15 · TT 10)
   │  5 akun gugur: seluruh post-nya terbit sebelum snapshot pertama
   ▼  aturan sampel: likes_hidden + is_collaboration
feature.*_engagement_analysis.engagement_rate                  22   (IG 12 · TT 10)
   │  3 akun gugur: seluruh post ber-denominator kena aturan sampel
   ▼
l2_gold.kol_metric_daily.er_followers_daily                    22   ← 0,28% dari 7.720
```

## Funnel per platform

| Tahap | Instagram | TikTok | Total |
|---|---:|---:|---:|
| s1 roster aktif | 3.409 | 4.087 | 7.496 |
| s2 punya `kol_social_account` | 3.409 | 4.087 | 7.496 |
| s3 **L0 profile** | **935** | **1.041** | **1.976** |
| s4 **L0 post** | **19** | **11** | **30** |
| s5 harmonized post | 19 | 11 | 30 |
| s6 L1 `unified_post` | 19 | 11 | 30 |
| s7 L1 snapshot follower | 931 | 1.041 | 1.972 |
| s8 post punya denominator | 15 | 10 | 25 |
| s9 Feature ER | 12 | 10 | 22 |
| s10 **L2 ER** | **12** | **10** | **22** |

## Konversi terukur di level post

| Metrik | Nilai |
|---|---|
| Total post di `post_metric` | 477 |
| Post yang jatuh **pada/sesudah** snapshot pertama akunnya | **159 (33,3%)** |
| Dari 159 itu, yang lolos aturan sampel dan dapat ER | **140 (88,1%)** |
| Akun ber-post yang akhirnya dapat ER | **22 / 30 (73,3%)** |

---

# C. Root Cause — diurutkan berdasarkan dampak

## ROOT CAUSE #1 — Post scraper tidak pernah dijalankan pada skala apa pun

**Dampak: 1.946 akun.** Ini penyebab tunggal terbesar.

Bukti:

| Bukti | Isi |
|---|---|
| `post_pipeline.py:196` | `p.add_argument("--limit", type=int, default=10, ...)` |
| `post_pipeline.py:197` | `--batch-size` default 10 |
| `post_pipeline.py:198` | `--results` default 10 post/akun |
| `pipeline.py:33` (pembanding) | `MAX_LIMIT = 1000`, default 1000 |
| Riwayat run L0 post (terukur) | 2026-08-20: 13 IG + 10 TT · 2026-08-27: 4 IG + 1 TT · 2026-08-28: 2 IG. **Total 30 akun, 3 hari** |
| Riwayat run L0 profil (terukur) | 2026-08-14: 931 IG + 86 TT · 08-17: 256 TT · 08-18: 698 TT · 08-24: 13 IG + 10 TT · 08-27: 4 IG + 1 TT · 08-28: 2 IG |

Profil dijalankan sampai ribuan akun; post tidak pernah lebih dari belasan per run. **Ini limit development, bukan business rule** — tidak ada satu pun komentar di `post_pipeline.py` yang menyatakan 10 adalah keputusan produk, dan `--limit` memang argumen CLI yang bebas diisi.

## ROOT CAUSE #2 — Post terbit sebelum snapshot follower pertama ada

**Dampak: 318 dari 477 post (67%), dan 5 akun gugur seluruhnya.**

Aturan carry-forward di `gold_post.py` dan `gold.py`:

```sql
SELECT pr.followers_count FROM l1_silver.unified_profile pr
 WHERE pr.social_account_id = ... AND pr.date <= <post_date>
 ORDER BY pr.date DESC LIMIT 1
```

Snapshot profil paling awal adalah **2026-08-14**, sementara post membentang sampai **2021-02-18**. Post yang lebih tua tidak punya penyebut, dan **tidak bisa diperbaiki dengan scraping profil hari ini** — snapshot 8 September tidak memenuhi `date <= 20 Agustus`.

Empat akun yang gagal total persis karena ini:

| Username | Post | Rentang post | Snapshot pertama | Post di jendela |
|---|---:|---|---|---:|
| `sekata_ai` | 10 | 2026-08-05 → 08-25 | **2026-08-28** | **0** |
| `raditya_dika` | 9 | 2026-08-17 → 08-26 | **2026-08-27** | **0** |
| `niacnofitasari` | 10 | 2024-10-08 → 2026-02-03 | 2026-08-27 | **0** |
| `leomessi` | 10 | 2025-11-10 → 2026-08-12 | 2026-08-14 | **0** |

Tiga dari empat gagal karena **urutan**: profilnya di-scrape *setelah* post-nya. Kalau urutannya dibalik, ketiganya dapat ER.

## ROOT CAUSE #3 — Scheduler secara struktural tidak bisa menambah coverage

**Dampak: menutup jalur otomatis apa pun.**

| Bukti | Isi |
|---|---|
| `scheduler_engine.py:99` | `PROFILE_TARGET_LIMIT = 1` |
| `scheduler_engine.py:103` | `MAX_RETRIES = 0` |
| `scheduler_engine.py:326–329` | `AND NOT EXISTS (SELECT 1 FROM {profile_table} ...)` **dan** `AND NOT EXISTS (SELECT 1 FROM {post_table} ...)` |
| `scheduler_engine.py:107` | `EXCLUDED_USERNAMES = frozenset({"aamandazahra"})` |
| Docstring baris 14 | *"Tidak ada loop, tidak ada cron, tidak ada retry otomatis"* |
| `scheduler_logs` (terukur) | 8 baris total, 2 hari (27–28 Agu), 4 akun unik, 6 success / 2 failed |

Dua konsekuensi yang perlu ditekankan:

1. Syarat `NOT EXISTS` di **kedua** tabel berarti scheduler **hanya bisa memilih akun yang belum pernah di-scrape sama sekali**. Ia tidak akan pernah menambah post untuk 1.946 akun yang sudah punya profil, dan tidak akan pernah membuat snapshot kedua untuk siapa pun.
2. `PROFILE_TARGET_LIMIT = 1` membuat satu eksekusi = satu akun. Untuk 1.942 akun butuh 1.942 eksekusi manual.

Ini **development/test harness**, bukan production scheduler — dan docstring-nya sendiri menyatakan begitu.

## ROOT CAUSE #4 — Aturan sampel memangkas Instagram, bukan TikTok

**Dampak: 19 post, 3 akun gugur.**

| Platform | Post punya denominator | Hilang `is_collaboration` | Hilang `likes_hidden` | Sisa dapat ER |
|---|---:|---:|---:|---:|
| instagram | 64 | **19** | 2 | **45 (70%)** |
| tiktok | 95 | 0 | 0 | **95 (100%)** |

Aturannya benar dan tidak boleh dilonggarkan — post kolaborasi memang tidak bisa dirasiokan ke follower satu akun. Tapi dampaknya asimetris: Instagram kehilangan 30% post yang sudah punya denominator, TikTok nol.

## ROOT CAUSE #5 — 224 KOL tidak punya `kol_social_account`

**Dampak: 224 KOL (2,9%) tidak akan pernah bisa masuk pipeline.**

Tanpa baris di `kol_social_account`, tidak ada `social_account_id`, sehingga tidak ada tujuan tulis di L0. Catatan tambahan: `db.fetch_usernames()` **tidak** memfilter ini — ia hanya join ke `platforms`. Jadi 224 akun itu bisa ikut terpilih, dibayar ke Apify, lalu hasilnya tidak bisa ditautkan.

---

# D. Existing Scraper Audit

| Komponen | File | Actor / source | Input | Output | Bisa diperluas? |
|---|---|---|---|---|---|
| IG profile | `apify_ig.py` + `pipeline.py` | `apify/instagram-profile-scraper` | `{"usernames": [...]}` | `l0_raw.ig_profile_apify` | **Ya** — `MAX_LIMIT=1000`, batch 100 |
| IG profile (mode details) | `apify_posts.py:110–130` | `apify/instagram-scraper` | `{"directUrls":[...], "resultsType":"details", "resultsLimit":N}` | profil + `latestPosts` sekaligus | **Ya** |
| IG post | `apify_posts.py:62–75` + `post_pipeline.py` | `apify/instagram-scraper` | `{"directUrls":[...], "resultsType":"posts", "resultsLimit":N}` | `l0_raw.ig_media_snapshots_apify` | **Ya** — tapi default `--limit 10` |
| TikTok profile | `apify_tiktok.py` + `pipeline.py` | `clockworks/tiktok-scraper` | `{"profiles":[...]}` | `l0_raw.tt_profile_apify` | **Ya** |
| TikTok video | `apify_posts.py:182–204` + `post_pipeline.py` | `clockworks/tiktok-scraper` | `{"profiles":[...], "profileScrapeSections":["videos"], "resultsPerPage":N}` | `l0_raw.tt_video_apify` | **Ya** |
| Followers | `apify_followers.py` + `scrape_followers.py` | actor followers | daftar username, `--limit` default 100/akun | `l0_raw.ig_followers_apify` | Ya — **tidak dibutuhkan untuk ER** |
| Scheduler one-shot | `scheduler_engine.py` | keduanya | 1 akun/run | L0 + `scheduler_logs` | **Tidak** — lihat Root Cause #3 |

## Jawaban pertanyaan spesifik

| Pertanyaan | Jawaban |
|---|---|
| Actor menerima banyak username? | **Ya, ketiganya.** IG profile `usernames[]`, IG post `directUrls[]`, TikTok `profiles[]`. Dipotong oleh `chunked()` di `apify_runner.py` |
| Batch size / limit | Profil: `--batch-size` 100, `MAX_LIMIT` 1000. Post: `--batch-size` 10, `--limit` 10, `--results` 10 |
| Selection logic | `db.fetch_usernames(platform, limit, order, only_unscraped)`. Order tersedia: `followers` / `stale` / `username` / `random` |
| Scraper hanya ambil KOL tertentu? | Tidak ada whitelist. Tapi `--order followers` (default) selalu mendahulukan akun terbesar, jadi 30 akun ber-post semuanya akun besar |
| Hardcoded limit? | **Ya, tiga:** `post_pipeline.py` `--limit` default **10** · `pipeline.py` `MAX_LIMIT = 1000` · `scheduler_engine.py` `PROFILE_TARGET_LIMIT = 1` |
| Scheduler jalankan subset? | **Ya — tepat satu akun per eksekusi**, dan hanya akun yang belum pernah di-scrape sama sekali |
| Kondisi yang membuat KOL lain tidak ikut? | (a) `--limit` kecil · (b) `NOT EXISTS` di scheduler · (c) `EXCLUDED_USERNAMES` (1 akun) · (d) tidak punya `kol_social_account` (224) · (e) `username` kosong |

**Tidak ditemukan satu pun business rule yang membatasi populasi.** Ketiga limit di atas adalah default CLI dan konstanta test harness.

---

# E. Existing Pipeline Audit — L0 → L2

| Layer | Expected | Actual | Bottleneck? | Reason |
|---|---:|---:|---|---|
| Roster → `kol_social_account` | 7.720 | 7.496 | **Kecil** | 224 KOL tanpa social account |
| `kol_social_account` → L0 profile | 7.496 | 1.976 | **Ya (scraping)** | Actor belum dijalankan untuk sisanya. 5.519 kandidat belum tersentuh |
| `kol_social_account` → L0 post | 7.496 | **30** | **YA — TERBESAR** | `--limit` default 10; hanya 3 hari run |
| L0 profile → harmonization | 1.976 | 1.976 | **Tidak** | 0% hilang |
| L0 post → harmonization | 30 | 30 | **Tidak** | 0% hilang |
| Harmonization → L1 `unified_profile` | 1.976 | **1.976** | **Tidak** | 0% hilang |
| Harmonization → L1 `unified_post` | 30 | **30** | **Tidak** | 0% hilang |
| L1 post → punya denominator | 30 akun / 477 post | 25 akun / 159 post | **Ya (urutan waktu)** | 318 post terbit sebelum snapshot pertama |
| Denominator → Feature ER | 25 akun / 159 post | 22 akun / 140 post | **Kecil (by design)** | `is_collaboration` 19, `likes_hidden` 2 — aturan benar |
| Feature → L2 | 22 | **22** | **Tidak** | Cocok sampai <0,005 poin |

## Kesimpulan pipeline

**Tidak ada bottleneck transformasi sama sekali.** Tidak ada data L0 yang gagal harmonisasi, tidak ada L1 yang tidak terbentuk, tidak ada mismatch platform, tidak ada join yang membuang KOL di dalam pipeline, tidak ada masalah identitas.

Dua hambatan yang ada — jendela waktu denominator dan aturan sampel — **keduanya perilaku yang disengaja dan benar**, bukan bug.

---

# F. Existing Scheduler Audit

| Aspek | Kondisi terukur |
|---|---|
| File | `scheduler_engine.py` (37 KB) |
| Cron / interval | **Tidak ada.** Docstring: *"Tidak ada loop, tidak ada cron, tidak ada retry otomatis"* |
| Batch size | **1 akun per eksekusi** (`PROFILE_TARGET_LIMIT = 1`) |
| Post per akun | `POSTS_PER_TARGET = 10` |
| Retry | `MAX_RETRIES = 0` |
| Failure handling | Setiap pekerjaan menghasilkan satu baris `scheduler_logs`, sukses maupun gagal. Tidak melempar exception |
| Riwayat jalan | **8 baris, 2 hari (27–28 Agu), 4 akun unik, 6 success / 2 failed** |
| Config per KOL | Tidak ada tabel jadwal/prioritas |
| Seleksi | Hanya akun yang **belum punya baris L0 profile DAN belum punya baris L0 post** |

## Apakah scheduler existing bisa dipakai menaikkan coverage hanya dengan memperluas selection/batch?

**Tidak — dan sebaiknya jangan dipaksa.**

Alasannya bukan cuma `PROFILE_TARGET_LIMIT = 1`. Yang lebih mengikat adalah dua klausa `NOT EXISTS` di baris 326–329: scheduler **secara definisi hanya menargetkan akun perawan**. Untuk menaikkan coverage ER yang dibutuhkan justru sebaliknya — menarik post untuk 1.942 akun yang **sudah** punya profil.

Menyesuaikan scheduler untuk itu berarti membalik kriteria intinya, dan itu bukan lagi "memperluas batch".

**Yang sudah siap dipakai adalah `post_pipeline.py`**, yang memang dirancang untuk populasi (`--limit`, `--batch-size`, `--from-file`, `--usernames`, penanganan kegagalan per batch, `--max-charge-usd`). Itu jalur yang benar; scheduler biarkan sebagai test harness sesuai maksud aslinya.

---

# G. Recommended Solution

## Minimum Change

**Jalankan `post_pipeline.py` yang sudah ada, dengan `--limit` besar, terhadap akun yang sudah punya snapshot follower.**

Populasi target terukur:

| Platform | Punya snapshot **tapi belum punya post** |
|---|---:|
| Instagram | **912** |
| TikTok | **1.030** |
| **Total** | **1.942** |

Untuk akun-akun ini denominator sudah ada. Snapshot mereka bertanggal 14–28 Agustus, jadi **jendela sudah terbuka rata-rata 24,9 hari (IG) dan 21,6 hari (TT)** per hari ini — setiap post yang terbit dalam ~3 minggu terakhir akan langsung punya penyebut.

Komponen yang perlu disentuh: **satu**, dan itu pun opsional.

| Komponen | Perlu diubah? | Catatan |
|---|---|---|
| Actor Apify | ❌ | Sudah menerima banyak username |
| `apify_posts.py` | ❌ | Sudah benar |
| `post_pipeline.py` | ❌ | `--limit` sudah jadi argumen CLI — cukup diisi angka besar |
| `post_raw_store.py` / harmonisasi / L1 / Feature / L2 | ❌ | Terbukti 0% kehilangan |
| Migration | ❌ | Tidak ada kolom baru |
| `db.fetch_usernames()` | **Mungkin** | Belum punya order/filter "sudah punya snapshot & belum punya post". Alternatif tanpa ubah kode: `--from-file` dengan daftar username hasil query manual |

`post_pipeline.py:237` sudah punya jalur `--from-file` yang membaca daftar username dan mencocokkannya ke roster dengan `limit=100000`. **Jadi Option A bisa dijalankan tanpa satu baris kode pun berubah.**

## Recommended

Urutan paling aman, tiap langkah bisa diverifikasi sebelum lanjut:

| # | Langkah | Kenapa urutannya begini |
|---|---|---|
| **1** | **Scrape profil lebih dulu, post kemudian** — untuk akun yang belum punya snapshot | Carry-forward `date <= post_date`. Kalau post ditarik duluan, post-nya permanen tanpa denominator (persis nasib `sekata_ai` dan `raditya_dika`) |
| **2** | Jalankan `post_pipeline.py` pilot ~**50 akun** dari populasi yang sudah punya snapshot, `--dry-run` dulu lalu run nyata | Memberi angka konversi nyata sebelum membelanjakan untuk 1.942 akun |
| **3** | Materialisasi ulang `unified_post` → `feature` → `post_metric` / `kol_metric_daily` | Rantai yang sudah ada, terbukti 0% kehilangan |
| **4** | Ukur ulang: berapa akun baru dapat ER, berapa post masuk jendela | Kalibrasi estimasi §H dengan data nyata |
| **5** | Kalau konversi sesuai, lanjutkan bertahap ke sisa populasi | Bertahap supaya biaya terkendali |
| **6** | Untuk akun yang **belum** punya snapshot: profil dulu, tunggu, baru post | Post hari ini + snapshot hari ini = denominator ada untuk post hari ini dan sesudahnya |

Tidak ada pipeline baru, actor baru, tabel baru, maupun perubahan source of truth di seluruh urutan ini.

## Long-term (tetap arsitektur existing)

| # | Item | Catatan |
|---|---|---|
| L1 | Jalankan `pipeline.py` (profil) berkala | Setiap run menambah satu snapshot per akun ke L0 yang append-only → membuka jendela denominator makin lebar, sekaligus memberi data Growth 30D. Ini pemakaian ulang komponen yang sudah ada, bukan komponen baru |
| L2 | Jalankan `post_pipeline.py` berkala mengikuti irama profil | Selama profil selalu lebih dulu, setiap post baru langsung dapat denominator |
| L3 | Naikkan `--results` di atas 10 untuk akun berfrekuensi tinggi | Terukur: `nanakoot` punya 200 post dan 40 di antaranya masuk jendela. Akun ber-`--results 10` maksimal menyumbang 10 |
| L4 | Pertimbangkan mode `details` (`apify_posts.py:110`) | Satu run mengembalikan profil **dan** `latestPosts` sekaligus — snapshot dan post lahir di tanggal yang sama, jadi denominator otomatis ada. Ini sudah ada di kode dan dipakai `scheduler_engine` |

Poin **L4** layak dipertimbangkan lebih dulu: ia menyelesaikan Root Cause #2 secara struktural, dengan kode yang sudah ada.

---

# H. Coverage Improvement Plan

```text
1. Susun daftar target: 1.942 akun yang PUNYA snapshot follower TAPI BELUM punya post
      → query read-only, keluarkan ke file username

2. Pilot: post_pipeline.py --from-file <daftar> --limit 50 --dry-run
      → verifikasi rencana & estimasi biaya, belum memanggil actor

3. Pilot nyata 50 akun (IG dan TikTok terpisah — aturan sampel berbeda jauh)
      → ukur: berapa post masuk jendela, berapa lolos aturan sampel

4. Materialisasi ulang unified_post → feature → post_metric → kol_metric_daily
      → verifikasi 0% kehilangan masih berlaku di skala lebih besar

5. Ukur konversi nyata, bandingkan dengan estimasi §I
      → putuskan lanjut atau setel ulang --results

6. Rollout bertahap ke sisa populasi (batch 200–500 akun)

7. Untuk 5.519 akun yang belum punya snapshot: pipeline.py (profil) DULU,
   baru post_pipeline.py — jangan dibalik

8. Setelah coverage naik, baru pindahkan minEr & field ER endpoint ke L2
      → keputusan ini menunggu coverage, bukan sebaliknya
```

Langkah **8** sengaja ditaruh terakhir: memindahkan filter ke L2 hari ini mengecilkan hasil direktori dari 219 KOL jadi maksimum 22.

---

# I. Estimate Coverage

## Dasar estimasi (terukur, bukan asumsi)

| Metrik | Nilai |
|---|---|
| Post yang jatuh pada/sesudah snapshot pertama akunnya | **33,3%** (159/477) |
| Post di jendela yang lolos aturan sampel | **88,1%** (140/159) |
| **Akun ber-post yang akhirnya dapat ER** | **73,3%** (22/30) |
| Jendela rata-rata hari ini | **24,9 hari** (IG) · **21,6 hari** (TT) |

## Estimasi

Untuk akun yang **sudah punya snapshot** (populasi 1.942), dengan `--results 10`:

| Akun di-scrape | Perkiraan dapat ER | Dasar |
|---:|---|---|
| 100 | **55–75** | Batas bawah 55% (koreksi bias, lihat di bawah); batas atas 73,3% terukur |
| 500 | **275–365** | Skala linear dari angka yang sama |
| 1.000 | **550–730** | Populasi memadai (1.942 tersedia) |
| 1.942 (seluruhnya) | **1.070–1.420** | Naik dari 22 → **48×–65×** |

## Kenapa ada koreksi ke bawah, dan kenapa juga ada faktor ke atas

**Yang menekan ke bawah — 30 akun acuan adalah sampel bias.** `--order followers` (default) mendahulukan akun terbesar, sehingga 30 akun itu berfrekuensi posting tinggi (`lambe_turah`, `pojoksatu.id`, `ditanganu`, `sptrakori_` semuanya 10/10 post masuk jendela). Ekor roster — Nano 1.943 dan Micro 2.942 akun — hampir pasti memposting lebih jarang, sehingga lebih sedikit dari 10 post terakhirnya yang jatuh dalam jendela ~3 minggu. Karena itu batas bawah saya turunkan ke 55%.

**Yang mengangkat ke atas — jendela sekarang jauh lebih lebar.** 30 akun acuan di-scrape 20 Agustus dengan snapshot 14 Agustus: jendela hanya **6 hari**, dan tetap menghasilkan 33,3% post masuk. Hari ini jendelanya **~25 hari, 4× lebih lebar**. Akun yang sama, di-scrape hari ini, akan menyumbang lebih banyak post.

Kedua efek berlawanan arah dan besarannya belum bisa dipisahkan tanpa pilot. **Itulah alasan langkah 2–3 di §H ada: 50 akun sudah cukup untuk mengganti rentang ini dengan angka nyata.**

## Bottleneck-nya di scraping atau calculation?

**Scraping — tanpa keraguan.**

| Bukti | Angka |
|---|---|
| Kehilangan di transformasi L0 → L1 | **0%** (profil 1.976→1.976, post 30→30) |
| Kehilangan Feature → L2 | **0%** (selisih <0,005 poin) |
| Post di jendela yang berhasil jadi ER | **88,1%** |
| Akun punya L0 profile tapi tanpa post | **1.946** |

Calculation sudah bekerja dengan efisiensi 88%. Yang tidak ada adalah bahan bakunya.

## Yang belum bisa diestimasi

| Item | Kenapa | Data yang dibutuhkan |
|---|---|---|
| Distribusi frekuensi posting 1.942 akun target | Belum pernah di-scrape post-nya | Pilot 50 akun |
| Tingkat kegagalan scrape (private/hilang/diblokir) | `scheduler_logs` cuma 8 baris (6 success / 2 failed) — terlalu kecil | Pilot |
| Rasio `is_collaboration` di luar 19 akun IG yang ada | Sekarang 19/64 post IG, sampel kecil | Pilot |
| Biaya aktual per akun | Butuh halaman harga actor + `usage_total_usd` dari run nyata | Pilot `--dry-run` lalu 1 batch |

---

# J. Scraping Cost / Risk

| Aspek | Kondisi terukur | Risiko |
|---|---|---|
| **Plafon biaya** | `apify_runner.py:108` `max_charge_usd`, diteruskan sebagai `max_total_charge_usd` ke run. `pipeline.py` default 1,5× estimasi satu batch | **Rendah** — plafon sudah ada |
| **Timeout** | `_run_timeout_secs()` = `max(timeout_secs, jumlah_username × seconds_per_username)`. IG post 20 dtk/username, IG details 30, profil 10 | **Rendah** — skala otomatis dengan batch |
| **Rate limit** | Dikelola Apify. `chunked()` memecah batch; ada backoff `time.sleep(backoff)` | **Rendah** |
| **Batch limit** | `--batch-size` 100 (profil), 10 (post). Bebas disetel | **Rendah** |
| **Retry** | `max_retries` ada di runner; `MAX_RETRIES = 0` hanya berlaku di `scheduler_engine` | **Rendah** |
| **Duplicate** | `raw_store.py:52` menyatakan tabel **append-only**: *"ingest file yang sama dua kali akan menggandakan baris"*. `count_existing()` memperingatkan lebih dulu | **Sedang** — jangan ingest file yang sama dua kali |
| **Overwrite snapshot lama** | **TIDAK ADA.** L0 `INSERT ... RETURNING id` tanpa `ON CONFLICT` → selalu menambah baris. Terukur: `ig_profile_apify` 953 baris / 950 pasangan (akun, tanggal) / 935 akun | **Rendah** |
| **Preservasi historis L1** | `unified_profile` bergrain `(social_account_id, date)` — terukur 2.001 baris / 2.001 pasangan unik / 1.976 akun. Scrape di tanggal **baru** membuat snapshot **baru** | **Rendah** |
| **Scrape dua kali di hari yang sama** | Grain L1 `(akun, date)` → `ON CONFLICT DO UPDATE`, menimpa dalam hari yang sama | **Rendah** — memang perilaku yang benar |
| **224 KOL tanpa `kol_social_account`** | `db.fetch_usernames()` tidak memfilternya | **Sedang** — bisa terbayar ke Apify lalu hasilnya tidak bisa ditautkan. Saring di daftar target |
| **`social_account_link_blocked()`** | `raw_store.py:65` — kalau kolom `social_account_id` punya dua FK sekaligus, kolomnya diisi NULL supaya data tetap masuk | **Perlu dicek sebelum run besar** — kalau aktif, seluruh hasil scrape masuk tanpa tautan akun dan tidak akan pernah sampai L1 |

## Catatan khusus follower historis

**Sudah aman.** Yang dibutuhkan adalah INSERT snapshot baru, bukan menimpa nilai follower saat ini — dan itu memang yang terjadi:

- L0 `INSERT` polos, append-only → riwayat tidak pernah hilang
- L1 bergrain `(social_account_id, date)` → satu snapshot per akun per tanggal
- `kol_directory.followers_count` **memang** ditimpa oleh `db.update_profiles()` (`COALESCE(v.followers_count, k.followers_count)`), tetapi kolom itu **bukan** sumber denominator ER. Denominator dibaca dari `l1_silver.unified_profile`, yang berjenjang tanggal

Jadi menjalankan `pipeline.py` berkala **menambah** riwayat follower, tidak menghapusnya.

---

# K. Development Dependency

## Bisa dikerjakan sekarang

| Item | Catatan |
|---|---|
| Query daftar 1.942 akun target (read-only) | Tidak mengubah apa pun |
| `post_pipeline.py --from-file ... --dry-run` | Tidak memanggil actor |
| Cek `social_account_link_blocked()` | Read-only, satu query |
| Saring 224 KOL tanpa `kol_social_account` dari daftar target | Read-only |

## Butuh approval Product / Mentor

| Item | Kenapa |
|---|---|
| Menjalankan scraping ke 1.942 akun | Ada biaya Apify nyata |
| Nilai `--results` (10 atau lebih) | Trade-off biaya vs coverage |
| Urutan prioritas: akun besar dulu atau merata | Menentukan siapa yang dapat ER lebih dulu |
| Kadens scraping profil berkala | Komitmen biaya berulang |

## Butuh credential / API

| Item | Status |
|---|---|
| `APIFY_API_TOKEN` | Sudah ada di `.env` |
| Kredit Apify untuk 1.942 akun | **Perlu dipastikan** — belum bisa dihitung tanpa harga actor |
| Insights API | Tidak dibutuhkan untuk ER berbasis follower |

## Butuh scraping run

| Item |
|---|
| Angka konversi nyata untuk populasi non-top-follower |
| Tingkat kegagalan scrape |
| Rasio `is_collaboration` di populasi lebih luas |
| Biaya aktual per akun |

## Blocked

| Item | Blocker |
|---|---|
| ER untuk 318 post yang sudah ada | Terbit sebelum snapshot pertama. **Tidak bisa diperbaiki** — snapshot hari ini tidak memenuhi `date <= post_date`. Satu-satunya jalan adalah post yang lebih baru |
| ER untuk 224 KOL tanpa `kol_social_account` | Butuh perbaikan penautan di roster, di luar scope scraping |
| ER berbasis reach | `unified_post.reach` 0/477, butuh Insights API |
| ER Instagram dengan komponen share | `shares` 0/186 di sumber |

---

# L. FINAL VERDICT

## **B. Existing pipeline BISA diperluas — bottleneck-nya di scraping, bukan arsitektur.**

Lebih tepatnya: **pipeline-nya sendiri bahkan tidak punya bottleneck sama sekali.** Yang perlu diperbaiki ada di luar pipeline — cara scraper dipanggil.

### Bukti untuk kesimpulan ini

| # | Bukti | Sumber |
|---|---|---|
| 1 | **L0 profile → L1 snapshot: 1.976 → 1.976. Kehilangan 0%** | query F6 |
| 2 | **L0 post → L1 post: 30 → 30. Kehilangan 0%** | query F7 |
| 3 | **Feature ER = L2 ER, selisih <0,005 poin di 8 akun sampel** | `AUTOME_2_ER_AUDIT.md` §H1 |
| 4 | **88,1% post yang punya denominator berhasil jadi ER** | query G2 |
| 5 | **Profil sudah menjangkau 1.976 akun; post baru 30** | query F1 |
| 6 | **1.942 akun sudah punya denominator, tinggal post-nya** | query G4 |
| 7 | **Jendela denominator sudah terbuka 21,6–24,9 hari** | query G3 |
| 8 | **Ketiga actor menerima banyak username per run** | `apify_ig.py:29`, `apify_posts.py:67`, `apify_posts.py:188` |
| 9 | **L0 append-only — riwayat aman** | `raw_store.py:52`, query G8 |
| 10 | **`--limit` post default 10 vs profil `MAX_LIMIT` 1000** | `post_pipeline.py:196`, `pipeline.py:33` |

### Yang harus diperbaiki (dan bukan arsitektur)

| Hambatan | Sifat | Perbaikan |
|---|---|---|
| `post_pipeline.py --limit` default 10 | Default CLI | Isi angka besar saat menjalankan |
| Scheduler 1 akun & hanya akun perawan | Test harness, sesuai maksud aslinya | Jangan dipakai untuk ini; pakai `post_pipeline.py` |
| Urutan scrape (post sebelum profil) | Operasional | Profil dulu, post kemudian |
| 224 KOL tanpa `kol_social_account` | Data roster | Saring dari daftar target |

Tidak satu pun dari empat hambatan itu menyentuh arsitektur `L0 → Harmonization → L1 → Feature → L2`.

---

*Audit read-only. Tidak ada perubahan pada kode, database, schema, migration, pipeline, endpoint, atau UI. Tidak ada commit, push, maupun scraping baru. Seluruh angka diukur langsung 2026-09-08 lewat sesi `set_session(readonly=True)`.*
