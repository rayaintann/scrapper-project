"""Taxonomy Style & Personality sisi KOL — SATU tempat, dua bentuk.

============================================================================
KENAPA FILE INI ADA
============================================================================

Nilai Style dan Personality datang dari DUA sumber yang tidak sama:

    Excel   docs/brand_style_personality.xlsx
            Content Style 10 · Communication Style 8 · Creator Personality 12
            (kolom `Source` menunjuk scripts/brand-match/vocabulary.mjs)

    UI      app/AUTOME_2.html, struktur DNA2 pada 8 creator contoh
            dna 8 · comm 7 · vis 7

Keduanya digabung, dan **tidak satu nilai pun dibuang** — termasuk yang cuma
ada di salah satu sisi. Kolom `sumber` merekam asalnya, jadi pertanyaan "ini
dari mana" tidak perlu ditebak lagi.

Sama seperti `metrics_thresholds.py`, daftar ini hidup SEKALI di sini lalu
diturunkan ke bentuk yang dibutuhkan:

    TAXONOMY          tuple Python   -- dipakai test dan kode aplikasi
    baris_seed_sql()  literal SQL    -- dipakai migration 045 mengisi master

`tests/test_kol_attribute_taxonomy.py` membandingkan keduanya terhadap Excel
dan prototype; kalau seseorang mengubah salah satu saja, test itu gagal.

============================================================================
KENAPA KUNCINYA (group, key) DAN BUKAN key SAJA
============================================================================

Label yang sama sah muncul di beberapa sumbu dengan arti berbeda:

    Educational   Content Style · Communication Style · Creator Personality
    Storytelling  Content Style · Communication Style
    Entertaining  Content Style · Creator Personality
    Humorous      Communication Style · Creator Personality
    Aesthetic     Content Style · Visual Style
    Casual        Creator Personality · Visual Style
    Professional  Creator Personality · Visual Style

`Educational` sebagai Content Style berarti "bentuk kontennya mengajar";
sebagai Creator Personality berarti "kreatornya bertipe pengajar". Dua
pernyataan berbeda tentang objek berbeda. Master yang mengunci pada label saja
akan melebur keduanya, jadi kunci uniknya `(kind, group, key)`.

============================================================================
YANG SENGAJA TIDAK ADA DI SINI
============================================================================

`Brand Personality` (10 nilai) dan `Brand Tone` (8 nilai) dari Excel TIDAK
dimasukkan. Keduanya atribut BRAND, bukan KOL — buktinya di `Brand_Profile`
mereka jadi kolom brand (`brand_personality`, `brand_tone`), dan
`Matching_Engine` memakainya sebagai sisi brand pada matriks 7 dan 8. Tidak
ada satu pun evidence bahwa keduanya dimaksudkan menempel ke kreator.
Rumahnya `public.brand`, dan itu pekerjaan terpisah.
"""

from __future__ import annotations

# ===========================================================================
# SUMBER
# ===========================================================================
EXCEL = "excel"
UI = "ui"
EXCEL_UI = "excel+ui"

# ===========================================================================
# KIND
# ===========================================================================
STYLE = "style"
PERSONALITY = "personality"

# ===========================================================================
# GROUP
# ===========================================================================
CONTENT_STYLE = "content_style"
COMMUNICATION_STYLE = "communication_style"
CREATOR_PERSONALITY = "creator_personality"
VISUAL_STYLE = "visual_style"

# ===========================================================================
# TAXONOMY  ->  (kind, group, key, label, sumber, urutan)
# ===========================================================================
#
# `key` dibuat dari `group` + label yang di-slug-kan, jadi ia unik lintas grup
# tanpa perlu diketik ulang: content_style.educational tidak akan tertukar
# dengan creator_personality.educational.
#
# `urutan` menentukan tampilan di UI, bukan prioritas atau bobot.

_CONTENT_STYLE = (
    # label,           sumber
    ("Educational",    EXCEL),
    ("Tutorial",       EXCEL_UI),
    ("Review",         EXCEL_UI),
    ("Storytelling",   EXCEL_UI),
    ("Aesthetic",      EXCEL),
    ("Entertaining",   EXCEL),
    ("Vlog",           EXCEL_UI),
    ("Talking Head",   EXCEL_UI),
    ("Demo",           EXCEL),
    ("Comedy",         EXCEL),
    ("Commentary",     UI),
)

_COMMUNICATION_STYLE = (
    ("Educational",    EXCEL),
    ("Storytelling",   EXCEL),
    ("Demonstrative",  EXCEL),
    ("Conversational", EXCEL),
    ("Data-driven",    EXCEL),
    ("Visual-first",   EXCEL),
    ("Humorous",       EXCEL),
    ("Testimonial",    EXCEL),
    ("Demonstration",  UI),      # lihat ALIAS_BELUM_DIPUTUSKAN di bawah
)

_CREATOR_PERSONALITY = (
    ("Professional",   EXCEL_UI),
    ("Educational",    EXCEL_UI),
    ("Relatable",      EXCEL_UI),
    ("Casual",         EXCEL_UI),
    ("Entertaining",   EXCEL_UI),
    ("Humorous",       EXCEL_UI),
    ("Inspirational",  EXCEL_UI),
    ("Creative",       EXCEL),
    ("Tech-savvy",     EXCEL),
    ("Reviewer",       EXCEL),
    ("Premium",        EXCEL),
    ("Luxury",         EXCEL),
    ("Expert",         UI),
)

# Sumbu keempat: hanya ada di prototype, tidak ada padanannya di Excel.
# Dipertahankan karena instruksinya eksplisit — nilai yang cuma ada di satu
# sumber tidak boleh dibuang.
_VISUAL_STYLE = (
    ("Aesthetic",      UI),
    ("Casual",         UI),
    ("Professional",   UI),
    ("Cinematic",      UI),
    ("Colorful",       UI),
    ("Lifestyle",      UI),
    ("Minimalist",     UI),
)

_BLOK = (
    (STYLE,       CONTENT_STYLE,       _CONTENT_STYLE),
    (STYLE,       COMMUNICATION_STYLE, _COMMUNICATION_STYLE),
    (PERSONALITY, CREATOR_PERSONALITY, _CREATOR_PERSONALITY),
    (STYLE,       VISUAL_STYLE,        _VISUAL_STYLE),
)


def _slug(label: str) -> str:
    """`Talking Head` -> `talking_head`, `Data-driven` -> `data_driven`."""
    hasil = []
    for ch in label.lower():
        hasil.append(ch if ch.isalnum() else "_")
    # rapatkan garis bawah beruntun, buang di ujung
    slug = "_".join(bagian for bagian in "".join(hasil).split("_") if bagian)
    return slug


def _bangun() -> tuple[dict, ...]:
    baris = []
    for kind, group, isi in _BLOK:
        for urutan, (label, sumber) in enumerate(isi, start=1):
            baris.append({
                "kind": kind,
                "attribute_group": group,
                "attribute_key": f"{group}.{_slug(label)}",
                "label": label,
                "source_origin": sumber,
                "sort_order": urutan,
            })
    return tuple(baris)


#: Seluruh taxonomy sisi KOL. Kunci unik: (kind, attribute_group, attribute_key).
TAXONOMY: tuple[dict, ...] = _bangun()


# ===========================================================================
# ALIAS YANG BELUM DIPUTUSKAN
# ===========================================================================
# Prototype memakai `demonstration` (sumbu comm). Excel punya DUA nilai yang
# mirip tapi tidak identik, di dua grup berbeda:
#
#     Demonstrative   Communication Style
#     Demo            Content Style
#
# Ketiganya DIPERTAHANKAN apa adanya. Menggabungkannya berarti memutuskan
# bahwa "cara menyampaikan secara demonstratif" sama dengan "konten berupa
# demo produk" — itu keputusan bisnis, bukan keputusan teknis, dan belum ada
# yang mengambilnya.
#
# Kalau nanti Product memutuskan salah satunya alias, hapus barisnya dari
# _COMMUNICATION_STYLE dan catat pemetaannya di sini.
ALIAS_BELUM_DIPUTUSKAN = {
    "communication_style.demonstration": (
        "kandidat alias: communication_style.demonstrative (Excel) atau "
        "content_style.demo (Excel). BELUM DIPUTUSKAN — ketiganya "
        "dipertahankan terpisah."
    ),
}


# ===========================================================================
# BENTUK KEDUA: literal SQL untuk migration
# ===========================================================================

def baris_seed_sql() -> str:
    """Literal `VALUES` untuk mengisi `public.kol_attribute`.

    Dipakai migration 045. Digenerate dari TAXONOMY yang sama dengan yang
    dibaca kode aplikasi, jadi keduanya tidak mungkin bergeser diam-diam.
    """
    potongan = []
    for r in TAXONOMY:
        potongan.append(
            "    ('{kind}', '{group}', '{key}', '{label}', '{sumber}', {urut})".format(
                kind=r["kind"],
                group=r["attribute_group"],
                key=r["attribute_key"],
                label=r["label"].replace("'", "''"),
                sumber=r["source_origin"],
                urut=r["sort_order"],
            )
        )
    return ",\n".join(potongan)


# ===========================================================================
# FILTER DISCOVERY
# ===========================================================================

#: Grup milik masing-masing kind, dipakai memvalidasi filter per-kind.
GRUP_PER_KIND = {
    STYLE: (CONTENT_STYLE, COMMUNICATION_STYLE, VISUAL_STYLE),
    PERSONALITY: (CREATOR_PERSONALITY,),
}

_KUNCI_SAH = {r["attribute_key"]: r for r in TAXONOMY}


def parse_attribute_keys(param: str | list[str] | tuple[str, ...] | None,
                         kind: str | None = None) -> list[str]:
    """`"content_style.educational,creator_personality.relatable"` -> daftar key sah.

    Menerima `attribute_key`, BUKAN label. Label tidak dipakai karena ambigu:
    `Educational` hidup di tiga grup dengan arti berbeda, jadi filter berbasis
    label akan menyaring hal yang tidak diminta pengguna. `attribute_key`
    sudah berbentuk `grup.slug`, yang persis dikirim chip UI.

    `kind` menyaring lebih jauh ke `style` atau `personality` saja. Kunci tak
    dikenal diabaikan, bukan menggagalkan request — UI yang lebih baru boleh
    mengirim nilai yang backend ini belum kenal.
    """
    if not param:
        return []
    bagian = param.split(",") if isinstance(param, str) else list(param)
    grup_boleh = GRUP_PER_KIND.get(kind) if kind else None
    hasil: list[str] = []
    for b in bagian:
        kunci = str(b).strip()
        baris = _KUNCI_SAH.get(kunci)
        if baris is None or kunci in hasil:
            continue
        if grup_boleh and baris["attribute_group"] not in grup_boleh:
            continue
        hasil.append(kunci)
    return hasil


def cocok_atribut(atribut_kol: list[str] | tuple[str, ...],
                  diminta: list[str] | tuple[str, ...]) -> bool:
    """Apakah satu KOL lolos satu grup filter.

    ATURAN: **OR di dalam satu grup.** Memilih `Educational` dan `Tutorial`
    berarti "salah satunya", bukan "keduanya" — sama seperti filter Category
    yang memakai overlap (`category_ids && $categories`), bukan kesetaraan.

    Daftar `diminta` kosong berarti "jangan saring".
    """
    if not diminta:
        return True
    return bool(set(atribut_kol) & set(diminta))


#: Sumber mapping di produksi. Dibuat parameter dengan alasan yang sama
#: seperti `db._GROWTH_CTE_TEMPLATE`: test bisa menyuntikkan klausa VALUES
#: sebagai pengganti, sehingga yang diuji adalah SQL yang BENAR-BENAR
#: dijalankan produksi — bukan tiruannya di Python — dan tanpa menulis satu
#: baris pun ke database.
#: Sumber pengganti HARUS menyediakan kolom `kol_directory_id` dan
#: `attribute_key`, beralias `m`.
SUMBER_MAP_DEFAULT = """(SELECT map.kol_directory_id, a.attribute_key
                              FROM public.kol_attribute_map map
                              JOIN public.kol_attribute a
                                ON a.id = map.kol_attribute_id
                             WHERE a.is_active) m"""


def sql_filter_atribut(param: str, alias_kol: str = "k.id",
                       sumber: str = SUMBER_MAP_DEFAULT) -> str:
    """`EXISTS` untuk satu grup filter, OR di dalamnya.

    Dibuat sebagai EXISTS, bukan JOIN, supaya satu KOL tidak terduplikasi saat
    ia punya beberapa atribut yang cocok sekaligus — itu akan membuat jumlah
    hasil bergantung pada berapa label yang menempel, bukan berapa KOL yang
    cocok.
    """
    return f"""EXISTS (
                 SELECT 1
                   FROM {sumber}
                  WHERE m.kol_directory_id = {alias_kol}
                    AND m.attribute_key = ANY({param}))"""


def ringkasan() -> dict[str, int]:
    """Jumlah baris per grup — dipakai test dan blok verifikasi migration."""
    hasil: dict[str, int] = {}
    for r in TAXONOMY:
        hasil[r["attribute_group"]] = hasil.get(r["attribute_group"], 0) + 1
    hasil["TOTAL"] = len(TAXONOMY)
    return hasil
