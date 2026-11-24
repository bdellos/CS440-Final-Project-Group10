"""Tests for per-agent tool pinning (scripts/permissions.py, config/permissions.json).
    .venv/Scripts/python -m pytest tests/test_permissions.py
"""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import models  # noqa: E402
import permissions  # noqa: E402

CFG = permissions.load_config()
MODEL_AGENTS = models.load_config()["agents"]


def agent_file(d: Path, name: str, tools_block: str | None):
    fm = f"name: {name}\ndescription: test\nmodel: claude-haiku-5-5\neffort: low\n"
    if tools_block is not None:
        fm += tools_block + "\n"
    (d / f"{name}.md").write_text(f"---\n{fm}---\nbody\n", encoding="utf-8")


def run(tmp_path, cfg=None):
    return permissions.check(cfg or CFG, agents_dir=tmp_path, model_agents=MODEL_AGENTS)


def test_repo_config_passes():
    problems, _ = permissions.check()
    assert problems == []


def test_config_covers_exactly_the_model_agents():
    assert set(CFG["agents"]) == set(MODEL_AGENTS)


def test_no_agent_gets_main_session_tools_or_agent_spawning():
    for name, a in CFG["agents"].items():
        assert not {"mcp__pipeline__start_run", "mcp__pipeline__finish_run", "Agent"} & set(a["tools"]), name


def test_raters_cannot_see_other_raters_labels():
    """No get_disagreements, and no file tools: labels/dump.sql holds every stored label."""
    for name in ("labeler", "skeptic", "open-coder", "context-classifier"):
        tools = set(CFG["agents"][name]["tools"])
        assert "mcp__pipeline__get_disagreements" not in tools, name
        assert not tools & {"Read", "Glob", "Grep", "Bash", "Write", "Edit", "NotebookEdit"}, name


def test_missing_agent_files_are_notes(tmp_path):
    problems, notes = run(tmp_path)
    assert problems == [] and len(notes) == len(CFG["agents"])


@pytest.mark.parametrize("block", [
    "tools: {tools}",
    "tools: [{tools}]",
    "tools:\n{yaml}",
])
def test_matching_tools_in_any_yaml_form(tmp_path, block):
    want = CFG["agents"]["labeler"]["tools"]
    agent_file(tmp_path, "labeler", block.format(tools=", ".join(want), yaml="\n".join(f"  - {t}" for t in want)))
    problems, _ = run(tmp_path)
    assert problems == []


def test_missing_tools_line_is_an_error(tmp_path):
    agent_file(tmp_path, "labeler", None)
    problems, _ = run(tmp_path)
    assert any("inherit every tool" in p for p in problems)


def test_extra_and_missing_tools_are_reported(tmp_path):
    tools = [t for t in CFG["agents"]["skeptic"]["tools"] if t != "mcp__pipeline__get_sample"] + ["mcp__pipeline__get_disagreements"]
    agent_file(tmp_path, "skeptic", "tools: " + ", ".join(tools))
    problems, _ = run(tmp_path)
    assert any("missing tools from config: mcp__pipeline__get_sample" in p for p in problems)
    assert any("not in config/permissions.json: mcp__pipeline__get_disagreements" in p for p in problems)


@pytest.mark.parametrize("bad, msg", [
    ("mcp__pipeline__start_run", "main-session only"),
    ("Agent", "main-session only"),
    ("mcp__pipeline__*", "wildcard"),
    ("mcp__github", "whole server"),
])
def test_config_refuses_dangerous_grants(bad, msg):
    cfg = copy.deepcopy(CFG)
    cfg["agents"]["labeler"]["tools"].append(bad)
    problems = permissions.check_config(cfg, MODEL_AGENTS)
    assert any(msg in p for p in problems), problems


def test_config_and_models_must_list_the_same_agents():
    cfg = copy.deepcopy(CFG)
    del cfg["agents"]["analyst"]
    cfg["agents"]["rogue"] = {"tools": ["Read"], "may_write": []}
    problems = permissions.check_config(cfg, MODEL_AGENTS)
    assert any("analyst is in config/models.json" in p for p in problems)
    assert any("rogue has tools but no entry" in p for p in problems)


def test_settings_json_allows_every_agent_mcp_tool():
    """Background subagents can't answer permission prompts, so every MCP tool an agent
    needs must be pre-approved in .claude/settings.json."""
    settings = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
    allowed = set(settings["permissions"]["allow"])
    needed = {t for a in CFG["agents"].values() for t in a["tools"] if t.startswith("mcp__")}
    assert needed <= allowed, needed - allowed
    assert set(settings["enabledMcpjsonServers"]) == set(json.loads((ROOT / ".mcp.json").read_text())["mcpServers"])
