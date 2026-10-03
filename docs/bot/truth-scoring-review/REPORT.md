# #6 Truth and scoring audit

Instruction baseline: `1451cae88b7f5f45ebd7077aaf2a880989e47298`.
Product baseline: `de9c498c62a71d075d570f4829a63801eba52810`.
Primary audit: 2026-10-03, Linux, separate work branch from the instruction baseline.
Independent review: first pass completed on local code SHA `1b2f0545e01d59c1f5126a7125e58e59f4354efb`; two findings fixed, exact published-SHA re-review pending.

## Conclusion

The original score was reproducible, but overstated what it proved. This PR fixes
scoring/input defects without changing any synthetic expected answer, moving any
must case to reference, or changing `omitnix/**`. Python remains **114/232 (49.14%)**
on must-set table-presence recall through expected depth 3. This is not a language
selection, product acceptance, or proof of provenance/certainty correctness.

The current index stores flat reads/writes and file-level reason strings. It cannot
prove the source line, direct/resolved/traced certainty, actual call-chain depth,
complete candidate set, or association between a reason and one SQL occurrence.
Those dimensions are now explicitly **not scored**, rather than silently implied
by a presence/honesty score. No invented output schema was imposed on the rewrites.

## Evidence and coverage

`SOURCE_REVIEW.md` was written after reading all source files and before inspecting
answers.json or running Python. `COVERAGE.json` enumerates every item with file,
source hash, source line and expected assertion, plus every extracted claim and
skip. Regenerate the enumeration with `python rewrite/truth/tools/audit_population.py`;
`--check` is non-mutating. The enumeration itself is not an automated correctness verdict.

Primary review population and remainder:

- 126 synthetic cases, 186 files, 937 source lines, 333 expectation items; **all
  reviewed** against sources, including all caller/callee files together. No remaining
  unreviewed synthetic items. Counts are 119 must cases/179 files and 7 reference cases/files.
- All 20 categories: select 16, write 7, DDL 6, comment 9, dynamic table 35, dynamic
  clause 4, escape 3, mixed 2, not-SQL 5, test-SQL 5, unreadable 5, system 1,
  query-builder 2, partial-read 1, dialect 4, unsupported 1, and 5 each at depths 1–4.
- All ten kinds: own 191, via 55, candidate 12, any-table 6, comment 22, not-table 21,
  unreadable 10, text-only 5, system 6, beyond-depth 5. Own occurrences collapse
  to 187 file/mode/table pairs (177 must + 10 reference); 55 via pairs are additional.
- All 192 claims from 111 of 176 adapter test functions reviewed for literal extraction
  fidelity, source context and policy limits. All 11 claim kinds reviewed, not a sample.
- All 65 excluded test functions/reasons inspected at source level. They remain outside
  extraction; there is no claim of equivalent golden-case execution. Of the exclusions,
  29 concern report/core objects, 15 grammar/unknown-reason checks, 9 declarations,
  6 internal helpers, 3 parameterized functions, and 1 each timing, generated fixture,
  and two-result comparison. “Grammar/unknown-reason” is not a claim they are all
  Python-only: parsing refusal/unknown-state behavior is relevant across implementations.
- The 111 extracted functions also contain **11 unrepresented assertions**, explicitly
  enumerated: 3 truthy-unresolved, 4 unknown-reason-is-None, 1 `all(detail.strip())`,
  2 recovered/escaped result comparisons, and 1 absolute-path exclusion. These are
  not covered by the 192 extracted claims; partial extraction is now visible.
- The original 49 directly analyzed input files were read. The fixed package retains
  all 58 public fixture files, with the additional 9 named as `support_inputs`.
  These extra files are context, not nine newly scored claims. Only the missing PHP
  helper has a new source/semantic audit here; the other eight are packaged context,
  not claimed additional product-truth coverage.

## Findings and scoped changes

### F1 — High: unrelated reasons and unknown status counted as honesty

Original `score.py:_unresolved`/`score_synthetic` accepted any nonempty unresolved
list or status `unknown`/`unresolved` for every any-table/unreadable/candidate item.
A `select_star` column warning, `dynamic_endpoint`, blank reason detail, or even
status alone could hide a missing table analysis. Candidate tables in the wrong
mode also passed if every name appeared in either flat list.

Controlled reproduction: a file expecting external table input plus a record with
only `select_star` and no table-name finding passed old honesty. A candidate read
set emitted only as writes also passed. Tests now check correct reasons and each
wrong substitution/status/empty detail. The scorer requires `dynamic_table_name`,
`sql_unreadable`, or `sql_unsupported` with nonblank detail as appropriate, based on
the public reason vocabulary and source meaning. This proves a relevant file-level
reason only. Candidate gap disclosure is separately named; complete candidate
resolution/certainty remains unscored. Unknown files are separately named, not
credited as successfully analyzed SQL gaps.

Original Python honesty was any-table 5/6 and candidates 12/12. Corrected disclosure
is any-table **3/6**, candidate gaps **11/12**, broken SQL **5/5**, dynamic unknowns
**5/5**. These changes expose scoring false confidence, not product regressions.

### F2 — High: neutral names hid wrong modes and invented qualification

Original neutral matching discarded mode and compared arbitrary qualified names by
suffix. A permitted text-only read of orders exempted `write:orders` and
`read:invented.orders`. Neutral matching also preceded the forbidden-table check.
Controlled tests cover text-only, system and beyond-depth in both correct/wrong modes,
qualified extras, candidate modes, and a forbidden/neutral collision.

Neutral matching is now mode/name-pair based. Only catalogue entries retain their
explicit bare-name alias for the public index's normalization convention. Forbidden
names win unless the same table is genuinely required in that file. Neutral pairs
are excluded from precision, not rewarded as true positives; numerator, denominator
and neutral count are emitted. A duplicate table occurrence remains one presence
unit; it does not increase recall. The file-level schema still cannot distinguish
an erroneous commented occurrence of a table also genuinely used in that file.

### F3 — High: unread/omitted fields could pass negative extracted assertions

`_judge` turned absent fields, out-of-scope, unknown or unclaimed records into empty
lists/reason sets. That rewarded not analyzing a file. It also sorted/lowercased
values even though the original assertions compare exact lists and strings.

Now readable records and compatible field states/types are required. Literal
assertions retain order, case and multiplicity. Document `none_observed` scalar
null maps explicitly to the adapter's empty string; explicitly unconfigured auth
names map to the helper's empty list, without treating unconfigured table fields as
observed empty. These are documented representation conversions, not answer edits.
Unsupported kinds fail closed. Duplicate file paths raise an error rather than
last-record-wins. Missing paths, unknowns, absent unknown reasons, unclaimed and
unexpected file records are individually visible.

### F4 — High: missing fixture dependency made the right code mean the wrong gap

The extractor copied only files named directly in analyze() calls. It omitted
`tests/fixtures/php/common/reports.php`, required by `summary.php`. Old from-tests
checked only `indirect_call_depth`, which also describes an absent/out-of-scan include;
97/97 therefore did not establish the intended second-hop behavior.

The extractor now copies the complete public fixture subtree and explicitly lists
support-only files. Regression tests regenerate a summary/helper pair and check the
helper bytes and manifest. Expanded detail assertions require `build_totals_sql` and
`common/reports.php`, distinguishing this context from a missing helper. No private
files or real repository input was copied. Regeneration retains all original 192
claim values unchanged.

### F5 — Medium: 95 exclusions and partially extracted tests obscured coverage

Original scoring checked 97 of 192 claims. All claim kinds and all six capabilities
are now supported, expanding execution to 178 claims. Fourteen configuration-bound
claims remain deliberately skipped: 8 need schema-snapshot setup, 6 exact scan scope.
They are listed individually with source/test/line/config and reason, not counted as
passes. Implementing those setups was left outside this focused scorer repair.

| Claim kind | Population | Original checked | Now checked | Still skipped |
|---|---:|---:|---:|---:|
| values | 75 | 32 | 73 | 2 |
| code_present | 33 | 27 | 27 | 6 |
| value_contains | 27 | 20 | 27 | 0 |
| details_nonempty | 15 | 0 | 15 | 0 |
| detail_contains | 14 | 0 | 10 | 4 |
| unresolved_empty | 9 | 9 | 9 | 0 |
| value_lacks | 6 | 3 | 6 | 0 |
| code_absent | 6 | 5 | 5 | 1 |
| value_starts_with | 3 | 0 | 3 | 0 |
| detail_lacks | 3 | 0 | 2 | 1 |
| codes_exactly | 1 | 1 | 1 | 0 |
| Total | 192 | 97 | 178 | 14 |

The semantics of `details_nonempty` remain the original vacuous `all(...)`: an empty
unresolved list passes that assertion alone. `detail_lacks` can likewise pass an
empty joined text. Separate positive gap claims are needed; neither kind is a full
honesty proof. Detail-code selection still means the first matching reason.

### F6 — Medium: verification failures still exited successfully

Original `extract_from_tests.py --verify` printed failed/error counts but always
returned 0. It now returns 1 when any verification fails or errors. Correct and
failing/error controls exercise this independently of running the real adapter.
Scorer exit 0 continues to mean **execution completed**, not expectations accepted;
the report never treats it as a product pass.

### F7 — High limitation: test fidelity is not the product contract

Source inspection found policy conflicts which were **preserved**, not silently
rewritten or moved between sets:

- `tests/test_php_adapter.py:test_a_second_hop_is_counted_rather_than_followed`
  expects no reads at depth 2. Synthetic chains explicitly require depths 1/2/3.
- `tests/test_adapter_rust.py:test_a_query_builder_call_is_unresolved_and_names_no_table`
  expects no reads/writes for explicit builder identifiers. The synthetic Rust and TS
  builder cases are must cases with a known table. A correct future implementation
  can fail these old assertions while improving product correctness.
- Summary text, detailed reason wording, exact list order, and warning-code policy
  are extraction-contract checks, not independent proof of database semantics.
- Finite loop/dictionary/type candidate classification and closed-corpus call-site
  tracing are package conventions. Python Literal annotations are not runtime
  enforcement; public callees can receive outside callers. Keep this static closed-
  corpus policy explicit rather than presenting it as a runtime guarantee.
- The 7 reference cases remain separate: MERGE (Go/PHP), arbitrary appended PHP
  clause, foreign-key target policy, Python UPDATE FROM, SQL procedure delimiters and
  SQL hash-comment dialect. Foreign-key reference currently requires only the CREATE
  target; it does not settle whether REFERENCES orders is a read. No policy was decided
  from whichever answer Python happened to emit.

## Final executable evidence

`EXECUTION.md` records exact commands, exit codes, versions and output. Scores were
written outside the repository and compared byte-for-byte. Required checks:

- make_synthetic --check: 189 generated files up to date; no answer/source changes.
- extract_from_tests --verify: 192/192 extracted assertions match Python; original
  expected values unchanged. This is extraction fidelity, not product acceptance.
- score.py twice: 178/178 applicable assertions; 14 explicit skips, deterministic JSON.
- python -m pytest: **403 passed, 1 skipped** of 404 collected. The skip is
  `test_the_rules_fire_on_the_violating_example_only`: semgrep is not installed.
- focused tests: **73 passed**; required ruff: passed. Full-repository ruff also passed.
- Initial hand-authored regression run against the original scorer: **36 failed,
  11 passed** (47 tests). This includes incorrect scoring and missing diagnostics.
  Additional regression cases were added after that baseline; they are not falsely
  claimed to have been part of the original failing run.

Must-set depth presence: d0 **110/177**, d1 **4/30**, d2 **0/15**, d3 **0/10**.
Cumulative <=3 **114/232**, precision **114/117 = 97.44%**, 11 neutral reported pairs,
3 false positives, zero commented/CTE name leaks. Reference: **4/10** recall,
**4/4** precision over 7 files. Five depth-4 entry expectations remain outside required
recall. Missing/unknown/unclaimed synthetic files: **0/0/0**. These low recall numbers
are product findings for the local owner; they were not fixed by editing product code.

## Constraints and remaining ownership

Python 3.12.14; isolated editable `[dev]` install with no package cache, plus ruff.
Venv 72 MB, checkout approximately 6 MB during work; disk started at 6.3 GB free and
was 6.0 GB free after tests (shared with other tasks). No large builds or real benchmarks.
Shell push lacked credentials; publication uses the already-authorized GitHub connector.
No credentials, external AI agents, private inputs, five-language rewrites, other PRs,
merge, release or deployment were used.

Independent review is required against the exact published SHA, including re-review
of any code changes. Windows behavior, local implementations/private inputs, schema-
scope skipped claims, semgrep-specific test, line/certainty/provenance scoring and the
policy disputes above remain explicit limitations/local-owner work. This PR is Draft.

## Independent first-pass findings addressed

The separate reviewer inspected the complete source/answer and extraction populations
and ran 2,163 controlled category instances, confirming the main results. Its report
is preserved in INDEPENDENT_REVIEW.md. R1 (medium) found contradictory observation
states could still pass a literal claim; state/value compatibility is now checked
before conversion. `none_observed` requires an empty list or documented scalar null,
`not_configured` must omit its value key, and `value` must have a nonempty correctly
typed value. Sixteen positive/negative controls preserve legitimate conversions.
R2 (low) corrected the rs06 source-review sentence: array line 2, SQL line 3. No
fixture or expected answer changed. Required commands passed again; the score hash
is unchanged. Independent re-review of the exact publication remains pending.
