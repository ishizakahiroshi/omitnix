# #20261005-008 Progress board

Repository: ishizakahiroshi/omitnix. PR base: `dots/truth-miss-triage`.
Updated: 2026-10-05. Investigation only; no product, truth or scorer changes.

Draft submission: [PR #10](https://github.com/ishizakahiroshi/omitnix/pull/10).
The PR body records the final immutable receipt SHA and its CI status. This board
records the fixed analysis SHA rather than attempting to embed its own future
commit hash. The PR stays a draft; no merge or release.

| Step | Owner | State | Evidence, remaining work, next step |
|---|---|---|---|
| Baseline reproduction | dot | passed | Python 3.12.14; declared `.[dev]` installed; corpus check and two scoring runs exit 0, byte-identical 118/242 found, 124 misses and 3 FP |
| Investigation (MISSES.csv, REPORT.md) | dot | complete | All 127 rows; misses A36/B71/E17, C0/D0; no-B required ceiling 161/232; improvements are proposals only |
| Independent review | separate reviewer | passed | All 127 rows checked; M1 evidence correction closed at `066464fa30b805ef1f3553aa4f80df3f6058994d`; no open findings. Final receipt-only SHA recheck is reported in PR #10 |
| Local tests / analysis checks | dot | passed with disclosed limits | 476 passed, 1 skipped (semgrep absent); ledger audit, public-input probes, whitespace and structural scan pass; local Ruff absent, no undeclared dependency installed |
| Draft PR / remote CI | dot | submitted; CI verification in PR | PR #10 targets the designated base. Exact final-head checks and any scope-limited blockers are recorded in its receipt; no green aggregate CI claimed here |
| Local full-line review | local owner's AI (different product) | pending | Not performed or claimed by dot |
| Policy decision (95% scope, fix order) | owner | pending | Required after review; no policy chosen and no fixes applied |

## SHAs

- Instruction / diff baseline: `cd819366abda0025e1c40efafa128d9767a71531`
- Scored product/scorer/truth SHA: `3feb28dc5a57e1609e0923f972980131fd7f392b`
- Initial analysis reviewed: `7c3c2049a78029df1c5d37fd4532673422f9e2ef`
- Corrected analysis reviewed, M1 closed: `066464fa30b805ef1f3553aa4f80df3f6058994d`
- Final receipt head and exact-SHA recheck: [PR #10 receipt](https://github.com/ishizakahiroshi/omitnix/pull/10)
- Working branch: `dots/truth-miss-triage-20261005-008`

Product, scorer, truth and dependency declaration paths match the scored main SHA.
The final receipt adds review/progress evidence only, plus the explicit final test
command and the single skip reason; it changes no classifications or projections.

## History

- 2026-10-05: instruction prepared by the local owner.
- 2026-10-05: no task-number collision found in repository docs or GitHub issue/PR search. Declared dependency retrieval succeeded. The initial bare pip install could not write `~/.local/lib`; the same install succeeded in a scratch-local virtual environment without additional dependencies or credentials.
- 2026-10-05: investigator and reviewer each reproduced byte-identical scoring files. SHA-256: `1fecbb6a164c1c726ea70ac1c34db6770d1aaf70f098b2656d816204092d45a8`.
- 2026-10-05: completed the ledger, countermeasure bundles, arithmetic bounds and source/adapter evidence. Preserved task #6 outputs unchanged.
- 2026-10-05: independent full-row review requested one medium correction: product field normalization strips placeholder padding before scorer normalization. Three evidence cells and the report were corrected; class/count/95% conclusions were unchanged.
- 2026-10-05: fixed-SHA recheck passed at `066464fa30b805ef1f3553aa4f80df3f6058994d`, including two fresh baseline runs, full ledger audit and the affected evidence. Submitted Draft PR #10; final-head receipt and CI facts are maintained in its body.

Separate self-reports from local confirmation. The independent reviewer is not the
owner's local full-line review. The owner still decides product scope and fix order.
