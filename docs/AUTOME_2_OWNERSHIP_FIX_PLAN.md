# AUTOME_2 — Rencana Perbaikan Ownership & 10 Post Terbaru

**Read-only · 8 September 2026 · tidak ada scraping, migration, UPDATE, DELETE, maupun perubahan kode**

Requirement: **1 KOL → maksimal 10 postingan terbaru MILIK KOL tersebut.**

---

> ## ⚠ Koreksi laporan saya sebelumnya
>
> Di `AUTOME_2_POST_OWNERSHIP_AUDIT.md` saya menulis bahwa 43 baris salah atribusi membuat *"likes/comments milik `adidasfootball` ikut dihitung ke ER `leomessi`"*.
>
> **Itu salah.** Setelah diukur: **0 dari 43 baris masuk perhitungan ER.**
>
> Sebabnya `l1_silver.sp_build_unified_post()` (migration 024, baris 137–147) mendefinisikan `is_collaboration` persis sebagai *"pemilik asli post berbeda dari pemilik akun"* — kondisi yang identik dengan salah-atribusi. Jadi ke-43 baris itu **otomatis tertandai** dan dikecualikan oleh `feature_post`, `gold_post`, maupun `gold`.
>
> Diverifikasi: `SELECT count(*) FROM l2_gold.post_metric WHERE is_collaboration AND er_followers IS NOT NULL` → **0**.
>
> ER tidak pernah tercemar. Yang terdampak hanya `post_count` — rinciannya di §6.

---

# 1. Root Cause

Tiga akar masalah terpisah. Hanya #1 dan #2 yang perlu perubahan kode.

## RC-1 — `resultsLimit` membatasi jumlah hasil, bukan kepemilikan

`apify_posts.py:67–74` mengirim `{"directUrls": [...], "resultsType": "posts", "resultsLimit": 10}`. Actor `apify/instagram-scraper` memenuhi plafon itu dengan **post apa pun yang muncul di feed profil**, termasuk post milik akun yang di-tag/kolaborasi.

Terukur pada run terbaik (20 Agu), tiap URL mengembalikan tepat 10 item tetapi yang benar-benar milik profil hanya 1–10:

| `inputUrl` | Item | Milik sendiri |
|---|---:|---:|
| `lambe_turah` | 10 | **10** |
| `pevpearce` | 10 | 9 |
| `cristiano` / `iben_ma` / `leomessi` / `saalhaerid` | 10 | 8 |
| `anyageraldine` / `inul.d` | 10 | 7 |
| `fadiljaidi` / `isyanasarasvati` / `lunamaya` | 10 | 6 |
| `raffinagita1717` | 10 | 5 |
| **`irwansyah_15`** | 10 | **1** |

Rata-rata 6,8 dari plafon 10. **Tidak ada parameter actor yang bisa memperbaiki ini** — pembatasan kepemilikan harus dilakukan di sisi kita.

## RC-2 — Pipeline tidak pernah membandingkan owner dengan siapa pun

`post_raw_store._partition()` (baris 136–154) hanya membuang item error, item tanpa username, dan item tanpa `content_id`. `insert_ig_posts()` (baris 294–297) menulis **setiap** item yang lolos; yang owner-nya tidak ter-resolve masuk dengan `social_account_id = NULL` dan hanya dihitung sebagai `stats.unlinked`.

Akibat terukur di pilot: **36 dari 62 baris** adalah post milik brand/akun non-roster (`neorheumacyl`, `bodrex`, `priveeclinic.id`, `elleindonesia`, …).

## RC-3 — Tidak ada pembatasan "N terbaru per pemilik"

Tidak ada satu pun titik yang mengurutkan per pemilik lalu memotong. `resultsLimit` dipercaya sepenuhnya. Terbukti gagal dua arah:

- **Kurang**: pilot 8 Sep rata-rata 2,48 item/URL, hanya 1 milik sendiri di seluruh 25 URL.
- **Lebih**: 27 Agu satu akun TikTok (`nanakoot`) menghasilkan **200 baris** dari satu URL.

Ironisnya helper untuk ini **sudah ada** — `scheduler_engine.latest_posts()` (baris 217–224) — tetapi `post_pipeline.py` tidak memakainya.

---

# 2. Logic Ownership yang Direkomendasikan

Kuncinya: **jangan membandingkan owner dengan username yang diminta.** Bandingkan owner dengan **roster**.

Alasannya terbukti di data — sebagian owner yang berbeda memang KOL roster yang sah:

| `ownerUsername` | Punya `social_account`? | Ada di `kol_directory`? | Salah ditautkan ke |
|---|---|---|---|
| `tasyafarasya` | **Ya** | **Ya** | `fadiljaidi` |
| `raffinagita1717` | **Ya** | **Ya** | `irwansyah_15` |
| `adidasfootball`, `mls`, `herbalife`, `voguemagazine`, `bodrex`, … | Tidak | Tidak | — |

Kalau filter memakai "owner == yang diminta", post `tasyafarasya` dan `raffinagita1717` ikut terbuang padahal itu data KOL roster yang benar-benar berharga.

## Tiga kategori dan perlakuannya

| # | Kategori | Cara mendeteksi | Perlakuan | Status hari ini |
|---|---|---|---|---|
| **1** | Post milik target | `ownerUsername` = username yang diminta | Simpan, tautkan ke target | ✅ sudah benar |
| **2** | Post KOL roster lain | `ownerUsername` **ter-resolve** oleh `fetch_social_account_ids()` (ada di `public.social_account` platform tsb) | Simpan, tautkan ke **pemilik sebenarnya** — bukan ke target | ✅ sudah benar sejak commit pertama |
| **3** | Post non-roster | `ownerUsername` **tidak ter-resolve** → `account_ids.get(u)` = `None` | **Buang sebelum INSERT** | ❌ sekarang di-insert dengan `social_account_id = NULL` |

## Kenapa `account_ids` adalah penguji roster yang tepat

`fetch_social_account_ids()` (`db.py:154–191`) mencocokkan username ke `public.social_account` untuk platform tersebut. Itu **persis** tabel yang ditunjuk FK `l0_raw.*.social_account_id`. Jadi "tidak ter-resolve" ≡ "tidak akan pernah bisa ditautkan" ≡ "tidak ada gunanya disimpan".

Tidak perlu query roster baru — pemetaannya **sudah dihitung** di `insert_ig_posts` baris 290. Yang kurang hanya keputusan untuk membuang yang kosong.

## Kategori 2 tidak boleh diubah jadi "tautkan ke target"

Itu justru bug yang menghasilkan 43 baris salah atribusi di data 20 Agu. Kode hari ini sudah benar; jangan diregresikan.

---

# 3. Logic 10 Post Terbaru per KOL

## Urutan operasi yang benar

```
items dari actor
   ↓ 1. _partition()            buang error / tanpa username / tanpa content_id   [sudah ada]
   ↓ 2. _account_ids()          resolve ownerUsername -> social_account.id        [sudah ada]
   ↓ 3. BUANG yang tidak ter-resolve                                              [BARU — §2 kategori 3]
   ↓ 4. KELOMPOKKAN per social_account_id (pemilik sebenarnya)                     [BARU]
   ↓ 5. URUTKAN posted_at menurun, ambil N teratas per kelompok                    [BARU — pakai latest_posts()]
   ↓ 6. INSERT
```

**Langkah 4 mengelompokkan per pemilik sebenarnya, bukan per URL yang diminta.** Kalau dikelompokkan per URL, satu KOL yang muncul dari dua URL berbeda bisa dapat 20 post.

## Kunci pengurutan sudah terdefinisi

`scheduler_engine.PLATFORM_TABLES` (baris 112–125):

| Platform | `posted_at_key` |
|---|---|
| instagram | `timestamp` |
| tiktok | `createTimeISO` |

## Helper sudah ada — pakai ulang, jangan tulis baru

`scheduler_engine.latest_posts()` (baris 217–224):

```python
def latest_posts(items, posted_at_key: str, limit: int = POSTS_PER_TARGET) -> list[dict]:
    """`limit` post TERBARU dari satu akun, diurutkan waktu tayang menurun.

    Tetap dipakai walau actor sudah dibatasi `resultsLimit`: batas actor tidak
    menjamin urutan. Post tanpa timestamp diberi kunci kosong supaya selalu
    kalah dari post yang punya.
    """
```

Docstring-nya sendiri sudah menyatakan alasan yang persis kita butuhkan. Masalahnya cuma: `post_pipeline.py` tidak memanggilnya.

## Apakah filtering + sorting perlu dilakukan setelah payload diterima?

**Ya, wajib.** `resultsLimit` terbukti gagal dua arah (RC-3), dan kepemilikan tidak bisa dibatasi lewat parameter actor mana pun (RC-1). Satu-satunya titik yang punya cukup informasi adalah **setelah payload diterima dan owner sudah di-resolve ke `social_account_id`**.

---

# 4. File yang Perlu Diubah

**Dua file. Tidak ada migration, tidak ada tabel baru, tidak ada pipeline baru.**

| # | File | Peran | Perkiraan |
|---|---|---|---|
| 1 | `post_raw_store.py` | Tempat filter + cap; sudah memegang `conn`, `account_ids`, dan seluruh item | ~20 baris |
| 2 | `post_pipeline.py` | Meneruskan `--results` sebagai batas per akun | ~2 baris |

## Kenapa bukan di `post_pipeline.py` saja

Filter kepemilikan butuh hasil `fetch_social_account_ids()`, yang baru dihitung di dalam `insert_*`. Menariknya ke `post_pipeline` berarti memanggil query itu dua kali atau menduplikasi logikanya.

## Catatan impor — ada risiko circular import

`scheduler_engine.py:80` sudah mengimpor dari `post_raw_store`. Jadi `post_raw_store` **tidak boleh** mengimpor `scheduler_engine` — akan circular.

Solusi minimum: **pindahkan** `_sort_key()` + `latest_posts()` (8 baris) dari `scheduler_engine.py` ke `post_raw_store.py`, lalu `scheduler_engine.py` mengimpornya dari sana. Arah impor tetap satu arah, tidak ada duplikasi aturan, dan perilaku scheduler tidak berubah.

---

# 5. Perubahan Minimum per File

## 5.1 `post_raw_store.py`

| Bagian | Perubahan | Baris |
|---|---|---|
| Pindahan | Terima `_sort_key()` + `latest_posts()` dari `scheduler_engine.py` | ~8 (pindah, bukan baru) |
| `PostInsertStats` | Tambah dua penghitung: `skipped_non_roster`, `skipped_over_limit` | 2 |
| Fungsi baru `_filter_owned()` | Terima `usable` + `account_ids` + `posted_at_key` + `limit` → buang yang tidak ter-resolve, kelompokkan per `social_account_id`, ambil N terbaru | ~12 |
| `insert_ig_posts()` | Tambah parameter `per_account_limit: int \| None = None`; setelah baris 290 panggil `_filter_owned(..., "timestamp", per_account_limit)` | 2 |
| `insert_tt_videos()` | Sama, dengan `"createTimeISO"` | 2 |

**Total ~18 baris baru + 8 baris pindahan.**

Aturan yang harus dipegang perubahan ini:

- `per_account_limit=None` → perilaku lama persis (tanpa cap), supaya pemanggil lain tidak berubah diam-diam.
- Yang dibuang **dihitung** di `stats`, tidak dibuang diam-diam — konsisten dengan `skipped_error` / `skipped_no_username` yang sudah ada.
- Jangan sentuh `_partition()`: ia tidak tahu soal roster, dan tugasnya memang lain.

## 5.2 `post_pipeline.py`

| Bagian | Perubahan | Baris |
|---|---|---|
| `_insert()` (baris 100) | Teruskan `per_account_limit` | 1 |
| Pemanggilan `_insert` (baris 330) | Kirim `args.results` | 1 |

## 5.3 `scheduler_engine.py`

| Bagian | Perubahan | Baris |
|---|---|---|
| Impor | `latest_posts` diambil dari `post_raw_store`, bukan didefinisikan lokal | 1 |

**Perubahan perilaku scheduler yang perlu diketahui:** sekarang scheduler menulis item ber-owner-lain dengan `social_account_id = NULL` (karena `peta` hanya berisi satu entri). Setelah perubahan, item itu **dibuang**. Ini perbaikan dan konsisten dengan maksud aslinya, tapi harus disebut supaya tidak mengejutkan.

## 5.4 Yang TIDAK boleh disentuh

| Komponen | Alasan |
|---|---|
| `apify_posts.build_input()` | Parameter actor sudah benar; masalahnya bukan di sini |
| Rumus ER di L1 / Feature / L2 | Di luar scope, dan terbukti sudah benar |
| `is_collaboration` di migration 024 | Justru inilah pengaman yang menyelamatkan ER dari 43 baris itu |
| `_partition()` | Tugasnya berbeda |
| Skema tabel mana pun | Tidak ada kolom baru |

---

# 6. Dampak terhadap 43 Baris Lama

## 6.1 Sebaran

| Metrik | Nilai |
|---|---|
| Baris di `l1_silver.unified_post` | **43** |
| Owner unik | 27 |
| Akun yang ditautkan (salah) | 14 |
| Rentang tanggal post | 2023-08-26 → 2026-08-27 |
| Asal | 41 dari scrape 20 Agu, 2 dari 27 Agu |

Semua berasal dari kode **sebelum commit pertama repo** (`494f977`, 27 Agu), jadi versinya tidak ada di git history. Kode hari ini tidak menghasilkan pola ini — pilot 8 Sep: **0 baris salah atribusi**.

## 6.2 Apakah memengaruhi ER — **TIDAK**

| Pemeriksaan | Hasil |
|---|---:|
| 43 baris ada di `post_metric` | 43 |
| Ditandai `is_collaboration` | **43 (100%)** |
| **Ikut perhitungan ER** | **0** |
| Akun-hari `kol_metric_daily` terdampak | **0** |
| Baris kolaborasi mana pun yang lolos ke ER (seluruh tabel) | **0** |

`is_collaboration` di migration 024 didefinisikan sebagai *"pemilik asli post berbeda dari pemilik akun"* — kondisi yang identik dengan salah-atribusi. Jadi setiap baris salah atribusi **pasti** tertandai, dan `feature_post` / `gold_post` / `gold` semuanya mengecualikannya.

**Pengaman ini bekerja tanpa direncanakan untuk kasus ini.**

## 6.3 Yang benar-benar terdampak: `post_count`

`gold.py` menghitung `count(*) AS post_count` tanpa filter (hanya `posts_in_sample` yang difilter). Jadi post kolaborasi **menggelembungkan** `post_count`:

| Akun | `post_count` | `posts_in_sample` | Selisih |
|---|---:|---:|---:|
| `irwansyah_15` | 10 | **0** | 10 |
| `isyanasarasvati` | 10 | **0** | 10 |
| `raffinagita1717` | 11 | 6 | 5 |
| `fadiljaidi` | 10 | 6 | 4 |
| `lunamaya` | 10 | 6 | 4 |
| `inul.d` | 11 | 8 | 3 |
| `anyageraldine` | 10 | 7 | 3 |

Untuk `irwansyah_15` dan `isyanasarasvati`, **seluruh post yang tercatat tidak ada satu pun yang layak sampel.**

Konsekuensinya baru terasa kalau **posting frequency** dihitung dari `post_count` — metrik itu belum ada (masih `NEED CALCULATION` di `AUTOME_2_DEVELOPMENT_AUDIT.md`). Jadi belum ada konsumen yang salah baca hari ini.

## 6.4 Rekomendasi remediation

### **Tidak perlu remediation data sekarang.**

| Pertimbangan | Alasan |
|---|---|
| ER tidak tercemar | 0 dari 43 masuk hitungan — terukur |
| Konsumen `post_count` belum ada | Posting frequency belum diimplementasi |
| Barisnya bukan sampah | Post itu **nyata**, hanya ditautkan ke akun yang salah |
| L0 append-only | Menghapus di L1 tanpa menyentuh L0 akan dipulihkan lagi pada materialisasi berikutnya |

### Cara paling aman kalau nanti tetap dibersihkan

Urutannya penting, dan **tidak satu pun boleh dijalankan tanpa approval terpisah**:

1. **Perbaiki di L0 lebih dulu, bukan L1.** L1 adalah turunan — memperbaiki L1 saja akan tertimpa saat `sp_build_unified_post()` jalan lagi.
2. **Pertimbangkan menautkan ulang, bukan menghapus.** Dua owner (`tasyafarasya`, `raffinagita1717`) punya `social_account` sendiri — post mereka bisa dipindahkan ke pemilik yang benar dan menjadi data yang sah. 25 owner sisanya non-roster dan memang layak dibuang.
3. **Jalankan sebagai skrip terpisah yang bisa di-`--dry-run`**, bukan migration — ini perbaikan data, bukan perubahan skema.
4. **Ukur ulang ER sebelum dan sesudah**, dan pastikan selisihnya nol. Kalau tidak nol, asumsi di §6.2 salah dan pekerjaannya harus dibatalkan.

### Prioritas: **rendah**

Tidak memblokir apa pun. Yang memblokir adalah perbaikan kode di §5 — supaya baris seperti ini tidak bertambah lagi.

---

# 7. Test yang Harus Ditambahkan

Mengikuti gaya repo: tanpa DB kalau bisa, `needs_db` + skip otomatis kalau perlu, semuanya read-only. Kandidat berkas: `tests/test_post_pipeline.py` (sudah ada) dan `tests/test_post_raw_store.py` (baru).

## 7.1 Ownership — tanpa DB, pakai `account_ids` yang disuntik

| # | Test | Harapan |
|---|---|---|
| T1 | Owner = target, ada di `account_ids` | Disimpan, `social_account_id` = id target |
| T2 | Owner = KOL roster lain, ada di `account_ids` | **Disimpan**, tertaut ke **pemilik sebenarnya**, bukan target |
| T3 | Owner non-roster, tidak ada di `account_ids` | **Dibuang**, `stats.skipped_non_roster` bertambah |
| T4 | Tidak ada baris ber-`social_account_id` NULL yang di-insert | `payload` bebas NULL |
| T5 | `account_ids` kosong (linking blocked) | Tidak ada yang di-insert; tidak diam-diam menulis NULL |

T2 adalah test terpenting — ia memagari agar perbaikan ini tidak berubah jadi "buang semua yang bukan target".

## 7.2 Batas 10 terbaru — tanpa DB

| # | Test | Harapan |
|---|---|---|
| T6 | Satu owner dengan 25 post | Tersisa 10, dan **10 yang `timestamp`-nya paling baru** |
| T7 | Post tanpa `timestamp` | Kalah dari yang punya; tidak melempar exception |
| T8 | Satu owner muncul dari dua `inputUrl` berbeda | Tetap maksimal 10 total, bukan 10 per URL |
| T9 | `per_account_limit=None` | Perilaku lama persis — tidak ada yang dipotong |
| T10 | TikTok memakai `createTimeISO`, Instagram memakai `timestamp` | Kunci urut benar per platform |

## 7.3 Regresi kontrak

| # | Test | Harapan |
|---|---|---|
| T11 | `is_collaboration` di migration 024 tetap berbunyi "pemilik asli post berbeda dari pemilik akun" | Pengaman ER tidak boleh hilang diam-diam |
| T12 | `latest_posts` yang diimpor `scheduler_engine` identik dengan yang di `post_raw_store` | Membuktikan tidak ada dua salinan aturan |
| T13 | `_partition()` tidak berubah perilakunya | Tidak ikut terseret perubahan |

## 7.4 Dengan DB (`needs_db`, read-only)

| # | Test | Harapan |
|---|---|---|
| T14 | Tidak ada baris `post_metric` dengan `is_collaboration AND er_followers IS NOT NULL` | 0 — memagari temuan §6.2 |
| T15 | Setelah fix, tidak ada baris L0 baru dengan `social_account_id IS NULL` | Diukur per `scrape_run_id` |

---

# 8. Cara Validasi dengan Pilot Kecil

Setelah perubahan disetujui dan diterapkan. **Belum boleh dijalankan sekarang.**

## Langkah

| # | Langkah | Verifikasi |
|---|---|---|
| 1 | Jalankan unit test §7.1–7.3 | Semua hijau, tanpa DB |
| 2 | `--dry-run` untuk 5 akun | Daftar akun benar, actor benar, tidak ada tulisan |
| 3 | **Replay tanpa memanggil Apify**: `post_pipeline.py --from-file <jsonl 8 Sep> --no-write` | Inilah validasi termurah — file mentah pilot **sudah tersimpan** di `output/`. Pastikan 36 item non-roster ditandai `skipped_non_roster` dan 26 sisanya lolos. **Nol biaya Apify** |
| 4 | Replay dengan tulisan, 5 akun saja | Bandingkan L0 sebelum/sesudah: tidak ada baris ber-`social_account_id` NULL |
| 5 | Pilot nyata 5 akun (bukan 50) | Ukur item/URL, milik-sendiri, dan yang tersimpan |
| 6 | Ukur ulang funnel L0 → L1 → Feature → L2 | Bandingkan dengan baseline |

**Langkah 3 adalah kuncinya.** File `.jsonl` hasil pilot 8 Sep sudah ada di `output/` (ditulis `post_pipeline.py:310`), jadi seluruh logika ownership + cap bisa divalidasi terhadap payload nyata **tanpa satu pun panggilan Apify**.

## Kriteria lulus

| Kriteria | Target |
|---|---|
| Baris L0 baru dengan `social_account_id` NULL | **0** |
| Post per pemilik | **≤ 10** |
| Post yang tersimpan dan milik target | naik dari 40% |
| Post KOL roster lain | tetap tersimpan, tertaut ke pemilik sebenarnya |
| Baris salah atribusi baru | **0** |
| ER akun yang sudah ada | **tidak berubah** |

## Baseline hari ini

| Metrik | Nilai |
|---|---:|
| KOL ber-ER L2 | 38 |
| `post_metric` | 503 |
| `unified_post` | 503 |
| Baris L0 IG tanpa link | 38 |
| Baris L1 salah atribusi | 43 |
| Post kolaborasi yang masuk ER | **0** |

---

# Yang masih perlu keputusan lo

| # | Pertanyaan | Kenapa perlu diputuskan |
|---|---|---|
| 1 | Post milik **KOL roster lain** — simpan (tertaut ke pemilik sebenarnya) atau buang? | Rekomendasi saya: **simpan**. Itu data sah dan gratis. Tapi ini keputusan produk |
| 2 | Nilai `--results` | Milik-sendiri rata-rata 68% pada run sehat. Untuk mengejar 10 milik sendiri butuh ±15, dan itu menaikkan biaya |
| 3 | 43 baris lama | Rekomendasi saya: **biarkan**. ER tidak terdampak, prioritas rendah |
| 4 | Efek "10 → 2,48 item per URL" | Di luar kendali kode kita. Tunggu dan ukur ulang, atau kompensasi lewat `--results`? |

---

*Read-only. Tidak ada scraping, retry Apify, migration, DELETE, UPDATE, scaling, perubahan rumus ER, maupun pipeline baru. Perubahan kode di sesi ini tetap hanya satu baris provenance actor yang sudah disetujui sebelumnya (`git diff --stat` = 1 file, 1 insertion, 3 deletions). Rencana di §5 **belum** diimplementasikan.*
