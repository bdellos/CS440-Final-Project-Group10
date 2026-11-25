"""Tests for scripts/codebook.py, run inside a throwaway git repository.
    .venv/Scripts/python -m pytest tests
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import codebook  # noqa: E402
from db import connect, init_schema  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"


def category(key="alpha-thing", name="Alpha thing", example=f"- {SHA}: \"quote\""):
    return (f"## {key}: {name}\n\n### Definition\nDefines {key}.\n\n### Include\n- yes\n\n"
            f"### Exclude\n- no\n\n### Examples\n{example}\n")


def doc(version=1, based_on=0, rnd=1, taxonomy="purpose", variant="main", body=""):
    return (f"---\ntaxonomy: {taxonomy}\nvariant: {variant}\nversion: {version}\n"
            f"based_on: {based_on if based_on is not None else 'none'}\nround: {rnd}\n---\n\n"
            f"# {taxonomy.capitalize()} codebook v{version:02d}\n\n{body}")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "test")
    git("config", "commit.gpgsign", "false")
    monkeypatch.setattr(codebook, "ROOT", tmp_path)

    def write(rel, text):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        return p

    def commit(msg="c"):
        git("add", "-A")
        git("commit", "-q", "-m", msg)

    write("codebook/purpose/v00.md", doc(0, None, 0))
    commit("v00")
    return type("Repo", (), {"path": tmp_path, "write": staticmethod(write), "commit": staticmethod(commit)})


# --- parsing --------------------------------------------------------------

def test_real_templates_are_valid():
    for f in ("codebook/purpose/v00.md", "codebook/context/v00.md"):
        cb = codebook.parse(ROOT / f)
        assert cb.errors == [] and cb.categories == [] and cb.version == 0


def test_parse_category(repo):
    p = repo.write("codebook/purpose/v01.md", doc(body=category() + category("beta", "Beta")))
    cb = codebook.parse(p)
    assert cb.errors == []
    assert [(c.key, c.name) for c in cb.categories] == [("alpha-thing", "Alpha thing"), ("beta", "Beta")]
    assert cb.categories[0].definition == "Defines alpha-thing."


def test_comments_are_ignored(repo):
    p = repo.write("codebook/purpose/v01.md", doc(body="<!--\n## Not A Category\n-->\n" + category()))
    assert codebook.parse(p).errors == []


@pytest.mark.parametrize("body, expect", [
    ("## Bad Key: Name\n", "lowercase slug"),
    (category().replace("### Exclude\n- no\n", ""), "missing or empty '### Exclude'"),
    (category() + category(), "defined twice"),
    (category(example="- not-a-sha: \"q\""), "example must start with '- <file_sha>: '"),
    (category().replace("### Include", "### Includes"), "unknown section 'Includes'"),
    ("### Definition\norphan\n", "outside a category"),
])
def test_parse_errors(repo, body, expect):
    p = repo.write("codebook/purpose/v01.md", doc(body=body))
    errs = codebook.parse(p).errors
    assert any(expect in e for e in errs), errs


@pytest.mark.parametrize("path, text, expect", [
    ("codebook/purpose/v02.md", doc(version=1), "file name says v02"),
    ("codebook/context/v01.md", doc(), "file name says context"),
    ("codebook/purpose/v01.md", doc(based_on=None), "based_on is required"),
    ("codebook/purpose/v01.md", doc(based_on=1), "must be an earlier version"),
    ("codebook/purpose/v01.md", doc().replace("round: 1", "round: one"), "round must be a number"),
])
def test_header_errors(repo, path, text, expect):
    errs = codebook.parse(repo.write(path, text)).errors
    assert any(expect in e for e in errs), errs


def test_context_examples_use_repos(repo):
    p = repo.write("codebook/context/v00.md",
                   doc(0, None, 0, taxonomy="context", body=category(example="- owner/repo: \"README says so\"")))
    assert codebook.parse(p).errors == []


# --- check: numbering and immutability -------------------------------------

def test_check_clean(repo):
    assert codebook.check() == []


def test_check_gap(repo):
    repo.write("codebook/purpose/v02.md", doc(version=2, based_on=1, rnd=2, body=category()))
    assert any("without gaps" in p for p in codebook.check())


def test_edited_past_version_is_caught(repo):
    repo.write("codebook/purpose/v01.md", doc(body=category()))
    repo.commit("v01")
    repo.write("codebook/purpose/v01.md", doc(body=category(name="Renamed")))
    assert any("uncommitted edits" in p for p in codebook.check())
    repo.commit("edit v01")
    assert any("changed in 2 commits" in p for p in codebook.check())


def test_uncommitted_new_draft_is_fine(repo):
    repo.write("codebook/purpose/v01.md", doc(body=category()))
    assert codebook.check() == []


# --- next -------------------------------------------------------------------

def test_next_copies_latest(repo):
    repo.write("codebook/purpose/v01.md", doc(body=category()))
    repo.commit("v01")
    dst = codebook.next_version("purpose", rnd=2)
    cb = codebook.parse(dst)
    assert (cb.path, cb.version, cb.based_on, cb.round, cb.errors) == ("codebook/purpose/v02.md", 2, 1, 2, [])
    assert [c.key for c in cb.categories] == ["alpha-thing"]
    assert codebook.commit_message(cb) == "codebook: purpose v02 (round 2)"


def test_next_refuses_uncommitted_latest(repo):
    repo.write("codebook/purpose/v01.md", doc(body=category()))
    with pytest.raises(SystemExit, match="isn't committed"):
        codebook.next_version("purpose", rnd=2)


def test_next_starts_a_variant(repo):
    dst = codebook.next_version("purpose", rnd=1, variant="seeded", base=repo.path / "codebook/purpose/v00.md")
    cb = codebook.parse(dst)
    assert (cb.path, cb.variant, cb.version, cb.based_on, cb.errors) == \
        ("codebook/purpose/seeded/v00.md", "seeded", 0, None, [])
    assert codebook.commit_message(cb) == "codebook: purpose v00 [seeded] (round 1)"


# --- register ---------------------------------------------------------------

@pytest.fixture
def con(tmp_path):
    c = connect(labels_db=tmp_path / "labels.db")
    init_schema(c)
    return c


def test_register(repo, con):
    repo.write("codebook/purpose/v01.md", doc(body=category() + category("beta", "Beta")))
    repo.commit("v01")
    msg = codebook.register(repo.path / "codebook/purpose/v01.md", con)
    assert "2 categories" in msg
    rows = con.execute("SELECT category_key, definition FROM categories JOIN codebook_versions USING "
                       "(codebook_version_id) WHERE version = 1 ORDER BY 1").fetchall()
    assert [tuple(r) for r in rows] == [("alpha-thing", "Defines alpha-thing."), ("beta", "Defines beta.")]
    assert "already registered" in codebook.register(repo.path / "codebook/purpose/v01.md", con)


def test_register_requires_commit(repo, con):
    repo.write("codebook/purpose/v01.md", doc(body=category()))
    with pytest.raises(SystemExit, match="must be committed"):
        codebook.register(repo.path / "codebook/purpose/v01.md", con)


def test_register_refuses_invalid(repo, con):
    repo.write("codebook/purpose/v01.md", doc(body="## Bad Key: x\n"))
    repo.commit("bad")
    with pytest.raises(SystemExit, match="has errors"):
        codebook.register(repo.path / "codebook/purpose/v01.md", con)


# --- register takes in decided proposals (#42) -----------------------------------

def _proposals_against_v01(con, decisions):
    """A human run on v01 with one annotation per proposal; decisions: [(name, status, merged_into)]."""
    v1 = con.execute("SELECT codebook_version_id FROM codebook_versions WHERE version = 1").fetchone()[0]
    con.execute("INSERT INTO samples (name, item_kind, method) VALUES ('r1', 'skill', 'test')")
    run = con.execute("INSERT INTO runs (sample_id, taxonomy, codebook_version_id, rater_kind, rater, purpose) "
                      "VALUES (1, 'purpose', ?, 'human', 'brendan', 'round')", (v1,)).lastrowid
    ids = []
    for i, (name, status, merged) in enumerate(decisions):
        ann = con.execute("INSERT INTO annotations (run_id, item_id) VALUES (?, ?)", (run, f"item{i}")).lastrowid
        ids.append(con.execute(
            "INSERT INTO proposals (annotation_id, proposed_name, definition, justification, status, merged_into, "
            "decided_by) VALUES (?, ?, 'd', 'j', ?, ?, ?)",
            (ann, name, status, merged, None if status == "pending" else "both")).lastrowid)
    con.commit()
    return ids


def test_register_takes_in_decided_proposals(repo, con):
    repo.write("codebook/purpose/v01.md", doc(body=category() + category("beta", "Beta")))
    repo.commit("v01")
    codebook.register(repo.path / "codebook/purpose/v01.md", con)
    acc, mer, rej, pen = _proposals_against_v01(con, [("Gamma Thing", "accepted", None), ("Delta", "merged", "beta"),
                                                     ("Epsilon", "rejected", None), ("Zeta", "pending", None)])
    repo.write("codebook/purpose/v02.md", doc(2, 1, 2, body=category() + category("beta", "Beta")
                                              + category("gamma-thing", "Gamma thing")))
    repo.commit("v02")
    msg = codebook.register(repo.path / "codebook/purpose/v02.md", con)
    v2 = con.execute("SELECT codebook_version_id FROM codebook_versions WHERE version = 2").fetchone()[0]
    got = dict(con.execute("SELECT proposal_id, resulting_version_id FROM proposals"))
    assert got == {acc: v2, mer: v2, rej: None, pen: None}
    assert f"took in 2 decided proposal(s): #{acc}, #{mer}" in msg
    assert "Zeta) is still pending" in msg and "has no category" not in msg


def test_register_warns_when_a_decision_is_missing_from_the_version(repo, con):
    repo.write("codebook/purpose/v01.md", doc(body=category() + category("beta", "Beta")))
    repo.commit("v01")
    codebook.register(repo.path / "codebook/purpose/v01.md", con)
    _proposals_against_v01(con, [("Gamma", "accepted", None), ("Delta", "merged", "beta")])
    repo.write("codebook/purpose/v02.md", doc(2, 1, 2, body=category()))     # forgot gamma, dropped beta
    repo.commit("v02")
    msg = codebook.register(repo.path / "codebook/purpose/v02.md", con)
    assert "accepted proposal #1 (Gamma) has no category" in msg
    assert "merged into 'beta', which this version lacks" in msg


# --- freeze (#43) -----------------------------------------------------------------

def _git_out(repo, *a):
    return subprocess.run(["git", *a], cwd=repo.path, capture_output=True, text=True).stdout.strip()


def test_freeze_sets_the_flag_and_tags_the_commit(repo, con):
    repo.write("codebook/purpose/v01.md", doc(body=category()))
    repo.commit("v01")
    codebook.register(repo.path / "codebook/purpose/v01.md", con)
    msg = codebook.freeze("purpose", con)
    assert "frozen at v01" in msg and "codebook-purpose-v01-frozen" in msg
    assert con.execute("SELECT frozen FROM codebook_versions WHERE version = 1").fetchone()[0] == 1
    assert _git_out(repo, "rev-parse", "codebook-purpose-v01-frozen^{commit}") == _git_out(repo, "rev-parse", "HEAD")
    assert "already frozen" in codebook.freeze("purpose", con)          # idempotent
    with pytest.raises(Exception, match="frozen"):                          # db trigger now blocks category changes
        con.execute("DELETE FROM categories")


def test_freeze_refuses_unregistered_newer_file_and_pending_proposals(repo, con):
    with pytest.raises(SystemExit, match="no registered"):
        codebook.freeze("purpose", con)
    repo.write("codebook/purpose/v01.md", doc(body=category() + category("beta", "Beta")))
    repo.commit("v01")
    codebook.register(repo.path / "codebook/purpose/v01.md", con)
    _proposals_against_v01(con, [("Zeta", "pending", None)])
    with pytest.raises(SystemExit, match="still pending"):
        codebook.freeze("purpose", con, tag=False)
    con.execute("UPDATE proposals SET status = 'rejected', decided_by = 'both'")
    repo.write("codebook/purpose/v02.md", doc(2, 1, 2, body=category()))
    with pytest.raises(SystemExit, match="newer than the registered v01"):
        codebook.freeze("purpose", con, tag=False)
