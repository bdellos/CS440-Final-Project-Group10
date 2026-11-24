"""Draw a stratified, de-duplicated sample of skills and store it as a frozen named sample (#12).

Used by the MCP tool draw_sample. The procedure, so it can be written up:
  1. Pool: distinct skills (one row per content) from the `skills_with_language` view, filtered by
     front-matter validity, body length and (by default) language = 'en'.
  2. Exclude skills already in any stored sample (Round 0, earlier rounds, held-out), and treat
     their names and repositories as taken, so samples share neither skills nor near-duplicates.
  3. Near-duplicates: keep at most one skill per name and one per repository; the lowest
     file_sha wins, so the result doesn't depend on chance.
  4. Strata: body-length quartiles of the remaining pool, or location class, or none.
     n is split across strata in proportion to their size (largest remainder).
  5. Random draw within each stratum with a fixed seed, then a shuffled presentation order.
"""
import random
import re

STRATIFY = ("length", "location", "none")
MAX_N = 20_000


class SampleError(ValueError):
    """A problem the caller should fix (bad arguments, name taken, pool too small)."""


def _allocate(sizes: dict, n: int) -> dict:
    """Split n across strata proportionally to their sizes (largest remainder method)."""
    total = sum(sizes.values())
    exact = {k: n * v / total for k, v in sizes.items()}
    alloc = {k: int(x) for k, x in exact.items()}
    # largest remainders first; ties go to the stratum that sorts first
    for k in sorted(exact, key=lambda k: (-(exact[k] - alloc[k]), k))[: n - sum(alloc.values())]:
        alloc[k] += 1
    return alloc


def method_text(p: dict) -> str:
    parts = ["distinct skills"]
    if p["english_only"]:
        parts.append("English only (language = 'en')")
    if p["valid_frontmatter_only"]:
        parts.append("valid front matter")
    parts.append(f"{p['min_chars']:,}-{p['max_chars']:,} body characters")
    if p["exclude_sampled"]:
        parts.append("excluding skills, skill names and repositories used in earlier samples")
    if p["one_per_name"]:
        parts.append("at most one per skill name")
    if p["one_per_repo"]:
        parts.append("at most one per repository")
    strat = {"length": "stratified by body-length quartile", "location": "stratified by location class",
             "none": "unstratified"}[p["stratify_by"]]
    return f"{', '.join(parts)}; {strat}, proportional allocation, seed {p['seed']}. scripts/sampling.py"


def draw(con, name: str, n: int, seed: int, stratify_by: str = "length", english_only: bool = True,
         valid_frontmatter_only: bool = True, min_chars: int = 200, max_chars: int = 20_000,
         exclude_sampled: bool = True, one_per_name: bool = True, one_per_repo: bool = True,
         dry_run: bool = False) -> dict:
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name or ""):
        raise SampleError(f"name must be a lowercase slug like 'round1' or 'heldout', got {name!r}")
    if not 1 <= n <= MAX_N:
        raise SampleError(f"n must be between 1 and {MAX_N:,}, got {n}")
    if stratify_by not in STRATIFY:
        raise SampleError(f"stratify_by must be one of {STRATIFY}, got {stratify_by!r}")
    if not 0 <= min_chars <= max_chars:
        raise SampleError("need 0 <= min_chars <= max_chars")
    if con.execute("SELECT 1 FROM samples WHERE name = ?", (name,)).fetchone():
        raise SampleError(f"a sample named {name!r} already exists; samples are frozen, pick a new name")
    if english_only and con.execute("SELECT 1 FROM skills_with_language WHERE language IS NULL LIMIT 1").fetchone():
        raise SampleError("some skills have no detected language yet; run scripts/detect_languages.py")

    params = dict(stratify_by=stratify_by, english_only=english_only, valid_frontmatter_only=valid_frontmatter_only,
                  min_chars=min_chars, max_chars=max_chars, exclude_sampled=exclude_sampled,
                  one_per_name=one_per_name, one_per_repo=one_per_repo, seed=seed)
    where = ["body_chars BETWEEN ? AND ?"]
    args = [min_chars, max_chars]
    if valid_frontmatter_only:
        where.append("frontmatter_valid = 1")
    if english_only:
        where.append("language = 'en'")
    if exclude_sampled:
        where.append("file_sha NOT IN (SELECT item_id FROM sample_items)")
    pool = con.execute(
        f"SELECT file_sha, name_key, repo_full_name, body_chars, location_class, name "
        f"FROM skills_with_language WHERE {' AND '.join(where)} ORDER BY file_sha", args).fetchall()

    names, repos, kept = set(), set(), []
    if exclude_sampled:
        # Names and repos already used by earlier samples count as taken, so a near-duplicate
        # (same name or same repo, different text) of an earlier sample's skill can't slip in.
        for nk, rp in con.execute("SELECT k.name_key, k.repo_full_name FROM sample_items i "
                                  "JOIN skills k ON k.file_sha = i.item_id"):
            names.add(nk)
            repos.add(rp)
    for r in pool:  # ordered by file_sha: the lowest hash per name / repo wins
        if one_per_name and r["name_key"] in names:
            continue
        if one_per_repo and r["repo_full_name"] in repos:
            continue
        names.add(r["name_key"])
        repos.add(r["repo_full_name"])
        kept.append(r)
    if len(kept) < n:
        raise SampleError(f"only {len(kept):,} skills meet the criteria, fewer than n = {n:,}")

    strata = {}
    if stratify_by == "length":
        by_len = sorted(kept, key=lambda r: (r["body_chars"], r["file_sha"]))
        for i in range(4):
            strata[f"length_q{i + 1}"] = by_len[i * len(by_len) // 4:(i + 1) * len(by_len) // 4]
    elif stratify_by == "location":
        for r in kept:
            strata.setdefault(f"location_{r['location_class']}", []).append(r)
    else:
        strata["all"] = kept

    rng = random.Random(seed)
    alloc = _allocate({k: len(v) for k, v in strata.items()}, n)
    picked = []
    for key in sorted(strata):
        picked += [(key, r) for r in rng.sample(strata[key], alloc[key])]
    rng.shuffle(picked)

    items = [{"position": i, "file_sha": r["file_sha"], "name": r["name"], "stratum": key,
              "repo_full_name": r["repo_full_name"], "body_chars": r["body_chars"]}
             for i, (key, r) in enumerate(picked, start=1)]
    result = {
        "name": name, "n": n, "seed": seed, "method": method_text(params), "params": params,
        "pool_before_dedup": len(pool), "pool": len(kept),
        "strata": {k: {"pool": len(v), "drawn": alloc[k]} for k, v in sorted(strata.items())},
        "items": items, "stored": False,
    }
    if dry_run:
        return result
    with con:
        sid = con.execute("INSERT INTO samples (name, item_kind, method, seed) VALUES (?, 'skill', ?, ?)",
                          (name, result["method"], seed)).lastrowid
        con.executemany("INSERT INTO sample_items (sample_id, item_id, position, stratum) VALUES (?, ?, ?, ?)",
                        [(sid, it["file_sha"], it["position"], it["stratum"]) for it in items])
    result["stored"] = True
    return result


def get(con, name: str, offset: int = 0, limit: int = 500) -> dict:
    s = con.execute("SELECT sample_id, name, item_kind, method, seed, created_at FROM samples WHERE name = ?",
                    (name,)).fetchone()
    if s is None:
        known = [r[0] for r in con.execute("SELECT name FROM samples ORDER BY sample_id")]
        raise SampleError(f"no sample named {name!r}; existing samples: {known}")
    total = con.execute("SELECT COUNT(*) FROM sample_items WHERE sample_id = ?", (s["sample_id"],)).fetchone()[0]
    rows = con.execute(
        """SELECT i.position, i.item_id, i.stratum, k.name FROM sample_items i
           LEFT JOIN skills k ON k.file_sha = i.item_id
           WHERE i.sample_id = ? ORDER BY i.position LIMIT ? OFFSET ?""",
        (s["sample_id"], limit, offset)).fetchall()
    return {"name": s["name"], "item_kind": s["item_kind"], "method": s["method"], "seed": s["seed"],
            "created_at": s["created_at"], "total_items": total, "offset": offset,
            "items": [{"position": r["position"], "id": r["item_id"], "stratum": r["stratum"], "name": r["name"]}
                      for r in rows]}
