# Source-first review record

Primary audit, 2026-10-03. Written after reading all 186 public synthetic source
files (937 lines), before reading answers.json or executing omitnix. No product
output was used to decide the following answers. Source files were read in lexical
path order, by language; all caller/callee files were read together.

## Independent decisions

- All six languages: literal SELECT reads its FROM/JOIN tables. INSERT writes the
  destination and reads its SELECT source; UPDATE/DELETE write their target. A
  target also read by a separate SELECT appears in both modes. SQL subqueries read
  their own tables. Literals spanning lines retain the table token's source line.
- The six DDL cases write the CREATE/ALTER/DROP target; RENAME writes both names;
  CREATE TABLE order_copy LIKE orders writes order_copy and reads orders. CREATE
  INDEX writes payments in the PHP/SQL cases. Duplicate statements/references do
  not make extra file/mode/table recall units, but source occurrences remain distinct.
- Comments are excluded in each host language and SQL -- / block comments. Inline
  comment markers in SQL string values do not end the statement. SQL hash comments
  remain dialect-dependent (sql91 reference); PHP # comments are host comments.
- All six CTE cases read orders (PHP additionally customers); recent is an alias,
  never a physical table. information_schema tables/columns remain system evidence.
- Five chain families, lengths 1/2/3/4: leaf reads orders directly. Every preceding
  file reads orders through a chain whose depth is leaf index minus current index.
  Depths 1/2/3 are required; the five depth-4 entry files are outside required recall.
- Five argument-trace families: a.* passes orders; b.* passes customers; lib.*
  receives the table argument. Caller evidence has depth 1, and the library's two
  source possibilities must remain traced rather than literal/direct evidence.
- Named constants and wrapped literal-return functions resolve ledger_entries,
  invoices, or shipments. Finite arrays/dictionaries and Literal/union annotations
  are bounded candidate sets under this package's convention, not proven names.
- External request/argv table names (six files) have no invented table. Unbound
  parameters (five files) are dynamic unknowns. Broken INSERT SQL (five files)
  cannot be silently treated as a successful empty analysis.
- Dynamic WHERE/value fragments leave literal table positions determined; php90
  appends an arbitrary clause, so it remains reference. MERGE, UPDATE FROM,
  foreign-key targets, stored-procedure delimiter syntax remain reference policy.
- Five prose cases contain no SQL tables. Five test-source cases distinguish
  orders string assertions (text only) from audit_log queries on fake connections;
  the fake execution convention is policy, not proof of a live database write.
- Rust diesel insert_into names orders with write mode; TS knex names orders with
  read mode. Both are must-set query-builder cases despite their historical ref IDs.
- Escapes are decoded at the host-language layer before SQL reading. PHP quoted
  escapes, Python adjacent literals/SQLAlchemy text, Rust raw strings/sqlx macros,
  and TypeScript template values preserve their literal tables.

## Scope

This records full primary source review, not an independent review of the author's
fixes. Next: compare every answer item and source line to these decisions, enumerate
all extraction claims and exclusions, then record discrepancies and scored limits.
