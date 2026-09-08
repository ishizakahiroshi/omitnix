# Example contract rules

These are **examples**, shipped so the division of labour is concrete. Copy them, replace
the fictional names with your own, and keep them in your repository — not here.

## The division of labour

| question | answered by |
|---|---|
| What does this file do, and what does it touch? | omitnix (the index) |
| Was every discovered file analyzed? | omitnix (the coverage line, exit 1) |
| Does a newly added file lack what its adapter can report? | omitnix (`--gate`, exit 4) |
| Is a required call missing, or a forbidden one present? | semgrep (these rules) |

**semgrep is never used to build the index.** An index assembled from grep-shaped rules
is an index that quietly omits whatever the rules did not anticipate, which is the exact
failure omitnix exists to make impossible.

## Where this stops

semgrep CE has no cross-file analysis. For PHP these rules see a single function at a
time, so:

- *expressible*: "this function does not call `require_session()`"
- **not expressible**: "the function it calls actually constrains the query"

The second needs types and call graphs across files. That is a job for PHPStan custom
rules, and omitnix deliberately does not attempt it. If you need it, write it there — do
not stretch these rules to fake it, because a rule that appears to check something it
cannot is worse than no rule.

## Running them

```
semgrep --config .semgrep/omitnix-contract.yaml --metrics off .semgrep/examples/
```

`examples/orders_list.php` produces no findings; `examples/orders_export.php` triggers
every rule. Verified with semgrep 1.176.1 on Windows 11 (2026-09-08): 4 rules, 2 files,
4 findings, one per rule, all in `orders_export.php`.

Two things to know before wiring this into CI:

- **semgrep exits 0 even when it finds something.** Pass `--error` if a finding should
  fail the job. Without it a red rule looks like a green build.
- `--metrics off` keeps the run from reporting usage. It is on by default when a rule
  comes from the registry rather than a local file.

### On Windows

semgrep's Windows support is documented as beta, so parallelism was measured rather than
assumed. On a synthetic corpus of 500 PHP files (8 logical cores, semgrep 1.176.1):

| `--jobs` | wall time |
|---|---|
| 1 | 15.37 s |
| 2 | 8.62 s |
| 4 | 8.51 s |
| 8 | 9.07 s |
| default | 8.35 s |

Parallelism works: `--jobs 1` is roughly twice the wall time of anything above it. It
stops paying past two jobs on a corpus this small, where start-up dominates. The `--jobs
4` run reported 2000 findings across 500 scanned files with no errors — four per file, so
the faster runs were not skipping work.

## Names

Everything here is fictional — `orders`, `customers`, `search_index`, `audit_log`,
`require_session`, `apply_visibility_filter`. This is a public repository, and a rule
file is one of the easiest places to leak a real internal function name.
