# DATA AUDIT — Brand Dummy · Taksonomi KOL · Brand Fit · CPE/CPV

**Peran:** Data (audit & validasi), bukan Backend.
**Tanggal audit:** 2026-09-15
**Source of truth KOL:** DB `kol` @ `10.100.14.216:5432` (TSDB **tidak** dipakai).
**Perubahan yang dilakukan:** **NOL.** Tidak ada kode, migration, ALTER, DML,
perubahan taxonomy DB, perubahan Brand Fit engine, commit, maupun push.
Dokumen ini satu-satunya artefak baru.

---

## 0. BUKTI SESI DB

Seluruh angka DB di dokumen ini **dibaca langsung hari ini** lewat sesi
read-only. Bukan kutipan dokumen lama, bukan tebakan.

```
SELECT inet_server_addr(), inet_server_port(), current_database(),
       current_user, current_setting('transaction_read_only'), version(), now()

host       = 10.100.14.216/32
port       = 5432
db         = kol
usr        = postgres
read_only  = on                 <- sesi dikunci read-only
version    = PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)
ts         = 2026-09-15 05:05:37 UTC
```

Akses lewat VPN Pritunl (`SourceAddress 10.100.16.102`). Label yang dipakai:

| Label | Arti |
|---|---|
| **[DB-LIVE]** | `SELECT` dijalankan 2026-09-15 05:05 UTC ke DB `kol`. |
| **[EXCEL]** | Dihitung ulang hari ini dari file Excel. |

> ### ⚠️ KOREKSI TERHADAP DOKUMEN LAMA
>
> Audit sebelumnya (`KOL_DB_VERIFICATION_TAHAP0.md` 2026-09-13,
> `KOL_BRAND_FIT_HOLD.md`, dan `brand_dummy.xlsx` evidence Q02) menyatakan sisi
> brand nyaris tidak punya kolom. **Itu sudah kedaluwarsa.**
>
> `public.brand_profile` sekarang punya **29 kolom**, dan **seluruh 11 field
> sisi brand yang dibutuhkan Brand Fit ADA** — termasuk `brand_tone`,
> `target_age_min`, `target_age_max`, `audience_interests`, dan
> `performance_targets`. Empat kolom terakhir berada di ordinal position 26–29,
> artinya **ditambahkan belakangan lewat `ALTER TABLE ADD COLUMN`** — sesudah
> POC `brand_dummy` dijalankan. Itu sebabnya Q02 hanya melihat 11 kolom.
>
> Konsekuensinya besar: **blocker sisi brand bergeser dari "tidak ada kolom"
> menjadi "kolomnya ada tapi 0 baris".** Itu masalah yang jauh lebih kecil.

---

# A. BRAND DUMMY

## A.1 Temuan struktural paling penting

**`docs/brand_dummy.xlsx` BUKAN dataset brand dummy. Ia adalah LAPORAN POC.**

Ke-13 sheet-nya berisi narasi, status, dan hasil sebuah POC Brand Fit yang sudah
dijalankan orang lain. Sumber data brand yang sebenarnya dinyatakan di dalamnya:

> Sheet `Source & Evidence` B18–B23:
> `Brand_Fit_Dummy_Data.xlsx` → `Complete Brand Taxonomy!A2:L2..L5`,
> `Brand Fit Scores!A2:H49`, `Dummy Creators!A2:F13`

**`Brand_Fit_Dummy_Data.xlsx` TIDAK ADA di repo ini.** Dicari di seluruh
project (`find . -iname "*.xlsx"`, 8 file, `venv` di-exclude) — nol hit.

| Yang bisa diaudit | Yang tidak bisa |
|---|---|
| 4 brand dummy (ringkasannya disalin ke sheet `Dummy Brand Input`) | 12 dummy creator (`Dummy Creators!A2:F13`) |
| Kosakata kategori, personality, tone, archetype, target demografi | 48 baris control run (`Brand Fit Scores!A2:H49`) — dasar klaim "48/48 REPRODUCED" |
| 10 real creator sample + 40 kombinasi hasil | 12 kolom penuh `Complete Brand Taxonomy` (workbook hanya mengekspos 8) |

> **Untuk Backend:** minta `Brand_Fit_Dummy_Data.xlsx` ke pembuat POC. Tanpa
> file itu, 48 baris control run — satu-satunya bukti bahwa formula Values
> Alignment benar — tidak bisa diverifikasi ulang oleh siapa pun.

*Catatan operasional:* ada `docs/~$brand_dummy.xlsx` — file lock Excel. Jangan
di-commit.

## A.2 Audit per sheet **[EXCEL]**

Semua sheet punya 2 baris banner (judul + disclaimer "POC ONLY") dan 1 baris
penjelas. "Data rows" = baris isi sesungguhnya.

| # | Sheet | Rows | Cols | Data rows | Kolom | Arti / fungsi | Dipakai Brand Fit? |
|---:|---|---:|---:|---:|---|---|---|
| 1 | `Executive Summary` | 20 | 4 | 6 + 4 | Pertanyaan, Jawaban, Status, (Kenapa) | Ringkasan vonis POC + coverage 4 komponen | ❌ narasi |
| 2 | `POC Methodology` | 28 | 4 | 8 + 5 + 3 | Bagian, Sumber, Perlakuan, Status | Titik injeksi resolver + **aturan workbook dummy** (r17–21) | ✅ **aturan skoring** |
| 3 | `Dummy Brand Input` | 30 | 9 | **4 brand** | Brand, Kategori Bisnis, Size Tier, Performance Archetype, Target Demografi, Brand Personality, Brand Tone, # Atribut, Sumber | **Satu-satunya data sisi brand** | ✅ **INTI** |
| 4 | `Real Creator Sample` | 17 | 13 | **10 creator** | Creator ID, Username, Followers, ER %, Kota, Kategori (taxonomy_key), Audience gender/age/geo/interest, Personality/tone, Performance metrics, Archetype | Sample creator nyata dari DB | ✅ **INTI** |
| 5 | `Category Fit` | 24 | 3 | 4 + 9 + 6 | Kosakata BRAND, Kosakata CREATOR | Perbandingan dua kosakata kategori | ✅ diagnostik |
| 6 | `Audience Fit` | 24 | 7 | 4 + **10** | Dimensi, Sisi CREATOR, Sisi BRAND, Bisa dibandingkan, Status / Username, Gender known %, Age coverage %, Geo known %, Geo top, Interest top, Sumber | Kesiapan 4 dimensi audiens | ✅ **INTI** |
| 7 | `Personality Values Fit` | 21 | 4 | 6 + 4 | Aspek, Temuan, Status / kind, attribute_group, #, label | Formula Values + taxonomy atribut DB | ✅ **INTI** |
| 8 | `Performance Fit` | 24 | 3 | **12** + 3 | Brand archetype, Creator archetype, Skor workbook | Lookup archetype hasil reverse-engineer | ⚠️ workbook kontradiktif |
| 9 | `Partnership Score` | 26 | 3 | 6 + 10 | Aspek, Temuan, Status / Kolom output, Nilai POC | Formula agregat + bentuk 1 baris output | ✅ bentuk output |
| 10 | `Final POC Results` | 47 | 13 | **40 kombinasi** | Creator ID, Username, Kategori, Brand, Category, Audience, Values, Performance, Partnership, # komponen, Coverage, Status, Diagnostik | 10 creator × 4 brand | ✅ **hasil** |
| 11 | `Coverage & Missing Data` | 19 | 6 | **12** | Input, Sisi, Lokasi, Tersedia, Coverage, Status | Peta coverage per input ke lokasi DB | ✅ **INTI** |
| 12 | `Decision Needed` | 12 | 5 | **7** | #, Keputusan, Kenapa script tidak bisa, Dampak, Status | Blocker yang butuh keputusan manusia | ✅ blocker |
| 13 | `Source & Evidence` | 26 | 4 | **9 SQL** + 6 | ID, Tujuan, SQL, Hasil / Nilai, File, Sheet&baris | 9 SELECT verbatim + asal nilai brand | ✅ **bukti** |

### Contoh data — `Dummy Brand Input` (4 baris, lengkap) **[EXCEL]**

| Brand | Kategori Bisnis | Size Tier | Performance Archetype | Target Demografi | Brand Personality | Brand Tone | # Atribut |
|---|---|---|---|---|---|---|---:|
| Kala Basics | LifeWear / Everyday Essentials | Macro (500K – 1M) | High Reach & Consistent Engagement | Pria & Wanita (18–45), pekerja kantoran urban, keluarga muda | Educational, Authentic, Caring, Modern | Informative, Straightforward, Warm | 7 |
| Vortex Athletic | Athleisure & Sport-Streetwear | Macro (500K – 1M) | High Viral & Hype Generation | Gen Z & Millennials (16–30), pegiat gym, sneakerhead lokal | Innovative, Bold, Playful, Authentic | Inspiring, Aspirational, Conversational | 7 |
| Aura Mode | Fast Fashion / Trend-Driven | Mid-tier (100K – 500K) | High Impulse & Visual Engagement | Urban Youth & Professionals (20–35) | Modern, Premium, Professional, Bold | Aspirational, Formal, Informative | 7 |
| Strive Pro | Athletic Performance & Footwear | Mega (> 1M) | Massive Reach & Emotional Resonance | Pelari, olahragawan, remaja–dewasa (17–40) | Innovative, Professional, Bold, Authentic | Inspiring, Straightforward, Aspirational | 7 |

**Fakta yang menentukan:** `Target Demografi` adalah **kalimat bahasa Indonesia**,
bukan distribusi — sementara DB sekarang **menyediakan kolom terstruktur**
(`gender_majority`, `target_age_min/max`, `audience_interests`). Jadi
masalahnya bukan lagi "DB tidak punya tempat", tapi **"Excel tidak punya
bentuk"**. Lihat §A.6.

## A.3 Row count seluruh tabel relevan **[DB-LIVE]**

| Relation | Ada? | Baris |
|---|---|---:|
| `public.brand` | ADA | **0** |
| `public.brand_profile` | ADA | **0** |
| `public.brand_members` | ADA | **0** |
| `feature.brand_fit_analysis` | ADA | **0** |
| `public.kol_directory` | ADA | **7.432** |
| `public.kol_categories` | ADA | **28** |
| `public.kol_tiers` | ADA | **5** |
| `public.agency_kol_accounts` | ADA | **7.431** |
| `public.kol_social_account` | ADA | **7.208** |
| `public.kol_attribute` | ADA | **40** |
| `public.kol_attribute_map` | ADA | **0** |
| `public.campaigns` | ADA | **0** |
| `public.campaign_kols` | ADA | **0** |
| `public.campaign_kol_deliverables` | ADA | **0** |
| `public.campaign_content_performance` | ADA | **0** |
| `public.campaign_orders` | ADA | **0** |
| `public.campaign_stages` | ADA | **12** |
| `l2_gold.kol_profile_card` | ADA | **1.978** |
| `feature.ig_audience_analysis` | ADA | **16** |
| `feature.tt_audience_analysis` | ADA | **11** |

Sapuan `information_schema.columns WHERE column_name ~* 'archetype'` seluruh
schema → **0 baris**. Archetype memang tidak punya rumah di mana pun. **CONFIRMED.**

## A.4 Mapping `brand_dummy` → DB `kol`

### A.4.1 Sisi BRAND **[EXCEL × DB-LIVE]**

| # | Excel | DB | Tersedia | Exact / Transform | Matching key | #Excel | #DB | Match | Coverage |
|---:|---|---|---|---|---|---:|---:|---:|---:|
| 1 | `Dummy Brand Input.Brand (dummy)` | `public.brand.name` (varchar) · `brand_profile.brand_name` (varchar) | ✅ kolom ADA | **exact** | — `brand.id` di-generate | 4 | **0 baris** | 0 | **0%** |
| 2 | `.Kategori Bisnis` | `brand.category` (varchar) · `brand_profile.brand_category` (varchar) | ✅ kolom ADA | ❌ **kosakata tidak cocok** — §C.1 | tidak ada key aman | 4 | 0 baris | 0 | **0%** |
| 3 | `.Brand Personality` | `brand_profile.brand_personality` **ARRAY(text)** | ✅ kolom ADA | split string → array | — | 16 nilai / 9 unik | 0 baris | 0 | **0%** |
| 4 | `.Brand Tone` | `brand_profile.brand_tone` **ARRAY(text)** | ✅ **KOLOM ADA** (koreksi) | split string → array | — | 12 nilai / 7 unik | 0 baris | 0 | **0%** |
| 5 | `.Target Demografi` | `brand_profile.gender_majority` · `target_age_min` · `target_age_max` · `target_country` · `target_city` · `audience_interests` | ✅ **6 kolom ADA** (koreksi) | ❌ **kalimat → 6 field = parsing bahasa alami** | — | 4 kalimat | 0 baris | 0 | **0%** |
| 6 | `.Size Tier` | `public.kol_tiers` | ⚠️ salah sisi | tier = sifat **creator** | — | 4 | 5 tier | n/a | **N/A** |
| 7 | `.Performance Archetype` | **TIDAK ADA KOLOM** di seluruh DB | ❌ | — | — | 4 | **0 kolom** | 0 | **0%** |
| 8 | `.# Atribut` | — (derived) | n/a | penyebut Values Fit | — | 4 | — | — | — |

### A.4.2 Sisi CREATOR **[EXCEL × DB-LIVE]**

| # | Excel | DB | Tersedia | Matching key | #Excel | #DB | Match | Coverage |
|---:|---|---|---|---|---:|---:|---:|---:|
| 9 | `Real Creator Sample.Creator ID` | `public.kol_directory.id` (uuid) | ✅ | uuid langsung | 10 | 7.432 | **10/10** | **100%** |
| 10 | `.Username` | `kol_directory.username` | ✅ | `username_normalized` | 10 | 7.432 | **10/10** | 100% |
| 11 | `.Kategori (taxonomy_key)` | `category_ids[]` → `kol_categories.taxonomy_key` | ✅ | `kc.id = ANY(kd.category_ids)` | 10 | 28 nama / **9 key** | **10/10** | 100% sample · **53,6%** roster |
| 12 | `.Followers` | `kol_directory.followers_count` (**integer**) | ✅ | — | 10 | 7.210 | 10 | 97,0% roster |
| 13 | `.ER %` | `kol_directory.engagement_rate` | ⚠️ | — | 7/10 | **1.736** | 7 | **23,4%** roster |
| 14 | `.Kota` | `kol_directory.creator_city` | ❌ | — | 0/10 | **0 terisi** | 0 | **0%** |
| 15 | `Audience Fit.Sumber audiens` | `feature.ig_audience_analysis` (16) / `tt_audience_analysis` (11) | ⚠️ | `social_account_id` via `kol_social_account` | 10 | **27 kreator** | 10 | **0,36%** roster |
| 16 | `.Performance metrics` | `l2_gold.kol_profile_card` | ⚠️ | `social_account_id` | 10 | 1.978 | 10 | §C.4 |
| 17 | `.Personality/tone` | `public.kol_attribute_map` | ❌ | `kol_directory_id` | 0/10 | **0 baris** | 0 | **0%** |
| 18 | `.Archetype` | **tidak ada kolom** | ❌ | — | 0/10 | 0 kolom | 0 | **0%** |

### A.4.3 GRAIN — diverifikasi, dan hasilnya BERSIH **[DB-LIVE]**

Grain Brand Fit dibuktikan constraint:

```
uq_brand_fit_analysis  UNIQUE (agency_kol_account_id, brand_id)
fk_brand_fit_analysis_agency_kol_account FK (agency_kol_account_id) -> agency_kol_accounts(id)
fk_brand_fit_analysis_brand              FK (brand_id)              -> brand(id)
```

Creator ID di Excel adalah `kol_directory.id`, jadi butuh satu hop lewat
`agency_kol_accounts.kol_account_id`
(FK `agency_kol_accounts_kol_account_id_fkey → kol_directory(id)`).

Hasil pengecekan relasi:

| Metrik | Nilai |
|---|---:|
| `kol_directory` | 7.432 |
| `agency_kol_accounts` | 7.431 |
| `kol_account_id` unik di `agency_kol_accounts` | **7.431** |
| `kol_directory` tanpa pasangan agency account | **1** |
| `agency_kol_accounts` tanpa pasangan `kol_directory` | **0** |
| KOL yang terdaftar di **lebih dari satu** agency | **0** |

> **Relasinya 1:1 bersih.** Tidak ada fan-out, tidak ada orphan di sisi agency.
> Hanya 1 baris `kol_directory` yang tidak punya agency account.

**Dan 10 creator sample POC: 10/10 punya `agency_kol_account_id`.**

| Username | taxonomy_key | `agency_kol_account_id` | #attr |
|---|---|---|---:|
| cristiano | Fitness | `917688cb-3cf0-4039-b3a2-22d5d0f2301e` | 0 |
| lunamaya | Beauty | `edd19b8d-a591-4665-8168-8b6017bf3fc8` | 0 |
| pevpearce | Lifestyle | `e701102e-13aa-4090-b538-ffdc2d5b4e05` | 0 |
| sptrakori_ | Entertainment | `1444c876-b9a2-4fb4-becc-e004ea88ba89` | 0 |
| isyanasarasvati | Fashion | `3230b006-f88e-49e1-be37-68ab22199726` | 0 |
| lambe_turah | Entertainment | `af802df5-c869-4742-adbf-9b0e592d90fc` | 0 |
| hesfinatia | Entertainment | `abcc4f3d-f1c5-4cc3-8769-529dd440707a` | 0 |
| anyageraldine | Lifestyle | `e5a3de7e-cf4a-4863-b143-0fc2812eda38` | 0 |
| iben_ma | Entertainment | `f333d6e7-b165-459f-b2c8-85087012e80c` | 0 |
| inul.d | Entertainment | `21153718-45d2-4b45-9161-86551da4f9a4` | 0 |

> **Kunci matching paling reliable, ditetapkan dari struktur DB (bukan asumsi):**
> `kol_directory.id` → `agency_kol_accounts.kol_account_id` → `agency_kol_accounts.id`.
> Ditopang FK sungguhan, unik, tanpa duplikat. **Tabel di atas siap diserahkan
> ke Backend apa adanya.**
>
> Username **tidak** dipakai sebagai kunci: `kol_directory` punya `platform_id`
> sebagai kolom, jadi satu handle bisa punya dua baris (satu per platform).
> UUID satu-satunya yang aman.

## A.5 Duplicate **[EXCEL]**

| Objek | Jumlah | Duplicate |
|---|---:|---:|
| Brand di `Dummy Brand Input` | 4 | **0** |
| Creator ID di `Real Creator Sample` | 10 | **0** |
| Pasangan (creator, brand) di `Final POC Results` | 40 | **0** (10×4 lengkap) |
| Atribut personality+tone per brand | 7 | **0** (dedup case-insensitive) |

## A.6 VALIDASI BRAND PROFILE — tabel yang diminta **[DB-LIVE]**

`public.brand_profile` = **29 kolom, 0 baris**. Seluruh field yang dibutuhkan ADA.

| Excel | DB field | Status | Catatan |
|---|---|---|---|
| `Dummy Brand Input.Brand (dummy)` | `brand.name` (varchar) | **AVAILABLE** | 0 baris. Juga ada `brand_profile.brand_name` |
| `Dummy Brand Input.Brand (dummy)` | `brand_profile.brand_name` (varchar) | **AVAILABLE** | duplikasi nama di dua tabel — perlu keputusan mana yang otoritatif |
| `.Kategori Bisnis` | `brand_profile.brand_category` (varchar) | **TRANSFORM** | Kolom ada, tapi kosakata Excel ("LifeWear / Everyday Essentials") tidak cocok `taxonomy_key`. **Tanpa CHECK/FK** — DB tidak menjamin apa pun |
| `.Target Demografi` (kalimat) | `brand_profile.gender_majority` (varchar, default `'Any'`) | **TRANSFORM** | Butuh parsing "Pria & Wanita" → nilai enum. Kosakata enum belum diketahui (0 baris) |
| `.Target Demografi` (kalimat) | `brand_profile.target_age_min` (smallint) | **TRANSFORM** | "18–45 tahun" → 18. Parsing regex, bisa diandalkan untuk keempat brand |
| `.Target Demografi` (kalimat) | `brand_profile.target_age_max` (smallint) | **TRANSFORM** | "18–45 tahun" → 45 |
| `.Target Demografi` (kalimat) | `brand_profile.target_country` / `target_city` (varchar) | **TRANSFORM** | "pekerja kantoran urban" bukan kota. Tidak ada kota eksplisit di keempat brand → realistis **MISSING** |
| — | `brand_profile.audience_interests` ARRAY(text) | **MISSING di Excel** | Kolom ADA di DB, tapi `brand_dummy` **tidak punya kolom interest sama sekali** |
| `.Brand Personality` | `brand_profile.brand_personality` ARRAY(text) | **TRANSFORM** | Split CSV → array. 4 nilai/brand |
| `.Brand Tone` | `brand_profile.brand_tone` ARRAY(text) | **TRANSFORM** | Split CSV → array. 3 nilai/brand |
| — | `brand_profile.performance_targets` jsonb | **MISSING di Excel** | Kolom ADA. Excel punya `Performance Archetype` (label), bukan target numerik. **Bukan hal yang sama** |
| `.Performance Archetype` | **tidak ada kolom** | **MISSING** | 0 kolom archetype di seluruh DB |
| `.Size Tier` | `brand_profile.preferred_tiers` ARRAY(text) | **TRANSFORM** | ⚠️ Excel menaruh tier sebagai sifat **brand**; kolom DB artinya "tier creator yang dipilih brand". Semantiknya beda — jangan disamakan tanpa keputusan |

### ⚠️ Tiga temuan struktural sisi brand

**1. Kosakata kategori brand tidak dijamin apa pun.**
Constraint pada `brand` + `brand_profile` hanya: `brand_pkey`, `fk_brand_agency`,
`brand_profile_pkey`, `brand_profile_organization_id_key`.
**Nol CHECK, nol FK pada `brand.category` maupun `brand_profile.brand_category`.**
Siapa pun bisa menulis string apa pun ke sana.

**2. `brand_profile` bergrain ORGANIZATION, bukan brand.**

```
brand_profile_organization_id_key  UNIQUE (organization_id)
brand_id                           uuid, NULLABLE, TANPA FK ke brand(id)
```

**Satu `brand_profile` per organization.** Artinya **4 brand dummy tidak bisa
disimpan sebagai 4 baris `brand_profile` di bawah satu organization.** Ini
bentrok langsung dengan grain Brand Fit yang `(agency_kol_account_id, brand_id)`.
**Perlu keputusan Backend/Product sebelum baris pertama masuk.**

**3. Tidak ada tabel pemetaan kategori.**
Sapuan seluruh DB untuk tabel berpola `map|alias|lookup|relevan|related|match_config|taxonom`
→ hanya **1 tabel**: `public.kol_attribute_map` (**0 baris**). **Tidak ada**
tabel yang memetakan kategori brand ke `taxonomy_key`.

## A.7 Gap — sisi brand

| Gap | Sifat | Berubah dari audit lama? |
|---|---|---|
| `Brand_Fit_Dummy_Data.xlsx` hilang dari repo | **Artefak** | — |
| `public.brand` / `brand_profile` = 0 baris | **Data** | tetap |
| `Kategori Bisnis` tidak memakai kosakata DB | **Keputusan bisnis** | tetap |
| `brand_tone` tidak punya kolom | ~~Struktur~~ | ✅ **SELESAI — kolom ADA** |
| Target demografi tidak punya kolom | ~~Struktur~~ | ✅ **SELESAI — 6 kolom ADA** |
| Target demografi Excel berbentuk kalimat | **Bentuk data** | **masih** |
| `brand_profile` UNIQUE per organization | **Struktur + keputusan** | **BARU** |
| `brand.category` tanpa CHECK/FK | **Struktur** | tetap |
| `Performance Archetype` tidak punya kolom | **Struktur + keputusan** | tetap |

---

# B. TAKSONOMI KOL

## B.1 Struktur Excel **[EXCEL]** — `docs/taksonomi_kol.xlsx`, 7 sheet

| Sheet | Rows (data) | Cols | Kolom | Level | ID? | Key? | Parent? |
|---|---:|---:|---|---|---|---|---|
| `Demografi` | 7 | 2 | Field Name, Dropdown Options | 1 (flat) | ❌ | ⚠️ `Field Name` seperti key | ❌ |
| `Industry` | **36** | 2 | Category, Subcategory | **2 (hierarki)** | ❌ | ❌ | ✅ implisit |
| `Follower Size Tier` | 5 | 2 | Tier, Follower Count | 1 | ❌ | ❌ | ❌ |
| `Performance Archetype` | 3 (+1 catatan) | 3 | Archetype, Main Strength, Formula | 1 | ❌ | ❌ | ❌ |
| `Sentiment Archetype` | 3 (+1 catatan) | 3 | Archetype, Meaning, Classification Rule | 1 | ❌ | ❌ | ❌ |
| `Content Format` | 4 | 2 | Format, Description | 1 | ❌ | ❌ | ❌ |
| `Posting Cadence` | 4 | 2 | Level, Frequency | 1 | ❌ | ❌ | ❌ |

> Taxonomy Excel **tidak punya satu pun ID, kode, atau key** — hanya label teks.
> Tidak ada `taxonomy_key`, `category_id`, `parent_id`, `level`.
> **Satu-satunya kunci matching yang mungkin adalah string label.**

## B.2 Struktur DB **[DB-LIVE]** — `public.kol_categories`

**5 kolom:** `id (uuid)`, `name (varchar)`, `created_at`, `updated_at`,
`taxonomy_key (text)`. **Tidak ada** parent, level, kode, atau hierarki.
**28 baris**, **9 `taxonomy_key` unik**, **6 baris ber-`taxonomy_key` NULL**.

| name | taxonomy_key | kreator | | name | taxonomy_key | kreator |
|---|---|---:|---|---|---|---:|
| Lifestyle | Lifestyle | 2.442 | | Cooking | Food | 9 |
| Beauty | Beauty | 1.206 | | Parenting and family | Moms | 8 |
| Moms | Moms | 542 | | Musicians | Entertainment | 7 |
| Entertainment | Entertainment | 458 | | Medical | **NULL** | 6 |
| Gen Z | Gen Z | 145 | | Dance | Entertainment | 3 |
| Fashion | Fashion | 73 | | Gym Enthusiast | Fitness | 3 |
| Foodies | Food | 63 | | Story Teller | Entertainment | 3 |
| Home Decor | Lifestyle | 58 | | Gaming | Tech | 2 |
| Food | Food | 55 | | Spirituality and religion | **NULL** | 2 |
| Fitness | Fitness | 24 | | Technology and gadgets | Tech | 2 |
| Sports | Fitness | 24 | | Animal Lovers | **NULL** | 1 |
| Humor | Entertainment | 12 | | Business and entrepreneurship | **NULL** | 1 |
| Travel | Lifestyle | 12 | | Cyclist | Fitness | 1 |
| Automotive and motorsports | **NULL** | 9 | | Environmentalism and sustainability | **NULL** | 1 |

**Rollup 9 canonical key [DB-LIVE]:** Lifestyle **2.511** · Beauty **1.206** ·
Moms **550** · Entertainment **483** · Gen Z **145** · Food **118** ·
Fashion **73** · Fitness **52** · **Tech 4**.

**Coverage roster:** total 7.432 · punya `category_ids` **4.002 (53,8%)** ·
punya ≥1 `taxonomy_key` **3.983 (53,6%)** · `category_ids` ada tapi semua key
NULL **19**.

**Distribusi kategori per kreator:** 1 key → **2.844** · 2 → **1.111** ·
3 → **27** · 5 → **1**. Jadi **1.139 dari 3.983 (28,6%)** kreator membawa ≥2
`taxonomy_key`.

## B.3 Matching `Industry` → `kol_categories` **[EXCEL × DB-LIVE]**

Metode: normalisasi lowercase + strip non-alfanumerik, lalu **exact match saja**.
**Tidak ada fuzzy matching** — fuzzy pada dua kosakata beda domain hanya
menghasilkan false positive.

| Perbandingan | #Excel unik | #DB unik | Exact match | Tidak match | Dup | Coverage Excel→DB | Coverage DB→Excel |
|---|---:|---:|---:|---:|---:|---:|---:|
| `Industry.Category` (L1) vs `taxonomy_key` (9) | 11 | 9 | **0** | 11 | 0 | **0,0%** | **0,0%** |
| `Industry.Category` (L1) vs `name` (28) | 11 | 28 | **2** | 9 | 0 | **18,2%** | 7,1% |
| `Industry.Subcategory` (L2) vs `taxonomy_key` (9) | 36 | 9 | **0** | 36 | 0 | **0,0%** | 0,0% |
| `Industry.Subcategory` (L2) vs `name` (28) | 36 | 28 | **0** | 36 | 0 | **0,0%** | 0,0% |
| **L1+L2 vs `name`+`taxonomy_key`** | **47** | **29** | **2** | **45** | 0 | **4,3%** | **6,9%** |

Duplicate di Excel: **0** pasangan Category–Subcategory ganda; **0** subcategory
dipakai lebih dari satu parent.

### Taxonomy hanya ada di Excel (45 dari 47)

**Category L1 (9):** Automotive · CPG & Food/Beverage · Education ·
Family, Kids & Pets · Financial Services · Health & Wellness ·
Other/Uncategorized · Retail & E-commerce · Technology & Telecom

**Subcategory L2 (36 — semuanya):** Accessories & Modification ·
Airlines/Transportation · App/Software · Automotive Marketplace/Service ·
Baby & Kids Products · Banking · Beauty & Personal Care ·
Beverages (coffee, RTD) · Cars · Courses/Tutoring · Destination/Hotel ·
E-wallet/Payment · EdTech App · Esports · Fashion & Apparel · Fitness/Gym ·
Healthcare Service · Higher Ed/Campus · Home & Living · Insurance ·
Investment & Fintech Lending · Mental Wellness · Mobile Gaming · Motorcycles ·
OTA · Online Shop/Marketplace · PC/Console Gaming · Packaged Food (FMCG) ·
Parenting Lifestyle · Pet Care · Restaurant/Culinary · Smart Home/IoT ·
Smartphone/Gadget · Supplements & Vitamins · Telco Provider · Uncategorized

### Taxonomy hanya ada di DB (27 dari 29)

**`taxonomy_key` (9 — TIDAK SATU PUN ada di Excel):** Beauty · Entertainment ·
Fashion · Fitness · Food · Gen Z · Lifestyle · Moms · Tech

**`name` (26 dari 28):** Animal Lovers · Automotive and motorsports · Beauty ·
Business and entrepreneurship · Cooking · Cyclist · Dance · Entertainment ·
Environmentalism and sustainability · Fashion · Fitness · Food · Foodies ·
Gen Z · Gym Enthusiast · Home Decor · Humor · Lifestyle · Medical · Moms ·
Musicians · Parenting and family · Spirituality and religion · Sports ·
Story Teller · Technology and gadgets

### ⚠️ Dua "match" itu palsu secara semantik

| Label | Di Excel | Di DB **[DB-LIVE]** | Sama? |
|---|---|---|---|
| **Gaming** | `Industry.Category` **L1** — industri brand (parent dari Mobile Gaming, PC/Console, Esports) | `kol_categories.name`, `taxonomy_key` = **Tech**, **2 kreator** | ❌ beda level, beda domain |
| **Travel** | `Industry.Category` **L1** — industri brand (parent dari Destination/Hotel, Airlines, OTA) | `kol_categories.name`, `taxonomy_key` = **Lifestyle**, **12 kreator** | ❌ beda level, beda domain |

> **Vonis: exact match yang bermakna = 0 dari 47. Coverage efektif 0,0%.**
> Ini bukan taxonomy sama dengan penamaan berbeda — ini **dua taxonomy untuk dua
> hal berbeda**. Excel `Industry` mengklasifikasi **industri brand**;
> `kol_categories` mengklasifikasi **niche konten creator**.
> Dan **tidak ada tabel pemetaan** di antara keduanya (§A.6).

## B.4 Sheet taxonomy lain vs DB **[DB-LIVE]**

| Sheet Excel | Padanan DB | #Excel | #DB | Match | Coverage | Catatan |
|---|---|---:|---:|---:|---:|---|
| `Follower Size Tier` | `public.kol_tiers` | 5 | **5** | **5 nama** | **100% nama** | ⚠️ **batas beda** |
| `Demografi` | tersebar | 7 field | — | — | — | daftar field+enum, bukan tabel taxonomy |
| `Performance Archetype` | **0 kolom** | 3 | 0 | **0** | **0%** | gap |
| `Sentiment Archetype` | **0 kolom** | 3 | 0 | **0** | **0%** | gap |
| `Content Format` | `kol_profile_card.format_dominant` | 4 | — | — | — | kolom ada |
| `Posting Cadence` | `kol_profile_card.post_frequency_*` | 4 | — | **0 label** | **0%** | DB simpan **angka**, bukan label bucket |

### ⚠️ `Follower Size Tier` — nama cocok 5/5, **batas 3/5 BEDA** [DB-LIVE]

| Tier | Excel (`taksonomi_kol`) | `public.kol_tiers` (dibaca hari ini) | Sama? |
|---|---|---|---|
| Nano | `< 10K` | `min 1.000` – `max 9.999` | ⚠️ DB punya lubang di bawah 1.000 |
| Micro | `10K – 100K` | `min 10.000` – `max 49.999` | ❌ **BEDA** |
| Mid-tier | `100K – 500K` | `min 50.000` – `max 499.999` | ❌ **BEDA** |
| Macro | `500K – 1M` | `min 500.000` – `max 999.999` | ✅ sama |
| Mega | `> 1M` | `min 1.000.000` – `max NULL` | ✅ sama |

Bahaya senyap: nama tier identik, jadi mismatch **tidak akan terlihat** sampai
ada KOL 60.000 follower yang disebut "Micro" oleh Excel dan "Mid-tier" oleh DB.
`brand_dummy.Size Tier` memakai konvensi **Excel**, bukan DB.

## B.5 Gap taxonomy

| Gap | Sifat | Dampak |
|---|---|---|
| Excel `Industry` dan `kol_categories` dua kosakata terpisah, 0% irisan bermakna | **Keputusan bisnis** | Category Matching mati |
| Excel tidak punya ID/key/level — hanya label | **Struktur** | Tidak ada join key stabil |
| Tidak ada tabel pemetaan kategori di DB | **Struktur** | Jembatan harus dibuat |
| 6 dari 28 `kol_categories` ber-`taxonomy_key` NULL (19 kreator di luar) | **Data** | Kreator tanpa tempat di matriks |
| Batas tier Micro/Mid-tier/Nano beda | **Data + keputusan** | Salah label senyap |
| `Performance` & `Sentiment Archetype` tidak punya rumah | **Struktur** | Past Performance mati |
| `Posting Cadence` label vs angka DB | **Transform** | Butuh aturan bucket |

---

# C. BRAND FIT DATA READINESS

Formula yang **TIDAK DIUBAH**: `100 = cocok · 50 = related · 0 = tidak cocok`,
threshold `CATEGORY_RELATEDNESS >= 60`.

> `CATEGORY_RELATEDNESS` **tidak ada di repo ini** (`grep -ri` = 0 hit di luar
> `venv`) dan **tidak ada di DB** (0 tabel `match_config`/`lookup`). Ia milik
> repo Backend. Yang bisa divalidasi di sini: apakah ada **data** yang memberi
> makna pada ambang itu. Jawabannya: ada, satu — matriks 11d.

## C.1 Category Matching (25%)

### Alur yang diminta — diuji hop demi hop

```
brand_dummy → brand category → taksonomi_kol → kol_categories.taxonomy_key → category KOL
```

| Hop | Dari | Ke | Hasil |
|---:|---|---|---|
| 1 | `brand_dummy.Kategori Bisnis` (4) | `taksonomi_kol.Industry` (47) | ❌ **0 / 4 match** |
| 2 | `taksonomi_kol.Industry` (47) | `kol_categories.taxonomy_key` (9) | ❌ **0 / 47 match** |
| 3 | `kol_categories.taxonomy_key` | kategori KOL | ✅ **3.983 kreator (53,6%)** |

**Hop 1 — bukti [EXCEL]:**

| `brand_dummy.Kategori Bisnis` | Ada di `taksonomi_kol.Industry`? | Ada di `kol_categories`? |
|---|---|---|
| LifeWear / Everyday Essentials | ❌ | ❌ |
| Athleisure & Sport-Streetwear | ❌ | ❌ |
| Fast Fashion / Trend-Driven | ❌ | ❌ |
| Athletic Performance & Footwear | ❌ | ❌ |

Keempatnya **positioning produk**, bukan kategori industri maupun niche creator.
Bahkan terhadap `taksonomi_kol` — yang seharusnya jadi jembatan — tidak satu pun
cocok.

> **Vonis: rantai putus di DUA hop dari tiga.** Category Matching **tidak bisa**
> dijalankan reliable dengan `brand_dummy` + `taksonomi_kol` apa adanya.

### Yang sudah ada dan terlewat: matriks relevansi 9×9

`docs/brand_match_master.xlsx` → `CMP_Lookup_Lists` **r346–356**, blok
`11d. CANONICAL CATEGORY × CANONICAL CATEGORY`. **Kedua sumbunya adalah 9
`taxonomy_key` yang persis sama dengan DB live** (diverifikasi §B.2).

| ↓brand / creator→ | Beauty | Entertainment | Fashion | Fitness | Food | Gen Z | Lifestyle | Moms | Tech |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Beauty** | 100 | 50 | 80 | 40 | 30 | 60 | 70 | 50 | 20 |
| **Entertainment** | 40 | 100 | 50 | 30 | 40 | 70 | 60 | 40 | 30 |
| **Fashion** | 80 | 50 | 100 | 40 | 20 | 60 | 70 | 40 | 20 |
| **Fitness** | 40 | 30 | 40 | 100 | 60 | 40 | 60 | 40 | 20 |
| **Food** | 30 | 50 | 20 | 50 | 100 | 40 | 70 | 60 | 20 |
| **Gen Z** | 60 | 70 | 60 | 40 | 40 | 100 | 60 | 20 | 50 |
| **Lifestyle** | 70 | 60 | 70 | 60 | 70 | 60 | 100 | 60 | 40 |
| **Moms** | 50 | 40 | 40 | 40 | 60 | 20 | 60 | 100 | 20 |
| **Tech** | 20 | 30 | 20 | 20 | 20 | 50 | 40 | 20 | 100 |

Tangga: 100 (9 sel) · 80 (2) · 70 (8) · 60 (15) · 50 (9) · 40 (18) · 30 (6) ·
20 (14) = **81 sel**. **Asimetris** pada 3 dari 36 pasangan
(Beauty↔Entertainment, Entertainment↔Food, Fitness↔Food) → **arah baca penting**:
baris = brand, kolom = creator.

**Jika `CATEGORY_RELATEDNESS >= 60` diterapkan** [EXCEL]:

| Skor Brand Fit | Aturan | Sel | % |
|---|---|---:|---:|
| **100** (cocok) | matriks = 100 | 9 | 11,1% |
| **50** (related) | 60 ≤ matriks < 100 | **25** | 30,9% |
| **0** (tidak cocok) | matriks < 60 | 47 | 58,0% |

> **Ini menjawab blocker "related = 50 tidak pernah terdefinisi"**
> (`brand_dummy.Decision Needed` #2). Matriks 11d + ambang 60 memberi **25
> pasangan related** yang berdasar data, bukan karangan.
>
> **Yang kurang: sumbu BARIS (brand).** Matriks butuh brand dinyatakan dalam
> `taxonomy_key`. `brand_dummy` tidak memberikannya, `taksonomi_kol` tidak
> memberikannya, `brand_profile.brand_category` ada tapi **0 baris dan tanpa
> CHECK/FK**.

### Blocker: kreator multi-kategori **[DB-LIVE]**

**1.139 dari 3.983 (28,6%)** kreator membawa ≥2 `taxonomy_key` (2 key: 1.111 ·
3 key: 27 · 5 key: 1). Matriks 11d memetakan satu-lawan-satu. **Aturan agregasi
(max / mean / primary) tidak ada di dokumen mana pun.**

| Item | Nilai |
|---|---|
| **Status Category Matching** | ⚠️ **PARTIAL — sisi creator SIAP, sisi brand 0 baris** |
| Coverage creator | **3.983 / 7.432 = 53,6%** |
| Coverage brand | **0%** (kolom ada, 0 baris, kosakata tidak cocok) |
| Coverage end-to-end | **0%** |

## C.2 Audience Overlap (25%)

### Sisi CREATOR **[DB-LIVE]**

`feature.ig_audience_analysis` **16 baris** · `feature.tt_audience_analysis`
**11 baris** → **27 kreator dari 7.432 = 0,36%**.

| Dimensi | Kolom | IG terisi | TT terisi | Coverage roster |
|---|---|---:|---:|---:|
| **Gender** | `gender_breakdown`, `gender_known_pct` | 16/16 | 11/11 | **0,36%** |
| **Age** | `age_gender_breakdown` (jsonb) | 16/16 | 11/11 | **0,36%** ⚠️ lihat bawah |
| **Location** | `geo_distribution` (jsonb) | 16/16 | 11/11 | **0,36%** |
| **Interests** | `interest_top`, `interest_source` | 16/16 | 11/11 | **0,36%** |
| `cpe` / `emv` / `avg_reach` | — | **0** | **0** | **0%** |

### ⚠️ AGE — kolomnya terisi, datanya tidak ada **[DB-LIVE]**

Gue buka isi `age_gender_breakdown` satu per satu:

```
27 baris punya age_gender_breakdown
 1 baris punya total bucket umur (selain 'unknown') > 0
26 baris SELURUH bucket umur = 0

contoh: {"45+": 0, "13-17": 0, "18-24": 0, "25-34": 0, "35-44": 0, "unknown": 100}
```

**26 dari 27 baris: kelima bucket umur nol, seluruh populasi di `unknown`.**
`count(age_gender_breakdown)` = 27 akan menipu siapa pun yang membaca sekilas.

> Sesuai aturan: **missing = NULL, bukan 0.** Kelima nol itu **bukan** "0% umur
> 18–24" — itu "tidak diukur". Skor age harus **NULL**.
> Coverage age yang jujur: **1 / 7.432 = 0,01%**.

### Tabel audience L2 **[DB-LIVE]**

| Tabel | Baris |
|---|---:|
| `l2_gold.audience_interest_daily` | 229 |
| `l2_gold.audience_geo_daily` | 196 |
| `l2_gold.audience_demographics_daily` | 113 |
| `l1_silver.unified_audience` | **0** |

### Sisi BRAND **[DB-LIVE]** — KOREKSI: kolomnya ADA

| Dimensi | Kolom `brand_profile` | Tipe | Baris | brand_dummy |
|---|---|---|---:|---|
| Gender | `gender_majority` | varchar, default `'Any'` | **0** | kalimat: "Pria & Wanita (18–45 tahun)" |
| Age | `target_age_min`, `target_age_max` | smallint | **0** | kalimat: "(16–30 tahun)" |
| Location | `target_country`, `target_city` | varchar | **0** | kalimat: "pekerja kantoran urban" |
| Interests | `audience_interests` | ARRAY(text) | **0** | **tidak ada kolomnya di Excel** |

**Blokernya berubah sifat.** Dulu: "DB tidak punya tempat". Sekarang: **"DB punya
tempat, Excel tidak punya bentuk, dan tabelnya 0 baris"**.

Tiga dari empat dimensi **bisa di-parse** dari kalimat `brand_dummy` dengan
aturan yang bisa ditulis (regex rentang umur, kata gender, negara). Dimensi
keempat — **interests — tidak bisa**, karena `brand_dummy` memang tidak punya
kolom interest sama sekali.

Angka `40` konstan di 48 baris workbook dummy adalah **placeholder**, bukan
hitungan (dinyatakan sendiri oleh `brand_dummy.Audience Fit` r2). Jangan dipakai
sebagai observed brand audience.

| Item | Nilai |
|---|---|
| **Status Audience Overlap** | ❌ **NOT READY**, tapi **naik** dari "tidak ada kolom" |
| Coverage creator | gender/geo/interest **0,36%** · **age 0,01%** |
| Coverage brand | **0%** (4 dimensi punya kolom, 0 baris) |
| Coverage end-to-end | **0%** |

## C.3 Values Alignment (25%)

Formula workbook: `matched attributes ÷ brand attributes × 100`.

### Sisi CREATOR **[DB-LIVE]**

| Tabel | Baris |
|---|---:|
| `public.kol_attribute` | **40** |
| `public.kol_attribute_map` | **0** (0 kreator ter-mapping) |

`public.kol_attribute` — 40 baris, **32 label unik**, 4 `attribute_group`,
dibaca langsung hari ini:

| kind | attribute_group | # | label |
|---|---|---:|---|
| personality | `creator_personality` | 13 | Casual, Creative, Educational, Entertaining, Expert, Humorous, Inspirational, Luxury, Premium, Professional, Relatable, Reviewer, Tech-savvy |
| style | `content_style` | 11 | Aesthetic, Comedy, Commentary, Demo, Educational, Entertaining, Review, Storytelling, Talking Head, Tutorial, Vlog |
| style | `communication_style` | 9 | Conversational, Data-driven, Demonstration, Demonstrative, Educational, Humorous, Storytelling, Testimonial, Visual-first |
| style | `visual_style` | 7 | Aesthetic, Casual, Cinematic, Colorful, Lifestyle, Minimalist, Professional |

> **Tidak ada `attribute_group` bernama `tone` maupun `values` di sisi CREATOR.**
> Sisi brand sekarang punya `brand_profile.brand_tone` (ARRAY) — jadi tone
> punya rumah di sisi brand tapi **tidak punya lawan** di sisi creator.
> Ini asimetri yang harus diputuskan Product.

### Sisi BRAND vs taxonomy DB **[EXCEL × DB-LIVE]**

Matching exact (lowercase, strip non-alfanumerik). Tidak ada fuzzy.

| Brand | #atribut (dedup) | Match `kol_attribute` | Cocok | Tidak cocok |
|---|---:|---:|---|---|
| Kala Basics | 7 | **1** | Educational | Authentic, Caring, Modern, Informative, Straightforward, Warm |
| Vortex Athletic | 7 | **1** | Conversational | Innovative, Bold, Playful, Authentic, Inspiring, Aspirational |
| Aura Mode | 7 | **2** | Premium, Professional | Modern, Bold, Aspirational, Formal, Informative |
| Strive Pro | 7 | **1** | Professional | Innovative, Bold, Authentic, Inspiring, Straightforward, Aspirational |
| **TOTAL** | **28** | **5** | — | **23** |

**Coverage penyebut Values Fit: 5/28 = 17,9%.**

Kosakata unik gabungan: **16 nilai** (9 personality + 7 tone).
Match DB: **4 / 16 = 25,0%** → Conversational, Educational, Premium, Professional.

**Hanya di Excel (12):** Aspirational · Authentic · Bold · Caring · Formal ·
Informative · Innovative · Inspiring · Modern · Playful · Straightforward · Warm

**Hanya di DB (28):** Aesthetic · Casual · Cinematic · Colorful · Comedy ·
Commentary · Creative · Data-driven · Demo · Demonstration · Demonstrative ·
Entertaining · Expert · Humorous · Inspirational · Lifestyle · Luxury ·
Minimalist · Relatable · Review · Reviewer · Storytelling · Talking Head ·
Tech-savvy · Testimonial · Tutorial · Visual-first · Vlog

⚠️ Pasangan **mirip tapi tidak sama**: `Inspiring` (brand) vs `Inspirational`
(DB). Ini persis jenis pasangan yang akan tergoda di-fuzzy-match. **Jangan** —
`kol_attribute_taxonomy.py` sudah punya `ALIAS_BELUM_DIPUTUSKAN` untuk kasus
sejenis (Demonstration/Demonstrative/Demo); menambah alias adalah keputusan yang
harus ditulis, bukan ditebak.

| Item | Nilai |
|---|---|
| **Status Values Alignment** | ❌ **NOT READY** |
| `kol_attribute_map` | **0 baris / 0 kreator** → coverage creator **0%** |
| Kosakata brand yang punya padanan DB | **4/16 = 25%** |
| Penyebut Values Fit ter-cover | **5/28 = 17,9%** |
| Coverage end-to-end | **0%** |
| **Catatan** | `valuesFit(brand, [])` mengembalikan **0**. Untuk kreator yang atributnya **ABSEN**, 0 terbaca "tidak cocok". Harus NULL. Cek ketersediaan **sebelum** memanggil. |

> **Jalur tercepat membuka Brand Fit:** isi `kol_attribute_map`. Taxonomy sudah
> ada (40 baris terverifikasi hari ini), formulanya sudah ada. Yang kurang hanya
> kurasi manual — di luar lingkup audit read-only ini.

## C.4 Past Performance (25%)

### Archetype — 0 kolom di seluruh DB **[DB-LIVE]**

Sapuan `information_schema.columns WHERE column_name ~* 'archetype'` seluruh
schema → **0 baris**. **CONFIRMED.**

Tiga kosakata archetype yang beredar, **saling asing**:

| Sumber | Nilai |
|---|---|
| `brand_dummy` sisi brand | High Reach & Consistent Engagement · High Viral & Hype Generation · High Impulse & Visual Engagement · Massive Reach & Emotional Resonance |
| `brand_dummy` sisi creator (workbook) | High Engagement · High Reach · Community Driven |
| `taksonomi_kol.Performance Archetype` | Reach Driver · Engagement Driver · Relevance/Niche Authority |

**Irisan antar ketiganya: 0.**

Lookup workbook itu sendiri **kontradiktif** [EXCEL]:

| Brand archetype | vs High Engagement | vs High Reach | vs Community Driven |
|---|---:|---:|---:|
| High Reach & Consistent Engagement | 70 | 70 | 50 |
| High Viral & Hype Generation | 0 | 0 | 50 |
| High Impulse & Visual Engagement | **0** | **70** | 50 |
| Massive Reach & Emotional Resonance | **70** | **0** | 50 |

Dua baris terakhir persis terbalik. Tidak ada aturan yang bisa menghasilkan
keduanya — ini penetapan manual, bukan formula. **Jangan dipakai sebagai rule.**

### Metrik performance — coverage dibaca hari ini **[DB-LIVE]**

`l2_gold.kol_profile_card` = **1.978 baris**.

| Metrik diminta | Source table.column | Terisi | NULL | Coverage |
|---|---|---:|---:|---:|
| `engagement_rate` | `l2_gold.kol_profile_card.monitoring_er_pct` | **1.012** | 966 | **51,16%** |
| | `public.kol_directory.engagement_rate` | **1.736** | 5.696 | **23,4%** dari 7.432 |
| `median_views` | `kol_profile_card.median_views` | **30** | 1.948 | **1,52%** |
| `followers_growth` | `kol_profile_card.followers_growth` | **25** | 1.953 | **1,26%** |
| `post_frequency_reliability` | `kol_profile_card.post_frequency_reliability` | **49** | 1.929 | **2,48%** |
| `performance_stability` | `kol_profile_card.performance_stability` | **11** | 1.967 | **0,56%** |

Pendukung: `tier` **1.913 (96,71%)** · `avg_views` 30 (1,52%) ·
`audience_quality_score` 27 (1,37%) · `view_to_follower_ratio` 22 (1,11%) ·
`rate_card_min_fee` **0 (0,00%)**.

Nilai `performance_stability` yang ada: `High Stability` **9** ·
`Medium Stability` **2**.

⚠️ **Outlier ER [DB-LIVE]:** `kol_directory.engagement_rate`
min **0,00** · max **223,41** · avg **2,83** · median **0,60**.
Nilai 223% jelas bukan ER nyata. Normalisasi apa pun perlu clamp atau pembersihan
sumber lebih dulu.

> **Temuan baru yang menguntungkan:** `monitoring_er_pct` terisi **1.012 (51,16%)**
> — jauh lebih baik dari `kol_directory.engagement_rate` (23,4%) dan tidak pernah
> tercatat di audit sebelumnya. Ini kandidat sumber ER terbaik untuk Past
> Performance.

### Data campaign — kosong total **[DB-LIVE]**

`campaigns` **0** · `campaign_kols` **0** · `campaign_kol_deliverables` **0** ·
`campaign_content_performance` **0** · `campaign_orders` **0**.
(`campaign_stages` = 12 baris master workflow, satu-satunya yang terisi.)

| Item | Nilai |
|---|---|
| **Status Past Performance** | ❌ **NOT READY** |
| Archetype | **0 kolom**, 3 kosakata asing, lookup kontradiktif |
| Metrik alternatif | ER **51,16%** · sisanya **0,56%–2,48%** |
| Data campaign historis | **0 baris di 5 tabel** |
| Coverage end-to-end | **0%** |

## C.5 Ringkasan Brand Fit **[DB-LIVE]**

| Component | Data tersedia | Coverage | Status |
|---|---|---:|---|
| **Category Matching** | Creator: `taxonomy_key` ✅ 3.983. Brand: kolom ADA, **0 baris**, kosakata 0% cocok. Matriks 9×9 **ADA** | creator **53,6%** · brand **0%** · **e2e 0%** | ⚠️ **PARTIAL** |
| **Audience Overlap** | Creator: 27 akun; **age 26/27 semua bucket nol**. Brand: **6 kolom ADA** (koreksi), 0 baris | creator **0,36%** (age **0,01%**) · brand **0%** · **e2e 0%** | ❌ **NOT READY** |
| **Values Alignment** | `kol_attribute` **40** ✅. `kol_attribute_map` **0**. Kosakata brand match **25%**. `brand_tone` ADA tapi tanpa lawan creator | creator **0%** · brand-vocab **25%** · **e2e 0%** | ❌ **NOT READY** |
| **Past Performance** | Archetype **0 kolom**. ER **51,16%**, sisanya <2,5%. Campaign **0 baris** | **0,56%–51,16%** · **e2e 0%** | ❌ **NOT READY** |

**`feature.brand_fit_analysis` = 0 baris**, 11 kolom, grain
`UNIQUE (agency_kol_account_id, brand_id)`. FK `fk_brand_fit_analysis_brand` →
`brand(id)` berarti **nol baris brand fit bisa ditulis selama `public.brand`
kosong**, apa pun yang dihitung.

---

# D. CPE

## D.1 Formula yang divalidasi

```
CPE = campaign_kols.deal_price / (likes + comments_count + shares)
```

## D.2 Source & aturan snapshot — diverifikasi di kode

| Aspek | Nilai | Bukti |
|---|---|---|
| Cost | `public.campaign_kols.deal_price` | `COST_CAMPAIGN_KOL` |
| Denominator | `likes + comments_count + shares` | `KOMPONEN_ENGAGEMENT` |
| Dikecualikan | `saves`, `reach`, `views` | `DIKELUARKAN_DARI_ENGAGEMENT` |
| Relasi | `campaign_kols` →1:N→ `campaign_kol_deliverables` →1:N→ `campaign_content_performance` | `sql_cpe_campaign_kol()` |
| Snapshot | `DISTINCT ON (campaign_kol_deliverable_id) ORDER BY is_final DESC NULLS LAST, snapshot_date DESC NULLS LAST, id DESC` | `sql_engagement_per_deliverable()` |
| Guard | `NULLIF(denominator, 0)` → NULL | `sql_cpe_ekspresi()` |

Urutan snapshot **persis** `is_final` → `snapshot_date` → `id`. ✅
Satu baris per deliverable, tidak menjumlahkan antar snapshot. ✅

## D.3 HASIL TEST — dijalankan ke Postgres live **[DB-LIVE]**

```
pytest tests/test_cpe_campaign_kol.py tests/test_cpv_campaign_kol.py \
       tests/test_campaign_cost_metrics.py -q

→ 101 passed in 0.79s          (0 skipped)
```

Sebelum VPN: 77 passed, **24 skipped**. Sekarang **24 test semantik SQL itu
JALAN dan LULUS semua.** Yang mereka buktikan:

| Test | Yang dibuktikan | Hasil |
|---|---|---|
| `test_sql_tidak_double_count_snapshot` | del-1 punya 3 snapshot; hanya baris terakhir dipakai → 342+57, bukan 600+ | ✅ |
| `test_sql_cpe_dihitung_benar` | `cpe = 3.000.000 / 399` | ✅ |
| `test_sql_multiple_deliverable_dijumlahkan` | 2 deliverable, masing-masing sekali | ✅ |
| `test_sql_shares_null_dilaporkan_bukan_disembunyikan` | shares NULL → dihitung 0 **tapi** `deliverable_shares = 0` sebagai penanda | ✅ |
| `test_sql_tanpa_bacaan_performa_cpe_null` | engagement NULL → cpe NULL | ✅ |
| `test_sql_deal_price_null_cpe_null` | deal_price NULL → cpe NULL | ✅ |
| `test_sql_agregasi_jumlah_memberi_angka_berbeda` | aturan agregasi memang mengubah hasil | ✅ |
| `test_sql_python_sepadan` | SQL == `ccm.cpe()` atas angka yang sama | ✅ |
| (+16 test CPV/guard setara) | — | ✅ |

## D.4 VERIFIKASI INDEPENDEN — fixture sendiri, expected dihitung tangan

Supaya vonis tidak hanya bersandar pada test yang ditulis bersama kodenya, gue
bikin fixture terpisah dan menghitung expected-nya manual.

**Fixture** (klausa `VALUES`, tidak menyentuh tabel produksi):

```
ck-A deal_price 6.000.000   deliverable dA1, dA2
ck-B deal_price 1.000.000   deliverable dB1

dA1  3 snapshot kumulatif, semua is_final=false
     2026-01-01 L10 C1  S0    V100
     2026-01-02 L40 C4  S2    V400
     2026-01-03 L90 C9  S1    V900   <- TERBARU
dA2  2 snapshot, yang LEBIH TUA justru is_final=true
     2026-02-01 L50 C5  S5    V500   <- is_final menang
     2026-02-09 L99 C9  S9    V999      (lebih baru, tapi bukan final)
dB1  1 snapshot, shares NULL (pola Instagram)
     2026-03-01 L80 C8  S NULL V1000
```

**Expected dihitung tangan:** dA1→100 eng/900 views · dA2→60/500 · dB1→88/1000
→ ck-A = 160 eng / 1.400 views · ck-B = 88 / 1.000.

**Hasil aktual dari Postgres:**

| ck | engagement | views | CPE aktual | CPE expected | CPV aktual | CPV expected | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| ck-A | **160** | **1.400** | 37.500,0000 | 37.500,0000 | 4.285,7143 | 4.285,7143 | **PASS** |
| ck-B | **88** | **1.000** | 11.363,6364 | 11.363,6364 | 1.000,0000 | 1.000,0000 | **PASS** |

`deliverable_shares` ck-B = **0** → shares NULL **dilaporkan**, bukan disembunyikan. ✅

> **Bagian tersulit dari aturan snapshot lulus:** pada dA2, baris `is_final=true`
> tertanggal **2026-02-01** mengalahkan baris `is_final=false` tertanggal
> **2026-02-09** yang lebih baru. Itu persis yang dimaksud "is_final didahulukan,
> baru snapshot_date". Kalau urutannya terbalik, engagement ck-A akan 60 → 117
> dan CPE-nya salah. **Tidak salah.**

**Bukti aturan agregasi memang menentukan:**

| | baris-terakhir (produksi) | jumlah-semua (salah) | Faktor |
|---|---:|---:|---:|
| ck-A engagement | **160** | 334 | **2,09×** |
| ck-A views | **1.400** | 2.899 | **2,07×** |

**Cek larangan terhadap string SQL produksi:**

| Larangan | Hasil |
|---|---|
| views tidak di penyebut CPE | ✅ OK |
| ER tidak dipakai | ✅ OK |
| rate card tidak dipakai | ✅ OK |
| `campaign_orders` tidak dipakai | ✅ OK |
| tidak ada pengali 1000 | ✅ OK |
| `CPV_UNIT_FACTOR == 1` | ✅ OK |
| cost = `campaign_kols.deal_price` | ✅ OK |
| `subtotal`/`unit_price` deliverable tidak dipakai | ✅ OK |
| urutan `is_final → snapshot_date → id` | ✅ OK |

**Dan SQL produksi dijalankan apa adanya ke schema live:**

```
CPE: EXECUTED OK — 0 baris
     kolom: campaign_kol_id, campaign_id, agency_kol_account_id, deal_price,
            currency, total_engagement, deliverable_count, deliverable_shares, cpe
CPV: EXECUTED OK — 0 baris
     kolom: campaign_kol_id, campaign_id, agency_kol_account_id, deal_price,
            currency, total_views, deliverable_count, cpv
```

Query-nya **sah terhadap schema nyata**; 0 baris semata karena tabel campaign kosong.

**VERDICT INDEPENDEN: PASS.**

## D.5 Test case dari data

| Sumber | Test case CPE | Keterangan |
|---|---:|---|
| DB `kol` | **0** | 5 tabel campaign 0 baris [DB-LIVE] |
| Excel testing | **0 yang bisa dihitung ulang** | §D.6 |

## D.6 ⚠️ Excel testing CPE — memakai formula LAIN

File Excel CPE/CPV yang ada: `docs/brand_match_master.xlsx` → sheet
**`KOL_Database`**, kolom **AN** `Rate Card (IDR)`, **AO** `CPV`, **AP** `CPE`,
**AQ** `CPM`. **30 baris KOL-01..KOL-30** (2 Rate Card NULL → CPE/CPV NULL).
*Tidak ada file Excel lain di project yang memuat expected value CPE/CPV —
dicari di 8 file `docs/`. `docs/filter.xlsx` menyebut CPE/CPV tapi statusnya
`HOLD — belum diimplementasikan`.*

**Verifikasi internal Excel [EXCEL] — 28 baris:**

| Hipotesis formula | Match | Hasil |
|---|---:|---|
| `CPE = Rate ÷ (Avg Views × ER% ÷ 100)` | **28 / 28** | ✅ |
| `CPV = Rate ÷ Avg Views` | **28 / 28** | ✅ |
| `CPV = Rate ÷ Median Views` | **0 / 28** | ❌ |
| `CPM = Rate ÷ Followers × 1000` | **28 / 28** | ✅ |

Contoh: KOL-01 Rate 3.677.000 · AvgViews 46.223 · ER 3,8%
→ CPE = 3.677.000 / (46.223 × 0,038) = **2.093,40**; Excel menulis **2.093**. ✅

**Excel konsisten dengan dirinya sendiri — dengan formula yang SUDAH DITOLAK.**

| | Excel `KOL_Database` | Formula disepakati (13 Sep 2026) |
|---|---|---|
| Cost | `Rate Card (IDR)` | `campaign_kols.deal_price` — **rate card DILARANG** |
| Denominator CPE | `Avg Views × ER% ÷ 100` — **turunan ER** | `likes + comments_count + shares` — **ER DILARANG** |
| Denominator CPV | `Avg Views` roster | `views` snapshot final per deliverable |
| Grain | per KOL roster | per `campaign_kols.id` |
| Snapshot | tidak ada konsep | `is_final` → `snapshot_date` → `id` |

**Test case yang bisa dihitung ulang dari data source: 0 dari 30.** Excel tidak
punya `deal_price`, tidak punya `likes`/`comments`/`shares`, tidak punya
`snapshot_date`/`is_final`, dan KOL-01..30 adalah **creator sintetis**
(`@ardidigital`, `@rifqi.codes`, …) yang **tidak ada** di `kol_directory`.

## D.7 Match / mismatch

| Metrik | Jumlah |
|---|---:|
| Test case Excel (baris ber-Rate Card) | **28** |
| Bisa dihitung ulang dengan formula disepakati | **0** |
| Match | **0** |
| Mismatch | **28** (100%) |
| Test case dari DB | **0** |
| **Test suite repo (Postgres live)** | **101 passed / 0 failed / 0 skipped** |
| **Verifikasi independen** | **PASS** |

### Contoh mismatch

| KOL | Rate | Excel CPE | CPE formula disepakati | Selisih |
|---|---:|---:|---|---|
| KOL-01 | 3.677.000 | **2.093** | tidak terhitung — tidak ada `deal_price` / `likes`+`comments`+`shares` | N/A |
| KOL-11 | 7.793.000 | **5.747** | tidak terhitung | N/A |
| KOL-30 | 19.218.000 | **8.868** | tidak terhitung | N/A |
| KOL-15 | NULL | NULL | NULL | ✅ kebetulan sama-sama NULL |

### Penyebab mismatch — 4, semuanya struktural

1. **Cost berbeda** — rate card vs `deal_price`.
2. **Denominator berbeda** — `Avg Views × ER/100` (estimasi) vs
   `likes + comments + shares` (terukur).
3. **Grain berbeda** — per KOL roster vs per `campaign_kols.id`.
4. **Tidak ada jembatan identitas** — KOL-01..30 sintetis.

## D.8 Vonis CPE

| Lapisan | Vonis |
|---|---|
| **Formula & guard** | ✅ **PASS** |
| **Semantik SQL di Postgres** | ✅ **PASS** — 101/101, aturan snapshot terbukti bekerja di DB nyata |
| **Verifikasi independen (fixture sendiri)** | ✅ **PASS** — expected tangan == hasil Postgres |
| **SQL produksi vs schema live** | ✅ **VALID** — execute OK, 0 baris karena tabel kosong |
| **Validasi vs expected value Excel** | ❌ **FAIL — Excel yang salah, bukan implementasi** |
| **Validasi vs data produksi** | ⛔ **TIDAK BISA** — 0 baris di 5 tabel campaign |

> **CPE BENAR.** Yang tidak ada adalah **data** dan **expected value yang sah**.
> `brand_match_master.xlsx` **tidak boleh** dipakai sebagai expected value CPE.

---

# E. CPV

## E.1 Formula yang divalidasi

```
CPV = campaign_kols.deal_price / views          (per SATU view, tanpa ×1000)
```

## E.2 Rule check **[terverifikasi di Postgres live]**

| Rule | Status | Bukti |
|---|---|---|
| **Tidak ×1000** | ✅ | `CPV_UNIT_FACTOR = 1`; SQL produksi tidak memuat `* 1000`; label wajib `CPV_UNIT_LABEL = "CPV / View"` |
| Tidak pakai engagement sebagai denominator | ✅ | `sql_cpv_campaign_kol()` → `sum(perf.views)` |
| Tidak pakai ER | ✅ | `"engagement_rate" not in sql` |
| Tidak pakai rate card | ✅ | `"unified_rate_card"`/`"rate_card"` absent |
| Tidak pakai `campaign_orders.total_amount` | ✅ | `"campaign_orders" not in sql` |
| Snapshot rule sama dengan CPE | ✅ | **CTE `performa` yang SAMA persis** |
| Guard nol/NULL | ✅ | `NULLIF(views, 0)` → NULL |

CPE dan CPV berbagi satu CTE — desain yang benar: dua salinan aturan snapshot
adalah cara tercepat membuat keduanya diam-diam memakai baris berbeda.

Verifikasi independen (§D.4) membuktikan keduanya memang memakai baris yang
sama: ck-A views **1.400** berasal dari deliverable yang persis sama dengan
engagement **160**.

### Sejarah kesalahan 1.000× — tertutup

| Sumber | Formula lama |
|---|---|
| Excel `KOL_Database.AO` | `Rate ÷ Avg Views` → per 1 view |
| UI `AUTOME_2.html` | `rate / views * 1000` → **per 1K view** |

Selisih **1.000×**. `CPV_UNIT_FACTOR = 1` + test menutup jalur itu.
Ironisnya **satuan** Excel (per 1 view) justru **sama** dengan yang disepakati —
yang berbeda **sumber cost** dan **sumber views**.

## E.3 Test cases

Sama seperti CPE: **101 passed, 0 skipped** di Postgres live, plus verifikasi
independen PASS (ck-A CPV **4.285,7143** == 6.000.000/1.400; ck-B CPV **1.000**
== 1.000.000/1.000).

| Sumber test case dari data | Jumlah |
|---|---:|
| DB `kol` | **0** (5 tabel campaign kosong) |
| Excel `KOL_Database` (28 baris ber-Rate) | **0 yang bisa dihitung ulang** |

## E.4 Match / mismatch

| Metrik | Jumlah |
|---|---:|
| Test case Excel | **28** |
| Bisa dihitung ulang dengan formula disepakati | **0** |
| Match | **0** |
| Mismatch | **28** (100%) |
| **Test suite repo (Postgres live)** | **101 passed** |
| **Verifikasi independen** | **PASS** |

### Contoh mismatch

| KOL | Rate | Avg Views | Excel CPV | Formula disepakati | Selisih |
|---|---:|---:|---:|---|---|
| KOL-01 | 3.677.000 | 46.223 | **79,55** | tidak terhitung — tidak ada `deal_price` / snapshot `views` | N/A |
| KOL-09 | 4.653.000 | 310.647 | **14,98** | tidak terhitung | N/A |
| KOL-30 | 19.218.000 | 83.349 | **230,57** | tidak terhitung | N/A |

### Penyebab mismatch

1. **Cost berbeda** — rate card vs `deal_price`.
2. **Views berbeda** — `Avg Views` roster vs `views` snapshot final per
   deliverable. Beda **konsep**, bukan beda angka.
3. **Grain berbeda** — per KOL roster vs per `campaign_kols.id`.
4. **Tidak ada jembatan identitas** — KOL sintetis.
5. **Satuan: TIDAK berbeda.** Keduanya per 1 view. ✅ Satu-satunya aspek di mana
   Excel dan formula disepakati sejalan.

## E.5 Vonis CPV

| Lapisan | Vonis |
|---|---|
| **Formula & guard** | ✅ **PASS** |
| **Semantik SQL di Postgres** | ✅ **PASS** — 101/101 |
| **Verifikasi independen** | ✅ **PASS** |
| **SQL produksi vs schema live** | ✅ **VALID** |
| **Validasi vs expected value Excel** | ❌ **FAIL** — Excel bukan expected value yang sah |
| **Validasi vs data produksi** | ⛔ **TIDAK BISA** — 0 baris |

---

# F. KESIMPULAN

## F.1 Status ringkas

| Area | Status | Satu kalimat |
|---|---|---|
| **Brand Dummy** | ⚠️ **PARTIAL** | Cukup untuk mendemonstrasikan alur; belum cukup untuk menghasilkan skor — tapi jaraknya **lebih dekat** dari dugaan awal. |
| **Taxonomy** | ❌ **NOT READY** | `taksonomi_kol` dan `kol_categories` dua taxonomy untuk dua hal berbeda; irisan bermakna **0**. |
| **Brand Fit** | ❌ **NOT READY** | 4/4 komponen coverage end-to-end **0%** — semuanya karena **0 baris**, bukan karena kolom tidak ada. |
| **CPE** | ✅ **PASS** | 101/101 di Postgres live + verifikasi independen. Excel bukan expected value yang sah. |
| **CPV** | ✅ **PASS** | Idem; rule "tidak ×1000" tertutup rapat. |

## F.2 Tujuh pertanyaan, tujuh jawaban

### 1. Apakah `brand_dummy` siap untuk testing Brand Fit?

**PARTIAL — siap untuk smoke test alur, belum siap untuk testing hasil.**
Tapi setelah verifikasi live, posisinya **lebih baik** dari dugaan awal.

Yang **cukup**:
- 10 creator nyata, **10/10 punya `agency_kol_account_id`** → kunci Brand Fit
  lengkap dan bisa langsung dipakai (tabel siap pakai di §A.4.3)
- 10/10 punya `taxonomy_key` valid
- 4 brand punya nama, kategori, personality, tone, size tier, archetype
- **Sisi DB sekarang punya kolom untuk 11 dari 11 field brand** yang dibutuhkan

Yang **tidak cukup**:
- File sumber `Brand_Fit_Dummy_Data.xlsx` **tidak ada di repo**
- `Kategori Bisnis` tidak cocok kosakata DB maupun `taksonomi_kol` → 0%
- `Target Demografi` kalimat, bukan nilai terstruktur (kolomnya sudah ada,
  bentuk Excel-nya yang belum)
- **Tidak ada kolom interest** di `brand_dummy`, padahal
  `brand_profile.audience_interests` ADA
- `Performance Archetype` tidak punya kolom di seluruh DB
- `brand_profile` **UNIQUE per organization** → 4 brand dummy tidak bisa jadi 4
  baris di bawah satu org
- Hasilnya sendiri: **0 dari 40 kombinasi measurable**

### 2. Apakah `taksonomi_kol` sudah match dengan DB `kol`?

**TIDAK. Coverage bermakna 0,0%.** Diverifikasi ke DB live.

- `Industry.Category` (11) vs `taxonomy_key` (9): **0 match**
- `Industry.Subcategory` (36) vs `taxonomy_key` (9): **0 match**
- L1+L2 (47) vs `name`+`taxonomy_key` (29): **2 match**, keduanya
  (`Gaming`, `Travel`) **palsu semantik** — beda level, beda domain
- Excel **tidak punya ID/key/level**, hanya label teks
- **Tidak ada tabel pemetaan** kategori di DB (disapu seluruh schema)
- `Follower Size Tier`: 5/5 nama cocok, **3/5 batas berbeda** → mismatch senyap
- `Performance` & `Sentiment Archetype`: **0 kolom** di DB
- `Posting Cadence`: DB simpan angka, bukan label

`Industry` mengklasifikasi **industri brand**; `kol_categories` mengklasifikasi
**niche konten creator**. Keduanya sah, tapi tidak saling menggantikan.

### 3. Bagian Brand Fit mana yang datanya SUDAH siap?

**Tidak satu pun siap end-to-end.** Yang siap adalah potongan — dan potongannya
**lebih banyak** dari dugaan awal:

| Yang sudah siap | Bukti [DB-LIVE] |
|---|---|
| **Kunci matching creator** | **10/10** sample punya `agency_kol_account_id`; relasi **1:1 bersih** (7.431 unik, 0 orphan, 0 multi-agency) |
| Kategori creator | **3.983 / 7.432 (53,6%)** punya ≥1 `taxonomy_key` |
| **Seluruh 11 kolom sisi brand** | `brand_profile` 29 kolom — termasuk `brand_tone`, `target_age_min/max`, `audience_interests`, `performance_targets` |
| **Matriks relevansi 9×9** | `CMP_Lookup_Lists` r346–356; sumbunya **persis** 9 `taxonomy_key` DB live; ambang ≥60 → **25 pasangan related** |
| Taxonomy atribut creator | `public.kol_attribute` **40 baris**, 4 grup, 32 label unik |
| Struktur output | `feature.brand_fit_analysis` 11 kolom, grain terbukti constraint |
| ER creator | `monitoring_er_pct` **1.012 (51,16%)** — temuan baru, coverage terbaik |
| Tier creator | **1.913 (96,71%)** |

### 4. Bagian mana yang masih kurang?

Diurutkan dari yang paling cepat membuka hasil:

| # | Kekurangan | Sifat | Yang dibuka |
|---:|---|---|---|
| 1 | `public.kol_attribute_map` = **0 baris** | Data (kurasi manual) | **Values Alignment** — taxonomy + formula sudah ada |
| 2 | Mapping `Kategori Bisnis` → `taxonomy_key` | **Keputusan bisnis** | Sumbu baris matriks 11d → Category Matching hidup |
| 3 | `brand` / `brand_profile` = **0 baris** | Data | Kolomnya sudah lengkap — tinggal diisi |
| 4 | `brand_profile` UNIQUE per organization | **Keputusan struktur** | **Harus dijawab sebelum baris pertama masuk** |
| 5 | Target demografi Excel berbentuk kalimat | Transform | 3 dari 4 dimensi Audience Overlap bisa di-parse |
| 6 | `brand_dummy` tidak punya kolom interest | **Bentuk data** | Dimensi keempat Audience Overlap |
| 7 | Aturan agregasi multi-kategori (**28,6%** bawa ≥2 key) | **Keputusan bisnis** | Matriks 11d tanpa ambiguitas |
| 8 | Archetype: 0 kolom, 3 kosakata asing, lookup kontradiktif | Struktur + keputusan | Past Performance — atau ganti metrik nyata |
| 9 | `age_gender_breakdown` **26/27 semua bucket nol** | Data (butuh Insights OAuth) | Dimensi age |
| 10 | Audiens creator hanya **27 / 7.432 (0,36%)** | Data | Audience Overlap skala roster |
| 11 | 5 tabel campaign = **0 baris** | Data | Past Performance **dan** CPE/CPV atas data nyata |
| 12 | `brand.category` tanpa CHECK/FK | Struktur | Jaminan kosakata |
| 13 | Batas tier Excel ≠ `kol_tiers` | Data + keputusan | Cegah salah label senyap |
| 14 | Tone brand ada, tone creator tidak ada | **Keputusan Product** | Sumbu Values yang simetris |

### 5. Apakah CPE benar?

**YA — dan sekarang terbukti di Postgres nyata, bukan cuma sebagai string.**

- **101/101 test hijau** (sebelumnya 77 lulus + 24 skip; ke-24 itu kini jalan
  dan lulus semua)
- **Verifikasi independen PASS**: fixture bikinan sendiri, expected dihitung
  tangan, hasil Postgres sama persis — `ck-A CPE 37.500`, `ck-B CPE 11.363,6364`
- Bagian tersulit lulus: `is_final=true` tertanggal lebih tua **mengalahkan**
  snapshot lebih baru yang bukan final
- Aturan agregasi terbukti menentukan: jumlah-semua memberi **2,09×** lipat
- SQL produksi **execute OK** terhadap schema live
- Ketujuh larangan (views/ER/rate card/`campaign_orders`/jumlah snapshot/
  ×1000/subtotal) **semuanya OK**

**Satu catatan:** tidak bisa divalidasi terhadap expected value. Excel yang ada
memakai formula lama (`Rate ÷ (AvgViews × ER/100)`), ditolak eksplisit 13 Sep
2026. Excel konsisten 28/28 dengan formula lamanya sendiri — itu bukti Excel
utuh, **bukan** bukti CPE benar. 0 dari 30 test case bisa dihitung ulang.

### 6. Apakah CPV benar?

**YA, dengan bukti yang sama.** Rule paling rawan — "tidak ×1000" — tertutup di
dua lapis: konstanta `CPV_UNIT_FACTOR = 1` dan test yang menguji nilainya.
Verifikasi independen: `ck-A CPV 4.285,7143` == 6.000.000/1.400 tepat, tanpa
pengali.

CPV berbagi CTE `performa` yang sama dengan CPE — terbukti keduanya memakai baris
snapshot identik. Label `CPV_UNIT_LABEL = "CPV / View"` wajib dipakai UI.

Sama seperti CPE: **0 test case** bisa dihitung ulang dari Excel maupun DB.

### 7. Apa yang perlu diberikan ke Backend?

#### Blocker artefak yang tersisa

| # | Item | Dari | Kenapa |
|---:|---|---|---|
| 1 | **`Brand_Fit_Dummy_Data.xlsx`** | Pembuat POC | Satu-satunya sumber 48 baris control run + 12 dummy creator. Tanpa ini klaim "48/48 reproduced" tidak terverifikasi |
| 2 | **Keputusan grain `brand_profile`** | Backend/Product | UNIQUE per organization vs 4 brand dummy — harus dijawab sebelum baris pertama |
| 3 | **Nilai & lokasi `CATEGORY_RELATEDNESS`** | Backend | Tidak ada di repo ini, tidak ada di DB |
| 4 | **Kosakata `gender_majority`** | Backend | Default `'Any'`, 0 baris → enum-nya belum diketahui |

*(Akses DB **sudah tidak jadi blocker** — semua verifikasi di dokumen ini
dijalankan lewat VPN pada 2026-09-15 05:05 UTC.)*

#### Yang bisa langsung dipakai Backend

| # | Artefak | Lokasi | Kegunaan |
|---:|---|---|---|
| 1 | **10 `agency_kol_account_id` siap pakai** | §A.4.3 | Kunci Brand Fit untuk 10 creator POC, terverifikasi live. Relasi 1:1 bersih |
| 2 | **Matriks relevansi 9×9** | `CMP_Lookup_Lists` r346–356 (disalin §C.1) | Sumbunya persis 9 `taxonomy_key` DB live. Ambang ≥60 → 9 cocok / **25 related** / 47 tidak. **Menjawab blocker "related tidak terdefinisi"** |
| 3 | **29 kolom `brand_profile` + status per field** | §A.6 | Tabel AVAILABLE/MISSING/TRANSFORM lengkap |
| 4 | **28 baris `kol_categories` + rollup 9 key** | §B.2 | Kosakata kanonik creator, dibaca hari ini |
| 5 | **40 baris `kol_attribute` (32 label, 4 grup)** | §C.3 | Kosakata kanonik Values Alignment |
| 6 | **Peta coverage per input** | §C.1–C.4 | Tahu duluan komponen mana yang akan NULL |
| 7 | **Batas `kol_tiers` sesungguhnya** | §B.4 | Cegah salah label Micro/Mid-tier senyap |
| 8 | **`monitoring_er_pct` 51,16%** | §C.4 | Sumber ER dengan coverage terbaik — tidak pernah tercatat sebelumnya |
| 9 | **Bukti Excel CPE/CPV bukan expected value** | §D.6 | 28/28 konsisten dengan formula LAMA |
| 10 | **Fixture verifikasi CPE/CPV independen** | §D.4 | Bisa dijalankan ulang kapan saja; expected dihitung tangan |

#### Aturan yang HARUS ikut dibawa

1. **Missing = NULL, bukan 0.** Terbukti konkret: `age_gender_breakdown` terisi
   27/27 tapi **26 di antaranya seluruh bucket = 0** dengan `unknown: 100`.
   `count()` = 27 akan menipu. Itu **NULL**, bukan "0% umur 18–24".
2. **Cek ketersediaan SEBELUM memanggil `valuesFit()`.** `valuesFit(brand, [])`
   mengembalikan **0**, dan 0 terbaca "tidak cocok" padahal artinya "tidak ada
   yang bisa dicocokkan".
3. **Jangan fuzzy-match kosakata atribut.** `Inspiring` (brand) ≠ `Inspirational`
   (DB). Alias harus diputuskan dan ditulis.
4. **Arah matriks 11d penting** — asimetris pada 3 pasangan. Baris = brand,
   kolom = creator.
5. **Kunci creator selalu UUID, jangan username.** `kol_directory` punya
   `platform_id` sebagai kolom → satu handle bisa punya dua baris.
6. **`CPV_UNIT_LABEL = "CPV / View"` wajib muncul di UI.**
7. **Jangan pakai `brand_match_master.xlsx` sebagai expected value CPE/CPV.**
8. **`brand.category` / `brand_profile.brand_category` tanpa CHECK/FK** —
   kosakatanya tidak dijamin DB. Sepakati sebelum brand pertama masuk.

---

## LAMPIRAN — apa yang dijalankan hari ini

| Perintah | Hasil |
|---|---|
| `Test-NetConnection 10.100.14.216 -Port 5432` | ✅ TcpTestSucceeded (via Pritunl VPN) |
| Sesi Postgres read-only (`transaction_read_only = on`) | ✅ `kol` @ PostgreSQL 16.15 |
| Row count 20 tabel relevan | ✅ |
| Schema penuh `brand` (11 kol) + `brand_profile` (**29 kol**) | ✅ |
| Constraint `brand`, `brand_profile`, `brand_fit_analysis` | ✅ |
| Sapuan kolom `archetype` seluruh schema | ✅ **0 baris** |
| Sapuan tabel pemetaan kategori | ✅ **tidak ada** |
| 28 baris `kol_categories` + rollup + distribusi multi-kategori | ✅ |
| `kol_tiers` batas sesungguhnya | ✅ |
| `kol_attribute` 40 baris per grup | ✅ |
| Relasi `agency_kol_accounts` ↔ `kol_directory` | ✅ 1:1 bersih |
| 10 creator POC → `agency_kol_account_id` | ✅ **10/10** |
| Coverage audience + isi `age_gender_breakdown` | ✅ **26/27 semua bucket nol** |
| Coverage 6 metrik performance `kol_profile_card` | ✅ |
| `pytest` CPE/CPV/cost_metrics | ✅ **101 passed, 0 skipped** |
| SQL produksi CPE + CPV ke schema live | ✅ execute OK |
| Verifikasi independen fixture snapshot | ✅ **PASS** |
| Baca 13 sheet `brand_dummy.xlsx` + 7 sheet `taksonomi_kol.xlsx` | ✅ |
| Hitung ulang 28 baris CPE/CPV/CPM `KOL_Database` | ✅ 28/28 formula lama |
| Matching taxonomy & atribut (exact, tanpa fuzzy) | ✅ |

**Perubahan ke kode / DB / production: NOL.** Seluruh sesi DB read-only.

---
---

# G. BRAND FIT DUMMY DATA MAPPING AUDIT

**Ditambahkan:** 2026-09-15 (sesudah audit §A–F).
**Fokus:** `Brand_Fit_Dummy_Data.xlsx`.
**Sesi DB:** read-only, `kol` @ `10.100.14.216:5432`, PostgreSQL 16.15.
**Perubahan ke DB / schema / source code / formula: NOL.**
Evidence §A–F di atas **tidak diubah dan tidak dihapus**.

---

## G.0 STATUS FILE — sebagian ketemu, sebagian tetap hilang

`Brand_Fit_Dummy_Data.xlsx` **dengan nama itu tidak ada** di mana pun. Dicari:

```
find <project> -iname "*brand*fit*dummy*"        -> 0 hit
Get-ChildItem -Recurse *.xlsx,*.xls,*.xlsm pada:
  ~\Downloads  ~\Desktop  ~\Documents  ~\OneDrive  D:\intern
  disaring nama ~ (brand|dummy|fit)               -> 8 hit
```

Dari 8 hit itu, **satu cocok sebagai sumber sebagian**:

| | |
|---|---|
| **Path** | `C:\Users\user\Downloads\brand dummy.xlsx` |
| **Ukuran** | 6,6 KB (vs `docs/brand_dummy.xlsx` 39,2 KB — **file berbeda**) |
| **Dimodifikasi** | 2026-09-14 12:45 |
| **Sheet** | **1 sheet saja**: `Complete Brand Taxonomy` |
| **Ukuran sheet** | 8 baris × **12 kolom** |

**Kenapa ini diyakini sumbernya:** `brand_dummy.xlsx` → `Source & Evidence`
mengutip `Complete Brand Taxonomy!A2:L2..L5`. Kolom **L = kolom ke-12**, dan
sheet ini memang **tepat 12 kolom** dengan nama sheet identik. Keempat brand-nya
juga sama persis (Kala Basics, Vortex Athletic, Aura Mode, Strive Pro).

### ⛔ Tiga sheet yang dikutip POC TETAP TIDAK ADA

| Sheet dikutip | Untuk apa | Status |
|---|---|---|
| `Brand Fit Scores!A2:H49` | **48 baris control run** — dasar klaim "Values 48/48 REPRODUCED" dan "Partnership 48/48" | ❌ **HILANG** |
| `Dummy Creators!A2:F13` | **12 dummy creator** — sisi creator untuk control run | ❌ **HILANG** |
| `Calculation Mapping` | aturan skoring 5 assessment (dikutip di `POC Methodology` r16–21) | ❌ **HILANG** |

> **Konsekuensi yang harus dibaca Backend:** klaim "formula Values Alignment
> sudah terbukti 48/48" **masih belum bisa diverifikasi siapa pun**, karena
> 48 baris itu ada di sheet yang hilang. Yang berhasil dipulihkan hanya **input
> sisi brand**, bukan **expected output**-nya.

---

## G.1 A. FILE INVENTORY

| Sheet | Rows | Cols | Baris header | Baris data | Fungsi | Relevan Brand Fit? |
|---|---:|---:|---:|---:|---|---|
| `Complete Brand Taxonomy` | 8 | **12** | Excel row **4** | **4 brand** (row 5–8) | Master input sisi brand: identitas, kategori, tier, archetype, demografi, style, personality, tone, format, cadence | ✅ **INTI** |
| *(`Brand Fit Scores`)* | — | — | — | — | 48 baris control run | ⛔ **HILANG** |
| *(`Dummy Creators`)* | — | — | — | — | 12 dummy creator | ⛔ **HILANG** |
| *(`Calculation Mapping`)* | — | — | — | — | aturan skoring | ⛔ **HILANG** |

**Struktur sheet:** row 1 = judul (`KOMPREHENSIF TAKSONOMI BRAND FASHION &
KAMPANYE (DUMMY)`), row 2 = subjudul, row 3 = kosong, **row 4 = header**,
row 5–8 = 4 brand. Header **bukan di baris 1** — parser yang mengasumsikan
baris 1 akan salah baca.

### Profil per kolom **[EXCEL]**

| Col | Nama kolom | Isi | NULL | Unik | Format | Contoh | Relevan Brand Fit? |
|---|---|---:|---:|---:|---|---|---|
| **A** | `Nama Brand (Dummy)` | 4 | 0 | **4** | teks pendek | `Kala Basics` | ✅ identitas |
| **B** | `Kategori Bisnis` | 4 | 0 | **4** | teks bebas | `LifeWear / Everyday Essentials` | ✅ Category Matching |
| **C** | `Size Tier` | 4 | 0 | **3** | label + rentang dalam kurung | `Macro (500K – 1M)` | ⚠️ sifat creator, bukan brand |
| **D** | `Performance Archetype` | 4 | 0 | **4** | teks bebas | `High Reach & Consistent Engagement` | ❌ ditolak DB — §G.9 |
| **E** | `Sentiment Archetype` | 4 | 0 | **4** | teks bebas | `Positive / Functional Satisfaction` | **UNKNOWN** — tidak ada padanan |
| **F** | `Contoh Campaign` | 4 | 0 | **4** | multi-line, bullet `•` + `\n` | `• #KalaSehariHari (…)` | ❌ NOT USED |
| **G** | `Target Demografi` | 4 | 0 | **4** | **kalimat bahasa Indonesia** | `Pria & Wanita (Usia 18–45 tahun), pekerja kantoran urban, keluarga muda` | ✅ Audience Overlap |
| **H** | `Style & Fashion Language` | 4 | 0 | **4** | CSV dalam satu sel | `Clean-cut, Minimalist, Basic, Fungsional` | ⚠️ kandidat `content_styles` |
| **I** | `Brand Personality` | 4 | 0 | **4** | CSV, 4 nilai | `Educational, Authentic, Caring, Modern` | ✅ Values Alignment |
| **J** | `Brand Tone` | 4 | 0 | **4** | CSV, 3 nilai | `Informative, Straightforward, Warm` | ✅ Values Alignment |
| **K** | `Content Format` | 4 | 0 | **4** | CSV dalam satu sel | `Carousel, Short Video (Reels/TikTok), Catalog Grid` | ⚠️ kandidat `format_dominant` |
| **L** | `Posting Cadence` | 4 | 0 | **4** | teks bebas + angka | `Daily / 3-5 posts per week` | ⚠️ kandidat `post_frequency_*` |

**NULL: 0 pada seluruh 12 kolom × 4 baris.**
**Duplicate: 0** — 4 nama brand unik, 4 baris utuh unik.

### 🔎 LIMA kolom yang TIDAK PERNAH diekspos POC

`brand_dummy.xlsx` → `Dummy Brand Input` hanya menampilkan 7 kolom asli
(A, B, C, D, G, I, J). **Lima kolom ini baru terlihat sekarang:**

| Col | Kolom | Nilai (keempat brand) |
|---|---|---|
| **E** | `Sentiment Archetype` | Positive / Functional Satisfaction · Enthusiastic / Brand Loyalty · Trend-Driven / Aesthetic Appreciation · Highly Inspired / Brand Advocacy |
| **F** | `Contoh Campaign` | `• #KalaSehariHari …` · `• Push Your Limit …` · `• Weekly Chic Drop …` · `• #MulaiLangkahmu …` |
| **H** | `Style & Fashion Language` | Clean-cut, Minimalist, Basic, Fungsional · Sporty, Streetwear, Heritage-Retro, Bold accents · High-fashion resemblance, Trend-conscious, Chic · High-performance athletic, Aerodynamic, Street-sport hybrid |
| **K** | `Content Format` | Carousel, Short Video (Reels/TikTok), Catalog Grid · Cinematic Video, High-Res Lookbook, Live Streaming · Aesthetic Reels, High-Fashion Editorial Photo, Story Highlights · Cinematic Long-form, Athlete Testimonial, Interactive Challenge |
| **L** | `Posting Cadence` | Daily / 3-5 posts per week · Daily / 4-6 posts per week + Flash Drop · High Frequency / Daily Drops · 4-5 posts per week + Campaign Burst |

---

## G.2 TEMUAN TERBESAR — COMMENT kolom DB adalah SPESIFIKASI Brand Fit

Ini tidak pernah terbaca di audit mana pun sebelumnya. `public.brand_profile`
membawa `COMMENT` per kolom yang **menyatakan aturan Brand Fit secara eksplisit**.
Dikutip **verbatim** dari DB live:

### `brand_profile` (COMMENT tabel)

> *"What one autometric workspace wants from a creator, in the shape the Brand
> Match Engine scores against. **Replaces `tsdb.public.discover_brand_profiles`,
> which is left in place but is no longer read.** `organization_id` and
> `updated_by` are unenforced UUIDs: their tables live on another server."*

→ Menegaskan aturan "**jangan pakai TSDB**": TSDB memang sengaja ditinggalkan.
→ Menjelaskan kenapa `organization_id` tanpa FK — tabelnya di server lain.

### `performance_targets`

> *"Brand Fit — Past Performance, Option B (direct metric). Object of metric →
> target value, e.g. `{"engagement_rate": 3, "median_views": 50000}`.
> **Recognised keys: `engagement_rate`, `median_views`, `followers_growth`,
> `post_frequency_reliability`, `performance_stability`.** A metric with no
> target is NOT MEASURED, and `{}` means Past Performance as a whole is NOT
> MEASURED. **Deliberately NOT a performance archetype**: the POC showed the
> workbook's archetype pairs contradict one another and cannot be generalised."*

→ **Kelima metric yang diminta di §10 tugas ini PERSIS kelima recognised keys.**
→ **`Performance Archetype` (kolom D) sudah ditolak by design.** Bukan gap —
keputusan yang sudah diambil.

### `brand_tone`

> *"Brand Fit — Values Alignment. Joined with `brand_personality` to form the
> brand attribute set, which is the **DENOMINATOR** of matched/brand × 100.
> Kept separate from `brand_personality` because the two are different questions
> (who the brand is vs how it speaks) and Brand Match reads only the former."*

→ Mengonfirmasi penyebut Values Fit = personality ∪ tone. Sama dengan "# Atribut
= 7" di POC.

### `target_age_min` / `target_age_max`

> *"Brand Fit — Audience Overlap, age dimension. **Inclusive** lower/upper bound
> of the brand target age. **NULL means the brand states no age target, and the
> age dimension is then NOT MEASURED rather than scored 0.**"*

→ Batas **inklusif**. NULL → NOT MEASURED, bukan 0. Konsisten dengan aturan
"missing = NULL, bukan 0".

### ⚠️ `gender_majority` — TIDAK ADA COMMENT

Dari 29 kolom `brand_profile`, hanya **4** yang punya COMMENT (keempat di atas).
**`gender_majority` tidak termasuk.** Lihat §G.5.

---

## G.3 B. BRAND FIELD MAPPING

Legend status: `MATCH` · `PARTIAL` · `MISSING` · `UNKNOWN` ·
`TRANSFORMATION NEEDED` (TN) · `NOT USED`

| Dummy Sheet | Dummy Column | DB Table | DB Column | Mapping Status | Catatan |
|---|---|---|---|---|---|
| Complete Brand Taxonomy | `Nama Brand (Dummy)` | `public.brand` | `name` (varchar) | **MATCH** | 4 nilai unik, 0 null. Salin apa adanya |
| Complete Brand Taxonomy | `Nama Brand (Dummy)` | `public.brand_profile` | `brand_name` (varchar) | **MATCH** | Duplikasi nama di 2 tabel — **butuh keputusan** mana yang otoritatif |
| Complete Brand Taxonomy | `Kategori Bisnis` | `public.brand_profile` | `brand_category` (varchar) | **TN** | Kolom menerima string apa pun (0 CHECK/FK). Tapi agar Category Matching jalan, harus `taxonomy_key` — **0/4 cocok**. §G.6 |
| Complete Brand Taxonomy | `Kategori Bisnis` | `public.brand` | `category` (varchar) | **TN** | Idem |
| Complete Brand Taxonomy | `Kategori Bisnis` | `public.brand_profile` | `preferred_categories` ARRAY(text) | **UNKNOWN** | Tidak ada COMMENT. Arti "kategori creator yang dipilih brand" vs "kategori brand" tidak tertulis → **jangan tebak** |
| Complete Brand Taxonomy | `Target Demografi` | `public.brand_profile` | `gender_majority` (varchar, default `'Any'`) | **PARTIAL / BLOCKED** | Hanya **1 dari 4** brand menyebut gender. Kosakata target tidak terdefinisi. §G.5 |
| Complete Brand Taxonomy | `Target Demografi` | `public.brand_profile` | `target_age_min` (smallint) | **TN** | Regex `(\d{2})\s*[–-]\s*(\d{2})` → **4/4 berhasil**. §G.6 |
| Complete Brand Taxonomy | `Target Demografi` | `public.brand_profile` | `target_age_max` (smallint) | **TN** | Idem, **4/4 berhasil** |
| Complete Brand Taxonomy | `Target Demografi` | `public.brand_profile` | `target_country` (varchar) | **MISSING** | **0 dari 4** menyebut negara. "lokal" bukan nama negara |
| Complete Brand Taxonomy | `Target Demografi` | `public.brand_profile` | `target_city` (varchar) | **MISSING** | **0 dari 4** menyebut kota. "urban" (2/4) adalah tipe wilayah, bukan kota |
| — *(tidak ada kolomnya)* | — | `public.brand_profile` | `audience_interests` ARRAY(text) | **MISSING** | Kolom ADA di DB; **dummy tidak punya kolom interest sama sekali** |
| Complete Brand Taxonomy | `Brand Personality` | `public.brand_profile` | `brand_personality` ARRAY(text) | **TN** | Split `,` → array. 4 nilai/brand, 0 null |
| Complete Brand Taxonomy | `Brand Tone` | `public.brand_profile` | `brand_tone` ARRAY(text) | **TN** | Split `,` → array. 3 nilai/brand, 0 null |
| — *(tidak ada kolomnya)* | — | *(tidak ada kolomnya)* | `brand_values` | **MISSING di kedua sisi** | Dummy tidak punya kolom values; DB tidak punya kolom `brand_values`. §G.10 |
| — *(tidak ada kolomnya)* | — | `public.brand` | `brand_keywords` (jsonb) | **MISSING** | Dummy tidak punya kolom keywords |
| — *(tidak ada kolomnya)* | — | `public.brand_profile` | `brand_keywords` ARRAY(text) | **MISSING** | Idem |
| — *(tidak ada kolomnya)* | — | `public.brand` | `brand_hashtags` (jsonb) | **PARTIAL** | Hashtag **ada terselip** di `Contoh Campaign`: `#KalaSehariHari`, `#MulaiLangkahmu` — hanya **2 dari 4** brand, dan di dalam kalimat |
| — *(tidak ada kolomnya)* | — | `public.brand_profile` | `brand_hashtags` ARRAY(text) | **PARTIAL** | Idem |
| Complete Brand Taxonomy | `Performance Archetype` | `public.brand_profile` | `performance_targets` (jsonb) | **NOT USED** | COMMENT DB: *"Deliberately NOT a performance archetype"*. §G.9 |
| Complete Brand Taxonomy | `Size Tier` | `public.brand_profile` | `preferred_tiers` ARRAY(text) | **UNKNOWN** | Dummy memakai tier sebagai **sifat brand**; nama kolom DB berarti **tier creator yang dipilih**. Tidak ada COMMENT → **jangan samakan** |
| Complete Brand Taxonomy | `Style & Fashion Language` | `public.brand_profile` | `content_styles` ARRAY(text) | **PARTIAL** | 14 nilai unik, **1 cocok** `kol_attribute` (`Minimalist`) = **7,1%**. §G.10 |
| Complete Brand Taxonomy | `Content Format` | *(tidak ada kolom brand)* | — | **MISSING** | Sisi brand tidak punya kolom content format. Sisi creator ada `kol_profile_card.format_dominant` |
| Complete Brand Taxonomy | `Posting Cadence` | *(tidak ada kolom brand)* | — | **MISSING** | Sisi brand tidak punya. Sisi creator ada `post_frequency_*` (numerik) |
| Complete Brand Taxonomy | `Sentiment Archetype` | *(tidak ada di mana pun)* | — | **UNKNOWN** | Tidak ada kolom sentiment di DB. Kosakatanya juga tidak cocok `taksonomi_kol.Sentiment Archetype` (0/4) |
| Complete Brand Taxonomy | `Contoh Campaign` | *(tidak ada)* | — | **NOT USED** | Deskripsi kampanye naratif. Bukan input Brand Fit |
| — | — | `public.brand_profile` | `organization_id` (uuid, NOT NULL, UNIQUE) | **BLOCKED** | Wajib diisi, tapi **tabelnya di server lain** (COMMENT). Nilai untuk dummy tidak diketahui |
| — | — | `public.brand_profile` | `min_followers`, `min_er_pct`, `verified_only`, `require_category`, `caption_terms`, `preferred_platforms` | **NOT USED** | Tidak ada padanan di dummy; punya default |

**Ringkasan status:** MATCH **2** · TRANSFORMATION NEEDED **6** ·
PARTIAL **4** · MISSING **7** · UNKNOWN **4** · NOT USED **3** · BLOCKED **1**.

---

## G.4 Ringkasan 13 field yang diminta

| Field diminta | Kolom DB | Ada kolom? | Ada nilai di dummy? | Status |
|---|---|---|---|---|
| company/brand name | `brand.name` + `brand_profile.brand_name` | ✅ | ✅ 4/4 | **MATCH** |
| `brand_category` | `brand_profile.brand_category` | ✅ | ✅ 4/4 (kosakata salah) | **TN** |
| `brand_keywords` | `brand.brand_keywords` + `brand_profile.brand_keywords` | ✅ | ❌ tidak ada kolom | **MISSING** |
| `brand_hashtags` | `brand.brand_hashtags` + `brand_profile.brand_hashtags` | ✅ | ⚠️ 2/4, terselip di `Contoh Campaign` | **PARTIAL** |
| target_gender / `gender_majority` | `brand_profile.gender_majority` | ✅ | ⚠️ **1/4** | **PARTIAL / BLOCKED** |
| `target_country` | `brand_profile.target_country` | ✅ | ❌ 0/4 | **MISSING** |
| `target_city` | `brand_profile.target_city` | ✅ | ❌ 0/4 | **MISSING** |
| target_interests / `audience_interests` | `brand_profile.audience_interests` | ✅ | ❌ tidak ada kolom | **MISSING** |
| `brand_personality` | `brand_profile.brand_personality` | ✅ | ✅ 4/4 (4 nilai) | **TN** |
| `brand_values` | **tidak ada kolom** | ❌ | ❌ tidak ada kolom | **MISSING (kedua sisi)** |
| `brand_tone` | `brand_profile.brand_tone` | ✅ | ✅ 4/4 (3 nilai) | **TN** |
| `target_age_min` | `brand_profile.target_age_min` | ✅ | ✅ 4/4 | **TN** |
| `target_age_max` | `brand_profile.target_age_max` | ✅ | ✅ 4/4 | **TN** |
| `performance_targets` | `brand_profile.performance_targets` | ✅ | ❌ 0/4 angka target | **MISSING** |

---

## G.5 C. GENDER MAPPING

### Nilai gender di dummy **[EXCEL]**

Gender **tidak punya kolom sendiri** — ia terbenam di dalam kalimat
`Target Demografi`. Hasil ekstraksi:

| Brand | `Target Demografi` (verbatim) | Gender tersurat |
|---|---|---|
| Kala Basics | `Pria & Wanita (Usia 18–45 tahun), pekerja kantoran urban, keluarga muda` | **male + female** |
| Vortex Athletic | `Gen Z & Millennials (Usia 16–30 tahun), pegiat gym, sneakerhead lokal` | **TIDAK DISEBUT** |
| Aura Mode | `Urban Youth & Professionals (Usia 20–35 tahun) yang dinamis dan melek tren` | **TIDAK DISEBUT** |
| Strive Pro | `Pelari, olahragawan, remaja hingga dewasa (17–40 tahun) yang aktif secara fisik` | **TIDAK DISEBUT** |

> **Hanya 1 dari 4 brand (25%) menyebut gender sama sekali** — dan yang disebut
> justru "Pria & Wanita" (= keduanya, setara `Any`). **Tiga brand lainnya diam.**
>
> Diam **bukan** berarti `Any`. Bisa juga "belum diisi". Membedakan keduanya
> adalah keputusan, bukan parsing.

### Pencarian kosakata target — READ-ONLY, empat jalur

| Jalur | Hasil |
|---|---|
| **Enum type di DB** | `SELECT … FROM pg_enum` seluruh DB → **TIDAK ADA satu pun enum type** |
| **CHECK constraint** | `pg_constraint` pada `brand` + `brand_profile` → **0 CHECK** (hanya 1 PK, 1 FK, 1 PK, 1 UNIQUE) |
| **COMMENT kolom** | `gender_majority` → **tidak ada COMMENT** (hanya 4 dari 29 kolom punya) |
| **Data existing** | `brand_profile` **0 baris** → tidak ada contoh nilai |
| **Source code** | Repo ini **tidak punya file `.ts`/`.tsx`/`.js`** sama sekali. Engine (`calculator.ts`) ada di repo Backend — di luar jangkauan |
| **UI prototype** | `app/AUTOME_2.html` + `Autometric-KOL-Module.html` → `gender:'Balanced'`, `gender:'all'`, chip `Female-skewed (60%+)`, `Male-skewed (55%+)`, `Balanced` |

### ⚠️ Kosakata UI itu SUMBU YANG BERBEDA

`Balanced` / `Female-skewed` / `Male-skewed` adalah **skew audiens CREATOR**
(chip filter Discovery, ambang 60%/55%). Itu **bukan** target gender brand.
Memakainya sebagai nilai `gender_majority` berarti menyamakan dua konsep berbeda.

### Yang BISA dinyatakan sekarang

```
Dummy value                          → Engine/DB value
"Pria & Wanita"  (Kala Basics)       → ??? (kandidat: 'Any' / 'All' / 'Both')
(tidak disebut)  (3 brand lain)      → ??? (kandidat: default 'Any' / NULL)
```

| | |
|---|---|
| Satu-satunya nilai yang diketahui DB | **`'Any'`** — dari `DEFAULT 'Any'::character varying` |
| Apakah ada `'Male'` / `'Female'`? | **TIDAK DIKETAHUI** — tidak ada enum, CHECK, COMMENT, maupun baris |
| Apakah kolom menerima NULL? | **YA** — `is_nullable = NO` dengan default… **koreksi: NOT NULL dengan default `'Any'`** → tidak bisa NULL |

> ### 🚫 BLOCKER — DECISION NEEDED
>
> **Kosakata `gender_majority` tidak terdefinisi di mana pun yang bisa diakses.**
> Satu-satunya fakta keras: default `'Any'`, `NOT NULL`, tanpa CHECK.
>
> Yang harus diputuskan Backend:
> 1. Daftar nilai sah — `Any` / `Male` / `Female`? Atau `All` / `Men` / `Women`?
> 2. Brand yang **tidak menyebut gender** → `'Any'` (default) atau ditolak?
> 3. `NOT NULL` berarti "tidak menyebut" **tidak bisa** direpresentasikan sebagai
>    NULL — padahal `target_age_min/max` boleh NULL untuk arti yang sama
>    ("NOT MEASURED"). **Asimetri ini perlu dikonfirmasi disengaja.**
>
> **Sampai dijawab: `gender_majority` = BLOCKED.** Tidak diisi dengan tebakan.

---

## G.6 D. AGE MAPPING

### Ekstraksi dari dummy **[EXCEL]**

Regex `(\d{2})\s*[–\-—]\s*(\d{2})` atas kolom `Target Demografi`:

| Brand | Teks sumber | `target_age_min` | `target_age_max` | Berhasil? |
|---|---|---:|---:|---|
| Kala Basics | "Usia **18–45** tahun" | **18** | **45** | ✅ |
| Vortex Athletic | "Usia **16–30** tahun" | **16** | **30** | ✅ |
| Aura Mode | "Usia **20–35** tahun" | **20** | **35** | ✅ |
| Strive Pro | "(**17–40** tahun)" | **17** | **40** | ✅ |

**4 dari 4 berhasil (100%).** Pemisahnya en-dash `–` (U+2013), bukan hyphen —
parser yang hanya mengenali `-` akan gagal keempatnya.

| Aspek | Hasil |
|---|---|
| Tipe DB | `smallint` — 16/18/20/17 dan 30/35/40/45 **jauh di bawah** batas int2 (32.767) ✅ |
| Semantik | COMMENT DB: **inclusive** bound. Dummy juga inklusif ("Usia 18–45 tahun") ✅ |
| NULL handling | COMMENT DB: NULL → **NOT MEASURED, bukan 0**. Keempat brand punya nilai, jadi tidak terpakai di sini |
| Bucket umur? | **TIDAK ADA** di dummy — hanya rentang bebas. Sesuai: DB juga minta rentang, bukan bucket |

### ⚠️ Pemisahan yang WAJIB dijaga

| | Brand target age | Creator audience age |
|---|---|---|
| **Sumber** | `brand_profile.target_age_min/max` | `feature.*_audience_analysis.age_gender_breakdown` |
| **Bentuk** | **rentang** (smallint, 2 angka) | **bucket distribusi** (`13-17`,`18-24`,`25-34`,`35-44`,`45+`,`unknown`) |
| **Grain** | per brand | per `social_account_id` |
| **Isi dummy** | 4/4 terisi | — |
| **Isi DB** | 0 baris | 27 baris, **26 di antaranya semua bucket = 0** |

> Keduanya **tidak boleh dicampur**. Brand menyatakan *"saya menyasar 18–45"*;
> creator menyatakan *"x% audiens saya 18–24"*. Perbandingannya adalah overlap
> rentang-terhadap-distribusi — dan itu aturan yang **belum tertulis di mana pun**.

**Status Age: READY WITH MAPPING** (transformasi regex, 4/4, deterministik).
Yang belum ada adalah **aturan perbandingannya**, bukan datanya.

---

## G.7 E. CATEGORY MAPPING

### Kategori dummy **[EXCEL]** — 4 nilai, semuanya unik

`LifeWear / Everyday Essentials` · `Athleisure & Sport-Streetwear` ·
`Fast Fashion / Trend-Driven` · `Athletic Performance & Footwear`

### Dicocokkan ke DB **[DB-LIVE]** — exact match, tanpa fuzzy

| Kategori dummy | vs `taxonomy_key` (9) | vs `kol_categories.name` (28) | Hasil |
|---|---|---|---|
| LifeWear / Everyday Essentials | ❌ | ❌ | **NO MATCH** |
| Athleisure & Sport-Streetwear | ❌ | ❌ | **NO MATCH** |
| Fast Fashion / Trend-Driven | ❌ | ❌ | **NO MATCH** |
| Athletic Performance & Footwear | ❌ | ❌ | **NO MATCH** |

**Exact match: 0 dari 4 (0,0%).**

### Possible related category — DILAPORKAN, TIDAK DIPUTUSKAN

Sesuai aturan (*"jangan menentukan angka 100/80/60 sendiri"*), di bawah ini
hanya **pengamatan leksikal**, **bukan** skor dan **bukan** usulan
`CATEGORY_RELATEDNESS`:

| Kategori dummy | `taxonomy_key` yang secara leksikal bersinggungan | Dasar pengamatan | Keputusan |
|---|---|---|---|
| LifeWear / Everyday Essentials | `Lifestyle` (2.511 kreator) · `Fashion` (73) | kata "LifeWear"/"Everyday" ↔ "Lifestyle"; produk = apparel | **BUTUH KEPUTUSAN MANUSIA** |
| Athleisure & Sport-Streetwear | `Fitness` (52) · `Fashion` (73) | "Sport" ↔ Fitness; "Streetwear" ↔ Fashion | **BUTUH KEPUTUSAN MANUSIA** |
| Fast Fashion / Trend-Driven | `Fashion` (73) | kata "Fashion" muncul literal | **BUTUH KEPUTUSAN MANUSIA** |
| Athletic Performance & Footwear | `Fitness` (52) | "Athletic" ↔ Fitness | **BUTUH KEPUTUSAN MANUSIA** |

> ⚠️ Kolom ketiga **bukan** mapping resmi. Tidak ada satu pun angka relatedness
> yang ditetapkan di sini. Keempatnya tetap **NO MATCH** sampai ada keputusan
> tertulis.
>
> Perhatikan juga skalanya: kalau keempat brand jatuh ke `Fashion` (73) dan
> `Fitness` (52), populasi creator yang bisa diskor **sangat kecil** — 125 dari
> 7.432 (**1,7%**), sementara `Lifestyle` + `Beauty` memegang 3.717.

### Infrastruktur taxonomy **[DB-LIVE]**

| Cek | Hasil |
|---|---|
| Tabel pemetaan kategori brand ↔ `taxonomy_key` | **TIDAK ADA** (sapuan `map\|alias\|lookup\|relevan\|related\|taxonom` → hanya `kol_attribute_map`, 0 baris) |
| Kolom penyimpan relatedness/affinity/weight | `public.campaign_stages.weight` saja — **tidak relevan** |
| CHECK/FK yang menjamin kosakata `brand_category` | **0** |
| `category_id` sebagai FK dari brand ke `kol_categories` | **TIDAK ADA** di `brand` maupun `brand_profile` |

→ **`CATEGORY_RELATEDNESS` tidak punya rumah di DB.** Ia hidup di repo Backend.
**Tidak diubah, tidak ditetapkan, tidak diusulkan angkanya.**

**Status Category: BLOCKED.**

---

## G.8 F. CREATOR MAPPING

### Dummy file TIDAK memuat creator

Sheet `Dummy Creators!A2:F13` (12 creator) **hilang** (§G.0). File yang ada
**tidak punya satu pun baris creator**.

→ Creator matching **tidak bisa dilakukan dari `Brand_Fit_Dummy_Data.xlsx`**.

### Yang tersedia: 10 creator dari POC — sudah divalidasi **[DB-LIVE]**

Validasi relasi diulang pada sesi ini:

| Metrik | Nilai |
|---|---:|
| `public.kol_directory` | 7.432 |
| `public.agency_kol_accounts` | 7.431 |
| `kol_account_id` unik | **7.431** |
| `kol_directory` tanpa agency account (**orphan sisi KOL**) | **1** |
| `agency_kol_accounts` tanpa `kol_directory` (**orphan sisi agency**) | **0** |
| KOL terdaftar di >1 agency | **0** |
| **Relasi** | **1:1 bersih** |

FK yang menopang: `agency_kol_accounts_kol_account_id_fkey`
FOREIGN KEY (`kol_account_id`) REFERENCES `kol_directory(id)`.

**10 creator POC — 10/10 valid, ada, dan punya kunci Brand Fit:**

| Username | `kol_directory.id` | `agency_kol_account_id` | taxonomy_key | Orphan? |
|---|---|---|---|---|
| cristiano | `7dd5bd80-…-df04cf57036a` | `917688cb-3cf0-4039-b3a2-22d5d0f2301e` | Fitness | tidak |
| lunamaya | `3491cdd5-…-a88ff2064a08` | `edd19b8d-a591-4665-8168-8b6017bf3fc8` | Beauty | tidak |
| pevpearce | `2a16a2e3-…-336cacfc995e` | `e701102e-13aa-4090-b538-ffdc2d5b4e05` | Lifestyle | tidak |
| sptrakori_ | `6b54df83-…-857de80da254` | `1444c876-b9a2-4fb4-becc-e004ea88ba89` | Entertainment | tidak |
| isyanasarasvati | `6f5d6884-…-8caef8ea3e28` | `3230b006-f88e-49e1-be37-68ab22199726` | Fashion | tidak |
| lambe_turah | `5dc465b4-…-0492f250c66b` | `af802df5-c869-4742-adbf-9b0e592d90fc` | Entertainment | tidak |
| hesfinatia | `8e0cdd34-…-d19a9d32db` | `abcc4f3d-f1c5-4cc3-8769-529dd440707a` | Entertainment | tidak |
| anyageraldine | `d6e669df-…-7c0a2c43cdd1` | `e5a3de7e-cf4a-4863-b143-0fc2812eda38` | Lifestyle | tidak |
| iben_ma | `de7b3261-…-afb68a980420` | `f333d6e7-b165-459f-b2c8-85087012e80c` | Entertainment | tidak |
| inul.d | `740a0e98-…-484173df7bd6` | `21153718-45d2-4b45-9161-86551da4f9a4` | Entertainment | tidak |

**Kunci matching yang ditetapkan dari struktur DB (bukan asumsi):**

```
kol_directory.id → agency_kol_accounts.kol_account_id → agency_kol_accounts.id
                                                        └─> kunci Brand Fit
```

Username **tidak** dipakai: `kol_directory` punya `platform_id` sebagai kolom,
jadi satu handle bisa punya dua baris. UUID satu-satunya yang aman.

**Status Creator: READY** untuk 10 creator POC · **BLOCKED** untuk 12 dummy
creator (sheet hilang).

---

## G.9 G. AUDIENCE MAPPING

Dihitung dengan aturan: **baris ada ≠ data ada**, dan **nilai 0 ≠ data bernilai nol**.

### Sisi BRAND (dari dummy)

| Dimensi | Kolom DB | Nilai di dummy | Status |
|---|---|---|---|
| Gender | `gender_majority` | **1/4** brand menyebut | **PARTIAL / BLOCKED** |
| Age | `target_age_min` / `target_age_max` | **4/4** terparsing | **READY WITH MAPPING** |
| Location | `target_country` / `target_city` | **0/4** — "urban"/"lokal" bukan negara/kota | **MISSING** |
| Interests | `audience_interests` | **0/4** — tidak ada kolomnya | **MISSING** |

### Sisi CREATOR — coverage INFORMATIF untuk 10 creator POC **[DB-LIVE]**

| Username | src | gender known % | age informatif? | geo known % | geo top | interest |
|---|---|---:|---|---:|---|---|
| anyageraldine | ig | 39% | **TIDAK** (semua bucket 0) | 10% | ID | religion (audience) |
| cristiano | ig | 22% | **YA** (total 1,0) | 6% | AR | religion (audience) |
| hesfinatia | tt | 20% | **TIDAK** | 9% | ID | parenting (audience) |
| iben_ma | ig | 38% | **TIDAK** | 14% | ID | religion (audience) |
| inul.d | tt | 27% | **TIDAK** | 12% | ID | religion (audience) |
| isyanasarasvati | ig | 26% | **TIDAK** | 6% | BD | business (audience) |
| lambe_turah | ig | 20% | **TIDAK** | 10% | ID | business (audience) |
| lunamaya | ig | 33% | **TIDAK** | 20% | ID | business (audience) |
| pevpearce | ig | 39% | **TIDAK** | 16% | ID | religion (audience) |
| sptrakori_ | tt | 31% | **TIDAK** | 16% | ID | parenting (audience) |

| Dimensi | Kolom terisi | **Informatif** | Selisih |
|---|---:|---:|---|
| Gender | 10/10 | **10/10** | — |
| **Age** | **10/10** | **1/10** | ⚠️ **9 creator "punya baris" tapi kosong** |
| Location | 10/10 | **10/10** | — |
| Interests | 10/10 | **10/10** | — |

### Bukti age di dua tabel berbeda **[DB-LIVE]**

**`feature.*_audience_analysis.age_gender_breakdown`:**
27 baris terisi, **26 di antaranya kelima bucket = 0** dengan `unknown: 100`.

**`l2_gold.audience_demographics_daily`** — `audience_type` × `dimension_key`:

| audience_type | dimension_key | baris | akun | total `audience_count` |
|---|---|---:|---:|---:|
| `age` | **`18-24`** | 1 | **1** | **1** |
| `age` | `unknown` | 28 | 27 | **2.567** |
| `gender` | `female` | 28 | 27 | 374 |
| `gender` | `male` | 28 | 27 | 366 |
| `gender` | `unknown` | 28 | 27 | 1.828 |

> Dua sumber, kesimpulan sama: **tepat 1 akun dari 27 punya data umur yang
> informatif**, dan nilainya pun hanya `1`.
>
> ⚠️ *Koreksi terhadap dokumen lama:* `docs/deliv.xlsx` menyatakan
> *"audience_demographics_daily tidak punya satu baris pun `audience_type='age'`"*.
> **Itu salah** — ada 29 baris `age`. Tapi **28 dari 29 ber-`dimension_key`
> `'unknown'`**, jadi kesimpulan praktisnya tetap sama.
>
> Perhatikan juga gender: `unknown` = **1.828** vs female+male = **740**.
> **71% bobot gender pun `unknown`** — jadi "gender 10/10 informatif" berarti
> *ada angkanya*, bukan *angkanya lengkap*. Renormalisasi `unknown` adalah
> aturan yang **belum ada**.

**Status Audience: BLOCKED** — brand 2 dari 4 dimensi tidak punya nilai; creator
age praktis kosong (1/27 akun) dan 71% bobot gender `unknown`.

---

## G.10 H. VALUES MAPPING

### Sisi BRAND (dummy) — penyebut Values Alignment

| Brand | personality | tone | gabungan dedup |
|---|---:|---:|---:|
| Kala Basics | 4 | 3 | **7** |
| Vortex Athletic | 4 | 3 | **7** |
| Aura Mode | 4 | 3 | **7** |
| Strive Pro | 4 | 3 | **7** |

Konsisten dengan COMMENT `brand_tone` (*"joined with brand_personality … the
DENOMINATOR"*) dan dengan "# Atribut = 7" di POC.

### `brand_values` — MISSING di KEDUA sisi

| Cek | Hasil |
|---|---|
| Kolom `brand_values` di dummy | **TIDAK ADA** (12 kolom, tidak satu pun values) |
| Kolom `brand_values` di `brand_profile` | **TIDAK ADA** (29 kolom) |
| Kolom `*values*` di seluruh DB | `l0_harmonization.instagram_audience.value`, `l1_silver.unified_audience.value`, `campaign_targets.current_value/target_value` — **nol yang relevan** |
| `attribute_group = 'values'` di `kol_attribute` | **TIDAK ADA** (hanya `creator_personality`, `content_style`, `communication_style`, `visual_style`) |

→ **`brand_values` = MISSING, dan itu konsisten**: tidak ada di dummy, tidak ada
di DB, tidak ada di taxonomy. Bukan gap data — konsep ini memang tidak
diimplementasikan.

### Kosakata brand vs `kol_attribute` **[EXCEL × DB-LIVE]**

| Kolom dummy | Nilai unik | Exact match `kol_attribute` | Coverage |
|---|---:|---:|---:|
| `Brand Personality` + `Brand Tone` | **16** | **4** (Conversational, Educational, Premium, Professional) | **25,0%** |
| — per-brand (penyebut) | 28 | **5** | **17,9%** |
| **`Style & Fashion Language`** (kolom H, baru) | **14** | **1** (`Minimalist`) | **7,1%** |
| **`Content Format`** (kolom K, baru) | **12** | **0** | **0,0%** |

`Content Format` vs `taksonomi_kol.Content Format` (4 nilai): **1 match**
(`Live Streaming`) = 8,3%.

**Hanya di dummy, tanpa padanan DB (12 dari 16):** Aspirational · Authentic ·
Bold · Caring · Formal · Informative · Innovative · Inspiring · Modern ·
Playful · Straightforward · Warm

⚠️ `Inspiring` (dummy) vs `Inspirational` (DB) — **jangan fuzzy-match.**
`kol_attribute_taxonomy.py` sudah punya `ALIAS_BELUM_DIPUTUSKAN` untuk kasus
sejenis (Demonstration/Demonstrative/Demo). Alias harus diputuskan dan ditulis.

### Sisi CREATOR — **SOURCE/MAPPING MISSING**

| Tabel | Baris | Arti |
|---|---:|---|
| `public.kol_attribute` | **40** | master taxonomy ADA (32 label unik, 4 grup) |
| `public.kol_attribute_map` | **0** | **0 kreator ter-mapping** |

Dicek juga untuk 10 creator POC: `#attr` = **0** untuk kesepuluhnya.

→ **Tidak ada satu pun creator yang punya atribut personality/style.**
Tidak ada tabel lain yang menyimpannya (`kol_directory` dan `kol_profile_card`
sudah dikonfirmasi tidak punya kolom style/personality/tone/values).

**Status Values: BLOCKED — `SOURCE/MAPPING MISSING` di sisi creator.**
Formula ada, taxonomy ada, penyebut brand ada. Yang kosong: pembilangnya.

⚠️ Asimetri yang perlu keputusan: sisi brand punya `brand_tone`; sisi creator
**tidak punya `attribute_group` tone**. Jadi 3 dari 7 atribut brand
(= 43% penyebut) **tidak punya sumbu lawan** bahkan setelah `kol_attribute_map`
diisi.

---

## G.11 I. PERFORMANCE TARGET MAPPING

### Bentuk yang diminta DB — dari COMMENT, verbatim

```json
{"engagement_rate": 3, "median_views": 50000}
```

**Recognised keys (5):** `engagement_rate` · `median_views` ·
`followers_growth` · `post_frequency_reliability` · `performance_stability`

Aturan NULL dari COMMENT: *"A metric with no target is NOT MEASURED, and `{}`
means Past Performance as a whole is NOT MEASURED."*

### Isi dummy: NOL angka target

| Kolom dummy | Isi | Bisa jadi `performance_targets`? |
|---|---|---|
| `Performance Archetype` | `High Reach & Consistent Engagement` dll — **4 label teks** | ❌ **NOT USED** — ditolak eksplisit oleh COMMENT |
| `Sentiment Archetype` | 4 label teks | ❌ bukan metric |
| `Posting Cadence` | `Daily / 3-5 posts per week` — teks + angka | ⚠️ lihat bawah |
| *(tidak ada kolom angka target)* | — | **0 angka target di seluruh file** |

### Mapping per metric

| Metric (recognised key) | Target di dummy | Metric source (creator) | Coverage source **[DB-LIVE]** | Status |
|---|---|---|---:|---|
| `engagement_rate` | **TIDAK ADA** | `l2_gold.kol_profile_card.monitoring_er_pct` | **1.012 / 1.978 = 51,16%** | **MISSING (target)** |
| | | `public.kol_directory.engagement_rate` | 1.736 / 7.432 = 23,4% | |
| `median_views` | **TIDAK ADA** | `kol_profile_card.median_views` | **30 / 1.978 = 1,52%** | **MISSING (target)** |
| `followers_growth` | **TIDAK ADA** | `kol_profile_card.followers_growth` | **25 / 1.978 = 1,26%** | **MISSING (target)** |
| `post_frequency_reliability` | ⚠️ `Posting Cadence` (teks) | `kol_profile_card.post_frequency_reliability` | **49 / 1.978 = 2,48%** | **TN + DECISION** |
| `performance_stability` | **TIDAK ADA** | `kol_profile_card.performance_stability` | **11 / 1.978 = 0,56%** | **MISSING (target)** |

### Catatan `Posting Cadence` → `post_frequency_reliability`

Nilai dummy: `Daily / 3-5 posts per week` · `Daily / 4-6 posts per week + Flash
Drop` · `High Frequency / Daily Drops` · `4-5 posts per week + Campaign Burst`.

Ini **frekuensi posting yang diharapkan brand**, sedangkan
`post_frequency_reliability` adalah **keandalan/konsistensi** posting creator —
**bukan hal yang sama**. Memetakan 3-5 posts/week menjadi angka reliability
berarti mengarang skala. **Tidak dilakukan.**
Padanan yang lebih dekat sebenarnya `post_frequency_monthly`/`_daily`, tapi
keduanya **bukan** recognised key.

> **Status Performance Targets: BLOCKED.**
> Kolom ADA, bentuknya TERDOKUMENTASI, 5 recognised key JELAS, dan sumber metric
> creator ADA — tapi **dummy tidak menyediakan satu pun angka target**.
> Sesuai aturan (*"jangan membuat target angka sendiri"*), tidak ada angka yang
> ditetapkan di sini.
>
> Kalau `performance_targets` diisi `{}`, COMMENT menyatakan Past Performance
> **NOT MEASURED** — dan itu perilaku yang sah, bukan kegagalan.

---

## G.12 J. FINAL READINESS

| # | Bagian | Status | Alasan singkat |
|---:|---|---|---|
| A | **File inventory** | **BLOCKED** | 1 dari 4 sheet ketemu; `Brand Fit Scores`, `Dummy Creators`, `Calculation Mapping` hilang |
| B | **Brand field mapping** | **READY WITH MAPPING** | 2 MATCH + 6 TRANSFORMATION NEEDED yang deterministik; sisanya MISSING/UNKNOWN |
| C | **Gender mapping** | **BLOCKED** | Kosakata tidak terdefinisi (0 enum, 0 CHECK, 0 COMMENT, 0 baris); hanya 1/4 brand menyebut |
| D | **Age mapping** | **READY WITH MAPPING** | 4/4 terparsing; tipe & semantik inklusif cocok |
| E | **Category mapping** | **BLOCKED** | 0/4 exact match; tidak ada tabel pemetaan; `CATEGORY_RELATEDNESS` di luar DB |
| F | **Creator mapping** | **READY** (10 POC) / **BLOCKED** (12 dummy) | Relasi 1:1 bersih, 10/10 punya `agency_kol_account_id`; sheet dummy creator hilang |
| G | **Audience mapping** | **BLOCKED** | Brand: 2/4 dimensi nihil. Creator: age informatif **1/27 akun**, gender 71% `unknown` |
| H | **Values mapping** | **BLOCKED** | `kol_attribute_map` = 0 baris → `SOURCE/MAPPING MISSING`. Tone brand tanpa sumbu creator |
| I | **Performance target mapping** | **BLOCKED** | 0 angka target di dummy; archetype ditolak by design |

### VONIS

> # NOT READY — BLOCKERS
>
> **7 dari 9 bagian BLOCKED.** Dua yang siap (**Age**, **Creator/10 POC**) dan
> satu yang READY WITH MAPPING (**Brand field**) tidak cukup untuk menjalankan
> satu pun dari empat komponen Brand Fit secara end-to-end.
>
> **Blocker utama, berurutan:**
>
> 1. **Tiga sheet hilang** — `Brand Fit Scores` (48 baris expected output),
>    `Dummy Creators` (12 creator), `Calculation Mapping` (aturan skoring).
>    Tanpa ini tidak ada **expected value** untuk diuji.
> 2. **`kol_attribute_map` = 0 baris** — Values Alignment mati di sisi creator.
> 3. **Kategori 0/4 match** — Category Matching mati di sisi brand.
> 4. **Kosakata `gender_majority` tidak terdefinisi.**
> 5. **0 angka `performance_targets` di dummy.**
> 6. **`organization_id`** wajib (NOT NULL, UNIQUE) tapi tabelnya di server lain.
> 7. **Grain `brand_profile` UNIQUE per organization** vs 4 brand dummy.

---

## G.13 TIGA OUTPUT PALING PENTING

### 1️⃣ MAPPING YANG SUDAH READY — bisa langsung dipakai Backend

| Mapping | Nilai | Bukti |
|---|---|---|
| **Age** → `target_age_min` / `target_age_max` | Kala Basics **18–45** · Vortex Athletic **16–30** · Aura Mode **20–35** · Strive Pro **17–40** | Regex 4/4; `smallint` muat; COMMENT DB: inklusif — sama dengan dummy |
| **Brand name** → `brand.name` / `brand_profile.brand_name` | Kala Basics · Vortex Athletic · Aura Mode · Strive Pro | 4 unik, 0 null, 0 duplicate |
| **Personality + Tone** → `brand_personality` / `brand_tone` (ARRAY) | 4 + 3 nilai per brand, dedup **7** | Split `,`; cocok dengan COMMENT `brand_tone` (penyebut) |
| **10 `agency_kol_account_id`** | tabel lengkap di §G.8 | Relasi 1:1 bersih, FK nyata, 0 orphan, 10/10 |
| **5 recognised key `performance_targets`** | `engagement_rate`, `median_views`, `followers_growth`, `post_frequency_reliability`, `performance_stability` | COMMENT DB verbatim — **kontrak resmi, bukan tafsiran** |
| **Sumber metric creator + coverage** | ER **51,16%** · median_views 1,52% · followers_growth 1,26% · post_freq_reliability 2,48% · performance_stability 0,56% | Dihitung ke DB live |

### 2️⃣ MAPPING YANG MASIH BUTUH KEPUTUSAN

| # | Item | Pilihan yang tersedia | Kenapa script tidak boleh memutuskan |
|---:|---|---|---|
| 1 | `Kategori Bisnis` → `taxonomy_key` | LifeWear→`Lifestyle`/`Fashion`? Athleisure→`Fitness`/`Fashion`? Fast Fashion→`Fashion`? Athletic→`Fitness`? | Menentukan ini = menentukan skor Category Matching. **Keputusan bisnis** |
| 2 | Brand tanpa gender tersurat (3/4) | `'Any'` (default) vs tolak vs tandai belum diisi | `NOT NULL` menutup opsi NULL — asimetris dengan age yang boleh NULL |
| 3 | Nama brand di dua tabel | `brand.name` vs `brand_profile.brand_name` | Tidak ada FK antara keduanya; dua sumber kebenaran |
| 4 | `Size Tier` → `preferred_tiers` | samakan vs jangan | Dummy = sifat brand; kolom DB = tier creator yang dipilih. **Semantik berbeda** |
| 5 | `Style & Fashion Language` → `content_styles` | isi apa adanya (7,1% cocok) vs alias dulu | Mengalias `Clean-cut`→`Minimalist` = mengarang taxonomy |
| 6 | `Inspiring` vs `Inspirational` | alias vs biarkan tidak cocok | `ALIAS_BELUM_DIPUTUSKAN` sudah jadi preseden |
| 7 | Aturan banding rentang-brand vs bucket-creator (age) | — | Belum tertulis di mana pun |
| 8 | Renormalisasi `unknown` (gender 71%, geo 80–94%) | — | Belum ada aturan |
| 9 | `Posting Cadence` → metric mana | `post_frequency_reliability` (recognised) vs `post_frequency_monthly` (bukan recognised) | Konsep beda: ekspektasi vs keandalan |
| 10 | `Sentiment Archetype`, `Contoh Campaign` | pakai vs buang | Tidak ada kolom tujuan; arti untuk Brand Fit **UNKNOWN** |

### 3️⃣ EXACT BLOCKER — yang harus ditanyakan ke mentor/Backend

> **B-1 — Tiga sheet hilang.**
> Minta `Brand_Fit_Dummy_Data.xlsx` **utuh**: `Brand Fit Scores!A2:H49`,
> `Dummy Creators!A2:F13`, `Calculation Mapping`.
> Yang beredar (`~\Downloads\brand dummy.xlsx`) **hanya** `Complete Brand
> Taxonomy`. **Tanpa `Brand Fit Scores` tidak ada expected value**, jadi klaim
> "Values 48/48 REPRODUCED" tetap tidak terverifikasi.
> *Ditanyakan ke:* pembuat POC.

> **B-2 — Kosakata `gender_majority`.**
> Daftar nilai sah? (`Any`/`Male`/`Female`? `All`/`Men`/`Women`?)
> Brand yang tidak menyebut gender → `'Any'` atau ditolak?
> Kenapa `NOT NULL` padahal `target_age_min/max` boleh NULL untuk arti yang sama
> ("NOT MEASURED")?
> *Bukti:* 0 enum, 0 CHECK, 0 COMMENT, 0 baris, default `'Any'`.
> *Ditanyakan ke:* Backend.

> **B-3 — Mapping kategori brand → `taxonomy_key`.**
> 4 kategori dummy, **0 exact match**. Tidak ada tabel pemetaan di DB.
> Siapa yang menetapkan, dan di mana disimpan (tabel DB atau konstanta Backend)?
> Catatan skala: kalau jatuh ke `Fashion`+`Fitness`, populasi ter-skor hanya
> **125 / 7.432 = 1,7%**.
> *Ditanyakan ke:* Product + Backend.

> **B-4 — `organization_id`.**
> `NOT NULL` + `UNIQUE`, tapi COMMENT bilang tabelnya **di server lain**.
> UUID mana yang dipakai untuk testing? Dan karena `UNIQUE (organization_id)`,
> **4 brand dummy tidak bisa jadi 4 baris di bawah satu organization** —
> apakah dibuat 4 organization, atau grain-nya memang begitu?
> *(Grain tidak diubah dalam audit ini.)*
> *Ditanyakan ke:* Backend.

> **B-5 — `kol_attribute_map` = 0 baris.**
> Siapa yang mengisi, dan kapan? Ini **satu-satunya** blocker Values Alignment —
> taxonomy (40 baris) dan formula sudah ada.
> Sekalian: sisi creator **tidak punya `attribute_group` tone**, padahal
> `brand_tone` menyumbang 3 dari 7 penyebut (**43%**). Apakah tone creator akan
> ditambahkan, atau penyebut dikurangi?
> *Ditanyakan ke:* Backend + yang menangani kurasi.

> **B-6 — Angka `performance_targets`.**
> Dummy tidak punya satu pun angka target. Siapa yang menetapkan nilai untuk
> kelima recognised key? Atau Past Performance sengaja dibiarkan `{}` =
> NOT MEASURED selama testing?
> *(Tidak ada angka yang ditetapkan dalam audit ini.)*
> *Ditanyakan ke:* Product.

> **B-7 — `CATEGORY_RELATEDNESS`.**
> Tidak ada di repo ini, **tidak ada di DB** (sapuan
> `related|relevan|affinity|similarity|weight|matrix` → hanya
> `campaign_stages.weight` yang tidak relevan). Di file mana konstanta itu
> hidup, dan berapa nilainya?
> *(Tidak dibuat dan tidak diubah dalam audit ini.)*
> *Ditanyakan ke:* Backend.

---

## G.14 LAMPIRAN — perintah yang dijalankan (section G)

| Perintah | Hasil |
|---|---|
| `find` project untuk `*brand*fit*dummy*` | **0 hit** |
| `Get-ChildItem -Recurse` pada Downloads/Desktop/Documents/OneDrive/D:\intern | 8 hit, **1 relevan** |
| Baca `~\Downloads\brand dummy.xlsx` (openpyxl, read-only) | 1 sheet, 8×12 |
| Profil 12 kolom: isi/null/unik/format/contoh | ✅ 0 null, 0 duplicate |
| Parsing `Target Demografi` → gender/age/lokasi | gender **1/4** · age **4/4** · lokasi **0/4** |
| `pg_constraint` pada `brand` + `brand_profile` | **0 CHECK** |
| `pg_enum` seluruh DB | **0 enum type** |
| `col_description` 29 kolom `brand_profile` | **4 kolom ber-COMMENT** — spesifikasi Brand Fit |
| `col_description` 11 kolom `feature.brand_fit_analysis` | 6 kolom ber-COMMENT |
| Sapuan kolom `gender` seluruh DB | 11 kolom |
| `gender_breakdown` → kunci jsonb | `female` / `male` / `unknown` |
| `audience_demographics_daily` audience_type × dimension_key | age: `18-24` **1 akun** · `unknown` 27 akun |
| Coverage audiens informatif 10 creator POC | gender 10/10 · **age 1/10** · geo 10/10 · interest 10/10 |
| Relasi `agency_kol_accounts` ↔ `kol_directory` | 1:1 bersih, 1 orphan sisi KOL, 0 sisi agency |
| 10 creator POC → `agency_kol_account_id` | **10/10** |
| Sapuan tabel/kolom relatedness | **tidak ada** |
| Matching kolom H & K vs `kol_attribute` / `taksonomi_kol` | H **1/14** · K **0/12** (vs taksonomi **1/12**) |
| Grep `gender_majority` di UI prototype | `Balanced`/`Female-skewed`/`Male-skewed` — **sumbu creator, bukan brand** |

**Perubahan ke DB / schema / source code / formula / taxonomy: NOL.**
Sesi DB read-only (`transaction_read_only = on`). Tidak ada commit, tidak ada push.
