# #20261005-008: why Python finds 118 of 242 synthetic pairs

## Result and decision boundary

The measured baseline is **118/242 (48.76%)**, including **114/232 required pairs
(49.14%)** and **4/10 reference pairs (40.00%)**. There are **124 misses and 3 false
positives**. `MISSES.csv` contains exactly those 127 distinct rows. No product,
truth, scorer, dependency declaration, or CI file was changed.

The principal finding is that the benchmark asks for both missing implementation
work and behavior deliberately outside the current adapters' scope. With the
existing denominators and all non-B misses hypothetically recovered, the ceiling
is **161/232 required (69.40%)**, or **171/242 overall (70.66%)**. Consequently,
**95% of the required set is not reachable without changing some B scope**.

Scope expansion alone is also insufficient: even recovering every A and B miss
while leaving all E misses gives **216/232 (93.10%)**. At least five of the 16
required dependency-limited misses must also be recovered. The owner chooses
whether to expand the product, redefine the acceptance population in a later
explicit policy change, or both. This report makes neither change.

Every recovery below is an **estimate for an unimplemented complete fix bundle**,
not a new measured recall. Direct probes establish which layer rejects an input;
they are not end-to-end patched-product measurements. No improved score is claimed.

## Provenance and method

- Instruction / diff baseline: `cd819366abda0025e1c40efafa128d9767a71531`.
- Product, scorer and truth baseline: main `3feb28dc5a57e1609e0923f972980131fd7f392b`.
- Execution checkout initially equals the instruction SHA. An exact Git diff of
  `omitnix`, `rewrite/truth`, and `pyproject.toml` between those SHAs is empty.
  The instruction commit changes its three task documents and the existing
  inventory only; it is not a correctness oracle.
- Work branch: `dots/truth-miss-triage-20261005-008`; PR target:
  `dots/truth-miss-triage`. No merge or release.
- Only the public synthetic corpus was used. The five rewrites were not fetched,
  run, or inferred to have identical individual misses. Python's measured causes
  are the intended common-cause investigation, not six new measurements.

For each affected case, the investigator read its source first (including all
companion files for a call chain), then its answer convention, then the retained
product record, then the adapter / SQL reader. The ledger is populated from the
scorer's missing/extra key set only after that source-based judgment. Source
lines, adapter locations, primary cause, and actual disclosure are retained per
row. Each miss has exactly one primary class even when multiple layers must
change. Secondary blockers appear in the proposal and evidence, not duplicate
recovery counts.

The retained corpus copy and output index live outside the repository. Passing
that retained index through the unchanged `score_synthetic` function exactly
matches the first baseline JSON. The independent reviewer separately reproduced
two runs. Fixed-revision review details accompany the submission; see
`INDEPENDENT_REVIEW.md` and the PR's final-SHA verification receipt.

### Runtime and commands

Python **3.12.14**, pip **25.0.1** in the scratch virtual environment,
pytest **9.1.1**, PyYAML **6.0.3**, sqlglot **30.21.0**, tree-sitter **0.26.0**;
grammars: PHP **0.24.1**, Python **0.25.0**, Go **0.25.0**, Rust **0.24.2**,
TypeScript **0.23.2**, JavaScript **0.25.0**, HTML **0.23.2**. Git **2.52.0**,
Node **24.19.0**. The declared unpinned dependency floors resolve to these versions.
No attempt was made to retrofit the older sqlglot version into the baseline.

Commands below ran from the repository root. `$VENV` and `$OUT` denote separate
scratch directories **outside the repository**, not real home paths.

| Command | Exit | Observed result |
|---|---:|---|
| `python --version` | 0 | Python 3.12.14 |
| `python -m pip install -e ".[dev]"` before creating the venv | 1 | Packages were obtainable, but final installation failed: `OSError: [Errno 30] Read-only file system: '~/.local/lib'` |
| `python -m venv "$VENV"` | 0 | Isolated writable environment created |
| `"$VENV/bin/python" -m pip install -e ".[dev]"` | 0 | Same declared dependencies installed; no new credentials or undeclared package needed |
| `export PATH="$VENV/bin:$PATH"; python rewrite/truth/tools/make_synthetic.py --check` | 0 | `up to date: 189 files` |
| `python rewrite/truth/tools/score.py --cmd "python -m omitnix" --json "$OUT/score-1.json"` | 0 | 118/242; 114/232 required; 3 FP |
| `python rewrite/truth/tools/score.py --cmd "python -m omitnix" --json "$OUT/score-2.json"` | 0 | Same result |
| `cmp "$OUT/score-1.json" "$OUT/score-2.json"` | 0 | Byte-identical |
| `cp -a rewrite/truth/synthetic/corpus "$OUT/corpus"; python -m omitnix --all-files --root "$OUT/corpus"` | 0 | Retained product index; independently compared to first score |
| `python -m pytest -p no:cacheprovider tests rewrite/truth` | 1 | Initial over-broad collection: 477 passed, 1 skipped, 1 error; synthetic input `test_orders.py` needs fictional `fake_db` fixture |
| `python -m pytest -p no:cacheprovider tests rewrite/truth/tests` | 0 | Correct test directories: 476 passed, 1 skipped; no fixture/source edit |
| `python -m pytest -q -rs -p no:cacheprovider tests rewrite/truth/tests` at corrected analysis SHA `066464fa30b805ef1f3553aa4f80df3f6058994d` | 0 | 476 passed, 1 skipped: `tests/test_gate.py:747`, semgrep is not installed |
| `python -m ruff --version` | 1 | Ruff absent locally. No undeclared dependency installed; CI's existing lint job is reported separately |
| `python docs/bot/truth-miss-triage/scripts/audit_ledger.py --score-json "$OUT/score-1.json"` | 0 | Exact population, metadata, class/group totals and projections validated |
| `python docs/bot/truth-miss-triage/scripts/probe_sql_layers.py --output "$OUT/probes.json"` | 0 | 30 public source files and quoted-placeholder diagnostic; no mutation |
| `git diff --check` | 0 | Whitespace check passed |
| `node scripts/secrets-scan.mjs --staged --block` | 0 | Structural scan; private watchlists unavailable |

Both score files have SHA-256:
`1fecbb6a164c1c726ea70ac1c34db6770d1aaf70f098b2656d816204092d45a8`.
The separate reviewer obtained the same hash. Scorer exit 0 means scoring ran,
not that Python achieved the threshold. CI status and the exact final review SHA
are recorded with the submitted PR; this report does not imply a green aggregate CI.

## Re-derived population

| Category | Found / expected | Misses |
|---|---:|---:|
| ddl | 5/43 | 38 |
| dynamic_table | 0/28 | 28 |
| call_depth_1 | 6/10 | 4 |
| call_depth_2 | 6/15 | 9 |
| call_depth_3 | 6/20 | 14 |
| call_depth_4 | 6/20 | 14 |
| dialect | 2/7 | 5 |
| write | 23/27 | 4 |
| escape | 0/4 | 4 |
| query_builder | 0/2 | 2 |
| unsupported | 0/1 | 1 |
| comment | 16/17 | 1 |

All other categories have no missed expected pair. By expected depth the result
is d0 **114/187**, d1 **4/30**, d2 **0/15**, d3 **0/10**. The tag
`limit:depth` is **6/11**, and `limit:no_import_follow` is **4/17**. The latter
is a Python-specific tag, not the complete set of cross-file limitations.

One correction to the instruction's pointer table: the **escape category** has
four misses, but **`defect:php_escape` has only two**. The remaining escaped-string
misses are Python and TypeScript. The `call_depth_4` category does not require
four-hop extraction: its intermediate files contain required depths 1–3; the
five actual depth-4 answers are neutral `beyond_depth` entries.

### Primary classes

| Class | Required misses | Reference misses | All misses | False positives |
|---|---:|---:|---:|---:|
| A: product defect | 31 | 5 | 36 | 3 |
| B: scope limit by design | 71 | 0 | 71 | 0 |
| C: answer questionable | 0 | 0 | 0 | 0 |
| D: scorer defect | 0 | 0 | 0 | 0 |
| E: dependency limitation | 16 | 1 | 17 | 0 |
| Total | 118 | 6 | 124 | 3 |

A B classification describes why the table is not extracted. It does **not** excuse
missing disclosure. Of 71 B misses, 21 have an attributable reason and **50 have
no relevant reason**. Those 50 include all 41 chain misses, eight non-PHP argument
callers, and the TypeScript builder. PHP's five depth-2/3 misses also lack the
promised `indirect_call_depth`: its second-hop detector only knows definitions
from the current and first included file, not the next include. A disclosure-only
repair would recover **zero table pairs** and must not be sold as increased recall.

## Countermeasures by shared root cause

The following proposals name complete bundles. Counts are distinct missed ledger
rows, not statement counts. A table appearing as both read and write in one file
can legitimately contribute two rows. Groups are ordered by total estimated
recoveries; ties use group ID. Precision risks are prospective, not measured.

| Group / primary class | Estimated recovered total (required + reference) | Layer, proposed bundle | Precision / honesty risk; policy decision |
|---|---:|---|---|
| `B_CALL_PROPAGATION` / B | **41 (41 + 0)** | `php.py:430–515`, `python.py:6–11`, `go.py:6–8,80–101`, `rust.py:17–18,336–357`, `tsjs.py:171–193`: resolve actual calls within the scan and propagate concrete SQL tables through a bounded three-hop graph, with cycle/ambiguity handling. Includes 25 depth-2/3 and 16 non-PHP depth-1 rows. | High risk of attributing every imported function or similarly named function in another case. Preserve unresolved ambiguity and depth boundaries; **owner must approve scope expansion**. |
| `A_DDL_GATE` / A | **27 (26 + 1)** | `_sql.py:33–45,98–102,157–162`, host adapter harvesters: admit precise CREATE/ALTER/DROP shapes to sqlglot, and restrict DDL target traversal so nested foreign-key targets are not writes. | Existing helper finds all27 expected pairs on the same captured literals, but gate-only admission adds a false write to FK target orders. No scope expansion for definite DDL targets; optional FK-read policy remains owner's choice. |
| `B_ARGUMENT_TABLE` / B | **20 (20 + 0)** | `_extract.py:183–220`, `php.py:104–151,430–474`, language adapters/call resolver: bind proven literal call arguments to callee SQL holes; emit per-caller tables and the explicitly scoped callee union. | Ten own + ten via rows; eight non-PHP callers also need graph support from the preceding graph group. Unknown callers, aliasing and dispatch must remain unresolved; **owner must approve value-flow and attribution scope**. |
| `E_OPAQUE_COMMAND` / E | **13 (13 + 0)** | sqlglot AST support; `_sql.py:33–45,114–120,138–164,194–199`, `php.py:262–282`: support RENAME and REPLACE ASTs, map targets, admit embedded RENAME, propagate unsupported reasons in PHP. | Twelve RENAME pairs + one REPLACE; ten RENAME pairs also need the opener gate. Current helper recovers zero on unchanged inputs. No tested newer dependency is promised; no regex SQL parser. No declared scope widening, but dependency solution is unimplemented. |
| `B_STATIC_TABLE_VALUE` / B | **8 (8 + 0)** | `_extract.py:183–220`, `php.py:104–151`, language string shapes: conservative same-file constant/value propagation and literal-return helper resolution, retaining uncertainty for mutable or unresolved expressions. | Five named constants, one class attribute, two wrapped return literals. Attribute rebinding, subclassing and side effects make blind evaluation unsafe. **Owner must approve narrower provable-value scope**. |
| `A_HOST_ESCAPE` / A | **4 (4 + 0)** | `php.py:63,104–151`, `_extract.py:183–220`, `python.py:49–54`, `tsjs.py:67–73`: decode constant host literal values according to language and literal kind before SQL parsing. | Semantic-literal helper probes find four; raw strings, interpolation and SQL-level escaping must not be over-decoded. No owner scope change. |
| `A_MERGE_GATE_MODE` / A | **4 (0 + 4)** | `_sql.py:33–45,98–102,150–164`: admit MERGE and classify the existing Merge AST target as write and USING tables as reads. | Gate-only bypass finds two source reads, misses two writes and invents two wrong-mode reads. No integration scope expansion; owner decides future reference-dialect guarantee. |
| `E_NUMBERED_PARAMETER` / E | **3 (3 + 0)** | sqlglot parameter grammar / `_sql.py:105–121`: add SQLite numbered-placeholder support upstream or rigorously token-aware parameter normalization. | Direct SQLite dialect also rejects `?1`. Replacing it with `?` recovers three only on altered diagnostic inputs; naive replacement could change quoted data. Retain unreadable reasons. No owner scope expansion. |
| `B_QUERY_BUILDER` / B | **2 (2 + 0)** | `rust.py:280–318`, `tsjs.py:171–193` and language queries: recognize a bounded set of genuine Diesel/Knex operations and their explicit table arguments or schema symbols. | Schema declarations are not queries; arbitrary methods with similar names must not produce tables. Rust already discloses; TS does not. **Owner must approve builder capability**, despite the truth convention already counting these calls. |
| `A_HEREDOC_GAPS` / A | **1 (1 + 0)** | `php.py:126–138`, `queries/php.scm:49`: preserve source byte gaps/newlines when reconstructing heredoc/nowdoc bodies and interpolation holes. | Named-node joining creates `idFROM` and joins a line comment into the next line. Verbatim-body helper finds orders without leaking coupons. Spaces alone are insufficient; no regex comment stripping. No policy change. |
| `E_CLIENT_SCRIPT` / E | **1 (0 + 1)** | sqlglot client-script parsing; `sql.py:76–85,132–144`, `_sql.py:150–164,202–211`: parse DELIMITER/script structure, classify nested DML, and exclude procedure names from table targets. | Removing client directives alone emits read orders / write close_orders, both wrong for the expected body write. Parser-backed handling needed; owner chooses reference-script priority. No explicit exclusion justified class B. |

The 12 RENAME pairs and one REPLACE pair share opaque-command parsing as their
primary blocker. PHP additionally drops opaque-command disclosure, which is a
secondary A honesty defect but yields no separate recall credit. None of the E
rows here was assigned solely because its case was named `unsupported`.

Layer diagnostics are deliberately separated: the unchanged helper accepts the
27 DDL pair-bearing literals, the four decoded semantic escape values and the
one verbatim heredoc body; MERGE exposes two expected reads but not its two writes.
These observations show the relevant blockers. They do not constitute measured
recoveries from a repaired product or justify summing diagnostic and proposal counts.

### Cumulative projections on unchanged denominators

| Applied group | Cumulative required / 232 | Required recall | Cumulative total / 242 | Total recall |
|---|---:|---:|---:|---:|
| Baseline (measured) | 114 | 49.14% | 118 | 48.76% |
| `B_CALL_PROPAGATION` | 155 | 66.81% | 159 | 65.70% |
| `A_DDL_GATE` | 181 | 78.02% | 186 | 76.86% |
| `B_ARGUMENT_TABLE` | 201 | 86.64% | 206 | 85.12% |
| `E_OPAQUE_COMMAND` | 214 | 92.24% | 219 | 90.50% |
| `B_STATIC_TABLE_VALUE` | 222 | 95.69% | 227 | 93.80% |
| `A_HOST_ESCAPE` | 226 | 97.41% | 231 | 95.45% |
| `A_MERGE_GATE_MODE` | 226 | 97.41% | 235 | 97.11% |
| `E_NUMBERED_PARAMETER` | 229 | 98.71% | 238 | 98.35% |
| `B_QUERY_BUILDER` | 231 | 99.57% | 240 | 99.17% |
| `A_HEREDOC_GAPS` | 232 | 100.00% | 241 | 99.59% |
| `E_CLIENT_SCRIPT` | 232 | 100.00% | 242 | 100.00% |


These sums are a conditional coverage budget: every group's full proposal and
listed prerequisite must work without regressing an existing hit. There is no
patched implementation, therefore no confidence interval or measured uplift.
The first five groups reach the required target in this ordering, **222/232
(95.69%)**, exceeding the minimum 221 pairs and leaving 10 required misses. That plan includes both
significant B scope expansion and the dependency-limited RENAME/REPLACE bundle.

Alternative bounds useful for the owner's decision:

- Recover all non-B misses: **161/232 required**, **171/242 overall**. Not 95%.
- Recover all A and B misses, none of E: **216/232 required**, **225/242 overall**.
  Still not 95%; at least five required E rows must improve.
- Leave all 25 depth-2/3 rows outside scope, even recovering everything else:
  **207/232 required (89.22%)**.
- Leave all 28 dynamic-name rows outside scope: **204/232 required (87.93%)**.
- Leave all 16 literal one-hop cross-file rows unsupported:
  **216/232 required (93.10%)**.
- With all proposals successful: **232/232 required and 242/242 overall** is the
  ledger's arithmetic upper bound, **not a validated attainable release result**.

### Overlap, prerequisites and precision

The call-propagation group contains only the 41 call-chain misses: 25 at expected depths
2–3 and 16 at depth 1. The argument group contains exactly 20 other rows: ten
callee-own expectations and ten callers' depth-1 expectations. They share graph
infrastructure with the call-propagation group but never share ledger rows. The dynamic
static-value group contains eight separate same-file rows. An implementation
should reuse machinery, not add these counts again for each shared component.

Widening the embedded-SQL opener gate alone does not recover every DDL miss:
RENAME still becomes an opaque parser command; MERGE additionally needs correct
target classification. Those rows belong to their own full-bundle groups, not
both the opener group and a second parser group. New tables exposed by a broader
gate can also reveal mode/precision defects (especially foreign-key references
and stored-procedure names); recovered recall must be remeasured together with
precision, not accepted in isolation.

The three false positives form separate group `A_QUOTED_PLACEHOLDER_FP`:
`php09_backtick_any`, `php10_backtick_array_loop`, and `py10_external_table`.
Interpolated holes are padded with spaces; sqlglot preserves padding inside
backticks. `_sql.py:204–211` compares that padded name to the unpadded sentinel,
then emits it as a table. Product field normalization in `omitnix/analyze.py:109`
strips padding before index serialization; the scorer subsequently normalizes
the already-unpadded spelling and correctly counts it as an extra. A focused probe reports `reads=(' omitnix_placeholder ',)`
and `dynamic_table=False`; the unpadded quoted form reports no table and
`dynamic_table=True`. Proposal: preserve explicit hole identity through SQL
extraction, suppress only the synthetic hole, and emit `dynamic_table_name`.
Do not indiscriminately trim valid quoted SQL identifiers. Estimate: **three FP
removed, zero missed pairs recovered**; unchanged hits would give 118/118
precision, but this is not a measured fixed-product result. No owner scope
expansion is needed for honest placeholder handling.

## Scope tension, truth and scoring

The current project explicitly excludes two or more indirect hops
(`CLAUDE.md:23`). Python and Go describe no import following; Rust says nothing
is followed into another file; TypeScript's analyzer processes only the local
parse. PHP follows one include/call hop. In contrast, the truth convention
requires each caller's concrete tables through depth 3. There are **25 missing
pairs directly requiring depth-2/3 expansion**, another **16** requiring currently
unsupported one-hop propagation, and **28** requiring static or argument value
resolution. Two more require query-builder support. These are quantified policy
choices, not evidence that the answer set should be silently lowered.

The dynamic argument convention is explicit: the callee gets the tables fixed
by known call sites as `own` with `certainty: traced`, while each caller gets its
own depth-1 `via`. All five fixture families were read together. That convention
may be a poor fit for an open-world program with unknown callers, but it is not
an erroneous answer under this fixed synthetic corpus. A wider product must
retain unknown-callsite uncertainty rather than guessing a complete union.
Likewise, the eight fixed same-file values need conservative value evaluation;
mutable attributes, rebinding, dynamic dispatch, and arbitrary helper execution
must stay unresolved when not provable.

No C or D primary cause was established. The source/answer review retains the
published conventions for DDL writes, CREATE LIKE source reads, builder calls,
and call-site attribution. The only scored FK expectation is the definite
CREATE target write; the FK target read is deliberately left unscored.
Reference-set choices such as MERGE, foreign-key relationships and procedure bodies remain reference choices; moving them to
must or deleting them was not proposed as a recall fix.

The scorer credits normalized unique `(file, mode, table)` presence, not source
lines, call provenance or certainty. Its `candidates` and explained unresolved
entries are **gap disclosure, not extraction hits**. Turning those entries into
true positives would change the metric, not fix a scorer defect. No acceptable
concrete product table was found hidden by normalization/status handling.
The three placeholder extras are real product-output errors, not normalization
errors in the scorer. Scorer/source-line and depth-provenance limits remain; no
new claim of provenance validation is made by matching a table name.

## What was not examined or changed

- No private repository, real schema, real application code or production data.
- No five-rewrite checkout, new six-way scoring, performance comparison or patch.
- No corpus/answer regeneration, scoring-result replacement, metric relaxation,
  dependency pin change, CI change, or inventory refresh.
- No executing the fixture programs as applications. Their incomplete imports,
  stub connections, and deliberately malformed inputs are static-analysis data.
- No broad sqlglot upgrade search or installation; E proposals are limited to
  the observed version/input boundary and require separate implementation work.
- No assertion that tree-sitter caused these misses: affected records parsed;
  the observed E blockers here are SQL parsing limits.
- No owner's local different-product full-line review. That remains pending,
  separately from the independent worker review.
- No local Ruff result. Its absent module was recorded without expanding the
  declared install. The existing PR lint check is a separate verification source.
- No full private-watchlist secret audit; only the repository's available
  structural scanner and manual review of public synthetic material.

The scoped investigation is reviewable without deciding the 95% product scope.
The owner's policy and fix-order decision remains the next step.
