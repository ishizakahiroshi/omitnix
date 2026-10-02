"""Compare two omitnix ``index.json`` documents (or two ``workspace.json`` documents).

Used to hold a rewrite of omitnix to the Python implementation, which is the reference.
Standard library only, so it runs wherever a rewrite is being built.

By default it prints **counts and categories only**: never a path, a table name or a
reason. The documents it compares can describe a repository nobody outside it should read,
and this tool's output ends up in plans, pull requests and chat. ``--show-details`` lists
the paths and names and is for a repository whose content you are entitled to print.

Exit status: 0 identical, 1 different, 2 a document could not be read.

What is ignored (run-to-run provenance, not content):

* ``generated.commit``, ``generated.dirty``, ``generated.tool``
* in a workspace document: ``generated`` except ``workspace_excludes_applied`` and
  ``tracked_files_only``; per repository ``commit``, ``dirty`` and ``documents``

Everything else must be equal, including the order of the ``files`` and ``tables`` lists,
the order of the keys, and the way the file was written (two-space indent, no ASCII
escaping, one trailing newline, ``\\n`` line ends). The last two are reported as their own
categories (``key_order`` and ``format``) so a difference of form is never mistaken for a
difference of content.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

EXIT_SAME = 0
EXIT_DIFFERENT = 1
EXIT_UNREADABLE = 2

_IGNORED_GENERATED = ("commit", "dirty", "tool")
_WORKSPACE_GENERATED_KEPT = ("workspace_excludes_applied", "tracked_files_only")
_WORKSPACE_REPO_IGNORED = ("commit", "dirty", "documents")


class Differences:
    """Counted differences, with the names behind them kept for ``--show-details``."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self.names: dict[str, list[str]] = {}

    def add(self, category: str, name: str = "") -> None:
        self.counts[category] += 1
        if name:
            self.names.setdefault(category, []).append(name)

    @property
    def same(self) -> bool:
        return not self.counts


def _dumps(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def _key_order_differences(expected: Any, actual: Any, found: Differences, where: str) -> None:
    """Dictionaries whose keys come in a different order, wherever they sit."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        if list(expected) != list(actual) and set(expected) == set(actual):
            found.add("key_order", where)
        for key in expected.keys() & actual.keys():
            _key_order_differences(expected[key], actual[key], found, f"{where}.{key}")
    elif isinstance(expected, list) and isinstance(actual, list):
        for index, (left, right) in enumerate(zip(expected, actual, strict=False)):
            _key_order_differences(left, right, found, f"{where}[{index}]")


def _file_label(record: Any) -> str:
    if isinstance(record, dict):
        return str(record.get("path", record.get("id", "?")))
    return "?"


def _record_label(record: Any) -> str:
    """The key of a workspace record: repository and path together.

    The same path (``README.md``, ``composer.json``) is routinely present in more than one
    repository, so the path alone is not a key. Keyed by it, one record shadowed the others
    and every comparison of two real workspaces reported ``records.duplicate_key`` and
    silently dropped the shadowed records from the comparison.
    """
    if isinstance(record, dict):
        if record.get("id") is not None:
            return str(record["id"])
        return f"{record.get('repo', '?')}/{record.get('path', '?')}"
    return "?"


def _changed_parts(left: Any, right: Any, prefix: str = "") -> list[str]:
    """Which parts of two records differ, as dotted names (``fields.reads.state``)."""
    if isinstance(left, dict) and isinstance(right, dict):
        parts: list[str] = []
        for key in sorted(left.keys() | right.keys()):
            if key not in left or key not in right:
                parts.append(f"{prefix}{key}")
            else:
                parts.extend(_changed_parts(left[key], right[key], f"{prefix}{key}."))
        return parts
    if left != right:
        return [prefix.rstrip(".")]
    return []


def _compare_keyed_list(
    expected: list[Any],
    actual: list[Any],
    key: Callable[[Any], str],
    section: str,
    found: Differences,
) -> None:
    """Missing, extra and changed entries of a list whose entries have a unique key."""
    left = {key(item): item for item in expected}
    right = {key(item): item for item in actual}
    for name in sorted(left.keys() - right.keys()):
        found.add(f"{section}.missing", name)
    for name in sorted(right.keys() - left.keys()):
        found.add(f"{section}.extra", name)
    for name in sorted(left.keys() & right.keys()):
        if left[name] == right[name]:
            continue
        for part in _changed_parts(left[name], right[name]):
            found.add(f"{section}.changed:{part}", name)
    shared_left = [name for name in left if name in right]
    shared_right = [name for name in right if name in left]
    if shared_left != shared_right:
        found.add(f"{section}.order")
    if len(left) != len(expected) or len(right) != len(actual):
        found.add(f"{section}.duplicate_key")


def _repo_view(document: dict[str, Any]) -> dict[str, Any]:
    generated = dict(document.get("generated") or {})
    for name in _IGNORED_GENERATED:
        generated.pop(name, None)
    view = {key: value for key, value in document.items() if key != "generated"}
    view["generated"] = generated
    return view


def _compare_repo(expected: dict[str, Any], actual: dict[str, Any], found: Differences) -> None:
    left, right = _repo_view(expected), _repo_view(actual)
    for key in sorted(left.keys() | right.keys()):
        if key in ("files", "tables"):
            continue
        if left.get(key) != right.get(key):
            for part in _changed_parts({key: left.get(key)}, {key: right.get(key)}):
                found.add(f"document.changed:{part}")
    _compare_keyed_list(
        left.get("files") or [], right.get("files") or [], _file_label, "files", found
    )
    _compare_keyed_list(
        left.get("tables") or [],
        right.get("tables") or [],
        lambda item: str(item.get("name", "?")) if isinstance(item, dict) else "?",
        "tables",
        found,
    )


def _workspace_view(document: dict[str, Any]) -> dict[str, Any]:
    view = {key: value for key, value in document.items() if key != "generated"}
    generated = document.get("generated") or {}
    view["generated"] = {k: generated[k] for k in _WORKSPACE_GENERATED_KEPT if k in generated}
    repos = []
    for entry in document.get("repos") or []:
        repos.append({k: v for k, v in entry.items() if k not in _WORKSPACE_REPO_IGNORED})
    view["repos"] = repos
    return view


def _compare_workspace(
    expected: dict[str, Any], actual: dict[str, Any], found: Differences
) -> None:
    left, right = _workspace_view(expected), _workspace_view(actual)
    for key in sorted(left.keys() | right.keys()):
        if key in ("repos", "records"):
            continue
        if left.get(key) != right.get(key):
            for part in _changed_parts({key: left.get(key)}, {key: right.get(key)}):
                found.add(f"document.changed:{part}")
    _compare_keyed_list(
        left.get("repos") or [],
        right.get("repos") or [],
        lambda item: str(item.get("repo", "?")) if isinstance(item, dict) else "?",
        "repos",
        found,
    )
    _compare_keyed_list(
        left.get("records") or [],
        right.get("records") or [],
        _record_label,
        "records",
        found,
    )


def compare_documents(
    expected: dict[str, Any], actual: dict[str, Any], expected_text: str, actual_text: str
) -> Differences:
    """Every difference between two parsed documents and the text they were read from."""
    found = Differences()
    workspace = expected.get("kind") == "workspace" or actual.get("kind") == "workspace"
    if workspace:
        _compare_workspace(expected, actual, found)
    else:
        _compare_repo(expected, actual, found)
    _key_order_differences(
        _strip_ignored(expected, workspace), _strip_ignored(actual, workspace), found, "$"
    )
    if actual_text != _dumps(actual):
        found.add("format")
    if expected_text != _dumps(expected):
        # The reference document itself is badly formed: report it as a different category
        # so that nobody chases a rewrite for a fault that is in the data.
        found.add("reference_format")
    return found


def _strip_ignored(document: dict[str, Any], workspace: bool) -> dict[str, Any]:
    if workspace:
        return _workspace_view(document)
    return _repo_view(document)


def read_document(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    # Kept exactly as read: a carriage return is a ``format`` difference, not something to
    # normalise away before looking.
    text = raw.decode("utf-8")
    document = json.loads(text)
    if not isinstance(document, dict):
        raise ValueError("the top level of the document is not an object")
    return document, text


def compare_files(expected_path: Path, actual_path: Path) -> Differences:
    expected, expected_text = read_document(expected_path)
    actual, actual_text = read_document(actual_path)
    return compare_documents(expected, actual, expected_text, actual_text)


def format_report(found: Differences, *, show_details: bool) -> str:
    if found.same:
        return "same\n"
    lines = ["different"]
    for category in sorted(found.counts):
        lines.append(f"  {category}: {found.counts[category]}")
        if show_details:
            for name in found.names.get(category, [])[:50]:
                lines.append(f"    {name}")
            extra = len(found.names.get(category, [])) - 50
            if extra > 0:
                lines.append(f"    ... {extra} more")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare two omitnix index.json or workspace.json documents."
    )
    parser.add_argument("expected", type=Path, help="the reference document (Python version)")
    parser.add_argument("actual", type=Path, help="the document produced by the rewrite")
    parser.add_argument(
        "--show-details",
        action="store_true",
        help="also list the paths and table names behind each category (prints repository "
        "content; do not use on a private repository whose output may not be shared)",
    )
    args = parser.parse_args(argv)

    try:
        found = compare_files(args.expected, args.actual)
    except (OSError, ValueError) as exc:
        # ValueError covers UnicodeDecodeError and json.JSONDecodeError. The message names
        # the problem and the file, never the content.
        print(f"compare_index: could not read a document: {type(exc).__name__}", file=sys.stderr)
        return EXIT_UNREADABLE

    sys.stdout.write(format_report(found, show_details=args.show_details))
    return EXIT_SAME if found.same else EXIT_DIFFERENT


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
