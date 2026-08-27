# Orkestrasi Dagster — Pipeline KOL

Orkestrasi untuk database **`kol`**:

```
l0_raw → l0_harmonization → l1_silver → feature → l2_gold
```

Dagster tidak menghitung apa pun sendiri. Ia menjaga **urutan** (asset mana
setelah asset mana), menjalankannya **terjadwal**, dan mencatat **apa yang
berhasil dan apa yang gagal**. Perhitungannya tetap di SQL/procedure yang sudah ada.

> **Status: 12 asset aktif**, mencakup jalur penuh
> `l0_harmonization → l1_silver → feature → l2_gold`.
> Terakhir diperbarui setelah SCRUM-513 dan SCRUM-516.

| Grup | Asset | Jumlah |
|---|---|---|
| `l0_harmonization` | `instagram_profile`, `tiktok_profile`, `instagram_post`, `tiktok_post` | 4 |
| `l1_silver` | `unified_profile`, `unified_post` | 2 |
| `feature` | `ig/tt_engagement_analysis`, `ig/tt_post_analysis` | 4 |
| `l2_gold` | `kol_metric_daily`, `kol_metric_monthly` | 2 |
| | **total** | **12** |

Schema `l2_gold` berisi **8 tabel**; enam di antaranya (`post_metric`,
`kol_profile_card`, `content_format_daily`, dan tiga tabel audience) sudah punya
schema tapi **belum punya asset** — lihat catatan di bawah graf dependency.

---

## Isi folder

| File | Fungsi |
|---|---|
| `pyproject.toml` | Metadata paket + dependency. `[tool.dagster] module_name` memberi tahu `dagster dev` di mana `Definitions` berada |
| `workspace.yaml` | Menunjuk modul yang memuat `Definitions` |
| `dagster.yaml` | Konfigurasi instance (timeout import, penyimpanan log) |
| `.env.example` | Contoh variabel environment. Nilai asli ada di `.env` root, yang sudah di-`.gitignore` |
| `cek_koneksi.py` | Verifikasi koneksi, **read-only** |
| `kol_orchestration/resources.py` | Koneksi database `kol` — `call_procedure()`, `call_function()`, `count_rows()`, `scalar()` |
| `kol_orchestration/repository.py` | `Definitions` — daftar asset, job, schedule, resource |
| `kol_orchestration/assets/harmonization.py` | 4 asset `l0_harmonization` — memanggil `sp_sync_*()` |
| `kol_orchestration/assets/silver.py` | 2 asset `l1_silver` — memanggil `sp_build_unified_*()` |
| `kol_orchestration/assets/feature_engagement.py` | `ig/tt_engagement_analysis` |
| `kol_orchestration/assets/feature_post.py` | `ig/tt_post_analysis` |
| `kol_orchestration/assets/gold.py` | `kol_metric_daily`, `kol_metric_monthly` |

---

## Kredensial

Tidak ada kredensial di dalam kode. `repository.py` membaca `.env` di **root
project** (satu tingkat di atas folder ini) — file yang sama dengan yang dipakai
pipeline scraping, supaya kredensialnya tidak terduplikasi di dua tempat.

Urutan pembacaan:

1. `KOL_DB_URL` bila diisi
2. kalau kosong, dirakit dari `PG_USER`, `PG_PASSWORD`, `PG_HOST`, `PG_PORT`, `PG_DB`

Normalnya **tidak ada yang perlu ditambahkan** — kelima variabel `PG_*` sudah ada
di `.env`.

---

## Graf dependency aktual

```
instagram_profile ─┐
tiktok_profile ────┴─► unified_profile ─┐
                                        │
instagram_post ────┐                    │
tiktok_post ───────┴─► unified_post ◄───┘
                          │
      ┌───────────────────┼───────────────────┬──────────────────┐
      ▼                   ▼                   ▼                  ▼
ig_engagement_    tt_engagement_        ig_post_analysis   tt_post_analysis
   analysis          analysis           tt_post_analysis
      (feature — keempatnya membaca L1, tidak pernah L0)

unified_post ──┐
               ├─► kol_metric_daily ─► kol_metric_monthly
unified_profile┘        (l2_gold)           (l2_gold)
```

`l2_gold` berisi **8 tabel**, tapi baru **2** yang punya asset. Enam sisanya
(`post_metric`, `kol_profile_card`, `content_format_daily`,
`audience_demographics_daily`, `audience_geo_daily`, `audience_interest_daily`)
dibuat migration 023 dan **sengaja masih kosong** — schema-nya ada, logic
pengisiannya belum dirancang. Tidak ada asset skeleton untuk keenamnya: asset
yang tidak punya logic hanya akan menghasilkan kotak hijau tanpa arti.

Rincian tiap tabel ada di `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md` §17.13.

Dua hal yang perlu dicatat:

- **`kol_metric_monthly` membaca `kol_metric_daily`, BUKAN L1.** Rumus metriknya
  hanya ditulis sekali, di asset harian.
- Keempat asset `feature` membaca `l1_silver`, tidak pernah `l0_harmonization`
  atau `l0_raw`. `feature` dan `l2_gold` adalah dua cabang paralel di atas L1 —
  `l2_gold` tidak membaca `feature`.
- `sp_sync_all()` **sengaja tidak dipakai**: ia membungkus ke-13 pemanggilannya
  dengan `EXCEPTION WHEN OTHERS THEN RAISE NOTICE` sehingga selalu sukses walau
  anaknya gagal. Keempat pekerja harmonization dipanggil langsung.

---

## Menjalankan

```powershell
# 1. Pasang dependency (sudah terpasang di venv/)
.\venv\Scripts\pip.exe install -e .\orchestration

# 2. Riwayat run disimpan di folder tetap
#    (tanpa ini Dagster memakai folder sementara acak dan riwayatnya hilang)
$env:DAGSTER_HOME = "D:\intern\scrapper-project\orchestration\.dagster_home"

# 3. Verifikasi koneksi — READ-ONLY, tidak menulis apa pun
.\venv\Scripts\python.exe orchestration\cek_koneksi.py

# 4. Buka UI Dagster di http://localhost:3000
cd orchestration
dagster dev
```

Materialize satu atau beberapa asset tanpa UI:

```powershell
cd orchestration
..\venv\Scripts\dagster.exe asset materialize -m kol_orchestration.repository `
    --select "kol_metric_daily,kol_metric_monthly"
```

Dagster menjaga urutannya sendiri: memilih `kol_metric_monthly` saja tidak akan
menjalankan ulang yang harian, tapi memilih keduanya menjalankan daily lebih dulu.

---

## Beda dengan project referensi

Pola arsitekturnya meniru project Dagster lain (database `tsdb`), tapi ada satu
perbedaan teknis yang penting dan sudah ditangani di `resources.py`:

| | `tsdb` | **`kol`** |
|---|---|---|
| Pengisi L1 | `sp_sync_unified_*()` — **PROCEDURE** → `CALL` | `sp_build_unified_*()` — **FUNCTION** → `SELECT` |
| Pengisi harmonization | pg_cron / asset | `sp_sync_*()` — **PROCEDURE** → `CALL` |

Karena itu `PostgresResource` menyediakan dua method terpisah, `call_procedure()`
dan `call_function()`. Salah pilih akan gagal saat runtime, jadi sengaja tidak
digabung jadi satu method serbaguna.

`tsdb` dan `kol` adalah **dua database berbeda untuk produk berbeda**. Kemiripan
nama schema (`l1_silver`, `feature`) hanya karena sama-sama memakai konvensi
medallion — struktur tabelnya berbeda dan tidak saling terhubung.

---

## Rencana pengisian

| Fase | Isi | Prasyarat |
|---|---|---|
| **0** ✅ | Skeleton: `pyproject`, `resources.py`, `repository.py` | — |
| **1a** ✅ | `ig/tt_engagement_analysis` | UNIQUE constraint (migration 016) |
| **1c** ✅ | `ig/tt_post_analysis` | UNIQUE constraint + migration 017/018 |
| **1b** ✅ | 4 asset harmonization + 2 asset L1 | migration 019/020 (dedup + `has_insights`) |
| **5a** ✅ | `l2_gold.kol_metric_daily` (SCRUM-513) | migration 021 |
| **5b** ✅ | `l2_gold.kol_metric_monthly` (SCRUM-516) | migration 022 |
| **2** | `cpe` | Keputusan `post_type` basis fee |
| **3** | comments / follower / Insights | Scraping komentar, scraping follower, OAuth Insights |
| **4** | authenticity, audience quality, brand fit, content category | **Definisi algoritma** — keputusan bisnis |
| **5c** | asset untuk 6 tabel L2 sisanya | schema sudah ada (migration 023), **asset belum dibuat** |

Rincian kesiapan tiap kolom feature ada di
`docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md` §16; dokumentasi lengkap kedua tabel
L2 Gold ada di §17.
