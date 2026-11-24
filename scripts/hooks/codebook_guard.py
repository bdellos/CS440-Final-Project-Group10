"""PreToolUse hook: codebook write guard (issue #33).

Registered in .claude/settings.json for Write, Edit, MultiEdit, NotebookEdit, Bash and PowerShell.
Claude Code sends the tool call as JSON on stdin; exit code 2 blocks it and stderr is shown
to the agent. Rules:

  * Only the codebook-consolidator subagent (`agent_type` in the hook input) may write under
    codebook/. The main session and every other agent are blocked: humans edit the codebook
    themselves or delegate to the consolidator.
  * Even the consolidator may only edit a version file (codebook/<taxonomy>/[<variant>/]vNN.md)
    that already exists and has never been committed, i.e. one made by
    `scripts/codebook.py next`. Committed versions are immutable; new files come only from `next`.
  * Nobody writes to a series once any of its versions is frozen (codebook_versions.frozen in
    labels.db, set at the freeze, #43). Freezing one taxonomy doesn't block the other.
  * Shell commands (Bash/PowerShell) are checked best-effort: `codebook.py check` and `register`
    are always allowed, `codebook.py next` only for the consolidator on an unfrozen series, and
    any other command that names codebook/ together with a write-like operation is blocked.
    Shell parsing can't be complete; the git pre-commit hook (.githooks/pre-commit) and
    `codebook.py check` catch anything that slips through.

If the hook itself fails on a call that touches the codebook, it blocks (fails closed).

Manual test:
    echo '{"tool_name":"Edit","tool_input":{"file_path":"codebook/purpose/v00.md"}}' | \
        .venv/Scripts/python scripts/hooks/codebook_guard.py; echo $?
"""
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

CONSOLIDATOR = "codebook-consolidator"
FILE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
SHELL_TOOLS = {"Bash", "PowerShell"}
VERSION_RE = re.compile(r"codebook/(purpose|context)/(?:([a-z0-9][a-z0-9-]*)/)?v\d\d\.md")
# An actual run of the script (python ... scripts/codebook.py <cmd>), not a mention of it in text.
CODEBOOK_CMD = re.compile(r"(?:^|[\s&|;(])[\"']?\S*python[\w.]*[\"']?\s+(?:-\S+\s+)*[\"']?(?:\S*[/\\])?"
                          r"scripts[/\\]codebook\.py[\"']?\s+(\w+)(.*)", re.I)
WRITE_OPS = re.compile(
    r">|\b(rm|rmdir|mv|cp|tee|touch|mkdir|truncate|dd|install|ln|chmod|patch|unzip|tar|rsync)\b|"
    r"\bsed\b[^|;&]*\s-i|\bperl\b[^|;&]*\s-[a-z]*i|\bpython\w*(\.exe)?\b[^|;&]*\s-c\b|"
    r"\bgit\s+(checkout|restore|reset|rm|mv|apply|stash|clean|switch|revert|cherry-pick|merge|pull|am)\b|"
    r"\b(Set-Content|Add-Content|Out-File|Remove-Item|Move-Item|Copy-Item|New-Item|Rename-Item|Clear-Content)\b",
    re.I)


class Blocked(Exception):
    pass


def rel_path(p: str, cwd: str | None = None) -> str | None:
    """Repo-relative POSIX path of p, or None if it is outside the repo."""
    path = Path(p)
    if not path.is_absolute():
        path = Path(cwd or ROOT) / path
    a = os.path.normcase(os.path.abspath(path))
    r = os.path.normcase(os.path.abspath(ROOT))
    if a != r and not a.startswith(r + os.sep):
        return None
    # keep the real case for the series name: take the tail of the original absolute path
    return os.path.abspath(path)[len(r) + 1:].replace("\\", "/")


def labels_db() -> Path:
    return Path(os.environ.get("LABELS_DB", ROOT / "labels/labels.db"))


def frozen(taxonomy: str, variant: str) -> bool:
    db = labels_db()
    if not db.exists():
        return False
    con = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return con.execute("SELECT 1 FROM codebook_versions WHERE taxonomy = ? AND variant = ? AND frozen = 1",
                           (taxonomy, variant)).fetchone() is not None
    except sqlite3.OperationalError:  # no such table yet
        return False
    finally:
        con.close()


def committed(rel: str) -> bool:
    import codebook
    return bool(codebook.commits_touching(rel))


def in_codebook(rel: str | None) -> bool:
    return rel is not None and (rel.lower() == "codebook" or rel.lower().startswith("codebook/"))


def check_file(rel: str, agent: str | None, *, is_frozen=frozen, is_committed=committed, root=ROOT) -> None:
    who = f"agent {agent!r}" if agent else "the main session"
    if agent != CONSOLIDATOR:
        raise Blocked(f"{who} may not write to codebook/ ({rel}). Only the codebook-consolidator agent writes "
                      "codebook versions; humans approve them (CLAUDE.md).")
    m = VERSION_RE.fullmatch(rel)
    if not m:
        raise Blocked(f"{rel} is not a codebook version file (codebook/<taxonomy>/[<variant>/]vNN.md); "
                      "the consolidator only edits version files.")
    taxonomy, variant = m.group(1), m.group(2) or "main"
    if is_frozen(taxonomy, variant):
        raise Blocked(f"the {taxonomy}/{variant} codebook is frozen (#43); no more edits to it.")
    if not (Path(root) / rel).exists():
        raise Blocked(f"{rel} does not exist. Create new versions only with "
                      f"`.venv/Scripts/python scripts/codebook.py next {taxonomy} --round N`, then edit that file.")
    if is_committed(rel):
        raise Blocked(f"{rel} is a committed codebook version and must never change. Create the next version "
                      f"with `.venv/Scripts/python scripts/codebook.py next {taxonomy} --round N` and edit that.")


def check_shell(command: str, agent: str | None, cwd: str | None = None, *, is_frozen=frozen) -> None:
    if "codebook" not in command.lower():
        return
    who = f"agent {agent!r}" if agent else "the main session"
    for part in re.split(r"&&|\|\||;|\n", command):
        m = CODEBOOK_CMD.search(part)
        if m:
            sub, rest = m.group(1), m.group(2)
            if sub in ("check", "register"):
                continue
            if sub == "next":
                if agent != CONSOLIDATOR:
                    raise Blocked(f"{who} may not create codebook versions; only the codebook-consolidator runs "
                                  "`codebook.py next`.")
                t = re.search(r"\b(purpose|context)\b", rest)
                v = re.search(r"--variant[ =](\S+)", rest)
                if t and is_frozen(t.group(1), v.group(1) if v else "main"):
                    raise Blocked(f"the {t.group(1)} codebook is frozen (#43); no new versions.")
                continue
        if re.search(r"codebook[/\\]", part, re.I) and WRITE_OPS.search(part):
            raise Blocked("shell commands may not write to codebook/. Only the codebook-consolidator edits "
                          "uncommitted version files, with the Edit/Write tools, after `codebook.py next`. "
                          f"Blocked: {part.strip()[:200]}")


def confine_consolidator(tool: str, args: dict, cwd: str | None) -> None:
    """The consolidator works only on codebook version files (#24): no file writes elsewhere, and
    no shell command except running `codebook.py check` / `codebook.py next`."""
    if tool in FILE_TOOLS:
        rel = rel_path(args.get(FILE_TOOLS[tool]) or "", cwd)
        if not in_codebook(rel):
            raise Blocked(f"the codebook-consolidator may only edit codebook version files, not {rel or args}.")
    elif tool in SHELL_TOOLS:
        command = args.get("command") or ""
        parts = [p for p in re.split(r"&&|\|\||;|\n|\|", command) if p.strip()]
        for part in parts or [""]:
            m = CODEBOOK_CMD.search(part)
            if not m or m.group(1) not in ("check", "next") or re.search(r"[<>`$]", part):
                raise Blocked("the codebook-consolidator may only run `.venv/Scripts/python scripts/codebook.py "
                              f"check` or `... next <taxonomy> --round N`. Blocked: {command.strip()[:200]}")


def decide(event: dict, *, is_frozen=frozen, is_committed=committed, root=ROOT) -> None:
    """Raise Blocked if the tool call must not run."""
    tool, args = event.get("tool_name"), event.get("tool_input") or {}
    agent, cwd = event.get("agent_type"), event.get("cwd")
    if agent == CONSOLIDATOR:
        confine_consolidator(tool, args, cwd)
    if tool in FILE_TOOLS:
        rel = rel_path(args.get(FILE_TOOLS[tool]) or "", cwd)
        if in_codebook(rel):
            check_file(rel, agent, is_frozen=is_frozen, is_committed=is_committed, root=root)
    elif tool in SHELL_TOOLS:
        check_shell(args.get("command") or "", agent, cwd, is_frozen=is_frozen)


def main():
    raw = sys.stdin.read()
    try:
        decide(json.loads(raw))
    except Blocked as e:
        print(f"Codebook guard (#33): {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:  # fail closed only when the call is about the codebook
        if "codebook" in raw.lower():
            print(f"Codebook guard (#33) failed ({type(e).__name__}: {e}); blocking to be safe.", file=sys.stderr)
            sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
