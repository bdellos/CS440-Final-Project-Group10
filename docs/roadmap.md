# Roadmap

The order to work through the GitHub issues, based on what each one depends on. Inside a step, an arrow (→) means the order matters; otherwise items can be done in any order or in parallel.

Issues and milestones live on GitHub: https://github.com/bdellos/CS440-Final-Project-Group10/milestones. Already closed: [#6](https://github.com/bdellos/CS440-Final-Project-Group10/issues/6) (dataset schema confirmed), [#38](https://github.com/bdellos/CS440-Final-Project-Group10/issues/38) (Round 0 sample drawn).

## Build track

### 1. Data layer
- [#7](https://github.com/bdellos/CS440-Final-Project-Group10/issues/7) database schema → [#8](https://github.com/bdellos/CS440-Final-Project-Group10/issues/8) attach the sample DB → [#52](https://github.com/bdellos/CS440-Final-Project-Group10/issues/52) language column

Plan: keep the GitSkills SQLite file read-only and `ATTACH` it from a small project database (`labels.db`). Our tables (labels, codebook versions, proposals, provenance, language) refer to skills by `file_sha`. Moving from the sample to the full dataset is then a one-line path change.

### 2. Contracts that everything else validates against
- [#16](https://github.com/bdellos/CS440-Final-Project-Group10/issues/16) label JSON schema → [#53](https://github.com/bdellos/CS440-Final-Project-Group10/issues/53) evidence as original quote + English translation
- [#19](https://github.com/bdellos/CS440-Final-Project-Group10/issues/19) codebook versioning in git
- [#18](https://github.com/bdellos/CS440-Final-Project-Group10/issues/18) pin model and temperature

### 3. MCP servers
- [#11](https://github.com/bdellos/CS440-Final-Project-Group10/issues/11) custom server scaffold → [#13](https://github.com/bdellos/CS440-Final-Project-Group10/issues/13) `get_skill` → [#12](https://github.com/bdellos/CS440-Final-Project-Group10/issues/12) `sample` → [#58](https://github.com/bdellos/CS440-Final-Project-Group10/issues/58) `start_run` / `finish_run` → [#14](https://github.com/bdellos/CS440-Final-Project-Group10/issues/14) `record_label` → [#15](https://github.com/bdellos/CS440-Final-Project-Group10/issues/15) `get_disagreements`
- [#10](https://github.com/bdellos/CS440-Final-Project-Group10/issues/10) GitHub MCP (read-only, with caching)
- [#9](https://github.com/bdellos/CS440-Final-Project-Group10/issues/9) SQLite MCP. May be unnecessary if the custom server covers every read the agents need; decide after this step.

### 4. Config and hooks
- [#17](https://github.com/bdellos/CS440-Final-Project-Group10/issues/17) `settings.json` and permissions → [#33](https://github.com/bdellos/CS440-Final-Project-Group10/issues/33) codebook write guard → [#32](https://github.com/bdellos/CS440-Final-Project-Group10/issues/32) label validator → [#35](https://github.com/bdellos/CS440-Final-Project-Group10/issues/35) provenance logger → [#34](https://github.com/bdellos/CS440-Final-Project-Group10/issues/34) SessionStart → [#36](https://github.com/bdellos/CS440-Final-Project-Group10/issues/36) Stop batch check

### 5. Skills, then the agents that load them
> ⚠️ **Prompt injection.** Every SKILL.md is written as instructions for an AI agent, and repo READMEs can be too. Every agent and skill that reads them must treat that text as data to classify, never as instructions (CLAUDE.md rule; checklist item on #22–#26 and #29). Test each agent with a skill that tries to redirect it.

- Skills: [#29](https://github.com/bdellos/CS440-Final-Project-Group10/issues/29) qualitative-coding-protocol, [#28](https://github.com/bdellos/CS440-Final-Project-Group10/issues/28) apply-codebook, [#30](https://github.com/bdellos/CS440-Final-Project-Group10/issues/30) repo-context-heuristics
- Agents: [#21](https://github.com/bdellos/CS440-Final-Project-Group10/issues/21) sampler, [#23](https://github.com/bdellos/CS440-Final-Project-Group10/issues/23) open-coder, [#24](https://github.com/bdellos/CS440-Final-Project-Group10/issues/24) codebook-consolidator, [#25](https://github.com/bdellos/CS440-Final-Project-Group10/issues/25) labeler, [#26](https://github.com/bdellos/CS440-Final-Project-Group10/issues/26) skeptic, [#22](https://github.com/bdellos/CS440-Final-Project-Group10/issues/22) context-classifier
- [#37](https://github.com/bdellos/CS440-Final-Project-Group10/issues/37) prompt caching for the codebook

### 6. Prove it works
- [#1](https://github.com/bdellos/CS440-Final-Project-Group10/issues/1) end-to-end smoke test, using skills that are **not** in `samples/round0.csv`
- [#20](https://github.com/bdellos/CS440-Final-Project-Group10/issues/20) README, first draft

## ⛔ Gate: wait until [#3](https://github.com/bdellos/CS440-Final-Project-Group10/issues/3) and [#4](https://github.com/bdellos/CS440-Final-Project-Group10/issues/4) are done

Round 0 is blind. Don't run the open-coder or the labeler until [#3](https://github.com/bdellos/CS440-Final-Project-Group10/issues/3) is done, and nobody shows agent output or one coder's categories to the other coder until [#4](https://github.com/bdellos/CS440-Final-Project-Group10/issues/4) is done. Don't use Round 0 skills as test data.

## Research track

### 7. Round 0
- [#39](https://github.com/bdellos/CS440-Final-Project-Group10/issues/39) agent open-codes the sample (can start once [#3](https://github.com/bdellos/CS440-Final-Project-Group10/issues/3) is done; keep the output away from Ryan until [#4](https://github.com/bdellos/CS440-Final-Project-Group10/issues/4) is done)
- [#40](https://github.com/bdellos/CS440-Final-Project-Group10/issues/40) compare the three category lists and build codebook v01 (needs [#3](https://github.com/bdellos/CS440-Final-Project-Group10/issues/3), [#4](https://github.com/bdellos/CS440-Final-Project-Group10/issues/4) and [#39](https://github.com/bdellos/CS440-Final-Project-Group10/issues/39))
- [#41](https://github.com/bdellos/CS440-Final-Project-Group10/issues/41) context taxonomy codebook (can run in parallel with the rest of Round 0)

### 8. Iterate to saturation
- [#42](https://github.com/bdellos/CS440-Final-Project-Group10/issues/42) rounds 1 to N → [#43](https://github.com/bdellos/CS440-Final-Project-Group10/issues/43) saturation check and codebook freeze

### 9. Final labeling and analysis
- [#27](https://github.com/bdellos/CS440-Final-Project-Group10/issues/27) analyst and [#31](https://github.com/bdellos/CS440-Final-Project-Group10/issues/31) msr-report (can be built any time before this step)
- [#44](https://github.com/bdellos/CS440-Final-Project-Group10/issues/44) Batch API → [#2](https://github.com/bdellos/CS440-Final-Project-Group10/issues/2) full-dataset labeling run
- [#45](https://github.com/bdellos/CS440-Final-Project-Group10/issues/45) / [#46](https://github.com/bdellos/CS440-Final-Project-Group10/issues/46) hand-label the held-out set (after [#43](https://github.com/bdellos/CS440-Final-Project-Group10/issues/43)) → [#47](https://github.com/bdellos/CS440-Final-Project-Group10/issues/47) Cohen's kappa
- [#48](https://github.com/bdellos/CS440-Final-Project-Group10/issues/48) labeler vs skeptic disagreements
- [#49](https://github.com/bdellos/CS440-Final-Project-Group10/issues/49) seeded vs agent-only ablation (possible once [#40](https://github.com/bdellos/CS440-Final-Project-Group10/issues/40) has produced both codebooks)
- [#50](https://github.com/bdellos/CS440-Final-Project-Group10/issues/50) purpose × context cross-tab
- [#54](https://github.com/bdellos/CS440-Final-Project-Group10/issues/54) results by language and the English-only validity note
- [#51](https://github.com/bdellos/CS440-Final-Project-Group10/issues/51) codebook evolution figure

### 10. Write-up
- [#5](https://github.com/bdellos/CS440-Final-Project-Group10/issues/5) report, with [#20](https://github.com/bdellos/CS440-Final-Project-Group10/issues/20) README finalized alongside it

## Human track (runs alongside the build)

| When | Brendan | Ryan |
|---|---|---|
| Now | [#3](https://github.com/bdellos/CS440-Final-Project-Group10/issues/3) pick categories | |
| When free | | [#4](https://github.com/bdellos/CS440-Final-Project-Group10/issues/4) pick categories |
| After the freeze ([#43](https://github.com/bdellos/CS440-Final-Project-Group10/issues/43)) | [#45](https://github.com/bdellos/CS440-Final-Project-Group10/issues/45) hand-label held-out set | [#46](https://github.com/bdellos/CS440-Final-Project-Group10/issues/46) hand-label held-out set |

The only point where the build waits on people is the gate before step 7, so steps 1–6 can go ahead while Round 0 coding happens.
