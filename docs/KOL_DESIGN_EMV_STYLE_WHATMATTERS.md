# DESAIN PRAKTIS — EMV/CPE/CPV · Style & Personality · What Matters Most

**Lanjutan dari** `KOL_EXCEL_DB_MATCHING_AUDIT.md` → `KOL_DB_VERIFICATION_TAHAP0.md`.
**Tanggal:** 13 September 2026 · **DB:** `kol` @ `10.100.14.216` · sesi
`transaction_read_only = on`.

**Sifat dokumen ini: DESAIN SAJA.** Nol `INSERT/UPDATE/DELETE`, nol
`CREATE/ALTER/DROP`, nol migration, nol perubahan DB. Seluruh query tambahan di
sesi ini hanya `SELECT` untuk memastikan kolom yang dipakai desain memang ada.

> ## ⚠️ REVISI — lihat `KOL_HOLD_RESOLUTION.md`
>
> Dokumen itu menutup sebagian HOLD di sini dan **mengoreksi dua hal**:
>
> 1. **Frontend TERNYATA ADA di repo** — `app/AUTOME_2.html` (883 KB) dan
>    `app/Autometric-KOL-Module.html` (689 KB). §3.1 di bawah menyatakan
>    "tidak ada di repo ini" — **itu salah**, gue melewatkan direktori `app/`.
>    Akibatnya: fungsi "What Matters Most" sekarang **terarah kuat ke
>    preference** ("tell us what matters" = picker kriteria Smart Discovery),
>    dan rekomendasinya berubah dari "master 7 baris" menjadi **nol tabel**.
> 2. **216 handle lintas-platform, bukan 439** (§2.5 dan §5.4 di bawah).
>
> Perubahan lain yang dibawa dokumen itu:
> - **CPV & CPM memang requirement UI** (slider `cpvMax`, `cpmMax`) — §2.3 di
>   bawah sempat meragukannya.
> - **Konflik baru**: UI mendefinisikan CPV **per 1.000 views**, Excel per
>   **1 view** → beda 1.000×. Dan CPM: UI berbasis `reach`, Excel berbasis
>   `followers`.
> - **CPE bukan konflik** untuk grain campaign — UI hanya membaca `k.cpe`.
> - Rekomendasi "jangan bikin kolom EMV/CPE/CPV" **bukan lagi pendapat** —
>   sudah ditegakkan test guard di `tests/test_calculated_metrics.py:372`.
> - Kunci mapping Style/Personality **terjawab**: `kol_directory.id`, karena
>   `kol_social_account.kol_id` ternyata ber-FK ke `kol_directory(id)` dan
>   kardinalitasnya 1:1 — **tidak ada entity "orang" di DB**.

---

## 0. TIGA KOLOM BARU YANG DITEMUKAN SESI INI

Sebelum masuk desain — tiga hal ini belum tercatat di TAHAP 0 dan langsung
mengubah jawaban soal biaya:

| Tabel | Kolom | Kenapa penting |
|---|---|---|
| `campaign_kol_deliverables` | `unit_price`, `subtotal`, `quantity`, `rate_card_id`, `rate_card_platform`, **`rate_card_snapshot` jsonb** | **Rate card sudah punya jalur masuk** — di-snapshot per deliverable saat order. Jadi biaya campaign **tidak menunggu `l1_silver.unified_rate_card` terisi** |
| `campaign_orders` | `subtotal`, `platform_fee_pct`, `platform_fee_amount`, `tax_pct`, `tax_amount`, `discount_amount`, `total_amount`, `currency` | Ada **tiga level biaya** (net kreator → subtotal → total brand). "Biaya" di CPE/CPV jadi ambigu dan itu keputusan bisnis |
| `campaign_targets` | `metric_type`, `target_value`, `current_value`, `achievement_pct`, `unit`, `is_primary`, `campaign_kol_id` | Wadah metrik generik per campaign(-KOL) yang sudah ada. Relevan untuk bagian 3 |

Fakta struktural lain yang dipakai desain ini:

- **Tidak ada satu pun enum di DB**, dan CHECK constraint hanya 4 buah —
  semuanya di `l2_gold.kol_profile_card` (migration 042–044).
- **Tidak ada view di DB** (0 view di 7 schema).
- **Tidak ada tabel preference/criteria/weight** apa pun.
- Index hanya PK. Di 7.432 baris, seq scan murah — jadi pilihan struktur di
  bawah tidak ditentukan oleh performa.
- `kol_directory` bergrain **(platform, akun)**: 7.432 baris tapi hanya 6.993
  handle unik → **439 handle punya baris di dua platform**.
- `agency_kol_accounts` hari ini **1:1** dengan `kol_directory` (1 agency,
  7.431 baris, 7.431 `kol_account_id` unik) dan sudah memegang atribut kurasi:
  `category_id → kol_categories`, `tier_id → kol_tiers`, `label`,
  `campaign_tag`, `notes`.

---

# BAGIAN 1 — EMV / CPE / CPV

## 1.1 Temuan pokok: ini BUKAN satu metrik, tapi DUA metrik berbeda grain

Ini yang paling penting dan yang membuat desainnya jadi sederhana:

| | **Versi DISCOVERY (estimasi)** | **Versi CAMPAIGN (aktual)** |
|---|---|---|
| Pertanyaan | "kalau pakai KOL ini, kira-kira berapa biaya per engagement?" | "campaign yang sudah jalan ini, biaya per engagement-nya berapa?" |
| Grain | per KOL (akun) | per campaign × KOL |
| Sumber biaya | rate card | `deal_price` / `subtotal` / `total_amount` |
| Sumber hasil | rata-rata views/ER historis | `total_engagement`, `views`, `reach` aktual |
| Rumah kolom | `feature.ig/tt_audience_analysis.cpe`, `.emv` | `campaign_kols.emv`, `campaign_content_performance.emv` |
| Dipakai untuk | filter & ranking di Discovery | laporan hasil campaign |
| **Kesiapan** | **BLOCKED** — `unified_rate_card` 0 baris | **SIAP STRUKTURNYA** — semua kolom ada, tinggal ada barisnya |

Excel memodelkan **versi Discovery**. DB punya rumah untuk **keduanya**.
Konflik formula Excel-vs-DB yang gue catat di audit lama (H5) ternyata **bukan
konflik** — keduanya benar untuk grain masing-masing. Yang perlu diputuskan
hanya rumus versi Discovery.

## 1.2 EMV

### Input EMV dari Excel

**Excel tidak pernah mendefinisikan EMV.** Tiga kemunculan, nol definisi:

| Lokasi | Teks |
|---|---|
| `brand_style_personality` → DB vs Hardcode | "Can support brand-level EMV/CPV" |
| `brand_match_master` → Discovery_Filters r42 | Estimated ROI, sumber: "EMV ÷ rate" |
| `brand_match_master` → CMP_Hard_vs_Soft_Filter r54 | "not measurable on this roster — EMV ÷ rate (0%)" |

Yang **ada** definisinya di Excel adalah **`Estimated ROI`**, dan di dalamnya
tersembunyi satu kandidat rumus EMV:

```
KOL_Database.AS  Estimated ROI
  = Estimated Reach × ER% ÷ 100 × CAL_VALUE_PER_ENG ÷ Rate Card
                     └────────── ini "earned value" ──────────┘
  CAL_VALUE_PER_ENG = 9.000 IDR   (Lookup_Lists D146)
  Estimated Reach   = Avg Views × 1,15 + Followers × 0,12   (D147, D148)
```

Jadi **kandidat A (dari Excel, tersirat):**
`EMV = jumlah_engagement × 9.000 IDR`

Dan **kandidat B (dari DB, tertulis di `FEATURE_METRICS_BACKLOG`):**
`EMV = reach × CPM ÷ 1000 × multiplier`

**Gue tidak memilih.** Tapi ada satu fakta desain yang menentukan biayanya:

| | Kandidat A (value-per-engagement) | Kandidat B (CPM) |
|---|---|---|
| Input | `total_engagement` + konstanta 9.000 | `reach` + konstanta CPM + `multiplier` |
| Kolom input tersedia di DB? | **`campaign_kols.total_engagement` ADA** · `campaign_content_performance.total_engagement` ADA | `reach` ADA (2 tabel) · **CPM TIDAK ADA** · **multiplier TIDAK ADA** |
| Konstanta ada di DB? | tidak (tapi cuma 1 angka, dan Excel menyebut 9.000) | tidak (2 angka, tidak disebut di mana pun) |
| Bisa dihitung begitu campaign jalan? | **Ya** | **Tidak** — `reach` 0 terisi dari 503 post, dan butuh Insights API |

Kandidat A bisa dihitung hari ini dari kolom yang sudah ada. Kandidat B butuh
`reach` (butuh Insights API) **plus** dua konstanta yang tidak ada di Excel
maupun DB. Itu bukan alasan untuk memilih A — itu alasan untuk **menanyakan
mana yang dimaksud Product sebelum satu baris pun ditulis.**

### `campaign_kols.emv` sebaiknya dihitung dari apa

| Kalau Product memilih | Sumber | Ekspresi |
|---|---|---|
| **Kandidat A** | `campaign_kols.total_engagement` | `total_engagement × <value_per_engagement>` |
| **Kandidat B** | `campaign_kols.reach` | `reach ÷ 1000 × <cpm> × <multiplier>` |

Keduanya memakai kolom yang **sudah ada di baris yang sama**. Tidak perlu join,
tidak perlu kolom baru, tidak perlu tabel baru.

### Apakah `campaign_content_performance.emv` dihitung terpisah?

**Ya — terpisah, dan `campaign_kols.emv` adalah agregat dari sana.** Alasannya
ada di strukturnya sendiri:

- `campaign_content_performance` bergrain **per deliverable per `snapshot_date`**
  dan punya `delta_views` / `delta_engagement` / `is_final` → ia **time-series**.
- `campaign_kols` bergrain **per campaign × KOL** → ia ringkasan.

Jadi arah alirannya:

```
campaign_content_performance (per deliverable, per snapshot)
   emv dihitung per baris dari reach/total_engagement baris itu
        │
        │  agregasi: SUM atas baris is_final = true per campaign_kol
        ▼
campaign_kols.emv  (ringkasan per KOL dalam campaign itu)
```

Menghitung `campaign_kols.emv` secara independen (bukan dari agregat) akan
membuat dua kolom yang bisa saling membantah — persis masalah yang sudah
didokumentasikan untuk `active_hours_heatmap` vs `best_posting_time_heatmap`.

⚠️ Satu hal yang **harus** diputuskan kalau agregasi dipakai: `snapshot_date`
artinya satu deliverable punya banyak baris. Menjumlahkan seluruh baris akan
**menghitung ganda**. Harus jelas: pakai `is_final = true` saja, atau baris
`snapshot_date` terakhir per deliverable, atau `delta_*`. Ini keputusan
Product/BE, bukan gue.

### Yang masih kurang untuk formula EMV

| # | Kurang | Kenapa memblokir |
|---|---|---|
| 1 | **Definisi resmi** — kandidat A atau B | Tanpa ini, angka apa pun tidak bisa dipertanggungjawabkan |
| 2 | Kalau A: nilai `value_per_engagement` | Excel menyebut 9.000 IDR, tapi **tanpa sumber**. Apakah ini angka bisnis atau tebakan penulis workbook? |
| 3 | Kalau B: konstanta **CPM** | Tidak ada di Excel, tidak ada di DB (sapuan 101 tabel: 0 kolom) |
| 4 | Kalau B: nilai **multiplier** | Idem — tidak pernah dinyatakan di mana pun |
| 5 | Kalau B: **`reach`** | 0 terisi dari 503 post; butuh Insights API (metrik pemilik akun) |
| 6 | Aturan agregasi `snapshot_date` → `campaign_kols` | Supaya tidak double-count |
| 7 | Apakah EMV per platform berbeda | `campaign_kol_deliverables.platform_id` ada; Excel tidak membedakan |

**Kesimpulan EMV: nol kolom baru, nol tabel baru. Yang kurang definisi, bukan
struktur.**

## 1.3 CPE

### Input dari Excel

```
KOL_Database.AP  CPE
  = Rate Card (IDR) ÷ (Average Views × ER% ÷ 100)
  Guard: kalau Rate Card / Avg Views / ER kosong atau 0 → "" (bukan 0)
  Pembulatan: 0 desimal
```

Penyebutnya **engagement hasil estimasi** (`views × ER`), bukan engagement
terukur — karena di Discovery belum ada campaign, jadi belum ada engagement
nyata.

Pembanding dari DB (`FEATURE_METRICS_BACKLOG` via E1):
`feature.*_audience_analysis.cpe = unified_rate_card.fee ÷ total_engagement`
→ engagement **nyata**.

**Ini bukan konflik** — Excel bicara Discovery (estimasi), DB bicara pasca-post
(aktual). Keduanya sah di grain masing-masing.

### Biaya ambil dari mana?

Ada **empat** kandidat, dan pilihannya mengubah arti angkanya:

| Kandidat | Kolom | Artinya | Cocok untuk |
|---|---|---|---|
| 1 | `campaign_kols.deal_price` | harga nego bersih ke kreator, per KOL | **CPE per campaign × KOL** ✅ |
| 2 | `campaign_kol_deliverables.unit_price × quantity` = `subtotal` | harga per deliverable | CPE per deliverable/konten |
| 3 | `campaign_orders.subtotal` | total sebelum fee & pajak | CPE level order |
| 4 | `campaign_orders.total_amount` | **termasuk** `platform_fee_amount` + `tax_amount` − `discount_amount` | CPE "biaya sebenarnya untuk brand" |
| 5 | `campaign_kol_deliverables.rate_card_snapshot` (jsonb) | harga rate card saat order | versi Discovery, **tanpa menunggu `unified_rate_card`** |

**Rekomendasi gue: kandidat 1 (`deal_price`) untuk CPE per campaign × KOL** —
karena grain-nya sama dengan tempat hasilnya disimpan, jadi tidak perlu join
dan tidak bisa salah alokasi.

**Tapi kandidat 1 vs 4 adalah keputusan bisnis**, bukan teknis: "biaya" yang
dilaporkan ke brand biasanya termasuk fee dan pajak. Gue tidak memilih.

### Engagement yang dipakai Excel apa?

Excel: `Average Views × ER% ÷ 100` — **engagement yang diestimasi dari views**,
bukan jumlah like+comment nyata. Perlu dicatat bahwa Excel memakai
`Average Views` sebagai basis, bukan followers.

### Apakah `campaign_kols.total_engagement` sudah cukup?

**Untuk CPE versi campaign: ya, cukup — dan lebih baik daripada rumus Excel.**

| | Excel | `campaign_kols.total_engagement` |
|---|---|---|
| Sifat | estimasi (`views × ER`) | **terukur** |
| Tipe | turunan 2 kolom | `bigint`, satu kolom |
| Butuh join? | ya (views + ER) | tidak |

Satu hal yang harus dipastikan: **definisi `total_engagement` itu apa.**
Tabelnya 0 baris jadi tidak bisa gue periksa dari data. Apakah
`likes + comments`? Ditambah `shares + saves`? `taksonomi_kol` memakai
`likes + comments + shares`, sedangkan `kol_directory.engagement_rate` dihitung
`AVG(likes + comments)` **tanpa shares**. Inkonsistensi ini (H4 di audit lama)
**tetap terbuka** dan sekarang menyentuh `total_engagement` juga.

### Formula final yang bisa dipastikan dari Excel

Hanya satu, dan hanya untuk versi Discovery:

```
CPE_discovery = Rate Card ÷ (Average Views × ER% ÷ 100)
```

Untuk versi campaign, **Excel tidak punya rumusnya** karena Excel tidak punya
konsep campaign yang sudah jalan. Yang bisa dipastikan dari struktur DB:

```
CPE_campaign = <biaya> ÷ campaign_kols.total_engagement
```

dengan `<biaya>` masih menunggu keputusan (kandidat 1–4 di atas).

## 1.4 CPV

### Input dari Excel

```
KOL_Database.AO  CPV
  = Rate Card (IDR) ÷ Average Views
  Guard: Rate Card atau Avg Views kosong/0 → ""
  Pembulatan: 2 desimal
```

Rumus paling sederhana dari ketiganya, dan **satu-satunya yang tidak punya
pembanding yang berbeda di DB** — tidak ada kolom `cpv` sama sekali, jadi tidak
ada definisi DB yang bisa bertabrakan.

### Biaya ambil dari mana

Sama dengan CPE — `campaign_kols.deal_price` untuk versi campaign,
`rate_card_snapshot` / `unified_rate_card.fee` untuk versi Discovery.

### Views ambil dari tabel mana

Di sini ada perbedaan penting dari CPE: **`campaign_kols` tidak punya kolom
`views`.** Yang ada:

| Tabel | Kolom views | Grain |
|---|---|---|
| `campaign_content_performance` | **`views`** bigint | per deliverable per snapshot |
| `l2_gold.post_metric` | `views` (397 dari 503 terisi) | per post |
| `feature.*_engagement_analysis` | `avg_views`, `median_views` (30 terisi) | per akun |
| `l1_silver.unified_post` | `views` (397 dari 503) | per post |

Jadi **CPV per campaign × KOL wajib agregasi dari
`campaign_content_performance`**, tidak bisa dibaca dari satu baris seperti CPE.
Ini asimetri yang perlu diketahui sebelum bikin query.

### Formula CPV yang sesuai Excel

```
CPV_discovery = Rate Card ÷ Average Views
CPV_campaign  = <biaya> ÷ SUM(campaign_content_performance.views)
                          [agregat per campaign_kol, aturan snapshot menyusul]
```

### Perlu kolom baru atau cukup calculated?

**Cukup calculated. Jangan tambah kolom.** Alasannya:

1. CPV = `biaya ÷ views` — pembagian dua kolom yang keduanya sudah ada.
   Menyimpannya berarti harus menjaganya sinkron setiap kali salah satu berubah.
   Pola ini sudah ditolak eksplisit di `KOL_DISCOVERY_FILTER_BACKEND_PLAN.md`
   untuk `next_refresh_at` ("turunan murni; menyimpannya berarti harus
   menjaganya tetap sinkron").
2. `views` di campaign bertambah tiap snapshot → CPV berubah tiap hari. Kolom
   tersimpan akan basi di antara dua job.
3. Di 7.432 KOL / 0 baris campaign, biaya hitung on-the-fly nol.

**Pengecualian:** `emv` **sudah** punya kolom di 4 tempat. Jadi untuk EMV,
polanya sudah ditetapkan (disimpan), sedangkan CPV/CPE/CPM belum punya kolom
sama sekali di grain campaign — dan sebaiknya tetap begitu.

## 1.5 Keputusan struktur: `Excel input → DB source → calculation → output`

### EMV

| | Versi Discovery (per KOL) | Versi Campaign (per campaign × KOL) |
|---|---|---|
| **Excel input** | *tidak ada definisi*; tersirat `engagement × CAL_VALUE_PER_ENG (9.000)` | *tidak ada* — Excel tidak punya konsep campaign aktual |
| **DB source** | `feature.ig/tt_audience_analysis.emv` (kolom ADA, 0 terisi) · input `avg_reach` 0 terisi | `campaign_kols.emv` & `campaign_content_performance.emv` (kolom ADA, 0 baris) · input `total_engagement` / `reach` ADA |
| **Calculation** | **HOLD** — tunggu definisi | per-baris di `campaign_content_performance`, lalu **SUM → `campaign_kols.emv`** |
| **Output** | kolom existing | kolom existing |
| **Kolom baru** | **TIDAK** | **TIDAK** |

### CPE

| | Versi Discovery | Versi Campaign |
|---|---|---|
| **Excel input** | `Rate Card ÷ (Average Views × ER% ÷ 100)` — pasti, dari `KOL_Database.AP` | — |
| **DB source** | `feature.*_audience_analysis.cpe` (kolom ADA, 0 terisi) · butuh `unified_rate_card.fee` (**0 baris**) atau `rate_card_snapshot` | biaya: `campaign_kols.deal_price` · engagement: `campaign_kols.total_engagement` |
| **Calculation** | `fee ÷ (avg_views × er_pct ÷ 100)`, guard NULL → NULL bukan 0 | `deal_price ÷ total_engagement` |
| **Output** | kolom existing `cpe` | **calculated di query/API** |
| **Kolom baru** | **TIDAK** | **TIDAK** |

### CPV

| | Versi Discovery | Versi Campaign |
|---|---|---|
| **Excel input** | `Rate Card ÷ Average Views` — pasti, dari `KOL_Database.AO` | — |
| **DB source** | `feature.*_engagement_analysis.avg_views` (30 terisi) + rate card (**0 baris**) | biaya `deal_price` + `SUM(campaign_content_performance.views)` |
| **Calculation** | `fee ÷ avg_views` | `deal_price ÷ SUM(views)` |
| **Output** | **calculated** — tidak ada kolom `cpv` di DB dan tidak perlu | **calculated** |
| **Kolom baru** | **TIDAK** | **TIDAK** |

### Jawaban atas pertanyaan inti

> **Apakah EMV/CPE/CPV perlu tabel/kolom baru?**

**TIDAK. Nol tabel baru, nol kolom baru.**

| Metrik | Kenapa tidak perlu |
|---|---|
| EMV | Kolomnya **sudah ada di 4 tempat**, di 2 grain yang tepat. Yang hilang definisi, bukan tempat |
| CPE | Kolom `cpe` sudah ada di grain Discovery. Di grain campaign, cukup `deal_price ÷ total_engagement` — dua kolom, satu baris, tanpa join |
| CPV | Turunan murni dua kolom. Menyimpannya menciptakan kewajiban sinkronisasi tanpa manfaat |

Satu-satunya hal opsional yang mungkin berguna nanti: **satu VIEW** yang
menyajikan `cpe_campaign` / `cpv_campaign` / `cpm_campaign` supaya API dan
laporan tidak menulis ulang pembagiannya. Tapi DB ini **belum punya satu view
pun** — jadi memperkenalkan view pertama adalah keputusan konvensi tim, bukan
sesuatu yang gue putuskan sendiri. Sampai itu disepakati, hitung di query/API.

---

# BAGIAN 2 — STYLE & PERSONALITY

## 2.1 Isi Excel — dibaca ulang, seluruh 6 sheet

### Daftar Style — sheet `Style List`

Header: `Group` · `Style` · `Count in DB` · `Source`. **Tidak ada kolom ID/key.**
18 baris, 2 grup, **16 nilai unik**.

| Grup | Jml | Nilai |
|---|---:|---|
| **Content Style** | 10 | Educational · Tutorial · Review · Storytelling · Aesthetic · Entertaining · Vlog · Demo · Talking Head · Comedy |
| **Communication Style** | 8 | Educational · Storytelling · Demonstrative · Conversational · Data-driven · Visual-first · Humorous · Testimonial |

### Daftar Personality — sheet `Personality List`

Header: `Group` · `Personality` · `Count in DB` · `Source`. **Tidak ada ID/key.**
30 baris, 3 grup, **26 nilai unik**.

| Grup | Jml | Nilai |
|---|---:|---|
| **Creator Personality** | 12 | Professional · Educational · Creative · Tech-savvy · Reviewer · Relatable · Casual · Premium · Luxury · Entertaining · Humorous · Inspirational |
| **Brand Personality** | 10 | Professional · Innovative · Friendly · Premium · Playful · Educational · Authentic · Bold · Caring · Modern |
| **Brand Tone** | 8 | Formal · Informative · Warm · Aspirational · Playful · Inspiring · Straightforward · Conversational |

`Count in DB` = **0** untuk seluruh 48 baris. `Source` = `scripts/brand-match/vocabulary.mjs`
(repo aplikasi, bukan repo ini).

### Sheet lain

| Sheet | Isi | Relevansi ke desain |
|---|---|---|
| `Summary` | "Style: 10 Content + 8 Communication · hardcoded, not in DB" | Konfirmasi, bukan struktur |
| `Brand List` | 38 brand dari `tsdb` | **Tidak relevan** untuk Style/Personality |
| `DB vs Hardcode` | "Needs creator/brand assignment" | Menegaskan: ini data kurasi, bukan metrik |
| `Anomalies` | cacat `tsdb` | Tidak relevan |

## 2.2 Tiga temuan dari Excel yang menentukan desain

### (1) Label yang sama muncul di grup berbeda dengan arti berbeda

| Label | Muncul di grup |
|---|---|
| `Educational` | Content Style **+** Communication Style **+** Creator Personality **+** Brand Personality |
| `Storytelling` | Content Style **+** Communication Style |
| `Professional` | Creator Personality **+** Brand Personality |
| `Premium` | Creator Personality **+** Brand Personality |
| `Playful` | Brand Personality **+** Brand Tone |
| `Conversational` | Communication Style **+** Brand Tone |
| `Entertaining` | Content Style **+** Creator Personality |
| `Humorous` | Communication Style **+** Creator Personality |

`Educational` sebagai **Content Style** = "bentuk kontennya mengajar".
`Educational` sebagai **Creator Personality** = "kreatornya bertipe pengajar".
Dua pernyataan berbeda tentang objek berbeda.

**Konsekuensi desain: kunci uniknya `(group, name)`, bukan `name`.** Master
dengan 38 nilai unik saja akan menghilangkan perbedaan ini dan **salah**.
Jumlah baris master yang benar = **jumlah baris Excel**, bukan jumlah nilai unik.

### (2) 48 baris Excel terbagi dua: sisi KOL dan sisi BRAND

Ini yang paling sering terlewat:

| Grup | Milik siapa | Baris |
|---|---|---:|
| Content Style | **KOL** | 10 |
| Communication Style | **KOL** | 8 |
| Creator Personality | **KOL** | 12 |
| Brand Personality | **BRAND** | 10 |
| Brand Tone | **BRAND** | 8 |

→ **sisi KOL = 30 baris · sisi BRAND = 18 baris.**

Requirement lo ("1 KOL bisa punya banyak Style dan banyak Personality") menyentuh
**30 baris sisi KOL saja**. 18 baris sisi brand adalah atribut `public.brand`,
dan itu pekerjaan terpisah yang **masih diblokir H2** (`brand` 0 baris, `tsdb`
tidak ada di host ini).

**Rekomendasi: kerjakan sisi KOL sekarang, sisi brand belakangan.** Memasukkan
48 baris ke satu tabel KOL akan menempelkan `Brand Tone` ke kreator — dan itu
salah secara konsep.

### (3) Tidak ada ID/key di Excel

Excel cuma punya label teks. Jadi **kode/ID harus kita tentukan**, dan itu
keputusan yang aman diambil sendiri asal konsisten dengan pola DB.

Pola DB yang sudah ada untuk master kecil:

| Tabel | PK | Kolom pembeda |
|---|---|---|
| `kol_categories` | `id uuid` | `name` + `taxonomy_key text` |
| `kol_tiers` | `id uuid` | `name` + `min_followers`/`max_followers` |
| `platforms` | `id uuid` | `key` + `label` + `icon` |
| `campaign_stages` | `id uuid` | `stage_key` + `label` + `sequence` + `owner_role` |

**Pola rumah: `id uuid` sebagai PK + satu kolom `*_key` slug yang stabil + satu
`label` yang bisa diterjemahkan.** Itu yang gue ikuti.

## 2.3 Adakah master/taxonomy existing yang bisa dipakai?

**Tidak ada yang bisa dipakai untuk Style/Personality.** Sapuan 101 tabel:
`%style%`, `%personality%`, `%persona%`, `%tone%`, `%positioning%`,
`%brand_value%` → **0 tabel, 0 kolom.**

Tapi ada **pola** yang bisa ditiru, dan ini yang membuat desainnya murah:

| Kebutuhan | Preseden di DB | Bentuknya |
|---|---|---|
| Master nilai berkurasi | `kol_categories` (28 baris) | `id uuid` + `name` + key |
| **Banyak nilai per KOL** | **`kol_directory.category_ids uuid[]`** | array uuid, difilter `&&` |
| Satu nilai per KOL berkurasi | `agency_kol_accounts.category_id`, `.tier_id` | uuid FK |
| Provenance/basis | `audience_*_daily.confidence`, `interest_source`, `content_topic_source` | varchar penanda asal |

Jadi DB **sudah punya dua pola untuk many-per-entity**: `uuid[]` (dipakai
`category_ids`) dan FK tunggal (dipakai `category_id`). Yang belum ada: junction
table. Tidak ada satu pun junction many-to-many di seluruh schema `public`.

## 2.4 Perbandingan opsi

### A. Tambah `style` + `personality` ke `l2_gold.kol_profile_card`

| | |
|---|---|
| Bentuk | 2 kolom varchar (atau jsonb) |
| Banyak nilai per KOL? | varchar: **tidak bisa**. jsonb: bisa tapi tanpa referential integrity |
| Filter UI | jsonb butuh operator `@>`; salah tulis nilai tidak terdeteksi |
| Duplikasi | tinggi — label diketik ulang di setiap baris, 1.978× |
| **Vonis** | ❌ **Tolak.** `kol_profile_card` adalah **tabel turunan L2 yang di-regenerate asset Dagster**. Menaruh data kurasi manual di sana berarti data hasil input orang bisa tertimpa job. Ini alasan terkuat menolak opsi A, lebih kuat daripada soal bentuknya |

### B. Satu tabel generic attribute

| | |
|---|---|
| Bentuk | `kol_attribute(id, kind, group, key, label)` + `kol_attribute_map(kol_id, attribute_id, …)` = **2 tabel** |
| Banyak nilai per KOL? | ✅ |
| Filter UI | ✅ satu jalur query untuk style & personality |
| Duplikasi | rendah |
| Risiko | Tabel generic cenderung jadi tempat buangan. `kind` harus dijaga disiplin |
| **Vonis** | ✅ **Kandidat kuat** — 2 tabel, kemampuan sama dengan C |

### C. Master Style + Master Personality + mapping

| | |
|---|---|
| Bentuk | `kol_style` + `kol_personality` + `kol_style_map` + `kol_personality_map` = **4 tabel** |
| Banyak nilai per KOL? | ✅ |
| Filter UI | ✅ tapi dua jalur query terpisah |
| Duplikasi | rendah |
| Kelebihan | Kalau nanti Style butuh kolom yang Personality tidak (mis. pemetaan ke `format_dominant`), tempatnya jelas |
| **Vonis** | ✅ Benar, tapi **4 tabel untuk dua konsep yang bentuknya identik** |

### D. Ikut pola `category_ids`: master + kolom `uuid[]`

| | |
|---|---|
| Bentuk | `kol_style` + `kol_personality` master, lalu `kol_directory.style_ids uuid[]` + `personality_ids uuid[]` |
| Banyak nilai per KOL? | ✅ |
| Filter UI | ✅ `style_ids && ARRAY[...]` — **paling sedikit kode**, dan persis pola `category_ids` yang sudah dipakai |
| Kekurangan | **Array tidak bisa menyimpan atribut per-pasangan** — tidak ada tempat untuk `assigned_by`, `assigned_at`, atau `basis`. Dan `uuid[]` tidak punya FK; nilai yatim tidak terdeteksi DB |
| **Vonis** | ⚠️ Paling ringkas, tapi **kehilangan jejak siapa/kapan** — dan lo bilang ini data yang **kita tentukan manual**, jadi jejak itu justru yang penting |

## 2.5 REKOMENDASI: opsi B (2 tabel), dengan catatan

**Pilih B.** Alasannya, diurutkan dari yang paling menentukan:

1. **Style dan Personality bentuknya identik** — keduanya "(grup, label) yang
   ditempelkan manual ke KOL, boleh lebih dari satu". Tidak ada satu pun kolom
   yang dibutuhkan salah satu tapi tidak yang lain. 4 tabel (opsi C) hanya
   menggandakan DDL dan kode filter tanpa manfaat.
2. **Data kurasi manual butuh jejak.** Opsi D (array) tidak bisa menyimpan
   `assigned_by` / `assigned_at`. Karena ini data yang tim tentukan sendiri —
   bukan hasil hitung — pertanyaan "siapa yang menaruh label ini dan kapan"
   pasti muncul. Junction menjawabnya, array tidak.
3. **Menjauhkan data manual dari tabel yang di-regenerate.** Ini yang membatalkan
   opsi A sepenuhnya.
4. **Label yang sama di grup berbeda tetap terpisah**, karena uniknya
   `(kind, group, key)`.
5. 2 tabel adalah jumlah paling sedikit yang masih memenuhi semua requirement.

**Catatan jujur:** opsi C tidak salah. Kalau mentor lo lebih suka satu master per
konsep — dan itu memang house style DB ini (`kol_categories`, `kol_tiers`,
`platforms`, `campaign_stages` semuanya master terpisah) — C sama-sama benar,
cuma lebih banyak DDL. Perbedaannya selera, bukan kebenaran. Yang **tidak** boleh
dipilih cuma A.

### Bentuk yang diusulkan (deskripsi, BUKAN DDL untuk dijalankan)

**Tabel 1 — master nilai** (usul nama `kol_attribute`):

| Kolom | Tipe | Isi |
|---|---|---|
| `id` | uuid PK | `gen_random_uuid()` — ikut pola `brand`, `campaign_stages` |
| `kind` | varchar | `style` \| `personality` |
| `attribute_group` | varchar | `content_style` \| `communication_style` \| `creator_personality` |
| `attribute_key` | varchar | slug stabil, mis. `content_style.educational` |
| `label` | varchar | label tampil, mis. `Educational` |
| `sort_order` | integer | urutan tampil di UI (ikut pola `campaign_stages.sequence`) |
| `is_active` | boolean | menonaktifkan nilai tanpa menghapusnya (ikut pola `brand.is_active`) |

Unik: `(kind, attribute_group, attribute_key)`. **Isi: 30 baris** (10 + 8 + 12).

**Tabel 2 — mapping KOL ↔ nilai** (usul nama `kol_attribute_map`):

| Kolom | Tipe | Isi |
|---|---|---|
| `id` | uuid PK | |
| `kol_directory_id` | uuid FK → `kol_directory(id)` | KOL-nya |
| `kol_attribute_id` | uuid FK → `kol_attribute(id)` | nilainya |
| `assigned_by` | uuid | siapa yang menaruh (FK → `user`) |
| `assigned_at` | timestamptz | kapan |
| `note` | text | opsional, alasan |

Unik: `(kol_directory_id, kol_attribute_id)` — supaya satu label tidak bisa
ditempel dua kali ke KOL yang sama.

### Contoh data

**`kol_attribute`** — 3 baris dari 30:

| id | kind | attribute_group | attribute_key | label | sort_order | is_active |
|---|---|---|---|---|---:|---|
| `a1…` | `style` | `content_style` | `content_style.educational` | Educational | 1 | true |
| `a2…` | `style` | `communication_style` | `communication_style.educational` | Educational | 1 | true |
| `a3…` | `personality` | `creator_personality` | `creator_personality.reviewer` | Reviewer | 5 | true |

Perhatikan baris 1 dan 2: label sama, **key dan grup beda** — inilah yang
membuat `Educational` sebagai bentuk konten tidak tertukar dengan `Educational`
sebagai gaya komunikasi.

**`kol_attribute_map`** — KOL `@ardidigital` punya 2 style + 1 personality:

| kol_directory_id | kol_attribute_id | assigned_by | assigned_at |
|---|---|---|---|
| `k7…` (@ardidigital) | `a1…` (Content Style / Educational) | `u9…` | 2026-09-15 10:02 |
| `k7…` (@ardidigital) | `a2…` (Communication Style / Educational) | `u9…` | 2026-09-15 10:02 |
| `k7…` (@ardidigital) | `a3…` (Creator Personality / Reviewer) | `u9…` | 2026-09-15 10:03 |

**Filter UI** — "tampilkan KOL ber-Content Style `Educational` ATAU `Review`":

```
SELECT d.* FROM kol_directory d
WHERE EXISTS (
  SELECT 1 FROM kol_attribute_map m
  JOIN kol_attribute a ON a.id = m.kol_attribute_id
  WHERE m.kol_directory_id = d.id
    AND a.attribute_group = 'content_style'
    AND a.attribute_key IN ('content_style.educational','content_style.review')
)
```

Di 7.432 baris tanpa index pun ini murah. Index baru ditinjau kalau populasi
tumbuh jauh — konsisten dengan catatan di
`KOL_DISCOVERY_FILTER_BACKEND_PLAN.md` ("7.720 baris, seq scan murah").

### Satu hal yang harus diputuskan sebelum tabel dibuat

**Kunci mapping: `kol_directory.id` atau `agency_kol_accounts.id`?**

| | `kol_directory.id` | `agency_kol_accounts.id` |
|---|---|---|
| Arti | akun di satu platform | KOL dalam roster satu agency |
| Baris | 7.432 | 7.431 |
| Preseden | `category_ids` ada di sini | `category_id`, `tier_id` ada di sini · **`brand_fit_analysis` pakai ini** |
| Masalah | **439 handle punya baris di 2 platform** → style harus diisi 2× untuk orang yang sama | per-agency → kalau nanti ada agency ke-2, kurasi harus diulang |

Gue **cenderung `kol_directory.id`** karena style/personality adalah sifat akun
yang kontennya kita lihat, dan karena `category_ids` (atribut multi-nilai yang
setara) sudah di sana. Tapi 439 handle lintas-platform itu masalah nyata: kalau
Product menganggap style itu sifat **orang**, bukan **akun**, maka kunci yang
benar bukan keduanya — dan DB belum punya tabel "orang". **Ini keputusan
Product**, dan gue tidak memilih sendiri.

---

# BAGIAN 3 — WHAT MATTERS MOST

## 3.1 Penelusuran UI → frontend → backend → DB

Lo minta gue jangan berhenti di "tidak ditemukan". Jadi gue telusuri sejauh yang
bisa ditelusuri dari sini, dan gue sebutkan terus terang di mana jejaknya putus.

| Lapis | Yang gue periksa | Hasil |
|---|---|---|
| **UI (katalog deliverable)** | `docs/deliv.xlsx` sheet `DELIVERABLES` — 132 baris fitur UI, per-halaman, dengan status DONE/IN PROGRESS | **7 item TIDAK ADA.** Yang ada: "Smart Preset Chips" berisi **8 preset lain** |
| **UI (katalog filter)** | `docs/filter.xlsx`, `docs/mapping filter database.xlsx`, `docs/KOL_DISCOVERY_AUDIT.xlsx` | **7 item TIDAK ADA** |
| **Spec engine** | 51 sheet di 3 Excel — sapuan `what matters`, `Strong Engagement`, `High Reach`, `Consistent Performance`, `Strong Company/Community` | **0 hit untuk kelimanya.** Hanya `Content Quality` dan `Brand Safety` yang ada sebagai nama kolom/komponen |
| **Frontend code** | — | **TIDAK ADA DI REPO INI.** Repo ini Python-only: tidak ada `package.json`, tidak ada `scripts/`, tidak ada `.mjs`, tidak ada `lib/`. Excel merujuk `@/lib/discover/vocab`, `scripts/brand-match/vocabulary.mjs`, dan migrasi **053** — repo ini baru sampai **044** |
| **Backend/API** | — | Idem, di repo aplikasi |
| **DB** | sapuan 101 tabel untuk `criteri`, `prefer`, `weight`, `priorit` | **Tidak ada tabel/kolom preference, criteria, atau weight-config apa pun** |

**Jejaknya putus di batas repo.** Gue tidak bisa membaca komponen UI-nya, jadi
gue **tidak bisa memastikan** fungsi ketujuh item itu. Yang bisa gue lakukan:
menunjukkan struktur apa saja di UI/Excel/DB yang **bentuknya cocok**, dan
membiarkan Product memilih.

### Yang UI sebenarnya punya (dan ini bukan 7 item itu)

`deliv.xlsx` r85 — **8 Smart Preset Chips**:

> Best Performing · High Engagement · Fast Growing · Audience Quality ·
> Brand Fit · Emerging · Campaign Ready · Cost Efficient
> *"Sebagian preset mengubah filter nyata, sebagian hanya mengurutkan ulang hasil."*

Dua item beririsan dengan daftar lo (`High Engagement` ≈ Strong Engagement,
`Audience Quality` ≈ High Audience Quality), enam tidak. Jadi **8 preset ini
bukan 7 "What Matters Most"** — dua daftar berbeda dengan fungsi berbeda.

`deliv.xlsx` r132 juga menyebut **EMV sudah jadi opsi sorting di UI**:
> "Dropdown sorting berdasarkan campaign, brand fit, followers, reach, ER,
> authenticity, **EMV**, posts, dan nama."

Itu memperkuat Bagian 1: UI **sudah** mengharapkan EMV, jadi mengisi
`campaign_kols.emv` punya konsumen nyata.

## 3.2 Dua kemungkinan fungsi — dan kenapa bedanya penting

| | **Tafsir P — Preference** | **Tafsir S — Score per KOL** |
|---|---|---|
| Pertanyaan UI | "Apa yang paling penting **untuk lo**?" — brand memilih | "Seberapa bagus **KOL ini** di 7 aspek?" |
| Siapa yang punya nilainya | brand / campaign | tiap KOL |
| Jumlah baris | 1 set per brand | 7 × 7.432 KOL |
| Efek | mengubah **bobot** ranking | jadi kolom yang di-filter/di-sort |
| Preseden di Excel | **`Brand_Profile.audience_priority`** — dropdown Age/Gender/Location/Interest yang menggeser bobot **+12 / −4** | **`Performance Quality` sub-skor** — 6 sub-skor per KOL |
| Butuh tabel baru? | ya, kecil (preference) | ya, besar (score) — **atau tidak, kalau pakai metrik existing** |

Kalimat "**what matters most when evaluating creators?**" secara gramatikal
adalah pertanyaan kepada **pengguna**, bukan label metrik. Dan Excel sudah punya
mekanisme yang persis begitu — `audience_priority` — yang menggeser 12 poin
bobot ke dimensi yang dipilih dan memotong sepertiga dari tiga lainnya.

Jadi **dugaan gue: tafsir P.** Tapi itu dugaan, bukan temuan — dan gue tidak
mendesain berdasarkan dugaan.

## 3.3 Pemetaan ketujuh item ke metrik yang SUDAH ADA di DB

Yang ini bisa gue pastikan, dan berguna untuk kedua tafsir:

| # | Item | Padanan di Excel | Kolom DB existing | Terisi | Kesiapan |
|---:|---|---|---|---:|---|
| 1 | **Strong Engagement** | `W_PQ_ER` 35% dari Performance | `public.kol_directory.engagement_rate` | **1.736** (23,4%) | ✅ **ADA** — cakupan terbesar dari ketujuhnya |
| 2 | **High Audience Quality** | `W_PQ_AUDIENCE` 20% | `l2_gold.kol_profile_card.audience_quality_score` + `audience_quality_tier` | **27** | ✅ **ADA** (naik status sejak TAHAP 0) |
| 3 | **Consistent Performance** | `W_PQ_CONSISTENCY` 20% | — tidak ada kolom `consistency`. Proksi: `performance_stability` (11) · `post_frequency_reliability` (49) | 11–49 | ⚠️ **PROKSI** — bukan konsep yang sama |
| 4 | **Strong Company/Community** | `W_PQ_COMMUNITY` 10% | **tidak ada apa pun** | 0 | ❌ **KOSONG** |
| 5 | **High Reach** | `W_PQ_VIEWS` 10% (dinormalisasi views/follower) | `reach` = **0 dari 503**. Proksi: `avg_views` (30) · `view_to_follower_ratio` (22) | 0 / 30 | ⚠️ **PROKSI** — `reach ≠ views`, dan itu diperingatkan eksplisit di dokumentasi |
| 6 | **Content Quality** | `KOL_Database.AM`, **bobot 0** | **tidak ada apa pun** | 0 | ❌ **KOSONG** — dan Excel pun tidak pernah memberinya bobot maupun rumus |
| 7 | **Brand Safety** | komponen ke-6, 10% | tidak ada kolom `safety`/`risk`. **Proksi 4-input kini lengkap**: `authenticity_score` (27) + `follower_quality_score` (27) + `verified_status` (931) + `paid_ratio` (48) | 27 | ⚠️ **PROKSI LENGKAP** — tapi ini *integrity screen*, bukan brand safety |

**Rekap: 2 siap · 3 proksi · 2 kosong.**

### Jawaban atas pertanyaan #5 lo

> Apakah "Performance Quality", "Target Audience", "Brand Safety" yang sudah ada
> sebenarnya source dari beberapa item ini?

**Ya — dan bukan sebagian, hampir seluruhnya.** Enam dari tujuh item adalah
sub-skor `Performance Quality` plus komponen `Brand Safety`, dengan nama berbeda:

| Item lo | Sub-skor Excel | Bobot di dalam komponennya |
|---|---|---:|
| Strong Engagement | Engagement Rate | 35% |
| High Audience Quality | Audience Quality | 20% |
| Consistent Performance | Consistency | 20% |
| Strong Company/Community | Community | 10% |
| High Reach | Average Views | 10% |
| *(tidak ada di daftar lo)* | Recent Growth | 5% |
| Brand Safety | — komponen tersendiri | 10% skor akhir |

Jadi `Performance Quality` **sudah** memuat 5 dari 7. `Content Quality` adalah
satu-satunya yang tidak punya rumah di mana pun — termasuk di Excel, yang
mencantumkan kolomnya tapi **tidak memberinya bobot maupun rumus**.

**Implikasi yang perlu diangkat ke Product:** `Performance Quality` bobotnya
hanya **10%** dari Final Match Score, sementara `Target Audience Relevance`
dapat 30%. Kalau ketujuh item ini benar-benar "apa yang paling penting", maka
model sekarang memberi 10% pada hal yang pengguna sebut paling penting. Itu
ketidakselarasan nyata — dan ia sudah gue catat sebagai **H17** di audit lama,
masih terbuka.

## 3.4 Perbandingan opsi

### A. 7 kolom di `kol_profile_card`

❌ **Tolak.** Tiga alasan, dan yang pertama sudah cukup:
1. `kol_profile_card` **di-regenerate oleh asset Dagster**. Kalau 7 item ini
   preference (tafsir P), data brand akan tertimpa job.
2. **Duplikasi metrik.** `audience_quality_score` sudah ada di tabel itu.
   Menambah kolom `high_audience_quality` = dua kolom untuk satu gagasan.
3. 2 dari 7 tidak punya sumber sama sekali — kolomnya akan permanen NULL, dan
   kolom kosong yang menunggu keputusan mengundang orang mengisinya dengan
   tebakan (pola yang sudah ditolak eksplisit di header migration 037/038).

### B. Tabel master `what_matters_criteria`

⚠️ **Hanya kalau tafsir P.** 7 baris referensi (`key`, `label`, `sort_order`,
`is_active`, plus kolom yang menunjuk metrik sumbernya). Murah dan tidak
merusak apa pun. Tapi **master saja tidak cukup** — kalau brand memilih, harus
ada tempat menyimpan pilihannya.

### C. Master criteria + mapping KOL/score

❌ **Tolak untuk sekarang.** Ini yang paling mahal dan paling mudah salah:
- Mapping per KOL berarti 7 × 7.432 = **52.024 baris** yang isinya **turunan
  kolom yang sudah ada**. Itu menyimpan hasil hitung dua kali.
- 2 dari 7 kriteria tidak punya input → 14.864 baris akan NULL selamanya.
- Kalau nanti rumus salah satu kriteria berubah, 52 ribu baris harus dihitung
  ulang — padahal kalau dihitung on-the-fly dari kolom sumber, tidak ada yang
  perlu di-backfill.

### D. Pakai scoring existing tanpa tabel baru

✅ **Ini yang paling tepat untuk 7 nilai per-KOL-nya.** Lima dari tujuh sudah
punya (atau jelas-jelas tidak punya) kolom sumber. Yang dibutuhkan bukan
penyimpanan, tapi **satu tabel pemetaan di level kode/config**: "kriteria
`strong_engagement` dibaca dari `kol_directory.engagement_rate`, dinormalisasi
terhadap target X".

### E. Kombinasi — **rekomendasi gue**

**E = B (master 7 baris) + D (baca dari metrik existing) + tempat menyimpan
pilihan brand.**

| Lapis | Bentuk | Kenapa |
|---|---|---|
| Daftar 7 kriteria | master `what_matters_criteria` — **7 baris**, kolom `criteria_key`, `label`, `sort_order`, `is_active`, `source_column`, `readiness` | UI butuh daftar yang bisa ditampilkan dan diurutkan tanpa hardcode. Mengikuti pola `campaign_stages` (master kecil + `sequence`) |
| Nilai per KOL | **tidak disimpan** — dibaca dari kolom existing sesuai `source_column` | Menghindari 52 ribu baris turunan |
| Pilihan brand | **HOLD sampai tafsir dipastikan.** Kalau tafsir P: 1 tabel kecil `brand_evaluation_preference(brand_id, criteria_id, rank/weight)` | Tidak ada tempat preference di DB sekarang. Tapi jangan dibuat sebelum fungsinya pasti |

**Kalau ternyata tafsir S** (setiap KOL wajib punya skor 7 item): tetap **jangan
pakai opsi C**. Yang benar adalah menghitung ketujuhnya dari kolom sumber saat
query, dan kalau performa jadi masalah baru dipertimbangkan menyimpannya —
persis pola yang sudah dipakai `Final Match Score` ("Computed, not stored.
Apply after ranking, never inside the SQL").

### Jawaban ringkas atas 6 pertanyaan lo

| # | Pertanyaan | Jawaban |
|---:|---|---|
| 1 | Di UI, 7 item dipakai untuk apa? | **Tidak bisa gue pastikan** — tidak ada di katalog UI mana pun di repo ini, dan kode frontend-nya di repo lain |
| 2 | User memilih sebagai preference/filter? | **Kemungkinan besar ya** (tafsir P), berdasarkan bentuk kalimatnya dan preseden `audience_priority`. Belum terbukti |
| 3 | Tiap KOL harus punya score untuk 7 item? | **Tidak perlu disimpan.** 5 dari 7 sudah bisa dihitung dari kolom existing; 2 tidak punya sumber apa pun |
| 4 | Sudah ada scoring existing dengan nama berbeda? | **Ya** — `Performance Quality` (6 sub-skor) + `Brand Safety`. Lihat §3.3 |
| 5 | Performance Quality / Brand Safety = source-nya? | **Ya, 6 dari 7.** Hanya `Content Quality` yang tidak punya rumah bahkan di Excel |
| 6 | Struktur paling simple kalau belum ada? | **1 tabel master 7 baris** + baca metrik existing. Tabel skor per KOL **tidak** diperlukan |

---

# OUTPUT FINAL

| Feature | Excel/UI Source | Existing DB | Need New Table? | Need New Column? | Recommended Structure | Formula/Logic | Status |
|---|---|---|---|---|---|---|---|
| **EMV** | Excel: **tidak ada definisi** (3 sebutan, 0 rumus); tersirat `engagement × 9.000 IDR` dari `Estimated ROI`. UI: sudah jadi opsi sorting (`deliv.xlsx` r132) | `campaign_kols.emv` · `campaign_content_performance.emv` · `feature.ig/tt_audience_analysis.emv` — **4 kolom, 0 terisi**. Input: `total_engagement` ✅, `reach` ❌ (0/503). **CPM & multiplier tidak ada** | **TIDAK** | **TIDAK** | Pakai 4 kolom existing. Hitung per baris di `campaign_content_performance`, **SUM → `campaign_kols.emv`** | **HOLD** — kandidat A `engagement × value_per_eng` atau B `reach × CPM ÷ 1000 × multiplier`. Jangan pilih sendiri | **HOLD** (definisi) |
| **CPE** | `KOL_Database.AP` = `Rate Card ÷ (Avg Views × ER% ÷ 100)` — **pasti** | Discovery: `feature.*_audience_analysis.cpe` (0 terisi), butuh rate card (**0 baris**). Campaign: `deal_price` + `total_engagement` **keduanya ada** | **TIDAK** | **TIDAK** | Discovery: kolom `cpe` existing. Campaign: **calculated di query/API** | Discovery: `fee ÷ (avg_views × er÷100)`. Campaign: `deal_price ÷ total_engagement`. Guard kosong → NULL, **bukan 0** | **PARTIAL** — campaign siap struktur, discovery blocked rate card |
| **CPV** | `KOL_Database.AO` = `Rate Card ÷ Average Views` — **pasti**, tanpa pembanding DB yang berbeda | **Tidak ada kolom `cpv`** di 101 tabel. Views: `campaign_content_performance.views` · `avg_views` (30) | **TIDAK** | **TIDAK** | **Calculated murni.** Jangan bikin kolom — turunan 2 kolom yang berubah tiap snapshot | Discovery: `fee ÷ avg_views`. Campaign: `deal_price ÷ SUM(cc_perf.views)` — **wajib agregasi**, `campaign_kols` tidak punya `views` | **PARTIAL** |
| **Style** | `brand_style_personality.Style List` — 18 baris, 2 grup, 16 nilai unik, **tanpa ID**. Sisi KOL: **18 baris** | **NOL** — 0 tabel, 0 kolom (`%style%` di 101 tabel). Preseden pola: `kol_categories` + `kol_directory.category_ids uuid[]` | **YA — 2 tabel** (bersama Personality) | TIDAK | **Opsi B**: `kol_attribute` (master, kind+group+key) + `kol_attribute_map` (junction ke `kol_directory`) | Bukan formula — **data kurasi manual**. Unik `(kind, group, key)` supaya `Educational` Content-Style ≠ Communication-Style | **READY didesain** — tunggu approval + keputusan kunci mapping |
| **Personality** | `brand_style_personality.Personality List` — 30 baris, 3 grup, 26 nilai unik, **tanpa ID**. Sisi KOL: **12 baris** (Creator Personality). Sisi brand: 18 baris (Brand Personality + Tone) | **NOL** — 0 tabel, 0 kolom | **TIDAK** — pakai 2 tabel yang sama dengan Style | TIDAK | Sama: `kol_attribute` `kind='personality'` | Idem. **Brand Personality + Brand Tone JANGAN masuk tabel KOL** — itu atribut `public.brand`, diblokir H2 | **READY didesain** (sisi KOL) · **HOLD** (sisi brand) |
| **What Matters Most** | **UI/Product, bukan Excel.** 0 hit di 51 sheet + 4 workbook UI. UI punya 8 Smart Preset yang **berbeda** | 6 dari 7 = sub-skor `Performance Quality` + komponen `Brand Safety`. Terisi: ER 1.736 · AQ 27 · proksi stability 11 / avg_views 30 / safety-4-input 27 · **Community & Content Quality NOL** | **YA — 1 tabel master, 7 baris** | **TIDAK** | **Opsi E**: master `what_matters_criteria` (7 baris + `source_column`) · nilai per KOL **tidak disimpan** · tempat preference brand **HOLD** | Tidak bikin rumus baru — tiap kriteria menunjuk kolom existing. 2 kriteria tanpa sumber tetap ditandai `readiness='missing'` | **HOLD** — fungsi (preference vs score) belum pasti |

---

## A. REKOMENDASI FINAL

Bahasa sederhana: **dari 6 fitur, cuma 2 yang butuh tabel baru. Empat lainnya
sudah punya rumahnya, dan yang hilang cuma keputusan.**

**1. EMV/CPE/CPV — jangan bikin apa pun.**
Kolom `emv` sudah ada di 4 tempat. CPE dan CPV cukup dihitung saat query dari
kolom yang sudah ada (`deal_price ÷ total_engagement`, `deal_price ÷ SUM(views)`).
Yang menghambat bukan struktur, tapi tiga hal: **definisi EMV belum ada**,
**"biaya" itu yang mana** (`deal_price` net kreator atau `total_amount` termasuk
fee+pajak), dan **rate card masih 0 baris** untuk versi Discovery.

Satu hal yang berubah baik sejak audit lama: `campaign_kol_deliverables` punya
`rate_card_snapshot` jsonb, jadi biaya campaign **tidak menunggu**
`unified_rate_card` terisi.

**2. Style & Personality — bikin 2 tabel, bukan 4.**
Keduanya bentuknya identik: "(grup, label) yang ditempel manual, boleh banyak
per KOL". Jadi satu master + satu junction cukup untuk keduanya. Kunci uniknya
harus `(kind, group, key)` — bukan label — karena `Educational` muncul di 4 grup
berbeda dengan arti berbeda.

Dan yang penting: **dari 48 baris Excel, hanya 30 milik KOL.** 18 sisanya
(Brand Personality + Brand Tone) milik `public.brand`. Jangan dicampur.

**3. What Matters Most — bikin 1 tabel master 7 baris, jangan bikin skor per KOL.**
Enam dari tujuh item **sudah ada** di DB dengan nama lain: mereka adalah sub-skor
`Performance Quality` (`engagement_rate`, `audience_quality_score`,
`performance_stability`, `avg_views`) plus komponen `Brand Safety`. Menyimpan
ulang sebagai 52 ribu baris skor = menyimpan hasil hitung dua kali. Yang
dibutuhkan cuma daftar 7 kriteria yang menunjuk kolom sumbernya.

**Tapi**: gue belum bisa memastikan ketujuh item itu **preference brand** atau
**skor KOL**, karena tidak ada di katalog UI mana pun dan kode frontend-nya di
repo lain. Bedanya besar — satu butuh tabel kecil, satu butuh 52 ribu baris.
Ini pertanyaan pertama yang harus dijawab Product.

---

## B. YANG SUDAH ADA — bisa langsung dipakai

| Kebutuhan | Tabel.kolom existing | Terisi | Catatan |
|---|---|---:|---|
| EMV per campaign × KOL | `public.campaign_kols.emv` | 0 baris | rumah siap, tunggu definisi |
| EMV per konten per snapshot | `public.campaign_content_performance.emv` | 0 baris | idem |
| EMV per akun (Discovery) | `feature.ig/tt_audience_analysis.emv` | 0 | idem |
| CPE per akun (Discovery) | `feature.ig/tt_audience_analysis.cpe` | 0 | butuh rate card |
| Biaya per KOL dalam campaign | `campaign_kols.deal_price` + `currency` | 0 baris | |
| Biaya per deliverable | `campaign_kol_deliverables.unit_price`, `subtotal`, `quantity` | 0 baris | |
| **Rate card tanpa menunggu `unified_rate_card`** | `campaign_kol_deliverables.rate_card_snapshot` jsonb | 0 baris | **temuan baru sesi ini** |
| Biaya total ke brand | `campaign_orders.total_amount` (+ `platform_fee_amount`, `tax_amount`, `discount_amount`) | 0 baris | |
| Engagement aktual | `campaign_kols.total_engagement` | 0 baris | |
| Views aktual | `campaign_content_performance.views` | 0 baris | |
| Reach aktual | `campaign_kols.reach`, `campaign_content_performance.reach` | 0 baris | |
| Strong Engagement | `kol_directory.engagement_rate` | **1.736** | cakupan terbesar |
| High Audience Quality | `kol_profile_card.audience_quality_score` + `audience_quality_tier` | **27** | terisi nyata |
| Brand Safety (proksi 4 input) | `authenticity_score` + `follower_quality_score` + `verified_status` + `paid_ratio` | 27 / 27 / 931 / 48 | **wajib dilabeli "integrity screen"** |
| Consistent Performance (proksi) | `performance_stability`, `post_frequency_reliability` | 11 / 49 | bukan konsep yang sama |
| High Reach (proksi) | `avg_views`, `median_views`, `view_to_follower_ratio` | 30 / 30 / 22 | **`reach` ≠ `views`** |
| Pola master kecil | `kol_categories`, `kol_tiers`, `platforms`, `campaign_stages` | 28 / 5 / 2 / 12 | pola `id uuid` + `*_key` + `label` + `sequence` |
| Pola banyak-nilai-per-KOL | `kol_directory.category_ids uuid[]` | 4.002 | alternatif junction |
| Pola provenance | `audience_*_daily.confidence`, `interest_source`, `content_topic_source`, `cc_perf.source`/`raw_ref_table`/`is_final` | — | **ikuti nama & nilai yang sudah ada**, jangan bikin vocabulary keempat |

---

## C. YANG PERLU DITAMBAH — hanya ini, tidak lebih

**Total: 3 tabel. Nol kolom baru di tabel existing.**

| # | Tabel | Baris | Untuk | Prasyarat |
|---:|---|---:|---|---|
| 1 | `kol_attribute` (master) | **30** | Style (18) + Personality sisi KOL (12) | Approval + keputusan D3 |
| 2 | `kol_attribute_map` (junction) | tumbuh | KOL ↔ attribute, many-to-many, dengan `assigned_by`/`assigned_at` | idem |
| 3 | `what_matters_criteria` (master) | **7** | daftar kriteria + `source_column` + `readiness` | **Keputusan D1** (preference vs score) |

**Yang TIDAK gue usulkan, dan alasannya:**

| Ditolak | Alasan |
|---|---|
| Kolom `emv`/`cpe`/`cpv` baru | `emv` sudah ada 4×; `cpe` sudah ada; `cpv` turunan murni |
| Kolom `style`/`personality` di `kol_profile_card` | tabel itu **di-regenerate asset Dagster** — data manual akan tertimpa |
| 4 tabel Style+Personality terpisah | bentuknya identik; 2 tabel sudah cukup |
| Tabel skor 7 kriteria × KOL | 52.024 baris turunan kolom yang sudah ada; 14.864 di antaranya NULL selamanya |
| Tabel brand baru | `public.brand` sudah ada (H2 masih terbuka) |
| Tabel campaign baru | 14 tabel sudah ada |
| Menyimpan `Final Match Score` | "Computed, not stored" — aturan Excel sendiri |
| VIEW untuk CPE/CPV | berguna, **tapi DB ini belum punya satu view pun** — memperkenalkan yang pertama adalah keputusan konvensi tim |
| Index tambahan | 7.432 baris, hanya PK yang ada sekarang, seq scan murah |

---

## D. YANG MASIH BUTUH KEPUTUSAN PRODUCT/MENTOR

Diurutkan dari yang paling memblokir:

| # | Keputusan | Pilihannya | Memblokir |
|---|---|---|---|
| **D1** | **7 item "What Matters Most" itu preference brand atau skor per KOL?** | P: brand memilih → 1 tabel kecil preference · S: tiap KOL punya nilai → hitung dari kolom existing | Seluruh Bagian 3. Tanpa ini, tabel apa pun berisiko salah bentuk |
| **D2** | **Definisi EMV resmi** | A: `engagement × value_per_engagement` (bisa dihitung hari ini) · B: `reach × CPM ÷ 1000 × multiplier` (butuh reach + 2 konstanta yang tidak ada) | Mengisi 4 kolom `emv`; sorting EMV di UI |
| **D3** | **Kunci mapping Style/Personality**: `kol_directory.id` atau `agency_kol_accounts.id`? | directory: preseden `category_ids`, tapi **439 handle lintas-platform harus diisi 2×** · agency: preseden `brand_fit_analysis`, tapi per-agency | Tabel #2 di bagian C |
| **D4** | **"Biaya" di CPE/CPV yang mana?** | `campaign_kols.deal_price` (net kreator) · `deliverables.subtotal` · `campaign_orders.total_amount` (termasuk fee + pajak) | Angka CPE/CPV yang dilaporkan |
| **D5** | **Definisi `total_engagement`** | `likes+comments` (seperti `kol_directory.engagement_rate`) atau `+shares+saves` (seperti `taksonomi_kol`) | CPE, EMV kandidat A, dan konsistensi ER — ini **H4 lama yang sekarang menyentuh campaign** |
| **D6** | **Aturan agregasi `snapshot_date` → `campaign_kols`** | `is_final=true` saja · snapshot terakhir per deliverable · pakai `delta_*` | EMV & CPV per campaign. **Salah pilih = double-count** |
| **D7** | Nilai `value_per_engagement` kalau D2 = A | Excel menyebut **9.000 IDR** tapi **tanpa sumber** | angka EMV |
| **D8** | Sisi brand Style/Personality (18 baris) disimpan di mana | kolom di `public.brand` · tabel `brand_attribute` · ikut `kol_attribute` dengan `kind` baru | Brand Personality Fit (10% skor). **Masih diblokir H2** |
| **D9** | Style/personality itu sifat **akun** atau **orang**? | kalau orang, DB belum punya tabel "orang" — 439 handle lintas-platform jadi masalah | Bentuk final tabel #2 |
| **D10** | Apakah "Content Quality" (#6) benar-benar dibutuhkan | Excel mencantumkan kolomnya tapi **tanpa sumber, tanpa rumus, dan bobot 0** | 1 dari 7 kriteria |
| **D11** | `Consistent Performance` = `performance_stability` (stddev ER) atau cadence posting? | dua konsep berbeda, keduanya ada sebagai proksi | kriteria #3 |
| **D12** | `High Reach` pakai `reach` asli (butuh Insights API) atau proksi `views`? | dokumentasi memperingatkan eksplisit `views ≠ reach` | kriteria #5 |

**Masih terbuka dari audit lama dan belum tersentuh sesi ini:** H1 (konstanta
CPM), H2 (`kol.brand` vs `tsdb.brands` — `tsdb` tidak ada di host ini), H3 (batas
tier), H17 (Performance cuma 10%), H20 (outlier ER 223,41%), H21 (`category_id`
vs `category_ids`), H22 (dua kosakata di `content_topic`), H23 (tipe
`followers_count`).

---

## E. IMPLEMENTATION ORDER

Dari paling aman ke paling berisiko. **Tidak satu langkah pun dimulai sebelum
approval lo.**

### Tahap 1 — nol perubahan DB, nol risiko

| # | Pekerjaan | Kenapa duluan |
|---|---|---|
| 1.1 | Bawa **D1** dan **D2** ke Product/mentor | Keduanya memblokir paling banyak, dan keduanya cuma butuh jawaban — bukan kode |
| 1.2 | Tulis pemetaan 7 kriteria → kolom sumber sebagai **config/konstanta di kode**, belum di DB | Bisa dipakai API sekarang, dan kalau D1 berubah, yang diubah cuma file config |
| 1.3 | Implementasi **CPE/CPV campaign sebagai query/API** — `deal_price ÷ total_engagement`, `deal_price ÷ SUM(views)` | Nol DDL. Jalan begitu campaign pertama ada barisnya |
| 1.4 | Sepakati aturan guard: input kosong → **NULL**, bukan 0 | Aturan Excel yang paling mudah salah diterjemahkan, dan paling mahal salahnya |

### Tahap 2 — 2 tabel, aditif, tidak menyentuh data existing

| # | Pekerjaan | Prasyarat |
|---|---|---|
| 2.1 | `kol_attribute` master + isi **30 baris** dari Excel | **D3** |
| 2.2 | `kol_attribute_map` junction | 2.1 |
| 2.3 | Endpoint filter UI Style/Personality (`EXISTS` + `attribute_group`) | 2.2 |

Aman karena: dua tabel baru yang tidak direferensikan siapa pun, tidak mengubah
satu kolom existing, dan tidak disentuh asset Dagster mana pun.

### Tahap 3 — setelah D1 dijawab

| # | Pekerjaan | Prasyarat |
|---|---|---|
| 3.1 | `what_matters_criteria` master **7 baris** | **D1** |
| 3.2 | Kalau D1 = tafsir P: tabel preference brand | **D1 + H2** (`brand` masih 0 baris) |
| 3.3 | Kalau D1 = tafsir S: hitung 7 nilai dari kolom sumber saat query — **tetap jangan bikin tabel skor** | **D1** |

### Tahap 4 — butuh data, bukan schema

| # | Pekerjaan | Membuka |
|---|---|---|
| 4.1 | Isi `public.brand` | `brand_fit_analysis` ber-FK ke `brand(id)` — **tidak satu baris pun bisa ditulis sebelum ini** |
| 4.2 | Campaign pertama masuk (`campaigns` → `campaign_kols` → `deliverables` → `cc_perf`) | Seluruh EMV/CPE/CPV versi campaign |
| 4.3 | Cari sumber rate card | CPE/CPV/CPM versi Discovery. ⚠️ bukan gap ETL — **0 baris di L0 juga** |
| 4.4 | Insights API untuk `reach` | EMV kandidat B, `avg_reach`, High Reach yang jujur |
| 4.5 | Naikkan cakupan `feature.*_audience_analysis` dari 27 akun | Audience Quality + Brand Safety proksi dari 0,36% ke populasi |

### Yang jangan dikerjakan sekarang

| Jangan | Alasan |
|---|---|
| Bikin kolom EMV/CPE/CPV | sudah ada atau turunan murni |
| Bikin tabel skor 7 kriteria × KOL | 52 ribu baris turunan, sebelum fungsinya pasti |
| Isi `emv` dengan rumus pilihan sendiri | **D2 belum dijawab** |
| Masukkan Brand Personality + Brand Tone ke tabel KOL | itu atribut brand, 18 baris, diblokir H2 |
| Taruh style/personality di `kol_profile_card` | di-regenerate Dagster; data manual akan hilang |
| Bikin VIEW pertama di DB ini | keputusan konvensi tim |
| Pakai proksi `views` sebagai "reach" tanpa label | dokumentasi memperingatkan eksplisit |
| Sebut proksi 4-input itu "Brand Safety" | itu *integrity screen*; nol pembacaan content-risk untuk akun mana pun |

---

## F. STATUS SESI

| | |
|---|---|
| Query dijalankan | ~10 `SELECT` tambahan (struktur & kardinalitas), seluruhnya read-only |
| INSERT / UPDATE / DELETE | **0** |
| CREATE / ALTER / DROP | **0** |
| Migration | **0** |
| Perubahan DB | **0** |
| Database disentuh | **`kol` saja** |
| File ditulis | `docs/KOL_DESIGN_EMV_STYLE_WHATMATTERS.md` (dokumen ini) |
| Keputusan yang gue ambil sendiri | bentuk struktur (2 tabel untuk Style/Personality, 1 master untuk 7 kriteria) dan penolakan opsi yang merusak. **Nol definisi bisnis, nol formula baru, nol threshold** |
| Keputusan yang gue serahkan | **12 item (D1–D12)** + 8 HOLD lama yang belum tersentuh |

**Menunggu approval sebelum tabel mana pun dibuat.**
