"""ONE-PASS ENRICHMENT -- satu perintah, nol biaya, dari evidence yang SUDAH ADA.

    python -m orchestration.one_pass_enrichment --report-only   coverage + Unknown, tanpa write
    python -m orchestration.one_pass_enrichment --dry-run       rehearsal: hitung write, lalu ROLLBACK
    python -m orchestration.one_pass_enrichment                 pipeline penuh yang aman

Modul ini ORKESTRATOR. Tidak ada classifier, metric, atau transformasi yang
ditulis ulang di sini -- semuanya dipanggil dari implementasi existing:

    evidence creator    creator_classification_dryrun.load        (D.load)
    creator classify    creator_classification.classify           (lewat D.run)
    creator write       creator_classification_writer.plan/apply  (guard + konvergensi)
    audience classify   audience_classification.load/classify     (MIN_KNOWN, GENDER_SHARE_MIN)
    L0 -> L2 Gold       one_shot.jalankan_transform_chain         (asset Dagster existing)
    creator gender/age  asset `creator_gender` / `creator_age`    (bagian rantai di atas)
    audience L2         asset `audience_feature` / `audience_gold`
    metrics             asset feature_* / gold_* (ER, views, viral, paid, frekuensi, ...)
    brand match         brand_match.recalculate_brand_match       (Autometric, hanya bila input berubah)

URUTAN
======
    [1/8] Cohort                 100 akun beku (data/one_pass_cohort.csv), 70 IG / 30 TT
    [2/8] Evidence               dibaca SEKALI per social_account_id, dipakai semua langkah
    [3/8] Creator enrichment     plan category/subcategory/style/personality (+ verifikasi gender/age)
    [4/8] Audience enrichment    classifier audiens existing atas evidence yang sama
    [5/8] Metrics                evidence per metric -> alasan Unknown
    [6/8] Materialization        rehearsal rantai L0->L2 (hitung write, deteksi delete)
                                 -> [normal] rantai sungguhan -> creator write -> brand match
    [7/8] Integrity              cohort, duplicate, orphan, ownership, taxonomy, curated, ER, delete
    [8/8] Report                 before.json / after.json / report.json / report.md

Seluruh penjaga ada di `one_pass_guard.py` dan dipasang SEBELUM langkah [1/8].
"""

from __future__ import annotations

import argparse
import csv
import functools
import hashlib
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import psycopg2  # noqa: E402

from kol_orchestration import one_pass_guard as G  # noqa: E402

COHORT_PATH = Path(__file__).with_name("data") / "one_pass_cohort.csv"
OUTPUT_ROOT = _PROJECT_ROOT / "output" / "one_pass"
BRAND_MATCH_STATE = OUTPUT_ROOT / "brand_match_input_state.json"
EVIDENCE_MODE = "l1+l0raw"     # default writer existing: L1 + roster + card + l0_raw profil (tanpa scraping)

# --- kode alasan Unknown ----------------------------------------------------
NO_SOURCE = "NO_SOURCE"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
BELOW_THRESHOLD = "BELOW_THRESHOLD"
CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
STRUCTURALLY_UNAVAILABLE = "STRUCTURALLY_UNAVAILABLE"
BLOCKED_BY_ZERO_COST = "BLOCKED_BY_ZERO_COST"
UNKNOWN_REASONS = (NO_SOURCE, INSUFFICIENT_EVIDENCE, BELOW_THRESHOLD, CONFLICTING_EVIDENCE,
                   STRUCTURALLY_UNAVAILABLE, BLOCKED_BY_ZERO_COST)
#: Bukan alasan Unknown: nilai sudah diketahui classifier tapi belum tertulis
#: (hanya muncul di --dry-run / --report-only).
PENDING_WRITE = "PENDING_WRITE"
#: Teks alasan classifier yang belum terpetakan. Dilaporkan apa adanya supaya
#: tidak ada alasan yang dikarang.
UNCLASSIFIED = "UNCLASSIFIED"

CREATOR_FIELDS = ("gender", "age", "category", "subcategory", "style", "personality")
AUDIENCE_FIELDS = ("gender", "age", "country", "city", "interest")
METRIC_FIELDS = ("ER", "avg_views", "median_views", "viral_frequency", "paid_ratio",
                 "post_frequency", "format_dominant", "content_topic", "audience_quality",
                 "authenticity", "interest", "gender", "brand_match")
#: metric -> kolom l2_gold.kol_profile_card (ER dan brand_match dibaca terpisah)
CARD_METRIC_COLS = {
    "avg_views": "avg_views", "median_views": "median_views",
    "viral_frequency": "viral_frequency", "paid_ratio": "paid_ratio",
    "post_frequency": "post_frequency_monthly", "format_dominant": "format_dominant",
    "content_topic": "content_topic", "audience_quality": "audience_quality_score",
    "authenticity": "authenticity_score", "interest": "audience_interest_top",
    "gender": "female_pct",
}


def _log(msg: str = "") -> None:
    print(msg, flush=True)


def _step(i: int, name: str) -> None:
    _log(f"\n[{i}/8] {name}")


def _jsonable(v):
    if isinstance(v, Decimal):
        return format(v.normalize(), "f") if v == v.to_integral() else str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


# ---------------------------------------------------------------------------
# [1/8] Cohort
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Member:
    platform: str
    username: str
    social_account_id: str
    kol_id: str


def load_cohort(path: Path = COHORT_PATH) -> list[Member]:
    with open(path, encoding="utf-8", newline="") as fh:
        return [Member(r["plat"], r["sa_username"], r["sa"], r["kol_id"]) for r in csv.DictReader(fh)]


def validate_cohort(members: list[Member], expect: dict) -> list[str]:
    """Pemeriksaan offline atas file cohort beku."""
    bad = []
    sa = [m.social_account_id for m in members]
    per = Counter(m.platform for m in members)
    if len(members) != expect["total"]:
        bad.append(f"cohort {len(members)} baris, harus {expect['total']}")
    if len(set(sa)) != len(sa):
        bad.append(f"social_account_id ganda di cohort: {len(sa) - len(set(sa))}")
    for plat in ("instagram", "tiktok"):
        if per[plat] != expect[plat]:
            bad.append(f"cohort {plat}={per[plat]}, harus {expect[plat]}")
    if len({m.kol_id for m in members}) != len(members):
        bad.append("kol_id ganda di cohort")
    return bad


SQL_COHORT_DB = """
    SELECT x.sa::text, p.key, k.kol_id::text, (SELECT count(*) FROM public.kol_social_account k2
                                                WHERE k2.social_account_id = x.sa)
      FROM unnest(%s::uuid[]) x(sa)
      LEFT JOIN public.social_account s ON s.id = x.sa
      LEFT JOIN public.platforms p ON p.id = s.platform_id
      LEFT JOIN public.kol_social_account k ON k.social_account_id = x.sa"""


def validate_cohort_db(cur, members: list[Member]) -> list[str]:
    """Cohort terhadap DB: akun ada, platform cocok, mapping ke kol_id tepat satu."""
    by_sa = {m.social_account_id: m for m in members}
    cur.execute(SQL_COHORT_DB, (list(by_sa),))
    bad = []
    for sa, plat, kol, n_map in cur.fetchall():
        m = by_sa[sa]
        if plat is None:
            bad.append(f"{sa}: social_account tidak ada")
        elif plat != m.platform:
            bad.append(f"{sa}: platform DB={plat}, cohort={m.platform}")
        if n_map != 1:
            bad.append(f"{sa}: mapping kol_social_account = {n_map}, harus 1")
        elif kol != m.kol_id:
            bad.append(f"{sa}: kol_id DB={kol}, cohort={m.kol_id}")
    return bad


# ---------------------------------------------------------------------------
# [2/8] Evidence
# ---------------------------------------------------------------------------
SQL_METRIC_EVIDENCE = """
    SELECT x.sa::text,
           coalesce(p.n_post, 0), coalesce(p.n_views, 0), coalesce(p.n_spons_known, 0),
           coalesce(p.n_caption, 0), p.last_post, s.first_snap,
           coalesce(f.n_follower, 0), coalesce(f.n_bio, 0),
           EXISTS (SELECT 1 FROM l2_gold.kol_profile_card c WHERE c.social_account_id = x.sa)
      FROM unnest(%s::uuid[]) x(sa)
      LEFT JOIN LATERAL (
            SELECT count(*) n_post,
                   count(*) FILTER (WHERE u.views IS NOT NULL) n_views,
                   count(*) FILTER (WHERE u.is_sponsored IS NOT NULL) n_spons_known,
                   count(*) FILTER (WHERE nullif(btrim(coalesce(u.caption, '')), '') IS NOT NULL) n_caption,
                   max((u.posted_at AT TIME ZONE 'UTC')::date) last_post
              FROM l1_silver.unified_post u WHERE u.social_account_id = x.sa) p ON true
      LEFT JOIN LATERAL (
            SELECT min(pr.date) first_snap FROM l1_silver.unified_profile pr
             WHERE pr.social_account_id = x.sa AND pr.followers_count > 0) s ON true
      LEFT JOIN LATERAL (
            SELECT count(*) n_follower,
                   count(*) FILTER (WHERE nullif(btrim(coalesce(uf.bio, '')), '') IS NOT NULL) n_bio
              FROM l1_silver.unified_follower uf WHERE uf.social_account_id = x.sa) f ON true"""

METRIC_EV_KEYS = ("n_post", "n_views", "n_spons_known", "n_caption", "last_post", "first_snap",
                  "n_follower", "n_bio", "has_card")


def load_metric_evidence(conn, sa_ids: list[str]) -> dict[str, dict]:
    with conn.cursor() as cur:
        cur.execute(SQL_METRIC_EVIDENCE, (sa_ids,))
        return {r[0]: dict(zip(METRIC_EV_KEYS, r[1:])) for r in cur.fetchall()}


def _default_loaders():
    import audience_classification as A
    import creator_classification_dryrun as D
    return {"creator": D.load, "audience": A.load, "metric": load_metric_evidence}


@dataclass
class EvidenceSet:
    """Satu evidence set untuk seluruh cohort, dibaca SEKALI lalu dipakai ulang.

    creator   -> tuple `D.load`: taxonomy, KOL, profil (bio/username/display name),
                 post L1 (caption/hashtag/media type), roster, kartu (gender/age),
                 l0_raw profil (businessCategoryName, latestPosts)
    audience  -> `A.load`: feature audience (gender/age/interest) + geo L2
    metric    -> per akun: jumlah post, views, sinyal sponsor, caption, snapshot
                 profil, follower + bio
    `loads` mencatat berapa kali tiap sumber benar-benar di-query."""

    creator: tuple
    audience: dict
    metric: dict
    loads: Counter = field(default_factory=Counter)
    _classified: dict | None = None

    @classmethod
    def build(cls, conn, members: list[Member], loaders=None) -> "EvidenceSet":
        loaders = loaders or _default_loaders()
        loads = Counter()
        creator = loaders["creator"](conn); loads["creator"] += 1
        audience = loaders["audience"](conn); loads["audience"] += 1
        metric = loaders["metric"](conn, [m.social_account_id for m in members]); loads["metric"] += 1
        return cls(creator, audience, metric, loads)

    def creator_results(self, members: list[Member], tahun: int, conn, prototype: bool = True):
        """Hasil classifier creator + audience untuk cohort, dihitung sekali.

        Mengembalikan (tax, rows, results) dengan bentuk yang sama seperti
        `creator_classification_writer.load_inputs`, tapi TANPA query ulang."""
        if self._classified is None:
            import creator_classification_writer as W
            kol_ids = {m.kol_id for m in members}
            tax, kols, *rest = self.creator
            data = (tax, [k for k in kols if str(k[0]) in kol_ids], *rest)
            self._classified = W.load_inputs(conn, prototype, tahun, data=data,
                                             audience_in=self.audience)[:3]
        return self._classified


# ---------------------------------------------------------------------------
# Snapshot (before / after): nilai per akun, lalu coverage
# ---------------------------------------------------------------------------
SQL_STATE = """
    SELECT x.sa::text,
           c.creator_gender, c.creator_age,
           d.inferred_category_id::text, d.inferred_subcategory_id::text,
           (SELECT string_agg(a.attribute_key, ',' ORDER BY a.attribute_key)
              FROM public.kol_attribute_map m JOIN public.kol_attribute a ON a.id = m.kol_attribute_id
             WHERE m.kol_directory_id = d.id AND a.kind = 'style'),
           (SELECT string_agg(a.attribute_key, ',' ORDER BY a.attribute_key)
              FROM public.kol_attribute_map m JOIN public.kol_attribute a ON a.id = m.kol_attribute_id
             WHERE m.kol_directory_id = d.id AND a.kind = 'personality'),
           coalesce(ie.engagement_rate, te.engagement_rate),
           {card_cols},
           (SELECT md5(string_agg(b.agency_id::text || ':' || coalesce(b.match_pct::text, '') || ':'
                                  || coalesce(b.unavailable, '') || ':' || coalesce(b.breakdown::text, ''),
                                  '|' ORDER BY b.agency_id))
              FROM public.brand_match_result b WHERE b.kol_directory_id = d.id)
      FROM unnest(%s::uuid[]) x(sa)
      LEFT JOIN public.kol_social_account k ON k.social_account_id = x.sa
      LEFT JOIN public.kol_directory d ON d.id = k.kol_id
      LEFT JOIN l2_gold.kol_profile_card c ON c.social_account_id = x.sa
      LEFT JOIN feature.ig_engagement_analysis ie ON ie.social_account_id = x.sa
      LEFT JOIN feature.tt_engagement_analysis te ON te.social_account_id = x.sa"""


def read_state(conn, members: list[Member], audience_inputs: dict) -> dict[str, dict]:
    """Nilai per akun untuk semua field laporan. Audiens memakai definisi (2):
    `audience_classification` (MIN_KNOWN, GENDER_SHARE_MIN) atas evidence feature/L2."""
    import audience_classification as A
    card = list(CARD_METRIC_COLS.items())
    sql = SQL_STATE.format(card_cols=", ".join(f"c.{col}" for _m, col in card))
    with conn.cursor() as cur:
        cur.execute(sql, ([m.social_account_id for m in members],))
        rows = cur.fetchall()
    out = {}
    for r in rows:
        sa = r[0]
        creator = dict(zip(CREATOR_FIELDS, r[1:7]))
        metric = {"ER": r[7]}
        metric.update({m: v for (m, _c), v in zip(card, r[8:8 + len(card)])})
        metric["brand_match"] = r[8 + len(card)]
        aud = A.classify(audience_inputs.get(sa, A.AudienceInput()))
        audience = {f: aud[f].value for f in AUDIENCE_FIELDS}
        out[sa] = {"creator": {k: _jsonable(v) for k, v in creator.items()},
                   "audience": audience,
                   "metric": {k: _jsonable(v) for k, v in metric.items()}}
    return out


def coverage(state: dict) -> dict[str, dict[str, int]]:
    cov = {"creator": Counter(), "audience": Counter(), "metric": Counter()}
    for acc in state.values():
        for grp, vals in acc.items():
            for f, v in vals.items():
                cov[grp][f] += v is not None
    return {g: dict(c) for g, c in cov.items()}


def count_changes(before: dict, after: dict) -> dict[str, int]:
    out = Counter()
    for sa, acc in after.items():
        for grp, vals in acc.items():
            for f, v in vals.items():
                out[grp] += before.get(sa, {}).get(grp, {}).get(f) != v
    return {g: out[g] for g in ("creator", "audience", "metric")}


# ---------------------------------------------------------------------------
# Alasan Unknown
# ---------------------------------------------------------------------------
#: urutan penting: pola yang lebih spesifik lebih dulu
_CREATOR_REASON_RULES = (
    ("tidak punya subkategori di taxonomy", STRUCTURALLY_UNAVAILABLE),
    ("akun bisnis", STRUCTURALLY_UNAVAILABLE),
    ("akun grup", STRUCTURALLY_UNAVAILABLE),
    ("kategori unknown", INSUFFICIENT_EVIDENCE),      # kaskade: induk tidak cukup bukti
    ("bertentangan", CONFLICTING_EVIDENCE),
    ("beberapa kategori", CONFLICTING_EVIDENCE),
    (": seri ", CONFLICTING_EVIDENCE),
    ("post ber-caption (<", BELOW_THRESHOLD),
    ("tidak ada pola", BELOW_THRESHOLD),
    ("terlalu lemah", INSUFFICIENT_EVIDENCE),
    ("hanya bukti lemah", INSUFFICIENT_EVIDENCE),
    ("sinyal pria yang lemah", INSUFFICIENT_EVIDENCE),
    ("nik tidak terurai", NO_SOURCE),
    ("tidak ada bukti", NO_SOURCE),
    ("tidak ada pernyataan", NO_SOURCE),
    ("tidak ada sinyal", NO_SOURCE),
)


def creator_reason(reason: str) -> str:
    r = (reason or "").lower()
    for pat, code in _CREATOR_REASON_RULES:
        if pat in r:
            return code
    return UNCLASSIFIED


def audience_reason(reason: str, n_follower: int) -> str:
    """Alasan Unknown audiens. Akun tanpa satu pun baris follower: sumbernya
    hanya bisa didapat lewat scraping berbayar -> BLOCKED_BY_ZERO_COST."""
    r = (reason or "").lower()
    if not n_follower:
        return BLOCKED_BY_ZERO_COST
    if "seri" in r:
        return CONFLICTING_EVIDENCE
    m = re.search(r"hanya ([\d.]+) follower diketahui", r)
    if m:   # 0 diketahui = tidak ada satu pun bukti, bukan "kurang sedikit dari ambang"
        return NO_SOURCE if float(m.group(1)) == 0 else BELOW_THRESHOLD
    if "seimbang" in r:
        return BELOW_THRESHOLD
    if "tidak ada feature" in r or "tidak ada baris" in r or "kosong" in r:
        return NO_SOURCE
    return UNCLASSIFIED


_POST_METRICS = ("avg_views", "median_views", "viral_frequency", "paid_ratio", "post_frequency",
                 "format_dominant", "content_topic", "ER")
_AUDIENCE_METRICS = ("audience_quality", "authenticity", "interest", "gender")


def metric_reason(metric: str, ev: dict | None) -> str:
    """Alasan Unknown metric dari evidence yang sudah dibaca (tanpa query ulang)."""
    if not ev or not ev.get("has_card"):
        return NO_SOURCE
    if metric == "brand_match":
        return NO_SOURCE                      # belum ada hasil Brand Match untuk KOL ini
    if metric in _POST_METRICS and not ev["n_post"]:
        return BLOCKED_BY_ZERO_COST           # post hanya bisa didapat lewat scraping
    if metric in _AUDIENCE_METRICS and not ev["n_follower"]:
        return BLOCKED_BY_ZERO_COST
    if metric == "ER":
        if ev["first_snap"] is None:
            return BLOCKED_BY_ZERO_COST       # tidak ada snapshot followers > 0
        if ev["last_post"] is not None and ev["first_snap"] > ev["last_post"]:
            return STRUCTURALLY_UNAVAILABLE   # ER point-in-time: semua post lebih tua dari snapshot
        return INSUFFICIENT_EVIDENCE
    if metric in ("avg_views", "median_views", "viral_frequency"):
        return STRUCTURALLY_UNAVAILABLE if not ev["n_views"] else INSUFFICIENT_EVIDENCE
    if metric == "paid_ratio":
        return STRUCTURALLY_UNAVAILABLE if not ev["n_spons_known"] else INSUFFICIENT_EVIDENCE
    if metric == "content_topic":
        return NO_SOURCE if not ev["n_caption"] else INSUFFICIENT_EVIDENCE
    return INSUFFICIENT_EVIDENCE


def unknown_reasons(state: dict, evidence: EvidenceSet, members: list[Member], tahun: int,
                    conn) -> dict:
    """{grup: {field: Counter(kode)}} untuk setiap nilai Unknown di `state`."""
    import audience_classification as A
    _tax, _rows, results = evidence.creator_results(members, tahun, conn)
    by_kol = {str(r[0]): r[2] for r in results}          # kol_id -> hasil classifier creator
    kol_of = {m.social_account_id: m.kol_id for m in members}
    out = {"creator": {}, "audience": {}, "metric": {}}
    for sa, acc in state.items():
        ev = evidence.metric.get(sa)
        res = by_kol.get(kol_of.get(sa))
        for f, v in acc["creator"].items():
            if v is not None:
                continue
            if res is None:
                code = NO_SOURCE
            elif res[f].known:
                code = PENDING_WRITE
            else:
                code = creator_reason(res[f].reason)
            out["creator"].setdefault(f, Counter())[code] += 1
        aud = A.classify(evidence.audience.get(sa, A.AudienceInput()))
        for f, v in acc["audience"].items():
            if v is None:
                code = audience_reason(aud[f].reason, (ev or {}).get("n_follower", 0))
                out["audience"].setdefault(f, Counter())[code] += 1
        for f, v in acc["metric"].items():
            if v is None:
                out["metric"].setdefault(f, Counter())[metric_reason(f, ev)] += 1
    return out


# ---------------------------------------------------------------------------
# Brand Match: hanya bila inputnya berubah
# ---------------------------------------------------------------------------
BRAND_MATCH_INPUTS = {
    "public.kol_directory": ("id", "inferred_category_id", "inferred_subcategory_id",
                             "category_id", "category_ids", "directory_status"),
    "public.kol_attribute_map": ("kol_directory_id", "kol_attribute_id"),
    "feature.ig_audience_analysis": None,     # None = semua kolom non-timestamp
    "feature.tt_audience_analysis": None,
    "l2_gold.kol_profile_card": None,
}


def _value_columns(cur, table: str) -> list[str]:
    schema, name = table.split(".")
    cur.execute("""SELECT column_name FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                      AND data_type NOT LIKE 'timestamp%%' AND data_type <> 'date'
                    ORDER BY ordinal_position""", (schema, name))
    return [c for (c,) in cur.fetchall()]


def brand_match_input_fingerprint(cur) -> dict[str, str]:
    """Sidik jari input Brand Match TANPA kolom waktu: timestamp yang bergeser
    tanpa perubahan nilai tidak boleh memicu perhitungan ulang."""
    out = {}
    for table, cols in BRAND_MATCH_INPUTS.items():
        cols = cols or _value_columns(cur, table)
        expr = "row(" + ", ".join(f't."{c}"' for c in cols) + ")::text"
        cur.execute(f"SELECT count(*), md5(coalesce(string_agg({expr}, '|' ORDER BY {expr}), '')) "
                    f"FROM {table} t")
        n, fp = cur.fetchone()
        out[table] = f"{n}:{fp}"
    return out


def brand_match_decision(before_fp: dict, after_fp: dict, stored: dict | None) -> tuple[bool, str]:
    if before_fp != after_fp:
        changed = sorted(k for k in after_fp if before_fp.get(k) != after_fp.get(k))
        return True, "input_changed_this_run: " + ", ".join(changed)
    if stored and stored.get("fingerprint") not in (None, after_fp):
        return True, "input_changed_since_last_brand_match"
    return False, "skipped_no_input_change"


#: Trigger yang diterima `scripts/brand-match-recalc.ts` (Autometric) hanya
#: brand_profile | kol_data | manual. One-pass memicu karena data KOL berubah.
BRAND_MATCH_TRIGGER = "kol_data"


def run_brand_match() -> dict:
    """Panggil op existing `recalculate_brand_match` (npm di repo Autometric)."""
    from dagster import build_op_context

    from kol_orchestration.brand_match import recalculate_brand_match
    with G.allow_subprocess("brand-match:recalc"):
        return recalculate_brand_match(build_op_context(op_config={"trigger": BRAND_MATCH_TRIGGER}))


# ---------------------------------------------------------------------------
# [7/8] Integrity
# ---------------------------------------------------------------------------
INTEGRITY_SQL = {
    # --- duplicate ---
    "duplicate unified_post (akun, content_id)": """SELECT count(*) FROM (SELECT 1 FROM l1_silver.unified_post
        WHERE social_account_id = ANY(%(sa)s::uuid[]) GROUP BY social_account_id, content_id HAVING count(*) > 1) z""",
    "duplicate unified_follower (akun, follower, tanggal)": """SELECT count(*) FROM (SELECT 1
        FROM l1_silver.unified_follower WHERE social_account_id = ANY(%(sa)s::uuid[])
        GROUP BY social_account_id, follower_platform_id, date HAVING count(*) > 1) z""",
    "duplicate kol_profile_card per akun": """SELECT count(*) FROM (SELECT 1 FROM l2_gold.kol_profile_card
        WHERE social_account_id = ANY(%(sa)s::uuid[]) GROUP BY social_account_id HAVING count(*) > 1) z""",
    "duplicate feature engagement per akun": """SELECT count(*) FROM (SELECT u.social_account_id
        FROM (SELECT social_account_id FROM feature.ig_engagement_analysis
              UNION ALL SELECT social_account_id FROM feature.tt_engagement_analysis) u
        WHERE u.social_account_id = ANY(%(sa)s::uuid[]) GROUP BY 1 HAVING count(*) > 1) z""",
    "duplicate kol_attribute_map (kol, attribute)": """SELECT count(*) FROM (SELECT 1
        FROM public.kol_attribute_map GROUP BY kol_directory_id, kol_attribute_id HAVING count(*) > 1) z""",
    "duplicate brand_match_result (agency, kol)": """SELECT count(*) FROM (SELECT 1
        FROM public.brand_match_result GROUP BY agency_id, kol_directory_id HAVING count(*) > 1) z""",
    # --- orphan ---
    "orphan unified_post": """SELECT count(*) FROM l1_silver.unified_post u WHERE NOT EXISTS
        (SELECT 1 FROM public.social_account s WHERE s.id = u.social_account_id)""",
    "orphan unified_follower": """SELECT count(*) FROM l1_silver.unified_follower f WHERE NOT EXISTS
        (SELECT 1 FROM public.social_account s WHERE s.id = f.social_account_id)""",
    "orphan kol_attribute_map": """SELECT count(*) FROM public.kol_attribute_map m
        WHERE NOT EXISTS (SELECT 1 FROM public.kol_directory d WHERE d.id = m.kol_directory_id)
           OR NOT EXISTS (SELECT 1 FROM public.kol_attribute a WHERE a.id = m.kol_attribute_id)""",
    "orphan kategori inferred (FK)": """SELECT count(*) FROM public.kol_directory d
        WHERE (d.inferred_category_id IS NOT NULL AND NOT EXISTS
               (SELECT 1 FROM public.kol_categories k WHERE k.id = d.inferred_category_id))
           OR (d.inferred_subcategory_id IS NOT NULL AND NOT EXISTS
               (SELECT 1 FROM public.kol_categories k WHERE k.id = d.inferred_subcategory_id))""",
    # --- ownership ---
    "invalid ownership: post platform != akun": """SELECT count(*) FROM l1_silver.unified_post u
        JOIN public.social_account s ON s.id = u.social_account_id
        WHERE u.social_account_id = ANY(%(sa)s::uuid[]) AND u.platform_id IS DISTINCT FROM s.platform_id""",
    "invalid ownership: card platform != akun": """SELECT count(*) FROM l2_gold.kol_profile_card c
        JOIN public.social_account s ON s.id = c.social_account_id
        JOIN public.platforms p ON p.id = s.platform_id
        WHERE c.social_account_id = ANY(%(sa)s::uuid[]) AND c.platform IS DISTINCT FROM p.key""",
    # --- ER invariant (sama dengan audit ER point-in-time) ---
    "ER invariant: post valid tapi ER NULL": """WITH snap AS (SELECT social_account_id, date
          FROM l1_silver.unified_profile WHERE followers_count > 0)
        SELECT count(*) FROM l1_silver.unified_post u WHERE u.social_account_id = ANY(%(sa)s::uuid[])
           AND u.likes_hidden IS NOT TRUE AND u.is_collaboration IS NOT TRUE
           AND u.engagement_rate IS NULL AND EXISTS (SELECT 1 FROM snap s
               WHERE s.social_account_id = u.social_account_id
                 AND s.date <= (u.posted_at AT TIME ZONE 'UTC')::date)""",
}

SQL_TOTALS = {
    "social_account": "SELECT count(*) FROM public.social_account",
    "kol_directory": "SELECT count(*) FROM public.kol_directory",
    "kol_profile_card": "SELECT count(*) FROM l2_gold.kol_profile_card",
    "brand_match_result": "SELECT count(*) FROM public.brand_match_result",
    "kol_attribute_map": "SELECT count(*) FROM public.kol_attribute_map",
    "cohort unified_post": "SELECT count(*) FROM l1_silver.unified_post WHERE social_account_id = ANY(%(sa)s::uuid[])",
    "cohort unified_follower": ("SELECT count(*) FROM l1_silver.unified_follower "
                                "WHERE social_account_id = ANY(%(sa)s::uuid[])"),
    "cohort kol_profile_card": ("SELECT count(*) FROM l2_gold.kol_profile_card "
                                "WHERE social_account_id = ANY(%(sa)s::uuid[])"),
}
#: Tabel berbutir per-akun/master: jumlahnya tidak boleh berubah oleh command ini.
FIXED_TOTALS = ("social_account", "kol_directory", "kol_profile_card", "cohort kol_profile_card")

SQL_CURATED_FP = {
    "kol_attribute_map non-classifier": """SELECT count(*), md5(coalesce(string_agg(t::text, '|'
        ORDER BY t::text), '')) FROM public.kol_attribute_map t WHERE t.source <> 'creator_classification'""",
    "kol_directory kurasi (category_id/category_ids)": """SELECT count(*), md5(coalesce(string_agg(
        t.id::text || ':' || coalesce(t.category_id::text, '') || ':' || coalesce(t.category_ids::text, ''),
        '|' ORDER BY t.id), '')) FROM public.kol_directory t""",
    "kol_profile_card creator manual": """SELECT count(*), md5(coalesce(string_agg(t.social_account_id::text
        || ':' || coalesce(t.creator_gender, '') || ':' || coalesce(t.creator_age::text, ''), '|'
        ORDER BY t.social_account_id), '')) FROM l2_gold.kol_profile_card t
        WHERE t.creator_gender_source = 'manual' OR t.creator_age_source = 'manual'""",
}


def db_meta(cur, sa_ids: list[str]) -> dict:
    """Total baris + sidik jari data kurasi, untuk dibandingkan before/after."""
    meta = {"totals": {}, "curated": {}}
    for k, sql in SQL_TOTALS.items():
        cur.execute(sql, {"sa": sa_ids})
        meta["totals"][k] = cur.fetchone()[0]
    for k, sql in SQL_CURATED_FP.items():
        cur.execute(sql)
        meta["curated"][k] = list(cur.fetchone())
    return meta


@dataclass
class Check:
    group: str
    name: str
    got: object
    want: object

    @property
    def ok(self) -> bool:
        return self.got == self.want


def run_integrity(cur, members: list[Member], baseline: dict, before_meta: dict,
                  after_meta: dict, deleted_rows: int) -> list[Check]:
    sa = [m.social_account_id for m in members]
    exp = baseline["cohort"]
    checks = [
        Check("cohort", "cohort file", validate_cohort(members, exp), []),
        Check("cohort", "cohort vs DB", validate_cohort_db(cur, members), []),
    ]
    for name, sql in INTEGRITY_SQL.items():
        cur.execute(sql, {"sa": sa})
        row = cur.fetchone()
        grp = name.split(" ")[0].rstrip(":")
        checks.append(Check(grp, name, row[0] if row else 0, 0))
    checks.append(Check("taxonomy", "fingerprint == baseline",
                        G.diff_taxonomy(baseline["taxonomy"], G.taxonomy_fingerprint(cur)), []))
    for k, v in before_meta["curated"].items():
        checks.append(Check("curated", f"{k} tidak tertimpa", after_meta["curated"][k], v))
    for k in FIXED_TOTALS:
        checks.append(Check("row explosion", f"total {k} tetap",
                            after_meta["totals"][k], before_meta["totals"][k]))
    for k in ("cohort unified_post", "cohort unified_follower", "kol_attribute_map", "brand_match_result"):
        checks.append(Check("row explosion", f"{k} tidak berkurang",
                            after_meta["totals"][k] >= before_meta["totals"][k], True))
    checks.append(Check("delete", "rows_deleted", deleted_rows, 0))
    return checks


# ---------------------------------------------------------------------------
# Laporan
# ---------------------------------------------------------------------------
NEXT_STEP = {
    NO_SOURCE: "sumber tidak ada di DB -- tidak ada yang bisa dikerjakan gratis",
    INSUFFICIENT_EVIDENCE: "bukti ada tapi tidak cukup untuk rule existing",
    BELOW_THRESHOLD: "di bawah ambang existing (ambang TIDAK diturunkan)",
    CONFLICTING_EVIDENCE: "bukti bertentangan / seri -- tidak ditebak",
    STRUCTURALLY_UNAVAILABLE: "platform/actor tidak menyediakan sinyal ini",
    BLOCKED_BY_ZERO_COST: "butuh scraping berbayar -> SKIP (blocked_by_zero_cost_constraint)",
    PENDING_WRITE: "classifier sudah tahu nilainya, akan ditulis run normal",
    UNCLASSIFIED: "teks alasan classifier belum terpetakan -- lihat report.json",
}


def build_rows(before_cov: dict, after_cov: dict | None, reasons: dict, n: int) -> list[dict]:
    rows = []
    for grp, fields in (("creator", CREATOR_FIELDS), ("audience", AUDIENCE_FIELDS), ("metric", METRIC_FIELDS)):
        for f in fields:
            b = before_cov[grp].get(f, 0)
            a = after_cov[grp].get(f, 0) if after_cov else None
            cur = a if a is not None else b
            rows.append({"group": grp, "field": f, "before": b, "after": a,
                         "delta": None if a is None else a - b, "unknown": n - cur,
                         "reason": dict(sorted(reasons[grp].get(f, Counter()).items()))})
    return rows


def render_table(rows: list[dict]) -> str:
    head = f"  {'field':<28}{'before':>7}{'after':>7}{'delta':>7}{'unknown':>9}  reason"
    lines = [head, "  " + "-" * (len(head) + 20)]
    for r in rows:
        name = f"{r['group']}.{r['field']}"
        a = "-" if r["after"] is None else r["after"]
        d = "-" if r["delta"] is None else f"{r['delta']:+d}"
        reason = ", ".join(f"{k}={v}" for k, v in r["reason"].items()) or "-"
        lines.append(f"  {name:<28}{r['before']:>7}{a!s:>7}{d:>7}{r['unknown']:>9}  {reason}")
    return "\n".join(lines)


def render_markdown(report: dict) -> str:
    out = [f"# One-pass enrichment -- {report['mode']} -- {report['started_at']}", "",
           f"Cohort: {report['cohort']['total']} ({report['cohort']['instagram']} IG / "
           f"{report['cohort']['tiktok']} TikTok)", "",
           "Audience memakai definisi `audience_classification` (MIN_KNOWN=5, GENDER_SHARE_MIN=60), "
           "bukan jumlah baris L2 mentah.", "",
           "| field | before | after | delta | unknown | reason |", "|---|---:|---:|---:|---:|---|"]
    for r in report["coverage"]:
        reason = ", ".join(f"{k}={v}" for k, v in r["reason"].items()) or "-"
        out.append(f"| {r['group']}.{r['field']} | {r['before']} | "
                   f"{'-' if r['after'] is None else r['after']} | "
                   f"{'-' if r['delta'] is None else r['delta']} | {r['unknown']} | {reason} |")
    out += ["", "## Kode alasan", ""] + [f"- **{k}**: {v}" for k, v in NEXT_STEP.items()]
    out += ["", "## Safety", ""] + [f"- {k}: {v}" for k, v in report["safety"].items()]
    out += ["", "## Integrity", ""] + [
        f"- {'PASS' if c['ok'] else 'FAIL'} [{c['group']}] {c['name']}: {c['got']}" for c in report["integrity"]]
    out += ["", "## Write", "", "```", json.dumps(report["writes"], indent=1, default=str), "```"]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
@dataclass
class Outcome:
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _connect_readonly():
    from config import load_config
    conn = psycopg2.connect(connect_timeout=15, **load_config().postgres.as_connect_kwargs())
    conn.set_session(readonly=True, autocommit=True)
    return conn


def _connect_guarded(mode: str):
    from config import load_config
    return G.guarded_connect(load_config().postgres.as_connect_kwargs(), mode=mode)


def _creator_plan(evidence: EvidenceSet, members, tahun, conn):
    import creator_classification_writer as W
    tax, _rows, results = evidence.creator_results(members, tahun, conn)
    with conn.cursor() as cur:
        attr_ids = {}
        cur.execute(W.SQL_ATTRIBUTE_IDS)
        for aid, kind, key in cur.fetchall():
            attr_ids[(kind, key)] = aid
        state = W.read_state(cur)
    return tax, results, attr_ids, W.plan(tax, results, state, attr_ids, EVIDENCE_MODE)


def _apply_creator(evidence, members, tahun, mode: str) -> dict:
    """Plan -> write -> guard writer existing -> COMMIT (mode write) / ROLLBACK (rehearse)."""
    import creator_classification_writer as W
    conn = _connect_guarded(mode)
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '15s'")
        tax, results, attr_ids, p = _creator_plan(evidence, members, tahun, conn)
        if p.map_deletes:
            conn.rollback()
            raise G.DeleteBlocked(f"BLOCKED: creator writer akan menghapus {len(p.map_deletes)} "
                                  "baris kol_attribute_map milik classifier")
        if p.invalid:
            conn.rollback()
            return {"status": "aborted_invalid", "invalid": len(p.invalid)}
        if not p.n_changes:
            conn.rollback()
            return {"status": "no_change", "candidate": 0, "written": 0}
        with conn.cursor() as cur:
            cur.execute(W.SQL_COUNTS["active"])
            active = cur.fetchone()[0]

        def replan(cur):
            return W.plan(tax, results, W.read_state(cur), attr_ids, EVIDENCE_MODE)
        done, problems, committed = W.apply(conn, replan, p, commit=True,
                                            check=functools.partial(W.guards, expect_active=active))
        status = "guard_failed" if problems else "committed" if committed and mode == "write" else "rehearsed"
        return {"status": status,
                "candidate": p.n_changes, "written": done, "guard_problems": problems}
    finally:
        conn.close()


def _run_chain(mode: str) -> tuple[bool, list[str]]:
    from kol_orchestration.one_shot import jalankan_transform_chain
    from kol_orchestration.repository import _build_connection_string
    res = G.GuardedPostgresResource(connection_string=_build_connection_string(), mode=mode)
    return jalankan_transform_chain(postgres=res)


def _l1_fingerprint(conn, sa_ids) -> str:
    """Perubahan evidence akibat materialisasi -> evidence perlu dibaca ulang."""
    parts = []
    with conn.cursor() as cur:
        for t in ("l1_silver.unified_post", "l1_silver.unified_profile",
                  "feature.ig_audience_analysis", "feature.tt_audience_analysis",
                  "l2_gold.kol_profile_card", "l2_gold.audience_geo_daily"):
            cols = [c for c in _value_columns(cur, t) if c not in ("id",)]
            expr = "row(" + ", ".join(f't."{c}"' for c in cols) + ")::text"
            cur.execute(f"SELECT md5(coalesce(string_agg({expr}, '|' ORDER BY {expr}), '')) FROM {t} t "
                        "WHERE t.social_account_id = ANY(%s::uuid[])", (sa_ids,))
            parts.append(cur.fetchone()[0])
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def _run_tests() -> dict:
    import subprocess
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
           str(_PROJECT_ROOT / "tests" / "test_one_pass_enrichment.py")]
    with G.allow_subprocess("test_one_pass_enrichment.py"):
        r = subprocess.run(cmd, cwd=_PROJECT_ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    summary = ((r.stdout or "").strip().splitlines()[-1:] or [""])[0]
    counts = {k: 0 for k in ("passed", "failed", "skipped", "error")}
    for n, k in re.findall(r"(\d+) (passed|failed|skipped|errors?)", summary):
        counts["error" if k.startswith("error") else k] += int(n)
    return {"summary": summary, **counts, "returncode": r.returncode}


def run(mode: str, *, with_tests: bool = True, out_root: Path = OUTPUT_ROOT) -> int:
    """mode: 'report-only' | 'dry-run' | 'normal'. Mengembalikan exit code."""
    t0 = time.time()
    started = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = out_root / f"{started}-{mode}"
    out_dir.mkdir(parents=True, exist_ok=True)
    tahun = date.today().year
    outcome = Outcome()
    G.RECORDER.reset()

    # --- penjaga dipasang SEBELUM apa pun ---------------------------------
    G.install_cost_guard()
    baseline = G.load_baseline()
    _log("=" * 72)
    _log(f"ONE-PASS ENRICHMENT  mode={mode}  output={out_dir}")
    _log("  " + "  ".join(f"{k}={str(v).lower()}" for k, v in G.POLICY.as_env().items()))
    G.check_thresholds(baseline)
    _log("  thresholds == baseline (MIN_KNOWN=%s, GENDER_SHARE_MIN=%s)" % (
        baseline["thresholds"]["audience_classification"]["MIN_KNOWN"],
        baseline["thresholds"]["audience_classification"]["GENDER_SHARE_MIN"]))
    _log("=" * 72)

    ro = _connect_readonly()
    try:
        # [1/8] -------------------------------------------------------------
        _step(1, "Cohort")
        members = load_cohort()
        sa_ids = [m.social_account_id for m in members]
        per = Counter(m.platform for m in members)
        with ro.cursor() as cur:
            G.check_taxonomy(cur, baseline)
            problems = validate_cohort(members, baseline["cohort"]) + validate_cohort_db(cur, members)
        _log(f"  {len(members)} akun  instagram={per['instagram']}  tiktok={per['tiktok']}  "
             f"masalah={len(problems)}")
        if problems:
            outcome.blockers += [f"cohort: {p}" for p in problems]

        # [2/8] -------------------------------------------------------------
        _step(2, "Evidence")
        evidence = EvidenceSet.build(ro, members)
        tax, kols = evidence.creator[0], evidence.creator[1]
        n_posts = sum(len(evidence.creator[3].get(sa, [])) for sa in sa_ids)
        _log(f"  creator: {len(kols)} KOL aktif dibaca, post L1 cohort={n_posts}")
        _log(f"  audience: feature untuk {sum(sa in evidence.audience for sa in sa_ids)}/{len(sa_ids)} akun")
        _log(f"  metric: follower cohort={sum(e['n_follower'] for e in evidence.metric.values())}, "
             f"bio={sum(e['n_bio'] for e in evidence.metric.values())}")
        before = read_state(ro, members, evidence.audience)
        with ro.cursor() as cur:
            before_meta = db_meta(cur, sa_ids)
            bm_before = brand_match_input_fingerprint(cur)
        (out_dir / "before.json").write_text(json.dumps(
            {"coverage": coverage(before), "accounts": before, "meta": before_meta},
            indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        _log(f"  before.json ditulis ({len(before)} akun)")

        # [3/8] -------------------------------------------------------------
        _step(3, "Creator enrichment")
        _tax, results, _ids, plan = _creator_plan(evidence, members, tahun, ro)
        creator_known = Counter()
        for r in results:
            for a in CREATOR_FIELDS:
                creator_known[a] += r[2][a].known
        _log("  classifier (ambang existing): " + ", ".join(f"{a}={creator_known[a]}" for a in CREATOR_FIELDS))
        _log(f"  kandidat write: kol_directory={len(plan.kd_updates)}  map insert={len(plan.map_inserts)}  "
             f"update={len(plan.map_updates)}  delete={len(plan.map_deletes)}  invalid={len(plan.invalid)}")
        _log(f"  gender/age kartu != classifier: {len(plan.card_mismatch)} (diisi asset creator_gender/age)")
        if plan.map_deletes:
            outcome.blockers.append(f"creator writer akan menghapus {len(plan.map_deletes)} baris "
                                    "kol_attribute_map -> STOP (delete disabled)")
        if plan.invalid:
            outcome.blockers.append(f"creator classifier menghasilkan {len(plan.invalid)} hasil tidak valid")

        # [4/8] -------------------------------------------------------------
        _step(4, "Audience enrichment")
        cov_b = coverage(before)
        _log("  audience_classification (MIN_KNOWN=5): " + ", ".join(
            f"{f}={cov_b['audience'].get(f, 0)}" for f in AUDIENCE_FIELDS))
        _log("  sumber kebenaran: asset audience_feature/audience_gold (ditulis di langkah 6)")

        # [5/8] -------------------------------------------------------------
        _step(5, "Metrics")
        _log("  " + ", ".join(f"{f}={cov_b['metric'].get(f, 0)}" for f in METRIC_FIELDS))
        _log("  definisi metric tidak diubah; dihitung asset feature_*/gold_* (langkah 6)")

        # [6/8] -------------------------------------------------------------
        _step(6, "Materialization")
        writes: dict = {"chain": None, "creator": None, "brand_match": None}
        after, after_meta = before, before_meta
        if mode == "report-only":
            _log("  --report-only: dilewati (tidak ada write, tidak ada rehearsal)")
            writes["brand_match"] = "skipped_report_only"
        elif mode == "dry-run":
            # Rehearsal PENUH: setiap asset benar-benar menjalankan SQL-nya, lalu
            # GuardedConnection mengganti commit dengan ROLLBACK dan mencatat
            # insert/update/delete per tabel dari pg_stat_xact_user_tables.
            _log("  rehearsal rantai L0 -> L2 (semua commit -> ROLLBACK) ...")
            ok, _summary = _run_chain("rehearse")
            reh = G.RECORDER.totals("rehearsed")
            per_table = G.RECORDER.per_table("rehearsed")
            writes["chain"] = {"status": "rehearsed_only", "success": ok, **reh, "per_table": per_table}
            _log(f"  rehearsal: sukses={ok}  insert={reh['inserted']}  update={reh['updated']}  "
                 f"delete={reh['deleted']}")
            if not ok:
                outcome.blockers.append("rehearsal rantai transformasi gagal: " + "; ".join(G.RECORDER.blocked))
            if reh["deleted"]:
                tables = {t: v["deleted"] for t, v in per_table.items() if v["deleted"]}
                outcome.blockers.append(f"rantai transformasi akan menghapus {reh['deleted']} baris {tables} "
                                        "-> run normal akan STOP (delete disabled)")
            cre = _apply_creator(evidence, members, tahun, "rehearse") if not plan.map_deletes else None
            writes["creator"] = cre or {"status": "not_rehearsed_blocked"}
            # Prediksi kasar: jumlah baris dari rehearsal ikut menghitung update
            # yang hanya menggeser timestamp; run normal memutuskan lewat sidik
            # jari NILAI (tanpa kolom waktu).
            touched = sorted(t for t, v in per_table.items() if t in BRAND_MATCH_INPUTS
                             and (v["inserted"] or v["updated"] or v["deleted"]))
            writes["brand_match"] = (f"would_check (rows touched: {', '.join(touched)})"
                                     if touched or plan.n_changes else "skipped_no_input_change")
            _log(f"  creator writer rehearsal: {writes['creator']}")
            _log(f"  brand_match = {writes['brand_match']}")
        else:
            # Tidak ada rehearsal penuh lebih dulu (rantai existing ~20 menit).
            # Asset yang transaksinya akan menghapus baris di-ROLLBACK utuh oleh
            # GuardedConnection saat commit, dicatat, dan pipeline berhenti --
            # delete tidak pernah tersimpan. Hitungan lengkap: jalankan --dry-run.
            if outcome.blockers:
                _log("  STOP: ada blocker, tidak ada write yang dijalankan")
                for b in outcome.blockers:
                    _log(f"    - {b}")
                writes["chain"] = writes["creator"] = "stopped"
                writes["brand_match"] = "skipped_blocked"
            else:
                l1_before = _l1_fingerprint(ro, sa_ids)
                _log("  rantai L0 -> L2 (write) ...")
                ok, summary = _run_chain("write")
                writes["chain"] = {"success": ok, "assets": len(summary)}
                if not ok:
                    outcome.blockers.append("rantai transformasi gagal: "
                                            + ("; ".join(G.RECORDER.blocked) or "lihat log Dagster"))
                if _l1_fingerprint(ro, sa_ids) != l1_before:
                    _log("  evidence berubah akibat materialisasi -> evidence dibaca ulang sekali")
                    evidence = EvidenceSet.build(ro, members)
                    outcome.notes.append("evidence refreshed after materialization")
                if not outcome.blockers:
                    try:
                        writes["creator"] = _apply_creator(evidence, members, tahun, "write")
                    except G.BlockedOperation as exc:
                        outcome.blockers.append(str(exc))
                        writes["creator"] = {"status": "blocked", "error": str(exc)}
                    _log(f"  creator writer: {writes['creator']}")
                with ro.cursor() as cur:
                    bm_after = brand_match_input_fingerprint(cur)
                stored = None
                if BRAND_MATCH_STATE.exists():
                    stored = json.loads(BRAND_MATCH_STATE.read_text(encoding="utf-8"))
                run_bm, why = brand_match_decision(bm_before, bm_after, stored)
                if outcome.blockers:
                    writes["brand_match"] = "skipped_blocked"
                elif not run_bm:
                    writes["brand_match"] = why
                    if stored is None:     # catat baseline pengamatan, BUKAN klaim telah dihitung
                        BRAND_MATCH_STATE.write_text(json.dumps(
                            {"fingerprint": bm_after, "status": "baseline_observed",
                             "at": datetime.now().isoformat()}, indent=1), encoding="utf-8")
                else:
                    try:
                        res = run_brand_match()
                        writes["brand_match"] = {"status": "ran", "reason": why, **res}
                        BRAND_MATCH_STATE.write_text(json.dumps(
                            {"fingerprint": bm_after, "status": "computed",
                             "at": datetime.now().isoformat()}, indent=1), encoding="utf-8")
                    except Exception as exc:   # Brand Match gagal tidak menghentikan laporan
                        writes["brand_match"] = {"status": "failed", "reason": why, "error": str(exc)[:300]}
                        outcome.notes.append("brand match gagal: " + str(exc)[:200])
                        # Catat sidik jari SEBELUM run: run berikutnya melihat input
                        # berbeda dari yang terakhir dihitung, jadi Brand Match dicoba lagi.
                        BRAND_MATCH_STATE.write_text(json.dumps(
                            {"fingerprint": stored.get("fingerprint", bm_before) if stored else bm_before,
                             "status": "failed", "at": datetime.now().isoformat()}, indent=1),
                            encoding="utf-8")
                _log(f"  brand_match = {writes['brand_match']}")
                after = read_state(ro, members, evidence.audience)
                with ro.cursor() as cur:
                    after_meta = db_meta(cur, sa_ids)
                (out_dir / "after.json").write_text(json.dumps(
                    {"coverage": coverage(after), "accounts": after, "meta": after_meta},
                    indent=1, ensure_ascii=False, default=str), encoding="utf-8")
                _log("  after.json ditulis")
        committed = G.RECORDER.totals("committed")
        writes["committed"] = {**committed, "per_table": G.RECORDER.per_table("committed")}

        # [7/8] -------------------------------------------------------------
        _step(7, "Integrity")
        G.check_thresholds(baseline)
        with ro.cursor() as cur:
            checks = run_integrity(cur, members, baseline, before_meta, after_meta, committed["deleted"])
        for c in checks:
            _log(f"  {'OK  ' if c.ok else 'FAIL'} [{c.group}] {c.name}: {c.got}")
        integrity_ok = all(c.ok for c in checks)

        # [8/8] -------------------------------------------------------------
        _step(8, "Report")
        reasons = unknown_reasons(after, evidence, members, tahun, ro)
        cov_a = coverage(after) if mode == "normal" and after is not before else None
        rows = build_rows(cov_b, cov_a, reasons, len(members))
        _log(render_table(rows))
        changes = count_changes(before, after)
        tests = _run_tests() if with_tests else {"summary": "not run (--skip-tests)", "passed": 0,
                                                 "failed": 0, "skipped": 0, "error": 0}
        report = {
            "mode": mode, "started_at": started, "duration_s": round(time.time() - t0, 1),
            "cohort": {"total": len(members), "instagram": per["instagram"], "tiktok": per["tiktok"]},
            "coverage": rows, "changes": changes, "writes": writes,
            "creator_plan": {"kd_updates": len(plan.kd_updates), "map_inserts": len(plan.map_inserts),
                             "map_updates": len(plan.map_updates), "map_deletes": len(plan.map_deletes),
                             "card_mismatch": len(plan.card_mismatch), "invalid": len(plan.invalid)},
            "evidence_loads": dict(evidence.loads),
            "safety": {**G.POLICY.as_env(), "paid_scraping_calls": 0, "external_spend_usd": 0,
                       "cost_guard_active": G.cost_guard_active(), "blocked_events": G.RECORDER.blocked},
            "integrity": [{"group": c.group, "name": c.name, "got": c.got, "want": c.want, "ok": c.ok}
                          for c in checks],
            "blockers": outcome.blockers, "notes": outcome.notes, "tests": tests,
        }
        (out_dir / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str),
                                             encoding="utf-8")
        (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    finally:
        ro.close()

    status = "COMPLETE" if not outcome.blockers else "STOPPED"
    title = {"normal": "ONE-PASS", "dry-run": "ONE-PASS DRY-RUN", "report-only": "ONE-PASS REPORT"}[mode]
    _log("\n" + "=" * 72)
    _log(f"{title} {status}\n")
    _log(f"Cohort: {len(members)}")
    _log(f"Creator changes: {changes['creator']}")
    _log(f"Audience changes: {changes['audience']}")
    _log(f"Metric changes: {changes['metric']}\n")
    if mode == "dry-run":
        reh = G.RECORDER.totals("rehearsed")
        _log(f"Rows that WOULD be inserted: {reh['inserted']}")
        _log(f"Rows that WOULD be updated: {reh['updated']}")
        _log(f"Rows that WOULD be deleted: {reh['deleted']}")
        _log(f"Creator candidate writes: {plan.n_changes}")
    _log(f"Rows inserted: {committed['inserted']}")
    _log(f"Rows updated: {committed['updated']}")
    _log(f"Rows deleted: {committed['deleted']}\n")
    _log("Paid scraping: 0")
    _log("External spend: $0\n")
    if with_tests:
        _log(f"Tests: {tests['passed']} passed / {tests['failed'] + tests['error']} failed"
             f" / {tests['skipped']} skipped")
    else:
        _log("Tests: not run (--skip-tests)")
    _log(f"Integrity: {'PASS' if integrity_ok else 'FAIL'}")
    bm = writes.get("brand_match")
    _log(f"Brand match: {bm.get('status') if isinstance(bm, dict) else bm}")
    for n in outcome.notes:
        _log(f"NOTE: {n}")
    for b in outcome.blockers:
        _log(f"BLOCKER: {b}")
    _log(f"Report: {out_dir}")
    _log("=" * 72)
    tests_ok = not with_tests or (tests["failed"] + tests["error"] == 0 and tests["returncode"] == 0)
    return 0 if integrity_ok and not outcome.blockers and tests_ok else 1


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m orchestration.one_pass_enrichment",
                                 description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true",
                   help="rehearsal penuh: hitung candidate/affected rows, deteksi delete, lalu ROLLBACK")
    g.add_argument("--report-only", action="store_true",
                   help="coverage + alasan Unknown dari state sekarang, tanpa write/rehearsal")
    ap.add_argument("--skip-tests", action="store_true", help="jangan jalankan test safety one-pass")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    mode = "dry-run" if args.dry_run else "report-only" if args.report_only else "normal"
    from run_lock import LockTaken, RunLock
    try:
        with RunLock("one_pass_enrichment"):
            return run(mode, with_tests=not args.skip_tests)
    except LockTaken as exc:
        print(exc)
        return 3
    except G.BlockedOperation as exc:
        print(f"\n{exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
