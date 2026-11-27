"""Final results from the stored labels: frequencies, purpose x context cross-tab (#50), codebook
evolution (#51), results by language (#54) and labeler-vs-skeptic disagreements (#48).

    .venv/Scripts/python analysis/results.py            # reads labels/dump.sql, writes analysis/results/

Outputs (analysis/results/): results.md (every table, with the numbers the report cites) and
figures fig_purpose.png, fig_context.png, fig_crosstab.png, fig_evolution.png, fig_language.png.

Final set: the skills of `heldout` + `final-01..10` that have a finished labeler run with the frozen
purpose codebook, joined to their repository's label from the finished context-classifier run on the
matching `<sample>-repos` sample (frozen context codebook). Repo samples are derived from skill
samples (stratum `skill:<file_sha>`), so context is counted per skill. A skill with two purpose labels
counts once in each (label assignments); shares of skills are given alongside.
"""
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
DUMP = ROOT / "labels/dump.sql"
OUT = ROOT / "analysis/results"
FINAL_SAMPLES = ["heldout"] + [f"final-{i:02d}" for i in range(1, 11)]

# Reference palette (dataviz skill, light mode): sequential blue ramp, ink tokens, surface.
BLUE = "#2a78d6"
ORANGE = "#eb6834"
SEQ = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb"


def load():
    con = sqlite3.connect(":memory:")
    con.executescript(DUMP.read_text(encoding="utf-8"))
    return con


def frozen_version(con, taxonomy):
    return con.execute("SELECT codebook_version_id, version FROM codebook_versions WHERE taxonomy = ? "
                       "AND variant = 'main' AND frozen = 1", (taxonomy,)).fetchone()


def run_for(con, sample, taxonomy, rater, cv_id):
    row = con.execute("""SELECT MAX(r.run_id) FROM runs r JOIN samples s USING (sample_id)
                         WHERE s.name = ? AND r.taxonomy = ? AND r.rater = ? AND r.codebook_version_id = ?
                           AND r.finished_at IS NOT NULL""", (sample, taxonomy, rater, cv_id)).fetchone()
    return row[0]


def labels(con, run_id):
    out = defaultdict(set)
    for item, cat in con.execute("SELECT a.item_id, l.category_key FROM annotations a JOIN annotation_labels l "
                                 "USING (annotation_id) WHERE a.run_id = ?", (run_id,)):
        if not cat.startswith("PROPOSED_NEW"):  # a proposal-only record has no codebook label
            out[item].add(cat)
        else:
            out.setdefault(item, set())
    return out


def final_set(con):
    """[{sha, sample, purpose:set, context:set|None, language}] and the runs used."""
    pcv, ccv = frozen_version(con, "purpose"), frozen_version(con, "context")
    rows, used, missing = [], [], []
    for s in FINAL_SAMPLES:
        prun = run_for(con, s, "purpose", "labeler", pcv[0])
        if prun is None:
            missing.append(s)
            continue
        crun = run_for(con, f"{s}-repos", "context", "context-classifier", ccv[0])
        used.append((s, prun, crun))
        plab, clab = labels(con, prun), (labels(con, crun) if crun else {})
        skill_to_repo = {st[len("skill:"):]: item for item, st in con.execute(
            "SELECT i.item_id, i.stratum FROM sample_items i JOIN samples x USING (sample_id) WHERE x.name = ?",
            (f"{s}-repos",)) if st and st.startswith("skill:")}
        lang = dict(con.execute("SELECT item_id, skill_language FROM annotations WHERE run_id = ?", (prun,)))
        for sha, cats in plab.items():
            repo = skill_to_repo.get(sha)
            rows.append({"sha": sha, "sample": s, "purpose": cats, "repo": repo,
                         "context": clab.get(repo) if repo else None, "language": lang.get(sha) or "?"})
    return rows, used, missing, pcv[1], ccv[1]


def codebook_keys(taxonomy):
    import codebook
    out = []
    for f in sorted((ROOT / "codebook" / taxonomy).glob("v*.md")):
        cb = codebook.parse(f)
        out.append((cb.version, [c.key for c in cb.categories]))
    return out


# --- figures -------------------------------------------------------------------------------

def _style(ax):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    ax.set_facecolor(SURFACE)


def bar_figure(path, counts: Counter, total, title, xlabel):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    items = counts.most_common()[::-1]
    fig, ax = plt.subplots(figsize=(6.4, 0.32 * len(items) + 0.9), dpi=200, facecolor=SURFACE)
    _style(ax)
    ys = range(len(items))
    ax.barh(ys, [v for _, v in items], height=0.62, color=BLUE, edgecolor=SURFACE, linewidth=1)
    ax.set_yticks(list(ys), [k for k, _ in items], fontsize=9, color=INK)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    top = max(v for _, v in items)
    for y, (_, v) in zip(ys, items):
        ax.text(v + top * 0.01, y, f"{v} ({v / total:.0%})" if v / total >= 0.005 else f"{v} (<1%)", va="center", fontsize=8, color=INK2)
    ax.set_xlim(0, top * 1.18)
    ax.set_xlabel(xlabel, fontsize=9, color=INK2)
    ax.set_title(title, loc="left", fontsize=10.5, color=INK)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def heatmap_figure(path, table, prows, ccols, col_tot):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    share = [[table[p][c] / col_tot[c] if col_tot[c] else 0 for c in ccols] for p in prows]
    cmap = LinearSegmentedColormap.from_list("seq_blue", SEQ)
    fig, ax = plt.subplots(figsize=(7.2, 0.36 * len(prows) + 1.6), dpi=200, facecolor=SURFACE)
    vmax = max(max(r) for r in share) or 1
    ax.imshow(share, cmap=cmap, vmin=0, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(ccols)), [f"{c}\n(n={col_tot[c]})" for c in ccols], fontsize=8, color=INK)
    ax.set_yticks(range(len(prows)), prows, fontsize=8.5, color=INK)
    ax.tick_params(length=0)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.set_xticks([x - 0.5 for x in range(1, len(ccols))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(prows))], minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2)
    ax.tick_params(which="minor", length=0)
    for i, p in enumerate(prows):
        for j, c in enumerate(ccols):
            n = table[p][c]
            if n:
                v = share[i][j]
                ax.text(j, i, f"{v:.0%}\n{n}", ha="center", va="center", fontsize=6.5,
                        color="#ffffff" if v > vmax * 0.55 else INK)
    ax.set_title("Purpose by repository context (column share, count)", loc="left", fontsize=10, color=INK)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def evolution_figure(path, series):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.0, 2.8), dpi=200, facecolor=SURFACE)
    _style(ax)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_color(GRID)
    for (name, pts), color in zip(series.items(), (BLUE, ORANGE)):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        ax.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=6,
                markeredgecolor=SURFACE, markeredgewidth=2)
        ax.text(xs[-1] + 0.08, ys[-1], f"{name} (frozen v{xs[-1]:02d})", va="center", fontsize=8.5, color=INK2)
    ax.set_xticks(sorted({p[0] for pts in series.values() for p in pts}),
                  [f"v{v:02d}" for v in sorted({p[0] for pts in series.values() for p in pts})])
    ax.set_ylabel("categories", fontsize=9, color=INK2)
    from matplotlib.ticker import MaxNLocator
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_ylim(0, max(p[1] for pts in series.values() for p in pts) + 3)
    ax.set_xlim(-0.2, max(p[0] for pts in series.values() for p in pts) + 1.6)
    ax.legend(list(series), frameon=False, fontsize=8, loc="lower right", labelcolor=INK2)
    ax.set_title("Codebook size by version", loc="left", fontsize=10.5, color=INK)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# --- tables -------------------------------------------------------------------------------------

def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def main():
    con = load()
    rows, used, missing, pv, cv = final_set(con)
    OUT.mkdir(parents=True, exist_ok=True)
    n = len(rows)
    md = ["# Results (generated)", "",
          f"Generated by `analysis/results.py` from `labels/dump.sql`. Purpose codebook v{pv:02d} (frozen), "
          f"context codebook v{cv:02d} (frozen).", "",
          f"**Final set:** {n} skills from {len(used)} samples "
          f"({', '.join(f'{s} (purpose run {p}, context run {c})' for s, p, c in used)})."]
    if missing:
        md += [f"**Not yet labeled for purpose:** {', '.join(missing)}. Rerun this script when they are."]
    md += [""]

    # purpose frequencies
    proposal_only = [r for r in rows if not r["purpose"]]
    rows = [r for r in rows if r["purpose"]]
    n = len(rows)
    pc = Counter(c for r in rows for c in r["purpose"])
    multi = sum(len(r["purpose"]) > 1 for r in rows)
    if proposal_only:
        md += [f"{len(proposal_only)} skill(s) got only a PROPOSED_NEW (no codebook category) and are left out "
               "below; the researchers decide the proposal (`scripts/proposals.py list`).", ""]
    md += ["## Purpose (what skills codify)", "",
           f"{n} skills, {sum(pc.values())} label assignments ({multi} skills have two labels). "
           "Share = share of skills with that label.", ""]
    md += md_table(["Category", "Skills", "Share"], [(f"`{k}`", v, f"{v / n:.1%}") for k, v in pc.most_common()])
    bar_figure(OUT / "fig_purpose.png", pc, n, f"What skills codify (n = {n} skills)", "skills")

    # context frequencies
    with_ctx = [r for r in rows if r["context"]]
    cc = Counter(c for r in with_ctx for c in r["context"])
    md += ["", "## Context (where skills live), per skill", "",
           f"{len(with_ctx)} of {n} skills have a context label for their repository.", ""]
    md += md_table(["Category", "Skills", "Share"],
                   [(f"`{k}`", v, f"{v / len(with_ctx):.1%}") for k, v in cc.most_common()])
    bar_figure(OUT / "fig_context.png", cc, len(with_ctx), f"Where skills live (n = {len(with_ctx)} skills)",
               "skills")

    # cross-tab (#50)
    prows = [k for k, _ in pc.most_common()]
    ccols = [k for k, _ in cc.most_common()]
    table = {p: Counter() for p in prows}
    for r in with_ctx:
        for p in r["purpose"]:
            for c in r["context"]:
                table[p][c] += 1
    col_tot = {c: sum(table[p][c] for p in prows) for c in ccols}
    md += ["", "## Purpose x context (#50)", "",
           "Counts of purpose label assignments by the context of the skill's repository. Column % = share "
           "of that context's purpose labels.", ""]
    md += md_table(["Purpose \\ Context"] + [f"`{c}`" for c in ccols] + ["Total"],
                   [[f"`{p}`"] + [f"{table[p][c]} ({table[p][c] / col_tot[c]:.0%})" if col_tot[c] else "0"
                                  for c in ccols] + [sum(table[p].values())] for p in prows]
                   + [["Total"] + [col_tot[c] for c in ccols] + [sum(col_tot.values())]])
    # biggest departures from the overall mix (lift), for the narrative
    overall = {p: sum(table[p].values()) / sum(col_tot.values()) for p in prows}
    lifts = []
    for c in ccols:
        for p in prows:
            if col_tot[c] >= 20 and table[p][c] >= 5:
                lifts.append((table[p][c] / col_tot[c] / overall[p], p, c, table[p][c]))
    md += ["", "Over-represented purposes per context (share in that context / overall share; contexts with "
           ">= 20 labels, cells with >= 5):", ""]
    md += md_table(["Context", "Purpose", "Count", "Lift"],
                   [(f"`{c}`", f"`{p}`", k, f"{l:.2f}x") for l, p, c, k in sorted(lifts, reverse=True)[:12]])
    heatmap_figure(OUT / "fig_crosstab.png", table, prows, ccols, col_tot)

    # language (#54)
    lc = Counter(r["language"] for r in rows)
    md += ["", "## By language (#54)", "",
           "Language as detected for each skill (stored on its purpose label). Human-coded sets (Round 0, "
           "held-out) are English-only, so kappa covers English skills only.", ""]
    md += md_table(["Language", "Skills", "Share"], [(k, v, f"{v / n:.1%}") for k, v in lc.most_common()])
    bar_figure(OUT / "fig_language.png", lc, n, f"Skill language in the final set (n = {n} skills)", "skills")
    en = [r for r in rows if r["language"] == "en"]
    non = [r for r in rows if r["language"] != "en"]
    if non:
        pe, pn = Counter(c for r in en for c in r["purpose"]), Counter(c for r in non for c in r["purpose"])
        md += ["", f"Purpose share, English ({len(en)}) vs non-English ({len(non)}) skills:", ""]
        md += md_table(["Category", "English", "Non-English"],
                       [(f"`{k}`", f"{pe[k] / len(en):.1%}", f"{pn[k] / len(non):.1%}") for k in prows])
        mostly = [k for k in prows if pn[k] > pe[k] and pn[k] / (pn[k] + pe[k]) > 0.5]
        md += ["", "Categories occurring mostly in non-English skills: "
               + (", ".join(f"`{k}`" for k in mostly) if mostly else "none") + "."]

    # codebook evolution (#51)
    series = {}
    md += ["", "## Codebook evolution (#51)", ""]
    for tax in ("purpose", "context"):
        vers = codebook_keys(tax)
        series[tax] = [(v, len(keys)) for v, keys in vers if v > 0]
        rowsv, prev = [], None
        for v, keys in vers:
            added = sorted(set(keys) - set(prev or [])) if prev is not None else keys
            removed = sorted(set(prev or []) - set(keys))
            rowsv.append((f"v{v:02d}", len(keys), ", ".join(f"`{k}`" for k in added) or "-",
                          ", ".join(f"`{k}`" for k in removed) or "-"))
            prev = keys
        md += [f"**{tax}**", ""] + md_table(["Version", "Categories", "Added", "Removed"], rowsv) + [""]
    md += ["Context v02 and v03 changed rules, not categories (personal collections -> skill-catalog; "
           "starting points -> template; gone-from-GitHub without description -> unclear). Purpose v01 came "
           "from 46 agent codes + 12 researcher codes (Round 0); v02 added `version-control` from the "
           "researchers' reading of round 1's imperfect-fit notes. The agents made no proposals during the "
           "coding rounds; the only ones came during final labeling, after the freeze (see "
           "`scripts/proposals.py list`).", ""]
    evolution_figure(OUT / "fig_evolution.png", series)

    # labeler vs skeptic (#48)
    pcv = frozen_version(con, "purpose")
    lab, sk = run_for(con, "heldout", "purpose", "labeler", pcv[0]), run_for(con, "heldout", "purpose", "skeptic", pcv[0])
    if lab and sk:
        sys.path.insert(0, str(ROOT / "analysis"))
        import kappa
        a, b = kappa.labels_of(con, lab), kappa.labels_of(con, sk)
        comp = kappa.compare(a, b)
        notes = dict(con.execute("SELECT item_id, notes FROM annotations WHERE run_id = ?", (sk,)))
        md += ["## Labeler vs skeptic on the held-out set (#48)", "",
               f"Runs {lab} (labeler) and {sk} (skeptic), {comp['n']} skills: Cohen's kappa "
               f"{kappa.fmt(comp['kappa'])}, exact agreement {comp['exact']:.0%}. Same model (Claude Haiku "
               "5.5), same codebook and skills; the skeptic weighs the strongest rival category, applies "
               "Exclude rules strictly and adds second labels only on clear evidence, and never sees the "
               "labeler's labels. Disagreement therefore marks category boundaries that are fragile under "
               "a stricter reading (plus run-to-run variation), not independent human disagreement.", ""]
        dis = [(i, sorted(a[i]), sorted(b[i])) for i in sorted(a.keys() & b.keys()) if a[i] != b[i]]
        md += md_table(["Skill (file_sha)", "Labeler", "Skeptic", "Skeptic's note"],
                       [(f"`{i[:12]}`", ", ".join(x), ", ".join(y), (notes.get(i) or "").replace("|", "/")[:200])
                        for i, x, y in dis])
        md += ["", "Per-category kappa (binary):", ""]
        md += md_table(["Category", "Labeler uses", "Skeptic uses", "Kappa"],
                       [(f"`{c}`", u[0], u[1], kappa.fmt(comp["per_category"][c])) for c, u in comp["uses"].items()])
    # full-text relabel (get_skill fix): earlier run vs latest run per sample and rater
    sys.path.insert(0, str(ROOT / "analysis"))
    import kappa as _k
    pairs = []
    for s in FINAL_SAMPLES:
        for rater in ("labeler", "skeptic"):
            ids = [r[0] for r in con.execute(
                """SELECT r.run_id FROM runs r JOIN samples x USING (sample_id) WHERE x.name = ? AND r.rater = ?
                   AND r.taxonomy = 'purpose' AND r.codebook_version_id = ? AND r.finished_at IS NOT NULL
                   ORDER BY r.run_id""", (s, rater, pcv[0]))]
            if len(ids) > 1:
                c = _k.compare(_k.labels_of(con, ids[0]), _k.labels_of(con, ids[-1]))
                pairs.append((s, rater, ids[0], ids[-1], c))
    if pairs:
        md += ["", "## Full-text relabel: earlier vs latest run", "",
               "Runs before the get_skill fix (commit 544e94f) could cap the skill text they read; run 24 "
               "reported about 30 skills labeled from partial text. These samples were relabeled with the full "
               "text; every table above uses the latest run. Agreement between the two runs mixes the effect "
               "of the full text with ordinary run-to-run variation.", ""]
        md += md_table(["Sample", "Rater", "Earlier run", "Latest run", "Items", "Exact agreement", "Kappa"],
                       [(s, r, a, b, c["n"], f"{c['exact']:.0%}", _k.fmt(c["kappa"])) for s, r, a, b, c in pairs])
    (OUT / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}/results.md and 5 figures; final set {n} skills"
          + (f"; missing purpose runs: {missing}" if missing else ""))


if __name__ == "__main__":
    main()
