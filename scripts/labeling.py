"""Store a label record (issue #14): validate it, then write it in one transaction.

Used by the MCP tool record_label (agent runs only) and, later, by imports of human coding
(which call store_label with allow_human=True from a script a person runs).

What gets written for one record:
  annotations        one row: run, item, language, notes
  annotation_labels  one row per category, plus 'PROPOSED_NEW' if the record proposes categories
  evidence           one row per quote; category_key is the label's category, or
                     'PROPOSED_NEW:<proposal_id>' for a proposal's evidence
  proposals          one row per proposed category, status 'pending' until the humans decide
"""
import sqlite3

from validate_label import validate_label


class LabelRejected(ValueError):
    """The record failed validation; .errors holds every problem."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__(f"label rejected ({len(self.errors)} problem{'s' if len(self.errors) != 1 else ''}):\n"
                         + "\n".join(f"- {e}" for e in self.errors))


def _write(con, record) -> dict:
    annotation_id = con.execute(
        "INSERT INTO annotations (run_id, item_id, skill_language, notes) VALUES (?, ?, ?, ?)",
        (record["run_id"], record["item_id"], record.get("skill_language"), record.get("notes"))).lastrowid
    for lab in record["labels"]:
        con.execute("INSERT INTO annotation_labels (annotation_id, category_key) VALUES (?, ?)",
                    (annotation_id, lab["category"]))
        con.executemany("INSERT INTO evidence (annotation_id, category_key, quote, quote_en) VALUES (?, ?, ?, ?)",
                        [(annotation_id, lab["category"], ev["quote"], ev["quote_en"]) for ev in lab["evidence"]])
    proposal_ids = []
    if record["proposals"]:
        con.execute("INSERT INTO annotation_labels (annotation_id, category_key) VALUES (?, 'PROPOSED_NEW')",
                    (annotation_id,))
        for p in record["proposals"]:
            pid = con.execute(
                "INSERT INTO proposals (annotation_id, proposed_name, definition, justification) VALUES (?, ?, ?, ?)",
                (annotation_id, p["name"], p["definition"], p["justification"])).lastrowid
            con.executemany("INSERT INTO evidence (annotation_id, category_key, quote, quote_en) VALUES (?, ?, ?, ?)",
                            [(annotation_id, f"PROPOSED_NEW:{pid}", ev["quote"], ev["quote_en"])
                             for ev in p["evidence"]])
            proposal_ids.append(pid)
    return {"annotation_id": annotation_id, "proposal_ids": proposal_ids}


def store_label(con: sqlite3.Connection, record: dict, allow_human: bool = False) -> dict:
    """Validate and store one record atomically. Raises LabelRejected with every problem."""
    con.commit()
    con.execute("BEGIN IMMEDIATE")  # lock first, so validation and write can't interleave with another writer
    try:
        errors = validate_label(record, con)
        if not errors:
            kind = con.execute("SELECT rater_kind FROM runs WHERE run_id = ?", (record["run_id"],)).fetchone()
            if kind and kind[0] == "human" and not allow_human:
                errors = [f"run {record['run_id']} is a human run; agents can't write labels into it"]
        if errors:
            raise LabelRejected(errors)
        written = _write(con, record)
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    progress = con.execute(
        """SELECT (SELECT COUNT(*) FROM sample_items i JOIN runs r USING (sample_id) WHERE r.run_id = ?),
                  (SELECT COUNT(*) FROM annotations WHERE run_id = ?)""",
        (record["run_id"], record["run_id"])).fetchone()
    return {"stored": True, "run_id": record["run_id"], "item_id": record["item_id"], **written,
            "labels": [lab["category"] for lab in record["labels"]],
            "run_progress": {"items": progress[0], "labeled": progress[1], "remaining": progress[0] - progress[1]}}
