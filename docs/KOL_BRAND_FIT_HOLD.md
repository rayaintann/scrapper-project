# Brand Fit — STATUS: HOLD

**Diverifikasi langsung ke DB `kol` (10.100.14.216) pada 2026-09-13 05:48 UTC.**
PostgreSQL 16.15. Sesi read-only. Nol DDL, nol DML, nol perubahan schema.

Scope dokumen ini **hanya** Brand Fit. CPE/CPV tidak disentuh. EMV, Rate Card,
What Matters Most, Style & Personality, ER, Content Quality, Brand Safety tidak
disentuh.

---

## 1. Vonis

| | |
|---|---|
| **Status** | **HOLD** |
| Alasan | Formula `partnership_score` dan keempat sub-skor **tidak pernah ditulis** di source code, docs, data dictionary, SQL, test, migration, maupun backlog |
| Implementasi | **Tidak ada.** Nol file kode diubah, nol test baru, nol migration |

Yang ditulis ulang di sini semuanya kutipan dari artefak yang sudah ada. Tidak
ada satu pun angka, bobot, atau aturan baru yang dikarang di dokumen ini.

---

## 2. Temuan kunci — Brand Fit ≠ Brand Match

Ini akar seluruh persoalan, dan sudah tercatat di
`docs/KOL_EXCEL_DB_MATCHING_AUDIT.md` §6.4.

| | Brand Match | Brand Fit |
|---|---|---|
| Asal | didefinisikan `brand_match_master.xlsx` | sudah ada di DB sebelum workbook itu |
| Rumah kolom | **tidak ada** | `feature.brand_fit_analysis.partnership_score` |
| Algoritma | **lengkap** — 6 komponen, 22 sub-bobot, 9 matriks relevansi | **belum didefinisikan** |
| Struktur output | `Final Match Score` + 6 komponen | `partnership_score` + **4** sub-skor |
| Di UI | `minBrandMatch` | `brandFitMin`, `k.aff`, `k.match` |
| Grain | brand × KOL | brand × KOL |

Grain-nya identik dan itu menggoda, tapi **struktur output-nya berbeda**: Brand
Match punya 6 komponen (Brand&Business, Target Audience, Content&Category,
Personality, Performance, Brand Safety), Brand Fit punya 4 aspek (Category
matching, Audience overlap, Values alignment, Past performance). Tidak ada
pemetaan 6→4 di dokumen mana pun.

Memakai formula Brand Match untuk mengisi `partnership_score` berarti
**memutuskan bahwa Brand Fit dan Brand Match adalah satu hal**. Itu keputusan
Product, bukan keputusan teknis — dan `KOL_EXCEL_DB_MATCHING_AUDIT.md` §6.4 sudah
menandainya **NEED PRODUCT DECISION**.

### 2.1 Tiga formula yang saling bertabrakan di dalam satu workbook

Kalaupun keputusan "Brand Fit = Brand Match" diambil, workbook-nya sendiri
menawarkan **tiga** bobot berbeda:

| Sumber | Formula |
|---|---|
| `README` r21 / `Lookup_Lists` §4 | `20 Brand&Business + 30 TargetAudience + 20 Content&Category + 10 Personality + 10 Performance + 10 BrandSafety` |
| `Unified_Spec` | `UNIFIED SCORE = 70% Brand Match + 30% Campaign Fit`, Campaign Fit = 30 Audience / 30 Style / 25 Personality / 15 Comm.Style |
| `CMP_README` | sub-bobot berbeda untuk komponen yang sama — Brand&Business = Category 60 / Keyword 25 / Hashtag 15; menyatakan dirinya **"supersedes section 4"** |

Tidak satu pun dari ketiganya menghasilkan 4 aspek Brand Fit.

---

## 3. Kondisi keempat aspek — angka dari DB hari ini

### A. Category Matching — sumber kreator SIAP, sisi brand KOSONG

| Bukti | Angka |
|---|---|
| `public.kol_directory` | **7.432** baris, seluruhnya `directory_status` = `active` |
| punya `category_ids` tidak kosong | **4.002** (53,9%) |
| di antaranya punya ≥1 `taxonomy_key` | **3.983** |
| hanya punya kategori ber-`taxonomy_key` NULL | **19** |
| `public.kol_categories` | **28** baris · 9 `taxonomy_key` unik · **6 kategori ber-`taxonomy_key` NULL** |
| `public.brand` | **0 baris** |
| constraint di `public.brand` | hanya `brand_pkey` + `fk_brand_agency`. **Tidak ada CHECK, tidak ada FK pada `category`** |

Matriks relevansi **11d** (`CMP_Lookup_Lists` baris 346–356) memang ada dan
lengkap: 9×9, tangga 100/80/60/40/20, kedua sumbunya nilai
`kol_categories.taxonomy_key` yang nyata. Ini satu-satunya dari 9 matriks yang
sumbunya bisa diisi dari DB hari ini.

**Tetap tidak bisa diimplementasikan**, karena empat hal:

1. **Sisi brand nol.** `public.brand` = 0 baris. Tidak ada satu pun nilai
   `brand.category` untuk dimasukkan ke sumbu baris matriks.
2. **Kosakata `brand.category` tidak terjamin.** Kolomnya `varchar` tanpa CHECK
   dan tanpa FK ke `kol_categories`. Workbook mengasumsikan isinya sebuah
   `taxonomy_key`, tapi tidak ada apa pun di DB yang menegakkan itu — dan dengan
   0 baris, asumsinya tidak bisa diuji.
3. **Kreator multi-kategori tidak punya aturan agregasi.** `category_ids` adalah
   `uuid[]`: **1.110** kreator punya 2 kategori, **28** punya 3, **1** punya 5 —
   total **1.139 dari 4.002 (28,5%)** membawa ≥2 `taxonomy_key`. Matriks 11d
   memetakan satu-lawan-satu. Ambil yang tertinggi? rata-rata? kategori primer?
   **Workbook tidak menyebutkannya.** Ini ambiguity yang nyata, bukan detail
   implementasi.
4. **19 kreator jatuh di luar matriks** karena seluruh kategorinya
   ber-`taxonomy_key` NULL (Animal Lovers, Automotive and motorsports, Business
   and entrepreneurship, Environmental, dst). Perlakuannya tidak didefinisikan —
   dan aturan missing-data workbook (audit §6.2) membedakan **tiga** kasus
   berbeda, jadi menebak salah satunya berisiko.

Selain itu matriks 11d menggerakkan `W_BB_CAT` — sub-skor **Brand Match**, bukan
sub-skor Brand Fit. Memakainya untuk aspek "Category matching" milik Brand Fit
kembali ke keputusan Product di §2.

**Status aspek A: NOT COMPUTABLE hari ini** (sumber kreator siap, sisi brand nol,
aturan agregasi tidak ada).

### B. Audience Overlap — TIDAK ADA SUMBER

Pencarian kolom bernama `%overlap%` di seluruh DB (7 schema) mengembalikan
**tepat 2 kolom, dan keduanya adalah kolom tujuan, bukan sumber**:
`feature.brand_fit_analysis.audience_overlap_pct` dan `.overlap_summary`.

Audiens sisi kreator memang ada, tapi tipis:

| Tabel | Baris |
|---|---:|
| `l2_gold.audience_interest_daily` | 229 (**27 akun** dari 7.432) |
| `l2_gold.audience_geo_daily` | 196 |
| `l2_gold.audience_demographics_daily` | 113 |
| `l1_silver.unified_audience` | **0** |

Audiens sisi **brand** tidak ada sama sekali. `public.brand` punya 11 kolom —
`id`, `agency_id`, `name`, `category`, `logo_url`, `is_competitor_tracked`,
`is_active`, `brand_keywords`, `brand_hashtags`, `created_at`, `updated_at` —
**nol kolom audiens**, dan 0 baris.

Overlap butuh dua himpunan audiens. Yang tersedia satu pun tidak lengkap.
Sesuai instruksi, `followers_count` **tidak** dipakai sebagai pengganti: jumlah
follower bukan irisan audiens.

**Status aspek B: HOLD / NULL.**

### C. Values Alignment — TIDAK ADA SUMBER, DI KEDUA SISI

Pencarian kolom ber-nama `value|align|ethos|principle` di seluruh DB, semua
schema kecuali katalog sistem, mengembalikan **4 kolom, nol di antaranya relevan**:

| Kolom | Kenapa tidak relevan |
|---|---|
| `l0_harmonization.instagram_audience.value` | nilai metrik audiens generik (pasangan key/value) |
| `l1_silver.unified_audience.value` | idem — dan tabelnya 0 baris |
| `public.campaign_targets.current_value` | target numerik campaign |
| `public.campaign_targets.target_value` | idem |

Brand values: tidak ada kolom. Creator values: tidak ada kolom. Taxonomy values:
tidak ada — `public.kol_attribute` (40 baris, migrasi 045) berisi
`content_style` 11 / `communication_style` 9 / `creator_personality` 13 /
`visual_style` 7, dan **tidak ada grup `values`**.

`brand_match_master.xlsx` menamai `brand_values`, `preferred_creator_values`, dan
sub-bobot `W_BP_VALUES` 25 — tapi ketiganya bertanda **NO MATCH**: field-nya ada
di spesifikasi, kolomnya tidak ada di mana pun.

Sesuai instruksi, **tidak dibuat proxy** dari category, personality, style,
maupun keyword.

**Status aspek C: NOT COMPUTABLE / NULL.**

### D. Past Performance — TIDAK ADA DATA CAMPAIGN

Seluruh rantai campaign → KOL → performance kosong:

| Tabel | Baris |
|---|---:|
| `public.campaigns` | **0** |
| `public.campaign_kols` | **0** |
| `public.campaign_kol_deliverables` | **0** |
| `public.campaign_content_performance` | **0** |

Strukturnya lengkap dan relasinya benar — modul CPE/CPV yang sudah selesai
memakai rantai yang sama — tapi tidak ada satu baris pun untuk diukur.

**Status aspek D: NOT COMPUTABLE / NULL.**

---

## 4. `partnership_score` — tetap HOLD

`feature.brand_fit_analysis` = **0 baris**.

Bobot antar-aspek tidak ditemukan di mana pun. Yang **tidak** dilakukan, sesuai
instruksi:

- tidak memakai equal weighting 25/25/25/25
- tidak membuat weighted average sendiri
- tidak memakai CPE/CPV sebagai proxy
- tidak memakai `followers_count` sebagai pengganti audience overlap
- tidak memakai Style/Personality sebagai pengganti Values Alignment
- tidak mengubah NULL menjadi 0 agar skor bisa keluar

Poin terakhir punya dasar tertulis di workbook sendiri (`CMP_README`, dikutip di
audit §6.2):

> "0 adalah pengukuran. Memakainya untuk 'tidak ada yang mengukur' akan
> menempatkan kreator tak terukur di bawah kreator yang buruk."

Workbook memang punya mekanisme partial scoring — kolom `*_Available` per
komponen plus `Available Weight`, di mana input yang hilang keluar dari rata-rata
tertimbang dan bobotnya direnormalisasi. Tapi mekanisme itu milik **Brand Match**
dan mengasumsikan sebagian besar komponennya tersedia. Di sini **tiga dari empat
aspek tidak punya sumber sama sekali**, dan yang keempat kosong di sisi brand.
Merenormalisasi bobot ke nol aspek yang bisa dihitung bukan partial scoring —
itu skor kosong dengan angka di depannya.

---

## 5. Pencarian yang dilakukan — supaya tidak diulang

| Tempat dicari | Hasil |
|---|---|
| Source code (`*.py`) | 3 hit, seluruhnya **guard larangan**: `tests/test_calculated_metrics.py:372` (`terlarang = (…,"partnership_score",…)`), `:400` `test_db_brand_fit_masih_kosong`, `docs/build_filter_doc.py:387` |
| `migrations/014_merge_brand_fit_analysis.sql` | Mendefinisikan **struktur + COMMENT**, eksplisit tidak memindahkan data. Nol formula |
| `migrations/FEATURE_METRICS_BACKLOG.md` §6 | "**BLOCKED** — LOGIC belum didefinisikan" |
| `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md` §16.8 | "Seluruh 6 kolom metrik BLOCKED" · baris 865: Formula "**belum ada**", Status "**NEED DEFINITION**" |
| `docs/BACKEND_PLAN.md` :692, :788 | "Belum pernah dibangun" |
| `docs/KOL_DISCOVERY_FINAL_FILTER_AUDIT.md` :76 | filter #21 Min brand fit — "⛔ disabled", "BLOCKED", "0 baris" |
| `docs/PIPELINE_STATUS.md` :86 | "Tabel ada, isi 0" |
| `brand_match_master.xlsx` (38 sheet) | Formula lengkap — tapi untuk **Brand Match**, dengan 6 komponen, dan **tiga versi bobot yang bertabrakan** (§2.1) |
| UI `app/Autometric-KOL-Module.html:1241` | Keempat aspek muncul dengan angka **hardcoded 95 / 78 / 88 / 90** terhadap brand fiktif "Acme Sportswear". **Mock, bukan formula** |
| Git history | Nol commit yang mendefinisikan formula brand fit |

Baris 1241 pada UI itu penting: ia satu-satunya tempat keempat aspek muncul
bersama angka. Angkanya konstanta yang ditulis tangan di dalam template render,
bukan hasil hitung — jadi ia menetapkan **nama dan urutan keempat aspek**, bukan
cara menghitungnya.

---

## 6. Blocker — yang benar-benar masih ada

| # | Blocker | Sifat | Yang membuka |
|---|---|---|---|
| **B1** | Formula `partnership_score` + bobot antar-4-aspek tidak ada | **Keputusan bisnis** | Mentor/Product menuliskan bobotnya |
| **B2** | Belum diputuskan apakah Brand Fit = Brand Match | **Keputusan Product** | Kalau ya, masih tersisa memilih 1 dari 3 bobot yang bertabrakan (§2.1) dan memetakan 6 komponen → 4 aspek |
| **B3** | `public.brand` = 0 baris | **Data** | Onboarding brand. FK `fk_brand_fit_analysis_brand` membuat **nol baris** brand fit bisa ditulis selama brand nol |
| **B4** | Values Alignment nol sumber di kedua sisi | **Data + keputusan** | Perlu vocabulary values + kolom brand + kolom kreator. Tidak boleh di-proxy |
| **B5** | Audience Overlap nol sumber sisi brand; sisi kreator 27/7.432 akun | **Data** | Definisi audiens brand + Insights OAuth (0 dari 7.208 akun terhubung) |
| **B6** | Seluruh 4 tabel campaign 0 baris | **Data** | Campaign nyata berjalan |
| **B7** | Kreator multi-kategori tidak punya aturan agregasi (1.139 / 4.002 = 28,5%) | **Keputusan bisnis** | Tetapkan: max / mean / kategori primer |
| **B8** | 6 dari 28 `kol_categories` ber-`taxonomy_key` NULL; 19 kreator jatuh di luar matriks 11d | **Data + keputusan** | Isi `taxonomy_key`, atau tetapkan perlakuan di luar matriks |
| **B9** | `brand.category` tanpa CHECK/FK, kosakatanya tidak terjamin `taxonomy_key` | **Struktur** | Sepakati kosakata sebelum brand pertama masuk |

B1 dan B2 adalah blocker sesungguhnya. B3–B6 hilang sendiri begitu data masuk.
B7–B9 kecil tapi harus dijawab sebelum baris pertama ditulis.

---

## 7. Yang TIDAK dilakukan

- Tidak ada formula baru
- Tidak ada schema/kolom/tabel/migration baru
- Tidak ada perubahan `kol_categories`, taxonomy, atau source of truth
- Tidak ada person table
- Tidak ada perubahan pada CPE/CPV
- Tidak menyentuh EMV, Rate Card, What Matters, Style & Personality, ER,
  Content Quality, Brand Safety
- Tidak ada integrasi JS/Next.js
- Tidak ada fake implementation demi test
- Tidak ada commit/push

Full test suite dijalankan untuk memastikan nol regresi: **1202 passed**.
