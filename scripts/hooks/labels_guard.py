"""PreToolUse hook: keep record_label the only way subagents get labels into the data (issue #32).

record_label (#14) runs scripts/validate_label.py (JSON schema + database checks) before it
writes, and stores nothing if anything is wrong (tests/test_record_label.py). This hook closes
the ways around it for subagents (`agent_type` set in the hook input):

  * file tools (Write/Edit/MultiEdit/NotebookEdit) on labels/ are blocked (settings.json also
    denies them for everyone);
  * shell commands (Bash/PowerShell) that name labels/, labels.db or LABELS_DB are blocked unless
    they only read (ls, cat, head, git log/diff/show, ...) with no write-like operation;
  * shell commands that run a script from scripts/ are blocked unless it is on SUBAGENT_SCRIPTS
    (checks that don't write labels). runs.py, load_dataset.py, db_dump.py, codebook.py register
    and the rest write labels.db and are for the main session and humans only.

The main session is not restricted: it starts and finishes runs and runs the maintenance scripts.
Shell parsing is best-effort; a script the analyst writes under analysis/ is not inspected, so
analysis code must open labels.db read-only (#27).

Registered in .claude/settings.json. Exit code 2 blocks the call; stderr goes to the agent.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codebook_guard import FILE_TOOLS, SHELL_TOOLS, WRITE_OPS, rel_path  # noqa: E402

LABELS_REF = re.compile(r"(?<![\w-])labels(?:[/\\]|\.db\b)|\bLABELS_DB\b", re.I)
READ_ONLY_CMDS = re.compile(r"^\s*(ls|dir|cat|type|head|tail|wc|stat|file|Get-ChildItem|Get-Content|"
                            r"git\s+(log|diff|show|status|blame|ls-files))\b", re.I)
SCRIPT_RUN = re.compile(r"python[\w.]*[\"']?\s+(?:-\S+\s+)*[\"']?(?:\S*[/\\])?scripts[/\\]([\w/\\]+\.py)[\"']?(.*)",
                        re.I)
# Scripts a subagent may run: (script, allowed first argument or None for any).
SUBAGENT_SCRIPTS = {
    "codebook.py": {"check", "next"},      # `next` is further limited by codebook_guard
    "models.py": {"check"},
    "permissions.py": {"check"},
    "validate_label.py": None,             # reads only
}


class Blocked(Exception):
    pass


def check_shell(command: str, agent: str) -> None:
    for part in re.split(r"&&|\|\||;|\n|\|", command):
        m = SCRIPT_RUN.search(part)
        if m:
            script = m.group(1).replace("\\", "/")
            first = (m.group(2).split() or [""])[0]
            allowed = SUBAGENT_SCRIPTS.get(script, "missing")
            if allowed == "missing" or (allowed is not None and first not in allowed):
                raise Blocked(f"agent {agent!r} may not run scripts/{script} {first}".rstrip() +
                              ": it can write labels.db. Labels go in only through the pipeline MCP tool "
                              "record_label; runs are started and finished by the main session.")
        if LABELS_REF.search(part) and (WRITE_OPS.search(part) or not READ_ONLY_CMDS.match(part)):
            raise Blocked(f"agent {agent!r} may not touch labels/ or labels.db from the shell "
                          f"(only read-only commands like ls/cat/git log). Write labels with record_label. "
                          f"Blocked: {part.strip()[:200]}")


def decide(event: dict) -> None:
    agent = event.get("agent_type")
    if not agent:
        return  # main session: unrestricted here
    tool, args = event.get("tool_name"), event.get("tool_input") or {}
    if tool in FILE_TOOLS:
        rel = rel_path(args.get(FILE_TOOLS[tool]) or "", event.get("cwd"))
        if rel is not None and (rel.lower() == "labels" or rel.lower().startswith("labels/")):
            raise Blocked(f"agent {agent!r} may not write {rel}. Labels go in only through record_label.")
    elif tool in SHELL_TOOLS:
        check_shell(args.get("command") or "", agent)


def main():
    raw = sys.stdin.read()
    try:
        decide(json.loads(raw))
    except Blocked as e:
        print(f"Labels guard (#32): {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:  # fail closed for subagent calls that mention labels or scripts
        if '"agent_type"' in raw and re.search(r"labels|scripts", raw, re.I):
            print(f"Labels guard (#32) failed ({type(e).__name__}: {e}); blocking to be safe.", file=sys.stderr)
            sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
