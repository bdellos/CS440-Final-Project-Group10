"""Tests for analysis/kappa.py (#47).
    .venv/Scripts/python -m pytest tests/test_kappa.py
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT / "scripts"))

import kappa  # noqa: E402
from db import connect, init_schema  # noqa: E402


def test_cohen_kappa_textbook_values():
    assert kappa.cohen_kappa([1, 1, 0, 0], [1, 0, 0, 0]) == pytest.approx(0.5)
    assert kappa.cohen_kappa(list("aabbcc"), list("aabbcc")) == 1
    assert kappa.cohen_kappa(list("ab"), list("ba")) == pytest.approx(-1)
    assert kappa.cohen_kappa(list("aaa"), list("aaa")) is None          # one value everywhere: undefined
    with pytest.raises(ValueError):
        kappa.cohen_kappa([1], [1, 2])


def test_label_sets_are_one_value_and_only_shared_items_count():
    x = {"i1": frozenset({"a"}), "i2": frozenset({"a", "b"}), "i3": frozenset({"b"}), "only-x": frozenset({"a"})}
    y = {"i1": frozenset({"a"}), "i2": frozenset({"a"}), "i3": frozenset({"b"})}
    c = kappa.compare(x, y)
    assert c["n"] == 3 and c["exact"] == pytest.approx(2 / 3) and c["multi"] == 1
    assert c["uses"] == {"a": (2, 2), "b": (2, 1)}
    assert c["per_category"]["a"] == 1


@pytest.fixture
def con(tmp_path):
    c = connect(labels_db=tmp_path / "labels.db")
    init_schema(c)
    with c:
        c.execute("INSERT INTO codebook_versions (taxonomy, version, file_path, git_commit, frozen) "
                  "VALUES ('purpose', 1, 'codebook/purpose/v01.md', 'x', 0)")
        c.execute("INSERT INTO codebook_versions (taxonomy, version, file_path, git_commit) "
                  "VALUES ('purpose', 2, 'codebook/purpose/v02.md', 'y')")
        c.execute("INSERT INTO categories VALUES (2, 'a', 'A', 'd')")
        c.execute("UPDATE codebook_versions SET frozen = 1 WHERE version = 2")
        c.execute("INSERT INTO samples (name, item_kind, method) VALUES ('heldout', 'skill', 'test')")
        for rid, rater, cv, done in [(1, "labeler", 2, 1), (2, "labeler", 2, 1), (3, "brendan", 2, 1),
                                     (4, "ryan", 2, 0), (5, "skeptic", 1, 1)]:
            c.execute("INSERT INTO runs (run_id, sample_id, taxonomy, codebook_version_id, rater_kind, rater, purpose, "
                      "finished_at) VALUES (?, 1, 'purpose', ?, 'human', ?, 'heldout', ?)",
                      (rid, cv, rater, "2026-11-25" if done else None))
    return c


def test_heldout_runs_take_the_latest_finished_run_on_the_frozen_codebook(con):
    assert kappa.heldout_runs(con, "purpose") == {"brendan": 3, "labeler": 2}   # ryan open, skeptic on unfrozen v01
    assert kappa.heldout_runs(con, "context") == {}
