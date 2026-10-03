# Local preparation evidence for #6

Updated: 2026-10-03. Product baseline: de9c498c62a71d075d570f4829a63801eba52810.

Package validation on Windows with the package root explicitly on PYTHONPATH:

- python -m pytest -q: 404 passed.
- make_synthetic.py --check: 189 generated files up to date (186 source files).
- extract_from_tests.py --verify: 192 extracted claims pass; 111 of 176 tests extracted.
- score.py --from-tests: only 97 claims checked, 95 skipped. This differs from extraction
  verification; inspect and report those exclusions. Do not present 97/97 as 192/192.
- Two score JSON outputs were byte-identical.
- Current scorer reports must-set recall through depth 3 of 49.1%, precision 97.4%,
  no missing file records and no commented/CTE leaks. These numbers are provisional
  evidence of scorer execution, not acceptance of its scoring contract or Python.
- ruff check . and omitnix --check pass. Self-inventory still reports 3 unresolved
  files and 38 unclaimed files; freshness is not complete semantic analysis.

Synthetic input directories are excluded from self-inventory and lint because they
deliberately include broken programs. Scoring tools remain subject to those checks.
No product implementation was changed by the local preparation.

Cloud audit, independent review, local rewrite scoring and private-input verification
remain pending. The branch is based only on published main, without publishing local
unrelated commits. Reproduce results in your environment rather than trusting this note.
