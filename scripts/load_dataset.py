"""Load the GitSkills dataset into labels.db (issue #8).

The dataset itself stays read-only and attached (see db.py). Loading means:
  1. create or upgrade the schema;
  2. rebuild the `skills` sampling frame with one scan of gs.artifacts;
  3. record the dataset file and counts in `dataset_loads`;
  4. register the Round 0 sample from samples/round0.csv.

    .venv/Scripts/python scripts/load_dataset.py
    GITSKILLS_DB=path/to/full.db .venv/Scripts/python scripts/load_dataset.py   # full dataset

Safe to rerun: `skills` is rebuilt, and an already registered sample is checked, not changed.
"""
import csv
import datetime as dt
import sys
import time

from db import ROOT, connect, dataset_path, init_schema

ROUND0_CSV = ROOT / "samples/round0.csv"
ROUND0_METHOD = (
    "Distinct English-language skills with valid front matter, 200-20,000 body characters, "
    "at most one per skill name and one per repository, stratified by body-length quartile "
    "(13/13/12/12). scripts/draw_round0_sample.py"
)


def build_skills(con):
    con.execute("DELETE FROM skills")
    con.execute(
        """
        INSERT INTO skills (file_sha, repo_full_name, path, name, name_key, frontmatter_valid,
                            body_chars, location_class, has_scripts, has_references, copies, n_repos)
        SELECT p.file_sha, p.repo_full_name, p.path, p.name, lower(trim(p.name)), p.frontmatter_valid,
               p.body_chars, p.location_class, p.has_scripts, p.has_references, c.copies, c.n_repos
        FROM gs.artifacts p
        JOIN (SELECT file_sha, COUNT(*) AS copies, COUNT(DISTINCT repo_full_name) AS n_repos
              FROM gs.artifacts GROUP BY file_sha) c USING (file_sha)
        WHERE p.dedup_primary = 1
        """
    )
    return con.execute("SELECT COUNT(*) FROM skills").fetchone()[0]


def record_load(con, distinct_skills):
    path = dataset_path().resolve()
    stat = path.stat()
    artifacts = con.execute("SELECT COUNT(*) FROM gs.artifacts").fetchone()[0]
    repos = con.execute("SELECT COUNT(*) FROM gs.repos").fetchone()[0]
    mtime = dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    con.execute(
        "INSERT INTO dataset_loads (dataset_path, dataset_bytes, dataset_mtime, artifacts, distinct_skills, repos) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),
         stat.st_size, mtime, artifacts, distinct_skills, repos),
    )
    return artifacts, repos


def register_round0(con):
    with open(ROUND0_CSV, encoding="utf-8") as fh:
        rows = [(int(r["id"][1:]), r["file_sha"], f"length_q{r['length_quartile']}") for r in csv.DictReader(fh)]

    missing = [sha for _, sha, _ in rows
               if not con.execute("SELECT 1 FROM skills WHERE file_sha = ?", (sha,)).fetchone()]
    if missing:
        # Expected on a dataset that doesn't contain the sample's skills; not fatal.
        print(f"  round0: {len(missing)} of {len(rows)} skills are not in this dataset; not registered")
        return

    existing = con.execute("SELECT sample_id FROM samples WHERE name = 'round0'").fetchone()
    if existing:
        stored = {(p, sha) for p, sha in con.execute(
            "SELECT position, item_id FROM sample_items WHERE sample_id = ?", (existing[0],))}
        if stored != {(p, sha) for p, sha, _ in rows}:
            sys.exit("round0 in the database differs from samples/round0.csv; refusing to change a frozen sample")
        print("  round0: already registered, matches samples/round0.csv")
        return

    sid = con.execute(
        "INSERT INTO samples (name, item_kind, method, seed) VALUES ('round0', 'skill', ?, 440)",
        (ROUND0_METHOD,),
    ).lastrowid
    con.executemany(
        "INSERT INTO sample_items (sample_id, item_id, position, stratum) VALUES (?, ?, ?, ?)",
        [(sid, sha, pos, stratum) for pos, sha, stratum in rows],
    )
    print(f"  round0: registered {len(rows)} skills")


def main():
    t0 = time.perf_counter()
    con = connect()
    init_schema(con)
    print(f"dataset: {dataset_path()}")
    with con:  # one transaction: a failed load leaves the previous state intact
        n = build_skills(con)
        artifacts, repos = record_load(con, n)
        print(f"  skills: {n:,} distinct ({artifacts:,} file occurrences, {repos:,} repos)")
        register_round0(con)
    print(f"done in {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
