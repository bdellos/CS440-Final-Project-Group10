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
    assert s["schema_version"] == 2
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
    assert r.structured_content["schema_version"] == 2
