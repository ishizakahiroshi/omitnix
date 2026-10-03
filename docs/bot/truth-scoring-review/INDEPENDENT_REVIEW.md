# Independent review: task #6

Reviewed code commit: `1b2f0545e01d59c1f5126a7125e58e59f4354efb`.
Reviewed tree: `58e7b6c560061dfb8e7523950007ecde168100ed`.
Instruction baseline: `1451cae88b7f5f45ebd7077aaf2a880989e47298`.
Reviewer is separate from the primary audit/fix author. Review performed locally on Linux; no publication, remote mutation, private input, other rewrite, or product edit was performed.

## Verdict

Two scoped corrections requested before final approval: one field-state scoring gap and one inaccurate source-review sentence. The principal fixes, unchanged expectations, coverage denominator, and executable evidence otherwise checked out. Re-review the final fixed code SHA and verify published-tree equality; this review does not attest to a remote SHA.

## Findings

### R1 — P2 / Medium: contradictory field states still pass literal claims

Location: `rewrite/truth/tools/score.py:341–353` (also the configured-name conversion at 336–340).

`_judge` admits both `value` and `none_observed`, then evaluates their payload identically. An analyzed record whose reads field is `{"state":"none_observed","value":["orders"]}` passes a `values / READS / ["orders"]` claim. The public field-state contract says `none_observed` means nothing was observed (`omitnix/model.py:FieldState`); the source normalization uses it only for empty observations (`omitnix/analyze.py:81–117`). A contradictory record therefore receives a literal-fidelity pass, despite REPORT.md saying compatible field states/types are required. The synthetic path interprets the same field as no reported table, making the two paths inconsistent.

Reproduction: run the independent controls script included with this review. Its final line on the reviewed SHA is `Contradictory none_observed + nonempty reads accepted: True`.

Requested fix: validate state/value compatibility before adapting the document value. A `none_observed` list must be empty; a `none_observed` scalar must be the documented empty representation. Likewise, a `not_configured` field must not conceal a nonempty payload during conversion to the helper's empty list. Keep intended empty/null conversions and all answer values unchanged. Add positive valid controls and negative contradictory-state controls for list, scalar, and configured-name fields. This is scoped scorer validation, not a product/schema rewrite.

Impact: a rewrite with incorrect observation-state serialization can receive passing extracted-claim scores. This is additional to, and does not negate, the documented distinction between assertion fidelity and product correctness.

### R2 — P3 / Low: source-first review misidentifies Rust fixture lines

Location: `docs/bot/truth-scoring-review/SOURCE_REVIEW.md:57–59`.

The text says rs06 candidate line 3 identifies the literal array declaration and SQL execution is line 4. `nl -ba rewrite/truth/synthetic/corpus/rust/rs06_array_loop/a.rs` shows the array on line 2 and SQL on line 3. The expected answer's line 3 is already correct. Correct the explanatory sentence; do not change the fixture or expectation.

## Independently verified coverage and invariants

- Read all 186 synthetic source files before inspecting the answer items; then compared all 333 items, across all 126 cases, 20 categories, 10 kinds, and the five call-chain families. No unreviewed synthetic source/answer items remain.
- The static conventions are preserved: literal/resolved/traced evidence, finite candidate sets, external-input unknowns, comments/CTE aliases, mode-sensitive neutrality, text-only/system evidence, and explicit reference policies. The seven reference cases are unchanged. No new answer weakening is justified.
- Read the public fixture inputs before adapter assertions; reviewed all 192 extracted claims in all 111 extracted functions, the 65 excluded test functions, and 11 unrepresented assertions in partially extracted functions. All eight adapter claim documents retain byte-equivalent parsed claim values from the instruction baseline.
- All 58 packaged inputs are byte-identical to their public fixture sources: 49 directly claimed files and 9 named support files. PHP `summary.php` now includes the required `common/reports.php` context.
- Enumerated denominators match: original 97 checked + 95 skips; current 178 checked + 14 skips (8 schema, 6 scope). Every claim kind is represented. Skip/exclusion evidence does not imply those semantics are Python-only or verified elsewhere.
- `git diff --quiet <instruction>..HEAD -- omitnix rewrite/truth/synthetic` exited 0. Product source, synthetic sources, answers and must/reference assignments are unchanged. The full diff is within the permitted truth tooling/tests/docs scope.
- The new scorer honestly describes flat presence only. It cannot establish actual source line, actual call depth/provenance/certainty, complete candidate resolution, or per-occurrence reason attribution. Those remain declared limitations, not passed dimensions.
- Independent controls exercised 2,163 category instances: 186 correct files, 186 missing files, 372 unknown/unclaimed records, 242 omitted required pairs, 242 wrong-mode pairs, 744 cumulative depth boundaries, 41 neutral pairs plus 41 wrong-mode and 41 invented-qualification controls, 28 reason controls, 28 forbidden leaks, duplicate-record rejection, and every literal/reason/detail claim kind. All intended checks passed. R1 was probed separately and reproduced.

## Execution evidence

Python 3.12.14. Used an independent venv, `/workspace/shared/omitnix-independent-venv`, with the already-installed dependency site-packages supplied through PYTHONPATH. No dependencies downloaded or installed. Repo root was also on PYTHONPATH for subprocess execution. Logs and the exact commands are alongside this report in `commands.json` and `check-*.log`.

All following commands exited 0:

1. `python rewrite/truth/tools/make_synthetic.py --check`: 189 files up to date.
2. `python rewrite/truth/tools/extract_from_tests.py --verify`: 176 functions, 111 extracted, 192 assertions pass, zero failures/errors; regeneration left the checkout clean.
3. `python rewrite/truth/tools/audit_population.py --check`: up to date.
4. `python -m pytest -q`: 403 passed, 1 skipped (semgrep unavailable).
5. `python -m pytest rewrite/truth/tests -q`: 57 passed.
6. `python -m ruff check rewrite/truth/tools rewrite/truth/tests`: passed.
7. `python rewrite/truth/tools/score.py --cmd "python -m omitnix" --from-tests --json /workspace/shared/omitnix-independent-evidence/score-a.json`.
8. Same scoring command to `score-b.json`.
9. `git diff --check`.
10. `git status --short`: empty.
11. Independent controlled-index script: exited 0; separately printed R1 reproduction.

Both score JSONs are byte-identical and exactly match the primary evidence hash: SHA-256 `91988addb61a8c6f4195edab83463bc661d9b10183ff62a6d63cbcb3eb8e6fe1`.

Must recall by expected depth: 110/177, 4/30, 0/15, 0/10; cumulative 114/232. Precision 114/117; 11 neutral pairs excluded; three false positives, zero commented/CTE leaks. Reference 4/10 and precision 4/4. Missing/unknown/unclaimed synthetic files 0/0/0. Applicable extracted assertions 178/178; 14 skipped. These are execution results, not acceptance of the Python product.

## Remaining limits

No Windows verification, semgrep test execution, private-input/rewrite scoring, real benchmark, or publication verification. No product changes requested. Full field/output-schema validation beyond R1 was not claimed. The existing policy disputes and unscored provenance dimensions remain explicit local-owner work. After R1/R2 fixes, rerun affected checks and review the exact final SHA.
