"""Regression tests for public fixture context and verification failure signalling."""
import importlib.util
import json
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
spec = importlib.util.spec_from_file_location("truth_extract", TOOLS / "extract_from_tests.py")
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)


def fake_doc():
    return dict(adapter="php", source="tests/test_php_adapter.py", tests_in_file=1,
                tests_extracted=1, not_extracted=[], claims=[dict(
                    call=dict(file="summary.php", config={}), test="test_context", line=1,
                    kind="detail_contains", capability=None, expected="build_totals_sql")])


def test_generation_preserves_unclaimed_dependency_context(tmp_path, monkeypatch):
    fixtures = tmp_path / "fixtures"
    (fixtures / "common").mkdir(parents=True)
    (fixtures / "summary.php").write_text("<?php require 'common/reports.php';")
    (fixtures / "common/reports.php").write_text("<?php function build_totals_sql() {}")
    out = tmp_path / "output"
    monkeypatch.setattr(extract, "OUT", out)
    monkeypatch.setattr(extract, "TEST_FILES", [Path("tests/test_php_adapter.py")])
    monkeypatch.setattr(extract, "extract_file", lambda _: fake_doc())
    monkeypatch.setattr(extract, "fixtures_dir", lambda _: fixtures)
    monkeypatch.setattr("sys.argv", ["extract_from_tests.py"])
    assert extract.main() == 0
    assert (out / "inputs/php/common/reports.php").read_bytes() == (
        fixtures / "common/reports.php").read_bytes()
    assert json.loads((out / "php.json").read_text())["support_inputs"] == ["common/reports.php"]


def test_verify_failures_and_errors_return_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "OUT", tmp_path / "output")
    monkeypatch.setattr(extract, "TEST_FILES", [Path("test.py")])
    monkeypatch.setattr(extract, "extract_file", lambda _: fake_doc())
    monkeypatch.setattr(extract, "fixtures_dir", lambda _: None)
    monkeypatch.setattr("sys.argv", ["extract_from_tests.py", "--verify"])
    for result in (dict(passed=0, failed=[{"test": "test_context"}], errors=[]),
                   dict(passed=0, failed=[], errors=[{"error": "ValueError"}])):
        monkeypatch.setattr(extract, "verify", lambda *_args, result=result: result)
        assert extract.main() == 1
