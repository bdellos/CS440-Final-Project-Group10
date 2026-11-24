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
import re
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


SCHEMA_VERSION = 3  # v3 (#35): prompt_versions table and prompt provenance triggers (additive)


def _columns(con, table):
    return {r[1] for r in con.execute(f"PRAGMA main.table_info({table})")}


def _table_sql(con, table):
    row = con.execute("SELECT sql FROM main.sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return row[0] if row else ""


def _schema_ddl(table):
    """The CREATE TABLE statement for `table` as written in schema.sql."""
    text = SCHEMA.read_text(encoding="utf-8")
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \(.*?\n\) STRICT;", text, re.S)
    if not m:
        raise LookupError(f"no CREATE TABLE for {table} in schema.sql")
    return m.group(0)


def _norm_ddl(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)              # comments don't change the table
    sql = sql.replace("IF NOT EXISTS ", "").replace('"', "")  # a renamed table's name is stored quoted
    return " ".join(sql.rstrip().rstrip(";").split())


def out_of_date(con, table) -> bool:
    """True if the stored definition of `table` differs from schema.sql in anything but
    whitespace, comments and quoting."""
    return _norm_ddl(_table_sql(con, table)) != _norm_ddl(_schema_ddl(table))


def rebuild_table(con: sqlite3.Connection, table: str, fill: dict | None = None) -> None:
    """Recreate `table` with its current schema.sql definition, keeping its rows.

    SQLite's ALTER TABLE can't change constraints, so this is the documented rebuild:
    new table, copy shared columns, drop old, rename. Views and triggers are dropped
    first and recreated by schema.sql afterwards. `fill` gives SQL expressions (over the
    old row) for new columns that existing rows need a value in.
    """
    fill = fill or {}
    old = _columns(con, table)
    keep = [c for c in old if c in _columns_of_ddl(table) and c not in fill]
    con.commit()
    con.execute("PRAGMA foreign_keys = OFF")
    try:
        con.execute("BEGIN")
        for kind, name in con.execute(
                "SELECT type, name FROM main.sqlite_master WHERE type IN ('view', 'trigger')").fetchall():
            con.execute(f'DROP {kind.upper()} IF EXISTS main."{name}"')
        new = f"{table}__new"
        con.execute(_schema_ddl(table).replace(f"IF NOT EXISTS {table} (", f"{new} (", 1))
        cols = ", ".join(keep + list(fill))
        exprs = ", ".join(keep + list(fill.values()))
        con.execute(f"INSERT INTO {new} ({cols}) SELECT {exprs} FROM main.{table}")
        con.execute(f"DROP TABLE main.{table}")
        con.execute(f"ALTER TABLE {new} RENAME TO {table}")
        bad = con.execute("PRAGMA main.foreign_key_check").fetchall()
        if bad:
            raise sqlite3.IntegrityError(f"foreign key problems after rebuilding {table}: {bad[:3]}")
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))  # recreate views and triggers


def _columns_of_ddl(table):
    tmp = sqlite3.connect(":memory:")
    tmp.execute(_schema_ddl(table))
    cols = _columns(tmp, table)
    tmp.close()
    return cols


def _migrate(con: sqlite3.Connection) -> None:
    """Bring a database created by an older schema.sql up to date.

    schema.sql uses CREATE ... IF NOT EXISTS, which creates missing tables but never
    changes existing ones, so table changes go here. Each step is safe to re-run.
    """
    # v2 (#18): runs gains `effort`, and agent runs must record both model and effort.
    # Agent runs from before then get effort 'unrecorded' rather than an invented value.
    if out_of_date(con, "runs"):
        effort = "effort" if "effort" in _columns(con, "runs") else "NULL"
        rebuild_table(con, "runs", fill={
            "effort": f"CASE WHEN {effort} IS NULL AND rater_kind = 'agent' THEN 'unrecorded' ELSE {effort} END"})
    con.execute(f"PRAGMA main.user_version = {SCHEMA_VERSION}")


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    _migrate(con)
    con.commit()


if __name__ == "__main__":
    con = connect()
    init_schema(con)
    tables = [r[0] for r in con.execute("SELECT name FROM main.sqlite_master WHERE type IN ('table','view') ORDER BY 1")]
    n = con.execute("SELECT COUNT(*) FROM gs.artifacts WHERE dedup_primary = 1").fetchone()[0]
    print(f"{labels_path().relative_to(ROOT)}: {', '.join(tables)}")
    print(f"attached {dataset_path().name} read-only: {n:,} distinct skills")
