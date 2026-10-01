# C# accepted-range walk benchmark

**BLOCKED / UNMEASURED: acceptance is not met.** There is deliberately no
`RESULT.txt`. No C# executable, tests, timings, or parser counts were obtained.

## Verified blocker (2026-10-01 UTC)

The cloud runner has no `dotnet`, `csc`, `mcs`, `mono`, or `csi` on PATH.
Standard SDK/runtime locations (/usr/share/dotnet, /usr/lib/mono, /opt/dotnet)
and a bounded search of /usr/local, /opt, /usr/share, and /usr/lib also found
no compiler. Running `./bench-walk/csharp/run.sh` exits 127, emits the compiler
blocker to stderr, and produces **zero stdout bytes**. The runner's existing
network allowlist prevents official toolchain retrieval; no denied route was
retried or bypassed for this task.

No tree-sitter runtime or Python grammar shared library was found in the
standard library inventory either. Native loading and parsing cannot be
executed until a C# runtime is available. The implemented P/Invoke path is
therefore **uncompiled and untested**, not evidence of a successful binding.

## Scope and algorithm

Base commit: `374e5bb337ec0f7e0f4a47d97c70083a306eb1ed`. Branch:
`bench-walk-csharp`. Only `bench-walk/csharp/` is added. This standalone
program never imports omitnix or calls build_report.

Generate all inputs, then sort by start ascending and end descending before
any measurement. For each candidate, scan the accepted List from its FRONT
in insertion order; increment the comparison counter once immediately before
`outer.Start <= current.Start && current.End <= outer.End`. Break on the first
containment. Append only if none contains the candidate. No reverse scan,
filter, index, or alternate containment algorithm is used.

| Input | Generation | Required candidates / comparisons / remaining |
| --- | --- | --- |
| S | (i, i+1), i=0..824 | 825 / 339900 / 825 |
| N | 200 outer (i*1000, i*1000+500), each followed by 20 inner (i*1000+1+j, i*1000+2+j), j=0..19 | 4200 / 421900 / 200 |
| M | (i, i+1), i=0..3999 | 4000 / 7998000 / 4000 |

These are required counter assertions, **not measured results**. Each case
uses one warm-up and five measured walks; only the minimum milliseconds is
printed, invariant-culture with one decimal. Accepted-list allocation and the
walk occur inside the Stopwatch interval. Input generation, sorting, counter
validation, output, and aggregation are outside. Results are consumed and all
six runs must agree; synthetic counters must also match the required values.

## Genuine tree-sitter path and coverage

The C# binding calls tree-sitter's actual C API through P/Invoke. It expects
runtime **0.26.6** and tree-sitter-python grammar **0.25.0** shared libraries.
There is no NuGet dependency, regex substitute, subprocess parser, precomputed
range file, or hardcoded successful parse result.

Sources used to check the ABI:
- [tree-sitter 0.26.6 api.h](https://github.com/tree-sitter/tree-sitter/blob/v0.26.6/lib/include/tree_sitter/api.h)
- [tree-sitter-python 0.25.0](https://github.com/tree-sitter/tree-sitter-python/tree/v0.25.0)

Intended coverage is **every tracked .py and .pyi blob at the fixed base**:
67 .py plus 1 .pyi = 68 files. The other 90 of 158 tracked paths are outside
this grammar's coverage. No files were actually parsed in this environment.
A successful run lists base paths with `git ls-tree -r -z --name-only` and reads
base blobs with `git show`; it cannot include this new benchmark or changed
working-tree files. Capture every `string` and `concatenated_string` AST node
using byte offsets, including nested/equal ranges. Include empty capture sets
and error-recovery trees (including the broken Python fixture).

Each file's candidates are sorted separately. The same Walk function runs
with a new accepted list for each file; byte offsets from distinct files are
never compared. Warm the full corpus once, then make five full repetitions,
summing only the individual file walk intervals and reporting the smallest
sum. Git, native loading, parsing, node traversal, and sorting are excluded.
Counters and file totals are aggregated. Counter mismatches and Git/parse
errors are hard failures; only a native loading, export, image, or ABI failure
produces the permitted fourth line `parse csharp BINDING_FAILED`.

## Reproduce when an SDK is available

Requires a **.NET 8 SDK** (C# 12), Git, and optionally the two native libraries.
The SDK must already include its net8.0 reference packs; NuGet sources are
cleared for this dependency-free build. The script bounds MSBuild to one job,
keeps build diagnostics on stderr, and uses disposable temporary build paths.

```sh
./bench-walk/csharp/run.sh --test
./bench-walk/csharp/run.sh > bench-walk/csharp/RESULT.txt
```

Only retain RESULT.txt if the command exits successfully with exactly four
stdout lines: three walk csharp S/N/M lines and one parse csharp line. A missing
SDK is a failed run, not permission to manufacture the fallback line or times.

For native parsing, obtain the exact official tags above in a scratch directory
on an environment permitted to access those sources, then build shared objects:

```sh
# TS_RUNTIME_SOURCE and TS_PYTHON_SOURCE are checkouts of the exact tags above.
# NATIVE_OUT is an existing scratch output directory.
cc -O3 -fPIC -shared -I "$TS_RUNTIME_SOURCE/lib/src" -I "$TS_RUNTIME_SOURCE/lib/include" \
  "$TS_RUNTIME_SOURCE/lib/src/lib.c" -o "$NATIVE_OUT/libtree-sitter.so"
cc -O3 -fPIC -shared -I "$TS_PYTHON_SOURCE/src" \
  "$TS_PYTHON_SOURCE/src/parser.c" "$TS_PYTHON_SOURCE/src/scanner.c" \
  -o "$NATIVE_OUT/libtree-sitter-python.so"
LD_LIBRARY_PATH="$NATIVE_OUT${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ./bench-walk/csharp/run.sh
```

These native build commands and the success path have **not** been tested here.
Without the native libraries, a working SDK still permits the three synthetic
measurements and an actual native-load attempt before BINDING_FAILED.

## Verification status

- Passed: shell syntax, missing-SDK exit/stdout contract, Git whitespace checks,
  and repository structural secrets scanner for all added files
- Not run: C# compilation, the 11 standalone checks in BenchmarkTests.cs,
  synthetic measurements, native interop/grammar checks, and parse measurements
- Private KB/FAMILY scanner watchlists are unavailable; only structural rules run
- Product tests/gate/dogfood were not invoked because they call build_report

Tests are provided for S/N/M counters, first-contained front scan, sorting,
empty/equal ranges, per-file isolation, exactly one warm-up plus five measured
walks, counter assertion failures, and TSNode ABI layout. They have not passed
until run with a compiler. Any future cloud measurements describe that run only;
shared cloud hardware is not a controlled cross-language ranking.
