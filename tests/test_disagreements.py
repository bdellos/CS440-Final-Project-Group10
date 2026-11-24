"""Tests for scripts/disagreements.py and the get_disagreements MCP tool (#15).
    .venv/Scripts/python -m pytest tests
"""
import sys
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import disagreements  # noqa: E402
import labeling  # noqa: E402
import load_dataset  # noqa: E402
import models  # noqa: E402
import runs  # noqa: E402
import sampling  # noqa: E402
from db import connect, init_schema  # noqa: E402
from pipeline_server import build_server  # noqa: E402


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
        for v in (1, 2):
            con.execute("INSERT INTO codebook_versions (taxonomy, version, file_path, git_commit) VALUES "
                        "('purpose', ?, 'x', 'abc')", (v,))
            con.executemany("INSERT INTO categories VALUES (?, ?, ?, 'd')",
                            [(v, "cat-a", "A"), (v, "cat-b", "B"), (v, "cat-c", "C")])
    sampling.draw(con, "s1", 5, seed=4, min_chars=1500, max_chars=6000)
    sampling.draw(con, "s2", 2, seed=4, min_chars=1500, max_chars=6000)
    items = []
    for (sha,) in con.execute("SELECT item_id FROM sample_items i JOIN samples s USING (sample_id) "
                              "WHERE s.name = 's1' ORDER BY position").fetchall():
        text = con.execute("SELECT content FROM gs.artifacts WHERE file_sha = ? AND dedup_primary = 1", (sha,)).fetchone()[0]
        items.append((sha, first_line(text)))
    a = runs.start_run(con, "s1", "purpose", "labeler", "round", 1)["run_id"]
    b = runs.start_run(con, "s1", "purpose", "skeptic", "round", 1)["run_id"]

    def put(run, i, cats=(), proposal=False, codebook=1, proposal_name="Something new"):
        sha, q = items[i]
        ev = [{"quote": q, "quote_en": q}]
        labeling.store_label(con, {
            "schema_version": 1, "run_id": run, "item_kind": "skill", "item_id": sha, "taxonomy": "purpose",
            "codebook_version": codebook, "skill_language": "en",
            "labels": [{"category": c, "evidence": ev} for c in cats],
            "proposals": [{"name": proposal_name, "definition": "A category the codebook lacks.",
                           "justification": "None of the existing categories fits this.", "evidence": ev}]
            if proposal else []})

    put(a, 0, ["cat-a"]);          put(b, 0, ["cat-a"])            # agree
    put(a, 1, ["cat-a"]);          put(b, 1, proposal=True)        # disjoint (PROPOSED_NEW vs cat-a)
    put(a, 2, ["cat-a", "cat-b"]); put(b, 2, ["cat-a"])            # partial
    put(a, 3, ["cat-c"])                                            # missing in b
    # item 4: labeled by neither
    yield dict(con=con, db=db, a=a, b=b, items=items, put=put)
    con.close()


def test_summary_counts(env):
    res = disagreements.compare(env["con"], env["a"], env["b"])
    assert res["summary"] == {"agree": 1, "partial": 1, "disjoint": 1, "missing": 1,
                              "items_compared": 3, "exact_agreement": round(1 / 3, 4)}
    assert (res["run_a"]["rater"], res["run_b"]["rater"]) == ("labeler", "skeptic")


def test_disagreements_listed_in_sample_order_with_evidence(env):
    res = disagreements.compare(env["con"], env["a"], env["b"])
    assert [(r["kind"], r["position"]) for r in res["items"]] == [("disjoint", 2), ("partial", 3), ("missing", 4)]
    disjoint, partial, missing = res["items"]
    assert disjoint["labels_a"] == ["cat-a"] and disjoint["labels_b"] == ["PROPOSED_NEW"]
    assert disjoint["b"]["proposals"] == ["Something new"] and "PROPOSED_NEW" in disjoint["b"]["evidence"]
    assert (partial["both"], partial["only_a"], partial["only_b"]) == (["cat-a"], ["cat-b"], [])
    assert partial["a"]["evidence"]["cat-b"] == [env["items"][2][1]]
    assert missing["labels_b"] == [] and "a" in missing and "b" not in missing
    assert all(r["name"] for r in res["items"])


def test_two_proposals_never_agree(env):
    """Both raters proposing something is not agreement: proposals are free-form."""
    con, put = env["con"], env["put"]
    a = runs.start_run(con, "s1", "purpose", "labeler", "round", 2)["run_id"]
    b = runs.start_run(con, "s1", "purpose", "skeptic", "round", 2)["run_id"]
    put(a, 0, proposal=True, codebook=2, proposal_name="Release notes")
    put(b, 0, proposal=True, codebook=2, proposal_name="Data cleaning")
    put(a, 1, ["cat-a"], proposal=True, codebook=2)
    put(b, 1, ["cat-a"], proposal=True, codebook=2)               # same name, still not 'agree'
    res = disagreements.compare(con, a, b, include_agreements=True)
    first, second = res["items"]
    assert (first["kind"], first["both"], first["only_a"], first["only_b"]) == \
        ("disjoint", [], ["PROPOSED_NEW"], ["PROPOSED_NEW"])
    assert (first["a"]["proposals"], first["b"]["proposals"]) == (["Release notes"], ["Data cleaning"])
    assert (second["kind"], second["both"]) == ("partial", ["cat-a"])
    assert res["summary"]["agree"] == 0 and res["summary"]["exact_agreement"] == 0


def test_include_agreements_and_paging(env):
    res = disagreements.compare(env["con"], env["a"], env["b"], include_agreements=True, offset=1, limit=2)
    assert res["total_listed"] == 4 and [r["position"] for r in res["items"]] == [2, 3]


def test_order_of_runs_is_symmetric(env):
    ab = disagreements.compare(env["con"], env["a"], env["b"])["summary"]
    ba = disagreements.compare(env["con"], env["b"], env["a"])["summary"]
    assert ab == ba


@pytest.mark.parametrize("make, expect", [
    (lambda con: runs.start_run(con, "s2", "purpose", "skeptic", "round", 1)["run_id"], "is on sample"),
    (lambda con: runs.start_run(con, "s1", "purpose", "skeptic", "round", 2)["run_id"], "only comparable within"),
    (lambda con: runs.start_run(con, "s1", "purpose", "open-coder", "round0")["run_id"], "free-form codes"),
])
def test_incomparable_runs(env, make, expect):
    other = make(env["con"])
    with pytest.raises(disagreements.CompareError, match=expect):
        disagreements.compare(env["con"], env["a"], other)


def test_same_or_missing_run(env):
    with pytest.raises(disagreements.CompareError, match="two different"):
        disagreements.compare(env["con"], env["a"], env["a"])
    with pytest.raises(disagreements.CompareError, match="does not exist"):
        disagreements.compare(env["con"], env["a"], 999)


def test_tool_end_to_end(env):
    async def go():
        async with Client(build_server(labels_db=env["db"])) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            ok = await client.call_tool("get_disagreements", {"run_a": env["a"], "run_b": env["b"]})
            bad = await client.call_tool("get_disagreements", {"run_a": env["a"], "run_b": env["a"]})
            return tools, ok, bad
    tools, ok, bad = anyio.run(go)
    assert tools["get_disagreements"].annotations.read_only_hint is True
    assert "never see another rater's labels" in " ".join(tools["get_disagreements"].description.split())
    assert not ok.is_error and ok.structured_content["summary"]["disjoint"] == 1
    assert bad.is_error and "two different" in bad.content[0].text
