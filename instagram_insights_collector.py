"""Collector Instagram Insights: demografi follower TERUKUR -> l0_raw.ig_profile_official.

    python instagram_insights_collector.py                     dry-run: target + request, TANPA network
    python instagram_insights_collector.py --cohort            dry-run, dibatasi cohort one-pass (100 akun)
    python instagram_insights_collector.py --apply --cohort    panggil Graph API, tulis L0, sync L0H -> L1

Ini jalur A di header `orchestration/kol_orchestration/assets/audience.py`:

    Graph API  /{ig-user-id}/insights?metric=follower_demographics
        -> l0_raw.ig_profile_official.demographics_{age,city,country,gender}   (modul ini)
        -> l0_harmonization.sp_sync_instagram_audience()                      (ada di DB)
        -> l1_silver.sp_build_unified_audience()                               (ada di DB)
        -> asset audience_age_measured / audience_geo_measured                 (L1 -> L2)
        -> audience_classification (measured menang atas inferred)

Yang TIDAK dilakukan modul ini:
  * Tidak ada OAuth flow. Token dibaca dari `public.social_account.oauth_token`
    (+ `platform_user_id`) -- definisi "Connected" yang sama dengan filter
    Discovery. Tanpa token, akun itu tidak disentuh.
  * Tidak ada data pengganti. Breakdown yang gagal/kosong ditulis NULL, bukan 0.
  * Tidak ada DELETE/UPDATE. L0 append-only; sync procedure memakai ON CONFLICT.

Format kolom demographics_* = objek datar {dimension_value: jumlah_follower},
persis yang dipecah `sp_sync_instagram_audience()` lewat jsonb_each_text.
Nilai dimensi disimpan APA ADANYA dari platform (umur "18-24", kota
"Jakarta, Jakarta", negara "ID", gender "F"/"M"/"U"); normalisasi terjadi di
L1 -> L2, bukan di raw.

Syarat per akun (Meta): akun Business/Creator, >= 100 follower, token dengan
izin `instagram_basic` + `instagram_manage_insights` (+ `pages_read_engagement`)
lewat Facebook Login, atau `instagram_business_basic` +
`instagram_business_manage_insights` lewat Instagram Login (--host instagram).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COHORT_PATH = ROOT / "orchestration" / "kol_orchestration" / "data" / "one_pass_cohort.csv"

API_VERSION = "v21.0"
HOSTS = {"facebook": "https://graph.facebook.com", "instagram": "https://graph.instagram.com"}
BREAKDOWNS = ("age", "city", "country", "gender")
PROFILE_FIELDS = "username,name,biography,website,followers_count,follows_count,media_count"
#: Batas platform: Insights demografi hanya untuk akun dengan >= 100 follower.
MIN_FOLLOWERS = 100
TABLE = "l0_raw.ig_profile_official"

SQL_TARGETS = """
    SELECT s.id::text, s.username, s.platform_user_id, s.oauth_token, s.token_expires_at
      FROM public.social_account s
      JOIN public.platforms p ON p.id = s.platform_id
     WHERE p.key = 'instagram'
       AND nullif(btrim(coalesce(s.oauth_token, '')), '') IS NOT NULL
       AND nullif(btrim(coalesce(s.platform_user_id, '')), '') IS NOT NULL
       AND (%(ids)s::uuid[] IS NULL OR s.id = ANY(%(ids)s::uuid[]))"""

SQL_COHORT_STATUS = """
    SELECT count(*),
           count(*) FILTER (WHERE nullif(btrim(coalesce(s.oauth_token, '')), '') IS NOT NULL),
           count(*) FILTER (WHERE nullif(btrim(coalesce(s.platform_user_id, '')), '') IS NOT NULL)
      FROM public.social_account s JOIN public.platforms p ON p.id = s.platform_id
     WHERE p.key = 'instagram' AND (%(ids)s::uuid[] IS NULL OR s.id = ANY(%(ids)s::uuid[]))"""

SQL_INSERT = f"""
    INSERT INTO {TABLE} (social_account_id, fetched_at, username, name, biography, website,
                         followers_count, follows_count, media_count,
                         demographics_age, demographics_city, demographics_country, demographics_gender)
    VALUES (%(social_account_id)s, %(fetched_at)s, %(username)s, %(name)s, %(biography)s, %(website)s,
            %(followers_count)s, %(follows_count)s, %(media_count)s,
            %(demographics_age)s, %(demographics_city)s, %(demographics_country)s, %(demographics_gender)s)
    RETURNING id"""


@dataclass
class Target:
    social_account_id: str
    username: str | None
    ig_user_id: str
    token: str
    token_expires_at: datetime | None = None

    def expired(self, now: datetime) -> bool:
        return self.token_expires_at is not None and self.token_expires_at <= now


@dataclass
class Result:
    target: Target
    row: dict | None = None
    errors: dict[str, str] = field(default_factory=dict)


# --- request / parse (tanpa DB, bisa diuji offline) --------------------------
def insights_url(ig_user_id: str, token: str, breakdown: str, host: str = "facebook",
                 version: str = API_VERSION) -> str:
    q = {"metric": "follower_demographics", "period": "lifetime", "metric_type": "total_value",
         "breakdown": breakdown, "access_token": token}
    return f"{HOSTS[host]}/{version}/{ig_user_id}/insights?{urllib.parse.urlencode(q)}"


def profile_url(ig_user_id: str, token: str, host: str = "facebook", version: str = API_VERSION) -> str:
    q = {"fields": PROFILE_FIELDS, "access_token": token}
    return f"{HOSTS[host]}/{version}/{ig_user_id}?{urllib.parse.urlencode(q)}"


def redact(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    q = [(k, "***" if k == "access_token" else v) for k, v in urllib.parse.parse_qsl(parts.query)]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(q, safe="*")))


def parse_breakdown(payload: dict, breakdown: str) -> dict[str, float] | None:
    """Respons `follower_demographics` -> {dimension_value: jumlah}. None bila tidak ada data.

    Bentuk respons Graph API (total_value):
        {"data": [{"name": "follower_demographics", "total_value": {"breakdowns": [
            {"dimension_keys": ["city"], "results": [{"dimension_values": ["Jakarta, Jakarta"], "value": 12}]}]}}]}
    Breakdown yang dimension_keys-nya bukan `breakdown` diabaikan (tidak ditebak)."""
    out: dict[str, float] = {}
    for item in payload.get("data") or []:
        if item.get("name") != "follower_demographics":
            continue
        for bd in (item.get("total_value") or {}).get("breakdowns") or []:
            if list(bd.get("dimension_keys") or []) != [breakdown]:
                continue
            for r in bd.get("results") or []:
                vals = r.get("dimension_values") or []
                v = r.get("value")
                if len(vals) != 1 or v is None or str(vals[0]).strip() == "":
                    continue
                key = str(vals[0]).strip()
                out[key] = out.get(key, 0) + float(v)
    return out or None


def _get_json(url: str, opener=urllib.request.urlopen, timeout: int = 30) -> dict:
    try:
        with opener(url, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:           # pesan error Graph ada di body
        try:
            body = json.load(e)
        except Exception:
            body = {}
        msg = (body.get("error") or {}).get("message") or str(e)
        raise RuntimeError(f"HTTP {e.code}: {msg}") from None


def collect_one(t: Target, host: str = "facebook", opener=urllib.request.urlopen,
                now: datetime | None = None) -> Result:
    """Satu akun: profil + 4 breakdown. Kegagalan per breakdown dicatat, tidak diganti nilai."""
    now = now or datetime.now(timezone.utc)
    res = Result(t)
    try:
        prof = _get_json(profile_url(t.ig_user_id, t.token, host), opener)
    except Exception as e:                        # token/izin rusak -> tidak ada baris sama sekali
        res.errors["profile"] = str(e)
        return res
    demo: dict[str, dict | None] = {}
    fc = prof.get("followers_count")
    for b in BREAKDOWNS:
        if fc is not None and fc < MIN_FOLLOWERS:
            demo[b] = None
            res.errors[b] = f"followers_count {fc} < {MIN_FOLLOWERS}: platform tidak menyediakan demografi"
            continue
        try:
            demo[b] = parse_breakdown(_get_json(insights_url(t.ig_user_id, t.token, b, host), opener), b)
        except Exception as e:
            demo[b] = None
            res.errors[b] = str(e)
    if all(v is None for v in demo.values()):
        return res
    res.row = {
        "social_account_id": t.social_account_id, "fetched_at": now,
        "username": prof.get("username") or t.username, "name": prof.get("name"),
        "biography": prof.get("biography"), "website": prof.get("website"),
        "followers_count": fc, "follows_count": prof.get("follows_count"), "media_count": prof.get("media_count"),
        **{f"demographics_{b}": demo[b] for b in BREAKDOWNS},
    }
    return res


# --- DB ------------------------------------------------------------------------
def load_cohort_ids(path: Path = COHORT_PATH) -> list[str]:
    with open(path, encoding="utf-8", newline="") as fh:
        return [r["sa"] for r in csv.DictReader(fh) if r["plat"] == "instagram"]


def load_targets(conn, ids: list[str] | None) -> list[Target]:
    with conn.cursor() as cur:
        cur.execute(SQL_TARGETS, {"ids": ids})
        return [Target(*r) for r in cur.fetchall()]


def cohort_status(conn, ids: list[str] | None) -> tuple[int, int, int]:
    with conn.cursor() as cur:
        cur.execute(SQL_COHORT_STATUS, {"ids": ids})
        return cur.fetchone()


def write(conn, rows: list[dict]) -> int:
    import psycopg2.extras
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(SQL_INSERT, {k: (psycopg2.extras.Json(v) if k.startswith("demographics_") and v is not None
                                         else v) for k, v in r.items()})
        cur.execute("CALL l0_harmonization.sp_sync_instagram_audience()")
        cur.execute("SELECT l1_silver.sp_build_unified_audience()")
    return len(rows)


def _connect(readonly: bool):
    import os
    import psycopg2
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    conn = psycopg2.connect(host=os.environ["PG_HOST"], port=os.environ["PG_PORT"], dbname=os.environ["PG_DB"],
                            user=os.environ["PG_USER"], password=os.environ["PG_PASSWORD"], connect_timeout=15)
    conn.set_session(readonly=readonly)
    return conn


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Instagram Insights follower_demographics -> l0_raw.ig_profile_official")
    p.add_argument("--cohort", action="store_true", help="Batasi ke akun Instagram cohort one-pass.")
    p.add_argument("--host", choices=sorted(HOSTS), default="facebook",
                   help="facebook = Facebook Login (graph.facebook.com), instagram = Instagram Login.")
    p.add_argument("--apply", action="store_true",
                   help="Panggil Graph API dan TULIS ke DB. Tanpa ini: dry-run tanpa network.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(argv)
    ids = load_cohort_ids() if a.cohort else None
    conn = _connect(readonly=not a.apply)
    try:
        n_ig, n_tok, n_uid = cohort_status(conn, ids)
        targets = load_targets(conn, ids)
        now = datetime.now(timezone.utc)
        live = [t for t in targets if not t.expired(now)]
        print(f"Akun Instagram{' cohort' if a.cohort else ''}: {n_ig} | oauth_token: {n_tok} | "
              f"platform_user_id: {n_uid} | target (token + id): {len(targets)} | token belum kedaluwarsa: {len(live)}")
        for t in live[:5]:
            for b in BREAKDOWNS:
                print("  ", t.username, redact(insights_url(t.ig_user_id, t.token, b, a.host)))
        if not a.apply:
            print(f"DRY-RUN: tidak ada request ke Graph API, tidak ada write. "
                  f"Request yang akan dikirim: {len(live) * (1 + len(BREAKDOWNS))}.")
            if not live:
                print("Tidak ada akun ter-connect. Butuh: akun Business/Creator + login app dengan izin "
                      "instagram_basic + instagram_manage_insights (token tersimpan di social_account.oauth_token).")
            return 0
        rows, fails = [], {}
        for t in live:
            r = collect_one(t, a.host, now=now)
            if r.row:
                rows.append(r.row)
            if r.errors:
                fails[t.username or t.social_account_id] = r.errors
        n = write(conn, rows)
        conn.commit()
        print(f"Ditulis ke {TABLE}: {n} baris; sync L0H + L1 dijalankan. Gagal/parsial: {len(fails)}")
        for u, e in list(fails.items())[:20]:
            print("  ", u, e)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
