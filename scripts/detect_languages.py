"""Detect the language of every distinct skill and store it in skill_language (issue #52).

Incremental and resumable: only skills with no result, or a result from a different
detector version, are processed, and results are committed in batches. Uses all CPU
cores (the full dataset is ~1.9M skills: hours on one core).

    .venv/Scripts/python scripts/detect_languages.py            # also run by load_dataset.py
    .venv/Scripts/python scripts/detect_languages.py --workers 4

The detector version is the hash of scripts/language.py plus the langdetect version,
so editing language.py makes every skill eligible for re-detection.
"""
import argparse
import hashlib
import os
import time
from importlib.metadata import version
from multiprocessing import Pool

from db import ROOT, connect

BATCH = 2000


def detector_id() -> str:
    src = (ROOT / "scripts/language.py").read_bytes().replace(b"\r\n", b"\n")
    return f"language.py@{hashlib.sha256(src).hexdigest()[:10]} langdetect=={version('langdetect')}"


def _detect(item):
    from language import detect  # imported in the worker process
    sha, content = item
    lang, conf = detect(content)
    return sha, lang, float(conf)


def pending(con, detector):
    return [r[0] for r in con.execute(
        """SELECT s.file_sha FROM skills s
           LEFT JOIN skill_language l USING (file_sha)
           WHERE l.file_sha IS NULL OR l.detector <> ?
           ORDER BY s.file_sha""",
        (detector,),
    )]


def run(con, workers=None, quiet=False):
    detector = detector_id()
    todo = pending(con, detector)
    if not todo:
        if not quiet:
            print(f"  language: all skills up to date ({detector})")
        return 0
    workers = workers or os.cpu_count() or 1
    print(f"  language: detecting {len(todo):,} skills on {workers} workers ({detector})")
    t0, done = time.perf_counter(), 0
    with Pool(workers) as pool:
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            marks = ",".join("?" * len(chunk))
            items = con.execute(
                f"SELECT file_sha, content FROM gs.artifacts WHERE dedup_primary = 1 AND file_sha IN ({marks})",
                chunk,
            ).fetchall()
            results = pool.map(_detect, [(r[0], r[1]) for r in items], chunksize=50)
            with con:
                con.executemany(
                    """INSERT INTO skill_language (file_sha, language, confidence, detector)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT (file_sha) DO UPDATE SET language = excluded.language,
                           confidence = excluded.confidence, detector = excluded.detector,
                           detected_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')""",
                    [(sha, lang, conf, detector) for sha, lang, conf in results],
                )
            done += len(chunk)
            rate = done / (time.perf_counter() - t0)
            print(f"    {done:,}/{len(todo):,}  ({rate:,.0f}/s, ~{(len(todo) - done) / rate / 60:.0f} min left)")
    return done


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workers", type=int, default=None, help="processes (default: all cores)")
    run(connect(), p.parse_args().workers)
