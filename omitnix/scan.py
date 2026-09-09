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
from .gitmeta import tracked_files
from .globs import directory_is_pruned, glob_match, matches_any, normalize

__all__ = [
    "effective_exclude",
    "discover_files",
    "discover_with_stats",
    "discover_repository_files",
    "Discovery",
    "RepoDiscovery",
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


@dataclass(frozen=True, slots=True)
class RepoDiscovery:
    """The files one repository offers a run, and how they were found."""

    files: list[str]
    #: ``tracked`` or ``walked``. Reported to the caller: the two answer different
    #: questions, and a document that mixed them without saying so would be comparing a
    #: repository's committed content against another run's working directory.
    mode: str
    excluded_files: int = 0
    pruned_directories: int = 0
    #: Tracked by git but not present on disk (deleted, or a submodule gitlink). Counted
    #: rather than dropped: they are files the index says exist.
    tracked_but_absent: int = 0
    note: str = ""


def discover_repository_files(config: Config, *, tracked_only: bool = True) -> RepoDiscovery:
    """What to analyze in one repository -- a single run, or one repository of a workspace.

    The default is what git tracks. A working tree also holds local scratch that is
    ignored on purpose -- one repository measured here keeps 24,436 files under a `tmp/`
    directory of database data directories and browser profiles -- and none of it is the
    repository's content. Committed files are, and they are the same set on every machine.

    That last clause is why a single-repository run uses this too, and not only a
    workspace one: a single run used to walk the filesystem unconditionally instead, which
    meant it was answering a different question depending on whose machine it ran on. On
    one real repository, wiring `--check` into CI surfaced this directly: the committed
    `.omitnix/index.json` had been generated on a developer's machine holding 66 files git
    does not track (a generated file, two other tools' scratch directories, stray
    `_scratch_*` files), so a clean CI checkout of the very same commit discovered 738
    files where the index said 803, and `--check` failed for a reason that had nothing to
    do with the inventory being stale -- the index was never reproducible from the
    repository at all. `--all-files` (``tracked_only=False``) asks for the walk on
    purpose, and still gets it, unlike that accident.

    The cost of the tracked-only default is that a brand new file, not yet added, is
    invisible here. That is the right trade for an index meant to be reproduced from a
    clean checkout, and the wrong one for the new-file gate, which is why the gate does
    not use this and looks at the working tree instead (:func:`omitnix.gitmeta.newly_added_files`).

    When git cannot answer, this walks the tree instead and says so in ``note``. Reporting
    zero files because the question could not be asked would be a repository silently
    emptied.
    """
    exclude = effective_exclude(config)
    if tracked_only:
        listed = tracked_files(config.root)
        if listed is not None:
            kept: list[str] = []
            excluded = 0
            absent = 0
            for raw in listed:
                rel = normalize(raw)
                if not (matches_any(config.include, rel) and not matches_any(exclude, rel)):
                    excluded += 1
                    continue
                if not (config.root / rel).is_file():
                    absent += 1
                    continue
                kept.append(rel)
            return RepoDiscovery(
                files=sorted(kept),
                mode="tracked",
                excluded_files=excluded,
                tracked_but_absent=absent,
            )
        note = "git could not list tracked files, so the working tree was walked instead"
    else:
        note = ""

    walked = discover_with_stats(config)
    return RepoDiscovery(
        files=walked.files,
        mode="walked",
        excluded_files=walked.excluded_files,
        pruned_directories=walked.pruned_directories,
        note=note,
    )


def discover_files(config: Config, *, tracked_only: bool = True) -> list[str]:
    """Repository-relative POSIX paths, sorted, for a full run.

    Delegates to :func:`discover_repository_files` and keeps only the file list -- mode,
    counts and the fallback note matter to the caller (the CLI prints the note; a
    workspace run reports mode and counts per repository), not to this entry point. The
    two are one function, not two independent walks, so a single-repository run and one
    repository of a workspace can never disagree about which files exist for the same
    ``tracked_only``.
    """
    return discover_repository_files(config, tracked_only=tracked_only).files


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
