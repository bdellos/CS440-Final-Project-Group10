# GitSkills Taxonomy: Agentic Pipeline Plan

Plan for the CS440 final: an agent pipeline for MSR 2027 Mining Challenge 1.2, building a taxonomy of what developers codify in skills and the contexts where skills appear. Living doc version: https://claude.ai/artifact/HDa6TkTDXSiLb47AdqKpQS

## Seeded vs free-rein categories

Use a hybrid: the agent proposes categories, and the two of us decide which ones enter the codebook. Both pure approaches have a known failure mode:

- **Seeded first:** the agent anchors on our categories and forces edge cases into them, so the taxonomy reflects what we expected to find.
- **Free rein:** categories multiply at mixed granularity ("git workflows" beside "commit message formatting" beside "DevOps"), with synonyms and drift between batches.

This is the deductive vs inductive coding tension from qualitative research, which MSR reviewers will recognize. We can turn the choice into a result:

1. **Round 0, blind and parallel.** Each of us drafts categories from the same ~50-skill sample, and an agent open-codes those 50 with no seeds. The overlap and gaps across the three lists are a finding.
2. **Rounds 1 to N, merged codebook plus an escape hatch.** The agent labels a new batch with the merged codebook and must emit `PROPOSED_NEW` with justification and quoted evidence when nothing fits. We accept, merge or reject each proposal.
3. **Stop at saturation.** Freeze the codebook when a batch of 100 yields fewer than ~2 accepted new categories.
4. **Final labeling.** The agent applies the frozen codebook to everything. We both hand-label a held-out set and report Cohen's kappa for agent vs each of us and between the two of us.

```
Round 0 -> Merged codebook -> Agent labels batch -> Saturated?
              ^                                        | no
              +------ We accept, merge or reject <-----+
                                                       | yes
                         Final labeling <- Freeze codebook
```

**Two taxonomies, not one.** The challenge asks about purpose (what a skill codifies) and context (operational project, catalog, template, demo). Build two classifiers and cross-tabulate them. A result like "catalogs are mostly X, operational repos mostly Y" is likely the headline.

## Subagents

Each subagent gets one narrow job, limited tools and a fixed output format.

| Subagent | Job | Tools |
| --- | --- | --- |
| Sampler | Stratified samples by repo type and size; drops near-duplicate skills, since catalogs copy each other heavily | Dataset/DB only |
| Context classifier | Labels repo type from README, file tree, stars and commit activity | GitHub MCP, read-only |
| Open coder | Round 0 only: free-form codes, each with an evidence quote | Read-only |
| Codebook consolidator | Merges synonyms, keeps granularity consistent, writes definition, include/exclude rules and examples per category | Only agent allowed to write the codebook |
| Labeler | Applies the frozen codebook and emits schema-valid JSON | Read skill, write labels |
| Skeptic / second rater | Labels independently or argues against the Labeler; disagreements go to us | Read-only |
| Analyst | Cross-tabs, frequencies, charts, agreement stats | Python, DB |

The Skeptic is cheap and yields agent-vs-agent disagreement data for the threats-to-validity section.

## Skills

Using skills to study skills is a nice meta angle for the write-up.

- **`apply-codebook`**: SKILL.md holds the labeling procedure. The codebook itself is not copied into the skill: the agent calls `get_codebook(run_id)`, which returns the exact version its run was started with, read from the commit it was registered at (decided in #28, so a copy can never drift from the run).
- **`qualitative-coding-protocol`**: how to quote evidence, when to multi-label, when to use `PROPOSED_NEW`.
- **`repo-context-heuristics`**: signals per repo type, e.g. a `skills/` folder with 40+ unrelated skills and no app code means a catalog.
- **`msr-report`**: the format for the paper's tables and figures.

How the pieces differ:

- **Config** (`settings.json`, agent definitions): which agents exist and which tools and hooks each gets.
- **Subagent:** a worker with its own context and one narrow job.
- **Skill:** a procedure plus reference material a worker loads when relevant.
- **README:** for humans; how to rerun the pipeline and what each piece does.

## MCPs

- **GitHub MCP:** repo metadata, READMEs, file trees and commit history for context classification. Watch rate limits and cache aggressively.
- **SQLite or DuckDB MCP:** one database for skills, labels, codebook versions and rationales, instead of hundreds of JSON files.
- **Small custom MCP server** (good learning exercise): tools like `sample(stratum, n)`, `get_skill(id)`, `record_label(id, labels, evidence, codebook_version)` and `get_disagreements()`. All writes go through validated tools, not free-form file edits.

## Hooks

| Hook | What it does |
| --- | --- |
| PostToolUse validator | Checks every label write against a JSON schema; rejects malformed output or unknown categories |
| PreToolUse guard | Blocks codebook writes from any agent but the consolidator, and from everyone after the freeze |
| SessionStart | Loads the current codebook version and round number into context |
| Provenance logger | Records model, codebook version, prompt hash and timestamp per label, for reproducibility |
| Stop / SubagentStop | Confirms every item in the batch got a label; computes batch agreement automatically |

## Other practices

- **Pin model and temperature** and record both, for reproducibility.
- **Prompt caching** for the codebook, which rides along on every labeling call; **Batch API** for the final full-dataset pass to cut cost.
- **Codebook in git**, one commit per round. The diff history shows how the taxonomy evolved and makes a good figure.
- **Ablation:** label the same sample with the seeded codebook and the agent-only one, then compare. This answers the seeded-vs-free-rein question directly and could be its own paper section.

**Open assumption:** context classification assumes each skill in the [GitSkills dataset](https://huggingface.co/datasets/mvaccargiu/gitskills) links back to its source repo. To confirm against the [preprint](https://arxiv.org/pdf/2608.10906) schema or the [sample dataset](https://github.com/giuseppedestefanis/gitskills-sample).
