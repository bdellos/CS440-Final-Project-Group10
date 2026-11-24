"""Tests for schemas/label.schema.json and scripts/validate_label.py.

Uses a throwaway labels.db over the gitskills sample. Test skills are never Round 0 skills.
    .venv/Scripts/python -m pytest tests
"""
import copy
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import load_dataset  # noqa: E402
from db import connect, init_schema  # noqa: E402
from validate_label import quote_found, validate_label  # noqa: E402

ROUND0 = {r["file_sha"] for r in csv.DictReader(open(ROOT / "samples/round0.csv", encoding="utf-8"))}


def _quote_line(text):
    """A verbatim line of prose from the skill body (after the front matter)."""
    body = text.split("---", 2)[-1] if text.lstrip().startswith("---") else text
    for line in body.splitlines():
        s = line.strip().lstrip("#>-* ").strip()
        if len(s) > 40 and sum(ch.isalpha() for ch in s) > 30 and "`" not in s and "|" not in s:
            return s
    raise LookupError("no prose line")


def _pick(con, language):
    for sha, content in con.execute(
            """SELECT s.file_sha, a.content FROM skills_with_language s
               JOIN gs.artifacts a ON a.file_sha = s.file_sha AND a.dedup_primary = 1
               WHERE s.language = ? AND s.frontmatter_valid = 1 AND s.body_chars BETWEEN 1000 AND 8000
               ORDER BY s.file_sha""", (language,)):
        if sha in ROUND0:
            continue
        try:
            return sha, _quote_line(content)
        except LookupError:
            continue
    raise LookupError(language)


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "labels.db"
    con = connect(labels_db=db)
    init_schema(con)
    with con:
        load_dataset.build_skills(con)
    # Detect language for a slice only (enough to find an English and a Chinese skill)
    import detect_languages
    from language import detect
    rows = con.execute("SELECT s.file_sha, a.content FROM skills s JOIN gs.artifacts a "
                       "ON a.file_sha = s.file_sha AND a.dedup_primary = 1 "
                       "WHERE s.frontmatter_valid = 1 AND s.body_chars BETWEEN 1000 AND 8000 "
                       "ORDER BY s.file_sha LIMIT 1500").fetchall()
    with con:
        con.executemany("INSERT INTO skill_language (file_sha, language, confidence, detector) VALUES (?,?,?,?)",
                        [(sha, *detect(t), detect_languages.detector_id()) for sha, t in rows])
    en_sha, en_quote = _pick(con, "en")
    zh_sha, zh_quote = _pick(con, "zh")
    repo = con.execute("SELECT full_name FROM gs.repos ORDER BY full_name LIMIT 1").fetchone()[0]

    with con:
        sid = con.execute("INSERT INTO samples (name, item_kind, method) VALUES ('test', 'skill', 'test')").lastrowid
        con.executemany("INSERT INTO sample_items VALUES (?, ?, ?, NULL)",
                        [(sid, en_sha, 1), (sid, zh_sha, 2)])
        rid = con.execute("INSERT INTO samples (name, item_kind, method) VALUES ('test-repos', 'repo', 'test')").lastrowid
        con.execute("INSERT INTO sample_items VALUES (?, ?, 1, NULL)", (rid, repo))
        cb = con.execute("INSERT INTO codebook_versions (taxonomy, version, file_path) "
                         "VALUES ('purpose', 1, 'codebook/purpose/v01.md')").lastrowid
        con.executemany("INSERT INTO categories VALUES (?, ?, ?, ?)",
                        [(cb, "testing", "Testing", "Writes or runs tests"),
                         (cb, "deployment", "Deployment", "Ships software")])
        ccb = con.execute("INSERT INTO codebook_versions (taxonomy, version, file_path) "
                          "VALUES ('context', 1, 'codebook/context/v01.md')").lastrowid
        con.execute("INSERT INTO categories VALUES (?, 'catalog', 'Catalog', 'Collection of unrelated skills')", (ccb,))
        q = ("INSERT INTO runs (sample_id, taxonomy, codebook_version_id, rater_kind, rater, model, temperature, "
             "purpose) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
        runs = {
            "coded": con.execute(q, (sid, "purpose", cb, "agent", "labeler", "m", 0.0, "smoke")).lastrowid,
            "open": con.execute(q, (sid, "purpose", None, "agent", "open-coder", "m", 0.0, "smoke")).lastrowid,
            "context": con.execute(q, (rid, "context", ccb, "agent", "context-classifier", "m", 0.0, "smoke")).lastrowid,
            "finished": con.execute(q, (sid, "purpose", cb, "agent", "labeler", "m", 0.0, "smoke")).lastrowid,
        }
        con.execute("UPDATE runs SET finished_at = '2026-01-01T00:00:00Z' WHERE run_id = ?", (runs["finished"],))
    return dict(con=con, runs=runs, en=(en_sha, en_quote), zh=(zh_sha, zh_quote), repo=repo)


def skill_record(env, run="coded", **over):
    sha, quote = env["en"]
    rec = {
        "schema_version": 1, "run_id": env["runs"][run], "item_kind": "skill", "item_id": sha,
        "taxonomy": "purpose", "codebook_version": 1 if run in ("coded", "finished") else None,
        "skill_language": "en",
        "labels": [{"category": "testing", "evidence": [{"quote": quote, "quote_en": quote}]}],
        "proposals": [],
    }
    rec.update(over)
    return rec


def errs(env, rec):
    return validate_label(rec, env["con"])


def has(errors, text):
    return any(text in e for e in errors), errors


# --- valid records --------------------------------------------------------

def test_valid_coded_record(env):
    assert errs(env, skill_record(env)) == []


def test_valid_open_coding_record(env):
    rec = skill_record(env, "open")
    rec["labels"][0]["category"] = "Writes unit tests for a CLI (free-form code)"
    assert errs(env, rec) == []


def test_valid_non_english_with_translation(env):
    sha, quote = env["zh"]
    rec = skill_record(env, item_id=sha, skill_language="zh")
    rec["labels"][0]["evidence"] = [{"quote": quote, "quote_en": "An English translation of the quote"}]
    assert errs(env, rec) == []


def test_valid_proposal_only(env):
    sha, quote = env["en"]
    rec = skill_record(env, labels=[], proposals=[{
        "name": "Release notes", "definition": "Skills that write release notes from commits.",
        "justification": "Neither testing nor deployment covers writing prose about a release.",
        "evidence": [{"quote": quote, "quote_en": quote}]}])
    assert errs(env, rec) == []


def test_valid_repo_context_record(env):
    rec = {"schema_version": 1, "run_id": env["runs"]["context"], "item_kind": "repo", "item_id": env["repo"],
           "taxonomy": "context", "codebook_version": 1,
           "labels": [{"category": "catalog", "evidence": [{"quote": "skills/ holds 40 unrelated skills",
                                                             "quote_en": "skills/ holds 40 unrelated skills"}]}],
           "proposals": []}
    assert errs(env, rec) == []


# --- schema (shape) -------------------------------------------------------

@pytest.mark.parametrize("mutate, expect", [
    (lambda r: r.pop("run_id"), "'run_id' is a required property"),
    (lambda r: r.update(extra=1), "Additional properties"),
    (lambda r: r.update(item_id="not-a-sha"), "does not match"),
    (lambda r: r.pop("skill_language"), "'skill_language' is a required property"),
    (lambda r: r.update(labels=[]), "schema"),                                   # nothing said at all
    (lambda r: r["labels"][0].update(evidence=[]), "should be non-empty"),
    (lambda r: r["labels"][0]["evidence"][0].pop("quote_en"), "'quote_en' is a required property"),
    (lambda r: r["labels"][0].update(category="Not A Slug"), "does not match"),  # coded runs need slugs
    (lambda r: r.update(item_kind="repo"), "schema"),                            # purpose labels skills only
])
def test_schema_rejects(env, mutate, expect):
    rec = skill_record(env)
    mutate(rec)
    ok, e = has(errs(env, rec), expect)
    assert ok, e


def test_open_coding_rejects_proposals(env):
    sha, quote = env["en"]
    rec = skill_record(env, "open", proposals=[{
        "name": "Anything", "definition": "Some definition here.", "justification": "Some justification.",
        "evidence": [{"quote": quote, "quote_en": quote}]}])
    ok, e = has(errs(env, rec), "proposals")
    assert ok, e


# --- database checks ------------------------------------------------------

def test_unknown_category(env):
    rec = skill_record(env)
    rec["labels"][0]["category"] = "made-up"
    ok, e = has(errs(env, rec), "'made-up' is not a category of purpose v01")
    assert ok, e


def test_duplicate_category(env):
    rec = skill_record(env)
    rec["labels"].append(copy.deepcopy(rec["labels"][0]))
    ok, e = has(errs(env, rec), "listed twice")
    assert ok, e


def test_proposal_that_already_exists(env):
    sha, quote = env["en"]
    rec = skill_record(env, proposals=[{"name": "Testing", "definition": "Tests things, again.",
                                        "justification": "I did not check the codebook.",
                                        "evidence": [{"quote": quote, "quote_en": quote}]}])
    ok, e = has(errs(env, rec), "already exists in the codebook")
    assert ok, e


def test_fabricated_quote(env):
    rec = skill_record(env)
    rec["labels"][0]["evidence"] = [{"quote": "This sentence is not in the skill at all.",
                                     "quote_en": "This sentence is not in the skill at all."}]
    ok, e = has(errs(env, rec), "quote not found")
    assert ok, e


def test_english_translation_must_match(env):
    rec = skill_record(env)
    rec["labels"][0]["evidence"][0]["quote_en"] = "a paraphrase instead of the quote"
    ok, e = has(errs(env, rec), "quote_en must equal quote")
    assert ok, e


def test_language_mismatch(env):
    ok, e = has(errs(env, skill_record(env, skill_language="de")), "detection says 'en'")
    assert ok, e


def test_wrong_codebook_version(env):
    ok, e = has(errs(env, skill_record(env, codebook_version=2)), "uses 1")
    assert ok, e


def test_item_not_in_sample(env):
    other = env["con"].execute("SELECT file_sha FROM skill_language WHERE language = 'en' AND file_sha NOT IN (?, ?)",
                               (env["en"][0], env["zh"][0])).fetchone()[0]
    ok, e = has(errs(env, skill_record(env, item_id=other)), "is not in sample 'test'")
    assert ok, e


def test_finished_run(env):
    ok, e = has(errs(env, skill_record(env, "finished")), "is finished")
    assert ok, e


def test_missing_run(env):
    ok, e = has(errs(env, skill_record(env, run_id=999)), "does not exist")
    assert ok, e


def test_already_labeled_in_run(env):
    con, rec = env["con"], skill_record(env)
    with con:
        con.execute("INSERT INTO annotations (run_id, item_id) VALUES (?, ?)", (rec["run_id"], rec["item_id"]))
    try:
        ok, e = has(errs(env, rec), "already labeled")
        assert ok, e
    finally:
        with con:
            con.execute("DELETE FROM annotations WHERE run_id = ? AND item_id = ?", (rec["run_id"], rec["item_id"]))


# --- quote matching -------------------------------------------------------

@pytest.mark.parametrize("quote, found", [
    ("Use this skill when deploying", True),
    ("Use   this skill\nwhen deploying", True),     # whitespace differences are fine
    ("Use this skill ... the service", True),       # elision
    ("Use this skill … the service", True),
    ("the service ... Use this skill", False),      # elided parts must stay in order
    ("use this skill when deploying", False),       # case matters: verbatim
])
def test_quote_found(quote, found):
    assert quote_found(quote, "Intro.\nUse this skill when deploying\n  the service to production.") is found
