"""Build the held-out labeling workbooks (#45, #46): one per researcher, for hand-labeling the
`heldout` skills with the frozen purpose codebook and their repositories (`heldout-repos`) with the
frozen context codebook. Cohen's kappa (#47) compares these labels with the agents' and each other's.

    .venv/Scripts/python scripts/heldout_workbook.py            # data/heldout/Heldout_Labeling_<Coder>.xlsx

The workbooks show no agent labels: only the skill, its repository and the two codebooks.
Rows are H01..H50 = positions 1..50 of the `heldout` sample; the repo of H07 is position 7 of
`heldout-repos` (derived from `heldout` in the same order). scripts/import_heldout.py reads them back.

Each item has its own tab with the full skill text and the repository context the context-classifier
saw (get_repo_context, rebuilt from the GitHub cache). Evidence is quoted from those tabs, so it
passes the same exact-quote check as the agents' evidence.
"""
import argparse
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codebook  # noqa: E402
from db import ROOT, connect  # noqa: E402
from draw_round0_sample import FILL_HEADER, FILL_INPUT, FONT, clean, github_url, link_to_sheet, put  # noqa: E402

CODERS = ["Brendan", "Ryan"]
OUT_DIR = ROOT / "data/heldout"
SKILLS, REPOS = "heldout", "heldout-repos"
REPO_LINES_MAX = 3000           # a repo's context can list thousands of paths; the tab keeps the first lines
HEADERS = ["ID", "Skill name", "Description (from front matter)", "Repository",
           "Purpose categories", "Purpose evidence", "Context category", "Context evidence", "Notes"]
WIDTHS = [7, 26, 55, 30, 24, 50, 22, 50, 30]


def frozen_codebook(con, taxonomy):
    """(version, path, keys) of the frozen version of a taxonomy; refuses if it isn't frozen."""
    row = con.execute("SELECT version, file_path FROM codebook_versions WHERE taxonomy = ? AND variant = 'main' "
                      "AND frozen = 1", (taxonomy,)).fetchone()
    if row is None:
        raise SystemExit(f"the {taxonomy} codebook isn't frozen yet (#43); held-out labeling uses frozen versions")
    cb = codebook.parse(ROOT / row[1])
    return row[0], ROOT / row[1], [c.key for c in cb.categories]


def items(con):
    """[(hid, skill row, repo)] in sample order."""
    def ordered(name):
        return [r[0] for r in con.execute("SELECT i.item_id FROM sample_items i JOIN samples s USING (sample_id) "
                                          "WHERE s.name = ? ORDER BY i.position", (name,))]
    shas, repos = ordered(SKILLS), ordered(REPOS)
    if not shas or len(shas) != len(repos):
        raise SystemExit(f"samples {SKILLS!r} and {REPOS!r} must both exist with the same number of items")
    out = []
    for i, (sha, repo) in enumerate(zip(shas, repos), start=1):
        r = con.execute("SELECT file_sha, name, description, repo_full_name, path, content FROM gs.artifacts "
                        "WHERE file_sha = ? AND dedup_primary = 1", (sha,)).fetchone()
        if r["repo_full_name"] != repo:
            raise SystemExit(f"position {i}: skill {sha[:8]} is in {r['repo_full_name']}, but {REPOS} has {repo}")
        out.append((f"H{i:02d}", r, repo))
    return out


def codebook_sheet(wb, title, path, f):
    ws = wb.create_sheet(title)
    ws.column_dimensions["A"].width = 120
    text = codebook._COMMENT.sub("", path.read_text(encoding="utf-8"))
    for j, line in enumerate(text.splitlines(), start=1):
        bold = line.startswith("#")
        put(ws, (j, 1), clean(line), font=f(bold=bold, size=12 if line.startswith("## ") else 10),
            alignment=Alignment(wrap_text=True, vertical="top"))


def build(con, coder, path, repo_text):
    pv, ppath, pkeys = frozen_codebook(con, "purpose")
    cv, cpath, ckeys = frozen_codebook(con, "context")
    wb = Workbook()
    f = lambda **kw: Font(name=FONT, **kw)  # noqa: E731

    ws = wb.active
    ws.title = "How to label"
    ws.column_dimensions["A"].width = 110
    lines = [
        (f"Held-out labeling: {coder}", f(bold=True, size=14)),
        ("", None),
        ("What this is", f(bold=True)),
        ("50 skills that the agents also labeled. Label each one yourself, with the frozen codebooks, without looking "
         "at the agents' or your teammate's labels. Cohen's kappa compares the three.", None),
        (f"Purpose codebook v{pv:02d} and context codebook v{cv:02d} are on their own tabs.", None),
        ("", None),
        ("For each row", f(bold=True)),
        ("1. Purpose categories: what the skill codifies. One category key from the purpose codebook (the dropdown); "
         "a second only when the skill clearly does both, separated by a semicolon.", None),
        ("2. Purpose evidence: a sentence copied exactly from the skill text on the item's tab. Several quotes: separate with |.", None),
        ("3. Context category: what kind of repository the skill lives in. One key from the context codebook.", None),
        ("4. Context evidence: a line copied exactly from the 'Repository context' part of the item's tab (README text, "
         "description, or a fact like `skill_md_files: 12`).", None),
        ("5. Notes (optional, max 300 characters): doubts, the second-best category.", None),
        ("", None),
        ("How to work", f(bold=True)),
        ("Open the 'Labeling' tab. Click an ID (H01...) to read the skill and its repository; each tab links back.", None),
        ("Fill only the yellow columns. Quotes must be exact (spacing aside; ... may skip text), or the import rejects the row.", None),
        ("Repository context: if it says available: false, the repo is gone from GitHub and only the dataset fields are "
         "left; follow the context codebook's rule for that case.", None),
    ]
    for i, (text, font) in enumerate(lines, start=1):
        put(ws, f"A{i}", text, font=font or f(), alignment=Alignment(wrap_text=True, vertical="top"))

    ls = wb.create_sheet("Labeling")
    for col, (h, w) in enumerate(zip(HEADERS, WIDTHS), start=1):
        put(ls, (1, col), h, font=f(bold=True, color="FFFFFF"), fill=FILL_HEADER,
            alignment=Alignment(wrap_text=True, vertical="center"))
        ls.column_dimensions[ls.cell(1, col).column_letter].width = w
    ls.freeze_panes = "C2"
    rows = items(con)
    # Dropdowns list the keys; a second purpose key typed with ';' is allowed (no error, just a hint).
    pdv = DataValidation(type="list", formula1=f'"{",".join(pkeys)}"', showErrorMessage=False)
    cdv = DataValidation(type="list", formula1=f'"{",".join(ckeys)}"', showErrorMessage=True,
                         error="Use one key from the context codebook tab.")
    ls.add_data_validation(pdv)
    ls.add_data_validation(cdv)
    top = Alignment(wrap_text=True, vertical="top")
    for n, (hid, r, repo) in enumerate(rows, start=2):
        c = put(ls, (n, 1), hid, font=f(color="0563C1", underline="single"), alignment=top)
        link_to_sheet(c, hid)
        put(ls, (n, 2), clean(r["name"]), font=f(bold=True), alignment=top)
        put(ls, (n, 3), clean(r["description"])[:2000], font=f(), alignment=top)
        put(ls, (n, 4), repo, font=f(), alignment=top)
        for col in range(5, 10):
            put(ls, (n, col), None, fill=FILL_INPUT, font=f(), alignment=top)
        pdv.add(ls.cell(n, 5))
        cdv.add(ls.cell(n, 7))

        ss = wb.create_sheet(hid)
        ss.column_dimensions["A"].width = 120
        c = put(ss, "A1", "<- back to Labeling", font=f(color="0563C1", underline="single"))
        link_to_sheet(c, "Labeling", f"A{n}")
        put(ss, "A2", f"{hid}  {clean(r['name'])}", font=f(bold=True, size=13))
        c = put(ss, "A3", f"{r['repo_full_name']}  /  {r['path']}  (open on GitHub)",
                font=f(italic=True, color="0563C1", underline="single"))
        c.hyperlink = github_url(r["repo_full_name"], r["path"])
        j = 5
        put(ss, (j, 1), "SKILL TEXT", font=f(bold=True))
        for line in clean(r["content"]).splitlines():
            j += 1
            put(ss, (j, 1), line[:32000], font=Font(name="Consolas", size=10), alignment=top)
        j += 2
        put(ss, (j, 1), "REPOSITORY CONTEXT (what the context-classifier saw)", font=f(bold=True))
        text = repo_text(repo)
        ctx = clean(text).splitlines() if text else ["(no cached GitHub context for this repository)"]
        for line in ctx[:REPO_LINES_MAX]:
            j += 1
            put(ss, (j, 1), line[:32000], font=Font(name="Consolas", size=10), alignment=top)
        if len(ctx) > REPO_LINES_MAX:
            put(ss, (j + 1, 1), f"... {len(ctx) - REPO_LINES_MAX} more lines (mostly file paths) not shown",
                font=f(italic=True, color="595959"))

    codebook_sheet(wb, f"Purpose codebook v{pv:02d}", ppath, f)
    codebook_sheet(wb, f"Context codebook v{cv:02d}", cpath, f)
    wb.active = wb.sheetnames.index("Labeling")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return len(rows)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--force", action="store_true", help="overwrite existing workbooks (they may hold someone's labels)")
    a = p.parse_args(argv)
    outs = [OUT_DIR / f"Heldout_Labeling_{c}.xlsx" for c in CODERS]
    existing = [o for o in outs if o.exists()]
    if existing and not a.force:
        raise SystemExit("refusing to overwrite workbooks that may already hold labels:\n  "
                         + "\n  ".join(str(o.relative_to(ROOT)) for o in existing))
    from github_server import evidence_text
    con = connect()
    for coder, out in zip(CODERS, outs):
        n = build(con, coder, out, evidence_text)
        print(f"wrote {out.relative_to(ROOT)} ({n} items)")


if __name__ == "__main__":
    main()
