# Handoff ke Backend Developer — KOL Discovery Filter

**Dari:** tim data (audit & data requirement)
**Untuk:** backend developer yang mengerjakan filter KOL Discovery
**Tanggal:** 2026-09-07 · **Jumlah KOL:** 7.720 (`public.kol_directory`)

> **Batas dokumen ini.** Berisi kebutuhan data dan hasil audit, **bukan** kode.
> Tidak ada framework API yang dipilih, tidak ada implementasi yang dibuat, tidak ada
> perubahan database. Semua angka hasil query **read-only** ke DB live 2026-09-07.

**Dokumen pendukung:** `KOL_DISCOVERY_TASK5_DESIGN.md` (struktur data lengkap) ·
`KOL_DISCOVERY_BACKEND_IMPLEMENTATION_PLAN.md` (SQL detail + daftar cek testing).
Dokumen ini merangkum dan menambahkan **hasil audit repo** serta **hal yang perlu dikoordinasikan**.

---

## 1. Yang diminta

Filter KOL Discovery supaya bisa dipakai UI. **Empat filter sudah final dan boleh dikerjakan:**

| Filter | Status |
|---|---|
| Kategori | ✅ final |
| Tier / Follower | ✅ final |
| Format konten | ✅ final |
| Connected | ✅ final |

Ditambah tiga yang sudah jelas sumbernya: Cari nama · Platform · Minimum follower.

**Yang belum boleh dikerjakan:** Profiling Status (tidak ada datanya), dan semua filter
jadwal update (Data Status, Update Frequency, Next Update, Monitoring Priority).

---

## 2. Sumber data per filter

| Filter | Tabel · kolom | Terisi |
|---|---|---|
| Cari nama | `kol_directory.username` + `.bio` + `l2_gold.kol_profile_card.display_name` | 97,1% · 11,7% · 25,4% |
| Platform | `platforms.key` ← `kol_directory.platform_id` | 7.496 · 97,1% |
| **Kategori** | `kol_directory.category_ids` → `kol_categories.taxonomy_key` | **4.155 · 53,82%** |
| **Tier / Min follower** | `kol_directory.followers_count` | 7.498 · 97,1% |
| **Format konten** | `l2_gold.content_format_daily.media_type` | **30 · 0,39%** |
| **Connected** | `social_account.oauth_token` + `social_account.platform_user_id` | **0 · 0%** |

### Jalur tabel

```
Filter sederhana:
  public.kol_directory                                    (7.720 baris)

Filter yang butuh data detail:
  kol_directory → kol_social_account → social_account → tabel L2
     (KOL)         (tabel penghubung)   (akun IG/TikTok)
```

Jalur bertiga ini menjangkau **7.496 dari 7.720 KOL**. **224 KOL tidak punya akun sosial
sama sekali** — untuk mereka semua filter yang lewat jalur ini jawabannya *belum diketahui*.

---

## 3. Logic filter

### Kategori

```sql
EXISTS (
  SELECT 1 FROM public.kol_categories c
  WHERE c.id = ANY(d.category_ids)
    AND c.taxonomy_key = ANY(:discovery_category)
)
```

9 nilai sah: `Lifestyle` `Beauty` `Fashion` `Food` `Fitness` `Entertainment` `Moms` `Gen Z` `Tech`

- **Wajib pakai `category_ids` (array), jangan `category_id` (skalar).** 1.183 KOL punya lebih
  dari satu kategori; kolom skalar cuma menyimpan salah satunya secara acak.
- 19 KOL punya kategori yang belum dikelompokkan (Medical, Spirituality, dll) — tetap muncul
  saat filter kategori mati, jangan dibuang.

### Tier

```sql
-- Sejak migration 033 ambang ini identik dengan public.kol_tiers, jadi
-- LEFT JOIN ke kol_tiers menghasilkan jawaban yang sama dan itu yang
-- dipakai Discovery. Migration 034 membuat L1/L2 ikut sama (P-01).
CASE
  WHEN d.followers_count IS NULL   THEN NULL      -- 222 KOL  → lihat P-01
  WHEN d.followers_count <    1000 THEN NULL      -- 304 KOL  → lihat P-01
  WHEN d.followers_count <   10000 THEN 'Nano'
  WHEN d.followers_count <   50000 THEN 'Micro'
  WHEN d.followers_count <  500000 THEN 'Mid-Tier'
  WHEN d.followers_count < 1000000 THEN 'Macro'
  ELSE                                  'Mega'
END
```

Batas bawah ikut, batas atas tidak: follower 500.000 → Macro, 499.999 → Mid-Tier.
Angka batas taruh di config, jangan ditulis langsung di kode.

### Format konten

```sql
clips              → 'Reels'
carousel_container → 'Carousel'
CAROUSEL           → 'Carousel'
feed               → 'Feed'
VIDEO              → 'Video'
unknown            → tidak dipetakan (3 KOL), jangan dibuang
```

Hasilnya **daftar per KOL** (`format_set`), bukan satu nilai. Artinya "pernah memposting
format ini". Story tidak ada sumbernya — jangan dibuatkan nilai.

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

**Kedua syarat harus dari baris `social_account` yang sama.**

---

## 4. Bentuk jawaban yang dibutuhkan UI

Satu baris = satu KOL. Jawaban wajib membawa tiga angka terpisah:

```
total_matched      → jumlah KOL yang cocok
total_unknown      → jumlah KOL yang datanya belum ada
total_population   → 7.720
```

**Kenapa wajib:** 22 dari 40 filter datanya di bawah 90%. Tanpa `total_unknown`, pengguna
akan menyimpulkan "tidak ada kreator yang cocok" padahal yang benar "kami belum tahu".

Perlu ada parameter untuk mengikutkan data yang belum diketahui (default: tidak diikutkan).

**Aturan keras:** `COALESCE(kolom, false)` **dilarang** untuk kolom yang datanya di bawah 90%.
Itu diam-diam mengubah "belum diketahui" jadi "tidak cocok".

---

## 5. Hasil audit repo — yang sudah ada dan bisa dipakai ulang

Repo `scrapper-project` sudah punya beberapa hal. **Jangan dibuat ulang.**

| Yang sudah ada | Lokasi | Catatan |
|---|---|---|
| **Query pencarian KOL** | `db.search_kol_directory()` (`db.py:273`) | Sudah benar memakai `category_ids` + `taxonomy_key` lewat `EXISTS`. Sudah ada peringkat hasil, escaping wildcard LIKE, limit/offset |
| **SQL yang sudah dioptimasi** | `db._SEARCH_QUERY` (`db.py:236`) | Pakai hash join, bukan LATERAL — 11 ms vs 2.080 ms. **Pertahankan polanya** |
| Bentuk hasil | `db.SearchResult` | 6 field; perlu ditambah `tier`, `is_connected`, `format_set` |
| CLI penguji | `search_kol.py` | Read-only, berguna untuk verifikasi |
| Koneksi & config | `db.open_connection()`, `config.py` | Tempat yang wajar untuk menaruh batas Tier |

**Yang belum ada:** filter Tier, Platform, Minimum follower, Format, Connected · kategori
multi-pilih (sekarang cuma terima 1 nilai) · ketiga hitungan di bagian 4 · dan **framework API
apa pun** (`requirements.txt` cuma berisi `apify-client`, `psycopg2-binary`, `python-dotenv`).

---

## 6. Dependency pipeline

### Sudah tersedia — tidak perlu pipeline baru

| Data | Diisi oleh | Perlu diubah? |
|---|---|---|
| `followers_count` | `db.update_profiles()` ← pipeline scraping | ❌ Tidak — ikut ter-refresh tiap scrape |
| `username` · `bio` · `verified_status` | sama | ❌ Tidak |
| `display_name` | Dagster asset `kol_profile_card` | ❌ Tidak |
| Format konten | Dagster asset `content_format_daily` | ❌ Tidak — sudah idempoten |
| Views · Save · Share | Dagster asset `post_metric` | ❌ Tidak |
| Data audiens | Dagster asset `audience_feature` + `audience_gold` | ❌ Tidak |

**Untuk keempat filter final, tidak ada pipeline baru yang perlu dibuat dan tidak perlu
scraping ulang.** Rantai L0 → L1 → L2 sudah lengkap dan berjalan.

### Belum tersedia — perlu koordinasi, bukan scraping

| Data | Kondisi | Yang dibutuhkan |
|---|---|---|
| **`social_account.platform_user_id`** | 0 dari 7.496 | **Tidak ada satu pun kode di repo ini yang menulisnya.** Yang ada hanya penulis `kol_directory.platform_user_id` (`db.py:389`). Selama connect flow tidak mengisi kolom ini, **Connected akan tetap 0 walaupun OAuth sudah jalan** |
| **`kol_directory.category_ids`** | 4.174 terisi | **Tidak ada kode di repo ini yang menulisnya** — berasal dari impor roster awal. KOL baru berisiko selamanya tanpa kategori |
| Cakupan format & audiens | 30 dan 23 KOL | Pipeline-nya sudah benar, cuma perlu dijalankan untuk lebih banyak akun. **Bukan pipeline baru** |

---

## 7. Gap coverage — apa yang akan terjadi saat filter dinyalakan

Ini yang paling penting dipahami sebelum menulis kode: **filternya akan benar, hasilnya yang kosong.**

| Filter | Maksimal hasil | Sisanya |
|---|---:|---|
| Cari nama · Platform · Tier | ~7.500 | wajar |
| Kategori | **4.155** | 3.565 belum ada datanya |
| Format konten | **30** | 7.690 belum ada datanya |
| **Connected** | **0** | 7.720 belum ada datanya |
| **Growth** | **25** | 1.951 KOL baru punya satu snapshot → growth NULL; 5.744 belum punya kartu L2 |

Chip **Connected** akan selalu mengembalikan hasil kosong sampai ada kreator yang benar-benar
menghubungkan akun. Ini bukan bug. Sejak 2026-09-07 Discovery memakai definisi bisnis
(`social_account.platform_user_id IS NOT NULL AND social_account.oauth_token IS NOT NULL`);
badge verified platform sudah **tidak lagi** ditampilkan di Discovery.

Filter **Growth** juga hampir kosong dengan alasan berbeda: growth butuh DUA snapshot profil,
dan 1.951 dari 1.976 akun ber-kartu baru di-scrape sekali. Angkanya akan naik sendiri seiring
scraping berjalan — tidak ada yang perlu diperbaiki di kode.

---

## 8. Aturan yang tidak boleh dilanggar

| Jangan pakai | Alasan |
|---|---|
| `kol_directory.category_id` (skalar) | 1.183 KOL kehilangan kategori ke-2/ke-3 |
| `l2_gold.kol_profile_card` sebagai sumber Followers/Tier | Sudah diputuskan bukan sumber resmi. Cuma mencakup 25,6% KOL. **Tetap berlaku** — tapi lihat catatan Growth di bawah: kartu ini SATU-SATUNYA sumber `followers_growth` |
| ~~Tabel `public.kol_tiers`~~ | ~~Batasnya kedaluwarsa (Macro 100rb–1jt)~~ **SUDAH DIPERBAIKI** oleh migration 033 (2026-09-07). Mid-tier kini 50rb–499.999, Macro 500rb–999.999. `kol_tiers` sekarang **boleh dan harus** dipakai |
| ~~Kolom `tier` di `kol_profile_card`~~ | ~~Sama, batas kedaluwarsa~~ **SUDAH DIPERBAIKI**. Sumber resmi Followers/Tier Discovery tetap `kol_directory.followers_count` |
| `social_account.connected` | Kolomnya ada, tapi **bukan** patokan resmi Connected |
| `kol_directory.platform_user_id` untuk Connected | Itu hasil scraping, bukan bukti kreator menghubungkan akun |
| ~~`kol_profile_card.followers_growth`~~ | ~~Bukan pertumbuhan 30 hari~~ **LARANGAN DICABUT** (keputusan produk 2026-09-07). Benar bahwa ini BUKAN pertumbuhan 30 hari — jendelanya 10–13 hari, yaitu jarak antar snapshot scrape. Produk menerima itu untuk sementara, dengan syarat **tidak pernah dilabeli "Monthly" atau "30 hari"**; label yang dipakai: "Sejak Snapshot Terakhir". Ini satu-satunya sumber Growth yang terukur, dan Discovery memakainya lewat `kol_directory → kol_social_account → kol_profile_card` |

Ditambah: **jangan membuat keputusan produk baru**, dan **jangan mengubah database supaya
prototype terlihat selesai**.

---

## 9. Yang perlu ditanyakan / dikoordinasikan

Diurutkan dari yang paling memblokir.

| # | Hal | Tanya ke siapa | Kenapa perlu |
|---|---|---|---|
| 1 | **Endpoint ini dibuat di repo mana?** Repo `scrapper-project` ini isinya pipeline scraping dan sama sekali belum punya framework API. Aplikasinya sendiri kelihatannya TypeScript (`kolDirectory.ts`, `KolDirectoryFilters.tsx`) | Backend lead / arsitek | Menentukan apakah repo ini cukup menyediakan query layer saja, atau endpoint memang dibuat di sini |
| 2 | ~~**P-01 — 526 KOL di luar tier.**~~ **SELESAI 2026-09-07.** Keputusan produk: `<1K` dan `NULL` **tidak mendapat tier** (`tier: null`), dan **tidak** dibuatkan kelompok `Unclassified`/`Unknown`. Migration 034 membuang fallback yang sebelumnya menjatuhkan 54 akun `<1K` ke `Nano` di L1/L2. Populasi 526 tetap dihitung terpisah oleh pemakai data | — | — |
| 3 | **Connect flow mengisi `social_account.platform_user_id` atau tidak?** | Pemilik OAuth / connect flow (di luar repo ini) | Kalau tidak, Connected akan selamanya 0 meski OAuth sudah jalan |
| 4 | **Siapa mengisi `category_ids` untuk KOL baru?** | Pemilik data / admin | Sekarang tidak ada jalur otomatis. KOL baru berisiko tidak berkategori |
| 5 | **Chip yang hasilnya selalu kosong** (Connected, Tech 4 KOL, Story, YouTube) | Product / design | Disembunyikan, atau ditampilkan dengan keterangan "belum ada datanya"? |
| 6 | **277 username kembar** | Pemilik data | Dibersihkan di data, atau disaring saat query? Memengaruhi **semua** angka hasil filter |
| 7 | **Jadwal update per KOL** | Product | Masih DEFERRED. Empat filter bergantung padanya. Jangan dipaksakan |

---

## 10. Dua catatan teknis

**Belum perlu bikin VIEW.** Task 5 menyebut `discovery.kol_filter_base` sebagai tempat
mengumpulkan data yang lewat tabel penghubung. Menurut audit, untuk tahap sekarang query
layer masih bisa jalan tanpa objek database baru. Saran: **tunda sampai filter Format dan
Connected benar-benar dipakai bersamaan**, supaya tidak menambah perubahan DB yang belum
terbukti perlu.

**`kol_social_account` tidak punya indeks di `kol_id`** — hanya primary key di `id`.
Ini yang membuat LATERAL join 185× lebih lambat (tercatat di komentar `db.py:224`).
Query yang ada sekarang menghindarinya dengan hash join, jadi **belum jadi masalah**.
Kalau nanti filter Connected/Format terasa lambat, ukur dulu, baru ajukan indeks.

---

## 11. Cara memverifikasi hasil

Angka patokan dari DB 2026-09-07. Daftar cek lengkap ada di
`KOL_DISCOVERY_BACKEND_IMPLEMENTATION_PLAN.md` bagian 6.

| Yang dicek | Hasil yang benar |
|---|---|
| Tanpa filter | 7.720 |
| Semua 9 kategori | **4.155** (bukan 4.174) |
| Per kategori | Lifestyle 2.592 · Beauty 1.271 · Moms 589 · Entertainment 501 · Gen Z 150 · Food 123 · Fashion 75 · Fitness 52 · Tech 4 |
| Tier | Nano 1.943 · Micro 2.942 · Mid-Tier 1.809 · Macro **187** · Mega 313 |
| Tier + 304 + 222 | = 7.720 (tidak ada KOL yang hilang) |
| Format | Reels 18 · Carousel 16 · Feed 11 · Video 11 |
| Connected | **0** |

Tiga uji yang paling mudah terlewat:

- `tasyakamila` harus muncul di Fashion **dan** Food **dan** Lifestyle — kalau cuma muncul
  di satu, berarti masih memakai `category_id` skalar
- Macro harus **bukan** 1.290 dan **bukan** 1.123 — dua angka itu dari batas tier lama
- KOL dengan `oauth_token` terisi tapi `platform_user_id` kosong → **tidak** Connected
