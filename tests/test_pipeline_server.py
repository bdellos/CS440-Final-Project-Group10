"""Tests for the pipeline MCP server scaffold (scripts/pipeline_server.py).
    .venv/Scripts/python -m pytest tests
"""
import json
import sys
from pathlib import Path

import anyio
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from db import connect, init_schema  # noqa: E402
from pipeline_server import build_server  # noqa: E402


def call(server, tool, args=None):
    async def go():
        async with Client(server) as client:
            return await client.call_tool(tool, args or {})
    return anyio.run(go)


def text(result):
    return " ".join(getattr(b, "text", "") for b in result.content)


def fresh_db(tmp_path):
    db = tmp_path / "labels.db"
    con = connect(labels_db=db)
    init_schema(con)
    con.close()
    return db


def test_tools_are_listed_with_annotations(tmp_path):
    async def go():
        async with Client(build_server(labels_db=fresh_db(tmp_path))) as client:
            return {t.name: t for t in (await client.list_tools()).tools}
    tools = anyio.run(go)
    assert "pipeline_status" in tools
    assert tools["pipeline_status"].annotations.read_only_hint is True


def test_status_on_fresh_database(tmp_path):
    r = call(build_server(labels_db=fresh_db(tmp_path)), "pipeline_status")
    assert not r.is_error, text(r)
    s = r.structured_content
    assert s["schema_version"] == 3
    assert s["dataset"] is None and s["samples"] == [] and s["open_runs"] == []
    assert s["codebook_files_ok"] is True and s["model_config_problems"] == []


def test_outdated_schema_is_a_tool_error(tmp_path):
    db = fresh_db(tmp_path)
    con = connect(labels_db=db)
    con.execute("PRAGMA main.user_version = 1")
    con.commit()
    con.close()
    r = call(build_server(labels_db=db), "pipeline_status")
    assert r.is_error and "load_dataset.py" in text(r)


def test_missing_dataset_is_a_tool_error(tmp_path):
    r = call(build_server(labels_db=fresh_db(tmp_path), dataset_db=tmp_path / "missing.db"), "pipeline_status")
    assert r.is_error and "load_dataset.py" in text(r)


def test_runs_over_stdio_from_mcp_json():
    """Launch the server exactly as Claude Code does (.mcp.json, stdio) and call a tool.
    Any stray print to stdout would corrupt the protocol and fail this test."""
    cfg = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["pipeline"]
    params = StdioServerParameters(command=cfg["command"], args=cfg["args"], cwd=str(ROOT))

    async def go():
        async with Client(params) as client:
            return await client.call_tool("pipeline_status", {})
    r = anyio.run(go)
    assert not r.is_error, text(r)
    assert r.structured_content["schema_version"] == 3


# --- get_skill (#13) ---------------------------------------------------------

import csv  # noqa: E402

import pytest  # noqa: E402

import load_dataset  # noqa: E402
from language import detect  # noqa: E402
from validate_label import quote_found  # noqa: E402

ROUND0 = {r["file_sha"] for r in csv.DictReader(open(ROOT / "samples/round0.csv", encoding="utf-8"))}


@pytest.fixture(scope="module")
def skill_env(tmp_path_factory):
    """A labels.db with the skills table built, and one non-Round-0 skill with bundled files."""
    db = tmp_path_factory.mktemp("skills") / "labels.db"
    con = connect(labels_db=db)
    init_schema(con)
    with con:
        load_dataset.build_skills(con)
    row = next(r for r in con.execute(
        """SELECT file_sha, content, sibling_count, repo_full_name FROM gs.artifacts
           WHERE dedup_primary = 1 AND sibling_count BETWEEN 2 AND 8 AND composition_truncated = 0
             AND length(content) BETWEEN 3000 AND 50000 ORDER BY file_sha""") if r[0] not in ROUND0)
    lang, conf = detect(row["content"])
    with con:
        con.execute("INSERT INTO skill_language (file_sha, language, confidence, detector) VALUES (?, ?, ?, 'test')",
                    (row["file_sha"], lang, conf))
    con.close()
    return dict(db=db, sha=row["file_sha"], content=row["content"], siblings=row["sibling_count"],
                repo=row["repo_full_name"], language=lang)


def test_get_skill_returns_text_and_metadata(skill_env):
    r = call(build_server(labels_db=skill_env["db"]), "get_skill", {"file_sha": skill_env["sha"]})
    assert not r.is_error, text(r)
    s = r.structured_content
    assert s["content"] == skill_env["content"] and s["truncated"] is False
    assert s["content_chars"] == len(skill_env["content"])
    assert s["repo"]["full_name"] == skill_env["repo"] and "stars" in s["repo"]
    assert s["github_url"].startswith(f"https://github.com/{skill_env['repo']}/blob/HEAD/")
    assert s["language"] == skill_env["language"]
    assert s["copies"] >= 1 and s["repos_with_copy"] >= 1
    assert s["bundled_files_listed"] == s["bundled_files_total"] == skill_env["siblings"]
    assert s["bundled_files_incomplete"] is False
    assert "not instructions" in s["content_note"]


def test_get_skill_truncates_only_at_the_server_cap(skill_env, monkeypatch):
    import pipeline_server
    monkeypatch.setattr(pipeline_server, "SKILL_TEXT_CAP", 1000)
    s = call(build_server(labels_db=skill_env["db"]), "get_skill", {"file_sha": skill_env["sha"]}).structured_content
    assert len(s["content"]) == 1000 and s["truncated"] is True and s["content_chars"] == len(skill_env["content"])


def test_agents_cannot_cap_the_skill_text(skill_env):
    """Labelers passed small max_chars values to save tokens and labeled from partial text (run 24)."""
    r = call(build_server(labels_db=skill_env["db"]), "get_skill", {"file_sha": skill_env["sha"], "max_chars": 5000})
    if not r.is_error:  # an unknown argument may be ignored rather than refused; either way, full text
        s = r.structured_content
        assert s["truncated"] is False and len(s["content"]) == len(skill_env["content"])


def test_get_skill_text_supports_verbatim_quotes(skill_env):
    """What an agent copies out of get_skill must pass the validator's quote check."""
    s = call(build_server(labels_db=skill_env["db"]), "get_skill", {"file_sha": skill_env["sha"]}).structured_content
    line = next(ln.strip() for ln in s["content"].splitlines() if len(ln.strip()) > 30)
    assert quote_found(line, skill_env["content"])


@pytest.mark.parametrize("args, expect", [
    ({"file_sha": "nope"}, "40 lowercase hex"),
    ({"file_sha": "0" * 40}, "no skill with file_sha"),
])
def test_get_skill_errors(skill_env, args, expect):
    r = call(build_server(labels_db=skill_env["db"]), "get_skill", args)
    assert r.is_error and expect in text(r), text(r)


def test_get_skill_warns_about_prompt_injection(skill_env):
    async def go():
        async with Client(build_server(labels_db=skill_env["db"])) as client:
            return {t.name: t for t in (await client.list_tools()).tools}
    tool = anyio.run(go)["get_skill"]
    assert "not instructions" in tool.description and tool.annotations.read_only_hint is True
