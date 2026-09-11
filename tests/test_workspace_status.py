"""The deployment survey: where is this tool actually installed, and has it gone stale.

A different question from "analyze these repositories". Every repository name and file
here is invented.

The failure this mode has to avoid is a false "out of date". A survey that calls a
current index stale teaches the reader to ignore it, and then the one real staleness is
ignored too.
"""

from __future__ import annotations

import importlib
import io
from pathlib import Path

from omitnix.adapters.base import AnalysisResult
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


# --------------------------------------------------------------------------------------
# A machine that cannot read what the index was made with
# --------------------------------------------------------------------------------------


MISSING_GRAMMAR = (
    "the flow grammar is not installed (No module named 'tree_sitter_flow'). "
    'Install it with: pip install "omitnix[flow]"'
)


def _make_this_run_blind(monkeypatch) -> None:
    """Take away the adapter's ability to read, leaving every file on disk untouched.

    This is what a bare ``pip install omitnix`` is: the same repository, the same
    committed index, and a run that has no grammar to read the sources with.
    """
    module = importlib.import_module("omitnix.adapters.flow")

    def blind(self, request):  # noqa: ANN001, ANN202 - matches the adapter contract
        return AnalysisResult.unknown(MISSING_GRAMMAR)

    monkeypatch.setattr(module.FlowAdapter, "analyze", blind)


def test_a_run_that_cannot_read_the_sources_does_not_call_the_index_stale(
    tmp_path: Path, with_test_adapters, monkeypatch
) -> None:
    """Measured 2026-09-11 against the published 0.1.2: a bare install reported all nine
    deployed repositories as out of date and told the reader to regenerate them, which
    would have replaced nine good indexes with nearly empty ones.

    Nothing about the index had changed. The run had no grammars.
    """
    repo = make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    generate(repo)
    assert survey_repository("alpha", repo, tracked_only=False).state == "current"

    _make_this_run_blind(monkeypatch)
    status = survey_repository("alpha", repo, tracked_only=False)

    assert status.state == "unverified"
    # The reader has to be able to act on it, and the action is not "regenerate".
    assert 'pip install "omitnix[flow]"' in status.detail


def test_a_file_the_index_also_gave_up_on_is_not_a_lost_answer(
    tmp_path: Path, with_test_adapters
) -> None:
    """Both runs refused the same file, so this run is no worse. The comparison stands."""
    repo = make_repo(
        tmp_path,
        "alpha",
        {"a.flow": ORDERS_FLOW, "refused.flow": "unparsable: on purpose\n"},
    )
    generate(repo)

    status = survey_repository("alpha", repo, tracked_only=False)

    assert status.state == "current"
    assert status.coverage is not None
    assert status.coverage.unknown == 1


def test_an_index_that_could_not_be_checked_is_not_reported_as_out_of_date(
    tmp_path: Path, with_test_adapters, monkeypatch
) -> None:
    repo = make_repo(tmp_path, "alpha", {"a.flow": ORDERS_FLOW})
    generate(repo)
    _make_this_run_blind(monkeypatch)

    code, out, err = cli("--workspace", str(tmp_path), "--status", "--all-files")

    # Not a pass: "I could not check" and "I checked and it is fine" must not share an
    # exit code. But the word on the line, and the advice, are the other ones.
    assert code == EXIT_STALE
    assert "UNVERIFIED" in out
    assert "0 out of date, 1 could not be checked here" in out
    assert "could not be checked: alpha" in err
    assert "out of date: alpha" not in err
    assert "regenerate with" not in err


def test_the_advice_names_every_extra_this_repository_turned_out_to_need(
    tmp_path: Path, with_test_adapters, monkeypatch
) -> None:
    """0.1.1 removed the loop where each run named only the next missing piece. A survey
    meets several languages at once, so quoting the first reason would put the loop back.
    """
    repo = make_repo(
        tmp_path, "alpha", {"a.flow": ORDERS_FLOW, "b.flow": ORDERS_FLOW}
    )
    generate(repo)

    module = importlib.import_module("omitnix.adapters.flow")
    extras = {"a.flow": "html", "b.flow": "python"}

    def blind(self, request):  # noqa: ANN001, ANN202 - matches the adapter contract
        extra = extras[request.path]
        return AnalysisResult.unknown(
            f"the {extra} grammar is not installed (No module named 'x'). "
            f'Install it with: pip install "omitnix[{extra}]"'
        )

    monkeypatch.setattr(module.FlowAdapter, "analyze", blind)
    status = survey_repository("alpha", repo, tracked_only=False)

    assert status.state == "unverified"
    # One command, both extras, sorted so two runs say the same thing.
    assert 'pip install "omitnix[html,python]"' in status.detail
