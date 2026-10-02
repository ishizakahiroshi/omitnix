# SQL behavior corpus

This corpus records 534 synthetic SQL strings passed to
`omitnix/adapters/_sql.py:read_sql` at commit `9311c9c8334ed74808e374aecf0cb2fb13534307`,
using exactly sqlglot `30.18.0`.
It records observed behavior, including surprising or unsupported results;
it is not an assertion of SQL validity or an ideal parser specification.

## Reproduce

Run from the repository root with Python 3.11 or newer:

```sh
python -m pip install -r rewrite/sqlbehavior/requirements.txt pytest ruff==0.16.2
python rewrite/sqlbehavior/make_cases.py
python rewrite/sqlbehavior/make_cases.py --check
python -m pytest rewrite/sqlbehavior rewrite/tools
python -m ruff check .
```

The generator refuses a different sqlglot version or different reference source.
It writes only cases.json and this README; --check writes nothing.
--output-dir DIR records into a separate directory for byte comparisons.

## Data contract

Each case contains id, category, sql, reads, writes, parsed, select_star,
dynamic_table, and unsupported. The last field is the reference integer count.
reads/writes are the reference tuples converted directly to JSON arrays.
Only read_sql produces outcomes. No parser, dialect override, SQL normalization,
salvage loop, exception-to-result conversion, or expected-value inference is added.
A multi-statement input is passed as one whole string, just like any other case.
Unsupported commands and parse failures are retained as observations.

Cases are ordered by category, template number, and object-name rotation.
Identifiers use orders/customers/invoices and synthetic columns; the adapter's
omitnix_placeholder sentinel is included explicitly to exercise dynamic_table.
No database connection or SQL execution is involved.
JSON uses two-space indentation, literal Unicode, LF, and a final newline.
No timestamps, machine paths, or environment-dependent commit lookups are recorded.

## Category summary

All columns count cases; unsupported >= 1 counts cases, not opaque statements.
parsed=true and unsupported >= 1 can overlap. Empty reads/writes do not prove
that a SQL string touches no tables; consult parsed and unsupported too.

| category | n | parsed=true | unsupported>=1 | parsed=false | nonempty reads | nonempty writes |
|---|---:|---:|---:|---:|---:|---:|
| alter_add_column | 6 | 6 | 0 | 0 | 0 | 6 |
| alter_change | 6 | 6 | 6 | 0 | 0 | 0 |
| alter_constraint | 6 | 6 | 3 | 0 | 3 | 3 |
| alter_drop_column | 6 | 6 | 0 | 0 | 0 | 6 |
| alter_engine | 6 | 6 | 6 | 0 | 0 | 0 |
| alter_modify | 6 | 6 | 6 | 0 | 0 | 0 |
| alter_owner | 6 | 6 | 6 | 0 | 0 | 0 |
| alter_rename | 6 | 6 | 0 | 0 | 3 | 6 |
| alter_rls | 6 | 6 | 6 | 0 | 0 | 0 |
| alter_trigger | 6 | 6 | 6 | 0 | 0 | 0 |
| analyze | 6 | 6 | 0 | 0 | 6 | 0 |
| column_fragment | 5 | 1 | 0 | 4 | 0 | 0 |
| comment_on | 6 | 6 | 0 | 0 | 3 | 0 |
| create_extension | 6 | 6 | 6 | 0 | 0 | 0 |
| create_index | 6 | 6 | 0 | 0 | 0 | 6 |
| create_policy | 6 | 6 | 6 | 0 | 0 | 0 |
| create_role | 6 | 6 | 6 | 0 | 0 | 0 |
| create_schema | 6 | 6 | 3 | 0 | 0 | 0 |
| create_sequence | 6 | 6 | 0 | 0 | 0 | 6 |
| create_table | 12 | 12 | 0 | 0 | 3 | 12 |
| create_trigger | 6 | 6 | 3 | 0 | 3 | 0 |
| create_type | 6 | 6 | 6 | 0 | 0 | 0 |
| create_view | 6 | 6 | 0 | 0 | 6 | 6 |
| deallocate | 6 | 3 | 0 | 3 | 0 | 0 |
| delete | 9 | 9 | 0 | 0 | 3 | 9 |
| drop | 33 | 33 | 12 | 0 | 0 | 18 |
| dynamic_table | 10 | 10 | 0 | 0 | 9 | 0 |
| execute | 6 | 6 | 6 | 0 | 0 | 0 |
| explain | 6 | 6 | 6 | 0 | 0 | 0 |
| fullwidth | 12 | 6 | 0 | 6 | 6 | 0 |
| grant_all_tables | 6 | 6 | 6 | 0 | 0 | 0 |
| grant_function | 6 | 6 | 0 | 0 | 0 | 0 |
| grant_named_function | 6 | 6 | 6 | 0 | 0 | 0 |
| grant_schema | 6 | 6 | 3 | 0 | 3 | 0 |
| grant_table | 6 | 6 | 3 | 0 | 3 | 0 |
| insert | 12 | 12 | 0 | 0 | 6 | 12 |
| joins | 9 | 9 | 0 | 0 | 9 | 0 |
| leading_comments | 9 | 9 | 0 | 0 | 6 | 3 |
| lock | 6 | 0 | 0 | 6 | 0 | 0 |
| multistatement | 12 | 9 | 3 | 3 | 9 | 3 |
| mysql_backticks | 6 | 6 | 0 | 0 | 3 | 3 |
| mysql_limit | 9 | 9 | 0 | 0 | 3 | 6 |
| mysql_multi_update | 6 | 6 | 0 | 0 | 6 | 6 |
| mysql_on_duplicate | 6 | 6 | 0 | 0 | 3 | 6 |
| near_blank | 7 | 0 | 0 | 7 | 0 | 0 |
| placeholders | 16 | 12 | 0 | 4 | 12 | 0 |
| plpgsql_assignment | 5 | 5 | 0 | 0 | 3 | 0 |
| postgres_cast | 6 | 6 | 0 | 0 | 6 | 0 |
| postgres_for_update | 6 | 6 | 0 | 0 | 6 | 0 |
| postgres_interval | 6 | 6 | 0 | 0 | 6 | 0 |
| postgres_on_conflict | 6 | 6 | 0 | 0 | 0 | 6 |
| postgres_returning | 9 | 9 | 0 | 0 | 0 | 9 |
| prepare | 6 | 6 | 6 | 0 | 0 | 0 |
| procedural_block | 11 | 8 | 4 | 3 | 0 | 0 |
| prose | 5 | 2 | 0 | 3 | 2 | 1 |
| return_new | 3 | 2 | 0 | 1 | 0 | 0 |
| revoke_all_tables | 6 | 6 | 6 | 0 | 0 | 0 |
| revoke_function | 6 | 6 | 0 | 0 | 0 | 0 |
| revoke_named_function | 6 | 6 | 6 | 0 | 0 | 0 |
| revoke_schema | 6 | 6 | 3 | 0 | 3 | 0 |
| revoke_table | 6 | 6 | 3 | 0 | 3 | 0 |
| select | 16 | 16 | 0 | 0 | 15 | 0 |
| sqlite_ignore | 6 | 6 | 0 | 0 | 3 | 6 |
| subquery | 9 | 9 | 0 | 0 | 9 | 0 |
| truncate | 6 | 6 | 0 | 0 | 0 | 6 |
| truncated_insert | 9 | 6 | 0 | 3 | 0 | 6 |
| unclosed_parenthesis | 9 | 0 | 0 | 9 | 0 | 0 |
| union | 9 | 9 | 0 | 0 | 9 | 0 |
| update | 9 | 9 | 0 | 0 | 3 | 9 |
| vacuum | 6 | 6 | 6 | 0 | 0 | 0 |
| with | 9 | 9 | 0 | 0 | 6 | 3 |

## Empirical boundaries

These 16 observations describe only the recorded cases. Category names and
case IDs refer to the table above and cases.json; they are not blanket grammar rules.

1. Projection star versus COUNT(*): `select.02.1`: reads=['orders'], writes=[], parsed=true, select_star=true, dynamic_table=false, unsupported=0; `select.04.1`: reads=['orders'], writes=[], parsed=true, select_star=false, dynamic_table=false, unsupported=0
2. One name on both sides of INSERT: `insert.03.1`: reads=['orders'], writes=['orders'], parsed=true, select_star=false, dynamic_table=false, unsupported=0
3. CTE aliases and a shadowed base name: `with.01.1`: reads=['orders'], writes=[], parsed=true, select_star=false, dynamic_table=false, unsupported=0; `with.03.1`: reads=[], writes=[], parsed=true, select_star=false, dynamic_table=false, unsupported=0
4. CREATE targets and source reads: `create_view.01.1`: reads=['orders'], writes=['invoices'], parsed=true, select_star=false, dynamic_table=false, unsupported=0; `create_index.01.1`: reads=[], writes=['orders'], parsed=true, select_star=false, dynamic_table=false, unsupported=0
5. Other CREATE objects (`create_schema`, `create_type`, `create_role`): 18/18 parsed; 15 parsed with unsupported >= 1; 0 have reads; 0 have writes
6. Administrative ALTER (`alter_owner`, `alter_rls`, `alter_trigger`): 18/18 parsed; 18 parsed with unsupported >= 1; 0 have reads; 0 have writes
7. Constraint and dialect ALTER (`alter_constraint`, `alter_modify`, `alter_change`, `alter_engine`): 24/24 parsed; 21 parsed with unsupported >= 1; 3 have reads; 3 have writes
8. DROP and TRUNCATE (`drop`, `truncate`): 39/39 parsed; 12 parsed with unsupported >= 1; 0 have reads; 24 have writes
9. Table/schema privileges (`grant_table`, `grant_all_tables`, `grant_schema`, `revoke_table`, `revoke_all_tables`, `revoke_schema`): 36/36 parsed; 24 parsed with unsupported >= 1; 12 have reads; 0 have writes
10. Function privilege signatures (`grant_function`, `grant_named_function`, `revoke_function`, `revoke_named_function`): 24/24 parsed; 12 parsed with unsupported >= 1; 0 have reads; 0 have writes
11. Command classifications (`comment_on`, `lock`, `vacuum`, `analyze`, `explain`, `prepare`, `execute`, `deallocate`): 39/48 parsed; 24 parsed with unsupported >= 1; 9 have reads; 0 have writes
12. Procedural and fragment boundaries (`procedural_block`, `plpgsql_assignment`, `return_new`, `column_fragment`): 16/24 parsed; 4 parsed with unsupported >= 1; 3 have reads; 0 have writes
13. Vendor syntax (`mysql_backticks`, `mysql_on_duplicate`, `mysql_limit`, `mysql_multi_update`, `postgres_cast`, `postgres_returning`, `postgres_for_update`, `postgres_interval`, `postgres_on_conflict`, `sqlite_ignore`): 66/66 parsed; 0 parsed with unsupported >= 1; 36 have reads; 42 have writes
14. Run-time table hole versus value text: `dynamic_table.02.1`: reads=['orders'], writes=[], parsed=true, select_star=false, dynamic_table=true, unsupported=0; `dynamic_table.04.1`: reads=['orders'], writes=[], parsed=true, select_star=false, dynamic_table=false, unsupported=0
15. Whole-string parsing (`multistatement`, `truncated_insert`, `unclosed_parenthesis`): 15/30 parsed; 3 parsed with unsupported >= 1; 9 have reads; 9 have writes
16. Input text is passed through unchanged (`placeholders`, `fullwidth`, `leading_comments`, `near_blank`, `prose`): 29/49 parsed; 0 parsed with unsupported >= 1; 26 have reads; 4 have writes

## Maintenance

Edit templates, regenerate both artifacts, and inspect the resulting diff.
A reference-source change needs an explicit new provenance record and review;
do not simply copy another parser's results into cases.json.
The repository's default pytest testpaths excludes this directory, so run
the explicit commands above. Existing CI does not automatically check this corpus.
Generation is not a claim that the separate pytest/ruff commands have passed.
