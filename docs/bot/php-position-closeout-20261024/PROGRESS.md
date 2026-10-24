# P-20261024-004 omitnix: request entry

Instructions: README.md, FACTS.md, REVIEW.md in this directory.
The local conductor owns this file. Dots must not edit it.

Current phase: completed. PR #15 is merged, tag v0.1.4 is published to PyPI,
and the published wheel passed isolated installation and diagnostic checks.
The two integrated local workspaces have been removed using the managed tool.
The release plan and parent plan were closed in that order after the owner's
additional approval and the conductor's manual acceptance.
Management issue: https://github.com/ishizakahiroshi/omitnix/issues/14

The bot could read the instructions but could not accept its repository invitation;
the local conductor performed the test/fixture changes. Dots independently reviewed
the final c555c27 revision and found no required correction, with execution explicitly
left to local acceptance. No report payload or manifest was submitted separately.
Dots has acknowledged completion; no further implementation or report is requested.

Accepted code: c555c27b01c7b4b3abc5965e9aa0f601dca7c583.
Main/tag: 7ec72e80308b7917ea6f01027e8e74f442796801 / v0.1.4.
PR: https://github.com/ishizakahiroshi/omitnix/pull/15
Publish: https://github.com/ishizakahiroshi/omitnix/actions/runs/40108027847
Package: https://pypi.org/project/omitnix/0.1.4/

Validation: 409 Python tests; 72/72 tracked-only Python golden cases; 72/72 for each
of the five experimental local rewrites; PR/main CI eleven jobs each plus both secret
scanners; publish three jobs. The published wheel's 40 package/query files exactly
match the tagged Git blobs. Bare installation, the documented PHP extra installation,
located unknown diagnostics with no partial SQL, and valid PHP all passed.

Cleanup was initially held after the execution policy refused cache deletion.
After renewed approval, a bounded recheck found only generated Python, pytest and
ruff caches, with no source changes or content links. Cache deletion and both managed
worktree removals succeeded. Both directories and Git registrations are absent and
both management records say removed. Commit histories remain saved in their branches.

The plan checker still classifies historical expected diagnostics as manual review.
The conductor preserved the original observations and structured results; automated
readiness is not claimed. The owner approved the remaining steps and manual acceptance
is recorded. The classifier issue remains a separate local follow-up.
No release was repeated, no partial parsing was introduced, and no archive was run.

Acceptance was completed by the local conductor after bot write access proved
unavailable. Dots supplied independent static review. Main integration, publication,
installed-package acceptance, cleanup and the parent plan's closeout are complete.
