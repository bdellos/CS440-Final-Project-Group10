BEGIN TRANSACTION;
CREATE TABLE annotation_labels (
    annotation_id INTEGER NOT NULL REFERENCES annotations(annotation_id),
    category_key TEXT NOT NULL,                      -- codebook key, or a free-form open code in Round 0
    PRIMARY KEY (annotation_id, category_key)
) STRICT;
CREATE TABLE annotations (
    annotation_id INTEGER PRIMARY KEY,
    run_id       INTEGER NOT NULL REFERENCES runs(run_id),
    item_id      TEXT NOT NULL,                      -- file_sha or repo full_name
    skill_language TEXT,                             -- copied at labeling time (#53)
    prompt_hash  TEXT,                               -- provenance logger (#35); NULL for humans
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (run_id, item_id)
) STRICT;
CREATE TABLE categories (
    codebook_version_id INTEGER NOT NULL REFERENCES codebook_versions(codebook_version_id),
    category_key TEXT NOT NULL,                      -- stable slug, e.g. 'test-generation'
    name         TEXT NOT NULL,
    definition   TEXT NOT NULL,
    PRIMARY KEY (codebook_version_id, category_key)
) STRICT;
CREATE TABLE codebook_versions (
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
CREATE TABLE evidence (
    evidence_id  INTEGER PRIMARY KEY,
    annotation_id INTEGER NOT NULL REFERENCES annotations(annotation_id),
    category_key TEXT,                               -- which label this quote supports; NULL = whole annotation
    quote        TEXT NOT NULL,                      -- verbatim, original language
    quote_en     TEXT NOT NULL                       -- English translation; equals quote for English skills (#53)
) STRICT;
CREATE TABLE proposals (
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
CREATE TABLE runs (
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
CREATE TABLE sample_items (
    sample_id    INTEGER NOT NULL REFERENCES samples(sample_id),
    item_id      TEXT NOT NULL,                      -- file_sha or repo full_name
    position     INTEGER NOT NULL,                   -- S01 = 1, ...
    stratum      TEXT,                               -- e.g. 'length_q2'
    PRIMARY KEY (sample_id, item_id),
    UNIQUE (sample_id, position)
) STRICT;
CREATE TABLE samples (
    sample_id    INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,               -- 'round0', 'round1', 'heldout', 'smoke'
    item_kind    TEXT NOT NULL CHECK (item_kind IN ('skill', 'repo')),
    method       TEXT NOT NULL,                      -- how it was drawn, for the methods section
    seed         INTEGER,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
) STRICT;
CREATE TABLE skill_language (          -- populated by #52
    file_sha     TEXT PRIMARY KEY,
    language     TEXT NOT NULL,                      -- 'en', 'zh', 'mixed', 'unknown', ...
    confidence   REAL NOT NULL,
    detector     TEXT NOT NULL,                      -- e.g. 'scripts/language.py langdetect==1.0.9'
    detected_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
) STRICT;
CREATE TRIGGER categories_frozen_insert
BEFORE INSERT ON categories
WHEN (SELECT frozen FROM codebook_versions WHERE codebook_version_id = NEW.codebook_version_id) = 1
BEGIN SELECT RAISE(ABORT, 'codebook version is frozen'); END;
CREATE TRIGGER categories_frozen_update
BEFORE UPDATE ON categories
WHEN (SELECT frozen FROM codebook_versions WHERE codebook_version_id = OLD.codebook_version_id) = 1
BEGIN SELECT RAISE(ABORT, 'codebook version is frozen'); END;
CREATE TRIGGER categories_frozen_delete
BEFORE DELETE ON categories
WHEN (SELECT frozen FROM codebook_versions WHERE codebook_version_id = OLD.codebook_version_id) = 1
BEGIN SELECT RAISE(ABORT, 'codebook version is frozen'); END;
CREATE TRIGGER labels_in_codebook
BEFORE INSERT ON annotation_labels
WHEN (SELECT r.codebook_version_id FROM annotations a JOIN runs r USING (run_id)
      WHERE a.annotation_id = NEW.annotation_id) IS NOT NULL
 AND NEW.category_key <> 'PROPOSED_NEW'
 AND NOT EXISTS (
      SELECT 1 FROM annotations a JOIN runs r USING (run_id)
      JOIN categories c ON c.codebook_version_id = r.codebook_version_id
      WHERE a.annotation_id = NEW.annotation_id AND c.category_key = NEW.category_key)
BEGIN SELECT RAISE(ABORT, 'category not in this run''s codebook'); END;
CREATE INDEX annotations_item ON annotations(item_id);
CREATE INDEX evidence_annotation ON evidence(annotation_id);
CREATE INDEX proposals_status ON proposals(status);
CREATE VIEW label_rows AS
SELECT r.run_id, r.purpose AS run_purpose, r.taxonomy, r.rater_kind, r.rater, r.model,
       cv.version AS codebook_version, cv.variant AS codebook_variant,
       s.name AS sample, a.item_id, a.skill_language, l.category_key, a.created_at
FROM annotation_labels l
JOIN annotations a USING (annotation_id)
JOIN runs r USING (run_id)
JOIN samples s USING (sample_id)
LEFT JOIN codebook_versions cv USING (codebook_version_id);
COMMIT;
