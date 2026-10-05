# #20261005-008 Why the synthetic recall is 49%: miss triage and countermeasures

Updated: 2026-10-05. Task number #20261005-008 is separate from GitHub Issue/PR numbers.

## Purpose

Task #6 finished the public synthetic scoring. All six implementations (Python and five
rewrites) find only about half of the expected tables, while what they do output is
almost always right:

| Implementation | Found/expected (must+reference) | Recall | Precision |
|---|---:|---:|---:|
| Python | 118/242 | 48.76% | 97.52% |
| Java (best) | 121/242 | 50.00% | 97.58% |

The owner's minimum bar is **recall of 95% or more on the synthetic set**. Nobody has yet
established *why* the misses happen. This task is **investigation and proposals only**:
for every expected pair that Python misses, determine which layer is responsible and
propose countermeasures with an estimate of how far each one moves recall.

**Do not fix anything.** No change to `omitnix/**`, `rewrite/truth/**` (answers, corpus,
scorer, tests) or CI. The owner will decide the 95% scope and the fix order from your
report, and the fixes will be a separate task.

## Baseline

- Repository: ishizakahiroshi/omitnix. PR base: `dots/truth-miss-triage` (created from main
  at 3feb28dc5a57e1609e0923f972980131fd7f392b).
- Product and scorer: main `3feb28dc5a57e1609e0923f972980131fd7f392b`. Scorer: `rewrite/truth/tools/score.py`.
  Answers: `rewrite/truth/synthetic/answers.json`. Corpus: `rewrite/truth/synthetic/corpus/`.
  Corpus design: `rewrite/truth/synthetic/README.md`. The scorer was independently reviewed
  in task #6 (`docs/bot/truth-scoring-review/`).
- Only the Python implementation is in this repository. Score Python. The five rewrites
  differ from Python by at most 3 pairs, so Python's causes stand for all six; do not try
  to obtain the rewrites.
- The initial instruction commit is the diff baseline for review, not a correctness oracle.

## Where the misses are (Python, from task #6 scoring, required depth <= 3)

| Category | Found/expected | Missed |
|---|---:|---:|
| ddl (tag `defect:plain_ddl_command`) | 5/43 | 38 |
| dynamic_table | 0/28 | 28 |
| call_depth_1 / 2 / 3 / 4 | 6/10, 6/15, 6/20, 6/20 | 41 |
| dialect | 2/7 | 5 |
| write | 23/27 | 4 |
| escape (tag `defect:php_escape`) | 0/4 | 4 |
| query_builder | 0/2 | 2 |
| unsupported | 0/1 | 1 |
| comment | 16/17 | 1 |

Also: false positives 3 (precision numerator 118 of 121), tags `limit:depth` 6/11 and
`limit:no_import_follow` 4/17. By depth of the expected answer: depth 1 4/30, depth 2 0/15,
depth 3 0/10. Re-derive all of these yourself; treat this table as a pointer, not evidence.

## Known tension you must surface (do not resolve it)

The project's stated scope (`CLAUDE.md`, "やらないこと") excludes **tracking indirect calls of
two levels or more**, and dynamic table names are designed to be reported as `unresolved`
with a reason rather than guessed. The answer set expects tables up to call depth 3 and
records table names fixed by arguments as "followed". Some misses are therefore by design,
not defects. Quantify exactly how many missed pairs depend on this, and state what recall
is reachable (a) within the current scope and (b) if the scope is widened. The owner decides.

## Cause classes (assign exactly one primary class per missed pair)

- **A product defect**: inside the adapter's declared capability, but it fails (wrong
  parse, dropped statement, SQL not handed to sqlglot, etc.).
- **B scope limit by design**: outside what the product says it does (the depth limit
  above, dynamic names reported as unresolved, query builders, unsupported dialect).
  Check whether the miss is at least *disclosed* (unresolved with reason, `unknown`).
- **C answer questionable**: the expected pair is wrong or depends on an unsettled
  convention. Give the source line and the convention you rely on. Do not edit answers.
- **D scorer defect**: the product output is acceptable but scored as a miss (e.g. a
  disclosed candidate or an unresolved entry that the contract counts, a depth or path
  normalization mismatch).
- **E dependency limit**: a sqlglot or tree-sitter grammar limitation.

Read the corpus source first, then the answer, then the product output, then the adapter
code. Never derive the right answer from product output.

## Countermeasures

Group missed pairs by **shared root cause**, not by category. For each group give:
the cause class, the layer and module to change (e.g. `omitnix/adapters/php.py`, `_sql.py`,
`score.py`, `answers.json`), the change in one or two sentences (no patch), the number of
missed pairs it recovers, the risk to precision and to `unknown`/`unresolved` honesty, and
whether it needs an owner policy decision. Order groups by recovered pairs. Then report
cumulative recall if groups are applied in that order, the recall ceiling without any B
change, and whether 95% of the 232 required pairs (221 pairs) is reachable.

## Deliverables (all under `docs/bot/truth-miss-triage/`)

- `MISSES.csv`: one row per missed expected pair and per false positive. Columns: case,
  file, table, mode, required_or_reference, expected_depth, category, tags, cause_class,
  disclosed (yes/no and how), evidence (source line and adapter location), group_id.
  The row count must equal the scorer's missed + false-positive counts.
- `REPORT.md`: method, exact commands with exit codes and tool versions, cause-class totals,
  the countermeasure table, the recall projections, the scope tension, questionable answers
  and scorer findings, and what you did not examine.
- Optional helper scripts in `docs/bot/truth-miss-triage/scripts/` (read-only analysis).
- Keep `PROGRESS.md` current at each checkpoint.

## Verification

Python 3.11+. Install with `python -m pip install -e ".[dev]"` if your environment allows.
If dependencies cannot be obtained, stop at that point, record the exact error (replace home
paths with `~/...`), and report it; do not produce cause classes from guesswork.

Run from the repo root; write result JSON outside the repo:

    python rewrite/truth/tools/make_synthetic.py --check
    python rewrite/truth/tools/score.py --cmd "python -m omitnix" --json <outside-repo>/score-1.json
    python rewrite/truth/tools/score.py --cmd "python -m omitnix" --json <outside-repo>/score-2.json

The two JSON files must be byte-identical and must reproduce 118/242 found. If they do not,
stop and report the difference before triaging. A scorer exit code 0 means it ran, not
that Python passed.

## How to proceed (one approval, then automatic)

Approval is given once by sending this instruction. Proceed without asking unless a stop
condition applies. Report to the conversation three times: acceptance, any stop, and the end.

Stop conditions: the baseline does not reproduce; a change outside `docs/bot/truth-miss-triage/`
seems required; new dependencies, billing, credentials or external services are needed;
the instruction contradicts the source; the owner must act (GitHub confirmation, CI not
starting); one step exceeds 90 minutes.

## Acceptance reply

In the same conversation reply with: the task number, any number collision, the instruction
commit you read, and whether you can install the dependencies and run Python 3.11+.

## Submission

Draft PR to `dots/truth-miss-triage` containing only `docs/bot/truth-miss-triage/**`.
Commit trailer `Agent: dot`. State the code SHA you scored, the review SHA, commands and exit
codes, and remaining limitations. Do not merge, release or touch other branches.
An independent reviewer follows `REVIEW.md` before you submit.

## Boundaries

Public synthetic data only. Do not read private repositories or import real code.
No secrets, private conversation URLs or real home paths in any file.
