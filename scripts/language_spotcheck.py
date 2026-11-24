"""Hand spot-check of the language detector (issue #52).

The decision that matters is English vs not English (human-coded sets are English-only),
so that is what a person checks. The workbook hides the detector's answer.

    .venv/Scripts/python scripts/language_spotcheck.py draw    # -> data/language_check/Language_Check.xlsx
    .venv/Scripts/python scripts/language_spotcheck.py score   # reads it back -> samples/language_check.csv

Strata (sampling range only: valid front matter, 200-20,000 body chars; Round 0 excluded):
  12 detected 'en', 12 detected another Latin-script language, 6 detected 'mixed'/'unknown'.
CJK and Cyrillic are not checked: the script-range test decides those, not langdetect.
"""
import csv
import random
import sys
from collections import Counter
from urllib.parse import quote

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from db import ROOT, connect
from language import prose

OUT = ROOT / "data/language_check/Language_Check.xlsx"
RESULT = ROOT / "samples/language_check.csv"
SEED = 52
NON_LATIN = ("zh", "ja", "ko", "cyrillic", "other-nonlatin")
STRATA = [  # (name, SQL condition, n)
    ("en", "language = 'en'", 12),
    ("latin_non_en", f"language NOT IN ('en', 'mixed', 'unknown', {', '.join(repr(x) for x in NON_LATIN)})", 12),
    ("mixed_unknown", "language IN ('mixed', 'unknown')", 6),
]
FONT = "Arial"


def draw():
    if OUT.exists():
        sys.exit(f"{OUT.relative_to(ROOT)} exists and may hold answers; move it aside first")
    con = connect()
    round0 = {r[0] for r in con.execute(
        "SELECT item_id FROM sample_items JOIN samples USING (sample_id) WHERE name = 'round0'")}
    rng = random.Random(SEED)
    picked = []
    for stratum, cond, n in STRATA:
        pool = [r for r in con.execute(
            f"""SELECT file_sha, name, repo_full_name, path, language, language_confidence
                FROM skills_with_language
                WHERE frontmatter_valid = 1 AND body_chars BETWEEN 200 AND 20000 AND {cond}
                ORDER BY file_sha""") if r["file_sha"] not in round0]
        picked += [(stratum, r) for r in rng.sample(pool, min(n, len(pool)))]
    rng.shuffle(picked)  # so the strata can't be guessed from the order

    wb = Workbook()
    ws = wb.active
    ws.title = "Check"
    put = lambda ref, v, **kw: setattr(ws[ref], "value", v) or [setattr(ws[ref], k, x) for k, x in kw.items()]  # noqa: E731
    put("A1", "Language spot-check: is each skill written in English?", font=Font(name=FONT, bold=True, size=13))
    put("A2", "Answer Y if the instructions are in English (code, product names and a few foreign words are fine), "
              "N if they are mainly in another language. Fill only the yellow columns. Example: Y | 'English, with some German UI strings'.",
        font=Font(name=FONT, italic=True), alignment=Alignment(wrap_text=True))
    ws.merge_cells("A2:F2")
    ws.row_dimensions[2].height = 32
    headers = ["ID", "Skill name", "Text (first 700 chars, code and front matter removed)", "GitHub link", "English? (Y/N)", "Notes"]
    for col, (h, w) in enumerate(zip(headers, [6, 26, 90, 14, 14, 30]), start=1):
        c = ws.cell(4, col, h)
        c.font = Font(name=FONT, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3864")
        ws.column_dimensions[c.column_letter].width = w
    ws.freeze_panes = "A5"
    key = []
    for i, (stratum, r) in enumerate(picked, start=1):
        row = 4 + i
        text = con.execute("SELECT content FROM gs.artifacts WHERE file_sha = ? AND dedup_primary = 1",
                           (r["file_sha"],)).fetchone()[0]
        snippet = " ".join(prose(text).split())[:700]
        cells = [f"L{i:02d}", r["name"], snippet, "open on GitHub", None, None]
        for col, v in enumerate(cells, start=1):
            c = ws.cell(row, col, v)
            if isinstance(v, str):
                c.data_type = "s"  # a leading '=' must stay text
            c.font = Font(name=FONT)
            c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(row, 4).hyperlink = f"https://github.com/{r['repo_full_name']}/blob/HEAD/{quote(r['path'])}"
        ws.cell(row, 4).font = Font(name=FONT, color="0563C1", underline="single")
        for col in (5, 6):
            ws.cell(row, col).fill = PatternFill("solid", fgColor="FFF2CC")
        key.append([f"L{i:02d}", r["file_sha"], stratum, r["language"], r["language_confidence"]])
    # The answer key goes on a hidden sheet so the checker isn't steered by it.
    ks = wb.create_sheet("key")
    ks.append(["id", "file_sha", "stratum", "detected", "confidence"])
    for k in key:
        ks.append(k)
    ks.sheet_state = "hidden"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(picked)} skills: {dict(Counter(s for s, _ in picked))})")


def score():
    wb = load_workbook(OUT)
    ws, ks = wb["Check"], wb["key"]
    answers = {ws.cell(r, 1).value: ((ws.cell(r, 5).value or "").strip().upper()[:1], ws.cell(r, 6).value)
               for r in range(5, ws.max_row + 1) if ws.cell(r, 1).value}
    rows, missing = [], []
    for kid, sha, stratum, detected, conf in ks.iter_rows(min_row=2, values_only=True):
        human, note = answers.get(kid, ("", None))
        if human not in ("Y", "N"):
            missing.append(kid)
            continue
        rows.append(dict(id=kid, file_sha=sha, stratum=stratum, detected=detected, confidence=conf,
                         human_english=human, detector_english="Y" if detected == "en" else "N",
                         agree=int((detected == "en") == (human == "Y")), notes=note or ""))
    if missing:
        sys.exit(f"no Y/N answer for: {', '.join(missing)}")
    with open(RESULT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {RESULT.relative_to(ROOT)}")
    for stratum in [s for s, _, _ in STRATA]:
        sub = [r for r in rows if r["stratum"] == stratum]
        print(f"  {stratum:14} {sum(r['agree'] for r in sub)}/{len(sub)} agree")
    mu = [r for r in rows if r["stratum"] == "mixed_unknown"]
    print(f"  mixed/unknown judged English by hand: {sum(r['human_english'] == 'Y' for r in mu)}/{len(mu)}")


if __name__ == "__main__":
    {"draw": draw, "score": score}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
