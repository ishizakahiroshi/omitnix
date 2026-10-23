# Go containment-walk benchmark (blocked, unmeasured)

Status: **draft source only; measurement acceptance is not met**. No Go benchmark
run completed, so no RESULT.txt is included and no timing is claimed. Do not treat
this draft as a completed benchmark or use it in a language-performance ranking.

Only bench-walk/go/ is added on branch bench-walk-go, based exactly on
374e5bb337ec0f7e0f4a47d97c70083a306eb1ed. No omitnix product code is imported or
modified, and build_report is never called by this standalone program.

## Run when the toolchain is available

Requirements: Go 1.23 or newer, Git, a working C compiler, CGO enabled, and access
to the pinned Go modules. From the repository root:

    GOMAXPROCS=1 ./bench-walk/go/run.sh > bench-walk/go/RESULT.txt

If the Go executable has a different path, set GO to that executable. The runner
resolves the native bindings with go mod tidy, attempts the treesitter-tagged
build, and uses one build worker (-p 1). Module/compiler diagnostics go to stderr.
If native binding preparation fails, it builds the standard-library-only fallback;
that program still measures S/N/M and writes parse go BINDING_FAILED as line four.
A missing Go toolchain prevents both builds and is not represented as a successful
fallback run. Git/source failures are real errors, not binding failures.

Successful stdout is exactly four lines:

    walk go S 825 339900 825 <minimum-ms>
    walk go N 4200 421900 200 <minimum-ms>
    walk go M 4000 7998000 4000 <minimum-ms>
    parse go ok <files> <candidates> <comparisons> <remaining> <minimum-ms>

These are format descriptions and required counters, not measured output.
Durations must have one decimal place. Dependency resolution can update go.sum;
the currently checked-in sum file records downloaded module metadata only.

## Exact loop and timing boundary

Generate inputs and sort by start ascending, then end descending, outside timing.
For every candidate, scan the accepted list from the front in insertion order.
Increment comparisons once per full containment predicate:

    outer.start <= candidate.start && candidate.end <= outer.end

Break on the first containing accepted range; append only when none contains it.
There is no reverse scan, accepted-list filtering, pre-check, or alternative
algorithm. Each walk creates its own accepted list.

Warm once, then perform five measured repetitions. Synthetic counts are checked
against the required constants; real-corpus counts from the single warm-up must
match every measured repetition. Report the minimum duration, formatted to one
decimal millisecond. Each per-file timer encloses only walk; parsing, traversal,
Git reads, sorting, counter aggregation, assertions, and printing are excluded.
For benchmark 2, each repetition sums its per-file walk durations and the minimum
of those five totals is reported. Byte ranges from separate files are never mixed.

Synthetic generation:
- S: (i, i+1), i=0..824; required counts 825 / 339900 / 825
- N: i=0..199, outer (i*1000, i*1000+500), twenty inner ranges
  (i*1000+1+j, i*1000+2+j), j=0..19; required counts 4200 / 421900 / 200
- M: (i, i+1), i=0..3999; required counts 4000 / 7998000 / 4000

## Real tree-sitter corpus

Enumerate all 158 tracked paths at the exact base commit with git ls-tree and read
original blobs with git show BASE:path. Parse every file with a supported extension,
including malformed fixtures and files with zero string candidates. Recovery trees
are retained. The source defines seven grammar families covering 110 files:

| Grammar | Extensions and tracked file counts | String node kinds |
| --- | --- | --- |
| Python | .py (67), .pyi (1) | string, concatenated_string |
| PHP | .php (14) | string, encapsed_string, heredoc, nowdoc |
| Go | .go (5) | interpreted_string_literal, raw_string_literal |
| Rust | .rs (8) | string_literal, raw_string_literal |
| JavaScript | .js (2), .mjs (3), .cjs (1); .jsx supported but absent | string, template_string |
| TypeScript / TSX | .ts (1), .tsx (1) | string, template_string |
| HTML | .html (6), .htm (1) | quoted_attribute_value, attribute_value |

Other extensions (48 tracked files) have no selected grammar. Documentation, SQL,
query files, configuration, shell, PowerShell, CSS, Vue, custom fixture formats,
and binary assets are outside this declared coverage. Embedded HTML scripts are
not reparsed as JavaScript. Binary concatenation expressions, macro containers,
and string-content fragments are not added. There is no regex or text fallback.

Pinned modules: go-tree-sitter 0.25.0; Python grammar 0.25.0; PHP 0.24.1; Go 0.25.0;
Rust 0.24.2; JavaScript 0.25.0; TypeScript/TSX 0.23.2; HTML 0.23.2.
The corpus test expects 110 files / 4104 candidates / 334231 comparisons / 3881
remaining from the same pinned-grammar reference corpus. These assertions have
not yet been run in Go and are not reported as Go measurements.

## Verification commands

    cd bench-walk/go
    go mod tidy >&2
    GOMAXPROCS=1 go test -p 1 -tags treesitter -v ./... >&2
    GOMAXPROCS=1 go vet -p 1 -tags treesitter ./... >&2
    GOMAXPROCS=1 go test -p 1 -v ./... >&2
    GOMAXPROCS=1 go vet -p 1 ./... >&2

The tests cover exact synthetic counters, front-first order and early break,
sorting, equality, empty input, per-file isolation, assertion failure, and the
fixed tree-sitter corpus. Product pytest/gate/dogfood are outside this standalone
verification because they may call build_report.

## Actual setup attempts and remaining blocker

The installed /usr/bin/go was an unrelated application. Official Go 1.27.1 for
Linux amd64 was downloaded and its vendor SHA-256 verified:
63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445.
Its version command and gofmt ran, and all requested grammar module sources were
downloaded. GCC 14.2.0 was available. The first dependency/build attempt failed
because the temporary filesystem was full (no space left on device), before any
Go test or benchmark could run.

A separate usable execution context could read this checkout but could not see
that temporary toolchain. Both the official archive at go.dev and the official
proxy.golang.org toolchain module endpoint then failed with CONNECT tunnel failed,
response 403. Those denied download routes were not bypassed.

Next step: supply an accessible official Go toolchain and pinned module cache, or
restore permitted registry access and sufficient temporary storage, then run the
commands above and record the four real output lines. Shared-cloud measurements
must not be presented as a cross-language ranking.
