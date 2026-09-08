"""The command line contract: what each flag does, and what each exit code means.

The exit codes are the part other tools consume, so they are asserted directly rather
than through the text of a message: 1 for a file that could not be analyzed, 3 for a
generated document that is out of date, 2 for a configuration this tool refuses to guess
at.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from omitnix.cli import EXIT_ERROR, EXIT_OK, EXIT_STALE, EXIT_UNKNOWN, main

from .conftest import ORDERS_FLOW, PLAIN_NOTE, REINDEX_FLOW, write_repo

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


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0


def test_full_run_writes_both_documents(tmp_path: Path, with_test_adapters: None) -> None:
    root = clean_repo(tmp_path)
    code, out, _ = run(["--root", str(root)])
    assert code == EXIT_OK
    assert (root / ".omitnix" / "index.json").is_file()
    assert (root / ".omitnix" / "index.md").is_file()
    assert "Coverage: 3/3 analyzed" in out


def test_an_unanalyzable_file_fails_the_run(tmp_path: Path, with_test_adapters: None) -> None:
    root = clean_repo(tmp_path)
    (root / "api" / "helper.unheardof").write_text("x", encoding="utf-8")
    # Widen the include patterns so the new extension is discovered rather than filtered.
    write_repo(root, {".omitnix.yaml": "include:\n  - '**/*.flow'\n  - '**/*.unheardof'\n"})
    code, _, err = run(["--root", str(root)])
    assert code == EXIT_UNKNOWN
    assert "could not be analyzed" in err
    assert "api/helper.unheardof" in err


def test_generated_documents_use_lf_on_every_platform(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """These documents get committed, so the platform that generated them must not show.

    Written in text mode without an explicit newline, Python would emit CRLF on Windows
    and LF elsewhere, and regenerating on another machine would read as a whole-file diff.
    """
    root = clean_repo(tmp_path)
    assert run(["--root", str(root)])[0] == EXIT_OK
    for name in ("index.json", "index.md"):
        assert b"\r\n" not in (root / ".omitnix" / name).read_bytes()


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


def test_print_on_an_unanalyzable_file_is_not_a_success(
    tmp_path: Path, with_test_adapters: None
) -> None:
    root = clean_repo(tmp_path)
    (root / "api" / "helper.unheardof").write_text("x", encoding="utf-8")
    code, out, _ = run(["--root", str(root), "--print", "api/helper.unheardof"])
    assert code == EXIT_UNKNOWN
    assert json.loads(out)["status"] == "unknown"


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
    assert "documents were not written" in err
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
