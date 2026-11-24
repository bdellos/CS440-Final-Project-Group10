"""Tests for the labels guard hook (scripts/hooks/labels_guard.py, issue #32).
The validation itself is tested in test_record_label.py / test_validate_label.py.
    .venv/Scripts/python -m pytest tests/test_labels_guard.py
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "hooks"))

import labels_guard as g  # noqa: E402

HOOK = ROOT / "scripts/hooks/labels_guard.py"


def decide(tool, agent, **tool_input):
    event = {"tool_name": tool, "tool_input": tool_input, "cwd": str(ROOT)}
    if agent:
        event["agent_type"] = agent
    g.decide(event)


def blocked(*a, match=None, **kw):
    with pytest.raises(g.Blocked, match=match):
        decide(*a, **kw)


# --- file tools ----------------------------------------------------------------

@pytest.mark.parametrize("path", ["labels/labels.db", "labels/dump.sql", "labels/round0/x.json",
                                  str(ROOT / "labels" / "new.json")])
def test_subagents_cannot_write_labels_files(path):
    blocked("Write", "labeler", file_path=path, match="record_label")
    blocked("Edit", "analyst", file_path=path)


def test_other_paths_and_main_session_pass():
    decide("Write", "analyst", file_path="analysis/table.csv")
    decide("Write", "analyst", file_path="analysis/labels_by_language.py")  # 'labels' in a name is fine
    decide("Write", None, file_path="labels/dump.sql")  # main session: settings.json decides


# --- shell -----------------------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "sqlite3 labels/labels.db \"DELETE FROM annotations\"",
    "python -c \"import sqlite3; sqlite3.connect('labels/labels.db').execute('INSERT ...')\"",
    "echo x > labels/fake.json",
    "cp /tmp/a.db labels/labels.db",
    "LABELS_DB=/tmp/x.db python analysis/run.py",
    "rm labels\\labels.db",
    "Remove-Item labels\\labels.db",
])
def test_subagent_shell_writes_to_labels_are_blocked(cmd):
    blocked("Bash", "analyst", command=cmd, match="labels")


@pytest.mark.parametrize("cmd", [
    "ls labels/",
    "cat labels/dump.sql | head -50",
    "git log --oneline -- labels/dump.sql",
    "wc -l labels/dump.sql",
    ".venv/Scripts/python analysis/crosstab.py",
    ".venv/Scripts/python scripts/codebook.py check",
    ".venv/Scripts/python scripts/models.py check",
    ".venv/Scripts/python scripts/validate_label.py /tmp/label.json",
    "grep -c labeler analysis/notes.md",
])
def test_subagent_read_only_commands_pass(cmd):
    decide("Bash", "analyst", command=cmd)


@pytest.mark.parametrize("cmd", [
    ".venv/Scripts/python scripts/runs.py start --sample round1 --taxonomy purpose --rater x --purpose round",
    ".venv/Scripts/python scripts/runs.py finish 3",
    ".venv/Scripts/python scripts/load_dataset.py",
    ".venv/Scripts/python scripts/db_dump.py --restore",
    ".venv/Scripts/python scripts/codebook.py register codebook/purpose/v01.md",
    ".venv/Scripts/python scripts/detect_languages.py",
    "python -I scripts\\db.py",
    "cd x && \"C:/r/.venv/Scripts/python.exe\" \"scripts/runs.py\" finish 2",
])
def test_subagents_cannot_run_scripts_that_write_labels_db(cmd):
    blocked("Bash", "codebook-consolidator", command=cmd, match="may not run scripts/")


@pytest.mark.parametrize("cmd", [
    "sqlite3 labels/labels.db .dump",
    ".venv/Scripts/python scripts/runs.py finish 3",
    ".venv/Scripts/python scripts/db_dump.py",
])
def test_main_session_is_not_restricted(cmd):
    decide("Bash", None, command=cmd)


def test_mentioning_scripts_in_text_does_not_count():
    decide("Bash", "analyst", command="grep -n runs analysis/README.md")


# --- the real hook process ---------------------------------------------------------

def run_hook(raw):
    return subprocess.run([sys.executable, str(HOOK)], input=raw, capture_output=True, text=True, cwd=ROOT)


def test_hook_process_blocks_with_exit_2():
    r = run_hook(json.dumps({"tool_name": "Bash", "agent_type": "analyst",
                             "tool_input": {"command": "sqlite3 labels/labels.db 'DELETE FROM runs'"}}))
    assert r.returncode == 2 and "Labels guard" in r.stderr


def test_hook_process_allows_main_session():
    r = run_hook(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls labels"}}))
    assert r.returncode == 0 and r.stderr == ""


def test_hook_fails_closed_for_subagents_only():
    assert run_hook('{"agent_type": "analyst", "tool_input": {"command": "x labels/"}, ').returncode == 2
    assert run_hook('{"tool_input": {"command": "x labels/"}, ').returncode == 0


def test_settings_registers_the_guard():
    s = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
    hooks = [(e["matcher"], h["command"]) for e in s["hooks"]["PreToolUse"] for h in e["hooks"]]
    m = [matcher for matcher, cmd in hooks if "labels_guard.py" in cmd]
    assert m and {"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash", "PowerShell"} <= set(m[0].split("|"))
