"""Tests for scripts/sampling.py and the draw_sample / get_sample MCP tools (#12).
Throwaway labels.db over the gitskills sample; languages are set synthetically.
    .venv/Scripts/python -m pytest tests
"""
import sys
from collections import Counter
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import load_dataset  # noqa: E402
import sampling  # noqa: E402
from db import connect, init_schema  # noqa: E402
from pipeline_server import build_server  # noqa: E402


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "labels.db"
    con = connect(labels_db=db)
    init_schema(con)
    with con:
        load_dataset.build_skills(con)
        shas = [r[0] for r in con.execute("SELECT file_sha FROM skills ORDER BY file_sha")]
        # every 10th skill is "German", the rest "English"
        con.executemany("INSERT INTO skill_language (file_sha, language, confidence, detector) VALUES (?, ?, 1, 'test')",
                        [(s, "de" if i % 10 == 0 else "en") for i, s in enumerate(shas)])
    german = {s for i, s in enumerate(shas) if i % 10 == 0}
    yield dict(con=con, db=db, german=german)
    con.close()


def keys(res, field):
    return [it[field] for it in res["items"]]


# --- allocation ----------------------------------------------------------------

@pytest.mark.parametrize("sizes, n, want", [
    ({"a": 10, "b": 10, "c": 10, "d": 10}, 10, {"a": 3, "b": 3, "c": 2, "d": 2}),
    ({"a": 70, "b": 20, "c": 10}, 10, {"a": 7, "b": 2, "c": 1}),
    ({"a": 1, "b": 1, "c": 98}, 3, {"a": 0, "b": 0, "c": 3}),
])
def test_allocate(sizes, n, want):
    got = sampling._allocate(sizes, n)
    assert sum(got.values()) == n and got == want


# --- drawing -------------------------------------------------------------------

def test_dry_run_stores_nothing(env):
    res = sampling.draw(env["con"], "t1", 40, seed=7, dry_run=True)
    assert res["stored"] is False and len(res["items"]) == 40
    assert env["con"].execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 0


def test_draw_stores_and_get_returns_it(env):
    res = sampling.draw(env["con"], "t1", 40, seed=7)
    got = sampling.get(env["con"], "t1")
    assert res["stored"] and got["total_items"] == 40
    assert [it["id"] for it in got["items"]] == keys(res, "file_sha")
    assert [it["position"] for it in got["items"]] == list(range(1, 41))
    assert "seed 7" in got["method"] and got["seed"] == 7


def test_same_seed_same_draw_different_seed_differs(env):
    a = keys(sampling.draw(env["con"], "a", 30, seed=1, dry_run=True), "file_sha")
    b = keys(sampling.draw(env["con"], "a", 30, seed=1, dry_run=True), "file_sha")
    c = keys(sampling.draw(env["con"], "a", 30, seed=2, dry_run=True), "file_sha")
    assert a == b and a != c


def test_length_strata_are_balanced(env):
    res = sampling.draw(env["con"], "t", 40, seed=3, dry_run=True)
    assert Counter(keys(res, "stratum")) == {"length_q1": 10, "length_q2": 10, "length_q3": 10, "length_q4": 10}
    assert all(v["drawn"] == 10 for v in res["strata"].values())


def test_location_strata_are_proportional(env):
    res = sampling.draw(env["con"], "t", 200, seed=3, stratify_by="location", dry_run=True)
    pools = {k: v["pool"] for k, v in res["strata"].items()}
    drawn = Counter(keys(res, "stratum"))
    assert drawn == sampling._allocate(pools, 200)
    assert set(drawn) <= {"location_canonical", "location_skills-dir", "location_other"}


def test_one_per_name_and_repo(env):
    res = sampling.draw(env["con"], "t", 300, seed=5, dry_run=True)
    names = [n.strip().lower() for n in keys(res, "name")]
    repos = keys(res, "repo_full_name")
    assert len(set(names)) == len(names) and len(set(repos)) == len(repos)


def test_filters_respected(env):
    res = sampling.draw(env["con"], "t", 300, seed=5, min_chars=1000, max_chars=5000, dry_run=True)
    assert all(1000 <= it["body_chars"] <= 5000 for it in res["items"])
    assert not set(keys(res, "file_sha")) & env["german"]           # English only by default


def test_english_only_can_be_turned_off(env):
    res = sampling.draw(env["con"], "t", 2000, seed=5, english_only=False, dry_run=True)
    assert set(keys(res, "file_sha")) & env["german"]


def test_missing_language_is_refused(env):
    with env["con"]:
        env["con"].execute("DELETE FROM skill_language WHERE rowid IN (SELECT rowid FROM skill_language LIMIT 1)")
    with pytest.raises(sampling.SampleError, match="detect_languages"):
        sampling.draw(env["con"], "t", 10, seed=1, dry_run=True)


def test_samples_never_overlap(env):
    con = env["con"]
    first = sampling.draw(con, "first", 200, seed=1)
    second = sampling.draw(con, "second", 200, seed=1)
    for field in ("file_sha", "repo_full_name"):
        assert not set(keys(first, field)) & set(keys(second, field))
    assert not {n.strip().lower() for n in keys(first, "name")} & {n.strip().lower() for n in keys(second, "name")}


@pytest.mark.parametrize("kwargs, expect", [
    (dict(name="Round 1", n=5, seed=1), "lowercase slug"),
    (dict(name="t", n=0, seed=1), "between 1 and"),
    (dict(name="t", n=5, seed=1, stratify_by="stars"), "stratify_by"),
    (dict(name="t", n=5, seed=1, min_chars=900, max_chars=100), "min_chars <= max_chars"),
    (dict(name="t", n=500, seed=1, min_chars=200, max_chars=210), "fewer than n"),
])
def test_bad_arguments(env, kwargs, expect):
    with pytest.raises(sampling.SampleError, match=expect):
        sampling.draw(env["con"], dry_run=True, **kwargs)


def test_taken_name_is_refused(env):
    sampling.draw(env["con"], "t", 5, seed=1)
    with pytest.raises(sampling.SampleError, match="already exists"):
        sampling.draw(env["con"], "t", 5, seed=2)


# --- through the MCP server ----------------------------------------------------

def call(db, tool, args):
    async def go():
        async with Client(build_server(labels_db=db)) as client:
            return await client.call_tool(tool, args)
    return anyio.run(go)


def test_tools_end_to_end(env):
    r = call(env["db"], "draw_sample", {"name": "via-mcp", "n": 12, "seed": 9})
    assert not r.is_error and r.structured_content["stored"] is True
    g = call(env["db"], "get_sample", {"name": "via-mcp", "limit": 5, "offset": 10})
    assert g.structured_content["total_items"] == 12 and [i["position"] for i in g.structured_content["items"]] == [11, 12]
    err = call(env["db"], "draw_sample", {"name": "via-mcp", "n": 12, "seed": 9})
    assert err.is_error and "already exists" in err.content[0].text
    missing = call(env["db"], "get_sample", {"name": "nope"})
    assert missing.is_error and "existing samples" in missing.content[0].text


# --- repo samples for context labeling (#22) -----------------------------------------

def test_repo_sample_follows_the_skill_sample(env):
    con = env["con"]
    skills = sampling.draw(con, "t1", 20, seed=3)["items"]
    dry = sampling.repos_of(con, "t1-repos", "t1", dry_run=True)
    assert dry["stored"] is False and con.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 1
    res = sampling.repos_of(con, "t1-repos", "t1")
    assert res["stored"] and res["item_kind"] == "repo"
    assert [it["repo"] for it in res["items"]] == [it["repo_full_name"] for it in skills]  # one per repo, same order
    got = sampling.get(con, "t1-repos")
    assert got["item_kind"] == "repo" and got["total_items"] == 20
    assert got["items"][0]["stratum"] == f"skill:{skills[0]['file_sha']}"
    assert "repositories of the skills in sample 't1'" in got["method"]


def test_repo_sample_needs_a_new_name_and_a_skill_sample(env):
    con = env["con"]
    sampling.draw(con, "t1", 5, seed=3)
    sampling.repos_of(con, "t1-repos", "t1")
    with pytest.raises(sampling.SampleError, match="already exists"):
        sampling.repos_of(con, "t1-repos", "t1")
    with pytest.raises(sampling.SampleError, match="no sample named"):
        sampling.repos_of(con, "x-repos", "nope")
    with pytest.raises(sampling.SampleError, match="derive repo samples from skill samples"):
        sampling.repos_of(con, "t1-repos-repos", "t1-repos")


def test_repo_sample_keeps_one_item_per_repo(env):
    con = env["con"]
    sampling.draw(con, "t2", 30, seed=5, one_per_repo=False)
    res = sampling.repos_of(con, "t2-repos", "t2", dry_run=True)
    repos = [it["repo"] for it in res["items"]]
    assert len(repos) == len(set(repos)) <= 30
