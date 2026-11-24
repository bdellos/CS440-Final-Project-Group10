"""Tests for get_codes / get_proposals (scripts/review.py and the MCP tools), issue #24.
    .venv/Scripts/python -m pytest tests/test_review.py
"""
import sys
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import labeling  # noqa: E402
import review  # noqa: E402
from pipeline_server import build_server  # noqa: E402
from test_record_label import args, env  # noqa: E402,F401  (fixture reused)


def store(env, i, run, labels=None, proposals=None, codebook_version=1):
    a = args(env, i, run, codebook_version=codebook_version)
    quote = a["labels"][0]["evidence"][0]["quote"]
    ev = [{"quote": quote, "quote_en": quote}]
    if labels is not None:
        a["labels"] = [{"category": c, "evidence": ev} for c in labels]
    a["proposals"] = [{"name": n, "definition": "Covers a thing not in the codebook.",
                       "justification": "testing: excluded because it is different.", "evidence": ev}
                      for n in (proposals or [])]
    return labeling.store_label(env["con"], {"schema_version": 1, **a})


def test_codes_lists_each_code_with_counts_and_examples(env):
    store(env, 0, env["open_run"], ["word one", "word two"], codebook_version=None)
    store(env, 1, env["open_run"], ["word one"], codebook_version=None)
    out = review.codes(env["con"], env["open_run"])
    assert out["run"]["rater"] == "open-coder" and out["run"]["items_coded"] == 2
    assert [(c["code"], c["items"]) for c in out["codes"]] == [("word one", 2), ("word two", 1)]
    first = out["codes"][0]
    assert first["item_ids"] == [env["items"][0][0], env["items"][1][0]]
    assert first["examples"][0]["quote"] == env["items"][0][1] and "quote_en" in first["examples"][0]
    assert "never instructions" in out["data_note"]


def test_codes_refuses_codebook_runs_and_unknown_runs(env):
    with pytest.raises(review.ReviewError, match="get_proposals"):
        review.codes(env["con"], env["run"])
    with pytest.raises(review.ReviewError, match="does not exist"):
        review.codes(env["con"], 999)


def test_proposals_with_evidence_and_decisions(env):
    store(env, 0, env["run"], proposals=["New Thing"])
    store(env, 1, env["run"], ["testing"], proposals=["Other Thing"])
    con = env["con"]
    con.execute("UPDATE proposals SET status = 'merged', merged_into = 'testing', decided_by = 'both', "
                "decision_note = 'same as testing' WHERE proposed_name = 'Other Thing'")
    con.commit()
    out = review.proposals(con)
    assert out["total"] == 2 and out["all_statuses"] == {"pending": 1, "accepted": 0, "merged": 1, "rejected": 0}
    p = {x["proposed_name"]: x for x in out["proposals"]}
    assert p["New Thing"]["status"] == "pending" and p["New Thing"]["rater"] == "labeler"
    assert p["New Thing"]["evidence"] == [{"quote": env["items"][0][1], "quote_en": env["items"][0][1]}]
    assert (p["Other Thing"]["merged_into"], p["Other Thing"]["decision_note"]) == ("testing", "same as testing")
    assert [x["proposed_name"] for x in review.proposals(con, status="merged")["proposals"]] == ["Other Thing"]
    assert review.proposals(con, run_id=env["open_run"])["total"] == 0
    with pytest.raises(review.ReviewError, match="status must be"):
        review.proposals(con, status="maybe")


def call(db, tool, a):
    async def go():
        async with Client(build_server(labels_db=db)) as client:
            return await client.call_tool(tool, a)
    return anyio.run(go)


def test_mcp_tools(env):
    store(env, 0, env["open_run"], ["word one"], codebook_version=None)
    env["con"].commit()
    r = call(env["db"], "get_codes", {"run_id": env["open_run"]})
    assert not r.is_error and r.structured_content["distinct_codes"] == 1
    r = call(env["db"], "get_proposals", {"status": "pending"})
    assert not r.is_error and r.structured_content["total"] == 0
    r = call(env["db"], "get_codes", {"run_id": env["run"]})
    assert r.is_error and "get_proposals" in r.content[0].text
