"""Prompt provenance (issue #35): which instructions produced a label.

A hook can't see the model's actual prompt, so a label's `prompt_hash` identifies the
instruction files its agent ran with: the agent definition .claude/agents/<rater>.md plus
every file of each skill it preloads (its `skills:` frontmatter, .claude/skills/<skill>/**).

    hash = sha256 over the sorted lines "<path>\\t<sha256 of file>\\n"

File contents are hashed with line endings normalised to LF, so a Windows (CRLF) and a
macOS/Linux checkout of the same commit give the same hash. record_label computes the hash
inside its write transaction and stores the exact file contents once per distinct hash in
prompt_versions, with the git commit and whether the files differed from it, so the
instructions behind every label can be recovered even if they were never committed.

    .venv/Scripts/python scripts/prompts.py labeler      # print the current hash and files
"""
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_DIR = ROOT / ".claude"   # tests point this at a throwaway copy
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


class ProvenanceError(Exception):
    pass


def _list_field(text: str, field: str) -> list:
    """A frontmatter list field (comma-separated, [flow] or YAML block list); [] if absent."""
    m = _FRONT.match(text.lstrip("﻿"))
    lines = m.group(1).splitlines() if m else []
    for i, line in enumerate(lines):
        key, sep, value = line.partition(":")
        if not sep or line.startswith((" ", "\t")) or key.strip() != field:
            continue
        value = value.strip().strip("[]")
        if value:
            return [v.strip().strip("'\"") for v in value.split(",") if v.strip()]
        items = []
        for nxt in lines[i + 1:]:
            s = nxt.strip()
            if not s.startswith("- "):
                break
            items.append(s[2:].strip().strip("'\""))
        return items
    return []


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def instruction_files(rater: str) -> list:
    """[(path relative to the repo, text)] for an agent, sorted by path."""
    base = CLAUDE_DIR.parent
    agent = CLAUDE_DIR / "agents" / f"{rater}.md"
    if not agent.is_file():
        raise ProvenanceError(f"no agent definition {agent.relative_to(base).as_posix()} for rater {rater!r}; "
                              "can't record which instructions produced this label")
    files = {agent}
    for skill in _list_field(_read(agent), "skills"):
        d = CLAUDE_DIR / "skills" / skill
        if not (d / "SKILL.md").is_file():
            raise ProvenanceError(f"agent {rater!r} preloads skill {skill!r}, but "
                                  f"{(d / 'SKILL.md').relative_to(base).as_posix()} doesn't exist")
        files |= {p for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    return sorted(((p.relative_to(base).as_posix(), _read(p)) for p in files))


def prompt_hash(files: list) -> str:
    lines = "".join(f"{path}\t{hashlib.sha256(text.encode('utf-8')).hexdigest()}\n" for path, text in files)
    return "sha256:" + hashlib.sha256(lines.encode("utf-8")).hexdigest()


def _git_state(paths: list) -> tuple:
    """(HEAD commit, whether any of the files differ from it) for files in this repo; (None, None) otherwise."""
    if CLAUDE_DIR.resolve().parent != ROOT:
        return None, None
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", *paths], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.strip()
        return head, bool(dirty)
    except (OSError, subprocess.CalledProcessError):
        return None, None


def record(con: sqlite3.Connection, rater: str) -> str:
    """Hash the rater's current instructions, store them in prompt_versions if new, return the hash.
    Call inside the label's transaction."""
    files = instruction_files(rater)
    h = prompt_hash(files)
    if con.execute("SELECT 1 FROM prompt_versions WHERE prompt_hash = ?", (h,)).fetchone() is None:
        commit, dirty = _git_state([p for p, _ in files])
        con.execute("INSERT INTO prompt_versions (prompt_hash, rater, files, git_commit, uncommitted_changes) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (h, rater, json.dumps([{"path": p, "text": t} for p, t in files], ensure_ascii=False),
                     commit, None if dirty is None else int(dirty)))
    return h


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    fs = instruction_files(sys.argv[1])
    print(prompt_hash(fs))
    for p, _ in fs:
        print(" ", p)
