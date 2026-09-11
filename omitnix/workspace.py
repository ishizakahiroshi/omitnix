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

from .analyze import TOOL, analyze_file, assemble_report, build_report
from .config import Config, load_config
from .errors import OmitnixError
from .gitmeta import last_commit_date_for, main_worktree_of
from .globs import glob_match, normalize
from .model import Coverage, FileRecord, Report
from .registry import AdapterSet, build_adapter_set
from .render import payload_for_check, render_json, to_payload
from .scan import RepoDiscovery, discover_repository_files
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
#: Since 2026-09-11 they are kept for size, not to keep a run green: a file no adapter
#: claims is ``unclaimed`` and fails nothing, so a repository is free to delete the
#: equivalent lines from its own configuration -- this repository did. What does not
#: survive deletion here is the scale. Discovering the other 96,926 files across 52
#: repositories would put a record for each of them in the workspace document, which is a
#: different kind of unusable from the one the exclusions were written for.
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
            unclaimed=sum(run.coverage.unclaimed for run in self.succeeded),
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
    job: tuple[Config, frozenset[str], tuple[str, ...], tuple[str, ...], frozenset[str]],
) -> list[FileRecord]:
    """Analyze a slice of one repository's files. Runs in a worker process."""
    config, schema_tables, paths, search_path, in_scope = job
    _use_adapter_search_path(search_path)
    adapter_set = _adapter_set_for(config.adapters)
    return [analyze_file(rel, adapter_set, config, schema_tables, in_scope) for rel in paths]


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


def _write_documents(report: Report, target_dir: Path) -> tuple[Path, ...]:
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "index.json"
    json_path.write_text(render_json(report), encoding="utf-8", newline="\n")
    return (json_path,)


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
        discovery: RepoDiscovery = discover_repository_files(config, tracked_only=tracked_only)
        schema_tables: frozenset[str] = frozenset()
        if config.schema_snapshot:
            schema_tables = load_schema_tables(config.root / config.schema_snapshot)

        # Every worker is held to the whole repository's selection, not to its own slice.
        # A batch is a scheduling detail; what an adapter may reach is not.
        in_scope = frozenset(discovery.files)

        if executor is None or len(discovery.files) < 2:
            adapter_set = _adapter_set_for(config.adapters)
            records = [
                analyze_file(rel, adapter_set, config, schema_tables, in_scope)
                for rel in discovery.files
            ]
        else:
            adapter_set = _adapter_set_for(config.adapters)
            search_path = adapter_search_path()
            batches = [
                (config, schema_tables, chunk, search_path, in_scope)
                for chunk in _chunks(discovery.files, jobs)
            ]
            records = []
            for produced in executor.map(_analyze_chunk, batches):
                records.extend(produced)

        report = assemble_report(
            config,
            records,
            adapter_set,
            schema_tables,
            tracked_only=tracked_only,
            discovery_note=discovery.note,
        )
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


def unclaimed_extensions(run: RepositoryRun) -> dict[str, int]:
    """How many files no adapter claims in this repository, by extension.

    Delegates to :attr:`omitnix.model.Report.unclaimed_extensions` rather than counting
    again here: a workspace run must group files exactly the way the single-repository run
    it wraps does, or the same repository reports two different shapes depending on which
    command was typed.
    """
    if run.report is None:
        return {}
    return run.report.unclaimed_extensions


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
    # The two halves of "not analyzed", in the two forms they are acted on: an extension
    # nothing claims is a count, a file an adapter could not read is a name and a reason.
    payload["unclaimed_extensions"] = unclaimed_extensions(run)
    payload["unknown_files"] = [
        {"id": record_id(run.repo, record.path), "reason": record.reason}
        for record in run.report.unknown_files
    ]
    # Qualified on both sides: the table belongs to this repository and nowhere else, and
    # the files that touch it are named by their workspace key.
    payload["tables"] = [
        {
            "name": table.name,
            "read_by": [record_id(run.repo, path) for path in table.read_by],
            "written_by": [record_id(run.repo, path) for path in table.written_by],
            "in_schema_snapshot": table.in_schema_snapshot,
            "unresolved_in": [record_id(run.repo, path) for path in table.unresolved_in],
        }
        for table in run.report.tables
    ]
    payload["table_gaps"] = {
        "files": [record_id(run.repo, path) for path in run.report.table_gaps.files],
        "unresolved_count": run.report.table_gaps.unresolved_count,
        "note": run.report.table_gaps.note,
    }
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


def write_workspace_documents(result: WorkspaceResult, out_dir: Path) -> tuple[Path, ...]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "workspace.json"
    json_path.write_text(render_workspace_json(result), encoding="utf-8", newline="\n")
    return (json_path,)


# --- Deployment survey -------------------------------------------------------
#
# A different question from "analyze these repositories": **where is this tool actually
# deployed, and has what it produced gone stale.** A committed index that nobody
# regenerates is worse than no index, because a reader takes it for the current state.
#
# This is deliberately part of omitnix rather than a separate script. The answer has to
# be available wherever the tool is installed -- a shell script for one operating system
# would simply not exist for everyone else who runs it.


@dataclass(frozen=True, slots=True)
class DeploymentStatus:
    """What one repository looks like from the point of view of this tool's output."""

    repo: str
    root: Path
    #: ``absent`` / ``current`` / ``stale`` / ``unreadable``
    state: str
    #: Date (YYYY-MM-DD) of the last commit that touched the index, when it is committed.
    applied: str | None = None
    #: Which of CLAUDE.md / AGENTS.md name the index. An index nobody is told to read is
    #: found by luck, and luck is not a property worth reporting as coverage.
    pointed_at_by: tuple[str, ...] = ()
    #: Set when this working tree is a linked worktree; the path of the main one.
    main_worktree: Path | None = None
    coverage: Coverage | None = None
    detail: str = ""

    @property
    def has_index(self) -> bool:
        return self.state != "absent"

    @property
    def is_worktree(self) -> bool:
        return self.main_worktree is not None


_POINTER_FILES = ("CLAUDE.md", "AGENTS.md")
_POINTER_NEEDLE = "omitnix/index.json"


def _pointer_files(repo_root: Path) -> tuple[str, ...]:
    found: list[str] = []
    for name in _POINTER_FILES:
        path = repo_root / name
        try:
            if path.is_file() and _POINTER_NEEDLE in path.read_text(
                encoding="utf-8", errors="replace"
            ):
                found.append(name)
        except OSError:
            continue
    return tuple(found)


def survey_repository(
    repo: str,
    repo_root: Path,
    *,
    tracked_only: bool = True,
) -> DeploymentStatus:
    """Report one repository's deployment state without writing anything.

    A repository with no committed index is reported as ``absent`` and is **not**
    analyzed: this survey answers where the tool is deployed, and running it everywhere
    to discover that it is not deployed would cost the whole workspace to learn nothing.

    **The comparison is made as a single-repository run, never with the workspace
    exclusions applied.** The committed index was produced by running the tool inside
    that repository, so anything else is a comparison against a document nobody ever
    generated -- and it reports every repository as out of date, which is the one answer
    a freshness survey must not get wrong. (Measured 2026-09-11: with the workspace
    exclusions on, three repositories whose ``--check`` exits 0 were all reported stale.)
    """
    main_tree = main_worktree_of(repo_root)
    pointers = _pointer_files(repo_root)

    try:
        config = repository_config(
            repo_root,
            apply_workspace_excludes=False,
            out_dir=None,
        )
    except OmitnixError as exc:
        return DeploymentStatus(
            repo=repo,
            root=repo_root,
            state="unreadable",
            pointed_at_by=pointers,
            main_worktree=main_tree,
            detail=str(exc),
        )

    json_path = config.json_path
    if not json_path.is_file():
        return DeploymentStatus(
            repo=repo,
            root=repo_root,
            state="absent",
            pointed_at_by=pointers,
            main_worktree=main_tree,
        )

    applied = last_commit_date_for(repo_root, ".omitnix/index.json")

    # build_report, not run_repository. The workspace runner caches adapter sets and
    # can be handed a different adapter search path, so reusing it compares the stored
    # document against a run that is *nearly* the single-repository one -- and "nearly"
    # shows up as a false "out of date". Calling what a single run calls makes the two
    # identical by construction rather than by coincidence.
    try:
        report = build_report(config, tracked_only=tracked_only)
    except OmitnixError as exc:
        return DeploymentStatus(
            repo=repo,
            root=repo_root,
            state="unreadable",
            applied=applied,
            pointed_at_by=pointers,
            main_worktree=main_tree,
            detail=str(exc),
        )

    # The only honest staleness test is the one --check performs: generate afresh and
    # compare. The index records the commit it was generated at, and comparing that to
    # HEAD looks tempting and is wrong -- the document is written before it is committed,
    # so a correctly maintained index always names the previous commit.
    try:
        stored = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return DeploymentStatus(
            repo=repo,
            root=repo_root,
            state="unreadable",
            applied=applied,
            pointed_at_by=pointers,
            main_worktree=main_tree,
            coverage=report.coverage,
            detail=f"{json_path.name} could not be read: {exc}",
        )

    fresh = payload_for_check(to_payload(report))
    state = "current" if payload_for_check(stored) == fresh else "stale"
    return DeploymentStatus(
        repo=repo,
        root=repo_root,
        state=state,
        applied=applied,
        pointed_at_by=pointers,
        main_worktree=main_tree,
        coverage=report.coverage,
    )


def survey_workspace(
    root: Path,
    *,
    exclude_repos: tuple[str, ...] = (),
    tracked_only: bool = True,
    progress=None,
) -> tuple[DeploymentStatus, ...]:
    """Survey every repository under ``root``. Writes nothing, anywhere."""
    root = root.resolve()
    discovery = discover_repositories(root, exclude_repos)
    statuses: list[DeploymentStatus] = []
    total = len(discovery.repositories)
    for position, repo in enumerate(discovery.repositories, start=1):
        if progress is not None:
            progress(position, total, repo)
        statuses.append(
            survey_repository(
                repo,
                root / repo,
                tracked_only=tracked_only,
            )
        )
    return tuple(statuses)
