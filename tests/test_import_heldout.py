"""Tests for the held-out workbook importer (scripts/import_heldout.py, #45-#47).
    .venv/Scripts/python -m pytest tests/test_import_heldout.py
"""
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import import_heldout as imp  # noqa: E402
import heldout_workbook as hw  # noqa: E402
from test_record_label import env  # noqa: E402,F401  (fixture reused)


def workbook(path, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Labeling"
    ws.append(hw.HEADERS)
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


def test_reads_both_taxonomies(tmp_path):
    rows = imp.read_workbook(workbook(tmp_path / "w.xlsx", [
        ["H01", "n", "d", "o/r", "write-code; write-tests", '"use it when" | “run it”', "template", "is_template: true", "hm"],
        ["H02", "n", "d", "o/r", None, None, None, None, None],
        [None, None, None, None, None, None, None, None, None]]))
    assert [r["id"] for r in rows] == ["H01", "H02"]
    assert rows[0]["purpose"] == ["write-code", "write-tests"]
    assert rows[0]["purpose_quotes"] == ["use it when", "run it"]
    assert rows[0]["context"] == ["template"] and rows[0]["context_quotes"] == ["is_template: true"]
    assert rows[1]["purpose"] == [] and rows[1]["notes"] == ""


def test_missing_columns_are_reported(tmp_path):
    wb = Workbook()
    wb.active.title = "Labeling"
    wb.active.append(["ID", "Purpose categories"])
    wb.save(tmp_path / "w.xlsx")
    with pytest.raises(imp.WorkbookError, match="missing columns"):
        imp.read_workbook(tmp_path / "w.xlsx")


def test_refuses_without_frozen_codebooks(env):
    with env["con"]:
        env["con"].execute("INSERT INTO samples (name, item_kind, method) VALUES ('heldout', 'skill', 'test')")
        env["con"].execute("INSERT INTO samples (name, item_kind, method) VALUES ('heldout-repos', 'repo', 'test')")
        sid = env["con"].execute("SELECT sample_id FROM samples WHERE name = 'heldout'").fetchone()[0]
        env["con"].execute("INSERT INTO sample_items (sample_id, position, item_id) VALUES (?, 1, ?)",
                           (sid, env["items"][0][0]))
        rid = env["con"].execute("SELECT sample_id FROM samples WHERE name = 'heldout-repos'").fetchone()[0]
        env["con"].execute("INSERT INTO sample_items (sample_id, position, item_id) VALUES (?, 1, 'o/r')", (rid,))
    with pytest.raises(imp.WorkbookError, match="isn't frozen"):
        imp.do_import(env["con"], [], "brendan")
