"""Sampel post untuk topik konten: kolaborasi dibuang, like tersembunyi TIDAK.

Regresi 22 September: akun yang menyembunyikan like di semua post tidak punya
topik konten (dan Audience Interest fallback `content_inferred`-nya kosong),
padahal caption-nya tersedia dan terklasifikasi.
"""

from kol_orchestration.assets import feature_engagement as fe


def test_topik_tidak_membuang_post_like_tersembunyi():
    assert "likes_hidden" not in fe.SQL_POST_UNTUK_TOPIK


def test_topik_tetap_membuang_post_kolaborasi():
    assert "is_collaboration IS NOT TRUE" in fe.SQL_POST_UNTUK_TOPIK


def test_sampel_engagement_tidak_ikut_berubah():
    # `lolos` untuk metrik engagement tetap membuang like tersembunyi.
    import inspect
    src = inspect.getsource(fe)
    assert "(u.likes_hidden IS NOT TRUE AND u.is_collaboration IS NOT TRUE) AS lolos" in src
