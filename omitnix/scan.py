"""Finding the files to analyze.

Discovery is deliberately blunt: everything under the root that the include patterns
accept and the exclude patterns do not. There is no "interesting file types" filter,
because a file type nobody thought about is precisely the case this tool must not
silently drop -- it becomes an ``unknown`` record later instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .globs import directory_is_pruned, glob_match, matches_any, normalize

__all__ = [
    "effective_exclude",
    "discover_files",
    "discover_with_stats",
    "Discovery",
    "select_files",
    "SelectionResult",
]


def effective_exclude(config: Config) -> tuple[str, ...]:
    """Configured exclusions plus the tool's own output directory."""
    own_output = f"{normalize(config.output_dir)}/**"
    if own_output in config.exclude:
        return config.exclude
    return config.exclude + (own_output,)


def _is_included(config: Config, exclude: tuple[str, ...], rel: str) -> bool:
    return matches_any(config.include, rel) and not matches_any(exclude, rel)


@dataclass(frozen=True, slots=True)
class Discovery:
    """What one walk of a repository found, and what it decided not to look at.

    The two rejection counts exist so that a caller can say out loud how much of a tree
    an exclusion list removed. A workspace run leans on broad defaults, and an exclusion
    nobody can see the size of is how a survey quietly stops covering anything.

    ``pruned_directories`` counts directory *trees* skipped whole, not the files inside
    them: the walk never enters them, so their contents were never counted. Saying
    "3 trees pruned" is the honest form of that; a file count would be invented.
    """

    files: list[str]
    #: Files the walk saw and the include/exclude patterns rejected.
    excluded_files: int = 0
    #: Directory trees the walk skipped whole. Their contents are in no count here.
    pruned_directories: int = 0


def discover_with_stats(config: Config) -> Discovery:
    """One walk of the repository, reporting what it kept and what it turned away."""
    exclude = effective_exclude(config)
    root = config.root
    found: list[str] = []
    excluded_files = 0
    pruned_directories = 0

    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = normalize(str(Path(dirpath).relative_to(root)))
        rel_dir = "" if rel_dir == "." else rel_dir
        kept_dirs: list[str] = []
        for name in sorted(dirnames):
            child = f"{rel_dir}/{name}" if rel_dir else name
            if directory_is_pruned(exclude, child):
                pruned_directories += 1
            else:
                kept_dirs.append(name)
        dirnames[:] = kept_dirs
        for filename in filenames:
            rel = f"{rel_dir}/{filename}" if rel_dir else filename
            if _is_included(config, exclude, rel):
                found.append(rel)
            else:
                excluded_files += 1

    return Discovery(
        files=sorted(found),
        excluded_files=excluded_files,
        pruned_directories=pruned_directories,
    )


def discover_files(config: Config) -> list[str]:
    """Repository-relative POSIX paths, sorted, for a full run."""
    return discover_with_stats(config).files


class SelectionResult(list[str]):
    """Paths to analyze, carrying the count of paths dropped by the configuration."""

    def __init__(self, paths: list[str], skipped: int = 0, missing: tuple[str, ...] = ()):
        super().__init__(paths)
        self.skipped = skipped
        self.missing = missing


def select_files(config: Config, requested: list[str]) -> SelectionResult:
    """Filter an explicit file list (from a hook) through the same rules as a full run.

    A requested path that the configuration excludes is reported as skipped rather than
    dropped quietly, and a path outside the repository is an error the caller surfaces.
    """
    exclude = effective_exclude(config)
    kept: list[str] = []
    missing: list[str] = []
    skipped = 0

    for raw in requested:
        candidate = Path(raw)
        absolute = candidate if candidate.is_absolute() else config.root / candidate
        try:
            rel = normalize(str(absolute.resolve().relative_to(config.root)))
        except ValueError:
            missing.append(raw)
            continue
        if not absolute.is_file():
            missing.append(raw)
            continue
        if _is_included(config, exclude, rel):
            kept.append(rel)
        else:
            skipped += 1

    return SelectionResult(sorted(set(kept)), skipped=skipped, missing=tuple(missing))


def matches_include(config: Config, rel: str) -> bool:
    return any(glob_match(pattern, rel) for pattern in config.include)
