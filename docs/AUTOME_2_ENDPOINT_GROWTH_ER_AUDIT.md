# AUTOME_2 — Audit Endpoint: Aliran Growth & ER dari L2 Gold ke UI

**Read-only · 8 September 2026 · tidak ada perubahan kode, scraping, migration, UPDATE, DELETE, maupun push**

Pertanyaan: apakah Growth/ER yang sudah ada di L2 Gold benar-benar mengalir ke endpoint dan dipakai UI?

| Repo | Kondisi saat audit |
|---|---|
| `scrapper-project` | `116243e` — bersih (7 dokumen audit untracked) |
| `D:/intern/autometric` (`engkol_v1`) | commit terakhir `19e2616` (1 Sep) — **9 file dimodifikasi, belum di-commit** |

---

> ## ⚠ Temuan pertama: pekerjaan Growth di repo app BELUM DI-COMMIT
>
> Seluruh dukungan Growth — parameter endpoint, kolom `growth_pct` di query, LATERAL ke `l2_gold.kol_profile_card`, preset filter di UI, kolom tabel, sort key — ada **hanya sebagai perubahan working tree**:
>
> ```
>  M src/app/api/organizations/[id]/discover/kol-directory/route.ts
>  M src/lib/discover/kolDirectory.ts          (+84/-…)
>  M src/lib/discover/kolGold.ts               (+13)
>  M src/components/discover/KolDirectoryFilters.tsx   (+79)
>  M src/components/discover/KolDirectoryPage.tsx      (+30)
>  M src/components/discover/KolCreatorSections.tsx    (+36)
>  M src/components/discover/KolCreatorWorkspace.tsx, KolCreatorReport.tsx, DiscoverCompare.tsx
> ```
>
> Commit terakhir (`19e2616`, 1 Sep) **tidak memuat Growth sama sekali** — di versi ter-commit, filter yang ada masih `verified=1`, bukan `connected=1`/`growthMin`/`growthMax`.
>
> Artinya: audit di bawah menggambarkan **working tree**, bukan kondisi yang tersimpan di git. Satu `git checkout` akan menghapus seluruhnya. **Ini risiko yang perlu ditangani lebih dulu, sebelum development apa pun.**

---

# 1. Endpoint yang relevan

| # | Endpoint | Peran | Growth | ER |
|---|---|---|---|---|
| 1 | `GET /api/organizations/[id]/discover/kol-directory` | List/Directory + filter + sort + facets | ✅ `growthPct` | ⚠ dari roster |
| 2 | `GET /api/organizations/[id]/discover/kol-directory/[kolId]` | Detail satu KOL | ✅ `gold.cards[].followersGrowth` | ✅ `gold.daily/monthly/posts[].erFollowers` **dan** ⚠ `creator.erPct` |
| 3 | `GET /api/organizations/[id]/discover/kol-directory/[kolId]/cover/[postId]` | Proxy gambar cover | — | — |

Endpoint lain di bawah `/discover` (`content`, `summary`, `directory`, `creators`, `assistant`, `rates`, `orders`, `inspirations`) melayani korpus brand/kompetitor atau entitas lain — **bukan roster KOL**, jadi di luar scope audit ini.

---

# 2. File yang relevan

| Lapisan | File | Isi |
|---|---|---|
| Route (list) | `src/app/api/organizations/[id]/discover/kol-directory/route.ts` | Parsing query param → `listKolDirectory()` |
| Route (detail) | `.../kol-directory/[kolId]/route.ts` | → `getKolCreator()` |
| Query layer | `src/lib/discover/kolDirectory.ts` (807 baris) | `BASE`, `filtered` CTE, `SORT_COLUMNS`, `listKolDirectory()`, `getKolCreator()` |
| Query layer L2 | `src/lib/discover/kolGold.ts` (667 baris) | `getKolGold()` — profile card, daily, monthly, audience, posts, formats |
| Query layer L1 | `src/lib/discover/kolMeasured.ts` | post & rate card dari L1 |
| Koneksi | `src/lib/kolDb.ts` | pool terpisah, kredensial `PG_*_KOL` |
| UI filter | `src/components/discover/KolDirectoryFilters.tsx` | `GROWTH_PRESETS`, mapping ke `growthMin`/`growthMax` |
| UI tabel | `src/components/discover/KolDirectoryPage.tsx` | kolom Growth, sort key, export CSV |
| UI detail | `src/components/discover/KolCreatorSections.tsx` | konsumsi `erFollowers` & `followersGrowth` |

---

# 3. Query database yang dipakai

## 3.1 Growth — **dari L2 Gold** ✅

`kolDirectory.ts` `BASE`:

```sql
g.followers_growth::float  AS growth_pct,
...
LEFT JOIN LATERAL (
  SELECT c.followers_growth
    FROM public.kol_social_account ksa
    JOIN l2_gold.kol_profile_card c ON c.social_account_id = ksa.social_account_id
   WHERE ksa.kol_id = kd.id
   ORDER BY c.followers_count DESC NULLS LAST
   LIMIT 1
) g ON TRUE
```

`LEFT JOIN LATERAL … LIMIT 1` dipilih tepat: baris roster tetap satu walau satu KOL punya lebih dari satu akun tertaut. Tidak ada risiko duplikasi baris.

## 3.2 ER — **dari roster, bukan L2** ⚠

```sql
kd.engagement_rate::float  AS er_pct
```

`public.kol_directory.engagement_rate` — sumber yang audit ER sebelumnya tandai sebagai paling lemah: tanpa aturan sampel, penyebut followers saat scrape, pembilang tanpa share, dan punya 7 nilai di atas 100% (maksimum 223,41%).

## 3.3 Detail — L2 dipakai penuh

`kolGold.ts` membaca `kol_profile_card`, `kol_metric_daily`, `kol_metric_monthly`, `post_metric`, `content_format_daily`, dan ketiga `audience_*_daily`.

---

# 4. Growth/ER: dari L2 Gold atau bukan?

| Field | Sumber sebenarnya | L2? |
|---|---|---|
| `growthPct` (list) | `l2_gold.kol_profile_card.followers_growth` | **✅ Ya** |
| `gold.cards[].followersGrowth` (detail) | idem | **✅ Ya** |
| `erPct` (list & detail `creator`) | `public.kol_directory.engagement_rate` | **❌ Tidak** |
| `gold.daily[].erFollowers` (detail) | `l2_gold.kol_metric_daily.er_followers_daily` | **✅ Ya** |
| `gold.monthly[].erFollowers` | `l2_gold.kol_metric_monthly` | **✅ Ya** |
| `gold.posts[].erFollowers` | `l2_gold.post_metric` | **✅ Ya** |
| `followers` | `kol_directory.followers_count` | ❌ roster |
| `tier` | `public.kol_tiers` (band atas roster) | ❌ roster |
| `lastRefreshedAt` | `kol_directory.last_refreshed_at` | ❌ roster |

## ⚠ Temuan: satu baris response mencampur dua sumber yang tidak rekonsiliasi

Terbukti pada trace §8. Untuk `pojoksatu.id`:

| Field di response | Nilai | Asal |
|---|---:|---|
| `followers` | **10.500.000** | roster |
| `growthPct` | **0,9174** | L2 — dihitung dari **10.900.000 → 11.000.000** |
| `erPct` | **0,01** | roster |
| ER di L2 (`er_followers_daily`) | **0,0221%** | L2 |
| `lastRefreshedAt` | **2023-08-16** | roster |
| `profile_snapshot_date` di L2 | **2026-08-24** | L2 |

Tiga masalah nyata:

1. **Growth tidak rekonsiliasi dengan follower yang ditampilkan.** UI menampilkan 10,5 juta follower dengan growth +0,9174%, padahal angka itu dihitung dari 10,9 juta → 11,0 juta. Pembaca tidak bisa memverifikasi sendiri.
2. **Dua nilai ER berbeda 2×** untuk kreator yang sama, dan yang ditampilkan di list adalah yang lebih lemah.
3. **`lastRefreshedAt` tertinggal 3 tahun** dari snapshot L2 yang menghasilkan growth-nya. Badge "Calculated"/"Live" ikut salah.

---

# 5. Field Growth yang dibutuhkan AUTOME_2 vs yang tersedia

## Yang tersedia di response

| Field | Ada? | Catatan |
|---|---|---|
| `growthPct` (persen, snapshot-ke-snapshot) | ✅ | Terdokumentasi jujur di komentar kode: *"never label it monthly or 30-day"* |
| `gold.cards[].followersGrowth` (detail) | ✅ | Sama, ditambahkan di working tree |
| `gold.cards[].snapshotDate` | ✅ | Tanggal snapshot terbaru |

## Yang MISSING untuk AUTOME_2

| Field diminta prototype | Ada di response? | Ada di DB? | Penghambat |
|---|---|---|---|
| **Growth 30D** (`((f_now/f_prev)^(30/days))−1`) | ❌ | ❌ | Perlu kalkulasi baru di L2 |
| **`days_between`** | ❌ | ❌ | `kol_profile_card` hanya punya `followers_growth` + `profile_snapshot_date` |
| **Tanggal snapshot sebelumnya** | ❌ | ❌ | Tidak disimpan di mana pun |
| **Growth classification** (exploding/rising/stable/declining) | ❌ | ❌ | Perlu threshold config + growth 30D |
| **`g7` / `g90`** | ❌ | ❌ | Butuh deret snapshot; 0 akun punya ≥3 |
| **Growth acceleration / stability** | ❌ | ❌ | Butuh ≥4 snapshot |
| **Momentum** | ❌ | ❌ | Butuh ≥3 snapshot; 0 akun punya |

Kolom yang benar-benar ada di `l2_gold.kol_profile_card` untuk growth — diperiksa langsung ke `information_schema`:

```
profile_snapshot_date   date
followers_growth        numeric
updated_at              timestamptz
```

**Tidak ada `days_between`, tidak ada `snapshot_prev_date`, tidak ada `growth_30d`.** Tanpa `days_between`, konsumen tidak bisa menilai apakah angkanya layak dipakai — persis rekomendasi P0-5 di `AUTOME_2_DEVELOPMENT_AUDIT.md`.

---

# 6. Filter Growth — sudah bekerja atau belum?

## ✅ Sudah bekerja, secara teknis benar

`route.ts`:
```ts
minGrowth: num('growthMin'),
maxGrowth: num('growthMax'),
```
`num()` menjaga param yang absen tetap absen — penting karena **0% adalah nilai nyata**, bukan "tanpa batas".

`kolDirectory.ts` `filtered` CTE:
```sql
AND ($12::float8 IS NULL OR b.growth_pct >= $12)
AND ($13::float8 IS NULL OR b.growth_pct <= $13)
```

Binding parameter diverifikasi: array `[q, platform, category, tiers, minErPct, connectedOnly, pageSize, offset, minFollowers, ids, maxRate, minGrowth, maxGrowth]` — `$12` dan `$13` memang `minGrowth`/`maxGrowth`. Tidak tertukar.

`sort=growth` juga sudah terdaftar di `SORT_COLUMNS` (`growth: 'growth_pct'`), dengan `NULLS LAST` di kedua arah.

## ⚠ Tapi hasilnya nyaris kosong — masalah data, bukan kode

Dijalankan langsung ke database dengan SQL yang sama persis:

| Skenario | KOL lolos |
|---|---:|
| Tanpa filter | 7.720 |
| `growthMin=0` | **18** |
| `growthMin=0.5` | **3** |
| `growthMin=4.5` (ambang *Rising* prototype) | **0** |
| `growthMin=8` (ambang *Exploding* prototype) | **0** |
| `growthMax=0` (declining) | **15** |

Cakupan `growth_pct` lewat jalur endpoint: **25 dari 7.720** (0,32%), rentang −0,0510% s.d. +0,9174%.

Begitu slider growth digeser sedikit pun, **99,7% roster hilang**.

## ✅ UI sudah dikalibrasi ke kenyataan, bukan ke prototype

`KolDirectoryFilters.tsx` `GROWTH_PRESETS`:

```ts
{ key: 'up',   label: 'Naik (> 0%)',   min: 0.0001, max: null },
{ key: 'flat', label: 'Datar (0%)',    min: 0,      max: 0    },
{ key: 'down', label: 'Turun (< 0%)',  min: null,   max: -0.0001 },
{ key: 'up05', label: 'Naik >= 0,5%',  min: 0.5,    max: null },
{ key: 'up1',  label: 'Naik >= 1%',    min: 1,      max: null },
```

Preset, bukan slider — dan ambangnya 0,5%/1%, bukan 4,5%/8% dari prototype. Komentarnya menyebut alasan yang tepat: *"0% growth is a real, common value"*. Keputusan ini sudah benar dan tidak perlu diubah.

## Filter ER — masih membaca sumber yang salah

`AND ($5::float8 IS NULL OR b.er_pct >= $5)` di mana `er_pct = kd.engagement_rate`. Filter berfungsi, tapi menyaring memakai nilai roster (1.756 terisi dari 7.720, maksimum 223,41%), bukan L2.

---

# 7. Ringkasan gap

## Filter yang sudah bekerja

| Filter | Param | Sumber | Catatan |
|---|---|---|---|
| Growth min/max | `growthMin`, `growthMax` | **L2 Gold** ✅ | Benar; datanya 25/7.720 |
| Sort growth | `sort=growth` | L2 Gold ✅ | `NULLS LAST` benar |
| Connected | `connected=1` | `social_account` | Benar; hasilnya 0 KOL |
| Platform, kategori, tier, follMin, maxRate, q, paging, facets, ids | — | roster | Berfungsi |

## Filter yang belum bekerja / belum ada

| Filter | Status |
|---|---|
| ER threshold | Ada param `minEr`, tapi membaca **roster**, bukan L2 |
| Growth classification (exploding/rising/stable/declining) | Tidak ada — butuh growth 30D + threshold config |
| Rising Creator | Tidak ada |
| 18 filter sidebar AUTOME_2 lainnya | Tidak ada (audiens, konten, performa, freshness) |

## Gap yang perlu development

| # | Gap | Dampak |
|---|---|---|
| **G1** | Pekerjaan Growth belum di-commit di repo app | **Risiko kehilangan seluruh pekerjaan** |
| **G2** | `growth_30d` + `days_between` tidak ada di L2 maupun response | AUTOME_2 minta Growth 30D; yang ada snapshot-ke-snapshot |
| **G3** | ER di list dari roster, bukan L2 | Dua nilai ER berbeda 2× dalam satu response |
| **G4** | `followers`, `lastRefreshedAt` dari roster sementara `growthPct` dari L2 | Angka tidak rekonsiliasi; growth 0,9174% "milik" follower yang tidak ditampilkan |
| **G5** | Growth classification belum ada | Butuh G2 + tabel/konstanta threshold |
| **G6** | Cakupan growth 25/7.720 | Bukan masalah endpoint — menunggu snapshot berkala |

---

# 8. Trace satu sample KOL

**`pojoksatu.id`** — TikTok, growth tertinggi di roster.
`kol_id = b5c58aa0…`, `social_account_id = 0a03ffa4…`

## [a] Sumber — `l1_silver.unified_profile` (snapshot yang membentuk growth)

| `date` | `followers_count` | `followers_growth` |
|---|---:|---:|
| 2026-08-14 | 10.900.000 | NULL |
| 2026-08-24 | 11.000.000 | **0,9174** |

`(11.000.000 − 10.900.000) / 10.900.000 × 100 = 0,9174%` — jarak **10 hari**, bukan 30.

## [b] L2 Gold — `l2_gold.kol_profile_card`

| `platform` | `username` | `followers_count` | `followers_growth` | `tier` | `profile_snapshot_date` |
|---|---|---:|---:|---|---|
| tiktok | pojoksatu.id | **11.000.000** | **0,9174** | Mega | **2026-08-24** |

## [c] L2 Gold — ER (`l2_gold.kol_metric_daily`)

| `metric_date` | `post_count` | `posts_in_sample` | `engagement_sum` | `followers_denom_sum` | `er_followers_daily` |
|---|---:|---:|---:|---:|---:|
| 2026-08-20 | 10 | 10 | 24.136 | 109.000.000 | **0,00022143** (= 0,0221%) |

## [d] Query endpoint (`BASE` + `WHERE id`)

| `followers` | `er_pct` | `tier` | `connected` | `status` | `growth_pct` | `last_refreshed_at` |
|---:|---:|---|---|---|---:|---|
| **10.500.000** | **0,01** | Mega | false | Calculated | **0,9174** | **2023-08-16** |

## [e] JSON response (`KolDirectoryRow`)

```json
{
  "id": "b5c58aa0-c1ee-40a4-9ba0-11befb331bd6",
  "username": "pojoksatu.id",
  "platform": "tiktok",
  "followers": 10500000,
  "erPct": 0.01,
  "tier": "Mega",
  "connected": false,
  "status": "Calculated",
  "growthPct": 0.9174,
  "lastRefreshedAt": "2023-08-16 04:19:47.635+00",
  "agency": null,
  "rateFrom": null,
  "rateCount": 0
}
```

## Yang terlihat dari trace ini

| Hal | Nilai |
|---|---|
| Growth **memang** mengalir L1 → L2 → endpoint → JSON | ✅ utuh, tanpa transformasi |
| Follower yang ditampilkan | 10,5 jt (roster) — **bukan** 11,0 jt yang dipakai menghitung growth |
| ER yang ditampilkan | 0,01% (roster) — L2 punya 0,0221%, **2,2× lebih besar** |
| `lastRefreshedAt` | 2023-08-16 — snapshot L2-nya 2026-08-24, **selisih 3 tahun** |
| `days_between` | Tidak ada di response; pembaca tidak tahu 0,9174% itu untuk 10 hari |

---

# 9. Rekomendasi perubahan minimum

**Belum dikerjakan. Menunggu approval.**

## Urutan yang saya sarankan

| # | Perubahan | File | Kenapa didahulukan |
|---|---|---|---|
| **R1** | **Commit dulu pekerjaan Growth yang ada di working tree repo app** | — (git) | 9 file WIP tanpa checkpoint. Ini bukan pengembangan, ini pengamanan. **Lakukan sebelum menyentuh apa pun** |
| **R2** | Kirim `days_between` + `snapshot_prev_date` bersama `growthPct` | `l2_gold.kol_profile_card` (kolom baru) → `kolGold.ts` → `kolDirectory.ts` | Tanpa itu "+0,9174%" tidak bisa dinilai. **Perubahan schema — butuh migration, jadi butuh approval terpisah** |
| **R3** | Rekonsiliasikan `followers` dengan sumber growth | `kolDirectory.ts` `BASE` | Ambil `followers` dari LATERAL `g` yang sama, atau kirim `followersAtSnapshot` sebagai field terpisah. **Tanpa migration** |
| **R4** | Pindahkan `erPct` list ke L2 | `kolDirectory.ts` `BASE` + `filtered` | ⚠ Konversi satuan **wajib**: L2 fraksi 0..1, UI mengirim `minEr` dalam poin persen. Tanpa `×100`, `minEr=3` mengembalikan 0 hasil. ⚠ Cakupan turun 1.756 → 22 |
| **R5** | Perbaiki `lastRefreshedAt` untuk baris ber-L2 | `kolDirectory.ts` | Pakai `profile_snapshot_date` kalau lebih baru |
| **R6** | `growth_30d` + threshold config | L2 + config | Menunggu snapshot ≥30 hari. **Belum ada gunanya sekarang** — 0 akun memenuhi |

## Yang TIDAK perlu diubah

| Komponen | Alasan |
|---|---|
| `GROWTH_PRESETS` di UI | Sudah dikalibrasi ke sebaran nyata (0,5%/1%), bukan ke placeholder prototype |
| Binding `$12`/`$13` | Sudah benar, sudah diverifikasi |
| `LEFT JOIN LATERAL … LIMIT 1` | Pola yang tepat; tidak menggandakan baris |
| `num()` di route | Sudah membedakan "absen" dari "0" — penting untuk growth |
| Label "sejak snapshot terakhir" di kolom tabel | Sudah jujur; jangan diganti jadi "/mo" |
| Detail endpoint | Sudah mengambil ER & growth dari L2 |

## Peringatan untuk R4

Memindahkan `erPct` ke L2 **hari ini** akan mengecilkan hasil filter `minEr` dari 219 KOL (pada `minEr=3`) menjadi **maksimum 22**, karena hanya 22 KOL punya ER di L2. Ini keputusan produk, bukan keputusan teknis — sama seperti yang sudah dicatat di `AUTOME_2_ER_AUDIT.md`.

---

*Read-only. Tidak ada perubahan kode, scraping, migration, UPDATE, DELETE, commit, maupun push di kedua repo. Seluruh angka diukur langsung ke database lewat sesi `set_session(readonly=True)`, memakai SQL yang disalin apa adanya dari `kolDirectory.ts`.*
