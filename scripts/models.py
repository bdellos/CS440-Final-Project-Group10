"""Pinned model and effort per agent (issue #18).

config/models.json is the single source of truth. This module:
  * checks that each .claude/agents/<name>.md pins exactly the configured `model:` and `effort:`
    (full model IDs only: an alias like `haiku` would drift to newer models);
  * detects environment variables that would silently override a pinned effort in Claude Code;
  * gives run_settings(agent) so every run records the model and effort it was configured with.

    .venv/Scripts/python scripts/models.py check      # exit 1 on any mismatch or override

Temperature can't be set on current Claude models, so it is not part of the config;
runs.temperature stays NULL and reproducibility rests on model + effort + prompt hash.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config/models.json"
AGENTS_DIR = ROOT / ".claude/agents"

EFFORTS = ("low", "medium", "high", "xhigh", "max")
ALIASES = {"sonnet", "opus", "haiku", "fable", "inherit"}
# Environment variables that override a subagent's `effort:` frontmatter in Claude Code.
OVERRIDE_VARS = ("CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_SUBAGENT_EFFORT")
_MODEL_ID = re.compile(r"^claude-[a-z]+(-\d+)+$")
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def load_config(path=None) -> dict:
    cfg = json.loads(Path(path or CONFIG).read_text(encoding="utf-8"))
    problems = []
    for name, s in {**cfg["agents"], "batch": cfg["batch"]}.items():
        if not _MODEL_ID.match(s.get("model", "")):
            problems.append(f"config: {name}: model must be a full model ID like claude-haiku-5-5, got {s.get('model')!r}")
        if s.get("effort") not in EFFORTS:
            problems.append(f"config: {name}: effort must be one of {EFFORTS}, got {s.get('effort')!r}")
    if problems:
        raise ValueError("\n".join(problems))
    return cfg


def run_settings(agent: str, cfg=None) -> dict:
    """Model and effort to store on a new run for this agent (or 'batch')."""
    cfg = cfg or load_config()
    s = cfg["batch"] if agent == "batch" else cfg["agents"].get(agent)
    if s is None:
        raise KeyError(f"{agent!r} is not in config/models.json")
    return {"model": s["model"], "effort": s["effort"]}


def frontmatter(path: Path) -> dict:
    m = _FRONT.match(path.read_text(encoding="utf-8").lstrip("﻿"))
    out = {}
    for line in (m.group(1).splitlines() if m else []):
        k, sep, v = line.partition(":")
        if sep and not line.startswith((" ", "\t")):
            out[k.strip()] = v.strip().strip("'\"")
    return out


def env_overrides(environ=None) -> list:
    environ = os.environ if environ is None else environ
    return [f"{v}={environ[v]!r} is set and would override the pinned effort; unset it"
            for v in OVERRIDE_VARS if environ.get(v)]


def check(cfg=None, agents_dir=None, environ=None) -> tuple:
    """(problems, notes). Problems fail the check; notes are informational."""
    cfg = cfg or load_config()
    agents_dir = Path(agents_dir or AGENTS_DIR)
    problems, notes = [], []
    for name, want in cfg["agents"].items():
        f = agents_dir / f"{name}.md"
        if not f.exists():
            notes.append(f"{name}: no agent file yet ({f.relative_to(ROOT) if f.is_relative_to(ROOT) else f})")
            continue
        fm = frontmatter(f)
        model, effort = fm.get("model"), fm.get("effort")
        if model is None:
            problems.append(f"{name}: missing `model: {want['model']}`")
        elif model in ALIASES:
            problems.append(f"{name}: model `{model}` is an alias that changes over time; pin `{want['model']}`")
        elif model != want["model"]:
            problems.append(f"{name}: model is {model!r}, config says {want['model']!r}")
        if effort is None:
            problems.append(f"{name}: missing `effort: {want['effort']}`")
        elif effort != want["effort"]:
            problems.append(f"{name}: effort is {effort!r}, config says {want['effort']!r}")
    if agents_dir.exists():
        for f in sorted(agents_dir.glob("*.md")):
            if f.stem not in cfg["agents"]:
                problems.append(f"{f.stem}: agent file has no entry in config/models.json")
    problems += env_overrides(environ)
    return problems, notes


def main():
    if sys.argv[1:] != ["check"]:
        sys.exit(__doc__)
    try:
        problems, notes = check()
    except ValueError as e:
        problems, notes = str(e).splitlines(), []
    for n in notes:
        print(f"  note: {n}")
    for p in problems:
        print(f"- {p}")
    print("models check:", "ok" if not problems else f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
