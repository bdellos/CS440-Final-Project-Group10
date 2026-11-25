# Roadmap

The order to work through the GitHub issues, based on what each one depends on. Inside a step, an arrow (→) means the order matters; otherwise items can be done in any order or in parallel. ✅ marks a closed issue.

Issues and milestones live on GitHub: https://github.com/bdellos/CS440-Final-Project-Group10/milestones.

**Status (2026-11-25):** the build track (steps 1–6) is done, apart from the parts of #1 and #20 that wait on later steps. The context codebook (#41) is done (v03, validated on the Round 0 repos). Both researchers have filled in their Round 0 workbooks, so the gate is effectively open: next is the Round 0 purpose flow (step 7).

## Build track ✅

### 1. Data layer ✅
- ✅ [#7](https://github.com/bdellos/CS440-Final-Project-Group10/issues/7) database schema → ✅ [#8](https://github.com/bdellos/CS440-Final-Project-Group10/issues/8) attach the sample DB → ✅ [#52](https://github.com/bdellos/CS440-Final-Project-Group10/issues/52) language column
- Also closed: ✅ [#6](https://github.com/bdellos/CS440-Final-Project-Group10/issues/6) dataset schema confirmed, ✅ [#38](https://github.com/bdellos/CS440-Final-Project-Group10/issues/38) Round 0 sample drawn.

The GitSkills SQLite file stays read-only and is `ATTACH`ed from a small project database (`labels.db`). Our tables refer to skills by `file_sha`, so moving from the sample to the full dataset is a one-line path change.

### 2. Contracts that everything else validates against ✅
- ✅ [#16](https://github.com/bdellos/CS440-Final-Project-Group10/issues/16) label JSON schema → ✅ [#53](https://github.com/bdellos/CS440-Final-Project-Group10/issues/53) evidence as original quote + English translation
- ✅ [#19](https://github.com/bdellos/CS440-Final-Project-Group10/issues/19) codebook versioning in git
- ✅ [#18](https://github.com/bdellos/CS440-Final-Project-Group10/issues/18) pin model and temperature (temperature can't be set; model and effort pinned)

### 3. MCP servers ✅
- ✅ [#11](https://github.com/bdellos/CS440-Final-Project-Group10/issues/11) server scaffold → ✅ [#13](https://github.com/bdellos/CS440-Final-Project-Group10/issues/13) `get_skill` → ✅ [#12](https://github.com/bdellos/CS440-Final-Project-Group10/issues/12) `sample` → ✅ [#58](https://github.com/bdellos/CS440-Final-Project-Group10/issues/58) `start_run` / `finish_run` → ✅ [#14](https://github.com/bdellos/CS440-Final-Project-Group10/issues/14) `record_label` → ✅ [#15](https://github.com/bdellos/CS440-Final-Project-Group10/issues/15) `get_disagreements`
- ✅ [#10](https://github.com/bdellos/CS440-Final-Project-Group10/issues/10) GitHub MCP (read-only, cached)
- ✅ [#9](https://github.com/bdellos/CS440-Final-Project-Group10/issues/9) SQLite MCP: closed as not needed (the custom server covers every read; raw SQL would bypass its validation)
- Added later in step 5: `get_codebook`, `get_codes`, `get_proposals`, `derive_repo_sample`.

### 4. Config and hooks ✅
- ✅ [#17](https://github.com/bdellos/CS440-Final-Project-Group10/issues/17) `settings.json` and permissions → ✅ [#33](https://github.com/bdellos/CS440-Final-Project-Group10/issues/33) codebook write guard → ✅ [#32](https://github.com/bdellos/CS440-Final-Project-Group10/issues/32) label validator → ✅ [#35](https://github.com/bdellos/CS440-Final-Project-Group10/issues/35) provenance logger → ✅ [#34](https://github.com/bdellos/CS440-Final-Project-Group10/issues/34) SessionStart → ✅ [#36](https://github.com/bdellos/CS440-Final-Project-Group10/issues/36) Stop batch check

### 5. Skills, then the agents that load them ✅
> ⚠️ **Prompt injection.** Every SKILL.md and README is treated as data, never instructions. Every rater agent passed a live test with hostile fixtures (#62).

- Skills: ✅ [#29](https://github.com/bdellos/CS440-Final-Project-Group10/issues/29) qualitative-coding-protocol, ✅ [#28](https://github.com/bdellos/CS440-Final-Project-Group10/issues/28) apply-codebook, ✅ [#30](https://github.com/bdellos/CS440-Final-Project-Group10/issues/30) repo-context-heuristics
- Agents: ✅ [#21](https://github.com/bdellos/CS440-Final-Project-Group10/issues/21) sampler, ✅ [#23](https://github.com/bdellos/CS440-Final-Project-Group10/issues/23) open-coder, ✅ [#24](https://github.com/bdellos/CS440-Final-Project-Group10/issues/24) codebook-consolidator, ✅ [#25](https://github.com/bdellos/CS440-Final-Project-Group10/issues/25) labeler, ✅ [#26](https://github.com/bdellos/CS440-Final-Project-Group10/issues/26) skeptic, ✅ [#22](https://github.com/bdellos/CS440-Final-Project-Group10/issues/22) context-classifier
- ✅ [#62](https://github.com/bdellos/CS440-Final-Project-Group10/issues/62) agent test harness: open-coder, labeler, skeptic and context-classifier pass on fixtures, including hostile items
- ✅ [#37](https://github.com/bdellos/CS440-Final-Project-Group10/issues/37) prompt caching: automatic inside Claude Code (80–83% of input cached); Batch API part moved to #44

### 6. Prove it works
- [#1](https://github.com/bdellos/CS440-Final-Project-Group10/issues/1) end-to-end smoke test: **passed on fixtures** (sampler → context-classifier → labeler → skeptic). Still open for the real run on sample `smoke1`, which needs purpose v01 (#40); it ends with the analyst (#27).
- [#20](https://github.com/bdellos/CS440-Final-Project-Group10/issues/20) README: **first draft merged**. Stays open until it's finalised with the report (#5).

## Gate: Round 0 coding ([#3](https://github.com/bdellos/CS440-Final-Project-Group10/issues/3), [#4](https://github.com/bdellos/CS440-Final-Project-Group10/issues/4))

Both researchers finished their Round 0 workbooks (2026-11-25); #3 and #4 can be closed. The workbooks live in the git-ignored `data/round0/`, so keep a backup outside the repo. Rules that still hold: the open-coder works from the skills alone (no seed categories), and Round 0 skills are never used as test data.

## Research track

### 7. Round 0 (purpose)
- [#64](https://github.com/bdellos/CS440-Final-Project-Group10/issues/64) consolidator harness test, in a throwaway worktree (must pass before #40)
- Import both workbooks as human open-coding runs (a small script a person runs; gap noted on [#40](https://github.com/bdellos/CS440-Final-Project-Group10/issues/40) and [#47](https://github.com/bdellos/CS440-Final-Project-Group10/issues/47))
- [#39](https://github.com/bdellos/CS440-Final-Project-Group10/issues/39) agent open-codes the Round 0 sample
- → [#40](https://github.com/bdellos/CS440-Final-Project-Group10/issues/40) the consolidator merges the three code lists into purpose v01; its `sources` / `unplaced` comments are the comparison record
- ✅ [#41](https://github.com/bdellos/CS440-Final-Project-Group10/issues/41) context codebook: v01 from the researchers' brief, refined to v03; runs 2 and 3 agree on all 50 Round 0 repos

### 8. Iterate to saturation
- Before round 1: a script to record the researchers' accept / merge / reject decisions on `PROPOSED_NEW`, and `codebook.py register` setting `resulting_version_id` (gaps noted on [#42](https://github.com/bdellos/CS440-Final-Project-Group10/issues/42))
- [#42](https://github.com/bdellos/CS440-Final-Project-Group10/issues/42) rounds 1 to N (purpose, and context alongside) → [#43](https://github.com/bdellos/CS440-Final-Project-Group10/issues/43) saturation check and codebook freeze

### 9. Final labeling and analysis
- [#27](https://github.com/bdellos/CS440-Final-Project-Group10/issues/27) analyst agent (can be built any time before this step). ✅ [#31](https://github.com/bdellos/CS440-Final-Project-Group10/issues/31) msr-report skill is written, but its file sits at `.claude/skills/msr-report-SKILL.md`; it has to move to `.claude/skills/msr-report/SKILL.md` for Claude Code to load it and for the skill tests to cover it.
- [#44](https://github.com/bdellos/CS440-Final-Project-Group10/issues/44) Batch API (with a cost estimate on a small real batch first) → [#2](https://github.com/bdellos/CS440-Final-Project-Group10/issues/2) full-dataset labeling run
- [#45](https://github.com/bdellos/CS440-Final-Project-Group10/issues/45) / [#46](https://github.com/bdellos/CS440-Final-Project-Group10/issues/46) hand-label the held-out set (after #43) → [#47](https://github.com/bdellos/CS440-Final-Project-Group10/issues/47) Cohen's kappa
- [#48](https://github.com/bdellos/CS440-Final-Project-Group10/issues/48) labeler vs skeptic disagreements
- [#49](https://github.com/bdellos/CS440-Final-Project-Group10/issues/49) seeded vs agent-only ablation (possible once #40 has produced both codebooks)
- [#50](https://github.com/bdellos/CS440-Final-Project-Group10/issues/50) purpose × context cross-tab (context frequencies are per skill)
- [#54](https://github.com/bdellos/CS440-Final-Project-Group10/issues/54) results by language and the English-only validity note
- [#51](https://github.com/bdellos/CS440-Final-Project-Group10/issues/51) codebook evolution figure

### 10. Write-up
- [#5](https://github.com/bdellos/CS440-Final-Project-Group10/issues/5) report, with [#20](https://github.com/bdellos/CS440-Final-Project-Group10/issues/20) README finalized alongside it

## Human track

| When | Brendan | Ryan |
|---|---|---|
| ✅ Done (2026-11-25) | [#3](https://github.com/bdellos/CS440-Final-Project-Group10/issues/3) Round 0 coding | [#4](https://github.com/bdellos/CS440-Final-Project-Group10/issues/4) Round 0 coding |
| Step 7 | Run the workbook import; review purpose v01 | Review purpose v01 |
| Each round (#42) | Accept / merge / reject proposals; approve the next codebook version | Same |
| After the freeze ([#43](https://github.com/bdellos/CS440-Final-Project-Group10/issues/43)) | [#45](https://github.com/bdellos/CS440-Final-Project-Group10/issues/45) hand-label held-out set | [#46](https://github.com/bdellos/CS440-Final-Project-Group10/issues/46) hand-label held-out set |
