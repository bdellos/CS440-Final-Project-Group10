# CS440 Group 10 Final Project: GitSkills Challenge 1.2

**What do developers codify in agent skills, and in which contexts do skills appear?**
This is our entry for the [MSR 2027 Mining Challenge](https://2027.msrconf.org/track/msr-2027-mining-challenge). We study the [GitSkills dataset](https://huggingface.co/datasets/mvaccargiu/gitskills) of `SKILL.md` files mined from GitHub ([preprint](https://arxiv.org/pdf/2608.10906)) and build two taxonomies, then cross-tabulate them:

1. **Purpose**: what a skill codifies.
2. **Context**: what kind of repository it lives in (operational project, catalog, template, demo, ...).

No taxonomy of skill purposes exists yet, so we build one with **human-gated, agent-assisted qualitative coding**: Claude Code agents label skills and propose categories; the two researchers decide.

## How it works

| Stage | Who | What happens |
|---|---|---|
| Round 0 | Both researchers + the open-coder agent | Code the same 50 skills independently and blind, then merge the three code lists into codebook v01 |
| Rounds 1..N | Labeler agent, researchers | The labeler applies the codebook to a new batch and proposes a new category (`PROPOSED_NEW`) when none fits; the researchers accept, merge or reject each proposal; the codebook-consolidator writes the next version |
| Freeze | Researchers | Stop when a batch of 100 yields fewer than ~2 accepted new categories |
| Final labeling | Labeler, skeptic, researchers | Agents label with the frozen codebook; the researchers hand-label a held-out set for Cohen's kappa |
| Analysis | Analyst agent | Frequencies, agreement, purpose x context cross-tab |

More info: the full design and its rationale are in [docs/plan.md](docs/plan.md); progress and issue order are in [docs/roadmap.md](docs/roadmap.md).

**Status:** the pipeline, its agents and their tests are built. Round 0 hand coding is in progress, and no real labels exist yet. The analyst and the report come last.

## Repository map

| Path | Contents |
|---|---|
| `scripts/` | Python pipeline: database, sampling, validation, MCP servers, test harness |
| `scripts/hooks/` | Claude Code hooks that enforce the study's rules |
| `.claude/agents/`, `.claude/skills/` | The agents and the skills they load |
| `config/` | Pinned model, effort and tools for every agent |
| `codebook/` | Versioned codebooks (`purpose/vNN.md`, `context/vNN.md`) |
| `schemas/label.schema.json` | Shape of every label record |
| `labels/dump.sql` | Text dump of the project database (samples, runs, labels) |
| `samples/round0.csv` | The Round 0 sample |
| `tests/` | Unit tests and agent test fixtures |
| `CLAUDE.md` | Standing rules for every agent working in this repo |

## Setup

Requires Windows with Python 3.15, git, and [Claude Code](https://code.claude.com) (CLI or VS Code extension) signed in. On macOS or Linux, use `.venv/bin/python` wherever this README says `.venv/Scripts/python`.

1. **Python environment** (from the repo root):
   ```
   py -3.15 -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```
2. **Dataset sample** (13,000 distinct skills), cloned into the ignored `data/` folder:
   ```
   git clone https://github.com/giuseppedestefanis/gitskills-sample data/gitskills-sample
   Expand-Archive data/gitskills-sample/agent_skills_sample.zip data/gitskills-sample/agent_skills_sample
   ```
3. **Project database**: restore the committed samples and runs, then rebuild the skill list and language detection from the dataset (about 10 seconds on the sample):
   ```
   .venv\Scripts\python scripts\db_dump.py --restore
   .venv\Scripts\python scripts\load_dataset.py
   ```
4. **Git hooks**, once per clone (runs the codebook check before commits):
   ```
   git config core.hooksPath .githooks
   ```
5. **Claude Code**: open the repo folder and accept the "trust this folder" prompt. The project settings then load and approve the two MCP servers (`pipeline` and `github`) automatically.
6. **GitHub token** (optional; needed only for context labeling at scale): create a fine-grained token with "Public repositories (read-only)" access and no other permissions, and set it as the user environment variable `GITSKILLS_GITHUB_TOKEN`. Without it, GitHub allows 60 requests an hour. Restart Claude Code afterwards.
7. **Check**:
   ```
   .venv\Scripts\python -m pytest tests                      # about 365 tests, ~1 minute
   .venv\Scripts\python scripts\pipeline_server.py --status  # dataset, samples, runs, config checks
   ```

## Running the pipeline

The work is done by asking Claude Code, in the repo, to delegate to an agent. The main session starts each run and hands the agent its `run_id`. Examples:

- *"Use the sampler agent to draw a sample named round1 of 100 skills with seed 7."*
- *"Start a labeler run on round1 with purpose codebook v01, then delegate it to the labeler agent."*
- *"Derive the repo sample of round1 with the sampler, then run the context-classifier on it."*

Every session starts with a status summary (codebook versions, samples, open runs, config checks), printed by a hook. To see it by hand: `.venv\Scripts\python scripts\hooks\session_start.py`. When an agent finishes, `finish_run` closes the run and reports agreement with other runs on the same sample.

A few steps are done by the researchers outside Claude Code: creating and registering codebook versions (`scripts/codebook.py`, see [codebook/README.md](codebook/README.md)), starting human runs (`scripts/runs.py`), and committing `labels/dump.sql` after each round (`scripts/db_dump.py`).

## Agents

All agents run on Claude Haiku 5.5, the cheapest model, with model, effort and tools pinned in [config/](config/). Skill text and READMEs are treated as data, never as instructions.

| Agent | Job |
|---|---|
| sampler | Draws stratified, de-duplicated samples; derives the repo sample of a skill sample. [More info on the sampler agent](.claude/agents/sampler.md) |
| open-coder | Round 0 only: free-form codes with no codebook, blind by construction. [More info on the open-coder agent](.claude/agents/open-coder.md) |
| labeler | Applies the purpose codebook with quoted evidence; proposes new categories. [More info on the labeler agent](.claude/agents/labeler.md) |
| skeptic | Independent second rater with a stricter reading of each category. [More info on the skeptic agent](.claude/agents/skeptic.md) |
| context-classifier | Labels repositories from their README, files, history and metadata. [More info on the context-classifier agent](.claude/agents/context-classifier.md) |
| codebook-consolidator | Writes the next codebook version from codes or decided proposals. [More info on the codebook-consolidator agent](.claude/agents/codebook-consolidator.md) |
| analyst | Statistics and figures (planned, [#27](https://github.com/bdellos/CS440-Final-Project-Group10/issues/27)) |

Skills the agents load: [qualitative-coding-protocol](.claude/skills/qualitative-coding-protocol/SKILL.md) (evidence, language and labeling rules), [apply-codebook](.claude/skills/apply-codebook/SKILL.md) (labeling procedure), [repo-context-heuristics](.claude/skills/repo-context-heuristics/SKILL.md) (signals for repo types).

## MCP servers

Agents read data and write labels only through these tools, which validate everything before storing it.

- **pipeline**: samples, skills, codebooks, runs, labels, disagreements. [More info on the pipeline server](scripts/pipeline_server.py)
- **github**: read-only, cached repo context for context labeling. [More info on the github server](scripts/github_server.py)

## Safeguards (hooks)

| Hook | What it enforces |
|---|---|
| [Codebook guard](scripts/hooks/codebook_guard.py) | Only the consolidator edits `codebook/`, and only a new, uncommitted version; nothing changes after a freeze |
| [Labels guard](scripts/hooks/labels_guard.py) | Agents can't write labels except through `record_label` |
| [Rater guard](scripts/hooks/rater_guard.py) | Each agent labels only its own run, so provenance is accurate |
| [Session start](scripts/hooks/session_start.py) | Loads the pipeline status and flags config problems |
| [Batch check](scripts/hooks/batch_check.py) | Sends an agent back if its batch has gaps; asks for `finish_run` when a batch is done |

Every label also records a hash of the exact instructions its agent ran with, so results can be traced and reproduced.

## Testing

- `.venv\Scripts\python -m pytest tests` runs the unit tests (no API calls).
- `.venv\Scripts\python scripts\agent_harness.py run labeler` runs one agent end to end on synthetic fixtures, including skills that try to hijack it, and checks it labels them on their merits. `... chain` runs sampler, context-classifier, labeler and skeptic in sequence. These use Claude Code (a few cents of Haiku each, inside the plan) and never touch real data. [More info on the agent test harness](scripts/agent_harness.py)

## Team

Brendan Dellos and Ryan Wright (CS440 Group 10).
