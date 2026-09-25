"""Importer keputusan classification MANUSIA (hasil review workbook) -> DB `kol`.

    python classification_manual_import.py <decisions.csv>            DRY-RUN (default): rencana + validasi
    python classification_manual_import.py <decisions.csv> --apply    tulis baris yang lolos validasi

Hanya baris yang ada di file keputusan (= sudah dikonfirmasi manusia) yang diproses.
Target dan source, sesuai constraint DB yang ada (tanpa migration):

    gender        l2_gold.kol_profile_card.creator_gender, creator_gender_source='manual',
                  creator_gender_confidence='high'. Asset creator_gender tidak pernah menimpa 'manual'.
    style         public.kol_attribute_map, source='curated' (ck: curated|creator_classification).
    personality   Writer classifier melewati kind yang punya baris curated.

    category      BLOCKED. Satu-satunya kolom kurasi adalah kol_directory.category_id/category_ids
    subcategory   (mapping roster), dan subkategori kurasi tidak punya kolom sama sekali;
                  inferred_* hanya boleh source 'creator_classification'. Menulisnya butuh
                  keputusan terpisah -- importer ini menolak, tidak menyamarkan.

Idempotent: baris yang nilainya sudah sama dilewati. Tidak ada DELETE, tidak ada
UPDATE atas baris milik classifier/roster: gender hanya ditulis bila kartu belum
'manual' dan nilainya kosong; attribute hanya di-INSERT bila (kol, attribute) belum ada.
Satu username bisa punya beberapa akun cohort (IG + TikTok) -- keputusan berlaku per
kreator, jadi semua akun dengan username itu ikut.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COHORT_PATH = ROOT / "orchestration" / "kol_orchestration" / "data" / "one_pass_cohort.csv"

FIELDS = ("gender", "category", "subcategory", "style", "personality")
GENDERS = ("female", "male")
BLOCKED_FIELDS = {
    "category": "tidak ada kolom kurasi yang sah untuk ditulis tanpa menimpa mapping roster "
                "(kol_directory.category_ids) -- butuh keputusan terpisah",
    "subcategory": "tidak ada kolom subkategori kurasi di schema; inferred_* hanya untuk "
                   "source 'creator_classification' -- butuh keputusan terpisah",
}
SRC_CURATED = "curated"
SRC_MANUAL = "manual"


@dataclass
class Decision:
    username: str
    field: str
    value: str
    evidence: str = ""


@dataclass
class Row:
    """Satu write yang direncanakan (atau alasan tidak ditulis)."""
    decision: Decision
    status: str                    # WRITE | SKIP_SAME | BLOCKED | INVALID
    reason: str = ""
    social_account_id: str | None = None
    kol_id: str | None = None
    platform: str | None = None
    target: str = ""
    params: dict = field(default_factory=dict)


def read_decisions(path: Path) -> list[Decision]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        out = []
        for r in csv.DictReader(fh):
            d = Decision(r["username"].strip().lstrip("@"), r["field"].strip().lower(),
                         r["value"].strip(), (r.get("evidence") or "").strip())
            if d.username and d.field:
                out.append(d)
    return out


def read_cohort(path: Path = COHORT_PATH) -> dict[str, list[dict]]:
    by_user: dict[str, list[dict]] = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            by_user.setdefault(r["sa_username"].lower(), []).append(
                {"sa": r["sa"], "kol_id": r["kol_id"], "platform": r["plat"]})
    return by_user


def plan(decisions: list[Decision], cohort: dict[str, list[dict]], attributes: dict[tuple[str, str], str],
         card: dict[str, tuple], attr_map: set[tuple[str, str]], today: date) -> list[Row]:
    """Murni (tanpa DB): keputusan -> baris rencana.

    attributes  (kind, attribute_key) -> kol_attribute.id (aktif)
    card        social_account_id -> (creator_gender, creator_gender_source)
    attr_map    {(kol_directory_id, kol_attribute_id)} yang sudah ada (source apa pun)"""
    rows: list[Row] = []
    seen: set[tuple] = set()
    for d in decisions:
        if d.field not in FIELDS:
            rows.append(Row(d, "INVALID", f"field tidak dikenal: {d.field}"))
            continue
        accounts = cohort.get(d.username.lower())
        if not accounts:
            rows.append(Row(d, "INVALID", "username tidak ada di cohort"))
            continue
        if d.field in BLOCKED_FIELDS:
            for a in accounts:
                rows.append(Row(d, "BLOCKED", BLOCKED_FIELDS[d.field], a["sa"], a["kol_id"], a["platform"]))
            continue
        for a in accounts:
            key = (a["sa"], d.field)
            if key in seen:
                rows.append(Row(d, "INVALID", "keputusan ganda untuk akun + field yang sama",
                                a["sa"], a["kol_id"], a["platform"]))
                continue
            seen.add(key)
            base = dict(social_account_id=a["sa"], kol_id=a["kol_id"], platform=a["platform"])
            if d.field == "gender":
                if d.value not in GENDERS:
                    rows.append(Row(d, "INVALID", f"gender harus salah satu {GENDERS}", **base))
                    continue
                cur_val, cur_src = card.get(a["sa"], (None, None))
                if a["sa"] not in card:
                    rows.append(Row(d, "INVALID", "akun tidak punya baris kol_profile_card", **base))
                elif cur_src == SRC_MANUAL and cur_val == d.value:
                    rows.append(Row(d, "SKIP_SAME", "sudah manual dengan nilai sama", **base))
                elif cur_val is not None:
                    rows.append(Row(d, "INVALID", f"kartu sudah berisi {cur_val} ({cur_src}); "
                                                  "importer tidak menimpa nilai yang ada", **base))
                else:
                    rows.append(Row(d, "WRITE", "", target="l2_gold.kol_profile_card", params={
                        "gender": d.value, "source": SRC_MANUAL, "confidence": "high"}, **base))
                continue
            # style / personality
            attr_id = attributes.get((d.field, d.value))
            if attr_id is None:
                rows.append(Row(d, "INVALID", f"{d.value} bukan kol_attribute aktif kind '{d.field}'", **base))
                continue
            if (a["kol_id"], attr_id) in attr_map:
                rows.append(Row(d, "SKIP_SAME", "pasangan (kol, attribute) sudah ada", **base))
                continue
            rows.append(Row(d, "WRITE", "", target="public.kol_attribute_map", params={
                "kol_attribute_id": attr_id, "source": SRC_CURATED,
                "note": f"manual review {today.isoformat()}: keputusan reviewer atas saran rubric",
                "evidence": {"basis": "manual_review", "decided": today.isoformat(),
                             "suggestion_evidence": d.evidence[:500]}}, **base))
    return rows


# --- DB --------------------------------------------------------------------------
SQL_ATTR = "SELECT kind, attribute_key, id::text FROM public.kol_attribute WHERE is_active"
SQL_CARD = """SELECT social_account_id::text, creator_gender, creator_gender_source
                FROM l2_gold.kol_profile_card WHERE social_account_id = ANY(%s::uuid[])"""
SQL_MAP = """SELECT kol_directory_id::text, kol_attribute_id::text FROM public.kol_attribute_map
              WHERE kol_directory_id = ANY(%s::uuid[])"""
SQL_WRITE_GENDER = """
    UPDATE l2_gold.kol_profile_card
       SET creator_gender = %(gender)s, creator_gender_source = %(source)s,
           creator_gender_confidence = %(confidence)s
     WHERE social_account_id = %(sa)s AND creator_gender IS NULL
       AND creator_gender_source IS DISTINCT FROM 'manual'"""
SQL_WRITE_ATTR = """
    INSERT INTO public.kol_attribute_map (kol_directory_id, kol_attribute_id, source, note, evidence)
    SELECT %(kol)s, %(attr)s, %(source)s, %(note)s, %(evidence)s
     WHERE NOT EXISTS (SELECT 1 FROM public.kol_attribute_map
                        WHERE kol_directory_id = %(kol)s AND kol_attribute_id = %(attr)s)"""


def load_db_state(conn, rows_cohort: dict[str, list[dict]]):
    sa = [a["sa"] for accs in rows_cohort.values() for a in accs]
    kol = [a["kol_id"] for accs in rows_cohort.values() for a in accs]
    with conn.cursor() as cur:
        cur.execute(SQL_ATTR)
        attributes = {(k, key): i for k, key, i in cur.fetchall()}
        cur.execute(SQL_CARD, (sa,))
        card = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
        cur.execute(SQL_MAP, (kol,))
        attr_map = {(r[0], r[1]) for r in cur.fetchall()}
    return attributes, card, attr_map


def apply(conn, rows: list[Row]) -> int:
    import psycopg2.extras
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            if r.status != "WRITE":
                continue
            if r.target == "l2_gold.kol_profile_card":
                cur.execute(SQL_WRITE_GENDER, {**r.params, "sa": r.social_account_id})
            else:
                cur.execute(SQL_WRITE_ATTR, {"kol": r.kol_id, "attr": r.params["kol_attribute_id"],
                                             "source": r.params["source"], "note": r.params["note"],
                                             "evidence": psycopg2.extras.Json(r.params["evidence"])})
            n += cur.rowcount
    return n


def _connect(readonly: bool):
    import os
    import psycopg2
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    conn = psycopg2.connect(host=os.environ["PG_HOST"], port=os.environ["PG_PORT"], dbname=os.environ["PG_DB"],
                            user=os.environ["PG_USER"], password=os.environ["PG_PASSWORD"], connect_timeout=15)
    conn.set_session(readonly=readonly)
    return conn


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Import keputusan classification manusia (default dry-run)")
    p.add_argument("decisions", type=Path)
    p.add_argument("--apply", action="store_true", help="Tulis baris WRITE. Tanpa ini: dry-run read-only.")
    a = p.parse_args(argv)
    cohort = read_cohort()
    decisions = read_decisions(a.decisions)
    conn = _connect(readonly=not a.apply)
    try:
        rows = plan(decisions, cohort, *load_db_state(conn, cohort), date.today())
        for r in rows:
            print(f"{r.status:<9} {r.decision.username:<18} {r.platform or '-':<9} {r.decision.field:<11} "
                  f"{r.decision.value:<36} {r.target or r.reason}")
        counts = {s: sum(r.status == s for r in rows) for s in ("WRITE", "SKIP_SAME", "BLOCKED", "INVALID")}
        print(json.dumps(counts))
        if not a.apply:
            print("DRY-RUN: tidak ada write.")
            return 0
        if counts["INVALID"]:
            print("DIHENTIKAN: ada baris INVALID; perbaiki file keputusan dulu.")
            return 2
        n = apply(conn, rows)
        if n != counts["WRITE"]:
            conn.rollback()
            print(f"ROLLBACK: baris terdampak {n} != rencana {counts['WRITE']}")
            return 3
        conn.commit()
        print(f"COMMIT: {n} baris ditulis.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
