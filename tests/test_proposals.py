"""Tests for recording decisions on PROPOSED_NEW (scripts/proposals.py, #42).
    .venv/Scripts/python -m pytest tests/test_proposals.py
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "hooks"))

import labeling  # noqa: E402
import proposals  # noqa: E402
from test_record_label import args, env  # noqa: E402,F401  (fixture reused)


def propose(env, i, name):
    a = args(env, i)
    q = a["labels"][0]["evidence"]
    rec = {"schema_version": 1, **a, "proposals": [{"name": name, "definition": "A category the codebook lacks.",
                                                     "justification": "testing: excluded, it is not about tests.",
                                                     "evidence": q}]}
    return labeling.store_label(env["con"], rec)["proposal_ids"][0]


def status(env, pid):
    return tuple(env["con"].execute("SELECT status, merged_into, decided_by, decision_note, decided_at IS NOT NULL "
                                    "FROM proposals WHERE proposal_id = ?", (pid,)).fetchone())


def test_accept_merge_reject(env):
    a, m, r = propose(env, 0, "Alpha Area"), propose(env, 1, "Beta Area"), propose(env, 2, "Gamma Area")
    proposals.decide(env["con"], a, "accepted", "both", note="its own thing")
    proposals.decide(env["con"], m, "merged", "brendan", merged_into="deployment")
    proposals.decide(env["con"], r, "rejected", "ryan")
    assert status(env, a) == ("accepted", None, "both", "its own thing", 1)
    assert status(env, m) == ("merged", "deployment", "brendan", None, 1)
    assert status(env, r) == ("rejected", None, "ryan", None, 1)


def test_merge_target_must_be_a_category_of_the_runs_codebook(env):
    pid = propose(env, 0, "Alpha Area")
    with pytest.raises(proposals.DecisionError, match="not a category of the codebook"):
        proposals.decide(env["con"], pid, "merged", "both", merged_into="no-such-category")
    assert status(env, pid)[0] == "pending"


def test_decisions_need_redo_to_change_and_freeze_once_taken_in(env):
    pid = propose(env, 0, "Alpha Area")
    proposals.decide(env["con"], pid, "accepted", "both")
    with pytest.raises(proposals.DecisionError, match="already accepted; pass --redo"):
        proposals.decide(env["con"], pid, "rejected", "both")
    proposals.decide(env["con"], pid, "rejected", "both", redo=True)
    assert status(env, pid)[0] == "rejected"
    env["con"].execute("UPDATE proposals SET resulting_version_id = 1 WHERE proposal_id = ?", (pid,))
    with pytest.raises(proposals.DecisionError, match="already in a codebook version"):
        proposals.decide(env["con"], pid, "accepted", "both", redo=True)


@pytest.mark.parametrize("by", ["Brendan", "", "brendan dellos", "both!"])
def test_decided_by_is_a_lowercase_name(env, by):
    pid = propose(env, 0, "Alpha Area")
    with pytest.raises(proposals.DecisionError, match="lowercase first name"):
        proposals.decide(env["con"], pid, "accepted", by)


def test_cli_list_and_decide(env, monkeypatch, capsys):
    pid = propose(env, 0, "Alpha Area")
    env["con"].commit()
    monkeypatch.setenv("LABELS_DB", str(env["db"]))
    proposals.main(["list"])
    out = capsys.readouterr().out
    assert f"#{pid} [pending] Alpha Area" in out and "evidence:" in out and "why new:" in out
    proposals.main(["decide", str(pid), "--merge", "testing", "--by", "both", "--note", "same thing"])
    assert "merged into testing" in capsys.readouterr().out
    proposals.main(["list", "--status", "merged"])
    assert "decided: merged into testing by both (same thing)" in capsys.readouterr().out


def test_agents_cannot_run_it():
    """Agents may propose but never decide: the labels guard (#32) blocks the script for subagents."""
    import labels_guard
    with pytest.raises(labels_guard.Blocked, match="may not run scripts/proposals.py"):
        labels_guard.decide({"tool_name": "Bash", "agent_type": "codebook-consolidator",
                             "tool_input": {"command": ".venv/Scripts/python scripts/proposals.py decide 3 --accept --by both"}})
