# KOL Discovery — Backend Plan

**Dokumentasi untuk engineer. Bukan implementasi.**
Database `kol` @ 10.100.14.216 — audit read-only · 2026-09-03
Populasi: `public.kol_directory` = 7.720 KOL

Cakupan dokumen ini saat ini: **Growth Classification**, **Rising Creator**, dan
**Monitoring Priority**.
Filter lain menyusul; jangan anggap dokumen ini lengkap untuk seluruh Discovery.

> **UPDATE 2026-09-07.** Dua hal berubah sejak dokumen ini ditulis:
>
> 1. **Ambang `public.kol_tiers` sudah dibetulkan** (migration 033) — angka yang
>    tertulis di §"Yang perlu dilihat sekali lagi" sudah **usang**, lihat koreksinya
>    di sana.
> 2. **Growth sudah tayang di Discovery**, tapi **bukan** `growth_30d` yang
>    direncanakan di T1. Yang tayang adalah `followers_growth` apa adanya, berlabel
>    "Sejak Snapshot Terakhir". **T1 tetap blocked** dan tetap relevan — lihat §3 T1.
>
> Monitoring Priority tidak terpengaruh sama sekali.

---

## 1. Ringkasan untuk yang buru-buru

> **Schema sudah cukup. Tidak ada perubahan DB yang diperlukan.**
> Yang belum ada adalah **history**-nya, dan itu terkumpul lewat scraping profil
> berulang — bukan lewat kolom atau tabel baru.
>
> **Growth 30D tidak bisa dihitung hari ini untuk satu akun pun** (0 dari 1.976).
> Tapi jaraknya lebih dekat dari yang terlihat: backfill 14–18 Agustus 2026 sudah
> berfungsi sebagai kaki "T−30". **Satu kali re-scrape pada ~17 September 2026
> langsung membuka 30D growth untuk 1.971 akun.**

---

## 2. Source Table & Column

### Tabel history yang dipakai

| Tabel | Grain | Kolom yang dipakai | Status |
|---|---|---|---|
| `l1_silver.unified_profile` | `(social_account_id, date)` — dijamin `UNIQUE uq_unified_profile` | `date`, `followers_count`, `followers_growth` | **Sumber kebenaran history** |
| `public.kol_social_account` | 1 baris per KOL | `kol_id`, `social_account_id` | Jembatan ke `kol_directory` |
| `public.kol_directory` | 1 baris per KOL | `id`, `followers_count` | Populasi + nilai terkini |

### Tabel yang TIDAK boleh dipakai sebagai history — dan alasannya

| Tabel/kolom | Kenapa tidak |
|---|---|
| `l2_gold.kol_profile_card` | `UNIQUE (social_account_id, platform)` → **1 baris per akun**. Ini kartu "kondisi terkini", bukan deret waktu. 1.976 baris untuk 1.976 akun |
| `l2_gold.kol_metric_monthly.followers_eom` | Bulannya berasal dari **tanggal posting**, bukan snapshot profil. **Tidak ada satu akun pun punya `followers_eom` di lebih dari 1 bulan** (25 akun punya tepat 1, 5 akun punya 0) → month-over-month mustahil |
| `l2_gold.kol_metric_daily.followers_growth` | `bigint`, **0 dari 280 baris terisi** |
| `l2_gold.kol_metric_monthly.followers_growth` | `bigint`, **0 dari 68 baris terisi** |
| `l1_silver.unified_follower` | Daftar **follower individu**; `followers_count` di sana milik si follower, bukan milik KOL |

---

## 3. Backend Task

### T1 — View/query `growth_30d` *(blocked: menunggu history)*

Hitung dari deret snapshot, **jangan** pakai `followers_growth` yang tersimpan
(alasannya di §5).

> **UPDATE 2026-09-07 — jangan tertukar antara dua hal ini.**
>
> | | `growth_30d` (T1, dokumen ini) | Growth yang sudah tayang |
> |---|---|---|
> | Periode | tepat 30 hari | jarak antar snapshot (10–13 hari) |
> | Sumber | dihitung dari deret snapshot | `kol_profile_card.followers_growth` apa adanya |
> | Status | **masih blocked** — butuh history | **sudah tayang** di list, filter, dan Detail |
> | Label di UI | belum ada | **"Sejak Snapshot Terakhir"** |
>
> Larangan di paragraf atas **tetap berlaku untuk T1**: kalau nanti membangun
> `growth_30d`, hitung dari deret snapshot, jangan pakai kolom tersimpan. Yang tayang
> sekarang bukan T1 dan tidak menggantikannya.

```sql
-- Untuk tiap akun: bandingkan snapshot terbaru dengan snapshot terdekat
-- yang berumur >= 30 hari sebelumnya.
WITH terbaru AS (
    SELECT DISTINCT ON (social_account_id)
           social_account_id, date AS d_now, followers_count AS f_now
      FROM l1_silver.unified_profile
     WHERE followers_count IS NOT NULL AND followers_count > 0
     ORDER BY social_account_id, date DESC
),
pembanding AS (
    SELECT DISTINCT ON (u.social_account_id)
           u.social_account_id, u.date AS d_prev, u.followers_count AS f_prev
      FROM l1_silver.unified_profile u
      JOIN terbaru t ON t.social_account_id = u.social_account_id
     WHERE u.date <= t.d_now - 30
       AND u.followers_count IS NOT NULL AND u.followers_count > 0
     ORDER BY u.social_account_id, u.date DESC   -- yang paling dekat ke batas 30 hari
)
SELECT ksa.kol_id,
       t.f_now, p.f_prev,
       (p.d_prev)                                   AS basis_date,
       (t.d_now - p.d_prev)                         AS actual_window_days,
       round((t.f_now - p.f_prev)::numeric / p.f_prev * 100, 4) AS growth_30d
  FROM terbaru t
  JOIN pembanding p            ON p.social_account_id = t.social_account_id
  JOIN public.kol_social_account ksa ON ksa.social_account_id = t.social_account_id;
```

**Wajib ikut dikembalikan ke API: `actual_window_days`.** Jendela nyata tidak akan
pas 30 hari (tergantung kapan scraping jalan), dan menyembunyikannya membuat angka
tidak bisa diaudit.

Guard yang tidak boleh dilewat:
- `f_prev > 0` — penyebut nol. **19 akun** sekarang punya `followers_count` NULL (4) atau 0 (15).
- `DISTINCT ON` di kedua CTE — mencegah baris ganda kalau nanti ada >1 snapshot yang memenuhi.

### T2 — Bucket Growth Classification *(blocked: menunggu T1 + keputusan produk)*

Bucket dihitung di atas `growth_30d`. **Ambangnya belum boleh ditetapkan** — lihat §7.

### T3 — Rising Creator *(blocked: butuh ≥3 snapshot)*

Definisi apa pun yang memakai momentum/akselerasi butuh **minimal 3 titik**.
Sekarang **0 akun** punya 3 snapshot. Sampai itu ada, Rising Creator hanya bisa
didefinisikan sebagai kombinasi growth + ER + followers pada satu jendela — bukan
momentum sesungguhnya.

### T4 — Parameter API *(baru dikerjakan setelah T1 hidup)*

| Parameter | Tipe | Catatan |
|---|---|---|
| `growth_bucket` | enum | Nilainya menunggu §7 |
| `growth_min` / `growth_max` | number | Persen |
| `min_window_days` | int, default 25 | Buang akun yang jendelanya terlalu pendek |
| `include_unknown` | bool, default `false` | Akun tanpa history — **hari ini 100% populasi** |

**`include_unknown` wajib ada sejak hari pertama.** Tanpa itu, menyalakan filter
Growth menyembunyikan seluruh populasi tanpa penjelasan, dan pengguna akan
menyimpulkan "tidak ada kreator yang cocok" padahal yang benar adalah "belum ada
datanya".

---

## 4. Dependency terhadap History Data

```
Scraping profil berulang
  └─> l0_raw.{ig,tt}_profile_apify           (baris baru per scraped_at)
        └─> l0_harmonization.{instagram,tiktok}_profile
              └─> l1_silver.unified_profile   (baris baru per (account, date))
                    └─> T1 growth_30d  →  T2 bucket  →  T3 Rising  →  T4 API
```

Seluruh jalur transform di atas **sudah ada dan terbukti bekerja** — 25 akun yang
di-scrape dua kali menghasilkan 2 baris `unified_profile` dengan benar. Tidak ada
kode pipeline yang perlu diubah untuk menambah history; yang perlu berubah hanya
**frekuensi** scraping.

---

## 5. Peringatan: `unified_profile.followers_growth` bukan 30D

Kolom ini **valid secara aritmetika** — 25 dari 25 nilai cocok persis saat dihitung
ulang. Tapi periodenya **bukan 30 hari dan tidak tetap**:

```sql
-- ekspresi hidup di l1_silver.sp_build_unified_profile()
(followers_count - prev_followers_count) / prev_followers_count * 100
-- prev_followers_count = LAG(followers_count) OVER (PARTITION BY social_account_id ORDER BY date)
```

`LAG` mengambil snapshot sebelumnya **berapa pun jaraknya**. Jarak nyata sekarang:
**10 hari** (22 akun) dan **13 hari** (3 akun).

> **Jangan tampilkan kolom ini sebagai "growth 30 hari" di Discovery.** Ia sah
> sebagai "perubahan sejak snapshot terakhir", dan hanya itu.

---

## 6. Menunggu Business / Product Decision

| # | Keputusan | Kenapa belum bisa ditetapkan |
|---|---|---|
| 1 | **Ambang bucket** (Fast Growing / Growing / Stable / Declining) | Belum ada satu pun sampel 30D nyata. Menetapkan ambang sekarang berarti menebak |
| 2 | **Toleransi jendela** — apakah 26 hari boleh disebut "30D"? | Menentukan berapa akun lolos filter |
| 3 | **Perlakuan akun tanpa history** — sembunyikan, atau tampilkan bertanda "belum ada data"? | Hari ini menyangkut **100%** populasi |
| 4 | **Definisi Rising Creator** — cukup growth+ER+followers, atau wajib momentum? | Momentum butuh ≥3 snapshot; growth saja butuh 2 |
| 5 | **Cakupan re-scrape** — 1.976 akun yang sudah punya baseline, atau seluruh 7.496? | Keputusan biaya. Referensi harga di `config.py`: IG $0,0026/profil · TikTok $0,0050/profil |

---

## 7. Yang TIDAK perlu dikerjakan

Ditulis eksplisit supaya tidak ada yang mengerjakannya karena mengira perlu:

- ❌ Kolom `growth_30d` / `growth_90d` — turunan murni dari deret snapshot; populasi 7.720 baris, query murah
- ❌ Tabel history followers baru — `unified_profile` sudah menjadi itu, dengan grain terjamin
- ❌ Index tambahan di `unified_profile` — `uq_unified_profile UNIQUE (social_account_id, date)` sudah menyediakan index yang dibutuhkan
- ❌ Perbaikan transform L0→L1 — sudah benar; L0 dan L1 punya kedalaman history identik (1.951 akun 1 hari, 25 akun 2 hari)
- ❌ Mengisi `kol_metric_daily/monthly.followers_growth` — grainnya tanggal posting, bukan tanggal snapshot; salah tempat secara konseptual

---

# Monitoring Priority — Backend Work Later

**Ditambahkan 2026-09-04, diperbarui 2026-09-04 (Rev 2).** Angka hasil query
langsung 2026-09-04, umur data terhadap snapshot 2026-09-03. Audit lengkapnya:
`docs/KOL_DISCOVERY_MONITORING_PRIORITY_AUDIT.md`.

**Dokumentasi, bukan implementasi.** Tidak ada backend/API/frontend yang dibuat.

### Rule sudah ditetapkan Product (Rev 2)

Monitoring Priority = **operational metadata**, bukan creator quality score.
**Tiga** level, ditentukan **rule-based** dan **otomatis** (bukan input manual):

| Level | Rule |
|---|---|
| **High** | Campaign aktif · KOL aktif dipantau · Perubahan/performa tinggi |
| **Medium** | KOL aktif dalam database · Monitoring standar |
| **Low** | Jarang diakses · Tidak ada aktivitas/campaign · Tidak butuh update sering |

> **Tetap blocked, tapi alasannya bergeser.** Yang memblokir sekarang bukan lagi
> "konsepnya belum ada" — konsepnya sudah jelas. Yang memblokir adalah **datanya**:
> dari 6 sinyal yang dibutuhkan rule, **nol** bisa dipakai hari ini. Rinciannya
> di M0.1.

---

## M0. Source Data

### M0.1 Kesiapan per sinyal rule *(Rev 2)*

| Sinyal | Source | Coverage | Siap? | Jenis gap |
|---|---|---:|---|---|
| High · Campaign aktif | `campaigns` → `campaign_kols` → `agency_kol_accounts` → `kol_directory` | **0 · 0%** | **NO** | Data Population Gap |
| High · Aktif dipantau | *(tidak ada)* | — | **NO** | **Data Gap** |
| High · Perubahan/performa tinggi | `l1_silver.unified_profile` (deret snapshot) | **25 · 0,32%** | **NO** | Data Population Gap + Business Decision |
| Medium · KOL aktif | `kol_directory.directory_status` | 7.720 · **100%** | **NO** | **MISMATCH** — 1 nilai unik (`active`) |
| Low · Jarang diakses | `public.audit_log` | **0 baris** | **NO** | Data Population Gap + **Data Gap** |
| Low · Tidak ada aktivitas | `l1_silver.unified_post` | **30 · 0,39%** | **NO** | Data Population Gap |

**Hanya 2 dari kekurangan di atas yang butuh schema baru** (aktif-dipantau,
riwayat akses). Sisanya sudah punya tempat, tinggal terisi.

### M0.2 Jalur join KOL ↔ campaign — sudah utuh, jangan dibuat ulang

```
campaigns.id
  └─ campaign_kols.campaign_id             FK fk_campaign_kols_campaign_id
       └─ .agency_kol_account_id           FK fk_campaign_kols_agency_kol_account_id
            └─ agency_kol_accounts.id
                 └─ .kol_account_id        FK agency_kol_accounts_kol_account_id_fkey
                      └─ kol_directory.id
```

Jembatannya **bukan** langsung ke `kol_directory` — lewat `agency_kol_accounts`
(7.719 baris, **7.719 cocok** dengan `kol_directory.id`). Query uji dengan definisi
"campaign aktif" yang wajar berjalan tanpa error dan mengembalikan **0** — jalurnya
valid, isinya yang kosong.

`campaigns` sudah punya `status`, `start_date`, `end_date`, `deleted_at`,
`tracking_status` (default `'inactive'`), `tracking_start_date`,
`tracking_end_date`, `last_tracked_at`. **Tidak ada kolom campaign yang perlu
ditambahkan.**

### Yang sudah ada dan bisa dipakai

| Sumber | Kolom | Coverage | Catatan |
|---|---|---|---|
| `public.kol_directory` | `last_refreshed_at` `timestamptz` | 7.496 / 7.720 · 97,10% | **Baca peringatan di M4 sebelum memakainya** |
| `public.kol_directory` | `refresh_tier` `varchar(255)` | **0 / 7.720** | Kolom kosong, tanpa CHECK/enum/comment. Tipe & panjangnya cukup menampung `high`/`medium`/`low` |
| `public.kol_directory` | `platform_id` → `platforms.key` | 7.496 · 97,10% | tiktok 4.087 · instagram 3.409 |
| `public.kol_directory` | `followers_count` | 7.498 · 97,12% | Tersedia; **belum ada rule** yang memakainya |
| `l0_raw.ig_profile_apify` / `tt_profile_apify` | `scraped_at`, `social_account_id` | 1.976 akun | **Sumber umur data yang jujur** — lihat M4 |
| `public.scheduler_logs` | 18 kolom | 8 baris | Riwayat eksekusi; grain per (run, akun, category) |

### Yang ada strukturnya tapi kosong

| Sumber | Isi | Implikasi |
|---|---|---|
| `public.scheduler_config` | **0 baris**; kolom `is_active`, `schedule_times jsonb` | Bentuknya jam absolut global, **tanpa kaitan ke KOL atau tier** — tidak cocok untuk interval per-tier walaupun diisi |
| `public.campaigns` | **0 baris** | Input "campaign aktif" tidak ada |
| `public.campaign_kols` | **0 baris** | Idem |
| `public.campaign_tracking_jobs` | **0 baris**; `job_type`, `status`, `scheduled_at`, `attempt_count` | **Periksa dulu tabel ini sebelum membuat tabel antrean baru** — bentuknya sudah job-queue |
| `l2_gold.kol_profile_card.followers_growth` | 25 / 1.976 terisi | Input growth |
| **`public.audit_log`** *(Rev 2)* | **0 baris**; `actor_id`, `actor_role`, `action`, `entity_type`, `entity_id`, `before`/`after` jsonb, `ip_address`, `created_at` | **Kandidat terkuat untuk "jarang diakses"** — bentuknya cocok. Tapi `before`/`after` menyiratkan audit **perubahan**, belum tentu **pembacaan**. Perlu MD12 |
| 12 tabel campaign lain | **0 baris** | Semua turunan `campaigns` |

### Yang perlu dilihat sekali lagi sebelum bikin sesuatu *(Rev 2)*

| Sumber | Isi | Kenapa perlu dicek dulu |
|---|---|---|
| `public.agency_kol_accounts` | **7.719 baris**, FK ke `kol_directory` | Punya `status`, `is_active`, `campaign_tag`, `notes` — semuanya **kosong atau seragam** (`status`=`active` & `is_active`=`true` untuk seluruh 7.719; `campaign_tag` 0; `notes` 0). Seluruh isinya satu batch impor 2026-08-27 dan **tidak pernah diubah** (`updated_at` terisi 1 dari 7.719). **Kalau kolom-kolom itu memang untuk "KOL dikelola/dipantau", tabel baru tidak perlu** |
| `public.kol_tiers` | 5 baris | **Bukan** `refresh_tier`. Ini tier **ukuran creator**. **UPDATE 2026-09-07 — ambangnya sudah dibetulkan (migration 033):** Nano 1.000–9.999 · Micro 10.000–49.999 · **Mid-tier 50.000–499.999** · **Macro 500.000–999.999** · Mega ≥1.000.000. *(Angka lama yang salah: Mid-tier 50.000–99.999, Macro 100.000–999.999.)* Dirujuk `agency_kol_accounts.tier_id` (7.207 terisi) — itu sebabnya perbaikan dilakukan lewat `UPDATE`, bukan hapus-lalu-isi. **Jangan tertukar** |
| `l2_gold.kol_profile_card.media_count` | 1.950 / 1.976 | Proxy aktivitas paling luas (25,26% populasi), tapi **kumulatif seumur akun**, bukan recency — perlu 2 snapshot untuk jadi sinyal, dan itu hanya ada untuk 25 akun |

### Yang TIDAK ada sama sekali

| Yang dicari | Hasil pencarian |
|---|---|
| Kolom mengandung `priorit` di seluruh DB | **0** |
| Routine/view/trigger menyentuh `refresh_tier` | **0** |
| `refresh_interval` / `refresh_frequency` / `monitoring_priority` di kode | **0 hit** |
| **Relasi user/organization ↔ KOL "sedang dipantau"** *(Rev 2)* | **0 tabel, 0 kolom** di seluruh DB |
| **Riwayat view / search / click / session KOL** *(Rev 2)* | **0 tabel**. Kolom `last_viewed` / `last_accessed`: **0** |
| `ScheduleDefinition` di Dagster | **0** — `one_shot_schedules = []` |
| `pg_cron` | Tidak terpasang (extension hanya `plpgsql`) |
| Interval refresh di environment | `.env` hanya `PG_*`, `APIFY_*`, `OUTPUT_DIR` |

> **Peringatan sumber palsu.** Semua kolom di DB yang namanya mengandung "track"
> (`campaigns.tracking_status`, `campaign_kols.last_tracked_at`,
> `campaign_kol_deliverables.first_tracked_at`, `campaign_tracking_jobs`) milik
> domain **campaign content tracking** — melacak konten selama campaign berjalan,
> bukan "KOL ini masuk daftar pantau". `brand.is_competitor_tracked` menandai
> **brand pesaing**, bukan KOL. Di codebase, 43 hit `watch` seluruhnya
> `reel_avg_watch_time`, dan 2 hit `followed` adalah `edge_followed_by`.
> **Jangan pakai satu pun sebagai sinyal "aktif dipantau".**

---

## M1 — Definisi `refresh_tier` *(sebagian terjawab di Rev 2)*

| Yang perlu ditetapkan | Status Rev 2 |
|---|---|
| Daftar nilai sah | **TERJAWAB** — tiga: `high` / `medium` / `low`. `varchar(255)` yang ada sudah cukup |
| Manual, otomatis, atau campuran | **TERJAWAB** — **otomatis**, rule-based |
| Definisi tiap level dalam kalimat | **TERJAWAB** — lihat tabel rule di atas |
| **Sinyal apa yang dibaca, dari kolom mana** | **BELUM** — 6 sinyal, 0 siap (M0.1) |
| **Ambang tiap sinyal** | **BELUM** — MD2 |
| **Kapan dihitung ulang** | **BELUM** — setelah scrape, terjadwal, atau on-demand |
| **Urutan menang antar-sinyal** | **BELUM** — MD10 |

Karena nilainya **otomatis**, `refresh_tier` menjadi **kolom turunan**, bukan kolom
input. Konsekuensinya: ia tidak boleh diisi manual, dan harus ada satu proses yang
bertanggung jawab menghitung ulang. Proses itu belum ada.

**Belum boleh dikerjakan** selama M0.1 masih 0 dari 6.

---

## M2 — Pemetaan tier → interval refresh *(blocked: menunggu MD3)*

Satu-satunya **schema gap** yang ditemukan audit. Tidak ada tempat di database
yang bisa menjawab "High itu tiap berapa jam".

Tiga opsi, lengkap dengan konsekuensinya, ada di
`docs/KOL_DISCOVERY_MONITORING_PRIORITY_AUDIT.md` §10 —
**menunggu approval, belum ada migration yang dibuat.** Ringkasnya:

| Opsi | Perubahan DB | Kapan cocok |
|---|---|---|
| 1 — konstanta di config aplikasi | **nol** | Selama nilai intervalnya masih dicari-cari |
| 2 — tabel `refresh_tier_config` | 1 tabel baru (3–4 baris) | Kalau Next Update / Data Status ingin dihitung di SQL |
| 3 — CHECK constraint di `refresh_tier` | 1 constraint | **Tunda** — mengunci jumlah level yang belum diputuskan |

Rekomendasi audit: **Opsi 1** sampai interval stabil, baru pertimbangkan Opsi 2.

---

## M3 — Query klasifikasi priority *(blocked: menunggu M1)*

Baru bisa ditulis setelah M1 ada. Yang perlu diperhatikan saat menulisnya:

- **Populasi.** Putuskan lebih dulu (MD5) apakah 224 baris tanpa
  `kol_social_account`/`platform_id` masuk hitungan. Mereka **tidak bisa
  di-refresh secara teknis**, apa pun priority-nya.
- **Duplikat.** 277 grup `username_normalized` duplikat (temuan audit
  sebelumnya) membuat satu kreator bisa terhitung dua kali.
- **Jembatan identitas.** Selalu lewat `kol_social_account` → `social_account`,
  **tidak pernah** join by username. Alasannya ada di `scheduler_engine.py:26-32`.
- **Index.** Untuk 7.720 baris, seq scan sudah murah. Jangan tambah index sebelum
  ada query nyata yang lambat.

---

## M4 — Freshness: perbaiki dulu pembilangnya *(bisa dimulai lebih awal)*

**Ini satu-satunya task yang tidak menunggu keputusan priority**, dan ia sudah
memengaruhi filter yang tayang hari ini (Last Updated, Data Status).

Masalahnya:

| Pengujian | Hasil |
|---|---:|
| KOL punya `last_refreshed_at` | 7.496 |
| ↳ **dan** punya baris profil di `l0_raw` | **1.976** |
| ↳ **tapi tidak punya** data apa pun di `l0_raw` | **5.520** |

`kol_directory.source` = `excel_import` untuk 7.718 baris. Untuk 5.520 KOL,
`last_refreshed_at` adalah **nilai warisan impor** — mencatat refresh di sistem
sebelumnya, bukan scrape oleh pipeline ini. (Ia bukan sekadar salinan
`created_at`: hanya 4 baris yang begitu.)

Akibatnya pada perhitungan `freshness = now() − last_refreshed_at`:

| Sumber umur | ≤1h | 2–3h | 4–7h | 8–14h | >14h | tanpa data |
|---|---:|---:|---:|---:|---:|---:|
| `kol_directory.last_refreshed_at` | 0 | 0 | 4 | 0 | **7.492** | 224 |
| `l0_raw.*.scraped_at` *(data nyata)* | 0 | 0 | 7 | 23 | **1.946** | **5.744** |

Rumus `now() − last_refreshed_at` **bisa dihitung** untuk 97,10% populasi —
secara aritmetika tidak ada yang salah. Yang salah adalah **artinya**: untuk
73,6% dari nilai itu, ia tidak menyatakan kapan warehouse ini terakhir punya data
segar.

Yang perlu dikerjakan setelah MD4 dijawab:

- kalau artinya "berhasil ditarik ke warehouse ini" → sediakan `last_scraped_at`
  turunan dari `max(l0_raw.*.scraped_at)` per KOL (**query/view, bukan kolom
  baru** — turunan murni), dan pisahkan dari `last_refreshed_at` warisan;
- kalau artinya "refresh di sistem mana pun" → biarkan apa adanya, tapi UI harus
  berhenti menyiratkan bahwa datanya ada di sistem ini.

**Perbandingan dengan expected interval belum bisa dilakukan sama sekali**,
karena penyebutnya (M2) belum ada. Ini **business/configuration gap**, bukan data
gap: `refresh_tier` 0 terisi, `scheduler_config` 0 baris, tidak ada di config,
env, scheduler, maupun Dagster.

---

## M5 — Parameter API *(baru dikerjakan setelah M1–M3 hidup)*

| Parameter | Tipe | Catatan |
|---|---|---|
| `monitoring_priority` | daftar nilai dari M1 | Jumlah nilainya tergantung MD1 (3 atau 4) |
| `include_unclassified` | boolean | Hari ini **100% populasi** belum terklasifikasi (MD6) |
| `data_age_max_days` | integer | Terpisah dari priority; hanya butuh pembilang M4 |

**Jangan** mengekspos `data_status` / `next_update` sebelum M2 ada — keduanya
butuh penyebut yang belum ada, dan akan mengembalikan nilai yang tampak sah tapi
tidak berarti.

---

## Scheduler Implications

Ini bagian yang paling mudah terlewat: **priority adalah instruksi untuk
penjadwal, dan penjadwalnya belum ada.**

| Kondisi sekarang | Bukti |
|---|---|
| Scheduler **one-shot**, bukan recurring | `scheduler_engine.py:12-16` — *"Tidak ada loop, tidak ada cron, tidak ada retry otomatis"*; `PROFILE_TARGET_LIMIT = 1`, `MAX_RETRIES = 0` |
| Kriteria target = **"belum pernah di-scrape"** | `NOT EXISTS` di tabel profil & post `l0_raw` (`scheduler_engine.py:325-332`) |
| Tidak ada schedule Dagster | `one_shot_schedules = []` (`one_shot.py:325`); state instance hanya berisi 1 instigator bertipe SENSOR |
| Sensor **tidak bisa** memicu refresh | `l0_raw_new_data_sensor` bereaksi pada kedatangan data L0 dan hanya menjalankan transformasi — tidak pernah memanggil Apify |
| Tidak ada penjadwalan di level DB | `pg_cron` tidak terpasang |
| Riwayat eksekusi | 8 baris `scheduler_logs`, 4 run, 4 akun. **Tidak ada satu akun pun yang di-scrape ulang** — 2 baris per akun adalah pasangan `profile`+`post` dari **satu** run |

**Implikasi yang harus disadari sebelum M1 dikerjakan:**

1. Kriteria `NOT EXISTS l0_raw` adalah **kebalikan** dari kebutuhan monitoring.
   Dengan kriteria itu, akun yang sudah pernah masuk L0 **tidak akan pernah
   terpilih lagi** — refresh berulang secara struktural tidak mungkin terjadi.
   Menggantinya adalah perubahan **query**, bukan schema.
2. `db.ORDER_CLAUSES` sudah punya mode `"stale"` =
   `last_refreshed_at ASC NULLS FIRST` (`db.py:26`), tapi itu milik `pipeline.py`
   (jalur Instagram lama), bukan `scheduler_engine.py`. Ada preseden, belum ada
   sambungannya.
3. `last_refreshed_at` **tidak ditulis** oleh scheduler. Satu-satunya penulisnya
   adalah `db.update_profiles()` (`db.py:399`), dipanggil hanya dari `ingest.py:231`
   dan `pipeline.py:304` — jalur Instagram lama. `scheduler_engine.py` dan jalur
   Dagster hanya **membaca** `kol_directory`. Jadi walaupun scheduler dibuat
   recurring hari ini, `last_refreshed_at` tidak akan ikut bergerak.
4. **Biaya.** One-shot itu **disengaja** karena Apify ditagih per hasil
   (`config.py`: IG $0,0026/profil · TikTok $0,0050/profil). Membuatnya recurring
   adalah keputusan anggaran (MD9), bukan keputusan teknis.

---

## Data yang perlu disediakan pipeline / data layer

| Kebutuhan | Kenapa belum ada | Siapa yang menyediakan |
|---|---|---|
| Penanda "terakhir berhasil ditarik ke warehouse ini" per KOL | Hari ini `last_refreshed_at` mencampur warisan impor dengan hasil scrape | Data layer — turunan `max(l0_raw.*.scraped_at)`, bukan kolom baru |
| `last_refreshed_at` yang ikut bergerak saat scrape | Jalur scraping aktif tidak menulisnya (lihat Implikasi #3) | Engineering, setelah MD4 |
| Snapshot profil berulang | 1.951 akun punya **1** snapshot, 25 akun punya 2. Growth/virality butuh ≥2 | Pipeline — hasil langsung dari scheduler recurring |
| Isi `campaigns` / `campaign_kols` | 0 baris; input "campaign aktif" untuk level tertinggi | Modul Campaign, di luar Discovery |
| Nilai `refresh_tier` | 0 terisi; menunggu M1 | Setelah M1 & MD7 |

---

## Menunggu Business / Product Decision

Ringkasan; alasan lengkapnya di audit §10.

### Sudah terjawab di Rev 2

| # | Keputusan | Jawaban |
|---|---|---|
| ~~MD1~~ | Berapa level | **Tiga** — High / Medium / Low |
| ~~MD7~~ | Manual, otomatis, atau campuran | **Otomatis**, rule-based |

### Masih menggantung

| # | Keputusan | Memblokir |
|---|---|---|
| MD2 | **Ambang "performa/perubahan tinggi"** — data followers 97,12% & ER 22,75% ada, artinya "tinggi" belum | Sinyal High #3 |
| MD3 | **Interval tiap level** — High tiap berapa jam? Tidak ada di DB/config/env/scheduler | M2, M5, scheduler |
| MD4 | **Arti `last_refreshed_at`** — refresh di sistem mana pun, atau di warehouse ini? Menyangkut 5.520 KOL | M4, seluruh freshness |
| MD5 | **Perlakuan 224 baris kosong** — tidak bisa di-refresh secara teknis | M3, denominator |
| MD6 | **Perlakuan KOL tanpa priority** — default Medium, atau "belum diklasifikasi"? Hari ini **100%** | M5, UI |
| MD8 | **Boleh recurring?** One-shot hari ini keputusan sadar karena biaya | Seluruh tujuan fitur |
| MD9 | **Anggaran re-scrape** | Cakupan implementasi |
| **MD10** *(Rev 2)* | **Urutan menang antar-sinyal** — satu KOL bisa memenuhi High (campaign aktif) sekaligus Low (tidak ada konten di warehouse) | Seluruh rule |
| **MD11** *(Rev 2)* | **Definisi "KOL aktif dalam database"** — `directory_status` 100% `active`, 1 nilai unik, tidak membedakan apa pun. Perlu sinyal pengganti | Sinyal Medium |
| **MD12** *(Rev 2)* | **Apakah `audit_log` akan mencatat `view`?** Bentuknya audit **perubahan** (`before`/`after`), bukan pembacaan | Sinyal Low #1 |
| **MD13** *(Rev 2)* | **Apakah "belum pernah kita scrape" = "tidak ada aktivitas"?** Hari ini 99,61% KOL tidak punya konten **karena belum di-scrape** | Sinyal Low #2 |
| **MD14** *(Rev 2)* | **Jendela perbandingan** — 7 / 14 / 30 hari? Data yang ada hanya berjarak **10–13 hari** untuk 25 akun; memilih 30 hari = 0 akun memenuhi syarat hari ini | Sinyal High #3 |

> **MD13 adalah yang paling murah sekaligus paling berbahaya kalau dilewat.**
> Ia tidak butuh biaya, schema, maupun scraping — hanya keputusan. Tapi kalau rule
> dijalankan tanpa menjawabnya, **7.690 KOL akan jatuh ke Low secara keliru**,
> dan setiap pekerjaan berikutnya mewarisi kesalahan itu.

---

## Yang TIDAK perlu dikerjakan

- ❌ **Kolom `monitoring_priority` baru** — `refresh_tier` sudah ada, kosong, dan
  tipenya cukup. Kolom kedua yang artinya sama = dua sumber kebenaran.
- ❌ **Kolom `next_refresh_at`** — turunan murni `last_refreshed_at + interval`;
  menyimpannya berarti harus menjaganya tetap sinkron.
- ❌ **Tabel antrean refresh baru** — periksa `campaign_tracking_jobs` dulu
  (0 baris, bentuknya sudah job-queue).
- ❌ **Mengisi `refresh_tier` dengan default** — itu menulis data berdasarkan rule
  yang belum diputuskan.
- ❌ **Index pada `last_refreshed_at` / `refresh_tier`** — 7.720 baris, seq scan
  murah. Tinjau ulang kalau populasi tumbuh ≫100k.
- ❌ **Memakai `directory_status` sebagai sinyal** — 7.720 baris, **satu nilai
  unik** (`active`). Tidak membedakan apa pun.
- ❌ **Memakai rule `dfPrioOf()` dari prototype apa adanya** — empat level (bukan
  tiga), berjalan di atas data mock dan state browser (`state.cart`,
  `state.tracked`, `k.camps`), dan inputnya 0% terisi di database.
- ❌ **Tabel campaign apa pun** *(Rev 2)* — schema campaign **sudah lengkap** dan
  FK-nya utuh sampai `kol_directory` lewat `agency_kol_accounts`. Yang kurang hanya
  datanya (0 baris di 13 dari 14 tabel).
- ❌ **Memakai `agency_kol_accounts.is_active` / `status` sebagai sinyal**
  *(Rev 2)* — 7.719 baris, **satu kombinasi** (`active`/`true`). Sama tidak
  membedakannya dengan `directory_status`.
- ❌ **Memakai kolom `*tracking*` dari domain campaign sebagai "aktif dipantau"**
  *(Rev 2)* — semuanya melacak **konten selama campaign berjalan**, konsep berbeda.
  Lihat peringatan sumber palsu di M0.
- ❌ **Memakai `last_refreshed_at` untuk "jarang diakses" atau "tidak ada
  aktivitas"** *(Rev 2)* — itu **freshness data**, bukan akses user dan bukan
  aktivitas KOL. Keempat konsep terpisah; lihat audit §8.
- ❌ **Tabel access log baru sebelum memeriksa `audit_log`** *(Rev 2)* — tabelnya
  sudah ada dengan bentuk yang cocok (`actor_id`, `action`, `entity_type`,
  `entity_id`, `created_at`, `ip_address`), hanya kosong. Selesaikan MD12 dulu.

---

**Status dokumen:** audit read-only, tidak ada perubahan database, schema, migration,
kode, atau UI. Angka Growth Classification & Rising Creator dari query 2026-09-03;
angka Monitoring Priority dari query 2026-09-04 — Rev 1 (freshness, scheduler,
`refresh_tier`) dan Rev 2 (kelayakan 6 sinyal rule Product), umur data terhadap
snapshot 2026-09-03.
