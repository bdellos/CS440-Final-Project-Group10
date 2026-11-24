"""Shared test setup.

record_label stores a prompt_hash over the rater's agent definition (#35), and the real
.claude/agents/ files don't exist yet (step 5). Every test therefore gets a throwaway .claude/
with a minimal agent file for each agent in config/models.json; tests about provenance itself
use the `claude_dir` fixture to change those files.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import models  # noqa: E402
import prompts  # noqa: E402


@pytest.fixture(autouse=True)
def claude_dir(tmp_path_factory, monkeypatch):
    d = tmp_path_factory.mktemp("repo") / ".claude"
    (d / "agents").mkdir(parents=True)
    for name, s in models.load_config()["agents"].items():
        (d / "agents" / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: test agent\nmodel: {s['model']}\neffort: {s['effort']}\n---\n"
            f"Test instructions for {name}.\n", encoding="utf-8")
    monkeypatch.setattr(prompts, "CLAUDE_DIR", d)
    return d
