# AUTOME_2 — Development Execution Plan P0

**Read-only · 8 September 2026 · belum ada implementasi**

| Repo | Branch | Checkpoint | Working tree |
|---|---|---|---|
| `scrapper-project` | `main` | `116243e` | bersih (dokumen audit untracked) |
| `autometric` | `engkol_v1` | `84ea2fc` | bersih |

---

> # ⚠ KOREKSI BESAR ATAS AUDIT SEBELUMNYA — P0-1 berubah total
>
> Audit sebelumnya menyimpulkan rate card = **source/data missing** dan menyarankan "cari source-nya".
>
> **Itu salah. Source-nya ada, lengkap, dan sudah di database.**
>
> Diverifikasi read-only hari ini:
>
> | Bukti | Hasil |
> |---|---|
> | `l0_raw.kol_roster_import` | **7.718 baris · 7.496 KOL distinct** |
> | Kolom harga (`story_price`, `story_session_price`, `feed_photo_price`, `feed_video_price`, `reel_price`, `live_price`, `owning_asset_price`) | **terisi untuk 7.496 KOL — ketujuhnya** |
> | Contoh nilai | `1500000.0`, `500000.0`, `95000000.0` (IDR) |
> | Procedure `l0_harmonization.sp_sync_roster_rate_card()` | **ADA**, 6.861 karakter, lengkap dan matang |
> | Procedure `l1_silver.sp_build_unified_rate_card()` | **ADA** |
>
> Procedure itu membaca `kol_roster_import`, memekarkan 7 kolom harga jadi `post_type` lewat `CROSS JOIN LATERAL`, men-dedup di grain `(akun, post_type)`, membuang harga NULL/0, menulis `currency = 'IDR'`, dan mencatat ke `sync_log`.
>
> **Kenapa tabelnya masih 0 baris:** `orchestration/.../harmonization.py` sengaja tidak membuatkan asset untuk rate card. Alasannya tertulis di keputusan #4: *"tabel `l0_raw` sumbernya 0 baris"*. Alasan itu **benar untuk `l0_extra.ig/tt_rate_card`** (memang 0), tapi **tidak berlaku untuk `kol_roster_import`** yang berisi 7.496 KOL.
>
> Docstring file yang sama sudah menyebut ini: *"`sp_sync_all` juga tidak memanggil `sp_sync_roster_rate_card` (yang justru menghasilkan seluruh 9.210 rate card)"*.
>
> **Jadi P0-1 bukan "cari source", melainkan "jalankan procedure yang sudah ada, setelah diverifikasi."** Angka 9.210 di docstring `kolMeasured.ts` dan `gold_profile.py` bukan halusinasi — itu hasil yang pernah/akan dihasilkan procedure ini.

---

# 1. Executive Decision

## 1.1 Bisa langsung dikerjakan secara teknis — tanpa keputusan produk

| # | Pekerjaan | Kenapa aman |
|---|---|---|
| **A** | **Verifikasi read-only `sp_sync_roster_rate_card`** — baca definisi lengkap, hitung berapa baris yang akan dihasilkan lewat `EXPLAIN`/simulasi `SELECT` | Tidak menulis apa pun. Menjawab P0-1 secara definitif |
| **B** | **Susun daftar target post scraping** (query read-only) | Sudah terbukti di preflight sebelumnya |
| **C** | **Dry-run `post_pipeline.py` dan `pipeline.py`** | `--dry-run` tidak memanggil Apify |
| **D** | **Investigasi ER read-only** (P0-5): bandingkan 3 sumber untuk akun yang sama | Sudah sebagian dikerjakan; tinggal dirapikan jadi tabel keputusan |

## 1.2 Butuh keputusan mentor/product — **jangan disentuh dulu**

| # | Keputusan | Kenapa bukan keputusan teknis |
|---|---|---|
| **Q1** | Menjalankan `sp_sync_roster_rate_card` di produksi | Menulis ~9.210 baris ke L0 harmonization + L1. Reversible, tapi tetap perubahan data produksi |
| **Q2** | NULL handling di filter `minEr` / `maxRate` / `growth` | Menentukan apakah 77–99,7% roster hilang saat slider digeser |
| **Q3** | Canonical ER | Pindah ke L2 memangkas cakupan filter 1.756 → 22 KOL |
| **Q4** | Interpretasi Growth | "sejak snapshot terakhir" vs "30D"; ambang classification |
| **Q5** | Biaya Apify untuk perluasan post scraping | ~1.942 akun |

## 1.3 Menunggu data/waktu — tidak bisa dipercepat kode

| # | Item | Penghambat |
|---|---|---|
| **W1** | Growth 30D, momentum, consistency, stability, viral frequency | Butuh snapshot berjarak ≥30 hari. Paling cepat **awal Oktober** kalau scheduler mulai minggu ini |
| **W2** | Reach, impressions, shares/saves IG, watch time, demografi umur | Insights API — lead time eksternal |

---

# 2. P0 Dependency Map

| P0 | Task | Bisa mulai sekarang? | Dependency | Owner decision | Risk |
|---|---|---|---|---|---|
| **P0-1a** | Verifikasi read-only rate card chain | **✅ Ya** | — | — | Nol |
| **P0-1b** | Jalankan `sp_sync_roster_rate_card` + `sp_build_unified_rate_card` | ❌ | P0-1a | **Q1** | Menulis ~9.210 baris L0+L1. Reversible (procedure idempoten, `ON CONFLICT`) |
| **P0-2a** | Putuskan NULL handling 3 filter | ❌ | — | **Q2** | Nol (keputusan) |
| **P0-2b** | Terapkan NULL handling di `kolDirectory.ts` | ❌ | P0-2a | — | Rendah — 1 file, klausa WHERE |
| **P0-3a** | Susun daftar target post scraping (read-only) | **✅ Ya** | — | — | Nol |
| **P0-3b** | Dry-run `post_pipeline.py` | **✅ Ya** | P0-3a | — | Nol |
| **P0-3c** | Jalankan scraping bertahap | ❌ | P0-3b | **Q5** | Biaya Apify; L0 append-only jadi aman |
| **P0-4a** | Dry-run `pipeline.py --order stale` | **✅ Ya** | — | — | Nol |
| **P0-4b** | Jadwalkan profil berkala | ❌ | P0-4a | **Q5** | Biaya berulang |
| **P0-5a** | Investigasi ER (read-only, tabel keputusan) | **✅ Ya** | — | — | Nol |
| **P0-5b** | Pindah canonical ER | ❌ | P0-5a | **Q3** | **Tinggi** — cakupan filter 1.756 → 22 |

**Empat task bisa dimulai hari ini tanpa menunggu siapa pun: P0-1a, P0-3a, P0-3b, P0-4a, P0-5a.**

---

# 3. Exact Development Sequence

Urutan ini disusun supaya setiap langkah bisa diverifikasi sebelum yang berikutnya, dan setiap perubahan data punya checkpoint.

```
LANGKAH 1  — CLARIFICATION (kirim Q1–Q5 ke mentor/product)
              paralel dengan langkah 2

LANGKAH 2  — READ-ONLY VERIFICATION           [tidak perlu approval]
   2a  Simulasi sp_sync_roster_rate_card: berapa baris, berapa akun,
       berapa yang harganya 0 dan terbuang
   2b  Daftar target post scraping: 1.942 akun sudah punya snapshot,
       belum punya post
   2c  Dry-run post_pipeline.py --dry-run untuk sampel 25 akun
   2d  Dry-run pipeline.py --dry-run --order stale
   2e  Tabel keputusan ER: 3 sumber x formula x satuan x coverage

LANGKAH 3  — DATA RUN #1: RATE CARD           [butuh Q1]
   3a  CALL sp_sync_roster_rate_card()        -> L0 harmonization
   3b  CALL sp_build_unified_rate_card()      -> L1
   3c  Validasi: hitung baris, akun, mata uang, sebaran post_type
   3d  Uji ulang filter maxRate: dari 0 KOL jadi berapa?
   -> CHECKPOINT: catat hasil, belum ubah kode

LANGKAH 4  — IMPLEMENTATION #1: NULL handling [butuh Q2]
   4a  Ubah klausa WHERE di kolDirectory.ts sesuai keputusan
   4b  Test unit + typecheck
   4c  Validasi: hitung hasil filter sebelum/sesudah
   -> CHECKPOINT COMMIT di autometric

LANGKAH 5  — DATA RUN #2: POST SCRAPING       [butuh Q5]
   5a  Pilot 50 akun (bukan 1.942)
   5b  Validasi L0 -> L1 -> Feature -> L2
   5c  Ukur konversi nyata, bandingkan estimasi
   5d  Rollout bertahap batch 200-500 kalau konversi sesuai
   -> CHECKPOINT: tidak ada perubahan kode, hanya data

LANGKAH 6  — DATA RUN #3: SCHEDULER PROFIL    [butuh Q5]
   6a  Jalankan pipeline.py --order stale berkala
   6b  Monitor: berapa akun dapat snapshot ke-2, ke-3
   6c  Tunggu span >= 30 hari (perkiraan awal Oktober)

LANGKAH 7  — IMPLEMENTATION #2: canonical ER  [butuh Q3, SETELAH langkah 5]
   Sengaja paling akhir: cakupan ER L2 naik dulu lewat langkah 5,
   supaya keputusan Q3 diambil di atas angka yang lebih baik.
```

**Alasan urutan ini:** rate card (langkah 3) tidak butuh scraping dan bisa langsung menghidupkan seluruh sisi komersial. Canonical ER (langkah 7) sengaja paling akhir karena keputusannya jauh lebih mudah setelah cakupan L2 naik dari 22 akun.

---

# 4. Per Task

## P0-1 — Rate Card

### Objective
Menghidupkan `l1_silver.unified_rate_card` dari source yang sudah ada, sehingga filter `maxRate`, kolom rate card, dan seluruh alur Ordering punya dasar harga.

### Existing file/table

| Lapisan | Objek | Kondisi |
|---|---|---|
| Source | `l0_raw.kol_roster_import` | **7.718 baris, 7.496 KOL, 7 kolom harga terisi** |
| Procedure L0→Harmonization | `l0_harmonization.sp_sync_roster_rate_card()` | **ADA**, tidak pernah dipanggil |
| Target harmonization | `l0_harmonization.instagram_rate_card`, `tiktok_rate_card` | 0 baris |
| Procedure Harmonization→L1 | `l1_silver.sp_build_unified_rate_card()` | **ADA** |
| Target L1 | `l1_silver.unified_rate_card` | 0 baris |
| Konsumen | `kolMeasured.ts` → `measured.rates[]`, `rateFrom`, `rateCount`; filter `maxRate` di `kolDirectory.ts` | siap |

### Pipeline/endpoint yang dipakai
Seluruhnya **existing**. `/discover/rates` dan `kolMeasured.getKolMeasured()` sudah membaca `unified_rate_card` — begitu terisi, langsung mengalir tanpa perubahan kode.

### File yang kemungkinan perlu diubah
**Kemungkinan besar: TIDAK ADA.**
Opsional menyusul, kalau ingin otomatis: tambahkan asset `roster_rate_card` di `orchestration/kol_orchestration/assets/harmonization.py` (pola sama persis dengan 4 asset yang sudah ada di file itu). **Bukan bagian P0.**

### Database yang terlibat
`l0_raw` (baca) → `l0_harmonization` (tulis) → `l1_silver` (tulis)

### Migration diperlukan?
**Tidak.** Semua tabel dan procedure sudah ada.

### Scraping diperlukan?
**Tidak.** Data sudah di database.

### Endpoint baru atau modify?
**Tidak keduanya.** Endpoint existing sudah membaca tabel yang akan terisi.

### Yang harus diverifikasi lebih dulu (read-only, tanpa approval)

| # | Verifikasi | Query |
|---|---|---|
| V1 | Berapa baris akan dihasilkan | Simulasi `SELECT` dari body procedure tanpa `INSERT` |
| V2 | Berapa harga bernilai `0.0` dan terbuang | `count(*) FILTER (WHERE reel_price = '0.0')` dst |
| V3 | 222 baris ber-`platform_id` NULL | Apakah ikut terbuang oleh `JOIN platforms` |
| V4 | Nilai `platform` sampah (`'76800'`, sebuah URL) | Apakah kolom itu dipakai procedure, atau ia pakai `platform_id` |
| V5 | Apakah `sp_build_unified_rate_card` idempoten | Baca `ON CONFLICT`-nya |

### Test
Tidak ada unit test kode — ini perubahan data. Yang berlaku: query validasi sebelum/sesudah.

### Validation query

```sql
-- sesudah CALL, jalankan read-only:
SELECT 'harmonization ig' t, count(*) FROM l0_harmonization.instagram_rate_card
UNION ALL SELECT 'harmonization tt', count(*) FROM l0_harmonization.tiktok_rate_card
UNION ALL SELECT 'L1 unified',      count(*) FROM l1_silver.unified_rate_card;

SELECT count(DISTINCT social_account_id) akun, count(*) baris,
       string_agg(DISTINCT currency, ', ') mata_uang, count(DISTINCT post_type) jenis
  FROM l1_silver.unified_rate_card;

-- dampak ke filter maxRate:
SELECT count(*) FILTER (WHERE EXISTS (
    SELECT 1 FROM public.kol_social_account ksa
      JOIN l1_silver.unified_rate_card u ON u.social_account_id = ksa.social_account_id
     WHERE ksa.kol_id = kd.id AND u.fee IS NOT NULL)) lolos_filter,
       count(*) total
  FROM public.kol_directory kd WHERE kd.directory_status = 'active';
```

### Expected result
Baseline docstring menyebut **9.210 baris / 7.230 akun**. Kalau hasilnya jauh berbeda, **berhenti dan laporkan** — jangan lanjut ke L1.

### Rollback / checkpoint
- Procedure memakai `ON CONFLICT` → rerun aman, idempoten.
- Rollback: `DELETE FROM l0_harmonization.instagram_rate_card WHERE source = 'uploader'` (dan tiktok, dan L1). **Butuh approval terpisah — jangan siapkan sebagai bagian eksekusi.**
- Checkpoint: catat `count(*)` ketiga tabel **sebelum** menjalankan.

### `NEEDS DECISION`
- **Q1** — boleh menjalankan procedure di produksi?
- Harga bernilai `0.0`: procedure sudah membuangnya. Apakah itu benar, atau `0` berarti "gratis/nego"?

---

## P0-2 — Filter yang hasilnya berpotensi salah

### `maxRate`

| Aspek | Isi |
|---|---|
| **Masalah teknis** | `EXISTS (… u.fee IS NOT NULL AND u.fee <= $11)` — terukur **0 dari 7.720** lolos |
| **Masalah produk** | Filter aktif di UI, digeser sedikit → direktori kosong tanpa penjelasan |
| **Klarifikasi** | Selesai sendiri setelah P0-1. **Jangan ubah kodenya dulu** |
| **Perubahan kode** | Kemungkinan besar **nol** — tunggu P0-1 |
| **Test** | Ulangi validation query P0-1 |

### `minEr`

| Aspek | Isi |
|---|---|
| **Masalah teknis** | `b.er_pct >= $5` dengan `er_pct = kd.engagement_rate`. NULL gagal perbandingan → **5.964 KOL terbuang diam-diam** |
| **Masalah produk** | Apakah "KOL yang ER-nya belum pernah diukur" harus hilang saat user memasang minimum? UI **sudah memperingatkan** — `KolDirectoryFilters.tsx` menulis *"memasang minimum akan menyembunyikan creator yang belum pernah diukur"* |
| **Klarifikasi** | **Q2** |
| **Perubahan kode minimum** (jika NULL harus ikut lolos) | Satu klausa di `kolDirectory.ts` `filtered` CTE: `AND ($5::float8 IS NULL OR b.er_pct IS NULL OR b.er_pct >= $5)` |
| **Test** | Hitung hasil `minEr=3` sebelum (219) vs sesudah. Unit test tidak perlu — ini SQL |

### `growthMin` / `growthMax`

| Aspek | Isi |
|---|---|
| **Masalah teknis** | Filter **benar secara implementasi** (binding `$12`/`$13` sudah diverifikasi). Cakupan datanya 25/7.720 |
| **Masalah produk** | `growthMin=0` → 18 hasil. Bukan bug — memang baru 25 KOL punya angkanya |
| **Klarifikasi** | **Q2** (NULL) + **Q4** (interpretasi) |
| **Perubahan kode minimum** | Kemungkinan **nol**. UI sudah memakai preset yang dikalibrasi (>0%, 0%, <0%, ≥0,5%, ≥1%), bukan ambang prototype 4,5%/8% |
| **Test** | Sudah terukur; ulangi setelah P0-4 berjalan |

### File yang terlibat (ketiganya)
`src/lib/discover/kolDirectory.ts` — `filtered` CTE. **Satu file, tiga klausa WHERE.**

### Migration / scraping / endpoint baru
Tidak, tidak, tidak. **Modify existing.**

### Rollback
Perubahan satu file di branch `engkol_v1` yang sudah punya checkpoint `84ea2fc`. `git checkout` cukup.

---

## P0-3 — Perluasan Post Scraping

### Objective
Menaikkan cakupan post dari 30 akun, memakai pipeline yang ada, dengan ownership filter yang sudah ter-commit di `116243e`.

### Target populasi

| Kriteria | Jumlah |
|---|---:|
| Punya snapshot follower (denominator ER sudah ada) **dan** belum punya post | **1.942** (912 IG + 1.030 TT) |
| Jendela denominator sudah terbuka | 21,6–24,9 hari |

### Cara memilih KOL

Query read-only yang sudah terbukti di preflight — syaratnya: punya `kol_social_account` + `social_account` dengan `platform_id` cocok, punya snapshot `unified_profile` ber-`followers_count > 0`, belum punya baris di `unified_post` maupun kedua tabel post L0, `username` tidak kosong, `directory_status='active'`.

**Catatan penting:** pilot sebelumnya memakai `--order followers` sehingga seluruh 50 kandidat bertier **Mega**. Untuk rollout, ambil **sampel berlapis per tier** supaya konversi yang diukur mewakili roster (Nano 1.943 + Micro 2.942 = 63% populasi).

### Command yang digunakan

```bash
# 1. dry-run dulu — tidak memanggil Apify
venv/Scripts/python.exe post_pipeline.py --platform instagram \
    --results 10 --batch-size 10 --dry-run --usernames <25 username>

# 2. run nyata dengan plafon biaya
venv/Scripts/python.exe post_pipeline.py --platform instagram \
    --results 10 --batch-size 10 --max-charge-usd 2.00 --usernames <25 username>

# 3. sama untuk --platform tiktok
```

**Bukan `--from-file`** — flag itu me-replay file `.jsonl` hasil scrape, bukan daftar username.

### Mencegah overwrite historical data

| Mekanisme | Bukti |
|---|---|
| L0 post **append-only** | `INSERT … RETURNING id` tanpa `ON CONFLICT` (`post_raw_store.py`) |
| Dedup di sisi aplikasi | `split_new_and_duplicate()` — post dengan `content_id` yang sudah ada untuk akun itu tidak dikirim ke INSERT |
| Peringatan ingest ganda | `raw_store.count_existing(scraped_at, source_actor)` |

**Tidak ada jalur DELETE atau UPDATE di `post_raw_store.py`** — dinyatakan eksplisit di docstring modul.

### Memastikan ownership filter bekerja

Sudah ter-commit di `116243e` dan tervalidasi terhadap dua payload nyata tanpa Apify:

| Payload | Lolos | Dibuang non-roster |
|---|---:|---:|
| 8 Sep (62 item) | 26 | 36 |
| 20 Agu (130 item) | 91 | 39 |

Ulangi validasi itu setelah setiap batch: `stats.skipped_non_roster` harus > 0 dan tidak ada baris L0 baru ber-`social_account_id` NULL.

### Memastikan maksimal 10 latest per actual owner

`_filter_owned()` mengelompokkan lewat `social_account_id` (pemilik sebenarnya), bukan URL. Diuji dengan `--results 3`: 38 lolos, 53 dibuang lewat batas, maks 3/pemilik.

**Validasi setelah run:**
```sql
SELECT social_account_id, count(*) n
  FROM l0_raw.ig_media_snapshots_apify
 WHERE scrape_run_id = '<run_id>'
 GROUP BY 1 HAVING count(*) > 10;   -- harus 0 baris
```

### Monitoring cost Apify

| Mekanisme | Nilai |
|---|---|
| `--max-charge-usd` per run | plafon; pilot lalu memakai 2,00 |
| Biaya tercatat per batch | `BatchResult.cost_usd` dari `usage_total_usd`, muncul di log |
| Baseline terukur | IG 62 item = **$0,5382** (3 batch) · TT 3 item = **$0,1230** |

### Validasi L0 → L1 → Feature → L2

Terbukti pipeline tidak kehilangan apa pun (L0→L1 = 0% hilang). Query per `scrape_run_id`:
L0 (`count(*)`) → harmonization → `unified_post` → `feature.*_post_analysis` → `post_metric` → `kol_metric_daily.er_followers_daily IS NOT NULL`.

### Sample KOL untuk verification
Ambil 3 dari batch: satu ber-post terbanyak, satu ber-post sedikit, satu yang gagal. Trace per post: `posted_at` vs `snapshot_pertama` akun → jelaskan kenapa dapat/tidak dapat denominator.

### Expected result
Berdasarkan konversi terukur (73,3% akun ber-post akhirnya dapat ER, dengan sampel bias ke Mega): **pilot 50 akun → 27–37 dapat ER**. Angka di bawah 20 berarti asumsinya salah — **berhenti dan ukur ulang**.

### Migration / endpoint baru
Tidak. Tidak.

### Rollback / checkpoint
Tidak ada rollback data (L0 append-only, dan menghapus L0 butuh approval terpisah). Checkpoint = catat `count(*)` L0/L1/L2 **sebelum** tiap batch, dan simpan `scrape_run_id`.

### `NEEDS DECISION`
- **Q5** — budget Apify
- Sampel berlapis per tier atau tetap follower terbesar dulu?
- Nilai `--results`: tetap 10, atau dinaikkan untuk mengejar 10 milik-sendiri? (audit ownership menyarankan **jangan dulu** sebelum cap 10 tervalidasi di run nyata)

---

## P0-4 — Scheduler Profile Historical

### Objective
Mengumpulkan snapshot follower berulang supaya Growth 30D, consistency, dan momentum punya dasar. Fokus pada `account identifier + followers_count + timestamp`.

### Tool yang dipakai — **bukan `scheduler_engine.py`**

| Tool | Cocok? | Alasan |
|---|---|---|
| `scheduler_engine.py` | **❌ TIDAK** | `PROFILE_TARGET_LIMIT = 1` (1 akun/run) dan syarat `NOT EXISTS` di tabel profil **dan** post — ia **hanya bisa memilih akun yang belum pernah di-scrape**. Secara struktural tidak bisa membuat snapshot kedua |
| **`pipeline.py`** (Instagram) | **✅ YA** | `--limit` s.d. 1000, `--batch-size` 100, dan **`--order stale`** = `last_refreshed_at ASC NULLS FIRST` — persis yang dibutuhkan untuk snapshot berulang |
| `tiktok_pipeline.py` | ✅ | padanan TikTok |

**Ini bukan layer baru** — memakai script yang sudah ada dengan flag yang sudah ada.

### Interval scraping

`NEEDS DECISION`. Yang bisa saya nyatakan dari data:
- Growth 30D butuh dua snapshot berjarak ≥ ambang span (usulan ≥21 hari).
- Snapshot saat ini: 14/17/18 Agu, lalu 24/27/28 Agu.
- Kalau scraping berkala mulai minggu ini, span 30 hari tersedia **awal Oktober**.
- Interval **mingguan** cukup untuk Growth 30D dan jauh lebih murah daripada harian.

### Selection logic

```bash
# dry-run dulu
venv/Scripts/python.exe pipeline.py --limit 1000 --order stale --dry-run

# run nyata
venv/Scripts/python.exe pipeline.py --limit 1000 --batch-size 100 \
    --order stale --max-cost-usd <plafon> --yes
```

`--order stale` mendahulukan akun yang paling lama tidak di-refresh — otomatis meratakan cakupan tanpa daftar manual.

### Penyimpanan historical snapshot — **sudah aman, tidak perlu layer baru**

| Lapisan | Perilaku | Bukti |
|---|---|---|
| `l0_raw.ig_profile_apify` | **append-only** | `INSERT … RETURNING id` tanpa `ON CONFLICT`. Terukur: 953 baris / 950 pasangan (akun,tanggal) / 935 akun |
| `l1_silver.unified_profile` | grain `(social_account_id, date)` | Terukur: 2.001 baris / 2.001 pasangan unik / 1.976 akun |
| Scrape dua kali di hari sama | `ON CONFLICT DO UPDATE` — menimpa dalam hari yang sama | Perilaku yang benar |

### Memastikan `followers_count` tidak overwrite history

**Sudah aman secara desain.** `db.update_profiles()` memang menimpa `kol_directory.followers_count`, **tapi kolom itu bukan sumber history**. History hidup di `unified_profile` yang berjenjang tanggal, dan itulah yang dibaca `sp_build_unified_profile()` untuk menghitung growth.

Opsi `--no-update-db` tersedia kalau ingin murni menambah snapshot tanpa menyentuh roster. **Tidak disarankan**: `--update-db` juga menyegarkan `last_refreshed_at`, yang memperbaiki badge Data Status (sekarang Live = **0**).

### L0 → Harmonization → L1 → Feature → L2
Rantai existing, terbukti 0% kehilangan (L0 profile 1.976 → L1 1.976).

### Kapan data cukup untuk Growth 30D

```sql
SELECT count(*) FILTER (WHERE span >= 21) siap_21h,
       count(*) FILTER (WHERE span >= 30) siap_30h, count(*) total
  FROM (SELECT social_account_id, max(date) - min(date) span
          FROM l1_silver.unified_profile WHERE followers_count IS NOT NULL
         GROUP BY 1 HAVING count(DISTINCT date) >= 2) x;
```
Baseline hari ini: **25 akun ber-2 snapshot, span 10–13 hari, 0 akun ≥25 hari.**

### Monitoring & failure handling
`pipeline.py` menulis metadata run ke `output/run_metadata_*.json` (biaya per batch, jumlah item). `--max-cost-usd` sebagai plafon. Kegagalan satu batch tidak menghentikan batch lain.

### Migration / scraping baru / endpoint baru
Tidak / bukan source baru (script existing) / tidak.

### `NEEDS DECISION`
- **Q5** — budget berulang
- Interval: mingguan / dua mingguan?
- Cakupan tiap run: 1.000 akun (batas `MAX_LIMIT`) atau lebih sedikit?

---

## P0-5 — Canonical ER

### Objective
Menyiapkan **bahan keputusan**, bukan mengimplementasi. Audit sudah membuktikan L2 paling benar secara formula tapi cakupannya 22 akun.

### Tabel keputusan (sudah terukur, tinggal dipakai)

| Sumber | Formula | Penyebut | Aturan sampel | Satuan | Terisi | Rentang |
|---|---|---|---|---|---|---|
| `kol_directory.engagement_rate` | `avg(likes+comments) / followers_saat_scrape × 100` | followers saat scrape | **tidak ada** | persen | **1.756 / 7.720** | 0 – **223,41%** |
| `feature.*_engagement_analysis` | `Σ(like+comment+share) / Σ(followers_pada_tanggal_post) × 100` | aditif, per tanggal post | ✅ eksplisit | persen | 22 akun | 0 – 16,15% |
| `l2_gold.kol_metric_daily.er_followers_daily` | `engagement_sum / followers_denom_sum` | aditif | ✅ eksplisit | **fraksi 0..1** | 73/280 baris · **22 akun** | 0 – 0,1615 |

### Apakah L2 layak jadi canonical?

**Ya pada formula, belum pada cakupan.** Formula L2 satu-satunya yang: penyebut followers-pada-tanggal-post, penyebut aditif, aturan sampel eksplisit, **0 nilai >100%, 0 negatif**.

Feature dan L2 cocok sampai <0,005 poin di 8 akun sampel — jadi keduanya konsisten; yang berbeda hanya roster.

### Impact

| Terhadap | Dampak |
|---|---|
| **List** | `erPct` berubah dari persen (roster) ke fraksi (L2) — **konversi ×100 wajib** |
| **Filter `minEr`** | Tanpa konversi, `minEr=3` vs maks `0,1615` → **0 hasil untuk semua KOL** |
| **Cakupan filter** | **1.756 → 22 KOL** |
| **Detail UI** | Sudah menampilkan keduanya (`creator.erPct` roster + `gold.daily[].erFollowers` L2) — dua angka beda satuan dalam satu response |

### Kenapa jangan dikerjakan sekarang

Cakupan L2 akan **naik sendiri** setelah P0-3 (perluasan post scraping). Mengambil keputusan Q3 di atas 22 akun jauh lebih buruk daripada di atas beberapa ratus.

### File yang akan terlibat (nanti)
`src/lib/discover/kolDirectory.ts` — `BASE` (`er_pct`) + `filtered` CTE ($5). Satu file.

### Migration / scraping / endpoint baru
Tidak / tidak / **modify existing**.

### `NEEDS DECISION`
**Q3** — dan sebaiknya **ditunda sampai setelah P0-3**.

---

# 5. Jangan Kerjakan (out of scope P0)

| # | Item | Alasan |
|---|---|---|
| 1 | Membuat scraper/tabel/endpoint rate card baru | **Source, procedure, dan tabelnya sudah ada.** Membuat yang baru = duplikasi |
| 2 | Insights API (reach, impressions, shares/saves IG, watch time, umur) | Lead time eksternal — ajukan aksesnya, jangan tunggu untuk P0 |
| 3 | Growth 30D, momentum, consistency, stability, viral frequency | Terblokir waktu, bukan kode. Paling cepat awal Oktober |
| 4 | Brand Fit, Opportunity Score, competitor saturation | Menunggu authenticity & content topic |
| 5 | Sentiment & content topic asset | Bernilai tinggi dan nol biaya Apify — tapi **P1**, bukan P0 |
| 6 | Saved list / collection / shortlist | Mandiri, tidak memblokir apa pun |
| 7 | Tabel monitoring per KOL (frekuensi/prioritas/next update) | P2 |
| 8 | Creator city, niche, YouTube, Story | Source baru |
| 9 | Membersihkan 43 baris salah atribusi | Terbukti **0/43** masuk ER. Prioritas rendah |
| 10 | Menaikkan `--results` di post scraping | Validasi dulu cap 10 di run nyata |
| 11 | Membuat asset Dagster untuk rate card | Setelah P0-1 terbukti, dan itu P1 |
| 12 | Memindahkan canonical ER | Tunggu cakupan naik (P0-3) |
| 13 | 18 filter sidebar AUTOME_2 lainnya | Menunggu calculation di atasnya |
| 14 | Menyentuh `is_collaboration` / rumus ER di L1-Feature-L2 | Terbukti benar; `is_collaboration` justru pengaman ER |

---

# 6. Product Questions

Siap kirim apa adanya.

> **Q1 — Rate card**
> Data harga 7.496 KOL sudah ada di `l0_raw.kol_roster_import`, dan procedure untuk memprosesnya (`sp_sync_roster_rate_card`) juga sudah ada — hanya belum pernah dijalankan. Boleh kami jalankan? Perkiraan hasil ~9.210 baris harga. Sifatnya idempoten dan bisa diulang.
>
> Ikutan: banyak harga bernilai `0`. Procedure membuangnya. Apakah `0` berarti "belum diisi" (benar dibuang) atau "gratis/nego" (harus disimpan)?

> **Q2 — NULL di filter**
> Saat user memasang minimum ER / max rate card / growth, KOL yang nilainya **belum pernah diukur** sekarang hilang dari hasil. Contoh: memasang ER minimum membuang 5.964 dari 7.720 KOL.
> Mana yang benar: (a) tetap dibuang, (b) ikut ditampilkan, atau (c) ditampilkan terpisah dengan penanda "belum diukur"?

> **Q3 — Canonical ER**
> Kami punya tiga angka ER dengan formula berbeda. Yang paling benar (L2 Gold) cuma tersedia untuk 22 KOL; yang sekarang dipakai (roster) tersedia untuk 1.756 KOL tapi punya nilai mustahil sampai 223%.
> Mana yang dipilih: akurat-tapi-sedikit, atau luas-tapi-kasar? **Saran kami: tunda keputusan ini sampai cakupan L2 naik lewat perluasan scraping.**

> **Q4 — Interpretasi Growth**
> Angka growth yang kami punya adalah perubahan follower **antar dua snapshot berjarak 10–13 hari**, bukan 30 hari. Prototype AUTOME_2 memintanya sebagai "Growth 30D".
> Sementara ini: tampilkan apa adanya sebagai "sejak snapshot terakhir" (yang sekarang berjalan), atau kosongkan sampai punya rentang 30 hari?

> **Q5 — Budget Apify**
> Untuk memperluas cakupan post dari 30 ke ~1.942 KOL. Baseline biaya terukur: **$0,54 untuk 25 akun Instagram**. Perkiraan kasar untuk 1.942 akun: **$35–45**, dijalankan bertahap.
> Ditambah scraping profil berkala (mingguan) untuk membangun histori Growth.
> Berapa plafon yang disetujui, dan untuk periode berapa lama?

---

# 7. Recommended First Action

## Jalankan verifikasi read-only rate card (P0-1a).

**Satu langkah, nol risiko, dan berpotensi menghapus satu kategori "source missing" seluruhnya.**

Kenapa ini yang pertama:

| Alasan | Penjelasan |
|---|---|
| **Tidak butuh persetujuan siapa pun** | Murni `SELECT`, tidak menulis apa pun |
| **Tidak butuh biaya** | Tidak memanggil Apify |
| **Tidak butuh menunggu** | Datanya sudah ada di database sekarang |
| **Dampaknya paling besar per usaha** | Membuka 7 requirement komersial (#60–66) dan memperbaiki filter `maxRate` yang sekarang mengembalikan 0 dari 7.720 |
| **Mengubah isi Q1 jadi konkret** | Lo bisa bertanya ke mentor dengan angka pasti, bukan "sepertinya ada data" |

Isi verifikasinya: simulasikan `sp_sync_roster_rate_card` sebagai `SELECT` (tanpa `INSERT`), hitung berapa baris dan akun yang akan dihasilkan, berapa yang terbuang karena harga `0`, dan apa yang terjadi pada 222 baris ber-`platform_id` NULL.

Kalau hasilnya mendekati 9.210 baris / 7.230 akun seperti yang tertulis di docstring, **Q1 tinggal jadi persetujuan formalitas** dan sisi komersial AUTOME_2 bisa hidup tanpa satu baris kode pun.

Bilang saja kalau mau saya jalankan — masih read-only, tidak menyentuh apa pun.

---

*Read-only. Tidak ada perubahan kode, database, migration, scraping, commit, push, maupun pipeline/layer baru. Seluruh temuan baru di dokumen ini (source rate card, procedure yang tidak dipanggil, kemampuan `pipeline.py --order stale`) diverifikasi langsung ke database dan ke kode existing sebelum direkomendasikan.*
