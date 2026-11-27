# Roadmap

The order to work through the GitHub issues, based on what each one depends on. Inside a step, an arrow (→) means the order matters; otherwise items can be done in any order or in parallel. ✅ marks a closed issue.

Issues and milestones live on GitHub: https://github.com/bdellos/CS440-Final-Project-Group10/milestones.

**Status (2026-11-26):** done apart from the write-up. Both codebooks are frozen (purpose v02, context v03), 1,000 skills are labeled for both taxonomies, the held-out kappa is computed, and the results are in `analysis/results/`. Open: the report ([#5](https://github.com/bdellos/CS440-Final-Project-Group10/issues/5)), the README's last pass ([#20](https://github.com/bdellos/CS440-Final-Project-Group10/issues/20)) and the language caveat in the report ([#54](https://github.com/bdellos/CS440-Final-Project-Group10/issues/54)).

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

### 6. Prove it works ✅
- ✅ [#1](https://github.com/bdellos/CS440-Final-Project-Group10/issues/1) end-to-end smoke test: passed on fixtures (sampler → context-classifier → labeler → skeptic); the real `smoke1` run was superseded by the same chain running on real data in every round.
- [#20](https://github.com/bdellos/CS440-Final-Project-Group10/issues/20) README: final version in PR #78; last pass after the report ([#5](https://github.com/bdellos/CS440-Final-Project-Group10/issues/5)).

## Gate: Round 0 coding ✅ ([#3](https://github.com/bdellos/CS440-Final-Project-Group10/issues/3), [#4](https://github.com/bdellos/CS440-Final-Project-Group10/issues/4))

Both researchers finished their Round 0 workbooks (2026-11-25); they are committed in `coding/round0/`.

## Research track ✅

### 7. Round 0 (purpose) ✅
- ✅ [#64](https://github.com/bdellos/CS440-Final-Project-Group10/issues/64) consolidator harness test, in a throwaway worktree
- ✅ [#39](https://github.com/bdellos/CS440-Final-Project-Group10/issues/39) agent open-codes the Round 0 sample; both workbooks imported as human open-coding runs (`scripts/import_round0.py`)
- ✅ [#40](https://github.com/bdellos/CS440-Final-Project-Group10/issues/40) purpose v01 from the agent's and one researcher's codes; which lists were used and why, and the framing: `docs/purpose-brief.md`
- ✅ [#41](https://github.com/bdellos/CS440-Final-Project-Group10/issues/41) context codebook: v01 from the researchers' brief, refined to v03

### 8. Iterate to saturation ✅
- ✅ [#42](https://github.com/bdellos/CS440-Final-Project-Group10/issues/42) one round per taxonomy (100 skills each) → ✅ [#43](https://github.com/bdellos/CS440-Final-Project-Group10/issues/43) both froze after round 1: purpose v02 (one new category, `version-control`), context v03 (no new categories)

### 9. Final labeling and analysis ✅
- ✅ [#2](https://github.com/bdellos/CS440-Final-Project-Group10/issues/2) final labeling: 1,000 skills from the sample dataset for both taxonomies (no full-dataset run, by budget; ~~[#44](https://github.com/bdellos/CS440-Final-Project-Group10/issues/44) Batch API~~ not used). Purpose runs before the `get_skill` full-text fix were relabeled.
- ✅ [#45](https://github.com/bdellos/CS440-Final-Project-Group10/issues/45) hand-labeled held-out set (Brendan); ~~[#46](https://github.com/bdellos/CS440-Final-Project-Group10/issues/46)~~ Ryan's not supplied → ✅ [#47](https://github.com/bdellos/CS440-Final-Project-Group10/issues/47) Cohen's kappa (`analysis/kappa.md`)
- ✅ [#48](https://github.com/bdellos/CS440-Final-Project-Group10/issues/48) labeler vs skeptic, ✅ [#50](https://github.com/bdellos/CS440-Final-Project-Group10/issues/50) purpose × context cross-tab, ✅ [#51](https://github.com/bdellos/CS440-Final-Project-Group10/issues/51) codebook evolution figure: `analysis/results/`
- [#54](https://github.com/bdellos/CS440-Final-Project-Group10/issues/54) results by language: tables done; the English-only kappa caveat goes in the report
- ~~[#27](https://github.com/bdellos/CS440-Final-Project-Group10/issues/27) analyst agent~~ not built (scripts in `analysis/` instead); ~~[#49](https://github.com/bdellos/CS440-Final-Project-Group10/issues/49) seeded vs agent-only ablation~~ not done

### 10. Write-up
- [#5](https://github.com/bdellos/CS440-Final-Project-Group10/issues/5) report, with [#20](https://github.com/bdellos/CS440-Final-Project-Group10/issues/20) README finalized alongside it

## Human track ✅

| When | Brendan | Ryan |
|---|---|---|
| ✅ Round 0 | [#3](https://github.com/bdellos/CS440-Final-Project-Group10/issues/3) Round 0 coding | [#4](https://github.com/bdellos/CS440-Final-Project-Group10/issues/4) Round 0 coding |
| ✅ Codebook rounds | Approved purpose v01, v02 and context v01-v03; decided all proposals | |
| ✅ After the freeze | [#45](https://github.com/bdellos/CS440-Final-Project-Group10/issues/45) hand-labeled held-out set | [#46](https://github.com/bdellos/CS440-Final-Project-Group10/issues/46) not supplied |
