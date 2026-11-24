"""Tests for prompt provenance (scripts/prompts.py, record_label, schema v3) and the rater guard
hook (scripts/hooks/rater_guard.py), issue #35.
    .venv/Scripts/python -m pytest tests/test_provenance.py
"""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "hooks"))

import labeling  # noqa: E402
import prompts  # noqa: E402
import rater_guard  # noqa: E402
from db import SCHEMA_VERSION  # noqa: E402
from test_record_label import args, env  # noqa: E402,F401  (fixture reused)


def record(env, i=0, run=None, **over):
    a = args(env, i, run)
    a.update(over)
    rec = {"schema_version": 1, "proposals": [], **a}
    return labeling.store_label(env["con"], rec)


def stored_hash(env, item):
    return env["con"].execute("SELECT prompt_hash FROM annotations WHERE item_id = ?", (item,)).fetchone()[0]


# --- hashing ---------------------------------------------------------------------

def test_hash_covers_agent_and_preloaded_skills(claude_dir):
    (claude_dir / "skills/apply-codebook").mkdir(parents=True)
    (claude_dir / "skills/apply-codebook/SKILL.md").write_text("---\nname: apply-codebook\n---\nsteps\n")
    (claude_dir / "skills/apply-codebook/codebook.md").write_text("ref\n")
    before = prompts.prompt_hash(prompts.instruction_files("labeler"))
    agent = claude_dir / "agents/labeler.md"
    agent.write_text(agent.read_text().replace("---\nTest", "skills:\n  - apply-codebook\n---\nTest"))
    files = [p for p, _ in prompts.instruction_files("labeler")]
    assert files == [".claude/agents/labeler.md", ".claude/skills/apply-codebook/SKILL.md",
                     ".claude/skills/apply-codebook/codebook.md"]
    with_skill = prompts.prompt_hash(prompts.instruction_files("labeler"))
    assert with_skill != before and with_skill.startswith("sha256:")
    (claude_dir / "skills/apply-codebook/codebook.md").write_text("ref changed\n")
    assert prompts.prompt_hash(prompts.instruction_files("labeler")) != with_skill  # skill files count


def test_line_endings_dont_change_the_hash(claude_dir):
    agent = claude_dir / "agents/labeler.md"
    agent.write_bytes(agent.read_bytes().replace(b"\r\n", b"\n"))  # write_text gives CRLF on Windows
    lf = prompts.prompt_hash(prompts.instruction_files("labeler"))
    agent.write_bytes(agent.read_bytes().replace(b"\n", b"\r\n"))
    assert prompts.prompt_hash(prompts.instruction_files("labeler")) == lf


def test_missing_agent_or_skill_is_an_error(claude_dir):
    with pytest.raises(prompts.ProvenanceError, match="no agent definition"):
        prompts.instruction_files("nobody")
    agent = claude_dir / "agents/skeptic.md"
    agent.write_text(agent.read_text().replace("---\nTest", "skills: ghost-skill\n---\nTest"))
    with pytest.raises(prompts.ProvenanceError, match="ghost-skill"):
        prompts.instruction_files("skeptic")


# --- record_label stores it ---------------------------------------------------------

def test_agent_label_gets_prompt_hash_and_instructions(env, claude_dir):
    out = record(env)
    h = out["prompt_hash"]
    assert h and stored_hash(env, env["items"][0][0]) == h
    row = env["con"].execute("SELECT rater, files FROM prompt_versions WHERE prompt_hash = ?", (h,)).fetchone()
    assert row[0] == "labeler"
    assert json.loads(row[1]) == [{"path": ".claude/agents/labeler.md",
                                   "text": (claude_dir / "agents/labeler.md").read_text()}]


def test_same_instructions_stored_once_changed_ones_again(env, claude_dir):
    h1 = record(env, 0)["prompt_hash"]
    assert record(env, 1)["prompt_hash"] == h1
    assert env["con"].execute("SELECT COUNT(*) FROM prompt_versions").fetchone()[0] == 1
    agent = claude_dir / "agents/labeler.md"
    agent.write_text(agent.read_text() + "Edited mid-run.\n")
    h3 = record(env, 2)["prompt_hash"]
    assert h3 != h1 and env["con"].execute("SELECT COUNT(*) FROM prompt_versions").fetchone()[0] == 2


def test_missing_agent_file_rejects_and_writes_nothing(env, claude_dir):
    (claude_dir / "agents/labeler.md").unlink()
    with pytest.raises(labeling.LabelRejected, match="no agent definition"):
        record(env)
    assert env["con"].execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 0
    assert env["con"].execute("SELECT COUNT(*) FROM prompt_versions").fetchone()[0] == 0


def test_human_labels_have_no_prompt_hash(env):
    a = args(env, 0, env["human"])
    out = labeling.store_label(env["con"], {"schema_version": 1, "proposals": [], **a}, allow_human=True)
    assert out["prompt_hash"] is None and stored_hash(env, env["items"][0][0]) is None


def test_database_refuses_agent_label_without_provenance(env):
    con = env["con"]
    with pytest.raises(sqlite3.IntegrityError, match="prompt_hash"):
        con.execute("INSERT INTO annotations (run_id, item_id) VALUES (?, 'x')", (env["run"],))
    with pytest.raises(sqlite3.IntegrityError, match="prompt_hash"):
        con.execute("INSERT INTO annotations (run_id, item_id, prompt_hash) VALUES (?, 'x', 'sha256:nope')",
                    (env["run"],))
    with pytest.raises(sqlite3.IntegrityError, match="human"):
        con.execute("INSERT INTO annotations (run_id, item_id, prompt_hash) VALUES (?, 'x', 'sha256:a')",
                    (env["human"],))
    con.rollback()


def test_schema_version_is_3():
    assert SCHEMA_VERSION == 3


# --- rater guard hook ------------------------------------------------------------------

def guard(agent, run_id=1, rater="labeler"):
    event = {"tool_name": "mcp__pipeline__record_label", "tool_input": {"run_id": run_id}}
    if agent:
        event["agent_type"] = agent
    rater_guard.decide(event, rater_of=lambda r: rater)


def test_rater_may_label_its_own_run():
    guard("labeler")


def test_other_agent_is_blocked():
    with pytest.raises(rater_guard.Blocked, match="belongs to rater 'labeler'.*'skeptic'"):
        guard("skeptic")


def test_main_session_is_blocked():
    with pytest.raises(rater_guard.Blocked, match="main session"):
        guard(None)


def test_unknown_run_is_left_to_record_label():
    guard("labeler", run_id=999, rater=None)


def test_guard_reads_the_run_from_labels_db(env, monkeypatch):
    monkeypatch.setenv("LABELS_DB", str(env["db"]))
    env["con"].commit()
    assert rater_guard.run_rater(env["run"]) == "labeler"
    assert rater_guard.run_rater(env["open_run"]) == "open-coder"
    assert rater_guard.run_rater(10_000) is None


def run_hook(raw):
    return subprocess.run([sys.executable, str(ROOT / "scripts/hooks/rater_guard.py")], input=raw,
                          capture_output=True, text=True, cwd=ROOT)


def test_hook_process_blocks_main_session_and_fails_closed():
    r = run_hook(json.dumps({"tool_name": "mcp__pipeline__record_label", "tool_input": {"run_id": 1}}))
    assert r.returncode == 2 and "Rater guard" in r.stderr
    assert run_hook("not json").returncode == 2


def test_settings_registers_the_rater_guard():
    s = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
    pairs = [(e["matcher"], h["command"]) for e in s["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert any(m == "mcp__pipeline__record_label" and "rater_guard.py" in c for m, c in pairs)
