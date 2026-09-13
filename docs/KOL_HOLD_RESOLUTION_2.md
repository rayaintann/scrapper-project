# RESOLUSI HOLD #2 — EMV · CPE/CPV · Style & Personality · What Matters Most

**Lanjutan** `KOL_HOLD_RESOLUTION.md`.
**Tanggal:** 13 September 2026 · DB **`kol`** @ `10.100.14.216` · `transaction_read_only = on`.
**Sifat:** READ-ONLY. Nol DDL, nol DML, nol migration, nol perubahan source code.

---

## 0. TEMUAN YANG MENGUBAH GAMBARAN — baca dulu

Tiga hal yang gue temukan sesi ini dan belum pernah tercatat di audit mana pun.

### 0.1 Ada register status internal yang otoritatif: `docs/filter.xlsx`

Sheet **`Filter Mapping`** — 34 item, tiap baris punya `Status`, `Definisi`,
`Kalkulasi / Logic`, `Source Schema/Table/Column`, `Data Coverage`, `Notes`.
Sheet `Validation` memverifikasi dirinya sendiri terhadap `information_schema`.

**24 item berstatus `FINAL / APPROVED`** dengan formula lengkap (ER, Growth,
Avg/Median Views, V2F, L2V, Paid Ratio, Share Rate, Save Rate, Audience
Interest/Location, Content Topic/Format, Viral Frequency, Rising Creator, Post
Frequency, Audience Quality, Performance Stability, Monitoring Priority, dll).

**7 item berstatus `HOLD`**, dan semuanya berbunyi sama —
*"Kalkulasi / Logic = Belum ada -- tidak diimplementasikan"*:

| No | Filter | Definisi (apa adanya) | Notes — apa yang dibutuhkan |
|---:|---|---|---|
| 25 | Age | "Rentang umur KOL." | "source age yang valid dari mentor. **Tidak boleh ditebak** dari username, display name, maupun follower count" |
| 26 | Brand Fit | "Seberapa cocok KOL dengan suatu brand." | "faktor + bobot + scoring yang disepakati" |
| **27** | **EMV** | **"Estimasi nilai media dari eksposur KOL."** | **"rate card + formula"** |
| **28** | **CPE** | **"Biaya per engagement."** | **"biaya campaign + definisi engagement yang dipakai"** |
| **29** | **CPV** | **"Biaya per view."** | **"biaya campaign + definisi view"** |
| **30** | **Content Style & Personality** | **"Taxonomy gaya dan kepribadian konten KOL."** | **"kategori style/personality + metode klasifikasi"** · Coverage: **"Tidak ada taxonomy final"** |
| 32 | Update Frequency | — | "Belum ada policy" |

**Ini menutup perdebatan soal status:** di register proyek sendiri, keempat hal
yang lo minta gue selesaikan **memang belum punya formula yang disetujui**.
Jadi tugas gue bukan menemukan formula yang tersembunyi — tapi memastikan
apakah ada bukti teknis yang cukup untuk mengusulkannya, dan di mana buktinya
berhenti.

⚠️ Satu catatan yang harus gue sampaikan: baris 30 menulis **"Tidak ada taxonomy
final"**. Lo menyatakan Excel berisi taxonomy yang harus dipakai. Register ini
tidak menganggapnya final. Karena lo yang menetapkan sebagai requirement bisnis,
gue pakai Excel — tapi perbedaan itu perlu lo ketahui, bukan gue diamkan.

### 0.2 Rate card TERNYATA ADA di `kol`, di L0 — klaim "0 baris di L0" itu SALAH

Audit sebelumnya (termasuk milik gue) menyatakan rate card *"bukan gap ETL — 0
baris di L0 sekalipun, tidak ada data masuk"*. **Itu keliru.**

```
l0_raw.kol_roster_import                → 7.718 BARIS   ✅
  14 kolom harga (text): reel_price, feed_video_price, feed_photo_price,
  story_price, live_price, host_price, photoshoot_price, comment_price,
  link_in_bio_price, tap_link_price, story_session_price,
  live_attendance_price, owning_asset_price, other_price

l0_extra.ig_rate_card                   → 0
l0_extra.tt_rate_card                   → 0
l0_harmonization.instagram_rate_card    → 0
l0_harmonization.tiktok_rate_card       → 0
l1_silver.unified_rate_card             → 0
```

Keterisian (hasil `SELECT` gue sendiri):

| Kolom | Terisi | **> 0** |
|---|---:|---:|
| seluruh 14 kolom harga | 7.496 / 7.718 (97,1%) | — |
| `feed_video_price` | 7.496 | **4.345** (56,3%) |
| `reel_price` | 7.496 | **2.898** (37,5%) |
| `feed_photo_price` | 7.496 | 685 |
| `story_price` | 7.496 | 674 |
| `live_price` | 7.496 | 223 |
| **≥ 1 harga > 0** | — | **7.231 / 7.718 = 93,7%** |

Nilainya IDR nyata (`500000.0`, `700000.0`, `150000.0`, …), seluruhnya numerik
(0 baris non-numerik). Dan tabel ini punya **`kol_directory_id`**,
`agency_kol_account_id`, `social_account_id` — jadi **bisa di-join langsung**.

Dua catatan kualitas yang harus ikut dibawa:
- **Sentinel `1.000.000.000` ada** (1 baris di `feed_video_price`) — persis yang
  diperingatkan backlog.
- 8 baris ber-harga antara 1 dan 1.000 (`min = 300`) — terlalu rendah untuk
  harga nyata.

**Implikasi:** blocker rate card **bukan** "tidak ada sumber", melainkan
**propagasi L0 → L1 belum jalan** + keputusan `post_type` mana yang jadi basis.
Itu masalah yang jauh lebih murah, dan mengubah status CPE/CPV dari MISSING
menjadi PARTIAL.

### 0.3 `estimated_reach` ada 96,2% — tapi terkontaminasi, dan penolakannya sah

`l0_raw.kol_roster_import` juga punya `estimated_reach`, `est_views`,
`estimated_engagement_rate`, `est_erb`, `influencer_gender`, `influencer_no_ktp`,
`size`, `size_category`.

| Kolom | Terisi |
|---|---:|
| `estimated_reach` | 7.494 · **> 0: 7.426 (96,2%)** |
| `est_views` | 7.496 |
| `estimated_engagement_rate` | 7.492 |
| `influencer_gender` | 3.133 |
| `influencer_no_ktp` | **183** ← sebab `creator_age` hanya 27 |

Sekilas ini seperti membuka `reach` untuk EMV. **Tidak.**
`FEATURE_METRICS_BACKLOG.md:236` sudah menolaknya dengan alasan, dan gue
**verifikasi ulang sendiri** — hasilnya mengonfirmasi, bahkan lebih buruk:

| `platform` | Baris | Rasio reach/follower (avg) | Rasio (median) | **reach > followers** |
|---|---:|---:|---:|---:|
| `0` | 3.282 | 91,9× | 0,400 | 14 |
| `1` | 3.879 | 12,2× | **1,494** | **2.164** |

Median 1,494 berarti separuh baris mengklaim reach **1,5× lebih besar dari
jumlah follower**-nya. Rata-rata 91,9× jelas outlier ekstrem. Backlog menyebut
560 baris bermasalah; ukuran gue **2.164**.

Dan `influencer_gender` memperkuat diagnosis *CSV column shift*: nilainya
`1` (2.588) dan `0` (542), tapi juga `Kota Jkt Utara`, `bca`, dan
`910493535412000` — isi kolom lain yang bergeser ke sini.

**Kesimpulan: `estimated_reach` adalah kandidat sumber yang menunggu
pembersihan, BUKAN solusi.** Gue tidak memakainya.

---

# 1. EMV — HASIL PENCARIAN MENYELURUH

Yang gue sapu: seluruh `*.py`, `*.md`, `*.sql`, `*.ps1`, 7 file `*.xlsx`,
kedua prototype HTML (1,57 MB), `migrations/`, `tests/`,
`orchestration/`, **git history (15 commit, `--all --name-only`)**, dan
`information_schema` 101 tabel.

## 1.1 Evidence EMV yang ditemukan

| # | File · lokasi | Formula / value | Konteks | Reliable? |
|---:|---|---|---|---|
| **E1** | `migrations/FEATURE_METRICS_BACKLOG.md:249` | **`reach × CPM ÷ 1000 × multiplier`** | Baris tabel spesifikasi metrik. Rumah kolom `feature.{ig,tt}_audience_analysis.emv`; Sumber `avg_reach` + konstanta CPM; Status **BLOCKED + NEED CONFIRMATION**; "Perlu migration ❌ kolom sudah ada" | ✅ **Paling reliable** — satu-satunya formula tertulis eksplisit, di dokumen spesifikasi repo |
| E2 | `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md:336` | idem | Kamus kolom: `emv \| numeric \| L2 METRIC (planned) \| UI k.emv` | ✅ kutipan E1 |
| E3 | `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md:862` | idem | + "pencarian `%cpm%`, `%benchmark%`, `%multiplier%`, `%coefficient%`, `%formula%` di 7 schema: **0 hasil**" | ✅ kutipan E1 + bukti ketiadaan |
| **E4** | `docs/filter.xlsx` → `Filter Mapping` r28 | **tidak ada formula** | Status **HOLD**; Definisi "Estimasi nilai media dari **eksposur** KOL"; Notes "Dibutuhkan: **rate card + formula**" | ✅ **Register status otoritatif** |
| E5 | `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md:1312` | — | "`*_audience_analysis.emv` \| BLOCKED \| tetap BLOCKED \| butuh `avg_reach` + konstanta CPM" | ✅ |
| E6 | `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md:1450` | — | Open issue #3: "**Konstanta CPM untuk `emv` tidak ada di database**… Perlu keputusan bisnis" | ✅ |
| **E7** | `orchestration/kol_orchestration/assets/audience.py:65, 476, 580, 855` | **sengaja NULL** | Di dalam `INSERT`: `-- SENGAJA tidak disebut (tetap NULL): active_hours_heatmap, avg_reach, cpe, emv`. Alasan: *"butuh reach/biaya kampanye, di luar jalur ini"* | ✅ **Bukti kode produksi** |
| **E8** | `tests/test_calculated_metrics.py:372` | **larangan kolom** | `terlarang = ("brand_fit","brand_fit_score","partnership_score","emv","cpe","cpv","estimated_media_value")` — test gagal bila nama itu jadi kolom di `l2_gold.kol_profile_card` | ✅ **Guard aktif** |
| E9 | `tests/test_calculated_metrics.py:385` | — | `test_db_emv_cpe_tetap_null_selama_rate_card_kosong`: assert `count(cpe)+count(emv)==0` selama `unified_rate_card` kosong | ✅ |
| E10 | `docs/filter.xlsx` → `Validation` r7 | — | "HOLD tidak terimplementasi \| PASS \| Tidak ada kolom brand_fit/emv/cpe/cpv/age/style di `kol_profile_card`; dijaga `test_db_metrik_blocked_tidak_punya_kolom`" | ✅ |
| **E11** | `app/AUTOME_2.html:609–617` | `emv:'$184K'`, `'$132K'`, `'$98K'`, `'$156K'`, `'$74K'`, `'$140K'`, `'$102K'`, `'$88K'`, `'$12K'` | **Literal hardcoded** di data sample 9 creator. **Nol formula client-side** | ❌ **MOCK** |
| E12 | `app/AUTOME_2.html:862, 704, 3370` | — | EMV sebagai **opsi sort** (`['emv','EMV']`), **kolom tabel** (`dirCols.emv=true`), dan formatter | ⚠️ Prototype — bukti **kebutuhan UI**, bukan formula |
| **E13** | `app/Autometric-KOL-Module.html:1796–1809` | seluruh nilai `emv:'—'` | Tabel campaign tracking: `alloc, pay, sched, appr, stage, reach, impr, eng, emv, roas, score` — **pemetaan 1:1 ke `campaign_kols`** | ⚠️ Prototype — bukti **grain campaign × KOL** |
| E14 | `docs/deliv.xlsx` → DELIVERABLES r132 | — | "Dropdown sorting berdasarkan campaign, brand fit, followers, reach, ER, authenticity, **EMV**, posts, dan nama" | ⚠️ katalog UI |
| E15 | `docs/brand_style_personality.xlsx` → DB vs Hardcode r2 | — | "Can support brand-level EMV/CPV" — pernyataan kelayakan | ❌ bukan definisi |
| E16 | `brand_match_master.xlsx` Discovery_Filters r42 · CMP_Hard_vs_Soft r54 | `EMV ÷ rate` | Estimated ROI memakai EMV **sebagai input** tanpa mendefinisikannya — **melingkar** | ❌ bukan definisi |
| E17 | `brand_match_master.xlsx` Lookup_Lists r146 | `CAL_VALUE_PER_ENG = 9.000` **IDR** | "Value per engagement (IDR) — earned value of one engagement, used by Estimated ROI". **Tidak pernah dinamai EMV** | ⚠️ kandidat, tanpa sumber angkanya |
| **E18** | git history | **nol** | 15 commit; `git log --grep` untuk emv/cpm/cpv/earned → **0 commit**; `git log --all --name-only` → **0 file** pernah ada yang menyangkut EMV | ✅ tidak ada formula legacy |
| **E19** | `information_schema`, 101 tabel | `emv` **4 kolom** · `cpe` 2 · **`cpm` 0** · **`cpv` 0** · **`multiplier` 0** · **`benchmark` 0** · **`coefficient` 0** | Sapuan `column_name ~* '(emv\|cpm\|cpv\|cpe\|multiplier\|benchmark\|coefficient\|earned)'` | ✅ **verifikasi langsung** |
| E20 | `app/AUTOME_2.html:2782` | `cpm = rate/reach*1000` | **Ini CPM sebagai OUTPUT** (biaya per mille yang dihitung), **bukan** konstanta CPM pasar yang jadi INPUT formula E1. Dua hal beda, nama sama | ⚠️ jangan tertukar |

### Uji rekayasa-balik nilai EMV di prototype

Gue uji apakah 9 nilai `emv` mock bisa diturunkan dari kolom lain:

| Pembagi | Rentang rasio | Spread | Stdev |
|---|---|---:|---:|
| **`emv / reach`** | 0,2786 – 0,3161 | **13,5%** | 0,0128 |
| `emv / followers` | 0,0743 – 0,1000 | 34,6% | 0,0097 |
| `emv / (reach × er)` | 0,0460 – 0,0754 | 64,0% | 0,0096 |

`emv/reach` mengelompok di **≈ 0,30** — konsisten dengan **bentuk** formula E1
(proporsional terhadap reach). Kalau dibaca sebagai
`reach × CPM ÷ 1000 × multiplier`, maka **CPM × multiplier ≈ 300** (dalam $ per
1.000 reach).

**Tapi ini tidak bisa dipakai**, tiga alasan:
1. Spread 13,5% berarti nilainya **tidak terhitung** — angka karangan yang
   dibulatkan, bukan output rumus.
2. Yang tersirat hanya **hasil kali** kedua konstanta. CPM dan multiplier
   **tidak bisa dipisahkan** dari satu rasio.
3. $300 CPM setara ~Rp 4,7 juta per 1.000 reach — tidak masuk akal sebagai CPM
   pasar Indonesia. Jadi angkanya kemungkinan besar sekadar "kelihatan wajar".

Gue laporkan sebagai **indikasi bentuk**, bukan sumber nilai.

## 1.2 Formula paling kuat berdasarkan evidence

**`EMV = Reach × CPM ÷ 1000 × Multiplier`** — dari **E1**.

Kekuatannya: satu-satunya formula yang **tertulis eksplisit**; ada di dokumen
spesifikasi repo; dikutip konsisten di 3 tempat lain (E2, E3, E5); rumah
kolomnya sudah dibuat sesuai itu; dan bentuknya **konsisten dengan data mock**
(emv ∝ reach).

Kelemahannya: penulisnya sendiri menandainya **BLOCKED + NEED CONFIRMATION**,
dan register `filter.xlsx` (E4) tetap mencatat EMV sebagai **HOLD tanpa
kalkulasi**.

**Gue tidak membuat formula baru, dan tidak menaikkan status E1 dari
"kandidat tertulis" menjadi "disetujui".**

## 1.3 Source CPM

**TIDAK ADA.** Dan ini terverifikasi tiga arah:

| Tempat dicari | Hasil |
|---|---|
| `information_schema` 101 tabel, pola `%cpm%` | **0 kolom** (verifikasi gue sendiri) |
| Excel — 7 file | Hanya `CPM` sebagai **metrik output** (`KOL_Database.AQ` = `Rate ÷ Followers × 1000`, filter `maxCpm`, preset "Lowest CPM"). **Nol** konstanta CPM pasar |
| Frontend | `cpm = rate/reach*1000` — **output**, bukan input (E20) |
| Backlog | "Konstanta CPM tidak ada di database… Perlu keputusan bisnis — **CPM per platform, per tier, atau global**" |
| Git history | 0 commit, 0 file |

**Bahkan granularitasnya belum diputuskan.** `NEEDS BUSINESS CONFIRMATION`.

## 1.4 Source multiplier

**TIDAK ADA — lebih kosong lagi daripada CPM.**

| Tempat dicari | Hasil |
|---|---|
| `information_schema` pola `%multiplier%`, `%coefficient%`, `%factor%` | **0 kolom** |
| Excel | Hanya **`Risk Multiplier`** (`Lookup_Lists` r137: High 0,6 / Medium 0,85 / Low 0,95 / None 1) — itu **pengali Brand Safety**, sama sekali bukan multiplier EMV |
| Kedua prototype HTML | **0 hit** untuk `multiplier`/`coefficient` (satu-satunya hit `factor` adalah "Two-factor authentication") |
| Dokumentasi | Disebut hanya sebagai bagian rumus E1, **tanpa nilai** |

`NEEDS BUSINESS CONFIRMATION`.

## 1.5 Grain EMV

Ini **bisa** dijawab dari schema — dan jawabannya: **EMV ada di tiga grain
sekaligus**, dan itu memang disengaja.

| Kolom | Grain | Bukti grain |
|---|---|---|
| `feature.ig_audience_analysis.emv` · `feature.tt_audience_analysis.emv` | **per akun** | PK/unik `social_account_id` |
| `public.campaign_kols.emv` | **per campaign × KOL** | FK `campaign_id` + `agency_kol_account_id`; UI-nya E13 |
| `public.campaign_content_performance.emv` | **per deliverable × `snapshot_date`** | FK `campaign_kol_deliverable_id` + kolom `snapshot_date`, `delta_views`, `delta_engagement`, `is_final` |

Alirannya yang masuk akal secara struktur:

```
campaign_content_performance.emv   (per deliverable, per snapshot)
        │  agregasi — aturannya BELUM ADA (is_final? snapshot terakhir? delta?)
        ▼
campaign_kols.emv                  (ringkasan per KOL dalam campaign)

feature.*_audience_analysis.emv    (estimasi pra-campaign, per akun)
```

Yang **per post**: tidak ada kolom `emv` di `l2_gold.post_metric` maupun
`l1_silver.unified_post`. Jadi grain post **tidak** dipakai.

## 1.6 Apakah sudah cukup aman untuk implementasi?

**BELUM. Jangan implementasi.**

| Input formula E1 | Status | Angka |
|---|---|---|
| `reach` | ❌ tidak tersedia | `unified_post.reach` **0 / 503** · `avg_reach` **0 / 27** · `campaign_kols.reach` 0 baris · proksi `estimated_reach` **terkontaminasi** (2.164 baris reach > followers) |
| `CPM` | ❌ tidak ada | 0 kolom di 101 tabel; granularitas belum diputuskan |
| `multiplier` | ❌ tidak ada | 0 kolom, 0 nilai, 0 sebutan bernilai |

**Nol dari tiga input tersedia.** Ditambah: register internal menandai EMV
`HOLD`, pipeline sengaja menulis NULL, dan ada test yang melarang penambahan
kolom. Semua sinyal mengarah ke satu arah yang sama.

**Kabar baiknya: tidak ada yang perlu dibangun.** Kolomnya sudah ada di 3 grain
yang tepat. Yang hilang murni definisi + data.

## 1.7 Persis apa yang masih harus dikonfirmasi

| # | Pertanyaan | Ke siapa | Kenapa tidak bisa dijawab dari repo |
|---:|---|---|---|
| Q1 | Formula E1 (`reach × CPM ÷ 1000 × multiplier`) **disetujui** sebagai definisi EMV? | Product/Mentor | Penulisnya sendiri menandai NEED CONFIRMATION; register `filter.xlsx` tetap HOLD |
| Q2 | Nilai **CPM** berapa, dan **per apa** — global / per platform / per tier? | Product | 0 kolom, 0 nilai di seluruh repo & DB |
| Q3 | Nilai **multiplier** berapa, dan apa artinya? | Product | 0 sebutan bernilai di mana pun |
| Q4 | `reach` pakai sumber apa: Insights API (belum ada) atau `estimated_reach` setelah dibersihkan? | Product + Data | `estimated_reach` 96,2% terisi tapi 2.164 baris reach > followers |
| Q5 | **Mata uang** — $ atau IDR? | Product | Prototype `$`, implementasi order **integer rupiah**; discrepancy ini **sudah tercatat** di `AUTOME_2_READINESS_AUDIT.md:137` ("prototype USD vs implementasi IDR") |
| Q6 | Aturan agregasi `campaign_content_performance` → `campaign_kols` | Product/BE | `snapshot_date` + `delta_*` + `is_final` ada, aturannya tidak |
| Q7 | EMV pra-campaign (`feature.*.emv`) dan EMV aktual (`campaign_kols.emv`) pakai formula **sama** atau beda? | Product | Keduanya bernama sama, grain beda; tidak ada dokumen yang membedakan |

---

# 2. CPE & CPV — FINALISASI GRAIN DAN COST SOURCE

## 2.1 Inventaris cost field — seluruh 39 kolom biaya di DB `kol`

Hasil sapuan `column_name ~* '(fee|price|amount|allocation|budget|subtotal|discount|tax)'`:

| Tabel.kolom | Tipe | Baris tabel | Grain | Terisi |
|---|---|---:|---|---|
| **`l0_raw.kol_roster_import`** — 14 kolom `*_price` | text | **7.718** | **KOL × jenis deliverable** | **7.231 (93,7%) punya ≥1 harga > 0** |
| `l0_extra.ig_rate_card.fee` · `tt_rate_card.fee` | numeric | **0** | KOL × post_type | — |
| `l0_harmonization.instagram_rate_card.fee` · `tiktok_rate_card.fee` | numeric | **0** | idem | — |
| `l1_silver.unified_rate_card.fee` | numeric | **0** | KOL × post_type | — |
| `l2_gold.kol_profile_card.rate_card_min_fee` / `_max_fee` | numeric | 1.978 | KOL | **0** |
| **`public.campaign_kols.deal_price`** (+ `currency`) | numeric | **0** | **campaign × KOL** | — |
| **`public.campaign_kol_deliverables.unit_price`** | numeric | **0** | **deliverable** | — |
| **`public.campaign_kol_deliverables.subtotal`** | numeric | **0** | **deliverable** | — |
| `public.campaign_kol_deliverables.rate_card_snapshot` | jsonb | 0 | deliverable | — |
| `public.campaign_orders.subtotal` · `platform_fee_pct` · `platform_fee_amount` · `tax_pct` · `tax_amount` · `discount_amount` · **`total_amount`** | numeric | **0** | **order** | — |
| `public.campaign_kol_payments.allocation` | numeric | 0 | payment | — |
| `public.campaigns.budget` | numeric | 0 | campaign | — |
| `public.payments.subtotal` · `platform_fee` · `agency_fee` · `tax` · `discount` | numeric | **0** | payment | — |

**Tidak ada tabel negotiation di `kol`.** Sapuan `negoti|offer|quote|fee|cart|
collection|saved|favorite|shortlist|bookmark|preference|setting` sebagai nama
tabel → hanya `public.campaign_orders` yang cocok (dari kata `order`).

⚠️ Ini penting: `AUTOME_2_READINESS_AUDIT.md:138` mencatat ada
**"tabel negotiation app"** dengan **"guaranteed fee + performance fee"** dan
implementasi `negotiation.ts` (785 baris) berstatus ✓. Tabel itu **ada di DB
aplikasi, bukan di `kol`**. Jadi kemungkinan besar **cost per-KOL yang
sebenarnya dinegosiasikan hidup di luar `kol`** — dan itu harus dikonfirmasi
sebelum `deal_price` ditetapkan sebagai sumber tunggal.

## 2.2 Apakah `campaign_orders.total_amount` memang biaya KOL?

**TIDAK. Itu total pembayaran order.** Dan ini bukan tafsir gue — ada bukti:

**`docs/AUTOME_2_READINESS_AUDIT.md:137`:**
> "Ordering / Cart / Checkout | tabel order app + **Midtrans** |
> **subtotal→promo→fee 8%→pajak 11%, integer rupiah** | 7 route
> `/discover/orders/*` + webhook | ✓ | **prototype USD vs implementasi IDR** |
> verifikasi field-by-field"

Empat hal yang dibuktikan baris ini:

1. **`total_amount` adalah nilai checkout** yang dibayar brand lewat Midtrans —
   bukan biaya satu KOL. Rantainya `subtotal → promo → platform fee 8% →
   pajak 11%`.
2. **Nilai `platform_fee_pct` = 8** dan **`tax_pct` = 11** — angka nyata.
3. **Mata uangnya IDR** (integer rupiah) di implementasi.
4. Discrepancy "prototype USD vs implementasi IDR" **sudah tercatat** sebagai
   item yang perlu diverifikasi field-by-field.

Struktur kolomnya sendiri mengonfirmasi: `campaign_orders` punya
`order_number`, `creators_count`, `deliverables_count`, `promo_code`,
`ordered_by`, `ordered_at`, `confirmed_at` — **bentuk dokumen transaksi**, satu
order mencakup **banyak** creator (`creators_count`).

**Jadi memakai `total_amount` sebagai cost CPE per KOL akan salah secara
konseptual** — ia mencampur fee platform + pajak + diskon dari beberapa creator
sekaligus. Gue tidak merekomendasikannya, dan sekarang alasannya berbasis bukti,
bukan preferensi.

## 2.3 Apakah ada implementasi/referensi lama yang memakai field-field itu?

**Pencarian di repo ini: nyaris tidak ada.**

| Yang dicari | Hasil |
|---|---|
| `deal_price` di `*.py`/`*.md`/`*.sql` | **0 hit** (selain dokumen gue sendiri) |
| `unit_price` · `subtotal` · `total_amount` · `allocation` | **1 hit** — `AUTOME_2_READINESS_AUDIT.md:137` (yang dikutip di §2.2) |
| `platform_fee` | idem, 1 hit |
| Git history | 0 commit menyentuh cost field |

Artinya: **belum ada satu pun implementasi di repo ini yang memakai cost field
campaign.** Referensi satu-satunya adalah baris readiness audit di atas, dan itu
menggambarkan flow order di repo aplikasi.

## 2.4 CPE — penentuan

### Perbandingan tiga definisi

| Sumber | Formula | Pembilang | Penyebut | Sifat penyebut |
|---|---|---|---|---|
| Excel `KOL_Database.AP` | `Rate Card ÷ (Avg Views × ER% ÷ 100)` | rate card | views × ER | **estimasi** |
| Backlog `:266` | `fee ÷ total_engagement` | `unified_rate_card.fee` | total engagement per post | **terukur** |
| Frontend `:2781` | `cpe = iqNum(k.cpe)` | — | — | **tidak mendefinisikan — hanya membaca** |
| Register `filter.xlsx` r29 | **"Belum ada"** | — | — | Status **HOLD** |

**Frontend tidak mendefinisikan CPE.** Itu menghapus satu kandidat konflik:
UI menerima apa pun yang backend hitung. Jadi yang tersisa Excel vs Backlog, dan
keduanya **beda grain**, bukan beda pendapat:
Excel = pra-campaign (estimasi), Backlog = pasca-post (terukur).

### Cost field mana yang grain-nya paling tepat

| Grain CPE | Cost field | Alasan grain |
|---|---|---|
| **campaign × KOL** | **`campaign_kols.deal_price`** | Satu-satunya cost yang **sebaris** dengan `total_engagement`. Nol join, nol risiko salah alokasi antar-creator |
| **deliverable / konten** | **`campaign_kol_deliverables.subtotal`** | Sebaris dengan `campaign_kol_deliverable_id` yang jadi FK di `campaign_content_performance`. `subtotal` (bukan `unit_price`) karena sudah memperhitungkan `quantity` |
| order | `campaign_orders.total_amount` | ❌ **jangan** — §2.2 |
| **Discovery (pra-campaign)** | `l1_silver.unified_rate_card.fee`, yang diisi dari **`l0_raw.kol_roster_import.*_price`** | Grain KOL × post_type; 93,7% roster punya harga di L0 |

⚠️ `subtotal` = `unit_price × quantity` adalah **inferensi dari nama + kolom
tetangga `quantity`**. Tabelnya 0 baris, jadi **tidak bisa gue buktikan**.
Harus dikonfirmasi.

### Denominator CPE dari mana

| Grain | Denominator | Ketersediaan |
|---|---|---|
| campaign × KOL | `campaign_kols.total_engagement` (bigint) | kolom ada, 0 baris |
| deliverable | `campaign_content_performance.total_engagement` | kolom ada, 0 baris |
| Discovery | agregat engagement per akun dari `l2_gold.post_metric` (503 baris) | tersedia sebagian |

⚠️ **Definisi `total_engagement` belum pasti** dan ini menentukan angkanya:
- `filter.xlsx` #1 (FINAL/APPROVED): ER = `Engagement / Followers × 100%` — tapi
  tidak merinci isi "Engagement"
- `filter.xlsx` #11 & #12 (FINAL/APPROVED): Share Rate & Save Rate memakai
  penyebut **`Likes + Comments + Shares`**
- `taksonomi_kol`: ER = `Likes + Comments + Shares`
- `transform.py` (implementasi ER `kol_directory`): `AVG(likes + comments)` —
  **tanpa shares**

Jadi di dalam register yang sama, penyebut Share/Save Rate **memasukkan shares**
sementara implementasi ER **tidak**. `NEEDS BUSINESS CONFIRMATION`.

### CPE per campaign-KOL atau per deliverable?

**Keduanya, dan bukan pilihan** — sama seperti EMV:

```
campaign_content_performance   → CPE per deliverable (cost = deliverables.subtotal)
        │ agregasi
        ▼
campaign_kols                  → CPE per campaign × KOL (cost = deal_price)
```

Yang dipakai UI: **campaign × KOL** — E13 menunjukkan tabel campaign tracking
bergrain per-KOL (`alloc`, `eng`, `emv`, `roas`, `score`). CPE per deliverable
berguna untuk analisis, bukan untuk tampilan utama.

### Formula yang bisa dipastikan

```
CPE_campaign = campaign_kols.deal_price ÷ campaign_kols.total_engagement
```

Status: **PARTIAL** — strukturnya pasti (dua kolom, satu baris, tanpa join,
tanpa konflik definisi lintas-sumber), tapi **penyebutnya menunggu definisi
`total_engagement`** dan **cost-nya menunggu konfirmasi `deal_price` vs
negotiation table di app DB**.

## 2.5 CPV — penentuan

### Perbandingan empat sumber — dan konfliknya nyata

| Sumber | Formula / definisi | Unit |
|---|---|---|
| Excel `KOL_Database.AO` | `Rate Card ÷ Average Views` | **per 1 view** |
| **Register `filter.xlsx` r30** | Definisi: **"Biaya per view."** · Kalkulasi: "Belum ada" | **per 1 view** |
| Frontend `app/AUTOME_2.html:2783` | `cpv = rate / views * 1000` | **per 1.000 views** |
| Frontend label `:2842` | `cpvMax: ['CPV / 1K views ≤ ($)', …]` | **per 1.000 views**, **$** |
| Frontend `IQ_GROUPS.eff:2446` | opsi `['cpv','Low Cost per View']` | label "per View" (tunggal) |

**Skornya 2–2, dan bukan sekadar beda label:**

- **Per 1 view**: Excel (formula eksplisit) + register internal (definisi
  tertulis "Biaya per view")
- **Per 1.000 views**: implementasi frontend (`*1000`) + label UI eksplisit
  ("CPV / 1K views")

Dan frontend sendiri **tidak konsisten**: label slider bilang "/ 1K views",
tapi opsi kriteria di `IQ_GROUPS` bilang "Low Cost per **View**".

Selisihnya **1.000×**. Salah pilih bukan sekadar salah format — angkanya salah
tiga digit. **`NEEDS BUSINESS CONFIRMATION` — gue tidak memilih.**

Catatan: kalau yang dimaksud per 1.000, maka CPV **identik bentuknya dengan CPM**
(`rate ÷ metrik × 1000`) — hanya beda penyebut (views vs reach). Itu justru
argumen bahwa yang dimaksud per-1-view, karena kalau tidak, CPV dan CPM jadi
metrik kembar. Tapi itu **penalaran gue, bukan bukti** — jadi tetap HOLD.

### Numerator & denominator

| Grain | Numerator | Denominator | Catatan |
|---|---|---|---|
| campaign × KOL | `campaign_kols.deal_price` | **`SUM(campaign_content_performance.views)`** | **`campaign_kols` TIDAK punya kolom `views`** → wajib agregasi. Asimetris dengan CPE |
| deliverable | `deliverables.subtotal` | `campaign_content_performance.views` | sebaris, tanpa agregasi |
| Discovery | `unified_rate_card.fee` ← L0 roster | `feature.*_engagement_analysis.avg_views` (30) atau `l2_gold.post_metric.views` (397/503) | |

### Formula

```
per 1 view   :  CPV = cost ÷ views
per 1K views :  CPV = cost ÷ views × 1000
```

Keduanya tertulis di sumber berbeda. **Tidak ada kolom `cpv` di DB** (0 dari 101
tabel) dan **tidak boleh ditambah** (test guard E8).

**Status: `NEEDS BUSINESS CONFIRMATION`** untuk unit; **READY secara struktur**
(calculated, nol kolom baru).

## 2.6 Ringkasan keputusan CPE/CPV

| | CPE | CPV |
|---|---|---|
| Formula | `cost ÷ total_engagement` | `cost ÷ views` **atau** `× 1000` |
| Numerator | `campaign_kols.deal_price` (campaign×KOL) · `deliverables.subtotal` (deliverable) · `unified_rate_card.fee` (Discovery) | sama |
| Denominator | `campaign_kols.total_engagement` | `SUM(campaign_content_performance.views)` |
| Unit | IDR per engagement | **BELUM PASTI** |
| Grain utama | campaign × KOL | campaign × KOL |
| Kolom baru | **TIDAK** — kolom `cpe` sudah ada + test guard melarang | **TIDAK** |
| Status | **PARTIAL** | **NEEDS BUSINESS CONFIRMATION** |

**Yang berubah dari dokumen sebelumnya:** gue sebelumnya menyebut CPE campaign
"bisa dipastikan". Sekarang gue turunkan jadi **PARTIAL** — karena register
`filter.xlsx` menandai CPE `HOLD` dengan catatan *"Dibutuhkan: biaya campaign +
**definisi engagement yang dipakai**"*, dan definisi `total_engagement` memang
belum pasti. Strukturnya pasti; penyebutnya belum.

**Dan yang membaik:** blocker rate card turun dari "tidak ada sumber" menjadi
"propagasi L0→L1 + pilih post_type", karena §0.2.

---

# 3. STYLE & PERSONALITY — VALIDASI IMPLEMENTASI

## 3.1 Apa yang UI sebenarnya punya sekarang

Ini yang belum pernah gue periksa, dan hasilnya mengubah gambaran.

### Filter UI yang sudah ada — `docs/KOL_DISCOVERY_AUDIT.xlsx` sheet `RICH FILTER` r15

| Field | Isi |
|---|---|
| Filter | **"Content Style & Creator Personality"** |
| UI Control | **Chips (multi-select)** ← multi-nilai per KOL sudah jadi asumsi UI |
| Options/Values | **10 nilai hardcoded**: `educational, entertaining, inspirational, relatable, storytelling, tutorial, review, aesthetic, minimalist, cinematic` |
| DB Table | **NOT FOUND** |
| Actual Behavior | "Berjalan hanya di **8 KOL mock** (`const KOLS` baris 608); **0 network call** di seluruh file" |
| Status | **NOT AVAILABLE** |
| Notes | "Nilai hardcoded di prototype; tidak ada kolom padanan di DB" |

**Tiga hal penting dari sini:**

1. UI **menggabungkan** Content Style dan Creator Personality jadi **satu**
   filter — sementara Excel (dan requirement lo) memisahkannya.
2. **`minimalist` dan `cinematic` tidak ada di Excel** sama sekali.
3. Tidak ada filter **Communication Style** terpisah di UI.

### Struktur di prototype — ternyata TIGA sumbu, bukan dua

`app/AUTOME_2.html:2715–2719` (`DNA2`) memodelkan setiap creator dengan tiga
array:

| Sumbu | Nilai yang muncul (dari 8 creator mock) | Padanan Excel |
|---|---|---|
| **`dna`** | relatable, educational, casual, inspirational, expert, professional, entertaining, humorous — **8 nilai** | ≈ Creator Personality (12) |
| **`comm`** | vlog, tutorial, storytelling, commentary, talkinghead, review, demonstration — **7 nilai** | ≈ campuran Content Style + Communication Style |
| **`vis`** | casual, aesthetic, lifestyle, minimalist, cinematic, colorful, professional — **7 nilai** | **TIDAK ADA di Excel** |

`DNA2_DEFAULT = cat => ({dna:['casual','relatable'], comm:['vlog'], vis:['casual'], …})`

**Semuanya array → multi-nilai per KOL sudah menjadi bentuk di UI.** Itu
mendukung requirement lo.

Tapi: **`vis` (visual style) adalah sumbu keempat yang taxonomy Excel tidak
punya**, dan pembagian `comm` di UI tidak sama dengan pembagian Excel — `vlog`,
`tutorial`, `review`, `talkinghead` di Excel masuk **Content** Style, di UI masuk
`comm`.

⚠️ Dan **tidak ada konstanta vocabulary yang dideklarasikan** di kedua prototype
(`const DNA*`/`STYLE*`/`VIS*`/`COMM*` → 0 hit yang relevan). Nilai-nilai itu cuma
ada di dalam literal data 8 creator mock. Jadi **prototype bukan sumber
vocabulary yang sah** — ia sampel.

### Vocabulary mana yang paling lengkap

| Sumber | Isi | Sifat |
|---|---|---|
| **`brand_style_personality.xlsx`** | 18 Style (2 grup) + 30 Personality (3 grup) = 48 baris; kolom `Source` = `scripts/brand-match/vocabulary.mjs` | **Paling lengkap.** Tapi ia **laporan** atas file hardcode di repo aplikasi, bukan taxonomy yang diratifikasi — dan `Count in DB = 0` untuk seluruh 48 baris |
| `brand_match_master.xlsx` `Lookup_Lists` | ContentStyle 10 · CommStyle 8 · CreatorPersonality 12 · BrandPersonality 10 · BrandTone 8 · Value 14 · Positioning 5 | Konsisten dengan di atas, + 2 vocabulary tambahan (Values, Positioning) |
| Prototype `DNA2` | dna 8 · comm 7 · vis 7 | Sampel 8 creator mock; ada `vis` yang tidak ada di Excel |
| Filter UI (RICH FILTER r15) | 10 nilai gabungan | Hardcode prototype; 2 nilai di luar Excel |
| `filter.xlsx` r31 | — | Status **HOLD**, *"Tidak ada taxonomy final"* |

**Kesimpulan: tidak ada satu sumber yang sekaligus lengkap dan diratifikasi.**
Excel paling lengkap; register internal menyatakan belum final; UI memakai
subset yang berbeda plus sumbu tambahan. `NEEDS BUSINESS CONFIRMATION` untuk
vocabulary final.

## 3.2 Apakah satu master table cukup?

**Cukup — dan jawabannya tidak berubah dari sesi lalu, tapi sekarang ada satu
alasan tambahan.**

Alasan utama tetap: Style dan Personality **bentuknya identik** — (grup, label),
ditempel manual, boleh banyak per KOL, tidak punya kolom yang dibutuhkan salah
satu tapi tidak yang lain.

Alasan tambahan yang baru: UI ternyata punya **sumbu ketiga (`vis`)** dan
menggabungkan Style+Personality dalam satu filter. Satu master ber-`kind` dan
`attribute_group` bisa **menampung sumbu baru tanpa DDL** — cukup tambah baris.
Kalau dipecah jadi 4 tabel terpisah, menambahkan Visual Style berarti tabel
kelima.

## 3.3 Membedakan kind / group / key, dan mencegah duplikat

Excel punya **label yang sama di grup berbeda dengan arti berbeda**. Dihitung
ulang sesi lalu, angkanya:

| | Baris | Nilai unik | Overlap antar-grup |
|---|---:|---:|---|
| Style | 18 | 16 | `Educational`, `Storytelling` |
| Personality | 30 | 26 | `Educational`, `Playful`, `Premium`, `Professional` |
| Lintas Style↔Personality | — | — | `Conversational`, `Educational`, `Entertaining`, `Humorous` |

`Educational` muncul di **4 grup**: Content Style, Communication Style, Creator
Personality, Brand Personality.

**Cara membedakan — tiga kolom, bukan satu:**

| Kolom | Isi | Fungsi |
|---|---|---|
| `kind` | `style` \| `personality` | pemisah kasar, untuk UI menampilkan dua seksi |
| `attribute_group` | `content_style` \| `communication_style` \| `creator_personality` | **sumbu sebenarnya** — inilah yang membuat `Educational` tidak tertukar |
| `attribute_key` | `content_style.educational` | slug stabil, aman untuk API & config |
| `label` | `Educational` | teks tampil, boleh berubah/diterjemahkan |

**Mencegah duplikat — dua lapis:**

1. **Unik `(kind, attribute_group, attribute_key)`** di master → `Educational`
   boleh ada 3× (tiga grup), tapi tidak boleh 2× dalam grup yang sama.
   Jumlah baris master yang benar = **jumlah baris Excel sisi KOL (30)**, bukan
   jumlah nilai unik.
2. **Unik `(kol_directory_id, kol_attribute_id)`** di mapping → satu label tidak
   bisa ditempel dua kali ke KOL yang sama.

**Catatan tipe:** DB ini **tidak punya enum** dan hanya punya 4 CHECK constraint
(semua di `kol_profile_card`, migration 042–044). Jadi `kind` dan
`attribute_group` sebagai `varchar` + CHECK mengikuti pola rumah yang sudah ada —
bukan enum.

## 3.4 Mapping ke `kol_directory.id` — dan kejujuran soal level-nya

**Rekomendasi tetap `kol_directory.id`.** Tapi lo benar untuk menekankan ini, dan
gue nyatakan terang:

> **`kol_directory` secara schema adalah ACCOUNT/PLATFORM-level, bukan
> person-level.** Buktinya: PK `id` per baris, `platform_id` sebagai kolom, dan
> 216 handle punya 2 baris (satu per platform).

Jadi menaruh atribut di sana **tidak** membuatnya person-level. Ia jadi
**atribut per akun**, dan secara bisnis lo memperlakukannya sebagai atribut
orang. Selisih itu nyata dan harus ditulis di dokumentasi kolomnya, bukan
disembunyikan.

### Tidak ada entity person lain yang bisa dipakai

| Kandidat | Kenapa bukan person |
|---|---|
| `public.kol_social_account` (7.208) | Namanya menjanjikan, kolomnya `kol_id`. Tapi FK-nya `kol_id → kol_directory(id)`, dan kardinalitasnya **1:1:1** (7.208 baris / 7.208 `kol_id` / 7.208 `social_account_id`, **0 KOL punya >1 akun**). Ia link 1:1, bukan jembatan person→accounts |
| `public.social_account` (7.208) | Akun platform + OAuth token. Lebih sempit dari `kol_directory` (kehilangan 224) |
| `public.agency_kol_accounts` (7.431) | Per-(agency, akun). 1 agency hari ini, 1:1. Tetap FK ke `kol_directory` → tetap per-platform |
| `public.user` (**1 baris**) | User aplikasi: `email`, `password_hash`, `google_id`, `role`, `agency_id`. Bukan creator |
| `l0_raw.kol_roster_import` (7.718) | **Paling dekat dengan "orang"**: punya `influencer_id` (text), `influencer_email`, `influencer_phone_number`, `influencer_no_ktp`, `influencer_bank_code`, `influencer_account_number` — **identitas manusia**. Tapi ia tabel **L0 raw import**, bukan master. `influencer_no_ktp` cuma 183 terisi, dan `influencer_gender` terkontaminasi column-shift |

### ⚠️ TEMUAN TERPENTING BAGIAN INI: `influencer_id` sudah mengelompokkan orang

`l0_raw.kol_roster_import.influencer_id` adalah satu-satunya identifier di
seluruh DB yang secara nama merujuk **orang**, bukan akun. Gue verifikasi
langsung:

| Ukuran | Angka |
|---|---:|
| Baris | 7.718 |
| `influencer_id` terisi | **7.718 (100%)** |
| `influencer_id` unik | **7.400** |
| `kol_directory_id` unik | 7.208 |

Distribusi jumlah akun per `influencer_id`:

| Akun per influencer | Jumlah influencer |
|---:|---:|
| 1 | 6.787 |
| **2** | **132** |
| 3 | 4 · 4 → 5 · 5 → 1 · 6 → 4 · 8 → 1 · 10 → 2 · 12 → 1 · 13 → 1 | |
| **43** | **1** ← outlier, perlu diperiksa |

**Total 152 `influencer_id` memetakan ke lebih dari satu akun.**

Dan inilah yang menentukan — contoh nyata:

```
influencer_id  handle                  platform    followers
1              tasyakamila             instagram   5.042.266
1              tasyakamilaofficial     tiktok        526.100     ← handle BEDA
10             tenggowicaksono         instagram     288.661
10             tenggowicaksono         tiktok        912.400
10011          destisetioningsih       instagram      22.323
10011          destisetioningsih       tiktok          4.245
```

**`influencer_id = 1` menghubungkan `tasyakamila` dengan
`tasyakamilaofficial` — dua handle BERBEDA, orang yang sama.** Pencocokan
berbasis handle **tidak akan pernah** menangkap ini.

**Artinya: DB sudah punya data pengelompokan person→accounts**, 100% terisi,
di L0. Ini bukan person *entity* (tidak ada tabelnya, tidak ada FK, tidak ada
constraint), tapi ia **data yang dibutuhkan untuk membuatnya**.

Dua hal yang harus diperiksa sebelum dipakai:
- **Outlier 43 akun untuk satu `influencer_id`** (dan 13, 12, 10) — apakah itu
  MCN/agency yang mengelola banyak akun, atau id sampah? Belum gue periksa.
- `influencer_id` bertipe **`text`** di tabel **L0 raw**, tanpa constraint —
  jadi stabilitasnya lintas-import belum terjamin (`import_batch_id` ada, jadi
  bisa diaudit).

### A. Solusi paling aman tanpa membuat person entity

Mapping ke **`kol_directory.id`**, dengan tiga pengaman:

| # | Pengaman | Kenapa |
|---|---|---|
| 1 | Dokumentasikan di `COMMENT ON COLUMN`: *"atribut per AKUN platform, bukan per orang"* | Supaya konsumen berikutnya tidak salah anggap |
| 2 | UI menawarkan (tidak otomatis) "terapkan juga ke akun platform lain dengan handle sama" | Mengurangi kurasi ganda untuk 216 handle **tanpa** auto-merge |
| 3 | Laporan QA "handle sama, atribut beda" | Deteksi, bukan constraint |

Keuntungan: cakupan terluas (7.432), preseden `category_ids` ada di tabel yang
sama, bisa dijangkau ke L2 (97%) dan roster (99,99%).

### B. Solusi ideal kalau nanti mau benar-benar person-level

```
person  (id uuid PK, display_name, …)          ← BELUM ADA
   │ 1:N
kol_directory  (+ person_id uuid NULL)         ← kolom baru, nullable
   │
kol_attribute_map  (person_id ATAU kol_directory_id)
```

Jalur migrasinya murah **kalau** mapping sekarang memakai FK terpisah
(`kol_directory_id`): nanti tinggal tambah `person_id` nullable dan pindahkan
bertahap. Yang mahal adalah kalau sekarang atributnya ditaruh sebagai kolom/array
di `kol_directory` — itu tidak bisa dipindah tanpa membongkar.

**Sumber penggabungan person: `influencer_id` adalah kandidat terkuat, dan
sekarang terbukti punya datanya** — 100% terisi, 152 grup multi-akun, dan
menangkap kasus yang handle tidak bisa (`tasyakamila` ↔ `tasyakamilaofficial`).
Kandidat lain jauh lebih lemah: `influencer_no_ktp` hanya 183 baris,
`influencer_email` belum gue ukur. **Bukan handle.**

Tetap butuh keputusan Product karena: `influencer_id` ada di **L0 raw** (bukan
master), bertipe `text` tanpa constraint, dan ada outlier 43-akun yang belum
dijelaskan.

### C. Risiko duplikat untuk KOL yang punya Instagram + TikTok

| Ukuran | Angka |
|---|---:|
| Handle hanya di 1 platform | 6.777 |
| **Handle di 2 platform** | **216** (2,9%) |
| Baris kelebihan | 216 |
| Maks baris per handle | 2 |
| Baris ber-handle NULL/kosong | **223** |

Contoh terverifikasi:

```
a.ci.pa   instagram  44be0d9f-…  375.972 follower
a.ci.pa   tiktok     80252a56-…  1.200.000 follower
```

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Kurasi ganda | 216 handle dilabeli 2× | UI: tawarkan copy ke sibling — **jangan otomatis** |
| Label berbeda antar platform | inkonsistensi tak terdeteksi | laporan QA |
| 223 baris ber-handle kosong | tidak bisa dicocokkan sama sekali | tidak ada mitigasi |
| Migrasi kalau person entity dibuat | seluruh baris mapping | pakai FK terpisah sejak awal (solusi A) |

⚠️ **Handle sama ≠ orang sama.** DB tidak menyatakan apa pun soal itu, dan gue
tidak melakukan auto-merge berbasis handle. Satu-satunya jalur merge yang sah
harus berbasis identifier orang (`influencer_id` / KTP / email) **setelah**
diverifikasi.

---

# 4. WHAT MATTERS MOST — AUDIT, TANPA IMPLEMENTASI

## 4.1 Apakah 7 item ini benar-benar dipakai?

**Tidak — bukan sebagai satu daftar bernama.** Yang ada: konsepnya tersebar di
tiga mekanisme UI berbeda, dengan nama berbeda, dan **tiga dari tujuh tidak ada
sama sekali**.

Yang gue sapu: kedua prototype (1,57 MB), 7 file Excel, seluruh `docs/*.md`,
`information_schema` 101 tabel, dan git history.

| Pencarian | Hasil |
|---|---|
| Frasa `"what matters"` di kedua prototype | **1 hit** — `app/AUTOME_2.html:2208`, copy marketing Smart Discovery |
| Ketujuh label sebagai satu grup/array | **0 hit** di mana pun |
| `"Content Quality"` di kedua prototype | **0 hit** |
| Tabel/kolom `criteri`/`prefer`/`weight`/`priorit` di DB | **0** (kecuali `campaign_stages.weight` = bobot progres, dan `monitoring_priority`) |

Satu-satunya kemunculan, `app/AUTOME_2.html:2208`:

> **Smart Discovery** — "Pick **any** creator from the complete database as your
> reference, **tell us what matters**, and we'll rank similar creators for you."

Kalimat itu merujuk picker kriteria di bawahnya, yaitu **`IQ_GROUPS`** — dan
`IQ_GROUPS` punya **13 grup** yang **bukan** daftar 7 lo.

## 4.2 Mapping 7 item ke implementasi yang ada

| # | Item | Ditemukan sebagai | Lokasi | Threshold UI | Sumber DB | Terisi | Sifat |
|---:|---|---|---|---|---|---:|---|
| 1 | **Strong Engagement** | badge `'High Engagement'`; filter chip "Engagement Rate" | `dirBadges():3179`; RICH FILTER r16 | badge `er ≥ 5.5`; chip **Good ≥3% / High ≥5.5%** | `kol_directory.engagement_rate` | **1.736** | ✅ **REAL** |
| 2 | **High Audience Quality** | badge `'High Audience Quality'`; filter chip "Audience Quality" | `:3188`; RICH FILTER r12 | badge `audQ ≥ 85`; chip **High 85+ / Good 75+ / Below 75** | `feature.*_audience_analysis.audience_quality_score` + `authenticity_score` (UI: `(auth+q)/2`) | **27** | ✅ **REAL**, cakupan 0,36% |
| 3 | **Consistent Performance** | badge `'Consistent Performer'`; filter chip **"Reliability"**; opsi `behav.consistent`; sort "Most Consistent Performance" | `:3181`; RICH FILTER **r20**; `IQ_GROUPS:2439` | badge `reliability ≥ 82`; chip **Consistent ≥78 / Very Consistent ≥88** | **NOT FOUND** — RICH FILTER r20: *"Sapuan katalog `consist\|reliab\|stabil\|volatil\|cadence\|frequency` = **0 kolom di seluruh DB**"* | **0** | ❌ **MOCK** — `k.cons` = **hash dari creator id** |
| 4 | **Strong Company/Community** | badge `'Strong Community'`; slider `community:'Community Strength'` | `:3187`; `:2846` | badge `community ≥ 72` | **tidak ada kolom**. UI: `community = er×9 + k.aff×3` | **0** | ❌ **MOCK** — bergantung `k.aff` yang tidak punya sumber DB |
| 5 | **High Reach** | opsi `eff.reach` = `'High Reach Efficiency'`; filter chip "Views" | `IQ_GROUPS:2446`; RICH FILTER r19 | chip **150K+ / 300K+ avg views** | `reach` **0 / 503**. Proksi: `avg_views` (30), `view_to_follower_ratio` (22) | **0** (reach) | ⚠️ **PROKSI** — `reach ≠ views`, diperingatkan eksplisit di backlog |
| 6 | **Content Quality** | **TIDAK ADA** | — | — | **tidak ada di DB, Excel (bobot 0), maupun frontend** | **0** | ❌ **TIDAK ADA** |
| 7 | **Brand Safety** | slider `safety:'Brand Safety Score'`; kolom tabel; badge risk level | `:2847`; `:3371`; `:3089` | `safety ≥85 low / ≥72 medium / else high` | **tidak ada kolom**. UI: `safety = (k.auth + posSent)/2`; `posSent` butuh sentiment (**0 baris**) | **0** | ⚠️ **PARSIAL** — 1 dari 2 input ada |

**Rekap: 2 REAL · 1 PROKSI · 1 PARSIAL · 2 MOCK · 1 TIDAK ADA.**

### Yang tidak ada di inventaris filter UI sama sekali

`RICH FILTER` mendaftar **28 filter UI**. Dari 7 item lo:
- Ada sebagai filter: Engagement (r16), Audience Quality (r12), Reliability (r20), Views≈Reach (r19)
- **Tidak ada sebagai filter**: **Community**, **Content Quality**, **Brand Safety**

Ketiganya hanya muncul sebagai badge/slider di prototype `AUTOME_2.html`, bukan
di inventaris filter yang diaudit.

## 4.3 Perbandingan dengan `IQ_GROUPS` / Smart Preset

| | Isi | Bentuk | Persist? |
|---|---|---|---|
| **Daftar 7 lo** | 7 item | — | — |
| **`IQ_GROUPS`** (`:2432`) | **13 grup**: `opp`, `roles`, `pfit`, `audopp`, `ws`, `pos`, `behav`, `mom`, `dep`, `risk`, `sat`, `expo`, `arch`, `eff`, `collab` + 2 basic | `{key, label, icon, opts:[[key,label]], ranges?, sub?}`; pilihan = `{group:[options]}` | ❌ state klien |
| **`IQ_MODES`** | 5: Best Match · Find Opportunities · Find Missing Pieces · Explore New Markets · Unexpected Matches | — | ❌ |
| **`IQ_PRESETS`** | shortcut, mis. `['gems','🔥','Hidden Gems',{mode:'oppo',sel:{opp:['untapped','underutilized'],sat:['lowsat']}}]` | — | ❌ |
| **Smart Preset Chips** (`deliv.xlsx` r85) | **8**: Best Performing · High Engagement · Fast Growing · Audience Quality · Brand Fit · Emerging · Campaign Ready · Cost Efficient | chip | ❌ |
| **`dirBadges()`** (`:3178`) | **16 badge** dari threshold | badge otomatis | ❌ |

**Empat daftar berbeda, tidak satu pun berisi 7 item lo.** Yang paling dekat:
Smart Preset (2 dari 8 beririsan) dan `dirBadges()` (4 dari 16 beririsan).

## 4.4 API / request parameter / persistence

| Pertanyaan | Jawaban | Bukti |
|---|---|---|
| Ada API parameter untuk 7 item? | **Tidak ada** | Parameter yang terdokumentasi di `docs/`: `num('minEr')`, `num('growthMin')`, `num('growthMax')`, `num('follMin')`, `query.minErPct`, `query.category` — **tidak ada yang menyerupai** |
| Route Discovery mendukung tulis? | **Tidak** | `docs/KOL_DISCOVERY_AUDIT.md:87` — *"route `kol-directory` hanya mengekspor **`GET`**. Tidak ada `POST`/`PUT`/`PATCH`"* |
| Prototype mempersist pilihan? | **Tidak** | `grep fetch(\|/api/\|XMLHttpRequest` di `AUTOME_2.html` → **0 hit**. Hanya **2** `localStorage`. Data creator hardcoded |
| Ada tabel preference/saved di DB? | **Tidak** | Sapuan nama tabel `preference\|saved\|collection\|favorite\|shortlist\|bookmark\|setting` → **0 tabel** |
| Ada preseden persistence untuk pilihan user? | **Tidak, dan itu tercatat** | `AUTOME_2_READINESS_AUDIT.md:141` — *"Saved List / Search / Collection / Favorite \| — \| **tak ada tabel** \| 4 collection bawaan + saved search + Favorite, **semua state lokal** \| tabel + CRUD endpoint"* |

**Kesimpulan: nol persistence, nol API parameter, nol tabel — dan preferensi
user jenis apa pun memang belum pernah dipersist di produk ini.**

## 4.5 Jadi ini preference/ranking criteria atau score per KOL?

**Bukti yang ada mengarah ke preference/ranking criteria, tapi tidak
konklusif.**

| Mendukung **preference** | Mendukung **score per KOL** |
|---|---|
| Frasa "tell us what matters" merujuk picker kriteria (`IQ_GROUPS`) | 4 dari 7 punya nilai numerik per creator di `intel2()` |
| Seluruh filter UI berbentuk **chip multi-select dengan threshold**, bukan kolom skor | `dirBadges()` menghasilkan badge per creator dari threshold |
| Route Discovery **GET-only** | — |
| Nol persistence, nol tabel preference | — |
| Excel punya preseden persis: `Brand_Profile.audience_priority` — dropdown yang menggeser bobot **+12 / −4** | — |

**Yang tidak bisa gue pastikan:** apakah daftar 7-item lo adalah **redesain**
picker itu, atau **komponen skor baru**. Prototype bertanggal 2 Sep 2026 dan
tidak memuatnya. `NEEDS BUSINESS CONFIRMATION`.

## 4.6 Perlu persistence atau cukup query/config?

**Cukup query/config — untuk kedua tafsir.**

| Kebutuhan | Cukup dengan | Perlu tabel? |
|---|---|---|
| Daftar 7 kriteria untuk ditampilkan UI | **vocabulary di config** — pola `IQ_GROUPS` yang sudah dipakai | ❌ |
| Pilihan user saat mencari | **query parameter** — pola `minEr`, `growthMin` yang sudah dipakai | ❌ |
| Nilai per KOL | **dihitung dari kolom sumber saat query** — pola `Final Match Score` ("Computed, not stored") | ❌ |
| Pilihan tersimpan & dipakai ulang | tabel preference | ✅ **tapi belum terbukti dibutuhkan** — dan Saved List/Collection pun belum punya tabel |

**Gue TIDAK mengusulkan tabel apa pun untuk What Matters Most sekarang.**

## 4.7 Yang TIDAK gue buatkan formula

Sesuai instruksi lo, dan alasannya masing-masing:

| Item | Kenapa gue tidak bikin formula |
|---|---|
| **Community** | UI-nya `er×9 + aff×3`, dan `k.aff` **tidak punya kolom DB** — jadi formulanya sendiri bertumpu pada mock. `AUTOME_2_READINESS_AUDIT.md:196` (F-5) sudah menandai: *"`k.aff` saja menopang 6 metrik turunan"*, aksinya *"definisikan atau buang"* |
| **Content Quality** | **Nol sumber di tiga tempat**: tidak ada di DB, di Excel bobotnya **0** dan tanpa rumus, di frontend **0 hit** |
| **Brand Safety** | Dua definisi bersaing: UI `(auth + posSent)/2` (butuh sentiment, **0 baris**) vs Excel CMP 4-input integrity screen. Excel sendiri menegaskan yang kedua **bukan** brand safety, melainkan *integrity screen* |
| **Consistent Performance** | Sapuan katalog `consist\|reliab\|stabil\|volatil\|cadence\|frequency` = **0 kolom**; UI memakai `k.cons` = **hash dari creator id**. Proksi terdekat `performance_stability` (11 baris) adalah **stddev ER**, bukan konsep yang sama |

---

# 5. FINAL DECISION MATRIX

| Item | Source/DB | Formula/Logic | Grain | Status | Evidence | Action |
|---|---|---|---|---|---|---|
| **EMV** | `campaign_kols.emv` · `campaign_content_performance.emv` · `feature.ig/tt_audience_analysis.emv` — 4 kolom, **0 terisi**. Input: `reach` **0/503** · CPM **0 kolom** · multiplier **0 kolom** | **Tertulis:** `Reach × CPM ÷ 1000 × Multiplier` (E1). Kandidat lain tersirat & melingkar | 3 grain: akun · campaign×KOL · deliverable×snapshot | **HOLD / NEEDS BUSINESS CONFIRMATION** | E1 backlog:249 · E4 filter.xlsx r28 HOLD · E7 pipeline sengaja NULL · E8 test guard · E11 UI hardcoded · E19 sapuan 101 tabel | **Jangan implementasi.** Tanyakan Q1–Q7 (§1.7). Kolom sudah ada, jangan tambah |
| **CPE** | Campaign: `campaign_kols.deal_price` + `total_engagement`. Deliverable: `deliverables.subtotal`. Discovery: `feature.*.cpe` ← `unified_rate_card.fee` ← **`l0_raw.kol_roster_import` 93,7%** | `cost ÷ total_engagement` (backlog) · `Rate ÷ (AvgViews × ER/100)` (Excel, estimasi) · UI **hanya membaca** | campaign × KOL (utama) · deliverable · KOL (Discovery) | **PARTIAL** | filter.xlsx r29 HOLD "butuh definisi engagement" · backlog:266 · frontend `:2781` | Struktur siap. Konfirmasi **definisi `total_engagement`** + **cost field**. Nol kolom baru |
| **CPV** | Tidak ada kolom `cpv` (0/101 tabel). Views: `campaign_content_performance.views` · `avg_views` (30) | **Konflik 1.000×**: `cost ÷ views` (Excel + register) **vs** `cost ÷ views × 1000` (frontend + label UI) | campaign × KOL (**wajib agregasi** — `campaign_kols` tanpa `views`) | **NEEDS BUSINESS CONFIRMATION** | Excel `KOL_Database.AO` · filter.xlsx r30 "Biaya per view" · `app:2783` + label `:2842` "CPV / 1K views" | **Tetapkan unit dulu.** Lalu calculated murni — jangan bikin kolom |
| **Content Style** | **NOL** di DB. Excel: **10 nilai**. UI: tergabung dalam 1 chip 10-nilai, **8 KOL mock** | Bukan formula — **kurasi manual** | KOL (akun) | **PARTIAL** *(vocabulary belum final)* | `brand_style_personality.Style List` · RICH FILTER r15 NOT AVAILABLE · filter.xlsx r31 "Tidak ada taxonomy final" | Desain siap (`kol_attribute` + `kol_attribute_map`). Konfirmasi vocabulary final |
| **Communication Style** | **NOL** di DB. Excel: **8 nilai**. UI: **tidak ada filter terpisah**; prototype `comm` punya 7 nilai dengan pembagian berbeda | Kurasi manual | KOL (akun) | **PARTIAL** | idem · prototype `DNA2.comm` | idem. **Konfirmasi**: UI tidak memisahkan sumbu ini |
| **Creator Personality** | **NOL** di DB. Excel: **12 nilai**. Prototype `dna`: 8 nilai | Kurasi manual | KOL (akun) | **PARTIAL** | `Personality List` · prototype `DNA2.dna` | idem |
| **Brand Personality** | **NOL**. Excel: **10 nilai**. Milik **brand**, bukan KOL | Kurasi manual | **brand** | **HOLD** | `Personality List` · `public.brand` **0 baris** | **Jangan masuk tabel KOL.** Diblokir `brand` kosong |
| **Brand Tone** | **NOL**. Excel: **8 nilai**. Milik **brand** | Kurasi manual | **brand** | **HOLD** | idem | idem |
| **Strong Engagement** | `kol_directory.engagement_rate` | Chip: **Good ≥3% / High ≥5.5%**. Badge: `er ≥ 5.5` | KOL | **READY** *(sebagai filter)* | RICH FILTER r16 PARTIAL · `dirBadges():3179` · filter.xlsx #1 FINAL/APPROVED | Pakai kolom existing. ⚠️ outlier ER sampai **223,41%** |
| **Audience Quality** | `feature.*_audience_analysis.audience_quality_score` + `authenticity_score`; `kol_profile_card` mirror | Chip: **High 85+ / Good 75+ / Below 75**. UI: `(auth+q)/2` | KOL | **PARTIAL** | RICH FILTER r12 · filter.xlsx #22 FINAL/APPROVED · **27 terisi (0,36%)** | Pakai kolom existing. Naikkan cakupan |
| **Consistent Performance** | **NOT FOUND** — 0 kolom di seluruh DB. Proksi: `performance_stability` (11) · `post_frequency_reliability` (49) | UI: `k.cons` = **hash creator id** | KOL | **MISSING** | RICH FILTER r20 NOT AVAILABLE · `FILTER_DB_MAPPING 2.md:82` "hasil acak dari ID" | **Jangan bikin formula.** Putuskan: `performance_stability` atau cadence? |
| **Company/Community** | **tidak ada kolom** | UI: `er×9 + k.aff×3` — `k.aff` **mock** | KOL | **MISSING** | `app:2788` · `AUTOME_2_READINESS_AUDIT.md:196` F-5 | **Jangan bikin formula.** `k.aff` harus "didefinisikan atau dibuang" dulu |
| **High Reach** | `reach` **0/503** · `avg_reach` **0/27** · `campaign_kols.reach` 0 baris · `l0_raw…estimated_reach` **96,2% tapi terkontaminasi** | Chip: **150K+ / 300K+ avg views** (views, bukan reach) | KOL · campaign×KOL | **MISSING** *(reach)* / **PARTIAL** *(proksi views)* | RICH FILTER r19 · backlog:236 · verifikasi gue: **2.164 baris reach > followers** | **Jangan samakan views dengan reach.** Butuh Insights API atau pembersihan roster |
| **Content Quality** | **tidak ada di DB, Excel, maupun frontend** | — | — | **MISSING** | `KOL_Database.AM` ada kolomnya tapi **bobot 0, tanpa rumus** · 0 hit di kedua prototype | **Tanyakan apakah memang dibutuhkan** |
| **Brand Safety** | tidak ada kolom `safety`/`risk`. Input proksi: `authenticity_score` 27 · `follower_quality_score` 27 · `verified_status` 931 · `paid_ratio` 48 | UI: `(auth + posSent)/2` — `posSent` butuh sentiment **0 baris**. Excel CMP: 4-input 40/30/15/15 | KOL | **NEEDS BUSINESS CONFIRMATION** | `app:2847` · CMP_Lookup §11 · `*_comments_analysis` **0 baris** | Pilih definisi dulu. Kalau pakai proksi, **wajib dilabeli "integrity screen"** |

---

## A. Yang sudah aman untuk dibuat design/schema

| # | Item | Kenapa aman |
|---|---|---|
| A1 | **`kol_attribute` (master) + `kol_attribute_map` (junction)** untuk Content Style · Communication Style · Creator Personality — **30 baris sisi KOL** | Nilai dari Excel lengkap; kunci mapping terjawab bukti (`kol_directory.id`); bentuk many-to-many sudah jadi asumsi UI (chips multi-select + array `dna`/`comm`/`vis`); dua tabel baru yang tidak direferensikan siapa pun dan tidak disentuh asset Dagster. ⚠️ Vocabulary final masih perlu konfirmasi — tapi **strukturnya** aman |
| A2 | **Endpoint filter Style/Personality** (`EXISTS` + `attribute_group`) | 7.432 baris, seq scan murah |
| A3 | **Vocabulary 7 kriteria + pemetaan ke kolom sumber, sebagai config** | Berguna untuk kedua tafsir; kalau fungsinya berubah, satu file yang diubah |
| A4 | **Laporan QA "handle sama / `influencer_id` sama, atribut beda"** | Mitigasi 216 handle + 152 grup `influencer_id` tanpa constraint |
| A5 | **Filter Strong Engagement & Audience Quality** dari kolom existing | Keduanya `FINAL/APPROVED` di register |

## B. Yang masih HOLD

| # | Item | Alasan |
|---|---|---|
| B1 | **EMV** | 0 dari 3 input tersedia; formula NEED CONFIRMATION; register HOLD |
| B2 | **CPV** | Unit belum pasti (konflik 1.000×) |
| B3 | **CPE** | Struktur siap, definisi `total_engagement` + cost field belum |
| B4 | **Brand Personality + Brand Tone** (18 baris) | Milik brand; `public.brand` **0 baris** |
| B5 | **What Matters Most** — tabel apa pun | Fungsi belum pasti; nol persistence di seluruh produk |
| B6 | **Consistent Performance · Community · Content Quality** | Sumber/definisi tidak ada; 2 dari 3 bertumpu mock |
| B7 | **Person entity** | Data ada (`influencer_id`), entity-nya belum; outlier 43-akun belum dijelaskan |

## C. Yang harus ditanyakan ke Mentor/Product

| # | Pertanyaan | Kenapa penting |
|---:|---|---|
| **C1** | **Formula EMV** — `Reach × CPM ÷ 1000 × Multiplier` disetujui? Kalau ya: **CPM berapa & per apa** (global/platform/tier), **multiplier berapa**? | 3 input, 0 tersedia. Tanpa ini EMV tidak bisa diisi sama sekali |
| **C2** | **Unit CPV** — per 1 view atau per 1.000 views? | **Selisih 1.000×.** Excel + register bilang per-view; frontend + label bilang per-1K |
| **C3** | **Definisi `total_engagement`** — `likes+comments` atau `+shares+saves`? | Register sendiri tidak konsisten: Share/Save Rate pakai `L+C+S`, implementasi ER pakai `L+C` |
| **C4** | **Cost field CPE/CPV** — `campaign_kols.deal_price`, atau **negotiation table di app DB** (`guaranteed fee + performance fee`)? | Tabel negotiation **tidak ada di `kol`**; kalau itu sumber cost sebenarnya, `deal_price` bukan jawabannya |
| **C5** | **Mata uang** — $ atau IDR? | Discrepancy **sudah tercatat** ("prototype USD vs implementasi IDR"); order flow = **integer rupiah** |
| **C6** | **Rate card**: propagasi L0→L1 boleh dijalankan? **`post_type` mana** yang jadi basis fee? Sentinel `1.000.000.000` dan 8 harga < Rp1.000 dibersihkan bagaimana? | **93,7% roster punya harga di L0** — blocker jauh lebih kecil dari yang dikira |
| **C7** | **Vocabulary Style/Personality final** — Excel (18+12), UI (10 gabungan), atau prototype (`dna`/`comm`/`vis`)? Dan **apakah `vis`/Visual Style ikut**? | Tiga vocabulary berbeda; register bilang "tidak ada taxonomy final"; UI punya sumbu keempat |
| **C8** | **Style/Personality: atribut akun atau orang?** Kalau orang: pakai `influencer_id` sebagai kunci person? | `influencer_id` 100% terisi, 152 grup multi-akun, menangkap `tasyakamila` ↔ `tasyakamilaofficial` |
| **C9** | **What Matters Most: preference atau score per KOL?** | Menentukan 0 tabel vs tabel skor |
| **C10** | **`Content Quality` memang dibutuhkan?** | 0 sumber di DB, Excel, dan frontend |
| **C11** | **`Brand Safety`**: definisi UI (butuh sentiment) atau integrity screen 4-input? | Dua definisi; yang kedua bukan brand safety menurut Excel sendiri |
| **C12** | **`Consistent Performance`** = `performance_stability` (stddev ER) atau cadence posting? | Dua konsep; UI-nya hash |
| **C13** | **`k.aff`** — didefinisikan atau dibuang? | Menopang Community + 5 metrik turunan lain (F-5) |
| **C14** | **`reach`**: tunggu Insights API, atau bersihkan `estimated_reach`? | 96,2% terisi tapi 2.164 baris reach > followers |

## D. Yang jangan disentuh dulu

| Jangan | Alasan |
|---|---|
| **Menambah kolom `emv`/`cpe`/`cpv`/`brand_fit`/`estimated_media_value` ke `l2_gold.kol_profile_card`** | **Test guard aktif** — `test_calculated_metrics.py:372` akan gagal |
| Mengisi `feature.*.cpe`/`emv` selama `unified_rate_card` kosong | `test_db_emv_cpe_tetap_null_selama_rate_card_kosong` akan gagal |
| Mengubah `audience.py` supaya menulis `avg_reach`/`cpe`/`emv` | Kolom itu **sengaja** NULL, dengan komentar alasannya |
| Memakai `campaign_orders.total_amount` sebagai biaya KOL | Itu total checkout Midtrans (subtotal→promo→fee 8%→pajak 11%), mencakup **banyak** creator |
| Memakai `l0_raw…estimated_reach` sebagai `reach` | 2.164 baris reach > followers; column shift |
| Memakai `views` sebagai `reach` | Diperingatkan eksplisit di backlog |
| Auto-merge KOL berdasarkan handle | Handle sama ≠ orang sama; dan `tasyakamila`↔`tasyakamilaofficial` justru **beda handle** |
| Membuat tabel What Matters Most | Fungsi belum pasti |
| Menaruh Style/Personality di `kol_profile_card` | Di-regenerate asset Dagster |
| Memakai `k.aff`, `k.cons` sebagai sumber | Mock — `k.cons` hash creator id |
| Membuat VIEW pertama di DB ini | 0 view sekarang; keputusan konvensi tim |

## E. Rekomendasi langkah berikutnya

Diurutkan dari paling murah & paling membuka:

| # | Langkah | Kenapa duluan | Butuh |
|---:|---|---|---|
| **1** | **Bawa C1–C6 ke mentor dalam satu sesi** | Enam pertanyaan ini memblokir EMV, CPE, dan CPV sekaligus. Semuanya butuh **jawaban**, bukan kode | 1 meeting |
| **2** | **Verifikasi rate card L0** — sampel `l0_raw.kol_roster_import` vs rate card asli, dan periksa sentinel + 8 harga < Rp1.000 | **Temuan terbesar sesi ini.** Kalau valid, CPE/CPV Discovery naik dari MISSING ke PARTIAL tanpa sumber baru | read-only + konfirmasi mentor |
| **3** | **Periksa outlier `influencer_id`** (43, 13, 12, 10 akun) | Menentukan apakah `influencer_id` layak jadi kunci person (C8) | read-only |
| **4** | **Bangun `kol_attribute` + `kol_attribute_map`** setelah C7 & C8 dijawab | Satu-satunya item yang strukturnya sudah aman | approval |
| **5** | **Tulis config 7 kriteria → kolom sumber**, tanpa tabel | Berguna untuk kedua tafsir C9 | — |
| **6** | **Implementasi filter Strong Engagement & Audience Quality** dari kolom existing | Dua item READY/PARTIAL yang kolomnya sudah `FINAL/APPROVED` | — |
| **7** | Naikkan cakupan `feature.*_audience_analysis` dari 27 akun | Membuka Audience Quality + 3 dari 4 input Brand Safety proksi | pipeline |
| **8** | Setelah campaign pertama masuk: hitung CPE campaign sebagai query | Butuh C3 + C4 dijawab dulu | data |

---

## F. STATUS SESI

| | |
|---|---|
| Query DB | ~18 `SELECT` (struktur, FK, kardinalitas, fill rate, verifikasi rasio) |
| INSERT / UPDATE / DELETE | **0** |
| CREATE / ALTER / DROP | **0** |
| Migration | **0** |
| Perubahan source code | **0** |
| Database disentuh | **`kol` saja** |
| File ditulis | `docs/KOL_HOLD_RESOLUTION_2.md` (dokumen ini) |
| Formula yang gue karang | **Nol** |
| Keputusan bisnis yang gue ambil | **Nol** — 14 diserahkan (C1–C14) |

**Tiga temuan baru terpenting sesi ini:**
1. **Rate card ADA di L0** — 7.231 dari 7.718 baris (93,7%) punya harga > 0.
   Klaim "0 baris di L0 sekalipun" **salah**; blocker sebenarnya propagasi L0→L1.
2. **`influencer_id` sudah mengelompokkan orang** — 100% terisi, 152 grup
   multi-akun, dan menangkap kasus yang handle tidak bisa.
3. **`docs/filter.xlsx` adalah register status otoritatif** — 24 FINAL/APPROVED,
   dan EMV/CPE/CPV/Style-Personality semuanya HOLD dengan catatan apa yang kurang.

**Read-only. Nol perubahan. Menunggu jawaban C1–C14.**
