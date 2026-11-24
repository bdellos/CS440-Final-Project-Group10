"""Codebook versions: parse, check, create the next version, register in labels.db (issue #19).

    .venv/Scripts/python scripts/codebook.py check                         # all files; exit 1 on problems
    .venv/Scripts/python scripts/codebook.py next purpose --round 3        # copy latest -> v(N+1).md
    .venv/Scripts/python scripts/codebook.py next purpose --round 1 --variant seeded
    .venv/Scripts/python scripts/codebook.py register codebook/purpose/v03.md

Format and rules: codebook/README.md. The key rule, "never edit a past version", is
enforced through git: a vNN.md file may appear in exactly one commit and must not have
uncommitted changes after that.
"""
import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODEBOOK_DIR = "codebook"
TAXONOMIES = ("purpose", "context")
SECTIONS = ("Definition", "Include", "Exclude", "Examples")

_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_CATEGORY = re.compile(rf"^## (?P<key>{_SLUG}): (?P<name>\S.*?)\s*$")
_EXAMPLE_ID = {"purpose": re.compile(r"^- [0-9a-f]{40}: \S"),
               "context": re.compile(r"^- [A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+: \S")}
_FILENAME = re.compile(rf"^{CODEBOOK_DIR}/(?P<tax>{'|'.join(TAXONOMIES)})/(?:(?P<variant>{_SLUG})/)?v(?P<num>\d\d)\.md$")


@dataclass
class Category:
    key: str
    name: str
    sections: dict = field(default_factory=dict)

    @property
    def definition(self):
        return self.sections.get("Definition", "")


@dataclass
class Codebook:
    path: str               # repo-relative, forward slashes
    taxonomy: str
    variant: str
    version: int
    based_on: int | None
    round: int
    categories: list
    errors: list


def rel(path) -> str:
    p = Path(path)
    p = p if p.is_absolute() else (ROOT / p)
    return p.resolve().relative_to(ROOT).as_posix()


def parse(path) -> Codebook:
    path = rel(path)
    text = (ROOT / path).read_text(encoding="utf-8").lstrip("﻿")
    errors = []
    m = _FRONT.match(text)
    meta = {}
    if not m:
        errors.append("missing --- header ---")
    else:
        for line in m.group(1).splitlines():
            if line.strip():
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        text = text[m.end():]

    def num(key, allow_none=False):
        v = meta.get(key)
        if allow_none and v == "none":
            return None
        if v is None or not v.isdigit():
            errors.append(f"header: {key} must be {'a number or none' if allow_none else 'a number'}, got {v!r}")
            return None
        return int(v)

    taxonomy, variant = meta.get("taxonomy"), meta.get("variant", "main")
    version, based_on, rnd = num("version"), num("based_on", allow_none=True), num("round")
    if taxonomy not in TAXONOMIES:
        errors.append(f"header: taxonomy must be one of {TAXONOMIES}, got {taxonomy!r}")
    if not re.fullmatch(_SLUG, variant or ""):
        errors.append(f"header: variant must be a lowercase slug, got {variant!r}")
    unknown = set(meta) - {"taxonomy", "variant", "version", "based_on", "round"}
    if unknown:
        errors.append(f"header: unknown keys {sorted(unknown)}")

    fm = _FILENAME.match(path)
    if not fm:
        errors.append(f"file name: expected {CODEBOOK_DIR}/<taxonomy>/[<variant>/]vNN.md")
    else:
        if fm["tax"] != taxonomy:
            errors.append(f"file name says {fm['tax']} but header says {taxonomy}")
        if (fm["variant"] or "main") != variant:
            errors.append(f"file name says variant {fm['variant'] or 'main'} but header says {variant}")
        if version is not None and int(fm["num"]) != version:
            errors.append(f"file name says v{fm['num']} but header says version {version}")
    if version is not None and based_on is not None and based_on >= version:
        errors.append(f"header: based_on ({based_on}) must be an earlier version than {version}")
    if version and based_on is None:
        errors.append("header: based_on is required for versions after v00")

    categories, cat, section = [], None, None
    for n, line in enumerate(_COMMENT.sub("", text).splitlines(), start=1):
        if line.startswith("## "):
            cm = _CATEGORY.match(line)
            if not cm:
                errors.append(f"line {n}: category heading must be '## key: Name' with a lowercase slug key: {line!r}")
                cat = section = None
                continue
            cat, section = Category(cm["key"], cm["name"]), None
            categories.append(cat)
        elif line.startswith("### "):
            title = line[4:].strip()
            if cat is None:
                errors.append(f"line {n}: section {title!r} outside a category")
            elif title not in SECTIONS:
                errors.append(f"line {n}: unknown section {title!r} in {cat.key} (expected {', '.join(SECTIONS)})")
                section = None
            elif title in cat.sections:
                errors.append(f"line {n}: section {title!r} repeated in {cat.key}")
            else:
                section = title
                cat.sections[title] = ""
        elif cat is not None and section is not None:
            cat.sections[section] += line + "\n"

    keys = [c.key for c in categories]
    for dup in sorted({k for k in keys if keys.count(k) > 1}):
        errors.append(f"category {dup!r} defined twice")
    for c in categories:
        c.sections = {k: v.strip() for k, v in c.sections.items()}
        for s in SECTIONS:
            if not c.sections.get(s):
                errors.append(f"{c.key}: missing or empty '### {s}'")
        if taxonomy in _EXAMPLE_ID and c.sections.get("Examples"):
            for line in c.sections["Examples"].splitlines():
                if line.strip() and not _EXAMPLE_ID[taxonomy].match(line.strip()):
                    want = "file_sha" if taxonomy == "purpose" else "owner/repo"
                    errors.append(f"{c.key}: example must start with '- <{want}>: ': {line.strip()[:60]!r}")
    return Codebook(path, taxonomy, variant, version if version is not None else -1, based_on,
                    rnd if rnd is not None else -1, categories, errors)


# --- git ------------------------------------------------------------------

def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def commits_touching(path) -> list:
    return _git("log", "--format=%H", "--", path).split()


def uncommitted(path) -> bool:
    """True if the file has changes git hasn't committed (untracked counts as uncommitted)."""
    return bool(_git("status", "--porcelain", "--", path).strip())


def immutability_errors(path) -> list:
    commits = commits_touching(path)
    if len(commits) > 1:
        return [f"{path}: changed in {len(commits)} commits; past versions must never be edited "
                f"(make the next version instead)"]
    if commits and uncommitted(path):
        return [f"{path}: committed version has uncommitted edits; revert them and create the next version"]
    return []


# --- commands -------------------------------------------------------------

def all_files() -> list:
    return sorted(p for p in (ROOT / CODEBOOK_DIR).rglob("v*.md"))


def check(files=None) -> list:
    """All problems across the codebook directory (format, numbering, immutability)."""
    problems, series = [], {}
    for f in files or all_files():
        cb = parse(f)
        problems += [f"{cb.path}: {e}" for e in cb.errors]
        problems += immutability_errors(cb.path)
        series.setdefault((cb.taxonomy, cb.variant), []).append(cb.version)
    for (tax, variant), versions in sorted(series.items(), key=str):
        if sorted(versions) != list(range(len(versions))):
            problems.append(f"{tax}/{variant}: versions must run v00, v01, ... without gaps; found "
                            + ", ".join(f"v{v:02d}" for v in sorted(versions)))
    return problems


def series_dir(taxonomy, variant) -> Path:
    return ROOT / CODEBOOK_DIR / taxonomy / ("" if variant == "main" else variant)


def latest(taxonomy, variant="main") -> Path | None:
    files = sorted(series_dir(taxonomy, variant).glob("v[0-9][0-9].md"))
    return files[-1] if files else None


def next_version(taxonomy, rnd, variant="main", base: Path | None = None) -> Path:
    """Create v(N+1).md as a copy of the latest version (or of `base` for a new variant)."""
    src = latest(taxonomy, variant)
    if src is None:
        if base is None:
            raise SystemExit(f"no {taxonomy}/{variant} versions yet; pass --from to start a variant")
        src_cb, new_num = parse(base), 0
    else:
        src_cb = parse(src)
        new_num = src_cb.version + 1
        if src_cb.errors:
            raise SystemExit(f"{src_cb.path} has errors; fix them first:\n  " + "\n  ".join(src_cb.errors))
        if uncommitted(src_cb.path):
            raise SystemExit(f"{src_cb.path} isn't committed yet; commit it before starting the next version")
    dst = series_dir(taxonomy, variant) / f"v{new_num:02d}.md"
    if dst.exists():
        raise SystemExit(f"{rel(dst)} already exists")
    text = (ROOT / src_cb.path).read_text(encoding="utf-8")
    header = (f"---\ntaxonomy: {taxonomy}\nvariant: {variant}\nversion: {new_num}\n"
              f"based_on: {src_cb.version if src is not None else 'none'}\nround: {rnd}\n---\n")
    body = _FRONT.sub("", text, count=1)
    body = re.sub(r"^# .*codebook v\d\d.*$", f"# {taxonomy.capitalize()} codebook v{new_num:02d}"
                  + ("" if variant == "main" else f" ({variant})"), body, count=1, flags=re.M)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(header + body, encoding="utf-8", newline="\n")
    return dst


def commit_message(cb: Codebook) -> str:
    variant = "" if cb.variant == "main" else f" [{cb.variant}]"
    return f"codebook: {cb.taxonomy} v{cb.version:02d}{variant} (round {cb.round})"


def register(path, con) -> str:
    """Load a committed, valid version into codebook_versions/categories. Idempotent."""
    cb = parse(path)
    if cb.errors:
        raise SystemExit(f"{cb.path} has errors:\n  " + "\n  ".join(cb.errors))
    commits = commits_touching(cb.path)
    if not commits or uncommitted(cb.path):
        raise SystemExit(f"{cb.path} must be committed (and unchanged) before registering, "
                         "so labels can be traced to an exact commit")
    errs = immutability_errors(cb.path)
    if errs:
        raise SystemExit(errs[0])
    commit = commits[0]
    row = con.execute("SELECT git_commit FROM codebook_versions WHERE taxonomy = ? AND variant = ? AND version = ?",
                      (cb.taxonomy, cb.variant, cb.version)).fetchone()
    if row:
        if row[0] != commit:
            raise SystemExit(f"{cb.path} is registered from commit {row[0][:8]}, but the file now comes "
                             f"from {commit[:8]}")
        return f"{cb.path}: already registered"
    with con:
        vid = con.execute(
            "INSERT INTO codebook_versions (taxonomy, version, variant, file_path, git_commit) VALUES (?, ?, ?, ?, ?)",
            (cb.taxonomy, cb.version, cb.variant, cb.path, commit)).lastrowid
        con.executemany("INSERT INTO categories (codebook_version_id, category_key, name, definition) VALUES (?, ?, ?, ?)",
                        [(vid, c.key, c.name, c.definition) for c in cb.categories])
    return f"{cb.path}: registered as {cb.taxonomy}/{cb.variant} v{cb.version:02d} " \
           f"({len(cb.categories)} categories, commit {commit[:8]})"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="check every codebook file")
    n = sub.add_parser("next", help="create the next version from the latest one")
    n.add_argument("taxonomy", choices=TAXONOMIES)
    n.add_argument("--round", type=int, required=True)
    n.add_argument("--variant", default="main")
    n.add_argument("--from", dest="base", help="for a new variant: the version file to start from")
    r = sub.add_parser("register", help="load a committed version into labels.db")
    r.add_argument("file")
    a = p.parse_args()

    if a.cmd == "check":
        problems = check()
        for pr in problems:
            print(f"- {pr}")
        print("codebook check:", "ok" if not problems else f"{len(problems)} problem(s)")
        sys.exit(1 if problems else 0)
    if a.cmd == "next":
        dst = next_version(a.taxonomy, a.round, a.variant, Path(a.base) if a.base else None)
        cb = parse(dst)
        print(f"created {cb.path} (based on v{cb.based_on:02d})" if cb.based_on is not None else f"created {cb.path}")
        print(f'when approved, commit it with:\n  git commit -m "{commit_message(cb)}"')
    if a.cmd == "register":
        from db import connect
        print(register(a.file, connect()))


if __name__ == "__main__":
    main()
