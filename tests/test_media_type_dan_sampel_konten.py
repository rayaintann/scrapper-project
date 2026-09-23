"""Dua regresi 23 September, keduanya membuang fakta yang sudah ada di gudang.

1. `media_type` hanya dibaca dari `productType`. Actor
   `apify/instagram-profile-scraper` mengirim field itu HANYA untuk Reels;
   untuk foto dan carousel ia tidak ada sama sekali, sementara `type` selalu
   dikirim. Akibatnya 342 baris L0 / 288 dari 902 post L1 Instagram cohort
   ber-media_type NULL, dan `format_dominant` ikut NULL karena `mode()`
   mengabaikan NULL.

2. `likes_hidden` dipakai sebagai sampel untuk metrik yang sama sekali tidak
   bergantung pada like. Like yang disembunyikan membuat ENGAGEMENT tidak
   diketahui; ia tidak mengubah tipe media, tidak menghapus play count yang
   tetap dilaporkan platform, tidak menghapus penanda endorse, dan tidak
   menghapus tanggal posting.
"""

import re

import post_raw_store as P
from kol_orchestration.assets import feature_engagement as F


# --- 1. media_type: productType, jatuh ke type -----------------------------

def test_product_type_dipakai_kalau_ada():
    assert P._media_type({"productType": "clips", "type": "Video"}) == "clips"


def test_jatuh_ke_type_kalau_product_type_tidak_ada():
    # Persis bentuk payload foto & carousel dari instagram-profile-scraper.
    assert P._media_type({"type": "Sidecar"}) == "carousel_container"
    assert P._media_type({"type": "Image"}) == "feed"
    assert P._media_type({"type": "Video"}) == "clips"


def test_type_tidak_dikenal_tetap_none():
    """Tidak menebak. Nilai asing -> NULL, bukan kategori karangan."""
    assert P._media_type({"type": "Gugelwarp"}) is None
    assert P._media_type({}) is None
    assert P._media_type({"type": ""}) is None


def test_pemetaan_konsisten_dengan_normalisasi_format_di_feature():
    """Setiap nilai yang ditulis _media_type harus dikenali _FORMAT_NORM.

    Kalau tidak, kolomnya terisi tapi `format_dominant` tetap NULL -- bug yang
    sama, hanya berpindah satu lapis.
    """
    dikenal = set(re.findall(r"WHEN '([a-z_]+)'", F._FORMAT_NORM))
    for nilai in P._TYPE_KE_PRODUCT.values():
        assert nilai in dikenal, f"{nilai} tidak dikenali _FORMAT_NORM"


# --- 2. sampel konten vs sampel engagement ---------------------------------

def test_ada_dua_sampel_yang_berbeda():
    cte = F._cte_dasar("instagram")
    assert "AS lolos" in cte and "AS lolos_konten" in cte
    assert "u.likes_hidden IS NOT TRUE AND u.is_collaboration IS NOT TRUE) AS lolos" in cte
    # lolos_konten TIDAK menyebut likes_hidden sama sekali.
    konten = cte[cte.index("(u.is_collaboration IS NOT TRUE) AS lolos_konten")
                 - 2: cte.index("AS lolos_konten") + len("AS lolos_konten")]
    assert "likes_hidden" not in konten


def test_fakta_non_engagement_memakai_lolos_konten():
    """Format, play count, penanda endorse, tanggal posting."""
    for nama, ekspr in [("_S_VIEWS", F._S_VIEWS), ("_S_V2F", F._S_V2F),
                        ("_S_PAID", F._S_PAID), ("_S_FREQ", F._S_FREQ),
                        ("_FORMAT_DOMINAN", F._FORMAT_DOMINAN)]:
        assert "lolos_konten" in ekspr, f"{nama} masih memakai sampel engagement"


def test_engagement_rate_tetap_memakai_lolos():
    """ER TIDAK boleh ikut berubah: tanpa like, engagement memang tak diketahui."""
    sql = F._sql_stats("instagram") if hasattr(F, "_sql_stats") else ""
    cte = F._cte_dasar("instagram")
    assert "AS lolos," in cte
    # Sampel ER di _ENG/_ER memakai `lolos`, bukan `lolos_konten`.
    assert "FILTER (WHERE lolos AND followers_count IS NOT NULL)" in F.SQL_IG or \
           "FILTER (WHERE lolos AND followers_count IS NOT NULL)" in sql


def test_topik_konten_tidak_membuang_post_berlike_tersembunyi():
    assert "likes_hidden" not in F.SQL_POST_UNTUK_TOPIK
    assert "is_collaboration IS NOT TRUE" in F.SQL_POST_UNTUK_TOPIK


# --- 3. ejaan topik dari fallback roster ------------------------------------

def test_fallback_kategori_ditulis_huruf_kecil():
    """'Beauty' dari roster di samping 'beauty' dari konten memecah satu nilai
    jadi dua pilihan di filter mana pun."""
    assert "lower(min(c.taxonomy_key))" in F.SQL_KATEGORI_FALLBACK
