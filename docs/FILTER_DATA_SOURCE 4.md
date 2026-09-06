# KOL Discovery — Data Source Final per Filter

**Task 4** · Database `kol` — read-only · 2026-09-03
**Populasi / denominator:** `public.kol_directory` = **7.720 KOL**
**Input:** `KOL_DISCOVERY_FILTER_REQUIREMENTS.md` (Task 1) ·
`KOL_DISCOVERY_FILTER_DB_MAPPING.md` (Task 2 + Correction) ·
`KOL_DISCOVERY_FILTER_DATA_COMPLETENESS.md` (Task 3)

> ### Status dokumen — direvisi 2026-09-06
>
> Pembagian empat jenis pekerjaan di §Kesimpulan **tetap berlaku dan menjadi dasar Task 5.**
> Lima hal yang berubah:
>
> 1. **Last Updated bukan READY** — 73,6% nilainya bukan jejak scrape. READY turun dari 3 ke 2.
> 2. **Kategori pakai `category_ids` + `taxonomy_key`**, bukan `category_id → name`; solusi
>    "tambah chip Entertainment + Moms" sudah dikerjakan migration `029`.
> 3. **6 filter app-only tidak tercakup** dokumen ini: Max Rate Card, Min Authenticity,
>    Min Brand Fit, Max Paid Ratio, Min Campaigns, Profiling Status.
> 4. **Solusi Growth ("sesuaikan threshold") prematur** — periodenya dulu yang salah, dan
>    belum ada satu pun sampel 30D untuk mengkalibrasi ambang.
> 5. **Kedua Excel tidak sinkron** dengan dokumen ini. `mapping filter database.xlsx` masih
>    beku di status Task 2; `deliv.xlsx` masih memetakan Tier ke `kol_profile_card.tier`.
>
> Detail di **§Revisi 2026-09-06** di akhir dokumen.
> Source mapping final: `docs/KOL_DISCOVERY_TASK5_DESIGN.md` §2.

---

## Aturan yang dipakai

| Aturan | Penerapan |
|---|---|
| Denominator | `public.kol_directory` = 7.720 — seluruh coverage dihitung terhadap angka ini |
| **Verified only** | Hanya `social_account.oauth_token IS NOT NULL` (= sudah connect/OAuth), **bukan** centang biru. Nilai token tidak pernah dibaca |
| **Roster** | `l0_raw.kol_roster_import` **tidak** dipakai sebagai source maupun denominator |
| **Location kreator** | Dipisahkan tegas dari audience location — `audience_geo_daily` tidak boleh dipakai untuk filter kreator |
| **KOL Tier** | Dua opsi dibandingkan, dipilih yang paling usable — lihat No. 3 |
| **Filter derived** | Field dasarnya ditulis eksplisit di kolom Logic |
| **Source baru** | Tidak ada yang diusulkan tanpa bukti dari DB atau repo |

**Coverage = jumlah KOL yang nilainya *usable* ÷ 7.720** (bukan relationship coverage).

**Status:** `READY` siap dipakai · `PARTIAL` jalan tapi coverage/opsi kurang ·
`MISSING` belum bisa dipakai · `SYNTHETIC` tidak ada padanan DB.

**JOIN path standar** (dipakai di tabel sebagai `[SA]`):

```
kol_directory.id → kol_social_account.kol_id
                   kol_social_account.social_account_id → social_account.id
                                                          → l2_gold.* / feature.*
```

---

## Tabel Utama — 32 Filter

| # | Filter | Source / Field | JOIN | Logic | Coverage | Status | Solusi |
|--:|---|---|---|---|---:|---|---|
| 1 | **Platform** | `kol_directory.platform_id` → `platforms.key` | `platforms` (FK `fk_kol_directory_platform_id`) | `platforms.key = chip` | **97,1%** (7.496) | **READY** | — · Chip **YouTube** tidak punya baris `platforms`: hapus chip atau tambah KOL YouTube *(keputusan produk)* |
| 2 | **Kategori KOL** | `kol_directory.category_id` → `kol_categories.name` | `kol_categories` (FK `fk_kol_directory_category_id`) | `name = chip`; Food = `Foodies` + `Food` | **39,8%** (3.070) | **PARTIAL** | Tambah chip untuk kategori besar yang belum ada (`Entertainment` 436, `Moms` 378) → +1.104 KOL. Chip **Tech** hanya 2 KOL |
| 3 | **KOL Tier** | `kol_directory.followers_count` | — *(Direct)* | Bucket dihitung saat query: Nano 1K–10K · Micro 10K–50K · Mid 50K–500K · Macro 500K–1M · Mega >1M | **93,2%** (7.194) | **READY** | **Ganti source.** L2 `kol_profile_card.tier` hanya 25,5% *(1.972)* — pakai `followers_count`, 3,7× lebih luas. Jangan pakai tabel `kol_tiers`: batasnya beda dari UI *(Macro 100K–1M vs 500K–1M)* |
| 4 | **Gender skew** | `l2_gold.audience_demographics_daily` (`audience_type='gender'`, `dimension_key`, `audience_count`) | `[SA]` | **Renormalisasi wajib:** `female ÷ (total − unknown) ≥ 0,60`; male ≥ 0,55 | **0,22%** (17) | **PARTIAL** | **Perbaiki rumus** — dengan penyebut mentah hasilnya 0 KOL, tanpa `unknown` jadi 17. `unknown` rata-rata 71,3%. Tambah data audiens untuk naikkan coverage |
| 5 | **Verified only** | `public.social_account.oauth_token` | `[SA]` | `sa.oauth_token IS NOT NULL` | **0%** (0) | **MISSING** | **Belum bisa digunakan.** Field & rule sudah benar *(migration 006/011/020)*; 0 dari 7.496 akun connect. Butuh KOL benar-benar OAuth — bukan pekerjaan pipeline. Jangan pakai `verified_status` (454 baris, artinya beda) |
| 6 | **Age** | — | — | — | **0%** (0) | **MISSING** | **Tambah data.** `audience_demographics_daily.audience_type` hanya berisi `gender`; tidak ada satu baris `age`. Butuh sumber inferensi umur audiens |
| 7 | **Location (kreator)** | `kol_directory.creator_city` | — *(Direct)* | `creator_city = pilihan dropdown` | **0%** (0) | **MISSING** | **Tambah data.** Kolom ada (`varchar`, ordinal 12), 0/7.720 terisi. Isi saat registrasi/onboarding KOL. `influencer_address` ditolak *(118 KOL, alamat surat, 43 nilai `Jalan jalan`)*; rate card `location` 0 baris |
| 8 | **Audience location** | `l2_gold.audience_geo_daily.geo_key` (`geo_level='city'`) | `[SA]` | Top-1 `geo_key` per KOL | **0,19%** (15) | **PARTIAL** | Tambah data audiens. Normalisasi granularitas: 9 dari 33 key sebenarnya provinsi/pulau (`Bali`, `Sulawesi`, `Jawa`, `Banten`, `Lampung`). Level `province` tidak ada di DB |
| 9 | **Audience interest** | `l2_gold.audience_interest_daily.interest_key` | `[SA]` | Top-N `interest_key`, **buang `unknown`** | **0,30%** (23) | **PARTIAL** | Tambah data audiens. `unknown` = 85,2% bobot (2.021 dari 2.371) — harus dikeluarkan sebelum diperingkat. Taksonomi 19 key perlu diselaraskan dengan `kol_categories` |
| 10 | **Audience Quality** | `feature.ig_audience_analysis` + `feature.tt_audience_analysis` — `authenticity_score`, `audience_quality_score` | `[SA]` + **UNION 2 tabel** | `(authenticity + audience_quality) / 2` → bucket ≥85 / ≥75 / <75 | **0,30%** (23) | **PARTIAL** | Tambah data. Kedua tabel 100% terisi untuk baris yang ada (IG 13 + TT 10). Bucket "High (85+)" hanya 1 KOL; rentang skor 43,5–90,0 |
| 11 | **Content Category / Topic** | — | — | Prototype: hash ID | — | **SYNTHETIC** | **Belum bisa digunakan.** Tidak ada kolom topik konten di DB. Butuh field/klasifikasi baru — keputusan produk dulu |
| 12 | **Content Format** | `l2_gold.content_format_daily.media_type` | `[SA]` | Mapping: `clips`→Reels · `carousel_container`/`CAROUSEL`→Carousel · `feed`→Feed · Video = `clips`+`VIDEO` · Photo = `feed`+Carousel | **0,38%** (29) | **PARTIAL** | Tambah data konten. Opsi **Story** tidak punya sumber (`unified_story` 0 baris) → hapus chip. 3 KOL ber-`media_type='unknown'` tidak terpetakan |
| 13 | **Content Style & Personality** | — | — | Prototype: 10 nilai hardcode | — | **SYNTHETIC** | **Belum bisa digunakan.** Tidak ada kolom gaya konten di DB |
| 14 | **Engagement Rate** | `kol_directory.engagement_rate` *(utama)* · `l2_gold.kol_metric_daily.er_followers_daily` *(alt)* | — *(Direct)* / `[SA]` | `engagement_rate ≥ 3` / `≥ 5,5` (satuan persen). L2 bersatuan fraksi → **×100** | **2,84%** (219) | **PARTIAL** | **Ganti source + bersihkan.** L2 hanya 22 KOL (0,28%); `kol_directory` 1.756 tapi **83 nilai >10% mustahil** (maks 223,41%) — buang dulu, sisa 1.673 valid (21,7%) |
| 15 | **Save Rate** | `l2_gold.post_metric.saves` ÷ (`likes`+`comments`) | `[SA]` | `saves ÷ engagement ≥ 5%` | **0,05%** (4) | **PARTIAL** | Tambah data. **11 KOL, TikTok saja** — IG tidak menyediakannya lewat scraping publik. Rumus prototype (*audience affinity*) tidak punya padanan kolom — pakai rumus rasio ini |
| 16 | **Share Rate** | `l2_gold.post_metric.shares` ÷ (`likes`+`comments`) | `[SA]` | `shares ÷ engagement ≥ 1,8%` | **0,09%** (7) | **PARTIAL** | Sama seperti No. 15 — 11 KOL TikTok saja |
| 17 | **Views** | `l2_gold.post_metric.views` | `[SA]` | `avg(views) per KOL ≥ 150K / ≥ 300K` | **0,27%** (21) | **PARTIAL** | Tambah data konten. Verifikasi outlier: 3 KOL rata-rata >10 juta, maks 78.091.457 (median 474.870) |
| 18 | **Reliability** | — | — | Prototype: `k.cons` (hash) | **0%** | **MISSING** | **Belum bisa digunakan.** Penyapuan katalog untuk `consist\|reliab\|stabil\|volatil\|cadence\|frequency` → **0 kolom di seluruh DB**. Butuh field baru + definisi produk |
| 19 | **Performance Stability** | `l2_gold.kol_metric_monthly` (deret `er_followers_monthly` / `followers_eom`) | `[SA]` | Volatilitas deret bulanan; Stable <28 | **0,06%** (5) | **PARTIAL** | Tambah kedalaman deret. Butuh ≥4 titik bulanan: hanya **5 KOL** punya (≥2 bulan: 18 · ≥3: 12 · **≥6: 0**, maks 5 bulan) |
| 20 | **Viral Frequency** | `l2_gold.kol_metric_monthly` (deret) | `[SA]` | Ketergantungan viral ≥55 dari deret bulanan | **0,06%** (5) | **PARTIAL** | Sama seperti No. 19 — field dasar & penghambatnya identik |
| 21 | **Growth Classification** | `l2_gold.kol_profile_card.followers_growth` | `[SA]` | **Satuan persen** *(migration 025)*. Exploding ≥8% · Rising ≥4,5% · Stable ≥1% · Declining <1% | **0,32%** (25) | **PARTIAL** | **Keputusan produk.** Rentang nyata **−0,051% s.d. +0,917%** → 3 dari 4 bucket **selalu 0**, semua 25 KOL masuk "Declining". Sesuaikan threshold atau definisi periode — menambah data tidak menolong |
| 22 | **Rising Creator** | `followers_growth` + `er_followers_daily` + `kol_directory.followers_count` | `[SA]` ×2 | growth ≥5,5% **AND** ER ≥4,5% **AND** followers <1 juta **AND** tren tidak turun | **0%** (0) | **MISSING** | **Keputusan produk.** Irisan ketiga field sehat (**21 KOL**), tapi threshold growth ≥5,5% **6× di atas nilai tertinggi** yang ada di DB (0,917%) → 0 lolos |
| 23 | **Data Status** | `kol_directory.last_refreshed_at` **÷ interval update** | — | `umur data ÷ interval`; Fresh <0,5 · Aging <0,85 · Due <1,2 · Outdated ≥1,2 | **0%** (0) | **MISSING** | **Tambah field.** Pembilang sehat (97,1%), **penyebut tidak ada**: `refresh_tier` 0/7.720 · `scheduler_config` 0 baris. Gap struktural — interval update per KOL belum punya tempat di schema |
| 24 | **Last Updated** | `kol_directory.last_refreshed_at` | — *(Direct)* | `now() − last_refreshed_at` ≤24j/72j/168j/720j/>720j | **97,1%** (7.496) | **READY** | — · Catatan sebaran: bucket 24 Jam & 3 Hari **kosong**; 6.493 KOL (84,1%) belum refresh >30 hari |
| 25 | **Update Frequency** | `kol_directory.refresh_tier` | — | Interval 6 / 24 / 168 / 720 jam | **0%** (0) | **MISSING** | **Tambah data.** Kolom ada, **0/7.720 terisi**. Di prototype ini turunan Monitoring Priority (No. 27), bukan field terpisah |
| 26 | **Next Update** | `last_refreshed_at` + interval update | — | `last_refreshed_at + interval` ≤9j / ≤24j / ≤72j | **0%** (0) | **MISSING** | **Tambah field.** Terblokir penyebut yang sama dengan No. 23 & 25 |
| 27 | **Monitoring Priority** | `campaigns` + `campaign_kols` + `followers_growth` + viral | `[SA]` | High = campaign aktif ATAU growth exploding ATAU viral frequent | **0%** (0) | **MISSING** | **Tambah data.** Keempat input kosong: `campaigns` 0 · `campaign_kols` 0 · growth 25 *(semua "declining")* · viral 5. Seluruh populasi jatuh ke "Standard" → tidak menyaring apa pun |
| 28 | **Keyword search** | `kol_directory.username` · `bio` · `kol_categories.name` · `kol_profile_card.display_name`/`bio` | `kol_categories` + `[SA]` | `ILIKE '%q%'` di seluruh field | **97,1%** (7.497) | **PARTIAL** | Union bio dua sumber → 11,7% naik ke 24,3%. **4 dimensi yang dijanjikan placeholder tidak punya kolom**: niche · topik utama/sub-topik · DNA/gaya konten · brand. Hapus dari placeholder atau tambah field |
| 29 | **Smart Criteria (NL)** | 29 aturan — mewarisi source filter lain | beragam | Pencocokan pola teks → set filter | — | **PARTIAL** | 6 aturan berbasis hash prototype *(Gen Z, Millennial, Indonesia, Jabodetabek, Brand Safe, Active community)* = **SYNTHETIC**. 23 sisanya mewarisi coverage filter rujukan — mayoritas <1% |
| 30 | **Section tabs** | `created_at` · `last_refreshed_at` · `brand_fit_analysis` · `unified_rate_card` | `[SA]` | Per tab | **99,7%** (7.698) | **PARTIAL** | **2 dari 7 tab punya sumber**: Newly Added (`created_at` 99,7%) · Recently Updated (97,1%). High Match butuh `brand_fit_analysis` **0 baris**; High ROI butuh `unified_rate_card` **0 baris**; Trending terblokir growth (No. 21); Recently Viewed = state browser |
| 31 | **Exclude** | `campaigns` · `campaign_kols` · `feature.*_audience_analysis` · `post_metric.is_sponsored` | `[SA]` | Per opsi | **0%** (0) | **MISSING** | **5 dari 7 opsi terblokir.** `campaign_kols`/`campaigns` 0 baris; "competitor-heavy" & "high-risk" tidak punya kolom. Yang bisa dihitung: low-quality (20 KOL) · declining (25) · sponsored-heavy (**30 KOL punya data, 0 lolos >35%**) |
| 32 | **Collections** | — | — | Shortlist di state browser | — | **SYNTHETIC** | **Belum bisa digunakan.** Penyapuan katalog `collection\|shortlist\|saved_list\|bookmark\|wishlist` → **0 tabel**. Butuh tabel baru kalau shortlist harus persist |

---

## Rekapitulasi

| Status | Jumlah | Filter |
|---|---:|---|
| **READY** | 3 | Platform · KOL Tier · Last Updated |
| **PARTIAL** | 16 | Kategori · Gender skew · Aud. location · Aud. interest · Aud. Quality · Content Format · Engagement Rate · Save Rate · Share Rate · Views · Performance Stability · Viral Frequency · Growth Classification · Keyword search · Smart Criteria · Section tabs |
| **MISSING** | 10 | Verified only · Age · Location kreator · Reliability · Rising Creator · Data Status · Update Frequency · Next Update · Monitoring Priority · Exclude |
| **SYNTHETIC** | 3 | Content Category/Topic · Content Style & Personality · Collections |
| | **32** | |

---

## Kesimpulan

> **Cara membaca empat bagian di bawah:** ini pengelompokan **jenis pekerjaan**,
> bukan pembagian ulang status — satu filter bisa muncul di dua bagian kalau
> memang butuh dua hal sekaligus (Kategori, Content Format, dan Keyword search
> masing-masing butuh perbaikan data **dan** keputusan produk). Jumlah per bagian
> karena itu tidak menjumlah menjadi 32; yang menjumlah 32 adalah tabel
> Rekapitulasi di atas.
>
> Dua filter PARTIAL bersifat **turunan** dan tidak muncul terpisah di bawah:
> **Smart Criteria** (23 dari 29 aturannya mewarisi filter lain, 6 sisanya
> SYNTHETIC) dan **Section tabs** (tiap tab mewarisi sumber filter lain).
> Keduanya ikut membaik sendiri begitu filter yang dirujuknya membaik.

### 1. Filter yang sudah READY — 3

| Filter | Source final | Coverage |
|---|---|---:|
| **Platform** | `kol_directory.platform_id` → `platforms.key` | 97,1% |
| **KOL Tier** | `kol_directory.followers_count` *(bucket dihitung saat query)* | 93,2% |
| **Last Updated** | `kol_directory.last_refreshed_at` | 97,1% |

Ketiganya `Direct` atau satu JOIN FK, tidak bergantung L2, dan menjangkau >93%
populasi. **Ketiganya juga sumber yang benar-benar aman dipakai hari ini.**

Keputusan penting di sini adalah **KOL Tier**: Task 2 memetakannya ke
`kol_profile_card.tier` (25,5%), padahal tier adalah fungsi murni dari jumlah
follower dan `kol_directory.followers_count` terisi 97,1%. Dengan menghitung
bucket saat query — bukan membaca kolom `tier` — coverage naik **3,7×**
(1.972 → 7.194) dan sekaligus menghindari konflik batas dengan tabel `kol_tiers`.

Dua catatan yang tidak memblokir tapi perlu diketahui: chip **YouTube** tidak
punya baris di `platforms`, dan **84,1% populasi** belum di-refresh lebih dari
30 hari sehingga Last Updated menumpuk di satu bucket.

> **⚠️ Koreksi (2026-09-06): READY bukan 3, melainkan 2.**
> **Last Updated keluar dari daftar ini.** Bukan karena coverage — 97,1% tetap benar — tapi
> karena **artinya**: untuk **5.520 dari 7.496 baris (73,6%)**, `last_refreshed_at` tidak
> berasal dari scrape mana pun. KOL-nya tidak punya satu baris pun di `l0_raw`; tanggalnya
> ikut masuk bersama excel import. Umur median 847 hari.
>
> Kalimat "84,1% belum di-refresh >30 hari" karenanya juga tidak akurat — yang benar,
> **untuk mayoritas populasi kita tidak tahu kapan terakhir di-refresh.** Status turun ke
> **PARTIAL**. Lihat §Revisi R1.
>
> Yang tetap READY: **Platform** dan **KOL Tier**. Kategori lewat `taxonomy_key` adalah
> kandidat ketiga, menunggu verifikasi V-01.

### 2. Filter yang perlu perbaikan data — 13

**Naik tanpa data baru (4)** — cukup ganti source atau perbaiki rumus:

| Filter | Perbaikan | Dampak |
|---|---|---|
| **Gender skew** | Keluarkan `unknown` dari penyebut | 0 → **17 KOL** lolos |
| **Engagement Rate** | Pakai `kol_directory.engagement_rate`, buang 83 nilai >10% | 0,28% → **21,7%** |
| **Keyword search** | Union `kol_directory.bio` + `kol_profile_card.bio` | 11,7% → **24,3%** |
| **Kategori KOL** | Tambah chip `Entertainment` + `Moms` | +1.104 KOL terjangkau |

**Butuh data di-scrape lebih banyak (9)** — Audience location · Audience interest ·
Audience Quality · Content Format · Save Rate · Share Rate · Views ·
Performance Stability · Viral Frequency.

Seluruhnya bertumpu pada dua tabel yang sama: data konten menutup **30 KOL (0,39%)**
dan data audiens **23 KOL (0,30%)**. Selama kedua angka itu tidak naik, sembilan
filter ini menyembunyikan >99% populasi — bukan karena kreatornya tidak memenuhi
kriteria, tapi karena nilainya tidak diketahui.

Dua di antaranya punya batas tambahan yang tidak selesai dengan menambah volume:
**Save/Share Rate hanya ada di TikTok** (11 KOL, 0 Instagram — IG tidak
menyediakannya lewat scraping publik), dan **Stability/Viral butuh kedalaman
deret**, bukan lebar — tidak ada satu pun KOL yang punya riwayat 6 bulan.

### 3. Filter yang butuh keputusan produk — 6

| Filter | Yang perlu diputuskan |
|---|---|
| **Growth Classification** | Rentang nyata −0,051% s.d. **+0,917%**, sementara bucket terendah UI menuntut ≥1% → 3 dari 4 chip **selalu nol**. Sesuaikan threshold atau definisi periode pertumbuhan |
| **Rising Creator** | Threshold growth ≥5,5% — **6× di atas nilai tertinggi** yang ada di database |
| **Platform** | Chip **YouTube** tanpa baris `platforms`: hapus chip, atau mulai kumpulkan KOL YouTube |
| **Content Format** | Chip **Story** tanpa sumber (`unified_story` 0 baris) |
| **Kategori KOL** | Chip **Tech** hanya 2 KOL; dua kategori terbesar berikutnya di DB tidak punya chip |
| **Keyword search** | Placeholder menjanjikan pencarian *topics, DNA, brands* — **empat dimensi ini tidak punya kolom**. Turunkan janji placeholder atau tambah field |

Yang perlu digarisbawahi: **Growth Classification dan Rising Creator tidak akan
membaik walaupun coverage-nya 100%.** Selama nilai maksimum `followers_growth`
0,917% dan lantai bucket terendah 1%, menambah data hanya menambah KOL di
bucket "Declining". Ini murni keputusan threshold, bukan pekerjaan data.

### 4. Filter yang belum bisa digunakan — 10

**Terblokir satu gap struktural (3)** — Data Status · Update Frequency · Next Update.

Ketiganya memakai penyebut yang sama: **interval update per KOL, yang belum punya
tempat di database.** `refresh_tier` ada sebagai kolom tapi 0/7.720 terisi,
`scheduler_config` 0 baris. Pembilangnya (`last_refreshed_at`) justru sehat 97,1%.
**Ini satu-satunya temuan yang butuh keputusan arsitektur**, bukan pengisian data.

**Butuh sumber data yang belum ada sama sekali (4)** — Age *(tidak ada baris
`audience_type='age'`)* · Reliability *(0 kolom di seluruh DB)* ·
Monitoring Priority *(keempat input kosong)* · Exclude *(5 dari 7 opsi terblokir,
`campaigns`/`campaign_kols` 0 baris)*.

**Butuh pengisian, kolomnya sudah ada (1)** — **Location kreator**.
`kol_directory.creator_city` tersedia secara struktural (`varchar`, ordinal 12)
tapi 0/7.720 terisi. Dua kandidat alternatif sudah ditelusuri dan **ditolak**:
`influencer_address` (118 KOL, alamat surat, 43 nilai berisi placeholder
`Jalan jalan`) dan rate card `location` (5 tabel, semuanya 0 baris).
Jalur yang direkomendasikan: isi saat registrasi/onboarding KOL.

**Terblokir adopsi, bukan teknis (1)** — **Verified only**.
Source, business rule, dan implementasinya **sudah benar dan konsisten 100%**
(`oauth_token IS NOT NULL`, terpasang di migration 006/011/020, terverifikasi
di DB live). Yang belum ada adalah KOL yang benar-benar connect: 0 dari 7.496.
**Tidak ada pekerjaan engineering yang perlu dilakukan di sini.**

**Tidak punya padanan DB (3)** — Content Category/Topic · Content Style &
Personality · Collections. Nilainya diciptakan prototype (hash ID / hardcode /
state browser). Untuk Collections, penyapuan katalog memastikan **tidak ada tabel
shortlist sama sekali** — perlu tabel baru kalau shortlist harus persist.

---

### Gambaran akhir

Dari 32 filter, **3 siap dipakai hari ini** dan **4 lagi bisa menyusul tanpa satu
baris data baru** — cukup ganti source atau perbaiki rumus. Tujuh filter itulah
yang realistis untuk rilis pertama.

Sisanya terbagi rapi menjadi tiga jenis pekerjaan yang pemiliknya berbeda:
**naikkan coverage scraping** (9 filter, bertumpu pada dua tabel yang sama),
**putuskan threshold & isi chip UI** (6 filter, tidak butuh data), dan
**sediakan tempat/sumber yang memang belum ada** (10 filter, dipimpin satu gap
struktural: interval update per KOL).

---

**Audit trail:** dokumen ini sintesis Task 1–3; seluruh angka berasal dari query
read-only yang sudah dijalankan di sesi sebelumnya. Tidak ada query baru, tidak
ada perubahan pada database, schema, source code, migration, atau config; tidak
ada commit/push. JOIN hanya disebut sebagai rencana analisis, tidak
diimplementasikan ke kode.

---

# Revisi — 2026-09-06

Sumber: revisi Task 1–3 di sesi yang sama · `deliv.xlsx` (DELIVERABLES + Mapping Filter-DB) ·
`KOL_DISCOVERY_FILTER_BACKEND_PLAN.md` · `KOL_DISCOVERY_MONITORING_PRIORITY_AUDIT.md` ·
migration `029` · diff `db.py`.

> Tabel utama dan §Kesimpulan **sengaja dibiarkan apa adanya** sebagai audit trail.
> Kalau ada pertentangan, **section ini yang berlaku**. Tidak ada query baru — database tidak
> bisa dijangkau saat revisi ini ditulis (TCP timeout ke `10.100.14.216:5432`).

## R1 — No. 24 Last Updated: READY → PARTIAL

Coverage 97,1% benar; **artinya** yang tidak. 5.520 dari 7.496 baris (73,6%) punya
`last_refreshed_at` tapi **tidak punya data apa pun di `l0_raw`** — tanggalnya warisan
`excel_import` (7.718 dari 7.720 baris `kol_directory`), bukan jejak scrape. Umur median 847 hari.

Efeknya ke §Kesimpulan bagian 4: *"Terblokir satu gap struktural (3) — ketiganya memakai penyebut
yang sama... Pembilangnya (`last_refreshed_at`) justru sehat 97,1%"* **tidak benar**.
Pembilangnya tidak sehat. Data Status, Update Frequency, dan Next Update butuh **dua** perbaikan,
bukan satu. Sumber: `KOL_DISCOVERY_MONITORING_PRIORITY_AUDIT.md` Lampiran C.

## R2 — No. 2 Kategori: source dan solusinya berubah

| | Isi lama | Setelah revisi |
|---|---|---|
| Join | `category_id` → `kol_categories.name` | **`category_ids`** (array) → **`taxonomy_key`** |
| Logic | `name = chip`; Food = `Foodies` + `Food` | `EXISTS (c.id = ANY(k.category_ids) AND c.taxonomy_key = ?)` |
| Coverage | 39,8% (3.070) | **±53,8% (±4.155)** — NEEDS VERIFICATION V-01/V-02 |
| Solusi | "Tambah chip `Entertainment` + `Moms` → +1.104 KOL" | **Sudah dikerjakan** — migration `029` memetakan 22 dari 28 kategori mentah ke 9 Discovery Category |

Chip **Tech** juga tidak lagi "hanya 2 KOL": taxonomy `Tech` menaungi `Technology and gadgets`
**dan** `Gaming`.

## R3 — Enam filter app-only yang tidak tercakup dokumen ini

Dokumen ini mewarisi scope Task 1, yang berbasis prototype. App produksi punya enam filter yang
tidak ada di tabel 32:

| Filter | Surface | Source | Status |
|---|---|---|---|
| Max Rate Card | Creator Database (**DONE**) | `l1_silver.unified_rate_card.fee` | `MISSING` — 5 tabel rate card, 0 baris |
| Min Authenticity | Creator Database (`disabled`) | `feature.{ig,tt}_audience_analysis.authenticity_score` | `PARTIAL` — 23 KOL |
| Min Brand Fit | Creator Database (`disabled`) | `feature.brand_fit_analysis` | `MISSING` — 0 baris |
| Max Paid Ratio | Creator Database (`disabled`) | `post_metric.is_sponsored` | `PARTIAL` — 29 KOL, 0 lolos >35% |
| Min Campaigns | Creator Database (`disabled`) | `campaign_kols` ← `agency_kol_accounts` | `MISSING` — 0 baris |
| Profiling Status | My Creators (**DONE**) | `kol_directory.scrape_status` | `PARTIAL` — 99 KOL · NEEDS VERIFICATION V-04 |

Ditambah **Lower Price than Reference** (Smart Discovery) yang memakai sumber sama dengan
Max Rate Card. Total inventaris menjadi **40**, bukan 32.

## R4 — No. 21/22: solusi "sesuaikan threshold" prematur

Dokumen ini menandai Growth Classification dan Rising Creator sebagai **keputusan produk** dengan
solusi *"sesuaikan threshold atau definisi periode"*. Urutannya terbalik:

1. `followers_growth` dihitung dengan `LAG()` antar-snapshot **berapa pun jaraknya** — jarak nyata
   **10 hari** (22 akun) dan **13 hari** (3 akun), bukan 30. Metriknya salah periode, bukan cuma
   ambangnya yang tidak terjangkau.
2. Growth 30D harus dihitung dari deret `l1_silver.unified_profile`
   (`KOL_DISCOVERY_FILTER_BACKEND_PLAN.md` T1), dan **wajib mengembalikan `actual_window_days`**.
3. Hari ini **0 akun** punya dua snapshot berjarak ≥30 hari, dan **0 akun** punya tiga snapshot
   (yang dibutuhkan syarat "tren tidak menurun").

**Threshold tidak boleh ditetapkan sekarang** — belum ada satu pun sampel 30D nyata untuk
mengkalibrasinya. Yang perlu lebih dulu: satu re-scrape sekitar **17 September 2026**, yang membuka
30D growth untuk **1.971 akun**.

## R5 — Kedua Excel tidak sinkron dengan dokumen ini

| Artefak | Kondisi |
|---|---|
| `docs/mapping filter database.xlsx` | Beku di status **Task 2** — AVAILABLE 2 · PARTIAL 18 · MISSING 9 · SYNTHETIC 3. Tidak memuat satu pun keputusan Task 3/4 |
| `docs/deliv.xlsx` sheet *Mapping Filter-DB* | Masih memetakan **Tier → `kol_profile_card.tier`** (dokumen ini sudah memindahkannya ke `followers_count`), **Kategori → `category_id → name`**, menandai **Verified = AVAILABLE** dan **Last Updated = AVAILABLE**, serta **Section tabs = MISSING** (dokumen ini: PARTIAL) |

Empat artefak, tiga kosakata status. **Belum disinkronkan** — Excel sengaja tidak disentuh di sesi
ini. Kosakata tunggal yang berlaku ada di `docs/KOL_DISCOVERY_TASK5_DESIGN.md`
(`DIRECT` / `DERIVED` / `PARTIAL` / `MISSING` / `DECISION`).

## Ringkasan dampak

| Bagian | Isi lama | Setelah revisi |
|---|---|---|
| No. 2 Kategori | `category_id → name` · 39,8% | `category_ids → taxonomy_key` · ±53,8% |
| No. 21/22 Growth | Solusi: sesuaikan threshold | **Periode dulu (T-09), threshold ditunda** |
| No. 24 Last Updated | **READY** | **PARTIAL** — semantik cacat |
| Rekapitulasi | READY 3 · PARTIAL 16 · MISSING 10 · SYNTHETIC 3 | **READY 2 · PARTIAL 17** · sisanya tetap, dari **40** filter |
| §Kesimpulan bag. 1 | 3 filter READY | **2** — Platform, KOL Tier |
| §Kesimpulan bag. 4 | "Pembilangnya justru sehat 97,1%" | **Pembilang juga bermasalah** (R1) |
| Scope | 32 filter | **40** — +6 app-only, +1 Smart Discovery, +1 My Creators |

Source mapping final, transformasi, dan desain lapisan data: `docs/KOL_DISCOVERY_TASK5_DESIGN.md`.
