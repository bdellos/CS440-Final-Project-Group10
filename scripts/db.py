"""Open the project database with the GitSkills dataset attached read-only.

    from db import connect
    con = connect()
    con.execute("SELECT name FROM gs.artifacts WHERE file_sha = ?", (sha,))

Paths (override with environment variables):
    GITSKILLS_DB  dataset file, attached read-only as schema `gs`
                  default: the sample under data/gitskills-sample/
    LABELS_DB     project database (our tables)
                  default: labels/labels.db

Run directly to create or upgrade the schema:
    .venv/Scripts/python scripts/db.py
"""
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = ROOT / "data/gitskills-sample/agent_skills_sample/agent_skills_sample.db"
DEFAULT_LABELS = ROOT / "labels/labels.db"
SCHEMA = ROOT / "scripts/schema.sql"


def dataset_path() -> Path:
    return Path(os.environ.get("GITSKILLS_DB", DEFAULT_DATASET))


def labels_path() -> Path:
    return Path(os.environ.get("LABELS_DB", DEFAULT_LABELS))


def connect(labels_db: Path | None = None, dataset_db: Path | None = None) -> sqlite3.Connection:
    labels_db = Path(labels_db or labels_path())
    dataset_db = Path(dataset_db or dataset_path())
    if not dataset_db.exists():
        raise FileNotFoundError(f"GitSkills dataset not found: {dataset_db} (unzip it or set GITSKILLS_DB)")
    labels_db.parent.mkdir(parents=True, exist_ok=True)

    # uri=True is required for the read-only `?mode=ro` ATTACH below.
    con = sqlite3.connect(labels_db.resolve().as_uri(), uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")  # hooks and MCP tools may open it at the same time
    con.execute("ATTACH DATABASE ? AS gs", (f"{dataset_db.resolve().as_uri()}?mode=ro",))
    return con


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA.read_text(encoding="utf-8"))


if __name__ == "__main__":
    con = connect()
    init_schema(con)
    tables = [r[0] for r in con.execute("SELECT name FROM main.sqlite_master WHERE type IN ('table','view') ORDER BY 1")]
    n = con.execute("SELECT COUNT(*) FROM gs.artifacts WHERE dedup_primary = 1").fetchone()[0]
    print(f"{labels_path().relative_to(ROOT)}: {', '.join(tables)}")
    print(f"attached {dataset_path().name} read-only: {n:,} distinct skills")
