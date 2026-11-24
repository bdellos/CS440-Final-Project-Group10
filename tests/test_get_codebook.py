"""Tests for get_codebook (codebook.for_run and the MCP tool), issue #28.
Uses the committed codebook/purpose/v00.md (an empty template) as a real registered version.
    .venv/Scripts/python -m pytest tests/test_get_codebook.py
"""
import subprocess
import sys
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import codebook  # noqa: E402
import runs  # noqa: E402
from pipeline_server import build_server  # noqa: E402
from test_record_label import env  # noqa: E402,F401  (fixture reused)

V00 = "codebook/purpose/v00.md"


@pytest.fixture
def cb_run(env):
    con = env["con"]
    codebook.register(V00, con)
    run = runs.start_run(con, "s1", "purpose", "labeler", "round", 0)["run_id"]
    return env, run


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def test_returns_the_registered_text_and_run(cb_run):
    env, run = cb_run
    out = codebook.for_run(env["con"], run)
    commit = git("log", "--format=%H", "--", V00).split()[0]
    assert out["codebook"] == {"taxonomy": "purpose", "variant": "main", "version": 0, "file": V00,
                               "git_commit": commit, "frozen": False}
    assert out["text"] == git("show", f"{commit}:{V00}")
    assert out["run"]["sample"] == "s1" and out["run"]["item_kind"] == "skill"
    assert out["run"]["items"] == 4 and out["run"]["remaining"] == 4
    assert out["category_keys"] == [] and out["categories"] == []   # v00 is the empty template


def test_unreadable_commit_is_an_error(env):
    """env registers v01 with a fake commit 'abc', which git can't read."""
    with pytest.raises(codebook.NoCodebook, match="can't read codebook/purpose/v01.md at commit abc"):
        codebook.for_run(env["con"], env["run"])


def test_open_coding_and_unknown_runs_have_no_codebook(env):
    with pytest.raises(codebook.NoCodebook, match="open coding"):
        codebook.for_run(env["con"], env["open_run"])
    with pytest.raises(codebook.NoCodebook, match="does not exist"):
        codebook.for_run(env["con"], 9999)


def call(db, tool, args):
    async def go():
        async with Client(build_server(labels_db=db)) as client:
            return await client.call_tool(tool, args)
    return anyio.run(go)


def test_mcp_tool(cb_run):
    env, run = cb_run
    env["con"].commit()
    r = call(env["db"], "get_codebook", {"run_id": run})
    assert not r.is_error
    assert r.structured_content["codebook"]["version"] == 0
    r = call(env["db"], "get_codebook", {"run_id": env["open_run"]})
    assert r.is_error and "open coding" in r.content[0].text


def test_tool_is_read_only_and_listed(cb_run):
    env, _ = cb_run

    async def go():
        async with Client(build_server(labels_db=env["db"])) as client:
            return {t.name: t for t in (await client.list_tools()).tools}
    tools = anyio.run(go)
    assert tools["get_codebook"].annotations.read_only_hint is True
