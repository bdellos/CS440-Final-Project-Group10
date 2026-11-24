"""Validate a label record: the JSON schema plus the checks that need the database.

Shared by the PostToolUse validator hook (#32) and record_label (#14), so every rule
lives in one place.

    from validate_label import validate_label
    errors = validate_label(record, con)        # [] when valid

    .venv/Scripts/python scripts/validate_label.py label.json [more.json ...]   # exit 1 on any error

Database checks (schemas/label.schema.json can only check shape):
  run       the run exists, is open, and matches the record's taxonomy and codebook version
  item      the item is in the run's sample and in the attached dataset; not labeled twice in the run
  language  skill_language matches the stored detection (#52)
  codebook  every label is a category of the run's codebook; no duplicates; proposals aren't existing categories
  evidence  each quote occurs in the skill text (whitespace-insensitive; '...' may elide text);
            for English skills quote_en equals quote (#53)
"""
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from db import ROOT, connect

SCHEMA_PATH = ROOT / "schemas/label.schema.json"
_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…|\[\.\.\.\])\s*")


@lru_cache(maxsize=1)
def _validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def schema_errors(record):
    out = []
    for e in sorted(_validator().iter_errors(record), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in e.absolute_path) or "(record)"
        out.append(f"schema: {where}: {e.message}")
    return out


def _norm(text):
    return " ".join(text.split())


def quote_found(quote, text):
    """True if quote occurs in text, ignoring whitespace; '...' may stand for elided text."""
    hay, pos = _norm(text), 0
    for part in (p for p in _ELLIPSIS.split(quote) if p.strip()):
        i = hay.find(_norm(part), pos)
        if i < 0:
            return False
        pos = i + len(_norm(part))
    return True


def validate_label(record, con):
    errors = schema_errors(record)
    if errors:
        return errors  # database checks assume a well-formed record

    run = con.execute(
        """SELECT r.*, cv.version AS cb_version, s.name AS sample_name
           FROM runs r JOIN samples s USING (sample_id)
           LEFT JOIN codebook_versions cv USING (codebook_version_id)
           WHERE r.run_id = ?""",
        (record["run_id"],),
    ).fetchone()
    if run is None:
        return [f"run: run_id {record['run_id']} does not exist"]
    if run["finished_at"] is not None:
        errors.append(f"run: run {run['run_id']} is finished; start a new run")
    if run["taxonomy"] != record["taxonomy"]:
        errors.append(f"run: taxonomy is {record['taxonomy']!r} but run {run['run_id']} is {run['taxonomy']!r}")
    if run["cb_version"] != record["codebook_version"]:
        errors.append(f"run: codebook_version is {record['codebook_version']} but run {run['run_id']} "
                      f"uses {run['cb_version']}")

    item = record["item_id"]
    if not con.execute("SELECT 1 FROM sample_items WHERE sample_id = ? AND item_id = ?",
                       (run["sample_id"], item)).fetchone():
        errors.append(f"item: {item} is not in sample {run['sample_name']!r} of run {run['run_id']}")
    if con.execute("SELECT 1 FROM annotations WHERE run_id = ? AND item_id = ?", (run["run_id"], item)).fetchone():
        errors.append(f"item: {item} is already labeled in run {run['run_id']}")

    text = None
    if record["item_kind"] == "skill":
        row = con.execute("SELECT content FROM gs.artifacts WHERE file_sha = ? AND dedup_primary = 1",
                          (item,)).fetchone()
        if row is None:
            errors.append(f"item: no skill with file_sha {item} in the dataset")
        else:
            text = row[0] or ""
        lang = con.execute("SELECT language FROM skill_language WHERE file_sha = ?", (item,)).fetchone()
        if lang is None:
            errors.append(f"language: no detected language for {item}; run scripts/detect_languages.py")
        elif lang[0] != record["skill_language"]:
            errors.append(f"language: skill_language is {record['skill_language']!r} but detection says {lang[0]!r}")
    elif not con.execute("SELECT 1 FROM gs.repos WHERE full_name = ?", (item,)).fetchone():
        errors.append(f"item: no repo {item} in the dataset")

    cats = [lab["category"] for lab in record["labels"]]
    for dup in sorted({c for c in cats if cats.count(c) > 1}):
        errors.append(f"codebook: category {dup!r} is listed twice")
    if run["codebook_version_id"] is not None:
        known = {r[0]: r[1] for r in con.execute(
            "SELECT category_key, name FROM categories WHERE codebook_version_id = ?",
            (run["codebook_version_id"],))}
        for c in cats:
            if c not in known:
                errors.append(f"codebook: {c!r} is not a category of {run['taxonomy']} v{run['cb_version']:02d}; "
                              "use proposals if nothing fits")
        names = {n.strip().lower() for n in known.values()} | set(known)
        for p in record["proposals"]:
            slug = re.sub(r"[^a-z0-9]+", "-", p["name"].lower()).strip("-")
            if p["name"].strip().lower() in names or slug in known:
                errors.append(f"proposals: {p['name']!r} already exists in the codebook; label it instead")

    english = record.get("skill_language") == "en"
    evidence = [(f"labels/{i}", ev) for i, lab in enumerate(record["labels"]) for ev in lab["evidence"]]
    evidence += [(f"proposals/{i}", ev) for i, p in enumerate(record["proposals"]) for ev in p["evidence"]]
    for where, ev in evidence:
        if text is not None and not quote_found(ev["quote"], text):
            errors.append(f"evidence: {where}: quote not found in the skill text: {ev['quote'][:80]!r}")
        if english and _norm(ev["quote_en"]) != _norm(ev["quote"]):
            errors.append(f"evidence: {where}: skill is English, so quote_en must equal quote")
    return errors


def main(paths):
    con, bad = connect(), 0
    for p in paths:
        errs = validate_label(json.loads(Path(p).read_text(encoding="utf-8")), con)
        bad += bool(errs)
        print(f"{p}: {'ok' if not errs else ''}")
        for e in errs:
            print(f"  - {e}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(sys.argv[1:] or sys.exit(__doc__))
