"""Jalur A (Instagram Insights) end-to-end tanpa network dan tanpa DB:

    collector (parse Graph API) -> agregasi geo L1->L2 -> audience_classification (measured menang)

Sumber sungguhan masih 0 akun ter-connect, jadi yang diuji adalah bagian yang
menentukan angka begitu sumbernya menyala.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orchestration"))

import audience_classification as A  # noqa: E402
import instagram_insights_collector as IC  # noqa: E402
from kol_orchestration import one_shot  # noqa: E402
from kol_orchestration.assets.audience import (  # noqa: E402
    agregasi_geo_terukur, audience_assets, normalisasi_geo_platform)

SA = "11111111-1111-1111-1111-111111111111"
NOW = datetime(2026, 9, 25, tzinfo=timezone.utc)


def _demo(breakdown, pairs):
    return {"data": [{"name": "follower_demographics", "period": "lifetime", "total_value": {"breakdowns": [
        {"dimension_keys": [breakdown], "results": [{"dimension_values": [k], "value": v} for k, v in pairs]}]}}]}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(routes: dict):
    """URL -> payload dict, atau Exception untuk disimulasikan sebagai HTTPError."""
    def op(url, timeout=None):
        for frag, payload in routes.items():
            if frag in url:
                if isinstance(payload, Exception):
                    raise payload
                return _Resp(json.dumps(payload).encode())
        raise AssertionError(f"request tak terduga: {url}")
    return op


def _target():
    return IC.Target(SA, "kol", "1789", "TOKEN123")


# --- collector ---------------------------------------------------------------
def test_parse_breakdown_mengambil_hanya_dimensi_yang_diminta():
    p = _demo("city", [("Jakarta, Jakarta", 120), ("Bandung, West Java", 30)])
    p["data"][0]["total_value"]["breakdowns"].append(
        {"dimension_keys": ["age"], "results": [{"dimension_values": ["18-24"], "value": 9}]})
    assert IC.parse_breakdown(p, "city") == {"Jakarta, Jakarta": 120.0, "Bandung, West Java": 30.0}


def test_parse_breakdown_kosong_adalah_none_bukan_nol():
    assert IC.parse_breakdown({"data": []}, "age") is None
    assert IC.parse_breakdown(_demo("age", []), "age") is None


def test_redact_menyembunyikan_token():
    url = IC.insights_url("1789", "RAHASIA", "age")
    assert "RAHASIA" in url and "RAHASIA" not in IC.redact(url)
    assert "breakdown=age" in url and "metric=follower_demographics" in url


def test_collect_one_menulis_empat_breakdown():
    routes = {"fields=": {"username": "kol", "followers_count": 5000},
              "breakdown=age": _demo("age", [("18-24", 60), ("25-34", 30)]),
              "breakdown=city": _demo("city", [("Jakarta, Jakarta", 40)]),
              "breakdown=country": _demo("country", [("ID", 90), ("MY", 5)]),
              "breakdown=gender": _demo("gender", [("F", 70), ("M", 25), ("U", 5)])}
    r = IC.collect_one(_target(), opener=_opener(routes), now=NOW)
    assert r.errors == {}
    assert r.row["demographics_age"] == {"18-24": 60.0, "25-34": 30.0}
    assert r.row["demographics_country"] == {"ID": 90.0, "MY": 5.0}
    assert r.row["followers_count"] == 5000 and r.row["social_account_id"] == SA


def test_collect_one_breakdown_gagal_dicatat_bukan_diisi():
    err = urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b'{"error":{"message":"(#10) permission"}}'))
    routes = {"fields=": {"followers_count": 5000}, "breakdown=age": err,
              "breakdown=city": _demo("city", [("Jakarta, Jakarta", 40)]),
              "breakdown=country": _demo("country", [("ID", 90)]), "breakdown=gender": _demo("gender", [("F", 1)])}
    r = IC.collect_one(_target(), opener=_opener(routes), now=NOW)
    assert r.row["demographics_age"] is None
    assert "permission" in r.errors["age"]
    assert r.row["demographics_city"] == {"Jakarta, Jakarta": 40.0}


def test_collect_one_di_bawah_100_follower_tidak_menulis_baris():
    r = IC.collect_one(_target(), opener=_opener({"fields=": {"followers_count": 80}}), now=NOW)
    assert r.row is None and set(r.errors) == set(IC.BREAKDOWNS)


def test_collect_one_token_rusak_tidak_menulis_baris():
    err = urllib.error.HTTPError("u", 190, "bad", {}, io.BytesIO(b'{"error":{"message":"Invalid OAuth"}}'))
    r = IC.collect_one(_target(), opener=_opener({"fields=": err}), now=NOW)
    assert r.row is None and "Invalid OAuth" in r.errors["profile"]


def test_target_kedaluwarsa():
    t = IC.Target(SA, "kol", "1", "t", datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert t.expired(NOW) and not _target().expired(NOW)


# --- L1 -> L2 geo terukur ------------------------------------------------------
def test_normalisasi_geo():
    assert normalisasi_geo_platform("country", "id") == "ID"
    assert normalisasi_geo_platform("country", "IDN") is None
    assert normalisasi_geo_platform("city", "Jakarta, Jakarta") == "Jakarta"
    assert normalisasi_geo_platform("city", " ") is None


def test_agregasi_geo_menjumlah_kota_yang_bertemu_di_kunci_sama():
    d = date(2026, 9, 25)
    mentah = [(SA, "instagram", d, "city", "Jakarta, Jakarta", 10),
              (SA, "instagram", d, "city", "Jakarta, DKI Jakarta", 5),
              (SA, "instagram", d, "country", "id", 20),
              (SA, "instagram", d, "country", "XYZ", 3),
              (SA, "instagram", d, "age", "18-24", 7)]
    got, bad = agregasi_geo_terukur(mentah)
    assert got == {(SA, "instagram", d, "city", "Jakarta"): 15.0, (SA, "instagram", d, "country", "ID"): 20.0}
    assert bad == {"country:XYZ": 1}


def test_asset_geo_terukur_terdaftar_dan_ikut_rantai():
    assert "audience_geo_measured" in {a.key.path[-1] for a in audience_assets}
    src = Path(one_shot.__file__).read_text(encoding="utf-8")
    assert src.index('"audience_age_measured"') < src.index('"audience_geo_measured"') < src.index('"creator_age"')


# --- classifier: measured menang atas inferred ----------------------------------
def test_umur_terukur_menang_atas_inferred():
    inp = A.AudienceInput(has_data=True, age_counts={"25-34": 50}, age_measured={"18-24": 600, "25-34": 300})
    r = A.classify_age(inp)
    assert (r.value, r.source, r.confidence) == ("18-24", A.SRC_AGE_MEASURED, "high")


def test_umur_terukur_di_bawah_ambang_jatuh_ke_inferred():
    inp = A.AudienceInput(has_data=True, age_counts={"25-34": 9}, age_measured={"18-24": 3})
    assert A.classify_age(inp).value == "25-34"


def test_akun_hanya_terukur_tetap_terklasifikasi():
    inp = A.AudienceInput(has_data=False, age_measured={"25-34": 70, "18-24": 20},
                          city={"Jakarta": (40.0, "measured")}, country={"ID": (90.0, "measured")})
    r = A.classify(inp)
    assert r["age"].value == "25-34" and r["city"].value == "Jakarta" and r["country"].value == "ID"
    assert r["city"].confidence == "high"
    assert A.validate(r) == []


def test_ambang_tidak_berubah():
    assert A.MIN_KNOWN == 5 and A.GENDER_SHARE_MIN == 60.0
