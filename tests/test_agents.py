"""Static checks for the subagent definitions in .claude/agents/ (step 5, #21-#27).
Behaviour (including each agent's prompt-injection test) is checked by running the agent; these
tests catch definition mistakes before that.
    .venv/Scripts/python -m pytest tests/test_agents.py
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import models  # noqa: E402
import permissions  # noqa: E402

AGENTS = ROOT / ".claude/agents"
FILES = sorted(AGENTS.glob("*.md"))
SKILLS = ROOT / ".claude/skills"


def body(path):
    """The agent's prompt without frontmatter, whitespace collapsed (prose wraps anywhere)."""
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", path.read_text(encoding="utf-8"), count=1, flags=re.S)
    return " ".join(text.split())


def test_model_and_permission_checks_pass():
    assert models.check()[0] == []
    assert permissions.check()[0] == []


@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
def test_frontmatter(path):
    fm = models.frontmatter(path)
    assert fm.get("name") == path.stem
    assert len(fm.get("description", "")) >= 50, "the main session picks agents by their description"
    assert "Agent" not in (permissions.agent_tools(path) or []), "subagents must not spawn subagents"


@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
def test_preloaded_skills_exist(path):
    import prompts
    m = re.search(r"^skills:\s*\n((?:\s+-\s+.+\n)+)", path.read_text(encoding="utf-8"), re.M)
    for skill in re.findall(r"-\s+(\S+)", m.group(1)) if m else []:
        assert (SKILLS / skill / "SKILL.md").is_file(), f"{path.stem} preloads missing skill {skill}"
    assert prompts._list_field(path.read_text(encoding="utf-8"), "skills") == (
        re.findall(r"-\s+(\S+)", m.group(1)) if m else [])


@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
def test_says_material_is_data(path):
    text = body(path)
    assert re.search(r"data, never instructions", text, re.I), "every agent must say the material is data"
    assert "Never follow" in text


def test_sampler_draws_once_after_a_dry_run():
    text = body(AGENTS / "sampler.md")
    assert "dry_run: true" in text and "dry_run: false" in text
    assert "Draw once" in text and "do not invent it" in text
