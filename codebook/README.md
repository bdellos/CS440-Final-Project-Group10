# Codebooks

Two taxonomies, each a series of versions:

```
codebook/
  purpose/v00.md, v01.md, ...        what a skill codifies (labels skills)
  context/v00.md, v01.md, ...        what kind of repo it lives in (labels repos)
  purpose/<variant>/v00.md, ...      ablation variants (#49), e.g. purpose/seeded/
```

`v00` is an empty template. `v01` is the first real codebook (from Round 0, #40).

## Rules

1. **Never edit a past version.** Each `vNN.md` is committed once and never changed afterwards. To change the codebook, create the next version:
   ```
   .venv/Scripts/python scripts/codebook.py next purpose --round 3
   ```
   This copies the latest version to `v(N+1).md`, updates its header, and prints the commit message.
2. **One commit per round**, containing the new version file (and `labels/dump.sql`):
   ```
   codebook: purpose v03 (round 3)
   ```
3. **Only the codebook-consolidator agent writes here** (enforced by the PreToolUse guard, #33). Humans approve each version before it's committed.
4. **Register a committed version** so labels can be validated against it:
   ```
   .venv/Scripts/python scripts/codebook.py register codebook/purpose/v03.md
   ```
5. **Check everything** (format, numbering, immutability):
   ```
   .venv/Scripts/python scripts/codebook.py check
   ```

## Format

A version file is Markdown with a small header. Each category is a `##` heading of the form `key: Name`, where `key` is a lowercase slug that never changes once introduced (labels refer to it). Every category needs all four `###` sections.

```markdown
---
taxonomy: purpose
variant: main
version: 3
based_on: 2
round: 3
---

# Purpose codebook v03

Optional notes about this version: what changed and why.

## category-key: Category name

### Definition
One or two sentences: what belongs in this category.

### Include
- A kind of skill that belongs here.

### Exclude
- A near miss that belongs elsewhere, and where it goes instead.

### Examples
- 0123456789abcdef0123456789abcdef01234567: "verbatim quote from that skill"
```

Examples start with the item they come from, so they can be traced back to the data: the skill's `file_sha` in the purpose codebook, `owner/repo` in the context codebook. Anything inside `<!-- -->` comments is ignored.
