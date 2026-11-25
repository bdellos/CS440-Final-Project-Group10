<!-- Saved 2026-11-25: verbatim copy of the uncommitted codebook/purpose/v01.md that the
codebook-consolidator wrote in mode A from runs 4 (open-coder), 5 (brendan) and 6 (ryan).
On hold pending the question about how run 6 was produced (#40). Kept as the record of the
three-way merge; the sources/unplaced comments are the overlap-and-gaps data. -->

---
taxonomy: purpose
variant: main
version: 1
based_on: 0
round: 0
---
# Purpose codebook v01

First real purpose codebook, built from the Round 0 open codes (#40): the open-coder agent (run 4), brendan (run 5) and ryan (run 6). Codes that name the same purpose were merged; the merged codes are listed under each category in the sources comments. Coarse rater codes (for example "Validation", "DevOps") were placed by where most of their items fall; codes that could not be placed are listed in the unplaced comment at the end.

## review-audit: Review and audit existing work

### Definition
Reviewing, auditing or validating an existing artifact (code change, architecture, document, configuration, model code) against quality, correctness, governance or compliance criteria.

### Include
- Reviewing source changes for bugs, security or code quality.
- Checking an implementation against approved architecture or design artifacts.
- Checking controls against compliance requirements.
- Validating a configuration or model against stated requirements.

### Exclude
- Writing tests or test cases for new code: goes to testing-qa.
- Reviewing UI usability or accessibility: goes to ux-accessibility.
- Triaging incoming GitHub issues and PRs: goes to workflow-automation.

### Examples
- 00fa616f2fc02bcead4010afb32e1ffcf619cfc4: "Review source files changed during a phase for bugs, security issues, and code quality problems"
- 00aa3df86cbfbc66b433f1f5633f3ea37481df3b: "Audit implementation shape against approved architecture and design artifacts for governance parity."
- 01b3c0eab4a503155700fbb3f95eb471f3b95c00: "Cross-check a document's controls against its declared compliance regimes"

<!-- sources: open-coder: review code changes, critically review artifacts, audit architecture alignment, verify compliance controls, validate automation job templates, validate physics model code; ryan: Code Review, auditing and compliance -->

## testing-qa: Testing and test-driven development

### Definition
Writing, selecting or guiding tests, test cases, test fixtures and test-driven implementation.

### Include
- Defining test cases or acceptance criteria before implementation.
- Writing test fixtures and mock patterns.
- Choosing testing frameworks for a platform.
- Guiding a red-green-refactor workflow.

### Exclude
- Reviewing existing code for bugs or quality: goes to review-audit.
- Writing the implementation plan itself: goes to plan-orchestrate.

### Examples
- 00181699d0e3b40ea90dbbd48e7757c84f51783f: "Define test cases BEFORE implementation, ensuring every API, business rule, and user journey has verifiable acceptance criteria"
- 0064c87c258a180bdbde72d3beede9ac6d9ae3a8: "Testing frameworks for web, mobile, API, and unit testing"
- 00562419b4b03388123490d294289ef0d96a957c: "Pytest fixture strategies, mock patterns, and service-specific testing quirks for aithena Python services"

<!-- sources: open-coder: guide test-driven implementation, select testing frameworks, write python test fixtures, write test cases; brendan: Testing; ryan: Testing and Quality Assurance -->

## ux-accessibility: UX, UI and accessibility

### Definition
Reviewing or designing user experience, interface usability, accessibility and design consistency, including adding delight to user-facing products.

### Include
- Checking text and UI contrast against WCAG.
- Aligning UI changes with a design system.
- Finding opportunities for playful micro-interactions.

### Exclude
- Reviewing code changes for general bugs or quality: goes to review-audit.
- Writing editorial copy or articles: goes to content-creation.

### Examples
- 00366eef12736b1e0b1f2a3fe0ef7e796be5e48d: "Verify text and non-text contrast against WCAG 2.2"
- 00705c4be9874ef9df72434646bb6145b3f0ce56: "Ensures usability, accessibility, and design consistency; aligns UI with project design system."
- 008cdc2c173557b6f4e3d07bfce1b936e94a0621: "This skill identifies opportunities to add personality, delight, and playful moments to user experiences."

<!-- sources: open-coder: review ui accessibility, add ux delight; ryan: User experience and accessibility, User experience and accessibility/code review -->

## network-ops: Network engineering and operations

### Definition
Designing, validating or operating network topologies, lab environments and packet captures.

### Include
- Validating network or lab topology designs.
- Starting and stopping packet captures on network links.

### Exclude
- Configuring API routes or gateways: goes to integrations-tools.

### Examples
- 00e56bc7f964fa0e3b38466fd0a25b6041c3159e: "Start and stop packet captures on links in GNS3 projects."
- 00814eb2877cad99547f99b5db369687f0232c19: "Validate EVE-NG topology designs and enforce final delivery structure."

<!-- sources: open-coder: capture network traffic, validate network topology; brendan: Tool usage; ryan: Network Engineering and Operations -->

## build-deploy-infra: Build and deployment infrastructure

### Definition
Configuring builds and dependencies, and designing or operating deployment infrastructure and supporting services such as caching.

### Include
- Configuring build tooling, dependencies and artifact generation.
- Designing cluster or platform architecture.
- Implementing a caching layer in production.

### Exclude
- Designing database schemas or advising on database administration: goes to database.
- Building API gateway routes: goes to integrations-tools.

### Examples
- 00c38e92580c2bc2e0908b2c85eed0af2f6bb5e2: "Use this skill when configuring builds, dependencies, testing, or artifact generation using Gradle."
- 00b73439353d835887e8f6af756b30fa3d297a63: "Designing Kubernetes platform architecture or multi-cluster strategy"
- 00fbe1da5f7c75ae27deb720339ca04c73b69b8f: "Implement Redis as a production support layer, not as a second database."

<!-- sources: open-coder: configure build tooling, design kubernetes infrastructure, implement redis caching; ryan: Build, Deployment and infrastructure Operations -->

## database: Database design and administration

### Definition
Designing data models, and advising on or administering databases.

### Include
- Designing and maintaining data models for integrity and scalability.
- Advising on database administration for a specific engine.

### Exclude
- Implementing Redis or other caching layers: goes to build-deploy-infra.

### Examples
- 0005bfdfffae9c0aa20b16c806c33b47bb41cc1c: "MongoDB expert advisor with fact-checked, version-aware guidance."
- 009584131d0b60ba50b2ab531c46ae93c7cdd045: "Guidelines for designing, implementing, and maintaining high-quality data models"

<!-- sources: open-coder: advise database administration, design data models; ryan: Database design and administration -->

## integrations-tools: Tool, API and integration development

### Definition
Building or configuring tools, API connections and integrations, such as MCP servers, API gateways, cloud storage and API skill packages.

### Include
- Building MCP servers that expose tools to AI clients.
- Configuring API gateway routes.
- Integrating third-party storage or APIs into an application.
- Finding and installing API skill packages.

### Exclude
- Automating routine tasks in existing tools (GitHub, email): goes to workflow-automation.
- Writing documentation about a tool or service: goes to documentation-knowledge.

### Examples
- 0067f5d456dc4b20c89b831e44f6cea72eeb2dd4: "Build production-quality MCP (Model Context Protocol) servers that expose tools, resources, and prompts"
- 00edc0dd19af8650c443922dec54804c2aef2947: "Designing and configuring API routes on APISIX"
- 008cd8b2dab7277393d342b83caf391f0595e233: "Integrate Vercel Blob object storage for file uploads, image management, and CDN-delivered assets in Next.js applications."
- 00203e0ea4418c3d09a779562031c07466ed02b2: "Manage Polymer Pay API skills - search, fetch, and install locally."

<!-- sources: open-coder: build mcp servers, configure api gateway, implement cloud file storage, find and install api skills; brendan: API usage, Code creation; ryan: Tool, API and Integration Development -->

## documentation-knowledge: Documentation and knowledge management

### Definition
Writing, maintaining or managing documentation, specifications, design documents, notes and incident reports.

### Include
- Writing technical design documents before implementation.
- Maintaining a cumulative system specification.
- Managing documentation spaces in Confluence.
- Generating structured incident postmortems.

### Exclude
- Keeping agent memory or session context for future runs: goes to context-memory.
- Generating editorial copy or articles: goes to content-creation.

### Examples
- 0140b6b237b0efe6d340f419c327bc4977a077fd: "You are helping the user compact closed specs into the system specification (`SYSTEM-SPEC.md`), which is the cumulative behavioral record of everything the project does and why."
- 00b56fd8884f2d6cd0067ebe232bff2439eb99b1: "Auto-generates a structured postmortem from a completed campaign."
- 006370aed1d3dfba12470bf51af6bafb49baa91e: "Atlassian Confluence expert for creating and managing spaces, knowledge bases, and documentation."

<!-- sources: open-coder: generate incident postmortem, maintain system specification, manage confluence documentation, manage org notes, write design documents; brendan: DevOps; ryan: Documentation and knowledge management -->

## context-memory: Agent memory and project context

### Definition
Keeping persistent memory, session context or codebase maps so that an agent starts future work informed by earlier sessions and by the project.

### Include
- Reading and writing a learnings or memory file across sessions.
- Recovering session context at the start of a session.
- Mapping codebase modules and symbols for an area of a project.

### Exclude
- Writing standalone documentation or specifications: goes to documentation-knowledge.
- Planning or dispatching a new piece of work: goes to plan-orchestrate.

### Examples
- 009f6859aecb945a798af8ce89b38a1675290746: "Read + write the per-pair learnings.md file so the running agent builds up institutional knowledge over time"
- 00e9d1dc478bca25eeb3565c42a781b2e69aa658: "**Activates:** every session start (before design or code)."
- 003cd0b9c1c6f7cbfe2b470fc5b5cd3195c884ee: "Skill for the Adaptive-learning area of rinkuzu. 54 symbols across 20 files."

<!-- sources: open-coder: maintain agent memory notes, map codebase modules, restore session context; brendan: Project knowledge; ryan: Agent Context/ Memory Management -->

## workflow-automation: Developer and office workflow automation

### Definition
Automating recurring tasks in developer tools and services, such as GitHub repositories and issues, email, and re-running stored pipelines.

### Include
- Managing GitHub repositories through the GitHub CLI.
- Triaging GitHub issues and PRs against templates.
- Automating email tasks through an MCP integration.
- Re-running stored pipeline runs.

### Exclude
- Building the tool or integration itself: goes to integrations-tools.
- Reviewing code changes for quality: goes to review-audit.

### Examples
- 006b86d5adb18c3aa56723bd9e505a6cce4e3d4a: "Automate Gmail tasks via Rube MCP (Composio): send/reply, search, labels, drafts, attachments."
- 00e785a3197b960d10e0f366f0eabf1fce7af552: "This skill helps manage GitHub repositories using GitHub CLI (gh)."
- 00076c3cfabfd0e211079180b2cec3477fff432a: "Triage and review open GitHub issues and PRs against project templates and contribution guidelines."

<!-- sources: open-coder: automate email tasks, manage github repositories, replay pipeline runs, triage github inbox; ryan: Developer Productivity and Workflow automation -->

## plan-orchestrate: Planning and orchestrating work

### Definition
Planning, sequencing, executing or dispatching multi-step work, including coordination across multiple agents.

### Include
- Starting a multi-agent project or feature.
- Executing a written implementation plan with review checkpoints.
- Picking up and executing queued agent tasks.

### Exclude
- Writing the design document that a plan is based on: goes to documentation-knowledge.
- Writing tests for the planned work: goes to testing-qa.

### Examples
- 00fcf2d40b84249f369934644c892ade85425e1e: "Start a new project/feature with multi-agent collaboration (Opus 4.6 + Agent Teams)."
- 0033699eb5500379694d489a4183436e9be98e41: "Use when you have a written implementation plan to execute in a separate session with review checkpoints"
- 01695901e62b50f80863a70170f2f4e621308d0b: "Pick up one queued instruction, execute it, then publish a structured report."

<!-- sources: open-coder: execute written plans, plan multi-agent project, process queued agent tasks; ryan: Multi-Agent Workflow/Software development and implementation, Project Planning and Coordination -->

## content-creation: Writing and visual content creation

### Definition
Writing, editing or producing editorial copy and visual content such as quote-highlight visuals.

### Include
- Creating and editing articles, headlines and site copy.
- Producing visual beats or quote-highlight visuals from transcripts.

### Exclude
- Post-production of finished video (captions, disclaimers) and downloading media: goes to media-processing.
- Writing technical documentation: goes to documentation-knowledge.

### Examples
- 008ee81c318e9b83f0e14fa9d49e65fb28eb59f9: "Create and edit copy for SwissCapital.news so it consistently sounds institutional, calm, analytical, and globally aware."
- 012b3423c7c58532a8e0496dff28c76044120633: "Make a selected spoken line land as a reviewable quote-highlight visual support proposal with transcript evidence and render verification."

<!-- sources: open-coder: produce video visuals, write editorial copy; brendan: Non-code content; ryan: Content Creation and Editing -->

## media-processing: Media download and post-production

### Definition
Downloading online media and processing or post-producing audio and video files.

### Include
- Downloading video, audio, playlists and subtitles.
- Adding captions or legal disclaimers to a finished video.

### Exclude
- Creating visual content or copy from a transcript: goes to content-creation.

### Examples
- 001d2557bc83de4d51172676c49c88f648037270: "Download video, audio, playlists, subtitles, and metadata with yt-dlp."
- 00bbfca09e5705082d83f14645f0bf7413c97b7f: "Burn captions and/or the legal disclaimer onto a finished video as a SEPARATE post-production step"

<!-- sources: open-coder: download online media; ryan: Media Processing and Production -->

## research-summarize: Research and summarization

### Definition
Researching an external topic or market, summarizing external sources, or mapping what is known about a topic.

### Include
- Summarizing a video, article, issue or repository.
- Producing a cited market or competitor report.
- Generating a knowledge map for a topic.

### Exclude
- Analyzing datasets or building dashboards and models: goes to data-models-dashboards.

### Examples
- 00a15635eb311dd05052cb594d719783dd731081: "Summarize any content — YouTube video, Medium article, Jira issue, GitHub repo, AWS/Amazon blog, or Slack thread."
- 00fdf30b13f5605d2c122250ccfb016f043a1390: "produces one consolidated, cited market+competitor report"
- 00a90a0cac2c384a26449bfe84839b7d8ac85930: "Generate a four-quadrant knowledge map for any topic or rough seed"

<!-- sources: open-coder: conduct market research, map knowledge gaps, summarize external content; ryan: Information Retrieval and Synthesis, Research and information synthesis -->

## data-models-dashboards: Quantitative models and dashboards

### Definition
Building quantitative or financial models, dashboards and analytical reports from data.

### Include
- Building macroeconomic or rates dashboards.
- Implementing mathematical models of financial patterns.

### Exclude
- Summarizing external sources or market research: goes to research-summarize.
- Designing database schemas: goes to database.

### Examples
- 00134ec76942976714a6ed9533e6b9536ab8b020: "Build macroeconomic and rates dashboards combining macro indicators, yield curves, inflation breakevens, and swap rates."
- 00f4706300a33f1c6e4da329052f0f3326537fdc: "This skill enforces high-performance mathematical modeling of financial regime-switching patterns"

<!-- sources: open-coder: build financial market dashboards, implement regime-switching models; ryan: Data Analysis & Reporting, Data Analysis and Reporting -->

<!-- unplaced: brendan: Validation (9 items; 3 review-audit, 2 build-deploy-infra, 1 each database, workflow-automation, ux-accessibility, network-ops: too spread to place); brendan: Data analysis (6 items: 2 research-summarize, 1 each media-processing, review-audit, plan-orchestrate, data-models-dashboards); brendan: Data generation (4 items, one each in documentation-knowledge, content-creation, research-summarize, workflow-automation); brendan: Agent info (3 items, one each in context-memory, ux-accessibility, plan-orchestrate); brendan: Other (catch-all label; 00bbfc to media-processing, 003cd0 to context-memory); ryan: Domain-Specific Technical Analysis (split: 015c2c to review-audit, 003cd0 to context-memory); ryan: Software Development and Implementation (split: 003369 to plan-orchestrate, 01a176 to testing-qa) -->
