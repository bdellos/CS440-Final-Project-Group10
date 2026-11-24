-- Project database (labels.db) for the GitSkills taxonomy pipeline.
--
-- Why SQLite (issue #7):
--   * The GitSkills dataset already ships as one SQLite file (277 MB sample, 41 GB full).
--     We ATTACH it read-only as schema `gs` instead of copying it, so skills and repos
--     are never duplicated and switching sample -> full dataset is a path change.
--   * Our own data is small (thousands of labels), written one row at a time by MCP
--     tools and hooks: SQLite's strength. DuckDB is better at big analytical scans,
--     but it could only read the dataset through an extension, and the analyst can
--     still load labels.db into DuckDB or pandas later if a query gets slow.
--   * Zero setup on Windows: the sqlite3 module ships with Python.
--
-- Identifiers that point into the dataset (cannot be foreign keys across ATTACHed files;
-- record_label (#14) checks them instead):
--   * skill   = gs.artifacts.file_sha of the dedup_primary = 1 row (one distinct content)
--   * repo    = gs.repos.full_name
--
-- Taxonomies: 'purpose' labels skills, 'context' labels repos.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Skill attributes we compute (the dataset's own columns stay in gs.artifacts)
-- ---------------------------------------------------------------------------

-- Sampling frame (#8): one row per distinct skill content, built by scripts/load_dataset.py
-- with a single scan of gs.artifacts. Holds only what sampling filters on, never the text,
-- so sample() never has to scan the dataset (content is stored inline: ~41 GB on the full set).
CREATE TABLE IF NOT EXISTS skills (
    file_sha     TEXT PRIMARY KEY,
    repo_full_name TEXT NOT NULL,                    -- the representative's repo (dedup_primary = 1)
    path         TEXT NOT NULL,
    name         TEXT,
    name_key     TEXT,                               -- lower(trim(name)), for one-per-name sampling
    frontmatter_valid INTEGER,
    body_chars   INTEGER,
    location_class TEXT,
    has_scripts  INTEGER,
    has_references INTEGER,
    copies       INTEGER NOT NULL,                   -- file occurrences with this content
    n_repos      INTEGER NOT NULL                    -- distinct repos holding a copy
) STRICT;
CREATE INDEX IF NOT EXISTS skills_sampling ON skills(frontmatter_valid, body_chars);
CREATE INDEX IF NOT EXISTS skills_repo ON skills(repo_full_name);
CREATE INDEX IF NOT EXISTS skills_name ON skills(name_key);

-- Which dataset file the skills table was built from (provenance for every later sample).
CREATE TABLE IF NOT EXISTS dataset_loads (
    load_id      INTEGER PRIMARY KEY,
    dataset_path TEXT NOT NULL,
    dataset_bytes INTEGER NOT NULL,
    dataset_mtime TEXT NOT NULL,
    artifacts    INTEGER NOT NULL,                   -- file occurrences
    distinct_skills INTEGER NOT NULL,
    repos        INTEGER NOT NULL,
    loaded_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
) STRICT;

-- Separate from `skills` so it survives the loader's rebuild of that table:
-- detection is incremental (scripts/detect_languages.py) and re-runs only when the detector changes.
CREATE TABLE IF NOT EXISTS skill_language (          -- populated by #52
    file_sha     TEXT PRIMARY KEY,
    language     TEXT NOT NULL,                      -- 'en', 'zh', 'mixed', 'unknown', ...
    confidence   REAL NOT NULL,
    detector     TEXT NOT NULL,                      -- e.g. 'scripts/language.py langdetect==1.0.9'
    detected_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
) STRICT;

-- ---------------------------------------------------------------------------
-- Samples: named, frozen lists of items (round0, round batches, held-out set, ...)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS samples (
    sample_id    INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,               -- 'round0', 'round1', 'heldout', 'smoke'
    item_kind    TEXT NOT NULL CHECK (item_kind IN ('skill', 'repo')),
    method       TEXT NOT NULL,                      -- how it was drawn, for the methods section
    seed         INTEGER,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
) STRICT;

CREATE TABLE IF NOT EXISTS sample_items (
    sample_id    INTEGER NOT NULL REFERENCES samples(sample_id),
    item_id      TEXT NOT NULL,                      -- file_sha or repo full_name
    position     INTEGER NOT NULL,                   -- S01 = 1, ...
    stratum      TEXT,                               -- e.g. 'length_q2'
    PRIMARY KEY (sample_id, item_id),
    UNIQUE (sample_id, position)
) STRICT;

-- ---------------------------------------------------------------------------
-- Codebooks: the text lives in git (codebook/<taxonomy>/vNN.md, #19);
-- the database records versions and their categories so labels can be validated.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS codebook_versions (
    codebook_version_id INTEGER PRIMARY KEY,
    taxonomy     TEXT NOT NULL CHECK (taxonomy IN ('purpose', 'context')),
    version      INTEGER NOT NULL,                   -- vNN
    variant      TEXT NOT NULL DEFAULT 'main',       -- 'main', or 'seeded' / 'agent_only' for the ablation (#49)
    file_path    TEXT NOT NULL,                      -- codebook/purpose/v03.md
    git_commit   TEXT,                               -- commit that added the file
    frozen       INTEGER NOT NULL DEFAULT 0 CHECK (frozen IN (0, 1)),
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (taxonomy, variant, version)
) STRICT;

CREATE TABLE IF NOT EXISTS categories (
    codebook_version_id INTEGER NOT NULL REFERENCES codebook_versions(codebook_version_id),
    category_key TEXT NOT NULL,                      -- stable slug, e.g. 'test-generation'
    name         TEXT NOT NULL,
    definition   TEXT NOT NULL,
    PRIMARY KEY (codebook_version_id, category_key)
) STRICT;

-- ---------------------------------------------------------------------------
-- Runs: one rater applying one codebook to one sample. Holds provenance shared
-- by every label in the run (model, temperature, codebook version).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS runs (
    run_id       INTEGER PRIMARY KEY,
    sample_id    INTEGER NOT NULL REFERENCES samples(sample_id),
    taxonomy     TEXT NOT NULL CHECK (taxonomy IN ('purpose', 'context')),
    codebook_version_id INTEGER REFERENCES codebook_versions(codebook_version_id),  -- NULL = open coding (Round 0)
    rater_kind   TEXT NOT NULL CHECK (rater_kind IN ('agent', 'human')),
    rater        TEXT NOT NULL,                      -- 'labeler', 'skeptic', 'open-coder', 'brendan', 'ryan'
    model        TEXT,                               -- pinned model id (#18); NULL for humans
    temperature  REAL,
    purpose      TEXT NOT NULL,                      -- 'round0', 'round', 'final', 'heldout', 'ablation', 'smoke'
    started_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    finished_at  TEXT,                               -- set by the Stop hook (#36)
    notes        TEXT,
    CHECK (rater_kind = 'human' OR model IS NOT NULL)
) STRICT;

-- ---------------------------------------------------------------------------
-- Annotations: one rater's judgment of one item in one run.
-- Multi-label: the categories are rows in annotation_labels.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS annotations (
    annotation_id INTEGER PRIMARY KEY,
    run_id       INTEGER NOT NULL REFERENCES runs(run_id),
    item_id      TEXT NOT NULL,                      -- file_sha or repo full_name
    skill_language TEXT,                             -- copied at labeling time (#53)
    prompt_hash  TEXT,                               -- provenance logger (#35); NULL for humans
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (run_id, item_id)
) STRICT;

CREATE TABLE IF NOT EXISTS annotation_labels (
    annotation_id INTEGER NOT NULL REFERENCES annotations(annotation_id),
    category_key TEXT NOT NULL,                      -- codebook key, or a free-form open code in Round 0
    PRIMARY KEY (annotation_id, category_key)
) STRICT;

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id  INTEGER PRIMARY KEY,
    annotation_id INTEGER NOT NULL REFERENCES annotations(annotation_id),
    category_key TEXT,                               -- which label this quote supports; NULL = whole annotation
    quote        TEXT NOT NULL,                      -- verbatim, original language
    quote_en     TEXT NOT NULL                       -- English translation; equals quote for English skills (#53)
) STRICT;

-- ---------------------------------------------------------------------------
-- PROPOSED_NEW: categories the agent suggests when nothing fits. Humans decide.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS proposals (
    proposal_id  INTEGER PRIMARY KEY,
    annotation_id INTEGER NOT NULL REFERENCES annotations(annotation_id),
    proposed_name TEXT NOT NULL,
    definition   TEXT NOT NULL,
    justification TEXT NOT NULL,                     -- always English
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'accepted', 'merged', 'rejected')),
    merged_into  TEXT,                               -- category_key when status = 'merged'
    decided_by   TEXT,                               -- 'brendan', 'ryan', 'both'
    decided_at   TEXT,
    decision_note TEXT,
    resulting_version_id INTEGER REFERENCES codebook_versions(codebook_version_id),
    CHECK (status <> 'merged' OR merged_into IS NOT NULL),
    CHECK (status = 'pending' OR decided_by IS NOT NULL)
) STRICT;

-- Evidence for a proposal is stored in `evidence` with category_key = 'PROPOSED_NEW:<proposal_id>'.

-- ---------------------------------------------------------------------------
-- Guards
-- ---------------------------------------------------------------------------
-- Frozen codebooks are read-only (backs up the PreToolUse guard, #33).
CREATE TRIGGER IF NOT EXISTS categories_frozen_insert
BEFORE INSERT ON categories
WHEN (SELECT frozen FROM codebook_versions WHERE codebook_version_id = NEW.codebook_version_id) = 1
BEGIN SELECT RAISE(ABORT, 'codebook version is frozen'); END;

CREATE TRIGGER IF NOT EXISTS categories_frozen_update
BEFORE UPDATE ON categories
WHEN (SELECT frozen FROM codebook_versions WHERE codebook_version_id = OLD.codebook_version_id) = 1
BEGIN SELECT RAISE(ABORT, 'codebook version is frozen'); END;

CREATE TRIGGER IF NOT EXISTS categories_frozen_delete
BEFORE DELETE ON categories
WHEN (SELECT frozen FROM codebook_versions WHERE codebook_version_id = OLD.codebook_version_id) = 1
BEGIN SELECT RAISE(ABORT, 'codebook version is frozen'); END;

-- In a run with a codebook, every label must be a category of that codebook
-- (backs up the PostToolUse validator, #32). Open-coding runs (codebook NULL) accept any label.
CREATE TRIGGER IF NOT EXISTS labels_in_codebook
BEFORE INSERT ON annotation_labels
WHEN (SELECT r.codebook_version_id FROM annotations a JOIN runs r USING (run_id)
      WHERE a.annotation_id = NEW.annotation_id) IS NOT NULL
 AND NEW.category_key <> 'PROPOSED_NEW'
 AND NOT EXISTS (
      SELECT 1 FROM annotations a JOIN runs r USING (run_id)
      JOIN categories c ON c.codebook_version_id = r.codebook_version_id
      WHERE a.annotation_id = NEW.annotation_id AND c.category_key = NEW.category_key)
BEGIN SELECT RAISE(ABORT, 'category not in this run''s codebook'); END;

-- ---------------------------------------------------------------------------
-- Indexes and views
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS annotations_item ON annotations(item_id);
CREATE INDEX IF NOT EXISTS evidence_annotation ON evidence(annotation_id);
CREATE INDEX IF NOT EXISTS proposals_status ON proposals(status);

-- Sampling frame with language, for the sampler (#21). language is NULL until detected.
CREATE VIEW IF NOT EXISTS skills_with_language AS
SELECT s.*, l.language, l.confidence AS language_confidence
FROM skills s LEFT JOIN skill_language l USING (file_sha);

-- Flat view for analysis: one row per (run, item, category).
CREATE VIEW IF NOT EXISTS label_rows AS
SELECT r.run_id, r.purpose AS run_purpose, r.taxonomy, r.rater_kind, r.rater, r.model,
       cv.version AS codebook_version, cv.variant AS codebook_variant,
       s.name AS sample, a.item_id, a.skill_language, l.category_key, a.created_at
FROM annotation_labels l
JOIN annotations a USING (annotation_id)
JOIN runs r USING (run_id)
JOIN samples s USING (sample_id)
LEFT JOIN codebook_versions cv USING (codebook_version_id);
