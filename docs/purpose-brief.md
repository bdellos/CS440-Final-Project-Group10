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

## Why

The challenge asks *what developers codify in skills*. The kind of work answers that directly and
is comparable across domains; the domain is mostly visible from the skill name and repository
anyway. The earlier three-way draft (kept in `analysis/round0/purpose-v01-draft-threeway.md`)
mixed both axes and followed the agent's fine codes too closely.
