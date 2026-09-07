# Rencana Pengerjaan Backend — KOL Discovery

**Dasar:** Task 5 (`KOL_DISCOVERY_TASK5_DESIGN.md`) + hasil pengecekan database 2026-09-07
**Jumlah KOL:** 7.720
**Untuk:** developer yang mengerjakan filter KOL Discovery

> Ini rencana, bukan hasil kerja. Tidak ada kode, tabel, atau kolom yang dibuat di sini.
> Angka di bawah adalah kondisi database 2026-09-07 dan dipakai sebagai patokan saat testing.

> ## ⚠️ STATUS 2026-09-07 — sebagian rencana ini SUDAH DIKERJAKAN
>
> Baca ini dulu sebelum mengerjakan apa pun di bawah. **Empat instruksi di dokumen
> ini sekarang KEBALIKAN dari yang benar**, dan sudah dikoreksi di tempatnya
> masing-masing (ditandai **UPDATE 2026-09-07**):
>
> | Instruksi lama | Sekarang |
> |---|---|
> | "Jangan pakai tabel `kol_tiers`" | **Pakai** — batasnya sudah dibetulkan (migration 033) |
> | "Jangan pakai `kol_profile_card.followers_growth`" | **Pakai** untuk Growth (bukan 30 hari) |
> | Tahap 2: "526 KOL dikasih label `Unclassified`" | **JANGAN.** Produk memutuskan: tanpa tier, tanpa `Unclassified` |
> | "526 KOL menunggu keputusan produk" | **P-01 CLOSED** (migration 034) |
>
> Yang sudah selesai: Tier (ambang + P-01), Connected, Growth (kolom, sort, filter,
> CSV export), dan Growth di KOL Detail. Yang masih berlaku sebagai rencana: perluasan
> `search_kol_directory()`, `discovery.kol_filter_base`, "tiga jawaban", dan filter sisanya.

---

## 1. Bentuk API

Satu alamat, dipakai bersama oleh halaman Creator Database, My Creators, dan Smart Discovery.

```
GET /api/discovery/kol
```

| Parameter | Isi | Sudah final? |
|---|---|---|
| `q` | kata kunci — dicari di username, nama, bio | ✅ |
| `discovery_category[]` | 9 kategori resmi | ✅ |
| `tier[]` | Nano · Micro · Mid-Tier · Macro · Mega | ✅ |
| `format[]` | Reels · Carousel · Feed · Video | ✅ |
| `connected` | ya / tidak | ✅ |
| `platform[]` | instagram · tiktok | ✅ |
| `min_followers` | angka | ✅ |
| `include_unknown` | ikutkan KOL yang datanya belum ada (default: tidak) | ✅ |
| `limit` / `offset` | untuk halaman berikutnya | ✅ |

**Bentuk jawaban.** Satu baris = satu KOL. Jawaban wajib membawa tiga angka:

```json
{ "total_matched": 0, "total_unknown": 0, "total_population": 7720, "items": [] }
```

**Dua aturan yang tidak boleh dilanggar:**

1. Jangan mengubah "belum ada datanya" jadi "tidak cocok". Untuk kolom yang datanya
   di bawah 90%, `COALESCE(kolom, false)` **dilarang** — itu diam-diam mengubah arti.
2. Filter yang hasilnya selalu kosong (Connected, Tech, Story) tetap dikembalikan
   dengan keterangan, bukan dihilangkan diam-diam.

---

## 2. Data diambil dari mana

| Filter | Tabel · kolom | Terisi |
|---|---|---|
| **Kategori** | `kol_directory.category_ids` → `kol_categories.taxonomy_key` | 4.155 · 53,8% |
| **Tier** | `kol_directory.followers_count` — **sumber resmi (P-02 APPROVED/CLOSED)** | 7.498 · 97,1% |
| **Format konten** | `content_format_daily.media_type` (lewat tabel penghubung) | 30 · 0,39% |
| **Connected** | `social_account.oauth_token` + `social_account.platform_user_id` | 0 · 0% |
| Cari nama | `kol_directory.username`, `.bio`, `kol_profile_card.display_name` | 97,1% / 11,7% / 25,4% |
| Platform | `platforms.key` | 7.496 · 97,1% |

**Jangan dipakai:**

| Jangan | Alasan |
|---|---|
| `kol_directory.category_id` | Cuma menyimpan satu kategori — 1.183 KOL kehilangan kategori lainnya |
| ~~Tabel `kol_tiers`~~ | ~~Batasnya sudah kedaluwarsa~~ **UPDATE 2026-09-07: JUSTRU DIPAKAI.** Migration 033 membetulkan Mid-tier jadi 50rb–499.999 dan Macro jadi 500rb–999.999. Satu tabel ini dipakai bersama query Discovery dan `sp_build_unified_profile()`, jadi ambangnya tidak bisa lagi berbeda antara UI dan L1/L2 |
| Kolom `tier` di `kol_profile_card` | **Bukan sumber resmi** untuk Tier — cuma mencakup 1.976 KOL. Tetap berlaku |
| `kol_profile_card.followers_count` | **Bukan sumber resmi** untuk Followers. Sumbernya `kol_directory.followers_count`. Tetap berlaku |
| `social_account.connected` | Kolomnya ada, tapi **bukan** patokan resmi Connected |
| `kol_directory.platform_user_id` | Hasil scraping, **bukan bukti** kreator menghubungkan akun |
| ~~`kol_profile_card.followers_growth`~~ | ~~Bukan pertumbuhan 30 hari~~ **UPDATE 2026-09-07: DIPAKAI.** Masih benar bahwa ini bukan pertumbuhan 30 hari (jendelanya 10–13 hari), tapi produk menerimanya sementara. Dua syarat: **jangan** dilabeli "Monthly"/"30 hari" (label resmi: **"Sejak Snapshot Terakhir"**), dan **jangan** bikin rumus baru. Jalurnya `kol_directory → kol_social_account → kol_profile_card`, dan hanya kolom growth-nya yang diambil — Followers dan Tier tetap dari `kol_directory` |
| `l2_gold.kol_metric_daily.followers_growth` | **Tetap jangan.** Kolomnya ada tapi 0 dari 280 terisi, dan memang tidak bisa diisi: grainnya tanggal tayang post, bukan pasangan snapshot profil |

---

## 3. Cara menghitung tiap filter

### Kategori

```sql
-- menyaring
EXISTS (
  SELECT 1 FROM public.kol_categories c
  WHERE c.id = ANY(d.category_ids)
    AND c.taxonomy_key = ANY(:discovery_category)
)

-- menampilkan kategori tiap KOL
ARRAY(
  SELECT DISTINCT c.taxonomy_key FROM public.kol_categories c
  WHERE c.id = ANY(d.category_ids) AND c.taxonomy_key IS NOT NULL
  ORDER BY 1
)
```

9 nilai yang sah: `Lifestyle` `Beauty` `Fashion` `Food` `Fitness` `Entertainment` `Moms` `Gen Z` `Tech`.

19 KOL punya kategori yang belum dikelompokkan (Medical, Spirituality, dll) — mereka tetap
muncul di hasil tanpa filter kategori, jangan dibuang.

### Tier

```sql
CASE
  WHEN d.followers_count IS NULL   THEN NULL      -- 222 KOL, belum diputuskan
  WHEN d.followers_count <    1000 THEN NULL      -- 304 KOL, belum diputuskan
  WHEN d.followers_count <   10000 THEN 'Nano'
  WHEN d.followers_count <   50000 THEN 'Micro'
  WHEN d.followers_count <  500000 THEN 'Mid-Tier'
  WHEN d.followers_count < 1000000 THEN 'Macro'
  ELSE                                  'Mega'
END
```

Batas bawah ikut, batas atas tidak: follower 500.000 → Macro, 499.999 → Mid-Tier.
Angka batasnya taruh di config, jangan ditulis langsung di kode.

**UPDATE 2026-09-07 — dua baris `NULL` itu sudah final, boleh dikunci.**

**P-01 CLOSED.** Follower di bawah 1.000 dan follower kosong **tidak mendapat tier**
(`tier: null`). **Tidak** dibuatkan kelompok `Unclassified` maupun `Unknown`.
Sudah dijalankan lewat migration 034; L1 dan L2 ikut dibetulkan (54 KOL yang tadinya
`Nano` sekarang `null`).

Yang tetap jadi tanggung jawab tampilan: 526 KOL itu **harus tetap dihitung** sebagai
kelompok tanpa tier (`total_unknown`), jangan dibuang diam-diam dari hasil filter —
kalau tidak, jumlah hasil tidak akan pernah 7.720 dan tidak ada yang tahu kenapa.

### Format konten

```sql
-- terjemahkan lalu kumpulkan jadi daftar per KOL
ARRAY_AGG(DISTINCT CASE cfd.media_type
  WHEN 'clips'              THEN 'Reels'
  WHEN 'carousel_container' THEN 'Carousel'
  WHEN 'CAROUSEL'           THEN 'Carousel'
  WHEN 'feed'               THEN 'Feed'
  WHEN 'VIDEO'              THEN 'Video'
  ELSE NULL                 -- 'unknown' (3 KOL) dibiarkan
END) AS format_set

-- menyaring: "pernah memposting format ini"
format_set && :format
```

Story tidak ada sumbernya — jangan dibuatkan nilai.

### Connected

```sql
EXISTS (
  SELECT 1
  FROM public.kol_social_account ksa
  JOIN public.social_account sa ON sa.id = ksa.social_account_id
  WHERE ksa.kol_id = d.id
    AND sa.oauth_token      IS NOT NULL
    AND sa.platform_user_id IS NOT NULL
)
```

Tiga hal yang wajib dijaga:

1. **Kedua syarat dari baris `social_account` yang sama.** Jangan dicampur dengan
   `kol_directory.platform_user_id`.
2. **Jangan pakai `social_account.connected`** sebagai patokan.
3. **224 KOL tidak punya akun sosial sama sekali** — jawabannya *belum diketahui*,
   bukan *tidak terhubung*.

---

## 4. Yang harus disiapkan pihak lain

| Yang dibutuhkan | Status | Kalau tidak dipenuhi |
|---|---|---|
| **Proses connect harus mengisi `oauth_token` DAN `platform_user_id` di `social_account`** | ❌ **Belum ada** | **Connected akan selamanya 0.** Di repo ini tidak ada satu pun kode yang mengisi `social_account.platform_user_id`. Mengisi `oauth_token` saja **tidak cukup**. Proses connect ada di luar repo ini — perlu dikonfirmasi ke pemiliknya |
| Data konten diperluas dari 30 KOL | ❌ 0,39% | Filter Format jalan, tapi menyembunyikan 99,6% kreator |
| Kategori baru harus ikut dikelompokkan | ⚠️ 22 dari 28 | Kategori baru otomatis tidak terjangkau filter |
| `kol_directory.followers_count` tetap diperbarui pipeline | ⚠️ | Ini **sumber resmi** Followers dan Tier, jadi kalau berhenti diperbarui, seluruh filter Tier ikut basi |

---

## 5. Urutan pengerjaan

| Tahap | Isi | Butuh apa dulu |
|---|---|---|
| **1** | Perluas `db.search_kol_directory()` jadi query yang bisa menerima banyak parameter: kata kunci, platform, minimum follower, kategori, halaman. Plus bentuk jawaban di bagian 1 | — |
| **2** | ~~Tier — bikin `CASE` dengan batas dari config. 526 KOL dikasih label sementara `Unclassified` + catatan TODO~~ **SELESAI 2026-09-07.** Ambang dibetulkan di `public.kol_tiers` (033) dan dibaca lewat `LEFT JOIN`; 526 KOL **tanpa tier**, **tanpa** `Unclassified` (034) | Tahap 1 |
| **3** | Buat `discovery.kol_filter_base` — satu query tersimpan yang merapikan jalur tabel penghubung jadi satu baris per KOL | Tahap 1 |
| **4** | Format konten dan Connected, keduanya diambil dari tahap 3 | Tahap 3 |
| **5** | Terapkan "tiga jawaban" ke semua filter + tampilkan `total_unknown` | Tahap 1–4 |
| **6** | Filter sisanya (ER, gender, audiens, rasio postingan) | Di luar rencana ini |
| **⛔** | Data Status, Update Frequency, Next Update, Monitoring Priority | **Jangan dimulai** — jadwal update belum diputuskan |

**Tahap 3 harus sebelum tahap 4.** Kalau jalur tabel penghubung ditulis langsung di kode
aplikasi, definisinya akan cepat melenceng — itu **sudah pernah terjadi** pada filter Verified.

---

## 6. Daftar cek testing

Angka di bawah kondisi database 2026-09-07.

**Kategori**

- [ ] Tanpa filter → 7.720 baris
- [ ] Semua 9 kategori dipilih → **4.155** KOL (bukan 4.174)
- [ ] Per kategori: Lifestyle 2.592 · Beauty 1.271 · Moms 589 · Entertainment 501 · Gen Z 150 · Food 123 · Fashion 75 · Fitness 52 · Tech 4
- [ ] `tasyakamila` muncul di Fashion **dan** Food **dan** Lifestyle
- [ ] 19 KOL berkategori belum dikelompokkan tetap muncul saat filter kategori mati

**Tier**

- [ ] Nano 1.943 · Micro 2.942 · Mid-Tier 1.809 · Macro **187** · Mega 313
- [ ] Kelima tier + 304 + 222 = **7.720** (tidak ada KOL yang hilang)
- [ ] Macro **bukan** 1.290 dan **bukan** 1.123
- [ ] Follower 500.000 → Macro · 499.999 → Mid-Tier · 1.000.000 → Mega
- [ ] ~~Tidak ada query yang menyentuh tabel `kol_tiers`~~ → **dibalik:** query Discovery **memang** `LEFT JOIN public.kol_tiers`, dan ambangnya harus persis Nano 1.000–9.999 · Micro 10.000–49.999 · Mid-tier 50.000–499.999 · Macro 500.000–999.999 · Mega ≥1.000.000
- [ ] Follower 999 → tanpa tier · follower kosong → tanpa tier · **tidak ada** tier bernama `Unclassified`/`Unknown`

**Growth** *(baru — UPDATE 2026-09-07)*

- [ ] Tanpa filter → 7.720 baris, kolom Growth terisi **25**, sisanya `—`
- [ ] Naik 10 · Datar (tepat 0%) 8 · Turun 7
- [ ] Preset "Datar (0%)" mengirim `growthMin=0` **dan** `growthMax=0`, dan dihitung sebagai filter aktif — 0% bukan berarti "tanpa batas"
- [ ] Nilai di list = nilai di KOL Detail = `kol_profile_card.followers_growth`
- [ ] CSV export memuat kolom Growth sebagai **angka mentah**, bukan string berformat; NULL → kosong
- [ ] Tidak ada label "Monthly" atau "30 hari" di mana pun

**Connected** *(UPDATE 2026-09-07)*

- [ ] Connected = `social_account.platform_user_id IS NOT NULL AND oauth_token IS NOT NULL` → **0 KOL**, dan itu benar
- [ ] Tidak ada sisa `verifiedOnly` / `?verified=1` / label "Verified" yang dipakai sebagai Connected

**Format konten**

- [ ] Reels 18 · Carousel 16 · Feed 11 · Video 11
- [ ] `carousel_container` dan `CAROUSEL` sama-sama jadi Carousel
- [ ] 3 KOL ber-`unknown` tetap muncul saat filter format mati

**Connected**

- [ ] Hasilnya **0** KOL
- [ ] Query **tidak** menyentuh `social_account.connected`
- [ ] Query **tidak** menyentuh `kol_directory.platform_user_id`
- [ ] Kalau `oauth_token` terisi tapi `platform_user_id` kosong → **tidak** Connected
- [ ] 224 KOL tanpa akun sosial masuk hitungan `total_unknown`

**Tiga jawaban**

- [ ] `total_matched` dan `total_unknown` dilaporkan terpisah
- [ ] Tidak ada `COALESCE(..., false)` pada kolom yang datanya di bawah 90%

---

## 7. Yang masih menghambat

### Tidak bisa dikerjakan sekarang

| Hal | Kondisi |
|---|---|
| **Profiling Status** | Tidak ada nilai di database yang berarti "sedang diproses". Jangan dibuatkan mapping atau kolom baru |
| **Definisi "Ready"** | `scrape_status = success` cuma 27 KOL — menyembunyikan 99,6% direktori |
| **Proses connect** | Tidak ada kode yang mengisi `social_account.platform_user_id` |

### Menunggu keputusan produk

**Kosong — tidak ada lagi yang menunggu keputusan produk untuk filter di dokumen ini.**

| Hal | Kondisi | Putusan |
|---|---|---|
| ~~526 KOL di luar tier~~ | 304 follower di bawah 1.000 + 222 tanpa data = 6,8% | **P-01 CLOSED 2026-09-07** — tanpa tier, **tanpa** `Unclassified`. Tetap dihitung di `total_unknown` |

### Sudah diputuskan

| Hal | Keputusan |
|---|---|
| **P-02 — Sumber jumlah follower & Tier** | **APPROVED / CLOSED.** Followers dan Tier sama-sama diambil dari **`kol_directory.followers_count`**. `l2_gold.kol_profile_card` **bukan** sumber resmi untuk Followers maupun Tier |

### Sengaja ditunda

| Hal | Alasan |
|---|---|
| Jadwal update per KOL | Belum ada aturannya. Jawabannya menentukan perlu tidaknya kolom baru. Empat filter ikut ditunda |
| Batas Growth & Rising | Belum ada data pertumbuhan 30 hari yang nyata |

### Data yang masih tipis

| Sumber | Terisi | Filter yang terdampak |
|---|---|---|
| Data konten | 30 · 0,39% | 10 filter |
| Data audiens | 23 · 0,30% | 5 filter |
| `last_refreshed_at` | 97,1% tapi 73,6% bukan jejak scraping | 4 filter |
| Kota kreator | 0% | 1 filter |
| Campaign & rate card | 18 tabel, hampir semua kosong | 7 filter |

### Masih terbuka

- Chip yang selalu kosong (Connected, Tech, Story, YouTube) — disembunyikan atau diberi keterangan?
- 277 username kembar — dibersihkan atau disaring saat query? Memengaruhi semua angka di bagian 6.
