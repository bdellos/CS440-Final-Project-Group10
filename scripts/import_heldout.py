"""Import a researcher's held-out labeling workbook as two human runs (#45, #46, #47).

    .venv/Scripts/python scripts/import_heldout.py data/heldout/Heldout_Labeling_Brendan.xlsx --rater brendan
    .venv/Scripts/python scripts/import_heldout.py data/heldout/Heldout_Labeling_Brendan.xlsx --rater brendan --apply

The workbook is the one scripts/heldout_workbook.py built: sheet "Labeling", rows H01..H50.
  purpose  "Purpose categories" (keys separated by ;) + "Purpose evidence" (quotes separated by |)
           -> human run <rater> on sample `heldout`, purpose heldout, the frozen purpose codebook
  context  "Context category" (one key) + "Context evidence"
           -> human run <rater> on sample `heldout-repos`, purpose heldout, the frozen context codebook
  "Notes" go on both records.

Every row faces the same validation as an agent's label (record_label's checks): categories from the
frozen codebook, exact quotes (skill text, or the repo's cached context for context evidence), notes
of at most 300 characters. Unlike Round 0 imports, evidence is required.

Without --apply it is a dry run in a throwaway copy of labels.db, listing every problem. --apply
imports only when the dry run finds none (or with --skip-problem-rows, leaving those rows out).
"""
import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labeling  # noqa: E402
import runs  # noqa: E402
from db import connect, labels_path  # noqa: E402
from import_round0 import QUOTE_CHARS, WorkbookError  # noqa: E402

SKILLS, REPOS = "heldout", "heldout-repos"
COLUMNS = {"id": "ID", "pcats": "Purpose categories", "pev": "Purpose evidence",
           "ccat": "Context category", "cev": "Context evidence", "notes": "Notes"}


def _split(value, sep):
    return [v.strip() for v in str(value or "").split(sep) if v.strip()]


def read_workbook(path: Path) -> list:
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    if "Labeling" not in wb.sheetnames:
        raise WorkbookError(f"{path.name} has no sheet named 'Labeling' (sheets: {wb.sheetnames})")
    rows = wb["Labeling"].iter_rows(values_only=True)
    header = [str(h or "").strip() for h in next(rows)]
    missing = [v for v in COLUMNS.values() if v not in header]
    if missing:
        raise WorkbookError(f"the Labeling sheet is missing columns {missing} (found {header})")
    col = {k: header.index(v) for k, v in COLUMNS.items()}
    out = []
    for r in rows:
        rid = str(r[col["id"]] or "").strip()
        if not rid:
            continue
        quotes = lambda k: [q.strip(QUOTE_CHARS) for q in _split(r[col[k]], "|") if q.strip(QUOTE_CHARS)]  # noqa: E731
        out.append({"id": rid, "purpose": _split(r[col["pcats"]], ";"), "purpose_quotes": quotes("pev"),
                    "context": _split(r[col["ccat"]], ";"), "context_quotes": quotes("cev"),
                    "notes": str(r[col["notes"]] or "").strip()})
    return out


def _positions(con, sample):
    rows = con.execute("SELECT i.position, i.item_id FROM sample_items i JOIN samples s USING (sample_id) "
                       "WHERE s.name = ?", (sample,)).fetchall()
    if not rows:
        raise WorkbookError(f"no sample named {sample!r}")
    return {f"H{pos:02d}": item for pos, item in rows}


def _frozen(con, taxonomy):
    row = con.execute("SELECT version FROM codebook_versions WHERE taxonomy = ? AND variant = 'main' AND frozen = 1",
                      (taxonomy,)).fetchone()
    if row is None:
        raise WorkbookError(f"the {taxonomy} codebook isn't frozen; held-out labels use the frozen version")
    return row[0]


def do_import(con, rows: list, rater: str, skip: set = frozenset()) -> dict:
    for sample in (SKILLS, REPOS):
        if con.execute("SELECT 1 FROM runs r JOIN samples s USING (sample_id) WHERE s.name = ? AND r.rater = ? "
                       "AND r.purpose = 'heldout'", (sample, rater)).fetchone():
            raise WorkbookError(f"{rater} already has a held-out run on {sample}; nothing imported")
    skills, repos = _positions(con, SKILLS), _positions(con, REPOS)
    note = f"Imported from {rater}'s held-out labeling workbook (scripts/import_heldout.py)."
    res = {"rows": len(rows), "stored": {"purpose": 0, "context": 0}, "uncoded": [], "problems": [], "runs": {}}
    for taxonomy, sample, items, kind in (("purpose", SKILLS, skills, "skill"), ("context", REPOS, repos, "repo")):
        version = _frozen(con, taxonomy)
        run_id = runs.start_run(con, sample, taxonomy, rater, "heldout", version, human=True, notes=note)["run_id"]
        res["runs"][taxonomy] = run_id
        for row in rows:
            rid = row["id"]
            if rid not in items:
                res["problems"].append((rid, f"ID {rid} is not a position in sample {sample!r}"))
                continue
            cats = row[taxonomy]
            if not cats:
                res["uncoded"].append(f"{rid} {taxonomy}")
                continue
            if rid in skip:
                continue
            evidence = [{"quote": q, "quote_en": q} for q in row[f"{taxonomy}_quotes"][:5]]
            lang = None
            if kind == "skill":
                hit = con.execute("SELECT language FROM skill_language WHERE file_sha = ?", (items[rid],)).fetchone()
                lang = hit[0] if hit else "en"
            rec = {"schema_version": 1, "run_id": run_id, "item_kind": kind, "item_id": items[rid],
                   "taxonomy": taxonomy, "codebook_version": version, "proposals": [],
                   "labels": [{"category": c, "evidence": evidence} for c in cats]}
            if kind == "skill":
                rec["skill_language"] = lang
            if row["notes"]:
                rec["notes"] = row["notes"]
            try:
                labeling.store_label(con, rec, allow_human=True)
                res["stored"][taxonomy] += 1
            except labeling.LabelRejected as e:
                res["problems"] += [(rid, f"{taxonomy}: {err}") for err in e.errors]
        runs.finish_run(con, run_id, allow_incomplete=True)
    return res


def report(res: dict, rater: str, dry: bool) -> None:
    print(f"{'DRY RUN (nothing changed)' if dry else 'IMPORTED'}: {rater}, runs {res['runs']}"
          f"{' (in a throwaway copy)' if dry else ''}")
    print(f"  rows {res['rows']}, stored purpose {res['stored']['purpose']}, context {res['stored']['context']}, "
          f"left blank {len(res['uncoded'])} of {2 * res['rows']} (purpose + context)"
          f"{': ' + ', '.join(res['uncoded']) if 0 < len(res['uncoded']) <= 10 else ''}")
    if res["problems"]:
        print(f"  {len(res['problems'])} problem(s), by row:")
        for rid, err in res["problems"]:
            print(f"    {rid}: {err}")
    else:
        print("  no problems")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("workbook", type=Path)
    p.add_argument("--rater", required=True, help="the coder's lowercase first name, e.g. brendan")
    p.add_argument("--apply", action="store_true", help="import into the real labels.db")
    p.add_argument("--skip-problem-rows", action="store_true", help="with --apply: leave out rows with problems")
    a = p.parse_args(argv)
    rows = read_workbook(a.workbook)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "labels.db"
        src, dst = connect(labels_db=labels_path()), sqlite3.connect(copy)
        src.backup(dst)
        src.close()
        dst.close()
        con = connect(labels_db=copy)
        try:
            dry = do_import(con, rows, a.rater)
        finally:
            con.close()
    report(dry, a.rater, dry=True)
    if not a.apply:
        return 0 if not dry["problems"] else 1
    if dry["problems"] and not a.skip_problem_rows:
        sys.exit("not imported: fix the problems above, or pass --skip-problem-rows to leave those rows out")
    skip = {rid for rid, _ in dry["problems"]}
    con = connect(labels_db=labels_path())
    try:
        res = do_import(con, rows, a.rater, skip=skip)
    finally:
        con.close()
    report(res, a.rater, dry=False)
    if skip:
        print(f"  left out (problems): {sorted(skip)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (WorkbookError, runs.RunError) as e:
        sys.exit(f"error: {e}")
