"""Running across many repositories at once.

A workspace run is **not** a single run with a wider root, and it is not the per-repository
runs concatenated. It is a layer on top: each repository is analyzed exactly as it would
be on its own, and this module identifies, aggregates and reports the results. Nothing
here changes what a single repository produces.

Three identities stop being unique the moment more than one repository is involved, and
each one is handled explicitly rather than by hoping the collision does not happen:

**A file's key.** Within a repository a record is keyed by its path relative to the root.
Two repositories very often hold the same relative path -- a repository and a deployment
clone of it are the ordinary case -- so a workspace record is keyed by
``<repository>/<path>`` (:func:`record_id`). The repository part is itself the path of the
repository relative to the workspace root, and because only the outermost working tree at
any location is treated as a repository, no two repositories can produce the same key.

**A table's name.** The per-file index is worth having because it can be read backwards:
which files touch ``orders``. Across repositories that reverse index would quietly place
one system's ``orders`` and another system's ``orders`` on the same row, and a reader has
no way to see that it happened. So the reverse index is **never merged**. It stays inside
the repository it was built from, and the rollup reports per-repository counts.

**A file's content.** Not used as a key at all. Two byte-identical files can analyze to
different results -- ``require __DIR__ . '/common/queries.php'`` resolves to a different
file in a different directory -- so there is no content-hash cache here. Repeated work is
answered with parallelism, which is stateless, instead.
"""

from __future__ import annotations

import importlib
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .analyze import TOOL, analyze_file, assemble_report
from .config import Config, load_config
from .errors import OmitnixError
from .gitmeta import tracked_files
from .globs import glob_match, matches_any, normalize
from .model import Coverage, FileRecord, Report, Status
from .registry import AdapterSet, build_adapter_set
from .render import render_json, render_markdown
from .scan import discover_with_stats, effective_exclude
from .schema import load_schema_tables

__all__ = [
    "WORKSPACE_OUTPUT_DIR",
    "WORKSPACE_DEFAULT_EXCLUDE",
    "record_id",
    "discover_repositories",
    "RepositoryDiscovery",
    "RepositoryRun",
    "WorkspaceResult",
    "run_workspace",
    "render_workspace_json",
    "render_workspace_markdown",
]

#: Where a workspace run writes, relative to the current directory unless ``--out`` says
#: otherwise. One place, outside every scanned repository: most of them belong to somebody
#: else's working day, and scattering generated files through them is not this tool's
#: business. ``--write-per-repo`` is the way to ask for that on purpose.
WORKSPACE_OUTPUT_DIR = ".omitnix-workspace"

#: Exclusions a workspace run adds to every repository that has not said otherwise.
#:
#: Measured, not guessed. Across 52 repositories on this machine, 139,686 files were
#: discovered and 96,926 of them had no adapter. The largest block by far -- 38,948 -- was
#: not a language question at all: it was build output and vendored dependencies, which no
#: list of extensions can describe (one Rust ``target/`` alone contributes ``.o``,
#: ``.rmeta``, ``.rlib``, ``.d`` and ``.timestamp``). So the first block is directories.
#:
#: The other blocks are file types that are not program source. That is a weaker claim
#: than "unimportant", and it is why every one of these is counted and reported: a
#: workspace run says how many paths its defaults removed, per repository.
#:
#: A repository that disagrees writes its own ``.omitnix.yaml``; one that says
#: ``exclude_defaults: false`` is walked exactly as it asked, with none of this added.
WORKSPACE_DEFAULT_EXCLUDE: tuple[str, ...] = (
    # --- A. Built here, or fetched here. Not authored here. -------------------------
    "**/.git/**",
    "**/node_modules/**",
    "**/bower_components/**",
    "**/jspm_packages/**",
    "**/vendor/**",
    "**/third_party/**",
    "**/dist/**",
    "**/build/**",
    "**/out/**",
    "**/target/**",
    "**/obj/**",
    "**/.next/**",
    "**/.nuxt/**",
    "**/.output/**",
    "**/.svelte-kit/**",
    "**/.turbo/**",
    "**/.parcel-cache/**",
    "**/.cache/**",
    "**/__pycache__/**",
    "**/.venv/**",
    "**/venv/**",
    "**/.tox/**",
    "**/.nox/**",
    "**/site-packages/**",
    "**/*.egg-info/**",
    "**/.mypy_cache/**",
    "**/.pytest_cache/**",
    "**/.ruff_cache/**",
    "**/coverage/**",
    "**/htmlcov/**",
    "**/.nyc_output/**",
    "**/.gradle/**",
    "**/.terraform/**",
    "**/.idea/**",
    "**/.vs/**",
    "**/*.min.js",
    "**/*.min.css",
    "**/*.map",
    # --- B. Prose and tabular documents ---------------------------------------------
    "**/*.md",
    "**/*.mdx",
    "**/*.mdc",
    "**/*.markdown",
    "**/*.txt",
    "**/*.rst",
    "**/*.adoc",
    "**/*.pdf",
    "**/*.csv",
    "**/*.tsv",
    "**/*.xlsx",
    "**/*.xls",
    "**/*.docx",
    "**/*.pptx",
    # --- C. Declarative data ---------------------------------------------------------
    # A schema snapshot is read by path, from `schema_snapshot:` in the repository's own
    # configuration, and never through discovery -- so excluding `*.json` here does not
    # hide one.
    "**/*.json",
    "**/*.jsonc",
    "**/*.json5",
    "**/*.yaml",
    "**/*.yml",
    "**/*.toml",
    "**/*.ini",
    "**/*.cfg",
    "**/*.conf",
    "**/*.properties",
    "**/*.lock",
    "**/*.xml",
    "**/*.plist",
    # --- D. Binary assets -------------------------------------------------------------
    "**/*.png",
    "**/*.jpg",
    "**/*.jpeg",
    "**/*.gif",
    "**/*.svg",
    "**/*.webp",
    "**/*.avif",
    "**/*.ico",
    "**/*.bmp",
    "**/*.icns",
    "**/*.woff",
    "**/*.woff2",
    "**/*.ttf",
    "**/*.otf",
    "**/*.eot",
    "**/*.mp3",
    "**/*.mp4",
    "**/*.wav",
    "**/*.mov",
    "**/*.webm",
    "**/*.ogg",
    "**/*.zip",
    "**/*.gz",
    "**/*.tgz",
    "**/*.xz",
    "**/*.7z",
    "**/*.rar",
    "**/*.tar",
    "**/*.exe",
    "**/*.dll",
    "**/*.so",
    "**/*.dylib",
    "**/*.bin",
    "**/*.wasm",
    "**/*.o",
    "**/*.a",
    "**/*.lib",
    "**/*.pdb",
    "**/*.class",
    "**/*.jar",
    "**/*.db",
    "**/*.sqlite",
    "**/*.sqlite3",
    "**/*.log",
    # --- E. Keys, certificates and environment files ----------------------------------
    # Excluded first of all so that nothing here ever opens one. A run that reports these
    # as unreadable invites somebody to go and look at them, which is the wrong direction.
    "**/*.pem",
    "**/*.crt",
    "**/*.cer",
    "**/*.csr",
    "**/*.key",
    "**/*.der",
    "**/*.p12",
    "**/*.pfx",
    "**/*.jks",
    "**/*.gpg",
    "**/*.asc",
    "**/.env",
    "**/.env.*",
    "**/*.env",
    # --- F. Well-known files that carry no extension ----------------------------------
    # Named one by one on purpose. "Everything without an extension" would also cover
    # shell scripts, which are program source and have an adapter.
    "**/LICENSE",
    "**/LICENCE",
    "**/COPYING",
    "**/NOTICE",
    "**/AUTHORS",
    "**/CONTRIBUTORS",
    "**/CHANGELOG",
    "**/README",
    "**/VERSION",
    "**/CODEOWNERS",
    "**/CNAME",
    "**/Makefile",
    "**/GNUmakefile",
    "**/Dockerfile",
    "**/Dockerfile.*",
    "**/Procfile",
    "**/Gemfile",
    "**/Rakefile",
    "**/Brewfile",
    "**/Vagrantfile",
    "**/Jenkinsfile",
    "**/.gitignore",
    "**/.gitattributes",
    "**/.gitmodules",
    "**/.gitkeep",
    "**/.editorconfig",
    "**/.npmrc",
    "**/.nvmrc",
    "**/.npmignore",
    "**/.dockerignore",
    "**/.prettierignore",
    "**/.eslintignore",
)

#: Directory names the search for repositories never descends into. They cannot contain a
#: repository of this workspace: the search already stops at the outermost working tree,
#: so anything inside one of these is inside a repository that was already found.
_NEVER_A_GROUP = frozenset({".git", "node_modules", "vendor", "__pycache__", "site-packages"})

_MAX_LISTED = 20


def record_id(repo: str, path: str) -> str:
    """The key of one file in a workspace run: ``<repository>/<path>``.

    Both halves are workspace-relative POSIX paths, so the result is just a path from the
    workspace root -- which is exactly why it cannot collide. Two repositories nested one
    inside the other would break that, and they cannot occur: only the outermost working
    tree at any location is treated as a repository.
    """
    return f"{repo}/{path}" if repo else path


@dataclass(frozen=True, slots=True)
class RepositoryDiscovery:
    """What the search for repositories found, including what it could not look at."""

    repositories: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    unreadable_directories: tuple[str, ...] = ()


def _repo_matches(rel: str, patterns: tuple[str, ...]) -> bool:
    for raw in patterns:
        pattern = normalize(raw).rstrip("/")
        if not pattern:
            continue
        if glob_match(pattern, rel) or glob_match(f"{pattern}/**", rel):
            return True
    return False


def discover_repositories(
    root: Path, exclude: tuple[str, ...] = ()
) -> RepositoryDiscovery:
    """Find the repositories under ``root``.

    A directory holding ``.git`` (a directory or, for a worktree, a file) is a repository,
    and the search does not go inside one: a deployment clone checked out within another
    working tree belongs to that tree's owner, not to this survey.

    ``root`` itself is never a repository even when it is a working tree, because the
    point of a workspace is the repositories it contains; treating the container as one
    of them would analyze all of them again as a single undifferentiated tree.

    Excluded repositories are returned rather than dropped. "We chose not to run these
    three" and "there were only 49" are different statements, and only the first is true.

    Directories that cannot be listed are returned too. A survey that silently skips what
    it could not open reports a smaller world as if it were the whole one.
    """
    root = root.resolve()
    found: list[str] = []
    unreadable: list[str] = []
    stack: list[Path] = [root]

    while stack:
        current = stack.pop()
        try:
            entries = sorted(os.scandir(current), key=lambda entry: entry.name)
        except OSError as exc:
            rel = normalize(str(current.relative_to(root))) if current != root else "."
            unreadable.append(f"{rel}: {exc.strerror or exc}")
            continue
        for entry in entries:
            if entry.name in _NEVER_A_GROUP:
                continue
            # follow_symlinks=False on purpose: a junction or symlink points at a tree
            # that lives somewhere else, and inventorying it here would report another
            # place's contents as this workspace's.
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            child = Path(entry.path)
            rel = normalize(str(child.relative_to(root)))
            if (child / ".git").exists():
                found.append(rel)
            else:
                stack.append(child)

    kept = tuple(sorted(rel for rel in found if not _repo_matches(rel, exclude)))
    excluded_repos = tuple(sorted(rel for rel in found if _repo_matches(rel, exclude)))
    return RepositoryDiscovery(
        repositories=kept,
        excluded=excluded_repos,
        unreadable_directories=tuple(sorted(unreadable)),
    )


@dataclass(frozen=True, slots=True)
class RepositoryRun:
    """One repository's part of a workspace run, successful or not."""

    repo: str
    root: Path
    ok: bool
    error: str | None = None
    report: Report | None = None
    #: ``own`` when the repository has its own ``.omitnix.yaml``, ``defaults`` otherwise.
    config_source: str = "defaults"
    workspace_excludes_applied: bool = False
    authentication_configured: bool = False
    authorization_configured: bool = False
    excluded_files: int = 0
    pruned_directories: int = 0
    tracked_but_absent: int = 0
    discovery_mode: str = "tracked"
    discovery_note: str = ""
    documents: tuple[Path, ...] = ()
    seconds: float = 0.0

    @property
    def coverage(self) -> Coverage:
        if self.report is None:
            return Coverage(0, 0, 0, 0)
        return self.report.coverage

    def configuration_label(self) -> str:
        base = "own .omitnix.yaml" if self.config_source == "own" else "no configuration"
        if self.workspace_excludes_applied:
            return f"{base} + workspace excludes"
        return f"{base}, workspace excludes off"


@dataclass(frozen=True, slots=True)
class WorkspaceResult:
    root: Path
    runs: tuple[RepositoryRun, ...]
    excluded_repositories: tuple[str, ...]
    unreadable_directories: tuple[str, ...]
    jobs: int
    workspace_excludes_applied: bool
    seconds: float
    tracked_only: bool = True
    out_dir: Path | None = None
    documents: tuple[Path, ...] = ()

    @property
    def succeeded(self) -> tuple[RepositoryRun, ...]:
        return tuple(run for run in self.runs if run.ok)

    @property
    def failed(self) -> tuple[RepositoryRun, ...]:
        return tuple(run for run in self.runs if not run.ok)

    @property
    def coverage(self) -> Coverage:
        """The sum over the repositories that ran.

        Repositories that could not be run contribute nothing here **and are counted
        separately**, never folded in as zeroes. A repository that failed to run has an
        unknown number of files, and calling that number zero is the repository-sized
        version of the mistake this tool exists to prevent.
        """
        return Coverage(
            discovered=sum(run.coverage.discovered for run in self.succeeded),
            analyzed=sum(run.coverage.analyzed for run in self.succeeded),
            unresolved=sum(run.coverage.unresolved for run in self.succeeded),
            unknown=sum(run.coverage.unknown for run in self.succeeded),
        )

    @property
    def unconfigured_authorization(self) -> tuple[RepositoryRun, ...]:
        return tuple(run for run in self.succeeded if not run.authorization_configured)

    def records(self) -> list[dict[str, Any]]:
        """Every analyzed file in the workspace, keyed by :func:`record_id`."""
        rows: list[dict[str, Any]] = []
        for run in self.succeeded:
            assert run.report is not None
            for record in run.report.files:
                rows.append(
                    {
                        "id": record_id(run.repo, record.path),
                        "repo": run.repo,
                        "path": record.path,
                        "adapter": record.adapter,
                        "status": str(record.status),
                    }
                )
        return rows


# --------------------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------------------

#: Built once per process and reused. Loading the grammars is the expensive part, and a
#: worker that rebuilt them per chunk would spend the parallelism on that.
_ADAPTER_SETS: dict[tuple[tuple[str, str], ...], AdapterSet] = {}


def _adapter_set_for(overrides: dict[str, str] | None) -> AdapterSet:
    key = tuple(sorted((overrides or {}).items()))
    cached = _ADAPTER_SETS.get(key)
    if cached is None:
        cached = build_adapter_set(dict(key))
        _ADAPTER_SETS[key] = cached
    return cached


def adapter_search_path() -> tuple[str, ...]:
    """Where this process looks for adapters.

    Sent to the workers so that a caller who extended the search path at run time gets
    the same adapters there. Without it, ``--jobs 2`` would quietly analyze a file with
    fewer adapters than ``--jobs 1`` did, and the difference would show up as an extra
    ``unknown`` rather than as an error.
    """
    return tuple(importlib.import_module("omitnix.adapters").__path__)


def _use_adapter_search_path(entries: tuple[str, ...]) -> None:
    package = importlib.import_module("omitnix.adapters")
    if list(package.__path__) == list(entries):
        return
    package.__path__[:] = list(entries)
    importlib.invalidate_caches()
    _ADAPTER_SETS.clear()


def _analyze_chunk(
    job: tuple[Config, frozenset[str], tuple[str, ...], tuple[str, ...]],
) -> list[FileRecord]:
    """Analyze a slice of one repository's files. Runs in a worker process."""
    config, schema_tables, paths, search_path = job
    _use_adapter_search_path(search_path)
    adapter_set = _adapter_set_for(config.adapters)
    return [analyze_file(rel, adapter_set, config, schema_tables) for rel in paths]


def _chunks(paths: list[str], jobs: int) -> list[tuple[str, ...]]:
    """Split a file list into batches for the workers.

    Two decisions, both from measurement.

    Several batches per worker rather than one each, because the cost of a file is
    dominated by its size and sizes are wildly uneven: in one repository measured here, a
    2.6 MB generated HTML file took 27.3 s while its 132 PHP files averaged 0.7 ms each.
    Equal-sized halves would leave seven workers idle.

    And the batches interleave (``paths[i::n]``) rather than take consecutive slices. The
    file list is sorted by path, so the expensive files sit together -- generated pages
    land in one directory -- and consecutive slices would drop all of them into the same
    batch, which is one worker doing the whole job while the rest finish early.

    Neither changes the result: the records are sorted by path before the report is
    assembled.
    """
    if not paths:
        return []
    count = max(1, min(len(paths), jobs * 8))
    batches = [tuple(paths[index::count]) for index in range(count)]
    return [batch for batch in batches if batch]


def repository_config(
    repo_root: Path,
    *,
    apply_workspace_excludes: bool = True,
    out_dir: Path | None = None,
) -> Config:
    """The configuration one repository is analyzed with in a workspace run.

    The repository's own ``.omitnix.yaml`` is loaded exactly as a single run would load
    it. The workspace defaults are then **added** to its exclusions -- never substituted
    for them, and never applied at all to a repository that said ``exclude_defaults:
    false``, which is a repository asking to be walked as written.
    """
    config = load_config(repo_root)
    extra: tuple[str, ...] = ()
    if apply_workspace_excludes and config.exclude_defaults_kept:
        extra += WORKSPACE_DEFAULT_EXCLUDE
    if out_dir is not None:
        try:
            inside = out_dir.resolve().relative_to(config.root)
        except ValueError:
            pass
        else:
            # The workspace's own output would otherwise be discovered as content of
            # whichever repository it happens to sit in.
            rel = normalize(str(inside))
            extra += (rel, f"{rel}/**")
    if not extra:
        return config
    return replace(config, exclude=config.exclude + extra)


@dataclass(frozen=True, slots=True)
class RepoDiscovery:
    """The files one repository offers a workspace run, and how they were found."""

    files: list[str]
    #: ``tracked`` or ``walked``. Reported per repository: the two answer different
    #: questions, and a page that mixed them without saying so would be comparing a
    #: repository's committed content against another's working directory.
    mode: str
    excluded_files: int = 0
    pruned_directories: int = 0
    #: Tracked by git but not present on disk (deleted, or a submodule gitlink). Counted
    #: rather than dropped: they are files the index says exist.
    tracked_but_absent: int = 0
    note: str = ""


def discover_repository_files(config: Config, *, tracked_only: bool = True) -> RepoDiscovery:
    """What to analyze in one repository during a workspace run.

    The default is what git tracks. A working tree also holds local scratch that is
    ignored on purpose -- one repository measured here keeps 24,436 files under a `tmp/`
    directory of database data directories and browser profiles -- and none of it is the
    repository's content. Committed files are, and they are the same set on every machine.

    The cost of that choice is that a brand new file, not yet added, is invisible here.
    That is the right trade for a survey of many repositories and the wrong one for the
    new-file gate, which is why the gate does not use this and looks at the working tree.

    When git cannot answer, this walks the tree instead and says so. Reporting zero files
    because the question could not be asked would be a repository silently emptied.
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


def _write_documents(report: Report, target_dir: Path) -> tuple[Path, ...]:
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "index.json"
    markdown_path = target_dir / "index.md"
    json_path.write_text(render_json(report), encoding="utf-8", newline="\n")
    markdown_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return (json_path, markdown_path)


def run_repository(
    repo: str,
    repo_root: Path,
    *,
    out_dir: Path | None,
    apply_workspace_excludes: bool,
    executor: ProcessPoolExecutor | None,
    jobs: int,
    write_per_repo: bool,
    write_documents: bool = True,
    tracked_only: bool = True,
) -> RepositoryRun:
    """Analyze one repository. Never raises: a failure is a result, not an exception.

    One repository that cannot be read must not end the survey of the other fifty-one,
    and it must not vanish from it either.
    """
    started = time.perf_counter()
    try:
        config = repository_config(
            repo_root,
            apply_workspace_excludes=apply_workspace_excludes,
            out_dir=out_dir,
        )
    except OmitnixError as exc:
        return RepositoryRun(
            repo=repo,
            root=repo_root,
            ok=False,
            error=str(exc),
            seconds=time.perf_counter() - started,
        )

    common = {
        "repo": repo,
        "root": repo_root,
        "config_source": "own" if config.source_path else "defaults",
        "workspace_excludes_applied": apply_workspace_excludes and config.exclude_defaults_kept,
        "authentication_configured": bool(config.authentication_functions),
        "authorization_configured": bool(config.authorization_functions),
    }

    try:
        discovery = discover_repository_files(config, tracked_only=tracked_only)
        schema_tables: frozenset[str] = frozenset()
        if config.schema_snapshot:
            schema_tables = load_schema_tables(config.root / config.schema_snapshot)

        if executor is None or len(discovery.files) < 2:
            adapter_set = _adapter_set_for(config.adapters)
            records = [
                analyze_file(rel, adapter_set, config, schema_tables)
                for rel in discovery.files
            ]
        else:
            adapter_set = _adapter_set_for(config.adapters)
            search_path = adapter_search_path()
            batches = [
                (config, schema_tables, chunk, search_path)
                for chunk in _chunks(discovery.files, jobs)
            ]
            records = []
            for produced in executor.map(_analyze_chunk, batches):
                records.extend(produced)

        report = assemble_report(config, records, adapter_set, schema_tables)
    except OmitnixError as exc:
        return RepositoryRun(
            **common, ok=False, error=str(exc), seconds=time.perf_counter() - started
        )
    except Exception as exc:  # noqa: BLE001 - one repository must not end the run
        return RepositoryRun(
            **common,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            seconds=time.perf_counter() - started,
        )

    documents: tuple[Path, ...] = ()
    if write_documents:
        if write_per_repo:
            documents = _write_documents(report, config.root / config.output_dir)
        elif out_dir is not None:
            documents = _write_documents(report, out_dir / "repos" / repo)

    return RepositoryRun(
        **common,
        ok=True,
        report=report,
        excluded_files=discovery.excluded_files,
        pruned_directories=discovery.pruned_directories,
        tracked_but_absent=discovery.tracked_but_absent,
        discovery_mode=discovery.mode,
        discovery_note=discovery.note,
        documents=documents,
        seconds=time.perf_counter() - started,
    )


def default_jobs() -> int:
    """How many worker processes a workspace run uses when nothing is asked for.

    Capped rather than unbounded because more workers stop paying: on the machine this
    was measured on (4 physical cores, 8 logical), 12 workers were slower than 8 --
    4.63 s against 4.34 s over the same 29 repositories. The cap also leaves the machine
    usable while a long run is going.
    """
    return max(1, min(8, os.cpu_count() or 1))


def run_workspace(
    root: Path,
    *,
    out_dir: Path | None,
    exclude_repos: tuple[str, ...] = (),
    apply_workspace_excludes: bool = True,
    jobs: int = 1,
    write_per_repo: bool = False,
    write_documents: bool = True,
    tracked_only: bool = True,
    progress=None,
) -> WorkspaceResult:
    """Analyze every repository under ``root`` and return the whole picture."""
    root = root.resolve()
    discovery = discover_repositories(root, exclude_repos)
    started = time.perf_counter()

    runs: list[RepositoryRun] = []
    executor: ProcessPoolExecutor | None = None
    try:
        if jobs > 1:
            executor = ProcessPoolExecutor(max_workers=jobs)
        for position, repo in enumerate(discovery.repositories, start=1):
            if progress is not None:
                progress(position, len(discovery.repositories), repo)
            runs.append(
                run_repository(
                    repo,
                    root / repo,
                    out_dir=out_dir,
                    apply_workspace_excludes=apply_workspace_excludes,
                    executor=executor,
                    jobs=jobs,
                    write_per_repo=write_per_repo,
                    write_documents=write_documents,
                    tracked_only=tracked_only,
                )
            )
    finally:
        if executor is not None:
            executor.shutdown()

    return WorkspaceResult(
        root=root,
        runs=tuple(runs),
        excluded_repositories=discovery.excluded,
        unreadable_directories=discovery.unreadable_directories,
        jobs=jobs,
        workspace_excludes_applied=apply_workspace_excludes,
        seconds=time.perf_counter() - started,
        tracked_only=tracked_only,
        out_dir=out_dir,
    )


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------


def _extension_of(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    dot = name.rfind(".")
    return name[dot:].lower() if dot > 0 else "(no extension)"


def unknown_extensions(run: RepositoryRun) -> dict[str, int]:
    counts: dict[str, int] = {}
    if run.report is None:
        return counts
    for record in run.report.files:
        if record.status is Status.UNKNOWN:
            extension = _extension_of(record.path)
            counts[extension] = counts.get(extension, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _repo_payload(run: RepositoryRun) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "repo": run.repo,
        "status": "ok" if run.ok else "could_not_run",
        "configuration": {
            "source": run.config_source,
            "workspace_excludes_applied": run.workspace_excludes_applied,
        },
        "authentication_functions_configured": run.authentication_configured,
        "authorization_functions_configured": run.authorization_configured,
    }
    if not run.ok:
        payload["error"] = run.error
        return payload

    assert run.report is not None
    payload["commit"] = run.report.generated.commit
    payload["dirty"] = run.report.generated.dirty
    payload["coverage"] = run.coverage.to_json()
    payload["discovery"] = {"mode": run.discovery_mode, "note": run.discovery_note}
    payload["excluded"] = {
        "files": run.excluded_files,
        "pruned_directories": run.pruned_directories,
        "tracked_but_absent": run.tracked_but_absent,
    }
    payload["unknown_extensions"] = unknown_extensions(run)
    # Qualified on both sides: the table belongs to this repository and nowhere else, and
    # the files that touch it are named by their workspace key.
    payload["tables"] = [
        {
            "name": table.name,
            "read_by": [record_id(run.repo, path) for path in table.read_by],
            "written_by": [record_id(run.repo, path) for path in table.written_by],
            "in_schema_snapshot": table.in_schema_snapshot,
        }
        for table in run.report.tables
    ]
    payload["documents"] = [str(path) for path in run.documents]
    return payload


def workspace_payload(result: WorkspaceResult) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "workspace",
        "generated": {
            "tool": TOOL,
            "workspace": result.root.as_posix(),
            "jobs": result.jobs,
            "seconds": round(result.seconds, 3),
            "workspace_excludes_applied": result.workspace_excludes_applied,
            "tracked_files_only": result.tracked_only,
        },
        "repositories": {
            "discovered": len(result.runs) + len(result.excluded_repositories),
            "excluded_by_request": len(result.excluded_repositories),
            "ran": len(result.succeeded),
            "could_not_run": len(result.failed),
            "excluded_names": list(result.excluded_repositories),
            "unreadable_directories": list(result.unreadable_directories),
        },
        "coverage": result.coverage.to_json(),
        "repos": [_repo_payload(run) for run in result.runs],
        "records": result.records(),
    }


def render_workspace_json(result: WorkspaceResult) -> str:
    return (
        json.dumps(workspace_payload(result), indent=2, ensure_ascii=False, sort_keys=False)
        + "\n"
    )


def _cell(text: str) -> str:
    return text.replace("|", r"\|").replace("\n", " ").strip()


def _code(text: str) -> str:
    return f"`{_cell(text)}`"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def render_workspace_markdown(result: WorkspaceResult) -> str:
    coverage = result.coverage
    discovered_repos = len(result.runs) + len(result.excluded_repositories)
    lines: list[str] = ["# omitnix workspace index", ""]
    lines.append(f"Workspace: {result.root.as_posix()}")
    lines.append(
        f"Repositories: {discovered_repos} found, {len(result.excluded_repositories)} "
        f"excluded by request, {len(result.succeeded)} analyzed, "
        f"{len(result.failed)} could not be run"
    )
    lines.append(coverage.headline())
    lines.append("")
    lines.append(
        f"Generated by {TOOL} in {result.seconds:.1f} s with {result.jobs} worker "
        f"process(es). Do not edit by hand."
    )
    lines.append("")

    lines.append("## How to read this document")
    lines.append("")
    lines.append(
        "- A file is named `<repository>/<path>`. The bare path is not a key here: two "
        "repositories commonly hold the same relative path, and a repository together "
        "with a deployment clone of it is the ordinary case."
    )
    lines.append(
        "- **Tables are never merged across repositories.** One system's `orders` and "
        "another system's `orders` are different tables that happen to share a name, and "
        "a single row for both would be a quiet, confident error."
    )
    lines.append(
        "- **not configured** against a repository means no authorization or "
        "authentication function was named for it, so no such check was performed. It is "
        "not a finding that the repository has none."
    )
    lines.append(
        "- The coverage line above sums the repositories that ran. Repositories that "
        "could not be run are counted as their own number and are never folded in as "
        "zeroes."
    )
    lines.append(
        "- `excluded` counts paths this run decided not to look at. Directory trees that "
        "were skipped whole are counted as trees, not as files: nothing walked inside "
        "them, so their file count is not known and is not invented here."
    )
    if result.tracked_only:
        lines.append(
            "- Only files git tracks were analyzed. A file that exists in a working "
            "directory but has never been added is not in any count here. The `found` "
            "column says how each repository was read, because a repository git could "
            "not answer for was walked instead and the two are not the same question."
        )
    else:
        lines.append(
            "- Working directories were walked, so untracked files are included and the "
            "counts describe one machine at one moment rather than the committed content."
        )
    lines.append("")

    lines.append("## Repositories")
    lines.append("")
    if result.succeeded:
        rows = []
        for run in result.succeeded:
            cov = run.coverage
            rows.append(
                [
                    _code(run.repo),
                    run.discovery_mode,
                    _cell(run.configuration_label()),
                    str(cov.discovered),
                    str(cov.analyzed),
                    str(cov.unresolved),
                    str(cov.unknown),
                    f"{run.excluded_files} files, {run.pruned_directories} trees",
                    "configured" if run.authorization_configured else "not configured",
                    f"{run.seconds:.1f}",
                ]
            )
        lines.extend(
            _table(
                [
                    "repository",
                    "found",
                    "configuration",
                    "discovered",
                    "analyzed",
                    "unresolved",
                    "unknown",
                    "excluded",
                    "authz",
                    "seconds",
                ],
                rows,
            )
        )
    else:
        lines.append("No repository was analyzed.")
    lines.append("")

    lines.append(f"## Repositories that could not be run ({len(result.failed)})")
    lines.append("")
    if result.failed:
        lines.append(
            "These are counted above as their own number. Their files are in no total on "
            "this page, and treating them as empty repositories would understate the "
            "workspace by an unknown amount."
        )
        lines.append("")
        lines.extend(
            _table(
                ["repository", "reason"],
                [[_code(run.repo), _cell(run.error or "-")] for run in result.failed],
            )
        )
    else:
        lines.append("Every repository that was not excluded by request ran.")
    lines.append("")

    fell_back = [run for run in result.succeeded if run.discovery_note]
    if fell_back:
        lines.append(f"## Read a different way ({len(fell_back)})")
        lines.append("")
        lines.append(
            "Every other repository above was read from what git tracks. These could not "
            "be, so their working directories were walked instead. Their counts describe "
            "a directory on this machine rather than committed content, and are not "
            "comparable with the rest."
        )
        lines.append("")
        lines.extend(
            _table(
                ["repository", "reason"],
                [[_code(run.repo), _cell(run.discovery_note)] for run in fell_back],
            )
        )
        lines.append("")

    if result.excluded_repositories:
        lines.append(f"## Excluded by request ({len(result.excluded_repositories)})")
        lines.append("")
        lines.append(
            "Named on the command line and not analyzed. Listed because "
            "\"we chose not to look\" and \"there was nothing there\" are different "
            "statements."
        )
        lines.append("")
        for repo in result.excluded_repositories:
            lines.append(f"- {_code(repo)}")
        lines.append("")

    if result.unreadable_directories:
        unreadable = len(result.unreadable_directories)
        lines.append(f"## Directories that could not be listed ({unreadable})")
        lines.append("")
        lines.append(
            "The search for repositories could not open these, so any repository below "
            "them is missing from this page."
        )
        lines.append("")
        for entry in result.unreadable_directories:
            lines.append(f"- {_cell(entry)}")
        lines.append("")

    totals: dict[str, int] = {}
    repos_with: dict[str, set[str]] = {}
    for run in result.succeeded:
        for extension, count in unknown_extensions(run).items():
            totals[extension] = totals.get(extension, 0) + count
            repos_with.setdefault(extension, set()).add(run.repo)
    lines.append(f"## Unknown, by extension ({coverage.unknown} files)")
    lines.append("")
    if totals:
        lines.append(
            "Every file here was discovered and could not be analyzed. Give the "
            "extension an adapter, or exclude it explicitly in the repository's "
            "`.omitnix.yaml`. The run exits non-zero while this section is not empty."
        )
        lines.append("")
        ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
        rows = [
            [_code(extension), str(count), str(len(repos_with[extension]))]
            for extension, count in ordered[:_MAX_LISTED]
        ]
        lines.extend(_table(["extension", "files", "repositories"], rows))
        if len(ordered) > _MAX_LISTED:
            remaining = sum(count for _, count in ordered[_MAX_LISTED:])
            lines.append("")
            lines.append(
                f"{len(ordered) - _MAX_LISTED} further extension(s) account for "
                f"{remaining} more file(s); the full list is in `workspace.json`."
            )
    else:
        lines.append("Every discovered file in every repository that ran was analyzed.")
    lines.append("")

    unconfigured = result.unconfigured_authorization
    lines.append(f"## Authorization not configured ({len(unconfigured)} repositories)")
    lines.append("")
    if unconfigured:
        lines.append(
            "No authorization function is named for these repositories, so **no "
            "authorization check was made in them**. This is a statement about the "
            "configuration, not about the code: nothing here says these repositories "
            "lack authorization. To have them checked, name the function in "
            "`authorization_functions` in each one's `.omitnix.yaml`."
        )
        lines.append("")
        for run in unconfigured:
            lines.append(f"- {_code(run.repo)}")
    else:
        lines.append("Every repository that ran names at least one authorization function.")
    lines.append("")

    lines.append("## Tables, by repository")
    lines.append("")
    lines.append(
        "One row per repository. The reverse index is not merged across repositories, "
        "so this page does not answer \"which files in the workspace touch `orders`\" -- "
        "that question has a different answer in every system that has such a table. Each "
        "repository's own document answers it for that repository."
    )
    lines.append("")
    rows = []
    for run in result.succeeded:
        if run.report is None or not run.report.tables:
            continue
        names = [table.name for table in run.report.tables]
        shown = ", ".join(_code(name) for name in names[:_MAX_LISTED])
        if len(names) > _MAX_LISTED:
            shown += f" (+{len(names) - _MAX_LISTED} more)"
        rows.append([_code(run.repo), str(len(names)), shown])
    if rows:
        lines.extend(_table(["repository", "tables observed", "names"], rows))
    else:
        lines.append("No table was observed in any repository that ran.")
    lines.append("")

    return "\n".join(lines)


def write_workspace_documents(result: WorkspaceResult, out_dir: Path) -> tuple[Path, ...]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "workspace.json"
    markdown_path = out_dir / "workspace.md"
    json_path.write_text(render_workspace_json(result), encoding="utf-8", newline="\n")
    markdown_path.write_text(render_workspace_markdown(result), encoding="utf-8", newline="\n")
    return (json_path, markdown_path)
