# KOL Discovery — Monitoring Priority · Data Audit

**DATA AUDIT ONLY.** Read-only. Tidak ada perubahan database, schema, migration,
kode, atau UI. Tidak ada commit.

Database `kol` @ 10.100.14.216 · sesi `SET SESSION READ ONLY`
Populasi / denominator: `public.kol_directory` = **7.720**
Snapshot perhitungan umur data: **2026-09-03**

| Revisi | Tanggal | Isi |
|---|---|---|
| **Rev 2** | **2026-09-04** | **Uji kelayakan rule Product yang sudah dikonfirmasi.** Bagian 1–11 di bawah |
| Rev 1 | 2026-09-04 | Audit ketersediaan awal (`refresh_tier`, scheduler, freshness). Dipertahankan di Lampiran A–C |

**Status yang dipakai:** CLEAR · PARTIAL · MISMATCH · BLOCKED · NOT AVAILABLE ·
NEEDS VERIFICATION.
**Jenis gap:** Data Gap · Data Population Gap · Business Decision Needed.

---

## Product Direction — SUDAH DIKONFIRMASI

Monitoring Priority adalah **operational metadata**, bukan creator quality score.
Ditentukan **rule-based** dan **otomatis** (bukan input manual per KOL).

| Level | Rule |
|---|---|
| **High** | Sedang ada campaign aktif · Sedang menjadi KOL yang aktif dipantau · Perubahan/performa tinggi |
| **Medium** | KOL aktif dalam database · Monitoring standar |
| **Low** | Jarang diakses · Tidak ada aktivitas/campaign · Tidak membutuhkan update sering |

Rev 2 **tidak lagi mempertanyakan konsep di atas**. Yang diuji hanya satu hal:
**apakah database punya data yang cukup untuk menjalankannya.**

---

## Ringkasan Rev 2

Dari **6 sinyal** yang dibutuhkan rule, **nol** bisa dipakai hari ini.

| Sinyal | Schema | Data | Bisa dipakai? |
|---|---|---|---|
| High · Active campaign | **Lengkap** — 14 tabel, FK utuh ke `kol_directory` | **0 baris** | **NO** |
| High · Active monitoring | **Tidak ada** | — | **NO** |
| High · High performance | Ada | Perbandingan antar periode hanya **25 akun** (0,32%) | **NO** |
| Medium · Active KOL | Ada, 100% terisi | **1 nilai unik** — tidak membedakan | **NO** |
| Low · Rarely accessed | `audit_log` ada, bentuknya cocok | **0 baris**, dan hanya **1 user** di sistem | **NO** |
| Low · No activity | Ada | **99,61% KOL tidak punya konten** di warehouse | **NO** |

Pembedanya penting: **empat dari enam bukan kekurangan schema.** Campaign,
performance, active-KOL, dan access-log semuanya sudah punya tempat — yang tidak
ada adalah **isinya**, atau **daya bedanya**. Hanya "active monitoring" yang
benar-benar tidak punya tempat sama sekali.

---

## 1. Monitoring Priority Rule → DB Mapping

| Priority Rule | Required Signal | DB Source | Column | Coverage | Bisa Dipakai? | Gap | Evidence |
|---|---|---|---|---:|---|---|---|
| **High** | Active campaign | `campaigns` → `campaign_kols` → `agency_kol_accounts` → `kol_directory` | `campaigns.status`, `start_date`, `end_date`, `deleted_at`, `tracking_status` | **0 / 7.720 · 0%** | **NO** — **NOT AVAILABLE** | **Data Population Gap** — schema & FK lengkap, 0 baris | S1, S2, S6, T15 |
| **High** | Active monitoring | *(tidak ada)* | *(tidak ada)* | **—** | **NO** — **NOT AVAILABLE** | **Data Gap** — tidak ada tabel/kolom mana pun yang menyatakan "KOL ini sedang dipantau" | P1, P2, S7, S8 |
| **High** | High performance *(followers/ER snapshot)* | `kol_directory` | `followers_count`, `engagement_rate` | 7.498 · 97,12% · ER 1.756 · 22,75% | **NO** *(sebagai sinyal "perubahan")* | **Business Decision Needed** + snapshot tunggal, tak bisa dibanding antar periode | S11 |
| **High** | High performance *(perubahan)* | `l1_silver.unified_profile` | `date`, `followers_count` | **25 / 7.720 · 0,32%** punya ≥2 snapshot | **NO** — **DATA INSUFFICIENT** | **Data Population Gap** — butuh ≥2 snapshot; 1.951 akun baru punya 1 | S18, U2 |
| **High** | High performance *(engagement)* | `l2_gold.post_metric`, `kol_metric_daily` | `likes`, `comments`, `views`, `er_followers` | **30 / 7.720 · 0,39%** | **NO** — **DATA INSUFFICIENT** | **Data Population Gap** | S14, S19 |
| **Medium** | Active KOL | `public.kol_directory` | `directory_status` | 7.720 · **100%** | **NO** — **MISMATCH** | **1 nilai unik (`active`)** — terisi penuh tapi tidak membedakan apa pun | S20 |
| **Medium** | Active KOL *(alternatif)* | `public.agency_kol_accounts` | `status`, `is_active` | 7.719 · **100%** | **NO** — **MISMATCH** | **1 kombinasi (`active`/`true`)** — sama, tidak membedakan | T1 |
| **Low** | Rarely accessed | `public.audit_log` | `actor_id`, `action`, `entity_type`, `entity_id`, `created_at`, `ip_address` | **0 baris** | **NO** — **NOT AVAILABLE** | **Data Population Gap** — bentuk tabel cocok, isinya kosong | T5, T6 |
| **Low** | Rarely accessed *(alternatif)* | *(view/search/click/session log)* | *(tidak ada)* | **—** | **NO** — **NOT AVAILABLE** | **Data Gap** — tidak ada tabel riwayat akses sama sekali. Tambahan: sistem hanya punya **1 user** | P1, T7 |
| **Low** | No activity *(konten)* | `l1_silver.unified_post` | `posted_at`, `social_account_id` | **30 / 7.720 · 0,39%** | **NO** — **DATA INSUFFICIENT** | **Data Population Gap** — 99,61% KOL tidak punya satu pun konten di warehouse | S22, S24 |
| **Low** | No activity *(proxy `media_count`)* | `l2_gold.kol_profile_card` | `media_count` | 1.950 / 7.720 · **25,26%** | **NO** — **PARTIAL** | Nilai kumulatif, bukan recency. Bisa dibandingkan antar periode hanya **25 akun** | T11, T12 |
| **Low** | No campaign | *(sama dengan High · Active campaign)* | — | **0 · 0%** | **NO** — **NOT AVAILABLE** | Kalau `campaigns` kosong, "tidak ada campaign" benar untuk **100%** populasi → tidak membedakan | S1, T15 |

---

## 2. Campaign Coverage

### 2.1 Tabel & isinya

14 tabel campaign. **13 kosong**, 1 berisi kamus.

| Tabel | Baris | Peran |
|---|---:|---|
| `campaigns` | **0** | Induk campaign |
| `campaign_kols` | **0** | **Hubungan KOL ↔ campaign** |
| `campaign_kol_deliverables` | **0** | Deliverable per KOL |
| `campaign_tracking_jobs` | **0** | Antrean job tracking konten |
| `campaign_content_performance` | **0** | Performa konten campaign |
| `campaign_activities` | **0** | Log aktivitas |
| `campaign_activity_attachments` | **0** | Lampiran |
| `campaign_brief` | **0** | Brief |
| `campaign_kol_payments` | **0** | Pembayaran |
| `campaign_kol_progress_logs` | **0** | Riwayat progres |
| `campaign_milestones` | **0** | Milestone |
| `campaign_orders` | **0** | Order |
| `campaign_targets` | **0** | Target |
| **`campaign_stages`** | **12** | **Kamus tahapan** — satu-satunya yang terisi |

Evidence: S1, P3, P4.

### 2.2 Status, tanggal, dan indikator aktif — semuanya ADA

`campaigns` punya 25 kolom, termasuk semua yang dibutuhkan untuk menentukan
"campaign aktif":

| Kolom | Tipe | Default | Kegunaan |
|---|---|---|---|
| `status` | `varchar` | NULL | Status campaign |
| `start_date` / `end_date` | `date` | NULL | Rentang aktif |
| `deleted_at` | `timestamptz` | NULL | Soft delete |
| `tracking_status` | `varchar` | **`'inactive'`** | Indikator aktif/tidak — **satu-satunya kolom di seluruh DB yang punya default non-trivial untuk ini** |
| `tracking_start_date` / `tracking_end_date` | `date` | NULL | Rentang tracking |
| `last_tracked_at` | `timestamptz` | NULL | Kapan terakhir di-track |
| `current_stage_id` | `uuid` | NULL | FK ke `campaign_stages` |

`campaign_kols` punya 36 kolom, termasuk `status`, `approval_status`,
`progress_stage`, `last_activity_at`, `last_tracked_at`, `performance_score`.

Isi `campaign_stages` (12 baris, semuanya `is_active = true`): `campaign_confirmed`
→ `creator_confirmation` → `briefing_completed` → `content_ideation` →
`content_production` → `editing` → `revision` → `approval` → `scheduled` →
`published` → `performance_update` → `completed`.

Evidence: S2, S3, S4, S5.

### 2.3 Hubungan KOL ↔ campaign — jalur FK-nya utuh

```
public.campaigns.id
  └─ public.campaign_kols.campaign_id          FK fk_campaign_kols_campaign_id
       └─ .agency_kol_account_id               FK fk_campaign_kols_agency_kol_account_id
            └─ public.agency_kol_accounts.id
                 └─ .kol_account_id            FK agency_kol_accounts_kol_account_id_fkey
                      └─ public.kol_directory.id
```

Jalurnya **bukan langsung** ke `kol_directory` — ia lewat `agency_kol_accounts`.
Dan jembatan itu **utuh**: 7.719 baris `agency_kol_accounts`, **7.719 di antaranya
cocok** dengan `kol_directory.id` (dari 7.720 KOL; 1 tanpa pasangan).

Evidence: S6, T2, T3.

### 2.4 Hitungan yang diminta

| Ukuran | Hasil |
|---|---:|
| Jumlah campaign | **0** |
| Jumlah campaign aktif | **0** |
| Jumlah KOL di campaign aktif *(per 2026-09-03)* | **0** |
| Coverage terhadap `kol_directory` | **0 / 7.720 · 0%** |

Query T15 menerapkan definisi "aktif" yang wajar (`deleted_at IS NULL`, status
bukan completed/cancelled/draft, tanggal mencakup 2026-09-03). Query-nya **berjalan
tanpa error** — membuktikan jalur join valid — dan mengembalikan **0**.

### 2.5 Status

**NOT AVAILABLE · Data Population Gap.**

Schema campaign lengkap dan siap. Tidak ada yang perlu ditambahkan. Yang tidak ada
adalah **datanya**: 0 campaign, 0 relasi KOL, 0 deliverable. Selama ini kosong,
sinyal "Active campaign" tidak bisa membedakan siapa pun — dan konsekuensi
keduanya: rule Low "tidak ada campaign" akan **benar untuk 100% populasi**,
sehingga ia juga tidak membedakan apa pun.

---

## 3. Active Monitoring Coverage

### 3.1 Pencarian menyeluruh

Pencarian atas nama tabel **dan** nama kolom di seluruh database, dengan pola
`monitor|track|shortlist|watch|follow|access|view|search|click|visit|favorit|bookmark|saved|pinned|starred|session|audit`.

| Yang ditemukan | Baris | Apakah menjawab "KOL ini sedang dipantau?" |
|---|---:|---|
| `campaigns.tracking_status` / `tracking_start_date` / `last_tracked_at` | 0 | **Tidak** — tracking **konten campaign**, dan hanya berlaku selama campaign berjalan |
| `campaign_kols.last_tracked_at`, `contents_tracked_count` | 0 | **Tidak** — idem, per deliverable |
| `campaign_kol_deliverables.tracking_status`, `first_tracked_at`, `last_tracked_at` | 0 | **Tidak** — idem |
| `campaign_tracking_jobs` | 0 | **Tidak** — antrean job, terikat `campaign_id` + `campaign_kol_deliverable_id` |
| `brand.is_competitor_tracked` | 0 | **Tidak** — menandai **brand pesaing**, bukan KOL |
| `campaign_activities.is_pinned` | 0 | **Tidak** — pin pada baris aktivitas |
| `public.audit_log` | **0** | **Tidak** — audit perubahan entitas (lihat §6) |
| `l0_raw.*_followers_*`, `l1_silver.unified_follower` | 2.548 | **Tidak** — daftar **follower KOL di media sosial**, bukan user kita yang memantau |
| `*.reel_avg_watch_time`, `*.saved`, `avg_watch_time_seconds` | — | **Tidak** — metrik konten (`watch time`, `saved post`) |
| `agencies.meta_access_token`, `agency_integrations.access_token` | 1 / 0 | **Tidak** — kredensial OAuth |

Evidence: P1, P2, S7, S8.

**Tidak satu pun cocok.** Semua kandidat yang namanya mengandung "track" ternyata
milik domain **campaign content tracking** — konsep yang berbeda: ia melacak
**konten** selama campaign berjalan, bukan "KOL ini masuk daftar pantau saya".

### 3.2 Kandidat terdekat: `agency_kol_accounts`

Ini tabel yang secara konsep paling dekat dengan "KOL yang dikelola organisasi":
7.719 baris, FK ke `kol_directory`.

| Kolom | Nilai |
|---|---|
| `status` | **`active`** untuk 7.719 baris — **1 nilai unik** |
| `is_active` | **`true`** untuk 7.719 baris — **1 nilai unik** |
| `campaign_tag` | **0 terisi** |
| `notes` | **0 terisi** |
| `tier_id` | 7.207 terisi → FK ke `kol_tiers` (**ukuran creator**, bukan monitoring) |
| `created_at` / `updated_at` | **1 dari 7.719 terisi**; keduanya `2026-08-27 10:13:18` |
| Pernah diubah setelah dibuat | **0 baris** |

Evidence: T1, T3, T4.

Artinya: seluruh isi tabel ini masuk dalam **satu batch impor** dan **tidak pernah
disentuh sejak itu**. Tidak ada satu baris pun yang menandai perlakuan berbeda.
Ini bukan daftar pantau — ini salinan roster.

### 3.3 Yang TIDAK boleh dipakai

Prototype punya konsep "Tracked", tapi sumbernya **bukan database**:

| Sumber prototype | Tempat hidupnya |
|---|---|
| `state.tracked[id]` | `localStorage` key `autometric-kol-cart`, ditulis `trackStart()` / `trackPause()` / `trackResume()` (`app/AUTOME_2.html:2125-2128`) |
| `state.cart`, `state.negos` | `localStorage`, sama |

Sesuai instruksi audit, **browser/UI state tidak dihitung sebagai source database**.

### 3.4 Status

> ## DATA SOURCE NOT AVAILABLE

**Data Gap** — bukan Data Population Gap. Berbeda dari campaign (yang tempatnya
sudah ada, tinggal diisi), "active monitoring" **tidak punya tempat sama sekali**:
tidak ada tabel, tidak ada kolom, tidak ada relasi user↔KOL mana pun di seluruh
database.

---

## 4. Performance Data Coverage

Untuk setiap metric: source, column, grain, coverage, snapshot/historical, dan
apakah bisa dibandingkan antar periode.

| Metric | Source | Column | Grain | Coverage *(dari 7.720)* | Historical? | Bisa dibanding antar periode? | Status |
|---|---|---|---|---:|---|---|---|
| Followers | `public.kol_directory` | `followers_count` | 1 baris / KOL | 7.498 · **97,12%** | **Snapshot** — nilai ditimpa | **TIDAK** | **PARTIAL** |
| Engagement rate | `public.kol_directory` | `engagement_rate` | 1 baris / KOL | 1.756 · **22,75%** | Snapshot | **TIDAK** | **PARTIAL** |
| Followers | `l2_gold.kol_profile_card` | `followers_count` | 1 baris / akun *(UNIQUE)* | 1.972 · 25,54% | **Snapshot** — kartu kondisi terkini | **TIDAK** | **PARTIAL** |
| Follower growth | `l2_gold.kol_profile_card` | `followers_growth` | idem | **25 · 0,32%** | Turunan | — | **NOT AVAILABLE** |
| Tier ukuran | `l2_gold.kol_profile_card` | `tier` | idem | 1.972 · 25,54% | Snapshot | — | **PARTIAL** |
| **Snapshot followers** | `l1_silver.unified_profile` | `date`, `followers_count` | **(akun, tanggal)** | 2.001 baris / 1.976 akun | **YA — satu-satunya deret waktu profil** | **Hanya 25 akun (0,32%)** | **DATA INSUFFICIENT** |
| Post frequency | `l2_gold.kol_metric_daily` | `post_count`, `posts_in_sample` | (akun, platform, **tanggal posting**) | 280 baris · **30 akun · 0,39%** | Ya, tapi grain = tanggal posting | Terbatas 30 akun | **DATA INSUFFICIENT** |
| ER harian | `l2_gold.kol_metric_daily` | `er_followers_daily` | idem | 30 akun · 0,39% | Ya | Terbatas | **DATA INSUFFICIENT** |
| Rekap bulanan | `l2_gold.kol_metric_monthly` | `post_count`, `active_days`, `er_followers_monthly` | (akun, platform, `month_start`) | 68 baris · **30 akun** · 21 bulan | Ya | 18 akun punya ≥2 bulan | **DATA INSUFFICIENT** |
| Followers akhir bulan | `l2_gold.kol_metric_monthly` | `followers_eom` | idem | 25 baris terisi | Ya | **NOL akun punya di >1 bulan** → month-over-month **mustahil** | **NOT AVAILABLE** |
| Views | `l2_gold.post_metric` | `views` | (akun, platform, konten) | 393 / 477 baris · **30 akun** | Ya, per konten | Terbatas | **DATA INSUFFICIENT** |
| Likes / Comments | `l2_gold.post_metric` | `likes`, `comments` | idem | 477 / 477 · 30 akun | Ya | Terbatas | **DATA INSUFFICIENT** |
| Saves / Shares | `l2_gold.post_metric` | `saves`, `shares` | idem | 291 / 477 · TikTok saja | Ya | Terbatas | **PARTIAL** |
| Recent activity | `l1_silver.unified_post` | `posted_at` | (akun, konten) | **30 akun · 0,39%** | Ya | — | **DATA INSUFFICIENT** |
| Growth momentum | — | — | — | — | — | Butuh ≥3 snapshot; maksimum yang ada **2** | **NOT AVAILABLE** |
| Performance score | `public.campaign_kols` | `performance_score` | per campaign-KOL | **0 baris** | — | — | **NOT AVAILABLE** |

Evidence: S11, S12, S14, S16, S17, S18, S19, S22, U1, U2.

### 4.1 Inti masalahnya: "perubahan" butuh dua titik waktu

Rule High menyebut **"perubahan/performa tinggi"**. Kata *perubahan* menuntut
perbandingan antar periode, dan hanya ada satu deret waktu profil yang sah:
`l1_silver.unified_profile`.

| Kedalaman snapshot | Akun |
|---|---:|
| 1 tanggal | **1.951** |
| 2 tanggal | **25** |
| ≥3 tanggal | **0** |

25 akun yang punya 2 snapshot pun jaraknya sempit: **10 hari** (22 akun) dan
**13 hari** (3 akun).

Jadi perbandingan antar periode hari ini mungkin untuk **25 akun (0,32% populasi)**,
dalam jendela 10–13 hari. Untuk 7.695 KOL sisanya, "perubahan" tidak terdefinisi —
bukan nol, melainkan **tidak diketahui**.

### 4.2 Peringatan grain — jangan tertukar

| Tabel | Grain waktunya | Artinya |
|---|---|---|
| `l1_silver.unified_profile.date` | **tanggal snapshot profil** | Kapan kita mengambil datanya → **sah** untuk growth |
| `l2_gold.kol_metric_daily.metric_date` | **tanggal posting konten** | Kapan KOL mem-posting → **bukan** deret snapshot |
| `l2_gold.kol_metric_monthly.month_start` | **bulan posting konten** | Idem. `min = 2021-02-01` bukan berarti kita punya data sejak 2021 |

`kol_metric_daily` merentang 2021-02-18 → 2026-08-28 dari hanya **30 akun** —
itu rentang tanggal **posting lama** yang ikut tertarik saat scraping, bukan
riwayat pemantauan.

### 4.3 Status

Untuk followers & ER sebagai **nilai**: **DATA AVAILABLE — BUSINESS THRESHOLD NOT
DEFINED.** Datanya ada (97,12% / 22,75%), tapi "tinggi" itu berapa belum
ditentukan, dan audit ini **tidak membuat threshold sendiri**.

Untuk **perubahan/growth/momentum**: **DATA INSUFFICIENT.** Bukan soal threshold —
bahannya memang belum terkumpul untuk 99,68% populasi.

---

## 5. Active KOL Coverage

Rule Medium: *"KOL aktif dalam database"*.

### 5.1 `directory_status`

| Nilai | KOL | % |
|---|---:|---:|
| `active` | **7.720** | **100,00%** |
| *(nilai lain)* | 0 | 0% |

**Satu nilai unik.** Kolomnya terisi sempurna, tapi **tidak ada satu pun KOL yang
non-active**. Field ini tidak membedakan apa pun.

### 5.2 `agency_kol_accounts.status` / `is_active`

| `status` | `is_active` | KOL |
|---|---|---:|
| `active` | `true` | **7.719** |

**Satu kombinasi.** Sama persis masalahnya.

### 5.3 Kandidat field status lain

Pencarian seluruh kolom berpola `_status$|^status$|is_active|active|enabled|deleted_at|archived`
menghasilkan 33 kolom. Yang relevan dengan KOL:

| Kolom | Coverage | Bisa membedakan active/inactive KOL? |
|---|---:|---|
| `kol_directory.directory_status` | 100%, 1 nilai | **Tidak** |
| `kol_directory.scrape_status` | 99 · 1,28% (72 `failed`, 27 `success`) | **Tidak** — status **percobaan scrape**, bukan status KOL |
| `kol_directory.verified_status` | 931 · 12,06% | **Tidak** — centang biru, konsep berbeda |
| `agency_kol_accounts.status` / `is_active` | 100%, 1 kombinasi | **Tidak** |
| `l2_gold.kol_metric_monthly.active_days` | 30 akun | **Tidak** — hari ber-posting dalam sebulan, bukan status |
| `feature.*_audience_analysis.active_hours_heatmap` | 23 akun | **Tidak** — jam aktif audiens |
| `campaign_stages.is_active`, `scheduler_config.is_active`, `brand.is_active` | — | **Tidak** — objek lain |

Sisanya milik domain campaign/agency/payment yang tidak menyentuh KOL.

Evidence: S20, S21, T1, B3 *(Rev 1)*.

### 5.4 Status

**MISMATCH.** Ini kasus yang paling mudah salah dibaca: coverage 100% terlihat
sehat di laporan mana pun, padahal **daya bedanya nol**. Kalau "KOL aktif" dipakai
apa adanya, **seluruh 7.720 KOL menjadi Medium** — dan Monitoring Priority berhenti
menjadi prioritas.

Perlu **Business Decision**: apa sebenarnya yang membuat sebuah KOL "aktif dalam
database"? Kalau jawabannya bukan `directory_status`, sinyalnya harus didefinisikan
ulang dari sesuatu yang benar-benar bervariasi.

---

## 6. User Access / Rarely Accessed Coverage

Ini bagian yang wajib dicek eksplisit, dan hasilnya tegas.

### 6.1 Pencarian riwayat akses

| Yang dicari | Ada di DB? | Ada di codebase? |
|---|---|---|
| User access log | Hanya `audit_log` — **0 baris** | 0 hit |
| KOL view history | **Tidak ada tabel** | 0 hit `view_history` |
| Search history | **Tidak ada tabel** | 0 hit `search_history` |
| Click history | **Tidak ada tabel** | 0 hit |
| `last_viewed` / `last_accessed` | **0 kolom** di seluruh DB | 0 hit |
| Interaction log | **Tidak ada tabel** | 0 hit |
| Organization activity log | `campaign_activities` **0 baris** (khusus campaign) | — |
| Session log | **Tidak ada tabel** | 0 hit |

Evidence: P1, P2, S7, S8 + grep repo.

### 6.2 `public.audit_log` — bentuknya cocok, isinya kosong

| Kolom | Tipe |
|---|---|
| `id` | `uuid` |
| `actor_id` | `uuid` — siapa |
| `actor_role` | `varchar` |
| `agency_id` | `uuid` |
| `action` | `varchar` — melakukan apa |
| `entity_type` / `entity_id` | `varchar` / `uuid` — terhadap apa |
| `before` / `after` | `jsonb` |
| `created_at` | `timestamptz` — kapan |
| `ip_address` | `varchar` |

**0 baris.** Evidence: T5, T6.

Bentuknya memang bisa menampung jejak akses (`actor_id` + `action` +
`entity_type='kol_directory'` + `entity_id` + `created_at`). Tapi dua hal harus
dicatat jujur:

1. **Isinya nol** — tidak ada satu pun peristiwa tercatat.
2. Kehadiran `before`/`after` `jsonb` menunjukkan tabel ini dirancang untuk
   **audit perubahan data**, bukan **pencatatan pembacaan**. Apakah `action` akan
   pernah mencatat `view`/`read` adalah **NEEDS VERIFICATION** — tidak ada kode di
   repo ini yang menulis ke sana.

### 6.3 Tidak ada populasi pengakses

| Tabel | Baris |
|---|---:|
| `public.user` | **1** |
| `public.agency_members` | **1** |
| `public.agencies` | **1** |
| `public.brand` | **0** |
| `public.brand_members` | **0** |

Evidence: T7.

Ini menambah lapisan masalah yang terpisah dari kekosongan log: **sistem baru punya
satu pengguna**. "Jarang diakses" adalah pernyataan statistik tentang perilaku
banyak pengguna sepanjang waktu. Dengan 1 user dan 0 peristiwa, sinyalnya tidak
akan bermakna bahkan seandainya log mulai diisi besok.

### 6.4 Yang TIDAK boleh dipakai

| Sumber | Kenapa tidak |
|---|---|
| `state.dirIQ.recent` di prototype | Array in-memory, **maksimum 8 entri**, per-sesi browser, dan **tidak** ikut disimpan `saveState()` (`app/AUTOME_2.html:3152, 3164`) |
| `kol_directory.last_refreshed_at` | **Freshness data, bukan akses user.** Instruksi audit melarang tegas, dan §8 menunjukkan kenapa: ia tidak pernah menyentuh perilaku pengguna sama sekali |

### 6.5 Status

> ## DATA SOURCE NOT AVAILABLE

**Data Population Gap** untuk `audit_log` (tempatnya ada, kosong) **+ Data Gap**
untuk riwayat akses/tampilan (tidak ada tempat sama sekali) **+** tidak ada
populasi pengguna untuk diukur.

---

## 7. Activity Coverage

Rule Low: *"tidak ada aktivitas"*.

### 7.1 Konten di warehouse

| Ukuran | Nilai |
|---|---:|
| Baris `l1_silver.unified_post` | **477** |
| Akun punya konten | **30** |
| Rentang `posted_at` | 2021-02-18 → 2026-08-28 |
| Baris `l2_gold.post_metric` | 477 · 30 akun |

Sebaran post per akun: 1 akun **200** post · 25 akun **10** post · 2 akun 9 ·
1 akun 8 · 1 akun 1.

Angka 10 itu bukan kebetulan: `POSTS_PER_TARGET = 10` di `scheduler_engine.py:100`.
Jadi kedalaman konten yang ada adalah **hasil batas uji coba**, bukan cerminan
aktivitas KOL sebenarnya.

Evidence: S19, S22, T13.

### 7.2 Umur konten terakhir terhadap 2026-09-03

| Bucket | KOL | % |
|---|---:|---:|
| **Tidak ada konten sama sekali** | **7.690** | **99,61%** |
| ≤ 7 hari | 3 | 0,04% |
| 8–30 hari | 25 | 0,32% |
| 31–90 hari | 0 | 0% |
| > 90 hari | 2 | 0,03% |

Evidence: S24.

### 7.3 Proxy `media_count` — lebih luas, tapi bukan recency

| Sumber | Baris | `media_count` terisi | Coverage populasi |
|---|---:|---:|---:|
| `l2_gold.kol_profile_card` | 1.976 | **1.950** | **25,26%** |
| `l1_silver.unified_profile` | 2.001 | 1.975 | — |

Dua batasan:

1. `media_count` adalah **jumlah kumulatif seumur akun**, bukan tanggal aktivitas
   terakhir. Akun dengan 5.000 post yang berhenti 2 tahun lalu tetap bernilai 5.000.
2. Untuk mengubahnya menjadi sinyal aktivitas, ia harus **dibandingkan antar
   snapshot** — dan itu hanya mungkin untuk **25 akun** (1.925 akun punya 1
   tanggal, 26 akun punya 0).

Evidence: T11, T12.

### 7.4 Status

> ## DATA INSUFFICIENT

**Data Population Gap.** Schema-nya benar dan lengkap (`unified_post`,
`post_metric`, `content_format_daily`, `media_count` di tiga layer). Yang belum ada
adalah datanya: 99,61% KOL tidak punya satu pun konten di warehouse.

Bahaya yang harus disadari: kalau rule dijalankan apa adanya, **7.690 KOL akan
dinilai "tidak ada aktivitas" → Low**, padahal yang benar adalah **"kita belum
pernah mengambil kontennya"**. Itu bukan sinyal tentang KOL — itu sinyal tentang
cakupan scraping kita sendiri.

---

## 8. Freshness vs Activity vs Access — empat konsep yang tidak boleh dicampur

| # | Konsep | Pertanyaan yang dijawab | Source | KOL punya nilai | Coverage |
|---|---|---|---|---:|---:|
| 1 | **Last refresh** | Kapan baris direktori ini terakhir diperbarui? | `kol_directory.last_refreshed_at` | **7.496** | **97,10%** |
| 2 | **Last scrape** | Kapan **kita** terakhir berhasil menarik datanya ke warehouse? | `max(l0_raw.*_profile_apify.scraped_at)` | **1.976** | **25,60%** |
| 3 | **Last content activity** | Kapan **KOL-nya** terakhir mem-posting? | `max(l1_silver.unified_post.posted_at)` | **30** | **0,39%** |
| 4 | **Last user access** | Kapan **user kita** terakhir membuka KOL ini? | *(tidak ada)* | **0** | **0%** |

Evidence: T14, B1 *(Rev 1)*, F2 *(Rev 1)*, S24.

**Keempatnya berbeda, dan jaraknya jauh — 7.496 vs 1.976 vs 30 vs 0.**

Tiga kekeliruan yang paling mungkin terjadi kalau keempatnya dicampur:

| Kalau dipakai untuk | Padahal artinya | Akibatnya |
|---|---|---|
| `last_refreshed_at` → "jarang diakses" | Umur data, tidak menyentuh perilaku user sama sekali | Priority ditentukan oleh **jadwal scraping kita**, bukan oleh kebutuhan bisnis |
| `last_refreshed_at` → "tidak ada aktivitas" | Kapan **kita** memperbarui, bukan kapan **KOL** posting | KOL yang sangat aktif tapi lama tidak kita scrape akan dinilai "tidak aktif" |
| `last_scraped` → "last refresh" | 5.520 KOL punya `last_refreshed_at` **tanpa** data L0 apa pun | Selisih 73,6% dari nilai yang ada — lihat Lampiran C |

Rule Low menyebut **"jarang diakses"** (konsep 4) dan **"tidak ada aktivitas"**
(konsep 3). Keduanya adalah konsep dengan coverage **terendah** dari keempatnya —
0% dan 0,39%. Konsep dengan coverage tertinggi (97,10%) justru yang **paling tidak
boleh** dipakai untuk keduanya.

---

## 9. Data Gap

Dipisah sesuai tiga kategori yang diminta.

### 9.1 Data Gap — tidak ada tempatnya di schema

| # | Yang hilang | Dampak |
|---|---|---|
| 1 | **Relasi "KOL sedang dipantau" (user/organization ↔ KOL)** | Sinyal High #2 tidak bisa dijalankan sama sekali |
| 2 | **Riwayat akses / tampilan / pencarian KOL** | Sinyal Low #1 tidak bisa dijalankan sama sekali |

Hanya dua ini yang benar-benar Data Gap. Keduanya menyangkut **perilaku pengguna**,
dan memang belum pernah ada domainnya di database ini.

### 9.2 Data Population Gap — schema cukup, data belum terisi

| # | Tempat | Isi sekarang | Yang dibutuhkan |
|---|---|---:|---|
| 1 | `campaigns` + 12 tabel turunannya | **0 baris** | Campaign berjalan |
| 2 | `public.audit_log` | **0 baris** | Peristiwa akses tercatat *(dan konfirmasi bahwa `action` memang mencatat view)* |
| 3 | `l1_silver.unified_profile` — snapshot ke-2 | 1.951 akun baru 1 snapshot | ≥2 snapshot per akun untuk "perubahan" |
| 4 | `l1_silver.unified_post` | 30 akun | Konten untuk sisa populasi |
| 5 | `l2_gold.kol_metric_monthly.followers_eom` | 25 baris, **0 akun punya di >1 bulan** | ≥2 bulan per akun |
| 6 | `kol_directory.refresh_tier` | **0 / 7.720** | Nilai priority hasil rule *(setelah rule bisa dijalankan)* |

### 9.3 Business Decision Needed — data ada, definisi belum

| # | Sinyal | Data yang tersedia | Yang belum ditentukan |
|---|---|---|---|
| 1 | "Performa tinggi" | `followers_count` 97,12% · `engagement_rate` 22,75% | **Tinggi itu berapa** |
| 2 | "Perubahan tinggi" | growth 25 akun, jendela 10–13 hari | Ambang **dan** jendela waktunya |
| 3 | "KOL aktif dalam database" | `directory_status` 100% tapi **1 nilai unik** | **Apa** yang membuat KOL disebut aktif, kalau bukan field ini |
| 4 | "Jarang diakses" | — | **Berapa kali / berapa lama** disebut jarang |
| 5 | Prioritas antar-sinyal | — | Kalau High dan Low sama-sama terpenuhi, mana yang menang |
| 6 | Default | — | KOL yang tidak memenuhi sinyal apa pun → Medium, atau "belum diklasifikasi" |

### 9.4 MISMATCH — terisi penuh tapi tidak berguna

| Field | Coverage | Masalah |
|---|---:|---|
| `kol_directory.directory_status` | **100%** | 1 nilai unik (`active`) |
| `agency_kol_accounts.status` + `is_active` | **100%** | 1 kombinasi (`active`/`true`) |
| `kol_directory.last_refreshed_at` | **97,10%** | 5.520 nilai tidak berpadanan dengan data mana pun di warehouse (Lampiran C) |

Tiga field dengan coverage tertinggi di seluruh audit ini justru **tidak satu pun
bisa dipakai**. Coverage tinggi ≠ dapat dipakai.

---

## 10. Business Decision Still Needed

Konsep High/Medium/Low sudah ditetapkan Product, jadi daftar ini **jauh lebih
pendek dari Rev 1**. Yang tersisa adalah penerjemahan konsep ke angka dan ke
perilaku sistem.

| # | Keputusan | Kenapa perlu | Memblokir |
|---|---|---|---|
| BD1 | **Ambang "performa/perubahan tinggi"** | Audit tidak boleh mengarang threshold. Data followers/ER ada, artinya "tinggi" belum ada | Sinyal High #3 |
| BD2 | **Jendela perbandingan** — 7 / 14 / 30 hari? | Data yang ada hanya berjarak **10–13 hari** untuk 25 akun. Memilih 30 hari berarti 0 akun memenuhi syarat hari ini | Sinyal High #3 |
| BD3 | **Definisi "KOL aktif dalam database"** | `directory_status` 100% `active` → tidak membedakan. Perlu sinyal pengganti | Sinyal Medium |
| BD4 | **Definisi "jarang diakses"** — berapa kali dalam berapa lama | Belum ada satuannya | Sinyal Low #1 |
| BD5 | **Apakah "belum pernah kita scrape" = "tidak ada aktivitas"?** | Hari ini 99,61% KOL tidak punya konten **karena belum di-scrape**, bukan karena tidak aktif. Menyamakan keduanya membuat 7.690 KOL jatuh ke Low secara keliru | Sinyal Low #2 |
| BD6 | **Urutan menang antar-sinyal** | Sebuah KOL bisa memenuhi High (campaign aktif) sekaligus Low (tidak ada konten di warehouse) | Seluruh rule |
| BD7 | **Default untuk KOL tanpa sinyal apa pun** | Hari ini berlaku untuk **100%** populasi | Seluruh rule |
| BD8 | **Perlakuan 224 baris kosong** | Tidak punya `platform_id`, `username`, maupun `kol_social_account` → **tidak bisa di-refresh secara teknis** | Denominator |
| BD9 | **Apakah `audit_log` akan mencatat `view`?** | Tabelnya berbentuk audit **perubahan** (`before`/`after`), belum tentu pembacaan | Sinyal Low #1 |

Dua hal dari Rev 1 yang **masih berlaku dan tidak terjawab oleh arahan Product**:

| # | Keputusan | Alasan |
|---|---|---|
| BD10 | **Arti `last_refreshed_at`** | 5.520 KOL berbeda hasilnya antara dua tafsir (Lampiran C) |
| BD11 | **Apakah scheduler boleh recurring?** | Priority adalah instruksi untuk penjadwal; hari ini penjadwalnya one-shot **secara sengaja** karena biaya (Lampiran B) |

---

## 11. Final Feasibility

### 11.1 Kelayakan per level

| Level | Sinyal | Bisa dijalankan hari ini? | KOL yang akan terklasifikasi |
|---|---|---|---:|
| **High** | Campaign aktif | **NO** — 0 campaign | **0** |
| **High** | Active monitoring | **NO** — tidak ada source | **0** |
| **High** | Performa/perubahan tinggi | **NO** — threshold belum ada **dan** hanya 25 akun punya data perbandingan | **0** |
| **Medium** | KOL aktif dalam database | **NO** — field ada tapi 1 nilai unik | **0 secara bermakna** *(atau 7.720 sekaligus)* |
| **Low** | Jarang diakses | **NO** — tidak ada access log, dan hanya 1 user | **0** |
| **Low** | Tidak ada aktivitas/campaign | **NO** — akan salah menandai 7.690 KOL | **0 yang sahih** |

### 11.2 Putusan

> **Rule Monitoring Priority BELUM BISA DIJALANKAN.**
> Nol dari enam sinyal siap. Kalau dipaksakan hari ini, hasilnya bukan sekadar
> tidak akurat — hasilnya **seragam**: setiap KOL jatuh ke kelas yang sama, dan
> Monitoring Priority tidak memprioritaskan apa pun.

### 11.3 Yang membuat ini tetap layak dikejar

Kabar baiknya nyata dan spesifik: **hanya 2 dari 8 kekurangan yang butuh schema
baru.** Sisanya sudah punya tempat.

| Butuh apa | Berapa | Contoh |
|---|---:|---|
| **Schema baru** | **2** | Relasi "sedang dipantau" · riwayat akses KOL |
| **Cukup diisi data** | **6** | Campaign · `audit_log` · snapshot ke-2 · konten · `followers_eom` · `refresh_tier` |
| **Cukup keputusan** | **11** | BD1–BD11 |

### 11.4 Urutan yang masuk akal

| Urutan | Langkah | Sifat | Hasilnya |
|---:|---|---|---|
| 1 | **BD3 + BD5** — definisikan "KOL aktif" dan putuskan apakah "belum di-scrape" = "tidak aktif" | Keputusan, **nol biaya** | Menghindari 7.690 KOL salah jatuh ke Low |
| 2 | **Snapshot profil kedua** untuk akun yang sudah punya baseline | Butuh scraping berulang (BD11) | Membuka sinyal "perubahan" dari 25 akun → ribuan |
| 3 | **BD1 + BD2** — ambang & jendela | Keputusan | Sinyal High #3 hidup |
| 4 | Campaign mulai terisi | Menunggu modul Campaign dipakai | Sinyal High #1 hidup **tanpa pekerjaan tambahan** — FK sudah utuh |
| 5 | Access log & monitoring relation | **Butuh schema baru** — proposal di Lampiran D | Sinyal High #2 & Low #1 hidup |

**Yang paling mendesak bukan yang paling sulit.** Langkah 1 tidak butuh biaya,
tidak butuh schema, tidak butuh scraping — hanya keputusan. Tapi tanpa itu, setiap
implementasi berikutnya akan mewarisi kesalahan klasifikasi 7.690 KOL.

---
---

# Lampiran — Temuan Rev 1 yang masih berlaku

Bagian ini tidak berubah oleh arahan Product; ia menyangkut **mesin** yang akan
menjalankan priority, bukan definisi priority-nya.

## Lampiran A — `refresh_tier`: kolom kosong tanpa kontrak

| Pemeriksaan | Hasil |
|---|---|
| Kolom ada? | Ya — `kol_directory` posisi 16, `varchar(255)`, nullable, tanpa default |
| Terisi | **0 / 7.720** |
| Nilai unik | **1** — hanya NULL |
| CHECK constraint | **Tidak ada** (constraint hanya PK + 2 FK) |
| Enum | **Tidak ada enum sama sekali di seluruh DB** |
| COMMENT | **Tidak ada** |
| Trigger | **Tidak ada** |
| Routine / view yang memakainya | **0 / 0** |
| Hit di kode | **0** |
| Index | Tidak ada; satu-satunya index adalah `kol_directory_pkey` |

**Jangan tertukar dengan `public.kol_tiers`** (5 baris: Nano 1.000–9.999 · Micro
10.000–49.999 · **Mid-tier 50.000–499.999** · **Macro 500.000–999.999** · Mega
≥1.000.000 — *dua ambang tengah dibetulkan migration 033 pada 2026-09-07; angka lama
yang salah: Mid-tier 50.000–99.999 dan Macro 100.000–999.999*).
Itu **tier ukuran creator** berdasarkan followers, dirujuk
`agency_kol_accounts.tier_id` (7.207 terisi) — konsep yang sama sekali berbeda dari
`refresh_tier`.

Evidence: A3, A4, A5, A6, B1, B2, G1, G3, G13, T8.

## Lampiran B — Scheduler: one-shot, bukan recurring

| Pemeriksaan | Temuan |
|---|---|
| Sifat eksekusi | *"Satu eksekusi ONE-SHOT... tidak ada loop, tidak ada cron"* — `scheduler_engine.py:1-16` |
| Batas | `PROFILE_TARGET_LIMIT = 1`, `POSTS_PER_TARGET = 10`, `MAX_RETRIES = 0` |
| Kriteria target | **`NOT EXISTS` di `l0_raw`** = *"belum pernah di-scrape"* — **kebalikan** dari kebutuhan monitoring |
| Schedule Dagster | **`one_shot_schedules = []`** (`one_shot.py:325`) |
| State instance Dagster | 1 instigator, bertipe **SENSOR**. Nol SCHEDULE |
| Sensor | Event-based pada kedatangan data `l0_raw`; hanya menjalankan transformasi, **tidak pernah memanggil Apify** |
| pg_cron | **Tidak terpasang** — extension hanya `plpgsql` |
| `scheduler_config` | Tabel ada (`is_active`, `schedule_times jsonb`), **0 baris**, dan bentuknya jam absolut global tanpa kaitan ke KOL/tier |
| `scheduler_logs` | **8 baris** · 4 run · 4 akun · 2026-08-27→28. 2 baris per akun adalah pasangan `profile`+`post` dari **satu** run — **tidak ada akun yang di-scrape ulang** |

Konsekuensi untuk Monitoring Priority: **selama kriteria "belum pernah di-scrape"
belum diganti, akun yang sudah masuk L0 tidak akan pernah terpilih lagi** — refresh
berulang secara struktural tidak mungkin, apa pun priority-nya.

Evidence: A1, D1–D7, E6, G12, `.dagster_home/schedules/schedules.db`.

## Lampiran C — `last_refreshed_at`: MISMATCH yang masih berdiri

| Pengujian | Hasil |
|---|---:|
| KOL punya `last_refreshed_at` | 7.496 · 97,10% |
| ↳ **dan** punya baris profil di `l0_raw` | **1.976** |
| ↳ **tapi tidak punya** data apa pun di `l0_raw` | **5.520** · 73,6% dari yang bernilai |
| Sekadar salinan `created_at` | hanya **4** |
| `kol_directory.source` | `excel_import` **7.718** · `manual_add` **2** |

Distribusi umur terhadap 2026-09-03: ≤1 hari **0** · 2–3 hari **0** · 4–7 hari
**4** · 8–14 hari **0** · >14 hari **7.492** (97,05%) · NULL 224.
Umur median **847 hari**, maksimum **1.306 hari**, tertua 2023-02-05.

Satu-satunya penulis `last_refreshed_at` adalah `db.update_profiles()`
(`db.py:399`), dipanggil hanya dari `ingest.py:231` dan `pipeline.py:304` — jalur
Instagram lama. `scheduler_engine.py` dan jalur Dagster hanya **membaca**
`kol_directory`.

**NEEDS VERIFICATION:** 914 baris bertanggal 2026-08-14 punya `scrape_status` NULL,
padahal `update_profiles` selalu menulis `scrape_status` di UPDATE yang sama
(`db.py:398`, tanpa COALESCE). Asal-usulnya di luar repo ini.

Evidence: B1, C1–C4, F2, G8, G9, G14, H1, I1.

## Lampiran D — Proposed DB Changes — WAITING FOR APPROVAL

**BELUM DIJALANKAN. Tidak ada migration yang dibuat.**

Rev 2 menambah **dua** kandidat baru pada satu kandidat dari Rev 1. Ketiganya
menunggu review.

| # | Kebutuhan | Kategori | Alternatif tanpa schema change |
|---|---|---|---|
| D1 | **Pemetaan tier → interval refresh** *(Rev 1)* | Schema belum cukup | **Ada** — simpan interval sebagai konstanta di config aplikasi, pakai `refresh_tier` yang sudah ada untuk labelnya. **Ini rekomendasi audit** |
| D2 | **Relasi "KOL sedang dipantau"** *(Rev 2)* | Schema belum cukup | **Ada, sebagian** — `agency_kol_accounts` sudah punya `status`, `is_active`, `campaign_tag`, `notes` yang semuanya kosong/seragam. **Periksa dulu apakah kolom itu memang diperuntukkan untuk ini** sebelum menambah tabel |
| D3 | **Riwayat akses KOL** *(Rev 2)* | Schema belum cukup **untuk view log** | **Ada** — `public.audit_log` sudah punya bentuk yang tepat (`actor_id`, `action`, `entity_type`, `entity_id`, `created_at`). **Mengisinya lebih murah daripada membuat tabel baru** — tapi perlu konfirmasi BD9 |

**Yang tetap TIDAK diusulkan:**

- ❌ Kolom `monitoring_priority` baru — `refresh_tier` sudah ada, kosong, tipenya cukup
- ❌ Kolom `next_refresh_at` — turunan murni `last_refreshed_at + interval`
- ❌ Tabel antrean refresh baru — periksa `campaign_tracking_jobs` dulu (0 baris, bentuknya sudah job-queue)
- ❌ Tabel campaign apa pun — **schema campaign sudah lengkap dan FK-nya utuh sampai `kol_directory`**; yang kurang hanya datanya
- ❌ Index pada `last_refreshed_at` / `refresh_tier` — 7.720 baris, seq scan murah
- ❌ CHECK constraint pada `refresh_tier` — tunda sampai daftar level final

---

## Lampiran E — Metode & Bukti

**Query.** 75 query read-only lewat `db.connect()` dengan
`conn.set_session(readonly=True, autocommit=True)`. Tidak ada satu pun perintah
tulis. Berkas di scratchpad sesi:

| Berkas | Blok | Isi |
|---|---|---|
| `mp_audit.sql` | A1–F2 | Rev 1 — inventaris, coverage, freshness, scheduler |
| `mp_audit2.sql` | G1–G14 | Rev 1 — routine, index, provenance, umur L0 |
| `mp_audit3.sql` | H1–H4 | Rev 1 — asal-usul batch 2026-08-14 |
| `mp_audit4.sql` | I1–I2 | Rev 1 — `last_refreshed_at` vs `created_at` |
| `mp5_discovery.sql` | P0–P7 | **Rev 2** — peta seluruh DB (101 tabel), pencarian keyword |
| `mp6_signals.sql` | S1–S25 | **Rev 2** — 6 sinyal rule |
| `mp7_deep.sql` | T1–T15 | **Rev 2** — agency_kol_accounts, audit_log, user, aktivitas |
| `mp8.sql` | U1–U3 | **Rev 2** — kelayakan perbandingan antar periode |

**Grep codebase.** Pola `monitoring`, `tracked`, `tracking`, `shortlist`,
`watchlist`, `watch`, `followed`, `monitored`, `access_log`, `last_viewed`,
`last_accessed`, `view_history`, `search_history` atas `*.py`, `*.sql`, `*.md`,
`*.html`, `*.ts`, `*.tsx`, `*.json`, `*.yaml`, `.env*`, dengan `venv/` dikecualikan.

Semuanya **0 hit**, kecuali dua yang ternyata bukan yang dicari:

| Pola | Hit | Sebenarnya apa |
|---|---:|---|
| `watch` | 43 | Seluruhnya `reel_avg_watch_time` — metrik durasi tonton video |
| `followed` | 2 | `edge_followed_by` — jumlah follower dari payload Instagram |

**Query yang gagal dan tidak dipakai sebagai kesimpulan positif:**

| Query | Error | Tindakan |
|---|---|---|
| E5 *(Rev 1)* | `WrongObjectType "array_agg" is an aggregate function` | Diulang sebagai G1 dengan filter `prokind IN ('f','p')` → 0 baris |
| E6 *(Rev 1)* | `UndefinedTable relation "cron.job" does not exist` | **Itu sendiri temuannya** — pg_cron tidak terpasang. Dikuatkan G12 |

Paket Rev 2 (`mp5`–`mp8`) berjalan **tanpa satu pun error**.

**NEEDS VERIFICATION — tidak disimpulkan:**

| Item | Kenapa |
|---|---|
| Asal-usul 914 baris `last_refreshed_at = 2026-08-14` dengan `scrape_status` NULL | Tidak ada jalur kode di repo ini yang bisa menghasilkannya |
| Apakah `audit_log.action` akan mencatat peristiwa **view/read** | Bentuk tabel (`before`/`after` jsonb) menunjukkan audit **perubahan**; tidak ada kode di repo ini yang menulis ke sana |
| Apakah `agency_kol_accounts.status` / `campaign_tag` / `notes` memang diperuntukkan bagi konsep monitoring | Ketiganya kosong atau seragam; tidak ada kode/comment yang menjelaskan maksudnya |

---

**Status dokumen:** audit read-only. Tidak ada perubahan database, schema,
migration, kode, atau UI. Tidak ada commit. Seluruh angka Rev 2 hasil query
langsung pada **2026-09-04**, dengan umur data dihitung terhadap snapshot
**2026-09-03**.
