# Independent review for #6

Updated: 2026-10-03.

Use a reviewer separate from the primary audit/fix author. State that separation and
the exact code SHA reviewed. Read README.md, the original instruction commit, and the
actual diff to the submitted code SHA. Independently inspect source/expected pairs,
scoring denominators, certainty, skipped claims, missing files, wrong modes, forbidden
tables, neutral extra tables, unknown/unresolved distinctions and depths 0 through 4.

Try a deliberately wrong controlled index for every scoring dimension. Verify that
each wrong answer is detected and that a correct control passes. Check regeneration
does not recreate removed errors. Review report claims against actual output and
enumerated coverage. Require reasons for answer changes; Python output is not proof.

Return findings with severity, path/line, reproduction and user impact; commands and
exit codes; unreviewed population; final reviewed SHA. Re-review new code after fixes.
If an independent reviewer cannot be provided, mark this stage pending explicitly.
Do not merge or claim Windows/private-input acceptance.
