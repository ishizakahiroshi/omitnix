# P-20261024-004 omitnix: independent review

Use a worker other than the implementation worker if available. State the independence
actually achieved. Review the final implementation SHA, all changed and removed lines,
and the exact allowed-file boundary relative to the initial instruction commit.

Verify that the generic position tests still run if cast/match becomes valid PHP in
the grammar; that invalid PHP, Unicode columns, repeatability and fallback are covered;
and that old no-position behavior fails the new assertions. The cast-specific case may
skip only when its actual parse succeeds. No production partial analysis is allowed.

Inspect the make_cases.py specification for every restored c22 file. Check bytes,
tracked presence, narrow ignore exceptions, and seven-file coverage in a fresh checkout.
Reject changes to golden expectations or inclusion/exclusion semantics as a workaround.

Report each finding with severity, path/line, evidence, minimal repair, and confirmed or
unconfirmed status. Give reviewed SHA, commands/exit codes, actually executed CI jobs,
skips, unavailable checks, and remaining local acceptance. Do not infer a passing CI
from an unrun or skipped job. Store standalone reports only in the specified Drive
version with a manifest. The conductor performs independent final acceptance.
