"""The command line contract: what each flag does, and what each exit code means.

The exit codes are the part other tools consume, so they are asserted directly rather
than through the text of a message: 3 for a generated document that is out of date, 2 for
a configuration this tool refuses to guess at, and 1 for a file an adapter claimed and
could not read *in a repository that asked to fail on that* -- which is why several tests
below appear in pairs, one for the default and one for ``fail_on_unknown: true``.

A file no adapter claims is the other half of "not analyzed" and never reaches 1. It is
counted by extension instead, which is asserted here too: the number has to survive, and
the 95 lines naming Markdown files one by one do not.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from omitnix.cli import EXIT_ERROR, EXIT_OK, EXIT_STALE, EXIT_UNKNOWN, main

from .conftest import EXPORT_FLOW, ORDERS_FLOW, PLAIN_NOTE, REINDEX_FLOW, write_repo

CONFIG_YAML = """
include:
  - '**/*.flow'
  - '**/*.note'
authentication_functions:
  - require_session
authorization_functions:
  - apply_visibility_filter
"""


def clean_repo(tmp_path: Path) -> Path:
    """A repository whose every discovered file has an adapter, so a run can succeed."""
    write_repo(
        tmp_path,
        {
            ".omitnix.yaml": CONFIG_YAML,
            "api/orders_list.flow": ORDERS_FLOW,
            "batch/reindex.flow": REINDEX_FLOW,
            "docs/RELEASE.note": PLAIN_NOTE,
        },
    )
    return tmp_path


def run(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(args, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def _git_commit(root: Path) -> None:
    for command in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "tests@example.invalid"],
        ["git", "config", "user.name", "omitnix tests"],
        ["git", "config", "commit.gpgsign", "false"],
        ["git", "add", "-A"],
        ["git", "commit", "-q", "-m", "baseline"],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0


def test_full_run_writes_only_the_json_index(tmp_path: Path, with_test_adapters: None) -> None:
    """The one generated document. A Markdown rendering used to sit next to it; it was
    removed once a second tool started reading the JSON and writing the readable document
    itself, so this run must not leave one behind."""
    root = clean_repo(tmp_path)
    code, out, _ = run(["--root", str(root)])
    assert code == EXIT_OK
    assert (root / ".omitnix" / "index.json").is_file()
    assert not (root / ".omitnix" / "index.md").exists()
    assert "Coverage: 3/3 analyzed" in out


def test_a_run_says_out_loud_that_the_table_list_may_be_short(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """Printed as well as written.

    The reverse index is the half of the output people quote without opening the file
    records, and the sentence it must never be allowed to imply is "nothing touches this
    table". A run that could not read a statement says so where the run is read.
    """
    root = clean_repo(tmp_path)
    write_repo(root, {"api/orders_export.flow": EXPORT_FLOW})
    code, _, err = run(["--root", str(root)])
    assert code == EXIT_OK
    assert "the table list may be incomplete" in err


def test_a_run_that_read_everything_says_nothing_about_the_table_list(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The control. A notice on every run is a notice nobody reads."""
    code, _, err = run(["--root", str(clean_repo(tmp_path))])
    assert code == EXIT_OK
    assert "table list" not in err


WIDE_INCLUDE = "include:\n  - '**/*.flow'\n  - '**/*.unheardof'\n"

#: A file the ``.flow`` adapter claims and cannot read. The failure half of "not
#: analyzed", as opposed to an extension no adapter claims at all.
UNREADABLE_FLOW = "unparsable: yes\n"


def test_a_file_its_own_adapter_could_not_read_is_named_but_does_not_fail_the_run(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """Reported, not punished.

    The file is named and counted; the run still succeeds. Failing by default made every
    repository owe its configuration a written excuse for each unreadable thing, and some
    of those gaps -- a grammar that cannot read valid source of a language its own adapter
    claims -- have no fix the repository could apply. What keeps a gap from hiding is that
    it is printed and written into the documents, and that happens whatever the exit code.
    """
    root = clean_repo(tmp_path)
    write_repo(root, {"api/weird.flow": UNREADABLE_FLOW})
    code, _, err = run(["--root", str(root)])
    assert code == EXIT_OK
    assert "could not read them" in err
    assert "api/weird.flow" in err


def test_files_no_adapter_claims_are_counted_by_extension_and_never_named(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The noise this split exists to remove, and the number it must not remove with it.

    Measured on a real repository: 192 files named one by one, 95 of them ``.md``. The
    extension is the whole fact and repeating it per file buries the one real failure. So
    they are counted by extension on stderr -- and still counted in the coverage line, and
    still in the document by name, because a file nobody looked at is still a file here.
    """
    root = clean_repo(tmp_path)
    for name in ("a.unheardof", "b.unheardof", "c.unheardof"):
        (root / "api" / name).write_text("x", encoding="utf-8")
    # Widen the include patterns so the new extension is discovered rather than filtered.
    write_repo(root, {".omitnix.yaml": WIDE_INCLUDE})

    code, out, err = run(["--root", str(root)])

    assert code == EXIT_OK
    assert "3 unclaimed" in out
    assert "claimed by no adapter" in err
    assert ".unheardof x3" in err
    assert "api/a.unheardof" not in err
    index = json.loads((root / ".omitnix" / "index.json").read_text(encoding="utf-8"))
    assert index["coverage"]["unclaimed"] == 3
    assert "api/a.unheardof" in [record["path"] for record in index["files"]]


def test_a_repository_can_ask_to_fail_on_what_its_adapters_could_not_read(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """Strictness stays available to whoever will carry it, and is imposed on nobody."""
    root = clean_repo(tmp_path)
    write_repo(
        root,
        {
            ".omitnix.yaml": CONFIG_YAML + "fail_on_unknown: true\n",
            "api/weird.flow": UNREADABLE_FLOW,
        },
    )
    code, _, err = run(["--root", str(root)])
    assert code == EXIT_UNKNOWN
    assert "api/weird.flow" in err


def test_fail_on_unknown_does_not_fail_a_repository_that_only_has_unclaimed_files(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The strictest setting there is, and prose still does not break the build.

    ``fail_on_unknown`` asks to fail on what this tool could not read. A file no adapter
    claims was not read *and nothing went wrong*: there is no defect for anybody to fix,
    and no configuration to write. Failing here is what turned the strict mode into a
    chore that gets switched off -- and it would fire on this repository's own README.
    """
    root = clean_repo(tmp_path)
    for name in ("a.unheardof", "b.unheardof"):
        (root / "api" / name).write_text("x", encoding="utf-8")
    write_repo(root, {".omitnix.yaml": WIDE_INCLUDE + "fail_on_unknown: true\n"})

    code, out, err = run(["--root", str(root)])

    assert code == EXIT_OK
    assert "2 unclaimed" in out
    assert "claimed by no adapter" in err


def test_generated_document_uses_lf_on_every_platform(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """This document gets committed, so the platform that generated it must not show.

    Written in text mode without an explicit newline, Python would emit CRLF on Windows
    and LF elsewhere, and regenerating on another machine would read as a whole-file diff.
    """
    root = clean_repo(tmp_path)
    assert run(["--root", str(root)])[0] == EXIT_OK
    assert b"\r\n" not in (root / ".omitnix" / "index.json").read_bytes()


def test_check_is_quiet_when_up_to_date(tmp_path: Path, with_test_adapters: None) -> None:
    root = clean_repo(tmp_path)
    assert run(["--root", str(root)])[0] == EXIT_OK
    code, out, _ = run(["--root", str(root), "--check"])
    assert code == EXIT_OK
    assert "up to date" in out


def test_check_fails_when_the_source_moved_on(tmp_path: Path, with_test_adapters: None) -> None:
    root = clean_repo(tmp_path)
    assert run(["--root", str(root)])[0] == EXIT_OK
    (root / "api" / "orders_delete.flow").write_text(
        "summary: Delete an order\nwrites: orders\n", encoding="utf-8"
    )
    code, _, err = run(["--root", str(root), "--check"])
    assert code == EXIT_STALE
    assert "out of date" in err
    assert "api/orders_delete.flow" in err


def test_check_fails_on_an_unreadable_file_even_when_the_documents_are_current(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """Current and complete are different claims, and --check states both.

    A document that records an unreadable file faithfully is still a document with a hole
    in it, so --check names the hole even when nothing is stale. Whether that also fails
    the job is the repository's call; this is the repository that made it.
    """
    root = clean_repo(tmp_path)
    write_repo(
        root,
        {
            ".omitnix.yaml": CONFIG_YAML + "fail_on_unknown: true\n",
            "api/weird.flow": UNREADABLE_FLOW,
        },
    )

    assert run(["--root", str(root)])[0] == EXIT_UNKNOWN  # generated, and it says so

    code, out, err = run(["--root", str(root), "--check"])
    assert code == EXIT_UNKNOWN
    assert "up to date" in out
    assert "api/weird.flow" in err


def test_check_fails_when_nothing_was_generated_yet(
    tmp_path: Path, with_test_adapters: None
) -> None:
    root = clean_repo(tmp_path)
    code, _, err = run(["--root", str(root), "--check"])
    assert code == EXIT_STALE
    assert "does not exist" in err


def test_print_reports_one_file(tmp_path: Path, with_test_adapters: None) -> None:
    root = clean_repo(tmp_path)
    code, out, _ = run(["--root", str(root), "--print", "api/orders_list.flow"])
    assert code == EXIT_OK
    record = json.loads(out)
    assert record["path"] == "api/orders_list.flow"
    assert record["adapter"] == "flow"
    assert record["fields"]["reads"]["value"] == ["customers", "orders"]
    assert record["fields"]["screen_to_api"] == {"state": "out_of_scope"}


def test_print_says_unknown_in_the_record_whatever_the_exit_code(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The record is the answer; the exit code only follows the repository's policy."""
    root = clean_repo(tmp_path)
    write_repo(root, {"api/weird.flow": UNREADABLE_FLOW})
    code, out, _ = run(["--root", str(root), "--print", "api/weird.flow"])
    assert code == EXIT_OK
    assert json.loads(out)["status"] == "unknown"

    write_repo(root, {".omitnix.yaml": CONFIG_YAML + "fail_on_unknown: true\n"})
    code, out, _ = run(["--root", str(root), "--print", "api/weird.flow"])
    assert code == EXIT_UNKNOWN
    assert json.loads(out)["status"] == "unknown"


def test_print_on_an_unclaimed_file_says_so_and_exits_zero(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """Even under ``fail_on_unknown``: nothing tried to read it, so nothing failed."""
    root = clean_repo(tmp_path)
    (root / "api" / "helper.unheardof").write_text("x", encoding="utf-8")
    write_repo(root, {".omitnix.yaml": WIDE_INCLUDE + "fail_on_unknown: true\n"})

    code, out, _ = run(["--root", str(root), "--print", "api/helper.unheardof"])

    assert code == EXIT_OK
    record = json.loads(out)
    assert record["status"] == "unclaimed"
    assert ".unheardof" in record["reason"]


def test_print_on_a_missing_file_is_a_usage_error(
    tmp_path: Path, with_test_adapters: None
) -> None:
    root = clean_repo(tmp_path)
    code, _, err = run(["--root", str(root), "--print", "api/nowhere.flow"])
    assert code == EXIT_ERROR
    assert "no such file" in err


def test_partial_run_does_not_overwrite_the_full_index(
    tmp_path: Path, with_test_adapters: None
) -> None:
    root = clean_repo(tmp_path)
    assert run(["--root", str(root)])[0] == EXIT_OK
    before = (root / ".omitnix" / "index.json").read_text(encoding="utf-8")

    code, out, err = run(["--root", str(root), "--files", "api/orders_list.flow"])
    assert code == EXIT_OK
    assert "the document was not written" in err
    assert "Coverage: 1/1 analyzed" in out
    assert (root / ".omitnix" / "index.json").read_text(encoding="utf-8") == before


def test_partial_run_writes_when_asked(tmp_path: Path, with_test_adapters: None) -> None:
    root = clean_repo(tmp_path)
    code, _, _ = run(["--root", str(root), "--files", "api/orders_list.flow", "--write"])
    assert code == EXIT_OK
    payload = json.loads((root / ".omitnix" / "index.json").read_text(encoding="utf-8"))
    assert payload["generated"]["partial"] is True
    assert len(payload["files"]) == 1


def test_bad_configuration_is_reported_not_raised(tmp_path: Path, with_test_adapters: None) -> None:
    write_repo(tmp_path, {".omitnix.yaml": "excludes: []\n"})
    code, _, err = run(["--root", str(tmp_path)])
    assert code == EXIT_ERROR
    assert "unknown key" in err


# --------------------------------------------------------------------------------------
# Discovery: what git tracks by default, the whole working tree with --all-files
# --------------------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_single_repository_run_discovers_only_what_git_tracks_by_default(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The defect this whole change exists to fix, reproduced at unit scale.

    A single-repository run used to walk the filesystem unconditionally, so an untracked
    file (local scratch, a generated file, another tool's droppings) was discovered on
    the machine that happened to hold it and invisible everywhere else -- exactly the gap
    that made `--check` fail in CI against an index generated on a developer's machine.
    """
    root = clean_repo(tmp_path)
    _git_commit(root)
    (root / "api" / "untracked.flow").write_text(ORDERS_FLOW, encoding="utf-8")

    code, out, _ = run(["--root", str(root)])
    assert code == EXIT_OK
    assert "Coverage: 3/3 analyzed" in out
    index = (root / ".omitnix" / "index.json").read_text(encoding="utf-8")
    assert "api/untracked.flow" not in index


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_all_files_walks_a_single_repository_instead_of_asking_git(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The escape hatch, and it is not workspace-only any more."""
    root = clean_repo(tmp_path)
    _git_commit(root)
    (root / "api" / "untracked.flow").write_text(ORDERS_FLOW, encoding="utf-8")

    code, out, _ = run(["--root", str(root), "--all-files"])
    assert code == EXIT_OK
    assert "Coverage: 4/4 analyzed" in out
    index = (root / ".omitnix" / "index.json").read_text(encoding="utf-8")
    assert "api/untracked.flow" in index


def test_when_git_cannot_answer_the_fallback_is_named_on_stderr(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """"I could not ask git, so I walked the tree" must reach the user, not just the file.

    No repository here is a git working tree (no `.git` is created), so
    `discover_repository_files` falls back to walking and sets a note -- which used to
    reach nowhere in a single-repository run.
    """
    root = clean_repo(tmp_path)
    code, _, err = run(["--root", str(root)])
    assert code == EXIT_OK
    assert "git could not list tracked files" in err


def test_all_files_cannot_be_combined_with_gate(tmp_path: Path) -> None:
    code, _, err = run(["--root", str(tmp_path), "--gate", "--all-files"])
    assert code == EXIT_ERROR
    assert "--all-files cannot be combined with --gate" in err
