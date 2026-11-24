"""Tests for the Stop / SubagentStop batch check (scripts/hooks/batch_check.py) and finish_run's
agreement report (runs.batch_agreement), issue #36.
    .venv/Scripts/python -m pytest tests/test_batch_check.py
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "hooks"))

import batch_check as hook  # noqa: E402
import labeling  # noqa: E402
import runs  # noqa: E402
import sampling  # noqa: E402
from test_record_label import args, env  # noqa: E402,F401  (fixture reused)


@pytest.fixture
def db(env, monkeypatch):
    monkeypatch.setenv("LABELS_DB", str(env["db"]))
    return env


def label(env, i, run, category="testing"):
    a = args(env, i, run)
    a["labels"][0]["category"] = category
    labeling.store_label(env["con"], {"schema_version": 1, "proposals": [], **a})


def label_all(env, run, category="testing"):
    for i in range(len(env["items"])):
        label(env, i, run, category)


def sub_stop(agent, **kw):
    return hook.decide({"hook_event_name": "SubagentStop", "agent_type": agent, **kw})


def main_stop(**kw):
    return hook.decide({"hook_event_name": "Stop", **kw})


# --- SubagentStop ----------------------------------------------------------------------

def test_agent_with_unlabeled_items_is_sent_back(db):
    label(db, 0, db["run"])
    reason = sub_stop("labeler")
    assert f"run {db['run']} (s1) has 3 of 4 items unlabeled" in reason
    for sha, _ in db["items"][1:]:
        assert sha in reason


def test_agent_with_complete_batch_may_stop(db):
    label_all(db, db["run"])
    assert sub_stop("labeler") is None


def test_only_sent_back_once(db):
    assert sub_stop("labeler") is not None
    assert sub_stop("labeler", stop_hook_active=True) is None


def test_agent_without_a_run_or_main_session_is_ignored(db):
    assert sub_stop("analyst") is None
    assert sub_stop(None) is None


def second_labeler_run(env):
    """Another open labeler run, on a second sample (one open run per rater and sample)."""
    sampling.draw(env["con"], "s2", 2, seed=3, min_chars=1500, max_chars=6000)
    return runs.start_run(env["con"], "s2", "purpose", "labeler", "round", 1)["run_id"]


def test_several_open_runs_without_transcript_are_left_alone(db):
    second_labeler_run(db)
    assert sub_stop("labeler") is None


def test_run_is_taken_from_the_transcript(db, tmp_path):
    second = second_labeler_run(db)
    t = tmp_path / "agent.jsonl"
    entry = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "mcp__pipeline__record_label", "input": {"run_id": second}}]}}
    t.write_text(json.dumps({"type": "user"}) + "\n" + json.dumps(entry) + "\nnot json record_label\n")
    assert hook.run_ids_from_transcript(str(t)) == {second}
    reason = sub_stop("labeler", agent_transcript_path=str(t))
    assert f"run {second} (s2) has 2 of 2 items unlabeled" in reason and f"run {db['run']} " not in reason


# --- Stop (main session) -----------------------------------------------------------------

def test_main_session_must_finish_complete_runs(db):
    assert main_stop() is None                      # nothing complete yet
    label_all(db, db["run"])
    reason = main_stop()
    assert f"run {db['run']} (labeler on s1) is fully labeled but not finished" in reason
    assert main_stop(stop_hook_active=True) is None
    runs.finish_run(db["con"], db["run"])
    assert main_stop() is None


def test_human_runs_are_not_nagged(db):
    for i in range(len(db["items"])):
        a = args(db, i, db["human"])
        labeling.store_label(db["con"], {"schema_version": 1, "proposals": [], **a}, allow_human=True)
    assert main_stop() is None


# --- agreement on finish -------------------------------------------------------------------

def test_finish_run_reports_agreement_with_matching_finished_runs(db):
    con = db["con"]
    skeptic = runs.start_run(con, "s1", "purpose", "skeptic", "round", 1)["run_id"]
    label_all(db, db["run"])
    for i in range(len(db["items"])):
        label(db, i, skeptic, "deployment" if i == 0 else "testing")
    first = runs.finish_run(con, db["run"])
    assert first["agreement"] == []                 # nothing else finished yet
    second = runs.finish_run(con, skeptic)
    [g] = second["agreement"]
    assert (g["other_run"], g["other_rater"]) == (db["run"], "labeler")
    assert (g["agree"], g["disjoint"], g["items_compared"], g["exact_agreement"]) == (3, 1, 4, 0.75)


def test_round0_runs_have_no_agreement(db):
    out = runs.finish_run(db["con"], db["open_run"], allow_incomplete=True)
    assert out["agreement"] == []


# --- process and settings -----------------------------------------------------------------

def run_hook(raw, env_db=None):
    import os
    e = dict(os.environ)
    if env_db:
        e["LABELS_DB"] = str(env_db)
    return subprocess.run([sys.executable, str(ROOT / "scripts/hooks/batch_check.py")], input=raw,
                          capture_output=True, text=True, cwd=ROOT, env=e)


def test_hook_process_blocks_with_json(db):
    db["con"].commit()
    r = run_hook(json.dumps({"hook_event_name": "SubagentStop", "agent_type": "labeler"}), db["db"])
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["decision"] == "block" and "Batch check" in out["reason"]


def test_hook_fails_open():
    r = run_hook("not json")
    assert r.returncode == 0 and r.stdout == "" and "skipped" in r.stderr


def test_settings_registers_both_stop_hooks():
    s = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
    for event in ("Stop", "SubagentStop"):
        assert any("batch_check.py" in h["command"] for e in s["hooks"][event] for h in e["hooks"]), event
