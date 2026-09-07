# omitnix

Static code inventory that **fails when anything discovered is left unanalyzed**.

> Status: early development. Nothing is usable yet. This is a personal hobby project; **no support is provided.**

## What it is

`omitnix` walks a codebase and produces two things:

- a per-file index (summary, authentication, authorization check, tables read, tables written)
- a reverse index from database tables back to the files that touch them

It never connects to a database. Schema information, when used, is read from a JSON snapshot produced by another tool.

## Why it exists

A generated inventory is easy. Keeping it honest is not.

The moment a file is added that the parser does not understand, most tools silently skip it. The row is simply missing, and a missing row reads like "this does not exist" — to a human, and even more so to an AI assistant reading the generated document. The newest code is exactly where the inventory is weakest, and exactly where an unchecked authorization path is most likely to be.

So `omitnix` treats completeness as the product:

```
discovered == analyzed + unresolved + unknown
```

If a discovered file cannot be classified, it is counted as `unknown` and the run **exits non-zero**. Anything the analyzer could not follow (dynamically built SQL, indirect calls beyond one hop) is recorded as `unresolved` with a reason — never as a blank cell.

Generated output always states what it is and is not:

```
Generated from commit: 0123456
Coverage: 202/202 analyzed, 8 unresolved, 0 unknown
```

And it never says "unused". It says: no static reference was observed by this analyzer at this commit.

## Example

Configuration lives in the repository being scanned, so nothing project-specific is baked into the tool:

```yaml
# .omitnix.yaml
include:
  - "api/**/*.php"
  - "batch/**/*.php"
exclude:
  - "vendor/**"
  - "node_modules/**"
authorization_functions:
  - apply_visibility_filter
authentication_functions:
  - require_session
schema_snapshot: schema.json
```

A generated table looks like this (fictional schema):

| file | summary | authn | authz | reads | writes | status |
|---|---|---|---|---|---|---|
| `api/orders_list.php` | List orders for the signed-in customer | yes | yes | `orders`, `customers` | — | analyzed |
| `api/orders_export.php` | Export orders as CSV | yes | yes | `orders` | — | unresolved (dynamic_sql) |
| `batch/reindex.py` | Nightly reindex | — | — | `orders` | `search_index` | analyzed |

## License

MIT. See [LICENSE](LICENSE).
