"""Workspace mode: many repositories in one run.

Every repository name, path, table and function in this file is invented. The point of
most of these tests is a collision: something that is a unique key inside one repository
and stops being one the moment there are two.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from omitnix.cli import EXIT_ERROR, EXIT_OK, EXIT_UNKNOWN, main
from omitnix.workspace import (
    WORKSPACE_DEFAULT_EXCLUDE,
    discover_repositories,
    record_id,
    run_workspace,
    workspace_payload,
)

from .conftest import ORDERS_FLOW, REINDEX_FLOW, write_repo

HANDLER_FLOW = """summary: Handle one order
reads: orders
"""


def make_repo(workspace: Path, rel: str, files: dict[str, str]) -> Path:
    """A directory that looks like a git working tree, with no history in it.

    ``.git`` is what the search looks for, and an empty one is enough: the commit lookup
    then fails and is recorded as unknown, which is the behaviour a repository with no
    commits would get anyway.
    """
    repo = workspace / rel
    (repo / ".git").mkdir(parents=True)
    write_repo(repo, files)
    return repo


def run(workspace: Path, **kwargs):
    kwargs.setdefault("out_dir", None)
    kwargs.setdefault("write_documents", False)
    return run_workspace(workspace, **kwargs)


def cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------------------------
# Finding the repositories
# --------------------------------------------------------------------------------------


def test_every_working_tree_under_the_root_is_found(tmp_path: Path) -> None:
    make_repo(tmp_path, "public/alpha", {"a.flow": ORDERS_FLOW})
    make_repo(tmp_path, "private/beta", {"b.flow": ORDERS_FLOW})
    make_repo(tmp_path, "gamma", {"c.flow": ORDERS_FLOW})

    found = discover_repositories(tmp_path)

    assert found.repositories == ("gamma", "private/beta", "public/alpha")


def test_the_workspace_root_is_not_itself_a_repository(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})

    found = discover_repositories(tmp_path)

    # Otherwise the container would be analyzed as one undifferentiated tree, and every
    # repository inside it would be counted a second time as part of it.
    assert found.repositories == ("alpha",)


def test_a_working_tree_inside_a_working_tree_is_not_a_second_repository(
    tmp_path: Path,
) -> None:
    outer = make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    (outer / "deploy" / ".git").mkdir(parents=True)
    write_repo(outer / "deploy", {"a.flow": ORDERS_FLOW})

    found = discover_repositories(tmp_path)

    # This is what keeps <repository>/<path> unique: if a repository could sit inside
    # another one, two different pairs could spell the same key.
    assert found.repositories == ("alpha",)


def test_excluded_repositories_are_reported_rather_than_dropped(tmp_path: Path) -> None:
    make_repo(tmp_path, "public/alpha", {"a.flow": ORDERS_FLOW})
    make_repo(tmp_path, "study/borrowed", {"b.flow": ORDERS_FLOW})
    make_repo(tmp_path, "study/cloned", {"c.flow": ORDERS_FLOW})

    found = discover_repositories(tmp_path, ("study",))

    assert found.repositories == ("public/alpha",)
    # "We chose not to look at these two" is a different statement from "there was one".
    assert found.excluded == ("study/borrowed", "study/cloned")


def test_a_group_can_be_excluded_by_glob(tmp_path: Path) -> None:
    make_repo(tmp_path, "public/alpha", {"a.flow": ORDERS_FLOW})
    make_repo(tmp_path, "study/borrowed", {"b.flow": ORDERS_FLOW})

    found = discover_repositories(tmp_path, ("study/*",))

    assert found.repositories == ("public/alpha",)
    assert found.excluded == ("study/borrowed",)


# --------------------------------------------------------------------------------------
# The three identities that stop being unique
# --------------------------------------------------------------------------------------


def test_the_same_relative_path_in_two_repositories_is_two_records(
    tmp_path: Path, with_test_adapters: None
) -> None:
    make_repo(tmp_path, "alpha", {"src/handler.flow": ORDERS_FLOW})
    make_repo(tmp_path, "beta", {"src/handler.flow": REINDEX_FLOW})

    result = run(tmp_path)
    ids = [row["id"] for row in result.records()]

    assert ids == ["alpha/src/handler.flow", "beta/src/handler.flow"]
    assert len(set(ids)) == 2


def test_record_id_is_the_repository_and_the_path(tmp_path: Path) -> None:
    assert record_id("public/alpha", "src/handler.flow") == "public/alpha/src/handler.flow"


def test_byte_identical_files_in_two_repositories_analyze_differently(
    tmp_path: Path,
) -> None:
    """The reason there is no content-hash cache, demonstrated rather than asserted.

    Both repositories hold the same bytes at ``src/handler.php``. Each resolves
    ``__DIR__ . '/queries.php'`` to its own file, so the same bytes report different
    tables. A cache keyed on the content of the file would return one repository's answer
    for the other's file, and nothing in the output would show that it had happened.
    """
    pytest.importorskip("tree_sitter", reason="the PHP adapter needs the tree-sitter binding")
    pytest.importorskip("tree_sitter_php", reason="the PHP adapter needs the PHP grammar")
    pytest.importorskip("sqlglot", reason="the PHP adapter reads SQL with sqlglot")

    handler = """<?php
// Handle one order.
require __DIR__ . '/queries.php';

function handle($db) {
    return fetch_rows($db);
}
"""
    make_repo(
        tmp_path,
        "alpha",
        {
            "src/handler.php": handler,
            "src/queries.php": (
                "<?php\n"
                "// Shared queries.\n"
                "function fetch_rows($db) {\n"
                "    return $db->query('SELECT id FROM orders');\n"
                "}\n"
            ),
        },
    )
    make_repo(
        tmp_path,
        "beta",
        {
            "src/handler.php": handler,
            "src/queries.php": (
                "<?php\n"
                "// Shared queries.\n"
                "function fetch_rows($db) {\n"
                "    return $db->query('SELECT id FROM customers');\n"
                "}\n"
            ),
        },
    )

    result = run(tmp_path)
    by_repo = {run_.repo: run_.report for run_ in result.succeeded}

    alpha = by_repo["alpha"].file("src/handler.php")
    beta = by_repo["beta"].file("src/handler.php")

    same_bytes = (tmp_path / "alpha/src/handler.php").read_bytes()
    assert same_bytes == (tmp_path / "beta/src/handler.php").read_bytes()
    assert alpha.fields[list(alpha.fields)[3]].value == ["orders"]
    assert beta.fields[list(beta.fields)[3]].value == ["customers"]


def test_the_same_table_name_in_two_repositories_is_not_one_row(
    tmp_path: Path, with_test_adapters: None
) -> None:
    make_repo(tmp_path, "alpha", {"read.flow": HANDLER_FLOW})
    make_repo(tmp_path, "beta", {"write.flow": "summary: Refresh\nwrites: orders\n"})

    result = run(tmp_path)
    payload = workspace_payload(result)
    tables = {entry["repo"]: entry["tables"] for entry in payload["repos"]}

    # Both repositories observe a table called `orders`. They are different tables that
    # happen to share a name, and a merged reverse index would say one file reads what
    # another writes.
    assert [table["name"] for table in tables["alpha"]] == ["orders"]
    assert [table["name"] for table in tables["beta"]] == ["orders"]
    assert tables["alpha"][0]["read_by"] == ["alpha/read.flow"]
    assert tables["alpha"][0]["written_by"] == []
    assert tables["beta"][0]["written_by"] == ["beta/write.flow"]


def test_a_table_whose_file_could_not_be_read_in_full_is_marked_here_too(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The rollup is where a table list is read for fifty repositories at once.

    Its rows are qualified by repository, so the mark and the run-wide count have to be
    qualified the same way -- a bare path in a document that spans repositories names
    nothing in particular.
    """
    make_repo(tmp_path, "alpha", {"read.flow": HANDLER_FLOW})
    make_repo(
        tmp_path,
        "beta",
        {"write.flow": "summary: Refresh\nwrites: orders\nunresolved: dynamic_sql / built later\n"},
    )

    payload = workspace_payload(run(tmp_path))
    by_repo = {entry["repo"]: entry for entry in payload["repos"]}

    assert by_repo["alpha"]["tables"][0]["unresolved_in"] == []
    assert by_repo["alpha"]["table_gaps"]["unresolved_count"] == 0
    assert by_repo["beta"]["tables"][0]["unresolved_in"] == ["beta/write.flow"]
    assert by_repo["beta"]["table_gaps"]["files"] == ["beta/write.flow"]
    assert "may be incomplete" in by_repo["beta"]["table_gaps"]["note"]


# --------------------------------------------------------------------------------------
# Counting
# --------------------------------------------------------------------------------------


def test_the_counting_invariant_holds_across_the_workspace(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The same four buckets, summed, and they still have to add up.

    One repository contributes a file its adapter could not read and another contributes
    an extension nothing claims, so both halves of "not analyzed" cross a repository
    boundary here. A workspace total that dropped either would be the same lie as a
    single-repository total that dropped it, multiplied by the number of repositories.
    """
    make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW, "b.flow": REINDEX_FLOW})
    make_repo(tmp_path, "beta", {"c.flow": ORDERS_FLOW, "d.unmapped": "?"})
    make_repo(tmp_path, "gamma", {"e.flow": "unparsable: yes\n"})

    coverage = run(tmp_path).coverage

    assert coverage.discovered == 5
    assert coverage.holds
    assert coverage.analyzed == 3
    assert coverage.unknown == 1
    assert coverage.unclaimed == 1


def test_each_repository_reports_its_own_two_halves_of_not_analyzed(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """Named where a name is the only way to find it, counted where the count is the fact.

    Both are keyed by the workspace path: a bare ``e.flow`` in a document spanning fifty
    repositories names nothing in particular.
    """
    make_repo(tmp_path, "beta", {"d.unmapped": "?", "d2.unmapped": "?"})
    make_repo(tmp_path, "gamma", {"e.flow": "unparsable: yes\n"})

    by_repo = {entry["repo"]: entry for entry in workspace_payload(run(tmp_path))["repos"]}

    assert by_repo["beta"]["unclaimed_extensions"] == {".unmapped": 2}
    assert by_repo["beta"]["unknown_files"] == []
    assert by_repo["gamma"]["unclaimed_extensions"] == {}
    assert [entry["id"] for entry in by_repo["gamma"]["unknown_files"]] == ["gamma/e.flow"]
    assert by_repo["gamma"]["unknown_files"][0]["reason"]


def test_a_repository_that_cannot_be_run_is_counted_and_stops_nothing(
    tmp_path: Path, with_test_adapters: None
) -> None:
    make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    make_repo(tmp_path, "broken", {".omitnix.yaml": "not_a_key: 1\n", "b.flow": ORDERS_FLOW})
    make_repo(tmp_path, "gamma", {"c.flow": ORDERS_FLOW})

    result = run(tmp_path)

    assert [item.repo for item in result.succeeded] == ["alpha", "gamma"]
    assert [item.repo for item in result.failed] == ["broken"]
    # Its files are in no total. Folding it in as a zero would be the repository-sized
    # version of counting an unanalyzable file as analyzed.
    assert result.coverage.discovered == 2


def test_a_file_an_adapter_could_not_read_anywhere_fails_the_workspace_run(
    tmp_path: Path, with_test_adapters: None
) -> None:
    make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    make_repo(tmp_path, "beta", {"broken.flow": "unparsable: yes\n"})

    code, out, err = cli(
        "--workspace", str(tmp_path), "--out", str(tmp_path / "artifacts"), "--jobs", "1"
    )

    assert code == EXIT_UNKNOWN
    assert "1 unknown" in out
    assert "could not read them" in err


def test_a_workspace_of_files_no_adapter_claims_is_counted_and_succeeds(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """Fifty repositories of prose are not fifty failures.

    Every one of these files is still discovered, still counted, and still written into
    the document -- the run just does not pretend something went wrong.
    """
    make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    make_repo(tmp_path, "beta", {"theme.unmapped": "?", "other.unmapped": "?"})

    code, out, err = cli(
        "--workspace", str(tmp_path), "--out", str(tmp_path / "artifacts"), "--jobs", "1"
    )

    assert code == EXIT_OK
    assert "2 unclaimed" in out
    assert "claimed by no adapter" in err
    assert "theme.unmapped" not in err


def test_a_repository_that_could_not_be_run_takes_precedence_over_unknown(
    tmp_path: Path, with_test_adapters: None
) -> None:
    make_repo(tmp_path, "alpha", {"theme.flow": "unparsable: yes\n"})
    make_repo(tmp_path, "broken", {".omitnix.yaml": "not_a_key: 1\n"})

    code, _out, err = cli(
        "--workspace", str(tmp_path), "--out", str(tmp_path / "artifacts"), "--jobs", "1"
    )

    assert code == EXIT_ERROR
    assert "could not run broken" in err


# --------------------------------------------------------------------------------------
# Configuration, and what "not configured" means
# --------------------------------------------------------------------------------------


def test_a_repository_without_configuration_is_not_configured_not_unauthorized(
    tmp_path: Path, with_test_adapters: None
) -> None:
    make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})

    result = run(tmp_path)
    entry = workspace_payload(result)["repos"][0]

    assert entry["authorization_functions_configured"] is False
    assert entry["configuration"]["source"] == "defaults"
    # `unconfigured_authorization` is what a caller reads back to tell "not configured"
    # apart from "checked and found nothing" -- the same distinction the CLI's own
    # stderr message states (see test_the_warning_is_printed_and_not_only_written).
    assert result.unconfigured_authorization == (result.runs[0],)


def test_the_warning_is_printed_and_not_only_written(
    tmp_path: Path, with_test_adapters: None
) -> None:
    make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})

    _code, _out, err = cli(
        "--workspace", str(tmp_path), "--out", str(tmp_path / "artifacts"), "--jobs", "1"
    )

    assert "name no authorization function" in err
    assert "not a finding that they have none" in err


def test_a_repository_keeps_its_own_configuration(
    tmp_path: Path, with_test_adapters: None
) -> None:
    make_repo(
        tmp_path,
        "alpha",
        {
            ".omitnix.yaml": (
                "authorization_functions:\n  - apply_visibility_filter\n"
                "authentication_functions:\n  - require_session\n"
            ),
            "a.flow": ORDERS_FLOW,
        },
    )

    result = run(tmp_path)
    entry = workspace_payload(result)["repos"][0]

    assert entry["configuration"]["source"] == "own"
    assert entry["authorization_functions_configured"] is True
    assert entry["configuration"]["workspace_excludes_applied"] is True


def test_exclude_defaults_false_is_honoured_and_the_workspace_adds_nothing(
    tmp_path: Path, with_test_adapters: None
) -> None:
    make_repo(
        tmp_path,
        "alpha",
        {
            ".omitnix.yaml": 'exclude_defaults: false\nexclude:\n  - "skip/**"\n',
            "a.flow": ORDERS_FLOW,
            "notes.md": "prose",
            "skip/b.flow": ORDERS_FLOW,
        },
    )

    result = run(tmp_path)
    entry = workspace_payload(result)["repos"][0]

    # It asked to be walked exactly as written, so `notes.md` is discovered (and unknown)
    # rather than removed by a default it never accepted.
    assert entry["configuration"]["workspace_excludes_applied"] is False
    paths = [row["path"] for row in result.records()]
    assert "notes.md" in paths
    assert "skip/b.flow" not in paths


# --------------------------------------------------------------------------------------
# The default exclusions
# --------------------------------------------------------------------------------------


def test_build_and_dependency_directories_are_excluded_by_default(
    tmp_path: Path, with_test_adapters: None
) -> None:
    make_repo(
        tmp_path,
        "alpha",
        {
            "src/a.flow": ORDERS_FLOW,
            "node_modules/pkg/index.flow": ORDERS_FLOW,
            "target/debug/build.flow": ORDERS_FLOW,
            "dist/bundle.flow": ORDERS_FLOW,
            "README.md": "prose",
        },
    )

    result = run(tmp_path)

    assert [row["path"] for row in result.records()] == ["src/a.flow"]
    entry = workspace_payload(result)["repos"][0]
    # Removed, and said out loud. An exclusion nobody can see the size of is how a survey
    # quietly stops covering anything.
    assert entry["excluded"]["pruned_directories"] >= 3
    assert entry["excluded"]["files"] >= 1


def test_turning_the_workspace_excludes_off_discovers_everything(
    tmp_path: Path, with_test_adapters: None
) -> None:
    make_repo(
        tmp_path,
        "alpha",
        {"src/a.flow": ORDERS_FLOW, "target/build.flow": ORDERS_FLOW, "README.md": "prose"},
    )

    result = run(tmp_path, apply_workspace_excludes=False)
    paths = sorted(row["path"] for row in result.records())

    # Only the workspace layer is switched off. The tool's own defaults (`vendor`,
    # `node_modules`, `dist`, `.git`) are part of a single run and stay in force.
    assert paths == ["README.md", "src/a.flow", "target/build.flow"]


def test_a_repository_git_cannot_answer_for_is_walked_and_says_so(
    tmp_path: Path, with_test_adapters: None
) -> None:
    # The fixture repositories here hold an empty `.git`, so `git ls-files` fails on them.
    # Reporting zero files because the question could not be asked would empty the
    # repository silently, so the walk is the fallback and the fallback is stated.
    make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})

    result = run(tmp_path)
    entry = workspace_payload(result)["repos"][0]

    assert entry["discovery"]["mode"] == "walked"
    assert "git could not list tracked files" in entry["discovery"]["note"]
    assert entry["coverage"]["discovered"] == 1


def test_tracked_files_are_the_default_target(tmp_path: Path, with_test_adapters: None) -> None:
    """A working directory holds local scratch that is not the repository's content."""
    import subprocess

    repo = tmp_path / "alpha"
    repo.mkdir()
    write_repo(repo, {"kept.flow": ORDERS_FLOW, "tmp/scratch.flow": REINDEX_FLOW})
    for command in (
        ["git", "init", "-q"],
        ["git", "add", "kept.flow"],
    ):
        completed = subprocess.run(command, cwd=repo, capture_output=True, check=False)
        if completed.returncode != 0:
            pytest.skip("git is not available here")

    tracked = run(tmp_path)
    walked = run(tmp_path, tracked_only=False)

    assert [row["path"] for row in tracked.records()] == ["kept.flow"]
    assert sorted(row["path"] for row in walked.records()) == ["kept.flow", "tmp/scratch.flow"]
    assert workspace_payload(tracked)["repos"][0]["discovery"]["mode"] == "tracked"


def test_keys_and_certificates_are_excluded_by_default() -> None:
    # Not "no adapter reads them" but "nothing here opens them". A run that reports a
    # private key as unreadable is a run that invites somebody to go and look at it.
    for pattern in ("**/*.pem", "**/*.key", "**/*.p12", "**/.env", "**/.env.*"):
        assert pattern in WORKSPACE_DEFAULT_EXCLUDE


# --------------------------------------------------------------------------------------
# Where the output goes
# --------------------------------------------------------------------------------------


def test_nothing_is_written_into_a_scanned_repository_by_default(
    tmp_path: Path, with_test_adapters: None
) -> None:
    repo = make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    out_dir = tmp_path / "artifacts"

    code, out, _err = cli(
        "--workspace", str(tmp_path), "--out", str(out_dir), "--jobs", "1"
    )

    assert code == EXIT_OK
    assert not (repo / ".omitnix").exists()
    assert (out_dir / "workspace.json").is_file()
    assert not (out_dir / "workspace.md").exists()
    assert (out_dir / "repos" / "alpha" / "index.json").is_file()
    assert not (out_dir / "repos" / "alpha" / "index.md").exists()
    assert "wrote" in out


def test_write_per_repo_is_the_only_way_into_a_repository(
    tmp_path: Path, with_test_adapters: None
) -> None:
    repo = make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})

    code, _out, _err = cli(
        "--workspace",
        str(tmp_path),
        "--out",
        str(tmp_path / "artifacts"),
        "--write-per-repo",
        "--jobs",
        "1",
    )

    assert code == EXIT_OK
    assert (repo / ".omitnix" / "index.json").is_file()
    assert not (repo / ".omitnix" / "index.md").exists()


def test_the_workspace_output_is_not_analyzed_as_repository_content(
    tmp_path: Path, with_test_adapters: None
) -> None:
    repo = make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    out_dir = repo / "artifacts"

    code, _out, _err = cli(
        "--workspace", str(tmp_path), "--out", str(out_dir), "--jobs", "1"
    )
    payload = json.loads((out_dir / "workspace.json").read_text(encoding="utf-8"))

    assert code == EXIT_OK
    assert [row["path"] for row in payload["records"]] == ["a.flow"]


def test_dry_run_lists_the_repositories_and_writes_nothing(
    tmp_path: Path, with_test_adapters: None
) -> None:
    make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    make_repo(tmp_path, "study/borrowed", {"b.flow": ORDERS_FLOW})
    out_dir = tmp_path / "artifacts"

    code, out, err = cli(
        "--workspace",
        str(tmp_path),
        "--out",
        str(out_dir),
        "--exclude-repo",
        "study",
        "--dry-run",
    )

    assert code == EXIT_OK
    assert "alpha" in out
    assert "2 repositor" in out
    assert "excluded by request: study/borrowed" in err
    assert not out_dir.exists()


# --------------------------------------------------------------------------------------
# Parallelism
# --------------------------------------------------------------------------------------


def test_batching_covers_every_file_exactly_once() -> None:
    from omitnix.workspace import _chunks

    paths = [f"src/file{index:03d}.flow" for index in range(37)]

    for jobs in (1, 2, 8):
        batches = _chunks(paths, jobs)
        flattened = [path for batch in batches for path in batch]
        assert sorted(flattened) == sorted(paths)
        assert len(flattened) == len(set(flattened))

    # Neighbouring paths land in different batches: the expensive files in a repository
    # sit next to each other, and consecutive slices would give one worker all of them.
    first, second = _chunks(paths, 2)[0], _chunks(paths, 2)[1]
    assert paths[0] in first
    assert paths[1] in second


def test_workers_produce_exactly_what_one_process_produces(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """Parallelism is only acceptable if it is invisible in the output."""
    files = {f"src/file{index:02d}.flow": ORDERS_FLOW for index in range(12)}
    files["src/other.flow"] = REINDEX_FLOW
    make_repo(tmp_path, "alpha", files)
    make_repo(tmp_path, "beta", {"b.flow": REINDEX_FLOW})

    sequential = workspace_payload(run(tmp_path, jobs=1))
    parallel = workspace_payload(run(tmp_path, jobs=2))

    for payload in (sequential, parallel):
        del payload["generated"]
        for entry in payload["repos"]:
            entry.pop("seconds", None)

    assert sequential == parallel


# --------------------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["--check", "--gate", "--write"])
def test_single_repository_questions_are_refused_in_a_workspace(
    tmp_path: Path, flag: str
) -> None:
    make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})

    code, _out, err = cli("--workspace", str(tmp_path), flag)

    assert code == EXIT_ERROR
    assert f"{flag} cannot be combined with --workspace" in err


def test_workspace_only_options_are_refused_on_a_single_repository(tmp_path: Path) -> None:
    code, _out, err = cli("--root", str(tmp_path), "--write-per-repo")

    assert code == EXIT_ERROR
    assert "only applies with --workspace" in err


def test_a_missing_workspace_directory_is_an_error(tmp_path: Path) -> None:
    code, _out, err = cli("--workspace", str(tmp_path / "nowhere"))

    assert code == EXIT_ERROR
    assert "no such directory" in err


def test_jobs_must_be_at_least_one(tmp_path: Path) -> None:
    code, _out, err = cli("--workspace", str(tmp_path), "--jobs", "0")

    assert code == EXIT_ERROR
    assert "--jobs must be at least 1" in err


def test_an_empty_workspace_is_reported_rather_than_failing(tmp_path: Path) -> None:
    code, out, _err = cli(
        "--workspace", str(tmp_path), "--out", str(tmp_path / "artifacts"), "--jobs", "1"
    )

    assert code == EXIT_OK
    assert "0 repositor(y/ies) analyzed" in out
