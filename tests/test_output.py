"""Output validation: generated documents are written only where a run may write."""

from __future__ import annotations

from pathlib import Path

import pytest

from omitnix.config import load_config
from omitnix.errors import ConfigError, OmitnixError
from omitnix.output import write_document

from .conftest import write_repo


def _link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available here")


@pytest.mark.parametrize("value", ["/etc/out", "C:/out", "..", "a/../../out", r"a\..\out"])
def test_output_dir_must_stay_inside_the_repository(tmp_path: Path, value: str) -> None:
    write_repo(tmp_path, {".omitnix.yaml": f"output_dir: '{value}'\n"})
    with pytest.raises(ConfigError, match="relative path inside"):
        load_config(tmp_path)


def test_write_document_writes_and_replaces(tmp_path: Path) -> None:
    target = tmp_path / "out" / "index.json"
    write_document(target, "one\n", root=tmp_path)
    write_document(target, "two\n", root=tmp_path)
    assert target.read_bytes() == b"two\n"
    assert [p.name for p in target.parent.iterdir()] == ["index.json"]


def test_write_document_rejects_a_linked_destination(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep")
    repo = tmp_path / "repo"
    (repo / "out").mkdir(parents=True)
    _link(repo / "out" / "index.json", outside)
    with pytest.raises(OmitnixError):
        write_document(repo / "out" / "index.json", "x", root=repo)
    assert outside.read_bytes() == b"keep"


def test_write_document_rejects_a_directory_leaving_the_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    _link(repo / "out", outside)
    with pytest.raises(OmitnixError):
        write_document(repo / "out" / "index.json", "x", root=repo)
    assert list(outside.iterdir()) == []


def test_full_run_refuses_a_linked_index(tmp_path: Path, with_test_adapters: None) -> None:
    from .test_cli import clean_repo, run

    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep")
    repo = clean_repo(tmp_path / "repo")
    (repo / ".omitnix").mkdir()
    _link(repo / ".omitnix" / "index.json", outside)
    code, _, err = run(["--root", str(repo)])
    assert code != 0
    assert "refusing" in err
    assert outside.read_bytes() == b"keep"
