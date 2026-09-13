# FINAL DATA / SYSTEM DESIGN — KOL Discovery

**Basis:** `KOL_HOLD_RESOLUTION_2.md` + keputusan sementara 13 Sep 2026.
**DB:** `kol` @ `10.100.14.216` · `transaction_read_only = on`.
**Sifat:** DESIGN PROPOSAL. Nol DDL, nol DML, nol migration, nol tabel dibuat,
nol perubahan source code. Seluruh pemeriksaan `SELECT`.

---

## 0. SATU KLARIFIKASI SEBELUM MULAI

Keputusan #3 berbunyi *"CPV → gunakan definisi yang sudah dipilih dari keputusan
terbaru."*

**Belum ada keputusan yang tercatat untuk unit CPV.** Audit sebelumnya menutup
CPV sebagai `NEEDS BUSINESS CONFIRMATION` dengan skor 2–2:

| Per **1 view** | Per **1.000 views** |
|---|---|
| Excel `KOL_Database.AO` = `Rate ÷ Average Views` | Frontend `app/AUTOME_2.html:2783` = `rate / views * 1000` |
| Register `docs/filter.xlsx` r30 = **"Biaya per view."** | Label UI `:2842` = `'CPV / 1K views ≤ ($)'` |

Gue **tidak memilih sendiri** — itu keputusan bisnis. Tapi gue penuhi bagian
*"pastikan unitnya jelas dan tidak terjadi kesalahan 1.000×"* dengan cara yang
lebih kuat daripada memilih: **§3 mendesain CPV dengan unit sebagai parameter
eksplisit yang wajib diisi**, sehingga angka tanpa unit tidak mungkin lolos.
Satu baris konfigurasi menutup keputusan ini kapan pun mentor menjawab.

---

# 1. EMV — DESAIN IMPLEMENTASI

Formula yang diadopsi: **`EMV = Reach × CPM ÷ 1000 × Multiplier`**
(sumber: `migrations/FEATURE_METRICS_BACKLOG.md:249`)

## 1.1 Source tiap komponen — dari schema `kol` yang sudah ada

### Reach

| Grain | Kolom | Status | Terisi |
|---|---|---|---|
| campaign × KOL | **`public.campaign_kols.reach`** (bigint) | ✅ kolom ada | 0 baris (tabel kosong) |
| deliverable × snapshot | **`public.campaign_content_performance.reach`** (bigint) | ✅ kolom ada | 0 baris |
| akun (Discovery) | `feature.ig/tt_audience_analysis.avg_reach` (integer) | ✅ kolom ada | **0 / 27** |
| post | `l1_silver.unified_post.reach` | ✅ kolom ada | **0 / 503** |
| — | `l0_raw.kol_roster_import.estimated_reach` | ⚠️ **ditolak** | 96,2% terisi tapi **2.164 baris reach > followers** |

**Keputusan desain: `reach` diambil dari baris yang sama dengan tempat EMV
disimpan.** Tidak ada join, tidak ada fallback lintas-grain. Kalau `reach` NULL →
EMV NULL (bukan 0).

⚠️ `estimated_reach` **tidak dipakai** sampai dibersihkan — penolakannya sudah
terdokumentasi di backlog dan gue verifikasi ulang sendiri.

### CPM

**Tidak ada source di database.** Sapuan `information_schema` 101 tabel untuk
`%cpm%` → **0 kolom**. Excel hanya punya CPM sebagai *metrik output*
(`Rate ÷ Followers × 1000`), bukan konstanta pasar. Frontend `:2782` juga
*output* (`rate/reach*1000`).

**Ini input formula yang harus disediakan dari luar DB.**

### Multiplier

**Tidak ada source, dan lebih kosong dari CPM.** `%multiplier%`,
`%coefficient%`, `%factor%` → **0 kolom**. Di Excel satu-satunya "multiplier"
adalah `Risk Multiplier` (0,6 / 0,85 / 0,95 / 1) yang merupakan **pengali Brand
Safety**, sama sekali bukan komponen EMV. Di kedua prototype: **0 hit**.

**Ini juga input yang harus disediakan.**

## 1.2 Bagaimana kalau CPM/Multiplier belum punya source database

Sesuai instruksi lo — **gue tidak membuat kolom baru hanya supaya formula bisa
jalan, dan tidak mengarang nilainya.** Tiga opsi, diurutkan dari paling aman:

| Opsi | Bentuk | Kelebihan | Kekurangan | Rekomendasi |
|---|---|---|---|---|
| **O1 — konfigurasi aplikasi** (env/config file) | `EMV_CPM_<platform>`, `EMV_MULTIPLIER` di config backend | Nol perubahan DB. Bisa diubah tanpa migration. Cocok untuk konstanta yang jarang berubah. **Sesuai preseden**: `README` workbook r47 sudah meminta konstanta Lookup_Lists disimpan sebagai konfigurasi, bukan di source | Tidak ter-audit per perubahan; tidak bisa beda per-brand | ✅ **Pakai ini dulu** |
| O2 — tabel konfigurasi `metric_config` | `(key, value, scope, effective_from)` | Ter-audit, bisa historis, bisa per-platform/tier | **Tabel baru untuk 2 angka** yang nilainya belum ada. Melanggar prinsip "jangan bikin tabel sebelum kebutuhannya terbukti" | ⏸ Nanti, kalau CPM perlu historis |
| O3 — kolom di tabel existing | — | — | **Ditolak**: tidak ada tabel yang grain-nya cocok untuk konstanta global | ❌ |

**Sampai nilainya ada: `emv` tetap NULL.** Itu bukan kegagalan — itu perilaku
yang sudah ditegakkan `tests/test_calculated_metrics.py:385`.

## 1.3 Grain EMV & tabel existing yang dipakai

Tiga grain, semuanya **kolom sudah ada**, nol kolom baru:

```
┌─ Discovery / pra-campaign ────────────────────────────────────┐
│ feature.ig_audience_analysis.emv                              │
│ feature.tt_audience_analysis.emv          grain: social_account│
│   reach ← avg_reach (0 terisi)                    → BLOCKED    │
└───────────────────────────────────────────────────────────────┘

┌─ Campaign aktual ─────────────────────────────────────────────┐
│ campaign_content_performance.emv                              │
│   grain: campaign_kol_deliverable_id × snapshot_date          │
│   reach ← campaign_content_performance.reach                  │
│                    │                                          │
│                    │ agregasi (aturan BELUM ADA)              │
│                    ▼                                          │
│ campaign_kols.emv         grain: campaign_id × agency_kol_acc │
│   reach ← campaign_kols.reach                                 │
└───────────────────────────────────────────────────────────────┘
```

**Tidak ada EMV di grain post** — dan memang tidak perlu: `l2_gold.post_metric`
dan `l1_silver.unified_post` tidak punya kolom `emv`, dan menambahkannya akan
melanggar test guard.

## 1.4 Calculated atau disimpan?

**Disimpan — dan ini pengecualian yang disengaja.**

| Metrik | Disimpan? | Alasan |
|---|---|---|
| **EMV** | ✅ **disimpan** | Kolomnya **sudah dibuat** di 4 tempat. Skema sudah memutuskan ini sebelum gue datang. Dan EMV bergantung konstanta (CPM, multiplier) yang bisa berubah — menyimpan hasilnya berarti angka historis tetap bisa dipertanggungjawabkan terhadap konstanta yang berlaku saat itu |
| CPE / CPV | ❌ calculated | Turunan murni dua kolom sebaris; tidak ada kolom di grain campaign; test guard melarang menambah |

⚠️ Konsekuensi menyimpan: kalau CPM/multiplier diubah, **`emv` lama menjadi
basi**. Harus diputuskan: recompute seluruh histori, atau simpan konstanta yang
dipakai bersama nilainya. Itu bagian dari keputusan O1/O2 di §1.2.

## 1.5 Ringkasan desain EMV

| Aspek | Keputusan |
|---|---|
| Formula | `Reach × CPM ÷ 1000 × Multiplier` |
| Reach | dari baris yang sama (`campaign_kols.reach` / `campaign_content_performance.reach` / `avg_reach`) |
| CPM | **config aplikasi (O1)** — belum ada nilainya |
| Multiplier | **config aplikasi (O1)** — belum ada nilainya |
| Grain | 3: akun · campaign×KOL · deliverable×snapshot |
| Penyimpanan | disimpan di kolom `emv` yang sudah ada |
| Kolom baru | **NOL** |
| Tabel baru | **NOL** |
| Guard | input NULL → hasil **NULL**, bukan 0 |
| Status | **BLOCKED sampai CPM + Multiplier + reach tersedia** |

---

# 2. CPE — FINALISASI DESAIN

## 2.1 Perbandingan eksplisit empat kandidat cost

| Kandidat | Tabel.kolom | Tipe | Grain kolom | Isi sekarang | Artinya |
|---|---|---|---|---|---|
| **K1** | `campaign_kols.deal_price` (+ `currency`) | numeric | **campaign × KOL** | 0 baris | Harga nego bersih untuk satu KOL dalam satu campaign |
| **K2** | `campaign_kol_deliverables.unit_price` | numeric | **deliverable** | 0 baris | Harga **satu unit** deliverable (perlu × `quantity`) |
| **K3** | `campaign_kol_deliverables.subtotal` | numeric | **deliverable** | 0 baris | Harga total deliverable — **diasumsikan** `unit_price × quantity` (nama + kolom tetangga `quantity`; **belum bisa dibuktikan**, tabel kosong) |
| **K4** | `l1_silver.unified_rate_card.fee` | numeric | **KOL × post_type** | **0 baris** — sumbernya ada di `l0_raw.kol_roster_import` (93,7% roster punya ≥1 harga > 0) | Harga rate card, pra-campaign |
| ❌ | `campaign_orders.total_amount` | numeric | **order** | 0 baris | **BUKAN biaya KOL** — total checkout Midtrans (`subtotal→promo→fee 8%→pajak 11%`), mencakup banyak creator (`creators_count`) |

## 2.2 Penetapan per level

### Campaign/KOL level → **K1 `campaign_kols.deal_price`**

Alasan, diurutkan:
1. **Grain-nya identik** dengan tempat hasilnya dibaca. `deal_price`,
   `total_engagement`, `emv`, `roas`, `performance_score` ada di **baris yang
   sama** → nol join, nol risiko salah alokasi antar-creator.
2. UI campaign tracking (`app/Autometric-KOL-Module.html:1796–1809`) memetakan
   1:1 ke tabel ini: `alloc`, `eng`, `emv`, `roas`, `score`.
3. K2/K3 bergrain lebih halus → butuh agregasi. K4 pra-campaign → beda
   pertanyaan.

### Deliverable level → **K3 `campaign_kol_deliverables.subtotal`**

Alasan: sebaris dengan `campaign_kol_deliverable_id`, yang persis FK di
`campaign_content_performance` (tempat engagement per konten hidup). `subtotal`
dipilih di atas K2 `unit_price` karena sudah memperhitungkan `quantity`.

⚠️ **Asumsi `subtotal = unit_price × quantity` belum terbukti** (0 baris).
Harus dikonfirmasi ke backend sebelum dipakai.

### Discovery / rate-card level → **K4 `l1_silver.unified_rate_card.fee`**

Alasan: itu grain KOL × post_type, sesuai pertanyaan "berapa CPE kalau saya
pakai KOL ini". **Sumbernya sudah ada** di `l0_raw.kol_roster_import` (14 kolom
harga, 7.231 baris punya ≥1 harga > 0) — yang belum jalan adalah propagasi
L0 → L1.

⚠️ Tiga hal harus dibereskan saat propagasi: **`post_type` mana** yang jadi
basis fee, **sentinel `1.000.000.000`**, dan **8 baris harga < Rp1.000**.

## 2.3 Denominator engagement

| Level | Denominator | Kolom | Status |
|---|---|---|---|
| Campaign/KOL | engagement aktual | `campaign_kols.total_engagement` (bigint) | kolom ada, 0 baris |
| Deliverable | engagement aktual per konten | `campaign_content_performance.total_engagement` | kolom ada, 0 baris |
| Discovery | engagement agregat per akun | dari `l2_gold.post_metric` (503 baris) | tersedia sebagian |

⚠️ **Definisi `total_engagement` belum pasti** — dan register internal tidak
konsisten dengan dirinya sendiri:

| Sumber | Isi "engagement" |
|---|---|
| `filter.xlsx` #11 & #12 (FINAL/APPROVED) — Share/Save Rate | penyebut **`Likes + Comments + Shares`** |
| `transform.py` — implementasi ER `kol_directory` | **`AVG(likes + comments)`** — tanpa shares |
| `taksonomi_kol` — Engagement Driver | `Likes + Comments + Shares` |

**`NEEDS MENTOR CONFIRMATION`.** Desain tidak memilih; ia membaca kolom
`total_engagement` apa adanya dan definisinya ditetapkan saat kolom itu diisi.

## 2.4 Formula final CPE

```
CPE_campaign_kol  = campaign_kols.deal_price
                    ÷ NULLIF(campaign_kols.total_engagement, 0)

CPE_deliverable   = campaign_kol_deliverables.subtotal
                    ÷ NULLIF(campaign_content_performance.total_engagement, 0)

CPE_discovery     = unified_rate_card.fee            -- post_type tertentu
                    ÷ NULLIF(total_engagement_akun, 0)
```

**Guard wajib:** pembilang atau penyebut NULL/0 → hasil **NULL**, bukan 0.
`NULLIF` pada penyebut mencegah division-by-zero sekaligus mengembalikan NULL.

| Aspek | Keputusan |
|---|---|
| Tabel existing | `campaign_kols`, `campaign_kol_deliverables`, `campaign_content_performance`, `unified_rate_card` |
| Kolom baru | **NOL** |
| Kolom `cpe` di `l2_gold.kol_profile_card` | ❌ **DILARANG** — `tests/test_calculated_metrics.py:372` |
| Penyimpanan | **calculated / query-time** untuk grain campaign; kolom `feature.*.cpe` yang sudah ada dipakai untuk Discovery |
| Unit | IDR per engagement |
| Status | **PARTIAL** — struktur pasti, denominator menunggu definisi |

---

# 3. CPV — FINALISASI DESAIN

## 3.1 Unit: dirancang sebagai parameter eksplisit

Karena unit belum diputuskan (§0), desainnya **memaksa unit dinyatakan**:

```
CPV = cost ÷ NULLIF(views, 0) × CPV_UNIT_FACTOR

CPV_UNIT_FACTOR = 1      → CPV per 1 view       (Excel + register filter.xlsx)
CPV_UNIT_FACTOR = 1000   → CPV per 1.000 views  (frontend + label UI)
```

Tiga aturan yang membuat kesalahan 1.000× tidak mungkin lolos:

| # | Aturan |
|---|---|
| 1 | `CPV_UNIT_FACTOR` **wajib** ada di config; **tidak boleh punya default**. Kalau tidak diset → error saat start, bukan angka diam-diam salah |
| 2 | Setiap nilai CPV yang keluar dari API **wajib** membawa field `unit` (`"IDR/view"` atau `"IDR/1K views"`) — bukan angka telanjang |
| 3 | Label UI **wajib** diturunkan dari `unit`, bukan ditulis manual. Ini yang mencegah kasus sekarang: slider bilang "/ 1K views" sementara `IQ_GROUPS` bilang "per View" |

## 3.2 Komponen

| Aspek | Isi |
|---|---|
| **Numerator (cost)** | Sama dengan CPE: `campaign_kols.deal_price` (campaign×KOL) · `campaign_kol_deliverables.subtotal` (deliverable) · `unified_rate_card.fee` (Discovery) |
| **Denominator (views)** | `campaign_content_performance.views` (bigint) · `l2_gold.post_metric.views` (397/503) · `feature.*_engagement_analysis.avg_views` (30) |
| **Unit** | `IDR / view` **atau** `IDR / 1.000 views` — parameter |
| **Grain** | campaign × KOL (utama) · deliverable · KOL (Discovery) |

⚠️ **Asimetri penting vs CPE:** `campaign_kols` **tidak punya kolom `views`**.
Jadi CPV di grain campaign × KOL **wajib agregasi** dari
`campaign_content_performance`, sementara CPE cukup baca satu baris.

## 3.3 Formula final

```
CPV_campaign_kol = campaign_kols.deal_price
                   ÷ NULLIF((SELECT SUM(ccp.views)
                             FROM campaign_content_performance ccp
                             JOIN campaign_kol_deliverables d
                               ON d.id = ccp.campaign_kol_deliverable_id
                             WHERE d.campaign_kol_id = campaign_kols.id
                               AND <ATURAN_SNAPSHOT>), 0)
                   × CPV_UNIT_FACTOR

CPV_deliverable  = campaign_kol_deliverables.subtotal
                   ÷ NULLIF(campaign_content_performance.views, 0)
                   × CPV_UNIT_FACTOR

CPV_discovery    = unified_rate_card.fee
                   ÷ NULLIF(avg_views, 0)
                   × CPV_UNIT_FACTOR
```

⚠️ **`<ATURAN_SNAPSHOT>` belum ada dan wajib diisi.**
`campaign_content_performance` bergrain **per snapshot_date** dan punya
`delta_views`, `delta_engagement`, `is_final`. Menjumlahkan seluruh baris akan
**menghitung ganda**. Tiga opsi: `WHERE is_final = true` · baris
`snapshot_date` terakhir per deliverable · `SUM(delta_views)`.
**Ini keputusan yang sama yang dibutuhkan EMV agregat** (§1.3) — satu keputusan,
dua metrik.

| Aspek | Keputusan |
|---|---|
| Existing table | `campaign_kols`, `campaign_kol_deliverables`, `campaign_content_performance`, `unified_rate_card`, `post_metric` |
| Kolom baru | **NOL** |
| Kolom `cpv` di profile card | ❌ **DILARANG** — test guard |
| Penyimpanan | **calculated murni** — tidak ada kolom `cpv` di seluruh DB, dan tidak perlu |
| Status | **NEEDS MENTOR CONFIRMATION** untuk `CPV_UNIT_FACTOR` + `<ATURAN_SNAPSHOT>` |

---

# 4. STYLE & PERSONALITY — TAXONOMY GABUNGAN

## 4.1 Sumber yang digabung

| Sumber | Isi | Catatan |
|---|---|---|
| **Excel** `brand_style_personality.xlsx` | Content Style 10 · Communication Style 8 · Creator Personality 12 · *(Brand Personality 10 · Brand Tone 8 — sisi brand)* | `Count in DB = 0` untuk seluruh 48; `Source` = `scripts/brand-match/vocabulary.mjs` |
| **UI prototype** `app/AUTOME_2.html` (`DNA2`) | `dna` 8 · `comm` 7 · `vis` 7 | Nilai hanya dari **8 creator mock**; tidak ada konstanta vocabulary yang dideklarasikan |

## 4.2 Hasil perbandingan — dihitung, bukan dikira

**Nilai UI yang TIDAK ada di Excel (7):**

| Sumbu UI | Nilai baru |
|---|---|
| `dna` | `expert` |
| `comm` | `commentary`, `demonstration`* |
| `vis` | `cinematic`, `colorful`, `lifestyle`, `minimalist` |

\* `demonstration` mirip-tapi-tidak-sama dengan Excel `Demonstrative`
(Communication Style) dan `Demo` (Content Style). **Butuh keputusan**: alias atau
nilai tersendiri.

**Nilai Excel yang TIDAK ada di UI (12):**

| Grup | Nilai |
|---|---|
| Content Style | `Demo`, `Comedy` |
| Communication Style | `Demonstrative`, `Conversational`, `Data-driven`, `Visual-first`, `Testimonial` |
| Creator Personality | `Creative`, `Tech-savvy`, `Reviewer`, `Premium`, `Luxury` |

**Label ambigu — sama di beberapa grup Excel:**

| Label | Muncul di |
|---|---|
| `Educational` | Content Style + Communication Style + Creator Personality (**3 grup**) |
| `Entertaining` | Content Style + Creator Personality |
| `Humorous` | Communication Style + Creator Personality |
| `Storytelling` | Content Style + Communication Style |

→ Inilah sebab kunci unik **wajib `(group, value)`**, bukan `value` saja.

## 4.3 TAXONOMY GABUNGAN — sisi KOL

Legenda `Source`: **E** = Excel · **U** = UI prototype · **E+U** = keduanya.

### Group: `content_style` (11)

| Kind | Group | Value | Source | KOL attribute? |
|---|---|---|---|---|
| style | Content Style | Educational | **E+U** | ✅ |
| style | Content Style | Tutorial | **E+U** | ✅ |
| style | Content Style | Review | **E+U** | ✅ |
| style | Content Style | Storytelling | **E+U** | ✅ |
| style | Content Style | Aesthetic | **E+U** | ✅ |
| style | Content Style | Entertaining | **E+U** | ✅ |
| style | Content Style | Vlog | **E+U** | ✅ |
| style | Content Style | Talking Head | **E+U** | ✅ |
| style | Content Style | Demo | **E** | ✅ |
| style | Content Style | Comedy | **E** | ✅ |
| style | Content Style | **Commentary** | **U** | ✅ |

### Group: `communication_style` (8, +1 pending)

| Kind | Group | Value | Source | KOL attribute? |
|---|---|---|---|---|
| style | Communication Style | Educational | **E** | ✅ |
| style | Communication Style | Storytelling | **E** | ✅ |
| style | Communication Style | Demonstrative | **E** | ✅ |
| style | Communication Style | Conversational | **E** | ✅ |
| style | Communication Style | Data-driven | **E** | ✅ |
| style | Communication Style | Visual-first | **E** | ✅ |
| style | Communication Style | Humorous | **E** | ✅ |
| style | Communication Style | Testimonial | **E** | ✅ |
| style | Communication Style | *Demonstration* | **U** | ⏸ **pending** — alias dari `Demonstrative`/`Demo`? |

### Group: `creator_personality` (13)

| Kind | Group | Value | Source | KOL attribute? |
|---|---|---|---|---|
| personality | Creator Personality | Professional | **E+U** | ✅ |
| personality | Creator Personality | Educational | **E+U** | ✅ |
| personality | Creator Personality | Relatable | **E+U** | ✅ |
| personality | Creator Personality | Casual | **E+U** | ✅ |
| personality | Creator Personality | Entertaining | **E+U** | ✅ |
| personality | Creator Personality | Humorous | **E+U** | ✅ |
| personality | Creator Personality | Inspirational | **E+U** | ✅ |
| personality | Creator Personality | Creative | **E** | ✅ |
| personality | Creator Personality | Tech-savvy | **E** | ✅ |
| personality | Creator Personality | Reviewer | **E** | ✅ |
| personality | Creator Personality | Premium | **E** | ✅ |
| personality | Creator Personality | Luxury | **E** | ✅ |
| personality | Creator Personality | **Expert** | **U** | ✅ |

### Group: `visual_style` (7) — sumbu yang hanya ada di UI

| Kind | Group | Value | Source | KOL attribute? |
|---|---|---|---|---|
| style | Visual Style | Aesthetic | **U** | ✅ |
| style | Visual Style | Casual | **U** | ✅ |
| style | Visual Style | Professional | **U** | ✅ |
| style | Visual Style | Cinematic | **U** | ✅ |
| style | Visual Style | Colorful | **U** | ✅ |
| style | Visual Style | Lifestyle | **U** | ✅ |
| style | Visual Style | Minimalist | **U** | ✅ |

> `Aesthetic`, `Casual`, `Professional` sengaja **diulang** di sini meski sudah
> ada di grup lain — karena di UI ia sumbu berbeda (`vis`), persis seperti
> `Educational` yang sah muncul di 3 grup Excel. Kunci `(group, value)` menjaga
> keduanya tidak tertukar.

### YANG SENGAJA TIDAK DIMASUKKAN — sisi brand

| Kind | Group | Value | Source | KOL attribute? |
|---|---|---|---|---|
| personality | Brand Personality | Professional · Innovative · Friendly · Premium · Playful · Educational · Authentic · Bold · Caring · Modern (10) | E | ❌ **atribut BRAND** |
| personality | Brand Tone | Formal · Informative · Warm · Aspirational · Playful · Inspiring · Straightforward · Conversational (8) | E | ❌ **atribut BRAND** |

Evidence bahwa keduanya milik brand: kolomnya di `Brand_Profile` Excel
(`brand_personality`, `brand_tone`), dan `Matching_Engine` memakainya sebagai
**sisi brand** dalam matriks 7 (Brand Personality × Creator Personality) dan
matriks 8 (Brand Tone × Content Style). **Tidak ada evidence** bahwa keduanya
dimaksudkan sebagai atribut KOL. Rumahnya `public.brand` — diblokir karena
tabel itu 0 baris.

### Rekap

| Grup | Jumlah | E saja | U saja | E+U |
|---|---:|---:|---:|---:|
| `content_style` | 11 | 2 | 1 | 8 |
| `communication_style` | 8 (+1 pending) | 8 | (1) | 0 |
| `creator_personality` | 13 | 5 | 1 | 7 |
| `visual_style` | 7 | 0 | 7 | 0 |
| **TOTAL sisi KOL** | **39** (+1 pending) | 15 | 9 | 15 |
| *(sisi brand — tidak dipakai)* | *18* | *18* | — | — |

## 4.4 Struktur yang diusulkan

**Dua tabel. Tidak dibuat — ini proposal.**

### Master: `kol_attribute` — 39 baris

| Kolom | Tipe usulan | Isi | Catatan |
|---|---|---|---|
| `id` | uuid PK, `gen_random_uuid()` | — | ikut pola `public.brand`, `campaign_stages` |
| `kind` | varchar(20) | `style` \| `personality` | pemisah kasar untuk UI |
| `attribute_group` | varchar(40) | `content_style` \| `communication_style` \| `creator_personality` \| `visual_style` | **sumbu sebenarnya** |
| `attribute_key` | varchar(80) | `content_style.educational` | slug stabil untuk API/config |
| `label` | varchar(80) | `Educational` | teks tampil, boleh berubah |
| `source_origin` | varchar(20) | `excel` \| `ui` \| `excel+ui` | **jejak asal**, sesuai permintaan |
| `sort_order` | integer | urutan tampil | ikut pola `campaign_stages.sequence` |
| `is_active` | boolean | menonaktifkan tanpa menghapus | ikut pola `brand.is_active` |

**Unik: `(kind, attribute_group, attribute_key)`** → `Educational` boleh ada di
3 grup, tapi tidak boleh dobel dalam satu grup.

### Junction: `kol_attribute_map`

| Kolom | Tipe usulan | Catatan |
|---|---|---|
| `id` | uuid PK | |
| `kol_directory_id` | uuid **FK → `kol_directory(id)`** | lihat §5 untuk alasan kunci ini |
| `kol_attribute_id` | uuid **FK → `kol_attribute(id)`** | |
| `assigned_by` | uuid FK → `"user"(id)` | data kurasi manual — jejak wajib |
| `assigned_at` | timestamptz | |
| `note` | text NULL | alasan opsional |

**Unik: `(kol_directory_id, kol_attribute_id)`** → satu label tidak bisa
ditempel dua kali ke KOL yang sama.

**Kenapa junction, bukan array `uuid[]` seperti `category_ids`:** array tidak
bisa membawa `assigned_by`/`assigned_at`, dan ini data kurasi manual di mana
jejak "siapa menaruh, kapan" justru yang penting.

### Contoh query filter UI

```sql
-- KOL dengan Content Style 'Storytelling' ATAU 'Educational'
SELECT d.*
FROM public.kol_directory d
WHERE EXISTS (
  SELECT 1 FROM kol_attribute_map m
  JOIN kol_attribute a ON a.id = m.kol_attribute_id
  WHERE m.kol_directory_id = d.id
    AND a.attribute_group = 'content_style'
    AND a.attribute_key IN ('content_style.storytelling','content_style.educational')
);
```

7.432 baris, seq scan murah — index ditinjau kalau populasi tumbuh ≫100k.

---

# 5. PERSON IDENTITY — VALIDASI `influencer_id`

## 5.1 Hasil validasi (seluruhnya `SELECT`, 13 Sep 2026)

### Konsistensi dasar

| Pemeriksaan | Hasil |
|---|---|
| Baris `l0_raw.kol_roster_import` | **7.718** |
| `influencer_id` NULL | **0** |
| `influencer_id` string kosong | **0** |
| `influencer_id` unik | **7.400** |
| **`influencer_id` non-numerik** | **17** ⚠️ |
| Baris **tanpa** `kol_directory_id` | **510** ⚠️ |
| Baris tanpa `social_account_id` | 512 |
| Jumlah `import_batch_id` | **1** ⚠️ |

**17 nilai non-numerik ternyata pecahan alamat** — `Pakuwon City`,
`RT 11 / RW 08`, `Kelurahan Kalisari`, `Kab/Kota : Jakarta Barat`,
`Jln. Patriot no.3 rawa aren rt/rw 03/24`, … Ini **CSV column shift** yang sama
yang mengontaminasi `influencer_gender` dan `estimated_reach`.

**Hanya 1 import batch** → **stabilitas `influencer_id` lintas-import BELUM
TERUJI.** Tidak ada bukti bahwa id yang sama akan menunjuk orang yang sama pada
import berikutnya.

### Sebaran akun per `influencer_id`

| Tier | Kriteria | `influencer_id` | Akun tercakup |
|---|---|---:|---:|
| **T0** | 1 akun | **6.785** | 6.785 |
| **T1** | 2 akun · 2 platform · **handle SAMA** | **61** | 122 |
| **T2** | 2 akun · 2 platform · **handle BEDA** | **53** | 106 |
| **T3** | 2 akun · **platform SAMA** | **18** ⚠️ | 36 |
| **T4** | **3+ akun** | **20** ⚠️ | **157** |
| | **Total ber-akun** | **6.937** | **7.206** |

- **Lintas platform (>1 platform): 126 `influencer_id`**
- **>1 akun dalam platform yang sama: 38** (T3 18 + sebagian T4)
- **Outlier terbesar: 43 akun** dalam satu `influencer_id`

### Apakah satu `influencer_id` bisa mencampur beberapa orang?

**YA — terbukti, dan itu pola, bukan kasus tunggal.**

`influencer_id = 8372` (43 akun, seluruhnya Instagram):

```
abednego_n (77K) · alfinpanduu (30K) · doktermedok (1,17M) ·
kangferrymaryadi (1,4M) · kyim.kusnadireja (11K) · limintangdilino (63K) ·
mas.dikaaa (12K) · putranugra (16K) · rafimnaf (36K) · revdy (140K) ·
rivaldimy (13K) · skidsans (24K) · syarif.yosee (38K) · teoakustikgitar (20K) …
```

Orang-orang yang jelas berbeda. Dan bukan satu-satunya:

| `influencer_id` | Akun | Handle unik | Contoh |
|---|---:|---:|---|
| 10005 | 13 | 13 | ahquote, alyakbar__, anyageraldine, ardhisekartaji … |
| 6014 | 12 | 12 | aliciaaurora_, anindya.ramaa, ataliabunga … |
| 10300 | 10 | **8** | a.ci.pa, bernadettegainara, deborahlvn … |
| 6869 | 10 | 10 | anaindahafsheenmy, bakpaoanget19, conytiwi … |
| 10245 | 8 | 8 | alviansyahnr, alvinsyahvin, andreayudias … |

**Seluruh 20 `influencer_id` di T4 punya duplikat dalam platform yang sama**,
dan hampir semuanya handle berbeda-beda → **T4 adalah bucket terkontaminasi**,
bukan orang.

### Sebaliknya: T1/T2 tampak sah

```
influencer_id = 1      tasyakamila (IG, 5.042.266) + tasyakamilaofficial (TT, 526.100)
influencer_id = 10     tenggowicaksono (IG, 288.661) + tenggowicaksono (TT, 912.400)
influencer_id = 10011  destisetioningsih (IG, 22.323) + destisetioningsih (TT, 4.245)
```

**T2 adalah nilai tambah sesungguhnya** — 53 `influencer_id` yang menghubungkan
handle BERBEDA lintas platform. Pencocokan berbasis handle **tidak akan pernah**
menangkap `tasyakamila` ↔ `tasyakamilaofficial`.

## 5.2 Vonis

| | |
|---|---|
| Bisa dipakai apa adanya? | **TIDAK** |
| Bisa dipakai setelah penyaringan? | **YA — untuk T1 + T2** (114 `influencer_id` / 228 akun) |
| Yang harus dikarantina | **T3 (18) + T4 (20) = 38 `influencer_id` / 193 akun** |
| Risiko kalau dipakai buta | **157 akun di T4 akan digabung sebagai "satu orang" padahal bukan** — 2,2% roster |

**Aturan penyaringan yang gue usulkan** (deterministik, bukan tebakan):

```
LAYAK  : jumlah akun = 2  DAN  jumlah platform = 2
KARANTINA : jumlah akun ≥ 3  ATAU  ada >1 akun dalam platform yang sama
           ATAU influencer_id non-numerik
```

T1 (handle sama) bisa diterima otomatis. **T2 (handle beda) sebaiknya lewat
review manual** — 53 baris, satu kali kerja.

## 5.3 Opsi A — tanpa person table

**Struktur:** `kol_attribute_map.kol_directory_id → kol_directory(id)`.
`influencer_id` dipakai **hanya sebagai alat bantu UI/QA**, tidak menjadi FK.

| | |
|---|---|
| **Kelebihan** | Nol tabel identitas baru · nol migrasi data · cakupan terluas (7.432) · preseden `category_ids` ada di tabel yang sama · **tidak terpapar kontaminasi T4** karena tidak ada penggabungan yang dilakukan DB |
| **Kekurangan** | Atribut tersimpan **per akun**, bukan per orang → 114 orang lintas-platform harus dilabeli 2× |
| **Risiko** | Label bisa berbeda antar platform tanpa terdeteksi DB |
| **Dampak ke Style/Personality** | Saat kurasi, UI menampilkan "akun ini punya saudara di platform lain (`influencer_id` sama, tier T1/T2) — terapkan juga?" → **tawaran, bukan otomatis**. Laporan QA: "`influencer_id` sama, atribut beda" |

## 5.4 Opsi B — person entity di masa depan

**Struktur:**

```
person (id uuid PK, external_influencer_id text, display_name, created_at)
   │ 1:N
kol_directory (+ person_id uuid NULL FK → person(id))     ← kolom baru, nullable
   │
kol_attribute_map (person_id  ATAU  kol_directory_id)
```

| | |
|---|---|
| **Kelebihan** | Atribut benar-benar per orang · kurasi sekali untuk semua platform · tempat sah untuk `influencer_no_ktp`, `influencer_email` |
| **Kekurangan** | Tabel + kolom baru · butuh proses seeding & review · `influencer_id` ada di **L0 raw** (bukan master), bertipe `text`, tanpa constraint |
| **Risiko** | **T4 mencampur orang** → seeding buta menggabungkan 157 akun yang bukan satu orang · hanya **1 import batch**, stabilitas lintas-import belum teruji · 510 baris tanpa `kol_directory_id` |
| **Dampak ke Style/Personality** | Kalau `kol_attribute_map` sejak awal memakai **FK terpisah** (`kol_directory_id`), menambah `person_id` nullable nanti **tidak merusak** yang sudah ada — migrasi bertahap. Kalau atribut ditaruh sebagai kolom/array di `kol_directory`, migrasi jadi mahal |

## 5.5 REKOMENDASI

**Opsi A sekarang, dengan jalur ke B dijaga terbuka.**

| # | Alasan |
|---|---|
| 1 | **`influencer_id` belum lolos validasi untuk jadi kunci identitas.** 38 dari 152 grup multi-akun terkontaminasi, dan satu bucket mencampur 43 orang |
| 2 | **Hanya 1 import batch** — stabilitas lintas-import belum teruji |
| 3 | Opsi A **tidak menutup** jalan ke B: FK terpisah membuat penambahan `person_id` nanti murah |
| 4 | Opsi A **tidak membuang** nilai `influencer_id` — ia tetap dipakai untuk saran kurasi (T1/T2) dan laporan QA |
| 5 | Membuat `person` sekarang berarti memutuskan aturan merge sebelum datanya bersih — kesalahan yang mahal untuk dibatalkan |

⚠️ **Tetap sesuai keputusan #5 lo** — `influencer_id` **memang** jadi dasar
pengelompokan, tapi *"setelah validasi data"*. Validasinya sudah gue lakukan,
dan hasilnya: **layak untuk 114 dari 152 grup, karantina untuk 38.** Gue tidak
melakukan merge apa pun.

---

# 6. WHAT MATTERS MOST — preference / ranking criteria

Diperlakukan sebagai **kriteria preferensi user**, bukan atribut permanen KOL.

## 6.1 Source per kriteria

| Criterion | Existing source | Real/Mock | Bisa dipakai sekarang? | Logic |
|---|---|---|---|---|
| **Strong Engagement** | `public.kol_directory.engagement_rate` — **1.736 / 7.432 (23,4%)** | ✅ **REAL** | ✅ **YA** | Chip UI existing: **Good ≥3% / High ≥5.5%**. Register `filter.xlsx` #1 **FINAL/APPROVED**. ⚠️ outlier sampai **223,41%** — perlu clamp |
| **High Audience Quality** | `feature.ig/tt_audience_analysis.audience_quality_score` + `authenticity_score`; mirror di `l2_gold.kol_profile_card` — **27 / 7.432 (0,36%)** | ✅ **REAL** | ⚠️ **YA, cakupan 0,36%** | Chip UI: **High 85+ / Good 75+ / Below 75**. UI menghitung `(auth + q) / 2`. Register #22 **FINAL/APPROVED** (label atas skor, skor tidak dihitung ulang) |
| **Consistent Performance** | **NOT FOUND** — sapuan `consist\|reliab\|stabil\|volatil\|cadence\|frequency` = **0 kolom di seluruh DB**. Proksi: `performance_stability` (11) · `post_frequency_reliability` (49) | ❌ **MOCK** — UI pakai `k.cons` = **hash dari creator id** | ❌ **TIDAK** | **Tidak ada logic yang sah.** Proksi terdekat `performance_stability` = STDDEV ER, **konsep berbeda** dari reliability |
| **Strong Company/Community** | **tidak ada kolom** | ❌ **MOCK** — UI: `community = er×9 + k.aff×3`, dan `k.aff` **tidak punya kolom DB** | ❌ **TIDAK** | **Tidak ada logic yang sah.** `k.aff` sendiri sudah ditandai F-5: *"definisikan atau buang"* |
| **High Reach** | `reach`: `unified_post.reach` **0/503** · `avg_reach` **0/27** · `campaign_kols.reach` 0 baris. Proksi: `avg_views` (30) · `view_to_follower_ratio` (22) | ⚠️ **PROKSI** | ⚠️ **hanya sebagai VIEWS**, bukan reach | Chip UI existing memang berbasis **views**: `150K+ / 300K+ avg views`. ⚠️ **`views ≠ reach`** — diperingatkan eksplisit di backlog |
| **Content Quality** | **tidak ada di DB, Excel, maupun frontend** | ❌ **BELUM ADA SOURCE** | ❌ **TIDAK** | **Tidak ada.** Kolom `KOL_Database.AM` ada isinya di Excel tapi **bobot 0, tanpa rumus**; 0 hit di kedua prototype |
| **Brand Safety** | tidak ada kolom `safety`/`risk`. Input proksi: `authenticity_score` 27 · `follower_quality_score` 27 · `verified_status` 931 · `paid_ratio` 48 | ❌ **BELUM ADA SOURCE** (definisi UI) / ⚠️ proksi tersedia | ❌ **TIDAK, sebagai "Brand Safety"** | UI: `(auth + posSent)/2` — `posSent` butuh sentiment, **`*_comments_analysis` 0 baris**. Excel CMP punya *integrity screen* 4-input (40/30/15/15) tapi **Excel sendiri menegaskan itu bukan brand safety** |

**Rekap: 2 bisa dipakai · 1 proksi (dengan peringatan) · 2 mock · 2 belum ada source.**

Sesuai instruksi lo, gue **tidak membuat formula** untuk Consistent Performance,
Community, Content Quality, maupun Brand Safety.

## 6.2 Bagaimana preference dikirim ke Discovery

**Rekomendasi: query parameter. Tanpa tabel persistence.**

### Bukti yang mendukung

| Bukti | Isi |
|---|---|
| Route Discovery | `docs/KOL_DISCOVERY_AUDIT.md:87` — *"route `kol-directory` hanya mengekspor **`GET`**. Tidak ada `POST`/`PUT`/`PATCH`"* |
| Prototype | **0** `fetch()` · **0** `/api/` · hanya 2 `localStorage` — pilihan kriteria hidup di state klien |
| Tabel preference di DB | sapuan `preference\|saved\|collection\|favorite\|shortlist\|bookmark\|setting` → **0 tabel** |
| Preseden fitur sejenis | `AUTOME_2_READINESS_AUDIT.md:141` — *"Saved List / Search / Collection / Favorite … **tak ada tabel** … semua state lokal"* |
| Preseden parameter | `num('minEr')`, `num('growthMin')`, `num('growthMax')`, `num('follMin')`, `query.category` — pola yang sudah dipakai |

Produk ini **belum pernah** mempersist pilihan user jenis apa pun. Membuat tabel
untuk What Matters Most akan jadi yang pertama — tanpa alasan yang terbukti.

### Bentuk yang diusulkan

```
GET /api/organizations/{id}/discover/kol
      ?matters=engagement,audience_quality
      &sort=match&dir=desc
```

| Aspek | Keputusan |
|---|---|
| Transport | **query parameter** `matters` — daftar `criteria_key`, dipisah koma |
| Vocabulary | **config di kode** — 7 baris, pola `IQ_GROUPS` yang sudah dipakai UI |
| Efek | menggeser **urutan** hasil (ranking), bukan menyaring keanggotaan |
| Persistence | **TIDAK ADA** |
| Tabel baru | **NOL** |

### Config vocabulary (di kode, bukan DB)

| `criteria_key` | Label UI | Kolom sumber | `readiness` |
|---|---|---|---|
| `strong_engagement` | Strong Engagement | `kol_directory.engagement_rate` | `ready` |
| `high_audience_quality` | High Audience Quality | `kol_profile_card.audience_quality_score` | `ready_low_coverage` |
| `consistent_performance` | Consistent Performance | — | **`missing`** |
| `strong_community` | Strong Company/Community | — | **`missing`** |
| `high_reach` | High Reach | `kol_profile_card.avg_views` *(proksi)* | **`proxy`** |
| `content_quality` | Content Quality | — | **`missing`** |
| `brand_safety` | Brand Safety | — | **`missing`** |

**Aturan wajib:** kriteria ber-`readiness = missing` **ditampilkan disabled
dengan alasannya**, tidak disembunyikan dan tidak diam-diam mengembalikan nol
hasil. Ini pola yang sudah diminta eksplisit di `README` workbook r50:
*"a filter that rests on one of those must ship disabled with its reason shown"*.

**Kapan tabel baru jadi perlu** (belum terbukti sekarang):

| Kalau… | Maka | Grain |
|---|---|---|
| Daftar 7 harus editable tanpa redeploy | master `what_matters_criteria` — **7 baris** | kriteria |
| Pilihan harus tersimpan & dipakai ulang per brand | `brand_evaluation_preference` | brand × kriteria — **diblokir**: `public.brand` 0 baris |

---

# 7. FINAL SCHEMA PROPOSAL

| Component | Existing/New | Table | Column/Relation | Purpose | Grain | Risk |
|---|---|---|---|---|---|---|
| EMV — Discovery | **Existing** | `feature.ig/tt_audience_analysis` | `emv` (ada) ← `avg_reach` (ada) | Estimasi nilai media pra-campaign | social_account | **Tinggi** — 3 input, 0 tersedia |
| EMV — campaign×KOL | **Existing** | `public.campaign_kols` | `emv` ← `reach` (sebaris) | EMV aktual per KOL | campaign × KOL | Sedang — tabel 0 baris |
| EMV — deliverable | **Existing** | `public.campaign_content_performance` | `emv` ← `reach` (sebaris) | EMV per konten per snapshot | deliverable × snapshot | Sedang |
| EMV — konstanta CPM & Multiplier | **New (bukan tabel)** | — | **config aplikasi** | Input formula | global / per platform | **Tinggi** — nilainya belum ada |
| CPE — campaign×KOL | **Existing** | `public.campaign_kols` | `deal_price ÷ total_engagement` | Biaya per engagement | campaign × KOL | Sedang — definisi `total_engagement` belum pasti |
| CPE — deliverable | **Existing** | `campaign_kol_deliverables` + `campaign_content_performance` | `subtotal ÷ total_engagement` | CPE per konten | deliverable | Sedang — `subtotal = unit_price × quantity` belum terbukti |
| CPE — Discovery | **Existing** | `l1_silver.unified_rate_card` | `fee ÷ engagement_akun` | CPE pra-campaign | KOL × post_type | Sedang — butuh propagasi L0→L1 + pilih `post_type` |
| CPV — semua level | **Existing** | `campaign_kols` · `campaign_content_performance` · `unified_rate_card` | `cost ÷ views × CPV_UNIT_FACTOR` | Biaya per view | campaign×KOL · deliverable · KOL | **Tinggi** — unit belum diputuskan (risiko 1.000×) |
| Style/Personality — master | **NEW** | **`kol_attribute`** | `kind`, `attribute_group`, `attribute_key`, `label`, `source_origin`, `sort_order`, `is_active`; unik `(kind, group, key)` | Taxonomy gabungan Excel+UI, **39 baris** | nilai atribut | **Rendah** — tabel referensi kecil, tidak direferensikan siapa pun |
| Style/Personality — mapping | **NEW** | **`kol_attribute_map`** | FK `kol_directory_id` → `kol_directory(id)`; FK `kol_attribute_id`; `assigned_by`, `assigned_at`; unik `(kol_directory_id, kol_attribute_id)` | KOL ↔ atribut, many-to-many | **akun (platform-level)** | **Sedang** — atribut per akun, bukan per orang; 114 KOL lintas-platform perlu kurasi 2× |
| Person identity | **Tidak dibuat sekarang** | *(kandidat `person`)* | *(kandidat `kol_directory.person_id`)* | Menggabungkan akun satu orang | orang | **Tinggi** — `influencer_id` T4 mencampur 43 orang; 1 batch saja |
| What Matters Most — vocabulary | **New (bukan tabel)** | — | **config di kode**, 7 kriteria | Daftar kriteria preferensi | kriteria | Rendah |
| What Matters Most — pilihan user | **Tidak ada** | — | **query parameter `matters=`** | Menggeser ranking | per-request | Rendah |
| Brand Personality + Brand Tone | **Tidak dibuat** | *(kandidat `public.brand`)* | 18 nilai | Atribut brand | brand | **Diblokir** — `public.brand` **0 baris** |

## A. Bisa pakai existing DB

| Kebutuhan | Tabel.kolom existing | Catatan |
|---|---|---|
| EMV (3 grain) | `feature.ig/tt_audience_analysis.emv` · `campaign_kols.emv` · `campaign_content_performance.emv` | 4 kolom sudah ada; **jangan tambah** |
| Reach | `campaign_kols.reach` · `campaign_content_performance.reach` · `avg_reach` | sudah ada, 0 terisi |
| Cost campaign×KOL | `campaign_kols.deal_price` + `currency` | |
| Cost deliverable | `campaign_kol_deliverables.subtotal`, `unit_price`, `quantity`, `rate_card_snapshot` | |
| Cost Discovery | `l1_silver.unified_rate_card.fee` ← **`l0_raw.kol_roster_import` 14 kolom harga (93,7%)** | sumber ada, propagasi belum |
| Engagement | `campaign_kols.total_engagement` · `campaign_content_performance.total_engagement` | |
| Views | `campaign_content_performance.views` · `l2_gold.post_metric.views` (397/503) · `avg_views` (30) | |
| Strong Engagement | `kol_directory.engagement_rate` (1.736) | |
| Audience Quality | `kol_profile_card.audience_quality_score` + `authenticity_score` (27) | |
| Filter Style/Personality | `kol_directory` sebagai anchor join | |

## B. Perlu master table baru

| Tabel | Baris | Kenapa benar-benar perlu |
|---|---:|---|
| **`kol_attribute`** | **39** | Sapuan 101 tabel: `%style%` dan `%personality%` = **0 tabel, 0 kolom**. Nilai harus punya rumah agar `Educational` di 3 grup berbeda tidak tertukar — dan itu butuh kunci `(group, value)`, yang tidak bisa dicapai kolom/array |

## C. Perlu junction/mapping table baru

| Tabel | Kenapa benar-benar perlu |
|---|---|
| **`kol_attribute_map`** | 1 KOL bisa punya banyak Style **dan** banyak Personality (requirement + sudah jadi bentuk di UI: chips multi-select, array `dna`/`comm`/`vis`). Junction dipilih di atas array `uuid[]` karena data kurasi manual butuh `assigned_by` / `assigned_at` yang array tidak bisa bawa |

## D. Tidak perlu table, cukup calculated query

| Item | Cara |
|---|---|
| **CPE** semua level | `cost ÷ NULLIF(engagement, 0)` — dua kolom sebaris (campaign×KOL), tanpa join |
| **CPV** semua level | `cost ÷ NULLIF(views, 0) × CPV_UNIT_FACTOR` — di grain campaign×KOL wajib agregasi |
| **CPM** | `cost ÷ NULLIF(reach\|followers, 0) × 1000` — **penyebut masih konflik** (Excel followers vs UI reach) |
| **7 kriteria What Matters Most** | dibaca dari kolom sumber saat query; **tidak disimpan** |
| Vocabulary 7 kriteria | config di kode |
| Konstanta CPM & Multiplier EMV | config aplikasi |

## E. Masih membutuhkan keputusan bisnis

| # | Keputusan | Memblokir |
|---:|---|---|
| E1 | **Nilai CPM** + granularitas (global/platform/tier) | EMV |
| E2 | **Nilai Multiplier** | EMV |
| E3 | **Sumber `reach`** — Insights API, atau bersihkan `estimated_reach` (2.164 baris reach > followers) | EMV, High Reach |
| E4 | **`CPV_UNIT_FACTOR`** — 1 atau 1000 | CPV — **risiko 1.000×** |
| E5 | **Definisi `total_engagement`** — `L+C` atau `L+C+S(+Saves)` | CPE |
| E6 | **`<ATURAN_SNAPSHOT>`** agregasi `campaign_content_performance` | EMV agregat + CPV campaign |
| E7 | **Mata uang** — $ atau IDR (order flow = integer rupiah) | semua metrik biaya |
| E8 | **`subtotal = unit_price × quantity`?** | CPE deliverable |
| E9 | **`post_type` mana** basis fee rate card + penanganan sentinel `1.000.000.000` & 8 harga < Rp1.000 | CPE/CPV Discovery |
| E10 | **Cost sebenarnya**: `deal_price` atau **negotiation table di app DB** (`guaranteed fee + performance fee`) | CPE, CPV |
| E11 | **`Demonstration` (UI)** — alias `Demonstrative`/`Demo`, atau nilai tersendiri | taxonomy: 39 atau 40 baris |
| E12 | **`visual_style` ikut atau tidak** (7 nilai, hanya dari UI) | taxonomy |
| E13 | **UI menggabungkan Style+Personality jadi 1 chip** — apakah UI dipecah jadi 4 grup? | kontrak filter |
| E14 | **Penyaringan `influencer_id`** — T1+T2 diterima, T3+T4 dikarantina? | person identity |
| E15 | **`Content Quality` memang dibutuhkan?** | 1 dari 7 kriteria |
| E16 | **`Brand Safety`** — definisi mana | 1 dari 7 kriteria |
| E17 | **`k.aff`** — didefinisikan atau dibuang | Community + 5 metrik turunan |

---

# 8. CONTOH DATA — STYLE/PERSONALITY (konseptual, bukan data sungguhan)

```
PERSON (konseptual — TIDAK ada tabelnya di DB)
  l0_raw.kol_roster_import.influencer_id = '1'          tier T2
        │
        ├── kol_directory  id=44be…  platform=instagram  username=tasyakamila
        │         │
        │         └── kol_attribute_map
        │               ├── content_style.storytelling
        │               ├── content_style.educational
        │               ├── communication_style.conversational
        │               └── creator_personality.relatable
        │
        └── kol_directory  id=8025…  platform=tiktok     username=tasyakamilaofficial
                  │
                  └── kol_attribute_map
                        └── (KOSONG — harus dikurasi terpisah)
```

**Isi tabel secara konseptual:**

`kol_attribute` (master, 4 dari 39 baris):

| id | kind | attribute_group | attribute_key | label | source_origin |
|---|---|---|---|---|---|
| a1… | style | `content_style` | `content_style.storytelling` | Storytelling | `excel+ui` |
| a2… | style | `content_style` | `content_style.educational` | Educational | `excel+ui` |
| a3… | style | `communication_style` | `communication_style.conversational` | Conversational | `excel` |
| a4… | personality | `creator_personality` | `creator_personality.relatable` | Relatable | `excel+ui` |

`kol_attribute_map` (4 baris untuk akun Instagram):

| kol_directory_id | kol_attribute_id | assigned_by | assigned_at |
|---|---|---|---|
| 44be… (tasyakamila / IG) | a1… Storytelling | u1… | 2026-09-20 09:14 |
| 44be… | a2… Educational | u1… | 2026-09-20 09:14 |
| 44be… | a3… Conversational | u1… | 2026-09-20 09:15 |
| 44be… | a4… Relatable | u1… | 2026-09-20 09:15 |

**Cara relasinya bekerja:**

| Pertanyaan | Jalur |
|---|---|
| Atribut satu akun | `kol_directory` → `kol_attribute_map` → `kol_attribute` |
| Filter "Content Style = Storytelling" | `EXISTS` pada map, difilter `attribute_group='content_style'` |
| **Menemukan akun saudara** | `kol_directory` → `l0_raw.kol_roster_import.kol_directory_id` → ambil `influencer_id` → cari `kol_directory_id` lain dengan `influencer_id` yang sama **DAN tier T1/T2** |
| Menyalin atribut ke saudara | UI **menawarkan**; tidak otomatis; user yang menyetujui |

⚠️ Dalam contoh ini akun TikTok **sengaja dibiarkan kosong** — itu konsekuensi
nyata Opsi A yang harus terlihat, bukan disembunyikan. Kalau nanti Opsi B
dijalankan, `person_id` menggantikan `kol_directory_id` di map dan kedua akun
berbagi satu set atribut.

---

# 9. PENUTUP

## READY FOR IMPLEMENTATION

Sudah cukup jelas untuk mulai dibuat — nol keputusan bisnis tersisa.

| # | Item | Kenapa siap |
|---:|---|---|
| **R1** | **Master `kol_attribute` (39 baris) + junction `kol_attribute_map`** | Taxonomy gabungan sudah final dan ber-jejak asal (§4.3). Kunci mapping terjawab bukti. Dua tabel baru yang tidak direferensikan siapa pun dan tidak disentuh asset Dagster. ⚠️ E11 (`Demonstration`) & E12 (`visual_style`) memengaruhi **isi**, bukan **struktur** — bisa jalan lalu tambah baris |
| **R2** | **Endpoint filter Style/Personality** — `EXISTS` + `attribute_group` | 7.432 baris, seq scan murah, tanpa index |
| **R3** | **Config vocabulary 7 kriteria** + `readiness` per kriteria | Nol tabel; berguna apa pun hasil E15/E16 |
| **R4** | **Query param `matters=`** untuk Discovery | Mengikuti pola `minEr`/`growthMin` yang sudah ada; nol persistence |
| **R5** | **Ranking pakai Strong Engagement & Audience Quality** dari kolom existing | Keduanya `FINAL/APPROVED` di register |
| **R6** | **Laporan QA**: `influencer_id` sama tapi atribut beda; dan daftar tier T1–T4 | Read-only; menyiapkan bahan E14 |
| **R7** | **Guard NULL** di semua metrik biaya (`NULLIF` penyebut, input kosong → NULL) | Aturan yang konsisten di Excel + backlog |

## NEEDS MENTOR/PRODUCT CONFIRMATION

Diurutkan dari yang paling memblokir:

| # | Pertanyaan | Memblokir | Kenapa gue tidak putuskan |
|---:|---|---|---|
| **1** | **`CPV_UNIT_FACTOR` = 1 atau 1000?** | CPV | Skor 2–2 antar sumber; **salah = salah 1.000×** |
| **2** | **Nilai CPM + granularitas** (global/platform/tier) | EMV | 0 kolom, 0 nilai di seluruh repo & DB |
| **3** | **Nilai Multiplier** | EMV | idem, bahkan lebih kosong |
| **4** | **Definisi `total_engagement`** — `L+C` atau `L+C+S(+Saves)` | CPE | Register sendiri tidak konsisten |
| **5** | **Sumber `reach`** — Insights API atau bersihkan `estimated_reach` | EMV, High Reach | 2.164 baris reach > followers |
| **6** | **Cost sebenarnya** — `deal_price` atau negotiation table di app DB | CPE, CPV | Tabel negotiation **tidak ada di `kol`** |
| **7** | **`<ATURAN_SNAPSHOT>`** agregasi `campaign_content_performance` | EMV agregat, CPV campaign | Tanpa ini `SUM` akan double-count |
| **8** | **Mata uang** — $ atau IDR | semua biaya | Discrepancy sudah tercatat |
| **9** | **Penyaringan `influencer_id`**: terima T1+T2, karantina T3+T4? | person identity | 38 grup terkontaminasi |
| **10** | **`Demonstration`** alias atau nilai baru? · **`visual_style`** ikut? | isi taxonomy | Excel dan UI beda |
| **11** | **UI dipecah jadi 4 grup filter?** | kontrak filter | UI sekarang menggabungkan Style+Personality jadi 1 chip |
| **12** | **`post_type` basis fee** + sentinel `1.000.000.000` + 8 harga < Rp1.000 | CPE/CPV Discovery | |
| **13** | **`subtotal = unit_price × quantity`?** | CPE deliverable | 0 baris, tidak bisa dibuktikan |
| **14** | **`Content Quality` dibutuhkan?** · **`Brand Safety` definisi mana?** · **`k.aff` didefinisikan atau dibuang?** | 3 dari 7 kriteria | Nol source |

## PROPOSED NEW TABLES

**Dua. Tidak lebih.**

| # | Tabel | Baris awal | Grain | Kenapa tidak bisa pakai existing |
|---:|---|---:|---|---|
| 1 | **`kol_attribute`** (master) | **39** | nilai atribut | Sapuan 101 tabel: `%style%`/`%personality%` = 0 tabel, 0 kolom. Butuh kunci `(group, value)` agar `Educational` di 3 grup tidak tertukar |
| 2 | **`kol_attribute_map`** (junction) | tumbuh | akun × atribut | Many-to-many; array `uuid[]` tidak bisa bawa `assigned_by`/`assigned_at` |

**Yang gue TIDAK usulkan** (dan alasannya):

| Ditolak | Alasan |
|---|---|
| Kolom `emv`/`cpe`/`cpv` baru | `emv` sudah ada 4×, `cpe` 2×; `cpv` turunan murni. **Test guard aktif** |
| Tabel `metric_config` untuk CPM/Multiplier | Tabel baru untuk 2 angka yang nilainya belum ada. Config aplikasi dulu |
| Tabel `what_matters_criteria` | Fungsi = preference; nol persistence di seluruh produk |
| Tabel `person` | `influencer_id` belum lolos validasi; 1 batch saja |
| Tabel brand personality/tone | `public.brand` 0 baris |
| Kolom style/personality di `kol_profile_card` | Di-regenerate asset Dagster; test guard juga melarang `style` |
| VIEW untuk CPE/CPV | DB ini **0 view**; memperkenalkan yang pertama = keputusan konvensi tim |
| Index tambahan | 7.432 baris, hanya PK sekarang, seq scan murah |

## NO NEW TABLE NEEDED

| Item | Cukup dengan |
|---|---|
| EMV (3 grain) | 4 kolom `emv` existing + config CPM/Multiplier |
| CPE (3 level) | calculated dari `deal_price`/`subtotal`/`fee` ÷ `total_engagement` |
| CPV (3 level) | calculated + `CPV_UNIT_FACTOR` |
| CPM | calculated — penyebut masih konflik |
| 7 kriteria What Matters Most | config di kode + query param `matters=` |
| Nilai per kriteria | dibaca dari kolom sumber saat query |
| Person grouping | `l0_raw.kol_roster_import.influencer_id` sebagai alat bantu UI/QA, **bukan FK** |
| Rate card | propagasi `l0_raw.kol_roster_import` → `unified_rate_card` (tabel tujuan sudah ada) |

## RISKS

Diurutkan dari paling besar:

| # | Risiko | Dampak | Mitigasi |
|---:|---|---|---|
| **1** | **Salah unit CPV — 1.000×** | Angka biaya salah tiga digit di UI dan laporan | `CPV_UNIT_FACTOR` **wajib**, tanpa default; setiap nilai membawa field `unit`; label UI diturunkan dari `unit` |
| **2** | **Mengarang CPM/Multiplier** supaya EMV "jalan" | Angka EMV yang terlihat kredibel tapi tidak bisa dipertanggungjawabkan — dan begitu masuk laporan, sulit dicabut | Biarkan `emv` NULL. Test `test_db_emv_cpe_tetap_null_selama_rate_card_kosong` sudah menegakkan ini |
| **3** | **Menggabungkan orang berdasarkan `influencer_id` tanpa penyaringan** | **157 akun di T4 digabung padahal bukan satu orang** (`8372` = 43 orang berbeda). Atribut satu orang bocor ke orang lain | Opsi A: jangan jadikan FK. Kalau ke Opsi B: hanya T1+T2, T2 lewat review manual |
| **4** | **Memakai `campaign_orders.total_amount` sebagai biaya KOL** | CPE/CPV membengkak — mencakup fee 8% + pajak 11% + beberapa creator sekaligus | Sudah dilarang eksplisit di desain |
| **5** | **Double-count `snapshot_date`** | EMV & CPV campaign membesar berlipat sesuai jumlah snapshot | `<ATURAN_SNAPSHOT>` wajib diisi sebelum agregasi apa pun |
| **6** | **Menyamakan `views` dengan `reach`** | "High Reach" sebenarnya mengukur views; EMV berbasis views bukan reach | Backlog memperingatkan eksplisit; tandai proksi di UI |
| **7** | **Menampilkan proksi 4-input sebagai "Brand Safety"** | Klaim keamanan merek tanpa satu pun pembacaan content-risk | Wajib dilabeli *integrity screen* |
| **8** | **Cakupan sangat rendah dianggap representatif** | Audience Quality **27 / 7.432 (0,36%)**; median_views 30; v2f 22 | Tampilkan cakupan di samping angkanya |
| **9** | **Outlier ER 223,41%** masuk ranking | Kreator dengan ER rusak naik ke puncak | Clamp atau bersihkan sumber dulu |
| **10** | **Atribut per akun dianggap per orang** | 114 KOL lintas-platform bisa punya label berbeda antar platform | Dokumentasikan di `COMMENT ON COLUMN`; laporan QA |
| **11** | **Rate card L0 dipropagasi tanpa dibersihkan** | Sentinel `1.000.000.000` dan 8 harga < Rp1.000 merusak rata-rata | Bersihkan saat propagasi, bukan sesudah |
| **12** | **Memakai `k.aff` / `k.cons`** | Keduanya mock (`k.cons` = hash creator id) | Jangan dipakai sampai F-5 diputuskan |

## RECOMMENDED IMPLEMENTATION ORDER

Dari paling aman ke paling berisiko. **Tidak satu langkah pun dimulai sebelum
approval.**

### Tahap 0 — nol perubahan DB

| # | Pekerjaan | Output |
|---:|---|---|
| 0.1 | Bawa **14 pertanyaan** ke mentor dalam satu sesi (prioritas #1–#5) | Jawaban tertulis |
| 0.2 | Laporan QA read-only: tier T1–T4 `influencer_id`, dan 17 baris non-numerik | Bahan keputusan #9 |
| 0.3 | Sampel `l0_raw.kol_roster_import` vs rate card asli — validasi 14 kolom harga | Bahan keputusan #12 |
| 0.4 | Konfirmasi ke backend: `subtotal = unit_price × quantity`? · negotiation table? | Bahan #6, #13 |

### Tahap 1 — dua tabel baru, aditif, tidak menyentuh apa pun

| # | Pekerjaan | Prasyarat |
|---:|---|---|
| 1.1 | `kol_attribute` + isi 39 baris | approval + #10 |
| 1.2 | `kol_attribute_map` | 1.1 |
| 1.3 | Endpoint filter Style/Personality | 1.2 |
| 1.4 | UI: kurasi + tawaran "salin ke akun saudara (T1/T2)" — **tidak otomatis** | 1.3, #9 |
| 1.5 | **Test**: unik `(kind, group, key)` · unik `(kol_dir, attr)` · `Educational` bisa hidup di 3 grup · filter mengembalikan hasil benar | 1.3 |

Aman karena: dua tabel baru tanpa referensi masuk, tidak mengubah satu kolom
existing, tidak disentuh asset Dagster mana pun.

### Tahap 2 — nol perubahan DB

| # | Pekerjaan | Prasyarat |
|---:|---|---|
| 2.1 | Config 7 kriteria + `readiness` | — |
| 2.2 | Query param `matters=`; kriteria `missing` **ditampilkan disabled dengan alasannya** | 2.1 |
| 2.3 | Ranking pakai Strong Engagement + Audience Quality; tampilkan cakupan | 2.2 |
| 2.4 | **Test**: kriteria `missing` tidak pernah diam-diam mengembalikan nol hasil | 2.2 |

### Tahap 3 — biaya, setelah jawaban ada

| # | Pekerjaan | Prasyarat |
|---:|---|---|
| 3.1 | Tetapkan `CPV_UNIT_FACTOR` di config (**tanpa default**) | **#1** |
| 3.2 | CPE campaign sebagai query: `deal_price ÷ NULLIF(total_engagement,0)` | #4, #6 |
| 3.3 | CPV campaign + `<ATURAN_SNAPSHOT>` | #1, #7 |
| 3.4 | **Test**: setiap nilai CPV membawa `unit`; NULL propagation; **uji faktor 1000 secara eksplisit** | 3.1–3.3 |
| 3.5 | Propagasi rate card L0 → `unified_rate_card`, dengan pembersihan sentinel | #12 |
| 3.6 | CPE/CPV Discovery | 3.5 |

### Tahap 4 — EMV, paling akhir

| # | Pekerjaan | Prasyarat |
|---:|---|---|
| 4.1 | Konstanta CPM + Multiplier di config | **#2, #3** |
| 4.2 | EMV per `campaign_content_performance` | 4.1, #7 |
| 4.3 | Agregasi → `campaign_kols.emv` | 4.2 |
| 4.4 | EMV Discovery | 4.1 + `reach` (#5) |
| 4.5 | **Test**: `emv` tetap NULL saat konstanta/`reach` tidak ada; tidak ada kolom `emv` baru di kartu L2 | 4.2 |

### Tahap 5 — person entity, opsional

| # | Pekerjaan | Prasyarat |
|---:|---|---|
| 5.1 | Review manual 53 grup T2 | #9 |
| 5.2 | Kalau disetujui: `person` + `kol_directory.person_id` nullable | 5.1 |
| 5.3 | Pindahkan `kol_attribute_map` ke `person_id` bertahap | 5.2 |

---

## STATUS SESI

| | |
|---|---|
| Query DB | ~12 `SELECT` (validasi `influencer_id`, tier, outlier, cost inventory) |
| INSERT / UPDATE / DELETE | **0** |
| CREATE / ALTER / DROP | **0** |
| Migration | **0** |
| Tabel dibuat | **0** |
| Perubahan source code | **0** |
| Database disentuh | **`kol` saja** |
| File ditulis | `docs/KOL_FINAL_DESIGN.md` (dokumen ini) |
| Formula yang gue karang | **Nol** |
| Keputusan bisnis yang gue ambil | **Nol** — 14 diserahkan |

**READ-ONLY DESIGN ONLY. Menunggu review mentor/backend.**
