"""Import a researcher's Round 0 coding workbook as a human open-coding run (#40, #47 gap).

    .venv/Scripts/python scripts/import_round0.py coding/round0/Round0_Coding_Brendan.xlsx --rater brendan
    .venv/Scripts/python scripts/import_round0.py coding/round0/Round0_Coding_Brendan.xlsx --rater brendan --apply

The workbook is the one scripts/draw_round0_sample.py created: sheet "Coding", columns "ID"
(S01..S50), and the coder's "Categories" (separated by ;), "Evidence quote" (one or more
quotes, separated by |) and "Notes".

Without --apply (the default) it is a dry run: the whole import is done in a throwaway copy of
labels.db, every row facing the same validation as an agent's label (record_label's checks:
exact quotes, at most 300 characters of notes, ...), and every problem is listed. Nothing in the
real labels.db changes. With --apply it imports into the real labels.db, but only if the dry run
finds no problems, unless --skip-problem-rows is given (those rows are left out and listed).

A row with codes but no evidence quote is imported without evidence (decided 2026-11-25: one coder
recorded none) and listed in the run's notes; a quote that is given must still be exact.

Each code becomes a label of the human run `<rater>` (purpose round0, no codebook), so the
codebook-consolidator sees it through get_codes. All the row's quotes go with each of its codes,
since the workbook has one evidence column per skill. quote_en = quote (Round 0 skills are English).
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

COLUMNS = {"id": "ID", "categories": "Categories", "evidence": "Evidence quote", "notes": "Notes"}
QUOTE_CHARS = "\"'“”‘’ "


class WorkbookError(RuntimeError):
    pass


def read_workbook(path: Path) -> list:
    """[{id, categories, quotes, notes}] for every row of the Coding sheet."""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    if "Coding" not in wb.sheetnames:
        raise WorkbookError(f"{path.name} has no sheet named 'Coding' (sheets: {wb.sheetnames})")
    rows = wb["Coding"].iter_rows(values_only=True)
    header = [str(h or "").strip() for h in next(rows)]
    missing = [v for v in COLUMNS.values() if v not in header]
    if missing:
        raise WorkbookError(f"the Coding sheet is missing columns {missing} (found {header})")
    col = {k: header.index(v) for k, v in COLUMNS.items()}
    out = []
    for r in rows:
        rid = str(r[col["id"]] or "").strip()
        if not rid:
            continue
        cats = [c.strip() for c in str(r[col["categories"]] or "").split(";") if c.strip()]
        quotes = [q.strip().strip(QUOTE_CHARS) for q in str(r[col["evidence"]] or "").split("|")]
        out.append({"id": rid, "categories": cats, "quotes": [q for q in quotes if q],
                    "notes": str(r[col["notes"]] or "").strip()})
    return out


def _items_by_id(con, sample: str) -> dict:
    """S01 -> file_sha, from the sample's stored positions (S01 = position 1)."""
    rows = con.execute("SELECT i.position, i.item_id FROM sample_items i JOIN samples s USING (sample_id) "
                       "WHERE s.name = ?", (sample,)).fetchall()
    if not rows:
        raise WorkbookError(f"no sample named {sample!r}")
    return {f"S{pos:02d}": sha for pos, sha in rows}


def do_import(con, rows: list, rater: str, sample: str, skip: set = frozenset()) -> dict:
    """Start the human run and store every coded row; returns the run id, counts and problems."""
    existing = con.execute("SELECT run_id FROM runs r JOIN samples s USING (sample_id) WHERE s.name = ? "
                           "AND r.rater = ? AND r.purpose = 'round0'", (sample, rater)).fetchone()
    if existing:
        raise WorkbookError(f"{rater} already has Round 0 run {existing[0]} on {sample}; nothing imported")
    items = _items_by_id(con, sample)
    no_evidence = [r["id"] for r in rows if r["categories"] and not r["quotes"] and r["id"] not in skip]
    note = f"Imported from {rater}'s Round 0 coding workbook (#40)."
    if no_evidence:
        note += (f" Codes imported without evidence (the coder recorded no quote) for {len(no_evidence)} row(s): "
                 f"{', '.join(no_evidence)}.")
    run_id = runs.start_run(con, sample, "purpose", rater, "round0", None, human=True, notes=note)["run_id"]
    problems, stored, uncoded = [], 0, []
    for row in rows:
        rid = row["id"]
        if rid not in items:
            problems.append((rid, f"ID {rid} is not a position in sample {sample!r}"))
            continue
        if not row["categories"]:
            uncoded.append(rid)
            continue
        if rid in skip:
            continue
        lang = con.execute("SELECT language FROM skill_language WHERE file_sha = ?", (items[rid],)).fetchone()
        evidence = [{"quote": q, "quote_en": q} for q in row["quotes"][:5]]
        rec = {"schema_version": 1, "run_id": run_id, "item_kind": "skill", "item_id": items[rid],
               "taxonomy": "purpose", "codebook_version": None, "skill_language": lang[0] if lang else "en",
               "proposals": [], "labels": [{"category": c, "evidence": evidence} for c in row["categories"]]}
        if row["notes"]:
            rec["notes"] = row["notes"]
        try:
            labeling.store_label(con, rec, allow_human=True)
            stored += 1
        except labeling.LabelRejected as e:
            problems += [(rid, err) for err in e.errors]
    runs.finish_run(con, run_id, allow_incomplete=True)
    return {"run_id": run_id, "rows": len(rows), "stored": stored, "uncoded": uncoded, "problems": problems,
            "no_evidence": no_evidence,
            "codes": sorted({c for r in rows for c in r["categories"]})}


def report(res: dict, rater: str, dry: bool) -> None:
    print(f"{'DRY RUN (nothing changed)' if dry else 'IMPORTED'}: {rater}, run {res['run_id']}"
          f"{' (in a throwaway copy)' if dry else ''}")
    print(f"  rows {res['rows']}, stored {res['stored']}, uncoded {len(res['uncoded'])}"
          f"{' ' + str(res['uncoded']) if res['uncoded'] else ''}, distinct codes {len(res['codes'])}")
    if res["no_evidence"]:
        print(f"  imported without evidence (allowed for researchers' Round 0 codes, noted on the run): "
              f"{len(res['no_evidence'])} row(s)")
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
    p.add_argument("--sample", default="round0")
    p.add_argument("--apply", action="store_true", help="import into the real labels.db")
    p.add_argument("--skip-problem-rows", action="store_true", help="with --apply: leave out rows with problems")
    a = p.parse_args(argv)
    rows = read_workbook(a.workbook)
    real = labels_path()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "labels.db"
        src = connect(labels_db=real)
        dst = sqlite3.connect(copy)
        src.backup(dst)
        src.close()
        dst.close()
        con = connect(labels_db=copy)
        try:
            dry = do_import(con, rows, a.rater, a.sample)
        finally:
            con.close()
    report(dry, a.rater, dry=True)
    if not a.apply:
        return 0 if not dry["problems"] else 1
    if dry["problems"] and not a.skip_problem_rows:
        sys.exit("not imported: fix the problems above, or pass --skip-problem-rows to leave those rows out")
    skip = {rid for rid, _ in dry["problems"]}
    con = connect(labels_db=real)
    try:
        res = do_import(con, rows, a.rater, a.sample, skip=skip)
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
