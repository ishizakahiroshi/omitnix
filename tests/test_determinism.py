"""The same source must produce the same document, every time.

This is not a nicety. The generated inventory is committed and `--check` compares it
against a fresh run, so a field that changes without its source changing turns CI red for
no reason and teaches everyone to ignore it. It also quietly destroys the claim the whole
tool rests on: that the document describes the commit it names.

Measured on 2026-09-08: the tree-sitter query cursor returned a capture's nodes in an
order that differed between processes, so "the first comment in the file" resolved to a
different comment from one run to the next, and two consecutive runs over this repository
produced different summaries for the same two files.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


def _print_record(path: Path, hash_seed: str) -> str:
    """Run the CLI in a separate process, so per-process ordering can differ."""
    completed = subprocess.run(
        [sys.executable, "-m", "omitnix", "--print", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
        timeout=180,
    )
    return completed.stdout


@pytest.mark.parametrize(
    "relative",
    [
        "php/orders_list.php",
        "python/orders_list.py",
        "tsjs/orders_list.ts",
    ],
)
def test_repeated_runs_produce_identical_records(relative: str) -> None:
    target = FIXTURES / relative
    if not target.is_file():  # pragma: no cover - fixture set differs per adapter
        pytest.skip(f"{relative} is not present")

    first = _print_record(target, "0")
    second = _print_record(target, "1")
    if not first.strip():  # pragma: no cover - the grammar is not installed here
        pytest.skip("the adapter produced no record; its grammar is probably missing")

    assert json.loads(first) == json.loads(second)
    assert first == second


def test_captures_come_back_in_document_order() -> None:
    """The property the fix guarantees, checked directly rather than through a diff."""
    treesitter = pytest.importorskip("omitnix.adapters._treesitter")
    try:
        grammar = treesitter.load_grammar("php", "tree_sitter_php", "language_php")
    except treesitter.GrammarUnavailable:  # pragma: no cover - grammar not installed
        pytest.skip("the PHP grammar is not installed")

    parsed = grammar.parse((FIXTURES / "php" / "orders_list.php").read_bytes())
    for nodes in parsed.captures.values():
        starts = [node.start_byte for node in nodes]
        assert starts == sorted(starts)
