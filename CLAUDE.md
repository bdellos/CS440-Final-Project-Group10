# CLAUDE.md — GitSkills Taxonomy (CS440 Final)

Standing context for Claude Code in this repo. Full design rationale lives in `docs/plan.md`; read it before changing the pipeline.

## Goal

MSR 2027 Mining Challenge, GitSkills Challenge 1.2:
**What do developers codify in skills, and in which contexts do skills appear** (operational projects, catalogs, templates, demonstrations)? No taxonomy of skill purposes exists yet; we are building one.

We produce **two taxonomies** and cross-tabulate them:
1. **Purpose** — what a skill codifies.
2. **Context** — what kind of repo it lives in (operational project, catalog, template, demo, ...).

## Data

- Full dataset: https://huggingface.co/datasets/mvaccargiu/gitskills
- Sample for testing: https://github.com/giuseppedestefanis/gitskills-sample
- Preprint (schema, collection method): https://arxiv.org/pdf/2608.10906
- Challenge page: https://2027.msrconf.org/track/msr-2027-mining-challenge

Develop against the **sample** first. Do not run anything over the full dataset without being asked.

> TODO: confirm the dataset schema (field names, whether each skill links to its source repo) and record it here.

## Method (summary)

Human-gated iterative coding. The agent proposes categories; the humans decide.

1. **Round 0** — both teammates and an agent open-code the same ~50 skills, blind and independently.
2. **Rounds 1..N** — agent labels a new batch with the merged codebook; emits `PROPOSED_NEW` (with justification + quoted evidence) when nothing fits. Humans accept, merge or reject.
3. **Saturation** — freeze the codebook when a batch of 100 yields fewer than ~2 accepted new categories.
4. **Final labeling** — agent applies the frozen codebook; humans hand-label a held-out set; report Cohen's kappa.

## Repo layout (planned)

```
CLAUDE.md               # this file (agent context)
README.md               # for humans: how to run the pipeline
docs/plan.md            # design doc
.claude/
  agents/               # subagent definitions (one file per agent)
  skills/               # skills, e.g. apply-codebook/SKILL.md
  settings.json         # tools, permissions, hooks
codebook/
  purpose/vNN.md        # one file per version; never edit a frozen version
  context/vNN.md
data/                   # local cache of dataset slices (gitignored if large)
labels/                 # label outputs, or a SQLite/DuckDB file
analysis/               # stats, figures
schemas/label.schema.json
```

## Subagents

| Agent | Job | May write |
|---|---|---|
| sampler | stratified samples, dedup near-duplicates | `data/` |
| context-classifier | repo type from README, tree, stars, activity | `labels/` |
| open-coder | Round 0 free-form codes with evidence | `labels/round0/` |
| codebook-consolidator | merge synonyms, write definitions + include/exclude + examples | `codebook/` (only this agent) |
| labeler | apply codebook, emit schema-valid JSON | `labels/` |
| skeptic | independent second rater / argues against labeler | `labels/` |
| analyst | cross-tabs, frequencies, kappa, figures | `analysis/` |

## Rules for agents

- **Only `codebook-consolidator` writes to `codebook/`.** After freeze, nobody does.
- **Never edit a past codebook version**; create the next `vNN`.
- Every label must validate against `schemas/label.schema.json` and include: item id, labels, quoted evidence, `codebook_version`, model id.
- Category changes are **proposals** for the humans, not decisions.
- Keep outputs reproducible: pin model and temperature; log them with each label.
- Cache GitHub API responses; respect rate limits.

## Conventions

- Python 3, scripts in `scripts/` or `analysis/`, runnable from repo root.
- One commit per codebook round (`codebook: purpose v03 (round 3)`).
