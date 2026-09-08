"""Commit provenance for the generated documents, and what git considers new.

Every generated document says which commit it came from, and whether the working tree
was dirty at the time. A document that cannot say what it describes is worse than no
document, so an unavailable commit is stated as unknown rather than left blank.

The same rule applies to newness. "This file is not new" and "I cannot tell whether it
is new" are different answers, so :func:`newly_added_files` returns ``None`` for the
second one instead of an empty set that would let a gate pass by accident.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__ = [
    "commit_of",
    "working_tree_is_dirty",
    "repository_root",
    "newly_added_files",
]


def _git_output(root: Path, *args: str) -> str | None:
    """Raw stdout of a git command, or None when it could not run or failed."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _git(root: Path, *args: str) -> str | None:
    output = _git_output(root, *args)
    return None if output is None else output.strip()


def commit_of(root: Path) -> str | None:
    """Full SHA of HEAD, or None when ``root`` is not a git working tree."""
    return _git(root, "rev-parse", "HEAD") or None


def working_tree_is_dirty(root: Path) -> bool:
    status = _git(root, "status", "--porcelain")
    return bool(status)


def repository_root(root: Path) -> Path | None:
    """Top of the working tree containing ``root``, or None when there is none."""
    top = _git(root, "rev-parse", "--show-toplevel")
    if not top:
        return None
    return Path(top).resolve()


def _parse_status_z(raw: str) -> list[tuple[str, str]]:
    """Split ``git status --porcelain -z`` into (status code, path) pairs.

    In this format a rename or copy is followed by its source path as a separate
    NUL-terminated field, which has to be consumed or every subsequent entry is
    misread as a status code.
    """
    fields = raw.split("\0")
    entries: list[tuple[str, str]] = []
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4 or entry[2] != " ":
            continue  # trailing empty field, or output we do not recognise
        code, path = entry[:2], entry[3:]
        if code[0] in "RC":
            index += 1  # the source path is its own field
        entries.append((code, path))
    return entries


def newly_added_files(root: Path) -> frozenset[str] | None:
    """Paths under ``root`` that git reports as newly added, relative to ``root``.

    Newly added means one of two things, which are the two ways a file that did not
    exist before reaches a review:

    * untracked (``??``) -- what a manual run sees before anything is staged;
    * staged as an addition (index status ``A``) -- what a pre-commit hook sees.

    A tracked file is not new however heavily it was rewritten, and a rename is not new
    either: its content existed before under another name, so the checks that matter for
    a brand new file were already owed on it earlier.

    Returns ``None`` when ``root`` is not inside a git working tree. Callers must treat
    that as "cannot tell" rather than as "nothing is new".
    """
    top = repository_root(root)
    if top is None:
        return None

    # The pathspec is a single "." rather than the caller's file list: it keeps the walk
    # inside ``root`` without ever building a command line out of an arbitrary number of
    # paths, which a pre-commit hook on a large change would otherwise overflow.
    raw = _git_output(root, "status", "--porcelain", "-z", "--untracked-files=all", "--", ".")
    if raw is None:
        return None

    resolved_root = root.resolve()
    added: set[str] = set()
    for code, path in _parse_status_z(raw):
        if code != "??" and code[0] != "A":
            continue
        # Porcelain paths are relative to the top of the working tree, which is not
        # necessarily the root being scanned.
        try:
            relative = (top / path).relative_to(resolved_root)
        except ValueError:
            continue  # inside the repository but outside the scanned root
        added.add(relative.as_posix())
    return frozenset(added)
