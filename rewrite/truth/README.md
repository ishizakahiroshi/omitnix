# Truth data for the omitnix rewrites

The Python output is not the answer (Python has defects of its own), so the rewrites are
scored against answers that do not come from running Python. This directory holds the
answers that already exist in the repository: the expectations people wrote by hand in
the adapter tests. Everything here is invented (`tests/fixtures/` is a fictional shop).

## from-tests/

One JSON file per adapter, plus the input files each claim reads (`inputs/<adapter>/`).
A claim is one assertion from a test, read from the test's syntax tree (nothing was run
to produce it): this file, read with this configuration (authentication / authorization
function names, schema tables, files in scope), gives exactly this value (`values`),
exactly this set of unresolved codes (`codes_exactly`), or does / does not report this
code (`code_present` / `code_absent`). Further kinds: `value_contains` /
`value_lacks` / `value_starts_with` (membership, substring or prefix of a capability's
value, e.g. a summary), `detail_contains` / `detail_lacks` (text in the details of the
unresolved items, optionally of one code), `unresolved_empty` and `details_nonempty`.
The exact forms are listed in the docstring of the extractor. A test of the form `a and
b` gives one claim per part; a part that is not a literal (a checkout path) is left out
and the rest kept.
Regenerate: `python rewrite/truth/tools/extract_from_tests.py` (add `--verify` to re-run
every claim on the Python adapters without pytest).

### Counts (2026-10-03, second pass)

Adapter test files: 176 test functions. Extracted: 111 tests, 192 claims, 49 input files
(first pass: 76 tests, 109 claims, 44 input files). Not extracted: 65 tests, each listed
with its reason in the `not_extracted` field of its adapter's JSON.

Claims by kind: values 75, code_present 33, value_contains 27, details_nonempty 15,
detail_contains 14, unresolved_empty 9, value_lacks 6, code_absent 6, value_starts_with 3,
detail_lacks 3, codes_exactly 1.

Not extracted, by reason:

- 29: builds a report through Python objects. The golden cases (`rewrite/golden/`)
  cover the same behaviour at the document level.
- 15: stubs a grammar or checks Python's reason text. Python only.
- 9: declares the adapter's own capabilities (`ADAPTER.capabilities` and the like).
  Python object.
- 6: calls an internal Python helper (`read_sql`, `looks_like_sql`,
  `hides_a_table_reference`) rather than the adapter on a file. Not a claim about a file.
- 3: parametrized; the inputs come from a table in the decorator.
- 1: a timing ratio on generated input (`test_cost_grows_...`), not an expectation about
  a file.
- 1: writes its own input file inside the test (`tmp_path`), so there is no fixture file
  to copy.
- 1: compares two analysis results with each other (the in-scope refusal reads the same
  with and without the file on disk); there is no literal. Not extractable as a claim.

The first pass left 45 tests as "no literal expectation in the supported forms"; that
bucket is now empty. 35 of them became claims (membership checks, summary prefixes,
details that name a file or table, emptiness of the unresolved list, schema-snapshot
codes); the other 10 were re-classified into the specific reasons above.

Caveat: `test_a_reason_never_carries_the_absolute_path_of_the_checkout` also asserts
that the fixture directory's absolute path is absent from the details. That half depends
on the machine, so only the `"..."`-absent half is extracted.
The other test files (`test_cli`, `test_gate`, `test_workspace`, `test_render`,
`test_config`, `test_analyze`, `test_registry`, ...) are not read here. §12 of the spec
says which are covered by golden cases and which are Python-only.

### Python on these claims

192 of 192 pass on the Python adapters. That is expected, not a finding: the same
assertions pass under pytest. It confirms the extraction did not distort them. A claim
Python failed would have meant a bug in the extractor or a test that is not what it says.

## What this is not

These claims are what the author of the tests believed. They are one source of truth, not
the whole: C1's answers for real repositories and C3's synthetic corpus cover what the
tests never asked.
