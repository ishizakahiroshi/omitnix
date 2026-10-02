"""Tests for compare_index.py. Every name in here is invented."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import compare_index as ci  # noqa: E402


def make_document() -> dict:
    return {
        "schema_version": 1,
        "generated": {
            "commit": "a" * 40,
            "dirty": False,
            "tool": "omitnix 0.1.3",
            "partial": False,
            "adapters": [{"name": "php", "extensions": [".php"], "capabilities": ["reads"]}],
            "tracked_only": True,
            "discovery_note": "",
        },
        "coverage": {
            "discovered": 2,
            "analyzed": 1,
            "unresolved": 1,
            "unknown": 0,
            "unclaimed": 0,
            "skipped_by_config": 0,
        },
        "files": [
            {
                "path": "src/a.php",
                "adapter": "php",
                "status": "analyzed",
                "fields": {"reads": {"state": "value", "value": ["orders"]}},
                "unresolved": [],
            },
            {
                "path": "src/b.php",
                "adapter": "php",
                "status": "unresolved",
                "fields": {"reads": {"state": "none_observed", "value": []}},
                "unresolved": [{"code": "dynamic_sql", "detail": "assembled"}],
            },
        ],
        "tables": [
            {
                "name": "orders",
                "read_by": ["src/a.php"],
                "written_by": [],
                "in_schema_snapshot": False,
                "unresolved_in": [],
            }
        ],
        "table_gaps": {"files": ["src/b.php"], "unresolved_count": 1, "note": "n"},
    }


def write(path: Path, document: dict, text: str | None = None) -> Path:
    path.write_text(
        text if text is not None else json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="",
    )
    return path


def run(tmp_path: Path, expected: dict, actual: dict, **kwargs) -> ci.Differences:
    left = write(tmp_path / "expected.json", expected)
    right = write(tmp_path / "actual.json", actual, kwargs.get("actual_text"))
    return ci.compare_files(left, right)


def test_identical_documents_are_the_same(tmp_path: Path) -> None:
    assert run(tmp_path, make_document(), make_document()).same


def test_run_to_run_provenance_is_ignored(tmp_path: Path) -> None:
    other = make_document()
    other["generated"]["commit"] = "b" * 40
    other["generated"]["dirty"] = True
    other["generated"]["tool"] = "omitnix-rust 0.1.3"
    assert run(tmp_path, make_document(), other).same


def test_the_discovery_question_is_not_ignored(tmp_path: Path) -> None:
    other = make_document()
    other["generated"]["tracked_only"] = False
    found = run(tmp_path, make_document(), other)
    assert found.counts == {"document.changed:generated.tracked_only": 1}


def test_the_adapter_list_is_compared(tmp_path: Path) -> None:
    other = make_document()
    other["generated"]["adapters"][0]["extensions"].append(".phtml")
    assert not run(tmp_path, make_document(), other).same


def test_a_missing_and_an_extra_file_are_counted_separately(tmp_path: Path) -> None:
    other = make_document()
    removed = other["files"].pop()
    removed["path"] = "src/c.php"
    other["files"].append(removed)
    found = run(tmp_path, make_document(), other)
    assert found.counts["files.missing"] == 1
    assert found.counts["files.extra"] == 1


def test_a_changed_field_is_named_by_part(tmp_path: Path) -> None:
    other = make_document()
    other["files"][0]["fields"]["reads"]["value"] = ["customers"]
    other["files"][1]["status"] = "analyzed"
    found = run(tmp_path, make_document(), other)
    assert found.counts["files.changed:fields.reads.value"] == 1
    assert found.counts["files.changed:status"] == 1


def test_a_changed_table_row_and_a_changed_coverage_are_reported(tmp_path: Path) -> None:
    other = make_document()
    other["tables"][0]["read_by"] = []
    other["coverage"]["analyzed"] = 2
    found = run(tmp_path, make_document(), other)
    assert found.counts["tables.changed:read_by"] == 1
    assert found.counts["document.changed:coverage.analyzed"] == 1


def test_the_same_entries_in_another_order_are_a_difference_of_order_only(
    tmp_path: Path,
) -> None:
    other = make_document()
    other["files"].reverse()
    found = run(tmp_path, make_document(), other)
    assert set(found.counts) == {"files.order"}


def test_key_order_is_its_own_category(tmp_path: Path) -> None:
    other = make_document()
    first = other["files"][0]
    other["files"][0] = {key: first[key] for key in reversed(list(first))}
    found = run(tmp_path, make_document(), other)
    assert set(found.counts) == {"key_order"}


def test_the_way_the_file_is_written_is_its_own_category(tmp_path: Path) -> None:
    document = make_document()
    compact = json.dumps(document)
    found = run(tmp_path, document, document, actual_text=compact + "\n")
    assert set(found.counts) == {"format"}


def test_a_trailing_newline_missing_is_a_format_difference(tmp_path: Path) -> None:
    document = make_document()
    text = json.dumps(document, indent=2, ensure_ascii=False)
    found = run(tmp_path, document, document, actual_text=text)
    assert set(found.counts) == {"format"}


def test_ascii_escaping_is_a_format_difference(tmp_path: Path) -> None:
    document = make_document()
    document["files"][0]["path"] = "src/注文.php"
    text = json.dumps(document, indent=2, ensure_ascii=True) + "\n"
    found = run(tmp_path, document, document, actual_text=text)
    assert set(found.counts) == {"format"}


def workspace_document() -> dict:
    return {
        "schema_version": 1,
        "kind": "workspace",
        "generated": {
            "tool": "omitnix 0.1.3",
            "workspace": "/somewhere",
            "jobs": 4,
            "seconds": 1.5,
            "workspace_excludes_applied": True,
            "tracked_files_only": True,
        },
        "repositories": {"discovered": 1, "ran": 1},
        "coverage": {"discovered": 1},
        "repos": [
            {
                "repo": "alpha",
                "status": "ok",
                "commit": "a" * 40,
                "dirty": False,
                "documents": ["/somewhere/out/repos/alpha/index.json"],
                "coverage": {"discovered": 1},
            }
        ],
        "records": [{"id": "alpha/a.php", "repo": "alpha", "path": "a.php", "status": "analyzed"}],
    }


def test_a_workspace_document_ignores_time_jobs_and_locations(tmp_path: Path) -> None:
    other = copy.deepcopy(workspace_document())
    other["generated"].update(workspace="/elsewhere", jobs=1, seconds=9.9, tool="x")
    other["repos"][0].update(commit="c" * 40, dirty=True, documents=[])
    assert run(tmp_path, workspace_document(), other).same


def test_a_workspace_record_difference_is_counted(tmp_path: Path) -> None:
    other = copy.deepcopy(workspace_document())
    other["records"][0]["status"] = "unknown"
    other["repos"][0]["coverage"]["discovered"] = 2
    found = run(tmp_path, workspace_document(), other)
    assert found.counts["records.changed:status"] == 1
    assert found.counts["repos.changed:coverage.discovered"] == 1


def test_the_same_path_in_two_repositories_is_two_records(tmp_path: Path) -> None:
    left = workspace_document()
    left["records"].append(
        {"id": "beta/a.php", "repo": "beta", "path": "a.php", "status": "analyzed"}
    )
    assert run(tmp_path, left, copy.deepcopy(left)).same
    other = copy.deepcopy(left)
    other["records"][1]["status"] = "unknown"
    found = run(tmp_path, left, other)
    assert found.counts["records.changed:status"] == 1
    assert "records.duplicate_key" not in found.counts


def test_the_default_report_names_no_path_and_no_table(tmp_path: Path) -> None:
    other = make_document()
    other["files"][0]["fields"]["reads"]["value"] = ["secret_table"]
    found = run(tmp_path, make_document(), other)
    report = ci.format_report(found, show_details=False)
    assert "src/a.php" not in report
    assert "orders" not in report
    assert "secret_table" not in report
    assert "files.changed:fields.reads.value: 1" in report


def test_details_are_available_on_request(tmp_path: Path) -> None:
    other = make_document()
    other["files"][0]["status"] = "unknown"
    report = ci.format_report(run(tmp_path, make_document(), other), show_details=True)
    assert "src/a.php" in report


def test_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    left = write(tmp_path / "a.json", make_document())
    same = write(tmp_path / "b.json", make_document())
    changed = make_document()
    changed["coverage"]["analyzed"] = 0
    different = write(tmp_path / "c.json", changed)

    assert ci.main([str(left), str(same)]) == ci.EXIT_SAME
    assert capsys.readouterr().out == "same\n"
    assert ci.main([str(left), str(different)]) == ci.EXIT_DIFFERENT
    assert "document.changed:coverage.analyzed: 1" in capsys.readouterr().out
    assert ci.main([str(left), str(tmp_path / "absent.json")]) == ci.EXIT_UNREADABLE


def test_a_document_that_is_not_json_is_unreadable_and_is_not_echoed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    left = write(tmp_path / "a.json", make_document())
    broken = tmp_path / "broken.json"
    broken.write_text("secret content {", encoding="utf-8")
    assert ci.main([str(left), str(broken)]) == ci.EXIT_UNREADABLE
    captured = capsys.readouterr()
    assert "secret content" not in captured.err
    assert "secret content" not in captured.out


def test_a_top_level_array_is_unreadable(tmp_path: Path) -> None:
    left = write(tmp_path / "a.json", make_document())
    other = tmp_path / "list.json"
    other.write_text("[]", encoding="utf-8")
    assert ci.main([str(left), str(other)]) == ci.EXIT_UNREADABLE
