# P-20261024-004 omitnix: finish PHP syntax-error location validation

Read FACTS.md, REVIEW.md and PROGRESS.md at this same instruction revision.
Management issue: https://github.com/ishizakahiroshi/omitnix/issues/14
The owner authorized the remaining integration, validation and Python distribution.
The owner decided to keep a file with a syntax error wholly `unknown`. Do not add
partial analysis or source rewriting. The local conductor handles merge and release.

## Work and ownership

Start a new branch `dots/P-20261024-004-php-position-closeout` from the final
instruction commit linked in the management issue. Submit one Draft PR to `main`.
The branch already contains the PHP location change, commit
`a9a55f2823384b9f8c138ccabe4de00416409b89`, on base
`d68b101425f2b599156d4521e6e7025f1b151d6b`. Do not reimplement that change.

You own only:

- `tests/test_php_adapter.py`: keep the cast/match regression, but make the generic
  error-location, repeatability, Unicode-column and no-position fallback coverage
  independent of the grammar defect. Use permanently invalid invented PHP for that
  generic coverage. The cast-specific regression may skip when the grammar is fixed.
  Show that the location assertions fail against the pre-C2 behavior.
- `.gitignore`: add narrowly scoped exceptions for the golden input `build` directory.
- `rewrite/golden/cases/c22_globs/input/build/**`: restore the invented fixtures as
  specified by the existing `rewrite/tools/make_cases.py`. Do not weaken expectations.

Keep all other files unchanged. In particular, do not edit the production parser,
golden expected outputs, workflows, public instructions, PROGRESS, versions or manifests.
Do not run the full case generator in the working tree if it rewrites unrelated cases.
Check the actual generator and baseline before editing; report any false premise.

## Validation and delivery

Use existing available dependencies only. Do not install or download dependencies.
If execution is unavailable, submit the Draft PR and identify each unexecuted check;
the PR's existing CI and the local conductor perform those checks. Relevant commands:

```
python -m pytest tests/test_php_adapter.py tests/test_determinism.py -q
python -m ruff check tests/test_php_adapter.py
python rewrite/tools/run_golden.py --cmd "python -m omitnix"
```

The golden subprocess runs in temporary repositories. Ensure it imports this branch's
package, for example using an absolute PYTHONPATH derived from this checkout at runtime.
Do not type a machine-specific absolute path into committed material. Check c22 from a
fresh checkout with only tracked fixtures; an existing ignored build directory can mask
missing inputs. Test data must be invented and outputs must remain deterministic.

GitHub operations must use `ishizakahiroshi-bot`, never the owner's account. A repository
write invitation was sent before this request. If needed, accept only that repository
invitation when your available tools support it, then verify write permission. If bot
write access or acceptance is unavailable, report the blocker in this same thread;
do not switch accounts. Source review can continue with public read access.

Allowed: the named branch's blobs/trees/commits/ref updates, one Draft PR to main,
corrections to that branch, comments on this management issue, and replies in the
request thread. Use commit trailer `Agent: dot`. Do not force push. Before retrying
a cancelled ref/PR operation, read its actual state. If unchanged, at most two retries;
if already applied, continue; if unexpectedly changed, stop that operation.

Independent non-code review results, if saved separately, belong in Google Drive
`bot/blob/2026/10/P-20261024-004/v1/`, including all subdirectories. Save payloads first,
read back and verify bytes/SHA256, then save manifest.json last with each relative path,
bytes and SHA256. New revisions use v2 and later; never overwrite a submitted version.
Do not store standalone review reports in a GitHub branch or PR.

Forbidden: main/other branch writes, merge/tag/release/publish/deploy, workflow changes
or manual CI dispatch/rerun, new dependencies or charges, private repositories, local
machine paths/settings/data/credentials, changes to other rewrites, and Drive writes
outside the specified version or deletion/overwrite of existing artifacts.

In the acknowledgement give the task ID, instruction commit, bot identity, repository
read/write and invitation capability, available execution capabilities, and whether
implementation and independent review can be assigned to different workers. Continue
within the allowed scope without another approval question. Report acceptance,
submission, questions, stopping and completion to the management issue and this same
thread. If the issue tool only accepts PR numbers, say so in Slack; the conductor will
copy the report with attribution. Every report starts
`#P-20261024-004 omitnix: <status>`. Do not post in another thread.

Stop the affected operation for a policy rejection, two identical CI failures, a
serious review finding still present after two corrections, out-of-scope requirements,
or a 90-minute stage. Report actual branch head/PR/checks and remaining work. Do not
change the task to bypass a rejection. The local conductor handles unavailable stages.
