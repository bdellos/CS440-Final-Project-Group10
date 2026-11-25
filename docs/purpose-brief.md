# Purpose codebook framing (input for v01, #40)

The researchers' framing decisions for the first purpose codebook. Unlike the context brief, this
one sets no categories: v01 is built bottom-up from the Round 0 open codes (consolidator mode A).
It only fixes what a category describes, how many to aim for, and which codes are the input.

## Decisions (2026-11-25, Brendan)

1. **Inputs: runs 4 and 5 only.** Run 4 is the open-coder agent (46 fine codes), run 5 is Brendan
   (12 broad codes). Run 6 (Ryan) is not used: its category list was made with AI assistance (note
   on run 6). It stays in the database and is disclosed in the report.
2. **Axis: the kind of work a skill codifies.** A category is the activity or kind of knowledge
   the skill gives an agent: what the developer has written down for the agent to do or know (for
   example testing, review and validation, writing code, operating infrastructure). The subject
   area alone (finance, video, Kubernetes, a particular API) is not a category: a skill that
   reviews Kubernetes manifests is a review skill. Codes that name only a subject area are placed
   by the kind of work their skills do; if that can't be told from the code, list them as
   unplaced.
3. **Granularity: about 10-15 categories.** Coarse enough for kappa on a 50-skill held-out set and
   for a readable cross-tab with the 6 context categories. Fine codes fold under them; don't keep a
   category for a single fine code unless no other category could hold it.
4. A catch-all for skills whose purpose can't be told is allowed (as in the context codebook).

## Decisions after round 1

### 2026-11-25: version control, and four boundaries (v02)

Round 1 (run 19, v01, 100 skills) made no proposals, but 24 labels note an imperfect fit. The
researchers read those notes and decided (Brendan):

1. **New category `version-control`: Version control and code hosting.** Skills that run or set
   rules for source-control work: staging and committing, commit messages, branching, pull
   requests, merging, rebasing, pushing, changelog and release steps.
   - Include: commit-and-push helpers; PR size, branch-protection and merge rules; preparing and
     submitting a pull request; merging feature or stacked branches.
   - Exclude: reviewing the code in a pull request (`review-validate`); operating a hosted service's
     issues, inbox or settings through its API (`integrate-external`); CI/CD pipelines and build
     tooling (`configure-operate`).
   - Examples:
     - `00cd790c1e4e9914e7e8d56fcc1c50ee07ce78ca`: "Analyze all uncommitted changes, generate a comprehensive yet succinct commit message, stage, commit, and push in one step."
     - `006bc2290cedf0d7d5743fbb65d00b3e16d1cbc9`: "Prepares and submits a pull request for feature or bugfix work."
     - `005dc0cb2c08aa3dc10144ee2e291a332219c543`: "Safely merge feature branches, bookmarks, and stacked changes into main."
   Place it after `write-code`. Add matching Exclude entries where other categories currently take
   git or PR work (`integrate-external`, `configure-operate`).
2. **`write-content` Include:** generating or formatting documentation (API reference documents,
   documentation formats), even when a build step produces it.
3. **`configure-operate` Include:** running local tools and automating the operating system (a local
   CLI, AppleScript window control). **`integrate-external`** stays for external services that hold
   the user's data or accounts (APIs, SaaS, connectors); add that to its Exclude.
4. **`design-plan` Include:** UI and visual design rules (colour, UI states). **`write-code`
   Include:** library and API usage guides for writing code against them.

Round 1 yields one new category (fewer than 2), so the purpose codebook is frozen at v02 (#43).
This category came from the researchers reading the labeler's notes, not from an agent proposal;
the report says so.

## Why

The challenge asks *what developers codify in skills*. The kind of work answers that directly and
is comparable across domains; the domain is mostly visible from the skill name and repository
anyway. The earlier three-way draft (kept in `analysis/round0/purpose-v01-draft-threeway.md`)
mixed both axes and followed the agent's fine codes too closely.
