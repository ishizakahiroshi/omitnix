# Independent fixed-SHA re-review: #6

Reviewed local commit: `f39363366ddeba076f82c737c10e6234f287397f`.
Reviewed tree: `f2aa5d9fabc3a99737d10082f424c42d523fd0c4`.
Previous reviewed commit: `1b2f0545e01d59c1f5126a7125e58e59f4354efb`.

## Verdict

Approve the local code. R1 and R2 are resolved; no new blocking finding. Final remote-commit/tree equality remains pending and is not implied by this local review. The original review's population coverage and limitations still apply.

## Fix verification

- R1: `_judge` now rejects nonempty `none_observed` payloads, invalid empty/null list forms, unexpected value keys on `not_configured` fields, and empty `value` payloads. The intended canonical empty-list, scalar-null, configured-name, and nonempty observation conversions remain accepted. The original direct reproduction now rejects the contradictory record.
- Independently authored 76 additional field-state controls across all six capabilities passed. Invalid-state controls use otherwise-matching expectations, so rejection cannot be attributed merely to a different literal value. Membership, non-membership and scalar-prefix paths were also exercised.
- All 2,163 prior controlled-index category instances passed again, covering missing records, omitted pairs, wrong modes, all depth boundaries, neutral/qualified extras, forbidden leaks, unknown/unclaimed records, relevant gap reasons, duplicate records, and every claim kind.
- R2: the Rust rs06 source-review sentence now correctly identifies the array on line 2 and SQL on line 3. No fixture/answer edit occurred.
- The only code change since the previous review is the scoped `_judge` validation plus 16 additional repository test cases. Product source and synthetic sources/answers remain identical to the instruction baseline. Regeneration left the checkout clean.

## Fresh execution

Used the independent venv and existing dependency paths from the first review; no install/download or product mutation. Exact first-pass commands and exits are recorded in `commands.json` beside this report; outputs in `check-*.log`.

Passed with exit 0:

- `python rewrite/truth/tools/make_synthetic.py --check`: 189 files up to date.
- `python rewrite/truth/tools/extract_from_tests.py --verify`: 192/192 claims; 111/176 functions extracted.
- `python rewrite/truth/tools/audit_population.py --check`.
- `python -m pytest rewrite/truth/tests -q`: 73 passed.
- `python -m ruff check rewrite/truth/tools rewrite/truth/tests`.
- Two complete scoring commands, including `--from-tests`: byte-identical score JSONs with unchanged SHA-256 `91988addb61a8c6f4195edab83463bc661d9b10183ff62a6d63cbcb3eb8e6fe1`.
- `git diff --check`; `git status --short` was empty.
- `independent_controls.py`: 2,163 category instances and the original R1 rejection.
- `state_controls.py`: 76 additional independent state/value controls.

### Full-suite retry evidence, retained rather than hidden

The first fresh `python -m pytest -q` exited 1: 402 passed, 1 skipped, and the unchanged `test_cost_grows_with_the_page_rather_than_with_its_square` failed with a 4.2x ratio (0.385679 / 0.091927 seconds) against its <3x bound. Neither the test nor product source changed in this patch.

Without edits or weakened assertions:

1. `python -m pytest -q tests/test_adapter_html.py::test_cost_grows_with_the_page_rather_than_with_its_square` exited 0: 1 passed in 1.34 seconds (`timing-retry.log`).
2. `python -m pytest -q` exited 0: 403 passed, 1 skipped in 6.91 seconds (`full-retry.log`).

This is consistent with transient timing variability on the shared runner; it is not a demonstrated scorer regression. Do not summarize it as every invocation passing. The semgrep-specific test remains skipped because semgrep is unavailable.

## Remaining limits

Remote publication equality, Windows behavior, private/rewrite scoring, real benchmarks, semgrep execution, and the original policy/provenance limitations are not established by this review. No expectation weakening, mode reclassification, product edit, or source schema expansion was introduced.
