# omitnix

Static code inventory that **never lets "not analyzed" look like "nothing there"**.

> Status: early development. Eleven language adapters ship (`pip install omitnix[all]`; see
> [Languages](#languages)). A file type none of them claims is reported as `unknown` and named
> in the generated document; whether that also fails the run is opt-in
> (`fail_on_unknown`). This is a personal hobby project; **no support is provided.**

## What it is

`omitnix` walks a codebase and writes one generated document, `.omitnix/index.json`, holding two things:

- a per-file index (summary, authentication, authorization check, tables read, tables written)
- a reverse index from database tables back to the files that touch them

It never connects to a database. Schema information, when used, is read from a JSON snapshot produced by another tool.

There used to be a second, human-readable rendering of the same facts, `.omitnix/index.md`. It was removed (2026-09) once a second tool ([OpenWiki](https://github.com/langchain-ai/openwiki)) started reading `index.json` and writing the readable document itself: two renderers of one set of facts drift out of sync, and on a real repository the flat Markdown table had grown to 3,538 rows that nobody opened. `omitnix` now writes the evidence; the document a person reads is somebody else's job.

## Why it exists

A generated inventory is easy. Keeping it honest is not.

The moment a file is added that the parser does not understand, most tools silently skip it. The row is simply missing, and a missing row reads like "this does not exist" — to a human, and even more so to an AI assistant reading the generated document. The newest code is exactly where the inventory is weakest, and exactly where an unchecked authorization path is most likely to be.

So `omitnix` treats completeness as the product:

```
discovered == analyzed + unresolved + unknown
```

If a discovered file cannot be classified, it is counted as `unknown` and **named, in the coverage line and by path**. Anything the analyzer could not follow (dynamically built SQL, indirect calls beyond one hop) is recorded as `unresolved` with a reason — never as a blank cell.

Whether an `unknown` also **fails** the run is a separate question, and the answer is off by default (`fail_on_unknown: true` turns it on). Making it unconditional was a mistake worth naming: it turned every gap into homework. A repository could only go green by writing, into its configuration, a sentence explaining each thing no adapter claims — and measured on one real repository, 36 of its 52 exclusion entries existed for no other reason. "PNG files are not program source" is not a decision anybody made; it is paperwork the tool demanded. Worse, some gaps are not the repository's to close at all: a grammar that cannot read valid source of a language its own adapter claims is *this tool's* defect, and failing the build over it offers a choice between editing correct code and writing a false reason.

What keeps a gap from hiding is that the document says so. That always holds. Failing the run is a policy on top, and it earns its place only where the person reading the failure has something they can do — which is why the [new-file gate](#the-new-file-gate) stays strict either way.

Every run prints the same coverage line, and `index.json` carries the same numbers plus the commit it was generated from:

```
Coverage: 202/210 analyzed, 8 unresolved, 0 unknown
```

```json
{
  "generated": { "commit": "0123456", "dirty": false, "tool": "omitnix", "partial": false, "tracked_only": true },
  "coverage": { "discovered": 210, "analyzed": 202, "unresolved": 8, "unknown": 0 }
}
```

Most of `generated` is excluded when `--check` compares two runs — see [Usage](#usage) — because the commit and dirty flag differ on every commit for reasons that have nothing to do with whether the inventory is stale. `tracked_only` is the exception: it says which question discovery answered, and two runs that answered different questions must not compare equal (see [What it looks at by default](#what-it-looks-at-by-default)).

And it never says "unused". It says: no static reference was observed by this analyzer at this commit.

### The four states behind every field

Every per-file field — summary, authentication, authorization, tables read, tables written — carries a `state` in `index.json`, and the state is never inferred by a reader from an empty-looking value:

| `state` in `index.json` | what it means | how the field looks |
|---|---|---|
| `out_of_scope` | the field is outside the declared capabilities of the adapter that handled the file. Not a missing value. | `{"state": "out_of_scope"}` — no `value` key at all |
| `none_observed` | the adapter declares this capability and looked, and found nothing at this commit. Never "unused". | `{"state": "none_observed", "value": []}` |
| `value` | an ordinary result, including an empty list the adapter is confident is complete. | `{"state": "value", "value": [...]}` |
| *(not a field state)* | the file itself could not be analyzed at all. `fields` is `{}`, `status` is `"unknown"`, and `unknown_reason` says why. Every such file is counted under `coverage.unknown` and named on stderr; the run still exits 0 unless the repository set `fail_on_unknown`. | top-level `"status": "unknown"` on the file record |

This table used to be spelled out in prose at the top of the generated `index.md`. It moved here when that document was removed: the four states themselves were never Markdown-only — they are `FieldState` values (`omitnix/model.py`) present in `index.json` on every run — only the words explaining them lived in the file that got deleted.

## Example

Configuration lives in the repository being scanned, so nothing project-specific is baked into the tool:

```yaml
# .omitnix.yaml
include:
  - "api/**/*.php"
  - "batch/**/*.php"
exclude:
  - "vendor/**"
  - "node_modules/**"
authorization_functions:
  - apply_visibility_filter
authentication_functions:
  - require_session
schema_snapshot: schema.json
```

The tool itself writes `index.json`; the same facts read as a table like this (fictional schema, and this table is not a file `omitnix` produces — it is here for a human reading this README):

| file | summary | authn | authz | reads | writes | status |
|---|---|---|---|---|---|---|
| `api/orders_list.php` | List orders for the signed-in customer | yes | yes | `orders`, `customers` | — | analyzed |
| `api/orders_export.php` | Export orders as CSV | yes | yes | `orders` | — | unresolved (dynamic_sql) |
| `batch/reindex.py` | Nightly reindex | — | — | `orders` | `search_index` | analyzed |

## Usage

```
omitnix                       # full run; writes .omitnix/index.json
omitnix --all-files           # full run over the whole working tree, not just what git tracks
omitnix --check               # write nothing; fail if the generated document is stale
omitnix --files a.php b.php   # analyze an explicit list, as a pre-commit hook passes it
omitnix --gate --files a.php  # check only the newly added files among them
omitnix --gate --since main   # check what this branch added; the form CI can use
omitnix --print api/x.php     # print one file's record as JSON
omitnix --workspace ~/code    # every git repository under a directory (see below)
```

There is no incremental mode and no cache, and regenerating everything removes the entire
question of whether the output is stale. What that costs depends on the size of the files
rather than on how many there are: parsing dominates, so a repository of ordinary source
files regenerates in well under a second, while one holding a few very large generated
files takes far longer. Measured on this project itself, 2026-09-08: 57 files in 0.5 s.

`--files` reports on that subset and, by default, writes nothing: a partial run must not
overwrite the full index with a slice of it. Pass `--write` if that is what you want.

`--check` compares the inventory, not most of the `generated` block (commit, dirty flag), so it does not fail merely
because the commit moved on. It does compare `generated.tracked_only` — see below.

### What a full run discovers, and why the default changed

A plain `omitnix` discovers what git tracks, the same default a workspace run has always
used (see [Across many repositories](#across-many-repositories)) — not everything a
filesystem walk turns up. `--all-files` asks for the walk instead, on a single repository
exactly as it does inside `--workspace`.

This used to be the other way around: a single-repository run walked the working tree
unconditionally, and `--workspace` was the only mode that asked git. That meant the same
tool answered two different questions depending on which mode was in use, and the
single-repository default was the wrong one. It was found by wiring `omitnix --check` into
one real repository's CI: the committed `.omitnix/index.json` had been generated on a
developer's machine, whose working tree held 66 files git does not track — a generated
file, other tools' scratch directories, stray files nobody meant to commit. A clean CI
checkout of the very same commit has none of them, so a fresh run there discovered 738
files where the index said 803, `--check` reported them as `removed`, and the job failed
for a reason that had nothing to do with the inventory being stale — the index was never
reproducible from the repository at all.

The cost of the tracked-only default is the same one the workspace default already pays: a
brand new file, not yet added, is invisible to a full run. That is the right trade for a
document meant to be regenerated identically from a clean checkout, and the wrong one for
the [new-file gate](#the-new-file-gate), which asks git a different question — "what is new
in the working tree" — and does not use this discovery path at all, which is also why the
gate keeps seeing an untracked file that a full run no longer does.

### Exit codes

| code | meaning |
|---|---|
| 0 | the run finished; anything unreadable was reported rather than hidden |
| 1 | a discovered file is `unknown` **and** `fail_on_unknown` is set |
| 2 | usage, configuration, or adapter-contract error |
| 3 | `--check` found the generated document out of date |
| 4 | `--gate` refused a newly added file |

`--workspace` reuses the same codes across many repositories: 1 when any repository that
ran holds an unknown file, and 2 when a repository could not be run at all. The second
wins when both happen, because a repository nothing could run is a hole of unknown size.

## The new-file gate

A full run asks "was everything analyzed?". `--gate` asks a stricter question about the
files that most need it: **a file being added right now must not arrive without the things
its own adapter is able to report.**

New code is where an inventory is weakest. It has no summary yet, its authorization call is
the one most likely to have been forgotten, and if the parser does not understand it at all,
it enters the index as a hole on the day it is written.

```
$ omitnix --gate
omitnix: gate refused 3 files newly added in the working tree
  orders_purge.flow: no authorization call (adapter 'flow' observed no call to any authorization function listed in authorization_functions)
  theme.unmapped: unknown (no adapter claims '.unmapped')
  undocumented.flow: no summary (adapter 'flow' reports summaries and found none here)
```

**New** means untracked, or staged as an addition — the two ways a file that did not exist
before reaches a review. A tracked file is not new however heavily it was rewritten, and a
rename is not new either. Outside a git working tree the gate reports an error rather than a
pass, because "nothing is new" and "I could not tell" are different answers.

### Ask about a range, not the working tree

The question above only has an answer while the file is still uncommitted, so on its own the
gate runs in a pre-commit hook — and a hook is enabled one machine at a time. A file
committed by somebody who never enabled it is tracked and clean by the time anyone else sees
it, and would never be gated again by anybody. **A gate whose coverage is the union of
everyone's local configuration is not a coverage anyone can state.**

`--since` asks the other question, the one a server can ask:

```
$ omitnix --gate --since origin/main
omitnix: gate refused 1 file added since origin/main
  reports/export.php: no authorization call (adapter 'php' observed no call to any authorization function listed in authorization_functions)
```

It compares against the merge base, so on a branch it means "added by this branch". Run it in
CI against the base of the pull request and every added file is gated, whatever anyone's
machine was configured to do. The hook then does what a hook is good at — telling you before
you push, rather than being the only thing standing there.

If the ref cannot be resolved — a shallow clone is the usual reason — the gate reports an
error and exits non-zero. It never reports that nothing was added, because a green run over
an unexamined push is the failure this exists to prevent, not one to reintroduce. In GitHub
Actions that means `fetch-depth: 0` on the checkout.

**What is required comes from the adapter's capability declaration, never from the file's
language.** An adapter that cannot report an authorization call is never asked for one. This
is what stops the day a stylesheet adapter is added from being the day every new stylesheet
fails the gate for missing a check it could never have had. Only capabilities whose absence
is a defect are required at all: a file that reads no tables is ordinary, not deficient.

`unknown` is the exception, and nothing softens it. A file nothing could classify has no
capability declaration to consult, and admitting it silently is the failure this tool exists
to prevent.

`unresolved` is the opposite case and does **not** refuse the file. It says the analyzer read
the file and could not follow part of it — SQL assembled at run time, a call past one hop —
which is a limit of this tool rather than a defect its author can fix. Refusing on it would
block work nobody can unblock by editing the file, and a gate that cannot be satisfied is a
gate that gets switched off. It is printed as a notice on every run, passing or not:

```
omitnix: not followed: batch/reindex.php: unresolved (dynamic_sql) (the table name is built at run time)
```

### Exemptions

Sometimes a check genuinely does not apply — a public endpoint that is deliberately reachable
without a session. Say so, with a reason:

```yaml
gate_exemptions:
  - paths: ['api/health_check.php']
    skip: [authentication, authorization]
    reason: Public liveness endpoint, deliberately reachable without a session.
```

The reason is a required field, not documentation: an entry without one is a configuration
error, and the reason is printed every time the exemption fires. An exemption nobody can
justify in writing, or that nobody ever sees again, is how a gate quietly stops meaning
anything. Exemptions cannot silence `unknown`, and cannot switch off a check the gate does
not make.

When an existing file trips the gate wrongly, the fix is the rule, not the exemption list.

## Across many repositories

`--workspace DIR` runs every git repository under `DIR` in one command. It is a layer on
top of the single-repository run, not a wider one: each repository is analyzed exactly as
it would be alone, and the workspace identifies and aggregates the results.

```
omitnix --workspace ~/code --dry-run                # list what would run; write nothing
omitnix --workspace ~/code                          # run it; writes ./.omitnix-workspace/
omitnix --workspace ~/code --exclude-repo vendored  # skip a group, and say that you did
```

**Nothing is written into the repositories being scanned.** Everything goes to one output
directory (`--out`, default `./.omitnix-workspace/`): a rollup plus one document per
repository. Most repositories in a workspace belong to somebody else's working day, and
scattering generated files through them is not this tool's business. `--write-per-repo`
asks for that explicitly.

### Three things stop being unique

| | inside one repository | across a workspace |
|---|---|---|
| a file's key | the path relative to the root | `<repository>/<path>` |
| a table's name | the whole point of the reverse index | **never merged** |
| a file's content | not a key | not a key |

The first is not hypothetical. Across the 52 repositories measured here, 937 relative
paths are held by more than one repository — one of them by 22 of them — so keying on the
bare path would have merged 1,063 of 36,958 records into each other, silently. The second
is worse than it looks. One
system's `orders` and another system's `orders` silently sharing a row is a confident,
quiet error, and in the same measurement 133 table names occurred in more than one
repository. So the reverse index stays inside the repository it came from, and the rollup
reports per-repository counts instead of one merged table.

The third is why **there is no content-hash cache**. Two byte-identical files can analyze
to different results: `require __DIR__ . '/queries.php'` resolves to a different file in a
different directory. A cache keyed on content would hand one repository's answer to the
other's file and nothing in the output would show it. Repeated work is answered with
`--jobs`, which is stateless, instead.

### What it looks at by default

The files git tracks, minus build output, dependency trees, prose, declarative data,
binary assets, and keys and certificates. A repository that disagrees writes its own
`.omitnix.yaml`; one that says `exclude_defaults: false` is walked exactly as written and
the workspace adds nothing to it.

"The files git tracks" is not a workspace-only rule — a single-repository run (no
`--workspace` at all) uses the same default; see [What a full run discovers, and why the
default changed](#what-a-full-run-discovers-and-why-the-default-changed). Only the extra
exclusions in this section (build output, prose, declarative data, binary assets) are
workspace-specific; a single repository keeps its own tool defaults (`vendor/`,
`node_modules/`, `dist/`, `.git/`) and whatever `.omitnix.yaml` adds.

The defaults are measured rather than guessed. Across 52 repositories on one machine
(2026-09-08):

| what is targeted | discovered | of which no adapter claims |
|---|---|---|
| working directories, tool defaults only | 139,764 | 96,931 |
| working directories, plus the workspace defaults | 67,838 | 26,408 |
| **tracked files, plus the workspace defaults** (the default) | 36,958 | 1,129 |

The largest single block the extension list could not describe was build output and
vendored dependencies, which is why the defaults lead with directories. The largest block
left after that was one repository's 24,436 ignored scratch files — database data
directories and browser profiles — which is why the default target is what git tracks.
`--all-files` walks the working directories instead.

Every one of those decisions is counted and reported per repository. An exclusion nobody
can see the size of is how a survey quietly stops covering anything.

### Not configured is not a finding

Authorization function names cannot have a default: they differ in every repository. A
repository that names none is reported as **not configured**, listed as such, and said out
loud on every run:

```
omitnix: 52 repositor(y/ies) name no authorization function, so no authorization check
was made in them. This is not a finding that they have none.
```

A repository that could not be run is counted as its own number and never folded in as a
zero. Its files are an unknown quantity, and calling that quantity zero is the
repository-sized version of the mistake this tool exists to prevent.

## Contract checks, and where they stop

The index says what a file does. It cannot say what a file was *required* to do — that a
call must be present, or that a direct access is forbidden. That is semgrep's job, and
[`.semgrep/`](.semgrep/) ships example rules written entirely with fictional names.

**semgrep is never used to build the index.** An index assembled from grep-shaped rules
omits whatever the rules did not anticipate, which is exactly what this tool exists to make
impossible.

The example rules were run against the example files (semgrep 1.176.1, Windows 11,
2026-09-08): every rule fires in `orders_export.php` and none in `orders_list.php`. Note that
**semgrep exits 0 even when it reports findings** — pass `--error` if a finding should fail
the job. `.semgrep/README.md` has the command and the Windows parallelism measurement.

Those rules stop at a real limit. semgrep CE has no cross-file analysis, so for PHP they see
one function at a time:

- *expressible*: "this function does not call the authorization function"
- **not expressible**: "the function it calls actually constrains the query"

The second needs types and a call graph across files. That belongs to **PHPStan custom
rules**, and omitnix deliberately does not attempt it — no wiring for it ships here. If you
need that guarantee, write it there rather than stretching a semgrep rule to imply a check it
cannot perform.

## Languages

Adapters come in three tiers, and **the tier is a declaration, not a limitation quietly
applied**. Each adapter states which columns it can fill; every other column is rendered
`n/a` rather than left blank, so a stylesheet is never shown as a file that was checked for
an authorization call and found to have none.

| tier | adapters | what they report |
|---|---|---|
| full | `php`, `python`, `go`, `tsjs`, `sql` | summary, authn, authz, tables read and written |
| reverse-lookup | `html` | summary, and the addresses the screen requests |
| minimal | `css`, `rust`, `shell`, `powershell`, `vue` | the file exists, and its header comment |

| adapter | extensions | install |
|---|---|---|
| `php` | `.php` `.phtml` | `omitnix[php]` |
| `python` | `.py` `.pyi` | `omitnix[python]` |
| `go` | `.go` | `omitnix[go]` |
| `tsjs` | `.ts` `.tsx` `.js` `.mjs` `.cjs` | `omitnix[tsjs]` |
| `sql` | `.sql` | `omitnix[sql]` |
| `html` | `.html` `.htm` | `omitnix[html]` |
| `css` `rust` `shell` `powershell` `vue` | `.css` `.rs` `.sh` `.ps1` `.vue` | nothing to install |

`tsjs` reports one column the others do not: **screen → API**, the addresses a file requests
through `fetch` or `axios`. `html` reports the same column from form actions, script sources
and the scripts inside the page. That is the direction an inventory is usually read in — *which
screen calls this endpoint* — and it is why HTML is worth an adapter that reports nothing else.

The minimal tier exists because **an extension a repository contains is not free to ignore**.
Every discovered file must be analyzed or explicitly excluded, so a language with no adapter
fails every run until an exclusion is written for it in every repository that has one. `.sh`
appears in 37 of the 52 repositories this was measured against and `.ps1` in 30. Three files
here are cheaper than an exclusion in thirty configurations — and unlike an exclusion, they
leave the file counted.

They also stop where the evidence stops. Rust is minimal because none of the measured Rust
repositories declares a database crate: an extractor for tables would have had nothing to be
tested against. It moves up when there is something real to test it on, not before.

## Writing an adapter

Adding a language means adding files, never editing the core. Drop a module into
`omitnix/adapters/`, expose an instance, and the discovery mechanism finds it:

```python
from omitnix.adapters.base import Adapter, AnalysisRequest, AnalysisResult
from omitnix.model import Capability


class IniAdapter(Adapter):
    name = "ini"
    extensions = (".ini",)
    capabilities = frozenset({Capability.SUMMARY})

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        first = request.text.splitlines()[0] if request.text else ""
        return AnalysisResult(values={Capability.SUMMARY: first.strip("; ")})


ADAPTER = IniAdapter()
```

An adapter declares the capabilities it can produce, and the core asks for nothing else. That
declaration is what keeps a stylesheet from being reported as a file missing an authorization
check: a capability the adapter never claimed is rendered `n/a`, which is a different thing
from `none observed`.

## Development

```
python -m pytest
python -m ruff check .
```

## License

MIT. See [LICENSE](LICENSE).
