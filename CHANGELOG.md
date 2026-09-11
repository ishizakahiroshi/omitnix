# Changelog

Notable changes to `omitnix`. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [semantic versioning](https://semver.org/spec/v2.0.0.html).

## 0.1.2 — 2026-09-11

### Added

- `omitnix --workspace <dir> --status` answers a question the tool could not answer about
  itself: **which repositories under a directory carry a committed index, and has any of
  them gone stale.** It reads what is there and writes nothing. Each repository is
  reported as `current`, `stale`, `unreadable`, or `absent`, together with the date of
  the commit that last touched the index, the coverage the document claims, and which
  instruction files (`CLAUDE.md`, `AGENTS.md`) actually name `omitnix/index.json` — an
  index nobody is told to read is a different problem from one that is out of date. The
  command exits 3 when any index is stale or could not be read.
  - A repository with no index is **listed as absent**, not omitted. A survey that leaves
    it out reads as "not looked at" rather than "nothing there".
  - A linked worktree is named as one, with the main worktree it belongs to, so the same
    repository checked out twice is not counted as two deployments.
  - The comparison reproduces the **single-repository run** that produced the committed
    document, not a wider workspace run. Applying the workspace exclusions to the
    comparison reported three repositories as out of date whose `--check` exits 0; a
    survey that calls a current index stale teaches the reader to ignore it, and then the
    one real staleness is ignored too.

### Fixed

- The guard on the HTML adapter's cost took one reading of each page size, and one
  reading on a shared runner is an upper bound of unknown looseness rather than a
  measurement. Measured over twelve attempts on one machine, the ratio of the two sizes
  landed anywhere between 1.6 and 2.8 against a limit of 3, and a macOS runner read 3.1
  and failed while the adapter was untouched. Each size is now the fastest of several
  runs. This does not weaken the guard: a query whose cost grows with the square of the
  page is slower in every attempt, not in an unlucky one, and a control that really is
  quadratic still reads 3.6 and fails.

## 0.1.1 — 2026-09-11

### Changed

- A reason for a dependency that is not installed now names the packaging extra rather
  than the distribution that failed to import: `pip install "omitnix[python]"` instead of
  `pip install tree-sitter`. Both were accurate, but the distribution name only fixes one
  of the three things the extra installs, so a reader who followed it was told about the
  next missing piece on the next run. The hint an HTML file gives names `omitnix[html]`
  even when the part that could not be read was an inline script, because that is the
  extra that makes the file the reader ran on readable.

## 0.1.0 — 2026-09-11

First published release. Everything below is what the initial version does, not what
changed since a previous one.

### Added

- A per-file index and a table reverse index, written to `.omitnix/index.json`, carrying
  the commit they were generated from and the coverage of the run.
- The completeness invariant `discovered == analyzed + unresolved + unknown + unclaimed`,
  checked on every run. A file an adapter claims and cannot read is `unknown` and named by
  path; a file no adapter claims is `unclaimed` and counted by extension; anything the
  analyzer could not follow is recorded as `unresolved` with a reason rather than left
  blank. All four are counted, and every file is in the document by name.
- Eleven language adapters in three tiers: `php`, `python`, `go`, `tsjs` and `sql` report
  summary, authentication, authorization and the tables read and written; `html` reports
  the addresses a page requests; `css`, `rust`, `shell`, `powershell` and `vue` report
  that the file exists and what its header comment says.
- A new-file gate (`--gate`) that refuses a file added without the fields its adapter's
  tier can supply, and `--since` to ask which files a commit range added.
- A workspace mode (`--workspace`) that runs across many repositories in parallel without
  merging their indexes.
- `--check`, which writes nothing and fails when the committed index no longer matches a
  fresh run, or when the run left a hole.
- Optional dependency extras per language, so the core installs without a compiler
  toolchain. A missing grammar reports its files as `unknown` rather than skipping them.

### Notes

- Whether an `unknown` fails the run is opt-in (`fail_on_unknown`); an `unclaimed` file
  never fails one. The new-file gate refuses an `unknown` either way, and notes an
  `unclaimed` file without refusing it.
- The tool never connects to a database. Schema information, where used, is read from a
  JSON snapshot produced by another tool.
