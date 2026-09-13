# WHAT MATTERS MOST — AUDIT & IMPLEMENTASI

**Tanggal:** 13 September 2026 · DB `kol` @ `10.100.14.216`
**Perubahan DB: NOL.** Tidak ada tabel, kolom, view, atau migration.
Seluruh skor dihitung saat dibaca.

---

## 1. AUDIT SOURCE — 7 kriteria

| # | Kriteria | Field | Tipe | Terisi | Rentang | Arah |
|---|---|---|---|---:|---|---|
| 1 | Strong Engagement | `kol_directory.engagement_rate` | numeric | **1.736 / 7.432 (23,4%)** | 0 – **223,41**; p50 0,600 · p95 9,42 · p99 49,39 | tinggi = baik |
| 2 | High Audience Quality | `kol_profile_card.audience_quality_score`<br>`.authenticity_score` | numeric | **27 / 1.978 (1,4%)** | aq 54–94 · auth 29–100 | tinggi = baik |
| 3 | Consistent Performance | `.performance_stability`<br>`.post_frequency_reliability` | **varchar** | 11 · 49 | label ordinal | tinggi = baik |
| 4 | Strong Company/Community | — **tidak ada kolom** | — | 0 | — | — |
| 5 | High Reach | `.median_views` / `.avg_views` | numeric | 30 · 30 | 679 – 136.309.208 | tinggi = baik |
| 6 | Content Quality | `.format_dominant` · `.content_topic` | varchar | 49 · 42 | 3 format · 11 topik | **tidak ada urutan kualitas** |
| 7 | Brand Safety | — **tidak ada kolom** | — | 0 | — | — |

### Temuan audit yang mengubah desain

**(a) `performance_stability` dan `post_frequency_reliability` adalah LABEL, bukan angka.**
Angka mentah stabilitas ada di `er_stddev_pp` (13 terisi), dan **SD kecil = stabil**
(High Stability SD 0,023–0,625; Medium 1,060–1,694). Pembalikan arahnya **sudah
dilakukan** `metrics_thresholds.klasifikasi_stability`. Jadi modul ini memakai
**labelnya**, bukan menghitung ulang dari SD — supaya tidak ada definisi kedua.

**(b) `audience_quality_score` SUDAH mengandung authenticity.**
`audience_inference.py:1102`:

```python
fq = follower_quality_score
au = authenticity_score
aq = round((fq + au) / 2)      # audience_quality_score
```

Diverifikasi atas data nyata: **21 dari 27 baris cocok persis**, 6 sisanya beda
1 poin karena pembulatan. Korelasi aq↔auth = **0,7367**.

→ Bobot yang diusulkan (AQ 40% + authenticity 30% + ER 30%) akan memberi
authenticity **0,40×0,50 + 0,30 = 50% efektif**, sementara follower quality
cuma 20%. **Itu double-count.** Diperbaiki di §2.4.

**(c) `median_views` lebih tepat daripada `avg_views`.**
Korelasi 0,957, tapi rata-rata tertarik post viral: p50 `avg_views` **638.034**
vs `median_views` **344.739**. Akun dengan satu post meledak akan naik melewati
akun yang konsisten.

**(d) Format dan topik tidak punya urutan kualitas.**
`format_dominant`: Carousel 24 · Video 20 · Image 5.
`content_topic`: 11 topik dari caption + 2 dari fallback.
Tidak ada satu sumber pun — DB, Excel, prototype — yang menyatakan Carousel
lebih berkualitas daripada Image, atau `food` lebih berkualitas daripada
`religion`.

**(e) Tidak ada sumber topic safety.**
`*_comments_analysis` (toxicity, sentiment) **0 baris**. Tidak ada taksonomi
aman/tidak-aman untuk ke-11 topik.

**(f) `k.cons` prototype = hash creator id** — tidak dipakai, sesuai instruksi.

---

## 2. FORMULA FINAL

Semua 0–100. **NULL tetap NULL, tidak pernah jadi 0.**

### 2.1 Strong Engagement — REAL

```
engagement_score = persentil(engagement_rate, populasi ER terukur) × 100
```

**Kenapa persentil, bukan normalisasi linear:** ER punya ekor sampai 223,41%.
Normalisasi terhadap maksimum akan memberi ER 4% (di atas median) skor
`4/223,41×100 = 1,79` — hampir seluruh populasi tertekan ke nol. Persentil
kebal outlier **dan tidak memerlukan benchmark yang harus dikarang**.

Populasi = hanya yang terukur. NULL tidak ikut, dan tidak dianggap nol.

### 2.2 High Audience Quality — REAL

```
audience_quality_score = rata-rata(aq, authenticity) yang tersedia
```

Keduanya sudah 0–100 di sumbernya → **tidak dinormalisasi ulang**. Satu NULL →
pakai yang ada. Keduanya NULL → NULL.

### 2.3 Consistent Performance — REAL

```
consistency_score = rata-rata dari yang tersedia:
    performance_stability      Low/Medium/High Stability -> 0 / 50 / 100
    post_frequency_reliability Low/Medium/High           -> 0 / 50 / 100
```

Aturan label→angka **deterministik**: posisi ordinal dinormalisasi
(`indeks / (jumlah_tingkat − 1) × 100`), bukan angka pilihan. Ini **urutan**,
bukan pengukuran — "Medium" tidak berarti separuh sebaik "High".

### 2.4 Strong Company/Community — **PROXY**

```
community_strength_score = audience_quality_score × 0,70
                         + engagement_percentile  × 0,30
```

**Berbeda dari bobot yang diusulkan, dan ini disengaja.** Karena
`audience_quality_score` = rata-rata(follower_quality, authenticity) — temuan
audit (b) — memakai authenticity lagi sebagai komponen terpisah akan
menghitungnya dua kali. AQ dipakai sendirian karena ia **sudah** membawa
follower quality dan authenticity dengan bobot setara.

⚠️ **Ini PROXY, bukan ukuran komunitas.** Tidak ada kolom community di seluruh
101 tabel. Ia gabungan dua sinyal yang masuk akal berkorelasi dengan audiens
yang hidup: audiens yang asli, dan audiens yang berinteraksi.

### 2.5 High Reach — **PROXY BERBASIS VIEWS**

```
reach_proxy_score = persentil(median_views, populasi views) × 100
```

⚠️ **Bukan reach Insights.** Views menghitung penayangan (bisa berulang dari
orang yang sama); reach menghitung akun unik.

`estimated_reach` **tidak** dipakai sebagai fallback — 2.164 barisnya punya
reach > followers (pergeseran kolom CSV). Reach kanonik tetap Insights;
seluruh tabel `*_official` **0 baris**, dan **0 dari 7.208 akun** tersambung
OAuth.

### 2.6 Content Quality — **TIDAK TERSEDIA, selalu NULL**

Bobot yang diusulkan: engagement 40% + format 30% + topik 30%.

Format dan topik (60% bobot) **tidak punya urutan kualitas yang bisa
dipertanggungjawabkan** — temuan (d). Memberi skor karena kolomnya terisi
persis yang dilarang.

Sisanya cuma engagement 40% — dan itu **sudah** kriteria #1. Memakainya ulang
akan membuat sinyal yang sama dihitung dua kali di rata-rata What Matters.

→ **NULL, bukan angka setengah jadi.**

### 2.7 Brand Safety — **TIDAK TERSEDIA, selalu NULL**

Bobot yang diusulkan: authenticity 50% + topic safety 30% + data quality 20%.

| Komponen | Status |
|---|---|
| authenticity | ✅ ada (27 baris) |
| topic safety | ❌ tidak ada sumber — temuan (e) |
| data quality | ❌ tidak ada definisinya sebagai komponen brand safety |

Setengah bobot tanpa sumber. Kalau sisanya dinormalisasi, hasilnya **persis
sama dengan `authenticity_score`** — satu angka, dua nama, dan yang kedua
menjanjikan jaminan keamanan merek yang tidak diberikannya.

→ **NULL.**

Keduanya **tetap terdaftar** di `KRITERIA` supaya UI menampilkannya
**nonaktif beserta alasannya**, bukan menyembunyikannya.

### 2.8 What Matters Score

```
what_matters_score = rata-rata(skor kriteria yang DIPILIH dan PUNYA NILAI)
ranking            = ORDER BY what_matters_score DESC NULLS LAST
```

Kriteria terpilih yang NULL **keluar dari penyebut**, bukan dihitung nol.
Contoh: `(85 + 72 + 90) / 3 = 82,33`. Kalau reach NULL:
`(80 + 60) / 2 = 70`, bukan `(80+60+0)/3 = 46,67`.

---

## 3. REAL vs PROXY

| Kriteria | Sifat | Alasan |
|---|---|---|
| Strong Engagement | **REAL** | ER memang mengukur engagement |
| High Audience Quality | **REAL** | kedua skor memang mengukur kualitas audiens |
| Consistent Performance | **REAL** | stabilitas ER + reliabilitas cadence memang mengukur konsistensi |
| Strong Company/Community | **PROXY** | tidak ada kolom community; dihitung dari kualitas audiens + engagement |
| High Reach | **PROXY** | dihitung dari **views**, bukan reach Insights |
| Content Quality | **TIDAK TERSEDIA** | format & topik tanpa urutan kualitas |
| Brand Safety | **TIDAK TERSEDIA** | topic safety & data quality tanpa sumber |

`SIFAT` disimpan per kriteria di `KRITERIA[...]["sifat"]` dan **wajib
diteruskan API** — supaya PROXY tidak pernah tampil sebagai pengukuran.

---

## 4. KONTRAK API

```
GET /api/organizations/{id}/discover/kol?matters=engagement,consistency,brand_safety
```

| Kunci | Kriteria | Skor |
|---|---|---|
| `engagement` | Strong Engagement | `engagement_score` |
| `audience_quality` | High Audience Quality | `audience_quality_score` |
| `consistency` | Consistent Performance | `consistency_score` |
| `community` | Strong Company/Community | `community_strength_score` |
| `reach` | High Reach | `reach_proxy_score` |
| `content_quality` | Content Quality | `content_quality_score` (NULL) |
| `brand_safety` | Brand Safety | `brand_safety_score` (NULL) |

`parse_matters()` mengabaikan kunci tak dikenal, bukan menggagalkan request.

---

## 5. COVERAGE ATAS DATA NYATA

Dijalankan read-only atas **7.208 baris** (`kol_directory` ⋈ `kol_profile_card`).
Populasi ER terukur **1.736**, populasi views **30**.

| Kriteria | Sifat | Ada | NULL | Coverage |
|---|---|---:|---:|---:|
| engagement | real | 1.736 | 5.472 | **24,08%** |
| audience_quality | real | 27 | 7.181 | 0,37% |
| consistency | real | 49 | 7.159 | 0,68% |
| community | proxy | 1.746 | 5.462 | **24,22%** |
| reach | proxy | 30 | 7.178 | 0,42% |
| content_quality | tidak tersedia | 0 | 7.208 | 0,00% |
| brand_safety | tidak tersedia | 0 | 7.208 | 0,00% |

**KOL yang punya What Matters Score (5 kriteria aktif dipilih): 1.748 / 7.208 = 24,25%.**

---

## 6. CONTOH RANKING NYATA

`matters=engagement,audience_quality,consistency,community,reach`

| # | KOL | Platform | WM Score | Kriteria berkontribusi | NULL (keluar penyebut) |
|---|---|---|---:|---|---|
| 1 | `@rhasiebatara` | instagram | **100,00** | engagement 100,0 · community 100,0 | audience_quality, consistency, reach |
| 2 | `@nikma.rahmaa` | instagram | **99,94** | engagement 99,9 · community 99,9 | audience_quality, consistency, reach |
| 3 | `@faniaelizaa` | instagram | **99,88** | engagement 99,9 · community 99,9 | audience_quality, consistency, reach |

⚠️ **Ketiganya justru outlier ER** — 223,41% · 174,85% · 173,36%. Untuk
definisi ER yang dipakai (`AVG(likes+comments) ÷ followers × 100`), nilai di
atas 100% secara aritmetika tidak masuk akal sebagai rata-rata berkelanjutan.
Ada **7 KOL dengan ER > 100%** dan **53 dengan ER > 20%**.

Persentil melindungi **skala** (outlier tidak menekan yang lain ke nol), tapi
ia **tidak memperbaiki data sumber** — dan tidak seharusnya. ER tidak diubah,
sesuai instruksi. Ini blocker B1 di §9.

Catatan kedua: peringkat teratas hanya punya 2 dari 5 kriteria. Itu konsekuensi
langsung aturan "NULL keluar dari penyebut" — sesuai spesifikasi, tapi berarti
kreator yang terukur di satu kriteria tinggi bisa mengalahkan kreator yang
terukur di lima kriteria sedang. Mitigasi yang disarankan: tampilkan
**jumlah kriteria yang berkontribusi** di samping skornya.

---

## 7. FILE & PERUBAHAN DB

### Dibuat

| File | Isi |
|---|---|
| `what_matters_scoring.py` | 7 kriteria, normalisasi persentil, ordinal, What Matters Score, ekspresi SQL |
| `tests/test_what_matters_scoring.py` | 68 test |
| `docs/KOL_WHAT_MATTERS_IMPLEMENTASI.md` | dokumen ini |

### Diubah

Nol file existing. Nol business logic lain.

### Migration

**Tidak ada.** Tidak diperlukan.

### Perubahan DB

**NOL.** Diverifikasi setelah implementasi:

| | |
|---|---|
| Tabel `public` | **42** (tidak berubah sejak migration 045) |
| Kolom `l2_gold.kol_profile_card` | **71** (tidak berubah) |
| View di DB | **0** (tidak ada yang dibuat) |
| Kolom skor What Matters di kartu L2 | **tidak ada** |
| `kol_attribute` / `kol_attribute_map` | 40 / 0 (tidak tersentuh) |
| `kol_directory` / `kol_profile_card` | 7.432 / 1.978 (tidak berubah) |

---

## 8. TEST

| | Sebelum | Sesudah |
|---|---:|---:|
| Total pytest | **983** | **1.051** |
| Test baru | — | **+68** |
| Gagal | 0 | **0** |

```
1051 passed, 7 subtests passed, 112 warnings in 26,17s
```

Nol regression. Guard lama yang jalan ke DB hidup tetap hijau.

Satu bug ditemukan test sendiri saat pengembangan: `persentil_ke_skor`
mengembalikan **120** untuk nilai di luar populasi. Diperbaiki dengan
membatasi pembilang ke `n−1`.

---

## 9. BLOCKER TERSISA

| # | Blocker | Dampak |
|---|---|---|
| **B1** | **Outlier ER**: 7 KOL > 100%, 53 KOL > 20%, maks 223,41% | Ketiganya menempati peringkat teratas. Perbaikannya di **sumber** (`transform.py` / data scraping), bukan di layer skor. ER tidak diubah sesuai instruksi |
| **B2** | Coverage `audience_quality` **0,37%** dan `reach` **0,42%** | Dua kriteria praktis tidak berpengaruh pada ranking populasi |
| **B3** | `content_quality` tanpa sumber | Butuh taksonomi kualitas format/topik dari Product, atau sinyal baru |
| **B4** | `brand_safety` tanpa sumber | Butuh topic-safety taxonomy + `*_comments_analysis` terisi |
| **B5** | Reach Insights **0 baris**, **0 akun OAuth** | `reach` tetap proxy views sampai Insights tersambung |
| **B6** | `consistency` coverage 0,68% | `er_stddev_pp` cuma 13 baris (butuh ≥3 periode) |
| **B7** | Bobot antar-kriteria | Sekarang seragam. Kalau Product mau bobot berbeda, `what_matters_score()` perlu parameter bobot |
| **B8** | Endpoint belum ada | Modul siap; integrasi ke route Discovery ada di repo aplikasi |
