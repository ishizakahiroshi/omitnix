# #6 Ground-truth and scoring review

Updated: 2026-10-03. Task number #6 is separate from GitHub PR numbers.

## Purpose and scope

We are evaluating whether to keep Python or rewrite omitnix. Python output is not an
oracle: the public synthetic sources and hand-written test assertions are the evidence.
Before comparing implementations, independently check that the answers and scoring
tool measure the intended behavior. A scorer which rewards an omitted table, hides
an unparsed file, or counts a comment as a table can produce a wrong language decision.

Repository: ishizakahiroshi/omitnix. PR base: dots/truth-scoring-review.
Product source baseline: de9c498c62a71d075d570f4829a63801eba52810.
The initial instruction commit is the review diff baseline, not a correctness oracle.
All input required for this task is in this branch. No local notes are prerequisites.

Allowed changes: rewrite/truth/**, docs/bot/truth-scoring-review/**, and focused tests
under rewrite/truth/tests/**. If a tooling setting or generated inventory must change,
explain the need and keep it scoped. Do not change omitnix/** to improve its score.
Do not implement or modify the five language rewrites. Their local sources are not
part of this package. Do not read private repositories or import external real code.
Do not merge, release, deploy, or alter other open benchmark/SQL-behavior PRs.

## Contract to check independently

- Read source before expected answers. Check table names, read/write modes, source
  lines, direct references and call depths 1/2/3. Depth 4 is outside required recall.
- Commented-out SQL and CTE aliases are not tables. CREATE TABLE LIKE reads its source
  and writes its destination. Text-only test assertions and system tables are separate.
- Preserve direct, followed, candidate and unknown certainty; do not treat a candidate
  as a proven answer. External-input table names cannot be assigned an invented table.
- Report must and reference sets separately. Reference covers deliberately unsettled
  dialect/policy cases. Do not silently move failures to reference or weaken an answer
  just because Python fails it. Explain disputed policy rather than deciding it.
- Audit score.py against this contract. Its current implementation uses some neutral
  matches and coarse unresolved checks; identify what those checks fail to prove.
  Test missing records, duplicate references, wrong modes, forbidden tables, neutral
  extras, unresolved reasons, unknown files and each depth boundary with controlled
  index documents. Distinguish extraction fidelity from product correctness.
- from-tests claims are another source of evidence, not proof the tests are correct.
  Audit exclusions/skips and every claim kind. Unsupported claims must remain visible.
- Check all synthetic case categories and every extraction claim kind. Enumerate the
  complete population first, record the reviewed sample and unreviewed remainder.
  Prefer full source/answer review where feasible; a sample is not full coverage.

## Work and verification

1. A primary reviewer audits inputs and scorer and writes REPORT.md with findings,
   reproduction, coverage, limitations and proposed focused fixes.
2. Apply evidence-backed fixes and add meaningful scorer regression tests. Preserve
   original failing evidence in the report. Never use implementation output to author
   correct answers. Keep product-source defects as findings for the local owner.
3. An independent reviewer follows REVIEW.md against the final code SHA.

Python 3.11+ is required. Dependencies are declared in pyproject.toml; if permitted
in your environment, install with python -m pip install -e ".[dev]" and ruff.
Record versions and exact commands/exit codes. If dependencies cannot be obtained,
continue stdlib/source review and report blocked executions without claiming a pass.

Run from repo root (write result JSON outside the repo; the implementation's generated
index itself stays inside its temporary corpus root):

    python rewrite/truth/tools/make_synthetic.py --check
    python rewrite/truth/tools/extract_from_tests.py --verify
    python rewrite/truth/tools/score.py --cmd "python -m omitnix" --from-tests --json <outside-repo-result.json>
    python -m pytest
    python -m pytest rewrite/truth/tests
    python -m ruff check rewrite/truth/tools rewrite/truth/tests

The focused tests directory does not exist at handoff; add it when fixing the scorer,
or explicitly state that no focused tests were added. Score twice and compare JSON
results. A scorer exit code 0 means it ran, not that Python passed the expectations.
Record denominators, skipped claims, missing files, recall/precision by depth, honesty
checks and leaks. Regeneration must not silently overwrite reviewed answer fixes.

## Delivery and ownership

Submit a Draft PR to dots/truth-scoring-review, with report, code SHA, independent
review SHA, exact execution evidence and outstanding limitations. The local owner
will inspect the PR, score local implementations/private inputs, and verify Windows
behavior and timings separately. Cloud results do not complete those local tasks.

Reply in the same task conversation with: recognized #6, any number collision,
instruction commit read, repository access, Python/dependency availability, disk/time
constraints and independent-review capability. Stop duplicate startup on collision.
Update PROGRESS.md at acceptance, first findings, fixes and review, and send a short
summary and board link in the same conversation. Distinguish self-report from evidence.
