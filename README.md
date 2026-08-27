# Instagram Scraping Pipeline

Ambil username Instagram dari `public.kol_directory`, scrape profilnya lewat Apify
Actor `apify/instagram-profile-scraper`, simpan hasilnya ke file, lalu tulis ke
dua tujuan di database `kol`:

| Tujuan | Sifat | Isi |
| --- | --- | --- |
| `l0_raw.ig_profile_apify` | append-only | Payload mentah Apify (`raw_payload jsonb`) + kolom profil dasar, apa adanya. |
| `l0_harmonization.instagram_profile` | upsert per `(social_account_id, date)` | Versi bersih: `''` → NULL, whitespace & karakter tak kasat mata dirapikan, `website` divalidasi, tertaut ke `social_account`. |
| `public.kol_directory` | update in-place | Ringkasan profil terkini per KOL. |

Alur lengkapnya: `pipeline.py` (scrape) → `ingest.py` (muat file lama, opsional) →
`harmonize.py` (cleaning).

## TikTok

Pipeline terpisah dengan alur yang sama, memakai actor `clockworks/tiktok-scraper`.

```powershell
python tiktok_pipeline.py --limit 100 --dry-run                  # lihat kandidat + estimasi biaya
python tiktok_pipeline.py --limit 100 --skip-existing --yes      # scrape + simpan
```

Hasilnya masuk ke `l0_raw.tt_profile_apify`, dengan `social_account_id` diambil
dari `public.social_account.id` (bukan `kol_directory.id` — keduanya sama sekali
berbeda dan FK-nya menunjuk `social_account`).

### Tiga perbedaan penting dari Instagram

**1. Actor-nya berorientasi video.** `clockworks/tiktok-scraper` mengembalikan
video, dan data profil menempel di `authorMeta` setiap video. Karena tiap video
dihitung sebagai satu hasil berbayar, `resultsPerPage` diset **1** — cukup untuk
mendapat data profil lengkap dengan biaya minimum.

**2. Wajib residential proxy.** Tanpa `proxyCountryCode`, TikTok memblokir hampir
semua request; run tetap berstatus `SUCCEEDED` tapi menghasilkan **0 profil**.
Default-nya `ID` (bisa diubah lewat `TIKTOK_PROXY_COUNTRY`).

**3. Lebih mahal.** ~**$0.005/profil** (hasil $0.0037 + proxy $0.0013) dibanding
$0.0026 untuk Instagram. Seluruh 4.085 username TikTok ≈ **$20**.

### Penanganan error khusus TikTok

| Kondisi | Perlakuan |
| --- | --- |
| Run `SUCCEEDED` tapi 0 item | Dianggap gagal dan di-retry — untuk actor ini artinya diblokir, bukan "tidak ada hasil" |
| Run `SUCCEEDED` tapi sebagian profil tidak kembali | Yang belum kembali di-retry; yang sudah didapat tidak dibayar ulang |
| Plafon biaya di bawah $0.50 | Dinaikkan otomatis — actor menolak nilai di bawah itu |

#### Kalau retry berulang tetap 0 item: ganti negara proxy

Diamati 2026-08-24. Enam akun (`iben_ma`, `ibnuwardani`, `jharnabhagwani`,
`pojoksatu.id`, `saalhaerid`, `sptrakori_`) gagal berulang dengan pola identik —
run `SUCCEEDED`, 0 item, "kemungkinan diblokir platform" — dan tetap ditagih
$0.003 per percobaan.

| Percobaan | `TIKTOK_PROXY_COUNTRY` | Batch | Hasil |
|---|---|---|---|
| Run awal | `ID` (default) | 4 | 3 dari 10 |
| Retry | `ID` | 4 | 1 dari 7 |
| Retry | `ID` | 1 | **0 dari 6** |
| Rotasi | **`US`** | 2 | **5 dari 5** |

Mengecilkan batch **tidak** menolong — justru membuktikan blokirnya per-IP, bukan
per-batch. Yang menyelesaikannya adalah mengganti pool IP:

```powershell
$env:TIKTOK_PROXY_COUNTRY = "US"
python tiktok_pipeline.py --usernames akun1 akun2 --no-skip-existing --yes
```

Default `ID` di `config.py` sengaja tidak diubah — untuk sebagian besar akun ia
bekerja. Perlakukan `US` (atau `SG`/`MY`/`GB`) sebagai jalan keluar saat `ID`
buntu, dan hentikan pengulangan dengan negara yang sama setelah dua kali nol
hasil: biayanya tetap jalan sementara peluangnya tidak membaik.

Kolom teks (`display_name`, `bio_description`) sudah dibersihkan memakai aturan
`clean.py` yang sama dengan Instagram sebelum disimpan, sementara `raw_payload`
tetap menyimpan item aslinya utuh.

### Pengaman biaya untuk run besar

| Opsi | Gunanya |
| --- | --- |
| `--skip-existing` | Buang username yang sudah punya baris di `l0_raw.tt_profile_apify`. Tanpa ini, `--limit 100` yang diulang membayar lagi profil yang sudah ada. |
| `--max-total-cost-usd N` | Plafon biaya **seluruh run**; sisa batch dibatalkan begitu terlampaui. `--max-cost-usd` hanya membatasi satu run actor. |
| `--usernames-file FILE` / `--usernames` | Scrape daftar username tertentu saja, tanpa menyentuh `kol_directory`. |
| `--batch-size` kecil | Batch 25 membatasi kerugian kalau satu run actor terpotong. |

`--only-unscraped` membaca `kol_directory.scrape_status`, dan jalur TikTok tidak
pernah mengisi kolom itu (semua 4.087 baris `NULL`), jadi untuk TikTok flag itu
**tidak menyaring apa pun** — pakai `--skip-existing`.

Jumlah username yang sudah ada di raw table selalu dilaporkan sebelum konfirmasi
biaya, baik `--skip-existing` dipakai maupun tidak.

### Melanjutkan run yang terputus

Hasil tiap batch langsung ditulis ke JSONL **dan** langsung di-commit ke DB
dengan koneksi yang diperiksa ulang (dan dibuka ulang kalau sudah mati). Jadi
run yang mati di tengah tidak menghanguskan batch sebelumnya. Untuk melanjutkan,
jalankan lagi perintah yang sama dengan `--skip-existing`: yang sudah masuk tidak
dibayar dua kali.

Kalau penulisan DB tetap gagal, hasilnya aman di JSONL dan bisa dimasukkan
belakangan tanpa scraping ulang:

```powershell
python ingest_tiktok.py output/tiktok_profiles_<stamp>.jsonl --dry-run  # insert lalu rollback
python ingest_tiktok.py output/tiktok_profiles_<stamp>.jsonl --yes      # tulis beneran
```

`ingest_tiktok.py` memakai satu transaksi untuk seluruh file (gagal = rollback
penuh), dan menolak file yang sudah pernah masuk berdasarkan
`(scraped_at, source_actor)` — `scraped_at` diambil dari stamp nama file, bukan
waktu ingest.

### Mengulang username yang belum berhasil

Username yang tidak mengembalikan hasil tercatat di `missing` pada
`output/run_metadata_tiktok_<stamp>.json`. Kumpulkan ke satu file teks (satu
username per baris, `#` = komentar), lalu:

```powershell
python tiktok_pipeline.py --usernames-file output/tiktok_belum_berhasil.txt --dry-run
python tiktok_pipeline.py --usernames-file output/tiktok_belum_berhasil.txt --skip-existing --yes
```

## Tes

Semua tes berjalan tanpa Apify dan tanpa Postgres, jadi aman dijalankan kapan
saja dan tidak memakai kredit:

```powershell
python -m unittest discover -s tests -t .
```

Yang ditutup: parsing/cleaning item TikTok, logika retry & penyelamatan biaya di
`apify_runner` (dengan client palsu), pemulihan koneksi DB per batch, dan
regresi terhadap file hasil run 100 profil yang sudah dibayar.

## Setup

```powershell
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # lalu isi kredensial
```

Variabel yang dipakai ada di `.env.example`. `.env` berisi kredensial asli dan
sudah masuk `.gitignore`.

## Cara pakai

```powershell
# 1. Lihat kandidat tanpa memanggil Apify (gratis)
python pipeline.py --limit 1000 --dry-run

# 2. Coba dulu dengan sedikit profil, hasil hanya ke folder output/
python pipeline.py --limit 20

# 3. Jalan penuh 1000 username (otomatis menulis ke kol_directory)
python pipeline.py --limit 1000 --batch-size 100 --yes

# 4. Kalau ingin scrape saja tanpa menyentuh DB
python pipeline.py --limit 1000 --no-update-db --yes
```

### Memasukkan file lama ke DB (`ingest.py`)

Kalau pipeline pernah dijalankan dengan `--no-update-db`, atau ada file hasil
scrape lama yang belum masuk DB, pakai `ingest.py`. Ini **tidak memanggil Apify**,
jadi tidak ada biaya tambahan.

```powershell
python ingest.py --latest --dry-run                       # lihat rencananya
python ingest.py --latest --yes                           # tulis ke DB
python ingest.py output/instagram_profiles_XXX.jsonl --yes # file tertentu
```

Operasinya idempoten: menjalankan ulang file yang sama hanya menyegarkan nilai
dan `last_refreshed_at`, tidak menggandakan baris.

### Cleaning ke layer harmonisasi (`harmonize.py`)

Membaca `l0_raw.ig_profile_apify`, membersihkan teks, menautkan ke
`public.social_account` lewat username, lalu upsert ke
`l0_harmonization.instagram_profile` — satu snapshot per akun per tanggal.

```powershell
python harmonize.py --dry-run                    # lihat rencana + contoh hasil
python harmonize.py --yes                        # proses semua baris raw
python harmonize.py --scrape-run-id <uuid> --yes # satu run saja
```

Aturan pembersihannya ada di `clean.py`:

| Aturan | Contoh |
| --- | --- |
| `''` → NULL | `biography = ''` menjadi `NULL` |
| Buang zero-width & NBSP | `​` , ` ` |
| Rapikan whitespace | spasi ganda, spasi di ujung baris |
| Batasi baris kosong | 5 newline berturut-turut → 2 |
| `name` dijadikan satu baris | `"Nama\nDua"` → `"Nama Dua"` |
| `website` wajib punya skema | `linktr.ee/foo` → `https://linktr.ee/foo` |
| Kupas tanda baca di ujung URL | `<https://x.com>,` → `https://x.com` |
| Buang URL yang tidak masuk akal | `not a url` → `NULL` |

Kolom insight (`reach`, `profile_views`, `total_interactions`, dst) hanya tersedia
lewat Instagram Business API, tidak dari Apify. Kolom-kolom itu dibiarkan NULL dan
`has_insights` diisi `false` supaya konsumen data tahu bedanya.

Idempoten lewat unique index `(social_account_id, date)`: run kedua di hari yang
sama memperbarui baris, bukan menambah.

### Opsi penting

| Opsi | Default | Keterangan |
| --- | --- | --- |
| `--limit` | 1000 | Jumlah username, dibatasi maksimal 1000. |
| `--batch-size` | 100 | Username per run actor. Batch yang gagal tidak menjatuhkan batch lain. |
| `--order` | `followers` | `followers`, `stale`, `username`, atau `random`. |
| `--only-unscraped` | off | Hanya baris yang `scrape_status`-nya belum `success`. |
| `--write-raw` / `--no-write-raw` | aktif | Tulis payload mentah ke `l0_raw.ig_profile_apify`. |
| `--update-db` / `--no-update-db` | aktif | Tulis balik ke `kol_directory`. |
| `--include-failed` | off | Ikut memasukkan item `not_found`/`Restricted profile` ke raw layer. |
| `--dry-run` | off | Berhenti setelah ambil daftar username. |
| `--max-cost-usd` | 1.5x estimasi batch | Plafon biaya per run actor; `0` berarti tanpa plafon. |
| `--yes` | off | Lewati konfirmasi biaya (wajib kalau dijalankan non-interaktif). |

## Layer data

README ini hanya mencakup **jalur scraping** (Apify → `l0_raw` →
`public.kol_directory`). Pipeline analitiknya berdiri di atas itu dan
diorkestrasi Dagster:

```
l0_raw ─► l0_harmonization ─► l1_silver ─┬─► feature      (per akun / per post)
                                         └─► l2_gold      (harian → bulanan)
```

| Layer | Schema | Kondisi per 2026-08-21 |
|---|---|---|
| L0 Raw | `l0_raw` | 20 tabel; `*_apify` terisi, `*_official` 0 baris |
| Harmonization | `l0_harmonization` | 14 tabel, 15 procedure |
| L1 Silver | `l1_silver` | 8 tabel, 9 function — `unified_post` 221, `unified_profile` 1.971 |
| Feature | `feature` | 9 tabel — 4 terisi (13, 10, 130, 91 baris) |
| L2 Gold | `l2_gold` | **8 tabel** — 2 terisi (`kol_metric_daily` 160, `kol_metric_monthly` 53), 6 kosong |

`l2_gold` **tidak** membaca `feature`; keduanya cabang paralel di atas L1.
`kol_metric_monthly` membaca `kol_metric_daily`, bukan L1.

Dokumentasi rinci:

| Topik | File |
|---|---|
| Kamus metrik seluruh layer, L0 → L2 | `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md` |
| L2 Gold (kolom, aturan, validasi) | idem, **§17** |
| Kolom metrik yang hidup di L1 | idem, **§14** |
| Backlog metrik feature/L2 | `migrations/FEATURE_METRICS_BACKLOG.md` |
| Orkestrasi Dagster (12 asset) | `orchestration/README.md` |

---

## Alur

1. `db.fetch_instagram_usernames` — join `kol_directory` ke `platforms` dan filter
   `platforms.key = 'instagram'` (bukan UUID hardcode), lalu `LIMIT`.
2. `db.dedupe_rows` — username duplikat cukup dikirim sekali karena Apify menagih
   per profil.
3. `apify_ig.InstagramProfileScraper` — satu run actor per batch, dengan retry
   (2x) dan plafon biaya per run.
4. `transform` — mapping item Apify ke kolom `kol_directory` + hitung engagement rate.
5. `pipeline.write_outputs` — tulis hasil ke `output/`.
6. `raw_store.insert_profiles` — append ke `l0_raw.ig_profile_apify`.
7. `db.update_profiles` — update `public.kol_directory`.

Username dinormalisasi lewat `transform.normalize_username` sebelum dikirim ke
Apify: query string, path, dan `@` dibuang. Sebagian data lama di `kol_directory`
tersimpan sebagai potongan URL (`imeyliem?hl=en`), yang kalau dikirim apa adanya
selalu balik `not_found` dan tetap kena biaya.

## Output

Setiap run menghasilkan tiga file di `output/` dengan timestamp UTC yang sama:

- `instagram_profiles_<stamp>.jsonl` — item mentah dari Apify, apa adanya.
- `instagram_profiles_<stamp>.csv` — ringkasan per profil (UTF-8 BOM, aman dibuka di Excel).
- `run_metadata_<stamp>.json` — run id, dataset id, status, biaya, dan error per batch.

## Kolom yang diupdate di `kol_directory`

`platform_user_id`, `username`, `username_normalized`, `followers_count`,
`engagement_rate`, `avatar_url`, `profile_url`, `bio`, `verified_status`
(`verified`/`unverified`), `scrape_status` (`success`/`failed`),
`last_refreshed_at`, `updated_at`.

Semua kolom kecuali `scrape_status` memakai `COALESCE`, jadi field yang tidak
dikembalikan Apify tidak akan menimpa data lama dengan `NULL`.

`engagement_rate` dihitung dari rata-rata `(likes + comments)` pada `latestPosts`
dibagi jumlah followers, dalam persen. Kolomnya `numeric` dengan 2 desimal, jadi
akun dengan engagement sangat kecil akan tersimpan sebagai `0.00`.

## Biaya

Actor ini ditagih per profil: **$0.0026/profil** di plan FREE (lebih murah di plan
berbayar). Jadi 1000 profil ≈ **$2.60**. Pipeline menampilkan estimasi dan minta
konfirmasi sebelum jalan, dan mencetak biaya aktual dari Apify di akhir run.

## Migrasi

```powershell
python apply_migration.py migrations/001_fix_ig_profile_apify_fk.sql --dry-run --yes
python apply_migration.py migrations/001_fix_ig_profile_apify_fk.sql --yes
```

`--dry-run` menjalankan seluruh isi file sungguhan lalu me-ROLLBACK, jadi blok
verifikasinya benar-benar diuji tanpa mengubah apa pun.

### 001 — FK ganda pada `social_account_id` (SUDAH DITERAPKAN)

Kolom `l0_raw.ig_profile_apify.social_account_id` sempat punya **dua** foreign key
ke tabel berbeda:

```
fk_ig_profile_apify_social_account     -> public.social_account(id)   (benar)
fk_ig_profile_apify_social_account_id  -> public.kol_directory(id)    (keliru)
```

Kedua tabel itu tidak berbagi satu id pun, jadi nilai non-NULL apa pun pasti
melanggar salah satunya — kolom tersebut efektif hanya bisa NULL. Migrasi 001
menghapus FK yang keliru lalu mengisi 928 baris berdasarkan username + platform
Instagram. Hasil: 928/928 tertaut, 0 kosong.

Yang keliru ditentukan dari nama kolomnya (`social_account_id`) dan dari tabel
sejenis yang FK-nya tunggal: `l0_harmonization.instagram_profile`
(`fk_instagram_profile_social_account`) dan `l1_silver.unified_profile`
(`fk_upr_social`), keduanya menunjuk `social_account(id)`.

### 002 — 26 tabel sisanya (SUDAH DITERAPKAN)

Pola FK ganda yang sama ternyata bukan cuma di `l0_raw`, tapi juga di `feature`:
**26 tabel** total (18 `l0_raw` + 8 `feature`). Semuanya masih 0 baris **saat
migrasi itu dijalankan**; sebagian `feature` sekarang sudah terisi — lihat
bagian "Layer data" di bawah.

Migrasi 002 tidak memakai daftar nama tabel. Ia mencocokkan tanda pengenal yang
presisi: FK ke `kol_directory`, kolomnya bernama `social_account_id`, dan kolom
yang sama juga punya FK ke `social_account`. Syarat terakhir memastikan tidak ada
kolom yang berakhir tanpa constraint, sekaligus membuatnya idempoten. Empat FK ke
`kol_directory` yang sah (`kol_id`, `kol_directory_id`) tidak tersentuh karena
nama kolomnya berbeda; jumlahnya dihitung sebelum dan sesudah lalu dituntut sama.

Karena semua tabelnya kosong, tidak ada backfill — hanya perubahan constraint.
Hasil: 26 constraint dihapus, 0 FK ganda tersisa di seluruh database, 8 FK sah ke
`kol_directory` utuh, dan tidak ada baris data yang berubah.

`raw_store.social_account_link_blocked()` mendeteksi kondisi ini saat runtime dan
mengisi NULL agar data tetap masuk, lalu menautkan otomatis begitu FK-nya dibereskan.

## Penanganan error

Scraping sudah dibayar begitu Apify mengembalikan profil, jadi penanganan error di
sini berfokus pada satu hal: **jangan sampai hasil yang sudah dibayar hilang.**

| Kondisi | Yang terjadi |
| --- | --- |
| Run berakhir bukan `SUCCEEDED` (timeout, kena plafon biaya, dibatalkan) | Isi dataset tetap diambil — profil yang sudah ditagih tidak dibuang |
| Retry setelah run gagal | Hanya mengirim ulang username yang belum ada hasilnya, jadi tidak dibayar dua kali |
| Token salah, kredit habis, actor tidak ada | Berhenti langsung (`FatalApifyError`), tanpa retry sia-sia; hasil batch sebelumnya tetap disimpan |
| Proses mati di tengah (Ctrl-C, crash) | JSONL ditulis bertahap per batch, jadi yang sudah selesai aman di disk |
| Penulisan ke database gagal | Tidak melempar traceback; mencetak perintah pemulihan `python ingest.py <file> --yes` |
| Host database tidak merespons | Gagal dalam 15 detik (`connect_timeout`), tidak menggantung |
| Baris JSONL rusak saat ingest | Baris itu dilewati dengan peringatan, sisanya tetap diproses |

Exit code `pipeline.py`: `0` sukses, `2` ada batch yang gagal, `3` scraping
terhenti atau penulisan DB gagal (hasil tetap ada di `output/`).

Karena file JSONL selalu tersimpan lebih dulu, **tidak ada kegagalan di sisi
database yang mengharuskan scrape ulang.** Pemulihannya selalu:

```powershell
python ingest.py output/instagram_profiles_<stamp>.jsonl --yes
```

## Catatan

- Akun yang sudah dihapus atau ganti nama dibalas Apify dengan `error: not_found`
  dan ditandai `scrape_status = 'failed'`, bukan dianggap sukses.
- `APIFY_INCLUDE_ABOUT_SECTION` hanya berfungsi untuk akun Apify berbayar.
- `l0_raw.ig_profile_apify` bersifat append-only. Ingest file yang sama dua kali
  akan menggandakan baris; `ingest.py` memperingatkan lebih dulu kalau mendeteksi
  `scraped_at` + `source_actor` yang sama sudah ada.
- Item error (`not_found`, `Restricted profile`) tidak dimasukkan ke raw layer
  secara default, tapi tetap ditandai `scrape_status = 'failed'` di `kol_directory`.
- `main.py` adalah script eksplorasi schema yang lama, tidak dipakai pipeline.
