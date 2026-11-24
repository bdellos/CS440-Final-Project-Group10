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
CREATE TABLE dataset_loads (
    load_id      INTEGER PRIMARY KEY,
    dataset_path TEXT NOT NULL,
    dataset_bytes INTEGER NOT NULL,
    dataset_mtime TEXT NOT NULL,
    artifacts    INTEGER NOT NULL,                   -- file occurrences
    distinct_skills INTEGER NOT NULL,
    repos        INTEGER NOT NULL,
    loaded_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
) STRICT;
INSERT INTO "dataset_loads" VALUES(1,'data/gitskills-sample/agent_skills_sample/agent_skills_sample.db',290955264,'2026-07-25T01:21:22Z',29786,13000,11841,'2026-11-24T00:20:23Z');
INSERT INTO "dataset_loads" VALUES(2,'data/gitskills-sample/agent_skills_sample/agent_skills_sample.db',290955264,'2026-07-25T01:21:22Z',29786,13000,11841,'2026-11-24T00:20:24Z');
INSERT INTO "dataset_loads" VALUES(3,'data/gitskills-sample/agent_skills_sample/agent_skills_sample.db',290955264,'2026-07-25T01:21:22Z',29786,13000,11841,'2026-11-24T00:28:15Z');
INSERT INTO "dataset_loads" VALUES(4,'data/gitskills-sample/agent_skills_sample/agent_skills_sample.db',290955264,'2026-07-25T01:21:22Z',29786,13000,11841,'2026-11-24T00:28:15Z');
INSERT INTO "dataset_loads" VALUES(5,'data/gitskills-sample/agent_skills_sample/agent_skills_sample.db',290955264,'2026-07-25T01:21:22Z',29786,13000,11841,'2026-11-24T01:28:36Z');
INSERT INTO "dataset_loads" VALUES(6,'data/gitskills-sample/agent_skills_sample/agent_skills_sample.db',290955264,'2026-07-25T01:21:22Z',29786,13000,11841,'2026-11-24T02:45:14Z');
INSERT INTO "dataset_loads" VALUES(7,'data/gitskills-sample/agent_skills_sample/agent_skills_sample.db',290955264,'2026-07-25T01:21:22Z',29786,13000,11841,'2026-11-24T03:22:12Z');
CREATE TABLE evidence (
    evidence_id  INTEGER PRIMARY KEY,
    annotation_id INTEGER NOT NULL REFERENCES annotations(annotation_id),
    category_key TEXT,                               -- which label this quote supports; NULL = whole annotation
    quote        TEXT NOT NULL,                      -- verbatim, original language
    quote_en     TEXT NOT NULL                       -- English translation; equals quote for English skills (#53)
) STRICT;
CREATE TABLE prompt_versions (
    prompt_hash  TEXT PRIMARY KEY,                   -- 'sha256:' + hex, see scripts/prompts.py
    rater        TEXT NOT NULL,
    files        TEXT NOT NULL,                      -- JSON [{"path", "text"}], LF line endings
    git_commit   TEXT,                               -- HEAD when first seen
    uncommitted_changes INTEGER CHECK (uncommitted_changes IN (0, 1)),  -- files differed from git_commit
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
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
CREATE TABLE "runs" (
    run_id       INTEGER PRIMARY KEY,
    sample_id    INTEGER NOT NULL REFERENCES samples(sample_id),
    taxonomy     TEXT NOT NULL CHECK (taxonomy IN ('purpose', 'context')),
    codebook_version_id INTEGER REFERENCES codebook_versions(codebook_version_id),  -- NULL = open coding (Round 0)
    rater_kind   TEXT NOT NULL CHECK (rater_kind IN ('agent', 'human')),
    rater        TEXT NOT NULL,                      -- 'labeler', 'skeptic', 'open-coder', 'brendan', 'ryan'
    model        TEXT,                               -- pinned model id from config/models.json (#18); NULL for humans
    temperature  REAL,                               -- always NULL: current Claude models reject temperature (#18)
    -- from config/models.json; 'unrecorded' only for agent runs made before effort was tracked (schema v2)
    effort       TEXT CHECK (effort IS NULL OR effort IN ('low', 'medium', 'high', 'xhigh', 'max', 'unrecorded')),
    purpose      TEXT NOT NULL,                      -- 'round0', 'round', 'final', 'heldout', 'ablation', 'smoke'
    started_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    finished_at  TEXT,                               -- set by the Stop hook (#36)
    notes        TEXT,
    CHECK (rater_kind = 'human' OR (model IS NOT NULL AND effort IS NOT NULL))
) STRICT;
CREATE TABLE sample_items (
    sample_id    INTEGER NOT NULL REFERENCES samples(sample_id),
    item_id      TEXT NOT NULL,                      -- file_sha or repo full_name
    position     INTEGER NOT NULL,                   -- S01 = 1, ...
    stratum      TEXT,                               -- e.g. 'length_q2'
    PRIMARY KEY (sample_id, item_id),
    UNIQUE (sample_id, position)
) STRICT;
INSERT INTO "sample_items" VALUES(1,'00e9d1dc478bca25eeb3565c42a781b2e69aa658',1,'length_q1');
INSERT INTO "sample_items" VALUES(1,'00fcf2d40b84249f369934644c892ade85425e1e',2,'length_q4');
INSERT INTO "sample_items" VALUES(1,'00181699d0e3b40ea90dbbd48e7757c84f51783f',3,'length_q4');
INSERT INTO "sample_items" VALUES(1,'00e56bc7f964fa0e3b38466fd0a25b6041c3159e',4,'length_q2');
INSERT INTO "sample_items" VALUES(1,'0067f5d456dc4b20c89b831e44f6cea72eeb2dd4',5,'length_q2');
INSERT INTO "sample_items" VALUES(1,'0140b6b237b0efe6d340f419c327bc4977a077fd',6,'length_q4');
INSERT INTO "sample_items" VALUES(1,'015c2c6dc864037709b07517608acaec536947f3',7,'length_q3');
INSERT INTO "sample_items" VALUES(1,'00a15635eb311dd05052cb594d719783dd731081',8,'length_q3');
INSERT INTO "sample_items" VALUES(1,'0120be3f962f87bdc5febd12fe716acbcd35607e',9,'length_q3');
INSERT INTO "sample_items" VALUES(1,'00b56fd8884f2d6cd0067ebe232bff2439eb99b1',10,'length_q2');
INSERT INTO "sample_items" VALUES(1,'008ee81c318e9b83f0e14fa9d49e65fb28eb59f9',11,'length_q3');
INSERT INTO "sample_items" VALUES(1,'0005bfdfffae9c0aa20b16c806c33b47bb41cc1c',12,'length_q4');
INSERT INTO "sample_items" VALUES(1,'00134ec76942976714a6ed9533e6b9536ab8b020',13,'length_q2');
INSERT INTO "sample_items" VALUES(1,'0033699eb5500379694d489a4183436e9be98e41',14,'length_q1');
INSERT INTO "sample_items" VALUES(1,'006370aed1d3dfba12470bf51af6bafb49baa91e',15,'length_q3');
INSERT INTO "sample_items" VALUES(1,'003eeeff35a3fb3ffc4aaaa0f599123a5058d9c8',16,'length_q3');
INSERT INTO "sample_items" VALUES(1,'012b3423c7c58532a8e0496dff28c76044120633',17,'length_q1');
INSERT INTO "sample_items" VALUES(1,'00a90a0cac2c384a26449bfe84839b7d8ac85930',18,'length_q4');
INSERT INTO "sample_items" VALUES(1,'001d2557bc83de4d51172676c49c88f648037270',19,'length_q1');
INSERT INTO "sample_items" VALUES(1,'00bbfca09e5705082d83f14645f0bf7413c97b7f',20,'length_q3');
INSERT INTO "sample_items" VALUES(1,'00c38e92580c2bc2e0908b2c85eed0af2f6bb5e2',21,'length_q1');
INSERT INTO "sample_items" VALUES(1,'008cdc2c173557b6f4e3d07bfce1b936e94a0621',22,'length_q1');
INSERT INTO "sample_items" VALUES(1,'00e785a3197b960d10e0f366f0eabf1fce7af552',23,'length_q2');
INSERT INTO "sample_items" VALUES(1,'00fbe1da5f7c75ae27deb720339ca04c73b69b8f',24,'length_q2');
INSERT INTO "sample_items" VALUES(1,'00705c4be9874ef9df72434646bb6145b3f0ce56',25,'length_q2');
INSERT INTO "sample_items" VALUES(1,'00b916d1ff667a8fdb44f9531a98df86e8f44839',26,'length_q1');
INSERT INTO "sample_items" VALUES(1,'008cd8b2dab7277393d342b83caf391f0595e233',27,'length_q4');
INSERT INTO "sample_items" VALUES(1,'00fdf30b13f5605d2c122250ccfb016f043a1390',28,'length_q2');
INSERT INTO "sample_items" VALUES(1,'00edc0dd19af8650c443922dec54804c2aef2947',29,'length_q4');
INSERT INTO "sample_items" VALUES(1,'003cd0b9c1c6f7cbfe2b470fc5b5cd3195c884ee',30,'length_q3');
INSERT INTO "sample_items" VALUES(1,'00f4706300a33f1c6e4da329052f0f3326537fdc',31,'length_q3');
INSERT INTO "sample_items" VALUES(1,'0064c87c258a180bdbde72d3beede9ac6d9ae3a8',32,'length_q4');
INSERT INTO "sample_items" VALUES(1,'00076c3cfabfd0e211079180b2cec3477fff432a',33,'length_q1');
INSERT INTO "sample_items" VALUES(1,'00b73439353d835887e8f6af756b30fa3d297a63',34,'length_q4');
INSERT INTO "sample_items" VALUES(1,'009584131d0b60ba50b2ab531c46ae93c7cdd045',35,'length_q2');
INSERT INTO "sample_items" VALUES(1,'01695901e62b50f80863a70170f2f4e621308d0b',36,'length_q1');
INSERT INTO "sample_items" VALUES(1,'00fa616f2fc02bcead4010afb32e1ffcf619cfc4',37,'length_q3');
INSERT INTO "sample_items" VALUES(1,'00562419b4b03388123490d294289ef0d96a957c',38,'length_q2');
INSERT INTO "sample_items" VALUES(1,'006b86d5adb18c3aa56723bd9e505a6cce4e3d4a',39,'length_q4');
INSERT INTO "sample_items" VALUES(1,'00379399656dd4da3f77835819c31a0fd84515e7',40,'length_q4');
INSERT INTO "sample_items" VALUES(1,'00366eef12736b1e0b1f2a3fe0ef7e796be5e48d',41,'length_q3');
INSERT INTO "sample_items" VALUES(1,'00814eb2877cad99547f99b5db369687f0232c19',42,'length_q1');
INSERT INTO "sample_items" VALUES(1,'0192d72e3c609c29854384982489a153db7df2ff',43,'length_q1');
INSERT INTO "sample_items" VALUES(1,'00966cd4efbe6131f462eb97933b62a187d72431',44,'length_q3');
INSERT INTO "sample_items" VALUES(1,'01b3c0eab4a503155700fbb3f95eb471f3b95c00',45,'length_q2');
INSERT INTO "sample_items" VALUES(1,'009f6859aecb945a798af8ce89b38a1675290746',46,'length_q4');
INSERT INTO "sample_items" VALUES(1,'00203e0ea4418c3d09a779562031c07466ed02b2',47,'length_q2');
INSERT INTO "sample_items" VALUES(1,'002b4e22d37f257fad9bf1213da5ce5b47997b4b',48,'length_q2');
INSERT INTO "sample_items" VALUES(1,'00aa3df86cbfbc66b433f1f5633f3ea37481df3b',49,'length_q1');
INSERT INTO "sample_items" VALUES(1,'01a176c42146ab8cb78d7dbd8b234e6b7ef3e457',50,'length_q1');
INSERT INTO "sample_items" VALUES(2,'00123a723aa46eb70312f871715b9187d207b47a',1,'length_q2');
INSERT INTO "sample_items" VALUES(2,'005e5d05355e0ffe17243dfbf75428f637c02bf6',2,'length_q2');
INSERT INTO "sample_items" VALUES(2,'0150755e72c6a392a030b18af63c32bfdf658afd',3,'length_q1');
INSERT INTO "sample_items" VALUES(2,'000c903b1fd54833adcb9dea1cef3fdda3b906a1',4,'length_q4');
INSERT INTO "sample_items" VALUES(2,'0129cacb251f6125cb0be38d134e6756b8ead3aa',5,'length_q3');
CREATE TABLE samples (
    sample_id    INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,               -- 'round0', 'round1', 'heldout', 'smoke'
    item_kind    TEXT NOT NULL CHECK (item_kind IN ('skill', 'repo')),
    method       TEXT NOT NULL,                      -- how it was drawn, for the methods section
    seed         INTEGER,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
) STRICT;
INSERT INTO "samples" VALUES(1,'round0','skill','Distinct English-language skills with valid front matter, 200-20,000 body characters, at most one per skill name and one per repository, stratified by body-length quartile (13/13/12/12). scripts/draw_round0_sample.py',440,'2026-11-24T00:20:23Z');
INSERT INTO "samples" VALUES(2,'smoke1','skill','distinct skills, English only (language = ''en''), valid front matter, 200-20,000 body characters, excluding skills, skill names and repositories used in earlier samples, at most one per skill name, at most one per repository; stratified by body-length quartile, proportional allocation, seed 20261124. scripts/sampling.py',20261124,'2026-11-24T21:52:01Z');
CREATE TABLE skill_language (          -- populated by #52
    file_sha     TEXT PRIMARY KEY,
    language     TEXT NOT NULL,                      -- 'en', 'zh', 'mixed', 'unknown', ...
    confidence   REAL NOT NULL,
    detector     TEXT NOT NULL,                      -- e.g. 'scripts/language.py langdetect==1.0.9'
    detected_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
) STRICT;
CREATE TABLE skills (
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
CREATE INDEX annotations_item ON annotations(item_id);
CREATE INDEX evidence_annotation ON evidence(annotation_id);
CREATE INDEX proposals_status ON proposals(status);
CREATE INDEX skills_sampling ON skills(frontmatter_valid, body_chars);
CREATE INDEX skills_repo ON skills(repo_full_name);
CREATE INDEX skills_name ON skills(name_key);
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
CREATE VIEW proposals_review AS
SELECT p.proposal_id, p.status, p.proposed_name, p.definition, p.justification,
       r.run_id, r.rater, a.item_id, a.skill_language,
       CASE WHEN a.skill_language IS NOT NULL AND a.skill_language <> 'en' THEN 1 ELSE 0 END AS needs_extra_review
FROM proposals p
JOIN annotations a USING (annotation_id)
JOIN runs r USING (run_id);
CREATE VIEW skills_with_language AS
SELECT s.*, l.language, l.confidence AS language_confidence
FROM skills s LEFT JOIN skill_language l USING (file_sha);
CREATE VIEW label_rows AS
SELECT r.run_id, r.purpose AS run_purpose, r.taxonomy, r.rater_kind, r.rater, r.model,
       cv.version AS codebook_version, cv.variant AS codebook_variant,
       s.name AS sample, a.item_id, a.skill_language, l.category_key, a.created_at
FROM annotation_labels l
JOIN annotations a USING (annotation_id)
JOIN runs r USING (run_id)
JOIN samples s USING (sample_id)
LEFT JOIN codebook_versions cv USING (codebook_version_id);
CREATE TRIGGER annotations_prompt_provenance
BEFORE INSERT ON annotations
WHEN (SELECT rater_kind FROM runs WHERE run_id = NEW.run_id) = 'agent'
 AND (NEW.prompt_hash IS NULL
      OR NOT EXISTS (SELECT 1 FROM prompt_versions p WHERE p.prompt_hash = NEW.prompt_hash))
BEGIN SELECT RAISE(ABORT, 'agent label needs a prompt_hash stored in prompt_versions (#35)'); END;
CREATE TRIGGER annotations_no_prompt_for_humans
BEFORE INSERT ON annotations
WHEN (SELECT rater_kind FROM runs WHERE run_id = NEW.run_id) = 'human' AND NEW.prompt_hash IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'human labels have no prompt_hash (#35)'); END;
COMMIT;
