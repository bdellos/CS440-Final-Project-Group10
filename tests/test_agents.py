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


def test_open_coder_is_blind_by_construction():
    """Round 0 (#3, #4, #39): the open-coder can't reach any file or codebook that could seed
    categories, and never puts its codes in its reply, where people could see them."""
    path = AGENTS / "open-coder.md"
    tools = set(permissions.agent_tools(path))
    assert not tools & {"Read", "Glob", "Grep", "Bash", "Write", "Edit", "WebFetch", "WebSearch",
                        "mcp__pipeline__get_codebook", "mcp__pipeline__get_disagreements"}
    assert not any(t.startswith("mcp__github__") for t in tools)
    text = body(path)
    assert "Never list or describe your codes in the reply" in text
    assert "`codebook_version: null`" in text and "No `proposals`" in text
    import prompts
    assert prompts._list_field(path.read_text(encoding="utf-8"), "skills") == ["qualitative-coding-protocol"]


def test_labeler_applies_the_codebook_independently():
    path = AGENTS / "labeler.md"
    import prompts
    assert prompts._list_field(path.read_text(encoding="utf-8"), "skills") == [
        "qualitative-coding-protocol", "apply-codebook"]
    tools = set(permissions.agent_tools(path))
    assert {"mcp__pipeline__get_codebook", "mcp__pipeline__record_label"} <= tools
    text = body(path)
    assert "Call `get_codebook` with it first" in text
    assert "Never start, finish or switch runs yourself" in text
    assert "reply with numbers only" in text and "Do not list the labels you gave" in text


def test_skeptic_is_an_independent_sceptical_second_rater(monkeypatch):
    """#26: independent labeling only (never the labeler's output), same codebook and skills as the
    labeler, but a different stance, so the two runs aren't the same rater twice."""
    import prompts
    monkeypatch.setattr(prompts, "CLAUDE_DIR", ROOT / ".claude")  # the real files, not conftest's stubs
    skeptic, labeler = AGENTS / "skeptic.md", AGENTS / "labeler.md"
    assert prompts._list_field(skeptic.read_text(encoding="utf-8"), "skills") == \
        prompts._list_field(labeler.read_text(encoding="utf-8"), "skills")
    assert set(permissions.agent_tools(skeptic)) == set(permissions.agent_tools(labeler))
    assert models.frontmatter(skeptic)["model"] == models.frontmatter(labeler)["model"]
    text = body(skeptic)
    for rule in ("Name the strongest rival", "Apply Exclude rules strictly", "Demand evidence for every label",
                 "Be strict about second labels", "not disagreeing on purpose"):
        assert rule in text
    assert "never see its labels" in text and "Do not list the labels you gave" in text
    assert prompts.prompt_hash(prompts.instruction_files("skeptic")) != \
        prompts.prompt_hash(prompts.instruction_files("labeler"))


def test_consolidator_works_only_through_next_and_its_tools():
    path = AGENTS / "codebook-consolidator.md"
    tools = set(permissions.agent_tools(path))
    assert {"mcp__pipeline__get_codes", "mcp__pipeline__get_proposals", "Edit", "Bash"} <= tools
    assert not tools & {"Write", "Glob", "Grep", "mcp__pipeline__record_label", "mcp__pipeline__get_skill"}
    text = body(path)
    for rule in ("codebook.py next <taxonomy> --round <N>", "Keys are permanent", "Nothing invented",
                 "<!-- sources:", "<!-- unplaced:", "If any proposal for this taxonomy is still pending, stop",
                 "resulting_version_id", "codebook.py check", "after the researchers say Round 0 coding is complete"):
        assert rule in text, rule


def test_context_classifier_reads_repos_before_labeling():
    path = AGENTS / "context-classifier.md"
    import prompts
    assert prompts._list_field(path.read_text(encoding="utf-8"), "skills") == [
        "qualitative-coding-protocol", "apply-codebook", "repo-context-heuristics"]
    tools = set(permissions.agent_tools(path))
    assert {"mcp__github__get_repo_context", "mcp__pipeline__get_codebook", "mcp__pipeline__record_label"} <= tools
    assert "mcp__pipeline__get_skill" not in tools   # it labels repos; it has no skill ids to read
    text = body(path)
    for rule in ("Always do this before labeling", "Classify the repository, not its skills",
                 "never label a repo you could not read", "no `skill_language`", "Do not list the labels you gave"):
        assert rule in text, rule


def test_sampler_draws_once_after_a_dry_run():
    text = body(AGENTS / "sampler.md")
    assert "dry_run: true" in text and "dry_run: false" in text
    assert "Draw once" in text and "do not invent it" in text
