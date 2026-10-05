# #20261005-008 Progress board

Repository: ishizakahiroshi/omitnix. PR base: `dots/truth-miss-triage`.
Updated: 2026-10-05. Investigation only; no product, truth or scorer changes.

| Step | Owner | State | Evidence, remaining work, next step |
|---|---|---|---|
| Baseline reproduction | dot | passed | Python 3.12.14, declared `.[dev]` installed in a scratch virtual environment; corpus check and two scoring runs exit 0, byte-identical 118/242 found, 124 misses and 3 false positives |
| Investigation (MISSES.csv, REPORT.md) | dot | in progress | Source-first classification of all 127 rows; countermeasure estimates and scope ceilings under preparation |
| Independent review | separate reviewer | in progress | Independent corpus check and two scorer runs pass; final documentation SHA review pending |
| Local full-line review | local owner's AI (different product) | pending | Not performed or claimed by dot |
| Policy decision (95% scope, fix order) | owner | pending | Required after review; no policy chosen and no fixes applied |

## SHAs

- Instruction commit: `cd819366abda0025e1c40efafa128d9767a71531`
- Scored product/scorer SHA: `3feb28dc5a57e1609e0923f972980131fd7f392b`
- Execution checkout: `cd819366abda0025e1c40efafa128d9767a71531`; product, scorer and truth paths match the scored main SHA
- Working branch: `dots/truth-miss-triage-20261005-008`
- Code SHA of PR head: pending
- Reviewed SHA: pending

## History

- 2026-10-05: instruction prepared by the local owner.
- 2026-10-05: no task-number collision found in repository docs or GitHub issue/PR search. Declared dependency retrieval succeeded. The initial bare pip install could not write `~/.local/lib`; the same install succeeded in a scratch-local virtual environment without additional dependencies or credentials.
- 2026-10-05: investigator and independent reviewer each reproduced two byte-identical scoring files. SHA-256: `1fecbb6a164c1c726ea70ac1c34db6770d1aaf70f098b2656d816204092d45a8`.

Separate self-reports from local confirmation. The independent reviewer is not the owner's local full-line review.
