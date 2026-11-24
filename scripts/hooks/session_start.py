"""SessionStart hook: load where the pipeline stands into Claude's context (issue #34).

Prints a short status that Claude Code adds to the session's context on startup, resume,
/clear and after compaction: codebook versions and rounds, samples, open runs, and the
result of every config check. Problems are listed first, with what to do.

A SessionStart hook can't stop a session from starting, so it can't literally "refuse to
start". The hard stop is in start_run (scripts/runs.py), which refuses to start any agent run
while `models.py check` fails (including CLAUDE_CODE_EFFORT_LEVEL / CLAUDE_CODE_SUBAGENT_EFFORT
being set) or `permissions.py check` fails. This hook makes the problem visible at once.

It never fails the session: if something goes wrong it prints one line saying so.

    .venv/Scripts/python scripts/hooks/session_start.py      # see what it prints
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def labels_db() -> Path:
    return Path(os.environ.get("LABELS_DB", ROOT / "labels/labels.db"))


def _check(name, fn):
    """(name, [problems]) from a check function returning a problem list or (problems, notes)."""
    try:
        out = fn()
        problems = out[0] if isinstance(out, tuple) else out
    except Exception as e:  # a broken config is a problem, not a crash
        problems = [f"{type(e).__name__}: {e}".splitlines()[0]]
    return name, list(problems)


def codebook_lines() -> list:
    import codebook
    latest = {}
    for f in codebook.all_files():
        cb = codebook.parse(f)
        key = (cb.taxonomy, cb.variant)
        if key not in latest or cb.version > latest[key].version:
            latest[key] = cb
    lines = []
    for (tax, variant), cb in sorted(latest.items()):
        label = tax if variant == "main" else f"{tax} [{variant}]"
        kind = "empty template" if not cb.categories else f"{len(cb.categories)} categories"
        lines.append(f"{label}: v{cb.version:02d} (round {cb.round}, {kind}, {cb.path})")
    return lines or ["no codebook files"]


def db_state() -> dict:
    from db import SCHEMA_VERSION
    db = labels_db()
    if not db.exists():
        return {"problems": [f"{db.name} not found; run scripts/load_dataset.py"]}
    con = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        out = {"problems": [], "schema": version}
        if version != SCHEMA_VERSION:
            out["problems"].append(f"labels.db is schema v{version}, code expects v{SCHEMA_VERSION}: "
                                   "run `.venv/Scripts/python scripts/db.py`, then reconnect the pipeline MCP server")
            return out
        out["registered"] = [f"{r['taxonomy']}{'' if r['variant'] == 'main' else ' [' + r['variant'] + ']'} "
                             f"v{r['version']:02d}{' (FROZEN)' if r['frozen'] else ''}"
                             for r in con.execute("SELECT taxonomy, variant, version, frozen FROM codebook_versions "
                                                  "ORDER BY taxonomy, variant, version")]
        out["samples"] = [f"{r['name']} ({r['n']} {r['item_kind']}s)" for r in con.execute(
            "SELECT s.name, s.item_kind, COUNT(i.item_id) AS n FROM samples s "
            "LEFT JOIN sample_items i USING (sample_id) GROUP BY s.sample_id ORDER BY s.sample_id")]
        out["open_runs"] = [f"run {r['run_id']}: {r['rater']} on {r['sample']} ({r['taxonomy']}, {r['purpose']}), "
                            f"{r['labeled']}/{r['items']} labeled" for r in con.execute(
            "SELECT r.run_id, r.rater, r.taxonomy, r.purpose, s.name AS sample, "
            "(SELECT COUNT(*) FROM annotations a WHERE a.run_id = r.run_id) AS labeled, "
            "(SELECT COUNT(*) FROM sample_items i WHERE i.sample_id = r.sample_id) AS items "
            "FROM runs r JOIN samples s USING (sample_id) WHERE r.finished_at IS NULL ORDER BY r.run_id")]
        out["finished_runs"] = con.execute("SELECT COUNT(*) FROM runs WHERE finished_at IS NOT NULL").fetchone()[0]
        return out
    finally:
        con.close()


def git_hooks_enabled() -> bool:
    r = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip().rstrip("/") == ".githooks"


def build() -> str:
    import codebook
    import models
    import permissions
    checks = [_check("models.py check", models.check),
              _check("permissions.py check", permissions.check),
              _check("codebook.py check", codebook.check)]
    try:
        db = db_state()
    except Exception as e:
        db = {"problems": [f"couldn't read labels.db: {type(e).__name__}: {e}"]}

    problems = [f"{name}: {p}" for name, ps in checks for p in ps] + db["problems"]
    warnings = []
    if not git_hooks_enabled():
        warnings.append("git pre-commit hook is off: run `git config core.hooksPath .githooks` once (#33)")
    if not os.environ.get("GITSKILLS_GITHUB_TOKEN"):
        warnings.append("GITSKILLS_GITHUB_TOKEN is not set: the github MCP server is limited to 60 requests/hour")

    out = ["# GitSkills pipeline status (SessionStart hook, #34)", ""]
    if problems:
        out += ["**PROBLEMS: do not start runs or delegate to labeling agents until these are fixed** "
                "(start_run refuses while the model or permission check fails):"]
        out += [f"- {p}" for p in problems] + [""]
    out.append("Codebooks (latest file per series): " + "; ".join(codebook_lines()))
    if "registered" in db:
        out.append("Registered in labels.db: " + (", ".join(db["registered"]) or "none"))
        out.append("Samples: " + (", ".join(db["samples"]) or "none"))
        out.append("Open runs: " + ("; ".join(db["open_runs"]) or "none")
                   + f". Finished runs: {db['finished_runs']}.")
    ok = [name for name, ps in checks if not ps]
    if ok:
        out.append("Checks passing: " + ", ".join(ok) + (f", schema v{db['schema']}" if "schema" in db and
                                                         not db["problems"] else ""))
    out += [f"Note: {w}" for w in warnings]
    return "\n".join(out)


def main():
    try:
        sys.stdin.read()  # the hook input (source: startup/resume/clear/compact) isn't needed
    except Exception:
        pass
    try:
        text = build()
    except Exception as e:
        text = f"SessionStart hook (#34) couldn't build the pipeline status: {type(e).__name__}: {e}"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
