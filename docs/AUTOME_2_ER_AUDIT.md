# AUTOME_2 — Engagement Rate Audit

**Read-only · 8 September 2026 06:19 · sesi `set_session(readonly=True)`**
Tidak ada perubahan kode / migration / commit / push. Tidak ada perbaikan apa pun.

Keputusan requirement yang divalidasi: **L2 Gold jadi source of truth ER untuk AUTOME_2.**

Bukti: `scratchpad/er_audit.py` (18 query) + `scratchpad/er2.py` (7 query). Seluruh angka di bawah terukur langsung dari database `kol` @ `10.100.14.216`.

---

# A. Current ER Architecture

Yang ada sekarang **bukan satu rantai, tapi dua rantai paralel** yang tidak pernah bertemu.

## Rantai 1 — Roster (melewati medallion sama sekali)

```
Apify actor (profil) → item.latestPosts[]
   ↓  transform.py::compute_engagement_rate()      ← Python, di luar DB
      avg(likes + comments) / followers_count × 100
   ↓  db.py::update_profiles()  UPDATE kol_directory
   ↓
public.kol_directory.engagement_rate      numeric(5,2) · PERSEN · 1.756 / 7.720
   ↓
kolDirectory.ts BASE:186  kd.engagement_rate::float AS er_pct
   ↓
GET /discover/kol-directory        → row.erPct
GET /discover/kol-directory/[kolId] → creator.erPct, platforms[].erPct, similar[].erPct
   ↓
UI AUTOME_2  (kolom "Engagement", filter "Min. engagement", sort "Engagement Rate")
```

**Rantai ini tidak menyentuh L0 / Harmonization / L1 / Feature / L2 sama sekali.**

## Rantai 2 — Medallion (yang diminta jadi source of truth)

```
l0_raw.ig_media_snapshots_apify (188) · tt_video_apify (291)
   ↓
l0_harmonization.instagram_post (186) · tiktok_post (291)
      engagement_rate: kolom ADA, terisi 0 / 477      ← tidak pernah diisi di layer ini
   ↓
l1_silver.unified_post.engagement_rate     numeric · PERSEN · 157 / 477
      sp_build_unified_post() (migration 024):
        (likes + comments + shares) / followers_PADA_TANGGAL_POST × 100
   ↓
FEATURE
   feature.ig_post_analysis.engagement_rate        numeric(9,4) · PERSEN ·  45 / 186
   feature.tt_post_analysis.engagement_rate        numeric(9,4) · PERSEN ·  95 / 291
        = pass-through dari unified_post, LEAST(round(x,4), 99999.9999), hanya post lolos sampel
   feature.ig_engagement_analysis.engagement_rate  numeric(5,2) · PERSEN ·  12 / 19  (per AKUN)
   feature.tt_engagement_analysis.engagement_rate  numeric(5,2) · PERSEN ·  10 / 11  (per AKUN)
        = SUM(like+comment+share) / SUM(followers_pada_tanggal_post) × 100
   ↓
L2 GOLD  ← dihitung ULANG dari L1, BUKAN diambil dari Feature
   l2_gold.post_metric.er_followers            numeric(12,8) · FRAKSI · 140 / 477
   l2_gold.kol_metric_daily.er_followers_daily numeric(12,8) · FRAKSI ·  73 / 280
   l2_gold.kol_metric_monthly.er_followers_monthly              FRAKSI ·  22 /  68
   l2_gold.content_format_daily.er_followers_daily              FRAKSI ·  82 / 300
   ↓
GET /discover/kol-directory/[kolId] → gold.posts[].erFollowers
                                       gold.daily[].erFollowers
                                       gold.monthly[].erFollowers
                                       gold.formats[].erFollowers
   ↓
UI — hanya di halaman detail. TIDAK dipakai di list, filter, maupun sort.
```

## Temuan arsitektur

| # | Temuan |
|---|---|
| **A1** | **Feature bukan hulu L2.** Flow yang diminta `Feature (calculation) → L2` **tidak** seperti itu di kode: `gold.py` dan `gold_post.py` menghitung engagement sendiri dari kolom mentah `unified_post`. Yang diambil L2 dari Feature hanya `rank_in_account` dan `top_hashtags`. Keduanya kebetulan **sepakat angkanya** (dibuktikan di §H), tapi mereka dua perhitungan paralel, bukan satu rantai |
| **A2** | **Endpoint detail mengembalikan DUA ER berbeda satuan dalam satu response** — `creator.erPct` (persen, dari roster) dan `gold.*.erFollowers` (fraksi, dari L2). Tidak ada field yang membedakan asal-usulnya |
| **A3** | `l0_harmonization.*_post.engagement_rate` punya kolom tapi **0/477 terisi**. ER pertama kali muncul di L1, bukan di harmonization |
| **A4** | Ada **22 kolom ber-nama ER** di seluruh database. Yang relevan untuk AUTOME_2 hanya 9; sisanya milik rate card (semuanya 0 baris) dan campaign (0 baris) |

---

# B. Source of Truth — Apakah L2 layak?

## **YES pada formula. NO pada coverage hari ini.**

### Kenapa YES pada formula

| Kriteria | L2 | Roster |
|---|---|---|
| Penyebut | followers **pada tanggal post** (carry-forward `date <= post_date`) | followers **saat scrape** |
| Penyebut aditif | ✅ `SUM(engagement) / SUM(followers_denom)` — rasio tidak dirata-rata | ⚠ konstan, jadi setara — tapi hanya karena 1 snapshot |
| Aturan sampel | ✅ eksplisit: buang `likes_hidden` + `is_collaboration` | ❌ tidak ada |
| Definisi engagement | ✅ `like + comment + share`, save sengaja tidak ikut, terdokumentasi | ❌ `like + comment` saja, share tidak masuk |
| Satuan | ✅ konsisten fraksi 0..1 di 4 tabel | persen |
| Presisi | `numeric(12,8)` | `numeric(5,2)` |
| Nilai mustahil | **0 di atas 100% · 0 negatif** | **7 di atas 100% · maks 223,41%** |
| NULL vs 0 | ✅ NULL kalau tidak diketahui, tidak pernah dinolkan | tidak dibedakan |

Secara rumus L2 jelas yang paling benar, dan satu-satunya yang tidak menghasilkan nilai mustahil.

### Kenapa NO pada coverage hari ini

| Fakta terukur | Angka |
|---|---|
| KOL aktif | **7.720** |
| KOL yang punya baris di `kol_metric_daily` | **30** |
| **KOL yang benar-benar dapat ER dari L2** | **22 (0,28%)** |
| KOL yang punya ER di roster | 1.756 (22,7%) |

Dan 22 itu pun bertumpu pada sampel yang sangat tipis:

| Jumlah post yang menyumbang ER | Akun |
|---:|---:|
| 0 | 8 |
| 1 | 5 |
| 2 | 3 |
| 3 | 1 |
| 5 | 4 |
| 6 | 2 |
| 7 | 2 |
| 10 | 4 |
| 40 | 1 |

**8 dari 30 akun ER-nya bertumpu pada ≤2 post.**

### Temuan paling penting: L2 ER bukan "ER kreator", tapi "ER 15 hari terakhir"

| | Jumlah | Rentang tanggal |
|---|---:|---|
| Seluruh post di `post_metric` | 477 | 2021-02-18 → 2026-08-28 |
| **Post yang menyumbang ER** | **140** | **2026-08-14 → 2026-08-28** |

Snapshot profil pertama adalah **2026-08-14**. Post yang lebih tua dari itu tidak punya penyebut sama sekali: **301 dari 477 post (63%)** terbit sebelum snapshot pertama.

Sebab `er_followers` NULL di `post_metric`:

| Sebab | Post |
|---|---:|
| Tidak ada snapshot follower ≤ tanggal post | **318** |
| `is_collaboration` | 43 |
| `likes_hidden` | 18 |
| **Total NULL** | **337 / 477 (70,6%)** |

Jadi ER dari L2 hari ini menjawab pertanyaan "berapa ER kreator ini **dalam 15 hari terakhir**", bukan "berapa ER kreator ini". Itu bukan kesalahan rumus — carry-forward memang menolak menebak. Tapi konsumennya harus tahu, dan **metadata itu tidak di-expose ke UI**.

### Kesimpulan

> **L2 layak jadi source of truth ER, dan seharusnya memang jadi source of truth.** Rumusnya benar, satuannya konsisten, tidak ada nilai mustahil.
> **Tapi belum bisa dipakai menggantikan roster hari ini** — cakupannya 22 KOL vs 1.756. Memindahkan filter `minEr` ke L2 sekarang akan mengecilkan hasil direktori dari 219 KOL (pada `minEr=3`) menjadi paling banyak 22.
> Yang memblokir bukan L2-nya, melainkan **dua hal di hulu**: post baru ter-harvest untuk 30 akun, dan snapshot profil baru ada sejak 14 Agustus.

---

# C. Calculation Status — `READY` (dengan satu catatan presisi)

## Formula per layer

| Layer | Objek | Formula | Penyebut | Snapshot follower | Satuan |
|---|---|---|---|---|---|
| **L1** `sp_build_unified_post()` | per POST | `(likes + COALESCE(comments,0) + COALESCE(shares,0)) / followers × 100`, `round(...,4)` | followers pada tanggal post | LATERAL `pr.date <= (posted_at AT TIME ZONE 'Asia/Jakarta')::date`, `ORDER BY date DESC LIMIT 1` | **persen** |
| **Feature** `*_post_analysis` | per POST | pass-through `LEAST(round(unified_post.engagement_rate,4), 99999.9999)`, **hanya post lolos sampel** | idem | idem | **persen** |
| **Feature** `*_engagement_analysis` | per AKUN | `SUM(like+comment+share) FILTER (lolos AND followers NOT NULL) / SUM(followers) FILTER (sama) × 100`, `round(...,2)` | **aditif** — jumlah followers-pada-tanggal-post tiap post | idem | **persen** |
| **L2** `post_metric` | per POST | `engagement_owned / followers_at_post_date`, `round(...,8)`. NULL kalau tidak lolos sampel | followers pada tanggal post | carry-forward `date <= post_date` | **fraksi** |
| **L2** `kol_metric_daily` | per AKUN-HARI | `engagement_sum / followers_denom_sum` di mana `followers_denom_sum = followers_at_post_date × posts_in_sample` | aditif | carry-forward `date <= metric_date` | **fraksi** |
| **L2** `kol_metric_monthly` | per AKUN-BULAN | `engagement_for_er_sum / followers_denom_sum` | aditif, pembilang **diselaraskan** (hanya hari yang penyebutnya diketahui) | dari daily | **fraksi** |
| **Roster** `transform.py` | per AKUN | `avg(likes + comments) / followers_count × 100` | followers **saat scrape** | tidak ada konsep tanggal post | **persen** |

## Jawaban pertanyaan audit

- **Source data Feature?** `l1_silver.unified_post` untuk metrik, `l1_silver.unified_profile` untuk penyebut.
- **Denominator?** Followers — bukan reach, bukan views. `er_reach*` ada kolomnya tapi **0/477 dan 0/280**, blocked karena `unified_post.reach` kosong.
- **Snapshot follower kapan?** Carry-forward: snapshot **terakhir dengan `date <= tanggal tayang post`**. Kalau tidak ada → NULL, tidak ditebak.
- **Per post lalu diagregasi, atau langsung per akun?** **Keduanya ada, dan berbeda.** ER per post dihitung terpisah (`post_metric.er_followers`); ER per akun **tidak** merata-rata ER per post — ia memakai penyebut aditif `SUM(eng)/SUM(denom)`. Ini benar: rasio tidak additive.
- **Sesuai requirement AUTOME_2?** Ya. Prototype menampilkan ER sebagai satu angka per kreator dan memfilter `≥3%` / `≥5,5%` — persis yang dihasilkan agregat per akun.
- **Output unit?** Feature persen, L2 fraksi 0..1.

## Verifikasi konsistensi Feature ↔ L2

Meski dihitung terpisah, angkanya cocok sampai batas presisi masing-masing:

| Akun | Feature ER (persen, 2 desimal) | L2 ER (dikali 100) | Selisih |
|---|---:|---:|---:|
| aamandazahra | 16,15 | 16,1499 | 0,0001 |
| iben_ma | 2,01 | 2,0112 | 0,0012 |
| hesfinatia | 1,81 | 1,8093 | 0,0007 |
| cristiano | 1,81 | 1,8060 | 0,0040 |
| sptrakori_ | 0,60 | 0,6021 | 0,0021 |
| nanakoot | 0,59 | 0,5892 | 0,0008 |
| saalhaerid | 0,55 | 0,5530 | 0,0030 |
| pevpearce | 0,46 | 0,4577 | 0,0023 |

Selisih seluruhnya < 0,005 poin — murni pembulatan. **Tidak ada perbedaan definisi.**

## Status: `READY` — satu catatan

`feature.ig_engagement_analysis.engagement_rate` dan `tt_*` bertipe **`numeric(5,2)`**, sementara `feature.*_post_analysis.engagement_rate` sudah dilebarkan jadi `numeric(9,4)` oleh migration 017 justru untuk mencegah pembulatan-ke-nol.

Nilai per akun sekarang: median IG **0,34%**, median TT **0,26%**, minimum tercatat **0,0000**. Rentang itu persis yang jadi alasan migration 017 ditulis. Karena L2 (`numeric(12,8)`) yang akan jadi source of truth, ini tidak memblokir — tapi inkonsistensinya ada dan layak dicatat.

---

# D. L2 Status — `READY`

| Pertanyaan | Jawaban |
|---|---|
| Tabel apa? | `l2_gold.post_metric` (per post) · `kol_metric_daily` (akun-hari) · `kol_metric_monthly` (akun-bulan) · `content_format_daily` (akun-hari-format) |
| Kolom apa? | `er_followers` · `er_followers_daily` · `er_followers_monthly` · `er_followers_daily` |
| Berasal dari Feature? | **Tidak.** Dihitung ulang dari `unified_post` + `unified_profile`. Dari Feature hanya `rank_in_account` dan `top_hashtags` |
| Ada transformasi lagi? | Tidak. Endpoint mengirimnya apa adanya (`num(r.er_followers_daily)`), tanpa ×100 |
| Unit? | **Fraksi 0..1**, `numeric(12,8)`, konsisten di keempat tabel |
| Coverage | `post_metric` 140/477 · `daily` 73/280 · `monthly` 22/68 · `content_format_daily` 82/300. **22 KOL** dapat ER akun |
| NULL? | Ya, banyak — 70,6% di `post_metric`. Sebabnya terukur (§B), dan NULL adalah jawaban yang benar |
| Nilai tidak masuk akal? | **Tidak ada.** 0 nilai >100%, 0 negatif, maksimum 16,1499% |

Komponen aditif (`engagement_sum`, `followers_denom_sum`, `engagement_for_er_sum`) ikut disimpan, sehingga ER rentang N hari bisa dihitung benar dengan `SUM(engagement_sum)/SUM(followers_denom_sum)` — bukan merata-rata kolom harian.

**Satu-satunya yang kurang: tidak ada kolom yang memberitahu berapa post yang benar-benar menyumbang ke ER.** `posts_in_sample` menghitung post yang lolos aturan sampel, bukan post yang punya penyebut. Untuk aamandazahra keduanya berbeda jauh: `posts_in_sample` = 10, penyumbang ER = **2**.

---

# E. Endpoint Status — `NEED ENDPOINT CHANGE`

| Endpoint | Ambil ER dari | Field response | Satuan | Status |
|---|---|---|---|---|
| `GET /discover/kol-directory` (list) | `public.kol_directory.engagement_rate` (`BASE:186`) | `rows[].erPct` | persen | **NEED ENDPOINT CHANGE** |
| `GET /discover/kol-directory/[kolId]` | roster **dan** L2 | `creator.erPct` (roster, persen) · `platforms[].erPct` (roster) · `similar[].erPct` (roster) · `gold.posts[].erFollowers`, `gold.daily[].erFollowers`, `gold.monthly[].erFollowers`, `gold.formats[].erFollowers` (L2, fraksi) | **campur** | **NEED ENDPOINT CHANGE** |
| Ranking di detail (`er_rank`, `er_measured_total`, `category_er_rank`, `category_er_total`) | `kd.engagement_rate` (baris 600, 603, 619, 623) | `rank.*` | persen | **NEED ENDPOINT CHANGE** |
| Feature layer (`*_engagement_analysis`) | — | — | — | **tidak di-expose sama sekali** |

Ringkasnya: **tidak ada satu pun endpoint yang mengambil ER akun dari L2.** L2 hanya muncul sebagai deret harian/bulanan/per-post di halaman detail; angka ER tunggal yang dipakai kartu, tabel, ranking, filter, dan sort semuanya dari roster.

---

# F. Filter Status — `NEED FILTER CHANGE`

## Trace lengkap

```text
UI AUTOME_2
  slider "Min. engagement"  (fEr → state.adv.erMin, 0–10 step 0.1, satuan %)
  chip  "Good ER (≥3%)" / "High ER (≥5.5%)"  (F2.erHi → intel2(k).er)
        ↓
endpoint parameter
  ?minEr=<angka dalam POIN PERSEN>
        ↓  route.ts:49   minErPct: num('minEr')
backend
  kolDirectory.ts:351   query.minErPct ?? null   → parameter $5
        ↓
SQL condition
  filtered CTE:327   AND ($5::float8 IS NULL OR b.er_pct >= $5)
        ↓
table.column
  BASE:186   kd.engagement_rate::float AS er_pct
        ↓
ER source
  public.kol_directory.engagement_rate   ← RANTAI 1 (roster), bukan L2
```

## Jawaban

| Pertanyaan | Jawaban |
|---|---|
| Filter pakai `kol_directory.engagement_rate`? | **Ya** |
| Pakai Feature? | Tidak |
| Pakai L2? | **Tidak** |
| Unit filter sama dengan unit ER yang dikirim ke UI? | **Ya, hari ini** — keduanya membaca kolom yang sama (`b.er_pct`), jadi konsisten. Tapi hanya karena keduanya sama-sama salah sumber |

## Dua risiko unit yang perlu diketahui

1. **Kalau sumber diganti ke L2 tanpa konversi**, `er_followers_daily` maksimumnya **0,1615** sedangkan UI mengirim `minEr=3`. Kondisi `0.1615 >= 3` selalu false → **0 hasil untuk semua KOL**. Konversi ×100 wajib, atau ambangnya yang dikonversi.
2. **Kalau hanya field response yang diganti tapi filternya tidak** (atau sebaliknya), UI akan menampilkan angka dari satu sumber sambil menyaring dengan sumber lain.

## Dampak filter sekarang terhadap populasi

| Kondisi | KOL lolos |
|---|---:|
| Total aktif | 7.720 |
| Punya ER (roster) | 1.756 |
| `minEr = 3` | **219** |
| `minEr = 5,5` | **137** |

Perhatikan: `er_pct >= $5` membuang seluruh **5.964 KOL ber-ER NULL** secara diam-diam. Begitu slider digeser sedikit pun dari 0, 77% roster hilang tanpa penjelasan di UI.

---

# G. Data Quality

## G1 — Coverage seluruh sumber ER

| Sumber | Baris | Terisi | Satuan |
|---|---:|---:|---|
| `public.kol_directory.engagement_rate` | 7.720 | **1.756** | persen |
| `l0_harmonization.instagram_post.engagement_rate` | 186 | **0** | — |
| `l0_harmonization.tiktok_post.engagement_rate` | 291 | **0** | — |
| `l1_silver.unified_post.engagement_rate` | 477 | **157** | persen |
| `feature.ig_post_analysis.engagement_rate` | 186 | **45** | persen |
| `feature.tt_post_analysis.engagement_rate` | 291 | **95** | persen |
| `feature.ig_engagement_analysis.engagement_rate` | 19 | **12** | persen |
| `feature.tt_engagement_analysis.engagement_rate` | 11 | **10** | persen |
| `l2_gold.post_metric.er_followers` | 477 | **140** | fraksi |
| `l2_gold.kol_metric_daily.er_followers_daily` | 280 | **73** | fraksi |
| `l2_gold.kol_metric_monthly.er_followers_monthly` | 68 | **22** | fraksi |
| `l2_gold.content_format_daily.er_followers_daily` | 300 | **82** | fraksi |
| `l2_gold.post_metric.er_reach` *(blocked)* | 477 | **0** | — |
| `l2_gold.kol_metric_daily.er_reach_daily` *(blocked)* | 280 | **0** | — |

## G2 — L2 ER per AKUN (yang akan dipakai AUTOME_2)

Dihitung benar: `SUM(engagement_sum) / SUM(followers_denom_sum) × 100`

| Metrik | Nilai |
|---|---|
| Total KOL aktif | **7.720** |
| KOL punya baris L2 | **30** |
| **KOL dengan ER** | **22** |
| **NULL / tanpa ER** | **7.698** |
| Minimum | **0,0016%** |
| Median | **0,2793%** |
| Average | **1,1794%** |
| Maksimum | **16,1499%** |
| ER > 100% | **0** |
| ER < 0% | **0** |

## G3 — L2 ER per POST dan per HARI

| Tabel | Platform | Baris | Terisi | NULL | Min | Median | Avg | Maks | >100% | <0% |
|---|---|---:|---:|---:|---|---|---|---|---:|---:|
| `post_metric` | instagram | 186 | 45 | 141 | 0,0016% | 0,1081% | 1,1065% | **31,2804%** | 0 | 0 |
| `post_metric` | tiktok | 291 | 95 | 196 | 0,0003% | 0,2174% | 0,4886% | 7,5343% | 0 | 0 |
| `post_metric` | **semua** | 477 | **140** | **337** | 0,0003% | 0,1747% | 0,6872% | 31,2804% | **0** | **0** |
| `kol_metric_daily` | instagram | 148 | 29 | 119 | 0,0016% | 0,1634% | 1,0921% | 16,1499% | 0 | 0 |
| `kol_metric_daily` | tiktok | 132 | 44 | 88 | 0,0076% | 0,3169% | 0,4774% | 3,0349% | 0 | 0 |
| `kol_metric_daily` | **semua** | 280 | **73** | **207** | 0,0016% | 0,2556% | 0,7216% | 16,1499% | **0** | **0** |
| `kol_metric_monthly` | — | 68 | **22** | 46 | 0,0016% | 0,2793% | — | 16,1499% | **0** | — |

## G4 — Roster ER: kenapa bisa 223,41%

**Formula** (`transform.py::compute_engagement_rate`):

```python
avg(likes + comments) atas item["latestPosts"]  /  followers_count  * 100
```

**Sebaran:**

| Metrik | Nilai |
|---|---|
| Terisi | 1.756 / 7.720 |
| Minimum | 0,0000 |
| Median | **0,6000** |
| Average | 2,8147 |
| Maksimum | **223,4100** |
| > 100% | **7** |
| > 20% | **53** |
| > 10% | **83** |
| < 0% | 0 |
| = 0 | 6 |

**Sepuluh nilai tertinggi — implied rata-rata interaksi per post:**

| Username | Followers | ER | Implied avg interaksi/post | Tier |
|---|---:|---:|---:|---|
| rhasiebatara | 116.777 | **223,41%** | 260.891 | Mid-tier |
| nikma.rahmaa | 102.105 | 174,85% | 178.531 | Mid-tier |
| faniaelizaa | 69.423 | 173,36% | 120.352 | Mid-tier |
| winnylieyantii | 43.600 | 127,34% | 55.520 | Micro |
| bjawato | 117.988 | 115,41% | 136.170 | Mid-tier |
| skupingg | 271.556 | 113,60% | 308.488 | Mid-tier |
| putrikurniads_ | 126.153 | 109,56% | 138.213 | Mid-tier |
| maverick.jonathan | 97.558 | 70,46% | 68.739 | Mid-tier |
| nisaput_hudia | 74.448 | 62,43% | 46.478 | Mid-tier |
| puputdewiasiah17 | 88.495 | 62,13% | 54.982 | Mid-tier |

**Terkonsentrasi di akun kecil-menengah** — dari 83 nilai >10%: Mid-tier 59, Micro 11, Macro 6, Mega 5, Nano 1, tanpa tier 1.

### Empat sebab, semuanya struktural

| # | Sebab |
|---|---|
| **1** | **Tidak ada aturan sampel.** `is_collaboration` tidak dikenal di jalur ini — flag itu baru muncul di L1. Post kolaborasi yang like-nya sebagian milik audiens akun lain tetap ikut dihitung terhadap follower akun ini |
| **2** | **Penyebut = followers saat scrape**, bukan followers saat post tayang. `latestPosts` bisa berisi konten lama dari masa akun jauh lebih kecil |
| **3** | **Pembilang tidak memasukkan share** — inkonsisten dengan definisi bisnis yang dipakai L1/Feature/L2 |
| **4** | **Sampel = apa pun isi `latestPosts`** (±12 post), tanpa jendela waktu, tanpa penjaga, tanpa hubungan dengan 477 post yang benar-benar ada di L1 |

Tambahan: konten Reels/TikTok memang bisa menjangkau jauh melampaui follower, jadi ER >100% **tidak selalu berarti data rusak** — tapi karena tidak ada satu pun penjaga di atas, **tidak ada cara membedakan "viral asli" dari "sampel salah"**.

### Layak dipakai AUTOME_2?

**Tidak layak sebagai angka yang ditampilkan maupun difilter.** Empat sebab di atas melanggar definisi ER yang dipakai di seluruh sisa pipeline. Nilainya tidak bisa direkonsiliasi dengan L2, dan 7 nilai >100% akan tampil apa adanya di kartu KOL.

**Tapi ini satu-satunya sumber dengan coverage 22,7%.** Membuangnya hari ini berarti direktori kehilangan angka ER untuk 1.734 KOL yang tidak punya padanan di L2.

## G5 — Roster vs L2 untuk akun yang sama

| Metrik | Nilai |
|---|---|
| Akun punya ER di **kedua** sumber | **12** |
| Rata-rata selisih | **0,94 poin persen** |
| Selisih maksimum | **9,21 poin persen** |
| Akun berbeda >1 poin | 1 |

Contoh terburuk terlihat di §H: **aamandazahra — roster 6,94% vs L2 16,15%**, selisih 9,21 poin untuk kreator yang sama.

---

# H. Sample Trace

## H1 — Delapan KOL: roster → Feature → L2

| Username | Platform | Followers | ER roster | ER Feature | **ER L2** | Post di L2 | Sampel | Post di Feature |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| aamandazahra | instagram | 1.194.675 | **6,94%** | 16,15% | **16,1499%** | 10 | 10 | 10 |
| iben_ma | instagram | 3.997.609 | 1,46% | 2,01% | **2,0112%** | 10 | 8 | 8 |
| hesfinatia | tiktok | 12.000.000 | **NULL** | 1,81% | **1,8093%** | 10 | 10 | 10 |
| cristiano | instagram | 679.264.838 | 2,21% | 1,81% | **1,8060%** | 10 | 8 | 8 |
| sptrakori_ | tiktok | 13.100.000 | **NULL** | 0,60% | **0,6021%** | 10 | 10 | 10 |
| nanakoot | tiktok | 9.900.000 | **NULL** | 0,59% | **0,5892%** | 200 | 200 | 200 |
| saalhaerid | instagram | 2.249.679 | 0,72% | 0,55% | **0,5530%** | 10 | 8 | 8 |
| pevpearce | instagram | 17.452.714 | 0,28% | 0,46% | **0,4577%** | 10 | 9 | 9 |

Tiga dari delapan **tidak punya ER di roster sama sekali** — jadi hari ini mereka tidak akan pernah lolos filter `minEr` berapa pun, meski L2 punya angkanya.

## H2 — Trace per post: aamandazahra (ER akun tertinggi)

| Tanggal | Media type | Likes | Comments | Engagement | Followers pada tgl post | ER post | Ikut ER? |
|---|---|---:|---:|---:|---|---:|---|
| 2026-08-26 | NULL | 372.538 | 1.161 | 373.699 | 1.194.675 | **31,2804%** | ✅ |
| 2026-08-26 | clips | 12.137 | 42 | 12.179 | 1.194.675 | 1,0194% | ✅ |
| 2026-08-13 | clips | 103.925 | 810 | 104.735 | **NULL** | NULL | ❌ |
| 2026-08-08 | clips | 65.407 | 298 | 65.705 | **NULL** | NULL | ❌ |
| 2026-08-06 | clips | 57.926 | 429 | 58.355 | **NULL** | NULL | ❌ |
| 2026-08-05 | clips | 47.265 | 492 | 47.757 | **NULL** | NULL | ❌ |
| 2026-07-25 | NULL | 72.389 | 180 | 72.569 | **NULL** | NULL | ❌ |
| 2026-07-24 | NULL | 116.234 | 644 | 116.878 | **NULL** | NULL | ❌ |
| 2026-07-16 | clips | 71.079 | 488 | 71.567 | **NULL** | NULL | ❌ |
| 2026-07-07 | NULL | 230.432 | 1.064 | 231.496 | **NULL** | NULL | ❌ |

Verifikasi aritmetika: `(373.699 + 12.179) / (1.194.675 × 2) = 385.878 / 2.389.350 = 16,1499%` ✅ — persis nilai `er_followers_daily` dan Feature ER.

**Rumusnya benar. Sampelnya yang menyesatkan:** ER "16,15%" akun ini berasal dari **2 post pada satu hari**, dan satu di antaranya outlier 31,28%. Delapan post lain — termasuk yang 230.432 likes — dibuang karena terbit sebelum snapshot profil pertama (2026-08-14).

Endpoint akan mengirim `gold.daily[].erFollowers = 0.16149915` untuk kreator ini, sementara `creator.erPct = 6.94`. Dua angka, satu kreator, satu response.

## H3 — Post ER tertinggi di seluruh L2

| Username | Tanggal | Likes | Comments | Engagement | Followers | ER post |
|---|---|---:|---:|---:|---:|---:|
| aamandazahra | 2026-08-26 | 372.538 | 1.161 | 373.699 | 1.194.675 | 31,2804% |
| nanakoot | 2026-08-14 | 701.600 | 1.699 | 745.899 | 9.900.000 | 7,5343% |
| iben_ma | 2026-08-16 | 181.245 | 1.351 | 182.596 | 3.997.609 | 4,5676% |
| hesfinatia | 2026-08-16 | 535.400 | 1.211 | 544.726 | 14.900.000 | 3,6559% |
| sptrakori_ | 2026-08-16 | 614.000 | 2.253 | 631.453 | 20.200.000 | 3,1260% |

Semuanya masuk akal secara aritmetika, dan tidak ada satu pun >100%.

---

# I. JOIN Audit

## Rantai join untuk ER dari L2

```text
public.kol_directory  (7.720 aktif)
   │  ksa.kol_id = kd.id
   ▼
public.kol_social_account  (7.496 kol_id)          ← 224 KOL TIDAK punya pasangan
   │  sa.id = ksa.social_account_id
   ▼
public.social_account  (7.496)
   │  d.social_account_id = sa.id
   ▼
l2_gold.kol_metric_daily  (280 baris / 30 akun)    ← 22 akun ber-ER
   │  penyebut: LATERAL ke l1_silver.unified_profile
   │            WHERE date <= metric_date ORDER BY date DESC LIMIT 1
   ▼
er_followers_daily  (fraksi 0..1)
```

| Sambungan | Join key | Kardinalitas | Risiko duplikat | Sudah dilakukan existing code? |
|---|---|---|---|---|
| `kol_directory` → `kol_social_account` | `ksa.kol_id = kd.id` | **1:1** (0 kol_id punya >1) | Tidak ada | ✅ Ya, sebagai `EXISTS` untuk Connected dan `maxRate` |
| `kol_social_account` → `social_account` | `sa.id = ksa.social_account_id` | 1:1 | Tidak ada | ✅ Ya |
| → `l2_gold.kol_metric_daily` | `d.social_account_id` | **1:N** — **28 dari 30 akun punya >1 `metric_date`** | **Ada, tinggi** | ❌ **Tidak.** `kolDirectory.ts` tidak pernah join ke L2 di list |
| → `l1_silver.unified_profile` (penyebut) | LATERAL `date <= metric_date` | 1:1 setelah `LIMIT 1` | Tidak ada | ✅ Ya, di dalam asset L2 |

## Temuan join

| # | Temuan |
|---|---|
| **J1** | **224 KOL akan hilang diam-diam** kalau join roster→`kol_social_account` memakai INNER. Wajib LEFT JOIN, atau `EXISTS`/subquery seperti yang sudah dipakai filter `maxRate` |
| **J2** | **Join langsung ke `kol_metric_daily` akan melipatgandakan baris** — 28 dari 30 akun punya banyak `metric_date`. Agregasi (`SUM(engagement_sum)/SUM(followers_denom_sum)`) **wajib** dilakukan di subquery sebelum join, bukan sesudahnya |
| **J3** | **Platform tidak menggandakan baris**: 0 `social_account_id` yang punya >1 platform di `kol_metric_daily` |
| **J4** | **Penyebut memakai snapshot yang tepat secara logika** (carry-forward `date <= post_date`, tidak menebak) tetapi **tidak memadai secara cakupan**: snapshot pertama 2026-08-14 sementara post membentang ke 2021-02-18. **301 dari 477 post (63%)** terbit sebelum snapshot mana pun |
| **J5** | `post_metric` punya 159 baris ber-`followers_at_post_date`, tetapi hanya **140** yang dapat ER — 19 sisanya terbuang aturan sampel (`is_collaboration` 43, `likes_hidden` 18, sebagian beririsan) |

---

# J. Development Needed

## 1. Tidak perlu diubah

| Item | Alasan |
|---|---|
| Formula ER di **L1** (`sp_build_unified_post`, migration 024) | Penyebut followers-pada-tanggal-post sudah benar; share sudah masuk pembilang |
| Formula ER di **Feature** (`*_engagement_analysis`, `*_post_analysis`) | Penyebut aditif, aturan sampel eksplisit, cocok dengan L2 sampai <0,005 poin |
| Formula ER di **L2** (keempat tabel) | Benar, konsisten fraksi, 0 nilai mustahil, komponen aditif ikut disimpan |
| Aturan sampel `likes_hidden` + `is_collaboration` | Sudah jadi kolom di L1, dipakai konsisten oleh Feature dan L2 |
| Carry-forward penyebut | Menolak menebak. NULL adalah jawaban yang benar |
| `er_reach*` dibiarkan NULL | Blocked karena `unified_post.reach` 0/477 — bukan bug |

## 2. Perlu diperbaiki

| # | Item | Bukti |
|---|---|---|
| **F1** | **Tetapkan satu ER kanonik dan tandai sisanya legacy** | 4 sumber ER hidup berdampingan; roster dan L2 berbeda sampai 9,21 poin untuk kreator yang sama |
| **F2** | **`kol_directory.engagement_rate` tidak layak ditampilkan** | 7 nilai >100%, maksimum 223,41%, tanpa aturan sampel, penyebut salah, pembilang tanpa share |
| **F3** | **Expose jumlah post penyumbang ER** | `posts_in_sample` ≠ post yang punya penyebut. aamandazahra: 10 vs **2**. Tanpa ini UI menampilkan 16,15% seolah dari 10 post |
| **F4** | **Expose jendela tanggal ER** | Seluruh 140 post penyumbang ada di 2026-08-14…08-28. Yang ditampilkan adalah ER 15 hari, bukan ER kreator |
| **F5** | **Lebarkan `feature.*_engagement_analysis.engagement_rate`** dari `numeric(5,2)` | Median 0,34% (IG) / 0,26% (TT), minimum tercatat 0,0000 — persis kondisi yang membuat migration 017 dibuat untuk `*_post_analysis` |

## 3. Perlu endpoint

| # | Item | Lokasi |
|---|---|---|
| **E1** | ER akun dari L2 di **list endpoint** — agregat `SUM(engagement_sum)/SUM(followers_denom_sum)` per KOL | `kolDirectory.ts` `BASE` / CTE baru |
| **E2** | Konversi satuan eksplisit fraksi → persen di batas API, dan **satu nama field** yang jelas asalnya | `kolDirectory.ts`, `kolGold.ts` |
| **E3** | Hentikan pengiriman dua ER berbeda satuan dalam satu response detail | `getKolCreator()` |
| **E4** | Ranking ER (`er_rank`, `er_measured_total`, `category_er_rank`) pindah ke sumber kanonik | `kolDirectory.ts:600, 603, 619, 623` |
| **E5** | Expose Feature `*_engagement_analysis` — belum pernah di-expose sama sekali | route detail |

## 4. Perlu filter

| # | Item | Bukti |
|---|---|---|
| **L1** | `minEr` pindah ke sumber kanonik | Sekarang `b.er_pct` = `kd.engagement_rate` |
| **L2** | **Konversi ambang wajib** | `er_followers_daily` maks **0,1615**; `minEr=3` → `0.1615 >= 3` false → **0 hasil** |
| **L3** | Putuskan perlakuan NULL | `er_pct >= $5` membuang 5.964 KOL diam-diam. Kalau pindah ke L2, yang terbuang jadi **7.698** |
| **L4** | Chip `≥3%` / `≥5,5%` perlu dicek ulang setelah sumber diganti | Dengan L2: median 0,2793%, maks 16,1499% → `≥3%` hanya menyisakan segelintir dari 22 |

## 5. Blocked / dependency

| # | Blocker | Angka | Konsekuensi |
|---|---|---|---|
| **B1** | **Snapshot profil baru ada sejak 2026-08-14** | 301/477 post (63%) tanpa penyebut | ER L2 hanya mencakup 15 hari. Tidak bisa diperbaiki dengan kode |
| **B2** | **Post baru ter-harvest untuk 30 akun** | 30 / 7.720 (0,39%) | ER L2 maksimum menjangkau 30 KOL |
| **B3** | **22 KOL punya ER L2** vs 1.756 di roster | 0,28% vs 22,7% | Pindah total ke L2 hari ini memperkecil hasil filter dari 219 → maks 22 |
| **B4** | **8 dari 30 akun ER-nya dari ≤2 post** | lihat §B | ER-nya sah secara rumus tapi rapuh secara statistik |
| **B5** | **`er_reach*` menunggu Insights API** | `unified_post.reach` 0/477 | ER berbasis reach tidak mungkin |
| **B6** | **Instagram tanpa `shares`** | 0/186 | `engagement_sum` Instagram efektif hanya `like + comment` — understated terhadap definisi bisnis. TikTok tidak terdampak (291/291) |

---

*Audit read-only. Tidak ada perubahan pada kode, database, schema, migration, pipeline, endpoint, atau UI. Tidak ada commit atau push. Seluruh angka diukur langsung 2026-09-08 06:19 lewat sesi `set_session(readonly=True)`.*
