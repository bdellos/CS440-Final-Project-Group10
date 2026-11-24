"""Compare two runs on the same items (issue #15): where do two raters disagree?

Typical pairs: labeler vs skeptic (#48), agent vs human on the held-out set (#47),
seeded vs agent-only codebook in the ablation (#49) once both use the same codebook.

Items can carry several categories, so each item compared falls in exactly one class:
  agree     both raters chose the same set of categories
  partial   the sets overlap but differ
  disjoint  no category in common
  missing   only one of the two raters has labeled it (items neither has labeled are not counted)
This is plain set comparison of codebook keys: no model and no similarity score. Categories are
flat (no hierarchy), so two different keys disagree even if they are related.

PROPOSED_NEW never matches anything, not even the other rater's PROPOSED_NEW: proposals are
free-form, so whether two of them mean the same thing is for a person to decide. An item where
both raters proposed something is therefore 'disjoint' (or 'partial' if they also share a
codebook category), never 'agree'.
Agreement statistics beyond the raw rate (Cohen's kappa) belong to the analyst (#47).
"""


class CompareError(ValueError):
    """The two runs can't be compared; the message says why."""


KINDS = ("agree", "partial", "disjoint", "missing")
PROPOSED = "PROPOSED_NEW"


def _run(con, run_id):
    r = con.execute(
        """SELECT r.run_id, r.sample_id, r.taxonomy, r.codebook_version_id, r.rater, r.rater_kind, r.model,
                  r.purpose, s.name AS sample, cv.version AS codebook_version, cv.variant AS codebook_variant
           FROM runs r JOIN samples s USING (sample_id)
           LEFT JOIN codebook_versions cv USING (codebook_version_id) WHERE r.run_id = ?""", (run_id,)).fetchone()
    if r is None:
        raise CompareError(f"run {run_id} does not exist")
    return r


def _labels(con, run_id):
    out = {}
    for item, cat in con.execute("""SELECT a.item_id, l.category_key FROM annotations a
                                    JOIN annotation_labels l USING (annotation_id) WHERE a.run_id = ?""", (run_id,)):
        out.setdefault(item, set()).add(cat)
    return out


def _evidence(con, run_id, item_id, per_label=2):
    rows = con.execute(
        """SELECT e.category_key, e.quote_en FROM evidence e JOIN annotations a USING (annotation_id)
           WHERE a.run_id = ? AND a.item_id = ? ORDER BY e.evidence_id""", (run_id, item_id)).fetchall()
    ev = {}
    for key, quote in rows:
        key = "PROPOSED_NEW" if key and key.startswith("PROPOSED_NEW:") else key
        if len(ev.setdefault(key, [])) < per_label:
            ev[key].append(quote)
    note = con.execute("SELECT notes FROM annotations WHERE run_id = ? AND item_id = ?", (run_id, item_id)).fetchone()
    proposals = [r[0] for r in con.execute(
        """SELECT p.proposed_name FROM proposals p JOIN annotations a USING (annotation_id)
           WHERE a.run_id = ? AND a.item_id = ?""", (run_id, item_id))]
    return {"evidence": ev, "proposals": proposals, "notes": note[0] if note else None}


def compare(con, run_a: int, run_b: int, include_agreements: bool = False, offset: int = 0, limit: int = 50) -> dict:
    if run_a == run_b:
        raise CompareError("pick two different runs")
    a, b = _run(con, run_a), _run(con, run_b)
    if a["sample_id"] != b["sample_id"]:
        raise CompareError(f"run {run_a} is on sample {a['sample']!r} but run {run_b} is on {b['sample']!r}")
    if a["taxonomy"] != b["taxonomy"]:
        raise CompareError(f"run {run_a} is {a['taxonomy']} but run {run_b} is {b['taxonomy']}")
    if a["codebook_version_id"] is None or b["codebook_version_id"] is None:
        raise CompareError("Round 0 runs use free-form codes, which can't be matched category by category; "
                           "compare those lists by hand (#40)")
    if a["codebook_version_id"] != b["codebook_version_id"]:
        raise CompareError(f"run {run_a} uses codebook v{a['codebook_version']:02d} ({a['codebook_variant']}) but "
                           f"run {run_b} uses v{b['codebook_version']:02d} ({b['codebook_variant']}); "
                           "categories are only comparable within one codebook version")

    la, lb = _labels(con, run_a), _labels(con, run_b)
    order = {r[0]: r[1] for r in con.execute("SELECT item_id, position FROM sample_items WHERE sample_id = ?",
                                             (a["sample_id"],))}
    rows = []
    for item in sorted(set(la) | set(lb), key=lambda i: order.get(i, 0)):
        sa, sb = la.get(item, set()), lb.get(item, set())
        # Proposals are free-form, so one rater's PROPOSED_NEW never matches the other's:
        # only codebook categories can agree, and any proposal makes an item at best 'partial'.
        both = (sa & sb) - {PROPOSED}
        if not sa or not sb:
            kind = "missing"
        elif sa == sb and PROPOSED not in sa:
            kind = "agree"
        else:
            kind = "partial" if both else "disjoint"
        rows.append({"item_id": item, "position": order.get(item), "kind": kind, "labels_a": sorted(sa),
                     "labels_b": sorted(sb), "both": sorted(both), "only_a": sorted(sa - both),
                     "only_b": sorted(sb - both)})

    counts = {k: sum(r["kind"] == k for r in rows) for k in KINDS}
    compared = counts["agree"] + counts["partial"] + counts["disjoint"]
    listed = [r for r in rows if include_agreements or r["kind"] != "agree"]
    page = listed[offset:offset + limit]
    for r in page:
        if r["kind"] != "missing" or r["labels_a"]:
            r["a"] = _evidence(con, run_a, r["item_id"])
        if r["kind"] != "missing" or r["labels_b"]:
            r["b"] = _evidence(con, run_b, r["item_id"])
        name = con.execute("SELECT name FROM skills WHERE file_sha = ?", (r["item_id"],)).fetchone()
        r["name"] = name[0] if name else None

    def side(r):
        return {k: r[k] for k in ("run_id", "rater", "rater_kind", "model", "purpose")}
    return {
        "run_a": side(a), "run_b": side(b), "sample": a["sample"], "taxonomy": a["taxonomy"],
        "codebook": {"version": a["codebook_version"], "variant": a["codebook_variant"]},
        "summary": {**counts, "items_compared": compared,
                    "exact_agreement": round(counts["agree"] / compared, 4) if compared else None},
        "total_listed": len(listed), "offset": offset, "items": page,
    }
