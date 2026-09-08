# Step 2B — Investigasi Followers: roster vs L2

**Read-only · 8 September 2026 · tidak ada perubahan DB, migration, atau Growth calculation**

Menindaklanjuti temuan T2 di `AUTOME_2_FULL_TRACE_AUDIT.md`: 1.024 / 1.972 akun punya `kol_directory.followers_count` berbeda dari `l2_gold.kol_profile_card.followers_count`.

---

# Kesimpulan singkat

**Ada DUA penyebab yang berbeda, dan keduanya butuh penanganan berbeda.**

| # | Penyebab | Akun | Siapa yang benar |
|---|---|---:|---|
| **1** | **Roster basi** — tidak pernah di-refresh sejak 2023–2024 | ~970 | **L2** |
| **2** | **Nilai scrape TikTok rusak** — L2 berisi 0/9/17 untuk akun berjuta follower | **54** | **Roster** |

Menjadikan L2 source of truth tanpa penjaga akan memperbaiki ~970 akun **dan merusak 54 akun**.

---

# 1. Kenapa berbeda

## Bukti pertama — roster SELALU lebih tua. Nol pengecualian.

| Perbandingan tanggal | Akun |
|---|---:|
| Mismatch total | **1.024** |
| `last_refreshed_at` **lebih tua** dari `profile_snapshot_date` | **1.024 (100%)** |
| Roster lebih baru | **0** |
| Tanggal sama | **0** |

Tidak ada satu pun kasus di mana roster lebih baru. Arah perbedaannya konsisten.

## Bukti kedua — saat keduanya segar, mereka sepakat sempurna

| `last_refreshed_at` | `profile_snapshot_date` | Akun | Berbeda |
|---|---|---:|---:|
| **2026-08-14** | **2026-08-14** | **912** | **0** |
| 2024-05-11 | 2026-08-18 | 151 | 151 |
| 2024-05-09 | 2026-08-18 | 118 | 117 |
| 2024-05-11 | 2026-08-17 | 62 | 57 |
| 2024-10-07 | 2026-08-18 | 43 | 43 |
| 2023-10-03 | 2026-08-18 | 13 | 13 |

**912 akun yang di-refresh pada hari yang sama dengan snapshot L2: nol perbedaan.** Rantai pipeline-nya benar. Yang bermasalah adalah roster yang tidak ikut diperbarui.

## Bukti ketiga — bedanya per platform, dan sebabnya ada di kode

| Platform | Punya keduanya | Berbeda | % |
|---|---:|---:|---:|
| **Instagram** | 931 | **16** | **1,7%** |
| **TikTok** | 1.041 | **1.008** | **96,8%** |

Sebabnya struktural, bukan kebetulan:

| Script | Flag `--update-db` | Memanggil `db.update_profiles()` | Roster ikut ter-refresh |
|---|---|---|---|
| `pipeline.py` (Instagram) | **✅ ada**, default aktif | **✅ ya** | **✅ ya** |
| `tiktok_pipeline.py` | **❌ tidak ada** | **❌ tidak pernah** | **❌ tidak** |

Diverifikasi: `grep -n "update_profiles" tiktok_pipeline.py` → **0 hasil**.

Jadi setiap kali TikTok di-scrape, hasilnya masuk L0 → L1 → L2, tetapi `kol_directory.followers_count` tetap memakai nilai dari 2023–2024.

---

# 2. Source of truth menurut implementation existing

| Konsumen | Membaca | Dokumentasi |
|---|---|---|
| Endpoint list `followers` | `kol_directory.followers_count` | `kolDirectory.ts`: *"followers and tier stay on kol_directory, which is the agreed source of truth for both"* |
| Filter `follMin` | idem | — |
| `kol_tiers` band → `tier` | idem | — |
| **Growth** | `unified_profile.followers_count` → L2 | `sp_build_unified_profile` |
| Detail `gold.cards[].followers` | `kol_profile_card.followers_count` | — |

**Jadi requirement existing menyatakan roster sebagai source of truth untuk followers dan tier** — sementara Growth dihitung dari L2. Itulah sumber ketidakcocokan yang terlihat di UI.

---

# 3. Klasifikasi penyebab

| Kandidat penyebab | Terbukti? | Bukti |
|---|---|---|
| **Stale roster** | **✅ YA — penyebab utama** | 1.024/1.024 roster lebih tua; TikTok tidak punya jalur update |
| **Snapshot lebih baru** | ✅ ya, sisi lain dari yang sama | L2 semuanya Agu 2026 |
| **Account mapping salah** | **❌ TIDAK** | `r_platform = l2_platform` untuk seluruh 1.972 baris. Tidak ada IG tertaut ke TikTok |
| **Salah data / scrape rusak** | **✅ YA — penyebab kedua** | 54 akun bernilai mustahil, semuanya TikTok |
| **Scraping** | ✅ untuk penyebab #2 | `clockworks/tiktok-scraper` mengembalikan `follower_count = 17` |
| **Pipeline** | ✅ untuk penyebab #1 | `tiktok_pipeline.py` tidak menulis balik ke roster |
| **Sebab lain** | ❌ | — |

## Penyebab #2 — nilai L2 yang mustahil

| Rentang nilai L2 | Akun |
|---|---:|
| **0** | **15** |
| 1 – 99 | **25** |
| 100 – 999 | **14** |
| ≥ 1.000 (normal) | 1.918 |

**54 akun** bernilai di bawah 1.000. Dari jumlah itu, **33 akun** rosternya di atas 100.000 — jelas rusak.

| Username | Roster | **L2** | Snapshot | Platform |
|---|---:|---:|---|---|
| `zeejkt48` | 4.500.000 | **17** | 2026-08-14 | tiktok |
| `lydiaaas__` | 3.600.000 | **9** | 2026-08-14 | tiktok |
| `machan15` | 3.400.000 | **0** | 2026-08-14 | tiktok |
| `adeljkt48` | 3.100.000 | **0** | 2026-08-14 | tiktok |
| `lauratheux` | 1.500.000 | **0** | 2026-08-17 | tiktok |
| `notriisaaa` | 1.100.000 | **1** | 2026-08-17 | tiktok |
| `xeronav` | 1.100.000 | **2** | 2026-08-17 | tiktok |
| `emilutfi` | 936.700 | **16** | 2026-08-17 | tiktok |
| `adam.vt7` | 711.400 | **5** | 2026-08-17 | tiktok |
| `meandthingss` | 521.500 | **187** | 2026-08-17 | tiktok |

**Seluruhnya TikTok. Nol kasus di Instagram.**

### Trace `zeejkt48` — layer pertama tempat nilai rusak muncul

```
clockworks/tiktok-scraper  →  follower_count = 17          ← RUSAK DI SINI
   ↓
l0_raw.tt_profile_apify        2026-08-14 · 17 · zeejkt48
   ↓  sp_sync_tiktok_profile()
l0_harmonization.tiktok_profile                    17
   ↓  sp_build_unified_profile()
l1_silver.unified_profile      2026-08-14 · 17 · source apify
   ↓  gold_profile.py (DISTINCT ON, snapshot terbaru)
l2_gold.kol_profile_card                           17
```

**Nilai rusak berasal dari actor, dan lolos seluruh empat layer tanpa satu pun penjaga.** Tidak ada bug di pipeline — pipeline meneruskan apa yang diterimanya, persis seperti desainnya.

Konsekuensi lain: akun-akun ini mendapat `tier` yang salah. `zeejkt48` dengan 17 follower jatuh ke Nano, bukan Mega.

---

# 4. Sample nyata

## Selisih kecil (<1.000) — pertumbuhan/penyusutan wajar

| Username | Roster | L2 | Delta | Roster refresh | Snapshot L2 |
|---|---:|---:|---:|---|---|
| `fakhrimu` | 98.100 | 97.200 | −900 | 2023-10-03 | 2026-08-18 |
| `suwantoasennn` | 111.000 | 110.300 | −700 | 2023-06-09 | 2026-08-18 |
| `dijaaaah.h` | 415.300 | 414.600 | −700 | 2024-05-11 | 2026-08-18 |

## L2 jauh lebih besar — roster basi, L2 benar

| Username | Roster | L2 | Delta | Roster refresh | Snapshot L2 |
|---|---:|---:|---:|---|---|
| `jennifer.coppen` | 4.100.000 | **17.200.000** | +13.100.000 | 2024-05-09 | 2026-08-14 |
| `ibnuwardani` | 26.200.000 | **35.000.000** | +8.800.000 | 2024-05-09 | 2026-08-24 |
| `sptrakori_` | 13.100.000 | **20.200.000** | +7.100.000 | 2024-05-11 | 2026-08-24 |
| `soimah_pancawati` | 3.400.000 | **9.500.000** | +6.100.000 | 2023-08-07 | 2026-08-14 |

Dua tahun pertumbuhan yang tidak pernah tercatat di roster. **L2 yang benar di sini.**

## L2 jauh lebih kecil — scrape rusak, roster benar

| Username | Roster | L2 | Delta |
|---|---:|---:|---:|
| `zeejkt48` | 4.500.000 | **17** | −4.499.983 |
| `lydiaaas__` | 3.600.000 | **9** | −3.599.991 |
| `machan15` | 3.400.000 | **0** | −3.400.000 |

## Sebaran seluruh selisih

| Besar selisih | Akun |
|---|---:|
| < 1.000 | 20 |
| 1rb – 100rb | 632 |
| 100rb – 1jt | 322 |
| 1jt – 10jt | 49 |
| > 10jt | 1 |

Mayoritas (954 dari 1.024) berada di bawah 1 juta — konsisten dengan pertumbuhan dua tahun, bukan kerusakan.

---

# 5. Source of truth yang direkomendasikan

> ## **L2 (`kol_profile_card.followers_count`) — dengan syarat.**

## Alasan berbasis bukti

| # | Bukti |
|---|---|
| 1 | Roster lebih tua di **100%** kasus mismatch |
| 2 | Saat keduanya segar (912 akun), sepakat **sempurna** |
| 3 | Growth sudah dihitung dari L2 — memakai roster untuk followers membuat dua angka tak bisa direkonsiliasi |
| 4 | L2 punya `profile_snapshot_date`, roster punya `last_refreshed_at` yang bisa tertinggal 3 tahun |
| 5 | Tidak ada masalah mapping — platform cocok 1.972/1.972 |

## Syaratnya

**54 akun bernilai <1.000 harus ditangani lebih dulu**, atau tampilan akan mundur untuk mereka. Tanpa penjaga, `zeejkt48` berubah dari 4,5 juta jadi **17**, dan tier-nya dari Mega jadi Nano.

---

# 6. Perlu development atau cukup pipeline/scraping?

| Masalah | Perlu development? | Yang sebenarnya dibutuhkan |
|---|---|---|
| **Roster basi (~970 akun)** | **TIDAK** | **Jalankan scraping profil TikTok berkala.** Tapi `tiktok_pipeline.py` tidak punya jalur update roster — jadi ada **satu gap kode kecil**: menambahkan `--update-db` seperti yang sudah ada di `pipeline.py`. Alternatifnya: biarkan roster basi dan pindahkan endpoint ke L2 |
| **54 nilai scrape rusak** | **YA, kecil** | Sanity guard. Yang harus diputuskan: di layer mana (L1 procedure, asset L2, atau endpoint) dan apa aturannya |
| **Endpoint pakai roster** | **YA, kecil** | Sudah ada LATERAL ke `kol_profile_card` di `BASE` (dipakai Step 1). Tinggal `COALESCE` seperti avatar/bio — **tapi jangan sebelum guard ada** |

**Ringkasnya: mayoritas masalah selesai dengan menjalankan pipeline, bukan menulis kode.** Yang benar-benar butuh kode hanya sanity guard dan (opsional) `--update-db` di `tiktok_pipeline.py`.

---

# 7. Dampak terhadap Growth

| Aspek | Dampak |
|---|---|
| Perhitungan growth | **Tidak terpengaruh sama sekali.** Growth memakai dua baris `unified_profile` dari akun yang sama; roster tidak ikut sama sekali |
| Rekonsiliasi UI | **Terpengaruh.** UI menampilkan followers roster, growth dari L2 — pembaca tidak bisa memverifikasi |
| Akun ber-nilai rusak | `zeejkt48` hanya punya **1 snapshot**, jadi growth-nya NULL. **Nilai rusak belum mencemari growth mana pun** |
| Ke depan | Kalau `zeejkt48` di-scrape lagi dan mendapat nilai benar (misal 4,5 juta), growth-nya jadi `(4.500.000 − 17) / 17 × 100` = **+26 juta persen**. Ini risiko nyata begitu snapshot kedua masuk |

**Poin terakhir itu yang paling mendesak.** Sanity guard bukan sekadar kosmetik tampilan — tanpa itu, snapshot berikutnya akan menghasilkan angka growth yang absurd dan mencemari classification.

---

# 8. Rekomendasi Step 3

Diurutkan dari yang paling aman:

| # | Langkah | Sifat | Kenapa urutannya begini |
|---|---|---|---|
| **3a** | **Putuskan aturan sanity guard** | keputusan | Perlu ambang: buang `followers = 0`? Buang penurunan >90% antar snapshot? Ambang mana yang tidak membuang penyusutan wajar |
| **3b** | **Terapkan guard** di layer yang disepakati | kode kecil | Melindungi growth sebelum snapshot kedua masuk — **ini yang paling mendesak** |
| **3c** | **Jalankan scraping profil TikTok** (butuh `--update-db` atau keputusan memindahkan endpoint ke L2) | pipeline | Menutup ~970 akun basi |
| **3d** | **Pindahkan `followers` endpoint ke L2** | kode kecil | LATERAL sudah ada; pola sama dengan Step 1. **Hanya setelah 3b** |
| **3e** | Tinjau ulang `tier` untuk 54 akun | verifikasi | Tier ikut salah karena dihitung dari followers |

## Yang TIDAK saya sarankan sekarang

- Memindahkan `followers` ke L2 **sebelum** guard ada — akan merusak 54 akun secara terlihat.
- Menyentuh rumus growth — tidak ada yang salah dengannya.
- Memperbaiki 54 nilai lewat UPDATE — sumbernya di L0, dan akan tertimpa saat materialisasi berikutnya.

---

*Read-only. Tidak ada UPDATE, DELETE, migration, scraping, maupun perubahan Growth calculation. Seluruh angka diukur langsung ke database lewat sesi `set_session(readonly=True)`.*
