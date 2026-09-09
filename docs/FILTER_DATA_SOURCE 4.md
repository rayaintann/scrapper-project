# Task 4 — Sumber Data yang Dipakai Tiap Filter

**Tugas:** untuk tiap kebutuhan filter, tentukan **satu** sumber yang dipakai.
Kalau ada beberapa kandidat, pilih satu dan tulis alasannya.

**Dasar:** Task 2 (apa yang ada di database) dan Task 3 (seberapa lengkap isinya).
**Terakhir diperbarui:** 2026-09-09 · **Jumlah KOL:** 7.720

> ## UPDATE 2026-09-09 — enam keputusan sumber berubah
>
> Diverifikasi terhadap kode yang **sudah ter-commit**: `scrapper-project` @ `fa3af27`,
> `autometric` @ `232da34`. Angka database dari pengukuran read-only 8 September 2026.
>
> | Filter | Sumber di dokumen ini | **Sumber yang benar-benar dipakai sekarang** |
> |---|---|---|
> | **Verified** | ~~`kol_directory.verified_status`~~ → dihapus | **`l2_gold.kol_profile_card.is_verified`** · **572** — dipakai lagi, sumbu terpisah dari Connected |
> | **Engagement rate** | `kol_directory.engagement_rate` (1.756) | **`COALESCE(feature.{ig,tt}_engagement_analysis.engagement_rate, kol_directory.engagement_rate)`** · **1.767** |
> | **Kategori** | `kol_categories.taxonomy_key` | **sama** — tapi baru sejak `232da34` endpoint benar-benar memakainya. Sebelumnya menyaring pakai `name` |
> | **Avatar · Bio · Display name** | `kol_directory.*` | **`COALESCE(kol_profile_card.*, kol_directory.*)`** — avatar 931 → **1.979**, bio 902 → **1.878**, display name 0 → **1.961** |
> | **Last Updated** | *(tidak ada keputusannya)* | **`kol_directory.last_refreshed_at`** — dipakai jadi filter `?updatedWithin=` dan sort `recent` |
> | **Agency** | *(tidak pernah dinilai)* | **`agency_kol_accounts` + `agencies`** · **7.684 dari 7.718** |
>
> **Yang TIDAK berubah:** Followers dan Tier tetap dari `kol_directory.followers_count`
> (P-02 tetap berlaku), Connected tetap `platform_user_id` + `oauth_token`, Growth tetap
> `kol_profile_card.followers_growth` berlabel "Sejak Snapshot Terakhir".
>
> **Satu baris di §"Sumber yang jangan dipakai" perlu dibaca ulang.**
> `kol_directory.last_refreshed_at` masih **tidak boleh dipercaya sebagai penanda kapan
> data di-scrape** — 73,6% nilainya warisan impor Excel, dan diverifikasi ia **selalu**
> lebih tua dari `profile_snapshot_date` L2 (1.024 dari 1.024 kasus). Tapi kolom itu
> **sudah dipakai** untuk filter "Last Updated" dan sort "Last updated". Yang dijual ke
> pengguna adalah *"kapan baris ini terakhir disentuh"*, bukan *"kapan di-scrape"* —
> perbedaan itu harus dijaga di label UI.
>
> **Rate card: keputusan "tidak ada sumber" gugur.** Sumbernya ada dan lengkap di
> `l0_raw.kol_roster_import` (7.718 baris / 7.496 KOL, 7 kolom harga terisi), dan kedua
> procedure-nya (`sp_sync_roster_rate_card`, `sp_build_unified_rate_card`) sudah ada.
> `l1_silver.unified_rate_card` tetap **0 baris** karena tidak ada asset Dagster yang
> memanggil procedure itu. Akibatnya filter `maxRate` **aktif dan selalu mengembalikan
> 0 dari 7.720** — bukan filter yang belum dibuat, melainkan filter yang benar di atas
> tabel kosong.
>
> **Pencarian nama: rancangan dan implementasi belum sama.** Dokumen ini memutuskan
> tiga kolom digabung (`username` + `bio` + `display_name`). Yang ter-implementasi:
>
> | Implementasi | Kolom yang dicari |
> |---|---|
> | `db.search_kol_directory()` (repo ini, CLI `search_kol.py`) | username + display_name + bio, dengan penjenjangan relevansi ✅ |
> | `kolDirectory.ts` (halaman Discovery) | **`username` saja** ⚠ |
>
> **Followers: satu sumber resmi, dua nilai nyata.** `kol_directory.followers_count` dan
> `l2_gold.kol_profile_card.followers_count` berbeda untuk **1.024 dari 1.972** akun.
> Penyebabnya dua dan berlawanan — ~970 roster basi (L2 benar) dan **54 scrape TikTok
> rusak** (roster benar). Aturan "satu filter, satu sumber" tetap dipegang: **roster**.
> Migration 035 memasang sanity guard di `sp_build_unified_profile()` supaya nilai runtuh
> tidak jadi penyebut growth berikutnya (51 baris → NULL). Yang **belum** diputuskan:
> UI menampilkan follower roster sementara growth dihitung dari follower L2, jadi kedua
> angka itu belum bisa direkonsiliasi.

---

> **Status implementasi (2026-09-07).** Tiga keputusan di dokumen ini sudah
> dijalankan dan terverifikasi, jadi dua baris "jangan pakai" di bawah **berubah**:
>
> | Hal | Sebelumnya di dokumen ini | Sekarang |
> |---|---|---|
> | `public.kol_tiers` | ditolak, batas kedaluwarsa | **dipakai** — batas diperbaiki migration 033 |
> | `kol_profile_card.followers_growth` | jangan pakai | **dipakai** untuk filter Growth (bukan 30 hari) |
> | Verified | dicatat sebagai sumber | **dihapus dari Discovery** — diganti Connected |
>
> Detailnya di masing-masing bagian, ditandai **UPDATE 2026-09-07**.

---

## Cara memilih

Tiga aturan yang dipakai saat ada lebih dari satu kandidat:

1. **Pilih yang menjangkau paling banyak KOL.** Sumber yang lebih baru tapi cuma mencakup
   25% populasi kalah dari sumber yang lebih lama tapi mencakup 97%.
2. **Pilih yang artinya paling tepat**, bukan yang kolomnya paling terisi.
   Kolom yang terisi 97% tapi artinya salah tetap tidak dipakai.
3. **Satu filter, satu sumber.** Kalau dua sumber dipertahankan bersamaan, cepat atau lambat
   keduanya akan berbeda dan tidak ada yang tahu mana yang benar.

---

## Keputusan sumber per filter

### Filter yang sumbernya sudah pasti dan datanya cukup

| Filter | Sumber yang dipakai | Terisi | Kenapa ini |
|---|---|---|---|
| **Cari nama** | `kol_directory.username` + `.bio`, digabung `kol_profile_card.display_name` | 97,1% · 11,7% · 25,4% | Tiga kolom digabung supaya hasil pencarian selengkap mungkin. **2026-09-09:** keputusan ini baru terpenuhi di `db.search_kol_directory()`; endpoint Discovery (`kolDirectory.ts`) masih `username` saja |
| **Platform** | `platforms.key` | 97,1% | Satu-satunya sumber platform |
| **Tier** | `kol_directory.followers_count`, **dihitung saat query** | 97,1% | Lihat penjelasan di bawah |
| **Minimum follower** | `kol_directory.followers_count` | 97,1% | Sumber yang sama dengan Tier |
| **Kategori** | `kol_directory.category_ids` → `kol_categories.taxonomy_key` | 53,8% | Lihat penjelasan di bawah. **2026-09-09:** endpoint Discovery memakai `COALESCE(taxonomy_key, name)` — 15 chip, karena 6 dari 28 nama belum punya `taxonomy_key` |
| **Last Updated** *(baru 2026-09-09)* | `kol_directory.last_refreshed_at` | 97,1% | Satu-satunya kolom waktu di roster. **Artinya tetap cacat** — 73,6% warisan impor Excel — jadi labelnya harus "terakhir disentuh", bukan "terakhir di-scrape" |
| **Agency** *(baru 2026-09-09)* | `agency_kol_accounts` + `agencies` | 7.684 / 7.718 | Dipakai lewat `EXISTS`, bukan `JOIN`, supaya kreator yang terdaftar di dua agency tetap satu baris |

### Filter yang sumbernya pasti tapi datanya masih tipis

Sumbernya sudah tidak perlu diperdebatkan. Yang kurang cuma jumlah barisnya.

| Filter | Sumber yang dipakai | Terisi |
|---|---|---|
| Engagement rate | **2026-09-09:** `COALESCE(feature.{ig,tt}_engagement_analysis.engagement_rate, kol_directory.engagement_rate)` | **1.767** · 22,9% |
| Format konten | `content_format_daily.media_type` | 30 · 0,39% |
| Views | `post_metric.views` | 30 · 0,39% |
| Rasio konten berbayar | `post_metric.is_sponsored` | 30 · 0,39% |
| Save rate / Share rate | `post_metric.saves` / `.shares` | 11 · 0,14% (TikTok saja) |
| Gender audiens | `audience_demographics_daily` | 23 · 0,30% |
| Lokasi audiens | `audience_geo_daily` (kota) | 15 · 0,19% |
| Minat audiens | `audience_interest_daily` | 23 · 0,30% |
| Kualitas audiens | `feature.ig_audience_analysis` + `tt_audience_analysis` | 23 · 0,30% |
| **Connected** | `social_account.oauth_token` + `social_account.platform_user_id` | 0 · 0% |
| **Verified** *(kembali 2026-09-09)* | **`l2_gold.kol_profile_card.is_verified`** — bukan `kol_directory.verified_status` | **572** |
| **Growth** *(baru)* | `l2_gold.kol_profile_card.followers_growth` | 25 · 0,32% |

~~**UPDATE 2026-09-07 — Verified dihapus dari Discovery.**~~ **DIBALIK 2026-09-09.**
Badge verified kembali sebagai field dan filter, tapi **bukan** dari
`kol_directory.verified_status` (454). Sumbernya sekarang
`l2_gold.kol_profile_card.is_verified` — **572 KOL** — yang diisi dari badge platform
asli di L0: `ig_profile_apify.raw_payload->>'verified'` (470 true) dan
`l0_harmonization.tiktok_profile.is_verified` (124 true). Discovery punya **dua** sumbu:
Connected (0) dan Verified (572), dengan ikon berbeda. Karena 572 ≠ 0, salah satu tidak
bisa mewakili yang lain.

**UPDATE 2026-09-07 — Growth masuk daftar ini.** Sumbernya `kol_profile_card.followers_growth`,
diambil lewat `kol_directory → kol_social_account → kol_profile_card`. Followers dan Tier
**tetap** dari `kol_directory` — kartu L2 hanya dipakai untuk kolom growth-nya saja.

### Filter yang belum punya sumber

| Filter | Kondisi | Yang dibutuhkan |
|---|---|---|
| Profiling Status | Tidak ada nilai apa pun di database yang berarti "sedang diproses" | Keputusan produk + perubahan pipeline |
| Kota kreator | `creator_city` kosong 100% | Diisi saat pendaftaran |
| Umur audiens | Barisnya tidak pernah ditulis pipeline | Perluas analisis audiens |
| Growth 30 hari | Belum ada akun yang punya 2 data berjarak 30 hari | Menunggu waktu — **tetap belum ada**. Yang dikirim sekarang adalah growth *sejak snapshot terakhir* (10–13 hari), bukan 30 hari |
| Data Status · Update Frequency · Next Update · Monitoring Priority | `refresh_tier` kosong, `scheduler_config` kosong | Keputusan jadwal update |
| Rate card · Data campaign | 19 tabel, hampir semuanya kosong | Adopsi produk |
| Reliability · Topik konten · Gaya konten | Kolomnya tidak ada di database | Fitur baru |
| Collections | Tabelnya tidak ada | **Satu-satunya tabel baru yang perlu dibuat** |

---

## Tiga pilihan sumber yang perlu dijelaskan

Ketiganya punya lebih dari satu kandidat, jadi alasannya ditulis lengkap.

### Kategori: `category_ids`, bukan `category_id`

| Kandidat | Isi | Terisi |
|---|---|---|
| `category_id` | **satu** kategori saja | 4.174 |
| **`category_ids`** ✅ | **daftar** kategori | 4.174 |

Terisi sama banyak, tapi isinya beda. **1.183 KOL punya lebih dari satu kategori**, dan
`category_id` cuma menyimpan salah satunya secara acak.

Contoh: `tasyakamila` sebenarnya Fashion + Food + Lifestyle, tapi `category_id` cuma berisi
"Food" — dia tidak akan muncul saat orang mencari kreator Fashion.

Nama kategorinya sendiri diambil dari `kol_categories.taxonomy_key`, yang mengelompokkan
28 nama mentah jadi 9 kategori resmi.

### Tier: dihitung dari follower, bukan dibaca dari kolom tier

Ada tiga kandidat:

| Kandidat | Terisi | Putusan |
|---|---|---|
| **`kol_directory.followers_count`, dihitung saat query** ✅ | 97,1% | **Dipakai** |
| `l2_gold.kol_profile_card.tier` | 25,6% | Ditolak — cuma mencakup seperempat KOL, dan batasnya kedaluwarsa |
| **Tabel `public.kol_tiers`** ✅ | — | **Dipakai** — batasnya sudah diperbaiki, lihat di bawah |

Batas yang berlaku ditetapkan tim produk, dan **jumlah follower diambil dari
`kol_directory.followers_count`** — ini sudah disetujui. `kol_profile_card` bukan sumber
resmi untuk Followers maupun Tier.

**UPDATE 2026-09-07 — `kol_tiers` tidak lagi ditolak.** Alasan penolakannya (batas
kedaluwarsa) sudah hilang: migration 033 memperbaiki dua baris yang salah.

| Tier | Batas lama (salah) | Batas sekarang |
|---|---|---|
| Nano | 1.000 – 9.999 | sama |
| Micro | 10.000 – 49.999 | sama |
| **Mid-tier** | 50.000 – **99.999** | 50.000 – **499.999** |
| **Macro** | **100.000** – 999.999 | **500.000** – 999.999 |
| Mega | 1.000.000+ | sama |

Diperbaiki lewat `UPDATE`, bukan hapus-lalu-isi, karena `agency_kol_accounts.tier_id`
punya foreign key ke `kol_tiers.id`. Dampaknya **1.103 KOL pindah dari Macro ke Mid-Tier**.
Jumlah follower tetap dibaca dari `kol_directory.followers_count`; `kol_tiers` hanya
menyediakan ambangnya. Nama `Mid-tier` di database sengaja belum diganti jadi `Mid-Tier`
— itu perubahan tersendiri karena nilainya sudah tersimpan sebagai teks di L1/L2.

### Connected: OAuth token + platform user ID, bukan kolom `connected`

| Kandidat | Isi | Putusan |
|---|---|---|
| **`oauth_token` + `platform_user_id` terisi di baris yang sama** ✅ | 0 dari 7.496 | **Dipakai** — ini patokan dari mentor |
| `social_account.connected` | semuanya `false` | Ditolak sebagai patokan. Kolomnya boleh dicatat sebagai kolom yang ada, tapi bukan definisi resmi |
| `kol_directory.platform_user_id` | 930 terisi | Ditolak — itu hasil scraping, **bukan bukti** kreator menghubungkan akun |

Hari ini ketiganya kebetulan menghasilkan angka mirip (0), jadi bedanya belum kelihatan.
Justru itu alasan perlu ditulis sekarang: begitu ada yang mulai terisi, ketiganya akan berbeda.

---

## Sumber yang jangan dipakai

| Jangan | Alasan |
|---|---|
| `kol_directory.last_refreshed_at` sebagai penanda kapan data di-scrape | Terisi 97,1%, tapi **73,6% nilainya warisan impor Excel**, bukan jejak scraping. Kolomnya boleh dipakai, artinya yang tidak boleh dipercaya |

### UPDATE 2026-09-07 — `followers_growth` dikeluarkan dari daftar ini

Dulu dilarang dengan alasan *"bukan pertumbuhan 30 hari"*. Alasan itu **masih benar**:
jaraknya 10 hari (22 akun) dan 13 hari (3 akun), bukan 30.

Yang berubah adalah keputusan produk: angka itu **boleh dipakai sementara**, karena ia
satu-satunya sumber growth yang benar-benar terukur, dengan dua syarat:

1. **Tidak boleh dilabeli "Monthly" atau "30 hari".** Label yang dipakai:
   **"Sejak Snapshot Terakhir"**.
2. **Tidak boleh dibuatkan rumus baru.** Angkanya dibawa apa adanya dari
   `l1_silver.sp_build_unified_profile()`:
   `round((followers - followers_sebelumnya) / followers_sebelumnya * 100, 4)`.

Cakupannya kecil dan itu bukan bug: **25 dari 7.720** (0,32%). Growth butuh dua snapshot
profil, sedangkan 1.951 dari 1.976 akun ber-kartu baru di-scrape satu kali. Angka ini naik
sendiri begitu scraping jalan lagi.

`l2_gold.kol_metric_daily.followers_growth` **tetap tidak boleh dipakai** — kolomnya ada
tapi tidak pernah terisi (0 dari 280), dan memang tidak bisa: grain-nya tanggal tayang post,
sedangkan growth melekat pada pasangan snapshot profil.

---

## Rekap

| Keadaan | Jumlah |
|---|---:|
| Sumber pasti, data cukup | 5 |
| Sumber pasti, data masih tipis | 11 |
| Belum punya sumber | 15 |

**Lima filter yang bisa langsung dikerjakan:** Cari nama · Platform · Tier · Minimum follower · Kategori.

Sisanya menunggu salah satu dari tiga hal, dan **ketiganya pemiliknya berbeda**:
menambah data (engineering) · memutuskan aturan (produk) · mengisi tabel campaign
dan rate card (adopsi produk).

---

Struktur data untuk dikembangkan ada di **Task 5** (`KOL_DISCOVERY_TASK5_DESIGN.md`).
Semua angka dari pengecekan **read-only** — tidak ada data, tabel, atau kode yang diubah.
