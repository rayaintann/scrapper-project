# IMPLEMENTASI — CPE · CPV · Reach Audit · Style & Personality

**Tanggal:** 13 September 2026 · DB `kol` @ `10.100.14.216`
**Lingkup:** implementasi bagian yang sudah punya keputusan/evidence.
**EMV TIDAK diimplementasikan** — alasannya di §1.

---

# 1. EMV — Rp9.000 BUKAN EMV, status tetap HOLD

## 1.1 Di mana Rp9.000 ditemukan

Sapuan `9000` / `9.000` / `Rp9.000` / `9k` di **seluruh** `*.py`, `*.md`,
`*.sql`, `*.ps1`, `*.html`, 7 file Excel, dan git history (15 commit,
`--all --name-only`):

| Lokasi | Isi | Relevan? |
|---|---|---|
| `docs/brand_match_master.xlsx` → `Lookup_Lists` **r146** | `Value per engagement (IDR)` \| `CAL_VALUE_PER_ENG` \| **9000** \| *"Earned value of one engagement, **used by Estimated ROI**"* | ✅ satu-satunya yang relevan |
| `docs/brand_match_master.xlsx` → `CMP_Lookup_Lists` r146 | identik | ✅ duplikat sheet |
| `app/AUTOME_2.html:1815` · `Autometric-KOL-Module.html:1813` | `budget:9000` — budget campaign mock, satuan `$` | ❌ bukan EMV |
| `tests/test_view_metrics.py:556, 673` | fixture jumlah views | ❌ tidak berkaitan |
| **source code · migrations · SQL · docs `*.md`** | **NOL hit** | — |
| **git history** | **0 commit, 0 file** | — |

## 1.2 Rp9.000 dipakai untuk metric apa

**Estimated ROI. Hanya itu.**

Gue lacak seluruh formula yang merujuk `Lookup_Lists!$D$146`: **31 rujukan**,
dan **30 di antaranya kolom `KOL_Database.AS` baris 5–34** — yaitu
`Estimated ROI` untuk 30 creator contoh. Rujukan ke-31 adalah `#REF!` rusak di
`DIST_Normalized_Scores`.

```
KOL_Database.AS  Estimated ROI
  = Estimated Reach × ER% ÷ 100 × Lookup_Lists!$D$146 ÷ Rate Card
                                  └── CAL_VALUE_PER_ENG = 9000 ──┘
```

**Nol formula EMV merujuknya.** `KOL_Database` bahkan tidak punya kolom EMV —
blok COMMERCIAL-nya berisi CPV, CPE, CPM, Estimated Reach, Estimated ROI.

## 1.3 Jawaban langsung

| Pertanyaan | Jawaban |
|---|---|
| Rp9.000 dipakai untuk metric apa? | **Estimated ROI** — sebagai *value per engagement*, satu faktor di dalam rumus ROI |
| Pernah disebut sebagai EMV? | **Tidak. Nol kali.** Labelnya "Value per engagement (IDR)", keterangannya "used by Estimated ROI" |
| Atau hanya Estimated ROI / metric lain? | **Hanya Estimated ROI** — 30 dari 30 rujukan |
| Dari mana asal angka Rp9.000? | **Tidak diketahui.** Tidak ada komentar, dokumen, commit, atau business requirement yang menjelaskannya. Ia muncul sebagai konstanta tanpa sumber |
| Ada penjelasan di commit/docs? | **Tidak ada.** `git log --grep` untuk emv/cpm/cpv/earned → 0 commit |

## 1.4 Formula EMV `Reach × CPM ÷ 1000 × Multiplier` — audit ulang

| Komponen | Ada nilainya di project? | Bukti |
|---|---|---|
| **Reach** | ❌ | `unified_post.reach` **0/503** · `avg_reach` **0/27** · `feature.ig_post_analysis.reach` **0/212** · `l2_gold.post_metric.reach` **0/503** · `kol_metric_daily.reach_sum` **0/306** · `campaign_kols.reach` 0 baris |
| **CPM** | ❌ | `information_schema` 101 tabel, pola `%cpm%` → **0 kolom**. Di Excel CPM hanya *output* (`Rate ÷ Followers × 1000`). Di UI juga *output* (`rate/reach*1000`) — bukan konstanta input |
| **Multiplier** | ❌ | `%multiplier%` / `%coefficient%` / `%factor%` → **0 kolom**. Di Excel satu-satunya "multiplier" adalah `Risk Multiplier` (0,6/0,85/0,95/1) — pengali **Brand Safety**, bukan EMV. Di kedua prototype: 0 hit |
| Formula alternatif yang dipakai backend/product? | ❌ | UI **tidak menghitung EMV** — `emv:'$184K'` adalah literal hardcoded. Tabel campaign tracking prototype menampilkan `emv:'—'` |

**Uji rekayasa-balik:** 9 nilai EMV mock punya rasio `emv/reach` ≈ 0,30
(spread 13,5%) — konsisten dengan *bentuk* formula, dan menyiratkan
`CPM × multiplier ≈ 300`. **Tidak dipakai**: spread 13,5% berarti angkanya
dibulatkan manual bukan terhitung, hanya *hasil kali* yang tersirat (tidak bisa
dipisah), dan $300 CPM ≈ Rp4,7 juta per 1.000 reach — tidak masuk akal.

## 1.5 Status EMV: **HOLD**

**Rp9.000 TIDAK boleh dipakai sebagai EMV.** Ia value-per-engagement milik
Estimated ROI, dan memakainya sebagai EMV berarti mengarang metric.

**Tidak ada implementasi EMV dibuat.** `campaign_cost_metrics.py` sengaja tidak
punya fungsi `emv()`, dan
`tests/test_campaign_cost_metrics.py::test_tidak_ada_fungsi_emv_yang_dikarang`
serta `::test_tidak_ada_konstanta_9000_di_modul_biaya` menjaganya.

### Opsi paling aman untuk Product/Mentor

| Opsi | Isi | Penilaian |
|---|---|---|
| **A** | Tetap HOLD sampai CPM + Multiplier + Reach ada | ✅ **Paling aman.** Kolom `emv` sudah ada di 4 tempat; tidak ada yang perlu dibangun |
| **B** | Tetapkan CPM sebagai **benchmark pasar** (bukan turunan rate card), + multiplier, di config aplikasi | ⚠️ Bisa jalan **setelah** Reach ada. Butuh angka dari Product, bukan dari kita |
| **C** | Definisikan ulang EMV berbasis engagement (`engagement × value_per_engagement`) | ⚠️ **Bukan formula yang ada.** Kalau dipilih, ia definisi BARU yang harus disetujui eksplisit — dan Rp9.000 baru boleh dipakai kalau Product menyatakan angka itu berlaku untuk EMV, bukan cuma ROI |
| **D** | Pakai Rp9.000 apa adanya sebagai EMV | ❌ **Ditolak.** Nol evidence |

---

# 2. CPE — IMPLEMENTASI

**File:** `campaign_cost_metrics.py`

```
Total Engagement = Like + Comment + Share
CPE              = Cost ÷ Total Engagement
```

`Save`, `Reach`, `Views` **tidak** masuk penyebut — tercatat eksplisit di
`DIKELUARKAN_DARI_ENGAGEMENT` supaya penolakannya terbaca, bukan tersirat.

| Grain | Cost source | Konstanta |
|---|---|---|
| campaign × KOL | `campaign_kols.deal_price` | `COST_CAMPAIGN_KOL` |
| deliverable | `campaign_kol_deliverables.subtotal` | `COST_DELIVERABLE` |
| discovery / rate card | `l1_silver.unified_rate_card.fee` | `COST_DISCOVERY` |

`campaign_orders.total_amount` terdaftar di `COST_TERLARANG` dan diuji test.

**Guard:** cost NULL → NULL · engagement NULL (ketiganya) → NULL · engagement
0 → NULL · `NULLIF` di sisi SQL menutup division-by-zero. Cost 0 tetap
menghasilkan 0 — gratis itu angka, bukan ketiadaan data.

⚠️ **Catatan yang sengaja tidak gue "perbaiki":** penyebut ini beda dari
`transform.py`, yang menghitung ER roster `AVG(likes + comments)` **tanpa
shares**. Mengubahnya akan menggeser 1.736 nilai yang sudah dipakai filter dan
ranking — di luar lingkup task ini. Perbedaannya didokumentasikan di docstring
modul.

**Status: READY** (grain campaign × KOL & deliverable) ·
**PARTIAL** (discovery — `unified_rate_card` masih 0 baris).

---

# 3. CPV — IMPLEMENTASI

```
CPV = Cost ÷ Views          <- PER 1 VIEW
CPV_UNIT_FACTOR = 1
CPV_UNIT_LABEL  = "CPV / View"
```

Pengali 1000 dari prototype (`rate / views * 1000`, label `CPV / 1K views`)
**ditinggalkan**. Tiga lapis penjaga supaya tidak masuk kembali:

1. `CPV_UNIT_FACTOR` konstanta bernama, diuji `== 1`
2. `sql_cpv()` diuji **tidak boleh mengandung string `1000`**
3. `CPV_UNIT_LABEL` diuji tidak mengandung `1K`

| Aspek | Isi |
|---|---|
| Numerator | sama dengan CPE (`deal_price` / `subtotal` / `fee`) |
| Denominator | `campaign_content_performance.views` · `l2_gold.post_metric.views` (397/503) · `avg_views` (30) |
| Unit | **IDR per 1 view** |
| Kolom baru | **NOL** — tidak ada kolom `cpv` di DB, dan tidak ditambah |

⚠️ Di grain campaign × KOL, CPV **wajib agregasi** dari
`campaign_content_performance` karena `campaign_kols` tidak punya kolom
`views`. Aturan agregasi `snapshot_date` **belum ada** — masih HOLD.

**Status: READY** (fungsi + guard) · **PARTIAL** (agregasi campaign menunggu
aturan snapshot).

---

# 4. REACH — HASIL AUDIT

**Source of truth: Instagram/TikTok Insights. Dan hasilnya kosong total.**

| Tabel Insights (`*_official`) | Baris | `reach` terisi |
|---|---:|---:|
| `l0_raw.ig_media_snapshots_official` | **0** | 0 |
| `l0_raw.ig_profile_official` | **0** | 0 |
| `l0_raw.ig_stories_official` | **0** | 0 |
| `l0_raw.tt_video_official` | **0** | — |
| `l0_raw.tt_profile_official` | **0** | — |

Seluruh rantai hilirnya ikut kosong:

| Tabel | Baris | `reach` terisi |
|---|---:|---:|
| `l0_harmonization.instagram_post` | 212 | **0** |
| `l1_silver.unified_post` | 503 | **0** |
| `l1_silver.unified_profile` | 2.009 | **0** |
| `l2_gold.post_metric` | 503 | **0** |
| `l2_gold.kol_metric_daily.reach_sum` | 306 | **0** |
| `feature.ig_post_analysis` | 212 | **0** |
| `feature.ig/tt_audience_analysis.avg_reach` | 27 | **0** |

**Akar penyebabnya:** `public.social_account` — 7.208 akun,
**`connected = true` untuk 0 akun**, **`oauth_token` terisi 0**, dan
`data_source` hanya `apify` (scraping) + `csv` (roster import). **Tidak ada
satu pun akun yang tersambung Insights**, jadi jalurnya memang belum pernah
hidup.

`l0_raw.kol_roster_import.estimated_reach` **TIDAK dijadikan canonical** sesuai
keputusan — dan verifikasi gue mendukung itu: dari 7.161 baris yang bisa
di-join, **2.164 baris punya reach > followers**, dengan median rasio 1,494 di
satu platform. Terindikasi CSV column shift.

**Gap-nya: OAuth/Insights connection belum ada sama sekali.** Bukan masalah
ETL, bukan masalah kolom. Tidak ada fallback diam-diam yang gue pasang.

---

# 5. STYLE & PERSONALITY — IMPLEMENTASI

## 5.1 Taxonomy final: 40 baris

| Group | Jumlah | excel | ui | excel+ui |
|---|---:|---:|---:|---:|
| `content_style` | 11 | 5 | 1 | 5 |
| `communication_style` | 9 | 8 | 1 | 0 |
| `creator_personality` | 13 | 5 | 1 | 7 |
| `visual_style` | 7 | 0 | 7 | 0 |
| **TOTAL** | **40** | **18** | **10** | **12** |

**Nol nilai dibuang.** `source_origin` merekam asal tiap baris.

- **Hanya UI (10):** Commentary · Demonstration · Expert · Aesthetic\* ·
  Casual\* · Professional\* · Cinematic · Colorful · Lifestyle · Minimalist
  *(\* di sumbu `visual_style`)*
- **Hanya Excel (19):** Demo · Comedy · Demonstrative · Conversational ·
  Data-driven · Visual-first · Testimonial · Creative · Tech-savvy · Reviewer ·
  Premium · Luxury · dan Educational/Aesthetic/Entertaining di sumbu masing-masing

**Tidak dimasukkan:** Brand Personality (10) + Brand Tone (8) — atribut brand.
Diuji `test_brand_personality_dan_brand_tone_tidak_ikut`.

**Alias `Demo` / `Demonstrative` / `Demonstration`:** ketiganya
**dipertahankan terpisah**. Menggabungkannya keputusan bisnis yang belum
diambil; dicatat di `kol_attribute_taxonomy.ALIAS_BELUM_DIPUTUSKAN`.

## 5.2 Struktur

`migrations/045_kol_attribute_taxonomy.sql` — **belum dijalankan**.

```
public.kol_attribute            master, 40 baris
  UNIQUE (kind, attribute_group, attribute_key)
  CHECK  kind IN (style, personality)
  CHECK  attribute_group IN (4 grup)
  CHECK  source_origin IN (excel, ui, excel+ui)

public.kol_attribute_map        junction, kosong
  FK     kol_directory_id -> public.kol_directory(id)
  FK     kol_attribute_id -> public.kol_attribute(id)
  UNIQUE (kol_directory_id, kol_attribute_id)
  INDEX  ix_kol_attribute_map_directory
```

**Kenapa kunci `(kind, group, key)`:** `Educational` sah muncul di 3 grup
dengan arti berbeda. Blok verifikasi migration meng-assert `Educational`
muncul **tepat 3 kali** — kalau tinggal 1, berarti kuncinya salah.

**Kenapa map ke `kol_directory`:** cakupan terluas (7.432), preseden
`category_ids` di tabel yang sama, bukan per-agency. `COMMENT ON COLUMN`
menyatakan terang bahwa ini **atribut AKUN, bukan orang**.

**Person table TIDAK dibuat**, `influencer_id` **tidak** jadi FK — sesuai
keputusan, dan didukung audit: 20 `influencer_id` memuat 3+ akun dan
seluruhnya mencampur orang berbeda (`8372` = 43 kreator tak berhubungan).

## 5.3 Sifat migration

Aditif sepenuhnya: `CREATE TABLE IF NOT EXISTS` ×2, `CREATE INDEX IF NOT
EXISTS` ×1, `INSERT … ON CONFLICT DO NOTHING`. **Nol** `DROP`, `TRUNCATE`,
`DELETE`, `ALTER` terhadap tabel existing. Blok `DO $verifikasi$` membatalkan
transaksi kalau hasilnya tidak sesuai — termasuk memastikan tidak ada kolom
`style`/`cpe`/`cpv`/`emv` yang muncul di `l2_gold.kol_profile_card`.

**Status: READY untuk dijalankan** setelah approval.

---

# 6. WHAT MATTERS MOST — HOLD

Tidak diimplementasikan. Tidak ada tabel, tidak ada kolom, tidak ada formula.

| Kriteria | Source | Status |
|---|---|---|
| Strong Engagement | `kol_directory.engagement_rate` (1.736) | real |
| High Audience Quality | `audience_quality_score` + `authenticity_score` (27) | real, cakupan 0,36% |
| Consistent Performance | — | **mock** (`k.cons` = hash creator id) |
| Strong Company/Community | — | **mock** (`k.aff` tanpa kolom DB) |
| High Reach | `reach` **0 terisi**; proksi `avg_views` (30) | proksi |
| Content Quality | — | **belum ada source** |
| Brand Safety | — | **belum ada source** (butuh sentiment, 0 baris) |

Alasan HOLD: 4 dari 7 tidak punya source valid, dan fungsinya (preference vs
score) belum diputuskan Product.

---

# 7. FILE YANG DIUBAH & HASIL TEST

## Dibuat

| File | Baris | Isi |
|---|---:|---|
| `campaign_cost_metrics.py` | ~200 | CPE, CPV, total engagement, ekspresi SQL, konstanta cost source. **Tanpa EMV** |
| `kol_attribute_taxonomy.py` | ~230 | 40 baris taxonomy + generator seed SQL + alias yang belum diputuskan |
| `migrations/045_kol_attribute_taxonomy.sql` | 303 | 2 tabel + seed 40 baris + blok verifikasi. **Belum dijalankan** |
| `tests/test_campaign_cost_metrics.py` | ~200 | 30 test |
| `tests/test_kol_attribute_taxonomy.py` | ~290 | 31 test |
| `docs/KOL_IMPLEMENTASI_CPE_CPV_TAXONOMY.md` | — | dokumen ini |

## Tidak diubah

Nol file existing disentuh. Nol business logic lain diubah. Nol perubahan DB.

## Hasil test

```
tests/test_campaign_cost_metrics.py    30 passed
tests/test_kol_attribute_taxonomy.py   31 passed
tests/  (seluruh suite)               983 passed, 7 subtests passed, 0 failed
```

Termasuk guard lama yang jalan terhadap DB hidup dan tetap hijau:
`test_db_metrik_blocked_tidak_punya_kolom` ·
`test_db_emv_cpe_tetap_null_selama_rate_card_kosong` ·
`test_db_brand_fit_masih_kosong`.

## Blocker tersisa

| # | Blocker | Menghambat |
|---:|---|---|
| B1 | Nilai **CPM** + granularitas | EMV |
| B2 | Nilai **Multiplier** | EMV |
| B3 | **Insights/OAuth belum tersambung** — 0 dari 7.208 akun | EMV, High Reach, avg_reach |
| B4 | **Aturan agregasi `snapshot_date`** | CPV campaign × KOL |
| B5 | `l1_silver.unified_rate_card` **0 baris** (sumbernya ada di `l0_raw.kol_roster_import`, 93,7%) | CPE/CPV discovery |
| B6 | `post_type` basis fee + sentinel `1.000.000.000` | propagasi rate card |
| B7 | Alias `Demo`/`Demonstrative`/`Demonstration` | isi taxonomy (40 atau 39) |
| B8 | Fungsi **What Matters Most** | 7 kriteria |
| B9 | Tabel campaign **0 baris** | CPE/CPV belum bisa diuji atas data nyata |

## Cara menjalankan migration (belum dilakukan)

```
python apply_migration.py migrations/045_kol_attribute_taxonomy.sql --dry-run
python apply_migration.py migrations/045_kol_attribute_taxonomy.sql --yes
```
