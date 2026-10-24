# P-20261024-004 omitnix: request entry

Instructions: README.md, FACTS.md, REVIEW.md in this directory.
The local conductor owns this file. Dots must not edit it.

Current phase: code delivery accepted. PR #15 is merged, tag v0.1.4 is published to PyPI,
and the published wheel passed isolated installation and diagnostic checks. Local
workspace cleanup and the plan's mechanical closeout remain on hold.
Management issue: https://github.com/ishizakahiroshi/omitnix/issues/14

The bot could read the instructions but could not accept its repository invitation;
the local conductor performed the test/fixture changes. Dots independently reviewed
the final c555c27 revision and found no required correction, with execution explicitly
left to local acceptance. No report payload or manifest was submitted separately.

Accepted code: c555c27b01c7b4b3abc5965e9aa0f601dca7c583.
Main/tag: 7ec72e80308b7917ea6f01027e8e74f442796801 / v0.1.4.
PR: https://github.com/ishizakahiroshi/omitnix/pull/15
Publish: https://github.com/ishizakahiroshi/omitnix/actions/runs/40108027847

Validation: 409 Python tests; 72/72 tracked-only Python golden cases; 72/72 for each
of the five experimental local rewrites; PR/main CI eleven jobs each plus both secret
scanners; publish three jobs. The published wheel's 40 package/query files exactly
match the tagged Git blobs. Bare installation, the documented PHP extra installation,
located unknown diagnostics with no partial SQL, and valid PHP all passed.

Two integrated local workspaces are retained because the execution policy refused the
generated-cache deletion step. The plan closeout checker also treats historical expected
diagnostics as unmet checks. These are recorded separately from the accepted delivery;
the conductor has not claimed that cleanup or the formal plan transition succeeded.

Required acceptance: code submission from the bot identity; independent review of the
submitted SHA; focused and full local Python checks; tracked-only golden acceptance;
separate local experimental-rewrite compatibility checks; main PR checks and merge;
Python package build, tag-driven PyPI publication and isolated installed-wheel smoke
test. The conductor owns integration and publication. Dots completion alone does not
complete this parent task. Status changes and evidence belong in the management issue.
