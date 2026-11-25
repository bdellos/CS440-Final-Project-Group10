"""Tests for scripts/runs.py and the start_run / finish_run MCP tools (#58).
    .venv/Scripts/python -m pytest tests
"""
import os
import subprocess
import sys
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import load_dataset  # noqa: E402
import models  # noqa: E402
import runs  # noqa: E402
import sampling  # noqa: E402
from db import connect, init_schema  # noqa: E402
from pipeline_server import build_server  # noqa: E402
from validate_label import validate_label  # noqa: E402


@pytest.fixture
def env(tmp_path, monkeypatch):
    for var in models.OVERRIDE_VARS:
        monkeypatch.delenv(var, raising=False)
    db = tmp_path / "labels.db"
    con = connect(labels_db=db)
    init_schema(con)
    with con:
        load_dataset.build_skills(con)
        con.execute("INSERT INTO skill_language (file_sha, language, confidence, detector) "
                    "SELECT file_sha, 'en', 1, 'test' FROM skills")
        con.execute("INSERT INTO codebook_versions (taxonomy, version, file_path, git_commit) "
                    "VALUES ('purpose', 1, 'codebook/purpose/v01.md', 'abc')")
        con.execute("INSERT INTO categories VALUES (1, 'testing', 'Testing', 'Writes tests')")
        con.execute("INSERT INTO samples (name, item_kind, method) VALUES ('repos', 'repo', 'test')")
    sampling.draw(con, "s1", 3, seed=1)
    yield dict(con=con, db=db)
    con.close()


def call(db, tool, args):
    async def go():
        async with Client(build_server(labels_db=db)) as client:
            return await client.call_tool(tool, args)
    r = anyio.run(go)
    return r, (r.structured_content if not r.is_error else r.content[0].text)


def label(con, run_id, sha):
    con.execute("INSERT OR IGNORE INTO prompt_versions (prompt_hash, rater, files) VALUES ('sha256:test', 'test', '[]')")  # agent labels need provenance (#35)
    con.execute("INSERT INTO annotations (run_id, item_id, prompt_hash) VALUES (?, ?, 'sha256:test')", (run_id, sha))
    con.commit()


# --- start_run --------------------------------------------------------------------

def test_agent_run_takes_model_and_effort_from_config(env):
    r, out = call(env["db"], "start_run", {"sample": "s1", "taxonomy": "purpose", "rater": "labeler",
                                           "purpose": "round", "codebook_version": 1})
    assert not r.is_error, out
    want = models.run_settings("labeler")
    assert (out["model"], out["effort"], out["rater_kind"], out["items"]) == (want["model"], want["effort"], "agent", 3)
    row = env["con"].execute("SELECT model, effort, rater_kind FROM runs WHERE run_id = ?", (out["run_id"],)).fetchone()
    assert tuple(row) == (want["model"], want["effort"], "agent")


def test_mcp_cannot_create_human_runs(env):
    r, out = call(env["db"], "start_run", {"sample": "s1", "taxonomy": "purpose", "rater": "brendan",
                                           "purpose": "round", "codebook_version": 1})
    assert r.is_error and "scripts/runs.py" in out
    assert env["con"].execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_human_run_from_python(env):
    out = runs.start_run(env["con"], "s1", "purpose", "brendan", "round0", human=True)
    assert (out["rater_kind"], out["model"], out["effort"]) == ("human", None, None)


@pytest.mark.parametrize("rater", ["labeler", "Brendan", "brendan2", ""])
def test_human_rater_names(env, rater):
    with pytest.raises(runs.RunError, match="human rater"):
        runs.start_run(env["con"], "s1", "purpose", rater, "round0", human=True)


@pytest.mark.parametrize("args, expect", [
    (dict(purpose="round0", codebook_version=1), "Round 0 is open coding"),
    (dict(purpose="round", codebook_version=None), "Round 0 is open coding"),
    (dict(purpose="round", codebook_version=2), "not registered"),
    (dict(purpose="round", codebook_version=1, sample="nope"), "no sample named"),
    (dict(purpose="round", codebook_version=1, sample="repos"), "holds repos"),
    (dict(purpose="party", codebook_version=1), "purpose must be one of"),
    (dict(purpose="round", codebook_version=1, taxonomy="vibes"), "taxonomy must be one of"),
])
def test_start_run_refusals(env, args, expect):
    kwargs = dict(sample="s1", taxonomy="purpose", rater="labeler") | args
    with pytest.raises(runs.RunError, match=expect):
        runs.start_run(env["con"], **kwargs)


def test_one_open_run_per_rater_sample_codebook(env):
    first = runs.start_run(env["con"], "s1", "purpose", "labeler", "round", 1)
    with pytest.raises(runs.RunError, match=f"open run {first['run_id']}"):
        runs.start_run(env["con"], "s1", "purpose", "labeler", "round", 1)
    runs.start_run(env["con"], "s1", "purpose", "skeptic", "round", 1)          # another rater is fine
    runs.finish_run(env["con"], first["run_id"], allow_incomplete=True)
    runs.start_run(env["con"], "s1", "purpose", "labeler", "round", 1)          # after finishing, fine again


def test_effort_override_blocks_agent_runs(env, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_EFFORT", "max")
    r, out = call(env["db"], "start_run", {"sample": "s1", "taxonomy": "purpose", "rater": "labeler",
                                           "purpose": "round", "codebook_version": 1})
    assert r.is_error and "CLAUDE_CODE_SUBAGENT_EFFORT" in out


# --- finish_run ---------------------------------------------------------------------

def test_finish_refuses_incomplete_then_allows(env):
    con = env["con"]
    run = runs.start_run(con, "s1", "purpose", "labeler", "round", 1)
    items = [r[0] for r in con.execute("SELECT item_id FROM sample_items i JOIN samples s USING (sample_id) "
                                       "WHERE s.name = 's1' ORDER BY position")]
    label(con, run["run_id"], items[0])
    r, out = call(env["db"], "finish_run", {"run_id": run["run_id"]})
    assert r.is_error and "2 unlabeled" in out
    r, out = call(env["db"], "finish_run", {"run_id": run["run_id"], "allow_incomplete": True})
    assert not r.is_error and (out["labeled"], out["unlabeled"]) == (1, 2)
    assert out["unlabeled_first_50"] == items[1:]


def test_finish_complete_run_and_twice(env):
    con = env["con"]
    run = runs.start_run(con, "s1", "purpose", "labeler", "round", 1)
    for (sha,) in con.execute("SELECT item_id FROM sample_items i JOIN samples s USING (sample_id) "
                              "WHERE s.name = 's1'").fetchall():
        label(con, run["run_id"], sha)
    assert runs.finish_run(con, run["run_id"])["unlabeled"] == 0
    with pytest.raises(runs.RunError, match="already finished"):
        runs.finish_run(con, run["run_id"])
    with pytest.raises(runs.RunError, match="does not exist"):
        runs.finish_run(con, 999)


def test_finished_run_rejects_labels(env):
    con = env["con"]
    run = runs.start_run(con, "s1", "purpose", "labeler", "round", 1)
    runs.finish_run(con, run["run_id"], allow_incomplete=True)
    sha = con.execute("SELECT item_id FROM sample_items LIMIT 1").fetchone()[0]
    rec = {"schema_version": 1, "run_id": run["run_id"], "item_kind": "skill", "item_id": sha, "taxonomy": "purpose",
           "codebook_version": 1, "skill_language": "en", "proposals": [],
           "labels": [{"category": "testing", "evidence": [{"quote": "abc", "quote_en": "abc"}]}]}
    assert any("is finished" in e for e in validate_label(rec, con))


# --- command line (human runs) -----------------------------------------------------------

def test_cli_starts_and_finishes_a_human_run(env):
    e = dict(os.environ, LABELS_DB=str(env["db"]))
    py = str(ROOT / ".venv/Scripts/python.exe")
    out = subprocess.run([py, "scripts/runs.py", "start", "--sample", "s1", "--taxonomy", "purpose",
                          "--rater", "ryan", "--purpose", "round0"], cwd=ROOT, env=e, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "started human run" in out.stdout and "3 items" in out.stdout
    run_id = out.stdout.split("human run ")[1].split(":")[0]
    fin = subprocess.run([py, "scripts/runs.py", "finish", run_id], cwd=ROOT, env=e, capture_output=True, text=True)
    assert fin.returncode != 0 and "unlabeled" in fin.stderr


# --- note ---------------------------------------------------------------------------

def test_note_appends_and_keeps_the_original(env):
    r = runs.start_run(env["con"], "s1", "purpose", "brendan", "round0", notes="imported", human=True)
    runs.add_note(env["con"], r["run_id"], "Category list was  AI-assisted.", "brendan")
    notes = env["con"].execute("SELECT notes FROM runs WHERE run_id = ?", (r["run_id"],)).fetchone()[0]
    first, second = notes.split("\n")
    assert first == "imported" and second.endswith("by brendan] Category list was AI-assisted.")


@pytest.mark.parametrize("run_id, text, by, expect", [(99, "x", "brendan", "does not exist"),
                                                      (1, "  ", "brendan", "empty"),
                                                      (1, "x", "Brendan", "lowercase first name")])
def test_note_refusals(env, run_id, text, by, expect):
    runs.start_run(env["con"], "s1", "purpose", "brendan", "round0", human=True)
    with pytest.raises(runs.RunError, match=expect):
        runs.add_note(env["con"], run_id, text, by)


def test_agents_cannot_add_notes():
    sys.path.insert(0, str(ROOT / "scripts" / "hooks"))
    import labels_guard
    with pytest.raises(labels_guard.Blocked):
        labels_guard.decide({"tool_name": "Bash", "agent_type": "labeler",
                             "tool_input": {"command": ".venv/Scripts/python scripts/runs.py note 6 hi --by brendan"}})
