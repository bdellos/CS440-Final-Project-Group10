# Context codebook brief (input for v01, #41)

The researchers' brief for the first context codebook. The codebook-consolidator turns it into
`codebook/context/v01.md`; the researchers approve that file. Validation on the Round 0 repos and
later rounds refine it.

## What is classified

The **repository** a skill lives in (the repo of the skill's representative copy in the dataset),
not the skill. The question is what the repository is *for*, and so what role its `SKILL.md` files
play there. One main kind per repository; a second only when the repository clearly serves two
purposes. Judge by the repository's own account (README, description) checked against what it
contains (files, number of skills, activity). Forks are classified by what they contain.

## Kinds

Keys are permanent once v01 is committed.

### `operational-project`: Operational project
The repository exists to build or run something else (an application, library, service, tool,
research code), and its skills support work on it.
- Include: source code dominates; a few skills tied to the project's own stack or conventions.
- Exclude: repositories meant to be copied as a starting point (`template`); repositories whose
  product is the skills themselves (`skill-catalog`).
- Examples:
  - `n8n-io/n8n`: "Fair-code workflow automation platform with native AI capabilities."
  - `mem0ai/mem0`: "Universal memory layer for AI Agents"

### `skill-catalog`: Catalog or collection of skills
The skills themselves are the product: the repository collects, curates, lists or distributes
skills for others to install or copy.
- Include: curated or "awesome" lists, registries, marketplaces, official skill collections.
- Exclude: one or a few skills used for the repository's own work (`operational-project`); a
  handful of skills written to teach how skills work (`demonstration`).
- Examples:
  - `ComposioHQ/awesome-claude-skills`: "A curated list of awesome Claude Skills, resources, and tools for customizing Claude AI workflows"
  - `laravel/agent-skills`: "Laravel official collection of agent skills"

### `template`: Template or starter
The repository is meant to be copied as the start of a new project.
- Include: repositories marked as GitHub templates; starters, boilerplates, scaffolds, starter kits.
- Exclude: guides that only contain copy-paste snippets (`demonstration`).
- Examples:
  - `epicweb-dev/epic-stack`: "This is a Full Stack app starter with the foundational things setup and configured for you to hit the ground running on your next EPIC idea."
  - `fullstackhero/dotnet-starter-kit`: "Production Grade Cloud-Ready .NET 10 Starter Kit"

### `demonstration`: Demonstration, example or tutorial
The repository shows how something works or teaches it, and is not meant for real use as is.
- Include: examples, demos, tutorials, guides, courses, workshop or talk material.
- Exclude: starters meant to be copied and filled in (`template`).
- Examples:
  - `luongnv89/claude-howto`: "A visual, example-driven guide to Claude Code"
  - `Unity-Technologies/PhysicsExamples2D`: "Examples of various Unity 2D Physics components and features."

### `personal-config`: Personal configuration
A person's own environment setup: dotfiles, editor and shell configuration, personal agent setup,
with skills as part of that configuration.
- Include: dotfiles repositories; personal Claude Code or agent configuration.
- Exclude: configuration published for others to copy as a starting point (`template`).
- Examples:
  - `freekmurze/dotfiles`: "My personal dotfiles"
  - `jackfranklin/dotfiles`: "My dotfiles for my dev environment, compromising of tmux, vim, zsh and git."

### `unclear`: Unclear or other
The kind can't be told from the repository (empty or missing README, deleted repository with
little metadata), or it fits none of the kinds above. Use sparingly; a repository that fits a kind
imperfectly gets that kind. During validation, repeated "other" cases with something in common
should become `PROPOSED_NEW` instead, for the researchers to decide.
- Examples:
  - `zhu637882-stack/jiaoyi`: "test" (the whole description; nothing says what the repository is for)

## Notes for the consolidator

- Write each kind in the codebook format (`codebook/README.md`). Definitions one or two sentences.
- Use the example quotes exactly as given; they are the repositories' dataset descriptions.
- Keep the kinds consistent with `.claude/skills/repo-context-heuristics/SKILL.md`, which gives the
  classifier signals for them; report any place where the two disagree.
