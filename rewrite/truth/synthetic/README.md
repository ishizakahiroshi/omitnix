# Synthetic truth corpus

Small invented repositories where the correct answer is fixed by how they are made.
`rewrite/truth/tools/make_synthetic.py` writes each source file together with the list
of what it touches, and finds the line numbers by searching the generated text. omitnix
is never run to produce an answer. Every name is invented (orders, customers, ...).

Regenerate: `python rewrite/truth/tools/make_synthetic.py` (add `--check` to confirm the
files on disk are what the script produces). The output is deterministic.

## Layout

`corpus/<lang>/<case>/...` holds the sources (one directory per case, so calls between
files stay inside the case). `corpus/.omitnix.yaml` includes all six extensions.
Run an implementation on `corpus/` (omitnix needs `--all-files` because it is not a
git repository). `answers.json` has one entry per file, in the shape used for the
answers of real repositories: `own`, `via`, `candidates`, `any_table`, `commented_out`,
`not_a_table`, `unreadable`, `text_only`, `system`, plus `beyond_depth` (calls deeper
than 3, not required) and the corpus fields `case`, `lang`, `category`, `set`, `tags`.
File paths in the answers are relative to `corpus/`. The conventions (depth, certainty,
comments, LIKE, argument-decided names, text-only, system tables) are listed under
`conventions` in `answers.json` and follow plan sections 14-16.

## Counts

Cases: 126 (must 119, reference 7).
Source files: 186.

By language (cases / files): go 21 / 33, php 33 / 45, python 25 / 37, rust 20 / 32, sql 5 / 5, ts 22 / 34.

Expected items (all / in the must set):

own: 191 / 181

via: 55 / 55

candidates: 12 / 12

any_table: 6 / 6

commented_out: 22 / 21

not_a_table: 21 / 21

unreadable: 10 / 10

text_only: 5 / 5

system: 6 / 6

beyond_depth: 5 / 5

Cases by category: call_depth_1 5, call_depth_2 5, call_depth_3 5, call_depth_4 5, comment 9, ddl 6, dialect 4, dynamic_clause 4, dynamic_table 35, escape 3, mixed 2, not_sql 5, partial_read 1, query_builder 2, select 16, system 1, test_sql 5, unreadable 5, unsupported 1, write 7.

## Patterns known to be Python problems

Tagged in `answers.json` (`tags`). The answer here is what the code says, not what
Python currently reports.

defect:backtick_placeholder: a backticked dynamic table name must not come out as a table (3 cases)

defect:php_escape: a PHP escaped quote must be unescaped before the SQL is read (1 cases)

defect:plain_ddl_command: plain CREATE / ALTER / RENAME / DROP name their table (6 cases)

limit:depth: PHP follows one hop only (3 cases)

limit:no_import_follow: Python does not follow imports, so callers get no via (5 cases)

## Must set and reference set

must: one correct answer. reference: the answer is fixed, but a dialect or an
undecided policy leaves room (partial read of a statement with a dynamic clause,
MERGE, UPDATE ... FROM, foreign-key targets, stored-procedure bodies). Report
reference results separately. Query builders that name the table (diesel, knex)
are in the must set (decided 2026-10-03).

## Independent check

2026-10-03. 30 expectations drawn with a fixed seed (20261003): one per
(language, kind) cell first, then random fill, from the 332 expectations of the
earlier corpus (own, via, candidates, any_table, commented_out, not_a_table,
unreadable, text_only, system, beyond_depth; all six languages). A second reader
looked only at the generated source files, decided what each file touches, and
only then compared with answers.json.

Result: 29 agreed, 1 disagreement (tables, modes, lines, depths and classes all
matched for the 29).

Disagreement: sql02_comments counted the hash line `# DELETE FROM sessions` as a
comment in the must set. A hash line is a comment in MySQL only; elsewhere it is
not. Fixed in the generator: the line moved to a new reference case
(sql91_ref_hash_comment); sql02_comments keeps only `--` and `/* */` comments.
PHP is unaffected (a hash line is a comment in every PHP SQL context here).

Limit: one reader of 30 of 332; call chains were read together with their case
files because a depth cannot be judged from one file.

## Not covered

Columns (stage 2), HTML / PowerShell / Shell, TypeScript tsx, templated PHP, and the
workspace-level behaviour (the golden cases cover those). The corpus is small and
written by one author; pattern coverage is checked by the 30-expectation spot check
in plan C3, not by this script.
