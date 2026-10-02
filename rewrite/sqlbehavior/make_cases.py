"""Record read_sql behavior for synthetic SQL; never infer expected parser output."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from omitnix.adapters import _sql as reference  # noqa: E402

SQLGLOT_VERSION = "30.18.0"
REFERENCE_COMMIT = "9311c9c8334ed74808e374aecf0cb2fb13534307"
REFERENCE_PATH = "omitnix/adapters/_sql.py"
REFERENCE_BLOB = "8b43f832505826518bc68782ee6065db20212e32"
ROTATIONS = (
    ("orders", "customers", "invoices"),
    ("customers", "invoices", "orders"),
    ("invoices", "orders", "customers"),
)

# Every identifier is synthetic. The object-name rotations exercise name ordering,
# deduplication, and identity-sensitive reads/writes without changing SQL grammar.
# Templates without object tokens occur once, rather than padding with duplicate SQL.
TEMPLATES = {
    "alter_add_column": (
        "ALTER TABLE {t} ADD COLUMN status TEXT",
        "ALTER TABLE {t} ADD COLUMN IF NOT EXISTS id INT DEFAULT 0",
    ),
    "alter_change": (
        "ALTER TABLE {t} CHANGE id order_id BIGINT",
        "ALTER TABLE {t} CHANGE COLUMN status state VARCHAR(30)",
    ),
    "alter_constraint": (
        "ALTER TABLE {t} VALIDATE CONSTRAINT {u}",
        "ALTER TABLE {t} DROP CONSTRAINT IF EXISTS {u}",
    ),
    "alter_drop_column": (
        "ALTER TABLE {t} DROP COLUMN status",
        "ALTER TABLE {t} DROP COLUMN IF EXISTS status CASCADE",
    ),
    "alter_engine": (
        "ALTER TABLE {t} ENGINE=innodb",
        "ALTER TABLE {t} ENGINE = myisam",
    ),
    "alter_modify": (
        "ALTER TABLE {t} MODIFY id BIGINT",
        "ALTER TABLE {t} MODIFY COLUMN status VARCHAR(30) NOT NULL",
    ),
    "alter_owner": (
        "ALTER TABLE {t} OWNER TO {u}",
        "ALTER TABLE IF EXISTS {t} OWNER TO {u}",
    ),
    "alter_rename": (
        "ALTER TABLE {t} RENAME TO {u}",
        "ALTER TABLE {t} RENAME COLUMN status TO state",
    ),
    "alter_rls": (
        "ALTER TABLE {t} ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE {t} FORCE ROW LEVEL SECURITY",
    ),
    "alter_trigger": (
        "ALTER TABLE {t} ENABLE TRIGGER {u}",
        "ALTER TABLE {t} ENABLE TRIGGER ALL",
    ),
    "analyze": (
        "ANALYZE {t}",
        "ANALYZE TABLE {t}",
    ),
    "column_fragment": (
        "id INT",
        "status TEXT NOT NULL",
        "id INT REFERENCES {t}(id)",
    ),
    "comment_on": (
        "COMMENT ON TABLE {t} IS 'synthetic'",
        "COMMENT ON COLUMN {t}.id IS 'synthetic'",
    ),
    "create_extension": (
        "CREATE EXTENSION {t}",
        "CREATE EXTENSION IF NOT EXISTS {t} WITH SCHEMA {u}",
    ),
    "create_index": (
        "CREATE INDEX {v} ON {t} (id)",
        "CREATE UNIQUE INDEX {v} ON {t} (id)",
    ),
    "create_policy": (
        "CREATE POLICY {v} ON {t} USING (id > 0)",
        "CREATE POLICY {v} ON {t} FOR SELECT TO {u} USING (true)",
    ),
    "create_role": (
        "CREATE ROLE {t}",
        "CREATE ROLE {t} WITH NOLOGIN",
    ),
    "create_schema": (
        "CREATE SCHEMA {t}",
        "CREATE SCHEMA IF NOT EXISTS {t} AUTHORIZATION {u}",
    ),
    "create_sequence": (
        "CREATE SEQUENCE {t}",
        "CREATE SEQUENCE IF NOT EXISTS {t} START WITH 1 INCREMENT BY 2",
    ),
    "create_table": (
        "CREATE TABLE {t} (id INT)",
        "CREATE TABLE IF NOT EXISTS {t} (id INT PRIMARY KEY, status TEXT)",
        "CREATE TABLE {t} AS SELECT id FROM {u}",
        "CREATE TABLE {t} (id INT REFERENCES {u}(id))",
    ),
    "create_trigger": (
        "CREATE TRIGGER {v} BEFORE INSERT ON {t} FOR EACH ROW EXECUTE FUNCTION {u}()",
        "CREATE TRIGGER {v} AFTER INSERT ON {t} BEGIN INSERT INTO {u} VALUES (new.id); END",
    ),
    "create_type": (
        "CREATE TYPE {t} AS ENUM ('open', 'closed')",
        "CREATE TYPE {t} AS (id INT, status TEXT)",
    ),
    "create_view": (
        "CREATE VIEW {v} AS SELECT id FROM {t}",
        "CREATE OR REPLACE VIEW {v} AS SELECT * FROM {t} JOIN {u} USING (id)",
    ),
    "deallocate": (
        "DEALLOCATE {t}",
        "DEALLOCATE PREPARE {t}",
    ),
    "delete": (
        "DELETE FROM {t} WHERE id = 1",
        "DELETE FROM {t}",
        "DELETE FROM {t} WHERE id IN (SELECT id FROM {u})",
    ),
    "drop": (
        "DROP TABLE {t}",
        "DROP TABLE IF EXISTS {t}, {u}",
        "DROP INDEX {v}",
        "DROP VIEW {v}",
        "DROP TRIGGER {v} ON {t}",
        "DROP SEQUENCE {t}",
        "DROP SCHEMA {t} CASCADE",
        "DROP TYPE {t}",
        "DROP POLICY {v} ON {t}",
        "DROP EXTENSION {t}",
        "DROP ROLE {t}",
    ),
    "dynamic_table": (
        "SELECT * FROM omitnix_placeholder",
        "SELECT {t}.id FROM {t} JOIN omitnix_placeholder ON {t}.id = 1",
        "INSERT INTO omitnix_placeholder SELECT id FROM {t}",
        "SELECT id FROM {t} WHERE status = 'omitnix_placeholder'",
    ),
    "execute": (
        "EXECUTE {t}",
        "EXECUTE {t}(1)",
    ),
    "explain": (
        "EXPLAIN SELECT id FROM {t}",
        "EXPLAIN ANALYZE SELECT * FROM {t}",
    ),
    "fullwidth": (
        "SELECT ＊ FROM {t}",
        "SELECT id FROM {t} WHERE id ＝ 1",
        "SELECT id，status FROM {t}",
        "INSERT INTO {t} （id） VALUES （1）",
    ),
    "grant_all_tables": (
        "GRANT SELECT ON ALL TABLES IN SCHEMA {t} TO {u}",
        "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA {t} TO {u}",
    ),
    "grant_function": (
        "GRANT EXECUTE ON FUNCTION {t}() TO {u}",
        "GRANT EXECUTE ON FUNCTION {t}(INT, TEXT) TO {u}",
    ),
    "grant_named_function": (
        "GRANT EXECUTE ON FUNCTION {t}(id INT) TO {u}",
        "GRANT EXECUTE ON FUNCTION {t}(id INT, status TEXT) TO {u}",
    ),
    "grant_schema": (
        "GRANT USAGE ON SCHEMA {t} TO {u}",
        "GRANT CREATE, USAGE ON SCHEMA {t}, {v} TO {u}",
    ),
    "grant_table": (
        "GRANT SELECT ON TABLE {t} TO {u}",
        "GRANT SELECT, INSERT, UPDATE ON {t}, {v} TO {u}",
    ),
    "insert": (
        "INSERT INTO {t} (id) VALUES (1)",
        "INSERT INTO {t} (id) SELECT id FROM {u}",
        "INSERT INTO {t} (id) SELECT id FROM {t}",
        "INSERT INTO {t} (id, status) VALUES (1, 'open'), (2, 'closed')",
    ),
    "joins": (
        "SELECT {t}.id FROM {t} JOIN {u} ON {t}.id = {u}.id",
        "SELECT {t}.* FROM {t} LEFT JOIN {u} ON {t}.id = {u}.id",
        "SELECT {t}.id FROM {t} CROSS JOIN {u}",
    ),
    "leading_comments": (
        "-- synthetic\nSELECT id FROM {t}",
        "/* synthetic */ SELECT * FROM {t}",
        "/* synthetic */\nUPDATE {t} SET id = 1",
    ),
    "lock": (
        "LOCK TABLE {t} IN ACCESS EXCLUSIVE MODE",
        "LOCK TABLE {t}, {u} IN SHARE MODE",
    ),
    "multistatement": (
        "SELECT id FROM {t}; INSERT INTO {u} (id) VALUES (1);",
        "SELECT id FROM {t}; SELECT id FROM {t};",
        "SELECT id FROM {t}; SELECT ((( FROM {u};",
        "SELECT id FROM {t}; VACUUM {u};",
    ),
    "mysql_backticks": (
        "SELECT `id` FROM `{t}`",
        "UPDATE `{t}` SET `status` = 'open' WHERE `id` = 1",
    ),
    "mysql_limit": (
        "UPDATE {t} SET status = 'open' LIMIT 1",
        "DELETE FROM {t} LIMIT 1",
        "SELECT id FROM {t} LIMIT 1, 2",
    ),
    "mysql_multi_update": (
        "UPDATE {t}, {u} SET {t}.id = {u}.id WHERE {t}.id = 1",
        "UPDATE {t} JOIN {u} ON {t}.id = {u}.id SET {t}.status = 'open', {u}.status = 'closed'",
    ),
    "mysql_on_duplicate": (
        "INSERT INTO {t} (id) VALUES (1) ON DUPLICATE KEY UPDATE id = VALUES(id)",
        "INSERT INTO {t} (id) SELECT id FROM {u} ON DUPLICATE KEY UPDATE id = 1",
    ),
    "near_blank": (
        "",
        " ",
        "\n\t",
        ";",
        ";;;",
        "-- synthetic",
        "/* synthetic */",
    ),
    "placeholders": (
        "SELECT id FROM {t} WHERE id = ?",
        "SELECT id FROM {t} WHERE id = :name",
        "SELECT id FROM {t} WHERE id = %s",
        "SELECT id FROM {t} WHERE id = $1",
        "SELECT id FROM {t} WHERE id = {{name}}",
        "SELECT id FROM {{name}}",
    ),
    "plpgsql_assignment": (
        "id := 1;",
        "status := 'open';",
        "id := (SELECT id FROM {t});",
    ),
    "postgres_cast": (
        "SELECT id::TEXT FROM {t}",
        "SELECT CAST(id AS TEXT) FROM {t}",
    ),
    "postgres_for_update": (
        "SELECT id FROM {t} FOR UPDATE",
        "SELECT id FROM {t} FOR UPDATE SKIP LOCKED",
    ),
    "postgres_interval": (
        "SELECT id FROM {t} WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '1 day'",
        "SELECT INTERVAL '2 hours' FROM {t}",
    ),
    "postgres_on_conflict": (
        "INSERT INTO {t} (id) VALUES (1) ON CONFLICT (id) DO NOTHING",
        "INSERT INTO {t} (id) VALUES (1) ON CONFLICT (id) DO UPDATE SET id = excluded.id",
    ),
    "postgres_returning": (
        "INSERT INTO {t} (id) VALUES (1) RETURNING *",
        "UPDATE {t} SET status = 'open' RETURNING id",
        "DELETE FROM {t} WHERE id = 1 RETURNING id",
    ),
    "prepare": (
        "PREPARE {v} AS SELECT id FROM {t} WHERE id = $1",
        "PREPARE {v}(INT) AS UPDATE {t} SET id = $1",
    ),
    "procedural_block": (
        "IF id > 0 THEN SELECT id FROM {t}; END IF;",
        "BEGIN SELECT id FROM {t}; END;",
        "IF",
        "END IF",
        "BEGIN",
        "END",
        "ENDIF",
    ),
    "prose": (
        "update your orders from the settings page",
        "delete an order from the orders",
        "select an invoice from invoices",
        "orders are ready",
        "please read invoices",
    ),
    "return_new": (
        "RETURN NEW;",
        "RETURN NEW.id;",
        "RETURN NULL;",
    ),
    "revoke_all_tables": (
        "REVOKE SELECT ON ALL TABLES IN SCHEMA {t} FROM {u}",
        "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {t} FROM {u}",
    ),
    "revoke_function": (
        "REVOKE EXECUTE ON FUNCTION {t}() FROM {u}",
        "REVOKE EXECUTE ON FUNCTION {t}(INT, TEXT) FROM {u}",
    ),
    "revoke_named_function": (
        "REVOKE EXECUTE ON FUNCTION {t}(id INT) FROM {u}",
        "REVOKE EXECUTE ON FUNCTION {t}(id INT, status TEXT) FROM {u}",
    ),
    "revoke_schema": (
        "REVOKE USAGE ON SCHEMA {t} FROM {u}",
        "REVOKE CREATE, USAGE ON SCHEMA {t}, {v} FROM {u}",
    ),
    "revoke_table": (
        "REVOKE SELECT ON TABLE {t} FROM {u}",
        "REVOKE SELECT, INSERT ON {t}, {v} FROM {u} CASCADE",
    ),
    "select": (
        "SELECT id FROM {t}",
        "SELECT * FROM {t} WHERE id = 1",
        "SELECT {t}.* FROM {t}",
        "SELECT COUNT(*) FROM {t}",
        "select id from {t}",
        "SELECT 1",
    ),
    "sqlite_ignore": (
        "INSERT OR IGNORE INTO {t} (id) VALUES (1)",
        "INSERT OR IGNORE INTO {t} (id) SELECT id FROM {u}",
    ),
    "subquery": (
        "SELECT id FROM {t} WHERE EXISTS (SELECT 1 FROM {u} WHERE {u}.id = {t}.id)",
        "SELECT id FROM (SELECT id FROM {t}) AS {u}",
        "SELECT (SELECT MAX(id) FROM {u}) FROM {t}",
    ),
    "truncate": (
        "TRUNCATE TABLE {t}",
        "TRUNCATE TABLE {t}, {u} RESTART IDENTITY CASCADE",
    ),
    "truncated_insert": (
        "INSERT INTO {t}",
        "INSERT INTO {t} (id)",
        "INSERT INTO {t} (id) VALUES",
    ),
    "unclosed_parenthesis": (
        "SELECT id FROM {t} WHERE (id = 1",
        "INSERT INTO {t} (id VALUES (1)",
        "SELECT (id FROM {t}",
    ),
    "union": (
        "SELECT id FROM {t} UNION SELECT id FROM {u}",
        "SELECT id FROM {t} UNION ALL SELECT id FROM {u}",
        "SELECT * FROM {t} UNION SELECT * FROM {t}",
    ),
    "update": (
        "UPDATE {t} SET status = 'open' WHERE id = 1",
        "UPDATE {t} SET id = id + 1",
        "UPDATE {t} SET status = (SELECT status FROM {u} WHERE id = 1) WHERE id = 2",
    ),
    "vacuum": (
        "VACUUM {t}",
        "VACUUM (ANALYZE) {t}",
    ),
    "with": (
        "WITH {v} AS (SELECT id FROM {t}) SELECT id FROM {v}",
        "WITH {v} AS (SELECT id FROM {t}) INSERT INTO {u} SELECT id FROM {v}",
        "WITH {t} AS (SELECT id FROM {t}) SELECT id FROM {t}",
    ),
}


def inputs() -> list[dict]:
    """Stable IDs and SQL inputs only; all outcome fields come from read_sql."""
    result = []
    for category, templates in sorted(TEMPLATES.items()):
        for number, template in enumerate(templates, 1):
            tokens = ("{t}", "{u}", "{v}")
            rotations = ROTATIONS if any(token in template for token in tokens) else ROTATIONS[:1]
            for rotation, names in enumerate(rotations, 1):
                sql = template
                for token, name in zip(tokens, names, strict=True):
                    sql = sql.replace(token, name)
                result.append(
                    {
                        "id": f"{category}.{number:02d}.{rotation}",
                        "category": category,
                        "sql": sql,
                    }
                )
    return result


def verify_reference() -> str:
    """Refuse version/source drift before recording any observations."""
    try:
        installed = version("sqlglot")
    except PackageNotFoundError as exc:
        raise RuntimeError(
            "Install the pinned parser: python -m pip install "
            "-r rewrite/sqlbehavior/requirements.txt"
        ) from exc
    if installed != SQLGLOT_VERSION:
        raise RuntimeError(f"Expected sqlglot {SQLGLOT_VERSION}; installed {installed}")
    source = Path(reference.__file__).resolve()
    if source != ROOT / REFERENCE_PATH:
        raise RuntimeError(f"read_sql must be imported from this checkout: {REFERENCE_PATH}")
    # Git may check this existing Python file out as CRLF on Windows.
    data = source.read_bytes().replace(b"\r\n", b"\n")
    blob = hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data,
        usedforsecurity=False,
    ).hexdigest()
    if blob != REFERENCE_BLOB:
        raise RuntimeError(f"{REFERENCE_PATH} differs from the recorded reference commit")
    return installed


def build_document() -> dict:
    """Call the repository function for each row; do not call sqlglot directly."""
    installed = verify_reference()
    cases = []
    for case in inputs():
        reading = reference.read_sql(case["sql"])
        cases.append(
            {
                **case,
                "reads": list(reading.reads),
                "writes": list(reading.writes),
                "parsed": reading.parsed,
                "select_star": reading.select_star,
                "dynamic_table": reading.dynamic_table,
                "unsupported": reading.unsupported,
            }
        )
    return {
        "format_version": 1,
        "sqlglot_version": installed,
        "reference": {
            "commit": REFERENCE_COMMIT,
            "source": REFERENCE_PATH,
            "git_blob": REFERENCE_BLOB,
            "entry_point": "read_sql",
        },
        "case_count": len(cases),
        "cases": cases,
    }


def json_bytes(document: dict) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def category_stats(cases: list[dict]) -> list[dict]:
    """Each statistic counts cases, not statements or distinct table names."""
    rows = []
    for category in sorted({case["category"] for case in cases}):
        group = [case for case in cases if case["category"] == category]
        rows.append(
            {
                "category": category,
                "n": len(group),
                "parsed_true": sum(case["parsed"] for case in group),
                "unsupported_ge_1": sum(case["unsupported"] >= 1 for case in group),
                "parsed_false": sum(not case["parsed"] for case in group),
                "nonempty_reads": sum(bool(case["reads"]) for case in group),
                "nonempty_writes": sum(bool(case["writes"]) for case in group),
            }
        )
    return rows


def outcome(case: dict) -> str:
    """Compact, factual wording for an observed row, never a predicted result."""
    flags = ", ".join(
        f"{key}={json.dumps(case[key])}"
        for key in ("parsed", "select_star", "dynamic_table", "unsupported")
    )
    return f"reads={case['reads']}, writes={case['writes']}, {flags}"


def empirical_notes(cases: list[dict]) -> list[str]:
    """Sixteen measured observations with category and case references."""
    by_id = {case["id"]: case for case in cases}

    def example(label: str, *ids: str) -> str:
        observed = "; ".join(f"\x60{key}\x60: {outcome(by_id[key])}" for key in ids)
        return f"{label}: {observed}"

    def group(label: str, categories: tuple[str, ...]) -> str:
        selected = [case for case in cases if case["category"] in categories]
        references = ", ".join(f"\x60{category}\x60" for category in categories)
        parsed = sum(case["parsed"] for case in selected)
        opaque = sum(case["parsed"] and case["unsupported"] > 0 for case in selected)
        reads = sum(bool(case["reads"]) for case in selected)
        writes = sum(bool(case["writes"]) for case in selected)
        return (
            f"{label} ({references}): {parsed}/{len(selected)} parsed; "
            f"{opaque} parsed with unsupported >= 1; {reads} have reads; {writes} have writes"
        )

    return [
        example("Projection star versus COUNT(*)", "select.02.1", "select.04.1"),
        example("One name on both sides of INSERT", "insert.03.1"),
        example("CTE aliases and a shadowed base name", "with.01.1", "with.03.1"),
        example("CREATE targets and source reads", "create_view.01.1", "create_index.01.1"),
        group("Other CREATE objects", ("create_schema", "create_type", "create_role")),
        group("Administrative ALTER", ("alter_owner", "alter_rls", "alter_trigger")),
        group(
            "Constraint and dialect ALTER",
            ("alter_constraint", "alter_modify", "alter_change", "alter_engine"),
        ),
        group("DROP and TRUNCATE", ("drop", "truncate")),
        group(
            "Table/schema privileges",
            (
                "grant_table", "grant_all_tables", "grant_schema",
                "revoke_table", "revoke_all_tables", "revoke_schema",
            ),
        ),
        group(
            "Function privilege signatures",
            (
                "grant_function", "grant_named_function",
                "revoke_function", "revoke_named_function",
            ),
        ),
        group(
            "Commands can parse opaquely",
            (
                "comment_on", "lock", "vacuum", "analyze",
                "explain", "prepare", "execute", "deallocate",
            ),
        ),
        group(
            "Procedural and fragment boundaries",
            ("procedural_block", "plpgsql_assignment", "return_new", "column_fragment"),
        ),
        group(
            "Vendor syntax",
            (
                "mysql_backticks", "mysql_on_duplicate", "mysql_limit", "mysql_multi_update",
                "postgres_cast", "postgres_returning", "postgres_for_update",
                "postgres_interval", "postgres_on_conflict", "sqlite_ignore",
            ),
        ),
        example(
            "Run-time table hole versus value text", "dynamic_table.02.1", "dynamic_table.04.1"
        ),
        group(
            "Whole-string parse failures",
            ("multistatement", "truncated_insert", "unclosed_parenthesis"),
        ),
        group(
            "Input text is passed through unchanged",
            ("placeholders", "fullwidth", "leading_comments", "near_blank", "prose"),
        ),
    ]


def render_readme(document: dict) -> bytes:
    """Derive every empirical number and observation from executed case results."""
    lines = [
        "# SQL behavior corpus",
        "",
        f"This corpus records {document['case_count']} synthetic SQL strings passed to",
        f"\x60{REFERENCE_PATH}:read_sql\x60 at commit \x60{REFERENCE_COMMIT}\x60,",
        f"using exactly sqlglot \x60{document['sqlglot_version']}\x60.",
        "It records observed behavior, including surprising or unsupported results;",
        "it is not an assertion of SQL validity or an ideal parser specification.",
        "",
        "## Reproduce",
        "",
        "Run from the repository root with Python 3.11 or newer:",
        "",
        "\x60\x60\x60sh",
        "python -m pip install -r rewrite/sqlbehavior/requirements.txt pytest ruff==0.16.2",
        "python rewrite/sqlbehavior/make_cases.py",
        "python rewrite/sqlbehavior/make_cases.py --check",
        "python -m pytest rewrite/sqlbehavior rewrite/tools",
        "python -m ruff check .",
        "\x60\x60\x60",
        "",
        "The generator refuses a different sqlglot version or different reference source.",
        "It writes only cases.json and this README; --check writes nothing.",
        "--output-dir DIR records into a separate directory for byte comparisons.",
        "",
        "## Data contract",
        "",
        "Each case contains id, category, sql, reads, writes, parsed, select_star,",
        "dynamic_table, and unsupported. The last field is the reference integer count.",
        "reads/writes are the reference tuples converted directly to JSON arrays.",
        "Only read_sql produces outcomes. No parser, dialect override, SQL normalization,",
        "salvage loop, exception-to-result conversion, or expected-value inference is added.",
        "A multi-statement input is passed as one whole string, just like any other case.",
        "Unsupported commands and parse failures are retained as observations.",
        "",
        "Cases are ordered by category, template number, and object-name rotation.",
        "Identifiers use orders/customers/invoices and synthetic columns; the adapter's",
        "omitnix_placeholder sentinel is included explicitly to exercise dynamic_table.",
        "No database connection or SQL execution is involved.",
        "JSON uses two-space indentation, literal Unicode, LF, and a final newline.",
        "No timestamps, machine paths, or environment-dependent commit lookups are recorded.",
        "",
        "## Category summary",
        "",
        "All columns count cases; unsupported >= 1 counts cases, not opaque statements.",
        "parsed=true and unsupported >= 1 can overlap. Empty reads/writes do not prove",
        "that a SQL string touches no tables; consult parsed and unsupported too.",
        "",
        "| category | n | parsed=true | unsupported>=1 | parsed=false | nonempty reads | "
        "nonempty writes |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in category_stats(document["cases"]):
        lines.append("| " + " | ".join(str(value) for value in row.values()) + " |")
    lines.extend(
        [
            "",
            "## Empirical boundaries",
            "",
            "These 16 observations describe only the recorded cases. Category names and",
            "case IDs refer to the table above and cases.json; they are not blanket grammar rules.",
            "",
        ]
    )
    for number, note in enumerate(empirical_notes(document["cases"]), 1):
        lines.append(f"{number}. {note}")
    lines.extend(
        [
            "",
            "## Maintenance",
            "",
            "Edit templates, regenerate both artifacts, and inspect the resulting diff.",
            "A reference-source change needs an explicit new provenance record and review;",
            "do not simply copy another parser's results into cases.json.",
            "The repository's default pytest testpaths excludes this directory, so run",
            "the explicit commands above. Existing CI does not automatically check this corpus.",
            "Generation is not a claim that the separate pytest/ruff commands have passed.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--check", action="store_true", help="compare without writing")
    args = parser.parse_args(argv)
    try:
        document = build_document()
        artifacts = {"cases.json": json_bytes(document), "README.md": render_readme(document)}
        if args.check:
            mismatches = [
                name
                for name, content in artifacts.items()
                if not (args.output_dir / name).is_file()
                or (args.output_dir / name).read_bytes() != content
            ]
            if mismatches:
                print("Missing or stale: " + ", ".join(mismatches), file=sys.stderr)
                return 1
            print(f"Verified {document['case_count']} cases and the empirical README")
            return 0
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, content in artifacts.items():
            (args.output_dir / name).write_bytes(content)
    except (OSError, RuntimeError) as exc:
        print(f"Cannot record SQL behavior: {exc}", file=sys.stderr)
        return 2
    print(f"Recorded {document['case_count']} cases and the empirical README")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
