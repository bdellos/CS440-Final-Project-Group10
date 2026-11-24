"""Stop / SubagentStop hook: every item in a batch gets a label, and finished batches get closed (issue #36).

SubagentStop (a labeling agent is about to finish):
    Finds the agent's run: the run_ids it passed to record_label (read from its transcript), or
    else its only open run (rater = the agent). If that run still has unlabeled items, the agent
    is sent back to label them, with the list. Only once: if it stops again (stop_hook_active),
    it is let go, so an agent that can't label an item isn't trapped; the main session then sees
    the gap when it calls finish_run.

Stop (the main session's turn is ending):
    If an agent run is fully labeled but not finished, the main session is asked to call
    finish_run, which closes the run and reports agreement with the other finished runs on the
    same sample and codebook version (runs.batch_agreement). Also only once per stop.

This hook fails open: an error never blocks stopping. Output is the documented JSON
{"decision": "block", "reason": ...}; no output means "go ahead".
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def labels_db() -> Path:
    return Path(os.environ.get("LABELS_DB", ROOT / "labels/labels.db"))


def _connect():
    db = labels_db()
    if not db.exists():
        return None
    con = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def run_ids_from_transcript(path: str | None) -> set:
    """run_ids the agent passed to record_label, from its JSONL transcript."""
    ids = set()
    if not path or not Path(path).is_file():
        return ids
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if "record_label" not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            for d in _walk(entry):
                if d.get("type") == "tool_use" and str(d.get("name", "")).endswith("record_label"):
                    rid = (d.get("input") or {}).get("run_id")
                    if isinstance(rid, int):
                        ids.add(rid)
    return ids


def _open_runs(con, where: str, params=()) -> list:
    return con.execute(
        f"""SELECT r.run_id, r.rater, s.name AS sample,
                   (SELECT COUNT(*) FROM sample_items i WHERE i.sample_id = r.sample_id) AS items,
                   (SELECT COUNT(*) FROM annotations a WHERE a.run_id = r.run_id) AS labeled
            FROM runs r JOIN samples s USING (sample_id)
            WHERE r.finished_at IS NULL AND r.rater_kind = 'agent' AND {where} ORDER BY r.run_id""",
        params).fetchall()


def _unlabeled(con, run_id: int, limit: int = 10) -> list:
    return [r[0] for r in con.execute(
        """SELECT i.item_id FROM sample_items i JOIN runs r USING (sample_id)
           WHERE r.run_id = ? AND i.item_id NOT IN (SELECT item_id FROM annotations WHERE run_id = ?)
           ORDER BY i.position LIMIT ?""", (run_id, run_id, limit))]


def subagent_stop(event: dict, con) -> str | None:
    agent = event.get("agent_type")
    if not agent:
        return None
    ids = run_ids_from_transcript(event.get("agent_transcript_path"))
    if ids:
        marks = ",".join("?" * len(ids))
        runs = _open_runs(con, f"r.run_id IN ({marks})", tuple(sorted(ids)))
    else:
        runs = _open_runs(con, "r.rater = ?", (agent,))
        if len(runs) != 1:  # none, or several in parallel: can't tell which is this agent's
            return None
    gaps = [r for r in runs if r["labeled"] < r["items"]]
    if not gaps:
        return None
    parts = []
    for r in gaps:
        missing = _unlabeled(con, r["run_id"])
        more = r["items"] - r["labeled"] - len(missing)
        parts.append(f"run {r['run_id']} ({r['sample']}) has {r['items'] - r['labeled']} of {r['items']} items "
                     f"unlabeled: {', '.join(missing)}" + (f" and {more} more" if more > 0 else ""))
    return ("Batch check (#36): not every item in your batch has a label. " + "; ".join(parts) +
            ". Label each one with record_label before stopping (get_sample lists the batch, get_skill "
            "reads an item). If an item truly can't be labeled, say which and why in your final message.")


def main_stop(event: dict, con) -> str | None:
    done = [r for r in _open_runs(con, "1 = 1") if r["items"] and r["labeled"] >= r["items"]]
    if not done:
        return None
    runs = ", ".join(f"run {r['run_id']} ({r['rater']} on {r['sample']})" for r in done)
    return (f"Batch check (#36): {runs} {'is' if len(done) == 1 else 'are'} fully labeled but not finished. "
            "Call finish_run for each: it closes the run and reports agreement with the other finished runs "
            "on the same sample and codebook. Then report the agreement to the user.")


def decide(event: dict) -> str | None:
    if event.get("stop_hook_active"):
        return None  # already sent back once: never loop
    con = _connect()
    if con is None:
        return None
    try:
        if event.get("hook_event_name") == "SubagentStop":
            return subagent_stop(event, con)
        if event.get("hook_event_name") == "Stop":
            return main_stop(event, con)
        return None
    finally:
        con.close()


def main():
    try:
        reason = decide(json.loads(sys.stdin.read()))
    except Exception as e:  # fail open: never trap a session because the check broke
        print(f"batch check (#36) skipped: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(0)
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    main()
