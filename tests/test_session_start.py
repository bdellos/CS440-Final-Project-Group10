"""Tests for the SessionStart hook (scripts/hooks/session_start.py) and the start_run checks, issue #34.
    .venv/Scripts/python -m pytest tests/test_session_start.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "hooks"))

import models  # noqa: E402
import permissions  # noqa: E402
import runs  # noqa: E402
import session_start as hook  # noqa: E402
from db import connect, init_schema  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    for var in models.OVERRIDE_VARS:
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / "labels.db"
    con = connect(labels_db=path)
    init_schema(con)
    con.execute("INSERT INTO samples (name, item_kind, method) VALUES ('round1', 'skill', 'test')")
    con.execute("INSERT INTO sample_items (sample_id, position, item_id) VALUES (1, 1, 'a'), (1, 2, 'b')")
    con.commit()
    monkeypatch.setenv("LABELS_DB", str(path))
    yield con
    con.close()


def test_healthy_status(db):
    runs.start_run(db, "round1", "purpose", "open-coder", "round0")
    text = hook.build()
    assert "PROBLEMS" not in text
    import codebook  # the real codebook files: whatever their latest versions are
    for tax in ("purpose", "context"):
        assert f"{tax}: v{codebook.parse(codebook.latest(tax)).version:02d}" in text
    assert "Samples: round1 (2 skills)" in text
    assert "run 1: open-coder on round1 (purpose, round0), 0/2 labeled" in text
    assert "models.py check" in text and "schema v3" in text


def test_effort_override_is_flagged_first(db, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_EFFORT", "high")
    text = hook.build()
    first = text.split("\n\n")[1]
    assert first.startswith("**PROBLEMS") and "CLAUDE_CODE_SUBAGENT_EFFORT" in first


def test_schema_mismatch_is_a_problem(db):
    db.execute("PRAGMA user_version = 2")
    db.commit()
    assert "schema v2, code expects v3" in hook.build()


def test_missing_db_is_a_problem(tmp_path, monkeypatch):
    monkeypatch.setenv("LABELS_DB", str(tmp_path / "nope.db"))
    assert "not found" in hook.build()


def test_permission_problem_is_flagged(db, monkeypatch):
    monkeypatch.setattr(permissions, "check", lambda: (["labeler: no `tools:` line"], []))
    assert "permissions.py check: labeler: no `tools:` line" in hook.build()


def test_hook_process_emits_additional_context():
    env = {k: v for k, v in os.environ.items() if k not in models.OVERRIDE_VARS}
    r = subprocess.run([sys.executable, str(ROOT / "scripts/hooks/session_start.py")], input='{"source":"startup"}',
                       capture_output=True, text=True, cwd=ROOT, env=env)
    assert r.returncode == 0
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart" and "GitSkills pipeline status" in out["additionalContext"]


def test_hook_never_fails_the_session(monkeypatch, capsys):
    monkeypatch.setattr(hook, "build", lambda: 1 / 0)
    monkeypatch.setattr(sys, "stdin", open(os.devnull))
    with pytest.raises(SystemExit) as e:
        hook.main()
    assert e.value.code == 0
    assert "couldn't build" in json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]


def test_start_run_refuses_on_permission_problems(db, monkeypatch):
    monkeypatch.setattr(permissions, "check", lambda: (["labeler: no `tools:` line"], []))
    with pytest.raises(runs.RunError, match="permissions check failed"):
        runs.start_run(db, "round1", "purpose", "open-coder", "round0")


def test_start_run_refuses_on_effort_override(db, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_EFFORT_LEVEL", "max")
    with pytest.raises(runs.RunError, match="model config check failed"):
        runs.start_run(db, "round1", "purpose", "open-coder", "round0")


def test_settings_registers_session_start():
    s = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
    entry = s["hooks"]["SessionStart"][0]
    assert set(entry["matcher"].split("|")) == {"startup", "resume", "clear", "compact"}
    assert "session_start.py" in entry["hooks"][0]["command"]
