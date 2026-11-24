"""Draw the shared Round 0 sample and build blind coding workbooks.

Run from the repo root:
    .venv/Scripts/python scripts/draw_round0_sample.py

Sampling (decided 2026-11-23):
  - Population: distinct skill contents (dedup_primary = 1) with valid YAML front
    matter and a body of 200..20,000 characters.
  - English only (scripts/language.py), because the human coders read English only.
    Applied before de-duplication.
  - Near-duplicates: at most one skill per front-matter name (case-insensitive);
    the representative is the one with the lowest file_sha (deterministic).
  - At most one skill per repository (lowest file_sha), so catalog repos holding
    hundreds of skills cannot dominate the sample.
  - Stratified by body length quartile: 13, 13, 12, 12 skills.
  - Fixed seed, so the same 50 skills come out every run.

Outputs:
  samples/round0.csv                        - the sample (committed; the open-coder uses it too)
  data/round0/Round0_Coding_<Coder>.xlsx    - one blank coding workbook per coder
"""
import csv
import random
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.hyperlink import Hyperlink

from language import is_english


def link_to_sheet(cell, sheet, target="A1"):
    """Internal link to another tab (a '#Sheet!A1' string would be saved as an external URL)."""
    cell.hyperlink = Hyperlink(ref=cell.coordinate, location=f"'{sheet}'!{target}")

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data/gitskills-sample/agent_skills_sample/agent_skills_sample.db"
SAMPLE_CSV = ROOT / "samples/round0.csv"
OUT_DIR = ROOT / "data/round0"
CODERS = ["Brendan", "Ryan"]

SEED = 440
PER_QUARTILE = [13, 13, 12, 12]
MIN_CHARS, MAX_CHARS = 200, 20_000

FONT = "Arial"
FILL_INPUT = PatternFill("solid", fgColor="FFF2CC")
FILL_HEADER = PatternFill("solid", fgColor="1F3864")


def draw_sample():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    candidates = con.execute(
        """
        SELECT a.*, r.stars
        FROM artifacts a LEFT JOIN repos r ON r.full_name = a.repo_full_name
        WHERE a.dedup_primary = 1 AND a.frontmatter_valid = 1
          AND a.content IS NOT NULL AND a.name IS NOT NULL AND trim(a.name) <> ''
          AND a.body_chars BETWEEN ? AND ?
        ORDER BY a.file_sha
        """,
        (MIN_CHARS, MAX_CHARS),
    ).fetchall()

    # English only: the human coders read English only (decided 2026-11-23).
    # Filter before de-duplicating so an English variant of a name can still be chosen.
    english = [r for r in candidates if is_english(r["content"])]
    print(f"candidates: {len(candidates)}, English: {len(english)} ({len(english) / len(candidates):.1%})")

    seen_names, rows = set(), []
    for r in english:  # sorted by file_sha, so the lowest hash per name wins
        key = r["name"].strip().lower()
        if key not in seen_names:
            seen_names.add(key)
            rows.append(r)
    seen_repos, deduped = set(), []
    for r in rows:
        if r["repo_full_name"] not in seen_repos:
            seen_repos.add(r["repo_full_name"])
            deduped.append(r)
    rows = deduped

    by_len = sorted(rows, key=lambda r: (r["body_chars"], r["file_sha"]))
    n = len(by_len)
    quartiles = [by_len[i * n // 4:(i + 1) * n // 4] for i in range(4)]

    rng = random.Random(SEED)
    picked = []
    for q, (stratum, k) in enumerate(zip(quartiles, PER_QUARTILE), start=1):
        for r in rng.sample(stratum, k):
            picked.append((q, r))
    rng.shuffle(picked)  # presentation order, so length doesn't follow the list
    print(f"eligible after one-per-name and one-per-repo: {n}")
    print("quartile bounds (body chars):", [(s[0]["body_chars"], s[-1]["body_chars"]) for s in quartiles])
    return picked


def github_url(repo, path):
    return f"https://github.com/{repo}/blob/HEAD/{quote(path)}"


def clean(text):
    return ILLEGAL_CHARACTERS_RE.sub("", text or "")


def put(ws, ref, value, **style):
    """Write a value as literal text (a leading '=' must not become a formula)."""
    c = ws[ref] if isinstance(ref, str) else ws.cell(*ref)
    c.value = value
    if isinstance(value, str):
        c.data_type = "s"
    for k, v in style.items():
        setattr(c, k, v)
    return c


def build_workbook(sample, coder, path):
    wb = Workbook()
    f = lambda **kw: Font(name=FONT, **kw)  # noqa: E731

    # --- Instructions -------------------------------------------------------
    ws = wb.active
    ws.title = "How to code"
    ws.column_dimensions["A"].width = 110
    lines = [
        (f"Round 0 blind coding: {coder}", f(bold=True, size=14)),
        ("", None),
        ("What this is", f(bold=True)),
        ("50 Agent Skills (SKILL.md files) drawn from the GitSkills sample. You, your teammate and an agent code the same 50, independently.", None),
        ("Goal: in your own words, what does each skill codify? There is no starting category list on purpose.", None),
        ("", None),
        ("Rules", f(bold=True)),
        ("1. Do not look at anyone else's categories until both of you have finished. The overlap and gaps between lists are a result.", None),
        ("2. Code what the skill is FOR (its purpose), not what repo it lives in. Repo context is a separate taxonomy.", None),
        ("3. Use as many categories per skill as genuinely apply (usually 1-2). Reuse your own labels where they fit.", None),
        ("4. Quote the line(s) from the skill that justify each category in the Evidence column.", None),
        ("", None),
        ("How to work", f(bold=True)),
        ("Open the 'Coding' tab. Click a skill's ID (S01...) to read it on its own tab; each tab has a link back.", None),
        ("Fill only the yellow columns: Categories, Evidence quote, Notes. Separate multiple categories with a semicolon.", None),
        ("The GitHub link opens the original file (it may have moved since July 2026).", None),
        ("", None),
        ("Example of the expected format (placeholder labels, so they don't steer your categories)", f(bold=True)),
        ("Categories:  category A; category B", None),
        ('Evidence quote:  "Use this skill when the user asks to ..."  |  "Run the script in scripts/ to ..."', None),
        ("Notes:  unsure whether A and B are really one category", None),
        ("", None),
        ("Sampling", f(bold=True)),
        (f"Distinct English-language skills with valid front matter, {MIN_CHARS:,}-{MAX_CHARS:,} body characters, at most one per skill name and one per repository, "
         f"stratified by length quartile (13/13/12/12), seed {SEED}. Generated by scripts/draw_round0_sample.py.", None),
    ]
    for i, (text, font) in enumerate(lines, start=1):
        put(ws, f"A{i}", text, font=font or f(), alignment=Alignment(wrap_text=True, vertical="top"))

    # --- Coding sheet -------------------------------------------------------
    cs = wb.create_sheet("Coding")
    headers = ["ID", "Skill name", "Description (from front matter)", "Repository", "Stars",
               "Body chars", "GitHub link", "Categories", "Evidence quote", "Notes"]
    widths = [7, 26, 60, 32, 8, 10, 14, 34, 50, 30]
    for col, (h, w) in enumerate(zip(headers, widths), start=1):
        put(cs, (1, col), h, font=f(bold=True, color="FFFFFF"), fill=FILL_HEADER,
            alignment=Alignment(wrap_text=True, vertical="center"))
        cs.column_dimensions[cs.cell(1, col).column_letter].width = w
    cs.freeze_panes = "C2"

    for i, (_, r) in enumerate(sample, start=1):
        sid = f"S{i:02d}"
        row = i + 1
        top = Alignment(wrap_text=True, vertical="top")
        c = put(cs, (row, 1), sid, font=f(color="0563C1", underline="single"), alignment=top)
        link_to_sheet(c, sid)
        put(cs, (row, 2), clean(r["name"]), font=f(bold=True), alignment=top)
        put(cs, (row, 3), clean(r["description"])[:2000], font=f(), alignment=top)
        put(cs, (row, 4), r["repo_full_name"], font=f(), alignment=top)
        put(cs, (row, 5), r["stars"], font=f(), alignment=top)
        put(cs, (row, 6), r["body_chars"], font=f(), alignment=top).number_format = "#,##0"
        c = put(cs, (row, 7), "open on GitHub", font=f(color="0563C1", underline="single"), alignment=top)
        c.hyperlink = github_url(r["repo_full_name"], r["path"])
        for col in (8, 9, 10):
            put(cs, (row, col), None, fill=FILL_INPUT, font=f(), alignment=top)

        # --- One tab per skill ----------------------------------------------
        ss = wb.create_sheet(sid)
        ss.column_dimensions["A"].width = 120
        c = put(ss, "A1", "<- back to Coding", font=f(color="0563C1", underline="single"))
        link_to_sheet(c, "Coding", f"A{row}")
        put(ss, "A2", f"{sid}  {clean(r['name'])}", font=f(bold=True, size=13))
        put(ss, "A3", f"{r['repo_full_name']}  /  {r['path']}", font=f(italic=True, color="595959"))
        for j, line in enumerate(clean(r["content"]).splitlines(), start=5):
            put(ss, (j, 1), line[:32000], font=Font(name="Consolas", size=10),
                alignment=Alignment(wrap_text=True, vertical="top"))

    wb.active = wb.sheetnames.index("Coding")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true",
                   help="overwrite existing coding workbooks (they may contain someone's coding)")
    force = p.parse_args().force

    outs = [OUT_DIR / f"Round0_Coding_{coder}.xlsx" for coder in CODERS]
    existing = [o for o in outs if o.exists()]
    if existing and not force:
        raise SystemExit(
            "refusing to overwrite coding workbooks that may already hold coding:\n  "
            + "\n  ".join(str(o.relative_to(ROOT)) for o in existing)
            + "\nmove them aside, or pass --force if they are blank")

    sample = draw_sample()

    SAMPLE_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(SAMPLE_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "repo_full_name", "path", "file_sha", "name", "body_chars", "length_quartile"])
        for i, (q, r) in enumerate(sample, start=1):
            w.writerow([f"S{i:02d}", r["repo_full_name"], r["path"], r["file_sha"], r["name"], r["body_chars"], q])
    print(f"wrote {SAMPLE_CSV.relative_to(ROOT)}")

    for coder, out in zip(CODERS, outs):
        build_workbook(sample, coder, out)
        print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
