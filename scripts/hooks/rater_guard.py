"""PreToolUse hook on record_label: the caller must be the run's rater (issue #35).

A run's provenance (model, effort, prompt_hash) is looked up from its `rater`, so a label is
only trustworthy if that rater is the agent that actually wrote it. Claude Code tells hooks
which subagent made a call (`agent_type`); this hook blocks record_label when:

  * the main session calls it (no agent_type): labels come from the rater subagents; human
    labels are imported by a script a person runs (labeling.store_label with allow_human=True);
  * the calling subagent is not the run's rater, e.g. the labeler writing into the skeptic's run.

An unknown run_id is let through, so record_label itself reports it. If the hook fails it blocks.
Registered in .claude/settings.json for mcp__pipeline__record_label. Exit 2 blocks; stderr goes
to the agent.
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class Blocked(Exception):
    pass


def labels_db() -> Path:
    return Path(os.environ.get("LABELS_DB", ROOT / "labels/labels.db"))


def run_rater(run_id) -> str | None:
    db = labels_db()
    if not db.exists():
        return None
    con = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT rater FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def decide(event: dict, rater_of=run_rater) -> None:
    agent = event.get("agent_type")
    run_id = (event.get("tool_input") or {}).get("run_id")
    if not agent:
        raise Blocked("the main session may not call record_label. Delegate to the run's rater agent "
                      "(pass it the run_id). Human labels are imported by a script, not through this tool.")
    rater = rater_of(run_id)
    if rater is not None and rater != agent:
        raise Blocked(f"run {run_id} belongs to rater {rater!r}, but this call comes from agent {agent!r}. "
                      "Each agent labels only its own run, so the run's model, effort and prompt_hash "
                      "describe who really wrote the label.")


def main():
    raw = sys.stdin.read()
    try:
        decide(json.loads(raw))
    except Blocked as e:
        print(f"Rater guard (#35): {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Rater guard (#35) failed ({type(e).__name__}: {e}); blocking to be safe.", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
