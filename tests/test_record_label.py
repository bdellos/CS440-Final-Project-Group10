"""Tests for scripts/labeling.py and the record_label MCP tool (#14).
Throwaway labels.db over the gitskills sample; quotes are taken from the real skill text.
    .venv/Scripts/python -m pytest tests
"""
import sys
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import labeling  # noqa: E402
import load_dataset  # noqa: E402
import models  # noqa: E402
import runs  # noqa: E402
import sampling  # noqa: E402
from db import connect, init_schema  # noqa: E402
from pipeline_server import build_server  # noqa: E402

TABLES = ("annotations", "annotation_labels", "evidence", "proposals")


def first_line(text):
    body = text.split("---", 2)[-1] if text.lstrip().startswith("---") else text
    return next(s for s in (ln.strip().lstrip("#>-* ").strip() for ln in body.splitlines())
                if len(s) > 30 and "`" not in s and "|" not in s)


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
        con.executemany("INSERT INTO categories VALUES (1, ?, ?, 'd')", [("testing", "Testing"), ("deployment", "Deployment")])
    sampling.draw(con, "s1", 4, seed=2, min_chars=1500, max_chars=6000)
    items = []
    for (sha,) in con.execute("SELECT item_id FROM sample_items ORDER BY position").fetchall():
        text = con.execute("SELECT content FROM gs.artifacts WHERE file_sha = ? AND dedup_primary = 1", (sha,)).fetchone()[0]
        items.append((sha, first_line(text)))
    run = runs.start_run(con, "s1", "purpose", "labeler", "round", 1)["run_id"]
    open_run = runs.start_run(con, "s1", "purpose", "open-coder", "round0")["run_id"]
    human = runs.start_run(con, "s1", "purpose", "brendan", "round", 1, human=True)["run_id"]
    yield dict(con=con, db=db, items=items, run=run, open_run=open_run, human=human)
    con.close()


def args(env, i=0, run=None, **over):
    sha, quote = env["items"][i]
    a = {"run_id": run or env["run"], "item_kind": "skill", "item_id": sha, "taxonomy": "purpose",
         "codebook_version": 1, "skill_language": "en",
         "labels": [{"category": "testing", "evidence": [{"quote": quote, "quote_en": quote}]}]}
    a.update(over)
    return a


def call(env, a):
    async def go():
        async with Client(build_server(labels_db=env["db"])) as client:
            return await client.call_tool("record_label", a)
    r = anyio.run(go)
    return r, (r.structured_content if not r.is_error else r.content[0].text)


def counts(con):
    return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


# --- storing --------------------------------------------------------------------

def test_stores_a_label(env):
    r, out = call(env, args(env))
    assert not r.is_error, out
    assert out["stored"] and out["labels"] == ["testing"] and out["proposal_ids"] == []
    assert out["run_progress"] == {"items": 4, "labeled": 1, "remaining": 3}
    con, a = env["con"], args(env)
    assert [tuple(x) for x in con.execute("SELECT category_key FROM annotation_labels")] == [("testing",)]
    ev = con.execute("SELECT category_key, quote, quote_en FROM evidence").fetchone()
    assert tuple(ev) == ("testing", a["labels"][0]["evidence"][0]["quote"], a["labels"][0]["evidence"][0]["quote"])
    row = con.execute("SELECT run_id, item_id, skill_language FROM annotations").fetchone()
    assert tuple(row) == (env["run"], a["item_id"], "en")


def test_multi_label_with_several_quotes(env):
    sha, quote = env["items"][1]
    a = args(env, 1, labels=[
        {"category": "testing", "evidence": [{"quote": quote, "quote_en": quote}, {"quote": quote[:20], "quote_en": quote[:20]}]},
        {"category": "deployment", "evidence": [{"quote": quote, "quote_en": quote}]}])
    r, out = call(env, a)
    assert not r.is_error, out
    assert counts(env["con"]) == {"annotations": 1, "annotation_labels": 2, "evidence": 3, "proposals": 0}


def test_proposal_only(env):
    sha, quote = env["items"][2]
    a = args(env, 2, labels=[], proposals=[{
        "name": "Release notes", "definition": "Skills that write release notes from commits.",
        "justification": "Neither testing nor deployment covers writing prose about a release.",
        "evidence": [{"quote": quote, "quote_en": quote}]}])
    r, out = call(env, a)
    assert not r.is_error, out
    pid = out["proposal_ids"][0]
    con = env["con"]
    assert [x[0] for x in con.execute("SELECT category_key FROM annotation_labels")] == ["PROPOSED_NEW"]
    assert con.execute("SELECT category_key FROM evidence").fetchone()[0] == f"PROPOSED_NEW:{pid}"
    review = con.execute("SELECT status, proposed_name, needs_extra_review FROM proposals_review").fetchone()
    assert tuple(review) == ("pending", "Release notes", 0)


def test_open_coding_stores_free_form_codes(env):
    a = args(env, run=env["open_run"], codebook_version=None)
    a["labels"][0]["category"] = "Runs the project's unit tests before a commit"
    r, out = call(env, a)
    assert not r.is_error, out


def test_full_run_can_then_finish(env):
    for i in range(4):
        r, out = call(env, args(env, i))
        assert not r.is_error, out
    assert out["run_progress"]["remaining"] == 0
    assert runs.finish_run(env["con"], env["run"])["unlabeled"] == 0


# --- rejecting ------------------------------------------------------------------

def test_rejection_lists_every_problem_and_writes_nothing(env):
    a = args(env, codebook_version=2, skill_language="de")
    a["labels"][0]["category"] = "made-up"
    a["labels"][0]["evidence"][0] = {"quote": "Not in the skill at all, anywhere.", "quote_en": "something else"}
    r, out = call(env, a)
    assert r.is_error and "label rejected (4 problems)" in out
    for problem in ("uses 1", "detection says 'en'", "quote not found"):
        assert problem in out, out
    assert counts(env["con"]) == dict.fromkeys(TABLES, 0)


def test_same_item_twice(env):
    call(env, args(env))
    r, out = call(env, args(env))
    assert r.is_error and "already labeled" in out
    assert counts(env["con"])["annotations"] == 1


def test_agents_cannot_write_into_human_runs(env):
    r, out = call(env, args(env, run=env["human"]))
    assert r.is_error and "human run" in out
    assert counts(env["con"])["annotations"] == 0
    stored = labeling.store_label(env["con"], {"schema_version": 1, **args(env, run=env["human"]), "proposals": []},
                                  allow_human=True)      # a person's import script may
    assert stored["stored"]


def test_shape_errors_come_back_as_tool_errors(env):
    r, out = call(env, args(env, labels=[{"category": "testing", "evidence": []}]))
    assert r.is_error and "should be non-empty" in out


def test_crash_mid_write_leaves_nothing(env, monkeypatch):
    real = labeling._write

    def boom(con, record, *rest):
        real(con, record, *rest)            # rows are inserted...
        raise RuntimeError("disk on fire")  # ...then something fails before commit
    monkeypatch.setattr(labeling, "_write", boom)
    record = {"schema_version": 1, **args(env), "proposals": []}
    with pytest.raises(RuntimeError):
        labeling.store_label(env["con"], record)
    assert counts(env["con"]) == dict.fromkeys(TABLES, 0)
    monkeypatch.setattr(labeling, "_write", real)
    assert labeling.store_label(env["con"], record)["stored"]   # and the connection still works
