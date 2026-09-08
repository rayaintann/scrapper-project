# AUTOME_2 — Preflight Pilot ER 50 KOL

**Read-only · 8 September 2026 · STATUS: `PREFLIGHT PASS DENGAN 1 TEMUAN` — scraping BELUM dijalankan**

Tidak ada perubahan kode, migration, commit, push, maupun panggilan Apify. Seluruh pengecekan memakai sesi `set_session(readonly=True)` dan `--dry-run`.

> ## ⛔ BERHENTI SEBELUM SCRAPING
>
> Preflight menemukan **satu bug pelabelan di `post_pipeline.py` yang khusus mengenai Instagram**. Sesuai instruksi ("kalau ada masalah yang membutuhkan perubahan code, STOP sebelum mengubahnya dan laporkan dulu"), pilot **tidak dijalankan** dan kodenya **tidak disentuh**. Detail di §11.
>
> TikTok tidak terdampak dan aman dijalankan kapan saja.

---

# 1. Social Linking Preflight

## 1.1 Hasil pemanggilan fungsi existing

| Pengecekan | Fungsi yang dipanggil | Hasil |
|---|---|---|
| Tabel profil | `raw_store.social_account_link_blocked(conn)` | **`None` → TIDAK BLOCKED** |
| Tabel post Instagram | `post_raw_store._link_blocked(conn, 'l0_raw.ig_media_snapshots_apify')` | **`None` → TIDAK BLOCKED** |
| Tabel post TikTok | `post_raw_store._link_blocked(conn, 'l0_raw.tt_video_apify')` | **`None` → TIDAK BLOCKED** |

## 1.2 FK di kolom `social_account_id`

| Tabel L0 | FK menuju |
|---|---|
| `l0_raw.ig_profile_apify` | `social_account` |
| `l0_raw.tt_profile_apify` | `social_account` |
| `l0_raw.ig_media_snapshots_apify` | `social_account` |
| `l0_raw.tt_video_apify` | `social_account` |

**Tepat satu FK per tabel.** Kondisi dua-FK yang dikhawatirkan `raw_store.py:65` (*"kolom itu punya dua foreign key sekaligus … jadi tidak ada nilai yang bisa memenuhi keduanya"*) **sudah tidak berlaku** — kemungkinan besar sudah dibereskan migration 001/002. Hasil scrape akan tertaut, bukan disimpan dengan `social_account_id = NULL`.

## 1.3 Total account yang berisiko tidak tertaut

| Kategori | Jumlah | Penyebab |
|---|---:|---|
| Roster aktif | 7.720 | — |
| **Tanpa `kol_social_account`** | **224** | Tidak punya `social_account_id` → tidak ada tujuan tulis di L0 |
| Tanpa `social_account` | 224 | Kelompok yang sama |
| Tanpa `platform_id` | 224 | Kelompok yang sama |
| Username kosong | 223 | Hampir seluruhnya beririsan dengan 224 di atas |

Ketiga angka menunjuk **satu populasi yang sama**: 224 baris roster yang belum pernah ditautkan sama sekali.

## 1.4 Pemeriksaan tambahan

| Pengecekan | Hasil | Arti |
|---|---|---|
| `social_account.platform_id` == `kol_directory.platform_id` | **7.496 dari 7.496 cocok, 0 tidak cocok** | Tidak ada risiko akun Instagram tertulis ke tabel TikTok |
| Username muncul >1× pada platform yang sama | **2** di seluruh roster | Ambiguitas ada, tapi sangat kecil |
| Username ganda **di antara 50 kandidat pilot** | **0** | Kandidat pilot bersih |
| Resolusi 50 kandidat ke `kol_directory` | **25 IG + 25 TT = 50 baris, 1:1** | Tidak ada yang berlipat maupun hilang |

## 1.5 Kesimpulan

> **Pilot 50 akun AMAN dari sisi linking. Tidak perlu perbaikan linking terlebih dahulu.**

224 akun bermasalah **sudah otomatis tersaring** dari kandidat karena query kandidat mewajibkan `JOIN kol_social_account` + `JOIN social_account`. Perbaikan 224 akun itu urusan terpisah dan tidak memblokir pilot.

---

# 2. Kandidat Pilot 50 KOL

## 2.1 Kriteria seleksi

Seluruhnya wajib terpenuhi:

| # | Syarat | Alasan |
|---|---|---|
| 1 | Punya snapshot follower di `l1_silver.unified_profile` dengan `followers_count > 0` | Denominator ER harus sudah ada |
| 2 | `snap_pertama <= CURRENT_DATE` | Jendela carry-forward sudah terbuka |
| 3 | Belum punya baris di `l1_silver.unified_post` | Belum punya post usable |
| 4 | Belum punya baris di `l0_raw.ig_media_snapshots_apify` **dan** `l0_raw.tt_video_apify` | Belum pernah di-scrape post-nya |
| 5 | Punya `kol_social_account` → `social_account`, dengan `platform_id` cocok | Hasil scrape pasti bisa ditautkan |
| 6 | `username` tidak NULL / tidak kosong | Input actor valid |
| 7 | `directory_status = 'active'` | Konsisten dengan seluruh Discovery |

Prioritas: **follower terbesar dulu**, 25 per platform. Alasan memilih yang terbesar untuk pilot: akun besar hampir pasti publik dan berfrekuensi posting tinggi, jadi kalau pipeline bermasalah, penyebabnya bukan "akunnya sepi" — persis alasan yang sudah ditulis `scheduler_engine.select_profile_target`.

## 2.2 Ukuran populasi yang memenuhi syarat

| Platform | Kandidat memenuhi SELURUH syarat |
|---|---:|
| Instagram | **909** |
| TikTok | **1.018** |
| **Total** | **1.927** |

Pilot mengambil 50 dari 1.927.

## 2.3 Daftar 50 kandidat

### Instagram (25)

| # | Username | Followers roster | Followers snapshot | Snapshot | Jendela | Tier |
|---:|---|---:|---:|---|---:|---|
| 1 | `instagram` | 685.896.635 | 685.896.635 | 2026-08-14 | 25 hari | Mega |
| 2 | `rayanurfitrird` | 8.408.364 | 8.408.364 | 2026-08-14 | 25 | Mega |
| 3 | `syakirdaulay` | 7.694.004 | 7.694.004 | 2026-08-14 | 25 | Mega |
| 4 | `tasyafarasya` | 7.358.061 | 7.358.061 | 2026-08-14 | 25 | Mega |
| 5 | `folkative` | 7.156.562 | 7.156.562 | 2026-08-14 | 25 | Mega |
| 6 | `wulanguritno` | 6.133.691 | 6.133.691 | 2026-08-14 | 25 | Mega |
| 7 | `indozone.id` | 5.511.969 | 5.511.969 | 2026-08-14 | 25 | Mega |
| 8 | `tasyakamila` | 5.042.266 | 5.042.266 | 2026-08-14 | 25 | Mega |
| 9 | `andreastaulany` | 4.874.978 | 4.874.978 | 2026-08-14 | 25 | Mega |
| 10 | `jktinfo` | 3.954.716 | 3.954.716 | 2026-08-14 | 25 | Mega |
| 11 | `alyssadaguise` | 3.918.239 | 3.918.239 | 2026-08-14 | 25 | Mega |
| 12 | `kikysaputrii` | 3.783.998 | 3.783.998 | 2026-08-14 | 25 | Mega |
| 13 | `nanamirdad_` | 3.768.396 | 3.768.396 | 2026-08-14 | 25 | Mega |
| 14 | `desta80s` | 3.599.718 | 3.599.718 | 2026-08-14 | 25 | Mega |
| 15 | `bobonsantoso` | 3.532.582 | 3.532.582 | 2026-08-14 | 25 | Mega |
| 16 | `sophia_latjuba88` | 3.495.969 | 3.495.969 | 2026-08-14 | 25 | Mega |
| 17 | `dahliachr` | 3.236.332 | 3.236.332 | 2026-08-14 | 25 | Mega |
| 18 | `chicco.jerikho` | 3.050.573 | 3.050.573 | 2026-08-14 | 25 | Mega |
| 19 | `cakecaine` | 2.961.548 | 2.961.548 | 2026-08-14 | 25 | Mega |
| 20 | `ahquote` | 2.775.736 | 2.775.736 | 2026-08-14 | 25 | Mega |
| 21 | `shela_lala96` | 2.512.148 | 2.512.148 | 2026-08-14 | 25 | Mega |
| 22 | `jakarta.terkini` | 2.308.270 | 2.308.270 | 2026-08-14 | 25 | Mega |
| 23 | `dillaljaidi` | 2.284.424 | 2.284.424 | 2026-08-14 | 25 | Mega |
| 24 | `indrowarkop_asli` | 2.258.700 | 2.258.700 | 2026-08-14 | 25 | Mega |
| 25 | `andreadianbimo` | 2.244.644 | 2.244.644 | 2026-08-14 | 25 | Mega |

### TikTok (25)

| # | Username | Followers roster | Followers snapshot | Snapshot | Jendela | Tier |
|---:|---|---:|---:|---|---:|---|
| 1 | `erickapineda09` | 11.800.000 | 16.800.000 | 2026-08-17 | 22 hari | Mega |
| 2 | `eunicetjoaa` | 10.000.000 | 9.400.000 | 2026-08-14 | 25 | Mega |
| 3 | `shaturday` | 9.100.000 | 12.200.000 | 2026-08-14 | 25 | Mega |
| 4 | `knzymyln__` | 8.900.000 | 8.400.000 | 2026-08-14 | 25 | Mega |
| 5 | `pandawaragroup` | 8.400.000 | 12.100.000 | 2026-08-14 | 25 | Mega |
| 6 | `dennysumargoreal` | 8.300.000 | 11.100.000 | 2026-08-14 | 25 | Mega |
| 7 | `yourrkayesss` | 8.000.000 | 10.700.000 | 2026-08-17 | 22 | Mega |
| 8 | `efritaasmr` | 7.200.000 | 8.100.000 | 2026-08-17 | 22 | Mega |
| 9 | `marcelldegen` | 6.700.000 | 9.100.000 | 2026-08-14 | 25 | Mega |
| 10 | `mursid241` | 6.685.227 | 7.300.000 | 2026-08-14 | 25 | Mega |
| 11 | `dimsthemeatguy` | 6.600.000 | 6.000.000 | 2026-08-17 | 22 | Mega |
| 12 | `veliaveve_` | 6.300.000 | 7.600.000 | 2026-08-14 | 25 | Mega |
| 13 | `arafahrianti02` | 6.200.000 | 6.400.000 | 2026-08-14 | 25 | Mega |
| 14 | `botakteras` | 6.200.000 | 6.600.000 | 2026-08-14 | 25 | Mega |
| 15 | `imeyhou` | 6.000.000 | 6.500.000 | 2026-08-14 | 25 | Mega |
| 16 | `celinenobleza` | 5.800.000 | 6.100.000 | 2026-08-14 | 25 | Mega |
| 17 | `azmannis` | 5.750.570 | 6.000.000 | 2026-08-14 | 25 | Mega |
| 18 | `megandomanii` | 5.700.000 | 6.100.000 | 2026-08-14 | 25 | Mega |
| 19 | `syahnazsadiqah` | 5.696.374 | 5.700.000 | 2026-08-14 | 25 | Mega |
| 20 | `cheekykiddo` | 5.600.000 | 5.800.000 | 2026-08-14 | 25 | Mega |
| 21 | `bangsaonline` | 5.400.000 | 7.600.000 | 2026-08-14 | 25 | Mega |
| 22 | `viliacarl` | 5.400.000 | 6.000.000 | 2026-08-14 | 25 | Mega |
| 23 | `drrichardlee` | 5.300.000 | 6.400.000 | 2026-08-14 | 25 | Mega |
| 24 | `vamells` | 5.200.000 | 4.800.000 | 2026-08-17 | 22 | Mega |
| 25 | `milaalawiyah` | 5.200.000 | 4.900.000 | 2026-08-14 | 25 | Mega |

## 2.4 Catatan atas daftar ini

| Catatan | Detail |
|---|---|
| **Seluruh 50 kandidat bertier Mega** | Konsekuensi `--order followers`. Bagus untuk membuktikan pipeline, **tidak mewakili** ekor roster (Nano 1.943 + Micro 2.942). Estimasi konversi dari pilot ini akan optimistis — perlu pilot kedua di tier bawah sebelum ekstrapolasi ke 1.927 |
| **Semua punya `n_snap = 1`** | Belum ada yang punya snapshot kedua. Cukup untuk ER (butuh 1), tidak cukup untuk Growth 30D (butuh 2 + span) |
| **Selisih `followers_roster` vs `followers_snapshot` di TikTok** | Contoh `shaturday` 9,1jt vs 12,2jt. Dua kolom berbeda sumber: roster dari `transform.py`, snapshot dari L1. **ER memakai yang snapshot** — yang benar |
| `instagram` (akun resmi Instagram) | Ikut terpilih karena follower terbesar. Tidak masalah teknis, tapi bukan KOL — pertimbangkan mengeluarkannya |

---

# 3. Command Existing Scraper

## 3.1 Koreksi terhadap laporan saya sebelumnya

Di `AUTOME_2_ER_COVERAGE_AUDIT.md` saya menulis pilot bisa dijalankan lewat `post_pipeline.py --from-file`. **Itu keliru.** `--from-file` adalah **replay file `.jsonl` hasil scrape** (`post_pipeline.py:201`: *"putar ulang file .jsonl hasil scrape, tanpa memanggil Apify"*), bukan daftar username.

Flag yang benar adalah **`--usernames`** (`post_pipeline.py:203`). Kesimpulannya tidak berubah — **tetap tanpa perubahan kode** — hanya flag-nya yang berbeda.

## 3.2 Command yang akan dipakai

```bash
# Instagram — 25 akun
venv/Scripts/python.exe post_pipeline.py \
    --platform instagram \
    --results 10 \
    --batch-size 10 \
    --max-charge-usd <plafon> \
    --usernames instagram rayanurfitrird syakirdaulay tasyafarasya folkative \
                wulanguritno indozone.id tasyakamila andreastaulany jktinfo \
                alyssadaguise kikysaputrii nanamirdad_ desta80s bobonsantoso \
                sophia_latjuba88 dahliachr chicco.jerikho cakecaine ahquote \
                shela_lala96 jakarta.terkini dillaljaidi indrowarkop_asli andreadianbimo

# TikTok — 25 akun
venv/Scripts/python.exe post_pipeline.py \
    --platform tiktok \
    --results 10 \
    --batch-size 10 \
    --max-charge-usd <plafon> \
    --usernames erickapineda09 eunicetjoaa shaturday knzymyln__ pandawaragroup \
                dennysumargoreal yourrkayesss efritaasmr marcelldegen mursid241 \
                dimsthemeatguy veliaveve_ arafahrianti02 botakteras imeyhou \
                celinenobleza azmannis megandomanii syahnazsadiqah cheekykiddo \
                bangsaonline viliacarl drrichardlee vamells milaalawiyah
```

**Input file: tidak ada.** Username diberikan langsung lewat `--usernames`; `post_pipeline.py:236` mencocokkannya ke `kol_directory` dengan `fetch_usernames(..., limit=100000)`.

## 3.3 Aliran data setelah scrape

```text
Apify actor
   ↓  post_pipeline._insert() → post_raw_store.insert_ig_posts / insert_tt_videos
l0_raw.ig_media_snapshots_apify  /  l0_raw.tt_video_apify     [append-only]
   ↓  sp_sync_instagram_post() / sp_sync_tiktok_post()
l0_harmonization.instagram_post  /  tiktok_post
   ↓  sp_build_unified_post()   ← ER per post dihitung di sini (migration 024)
l1_silver.unified_post
   ↓  asset ig_post_analysis / tt_post_analysis
feature.{ig,tt}_post_analysis        (rank, top_hashtags, engagement_rate)
   ↓  asset ig_engagement_analysis / tt_engagement_analysis
feature.{ig,tt}_engagement_analysis  (ER per AKUN, persen)
   ↓  asset post_metric / kol_metric_daily / kol_metric_monthly / content_format_daily
l2_gold.post_metric.er_followers            (fraksi 0..1)
l2_gold.kol_metric_daily.er_followers_daily (fraksi 0..1)   ← SOURCE OF TRUTH AUTOME_2
```

Tidak ada komponen baru di jalur ini. Seluruhnya asset dan procedure yang sudah ada.

---

# 4. Actor yang Digunakan

| Platform | Kelas scraper | Actor sebenarnya | Input | Sumber |
|---|---|---|---|---|
| Instagram | `InstagramPostScraper` | **`apify/instagram-scraper`** | `{"directUrls":[...], "resultsType":"posts", "resultsLimit":10, "addParentData":false}` | `apify_posts.py:27, 63, 67` |
| TikTok | `TikTokVideoScraper` | **`clockworks/tiktok-scraper`** | `{"profiles":[...], "profileScrapeSections":["videos"], "resultsPerPage":10, shouldDownload*: false}` | `apify_posts.py:183, 188` |

Keduanya menerima banyak username per run. `chunked()` memecah jadi batch 10.

---

# 5. Hasil DRY RUN

## 5.1 Instagram

```
INFO    | Mengambil 3409 username instagram dari kol_directory
Platform   : instagram
Akun       : 25
Mode       : SCRAPE apify/instagram-profile-scraper     ← ⚠ LABEL SALAH
run_id     : 3b176611-dfd9-4386-833a-8d56df82fb7f
[dry-run] tidak ada yang di-scrape maupun ditulis.
  (25 username terdaftar)
```

## 5.2 TikTok

```
INFO    | Mengambil 4086 username tiktok dari kol_directory
Platform   : tiktok
Akun       : 25
Mode       : SCRAPE clockworks/tiktok-scraper           ← benar
run_id     : 0c357d31-7148-4b9f-867d-55865f924dd0
[dry-run] tidak ada yang di-scrage maupun ditulis.
  (25 username terdaftar)
```

## 5.3 Verifikasi

| Cek | Hasil |
|---|---|
| 50 username resolve ke `kol_directory` | ✅ 25 IG + 25 TT |
| Tidak ada yang berlipat / hilang | ✅ 1:1 |
| `--dry-run` tidak menulis apa pun | ✅ `return 0` sebelum blok scrape (`post_pipeline.py:266`) |
| Actor TikTok benar | ✅ |
| **Actor Instagram salah label** | ❌ **lihat §11** |

---

# 6–9. Hasil Scraping, Funnel, Coverage, Biaya

**BELUM ADA — pilot tidak dijalankan.**

Alasannya di §11. Begitu keputusan lo turun, urutan pengukurannya sudah disiapkan:

| Yang akan diukur | Query |
|---|---|
| KOL berhasil scrape | `scheduler_logs` per `run_id` |
| Post masuk L0 | `count(*)` per `scrape_run_id` di `l0_raw.*` |
| Post masuk L1 | `unified_post` untuk 50 `social_account_id` |
| Post punya denominator | `post_metric.followers_at_post_date IS NOT NULL` |
| Post masuk perhitungan ER | `post_metric.er_followers IS NOT NULL` |
| KOL dapat ER L2 | `kol_metric_daily.er_followers_daily IS NOT NULL` |
| ER sebelum vs sesudah | baseline **22 KOL** |
| Biaya | `BatchResult.cost_usd` dari `usage_total_usd` tiap run |

---

# 10. Apakah Aman Scale ke 500 KOL?

**Belum bisa dijawab — butuh hasil pilot dulu.** Yang sudah pasti dari preflight:

| Aspek | Status |
|---|---|
| Populasi memadai | ✅ 1.927 kandidat memenuhi syarat |
| Linking aman | ✅ 0 FK ganda, 0 mismatch platform |
| Actor menerima batch | ✅ ketiganya |
| Plafon biaya ada | ✅ `--max-charge-usd` |
| L0 append-only | ✅ snapshot lama tidak tertimpa |
| Representativitas pilot | ❌ **50 kandidat semuanya Mega** — tidak mewakili 4.885 akun Nano+Micro |

Rekomendasi: sebelum 500, jalankan **pilot kedua di tier Micro/Nano**. Konversi ER akun kecil hampir pasti berbeda karena frekuensi posting lebih rendah.

---

# 11. ⛔ Perubahan Kode Minimum yang Ternyata Diperlukan

## Temuan: `source_actor` Instagram tercatat sebagai actor yang salah

### File & baris

**`post_pipeline.py:227–229`**

```python
actor = (
    cfg.apify.actor_id if platform == "instagram" else cfg.tiktok.actor_id
)
```

### Kenapa salah

| Langkah | Nilai |
|---|---|
| `cfg.apify.actor_id` ← `.env` `APIFY_ACTOR_ID` | `apify/instagram-profile-scraper` |
| Actor yang **benar-benar dipanggil** — `_build_scraper()` (`post_pipeline.py:90–94`) membangun `InstagramPostScraper`, yang memakai `DEFAULT_IG_POST_ACTOR` (`apify_posts.py:27, 63`) | **`apify/instagram-scraper`** |
| Ke mana `actor` mengalir | `_insert()` → `insert_ig_posts(source_actor=actor)` → kolom `l0_raw.ig_media_snapshots_apify.source_actor`, dan `scheduler_logs.actor` |

Jadi barisnya akan tertulis berasal dari **profile-scraper**, padahal datanya dari **instagram-scraper**.

### Bukti bahwa ini memang salah

188 baris Instagram yang sudah ada di `l0_raw.ig_media_snapshots_apify` **seluruhnya** bernilai `apify/instagram-scraper`. Menjalankan pilot sekarang akan memasukkan nilai **kedua yang berbeda** untuk actor yang sama — provenance jadi tidak konsisten di dalam satu tabel.

### TikTok tidak terdampak

`cfg.tiktok.actor_id` = `clockworks/tiktok-scraper`, dan `TikTokVideoScraper` memang memakai actor itu (`apify_posts.py:183` — `cfg.actor_id or DEFAULT_TT_VIDEO_ACTOR`). Terbukti di dry-run.

### Tingkat keparahan: SEDANG — bukan blocker pipeline

| Pertanyaan | Jawaban |
|---|---|
| Apakah menghentikan aliran L0 → L1 → Feature → L2? | **Tidak.** `grep -rn "source_actor" migrations/*.sql` → **0 hasil**. Tidak ada sync procedure yang membaca kolom ini |
| Apakah ER tetap terhitung? | **Ya**, tidak terpengaruh sama sekali |
| Apa yang rusak? | (a) Provenance — kolom ini ada persis untuk mencatat actor asal. (b) `raw_store.count_existing(scraped_at, source_actor)`, penjaga ingest ganda, ber-key pada `source_actor` — label yang salah membuat penjaganya meleset |

### Perubahan minimum yang diperlukan

**Satu baris**: ambil actor id dari objek scraper, bukan dari config. Atribut `self._actor_id` sudah ada di `apify_runner.py:112`. Karena `actor` sekarang di-assign **sebelum** `scraper` dibangun, perbaikannya berupa memindahkan/menurunkan ulang nilainya setelah `_build_scraper()` dipanggil.

**Saya belum menyentuh kode ini.** Menunggu keputusan lo.

### Kenapa mengubah `.env` bukan solusi

Mengganti `APIFY_ACTOR_ID` jadi `apify/instagram-scraper` memang membetulkan label di sini, tapi **merusak `pipeline.py`**: `InstagramProfileScraper` (`apify_ig.py:22`) tidak menetapkan `actor_id` sendiri, jadi ia jatuh ke `cfg.actor_id`. Scraping profil akan memanggil actor post. Jangan ditempuh.

---

# Tiga opsi untuk lo pilih

| Opsi | Isi | Konsekuensi |
|---|---|---|
| **A** | Perbaiki 1 baris di `post_pipeline.py`, lalu jalankan seluruh 50 | Provenance bersih. Butuh persetujuan lo untuk menyentuh kode |
| **B** | Jalankan **TikTok 25 dulu** (label sudah benar), tahan Instagram sampai fix | Tidak ada perubahan kode. Pilot jadi separuh, dan TikTok kebetulan platform yang aturan sampelnya nol-kerugian — hasilnya akan lebih bagus dari rata-rata |
| **C** | Jalankan seluruh 50 apa adanya, betulkan label belakangan | Paling cepat, tapi 25 baris IG masuk dengan provenance salah dan perlu dibersihkan lewat UPDATE ke produksi |

Saya sarankan **A**. Perubahannya satu baris, risikonya nol terhadap kalkulasi ER, dan menghindari menulis data ber-provenance salah ke tabel yang append-only.

---

*Preflight read-only. Tidak ada perubahan kode, database, migration, commit, push, maupun panggilan Apify. Seluruh pengecekan memakai `set_session(readonly=True)` dan `--dry-run`.*
