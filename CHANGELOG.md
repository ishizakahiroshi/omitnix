# Changelog

Notable changes to `omitnix`. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [semantic versioning](https://semver.org/spec/v2.0.0.html).

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
