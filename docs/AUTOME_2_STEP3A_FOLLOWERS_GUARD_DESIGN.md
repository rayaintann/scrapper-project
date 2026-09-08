# Step 3A — Rancangan Sanity Guard `followers_count`

**Read-only · 8 September 2026 · rancangan saja, tidak ada implementasi**

Tidak ada perubahan DB/schema, Growth, endpoint, UI, maupun bulk scraping.

Baseline: `AUTOME_2_FULL_TRACE_AUDIT.md` + `AUTOME_2_STEP2B_FOLLOWERS_INVESTIGATION.md`.

---

# Temuan yang mengubah rancangan

## Temuan 1 — "followers < 1000 = invalid" memang berbahaya, dan angkanya besar

| Roster aktif | Akun |
|---|---:|
| `followers_count = 0` | **14** |
| 1 – 99 | **133** |
| 100 – 999 | **157** |
| **Total < 1.000** | **304** |
| NULL | 222 |

Aturan ambang mutlak akan salah menolak **304 KOL yang sah**. Kekhawatiran lo terbukti.

## Temuan 2 — SELURUH nilai kecil yang rusak adalah **snapshot pertama**

| | Akun |
|---|---:|
| Punya **1** snapshot saja | **1.948** |
| Punya ≥2 snapshot | **25** |

Dan di antara 25 pasangan snapshot yang ada:

| Cek | Hasil |
|---|---:|
| Turun >90% | **0** |
| Naik >10× | **0** |

**Guard yang hanya membandingkan dengan snapshot sebelumnya tidak akan menangkap satu pun kasus rusak hari ini** — karena semuanya snapshot pertama. Ini yang paling menentukan bentuk aturannya.

## Temuan 3 — untuk setiap nilai kecil yang rusak, roster SELALU tersedia sebagai pembanding

| Baris L0 TikTok ber-`fans` < 1.000 | Akun |
|---|---:|
| Total | **39** |
| Roster > 1.000 | **39 (100%)** |
| Roster ≤ 1.000 | **0** |
| Roster NULL | **0** |

Tidak ada satu pun kasus di mana nilai kecil itu didukung roster. Roster adalah pembanding yang tersedia justru ketika snapshot sebelumnya tidak ada.

## Temuan 4 — sinyal profil kosong (khusus TikTok)

`likes_count` (heart) dan `video_count` dari `authorMeta`:

| `fans` | Baris | `video=0` | `likes=0` | **`video` DAN `likes` = 0** |
|---|---:|---:|---:|---:|
| 0 | 12 | 9 | 10 | **9** |
| 1 – 99 | 19 | 14 | 12 | **12** |
| 100 – 999 | 8 | 4 | **0** | **0** |
| **≥ 1.000** | **1.019** | 2 | **0** | **0** |

**`likes_count = 0` tidak pernah terjadi pada akun ber-`fans` ≥ 1.000 — nol dari 1.019.** Pembandingnya: rata-rata `heart` akun normal **67.019.939**.

Tapi sinyal ini **tidak cukup sendirian**: `emilutfi` punya `fans=16, heart=9, video=13` — terlihat seperti akun kecil yang hidup, padahal rosternya **936.700**. Sinyal profil-kosong menangkap 21 dari 39; sisanya butuh pembanding.

## Temuan 5 — bukan eksklusif TikTok, hanya jauh lebih jarang di Instagram

| Platform | Baris L0 | `followers` < 1.000 | Rasio |
|---|---:|---:|---:|
| TikTok | 1.058 | **39** | 3,7% |
| Instagram | 957 | **15** | 1,6% |

Guard sebaiknya **berlaku untuk kedua platform**, bukan hanya TikTok.

---

# A. Recommended Guard Rule

Tiga lapis, dievaluasi berurutan. Hanya lapis 1 yang menolak mutlak.

## Lapis 1 — Invalid secara struktural (tanpa pembanding)

```
JIKA followers_count < 0            -> INVALID
JIKA followers_count IS NULL        -> LEWATKAN (bukan invalid; "tidak diketahui")
```

Nilai negatif tidak punya arti apa pun untuk followers. Tidak ada sentinel seperti `likes = -1` pada post — jadi negatif = rusak.

NULL **bukan** kasus guard: pipeline sudah memperlakukannya sebagai "tidak diketahui", dan growth sudah mengembalikan NULL. Jangan diubah.

## Lapis 2 — Keruntuhan tak masuk akal (butuh pembanding)

```
referensi := COALESCE(
    followers_count snapshot SEBELUMNYA milik akun ini,   -- prioritas 1
    kol_directory.followers_count                          -- prioritas 2
)

JIKA referensi IS NULL              -> LEWATKAN   (tidak ada dasar menilai)
JIKA referensi < AMBANG_DASAR       -> LEWATKAN   (akun memang kecil)
JIKA followers_count < referensi × RASIO_RUNTUH -> SUSPECT
```

Nilai awal yang saya sarankan, dan alasannya:

| Konstanta | Usulan | Alasan berbasis data |
|---|---|---|
| `AMBANG_DASAR` | **1.000** | Di bawah ini akun memang kecil (304 akun sah). Guard sengaja **tidak berlaku** di sana |
| `RASIO_RUNTUH` | **0,10** (turun >90%) | Di 25 pasangan snapshot yang ada, penurunan terbesar **0,051%**. Ambang 90% berjarak sangat jauh dari perilaku nyata |

**Prioritas pembanding itu penting.** Snapshot sebelumnya lebih dipercaya daripada roster karena roster bisa basi 2–3 tahun (terbukti di Step 2B). Roster dipakai hanya kalau snapshot sebelumnya tidak ada — dan justru itulah kondisi 1.948 akun hari ini.

## Lapis 3 — Profil kosong (corroborating, khusus platform yang punya sinyalnya)

```
JIKA platform = 'tiktok'
 DAN followers_count < AMBANG_DASAR
 DAN likes_count = 0
 DAN video_count = 0            -> SUSPECT
```

Dipakai untuk akun yang **tidak punya pembanding sama sekali** (roster NULL dan belum ada snapshot). Menangkap 21 dari 39 kasus tanpa perlu referensi apa pun.

Instagram tidak punya padanan sekuat ini di kolom L0 saat ini, jadi lapis 3 khusus TikTok. **Itu perbedaan perilaku antar-platform yang disengaja dan harus didokumentasikan**, bukan kelalaian.

---

# B. Kenapa aturan ini aman untuk KOL kecil yang sah

| Pengaman | Efeknya |
|---|---|
| **Guard hanya aktif kalau ada pembanding** | Akun tanpa referensi tidak pernah ditolak lapis 2 |
| **`AMBANG_DASAR` diterapkan pada REFERENSI, bukan pada nilai baru** | Akun ber-referensi 480 tidak pernah dinilai, berapa pun nilai barunya. Inilah yang melindungi 304 akun kecil |
| **Rasio, bukan angka mutlak** | Akun 800 → 700 lolos. Akun 4.500.000 → 17 tidak |
| **Ambang 90% berjarak jauh dari perilaku nyata** | Penurunan terbesar yang pernah terjadi: **0,051%** |
| **Lapis 3 butuh TIGA kondisi bersamaan** | `fans` kecil **dan** `heart=0` **dan** `video=0`. Akun kecil yang hidup (`ayobersyucure` 635/3.378/15) lolos |

## Uji balik terhadap 304 akun kecil yang sah

Ketiganya tidak akan menyentuh mereka:

- Lapis 1 — nilainya positif, tidak kena.
- Lapis 2 — referensinya (roster mereka sendiri) < 1.000, jadi guard tidak berlaku.
- Lapis 3 — hanya kena kalau `heart` dan `video` dua-duanya nol; akun kecil yang benar-benar aktif punya keduanya.

## Yang jujur harus disebut: false positive yang mungkin terjadi

Akun yang **benar-benar** runtuh >90% (di-rebrand, dibersihkan, atau kehilangan massal) akan ditandai suspect. Itu konsekuensi yang saya terima — dan **justru alasan kenapa rekomendasinya menandai, bukan menghapus** (§ berikut).

---

# C. Titik implementasi

## Rekomendasi: **`l1_silver.sp_build_unified_profile()`**

### Kenapa L1, bukan yang lain

| Kandidat | Menahan sebelum growth? | Raw terjaga? | Memperbaiki 54 nilai yang SUDAH ada? | Cakupan |
|---|---|---|---|---|
| Sebelum L0 (`tt_raw_store.py`) | ✅ | ⚠ hanya kalau kolom di-NULL-kan dan `raw_payload` dibiarkan | **❌ tidak** | per-platform, dua tempat |
| Harmonization (`sp_sync_*_profile`) | ✅ | ✅ | ✅ | per-platform, dua procedure |
| **L1 (`sp_build_unified_profile`)** | **✅** | **✅** | **✅** | **satu tempat, dua platform** |
| L2 (`gold_profile.py`) | **❌ TERLAMBAT** | ✅ | sebagian | — |

Tiga alasan menentukan:

1. **Growth dihitung di sini.** `sp_build_unified_profile()` sudah menghitung `followers_growth` dari pasangan snapshot. Guard di L2 tidak akan mencegah nilai rusak jadi **penyebut** growth berikutnya.
2. **54 nilai rusak sudah ada di L0 dan L1 hari ini.** Guard di ingest hanya melindungi scrape berikutnya. Guard di L1 ikut membersihkan yang lama setiap kali procedure dijalankan ulang.
3. **Procedure ini sudah memegang snapshot sebelumnya.** `prev_followers_count` sudah dihitung untuk growth — pembandingnya sudah ada di tangan, tidak perlu query baru.

### Konsekuensi yang harus disepakati

Mengubah `sp_build_unified_profile()` berarti **satu file migration baru** (`CREATE OR REPLACE FUNCTION`). Itu **bukan perubahan schema tabel** — tidak ada kolom baru, tidak ada ALTER TABLE. Pola yang sama persis dipakai migration 024, 031, dan 034.

Saya sebutkan ini terang-terangan karena instruksi Step 3A melarang migration; yang saya maksud adalah **Step 3B akan membutuhkannya**, dan itu perlu persetujuan lo.

### Kalau migration benar-benar tidak diinginkan

Alternatif tanpa migration: guard di `tt_raw_store.py` + `raw_store.py` — NULL-kan kolom `follower_count`/`followers_count`, biarkan `raw_payload` utuh. Kelemahannya jelas: **tidak memperbaiki 54 nilai yang sudah ada**, dan aturannya hidup di dua tempat. Saya tidak menyarankannya sebagai pilihan utama.

---

# Perlakuan: reject, jangan-propagate, atau flag?

## Rekomendasi: **jangan propagate, dan pertahankan raw** — bukan reject, bukan sekadar flag

| Opsi | Penilaian |
|---|---|
| **Reject/drop di L0** | ❌ Melanggar prinsip append-only dan menghapus bukti. `raw_store` sendiri menyatakan tidak punya jalur DELETE/UPDATE |
| **Flag saja, tetap propagate** | ❌ Nilai rusak tetap jadi penyebut growth. Tidak menyelesaikan masalah |
| **Jangan propagate, raw tetap utuh** | ✅ **Ini yang disarankan** |

Mekanismenya:

- `l0_raw.*` **tidak disentuh sama sekali** — baris tetap masuk apa adanya, `raw_payload` utuh, `follower_count` asli tetap tersimpan. Audit dan debugging tetap mungkin.
- Di L1, baris yang suspect ditulis dengan **`followers_count = NULL`**, bukan dengan nilai rusaknya.
- NULL adalah bahasa yang **sudah dipakai** seluruh pipeline untuk "tidak diketahui" — growth sudah mengembalikan NULL untuk penyebut NULL, tier sudah NULL untuk followers NULL (migration 034). **Tidak ada konsumen hilir yang perlu diubah.**

Kalau nanti ingin lebih dari itu (misalnya kolom `followers_guard_reason` untuk review), itu **perubahan schema** dan sebaiknya jadi keputusan terpisah. Untuk Step 3B, NULL + baris log sudah cukup dan tidak menambah kolom apa pun.

---

# D. Expected Behavior

`AMBANG_DASAR = 1.000`, `RASIO_RUNTUH = 0,10`

| # | Kondisi | Referensi | Hasil | Alasan |
|---|---|---|---|---|
| 1 | **Snapshot pertama = 500**, roster NULL | — | **LOLOS** → `followers_count = 500` | Tidak ada dasar menilai. Guard tidak menebak |
| 2 | **Snapshot pertama = 500**, roster = 480 | 480 | **LOLOS** → 500 | Referensi < 1.000 → guard tidak berlaku. Inilah pelindung 304 akun kecil |
| 3 | **Snapshot pertama = 500**, roster = 4.500.000 | 4.500.000 | **SUSPECT** → `NULL` | 500 < 450.000 |
| 4 | prev = 500, current = **700** | 500 | **LOLOS** → 700 | Referensi < 1.000 |
| 5 | prev = **4.500.000**, current = **17** | 4.500.000 | **SUSPECT** → `NULL` | 17 < 450.000. Kasus `zeejkt48` |
| 6 | prev = 4.500.000, current = **4.600.000** | 4.500.000 | **LOLOS** → 4.600.000 | Naik, jelas wajar |
| 7 | current = **NULL** | apa pun | **LOLOS sebagai NULL** | Perilaku existing, tidak diubah |
| 8 | current = **−1** | apa pun | **INVALID** → `NULL` | Lapis 1, tanpa perlu referensi |
| 9 | prev = 2.000.000, current = **1.500.000** (turun 25%) | 2.000.000 | **LOLOS** | 1.500.000 > 200.000 |
| 10 | TikTok, current = 40, roster NULL, `heart=0`, `video=0` | — | **SUSPECT** → `NULL` | Lapis 3 |
| 11 | TikTok, current = 635, roster NULL, `heart=3.378`, `video=15` | — | **LOLOS** | Akun kecil yang hidup (`ayobersyucure`) |
| 12 | prev = 1.200, current = **50** | 1.200 | **SUSPECT** → `NULL` | Referensi ≥ 1.000 dan runtuh >90%. Perlu review manual |

Kasus 12 adalah false positive yang paling mungkin. Karena hasilnya NULL dan bukan penghapusan, `raw_payload` tetap menyimpan 50 dan bisa ditinjau.

---

# E. Dampak ke Growth

## Skenario yang dicegah: `4.500.000 → 17 → 4.500.000`

### Tanpa guard

| Snapshot | followers | `prev` | growth |
|---|---:|---:|---|
| 1 | 4.500.000 | — | NULL |
| 2 | **17** | 4.500.000 | **−99,9996%** |
| 3 | 4.500.000 | **17** | **+26.470.488%** |

Dua angka absurd dari satu nilai rusak. Yang kedua jauh lebih merusak: `gClass` akan menandai akun ini **"exploding"**, dan kalau threshold classification dikalibrasi dari sebaran, satu baris ini bisa menggeser seluruh kalibrasi.

### Dengan guard

| Snapshot | followers tersimpan | `prev` | growth |
|---|---:|---:|---|
| 1 | 4.500.000 | — | NULL |
| 2 | **NULL** (suspect) | — | **NULL** |
| 3 | 4.500.000 | **4.500.000** *(snapshot 1)* | **0%** — benar |

## Mekanisme intinya

Guard bukan sekadar menyembunyikan satu angka jelek di layar. Yang dicegah adalah **nilai rusak menjadi PENYEBUT perhitungan growth berikutnya**.

Syaratnya: pencarian `prev` harus **melewati** baris ber-`followers_count` NULL, bukan berhenti di sana. Rumus growth sekarang sudah mengambil snapshot terdekat yang lebih kecil tanggalnya — perlu dipastikan ia mencari baris terdekat **yang followers-nya tidak NULL**. Itu bagian dari verifikasi Step 3B.

## Kondisi hari ini

| Fakta | Nilai |
|---|---|
| Akun ber-nilai rusak yang sudah punya 2 snapshot | **0** |
| Growth yang sudah tercemar hari ini | **0** |
| Akun ber-nilai rusak yang menunggu snapshot kedua | **54** |

**Belum ada kerusakan. Tapi 54 bom waktu sedang menunggu scrape berikutnya** — dan Step P0-4 (scheduler profil berkala) justru akan memicunya. Itu sebabnya guard harus mendahului scraping berkala.

---

# F. File yang akan diubah pada Step 3B

**Disebutkan saja — belum disentuh.**

| # | File | Perubahan | Sifat |
|---|---|---|---|
| 1 | `migrations/035_followers_sanity_guard.sql` *(baru)* | `CREATE OR REPLACE FUNCTION l1_silver.sp_build_unified_profile()` — tambah lapis 1–3 dan pastikan pencarian `prev` melewati NULL | Migration procedure, **bukan schema tabel** |
| 2 | `tests/test_followers_guard.py` *(baru)* | Uji kontrak SQL migration, mengikuti pola `tests/test_identity_guard.py` | Test |
| 3 | *(opsional)* `docs/` | Catat ambang yang disepakati | Dokumentasi |

**Yang TIDAK disentuh:** `tt_raw_store.py`, `raw_store.py`, `tiktok_pipeline.py`, `pipeline.py`, `gold_profile.py`, `gold.py`, seluruh endpoint, seluruh UI, dan seluruh tabel.

---

# Yang perlu keputusan lo sebelum Step 3B

| # | Pertanyaan | Usulan saya |
|---|---|---|
| **1** | `AMBANG_DASAR` — di bawah berapa guard tidak berlaku? | **1.000** |
| **2** | `RASIO_RUNTUH` — turun berapa persen dianggar suspect? | **90%** (rasio 0,10) |
| **3** | Boleh menambah satu migration `CREATE OR REPLACE FUNCTION`? | **Ya** — tanpa itu 54 nilai lama tidak bisa dibersihkan |
| **4** | Lapis 3 (profil kosong) khusus TikTok — setuju perbedaan antar-platform? | **Ya**, dan didokumentasikan |
| **5** | Suspect → NULL, atau perlu kolom alasan untuk review? | **NULL dulu.** Kolom alasan = perubahan schema, keputusan terpisah |

---

*Read-only. Tidak ada implementasi, perubahan DB/schema, perubahan Growth, endpoint, UI, maupun scraping. Seluruh angka diukur langsung ke database 8 September 2026 lewat sesi `set_session(readonly=True)`.*
