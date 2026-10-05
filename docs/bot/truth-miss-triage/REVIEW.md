# #20261005-008 Independent review instructions

The reviewer must be a different worker from the investigator and must not reuse the
investigator's reasoning. Review the final code SHA of the Draft PR against `README.md`.

## What to check

1. Reproduce the baseline: run the two scorer commands from `README.md` yourself and
   confirm byte-identical JSON and 118/242 found.
2. Population: `MISSES.csv` rows equal the scorer's missed pairs plus false positives.
   No pair is missing, duplicated or filed under the wrong case/file.
3. Every row in classes **A, C and D** (they drive fix decisions): open the corpus source,
   the answer and the adapter location, and confirm or reject the class. Record each
   disagreement with evidence.
4. Class **B and E**: check at least 30% of rows, spread across every group, plus every
   row where `disclosed` is "no". State which rows you checked.
5. Countermeasures: each group's recovered-pair count equals the number of `MISSES.csv`
   rows carrying that `group_id`. The cumulative recall and the "no B change" ceiling are
   recomputed correctly from 232 required and 242 total pairs.
6. The scope tension section quantifies, and does not decide, the depth and dynamic-name
   policy.
7. The PR changes only `docs/bot/truth-miss-triage/**`; no secrets, private URLs or home
   paths.

## Report

Write `INDEPENDENT_REVIEW.md` with: review SHA, commands and exit codes, findings with
severity (high: a wrong class that changes a countermeasure's recovered count or the 95%
reachability verdict; medium: wrong evidence, wrong count; low: wording), rows checked and
rows not checked. After the investigator fixes findings, re-check the affected rows at the
new SHA; do not carry an earlier pass forward.
