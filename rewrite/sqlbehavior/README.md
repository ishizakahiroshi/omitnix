# SQL behavior corpus (source-only draft)

This is incomplete. The generator and tests are present, but no SQL behavior has been
measured in this task. cases.json is deliberately absent until the repository's
read_sql function can actually run with sqlglot 30.18.0.

The source defines 534 input cases in 71 categories. These are static definition
counts, not observed parse-success, failure, unsupported, read, or write counts.
There is no empirical summary or inferred behavior rule in this draft.

## Blocker

The available cloud executor failed before Python started with an ENOSPC workspace
setup error. Dependency installation, corpus generation, pytest, and ruff could not
run in that executor. The separate existing PR CI has run; exact commit/check results
are recorded in [draft PR #7](https://github.com/ishizakahiroshi/omitnix/pull/7).
Its default tests do not run rewrite/sqlbehavior or rewrite/tools, and its parser is
not pinned to sqlglot 30.18.0. A green default test job does not establish corpus verification.

The reference is commit 9311c9c8334ed74808e374aecf0cb2fb13534307 on rewrite-spec.
Only new files under rewrite/sqlbehavior are included; the adapter and CI are unchanged.

## Complete the recording

From a checkout of this branch, with Python 3.11 or newer, run:

```sh
python -m pip install -r rewrite/sqlbehavior/requirements.txt pytest ruff==0.16.2
python rewrite/sqlbehavior/make_cases.py
python rewrite/sqlbehavior/make_cases.py --check
python -m pytest rewrite/sqlbehavior rewrite/tools
python -m ruff check .
```

The generator calls omitnix/adapters/_sql.py:read_sql once for each input. It never
calls sqlglot directly. It verifies the installed sqlglot version and the reference
adapter's Git blob, with checkout CRLF normalized to LF for that source check.
It writes cases.json and replaces this draft README with a category summary and 16
observations derived from the returned values. Review both generated files before
committing them. Generation alone is not a pytest or ruff result.

--output-dir DIR records both artifacts separately. --check compares byte-for-byte
and writes nothing. JSON and README use UTF-8, LF, and a trailing newline; a
directory-local .gitattributes preserves those bytes on checkout.

Tests require the recorded cases.json and fail with an explicit regeneration command
when it is absent. They check unique IDs, all 71 categories, stable input ordering,
reference metadata, exact result fields, tuple-to-array conversion shape, sorted
reads/writes, one real reader call per input, byte-identical CLI regeneration, and
README statistics.

## Coverage defined in the source

- SELECT, INSERT, UPDATE, DELETE, WITH, joins, subqueries, and UNION
- CREATE TABLE/INDEX/VIEW/TRIGGER/SEQUENCE/SCHEMA/TYPE/POLICY/EXTENSION/ROLE
- ALTER TABLE add/drop columns, rename, owner, row-level security, triggers,
  validate/drop constraints, MODIFY, CHANGE, and ENGINE
- DROP of multiple object kinds and TRUNCATE
- GRANT/REVOKE on tables, all tables in a schema, schemas, functions, and
  function signatures with named arguments
- COMMENT ON, LOCK, VACUUM, ANALYZE, EXPLAIN, PREPARE, EXECUTE, and DEALLOCATE
- IF/END IF/ENDIF/BEGIN/END, procedural assignments, RETURN NEW, and column fragments
- MySQL backticks, ON DUPLICATE KEY, LIMIT, and multi-table UPDATE
- PostgreSQL casts, RETURNING, FOR UPDATE, INTERVAL, and ON CONFLICT
- SQLite INSERT OR IGNORE; ?, :name, %s, $1, and {{name}} placeholders
- Dynamic table holes, full-width symbols, multiple statements, truncated INSERT,
  unclosed parentheses, leading comments, near-blank input, and prose

Object identifiers rotate only among orders, customers, and invoices; columns and
other text are synthetic. The adapter's omitnix_placeholder sentinel is used solely
to probe dynamic_table. No real schemas, people, companies, or database connections
are involved. SQL strings are parser inputs and are never executed against a database.
