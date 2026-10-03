# Execution evidence

All commands ran at the repository root with the isolated venv bin directory first on PATH.
Score JSON files remain outside the repository. Durations are verification observations, not benchmarks.

## Toolchain

```text
Python 3.12.14
git version 2.52.0
iniconfig==2.3.0
-e git+https://github.com/ishizakahiroshi/omitnix.git@1451cae88b7f5f45ebd7077aaf2a880989e47298#egg=omitnix
packaging==26.3
pluggy==1.6.0
Pygments==2.21.0
pytest==9.1.1
PyYAML==6.0.3
ruff==0.16.10
sqlglot==30.21.0
tree-sitter==0.26.0
tree-sitter-go==0.25.0
tree-sitter-html==0.23.2
tree-sitter-javascript==0.25.0
tree-sitter-php==0.24.1
tree-sitter-python==0.25.0
tree-sitter-rust==0.24.2
tree-sitter-typescript==0.23.2
```

## Dependency installation

`python -m venv /workspace/shared/omitnix-truth-review-venv` (exit 0)

`/workspace/shared/omitnix-truth-review-venv/bin/python -m pip install --no-cache-dir -e ".[dev]" ruff` (exit 0)

## Command 1

`python rewrite/truth/tools/make_synthetic.py --check`

Exit: 0; elapsed 0.087 seconds.

```text
up to date: 189 files
```

## Command 2

`python rewrite/truth/tools/extract_from_tests.py --verify`

Exit: 0; elapsed 0.629 seconds.

```text
tests 176  extracted 111  claims 192
  go       tests  17  extracted  11  claims  17  python pass 17 fail 0 error 0
  html     tests  20  extracted  13  claims  18  python pass 18 fail 0 error 0
  minimal  tests  14  extracted   4  claims   4  python pass 4 fail 0 error 0
  python   tests  26  extracted  20  claims  35  python pass 35 fail 0 error 0
  rust     tests  24  extracted  15  claims  30  python pass 30 fail 0 error 0
  sql      tests  15  extracted  10  claims  18  python pass 18 fail 0 error 0
  tsjs     tests  19  extracted  11  claims  20  python pass 20 fail 0 error 0
  php      tests  41  extracted  27  claims  50  python pass 50 fail 0 error 0
```

## Command 3

`python rewrite/truth/tools/score.py --cmd "python -m omitnix" --from-tests --json /workspace/shared/omitnix-truth-evidence/score-1.json`

Exit: 0; elapsed 3.317 seconds.

```text
synthetic: extraction presence only; provenance/lines/candidate certainty unscored
synthetic: files missing from the index: 0
unknown files: 0; unclaimed files: 0
group                          files  recall d0/d1/d2/d3        <=3 recall  <=3 prec  leaks
all                              186  61.0%/13.3%/0.0%/0.0%     48.8%   97.5%  0
set:must                         179  62.2%/13.3%/0.0%/0.0%     49.1%   97.4%  0
set:reference                      7  40.0%/n/a/n/a/n/a         40.0%  100.0%  0
tag:defect:backtick_placeholder     3  n/a/n/a/n/a/n/a          n/a    0.0%  0
tag:defect:php_escape              1  0.0%/n/a/n/a/n/a           0.0%  n/a  0
tag:defect:plain_ddl_command       6  11.6%/n/a/n/a/n/a         11.6%  100.0%  0
tag:limit:depth                   12  100.0%/100.0%/0.0%/0.0%   54.5%  100.0%  0
tag:limit:no_import_follow        17  66.7%/0.0%/0.0%/0.0%      23.5%  100.0%  0
honesty all: any_table 3/6, candidates_gap_disclosed 11/12, unreadable_broken 5/5, unreadable_dynamic 5/5
honesty set:must: any_table 3/6, candidates_gap_disclosed 11/12, unreadable_broken 5/5, unreadable_dynamic 5/5
honesty set:reference:
from-tests: 178/178 claims pass (100.0%); skipped 14
```

## Command 4

`python -m pytest`

Exit: 0; elapsed 7.425 seconds.

```text
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
rootdir: /workspace/shared/omitnix-truth-review-work
configfile: pyproject.toml
testpaths: tests
collected 404 items

tests/test_adapter_go.py .................                               [  4%]
tests/test_adapter_html.py ....................                          [  9%]
tests/test_adapter_minimal.py ...................                        [ 13%]
tests/test_adapter_python.py ..........................                  [ 20%]
tests/test_adapter_rust.py ........................                      [ 26%]
tests/test_adapter_sql.py ...............                                [ 29%]
tests/test_adapter_tsjs.py .......................                       [ 35%]
tests/test_analyze.py .........................                          [ 41%]
tests/test_cli.py ........................                               [ 47%]
tests/test_config.py .......                                             [ 49%]
tests/test_determinism.py .....                                          [ 50%]
tests/test_gate.py .....................................s                [ 60%]
tests/test_globs.py .................                                    [ 64%]
tests/test_install_hints.py ..................                           [ 68%]
tests/test_output.py .........                                           [ 71%]
tests/test_php_adapter.py .........................................      [ 81%]
tests/test_reasons.py ....                                               [ 82%]
tests/test_registry.py .......                                           [ 83%]
tests/test_render.py ...........                                         [ 86%]
tests/test_workspace.py ......................................           [ 96%]
tests/test_workspace_status.py ................                          [100%]

======================== 403 passed, 1 skipped in 7.10s ========================
```

## Command 5

`python -m pytest rewrite/truth/tests`

Exit: 0; elapsed 0.351 seconds.

```text
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
rootdir: /workspace/shared/omitnix-truth-review-work
configfile: pyproject.toml
collected 73 items

rewrite/truth/tests/test_extract.py ..                                   [  2%]
rewrite/truth/tests/test_score.py ...................................... [ 54%]
.................................                                        [100%]

============================== 73 passed in 0.09s ==============================
```

## Command 6

`python -m ruff check rewrite/truth/tools rewrite/truth/tests`

Exit: 0; elapsed 0.04 seconds.

```text
All checks passed!
```

## Command 7

`python rewrite/truth/tools/score.py --cmd "python -m omitnix" --from-tests --json /workspace/shared/omitnix-truth-evidence/score-2.json`

Exit: 0; elapsed 3.577 seconds.

```text
synthetic: extraction presence only; provenance/lines/candidate certainty unscored
synthetic: files missing from the index: 0
unknown files: 0; unclaimed files: 0
group                          files  recall d0/d1/d2/d3        <=3 recall  <=3 prec  leaks
all                              186  61.0%/13.3%/0.0%/0.0%     48.8%   97.5%  0
set:must                         179  62.2%/13.3%/0.0%/0.0%     49.1%   97.4%  0
set:reference                      7  40.0%/n/a/n/a/n/a         40.0%  100.0%  0
tag:defect:backtick_placeholder     3  n/a/n/a/n/a/n/a          n/a    0.0%  0
tag:defect:php_escape              1  0.0%/n/a/n/a/n/a           0.0%  n/a  0
tag:defect:plain_ddl_command       6  11.6%/n/a/n/a/n/a         11.6%  100.0%  0
tag:limit:depth                   12  100.0%/100.0%/0.0%/0.0%   54.5%  100.0%  0
tag:limit:no_import_follow        17  66.7%/0.0%/0.0%/0.0%      23.5%  100.0%  0
honesty all: any_table 3/6, candidates_gap_disclosed 11/12, unreadable_broken 5/5, unreadable_dynamic 5/5
honesty set:must: any_table 3/6, candidates_gap_disclosed 11/12, unreadable_broken 5/5, unreadable_dynamic 5/5
honesty set:reference:
from-tests: 178/178 claims pass (100.0%); skipped 14
```

## Command 8

`python rewrite/truth/tools/audit_population.py --check`

Exit: 0; elapsed 0.087 seconds.

```text
audit population up to date
```

## Determinism

Both external score outputs have SHA-256 `91988addb61a8c6f4195edab83463bc661d9b10183ff62a6d63cbcb3eb8e6fe1`; byte comparison passed.

Original score JSON SHA-256: `fc3eca0a811d5ffd303a91f52131150298cb43e4c3f3ba22857d992503ac65fd`.

Additional checks: `git diff --check`, `node scripts/check-claude-md.mjs`, and `python -m ruff check .` all exited 0. The staged structural secrets scan passed; KB_ROOT and FAMILY_ROOT were unavailable, so private-name watchlists were not run. No sensitive fixture data was introduced.

These required commands were rerun after the independent R1 field-state fix; focused tests now include 16 additional positive/negative state/payload controls.
