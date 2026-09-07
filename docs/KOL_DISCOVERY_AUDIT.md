# KOL Discovery — Audit Add KOL, Discovery & Filter

**Read-only audit · 2026-09-03**

| Sumber | Detail |
|---|---|
| Aplikasi | `github.com/devsekata/autometric` — branch **`discover/data-terukur-kol`** (`b5093e2`) |
| Prototype filter | `app/AUTOME_2.html` (repo `scrapper-project`) |
| Database | `kol` @ 10.100.14.216 — sesi `set_session(readonly=True)` |
| Populasi | `public.kol_directory` = **7.720** |
| Spreadsheet | `docs/KOL_DISCOVERY_AUDIT.xlsx` (3 sheet: ADD_KOL · KOL_DISCOVERY · FILTER) |

> **Branch penting.** Branch `main` **tidak memuat KOL Discovery sama sekali** — tidak
> ada satu pun file ber-nama `kol`/`discover` di `src/`. Seluruh implementasi ada di
> branch `discover/data-terukur-kol`. Audit ini memakai branch itu.

**Tidak ada perubahan apa pun yang dilakukan:** tanpa modifikasi kode, database,
schema, migration, UI, tanpa perbaikan bug, tanpa commit/push. Database hanya
diakses lewat `SELECT`.

### Ringkasan status

| Status | ADD_KOL | KOL_DISCOVERY | FILTER |
|---|---:|---:|---:|
| CLEAR | 1 | 19 | 0 |
| PARTIAL | 2 | 7 | 13 |
| MISMATCH | 2 | 4 | 2 |
| BLOCKED | 0 | 0 | 6 |
| NOT AVAILABLE | 14 | 2 | 7 |
| NEEDS VERIFICATION | 3 | 3 | 0 |
| **Total baris audit** | **22** | **35** | **28** |

---

# 1. ADD KOL

## 1.1 Flow

Flow Add KOL **berhenti di langkah pertama**.

```
User membuka KOL Directory
  └─> Tombol "Add KOL" tampil di header            ✅ ada
        └─> Klik
              └─> flash('Form tambah KOL dibuka')  ⟵ toast 2,2 detik
                    └─> SELESAI. Tidak ada apa-apa lagi.
```

`KolDirectoryPage.tsx:472`:

```tsx
<Btn kind="primary" icon="person_add" onClick={() => flash('Form tambah KOL dibuka')}
  title="Register a new influencer">
  Add KOL
</Btn>
```

`flash` (baris 234–237) hanya `setToast(msg)` lalu `setTimeout(() => setToast(null), 2200)`.

Tidak ada form, modal, input, validasi, submit, loading, success, maupun error state.
Karena tidak ada data yang ditulis, tidak ada KOL yang masuk Discovery dan tidak ada
yang bertahan setelah reload.

## 1.2 UI Element

| Element | Muncul? | Berfungsi? | Status |
|---|---|---|---|
| Tombol "Add KOL" | Ya | Hanya toast | **MISMATCH** |
| Form / modal | Tidak | — | **NOT AVAILABLE** |
| Platform selector | Tidak | — | **NOT AVAILABLE** |
| Input username / URL | Tidak | — | **NOT AVAILABLE** |
| Validation & error message | Tidak | — | **NOT AVAILABLE** |
| Preview / profile picture | Tidak | — | **NOT AVAILABLE** |
| Loading / success / error state | Tidak | — | **NOT AVAILABLE** |

## 1.3 Button / Action

| Action | Expected | Actual | Handler | API | Status |
|---|---|---|---|---|---|
| Add KOL | Buka form | Toast | `flash()` | — | **MISMATCH** |
| Submit / Cancel / Back / Close / Retry / Remove | — | Tidak ada | — | — | **NOT AVAILABLE** |

## 1.4 Data yang disimpan & DB mapping

**Tidak ada data yang disimpan dari UI ini.** Bukti:

- `route.ts:15` — route `kol-directory` hanya mengekspor `GET`. Tidak ada `POST`/`PUT`/`PATCH`.
- `grep "INSERT INTO kol_directory"` di `src/` dan `migrations/` → **0 hasil**.
- `grep "AddKol|addKol|add-kol|Add KOL"` di seluruh `src/` → **1 hit**, yaitu tombolnya sendiri.

Kolom DB yang *seharusnya* diisi Add KOL, beserta kondisinya sekarang:

| UI Field (seharusnya) | DB Table | DB Column | Terisi |
|---|---|---|---:|
| username | `public.kol_directory` | `username` | 7.497 (97,1%) |
| profile URL | `public.kol_directory` | `profile_url` | 7.498 (97,1%) |
| platform | `public.platforms` | `key` | 2 baris (IG, TT) |
| avatar | `public.kol_directory` | `avatar_url` | **931 (12,1%)** |
| category | `public.kol_categories` | `category_ids` / `name` | 4.174 (54,1%) |
| followers / ER | `public.kol_directory` | `followers_count`, `engagement_rate` | 7.498 / 1.756 |
| display name | `l2_gold.kol_profile_card` | `display_name` | 1.958 (25,4%) |
| relasi akun | `public.kol_social_account`, `public.social_account` | `kol_id`, `social_account_id` | 7.496 (1:1) |

## 1.5 Temuan penting — flow ini PERNAH berjalan, dari tempat lain

Database memuat bukti bahwa Add KOL pernah dijalankan, tetapi **bukan** dari kedua
repo yang saya akses:

| Bukti | Nilai |
|---|---|
| `kol_directory.source` | `excel_import` 7.718 · **`manual_add` 2** |
| KOL manual | `raditya_dika` (2026-08-27) · `sekata_ai` (2026-08-28) — keduanya `scrape_status='success'`, punya avatar |
| `public.add_kol_pipeline_log` | **18 baris**, 6 step × 3 run, semua `success`: `sync_profile`, `sync_follower`, `sync_post`, `build_unified_profile`, `build_unified_follower`, `build_unified_post` |
| `public.add_kol_scrape_log` | **9 baris** |

Kedua tabel log itu **tidak direferensikan di repo `autometric` maupun `scrapper-project`**
(diverifikasi dengan grep di `src/`, `migrations/`, dan seluruh `*.py`/`*.sql`).

> **NEEDS VERIFICATION** — ada service/codebase ketiga yang mengimplementasikan Add KOL.
> Lokasinya perlu dikonfirmasi sebelum menyimpulkan fitur ini "tidak ada".

## 1.6 Issues

| # | Issue | Status |
|---|---|---|
| A1 | Tombol Add KOL hanya menampilkan toast, tanpa form apa pun | **MISMATCH** |
| A2 | Toast "Form tambah KOL dibuka" berpotensi menyesatkan — terlihat seperti aksi berhasil | **MISMATCH** |
| A3 | Tidak ada endpoint POST dan tidak ada `INSERT` ke `kol_directory` | **NOT AVAILABLE** |
| A4 | Tidak ada validasi duplikat, padahal DB sudah memuat **277 grup** `username_normalized` duplikat | **NOT AVAILABLE** |
| A5 | Implementasi Add KOL yang sebenarnya berada di luar kedua repo | **NEEDS VERIFICATION** |

---

# 2. KOL DISCOVERY

Berbeda dari Add KOL, halaman ini **benar-benar terhubung ke database** dan sebagian
besar berjalan sebagaimana mestinya: 19 dari 35 item berstatus CLEAR.

## 2.1 UI / Page

| Bagian | Status | Catatan |
|---|---|---|
| Halaman KOL Directory | **CLEAR** | Terhubung DB lewat `kolDb()` |
| Header jumlah creator | **CLEAR** | `COUNT(*) OVER()` |
| Search box | **PARTIAL** | Hanya `username` |
| Filter sidebar (8 section) | **PARTIAL** | Sebagian kontrol `disabled` |
| List/grid (card + table) | **CLEAR** | |
| Loading / Error / Empty state | **CLEAR** | Ketiganya ada |
| Pagination | **CLEAR** | `page`, `pageSize` default 20 |
| Sorting | **CLEAR** | Whitelist kolom — aman dari injection |
| Facets | **CLEAR** | Hanya di-load sekali |
| Otorisasi | **CLEAR** | `requireOrgMemberById` → 401 |

Chain lengkap: **UI** `KolDirectoryPage.tsx` → **API** `GET /api/organizations/[id]/discover/kol-directory`
→ **Query** `src/lib/discover/kolDirectory.ts` (`BASE` + `filtered`) → **DB** `public.kol_directory` (+ join).

## 2.2 KOL Card — field per field

| Field | DB Column | Coverage | Status |
|---|---|---:|---|
| Username | `kol_directory.username` | 97,1% | **CLEAR** |
| Platform | `platforms.key` | 97,1% | **CLEAR** |
| Followers | `kol_directory.followers_count` | 97,1% | **CLEAR** |
| Profile URL | `kol_directory.profile_url` | 97,1% | **CLEAR** |
| Agency | `agency_kol_accounts` + `agencies` | 7.719 | **CLEAR** |
| Tier | `kol_tiers` (JOIN rentang follower) | 93,2% | **CLEAR** |
| Avatar | `kol_directory.avatar_url` | **12,1%** | **PARTIAL** |
| Engagement Rate | `kol_directory.engagement_rate` | 22,7% | **PARTIAL** |
| Category | `kol_categories.name` (mentah) | 54,1% | **PARTIAL** |
| Bio | `kol_directory.bio` | 11,7% | **PARTIAL** |
| Data status badge | `last_refreshed_at` + `engagement_rate` | — | **PARTIAL** |
| **Display name** | `kol_profile_card.display_name` | 25,4% tersedia | **MISMATCH** |
| **Verified badge** | `kol_directory.verified_status` | 454 | **MISMATCH** |
| **Rate card** | `l1_silver.unified_rate_card.fee` | **0 baris** | **MISMATCH** |
| City | `kol_directory.creator_city` | **0** | **NOT AVAILABLE** |

## 2.3 Verifikasi UI vs DB

**Sample (3 KOL follower terbesar):**

| Username | DB followers | DB ER | DB verified_status | Tier (JOIN) | Avatar |
|---|---:|---:|---|---|---|
| `instagram` | 685.896.635 | 0,07 | verified | Mega | ada |
| `cristiano` | 679.264.838 | 2,21 | verified | Mega | ada |
| `leomessi` | 516.185.245 | 2,66 | verified | Mega | ada |

Nilai yang dirender UI diturunkan langsung dari kolom-kolom ini (`fmtNum` untuk
follower, `toFixed` untuk ER), jadi **sesuai setelah formatting**.

**Sebaran Data Status badge** — logikanya benar, tetapi hasilnya timpang:

| Badge | KOL |
|---|---:|
| Estimated | 5.964 (77,3%) |
| Calculated | 1.755 |
| **Live** | **1** |

## 2.4 Profile Picture

| Pertanyaan | Jawaban |
|---|---|
| Muncul? | Ya, bila `avatar_url` ada |
| Source | `public.kol_directory.avatar_url` |
| URL valid? | **931 dari 931 berskema `http(s)`** — tidak ada yang rusak formatnya |
| Coverage | **931 / 7.720 = 12,1%** — 87,9% KOL tidak punya avatar |
| Fallback | Ya — inisial username |

Implementasi (`ui.tsx:307–324`) memakai `<img>` biasa dengan `referrerPolicy="no-referrer"`
dan `onError` yang menandai URL rusak lalu jatuh ke inisial. Karena bukan `next/image`,
`remotePatterns` di `next.config.ts` tidak berlaku untuk avatar roster.

**Status: PARTIAL**, bukan MISMATCH — fallback-nya bekerja; yang kurang adalah datanya.

## 2.5 Button & Interaction

| Action | Status | Catatan |
|---|---|---|
| Compare · Clear search · Collapse sidebar | **CLEAR** | |
| Search · Filter | **PARTIAL** | Lihat §2.1 dan bagian 3 |
| **Add KOL** | **MISMATCH** | Toast saja |
| **Favorite** | **NOT AVAILABLE** | State lokal; **tidak ada tabel** favorit/shortlist di DB |
| Reset filter · View detail · Export | **NEEDS VERIFICATION** | Dinilai dari kode; belum dijalankan di browser |

## 2.6 Issues

| # | Issue | Status |
|---|---|---|
| D1 | **Rate card selalu kosong.** Komentar `kolDirectory.ts:44` menyatakan *"`l1_silver.unified_rate_card` prices 7,230 of them"*, padahal tabelnya **0 baris** | **MISMATCH** |
| D2 | **Verified memakai definisi berbeda dari pipeline.** App: `verified_status` (454 KOL). Business rule migration 006/011/020: `social_account.oauth_token IS NOT NULL` (**0 KOL**) | **MISMATCH** |
| D3 | **Display name tidak ditampilkan** walau tersedia untuk 1.958 KOL | **MISMATCH** |
| D4 | `creator_city` diambil query sebagai `city` tetapi 0% terisi | **NOT AVAILABLE** |
| D5 | Avatar hanya 12,1% | **PARTIAL** |
| D6 | ER punya **83 nilai mustahil** (>10%, maks 223,41%) yang ikut ditampilkan | **PARTIAL** |
| D7 | Kategori memakai 28 nama mentah, belum memakai `taxonomy_key` (9 Discovery Category) | **PARTIAL** |
| D8 | Favorite tidak persist — tidak ada tabelnya | **NOT AVAILABLE** |
| D9 | Search tidak menyertakan `display_name` dan `bio` yang datanya ada | **PARTIAL** |

---

# 3. FILTER

Sumber inventaris: **sidebar `AUTOME_2.html`** — `FPG` (baris 3554) dan `fpBody()` (baris 3585).
Ditemukan **6 grup berisi 28 filter**. Seluruhnya dimasukkan, tidak ada yang dilewatkan.

> **Catatan lingkungan.** Seluruh filter di `AUTOME_2.html` berjalan pada **8 KOL mock**
> (`const KOLS`, baris 608). File ini punya **0 network call** (`fetch|XMLHttpRequest|axios` = 0),
> jadi *functionality testing* terhadap database tidak mungkin dilakukan dari prototype.
> Kolom "Actual Behavior" karena itu berisi kondisi itu, dan kolom DB/Coverage diverifikasi
> langsung ke database.

## 3.1 Inventaris per grup

| Grup | Filter |
|---|---|
| **Creator Profile** (8) | Platform · Kategori KOL · KOL Tier · Female-skewed · Male-skewed · Verified only · Age · Location |
| **Audience** (3) | Audience location · Audience interest · Audience Quality |
| **Content** (3) | Content Category/Topic · Content Format · Content Style & Personality |
| **Performance** (7) | Engagement Rate · Save Rate · Share Rate · Views · Reliability · Performance Stability · Viral Frequency |
| **Growth** (2) | Growth Classification · Rising Creator |
| **Data Freshness & Monitoring** (5) | Data Status · Last Updated · Update Frequency · Next Update · Monitoring Priority |

## 3.2 Ringkasan status

| Status | Jumlah | Filter |
|---|---:|---|
| **PARTIAL** | 13 | Platform · Kategori · Female-skewed · Male-skewed · Audience location · Audience interest · Audience Quality · Content Format · Engagement Rate · Save Rate · Share Rate · Views · Last Updated |
| **NOT AVAILABLE** | 7 | Age · Location kreator · Content Category/Topic · Content Style · Reliability · Update Frequency · Monitoring Priority |
| **BLOCKED** | 6 | Performance Stability · Viral Frequency · Growth Classification · Rising Creator · Data Status · Next Update |
| **MISMATCH** | 2 | KOL Tier · Verified only |
| **CLEAR** | **0** | — |

**Tidak ada satu filter pun berstatus CLEAR.** Filter dengan coverage terbaik
(Platform 97,1%) pun tetap PARTIAL karena chip **YouTube** tidak punya baris di
tabel `platforms`.

## 3.3 Dua MISMATCH

> **✅ RESOLVED 2026-09-07 — kedua mismatch di bawah sudah ditutup.**
> Isi section ini dibiarkan apa adanya sebagai catatan temuan; yang berlaku sekarang
> adalah dua putusan berikut.
>
> | Mismatch | Putusan |
> |---|---|
> | **KOL Tier** | Ambang `public.kol_tiers` **dibetulkan** (migration 033): Mid-tier jadi 50.000–499.999, Macro jadi 500.000–999.999. Tidak ada lagi dua versi ambang. Macro sekarang **187**, Mid-Tier **1.809** |
> | **Verified only** | Definisi app **dibuang**. Discovery memakai Connected = `social_account.platform_user_id IS NOT NULL AND oauth_token IS NOT NULL` → **0 KOL**, dan itu benar. Badge `verified_status` (454) tidak lagi jadi field Discovery |

**KOL Tier** — batas UI berbeda dari tabel `kol_tiers`:

| Tier | Batas prototype | Batas `kol_tiers` |
|---|---|---|
| Mid-tier | 50K–500K | 50.000–99.999 |
| Macro | 500K–1M | 100.000–999.999 |

Akibatnya nyata: "Macro" = **191 KOL** menurut batas UI, tetapi **1.290 KOL** menurut
batas DB — selisih 6,8×. App nyata memakai batas DB.

**Verified only** — dua definisi bertabrakan untuk konsep yang sama:

| Sumber | Definisi | Hasil |
|---|---|---:|
| Pipeline (migration 006/011/020) | `social_account.oauth_token IS NOT NULL` | **0 KOL** |
| App (`kolDirectory.ts:157`) | `LOWER(verified_status) IN ('verified','true','yes')` | **454 KOL** |

Keduanya tidak bisa benar bersamaan. Perlu keputusan definisi.

**Keputusan (2026-09-07):** yang dipakai definisi pipeline, diperketat jadi
`platform_user_id` **dan** `oauth_token` harus sama-sama terisi di baris
`social_account` yang sama. Definisi app (`verified_status`) dihapus dari Discovery
— beserta 454 badge yang dulu tampil di kartu dan tabel.

## 3.4 Enam BLOCKED

Seluruhnya terblokir **data**, bukan schema:

| Filter | Penghambat |
|---|---|
| Growth Classification | `followers_growth` = LAG snapshot-to-snapshot berjarak **10 & 13 hari**, bukan 30. Rentang −0,051% s.d. +0,917% → 3 dari 4 bucket selalu 0 |
| Rising Creator | Threshold growth ≥5,5% = **6× nilai tertinggi** di DB. Momentum butuh ≥3 snapshot; **0 akun** punya |
| Performance Stability | Butuh ≥4 titik bulanan; hanya **5 KOL** |
| Viral Frequency | Sumber & penghambat identik |
| Data Status | Penyebut rumus tidak ada: `refresh_tier` 0/7.720, `scheduler_config` 0 baris |
| Next Update | Terblokir penyebut yang sama |

## 3.5 Filter yang app-nya sudah jujur menandai

Sidebar app nyata (`KolDirectoryFilters.tsx`) merender beberapa kontrol dalam keadaan
`disabled` lengkap dengan penjelasan — perilaku yang lebih akurat daripada prototype:

| Kontrol | Baris | Catatan di UI |
|---|---|---|
| Format chips | 331–336 | *"Format konten belum ada datanya di roster KOL"* |
| Age bands | 366 | disabled |
| Major Female / Male (%) | 369–371 | disabled |
| Location select | 395–405 | *"Kolom kota creator sudah ada di roster, tapi belum terisi"* |
| Min. authenticity / brand fit / paid ratio / campaigns | 411–414 | *"tidak punya kolom di roster"* |

## 3.6 Issues

| # | Issue | Status |
|---|---|---|
| F1 | Batas tier UI ≠ `kol_tiers` — selisih 6,8× pada Macro | **MISMATCH** |
| F2 | Dua definisi Verified yang saling bertentangan | **MISMATCH** |
| F3 | 6 filter terblokir karena history/penyebut belum ada | **BLOCKED** |
| F4 | 7 filter tidak punya source DB sama sekali | **NOT AVAILABLE** |
| F5 | Chip YouTube · Story · Tech(2 KOL) tidak punya data | **PARTIAL** |
| F6 | Prototype `AUTOME_2.html` tidak bisa diuji terhadap DB — 0 network call, 8 KOL mock | — |

---

**Audit trail:** seluruh statement `SELECT`/katalog pada sesi `readonly=True`.
Repo `autometric` di-clone read-only ke direktori scratchpad di luar project. Tidak ada
perubahan pada database, schema, migration, source code, atau UI; tidak ada commit/push.
