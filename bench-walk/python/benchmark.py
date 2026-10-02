#!/usr/bin/env python3
"""Measure the unchanged front-to-back containment loop; never run omitnix."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from time import perf_counter_ns

BASE_COMMIT = "374e5bb337ec0f7e0f4a47d97c70083a306eb1ed"
RUNS = 5
Range = tuple[int, int]


def walk(candidates: list[Range]) -> tuple[int, int]:
    """Keep insertion order and count one comparison per containment predicate."""
    accepted: list[Range] = []
    comparisons = 0
    for start, end in candidates:
        for outer_start, outer_end in accepted:
            comparisons += 1
            if outer_start <= start and end <= outer_end:
                break
        else:
            accepted.append((start, end))
    return comparisons, len(accepted)


def prepare(candidates: list[Range]) -> list[Range]:
    return sorted(candidates, key=lambda item: (item[0], -item[1]))


def measure(
    batches: list[list[Range]], expected: tuple[int, int] | None = None
) -> tuple[int, int, float]:
    """Warm once, run five times, and time only calls to the same walk loop."""
    warm_comparisons = warm_remaining = 0
    for candidates in batches:
        comparisons, remaining = walk(candidates)
        warm_comparisons += comparisons
        warm_remaining += remaining
    if expected is None:
        expected = (warm_comparisons, warm_remaining)
    assert (warm_comparisons, warm_remaining) == expected

    samples = []
    for _ in range(RUNS):
        comparisons = remaining = elapsed = 0
        for candidates in batches:
            started = perf_counter_ns()
            batch_comparisons, batch_remaining = walk(candidates)
            elapsed += perf_counter_ns() - started
            comparisons += batch_comparisons
            remaining += batch_remaining
        assert (comparisons, remaining) == expected
        samples.append(elapsed / 1_000_000)
    return *expected, min(samples)


def synthetic_cases() -> list[tuple[str, list[Range], tuple[int, int, int]]]:
    small = [(i, i + 1) for i in range(825)]
    nested = []
    for i in range(200):
        nested.append((i * 1000, i * 1000 + 500))
        for j in range(20):
            nested.append((i * 1000 + 1 + j, i * 1000 + 2 + j))
    medium = [(i, i + 1) for i in range(4000)]
    return [
        ("S", prepare(small), (825, 339900, 825)),
        ("N", prepare(nested), (4200, 421900, 200)),
        ("M", prepare(medium), (4000, 7998000, 4000)),
    ]


# All families for which the base repository declares a tree-sitter grammar.
# Literal containers only: no string-content fragments or regex/text fallbacks.
GRAMMARS = (
    ((".py", ".pyi"), "python", "language", {"string", "concatenated_string"}),
    ((".php",), "php", "language_php", {"string", "encapsed_string", "heredoc", "nowdoc"}),
    ((".go",), "go", "language", {"interpreted_string_literal", "raw_string_literal"}),
    ((".rs",), "rust", "language", {"string_literal", "raw_string_literal"}),
    ((".js", ".mjs", ".cjs", ".jsx"), "javascript", "language", {"string", "template_string"}),
    ((".ts",), "typescript", "language_typescript", {"string", "template_string"}),
    ((".tsx",), "typescript", "language_tsx", {"string", "template_string"}),
    ((".html", ".htm"), "html", "language", {"quoted_attribute_value", "attribute_value"}),
)


class BindingUnavailable(RuntimeError):
    """The required native parser or a grammar could not be prepared."""


def load_parsers():
    try:
        from tree_sitter import Language, Parser

        parsers = {}
        for extensions, module_name, entry, kinds in GRAMMARS:
            grammar = importlib.import_module(f"tree_sitter_{module_name}")
            parser = Parser(Language(getattr(grammar, entry)()))
            for extension in extensions:
                parsers[extension] = (parser, kinds)
        return parsers
    except (ImportError, AttributeError, TypeError, ValueError, OSError) as exc:
        raise BindingUnavailable(str(exc)) from exc


def parse_batches(repo: Path) -> list[list[Range]]:
    """Parse all supported tracked blobs from BASE_COMMIT, never the worktree."""
    parsers = load_parsers()
    paths = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "-z", BASE_COMMIT], cwd=repo
    ).split(b"\0")
    batches = []
    for raw_path in paths:
        if not raw_path:
            continue
        path = raw_path.decode("utf-8")
        binding = parsers.get(Path(path).suffix)
        if binding is None:
            continue
        parser, kinds = binding
        source = subprocess.check_output(["git", "show", f"{BASE_COMMIT}:{path}"], cwd=repo)
        tree = parser.parse(source)
        candidates = []
        pending = [tree.root_node]
        while pending:
            node = pending.pop()
            if node.type in kinds:
                candidates.append((node.start_byte, node.end_byte))
            pending.extend(node.children)
        batches.append(prepare(candidates))
    if not batches:
        raise RuntimeError("No supported tracked source files found at the fixed base commit")
    return batches


def main() -> None:
    for label, candidates, expected in synthetic_cases():
        count, comparisons, remaining = expected
        assert len(candidates) == count
        _, _, elapsed = measure([candidates], (comparisons, remaining))
        print(f"walk python {label} {count} {comparisons} {remaining} {elapsed:.1f}")

    repo = Path(__file__).resolve().parents[2]
    try:
        batches = parse_batches(repo)
    except BindingUnavailable as exc:
        print(f"tree-sitter binding preparation failed: {exc}", file=sys.stderr)
        print("parse python BINDING_FAILED")
        return
    # The single warm-up establishes counters; every timed repetition must match.
    comparisons, remaining, elapsed = measure(batches)
    count = sum(len(candidates) for candidates in batches)
    print(
        f"parse python ok {len(batches)} {count} {comparisons} "
        f"{remaining} {elapsed:.1f}"
    )


if __name__ == "__main__":
    main()
