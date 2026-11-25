"""Tests for the Round 0 workbook importer (scripts/import_round0.py).
Builds workbooks in the layout draw_round0_sample.py creates, against the throwaway database of
test_record_label (sample s1, 4 skills -> IDs S01..S04).
    .venv/Scripts/python -m pytest tests/test_import_round0.py
"""
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import import_round0 as imp  # noqa: E402
from test_record_label import env  # noqa: E402,F401  (fixture reused)

HEADERS = ["ID", "Skill name", "Description (from front matter)", "Repository", "Stars", "Body chars",
           "GitHub link", "Categories", "Evidence quote", "Notes"]


def workbook(path, rows):
    wb = Workbook()
    wb.active.title = "How to code"
    ws = wb.create_sheet("Coding")
    ws.append(HEADERS)
    for rid, cats, ev, notes in rows:
        ws.append([rid, "name", "desc", "repo", 0, 0, "link", cats, ev, notes])
    wb.save(path)
    return path


def good_rows(env):
    q = [quote for _, quote in env["items"]]
    return [("S01", "code a", f'"{q[0]}"', None),
            ("S02", "code b; code c", f'"{q[1]}" | "{q[1][:20]}"', "unsure whether b and c are one"),
            ("S03", "code a", f"“{q[2]}”", None),
            ("S04", None, None, None)]                      # left uncoded


def run_main(env, monkeypatch, path, *extra):
    monkeypatch.setenv("LABELS_DB", str(env["db"]))
    env["con"].commit()
    return imp.main([str(path), "--rater", "brendan", "--sample", "s1", *extra])


def human_runs(env):
    return env["con"].execute("SELECT run_id FROM runs WHERE rater = 'brendan' AND purpose = 'round0'").fetchall()


def test_read_workbook_parses_categories_quotes_and_notes(env, tmp_path):
    rows = imp.read_workbook(workbook(tmp_path / "w.xlsx", good_rows(env)))
    assert [r["id"] for r in rows] == ["S01", "S02", "S03", "S04"]
    assert rows[1]["categories"] == ["code b", "code c"] and len(rows[1]["quotes"]) == 2
    assert rows[2]["quotes"] == [env["items"][2][1]]          # curly quotes stripped
    assert rows[3]["categories"] == []


def test_dry_run_changes_nothing(env, tmp_path, monkeypatch, capsys):
    assert run_main(env, monkeypatch, workbook(tmp_path / "w.xlsx", good_rows(env))) == 0
    assert "DRY RUN" in capsys.readouterr().out
    assert human_runs(env) == []


def test_apply_imports_a_human_open_coding_run(env, tmp_path, monkeypatch, capsys):
    run_main(env, monkeypatch, workbook(tmp_path / "w.xlsx", good_rows(env)), "--apply")
    out = capsys.readouterr().out
    assert "IMPORTED" in out and "stored 3, uncoded 1" in out
    [(run_id,)] = human_runs(env)
    con = env["con"]
    r = con.execute("SELECT rater_kind, codebook_version_id, finished_at FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    assert r[0] == "human" and r[1] is None and r[2] is not None
    codes = sorted(x[0] for x in con.execute("SELECT l.category_key FROM annotation_labels l JOIN annotations a "
                                             "USING (annotation_id) WHERE a.run_id = ?", (run_id,)))
    assert codes == ["code a", "code a", "code b", "code c"]
    assert con.execute("SELECT COUNT(*) FROM annotations WHERE run_id = ? AND prompt_hash IS NOT NULL",
                       (run_id,)).fetchone()[0] == 0     # human labels carry no prompt_hash


def test_problems_are_listed_and_block_apply(env, tmp_path, monkeypatch, capsys):
    rows = good_rows(env)
    rows[0] = ("S01", "code a", '"a sentence this skill never says"', None)
    rows[2] = ("S03", "code a", None, None)
    rows.append(("S99", "code z", '"x"', None))
    path = workbook(tmp_path / "w.xlsx", rows)
    assert run_main(env, monkeypatch, path) == 1
    out = capsys.readouterr().out
    assert "S01: evidence" in out and "quote not found" in out
    assert "S03:" not in out and "imported without evidence" in out   # allowed for researchers (2026-11-25)
    assert "S99: ID S99 is not a position" in out
    with pytest.raises(SystemExit, match="not imported"):
        run_main(env, monkeypatch, path, "--apply")
    assert human_runs(env) == []


def test_long_notes_are_a_problem(env, tmp_path, monkeypatch, capsys):
    rows = good_rows(env)
    rows[0] = (rows[0][0], rows[0][1], rows[0][2], "x" * 301)
    assert run_main(env, monkeypatch, workbook(tmp_path / "w.xlsx", rows)) == 1
    assert "S01: schema" in capsys.readouterr().out


def test_skip_problem_rows_imports_the_rest(env, tmp_path, monkeypatch, capsys):
    rows = good_rows(env)
    rows[0] = ("S01", "code a", '"a sentence this skill never says"', None)
    run_main(env, monkeypatch, workbook(tmp_path / "w.xlsx", rows), "--apply", "--skip-problem-rows")
    out = capsys.readouterr().out
    assert "stored 2" in out and "left out (problems): ['S01']" in out


def test_a_second_import_is_refused(env, tmp_path, monkeypatch):
    path = workbook(tmp_path / "w.xlsx", good_rows(env))
    run_main(env, monkeypatch, path, "--apply")
    with pytest.raises(imp.WorkbookError, match="already has Round 0 run"):
        run_main(env, monkeypatch, path, "--apply")


def test_codes_without_evidence_are_imported_and_noted(env, tmp_path, monkeypatch, capsys):
    """Decided 2026-11-25: a coder who recorded no quotes still gets their codes into the merge (#40),
    flagged on the run. Quotes that are given must still be exact."""
    rows = [(rid, cats, None, None) for rid, cats, _, _ in good_rows(env)]
    run_main(env, monkeypatch, workbook(tmp_path / "w.xlsx", rows), "--apply")
    out = capsys.readouterr().out
    assert "stored 3" in out and "imported without evidence" in out
    [(run_id,)] = human_runs(env)
    note = env["con"].execute("SELECT notes FROM runs WHERE run_id = ?", (run_id,)).fetchone()[0]
    assert "without evidence" in note and "S01, S02, S03" in note
    assert env["con"].execute("SELECT COUNT(*) FROM evidence e JOIN annotations a USING (annotation_id) "
                              "WHERE a.run_id = ?", (run_id,)).fetchone()[0] == 0
