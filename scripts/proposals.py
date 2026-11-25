"""Record the researchers' decisions on PROPOSED_NEW proposals (#42).

    .venv/Scripts/python scripts/proposals.py list                       # pending proposals
    .venv/Scripts/python scripts/proposals.py list --status all --run 7
    .venv/Scripts/python scripts/proposals.py decide 12 --accept --by both --note "keep as its own category"
    .venv/Scripts/python scripts/proposals.py decide 13 --merge testing-qa --by brendan
    .venv/Scripts/python scripts/proposals.py decide 14 --reject --by ryan --note "a kind of review-audit"

Every proposal made in a round must be decided before the codebook-consolidator writes the next
version (it stops while any is pending). A merge target must be a category of the codebook the
proposal was made against. A decision can be changed with --redo until a codebook version has
taken the proposal in (resulting_version_id, set by `codebook.py register`).

For people only: the labels guard (#32) blocks agents from running this script, so an agent can
propose categories but never decide them.
"""
import argparse
import re
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review  # noqa: E402
from db import connect  # noqa: E402


class DecisionError(ValueError):
    pass


def decide(con, proposal_id: int, status: str, by: str, merged_into: str | None = None,
           note: str | None = None, redo: bool = False) -> dict:
    if status not in ("accepted", "merged", "rejected"):
        raise DecisionError(f"status must be accepted, merged or rejected, got {status!r}")
    if not re.fullmatch(r"[a-z]+", by or ""):
        raise DecisionError(f"--by must be a lowercase first name or 'both', got {by!r}")
    row = con.execute(
        """SELECT p.proposal_id, p.proposed_name, p.status, p.resulting_version_id, r.codebook_version_id
           FROM proposals p JOIN annotations a USING (annotation_id) JOIN runs r USING (run_id)
           WHERE p.proposal_id = ?""", (proposal_id,)).fetchone()
    if row is None:
        raise DecisionError(f"no proposal {proposal_id}")
    if row["resulting_version_id"] is not None:
        raise DecisionError(f"proposal {proposal_id} is already in a codebook version; it can't be changed")
    if row["status"] != "pending" and not redo:
        raise DecisionError(f"proposal {proposal_id} is already {row['status']}; pass --redo to change the decision")
    if status == "merged":
        known = {r[0] for r in con.execute("SELECT category_key FROM categories WHERE codebook_version_id = ?",
                                            (row["codebook_version_id"],))}
        if merged_into not in known:
            raise DecisionError(f"{merged_into!r} is not a category of the codebook this proposal was made against "
                                f"(categories: {', '.join(sorted(known)) or 'none'})")
    elif merged_into:
        raise DecisionError("--merge takes the target category; use it instead of --accept / --reject")
    with con:
        con.execute("""UPDATE proposals SET status = ?, merged_into = ?, decided_by = ?, decision_note = ?,
                       decided_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE proposal_id = ?""",
                    (status, merged_into if status == "merged" else None, by, note, proposal_id))
    return {"proposal_id": proposal_id, "name": row["proposed_name"], "status": status, "merged_into": merged_into}


def show(res: dict) -> None:
    print(f"{res['total']} proposal(s). All statuses: {res['all_statuses']}")
    for p in res["proposals"]:
        print(f"\n#{p['proposal_id']} [{p['status']}] {p['proposed_name']}  (run {p['run_id']}, {p['rater']}, "
              f"{p['taxonomy']}, item {p['item_id'][:12]}{', non-English' if p.get('skill_language') not in (None, 'en') else ''})")
        for label, text in (("definition", p["definition"]), ("why new", p["justification"])):
            print(textwrap.fill(f"{label}: {text}", 100, initial_indent="  ", subsequent_indent="    "))
        for ev in p["evidence"][:2]:
            print(textwrap.fill(f'evidence: "{ev["quote_en"]}"', 100, initial_indent="  ", subsequent_indent="    "))
        if p["status"] != "pending":
            extra = f" into {p['merged_into']}" if p["merged_into"] else ""
            print(f"  decided: {p['status']}{extra} by {p['decided_by']}" + (f" ({p['decision_note']})" if p["decision_note"] else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="show proposals with their evidence")
    ls.add_argument("--status", default="pending", choices=review.STATUSES + ("all",))
    ls.add_argument("--run", type=int)
    d = sub.add_parser("decide", help="accept, merge or reject one proposal")
    d.add_argument("proposal_id", type=int)
    g = d.add_mutually_exclusive_group(required=True)
    g.add_argument("--accept", action="store_true")
    g.add_argument("--merge", metavar="CATEGORY")
    g.add_argument("--reject", action="store_true")
    d.add_argument("--by", required=True, help="who decided: a lowercase first name, or 'both'")
    d.add_argument("--note", help="why (shown to the consolidator)")
    d.add_argument("--redo", action="store_true", help="change an earlier decision")
    a = ap.parse_args(argv)
    con = connect()
    try:
        if a.cmd == "list":
            show(review.proposals(con, None if a.status == "all" else a.status, a.run, 0, 10_000))
        else:
            status = "accepted" if a.accept else "merged" if a.merge else "rejected"
            r = decide(con, a.proposal_id, status, a.by, a.merge, a.note, a.redo)
            print(f"proposal {r['proposal_id']} ({r['name']}): {r['status']}"
                  + (f" into {r['merged_into']}" if r["merged_into"] else ""))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (DecisionError, review.ReviewError) as e:
        sys.exit(f"error: {e}")
