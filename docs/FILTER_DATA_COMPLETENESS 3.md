# KOL Discovery — Kelengkapan Data Filter

**Task 3** · Database `kol` @ 10.100.14.216 — sesi read-only · 2026-09-03
**Populasi / denominator:** `public.kol_directory` = **7.720 KOL**
**Input:** `docs/KOL_DISCOVERY_FILTER_REQUIREMENTS.md` (Task 1) ·
`docs/KOL_DISCOVERY_FILTER_DB_MAPPING.md` (Task 2 + Correction)

> ### Status dokumen — direvisi 2026-09-06
>
> Kerangka tiga lapis (relationship / data / usable) di §1 **tetap berlaku dan tetap jadi
> cara baca yang benar.** Empat angka di dalamnya yang berubah:
>
> 1. **Last Updated bukan COMPLETE.** Terisi 97,1%, tapi **73,6% nilainya bukan jejak scrape**
>    — warisan excel import. Rekapitulasi `COMPLETE 1` menjadi `COMPLETE 0`.
> 2. **§5.5 mencampur dua denominator** — "Macro 1.123" dan "Macro 1.290" mengukur populasi
>    yang berbeda.
> 3. **`followers_growth` periodenya 10–13 hari**, bukan 30 — jadi §3.5 benar, tapi sebabnya
>    lebih berat dari yang ditulis.
> 4. **Kedalaman snapshot profil tidak terukur** di dokumen ini: 0 akun punya 3 snapshot.
>
> Detail di **§Revisi 2026-09-06** di akhir dokumen. Coverage final:
> `docs/KOL_DISCOVERY_TASK5_DESIGN.md` §3.

> ### Revisi kedua — 2026-09-07 (implementasi)
>
> Sejak revisi di atas, empat hal **sudah dikerjakan dan diverifikasi**, bukan lagi temuan:
>
> 1. **Batas tier `kol_tiers` dibetulkan** (migration 033) — §5.5 tidak lagi menggambarkan
>    dua ambang yang bertentangan.
> 2. **P-01 ditutup** (migration 034) — 54 KOL di bawah 1rb tidak lagi bertier `Nano`.
> 3. **Connected dipasang**, **Verified dihapus** dari Discovery — "Verified only" di
>    rekapitulasi MISSING sekarang bukan lagi filter yang direncanakan.
> 4. **Growth dikirim ke UI** memakai `followers_growth` (25 KOL), berlabel
>    "Sejak Snapshot Terakhir".
>
> Detail di **§Revisi 2026-09-07** di akhir dokumen. Kalau bertentangan dengan §1–§6
> maupun dengan revisi 2026-09-06, **section terbaru yang berlaku**.

> ### Revisi ketiga — 2026-09-09 (implementasi lanjutan)
>
> Sejak revisi kedua, **sembilan** hal berubah lagi — termasuk satu keputusan yang
> dibalik:
>
> 1. **Verified kembali ke Discovery** dengan sumber baru
>    (`l2_gold.kol_profile_card.is_verified`, **572 KOL**), terpisah tegas dari Connected.
> 2. **ER memakai `feature.*_engagement_analysis` lebih dulu** — cakupan 1.757 → **1.767**.
> 3. **Kategori disaring lewat `taxonomy_key`**, dan chip-nya jadi **15**.
> 4. **Followers punya dua nilai** (roster vs L2, beda di 1.024 akun); migration 035
>    memasang **sanity guard**.
> 5. **Rate card bukan "tanpa source"** — source dan procedure-nya ada, asset-nya tidak.
> 6. **Last Updated dan Agency jadi filter yang jalan.**
> 7. **Identitas dibaca dari L2** — avatar 931 → 1.979, bio 902 → 1.878, display name 0 → 1.961.
> 8. **`SCRAPED_FIRST` dibuang**, tie-break berakhir di `id`.
> 9. **Dominant format & heatmap jam posting** naik ke endpoint detail.
>
> Detail di **§Revisi 2026-09-09** di akhir dokumen — **section itu yang paling berlaku**.

---

## 1. Scope & Denominator

### Yang diukur

Task 2 menjawab **"filter ini datanya ada di mana"**. Task 3 menjawab
**"dari 7.720 KOL, berapa yang benar-benar punya datanya, dan berapa yang
nilainya bisa dipakai"**. Tidak ada filter baru yang dibuat.

Seluruh angka di dokumen ini hasil query langsung ke database pada 2026-09-03.
Yang tidak ditemukan ditulis apa adanya, tidak diperkirakan.

### Tiga lapis pengukuran — dan kenapa dibedakan

| Lapis | Pertanyaan | Contoh |
|---|---|---|
| **Relationship coverage** | Berapa KOL yang *bisa* dijangkau JOIN-nya? | 7.496 KOL punya `social_account` = 97,1% |
| **Data coverage** | Berapa yang field-nya benar-benar terisi? | 0 KOL punya `oauth_token` = 0% |
| **Usable** | Berapa yang nilainya lolos threshold UI / masuk akal? | 0 KOL lolos "Verified only" |

**Relationship coverage adalah plafon, bukan hasil.** Verified only adalah contoh
paling ekstremnya: jalur JOIN-nya sehat 97,1%, tapi filternya tetap 0% karena
kolom di ujung jalur itu kosong. Angka yang menentukan pengalaman pengguna adalah
kolom **Usable** — bukan Relationship.

Di seluruh dokumen ini, **Coverage % dihitung dari kolom Usable ÷ 7.720**.

### Aturan penghitungan

- **Time-series dihitung per KOL unik**, bukan per baris. `kol_metric_monthly`
  punya 30 KOL, tapi hanya 5 yang punya ≥4 titik bulanan — yang dipakai adalah 5.
- **Filter derived diukur di dua tempat**: coverage tiap field dasarnya (§4),
  lalu coverage hasil akhirnya (irisan semua field + threshold).
- **Verified only** memakai definisi hasil koreksi Task 2:
  `social_account.oauth_token IS NOT NULL` = KOL sudah connect/OAuth ke sistem,
  **bukan** centang biru platform. Nilai token tidak pernah di-SELECT.
- **Location kreator** memakai hasil re-validation Task 2, dan **dipisahkan tegas**
  dari Audience location. `audience_geo_daily` tidak dipakai untuk filter kreator.
- **Penomoran mengikuti Task 2** (32 filter; chip Kategori di header digabung ke
  No. 2 karena menulis state yang sama).

### Status

| Status | Artinya |
|---|---|
| **COMPLETE** | Data terisi memadai, filter jalan sebagaimana dirancang |
| **PARTIAL** | Ada datanya, tapi coverage rendah atau sebagian opsi UI kosong |
| **MISSING** | Tidak ada sumber terpakai — 0 baris atau 0 nilai berguna |
| **DERIVED — INCOMPLETE** | Rumusnya bisa dijalankan, tapi field dasarnya belum memadai |
| **SYNTHETIC / PROTOTYPE ONLY** | Nilainya diciptakan prototype (hash ID / hardcode / state browser), bukan data DB |

Kalau satu filter kena beberapa kondisi, yang dipakai adalah **kondisi yang memblokir**.

---

## 2. Summary Coverage — 32 Filter

| Filter | Source | Total KOL | Data Tersedia | Usable | Coverage | Status |
|---|---|---:|---:|---:|---:|---|
| 1 · Platform | `kol_directory.platform_id` → `platforms.key` | 7.720 | 7.496 | 7.496 | 97,1% | **PARTIAL** |
| 2 · Kategori KOL | `category_ids` → `kol_categories.taxonomy_key` | 7.720 | 4.174 | 4.155 | 53,82% | **PARTIAL** |
| 3 · KOL Tier | `kol_directory.followers_count` | 7.720 | 7.498 | 7.194 | 93,2% | **PARTIAL** |
| 3b · ↳ via L2 | `l2_gold.kol_profile_card.tier` | 7.720 | 1.972 | 1.972 | 25,5% | **PARTIAL** |
| 4 · Gender skew | `audience_demographics_daily` (`gender`) | 7.720 | 23 | 17 | 0,22% | **DERIVED — INCOMPLETE** |
| 5 · Verified only | `social_account.oauth_token` | 7.720 | **0** | **0** | **0%** | **MISSING** |
| 6 · Age | `audience_demographics_daily` (`age`) | 7.720 | **0** | **0** | **0%** | **MISSING** |
| 7 · Location (kreator) | `kol_directory.creator_city` | 7.720 | **0** | **0** | **0%** | **MISSING** |
| 8 · Audience location | `audience_geo_daily` (`level='city'`) | 7.720 | 15 | 15 | 0,19% | **PARTIAL** |
| 9 · Audience interest | `audience_interest_daily.interest_key` | 7.720 | 23 | 23 | 0,30% | **PARTIAL** |
| 10 · Audience Quality | `feature.{ig,tt}_audience_analysis` | 7.720 | 23 | 23 | 0,30% | **PARTIAL** |
| 11 · Content Category/Topic | — | 7.720 | — | — | — | **SYNTHETIC / PROTOTYPE ONLY** |
| 12 · Content Format | `content_format_daily.media_type` | 7.720 | 30 | 29 | 0,38% | **PARTIAL** |
| 13 · Content Style & Personality | — | 7.720 | — | — | — | **SYNTHETIC / PROTOTYPE ONLY** |
| 14 · Engagement Rate | `kol_metric_daily.er_followers_daily` | 7.720 | 22 | 1 | 0,01% | **PARTIAL** |
| 14b · ↳ alternatif | `kol_directory.engagement_rate` | 7.720 | 1.756 | 219 | 2,84% | **PARTIAL** |
| 15 · Save Rate | `post_metric.saves` | 7.720 | 11 | 4 | 0,05% | **PARTIAL** |
| 16 · Share Rate | `post_metric.shares` | 7.720 | 11 | 7 | 0,09% | **PARTIAL** |
| 17 · Views | `post_metric.views` | 7.720 | 29 | 21 | 0,27% | **PARTIAL** |
| 18 · Reliability | — *(tidak ada kolom)* | 7.720 | **0** | **0** | **0%** | **MISSING** |
| 19 · Performance Stability | `kol_metric_monthly` (≥4 bulan) | 7.720 | 30 | 5 | 0,06% | **DERIVED — INCOMPLETE** |
| 20 · Viral Frequency | `kol_metric_monthly` (≥4 bulan) | 7.720 | 30 | 5 | 0,06% | **DERIVED — INCOMPLETE** |
| 21 · Growth Classification | `kol_profile_card.followers_growth` | 7.720 | 25 | 25 | 0,32% | **DERIVED — INCOMPLETE** |
| 22 · Rising Creator | growth + ER + followers | 7.720 | 21 | **0** | **0%** | **DERIVED — INCOMPLETE** |
| 23 · Data Status | `last_refreshed_at` ÷ interval | 7.720 | 7.496 | **0** | **0%** | **MISSING** |
| 24 · Last Updated | `kol_directory.last_refreshed_at` | 7.720 | 7.496 | 7.496 | 97,1% | **COMPLETE** |
| 25 · Update Frequency | `kol_directory.refresh_tier` | 7.720 | **0** | **0** | **0%** | **MISSING** |
| 26 · Next Update | `last_refreshed_at` + interval | 7.720 | 7.496 | **0** | **0%** | **MISSING** |
| 27 · Monitoring Priority | campaign + growth + virality | 7.720 | 25 | **0** | **0%** | **MISSING** |
| 28 · Keyword search | `username` · `bio` · kategori | 7.720 | 7.497 | 7.497 | 97,1% | **PARTIAL** |
| 29 · Smart Criteria (NL) | 29 aturan, beragam sumber | 7.720 | — | — | — | **PARTIAL** |
| 30 · Section tabs | `created_at` · `last_refreshed_at` dll | 7.720 | 7.698 | 7.698 | 99,7% | **PARTIAL** |
| 31 · Exclude | `campaigns` · `campaign_kols` | 7.720 | **0** | **0** | **0%** | **MISSING** |
| 32 · Collections | — *(state browser)* | 7.720 | — | — | — | **SYNTHETIC / PROTOTYPE ONLY** |

> **3b** dan **14b** sumber alternatif untuk filter yang sama, bukan filter tambahan
> — total tetap **32**.

### Rekapitulasi

| Status | Jumlah |
|---|---:|
| **COMPLETE** | 1 |
| **PARTIAL** | 14 |
| **DERIVED — INCOMPLETE** | 5 |
| **MISSING** | 9 |
| **SYNTHETIC / PROTOTYPE ONLY** | 3 |
| **Total** | **32** |

### Sebaran coverage

| Rentang coverage | Filter | Jumlah |
|---|---|---:|
| **>90%** | Platform · KOL Tier *(via followers)* · Last Updated · Keyword · Section tabs | 5 |
| **20–90%** | Kategori | 1 |
| **<1%, >0** | Gender · Aud. location · Aud. interest · Aud. Quality · Content Format · Engagement Rate · Save · Share · Views · Stability · Viral · Growth | 12 |
| **0%** | Verified · Age · Location kreator · Reliability · Data Status · Update Freq · Next Update · Monitoring · Exclude · Rising Creator | 10 |
| **Tidak ada padanan DB** | Content Category · Content Style · Collections | 3 |
| **Tidak punya satu angka tunggal** | Smart Criteria *(29 aturan, mewarisi filter lain)* | 1 |
| | | **32** |

*(Dua sumber alternatif — Tier via L2 25,5% dan ER via `kol_directory` 21,7% —
tidak dihitung terpisah; keduanya masuk ke filter induknya.)*

**Angka yang paling menentukan: 12 filter berada di bawah 1% coverage, dan 10 filter
tepat 0%.** Artinya 22 dari 32 filter praktis tidak bisa dipakai untuk menyaring
populasi hari ini.

> **⚠️ Koreksi rekapitulasi (2026-09-06): `COMPLETE` bukan 1, melainkan 0.**
> Satu-satunya isinya — **Last Updated** — turun ke `PARTIAL`. Field-nya terisi 97,1% dan
> tiap KOL memang jatuh di salah satu bucket, tapi untuk **5.520 dari 7.496 baris (73,6%)**
> nilai itu **tidak berasal dari scrape**: KOL-nya tidak punya satu baris pun di `l0_raw`.
> Bucket-nya benar; yang diukur bukan yang dikira. Lihat §Revisi R1.
>
> Rekapitulasi yang berlaku: **COMPLETE 0 · PARTIAL 15 · DERIVED–INCOMPLETE 5 · MISSING 9 ·
> SYNTHETIC 3**. Dan denominatornya bukan lagi 32 melainkan **40** — baseline berpindah ke
> app produksi (`FILTER_REQUIREMENTS 1.md` §Revisi).

---

## 3. Detail per Kategori Filter

### 3.1 Creator Profile (7 filter)

| Filter | Data | Usable | Coverage | Catatan |
|---|---:|---:|---:|---|
| Platform | 7.496 | 7.496 | 97,1% | Chip **YouTube** tidak punya baris sama sekali |
| Kategori KOL | 4.174 | 4.155 | 53,82% | 22 dari 28 kategori DB ter-map ke 9 Discovery Category |
| KOL Tier | 7.498 | 7.194 | 93,2% | Dihitung dari `followers_count` |
| Gender skew | 23 | 17 | 0,22% | Perlu renormalisasi `unknown` |
| Verified only | 0 | 0 | 0% | Belum ada KOL yang connect |
| Age | 0 | 0 | 0% | `audience_type` hanya berisi `gender` |
| Location (kreator) | 0 | 0 | 0% | Kolom ada, data belum terisi |

**Platform** — `platforms` hanya berisi dua baris terpakai: tiktok 4.087,
instagram 3.409. Chip **YouTube** di UI mengembalikan 0 hasil, bukan karena
filternya salah tapi karena tidak ada KOL YouTube di database. 224 KOL sisanya
tidak punya `platform_id` sama sekali.

**Kategori KOL** — 4.174 KOL punya kategori, tapi UI hanya menyediakan 5 chip.
Irisannya:

| Chip UI | Kategori DB | KOL |
|---|---|---:|
| Lifestyle | `Lifestyle` | 2.592 |
| Beauty | `Beauty` | 1.271 |
| Food | `Foodies` + `Food` + `Cooking` | 123 |
| Fitness | `Fitness` | 52 |
| Tech | `Technology and gadgets` + `Gaming` | **4** |
| | **Total usable** | **3.487** |

**668 KOL berkategori jadi tidak terjangkau chip mana pun** — termasuk dua
kategori terbesar berikutnya di database: `Entertainment` (501) dan `Moms` (589).
Chip **Tech** secara praktis mati: hanya 4 KOL.

**KOL Tier — coverage jauh lebih baik lewat `followers_count`, bukan L2.**
Task 2 memetakan filter ini ke `kol_profile_card.tier` (1.972 KOL · 25,5%).
Padahal tier adalah fungsi murni dari jumlah follower, dan `kol_directory.followers_count`
terisi untuk 7.498 KOL:

| Bucket UI | KOL |
|---|---:|
| Nano 1K–10K | 1.943 |
| Micro 10K–50K | 2.942 |
| Mid-tier 50K–500K | 1.809 |
| Macro 500K–1M | 187 |
| Mega >1M | 313 |
| **Total masuk chip** | **7.194 · 93,2%** |
| <1K (di luar semua chip) | 304 |
| Tanpa data | 222 |

**Selisihnya 3,6× lipat: 7.194 vs 1.972.** Tapi ada syaratnya — lihat §5.5 soal
batas tier UI yang berbeda dari tabel `kol_tiers`.

**Gender skew — angka Task 2 perlu diperbaiki.** Task 2 §3.4 menyatakan 0 KOL
lolos kedua chip. Itu benar **kalau `unknown` ikut masuk penyebut**. Kalau
`unknown` dikeluarkan (renormalisasi, yang memang cara wajar membaca data ini):

| Perhitungan | Female ≥60% | Male ≥55% |
|---|---:|---:|
| Penyebut mentah (termasuk `unknown`) | **0** | **0** |
| Penyebut direnormalisasi (tanpa `unknown`) | **7** | **10** |

Jadi filternya **bisa** mengembalikan hasil — 17 KOL dari 23 yang punya data —
asal rumusnya mengeluarkan `unknown` lebih dulu. Rata-rata porsi `unknown`
tetap **71,3%**, jadi hasilnya dihitung dari 28,7% audiens yang gendernya diketahui.

**Verified only** — relationship 7.496 (97,1%), data **0**. Lima kolom koneksi
di `social_account` (`oauth_token`, `connected`, `connected_at`, `refresh_token`,
`token_expires_at`) seluruhnya kosong/false; `data_source` = csv 7.494 / apify 2.
Detail lengkap ada di Task 2 §4.1.

**Age** — `audience_demographics_daily` hanya punya satu `audience_type`:
`gender` (69 baris · 23 akun). Tidak ada satu baris pun ber-`audience_type='age'`.
Ketiga bucket umur di UI tidak punya sumber.

---

### 3.2 Audience (3 filter)

| Filter | Data | Usable | Coverage | Catatan |
|---|---:|---:|---:|---|
| Audience location | 15 | 15 | 0,19% | 9 dari 33 key bukan kota |
| Audience interest | 23 | 23 | 0,30% | 85,2% bobot = `unknown` |
| Audience Quality | 23 | 23 | 0,30% | Bucket "High (85+)" hanya 1 KOL |

**Audience location** — `geo_level` hanya `country` (23 KOL) dan `city` (15 KOL).
Tidak ada level `province`. Dari 33 key ber-`geo_level='city'`, **9 sebenarnya
provinsi atau pulau** — `Bali`, `Jawa`, `Jawa Tengah`, `Kalimantan Barat`,
`Sulawesi`, `Sulawesi Selatan`, `Sulawesi Tenggara`, `Banten`, `Lampung` —
menyentuh 10 dari 15 KOL. Dropdown kota akan mencampur "Bandung" dengan "Sulawesi".

**Audience interest** — 19 key unik, 23 KOL, dan **ke-23 KOL punya minimal satu
minat non-`unknown`**. Tapi dari sisi bobot, `unknown` mendominasi:

| | Baris | Bobot (`audience_count`) |
|---|---:|---:|
| Minat diketahui | 191 | 350 |
| `unknown` | 23 | **2.021** |
| | | **85,2% bobot = unknown** |

Jadi filternya bisa jalan untuk 23 KOL, tapi peringkat minatnya dihitung dari
14,8% audiens saja.

**Audience Quality** — skor `(authenticity + audience_quality) / 2`, perlu UNION
`feature.ig_audience_analysis` (13 akun) + `feature.tt_audience_analysis` (10 akun).
Kedua tabel 100% terisi untuk baris yang ada. Sebaran vs bucket UI:

| Bucket UI | KOL |
|---|---:|
| High (85+) | **1** |
| Good (75+) | 3 |
| Below 75 | 20 |

Rentang skor 43,5–90,0. Bucket "High (85+)" secara teknis **tidak kosong** —
berisi 1 KOL. *(Task 2 memperkirakan maksimum 88; angka sebenarnya 90,0.)*

---

### 3.3 Content (3 filter)

| Filter | Data | Usable | Coverage | Catatan |
|---|---:|---:|---:|---|
| Content Category / Topic | — | — | — | SYNTHETIC |
| Content Format | 30 | 29 | 0,38% | Opsi **Story** 0 KOL |
| Content Style & Personality | — | — | — | SYNTHETIC |

**Content Format** — 30 KOL punya baris `content_format_daily`, tapi 3 di antaranya
hanya ber-`media_type='unknown'` sehingga tidak terpetakan ke opsi UI mana pun →
usable **29**. Setelah mapping:

| Opsi UI | Sumber `media_type` | KOL |
|---|---|---:|
| Reels | `clips` | 18 |
| Carousel | `carousel_container` 14 + `CAROUSEL` 2 | 16 |
| Feed | `feed` | 11 |
| Video *(grup)* | `clips` + `VIDEO` | 29 |
| Photo *(grup)* | `feed` + `carousel_container` + `CAROUSEL` | 18 |
| **Story** | — | **0** |
| *(tak terpetakan)* | `unknown` | 3 |

Opsi **Story** tidak punya sumber: `l1_silver.unified_story` = **0 baris**.
Perhatikan juga penamaan `media_type` belum konsisten antar-platform
(`CAROUSEL` vs `carousel_container`) — mapping harus menangani keduanya.

**Content Category/Topic** dan **Content Style & Personality** tidak punya padanan
kolom di database. Di prototype nilainya dihasilkan dari hash ID / daftar hardcode.
Ditandai **SYNTHETIC / PROTOTYPE ONLY** — bukan data DB.

---

### 3.4 Performance (7 filter)

| Filter | Data | Usable | Coverage | Catatan |
|---|---:|---:|---:|---|
| Engagement Rate *(L2)* | 22 | 1 | 0,01% | Satuan fraksi → perlu ×100 |
| Engagement Rate *(alt)* | 1.756 | 219 | 2,84% | 83 nilai di atas batas wajar |
| Save Rate | 11 | 4 | 0,05% | TikTok saja |
| Share Rate | 11 | 7 | 0,09% | TikTok saja |
| Views | 29 | 21 | 0,27% | 3 KOL rata-rata >10 juta views |
| Reliability | 0 | 0 | 0% | Tidak ada kolom di seluruh DB |
| Performance Stability | 30 | 5 | 0,06% | Butuh ≥4 titik bulanan |
| Viral Frequency | 30 | 5 | 0,06% | Butuh ≥4 titik bulanan |

**Engagement Rate — dua sumber, dua masalah berbeda.**

| Sumber | Data | ≥3% | ≥5,5% | Rentang | Masalah |
|---|---:|---:|---:|---|---|
| `kol_metric_daily.er_followers_daily` | 22 | 1 | 1 | 0,00–16,15% | Coverage 0,28% |
| `kol_directory.engagement_rate` | 1.756 | 219 | 137 | maks **223,41%** | 83 baris >10% |

Yang L2 nilainya benar tapi cakupannya 80× lebih sempit. Yang di `kol_directory`
cakupannya luas tapi **83 nilai mustahil secara matematis** (ER di atas 100%).
Kalau 83 baris itu dibuang, sisa 1.673 nilai yang masuk akal (21,7%).

**Save Rate & Share Rate — hanya TikTok, dan rumus prototype tidak memakai kolomnya.**
11 KOL punya `saves`/`shares`, **seluruhnya TikTok** — 0 dari Instagram, karena
metrik ini tidak tersedia lewat scraping publik IG. Diuji pada threshold UI:

| Filter | Threshold | KOL lolos |
|---|---|---:|
| High Save Rate | ≥5% | 4 |
| High Share Rate | ≥1,8% | 7 |

Catatan penting dari Task 2 §3.5 tetap berlaku: prototype **tidak memakai** kolom
`saves`/`shares` sama sekali, melainkan rumus turunan dari *audience affinity*
yang tidak punya padanan kolom di DB. Angka di atas adalah coverage untuk
**rumus yang benar**, bukan rumus prototype.

**Views** — 29 KOL, 21 lolos ≥150K, 18 lolos ≥300K. Tapi sebarannya ekstrem:
median rata-rata views 474.870, maksimum **78.091.457**, dan **3 KOL punya
rata-rata di atas 10 juta**. Angka setinggi itu perlu diverifikasi sebelum
dipakai menyaring.

**Reliability — tidak ada sumbernya, dan ini sudah dipastikan.** Penyapuan seluruh
katalog untuk nama kolom yang mengandung
`consist|reliab|stabil|volatil|viral|cadence|frequency|posting_freq`
mengembalikan **nol kolom di seluruh database**. Prototype memakai `k.cons`
(hash-based). Kedua chip Reliability tidak punya jalan untuk dihitung.

**Performance Stability & Viral Frequency — kedalaman deret waktu, bukan lebar.**
Keduanya butuh deret bulanan. Diukur per **KOL unik**:

| Kedalaman | KOL |
|---|---:|
| Punya `kol_metric_monthly` | 30 |
| ≥2 bulan | 18 |
| ≥3 bulan | 12 |
| **≥4 bulan** *(minimum untuk volatilitas)* | **5** |
| ≥6 bulan | **0** |
| Maksimum yang dimiliki satu KOL | 5 bulan |

Tidak ada satu pun KOL dengan riwayat 6 bulan. Volatilitas dan frekuensi viral
yang dihitung dari 4–5 titik akan sangat sensitif terhadap satu bulan anomali.

---

### 3.5 Growth (2 filter)

| Filter | Data | Usable | Coverage | Catatan |
|---|---:|---:|---:|---|
| Growth Classification | 25 | 25 | 0,32% | 3 dari 4 bucket UI kosong |
| Rising Creator | 21 | **0** | **0%** | Threshold tidak terjangkau |

**Growth Classification — datanya ada, tapi semuanya jatuh di satu bucket.**

`kol_profile_card.followers_growth` berisi **persen** — dipastikan oleh
`migrations/025_fix_followers_growth_type.sql` (yang mengubah tipe `bigint` →
`numeric` justru supaya nilai persen tidak hilang) dan komentar
`gold_profile.py:120` *("PERSEN, dari snapshot yang sama")*.

Rentang nyatanya: **−0,051% s.d. +0,917%**. Dibandingkan threshold UI:

| Bucket UI | Threshold | KOL lolos |
|---|---|---:|
| Exploding | ≥8% | **0** |
| Rising | ≥4,5% | **0** |
| Stable | ≥1% | **0** |
| Declining | <1% | **25** |

**Seluruh 25 KOL masuk "Declining", termasuk yang pertumbuhannya positif.**
Nilai tertinggi di seluruh database (+0,917%) masih di bawah lantai bucket
"Stable" (≥1%). Tiga chip pertama akan selalu mengembalikan nol hasil — bukan
karena datanya kurang, tapi karena **threshold UI dirancang untuk skala
pertumbuhan bulanan sementara data yang ada adalah selisih antar-snapshot
berjarak pendek**. Ini keputusan produk, bukan pekerjaan data.

**Rising Creator — irisan tiga field, lalu terhenti di threshold.**

| Syarat | KOL |
|---|---:|
| Punya `followers_growth` | 25 |
| Punya `er_followers_daily` | 22 |
| Punya `followers_count` | 7.498 |
| **Punya ketiganya sekaligus** | **21** |
| Lolos `followers_count` < 1 juta | 7.185 |
| **Lolos growth ≥5,5%** | **0** |

Irisan field-nya sendiri sehat (21 dari 25). Yang memblokir adalah aturan
growth ≥5,5%, yang — seperti di atas — tidak akan pernah terpenuhi selama
nilai maksimum di database 0,917%.

---

### 3.6 Data Freshness & Monitoring (5 filter)

| Filter | Data | Usable | Coverage | Catatan |
|---|---:|---:|---:|---|
| Data Status | 7.496 | **0** | **0%** | Penyebut rumus tidak ada |
| Last Updated | 7.496 | 7.496 | 97,1% | **Satu-satunya yang jalan** |
| Update Frequency | 0 | 0 | 0% | `refresh_tier` 0% terisi |
| Next Update | 7.496 | **0** | **0%** | Butuh interval yang sama |
| Monitoring Priority | 25 | **0** | **0%** | Empat input, semua kosong |

**Grup ini punya satu penghalang bersama: interval update per KOL tidak ada.**

Prototype menghitung `Data Status = umur data ÷ interval update kreator`.
Pembilangnya sehat, penyebutnya tidak ada:

| Komponen | Sumber | Kondisi |
|---|---|---|
| Umur data | `kol_directory.last_refreshed_at` | 7.496 · 97,1% ✅ |
| Interval update | `kol_directory.refresh_tier` | **0 · 0%** ❌ |
| Interval update *(alt)* | `public.scheduler_config` | **0 baris** ❌ |
| Penanda proses | `kol_directory.scrape_status` | 99 · 1,28% (72 `failed`, 27 `success`) |
| Riwayat scheduler | `public.scheduler_logs` | 8 baris |

Tanpa penyebut, **Data Status, Update Frequency, dan Next Update tidak bisa
dihitung sama sekali** — bukan sebagian, melainkan untuk seluruh 7.720 KOL.

**Last Updated — field bagus, tapi 2 dari 5 bucket kosong:**

| Bucket UI | KOL |
|---|---:|
| Last 24 Hours | **0** |
| Last 3 Days | **0** |
| Last 7 Days | 4 |
| Last 30 Days | 1.003 |
| Older than 30 Days | **6.493** |
| *(tanpa tanggal)* | 224 |

**6.493 KOL (84,1% populasi) belum di-refresh lebih dari 30 hari.** Filter ini
berstatus COMPLETE karena field-nya terisi 97,1% dan setiap KOL selalu jatuh di
salah satu bucket — tapi sebarannya menumpuk di satu ujung.

**Monitoring Priority — keempat inputnya kosong atau nyaris kosong:**
`campaign_kols` 0 baris · `campaigns` 0 baris · growth 25 KOL (semuanya
"declining") · viral 5 KOL. Tidak ada satu KOL pun yang bisa diklasifikasikan
sebagai High / Active / Low, sehingga seluruh populasi akan jatuh ke "Standard"
secara default — yang membuat filternya tidak menyaring apa pun.

`directory_status` terisi 100% (7.720) tapi nilainya seragam `active` — satu nilai
unik, jadi tidak bisa dipakai menyaring.

---

### 3.7 Header — Keyword, Smart Criteria, Tabs, Exclude, Collections (5 filter)

| Filter | Data | Usable | Coverage | Catatan |
|---|---:|---:|---:|---|
| Keyword search | 7.497 | 7.497 | 97,1% | 4 field yang dicari tidak ada di DB |
| Smart Criteria | — | — | — | 6 dari 29 aturan berbasis hash |
| Section tabs | 7.698 | 7.698 | 99,7% | 2 dari 7 tab punya sumber |
| Exclude | 0 | 0 | 0% | 5 dari 7 opsi terblokir |
| Collections | — | — | — | Tidak ada tabelnya |

**Keyword search — field yang ada vs field yang dicari prototype:**

| Field yang dicari | Sumber DB | Coverage |
|---|---|---:|
| nama / handle | `kol_directory.username` | 7.497 · 97,1% ✅ |
| nama tampilan | `kol_profile_card.display_name` | 1.958 · 25,4% |
| kategori | `category_ids` → `kol_categories.taxonomy_key` | 4.174 · 54,07% |
| bio | `kol_directory.bio` | 902 · 11,7% |
| bio *(L2)* | `kol_profile_card.bio` | 1.873 · 24,3% |
| **niche** | — | **tidak ada kolom** |
| **topik utama / sub-topik** | — | **tidak ada kolom** |
| **DNA / atribut gaya konten** | — | **tidak ada kolom** |
| **brand yang pernah dikerjakan** | — | **tidak ada kolom** |

Pencarian nama jalan baik. Empat dimensi lain yang dijanjikan placeholder
(*"topics, DNA, brands"*) tidak punya sumber sama sekali.

**Smart Criteria** — 29 aturan. 6 di antaranya bertumpu nilai hash prototype
(Gen Z, Millennial, Indonesia, Jabodetabek, Brand Safe, Active community) —
**SYNTHETIC**. 23 sisanya mewarisi status filter lain, jadi coverage-nya sama
dengan filter yang dirujuk. Karena mayoritas filter rujukannya <1%, aturan-aturan
ini akan mengembalikan hasil yang sangat sedikit.

**Section tabs — 2 dari 7 punya sumber:**

| Tab | Sumber | Coverage |
|---|---|---:|
| 🆕 Newly Added | `kol_directory.created_at` | 7.698 · 99,7% ✅ |
| 🔄 Recently Updated | `kol_directory.last_refreshed_at` | 7.496 · 97,1% ✅ |
| 📈 Trending | growth exploding/rising ATAU viral | **0** *(lihat §3.5)* |
| 🎯 High Match | `feature.brand_fit_analysis` | **0 baris** |
| ⚡ High ROI | `l1_silver.unified_rate_card` | **0 baris** |
| 💎 Hidden Gems | audience quality + follower rendah | 23 |
| 🕘 Recently Viewed | state browser | **SYNTHETIC** |

**Exclude — 5 dari 7 opsi terblokir total:**

| Opsi | Sumber | Kondisi |
|---|---|---|
| already-selected creators | state browser | SYNTHETIC |
| existing brand partners | `campaign_kols` | **0 baris** ❌ |
| competitor-heavy creators | saturasi kompetitor | **tidak ada kolom** ❌ |
| high-risk creators | level risiko | **tidak ada kolom** ❌ |
| low-quality audiences (<75) | `feature.*_audience_analysis` | 20 KOL |
| declining creators | `followers_growth` | 25 KOL *(semua "declining")* |
| sponsored-heavy (>35%) | `post_metric.is_sponsored` | 30 KOL punya data · **0 lolos** |

`is_sponsored` terisi untuk 29 dari 30 KOL yang punya post, dan rasionya bisa
dihitung — tapi **tidak ada satu KOL pun yang rasio sponsored-nya melebihi 35%**.

**Collections** — penyapuan katalog untuk nama tabel yang mengandung
`collection|shortlist|saved_list|favorit|bookmark|wishlist` mengembalikan
**nol tabel**. Shortlist hanya hidup di state browser. **SYNTHETIC / PROTOTYPE ONLY**.

---

## 4. Base-Field Coverage untuk Filter Derived

Delapan filter dihitung dari lebih dari satu field. Bagian ini memisahkan
coverage tiap field dasar dari coverage hasil akhirnya — supaya jelas
**field mana** yang menjadi penghambat.

| Filter | Field dasar | Coverage field | Hasil akhir | Penghambat |
|---|---|---:|---:|---|
| **Gender skew** | `audience_demographics_daily` (`gender`) | 23 · 0,30% | 17 · 0,22% | Coverage, lalu `unknown` 71,3% |
| **Audience Quality** | `authenticity_score` (IG 13 + TT 10) | 23 · 0,30% | 23 · 0,30% | Coverage |
| | `audience_quality_score` (IG 13 + TT 10) | 23 · 0,30% | | Perlu UNION 2 tabel |
| **Engagement Rate** | `er_followers_daily` | 22 · 0,28% | 1 · 0,01% | Coverage + threshold |
| | *(alt)* `kol_directory.engagement_rate` | 1.756 · 22,7% | 219 · 2,84% | 83 nilai tidak valid |
| **Save Rate** | `post_metric.saves` | 11 · 0,14% | 4 · 0,05% | Coverage — TikTok saja |
| | `post_metric.likes` + `comments` *(penyebut)* | 30 · 0,39% | | |
| **Share Rate** | `post_metric.shares` | 11 · 0,14% | 7 · 0,09% | Coverage — TikTok saja |
| **Views** | `post_metric.views` | 29 · 0,38% | 21 · 0,27% | Coverage + outlier |
| **Stability** | `kol_metric_monthly` ≥4 titik | 5 · 0,06% | 5 · 0,06% | Kedalaman deret |
| **Viral Frequency** | `kol_metric_monthly` ≥4 titik | 5 · 0,06% | 5 · 0,06% | Kedalaman deret |
| **Growth Classification** | `kol_profile_card.followers_growth` | 25 · 0,32% | 25 · 0,32% | Threshold — 3 dari 4 bucket kosong |
| **Rising Creator** | `followers_growth` | 25 · 0,32% | **0 · 0%** | **Threshold growth ≥5,5%** |
| | `er_followers_daily` | 22 · 0,28% | | |
| | `kol_directory.followers_count` | 7.498 · 97,1% | | |
| | *irisan ketiganya* | **21 · 0,27%** | | |
| **Data Status** | `last_refreshed_at` | 7.496 · 97,1% | **0 · 0%** | **Interval update tidak ada** |
| | `refresh_tier` *(penyebut)* | **0 · 0%** | | |
| **Next Update** | `last_refreshed_at` | 7.496 · 97,1% | **0 · 0%** | **Interval update tidak ada** |
| | interval | **0 · 0%** | | |
| **Monitoring Priority** | `campaign_kols` | **0 baris** | **0 · 0%** | Seluruh input kosong |
| | `followers_growth` | 25 · 0,32% | | |
| | viral (≥4 bulan) | 5 · 0,06% | | |

### Pola yang terlihat

Filter derived gagal karena **tiga sebab yang berbeda**, dan pembedaan ini
menentukan siapa yang harus mengerjakannya:

| Sebab | Filter | Yang perlu dilakukan |
|---|---|---|
| **Coverage field dasar terlalu kecil** | Gender · Aud. Quality · ER · Save · Share · Views · Stability · Viral | Scraping/pipeline diperluas — **kerja data** |
| **Field ada & cukup, threshold-nya yang tidak terjangkau** | Growth Classification · Rising Creator | **Keputusan produk** — sesuaikan threshold atau definisi periode |
| **Salah satu field dasar sama sekali tidak ada** | Data Status · Next Update · Monitoring Priority · Reliability | **Keputusan arsitektur** — perlu tempat baru di schema |

Yang paling perlu digarisbawahi: **Growth Classification dan Rising Creator tidak
akan membaik walaupun coverage-nya naik menjadi 100%.** Selama nilai maksimum
`followers_growth` di database 0,917% sementara bucket terendah UI menuntut ≥1%,
menambah data hanya menambah KOL di bucket "Declining".

---

## 5. Data Quality Issues yang Memengaruhi Filter

Sembilan temuan yang mengubah hasil filter, walaupun coverage-nya terlihat cukup.

### 5.1 224 KOL tidak terjangkau filter apa pun

| Ukuran | KOL |
|---|---:|
| Tanpa `kol_social_account` / `social_account` | 224 |
| ↳ juga tanpa `platform_id` | **224** (semuanya) |
| ↳ juga tanpa `followers_count` | 222 |
| ↳ juga tanpa `last_refreshed_at` | 224 |
| ↳ juga tanpa `username` | 223 |

Ini bukan 224 KOL yang "kurang data" — ini 224 baris yang **hanya punya id**.
Mereka menaikkan denominator tapi tidak akan pernah muncul di hasil filter mana
pun. **2,90% populasi adalah baris kosong.**

### 5.2 277 grup username duplikat

277 nilai `username_normalized` muncul lebih dari sekali, menyumbang **277 baris
ekstra**. Akibatnya jumlah hasil filter melebihi jumlah kreator sesungguhnya, dan
satu kreator bisa muncul dua kali di daftar.

### 5.3 `engagement_rate` di `kol_directory` punya 83 nilai mustahil

Maksimum **223,41%**, dengan **83 baris di atas 10%**. ER di atas 100% berarti
interaksi melebihi jumlah follower — tidak mungkin untuk metrik ini. Kalau kolom
ini dipakai sebagai sumber ER (yang cakupannya 80× lebih luas dari L2), 83 baris
itu akan selalu lolos filter "High ER" dan menduduki peringkat teratas.

### 5.4 `views` punya 3 outlier ekstrem

| Ukuran | Nilai |
|---|---:|
| Rata-rata views terendah | 295 |
| **Median** | 474.870 |
| **Maksimum** | **78.091.457** |
| KOL dengan rata-rata >10 juta | **3** |

Dari 21 KOL yang lolos "150K+ avg views", 3 di antaranya dengan angka yang perlu
diverifikasi lebih dulu.

### 5.5 Batas tier UI berbeda dari tabel `kol_tiers`

> **✅ RESOLVED 2026-09-07** — migration 033 membetulkan ambang di `kol_tiers`,
> sehingga UI dan tabel sekarang memakai angka yang sama. Tabel di bawah dibiarkan
> sebagai catatan temuan. Detail dan angka sesudahnya di **§Revisi 2026-09-07 · I1**.

| Tier | Batas UI *(tooltip prototype)* | Batas `public.kol_tiers` |
|---|---|---|
| Nano | 1K–10K | 1.000–9.999 ✅ |
| Micro | 10K–50K | 10.000–49.999 ✅ |
| **Mid-tier** | **50K–500K** | **50.000–99.999** ❌ |
| **Macro** | **500K–1M** | **100.000–999.999** ❌ |
| Mega | >1M | ≥1.000.000 ✅ |

Dua tier tengah **tidak cocok**, dan selisihnya besar. Akibatnya nyata:

| | KOL |
|---|---:|
| "Macro" menurut `kol_profile_card.tier` *(batas DB)* | **1.123** |
| "Macro" menurut batas UI 500K–1M | **187** |

**Selisih 6,0×.** Selama batas ini belum diselaraskan, angka yang ditampilkan chip
Tier akan berbeda tergantung sumber mana yang dipakai. Ini menjadi syarat sebelum
rekomendasi §3.1 (hitung tier dari `followers_count`) bisa dijalankan.

> **⚠️ Perbandingan di atas mencampur dua denominator (koreksi 2026-09-06).**
> **1.123** dihitung dari kolom `kol_profile_card.tier` — populasinya hanya **1.972 kartu L2**.
> **187** dihitung dari `followers_count` batas UI — populasinya **seluruh 7.720**.
> Keduanya bukan ukuran yang sama, jadi "selisih 6,0×" tidak sah.
>
> `KOL_DISCOVERY_AUDIT.md` §3.3 menghitung ulang dengan denominator yang seragam (seluruh
> direktori, batas `kol_tiers`) dan mendapat **1.290**, selisih **6,9×**.
> **TERVERIFIKASI (V-03, 2026-09-07):** ketiga angka benar dan mengukur hal berbeda —
> **1.290** (direktori, batas lama) · **1.123** (1.976 kartu L2, batas lama) · **187**
> (direktori, batas produk). Batas produk yang berlaku; **1.103 KOL** pindah Macro → Mid-Tier.
> Kesimpulan §5.5 sendiri — bahwa batas UI dan `kol_tiers` tidak cocok — **tetap berlaku**.

### 5.6 `unknown` mendominasi data audiens

| Dimensi | Porsi `unknown` |
|---|---:|
| Gender | rata-rata **71,3%** per KOL |
| Interest | **85,2%** dari total bobot (2.021 dari 2.371) |

Keduanya harus dikeluarkan dari penyebut sebelum dipakai menyaring — kalau tidak,
Gender skew mengembalikan 0 hasil (§3.1) dan peringkat minat menjadi bias.

### 5.7 Sebagian rasio dihitung dari sampel post yang sangat tipis

| Ukuran | Nilai |
|---|---:|
| KOL punya `post_metric` | 30 |
| Post paling sedikit yang dimiliki satu KOL | **1** |
| Rata-rata post per KOL | 15,9 |
| Post terbanyak | 200 |
| KOL dengan <5 post | 1 |

Save Rate, Share Rate, Views, dan rasio sponsored dihitung dari sampel ini.
Satu KOL rasionya berasal dari **satu post**.

### 5.8 Save/Share hanya ada di TikTok

Ke-11 KOL yang punya `saves`/`shares` **seluruhnya TikTok** — 0 Instagram.
Filter Save Rate dan Share Rate secara efektif menjadi filter khusus TikTok,
dan akan menyembunyikan seluruh 3.409 KOL Instagram tanpa memberi tahu penggunanya.

### 5.9 Granularitas `geo_key` bercampur

9 dari 33 key ber-`geo_level='city'` sebenarnya provinsi atau pulau, menyentuh
10 dari 15 KOL. Tidak ada level `province` di database, padahal UI Audience
Insights memerlukannya.

---

## 6. Final Findings

### 6.1 Struktur bukan masalahnya — isi yang masalah

Jalur JOIN `kol_directory → kol_social_account → social_account → l2_gold.*`
ber-FK resmi dan menjangkau **97,1% populasi**. Hampir setiap filter punya tabel
dan kolomnya. Yang tidak ada adalah **barisnya**.

| Lapisan | KOL terjangkau | % |
|---|---:|---:|
| `kol_directory` *(populasi)* | 7.720 | 100% |
| Punya jalur ke `social_account` | 7.496 | 97,1% |
| Punya `l2_gold.kol_profile_card` | 1.976 | 25,6% |
| Punya data konten (`post_metric` / `content_format_daily`) | 30 | **0,39%** |
| Punya data audiens (`audience_*` / `feature.*`) | 23 | **0,30%** |

**Dua baris terakhir menopang 12 filter.** Selama keduanya di bawah 0,4%,
filter-filter itu menyembunyikan lebih dari 99% populasi — bukan karena
kreatornya tidak memenuhi kriteria, tapi karena nilainya tidak diketahui.

### 6.2 Empat filter bisa naik tanpa menunggu scraping

Ini temuan yang paling bisa langsung ditindaklanjuti:

| Filter | Sumber di Task 2 | Coverage | Sumber yang lebih baik | Coverage | Syarat |
|---|---|---:|---|---:|---|
| **KOL Tier** | `kol_profile_card.tier` | 25,5% | `kol_directory.followers_count` | **93,2%** | Selaraskan batas tier (§5.5) |
| **Gender skew** | penyebut mentah | **0 KOL lolos** | penyebut tanpa `unknown` | **17 KOL lolos** | Ubah rumus, bukan data |
| **Engagement Rate** | `er_followers_daily` | 0,28% | `kol_directory.engagement_rate` | 21,7% | Buang 83 nilai >10% (§5.3) |
| **Keyword search** | `kol_directory.bio` | 11,7% | + `kol_profile_card.bio` | 24,3% | Union dua sumber bio |

Keempatnya perbaikan **rumus atau pilihan sumber** — tidak perlu satu baris data baru.

### 6.3 Tiga filter terblokir keputusan produk, bukan data

| Filter | Kondisi | Kenapa data tidak menolong |
|---|---|---|
| **Growth Classification** | Nilai maks 0,917%, lantai bucket terendah 1% | Menambah data hanya menambah KOL di "Declining" |
| **Rising Creator** | Butuh growth ≥5,5% | Threshold 6× di atas nilai tertinggi yang ada |
| **Gender skew** | Threshold 60%/55% dengan `unknown` 71,3% | Matematis tidak terjangkau tanpa renormalisasi |

Ditambah lima keputusan produk yang lebih kecil: chip **YouTube** tanpa baris
`platforms`, chip **Story** tanpa `unified_story`, chip **Tech** dengan 2 KOL,
bucket **Audience Quality "High (85+)"** dengan 1 KOL, dan batas tier yang
berbeda dari `kol_tiers`.

### 6.4 Satu gap struktural yang nyata

Dari 9 filter MISSING, delapan kekurangan **data**. Satu kekurangan **tempat
untuk menyimpan data**:

> **Interval update per KOL tidak punya rumah di database.**
> `refresh_tier` ada sebagai kolom tapi 0% terisi; `scheduler_config` 0 baris.

Tiga filter mati karenanya — Data Status, Update Frequency, Next Update —
dan keduanya adalah penyebut dari rumus yang sama. Ini satu-satunya temuan
di dokumen ini yang membutuhkan keputusan arsitektur, bukan sekadar pengisian data.

### 6.5 Yang sebenarnya bisa dipakai hari ini

Kalau KOL Discovery diluncurkan dengan data sekarang, filter yang benar-benar
menyaring populasi secara berarti ada **lima**:

| Filter | Coverage |
|---|---:|
| Platform | 97,1% |
| Last Updated | 97,1% |
| Keyword search *(nama/handle)* | 97,1% |
| Section tabs *(Newly Added / Recently Updated)* | 99,7% |
| KOL Tier *(kalau dipindah ke `followers_count`)* | 93,2% |

Ditambah **Kategori** di 53,82% sebagai filter kelas dua.

**26 filter sisanya** akan menampilkan hasil kosong, hasil yang menyesatkan
(karena menyembunyikan mayoritas populasi tanpa penjelasan), atau nilai yang
diciptakan prototype. Rekomendasinya: sembunyikan atau beri penanda eksplisit
"data belum tersedia" pada filter <1% coverage, supaya pengguna tidak
menyimpulkan bahwa nol hasil berarti tidak ada kreator yang cocok.

---

## Ringkasan Status

| Status | Jumlah | Filter |
|---|---:|---|
| **COMPLETE** | 1 | Last Updated |
| **PARTIAL** | 14 | Platform · Kategori · KOL Tier · Aud. location · Aud. interest · Aud. Quality · Content Format · Engagement Rate · Save Rate · Share Rate · Views · Keyword · Smart Criteria · Section tabs |
| **DERIVED — INCOMPLETE** | 5 | Gender skew · Performance Stability · Viral Frequency · Growth Classification · Rising Creator |
| **MISSING** | 9 | Verified only · Age · Location kreator · Reliability · Data Status · Update Frequency · Next Update · Monitoring Priority · Exclude |
| **SYNTHETIC / PROTOTYPE ONLY** | 3 | Content Category/Topic · Content Style & Personality · Collections |
| | **32** | |

> **3b** (Tier via `kol_profile_card`) dan **14b** (ER via `kol_directory`) adalah
> sumber alternatif untuk filter yang sama — tidak dihitung sebagai filter terpisah.

---

**Audit trail:** sesi Postgres `set_session(readonly=True, autocommit=True)`,
seluruh statement `SELECT` / katalog. JOIN hanya dipakai di dalam `SELECT` untuk
menghitung coverage — tidak ada implementasi JOIN yang ditulis ke kode. Nilai
`oauth_token` tidak pernah di-SELECT; hanya `IS NULL` / `IS NOT NULL` dan `count()`.
Tidak ada perubahan pada database, schema, source code, migration, atau config;
tidak ada commit/push.

---

# Revisi — 2026-09-06

Sumber: `KOL_DISCOVERY_MONITORING_PRIORITY_AUDIT.md` (Lampiran C) ·
`KOL_DISCOVERY_FILTER_BACKEND_PLAN.md` (§2, §5) · `KOL_DISCOVERY_AUDIT.md` (§3.3) ·
migration `029`.

> §1–§6 **sengaja dibiarkan apa adanya** sebagai audit trail. Kalau ada pertentangan,
> **section ini yang berlaku**. Tidak ada query baru — database tidak bisa dijangkau saat
> revisi ini ditulis (TCP timeout).

## R1 — Last Updated: COMPLETE → PARTIAL

Ini satu-satunya perubahan status di dokumen ini, dan alasannya bukan coverage.

Kerangka tiga lapis di §1 mengukur **relationship**, **data**, dan **usable**. Last Updated lolos
ketiganya. Yang tidak diperiksa adalah lapis keempat yang tidak ada di kerangka itu:
**apakah nilainya berarti seperti yang diasumsikan.**

| Pengujian | Hasil |
|---|---:|
| Punya `last_refreshed_at` | 7.496 · 97,1% |
| ↳ **dan** punya baris profil di `l0_raw` | **1.976** |
| ↳ **tapi tidak punya** data apa pun di `l0_raw` | **5.520 · 73,6%** |
| Sekadar salinan `created_at` | 4 |
| Umur median / maksimum | **847 hari** / 1.306 hari |
| `kol_directory.source` | `excel_import` 7.718 · `manual_add` 2 |

Untuk 73,6% baris, tanggal itu **tidak pernah dihasilkan oleh scrape apa pun** — ia ikut masuk
bersama excel import. Satu-satunya penulis kolom ini adalah `db.update_profiles()` (`db.py:399`),
dipanggil dari `ingest.py:231` dan `pipeline.py:304` — jalur Instagram lama.
`scheduler_engine.py` dan jalur Dagster hanya **membaca** `kol_directory`.

Efek berantai ke §3.6: kesimpulan *"Data Freshness terblokir karena penyebutnya tidak ada"*
**kurang lengkap**. Yang benar: **pembilang dan penyebutnya sama-sama bermasalah** — penyebut
(`refresh_tier`) kosong, pembilang (`last_refreshed_at`) ada tapi salah arti. Memperbaiki penyebut
saja tidak akan membuat Data Status benar.

## R2 — §3.5: sebab kegagalan Growth lebih berat dari yang ditulis

Dokumen ini menyimpulkan Growth Classification gagal karena **threshold** — rentang nyata
−0,051% s.d. +0,917% vs lantai bucket ≥1%. Itu benar, tapi ada sebab yang lebih mendasar:
**metrik yang dibandingkan bukan metrik yang didefinisikan UI.**

`kol_profile_card.followers_growth` dihitung dengan `LAG()` antar-snapshot **berapa pun jaraknya**.
Jarak nyata sekarang: **10 hari** (22 akun) dan **13 hari** (3 akun). UI mendefinisikan
"pertumbuhan 30 hari". Membandingkan pertumbuhan 10 hari dengan ambang 30 hari salah secara
konseptual, terlepas dari berapa pun angkanya.

Konsekuensinya untuk §4: baris "Growth Classification — penghambat: **Threshold**" seharusnya
"**Periode, lalu threshold**". Menyesuaikan threshold di atas metrik yang salah periode hanya
memindahkan kesalahannya.

## R3 — Kedalaman snapshot profil tidak terukur di dokumen ini

§3.4 mengukur kedalaman deret **bulanan** (`kol_metric_monthly`: 5 KOL punya ≥4 titik, 0 punya 6).
Yang tidak diukur adalah kedalaman deret **snapshot profil** (`l1_silver.unified_profile`), padahal
itulah yang menentukan Growth dan Rising Creator:

| Kedalaman | Akun |
|---|---:|
| Punya ≥1 snapshot | 1.976 |
| Punya 2 snapshot | **25** *(jarak 10–13 hari)* |
| Punya 2 snapshot berjarak **≥30 hari** | **0** |
| Punya **≥3** snapshot *(minimum untuk momentum)* | **0** |

Jadi §3.5 "Rising Creator — 21 KOL punya ketiga field, 0 lolos threshold" masih menyembunyikan satu
lapis: syarat "tren tidak menurun" **tidak bisa dievaluasi sama sekali** untuk akun mana pun.

Kabar baiknya, jaraknya dekat: backfill 14–18 Agustus 2026 sudah berfungsi sebagai kaki "T−30".
Satu re-scrape sekitar **17 September 2026** membuka growth 30D untuk **1.971 akun**.

## R4 — §5.5: dua denominator yang tercampur

Sudah ditandai inline di §5.5. Ringkasnya: **1.123** dihitung atas 1.972 kartu L2, **187** atas
seluruh 7.720 — bukan perbandingan yang sah. Angka berdenominator seragam ada di
`KOL_DISCOVERY_AUDIT.md` §3.3: **1.290 vs 187**, selisih 6,9×. **TERVERIFIKASI (V-03, 2026-09-07).**

## R5 — §3.1 Kategori: irisan 5 chip sudah tidak relevan

Tabel "Chip UI × Kategori DB" di §3.1 (total usable 3.487) dihitung terhadap **5 chip
hardcode prototype**. Migration `029` (2026-09-03, **sesudah** dokumen ini) menetapkan **9 Discovery
Category** lewat `kol_categories.taxonomy_key`, memetakan 22 dari 28 kategori mentah.

Dua keluhan di §3.1 karenanya **terselesaikan**: `Entertainment` (501) dan `Moms` (589) sekarang
punya kategori sendiri, dan 668 KOL yang tadinya "tidak terjangkau chip mana pun" ikut tercakup.
Coverage naik ke **4.155 · 53,82%** *(TERVERIFIKASI V-01/V-02, 2026-09-07 — dihitung ulang lewat
query; kolom join yang benar `category_ids`, bukan `category_id`)*.

## Ringkasan dampak

| Bagian | Isi lama | Setelah revisi |
|---|---|---|
| §2 No. 24 Last Updated | **COMPLETE** · 97,1% | **PARTIAL** — 73,6% nilainya bukan jejak scrape |
| Rekapitulasi | COMPLETE 1 · PARTIAL 14 | **COMPLETE 0 · PARTIAL 15** |
| §2 No. 2 Kategori | 3.070 · 39,8% | **4.155 · 53,82%** lewat `taxonomy_key` |
| §3.1 keluhan 5 chip | Berlaku | **Terselesaikan** oleh taxonomy 9 kategori |
| §3.5 / §4 Growth | Penghambat: threshold | **Penghambat: periode, lalu threshold** |
| §3.5 Rising Creator | 21 punya field, 0 lolos | + syarat momentum **tidak bisa dievaluasi** (0 akun ≥3 snapshot) |
| §3.6 Data Freshness | Penyebut tidak ada | **Pembilang dan penyebut sama-sama bermasalah** |
| §5.5 Tier | 1.123 vs 191 · 5,9× | Denominator tercampur — pakai **1.290 vs 187 · 6,9×** *(V-03 terverifikasi)* |
| Denominator filter | 32 | **40** *(baseline app)* |
| §6.5 "yang bisa dipakai hari ini" | 5 filter | **6** — tambah Kategori lewat taxonomy; Last Updated tetap masuk tapi **dengan catatan semantik** |

Coverage final per field: `docs/KOL_DISCOVERY_TASK5_DESIGN.md` §3.

---

# Revisi — 2026-09-07 (implementasi)

Sumber: migration `033`, `034` · `tests/test_discovery_tier_growth.py` ·
verifikasi end-to-end 2026-09-07 (SQL dijalankan langsung ke database `kol`,
query diekstrak dari `kolDirectory.ts` yang di-ship).

> Berbeda dari revisi 2026-09-06 yang ditulis tanpa akses database, section ini
> **dihitung ulang lewat query nyata**. §1–§6 dan revisi 2026-09-06 tetap dibiarkan
> apa adanya sebagai audit trail; kalau bertentangan, **section ini yang berlaku**.

## I1 — Batas tier: dua ambang yang bertentangan sudah tidak ada

§5.5 dan revisi R2 menyoroti bahwa batas tier di UI berbeda dari tabel `kol_tiers`.
Penyebabnya sekarang dihapus di sumbernya.

| Tier | Batas lama di `kol_tiers` | Batas sekarang |
|---|---|---|
| **Mid-tier** | 50.000 – **99.999** | 50.000 – **499.999** |
| **Macro** | **100.000** – 999.999 | **500.000** – 999.999 |

Nano, Micro, Mega tidak berubah. Diperbaiki lewat `UPDATE` — bukan hapus-lalu-isi —
karena `agency_kol_accounts.tier_id` punya foreign key ke `kol_tiers.id`.

Dampak terukur, dihitung dari `kol_directory` (denominator 7.720, populasi aktif):

| Tier | Sebelum | Sesudah | Selisih |
|---|---:|---:|---:|
| Nano | 1.943 | 1.943 | 0 |
| Micro | 2.942 | 2.942 | 0 |
| **Mid-tier** | 706 | **1.809** | **+1.103** |
| **Macro** | 1.290 | **187** | **−1.103** |
| Mega | 313 | 313 | 0 |
| Tanpa tier | 526 | 526 | 0 |

Angka **1.809 / 187** yang sudah tertulis di §5.5 dan di tabel bucket UI ternyata benar —
itu memang hasil dengan ambang yang disepakati. Yang dulu salah adalah isi tabel
`kol_tiers`, dan sekarang keduanya sudah sama.

## I2 — P-01 ditutup: di bawah 1rb tidak lagi masuk Nano

Yang tidak terlihat di dokumen ini: `l1_silver` dan `l2_gold` diam-diam memberi tier
`Nano` kepada KOL yang followernya di bawah 1.000, lewat `COALESCE` fallback di
`sp_build_unified_profile()`. UI tidak pernah begitu — ia memakai `LEFT JOIN kol_tiers`
tanpa fallback, sehingga menghasilkan tier kosong. Jadi selama ini UI benar dan L1/L2 salah.

| | Sebelum | Sesudah |
|---|---:|---:|
| L1 follower di bawah 1rb bertier `Nano` | 54 | **0** |
| L2 follower di bawah 1rb bertier `Nano` | 54 | **0** |
| L1 follower di bawah 1rb tier NULL | 0 | **54** |
| L1 follower NULL bertier | 0 | 0 |

Keputusan produk: **tidak** dibuatkan kelompok `Unclassified` maupun `Unknown`.
Populasi 526 (304 di bawah 1rb + 222 tanpa data) tetap 526 dan tetap harus dihitung
sebagai kelompok tanpa tier — jangan dibuang diam-diam dari hasil filter.

## I3 — Verified keluar dari daftar filter

Rekapitulasi §Ringkasan Status mencatat **Verified only** sebagai MISSING (relationship
7.496, data 0). Status itu sekarang tidak relevan: **Verified dihapus dari Discovery**
atas keputusan produk. Badge platform (`verified_status`: 454 verified) tidak
dipertahankan sebagai field terpisah.

Penggantinya **Connected**, dengan definisi bisnis:

```
social_account.platform_user_id IS NOT NULL AND social_account.oauth_token IS NOT NULL
```

Hasil hari ini **0 dari 7.720**, dan itu benar — belum ada kreator yang menghubungkan
akun. Chip-nya akan selalu kosong sampai connect flow berjalan; ini bukan kegagalan
coverage, dan tidak perlu dihitung sebagai filter MISSING yang menunggu data.

## I4 — Growth: statusnya berubah, angkanya tidak

§3.5 menulis Growth Classification **DERIVED — INCOMPLETE**, 25 KOL · 0,32%.
**Angka itu masih persis sama.** Yang berubah cuma keputusan produk: growth
**boleh dipakai sementara** meski periodenya bukan 30 hari.

| | Nilai |
|---|---:|
| KOL punya `followers_growth` | **25** · 0,32% |
| Naik (di atas 0%) | 10 |
| Datar (tepat 0%) | 8 |
| Turun (di bawah 0%) | 7 |
| Jarak antar snapshot | 10 hari (22 akun) · 13 hari (3 akun) |

Dua syarat yang mengikat implementasi:

1. **Dilarang dilabeli "Monthly" atau "30 hari".** Label resmi: **"Sejak Snapshot Terakhir"**.
2. **Dilarang membuat rumus baru.** Angkanya dibawa apa adanya dari
   `l1_silver.sp_build_unified_profile()` dan diverifikasi identik di L1, L2, dan API.

Temuan R2/R3 (periode 10–13 hari, 0 akun punya 3 snapshot) **tetap berlaku dan tetap
jadi penghambat sebenarnya**. Growth akan naik sendiri begitu scraping jalan lagi —
1.951 dari 1.976 akun ber-kartu masih punya satu snapshot. Catatan: scraping berhenti
sejak 2026-08-28, jadi selama itu angka 25 tidak akan bergerak.

**Rising Creator tetap DERIVED — INCOMPLETE.** Ambang 5,5% masih tidak dipenuhi siapa pun
(0 KOL), jadi filternya belum dibuat.

## Ringkasan dampak revisi 2026-09-07

| Bagian | Isi sebelumnya | Setelah implementasi |
|---|---|---|
| §5.5 · batas tier | dua ambang bertentangan | **satu ambang** — `kol_tiers` dibetulkan (033) |
| §2 bucket tier | Mid-tier 1.809 · Macro 187 *(hitung manual)* | **sama, dan sekarang itu yang benar-benar dipakai** |
| P-01 · 526 KOL di luar tier | menunggu keputusan produk | **CLOSED** — tanpa tier, tanpa `Unclassified` (034) |
| §Ringkasan · Verified only | MISSING | **dihapus dari scope** — diganti Connected |
| §3.5 Growth Classification | DERIVED — INCOMPLETE | **tetap 25 · 0,32%**, tapi **sudah dipakai** dengan label "Sejak Snapshot Terakhir" |
| §3.5 Rising Creator | DERIVED — INCOMPLETE | **tidak berubah** — 0 KOL lolos ambang 5,5% |

Semua angka di section ini dihitung ulang lewat query read-only ke database `kol`
pada 2026-09-07, setelah migration 033 dan 034 diterapkan dan pipeline dijalankan ulang.

---

# Revisi — 2026-09-09 (implementasi lanjutan)

Sumber: `scrapper-project` @ `fa3af27` (migration 035, `gold_profile.py`, 354 test lulus) ·
`autometric` @ `232da34` (`npx tsc --noEmit` exit 0) · pengukuran read-only database `kol`
8 September 2026 yang terekam di `AUTOME_2_FULL_TRACE_AUDIT.md`,
`AUTOME_2_DEVELOPMENT_AUDIT.md`, `AUTOME_2_FULL_ENDPOINT_COVERAGE_AUDIT.md`.

> Kalau bertentangan dengan §1–§6, revisi 2026-09-06, maupun revisi 2026-09-07,
> **section ini yang berlaku**. Section-section lama sengaja tidak dihapus — dipakai
> sebagai audit trail.

## J1 — Verified: dari MISSING, ke "dihapus", ke **jalan dengan 572 KOL**

Revisi I3 menulis Verified **dihapus dari scope**. Itu sudah tidak berlaku.

Yang berubah bukan cuma keputusan, tapi **sumbernya** — dan itu yang membuat angkanya
berbeda dari semua versi sebelumnya:

| Versi | Sumber | Terisi | Status |
|---|---|---:|---|
| §2 No. 5 (Task 3 asli) | `social_account.oauth_token` | **0** | MISSING — ini sebenarnya **Connected**, bukan Verified |
| Task 2 / Task 4 | `kol_directory.verified_status` | 454 | ditolak, lalu dihapus |
| **Sekarang** | **`l2_gold.kol_profile_card.is_verified`** | **572** | **PARTIAL — dipakai** |

Sumber 572 itu badge platform asli yang selama ini ada di L0 tapi tidak pernah diekstrak:

| Platform | Kolom L0 | Baris | Bertanda true |
|---|---|---:|---:|
| Instagram | `l0_raw.ig_profile_apify.raw_payload->>'verified'` | 953 | **470** |
| TikTok | `l0_harmonization.tiktok_profile.is_verified` | 1.058 | **124** |

Sebelum `fa3af27`, `l1_silver.unified_profile.is_verified` justru diisi **ekspresi
Connected** (sejak migration 031), sehingga 2.010 baris L1 dan 1.979 kartu L2 semuanya
`false` — badge platform hilang di tengah jalan. `gold_profile.py` keputusan #7 sekarang
mengambilnya dari sumbernya. Definisi Connected **tidak diubah**.

Connected tetap **0 dari 7.720**, dan itu tetap benar. Karena 572 ≠ 0, keduanya
dipertahankan sebagai **dua sumbu terpisah** di endpoint (`?verified=1` dan
`?connected=1`) dengan ikon berbeda.

## J2 — Engagement Rate: dua baris di §2 (No. 14 dan 14b) sekarang satu ekspresi

§2 mencatat dua kandidat ER yang bersaing: `kol_metric_daily.er_followers_daily`
(22 akun, usable 1) dan `kol_directory.engagement_rate` (1.756, usable 219).

Endpoint yang di-ship **tidak memilih salah satu** — ia memakai kandidat ketiga lebih
dulu, yaitu metrik yang benar-benar dihitung project ini:

```sql
COALESCE(
  feature.{ig,tt}_engagement_analysis.engagement_rate,   -- 38 nilai, rentang 0-16,15%
  kol_directory.engagement_rate                          -- 1.757 nilai, maks 223,41%
)
```

| | Nilai |
|---|---:|
| Cakupan sebelum | 1.757 |
| **Cakupan sesudah** | **1.767** |
| KOL yang hilang | **0** |
| Di antaranya yang **hanya** punya nilai feature | 10 |

Feature dipilih lebih dulu karena penyebutnya follower **pada tanggal post**, dan post
kolaborasi serta likes-hidden dikecualikan (`feature_engagement.py`) — aturan sampel yang
sudah terbukti menyelamatkan 43 baris salah-atribusi dari mencemari ER.

**Yang belum diputuskan tetap belum diputuskan:** memindahkan ER sepenuhnya ke L2
(`er_followers_daily`) akan memangkas cakupan filter dari 1.756 menjadi 22 KOL. Keputusan
itu sengaja ditunda sampai cakupan post naik.

## J3 — Kategori: filter akhirnya memakai `taxonomy_key`, dan chip-nya 15

§2 No. 2 sudah menulis sumbernya `taxonomy_key`. Yang tidak terlihat di dokumen ini:
**endpoint aplikasi selama ini menyaring pakai `kol_categories.name`**, bukan
`taxonomy_key` — jadi dua implementasi (`db.py` di repo ini dan `kolDirectory.ts`)
menjawab pertanyaan yang sama dengan hasil berbeda.

| Chip | Jawaban lama (`name`) | Jawaban benar (`taxonomy_key`) |
|---|---:|---:|
| Food | 57 | **123** |
| Dance → Entertainment | 3 | **501** |

Sejak `232da34` keduanya memakai `COALESCE(taxonomy_key, name)`, di filter **dan** di
facet, sehingga hitungan chip sama persis dengan panjang hasil filter.

Konsekuensi yang perlu dicatat: **chip-nya 15, bukan 9.** 6 dari 28 nama kategori mentah
belum punya `taxonomy_key`, dan `COALESCE` membuat mereka muncul apa adanya. Tanpa itu,
6 kategori tersebut beserta 20 KOL yang memakainya tidak akan terjangkau chip mana pun.
Nama sub-kategori tetap diterima sebagai nilai filter supaya link lama tidak mati.

## J4 — Followers: satu kolom, dua nilai, dan sanity guard yang menutup risikonya

Dokumen ini mengukur `followers_count` sebagai satu angka (7.498 · 97,1%). Pengukuran
8 September menemukan bahwa ada **dua** nilai yang hidup bersamaan:

| | Akun |
|---|---:|
| Punya followers di roster **dan** L2 | 1.972 |
| Sama persis | 948 |
| **Berbeda** | **1.024 (52%)** |
| Rata-rata selisih | 252.320 |

Dua penyebab yang berlawanan, jadi tidak ada satu pun sumber yang benar untuk semuanya:

| # | Penyebab | Akun | Yang benar |
|---|---|---:|---|
| 1 | Roster basi — tidak pernah di-refresh sejak 2023–2024 | ~970 | **L2** |
| 2 | Nilai scrape TikTok rusak (0/9/17 untuk akun berjuta follower) | **54** | **roster** |

Bukti arahnya konsisten: `last_refreshed_at` **selalu** lebih tua dari
`profile_snapshot_date` — 1.024 dari 1.024, nol pengecualian. Dan saat keduanya sama-sama
segar (912 akun di-refresh 2026-08-14), selisihnya **nol**.

Bahaya sebenarnya bukan angka di layar, melainkan angka itu menjadi **penyebut growth
berikutnya**: `zeejkt48` 4.500.000 → 17 → 4.500.000 akan menghasilkan −99,9996% lalu
**+26.470.588%**.

**Migration 035 (sudah diterapkan) memasang sanity guard tiga lapis** di
`sp_build_unified_profile()`, dengan `AMBANG_DASAR = 1.000` dan `RASIO_RUNTUH = 0,10`:

1. `followers < 0` → NULL
2. acuan = snapshot valid sebelumnya, atau roster; acuan ≥ 1.000 **dan** nilai < acuan × 0,10 → NULL
3. tanpa acuan sama sekali, TikTok, < 1.000, `likes = 0` **dan** `video = 0` → NULL

Ambang diterapkan pada **acuan**, bukan pada nilai baru, sehingga **304 KOL yang memang
berfollower di bawah 1.000 tidak pernah tersentuh**. Terukur: **51 baris menjadi NULL**,
nol di antaranya ber-acuan di bawah 1.000. Rumus Growth **tidak berubah satu karakter pun**;
yang ditambah cuma pembanding dua tahap supaya snapshot yang di-NULL-kan dilewati, bukan
memutus riwayat. `l0_raw` dan `l0_harmonization` tidak disentuh.

**Sumber resmi Followers tetap `kol_directory.followers_count` (P-02).** Konsekuensinya
diakui apa adanya: UI menampilkan follower roster sementara `growthPct` dihitung dari
follower L2, jadi kedua angka itu **belum bisa direkonsiliasi**. Itu keputusan terbuka,
bukan bug yang sudah ditutup.

## J5 — Rate card: bukan "tidak ada source", tapi "procedure tidak dipanggil"

§Ringkasan dan Task 2 mencatat rate card sebagai tabel kosong tanpa sumber. Pengukuran
8 September membalik pembacaan itu:

| Bukti | Hasil |
|---|---|
| `l0_raw.kol_roster_import` | **7.718 baris · 7.496 KOL distinct** |
| 7 kolom harga (`story_price`, `feed_photo_price`, `reel_price`, dst.) | **terisi untuk 7.496 KOL** |
| `l0_harmonization.sp_sync_roster_rate_card()` | **ada**, lengkap |
| `l1_silver.sp_build_unified_rate_card()` | **ada** |
| `l1_silver.unified_rate_card` | **0 baris** |

Penyebabnya: `orchestration/.../harmonization.py` sengaja tidak membuatkan asset untuk
rate card, dengan alasan *"tabel `l0_raw` sumbernya 0 baris"*. Alasan itu benar untuk
`l0_extra.ig/tt_rate_card`, tapi **tidak berlaku** untuk `kol_roster_import`.

**Dampak yang sudah terukur ke pengguna:** filter `?maxRate=` aktif di endpoint dan
memakai `EXISTS (… fee IS NOT NULL AND fee <= $)`. Karena tabelnya kosong, **0 dari 7.720
KOL lolos** — begitu slider digeser dari maksimum, direktori jadi kosong total. Ini
filter yang bekerja dengan benar di atas tabel kosong, bukan filter yang belum dibuat.

> **Catatan dokumentasi:** angka "9.210 baris / 7.230 akun" yang muncul di
> `docs/L0_L1_L2_FLOW.md` (tabel L1) dan di docstring `kolMeasured.ts` / `gold_profile.py`
> **tidak akurat** — itu hasil yang *akan* dihasilkan procedure, bukan isi tabel sekarang.
> Sudah dikoreksi di `AUTOME_2_DEVELOPMENT_AUDIT.md` §K-1.

## J6 — Filter yang naik status tanpa penambahan data

Tiga hal berikut tidak butuh scraping baru; datanya sudah ada dan cuma belum dipakai.

| Filter / field | Status di §2 | Status 2026-09-09 | Sumber |
|---|---|---|---|
| **Last Updated** | tidak ada di daftar 32 | **jalan** — `?updatedWithin=<hari>` + sort `recent` | `kol_directory.last_refreshed_at` (7.496) |
| **Agency** | tidak pernah dicek | **jalan** — `?agency=<nama>` + facet ber-count | `agency_kol_accounts` + `agencies` (**7.684 / 7.718**) |
| **Identitas (avatar, bio, display name)** | diukur dari roster | **dibaca dari L2 lebih dulu** | avatar 931 → **1.979** · bio 902 → **1.878** · display name 0 → **1.961** |

L2 terbukti **superset ketat** roster untuk avatar dan bio: nol kasus di mana roster punya
nilai tapi L2 tidak. Endpoint memakai `COALESCE(L2, roster)` — bukan penggantian — supaya
baris roster yang lebih dulu terisi tidak pernah mundur.

## J7 — Sorting: 27 KOL yang selalu di puncak sudah tidak ada

Tidak tercatat di dokumen ini, tapi memengaruhi **semua** hasil filter: kunci urutan
`SCRAPED_FIRST` mendahului pilihan user, sehingga 28 creator ber-`status` Live/Calculated
selalu di baris atas apa pun sort-nya — `bobbykertanegara` (948.683) mengalahkan
`cristiano` (679.264.838) saat diurut followers menurun, dan tetap di atas `sekata_ai`
(200) saat menaik.

Kunci itu dibuang di `232da34`. Kolom `status` tetap dikembalikan dan tetap digambar
sebagai chip. Tie-break sekarang berakhir di `id` (unik) karena **username tidak unik**:
7.721 baris aktif hanya punya 7.224 username berbeda — tanpa kunci unik, sampai 497 baris
berada dalam urutan yang bebas diubah planner, dan dua halaman bisa mengulang satu
creator sambil menjatuhkan yang lain.

Ini menjawab §5.2 (277 grup username duplikat) dari sisi paging: **duplikatnya belum
dibersihkan**, tapi paging-nya tidak lagi goyah karenanya.

## J8 — Content Format & Heatmap: naik ke endpoint, tanpa tabel baru

| Fitur | Sumber | Cakupan | Di mana |
|---|---|---:|---|
| **Dominant format** | diturunkan dari `l2_gold.content_format_daily` yang sudah ada | **56 akun** | `gold.dominantFormat` di halaman detail |
| **Heatmap jam posting** | `feature.{ig,tt}_engagement_analysis.best_posting_time_heatmap` | **50 akun** | `gold.heatmap` di halaman detail |

Dua catatan penting:

* `media_type` **tidak** dipetakan ke kosakata prototype (Reels/Feed/Carousel). Pemetaan
  itu tidak terdefinisi di mana pun, dan mengarangnya berarti menaruh label di layar yang
  tidak didukung data. Nilainya dibawa apa adanya: `clips`, `carousel_container`, `feed`,
  `VIDEO`, `CAROUSEL`, `unknown`.
* Heatmap dibaca **langsung dari layer Feature**, bukan L2 — karena `l2_gold` di database
  `kol` hanya punya 8 tabel dan `posting_time_heatmap` bukan salah satunya. Menambahkannya
  berarti migration. `dow`/`hour` sudah Asia/Jakarta dan **tidak boleh digeser lagi**.

Ini juga membatalkan pernyataan di `docs/L0_L1_L2_FLOW.md` §Feature Layer bahwa *"tidak
satu pun tabel feature dibaca langsung oleh UI"* — sejak `232da34`, dua kolom feature
(`engagement_rate` dan `best_posting_time_heatmap`) dibaca endpoint.

## J9 — Yang **tidak** berubah, dan kenapa

| Filter | Status | Penghambat sebenarnya |
|---|---|---|
| Growth 30D · Rising Creator · Stability · Viral Frequency · Momentum | **tetap DERIVED — INCOMPLETE** | Butuh snapshot berjarak ≥30 hari. **0 akun punya 3 snapshot.** Scraping berhenti sejak 2026-08-28, jadi angka 25 tidak bergerak. Paling cepat awal Oktober kalau scheduler mulai minggu ini |
| Riwayat follower (time-series) | **tidak ada** | Gudang menyimpan paling banyak **2 snapshot per akun**. Kurva enam bulan di halaman detail masih model, bukan data |
| Gender · Lokasi · Minat · Kualitas audiens | **tetap PARTIAL, dan tetap tanpa filter di listing** | 23 KOL. Sudah tampil di halaman detail, tapi tidak ada filter backend-nya |
| Avg/Median Views · Posting Frequency · Paid Ratio · V2F · L2V | **CALCULATION MISSING** | Bahannya ada di L2 mentah (`post_metric`, `kol_metric_daily/_monthly`), agregatnya belum pernah dihitung |
| Authenticity · Audience Quality | **CALCULATION MISSING** | Skornya ada di `feature.{ig,tt}_audience_analysis` (23 KOL), belum diekspos endpoint |
| Save/Share rate | **tetap MISSING untuk Instagram** | `post_metric.saves`/`shares` 0 dari 186 baris IG; TikTok 291 baris punya |
| Reach · Impressions · Watch time · Umur audiens | **tetap MISSING** | Butuh Insights API — lead time eksternal, bukan pekerjaan kode |
| Profiling Status · Data Status · Update Frequency · Next Update · Monitoring Priority | **tetap MISSING** | `refresh_tier` 0 · `scheduler_config` 0 baris. Keputusan jadwal belum diambil |
| Creator city | **tetap MISSING** | 0 dari 7.720 |
| Reliability · Content Topic · Content Style · Sentiment | **tetap MISSING** | Sentiment & content topic punya raw di L0 tapi belum ada asset; sisanya tidak punya kolom |
| Collections / shortlist | **tetap tidak ada tabelnya** | Daftar tersimpan di halaman Discovery masih state klien, bukan tabel database |
| 277 grup username duplikat | **belum dibersihkan** | Dampaknya ke paging sudah ditutup (J7); dampaknya ke hitungan hasil filter **belum** |

## Verifikasi yang benar-benar dijalankan

| Apa | Hasil |
|---|---|
| `pytest` di `scrapper-project` | **354 lulus**, 40 di antaranya `tests/test_followers_guard.py` (baru) |
| `npx tsc --noEmit` di `autometric` | **exit 0** |
| Baseline baris roster sesudah semua perubahan endpoint | **7.721**, nol duplikat, nol KOL hilang |
| Badge verified L2 vs sumber L0 | **0 beda** |
| Sanity guard followers | **51 baris → NULL**, 0 di antaranya ber-acuan < 1.000 |
| Pengukuran database | read-only, `set_session(readonly=True)`, 8 September 2026 |

Tidak ada scraping baru dan tidak ada perubahan schema tabel pada perubahan 8–9 September.
Satu-satunya penulisan data adalah migration 035, yang mengganti definisi
`sp_build_unified_profile()` sehingga kolom `followers_count` di L1 dibangun ulang dengan
guard — bukan `DELETE`/`UPDATE` manual atas data.
