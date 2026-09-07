# Task 4 — Sumber Data yang Dipakai Tiap Filter

**Tugas:** untuk tiap kebutuhan filter, tentukan **satu** sumber yang dipakai.
Kalau ada beberapa kandidat, pilih satu dan tulis alasannya.

**Dasar:** Task 2 (apa yang ada di database) dan Task 3 (seberapa lengkap isinya).
**Terakhir diperbarui:** 2026-09-07 · **Jumlah KOL:** 7.720

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
| **Cari nama** | `kol_directory.username` + `.bio`, digabung `kol_profile_card.display_name` | 97,1% · 11,7% · 25,4% | Tiga kolom digabung supaya hasil pencarian selengkap mungkin |
| **Platform** | `platforms.key` | 97,1% | Satu-satunya sumber platform |
| **Tier** | `kol_directory.followers_count`, **dihitung saat query** | 97,1% | Lihat penjelasan di bawah |
| **Minimum follower** | `kol_directory.followers_count` | 97,1% | Sumber yang sama dengan Tier |
| **Kategori** | `kol_directory.category_ids` → `kol_categories.taxonomy_key` | 53,8% | Lihat penjelasan di bawah |

### Filter yang sumbernya pasti tapi datanya masih tipis

Sumbernya sudah tidak perlu diperdebatkan. Yang kurang cuma jumlah barisnya.

| Filter | Sumber yang dipakai | Terisi |
|---|---|---|
| Engagement rate | `kol_directory.engagement_rate` | 1.756 · 22,7% |
| Format konten | `content_format_daily.media_type` | 30 · 0,39% |
| Views | `post_metric.views` | 30 · 0,39% |
| Rasio konten berbayar | `post_metric.is_sponsored` | 30 · 0,39% |
| Save rate / Share rate | `post_metric.saves` / `.shares` | 11 · 0,14% (TikTok saja) |
| Gender audiens | `audience_demographics_daily` | 23 · 0,30% |
| Lokasi audiens | `audience_geo_daily` (kota) | 15 · 0,19% |
| Minat audiens | `audience_interest_daily` | 23 · 0,30% |
| Kualitas audiens | `feature.ig_audience_analysis` + `tt_audience_analysis` | 23 · 0,30% |
| **Connected** | `social_account.oauth_token` + `social_account.platform_user_id` | 0 · 0% |
| Verified | `kol_directory.verified_status` | 931 · 12,1% |

### Filter yang belum punya sumber

| Filter | Kondisi | Yang dibutuhkan |
|---|---|---|
| Profiling Status | Tidak ada nilai apa pun di database yang berarti "sedang diproses" | Keputusan produk + perubahan pipeline |
| Kota kreator | `creator_city` kosong 100% | Diisi saat pendaftaran |
| Umur audiens | Barisnya tidak pernah ditulis pipeline | Perluas analisis audiens |
| Growth 30 hari | Belum ada akun yang punya 2 data berjarak 30 hari | Menunggu waktu |
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
| Tabel `public.kol_tiers` | — | Ditolak — batasnya kedaluwarsa (Macro 100rb–1jt) |

Batas yang berlaku ditetapkan tim produk, dan **jumlah follower diambil dari
`kol_directory.followers_count`** — ini sudah disetujui. `kol_profile_card` bukan sumber
resmi untuk Followers maupun Tier.

### Connected: OAuth token + platform user ID, bukan kolom `connected`

| Kandidat | Isi | Putusan |
|---|---|---|
| **`oauth_token` + `platform_user_id` terisi di baris yang sama** ✅ | 0 dari 7.496 | **Dipakai** — ini patokan dari mentor |
| `social_account.connected` | semuanya `false` | Ditolak sebagai patokan. Kolomnya boleh dicatat sebagai kolom yang ada, tapi bukan definisi resmi |
| `kol_directory.platform_user_id` | 930 terisi | Ditolak — itu hasil scraping, **bukan bukti** kreator menghubungkan akun |

Hari ini ketiganya kebetulan menghasilkan angka mirip (0), jadi bedanya belum kelihatan.
Justru itu alasan perlu ditulis sekarang: begitu ada yang mulai terisi, ketiganya akan berbeda.

---

## Dua sumber yang jangan dipakai

| Jangan | Alasan |
|---|---|
| `kol_profile_card.followers_growth` | **Bukan** pertumbuhan 30 hari. Isinya selisih antara dua data terakhir, jaraknya bisa berapa saja — sekarang nyatanya 10 hari (22 akun) dan 13 hari (3 akun) |
| `kol_directory.last_refreshed_at` sebagai penanda kapan data di-scrape | Terisi 97,1%, tapi **73,6% nilainya warisan impor Excel**, bukan jejak scraping. Kolomnya boleh dipakai, artinya yang tidak boleh dipercaya |

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
