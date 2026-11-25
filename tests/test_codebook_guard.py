"""Tests for the codebook write guard hook (scripts/hooks/codebook_guard.py, issue #33).
    .venv/Scripts/python -m pytest tests/test_codebook_guard.py
"""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "hooks"))

import codebook_guard as g  # noqa: E402

CONS = "codebook-consolidator"
NEW = "codebook/purpose/v01.md"          # pretend `next` created it and it's uncommitted


def decide(tool, agent=None, frozen=False, committed=False, exists=True, tmp=None, **tool_input):
    root = tmp
    if tmp is not None and exists:
        for key in ("file_path", "notebook_path"):
            if key in tool_input and not Path(tool_input[key]).is_absolute():
                (tmp / tool_input[key]).parent.mkdir(parents=True, exist_ok=True)
                (tmp / tool_input[key]).write_text("x")
    event = {"tool_name": tool, "tool_input": tool_input, "cwd": str(root or ROOT)}
    if agent:
        event["agent_type"] = agent
    g.decide(event, is_frozen=lambda t, v: frozen, is_committed=lambda r: committed, root=root or ROOT)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "ROOT", tmp_path)
    return tmp_path


def blocked(match, *a, **kw):
    with pytest.raises(g.Blocked, match=match):
        decide(*a, **kw)


# --- file tools ---------------------------------------------------------------

def test_consolidator_may_edit_an_uncommitted_version(repo):
    decide("Edit", CONS, tmp=repo, file_path=NEW)
    decide("Write", CONS, tmp=repo, file_path="codebook/purpose/seeded/v00.md")
    decide("Edit", CONS, tmp=repo, file_path=str(repo / NEW))  # absolute path


@pytest.mark.parametrize("agent", [None, "labeler", "skeptic", "analyst"])
def test_everyone_else_is_blocked(repo, agent):
    blocked("Only the codebook-consolidator", "Edit", agent, tmp=repo, file_path=NEW)


@pytest.mark.parametrize("tool, key", [("Write", "file_path"), ("MultiEdit", "file_path"),
                                       ("NotebookEdit", "notebook_path")])
def test_all_file_tools_are_guarded(repo, tool, key):
    blocked("Only the codebook-consolidator", tool, "labeler", tmp=repo, **{key: NEW})


def test_committed_version_is_immutable(repo):
    blocked("committed codebook version", "Edit", CONS, committed=True, tmp=repo, file_path=NEW)


def test_new_files_only_via_next(repo):
    blocked("does not exist", "Write", CONS, exists=False, tmp=repo, file_path="codebook/purpose/v02.md")


def test_frozen_series_is_closed(repo):
    blocked("frozen", "Edit", CONS, frozen=True, tmp=repo, file_path=NEW)


def test_non_version_files_are_blocked_even_for_consolidator(repo):
    blocked("not a codebook version file", "Edit", CONS, tmp=repo, file_path="codebook/README.md")
    blocked("not a codebook version file", "Write", CONS, tmp=repo, file_path="codebook/purpose/notes.md")


def test_paths_outside_codebook_pass(repo):
    decide("Edit", "labeler", tmp=repo, file_path="scripts/x.py")
    decide("Write", None, tmp=repo, file_path="docs/codebook-notes.md")


def test_dotdot_into_codebook_is_caught(repo):
    blocked("Only the codebook-consolidator", "Edit", "labeler", tmp=repo, file_path="scripts/../codebook/purpose/v01.md")


def test_real_committed_v00_is_protected():
    """Against the real repo: v00.md is committed, so even the consolidator can't touch it."""
    with pytest.raises(g.Blocked, match="committed codebook version"):
        g.decide({"tool_name": "Edit", "agent_type": CONS,
                  "tool_input": {"file_path": str(ROOT / "codebook/purpose/v00.md")}},
                 is_frozen=lambda t, v: False)


# --- shell ---------------------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    ".venv/Scripts/python scripts/codebook.py check",
    ".venv/Scripts/python scripts/codebook.py register codebook/purpose/v01.md",
    "cat codebook/purpose/v00.md",
    "git diff codebook/",
    "git log -- codebook/purpose/v00.md",
    "ls scripts",
])
def test_harmless_shell_commands_pass(cmd):
    decide("Bash", "labeler", command=cmd)
    decide("Bash", None, command=cmd)


@pytest.mark.parametrize("cmd", [
    "echo hi > codebook/purpose/v00.md",
    "sed -i 's/a/b/' codebook/purpose/v00.md",
    "rm codebook/context/v00.md",
    "git checkout HEAD~1 -- codebook/purpose/v00.md",
    "python -c \"open('codebook/purpose/v00.md','w')\"",
    "cp /tmp/x.md codebook/purpose/v01.md",
    "ls && mv codebook/purpose/v00.md /tmp",
])
def test_shell_writes_are_blocked_for_everyone(cmd):
    with pytest.raises(g.Blocked, match="may not write to codebook"):
        decide("Bash", None, command=cmd)
    with pytest.raises(g.Blocked, match="may only run"):  # the consolidator is stopped earlier (#24)
        decide("Bash", CONS, command=cmd)


# --- consolidator confinement (#24) ---------------------------------------------------

@pytest.mark.parametrize("cmd", [
    ".venv/Scripts/python scripts/codebook.py check",
    ".venv/Scripts/python scripts/codebook.py next purpose --round 3",
    ".venv/Scripts/python scripts/codebook.py next purpose --round 1 && .venv/Scripts/python scripts/codebook.py check",
])
def test_consolidator_may_run_check_and_next(cmd):
    decide("Bash", CONS, command=cmd)


@pytest.mark.parametrize("cmd", [
    "ls",
    "git commit -am 'codebook v02'",
    "cat labels/dump.sql",
    ".venv/Scripts/python scripts/codebook.py register codebook/purpose/v01.md",
    ".venv/Scripts/python scripts/codebook.py check > /tmp/out",
    ".venv/Scripts/python scripts/codebook.py check | tee x",
    ".venv/Scripts/python scripts/codebook.py next purpose --round $(rm -rf .)",
    ".venv/Scripts/python scripts/runs.py finish 3",
])
def test_consolidator_shell_is_confined(cmd):
    with pytest.raises(g.Blocked, match="may only run"):
        decide("Bash", CONS, command=cmd)


def test_consolidator_cannot_write_outside_codebook(repo):
    for path in ("scripts/x.py", "CLAUDE.md", ".claude/agents/codebook-consolidator.md", "labels/dump.sql"):
        with pytest.raises(g.Blocked, match="may only edit codebook version files"):
            decide("Edit", CONS, tmp=repo, file_path=path)
    decide("Edit", CONS, tmp=repo, file_path=NEW)  # its own uncommitted version file is still fine


def test_powershell_writes_are_blocked():
    with pytest.raises(g.Blocked):
        decide("PowerShell", CONS, command="Set-Content codebook\\purpose\\v00.md 'x'")


def test_next_only_for_consolidator_and_unfrozen():
    cmd = ".venv/Scripts/python scripts/codebook.py next purpose --round 2"
    decide("Bash", CONS, command=cmd)
    with pytest.raises(g.Blocked, match="only the codebook-consolidator"):
        decide("Bash", None, command=cmd)
    with pytest.raises(g.Blocked, match="frozen"):
        decide("Bash", CONS, frozen=True, command=cmd)


@pytest.mark.parametrize("cmd", [
    "python scripts/codebook.py next purpose --round 2",
    "cd repo && .venv/Scripts/python.exe -I scripts/codebook.py next context --round 1",
    '"C:/x/.venv/Scripts/python.exe" "scripts/codebook.py" next purpose --round 2',
])
def test_next_is_recognised_however_python_is_called(cmd):
    with pytest.raises(g.Blocked, match="only the codebook-consolidator"):
        decide("Bash", None, command=cmd)


@pytest.mark.parametrize("cmd", [
    "git commit -m 'new versions only via `scripts/codebook.py next`'",
    "gh issue comment 43 --body 'run scripts/codebook.py next purpose --round 3 first'",
])
def test_mentioning_next_in_text_is_not_running_it(cmd):
    decide("Bash", None, command=cmd)


def test_only_the_main_session_freezes():
    cmd = ".venv/Scripts/python scripts/codebook.py freeze context"
    decide("Bash", None, command=cmd)
    for agent in (CONS, "labeler", "analyst"):
        with pytest.raises(g.Blocked):
            decide("Bash", agent, command=cmd)


def test_a_frozen_series_blocks_the_consolidator_via_the_real_flag(repo, monkeypatch):
    """#43: once `codebook.py freeze` sets the flag, the guard (reading labels.db) closes the series."""
    db = repo / "labels.db"
    monkeypatch.setenv("LABELS_DB", str(db))
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE codebook_versions (taxonomy TEXT, variant TEXT, version INT, frozen INT)")
    con.execute("INSERT INTO codebook_versions VALUES ('context', 'main', 3, 1)")
    con.commit()
    con.close()
    (repo / "codebook/context").mkdir(parents=True)
    (repo / "codebook/context/v04.md").write_text("x")
    event = {"tool_name": "Edit", "agent_type": CONS, "cwd": str(repo),
             "tool_input": {"file_path": "codebook/context/v04.md"}}
    with pytest.raises(g.Blocked, match="frozen"):
        g.decide(event, is_committed=lambda r: False, root=repo)
    with pytest.raises(g.Blocked, match="frozen"):
        g.decide({"tool_name": "Bash", "agent_type": CONS, "tool_input": {
            "command": ".venv/Scripts/python scripts/codebook.py next context --round 3"}})
    g.decide({"tool_name": "Bash", "agent_type": CONS, "tool_input": {  # the other taxonomy stays open
        "command": ".venv/Scripts/python scripts/codebook.py next purpose --round 1"}})


# --- freeze flag and the real hook process ---------------------------------------

def test_frozen_reads_labels_db(tmp_path, monkeypatch):
    db = tmp_path / "labels.db"
    monkeypatch.setenv("LABELS_DB", str(db))
    assert g.frozen("purpose", "main") is False  # no db yet
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE codebook_versions (taxonomy TEXT, variant TEXT, version INT, frozen INT)")
    con.execute("INSERT INTO codebook_versions VALUES ('purpose', 'main', 4, 1)")
    con.commit()
    con.close()
    assert g.frozen("purpose", "main") is True
    assert g.frozen("context", "main") is False
    assert g.frozen("purpose", "seeded") is False


def run_hook(event):
    return subprocess.run([sys.executable, str(ROOT / "scripts/hooks/codebook_guard.py")],
                          input=json.dumps(event), capture_output=True, text=True, cwd=ROOT)


def test_hook_process_blocks_with_exit_2():
    r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "codebook/purpose/v00.md"}})
    assert r.returncode == 2 and "Codebook guard" in r.stderr


def test_hook_process_allows_unrelated_calls():
    r = run_hook({"tool_name": "Edit", "tool_input": {"file_path": "README.md"}})
    assert r.returncode == 0 and r.stderr == ""


def test_hook_fails_closed_on_bad_input_about_codebook():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/hooks/codebook_guard.py")],
                       input="not json codebook/", capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 2
    r = subprocess.run([sys.executable, str(ROOT / "scripts/hooks/codebook_guard.py")],
                       input="not json", capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0


def test_settings_registers_the_guard():
    s = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
    entries = s["hooks"]["PreToolUse"]
    guard = [e for e in entries if any("codebook_guard.py" in h["command"] for h in e["hooks"])]
    assert guard, "codebook_guard.py is not registered as a PreToolUse hook"
    tools = set(guard[0]["matcher"].split("|"))
    assert {"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash", "PowerShell"} <= tools
