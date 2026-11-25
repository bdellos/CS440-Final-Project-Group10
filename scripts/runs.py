"""Start and finish runs (issue #58). A run is one rater applying one codebook to one sample;
every label belongs to a run, and the run holds the provenance (model, effort, codebook).

Agents start runs through the MCP tool start_run (agent raters only; model and effort always
come from config/models.json). Human runs are started here, from the command line, by the
human: an agent must never be able to create labels recorded as a person's.

    .venv/Scripts/python scripts/runs.py start --sample round0 --taxonomy purpose --rater brendan --purpose round0
    .venv/Scripts/python scripts/runs.py finish 12 [--allow-incomplete]
    .venv/Scripts/python scripts/runs.py note 6 "Category list was AI-assisted ..." --by brendan
"""
import argparse
import re
import sys

import models
import permissions
from db import connect

PURPOSES = ("round0", "round", "final", "heldout", "ablation", "smoke")
TAXONOMY_ITEM = {"purpose": "skill", "context": "repo"}


class RunError(ValueError):
    """A problem the caller should fix."""


def start_run(con, sample: str, taxonomy: str, rater: str, purpose: str, codebook_version: int | None = None,
              codebook_variant: str = "main", notes: str | None = None, human: bool = False) -> dict:
    if taxonomy not in TAXONOMY_ITEM:
        raise RunError(f"taxonomy must be one of {tuple(TAXONOMY_ITEM)}, got {taxonomy!r}")
    if purpose not in PURPOSES:
        raise RunError(f"purpose must be one of {PURPOSES}, got {purpose!r}")
    if (codebook_version is None) != (purpose == "round0"):
        raise RunError("Round 0 is open coding: purpose 'round0' needs codebook_version = null, "
                       "and every other purpose needs a registered codebook_version")

    if human:
        if not re.fullmatch(r"[a-z]+", rater or "") or rater in models.load_config()["agents"]:
            raise RunError(f"a human rater is a lowercase first name like 'brendan', got {rater!r}")
        model = effort = None
    else:
        try:
            settings = models.run_settings(rater)
        except KeyError:
            agents = sorted(models.load_config()["agents"])
            raise RunError(f"rater must be one of the agents in config/models.json {agents}, got {rater!r}. "
                           "Human runs are started by a person with scripts/runs.py.") from None
        problems, _ = models.check()
        if problems:
            raise RunError("model config check failed; fix it before starting a run:\n  " + "\n  ".join(problems))
        problems, _ = permissions.check()  # an agent file without `tools:` would inherit every tool (#17)
        if problems:
            raise RunError("permissions check failed; fix it before starting a run:\n  " + "\n  ".join(problems))
        model, effort = settings["model"], settings["effort"]

    s = con.execute("SELECT sample_id, item_kind FROM samples WHERE name = ?", (sample,)).fetchone()
    if s is None:
        raise RunError(f"no sample named {sample!r}; draw one with draw_sample first")
    if s["item_kind"] != TAXONOMY_ITEM[taxonomy]:
        raise RunError(f"{taxonomy} labels {TAXONOMY_ITEM[taxonomy]}s, but sample {sample!r} holds {s['item_kind']}s")

    cb_id = None
    if codebook_version is not None:
        cb = con.execute("SELECT codebook_version_id FROM codebook_versions WHERE taxonomy = ? AND variant = ? "
                         "AND version = ?", (taxonomy, codebook_variant, codebook_version)).fetchone()
        if cb is None:
            raise RunError(f"{taxonomy} codebook v{codebook_version:02d} ({codebook_variant}) is not registered; "
                           "run scripts/codebook.py register first")
        cb_id = cb[0]

    open_run = con.execute(
        "SELECT run_id FROM runs WHERE sample_id = ? AND taxonomy = ? AND rater = ? AND finished_at IS NULL "
        "AND codebook_version_id IS ?", (s["sample_id"], taxonomy, rater, cb_id)).fetchone()
    if open_run:
        raise RunError(f"{rater} already has open run {open_run[0]} on sample {sample!r} with this codebook; "
                       "continue that run, or finish it first")

    with con:
        run_id = con.execute(
            """INSERT INTO runs (sample_id, taxonomy, codebook_version_id, rater_kind, rater, model, effort,
                                 purpose, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (s["sample_id"], taxonomy, cb_id, "human" if human else "agent", rater, model, effort, purpose,
             notes)).lastrowid
    return {"run_id": run_id, "sample": sample, "taxonomy": taxonomy, "rater": rater,
            "rater_kind": "human" if human else "agent", "model": model, "effort": effort,
            "codebook_version": codebook_version, "codebook_variant": codebook_variant if cb_id else None,
            "purpose": purpose, "items": _progress(con, run_id)["items"]}


def _progress(con, run_id: int) -> dict:
    total = con.execute("SELECT COUNT(*) FROM sample_items i JOIN runs r USING (sample_id) WHERE r.run_id = ?",
                        (run_id,)).fetchone()[0]
    labeled = con.execute("SELECT COUNT(*) FROM annotations WHERE run_id = ?", (run_id,)).fetchone()[0]
    missing = [r[0] for r in con.execute(
        """SELECT i.item_id FROM sample_items i JOIN runs r USING (sample_id)
           WHERE r.run_id = ? AND i.item_id NOT IN (SELECT item_id FROM annotations WHERE run_id = ?)
           ORDER BY i.position LIMIT 50""", (run_id, run_id))]
    return {"items": total, "labeled": labeled, "unlabeled": total - labeled, "unlabeled_first_50": missing}


def finish_run(con, run_id: int, allow_incomplete: bool = False) -> dict:
    run = con.execute("SELECT run_id, finished_at FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        raise RunError(f"run {run_id} does not exist")
    if run["finished_at"] is not None:
        raise RunError(f"run {run_id} already finished at {run['finished_at']}")
    progress = _progress(con, run_id)
    if progress["unlabeled"] and not allow_incomplete:
        raise RunError(f"run {run_id} still has {progress['unlabeled']} unlabeled item(s), e.g. "
                       f"{progress['unlabeled_first_50'][:5]}; label them, or pass allow_incomplete to finish anyway")
    with con:
        con.execute("UPDATE runs SET finished_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE run_id = ?", (run_id,))
    return {"run_id": run_id, "finished": True, **progress, "agreement": batch_agreement(con, run_id)}


def batch_agreement(con, run_id: int) -> list:
    """Agreement of a run with every other finished run on the same sample, taxonomy and codebook
    version (#36), e.g. labeler vs skeptic, or agent vs human on the held-out set. Round 0 runs
    (no codebook) can't be compared category by category, so they get []."""
    import disagreements
    others = con.execute(
        """SELECT o.run_id, o.rater, o.rater_kind FROM runs r JOIN runs o
             ON o.sample_id = r.sample_id AND o.taxonomy = r.taxonomy
            AND o.codebook_version_id = r.codebook_version_id AND o.run_id <> r.run_id
            AND o.finished_at IS NOT NULL
           WHERE r.run_id = ? ORDER BY o.run_id""", (run_id,)).fetchall()
    out = []
    for o in others:
        s = disagreements.compare(con, run_id, o["run_id"], limit=1)["summary"]
        out.append({"other_run": o["run_id"], "other_rater": o["rater"], "other_rater_kind": o["rater_kind"],
                    **s})
    return out


def add_note(con, run_id: int, text: str, by: str) -> str:
    """Append a dated researcher note to a run's notes (the original notes are kept). For facts
    learned after a run, e.g. how a human coder built their categories."""
    if not re.fullmatch(r"[a-z]+", by or ""):
        raise RunError("--by must be your lowercase first name")
    text = " ".join((text or "").split())
    if not text:
        raise RunError("the note is empty")
    row = con.execute("SELECT notes FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise RunError(f"run {run_id} does not exist")
    from datetime import date
    entry = f"[note {date.today().isoformat()} by {by}] {text}"
    with con:
        con.execute("UPDATE runs SET notes = ? WHERE run_id = ?",
                    ((row[0] + "\n" if row[0] else "") + entry, run_id))
    return entry


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start", help="start a HUMAN run (agents use the start_run MCP tool)")
    s.add_argument("--sample", required=True)
    s.add_argument("--taxonomy", required=True, choices=tuple(TAXONOMY_ITEM))
    s.add_argument("--rater", required=True, help="your first name, lowercase")
    s.add_argument("--purpose", required=True, choices=PURPOSES)
    s.add_argument("--codebook-version", type=int)
    s.add_argument("--codebook-variant", default="main")
    s.add_argument("--notes")
    f = sub.add_parser("finish", help="finish a run")
    f.add_argument("run_id", type=int)
    f.add_argument("--allow-incomplete", action="store_true")
    n = sub.add_parser("note", help="append a researcher note to a run (humans only)")
    n.add_argument("run_id", type=int)
    n.add_argument("text")
    n.add_argument("--by", required=True, help="your first name, lowercase")
    a = p.parse_args()
    con = connect()
    try:
        if a.cmd == "start":
            r = start_run(con, a.sample, a.taxonomy, a.rater, a.purpose, a.codebook_version, a.codebook_variant,
                          a.notes, human=True)
            print(f"started human run {r['run_id']}: {r['rater']} on {r['sample']} ({r['items']} items)")
        elif a.cmd == "note":
            print(f"run {a.run_id}: {add_note(con, a.run_id, a.text, a.by)}")
        else:
            r = finish_run(con, a.run_id, a.allow_incomplete)
            print(f"finished run {r['run_id']}: {r['labeled']}/{r['items']} labeled")
            for g in r["agreement"]:
                print(f"  vs run {g['other_run']} ({g['other_rater']}): exact agreement {g['exact_agreement']} "
                      f"over {g['items_compared']} items ({g['agree']} agree, {g['partial']} partial, "
                      f"{g['disjoint']} disjoint, {g['missing']} missing)")
    except RunError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
