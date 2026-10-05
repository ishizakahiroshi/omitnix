# #20261005-008 Independent review

## Revision and disposition

- Review date: 2026-10-05.
- Reviewed analysis SHA: `7c3c2049a78029df1c5d37fd4532673422f9e2ef`.
- Instruction / diff baseline: `cd819366abda0025e1c40efafa128d9767a71531`.
- Product, truth and scorer SHA: `3feb28dc5a57e1609e0923f972980131fd7f392b`.
- Reviewer: a separate worker from the investigator and SQL investigation worker.
- Disposition at this SHA: **one medium evidence-only correction requested**.
  No high finding, cause-class disagreement, population error, recovery-count
  error, or 95%-reachability disagreement was found. Do not carry this review
  forward to changed analysis without a fixed-SHA recheck.

I independently read all 186 corpus source files before examining the affected
answers and my own retained product output, then inspected the relevant adapter,
shared extraction and SQL parsing code. All affected call-chain and argument
companion files were included. This work preceded receipt of the investigator's
final ledger/report. The review did not use the investigator's reasoning as an
answer oracle. After the candidate SHA was supplied, I compared the ledger to
those independently established facts and repeated the baseline at that SHA.

## Commands and results

Commands ran from the checkout root unless stated otherwise. `$VENV` is the
already installed scratch virtual environment and `$OUT` is the reviewer's
separate scratch directory outside the checkout. No dependency installation,
repository write, Git mutation or external service call was performed by this
reviewer.

Preparation: `export PATH="$VENV/bin:$PATH"` and
`export PYTHONDONTWRITEBYTECODE=1`.

| Command | Exit | Result |
|---|---:|---|
| `python --version` | 0 | Python 3.12.14 |
| `python rewrite/truth/tools/make_synthetic.py --check` | 0 | Corpus current, both initial and fixed-SHA review |
| `python rewrite/truth/tools/score.py --cmd 'python -m omitnix' --json "$OUT/score-1.json"` | 0 | Initial independent 118/242, 3 FP |
| `python rewrite/truth/tools/score.py --cmd 'python -m omitnix' --json "$OUT/score-2.json"` | 0 | Initial independent 118/242, 3 FP |
| `cmp "$OUT/score-1.json" "$OUT/score-2.json"` | 0 | Byte-identical |
| `cp -a rewrite/truth/synthetic/corpus "$OUT/corpus"; python -m omitnix --all-files --root "$OUT/corpus"` | 0 | Separate retained index for row-by-row disclosure checks |
| `python rewrite/truth/tools/score.py --cmd 'python -m omitnix' --json "$OUT/final-score-1.json"` | 0 | Repeated at reviewed SHA: 118/242, 3 FP |
| `python rewrite/truth/tools/score.py --cmd 'python -m omitnix' --json "$OUT/final-score-2.json"` | 0 | Repeated at reviewed SHA: 118/242, 3 FP |
| `cmp "$OUT/final-score-1.json" "$OUT/final-score-2.json"` | 0 | Byte-identical |
| `cmp "$OUT/final-score-1.json" "$OUT/score-1.json"` | 0 | Same as original independent baseline |
| `python "$OUT/audit_population.py"` | 0 | Reviewer-local standard-library reconstruction, independent of scorer/investigator code: exact 124 misses + 3 FP |
| `python "$OUT/audit_final_ledger.py"` | 0 | All 127 distinct keys, source-line references, case/file/mode/table, set, depth, category/tags, classes and disclosure decisions match |
| `python docs/bot/truth-miss-triage/scripts/audit_ledger.py --score-json "$OUT/final-score-1.json"` | 0 | Published helper agrees with independently verified counts and projections |
| `python docs/bot/truth-miss-triage/scripts/probe_sql_layers.py --output "$OUT/final-probes.json"` | 0 | 30 public files and quoted-placeholder diagnostic; inspected implementation and results |
| `git diff --exit-code 3feb28dc5a57e1609e0923f972980131fd7f392b..7c3c2049a78029df1c5d37fd4532673422f9e2ef -- omitnix rewrite/truth pyproject.toml .github` | 0 | Product, truth, dependency declaration and CI identical |
| `git diff --check cd819366abda0025e1c40efafa128d9767a71531..7c3c2049a78029df1c5d37fd4532673422f9e2ef` | 0 | No whitespace errors |
| `git diff --name-only cd819366abda0025e1c40efafa128d9767a71531..7c3c2049a78029df1c5d37fd4532673422f9e2ef` | 0 | Five changed files, all within authorized documentation directory |
| `git status --short` | 0 | Empty before and after review execution |

All four independently generated score files have SHA-256
`1fecbb6a164c1c726ea70ac1c34db6770d1aaf70f098b2656d816204092d45a8`.
Scorer exit zero means the scoring operation ran, not that 95% recall was met.

Installed versions were independently read: sqlglot 30.21.0, tree-sitter 0.26.0,
PHP grammar 0.24.1, Python/Go/JavaScript grammars 0.25.0, Rust grammar 0.24.2,
TypeScript grammar 0.23.2, HTML grammar 0.23.2, PyYAML 6.0.3, pip 25.0.1,
pytest 9.1.1. The reviewer-local audit scripts reconstruct normalized expected,
neutral and forbidden pairs from answers and compare them to the independently
retained index; they do not import `score.py` or investigator classification code.

## Finding

### M1 — medium: inaccurate normalization-layer evidence for the three false positives

Affected rows at the reviewed SHA: CSV physical lines **28, 29 and 60**;
`php09_backtick_any`, `php10_backtick_array_loop`, `py10_external_table`, each
`read:omitnix_placeholder`, group `A_QUOTED_PLACEHOLDER_FP`.

The underlying A classification is correct. `_sql.py:204–211` compares the
padded quoted identifier to the unpadded sentinel and emits it as a table.
However, the evidence currently says that scorer `_norm` strips the padding
only after product output. The retained product index already contains
`omitnix_placeholder` without padding: **`omitnix/analyze.py:109` strips list
values before index serialization**. Scorer normalization is a later layer and
is not what first changes the spelling in this example.

The Python row also cites `php.py:104–151`, which is not its execution path.
Use `python.py:49–64` and `_extract.py:158,183–220` for that row; use the PHP
extractor for the two PHP rows. Cite the shared `_sql.py` sentinel check,
`analyze.py:109`, and the later scorer normalization distinctly.

Requested correction: revise the three evidence cells and the report's
placeholder explanation to show **host hole → SQL sentinel-check failure →
product field normalization → correctly scored extra**. This changes no class,
missed-pair count, FP count, proposal budget or reachability verdict. A fixed-SHA
recheck of the corrected cells and explanation is required.

No other high/medium/low issue was established in the substantive analysis.
The progress board is a submission checkpoint and still needs the investigator's
normal completion/review-SHA update before the Draft PR is finalized.

## Population, classes and disclosure

The independently reconstructed baseline is 114/232 required plus 4/10 reference,
118/242 overall. All 186 file records are present; none is unknown or unclaimed.
The ledger contains every one of the 124 missing normalized pairs and exactly
three extras, with no duplication or wrong case/file association.

Confirmed primary classes: **A 36 misses + 3 FP; B 71 misses; E 17 misses;
C 0; D 0**. The E classification of the ten embedded RENAME misses is reasonable
because direct parser probes still produce opaque commands after the gate is
bypassed, while the ledger and full-bundle proposal explicitly retain the
secondary opener defect. They are not also counted in A_DDL_GATE.

All 71 B and 17 E rows were checked, including **every 50 undisclosed B row and
11 undisclosed E row**. B disclosure is 21 yes / 50 no; E is 6 yes / 11 no.
PHP depth misses and non-PHP callers are correctly marked undisclosed despite
their design-limit classification. The PHP REPLACE row is also correctly marked
undisclosed: another statement's `dynamic_sql` reason does not disclose this loss.

All 39 A rows, including all three extras, were checked. There are no C or D rows
requiring an additional sample. The source/answer conventions for CREATE LIKE,
DDL writes, builder calls and argument-derived attribution are explicit; no
contrary source fact justified reclassifying them as questionable answers. The
scorer's extraction-presence metric does not promise credit for unresolved
reasons, candidate sets, source-line provenance or call-path provenance.

## Countermeasures and arithmetic

The complete-bundle recovery counts equal the disjoint missed-pair rows in each
group: **41, 27, 20, 13, 8, 4, 4, 3, 2, 1, 1**, totaling 124. The separate
placeholder group has three false positives to remove and zero recall recovery;
those three rows must not be added to the recall numerator.

I independently recomputed every cumulative numerator and percentage in REPORT.
The no-B ceiling is **161/232 = 69.40% required**, **171/242 = 70.66% overall**.
The 95% required threshold is **ceil(0.95 × 232) = 221**. The first five listed
full bundles conditionally reach **222/232 = 95.69%**, while leaving E unrecovered
even after all A+B fixes reaches only **216/232 = 93.10%**. At least five of the
16 required E pairs would then still be needed.

The report correctly separates the 25 depth-2/3 misses, 16 additional literal
one-hop misses, 20 argument-derived table misses, eight same-file value misses,
and two builder misses. It quantifies rather than decides the scope policy.
The 20 argument rows are disjoint from the 41 literal call-chain rows, and their
shared graph prerequisite is disclosed. The projections remain hypothetical;
there was no patched-product experiment establishing improved recall.

The direct diagnostics support the layer distinctions: 27 DDL pairs survive the
helper gate bypass; RENAME/REPLACE stay opaque; MERGE has a correct AST but wrong
wrapper write attribution; escaped host quotes and heredoc newlines are damaged
before SQL parsing; `?1` fails even with the SQLite dialect; the procedure script
requires more than removing client delimiters. FK/procedure precision risks and
the need to preserve unresolved disclosure are explicitly retained.

## Rows checked and not checked

**Checked: every logical data row, corresponding to physical CSV lines 2–128
at the reviewed SHA (127/127). Unchecked ledger rows: none.** Group-specific
line manifest follows so the review coverage is unambiguous after later edits.

| Group | Checked CSV lines at reviewed SHA |
|---|---|
| B_ARGUMENT_TABLE | 2–5, 31–34, 56–59, 81–84, 106–109 |
| B_STATIC_TABLE_VALUE | 6, 30, 35, 53–55, 85, 110 |
| A_DDL_GATE | 7, 10–13, 36, 39–43, 47, 61, 64–67, 86, 89–92, 111, 114–117 |
| E_OPAQUE_COMMAND | 8–9, 37–38, 44, 62–63, 87–88, 103–104, 112–113 |
| A_MERGE_GATE_MODE | 14–15, 45–46 |
| B_CALL_PROPAGATION | 16–24, 48–52, 69–77, 94–102, 120–128 |
| A_HOST_ESCAPE | 25–26, 68, 118 |
| A_HEREDOC_GAPS | 27 |
| A_QUOTED_PLACEHOLDER_FP | 28–29, 60 |
| E_NUMBERED_PARAMETER | 78–80 |
| B_QUERY_BUILDER | 93, 119 |
| E_CLIENT_SCRIPT | 105 |

Both published helper scripts were read before execution. They inspect public
corpus inputs and write requested outputs only outside the repository; they do
not patch the product, truth, scorer or fixtures. Diagnostic input transformations
are labeled and not misrepresented as baseline or end-to-end fixed-product runs.

## Scope and limitations

The five changed paths are MISSES.csv, REPORT.md, PROGRESS.md, and the two analysis
helpers, all under `docs/bot/truth-miss-triage/`. Manual diff inspection found no
secrets, private URLs, private source material or real home paths. Sanitized
`~/.local/lib` and execution placeholders are not real home-path disclosures.
Product/truth/scorer/dependency/CI diffs are empty against the specified main SHA.

This is an independent investigation review, not the owner's separate local
full-line review. I did not run the five rewrites, execute synthetic fixture
programs, install alternate parser versions, implement any proposal, or validate
precision after hypothetical changes. I did not independently rerun the full
pytest suite or verify remote PR/CI publication; those remain investigator
submission responsibilities. No decision on product scope or fix order is made.
