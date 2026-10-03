"""Bridge: hasil Creator Classification -> field category yang dibaca aplikasi.

    python creator_category_bridge.py [--dry-run]   # default: tidak menulis apa pun
    python creator_category_bridge.py --rehearse    # WRITE -> GUARD -> ROLLBACK
    python creator_category_bridge.py --commit      # WRITE -> GUARD -> COMMIT (ROLLBACK kalau guard gagal)
    python creator_category_bridge.py ... --kol-id UUID [--kol-id UUID ...]

`creator_classification_writer` menulis hasil classifier ke
`kol_directory.inferred_category_id` / `inferred_subcategory_id`. Aplikasi
(Discovery, facet, Brand Match) membaca Category dari `category_id` /
`category_ids`. KOL dari "Add New KOL" tidak masuk roster, jadi dua kolom itu
kosong selamanya walau classifier sudah punya jawabannya. Modul ini menyalin
jawaban itu, HANYA untuk KOL yang kolom kurasinya masih kosong:

    category_id  := inferred_category_id
    category_ids := ARRAY[inferred_category_id]

Aturan (semuanya juga dijaga di WHERE `SQL_BRIDGE_UPDATE`, bukan hanya di plan):

    * KOL aktif saja.
    * `category_id` ATAU `category_ids` sudah terisi -> tidak disentuh. Tidak ada
      jalur yang menimpa atau mengosongkan nilai yang sudah ada.
    * Hanya hasil classifier (`inferred_category_source = 'creator_classification'`)
      dengan confidence high/medium. Low tidak dipromosikan (tetap di inferred_*).
      Baris `curated` sudah punya jalurnya sendiri dan bukan urusan bridge.
    * Subcategory TIDAK dimasukkan ke `category_ids`: pembaca array itu menganggap
      tiap elemen Category level 1 (lihat `kol_sub_category_taxonomy.py`).
      Subcategory tetap di `inferred_subcategory_id` -- field yang dipakai aplikasi.

Tidak ada DELETE, tidak ada INSERT, tidak ada perubahan schema/taxonomy.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

import psycopg2

from config import load_config

CLASSIFIER_SOURCE = "creator_classification"
#: Confidence yang boleh dipromosikan ke kolom category aplikasi.
BRIDGE_CONFIDENCE = ("high", "medium")

SQL_CANDIDATES = """
    SELECT k.id::text, k.username, k.category_id::text, k.category_ids::text[],
           k.inferred_category_id::text, k.inferred_subcategory_id::text,
           k.inferred_category_source, k.inferred_category_confidence,
           c.name, s.name
      FROM public.kol_directory k
      LEFT JOIN public.kol_categories c ON c.id = k.inferred_category_id
      LEFT JOIN public.kol_categories s ON s.id = k.inferred_subcategory_id
     WHERE k.directory_status = 'active'
       AND k.category_id IS NULL AND coalesce(cardinality(k.category_ids), 0) = 0
     ORDER BY k.id"""
SQL_BRIDGE_UPDATE = f"""
    UPDATE public.kol_directory
       SET category_id = inferred_category_id,
           category_ids = ARRAY[inferred_category_id]
     WHERE id = %s
       AND directory_status = 'active'
       AND category_id IS NULL AND coalesce(cardinality(category_ids), 0) = 0
       AND inferred_category_id IS NOT NULL
       AND inferred_category_source = '{CLASSIFIER_SOURCE}'
       AND inferred_category_confidence IN ({', '.join(f"'{c}'" for c in BRIDGE_CONFIDENCE)})"""

#: Sidik jari guard. `rest` = SEMUA baris di luar target, seluruh kolom.
#: `target_other` = baris target, seluruh kolom KECUALI dua kolom yang ditulis bridge.
SQL_FP_REST = """
    SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t.id), ''))
      FROM public.kol_directory t WHERE NOT (t.id = ANY(%s::uuid[]))"""
SQL_FP_TARGET_OTHER = """
    SELECT count(*), md5(coalesce(string_agg((to_jsonb(t) - 'category_id' - 'category_ids')::text,
                                             '|' ORDER BY t.id), ''))
      FROM public.kol_directory t WHERE t.id = ANY(%s::uuid[])"""
SQL_ACTIVE = "SELECT count(*) FROM public.kol_directory WHERE directory_status = 'active'"
SQL_TOTAL = "SELECT count(*) FROM public.kol_directory"
SQL_BAD_CATEGORY = """
    SELECT count(*) FROM public.kol_directory k
      LEFT JOIN public.kol_categories c ON c.id = k.category_id
     WHERE k.id = ANY(%s::uuid[]) AND k.category_id IS NOT NULL
       AND (c.id IS NULL OR c.level <> 'category' OR c.parent_id IS NOT NULL
            OR k.category_ids IS DISTINCT FROM ARRAY[k.category_id]
            OR k.category_id IS DISTINCT FROM k.inferred_category_id)"""


@dataclass
class Candidate:
    kol_id: str
    username: str | None
    category_id: str | None
    category_ids: tuple
    inferred_category_id: str | None
    inferred_subcategory_id: str | None
    source: str | None
    confidence: str | None
    category_name: str | None = None
    subcategory_name: str | None = None


@dataclass
class BridgePlan:
    updates: list[Candidate] = field(default_factory=list)
    skipped: dict[str, list[str]] = field(default_factory=dict)

    def skip(self, why: str, kol_id: str) -> None:
        self.skipped.setdefault(why, []).append(kol_id)

    @property
    def target_ids(self) -> list[str]:
        return [c.kol_id for c in self.updates]


def plan(cands) -> BridgePlan:
    """Murni: kandidat -> baris yang boleh dibridge, sisanya dicatat dengan alasannya."""
    p = BridgePlan()
    for c in cands:
        if c.category_id is not None or c.category_ids:
            p.skip("category sudah terisi", c.kol_id)
        elif c.inferred_category_id is None:
            p.skip("belum ada hasil classifier", c.kol_id)
        elif c.source != CLASSIFIER_SOURCE:
            p.skip(f"source {c.source!r} bukan milik classifier", c.kol_id)
        elif c.confidence not in BRIDGE_CONFIDENCE:
            p.skip(f"confidence {c.confidence!r} tidak dipromosikan", c.kol_id)
        else:
            p.updates.append(c)
    return p


def read_candidates(cur, kol_ids=None) -> list[Candidate]:
    cur.execute(SQL_CANDIDATES)
    want = None if kol_ids is None else {str(k) for k in kol_ids}
    return [Candidate(r[0], r[1], r[2], tuple(r[3] or ()), r[4], r[5], r[6], r[7], r[8], r[9])
            for r in cur.fetchall() if want is None or r[0] in want]


def snapshot(cur, target_ids: list[str]) -> dict:
    snap = {}
    for key, sql, params in (("rest", SQL_FP_REST, (target_ids,)),
                             ("target_other", SQL_FP_TARGET_OTHER, (target_ids,)),
                             ("active", SQL_ACTIVE, None), ("total", SQL_TOTAL, None),
                             ("bad_category", SQL_BAD_CATEGORY, (target_ids,))):
        cur.execute(sql, params)
        row = cur.fetchone()
        snap[key] = list(row) if len(row) > 1 else row[0]
    return snap


def guards(before: dict, after: dict, n_planned: int, n_done: int, n_left: int,
           expect_active: int | None = None) -> list[str]:
    bad = []
    if before["active"] != after["active"]:
        bad.append(f"active KOL berubah selama transaksi: {before['active']} -> {after['active']}")
    elif expect_active is not None and after["active"] != expect_active:
        bad.append(f"active KOL {after['active']}, expected {expect_active}")
    if before["total"] != after["total"]:
        bad.append(f"jumlah baris kol_directory berubah: {before['total']} -> {after['total']}")
    if before["rest"] != after["rest"]:
        bad.append(f"baris kol_directory di luar target berubah: {before['rest']} -> {after['rest']}")
    if before["target_other"] != after["target_other"]:
        bad.append("kolom selain category_id/category_ids pada baris target berubah")
    if n_done != n_planned:
        bad.append(f"written {n_done} != candidate {n_planned}")
    if n_left:
        bad.append(f"state belum konvergen: {n_left} kandidat tersisa setelah write")
    if after["bad_category"]:
        bad.append(f"bad_category = {after['bad_category']}")
    return bad


def execute_plan(cur, p: BridgePlan) -> int:
    done = 0
    for c in p.updates:
        cur.execute(SQL_BRIDGE_UPDATE, (c.kol_id,))
        done += cur.rowcount
    return done


def apply(conn, p: BridgePlan, *, commit: bool, kol_ids=None, snap=snapshot, check=guards,
          expect_active: int | None = None) -> tuple[int, list[str], bool]:
    """Satu transaksi: snapshot -> write -> snapshot -> re-plan -> guard -> COMMIT/ROLLBACK.
    Tanpa commit=True selalu ROLLBACK. Error apa pun -> ROLLBACK lalu dilempar ulang."""
    try:
        ids = p.target_ids
        with conn.cursor() as cur:
            before = snap(cur, ids)
            done = execute_plan(cur, p)
            after = snap(cur, ids)
            left = len(plan(read_candidates(cur, kol_ids)).updates)
        problems = check(before, after, len(p.updates), done, left, expect_active)
        if problems or not commit:
            conn.rollback()
            return done, problems, False
        conn.commit()
        return done, problems, True
    except Exception:
        conn.rollback()
        raise


def print_plan(p: BridgePlan) -> None:
    print(f"\n== BRIDGE PLAN: {len(p.updates)} KOL ==")
    for c in p.updates:
        print(f"  @{c.username} ({c.kol_id}) -> category {c.category_name!r} "
              f"[{c.confidence}] | subcategory {c.subcategory_name!r}")
    for why, ids in sorted(p.skipped.items()):
        print(f"  skip {len(ids)}: {why}")


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="default: tidak menulis apa pun")
    g.add_argument("--rehearse", action="store_true", help="WRITE -> GUARD -> ROLLBACK")
    g.add_argument("--commit", action="store_true", help="WRITE -> GUARD -> COMMIT")
    ap.add_argument("--kol-id", action="append", default=None, metavar="UUID",
                    help="batasi ke kol_directory.id ini (boleh diulang)")
    ap.add_argument("--expect-active", type=int, default=None,
                    help="guard tambahan: jumlah KOL aktif harus persis N (default: dinamis)")
    args = ap.parse_args()
    write = args.rehearse or args.commit
    conn = psycopg2.connect(connect_timeout=10, **load_config().postgres.as_connect_kwargs())
    try:
        if not write:
            conn.set_session(readonly=True)
        with conn.cursor() as cur:
            if write:
                cur.execute("SET LOCAL lock_timeout = '15s'")
            p = plan(read_candidates(cur, args.kol_id))
        print_plan(p)
        if not write:
            conn.rollback()
            print("\n(no database writes)")
            return 0
        done, problems, committed = apply(conn, p, commit=args.commit, kol_ids=args.kol_id,
                                          expect_active=args.expect_active)
        print(f"\nwritten in transaction: {done} / candidate {len(p.updates)}")
        for x in problems:
            print("  GUARD FAILED:", x)
        print("COMMIT" if committed else "ROLLBACK" + (" (guard gagal)" if problems else " (rehearse)"))
        return 0 if not problems else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
