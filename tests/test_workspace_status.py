"""The deployment survey: where is this tool actually installed, and has it gone stale.

A different question from "analyze these repositories". Every repository name and file
here is invented.

The failure this mode has to avoid is a false "out of date". A survey that calls a
current index stale teaches the reader to ignore it, and then the one real staleness is
ignored too.
"""

from __future__ import annotations

import io
from pathlib import Path

from omitnix.cli import EXIT_OK, EXIT_STALE, main
from omitnix.workspace import survey_repository, survey_workspace

from .conftest import ORDERS_FLOW, write_repo
from .test_workspace import make_repo


def cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def generate(repo: Path) -> None:
    """Produce the index the way a single-repository run does."""
    code, _, err = cli("--root", str(repo), "--all-files")
    assert code == EXIT_OK, err


# --------------------------------------------------------------------------------------
# What the survey reports
# --------------------------------------------------------------------------------------


def test_a_repository_without_an_index_is_absent_not_blank(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})

    status = survey_repository("alpha", repo, tracked_only=False)

    assert status.state == "absent"
    assert status.has_index is False
    # Absent is an answer. A survey that leaves it blank reads as "not looked at".
    assert status.coverage is None


def test_a_freshly_generated_index_is_current(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    generate(repo)

    status = survey_repository("alpha", repo, tracked_only=False)

    assert status.state == "current"
    assert status.has_index is True
    assert status.coverage is not None


def test_an_index_left_behind_by_a_change_is_stale(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    generate(repo)
    write_repo(repo, {"b.flow": ORDERS_FLOW})

    status = survey_repository("alpha", repo, tracked_only=False)

    assert status.state == "stale"


def test_a_corrupt_index_is_unreadable_rather_than_current(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    generate(repo)
    (repo / ".omitnix" / "index.json").write_text("{ not json", encoding="utf-8")

    status = survey_repository("alpha", repo, tracked_only=False)

    # "Could not be read" and "matches" must never collapse into the same answer.
    assert status.state == "unreadable"
    assert "could not be read" in status.detail


# --------------------------------------------------------------------------------------
# The pointer: an index nobody is told to read
# --------------------------------------------------------------------------------------


def test_an_index_no_instruction_file_names_is_reported(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    generate(repo)

    status = survey_repository("alpha", repo, tracked_only=False)

    assert status.pointed_at_by == ()


def test_the_instruction_files_that_name_the_index_are_listed(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        "alpha",
        {
            "a.flow": ORDERS_FLOW,
            "CLAUDE.md": "read .omitnix/index.json before searching\n",
            "AGENTS.md": "the file index lives at .omitnix/index.json\n",
        },
    )
    generate(repo)

    status = survey_repository("alpha", repo, tracked_only=False)

    assert status.pointed_at_by == ("CLAUDE.md", "AGENTS.md")


def test_an_instruction_file_that_does_not_name_the_index_does_not_count(
    tmp_path: Path,
) -> None:
    repo = make_repo(
        tmp_path,
        "alpha",
        {"a.flow": ORDERS_FLOW, "CLAUDE.md": "this project uses omitnix\n"},
    )
    generate(repo)

    status = survey_repository("alpha", repo, tracked_only=False)

    # Naming the tool is not naming the document. Only the path counts.
    assert status.pointed_at_by == ()


# --------------------------------------------------------------------------------------
# The comparison has to match the run that produced the document
# --------------------------------------------------------------------------------------


def test_the_workspace_exclusions_do_not_make_a_current_index_look_stale(
    tmp_path: Path,
) -> None:
    """Measured 2026-09-11: with the workspace exclusions applied to the comparison,
    three repositories whose ``--check`` exits 0 were all reported out of date.

    The committed index is produced by running the tool inside the repository, so the
    survey has to reproduce that run and not a wider one.
    """
    repo = make_repo(
        tmp_path,
        "alpha",
        {
            "a.flow": ORDERS_FLOW,
            # The workspace defaults drop prose and declarative data by extension.
            # A single repository run keeps them and counts them as unclaimed, so the
            # two runs disagree about what was even discovered.
            "notes.md": "# notes\n",
            "data.json": "{}\n",
        },
    )
    generate(repo)

    status = survey_repository("alpha", repo, tracked_only=False)

    assert status.state == "current"
    # The count the survey reports has to be the single-run count, not a narrower one.
    assert status.coverage is not None
    assert status.coverage.discovered == 3


# --------------------------------------------------------------------------------------
# The whole workspace, and the exit code
# --------------------------------------------------------------------------------------


def test_the_survey_writes_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    generate(repo)
    before = sorted(p.name for p in tmp_path.rglob("*") if p.is_file())

    survey_workspace(tmp_path, tracked_only=False)

    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == before


def test_a_stale_repository_makes_the_command_exit_three(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    generate(repo)
    write_repo(repo, {"b.flow": ORDERS_FLOW})

    code, out, err = cli("--workspace", str(tmp_path), "--status", "--all-files")

    assert code == EXIT_STALE
    assert "STALE" in out
    assert "out of date: alpha" in err


def test_a_workspace_with_nothing_deployed_is_not_a_failure(tmp_path: Path) -> None:
    make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    make_repo(tmp_path, "beta", {"b.flow": ORDERS_FLOW})

    code, out, _ = cli("--workspace", str(tmp_path), "--status", "--all-files")

    assert code == EXIT_OK
    assert "0 with a committed index" in out


def test_repositories_without_an_index_are_still_listed(tmp_path: Path) -> None:
    make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    repo = make_repo(tmp_path, "beta", {"b.flow": ORDERS_FLOW})
    generate(repo)

    code, out, _ = cli("--workspace", str(tmp_path), "--status", "--all-files")

    assert code == EXIT_OK
    # "We surveyed 2 and 1 has it" and "there was 1" are different statements.
    assert "alpha" in out
    assert "2 repositor(y/ies) surveyed, 1 with a committed index" in out
