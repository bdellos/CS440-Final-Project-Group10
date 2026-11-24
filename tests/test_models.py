"""Tests for config/models.json, scripts/models.py and the runs migration in scripts/db.py.
    .venv/Scripts/python -m pytest tests
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import models  # noqa: E402
from db import connect, init_schema, out_of_date  # noqa: E402


# --- config ----------------------------------------------------------------

def test_real_config_is_valid():
    cfg = models.load_config()
    assert set(cfg["agents"]) == {"sampler", "context-classifier", "open-coder", "codebook-consolidator",
                                  "labeler", "skeptic", "analyst"}
    assert models.run_settings("labeler", cfg) == cfg["agents"]["labeler"]
    assert models.run_settings("batch", cfg)["model"].startswith("claude-")


def test_unknown_agent():
    with pytest.raises(KeyError):
        models.run_settings("nobody")


@pytest.mark.parametrize("setting, expect", [
    ({"model": "haiku", "effort": "low"}, "full model ID"),
    ({"model": "claude-haiku-5-5", "effort": "fast"}, "effort must be one of"),
])
def test_invalid_config(tmp_path, setting, expect):
    cfg = {"agents": {"labeler": setting}, "batch": {"model": "claude-haiku-5-5", "effort": "low"}}
    p = tmp_path / "models.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    with pytest.raises(ValueError, match=expect):
        models.load_config(p)


# --- agent files vs config -------------------------------------------------

CFG = {"agents": {"labeler": {"model": "claude-haiku-5-5", "effort": "low"}},
       "batch": {"model": "claude-haiku-5-5", "effort": "low"}}


def agent(tmp_path, name="labeler", **fm):
    d = tmp_path / "agents"
    d.mkdir(exist_ok=True)
    head = "\n".join(f"{k}: {v}" for k, v in {"name": name, "description": "x", **fm}.items())
    (d / f"{name}.md").write_text(f"---\n{head}\n---\n\nPrompt.\n", encoding="utf-8")
    return d


def test_matching_agent(tmp_path):
    d = agent(tmp_path, model="claude-haiku-5-5", effort="low")
    assert models.check(CFG, d, environ={}) == ([], [])


@pytest.mark.parametrize("fm, expect", [
    ({"model": "haiku", "effort": "low"}, "alias that changes over time"),
    ({"model": "claude-opus-5-5", "effort": "low"}, "config says 'claude-haiku-5-5'"),
    ({"model": "claude-haiku-5-5"}, "missing `effort: low`"),
    ({"effort": "low"}, "missing `model: claude-haiku-5-5`"),
    ({"model": "claude-haiku-5-5", "effort": "high"}, "config says 'low'"),
])
def test_agent_mismatch(tmp_path, fm, expect):
    problems, _ = models.check(CFG, agent(tmp_path, **fm), environ={})
    assert any(expect in p for p in problems), problems


def test_agent_not_in_config(tmp_path):
    agent(tmp_path, model="claude-haiku-5-5", effort="low")
    d = agent(tmp_path, name="stray", model="claude-haiku-5-5", effort="low")
    problems, _ = models.check(CFG, d, environ={})
    assert any("no entry in config/models.json" in p for p in problems), problems


def test_missing_agent_file_is_only_a_note(tmp_path):
    problems, notes = models.check(CFG, tmp_path / "none", environ={})
    assert problems == [] and any("no agent file yet" in n for n in notes)


def test_env_override_is_a_problem(tmp_path):
    d = agent(tmp_path, model="claude-haiku-5-5", effort="low")
    problems, _ = models.check(CFG, d, environ={"CLAUDE_CODE_SUBAGENT_EFFORT": "max"})
    assert any("CLAUDE_CODE_SUBAGENT_EFFORT" in p for p in problems), problems


# --- runs migration ----------------------------------------------------------

OLD_RUNS = """CREATE TABLE runs (
    run_id       INTEGER PRIMARY KEY,
    sample_id    INTEGER NOT NULL REFERENCES samples(sample_id),
    taxonomy     TEXT NOT NULL CHECK (taxonomy IN ('purpose', 'context')),
    codebook_version_id INTEGER REFERENCES codebook_versions(codebook_version_id),
    rater_kind   TEXT NOT NULL CHECK (rater_kind IN ('agent', 'human')),
    rater        TEXT NOT NULL,
    model        TEXT,
    temperature  REAL,
    purpose      TEXT NOT NULL,
    started_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    finished_at  TEXT,
    notes        TEXT,
    CHECK (rater_kind = 'human' OR model IS NOT NULL)
) STRICT"""


def test_migration_rebuilds_runs_and_keeps_data(tmp_path):
    db = tmp_path / "labels.db"
    # An old database: runs without `effort`, with a run and an annotation pointing at it.
    raw = sqlite3.connect(db)
    raw.execute("CREATE TABLE samples (sample_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, "
                "item_kind TEXT NOT NULL, method TEXT NOT NULL, seed INTEGER, created_at TEXT) STRICT")
    raw.execute(OLD_RUNS)
    raw.execute("INSERT INTO samples (name, item_kind, method) VALUES ('s', 'skill', 'm')")
    raw.execute("INSERT INTO runs (sample_id, taxonomy, rater_kind, rater, model, purpose) "
                "VALUES (1, 'purpose', 'agent', 'labeler', 'claude-haiku-5-5', 'smoke')")
    raw.commit()
    raw.close()

    con = connect(labels_db=db)
    init_schema(con)
    with con:
        con.execute("INSERT INTO annotations (run_id, item_id) VALUES (1, 'x')")
    row = con.execute("SELECT rater, model, effort FROM runs WHERE run_id = 1").fetchone()
    assert tuple(row) == ("labeler", "claude-haiku-5-5", "unrecorded")  # old row kept, honestly marked
    assert con.execute("PRAGMA main.user_version").fetchone()[0] == 2
    with pytest.raises(sqlite3.IntegrityError):                          # new rule applies to new rows
        con.execute("INSERT INTO runs (sample_id, taxonomy, rater_kind, rater, model, purpose) "
                    "VALUES (1, 'purpose', 'agent', 'labeler', 'claude-haiku-5-5', 'smoke')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO runs (sample_id, taxonomy, rater_kind, rater, model, effort, purpose) "
                    "VALUES (1, 'purpose', 'agent', 'labeler', 'claude-haiku-5-5', 'fast', 'smoke')")
    con.execute("INSERT INTO runs (sample_id, taxonomy, rater_kind, rater, model, effort, purpose) "
                "VALUES (1, 'purpose', 'agent', 'labeler', 'claude-haiku-5-5', 'low', 'smoke')")
    views = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('view', 'trigger')")}
    assert {"label_rows", "proposals_review", "labels_in_codebook"} <= views
    init_schema(con)  # re-running is a no-op
    assert con.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
    assert not out_of_date(con, "runs")


def test_fresh_database_matches_schema(tmp_path):
    """Every table in a new database matches schema.sql, so migrations don't rebuild it again."""
    import re
    con = connect(labels_db=tmp_path / "labels.db")
    init_schema(con)
    tables = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", (ROOT / "scripts/schema.sql").read_text(encoding="utf-8"))
    assert tables and [t for t in tables if out_of_date(con, t)] == []
