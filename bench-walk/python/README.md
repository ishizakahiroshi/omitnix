# Python containment-walk benchmark

Standalone benchmark on branch `bench-walk-python`, based on commit
`374e5bb337ec0f7e0f4a47d97c70083a306eb1ed`. Only `bench-walk/python/` is added.
The program does not import omitnix, call `build_report`, regenerate the inventory,
or change product code.

## Run

From the repository root, with Python 3.11+ and the base commit available locally:

```sh
python3 -m venv /tmp/omitnix-bench-python-venv
/tmp/omitnix-bench-python-venv/bin/python -m pip install -r bench-walk/python/requirements.txt >&2
/tmp/omitnix-bench-python-venv/bin/python bench-walk/python/benchmark.py > bench-walk/python/RESULT.txt
```

Run normally, without `-O`/`PYTHONOPTIMIZE`, so counter assertions remain active.
Installation and diagnostics go to stderr. The benchmark writes exactly four
stdout lines: three synthetic rows followed by one parse row. If the native
binding or any required grammar cannot be prepared, the fourth line is exactly
`parse python BINDING_FAILED`; the explanation goes to stderr. Git/source errors
are actual failures, not misreported binding failures. There is no regex fallback.

## Algorithm and measurement

- Generate every input and sort by `(start ascending, end descending)` before timing
- For each candidate, scan accepted ranges from the **front in insertion order**
- Increment the comparison counter once per whole predicate:
  `outer.start <= start and end <= outer.end`
- Break at the first containing range; append only if no range contains it
- Do not reverse, filter, pre-check, binary-search, or otherwise optimize that loop
- Warm once, then run five measured repetitions; assert counters every time
- Report the minimum measured duration in milliseconds with one decimal place
- Time `walk` using `perf_counter_ns`; exclude preparation, sorting, parsing, Git
  reads, printing, counter assertions, and cross-file counter aggregation

Synthetic datasets and asserted `(candidates, comparisons, remaining)`:

| Case | Generated ranges | Expected |
| --- | --- | --- |
| S | `(i, i+1)` for `i=0..824` | `825, 339900, 825` |
| N | For `i=0..199`, outer `(i*1000, i*1000+500)` and 20 inner `(i*1000+1+j, i*1000+2+j)`, `j=0..19` | `4200, 421900, 200` |
| M | `(i, i+1)` for `i=0..3999` | `4000, 7998000, 4000` |

## Real tree-sitter input (benchmark 2)

Enumerate **all 158 tracked paths at the exact base commit** with `git ls-tree`.
Read the original blobs with `git show BASE:path`, not the current worktree. Parse
all 110 files with extensions supported below, including fixtures, `.pyi`, files
with no matching string nodes, and malformed fixtures. Error-recovered trees are
included; files are not discarded just because a tree contains errors.

Coverage uses every tree-sitter grammar family declared in the base repository's
parsing extras. Walk the actual trees and collect these literal-node byte ranges:

| Grammar | Extensions (tracked files) | Captured node kinds |
| --- | --- | --- |
| Python | `.py` (67), `.pyi` (1) | `string`, `concatenated_string` |
| PHP | `.php` (14) | `string`, `encapsed_string`, `heredoc`, `nowdoc` |
| Go | `.go` (5) | `interpreted_string_literal`, `raw_string_literal` |
| Rust | `.rs` (8) | `string_literal`, `raw_string_literal` |
| JavaScript | `.js` (2), `.mjs` (3), `.cjs` (1); `.jsx` supported, absent | `string`, `template_string` |
| TypeScript / TSX | `.ts` (1), `.tsx` (1) | `string`, `template_string` |
| HTML | `.html` (6), `.htm` (1) | `quoted_attribute_value`, `attribute_value` |

The other 48 tracked files have no selected grammar; documentation, SQL, query
files, configuration, shell, PowerShell, CSS, Vue, custom fixture extensions, and
binary assets are outside this declared coverage. HTML embedded script contents
are not reparsed as JavaScript. This measures string-node containment, not the
full omitnix SQL-candidate pipeline: binary concatenation expressions and macro
containers are not added. No fallback text extraction is used.

Sort each file's candidate ranges before measurement and run the identical
`walk` per file, with a new accepted list each time. Byte offsets from different
files are never compared. Each repetition's duration is the sum of its per-file
walk durations; the result reports the minimum total across five repetitions.
The single warm-up supplies expected aggregate counters, asserted by every
measured repetition. With the pinned grammars the fixture check additionally
asserts `110 files / 4104 candidates / 334231 comparisons / 3881 remaining`.

`RESULT.txt` contains the four measured stdout lines only.

## Recorded environment

- CPython 3.12.14
- Linux 6.18.44, x86_64, glibc 2.41, shared cloud execution environment
- tree-sitter 0.26.0
- Python grammar 0.25.0; PHP 0.24.1; Go 0.25.0; Rust 0.24.2;
  TypeScript/TSX 0.23.2; JavaScript 0.25.0; HTML 0.23.2
- CPU model/count could not be determined through `lscpu` in this environment
- Timings are observations of this runtime and shared host, not a cross-language
  ranking; other language implementations may have different parser coverage

## Checks

```sh
/tmp/omitnix-bench-python-venv/bin/python -m unittest discover -s bench-walk/python -p test_benchmark.py >&2
/tmp/omitnix-bench-python-venv/bin/python -m pip install ruff==0.16.2 >&2
/tmp/omitnix-bench-python-venv/bin/python -m ruff check bench-walk/python >&2
```

The standalone tests cover exact S/N/M counters, front-first ordering and early
break, sort order, equality, empty inputs, exactly one warm-up plus five runs,
per-file state isolation, assertion failures, and the fixed parse corpus.
The product pytest/gate/dogfood commands are intentionally not run because they
can call `build_report`, which this task prohibits.
