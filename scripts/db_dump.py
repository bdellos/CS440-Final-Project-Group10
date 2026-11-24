"""Dump labels.db to text for git, or rebuild labels.db from that dump.

labels.db is gitignored (binary, changes on every write). Commit labels/dump.sql
at the end of each round, together with the codebook commit.

    .venv/Scripts/python scripts/db_dump.py             # labels.db -> labels/dump.sql
    .venv/Scripts/python scripts/db_dump.py --restore   # labels/dump.sql -> labels.db (refuses to overwrite)

Only our tables are dumped; the attached GitSkills dataset is never included.
Derived tables (DERIVED below) keep their schema but not their rows: rebuild them
after a restore with scripts/load_dataset.py.
"""
import argparse
import sqlite3
import sys

from db import ROOT, labels_path

DUMP = ROOT / "labels/dump.sql"

# Rebuilt from the dataset by load_dataset.py; ~1.9M rows on the full dataset, so not in git.
DERIVED = ("skills",)


def dump() -> None:
    src = labels_path()
    if not src.exists():
        sys.exit(f"no database at {src}")
    disk = sqlite3.connect(src)  # plain connection: nothing attached, so only our tables are dumped
    disk.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    mem = sqlite3.connect(":memory:")  # work on a copy so labels.db is never modified
    disk.backup(mem)
    disk.close()
    for table in DERIVED:
        mem.execute(f'DELETE FROM "{table}"')
    with open(DUMP, "w", encoding="utf-8", newline="\n") as fh:
        for line in mem.iterdump():
            fh.write(line + "\n")
    mem.close()
    print(f"wrote {DUMP.relative_to(ROOT)}")


def restore() -> None:
    dst = labels_path()
    if dst.exists():
        sys.exit(f"{dst} already exists; move it aside first so nothing is overwritten")
    if not DUMP.exists():
        sys.exit(f"no dump at {DUMP}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(dst)
    con.executescript(DUMP.read_text(encoding="utf-8"))
    con.close()
    print(f"restored {dst} from {DUMP.relative_to(ROOT)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--restore", action="store_true", help="rebuild labels.db from labels/dump.sql")
    restore() if p.parse_args().restore else dump()
