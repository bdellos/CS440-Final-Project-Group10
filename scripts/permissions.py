"""Pinned tool access per agent (issue #17).

config/permissions.json is the single source of truth for which tools each subagent gets.
This module checks that:
  * the config covers exactly the agents in config/models.json;
  * no agent is given a main-session-only tool (start_run, finish_run, Agent) or a wildcard;
  * each .claude/agents/<name>.md lists exactly its configured tools in `tools:` (comma-separated
    or a YAML list). A missing `tools:` is an error: the agent would inherit every tool.

    .venv/Scripts/python scripts/permissions.py check      # exit 1 on any problem

Path limits (who may write where) can't be expressed in `tools:`; they live in
.claude/settings.json and the hooks (#33). `may_write` in the config records them for those hooks.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import models  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config/permissions.json"
AGENTS_DIR = ROOT / ".claude/agents"
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def load_config(path=None) -> dict:
    return json.loads(Path(path or CONFIG).read_text(encoding="utf-8"))


def agent_tools(path: Path) -> list | None:
    """The `tools:` of an agent file as a list, or None if it has none."""
    m = _FRONT.match(path.read_text(encoding="utf-8").lstrip("﻿"))
    lines = m.group(1).splitlines() if m else []
    for i, line in enumerate(lines):
        key, sep, value = line.partition(":")
        if not sep or line.startswith((" ", "\t")) or key.strip() != "tools":
            continue
        value = value.strip()
        if value.startswith("["):  # flow list: [a, b]
            value = value.strip("[]")
        if value:
            return [t.strip().strip("'\"") for t in value.split(",") if t.strip()]
        items = []  # block list on the following lines: "  - a"
        for nxt in lines[i + 1:]:
            s = nxt.strip()
            if not s.startswith("- "):
                break
            items.append(s[2:].strip().strip("'\""))
        return items
    return None


def check_config(cfg: dict, model_agents) -> list:
    problems = []
    forbidden = set(cfg.get("main_session_only", []))
    agents = cfg.get("agents", {})
    for name in sorted(set(model_agents) - set(agents)):
        problems.append(f"config: {name} is in config/models.json but has no tools in config/permissions.json")
    for name in sorted(set(agents) - set(model_agents)):
        problems.append(f"config: {name} has tools but no entry in config/models.json")
    for name, a in agents.items():
        tools = a.get("tools")
        if not tools or not isinstance(tools, list):
            problems.append(f"config: {name}: `tools` must be a non-empty list")
            continue
        if len(set(tools)) != len(tools):
            problems.append(f"config: {name}: duplicate tools")
        for t in tools:
            if t in forbidden:
                problems.append(f"config: {name}: {t} is main-session only")
            if "*" in t or re.fullmatch(r"mcp__[^_]+(?:_[^_]+)*", t):
                problems.append(f"config: {name}: {t!r} grants a whole server or a wildcard; list tools one by one")
        if not isinstance(a.get("may_write"), list):
            problems.append(f"config: {name}: `may_write` must be a list of paths")
    return problems


def check(cfg=None, agents_dir=None, model_agents=None) -> tuple:
    """(problems, notes). Problems fail the check; notes are informational."""
    cfg = cfg or load_config()
    agents_dir = Path(agents_dir or AGENTS_DIR)
    if model_agents is None:
        model_agents = models.load_config()["agents"]
    problems, notes = check_config(cfg, model_agents), []
    for name, a in cfg.get("agents", {}).items():
        f = agents_dir / f"{name}.md"
        if not f.exists():
            notes.append(f"{name}: no agent file yet")
            continue
        have = agent_tools(f)
        want = a.get("tools") or []
        if have is None:
            problems.append(f"{name}: no `tools:` line, so it would inherit every tool; add `tools: {', '.join(want)}`")
            continue
        missing, extra = sorted(set(want) - set(have)), sorted(set(have) - set(want))
        if missing:
            problems.append(f"{name}: missing tools from config: {', '.join(missing)}")
        if extra:
            problems.append(f"{name}: tools not in config/permissions.json: {', '.join(extra)}")
    return problems, notes


def main():
    if sys.argv[1:] != ["check"]:
        sys.exit(__doc__)
    try:
        problems, notes = check()
    except (ValueError, json.JSONDecodeError) as e:
        problems, notes = str(e).splitlines(), []
    for n in notes:
        print(f"  note: {n}")
    for p in problems:
        print(f"- {p}")
    print("permissions check:", "ok" if not problems else f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
