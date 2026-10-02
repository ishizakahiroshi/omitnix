# Golden cases for the omitnix rewrites

A rewrite of omitnix in another language is accepted by one test: given the same
repository, it must do what the Python version does. This directory is that test, kept
independent of any language.

There are 72 cases. Each is a small repository (or a directory of repositories), the
arguments to run with, and what the Python version produced: the exit status, standard
output, standard error and every document it wrote. Everything in here is invented. The
code under `cases/*/input/` comes from `tests/fixtures/` (an invented service with orders,
customers, a search index and an audit log) or is written in `rewrite/tools/make_cases.py`.
A case that needs a real repository to make its point does not belong here.

## Run it

```sh
python rewrite/tools/run_golden.py --cmd "<your command>"
python rewrite/tools/run_golden.py --cmd "python -m omitnix"      # the reference: 72/72
python rewrite/tools/run_golden.py --cmd ./target/release/omitnix --cases c01_php,g02_gate_refuses
python rewrite/tools/run_golden.py --list
```

`--cmd` is anything that behaves like `omitnix`. The harness appends the arguments of the
case, so the command must accept `--root DIR` (and `--workspace DIR --out DIR` for the `w*`
cases). It needs `git` on the PATH: most cases are git working trees, built fresh in a
temporary directory (`git init`, add everything, one commit tagged `base`).

A failed case prints what differs and never the content of a document: counts per category
(`files.changed:status: 1`, `tables.missing: 2`, `format: 1` ...). Add `--show-details` to
see the paths behind a category and a diff of a stream. The golden data is invented, so
that is safe here. Do not use `--show-details` with `compare_index.py` on a real private
repository.

To compare two documents directly: `python rewrite/tools/compare_index.py EXPECTED ACTUAL`
(exit 0 same, 1 different, 2 unreadable).

## What is compared

For every case: the exit status; standard output and standard error, line for line, after
machine paths are replaced by `<ROOT>` and `<OUT>` and backslashes after them by `/`
(`case.json` can narrow this with `"streams"`); and each document listed in `artifacts`,
by `compare_index.py`, which ignores only `generated.commit`, `generated.dirty` and
`generated.tool` (and in a workspace document the time, the job count, the workspace path
and the written document paths). Everything else must be equal: counts, the order of the
files and tables, the order of the keys, and how the file is written (two-space indent, no
ASCII escaping, a trailing newline, LF line ends).

Standard error is part of the contract **where the Python version writes its own
sentence**: a gate refusal, a configuration error, the coverage notes. It is not where the
argument parser writes the sentence (`--help`, an unknown flag): those cases compare the
exit status only.

## Layout

```
cases/<name>/case.json      what to run (see below)
cases/<name>/input/         the repository, or the directory of repositories
cases/<name>/overlay/       files added after the base commit (gate and discovery cases)
cases/<name>/expected/      what the Python version did: result.json (exit status),
                            stdout.txt, stderr.txt, and the documents
data/                       tables to carry, written out of the Python version
```

`case.json`: `mode` (`repo` or `workspace`), `args` (`{ROOT}` and `{OUT}` are replaced),
`git` (the directories to make into repositories; `[]` for none; default: the root in
`repo` mode), `fake_repositories` (an empty `.git` directory, which is a working tree
with no history), `steps` (`overlay` with `stage` or `commit`; `run` for a preparation run
of the command itself, so that a `--check` case has a document to check), `artifacts`
(`actual` and `expected` paths), `absent` (paths that must not exist afterwards) and
`streams`.

## Case groups

`c01`..`c13` one adapter at a time and everything together. `c14`..`c22` configuration
(valid and invalid) and the include and exclude patterns. `c23`..`c26` discovery: the
tracked set against a walk, no git at all. `c27`..`c41` partial runs, `--print` and
`--check`. `c42`..`c50` usage errors. `g01`..`g11` the new-file gate. `w01`..`w11`
workspace mode.

## `data/`

Written by `make_cases.py` out of the Python version, so that a rewrite does not type them
by hand and cannot drift from them: `default_exclude.txt`, `workspace_default_exclude.txt`,
`adapters.json` (name, extensions and capabilities of each adapter), `reason_codes.json`.

## What the cases do not cover

See "What the golden cases do not cover" in the specification
(`docs/local/reference_omitnix-rewrite-spec.md`): the deployment survey (`--status`), the
parts of the glob language no case reaches, the messages that name a Python exception
class, and tree-sitter behaviour on files the fixtures do not contain.

## Changing a case

Only the reference may change `expected/`. Edit `rewrite/tools/make_cases.py`, run it, then
`run_golden.py --cmd "python -m omitnix" --record`, and read the diff of `expected/` before
committing. A change to `expected/` is a change to the contract: it needs a reason in the
commit message, and every rewrite is re-checked against it.
