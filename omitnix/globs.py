"""Glob matching for include and exclude patterns.

``PurePath.match`` does not treat ``**`` as "any number of directories" before Python
3.13, and ``fnmatch`` lets ``*`` cross a directory separator. Both are wrong for this
tool, so the translation is done here: ~40 lines, no dependency, and testable.

Paths handed to these helpers are repository-relative and use forward slashes.
"""

from __future__ import annotations

import re
from functools import lru_cache

__all__ = ["glob_match", "matches_any", "normalize", "directory_is_pruned"]


def normalize(path: str) -> str:
    """Repository-relative POSIX form, without a leading ``./`` or ``/``."""
    text = path.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


@lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern[str]:
    pattern = normalize(pattern)
    out: list[str] = ["(?s:"]
    i = 0
    n = len(pattern)
    while i < n:
        char = pattern[i]
        if char == "*":
            if pattern.startswith("**/", i):
                out.append("(?:.*/)?")
                i += 3
                continue
            if pattern.startswith("**", i):
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if char == "?":
            out.append("[^/]")
            i += 1
            continue
        if char == "[":
            end = i + 1
            if end < n and pattern[end] in "!^":
                end += 1
            if end < n and pattern[end] == "]":
                end += 1
            while end < n and pattern[end] != "]":
                end += 1
            if end >= n:  # unterminated class: treat as a literal bracket
                out.append(re.escape(char))
                i += 1
                continue
            body = pattern[i + 1 : end].replace("\\", "\\\\")
            if body[:1] in ("!", "^"):
                body = "^" + body[1:]
            out.append(f"[{body}]")
            i = end + 1
            continue
        out.append(re.escape(char))
        i += 1
    out.append(r")\Z")
    return re.compile("".join(out))


def glob_match(pattern: str, path: str) -> bool:
    return _compile(pattern).match(normalize(path)) is not None


def matches_any(patterns: tuple[str, ...], path: str) -> bool:
    return any(glob_match(pattern, path) for pattern in patterns)


def directory_is_pruned(exclude: tuple[str, ...], rel_dir: str) -> bool:
    """True when *every* file under ``rel_dir`` is excluded, so the walk can skip it.

    Pruning is an optimisation, and a wrong optimisation would silently drop files --
    the one failure mode this tool exists to prevent. So it only fires on patterns that
    provably cover the whole subtree: an exact match on the directory, or a recursive
    ``.../**`` pattern whose prefix matches it.
    """
    rel_dir = normalize(rel_dir)
    if not rel_dir:
        return False
    for pattern in exclude:
        pattern = normalize(pattern)
        if glob_match(pattern, rel_dir):
            return True
        if pattern.endswith("/**") and glob_match(pattern[:-3], rel_dir):
            return True
    return False
