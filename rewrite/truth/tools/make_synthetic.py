"""Generate the synthetic ground-truth corpus (rewrite/truth/synthetic/).

The answer is fixed by construction. Every source file below is written together with
the statement of what it touches, and the line numbers are found by searching the
generated text for an anchor string. omitnix is never run here, and nothing here reads
output from any implementation.

Usage (from the repository root):

    python rewrite/truth/tools/make_synthetic.py            # regenerate
    python rewrite/truth/tools/make_synthetic.py --check    # regenerate in memory and
                                                            # compare with what is on disk

The output is deterministic: the same script produces byte-identical files.
All names (orders, customers, ...) are invented.
"""

# ruff: noqa: E501  (case tables and embedded sources have long lines by nature)
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from textwrap import dedent

OUT_DIR = Path(__file__).resolve().parent.parent / "synthetic"
CORPUS = "corpus"

# Answer shape: the one used for the answers of real repositories (one entry per file with
# own / via / candidates / any_table / commented_out / not_a_table / unreadable /
# text_only / system), plus the fields this corpus adds (case, lang, set, tags,
# beyond_depth).
#
# own            the file's own SQL touches the table. certainty: direct (written in the
#                string), resolved (a constant or literal in the same file decides it),
#                traced (the name comes in as an argument and the call sites decide it).
# via            another file's SQL, reached by calls from this file. depth 1 = the callee
#                holds the SQL. Up to depth 3 is required; deeper goes to beyond_depth.
# candidates     the table name is one of a fixed list; every member is reported, as a
#                candidate.
# any_table      the table name comes from outside input: any table may be touched.
# commented_out  SQL that is only in a comment; it is not counted.
# not_a_table    something that looks like a table but is not (CTE name, prose).
# unreadable     no table can be taken. class: broken | dynamic | unsupported.
# text_only      SQL text that is built but never run (a test checking a string).
# system         catalogue tables (information_schema ...), kept apart from business ones.

KINDS = (
    "own",
    "via",
    "candidates",
    "any_table",
    "commented_out",
    "not_a_table",
    "unreadable",
    "text_only",
    "system",
    "beyond_depth",
)

CASES: list[dict] = []


def src(text: str) -> str:
    """Dedent a source snippet and make sure it ends with exactly one newline."""
    return dedent(text).strip("\n") + "\n"


def case(cid, lang, cat, files, exp, set_="must", tags=(), note=""):
    assert cid not in {c["id"] for c in CASES}, cid
    CASES.append(
        {
            "id": cid,
            "lang": lang,
            "category": cat,
            "files": {k: src(v) for k, v in files.items()},
            "exp": exp,
            "set": set_,
            "tags": list(tags),
            "note": note,
        }
    )


# --- expectation builders: (kind, file, fields). `anchor` is found in the file text. ---


def own(f, mode, table, anchor, cert="direct", how=""):
    return ("own", f, dict(mode=mode, table=table, anchor=anchor, certainty=cert, how=how))


def via(f, mode, table, depth, anchor, fn, target):
    return (
        "via" if depth <= 3 else "beyond_depth",
        f,
        dict(mode=mode, table=table, depth=depth, anchor=anchor, fn=fn, target=target),
    )


def cand(f, mode, tables, anchor, why):
    return ("candidates", f, dict(mode=mode, tables=sorted(tables), anchor=anchor, why=why))


def anyt(f, mode, anchor, why):
    return ("any_table", f, dict(mode=mode, anchor=anchor, why=why))


def comm(f, tables, anchor):
    return ("commented_out", f, dict(tables=sorted(tables), anchor=anchor))


def nott(f, anchor, what):
    return ("not_a_table", f, dict(anchor=anchor, what=what))


def unread(f, anchor, cls, why):
    return ("unreadable", f, dict(anchor=anchor, cls=cls, why=why))


def text(f, mode, table, anchor):
    return ("text_only", f, dict(mode=mode, table=table, anchor=anchor, certainty="direct"))


def sysq(f, mode, table, anchor):
    return ("system", f, dict(mode=mode, table=table, anchor=anchor))


# =====================================================================================
# PHP
# =====================================================================================

PHP = "<?php\n"


def php(body):
    return PHP + dedent(body).strip("\n") + "\n"


case("php01_select", "php", "select", {"a.php": php("""
    function listOrders(PDO $pdo) {
        return $pdo->query("SELECT id, total FROM orders WHERE total > 10")->fetchAll();
    }
""")}, [own("a.php", "read", "orders", "FROM orders")])

case("php02_join", "php", "select", {"a.php": php("""
    function ordersWithCustomers(PDO $pdo) {
        $sql = "SELECT o.id, c.name
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                LEFT JOIN coupons cp ON cp.id = o.coupon_id";
        return $pdo->query($sql)->fetchAll();
    }
""")}, [
    own("a.php", "read", "orders", "FROM orders o"),
    own("a.php", "read", "customers", "JOIN customers c"),
    own("a.php", "read", "coupons", "LEFT JOIN coupons"),
])

case("php03_insert_select", "php", "write", {"a.php": php("""
    function reindex(PDO $pdo) {
        $pdo->exec("INSERT INTO search_index (order_id, total)
                    SELECT id, total FROM orders");
    }
""")}, [
    own("a.php", "write", "search_index", "INSERT INTO search_index"),
    own("a.php", "read", "orders", "SELECT id, total FROM orders"),
])

case("php04_update_delete", "php", "write", {"a.php": php("""
    function settle(PDO $pdo, int $id) {
        $pdo->prepare("UPDATE invoices SET paid = 1 WHERE id = ?")->execute([$id]);
        $pdo->prepare("DELETE FROM sessions WHERE order_id = ?")->execute([$id]);
        $pdo->prepare("SELECT total FROM invoices WHERE id = ?")->execute([$id]);
    }
""")}, [
    own("a.php", "write", "invoices", "UPDATE invoices"),
    own("a.php", "write", "sessions", "DELETE FROM sessions"),
    own("a.php", "read", "invoices", "SELECT total FROM invoices"),
])

case("php05_escaped_quotes", "php", "escape", {"a.php": php(r"""
    function openOrders(PDO $pdo) {
        return $pdo->query('SELECT id FROM orders WHERE status = \'open\'')->fetchAll();
    }
    function namedCustomers(PDO $pdo) {
        return $pdo->query("SELECT id FROM customers WHERE name = \"Ann\"")->fetchAll();
    }
""")}, [
    own("a.php", "read", "orders", "FROM orders WHERE status"),
    own("a.php", "read", "customers", "FROM customers WHERE name"),
], tags=["defect:php_escape"], note="A PHP backslash-escaped quote must be unescaped before the SQL is read.")

case("php06_heredoc_comment", "php", "comment", {"a.php": php("""
    function recent(PDO $pdo) {
        $sql = <<<SQL
    SELECT id
    FROM orders
    -- JOIN coupons ON coupons.id = orders.coupon_id
    WHERE id > 5
    SQL;
        return $pdo->query($sql)->fetchAll();
    }
""")}, [
    own("a.php", "read", "orders", "FROM orders"),
    comm("a.php", ["coupons"], "-- JOIN coupons"),
])

case("php07_comments", "php", "comment", {"a.php": php("""
    // $pdo->query("SELECT * FROM coupons");
    # $pdo->query("DELETE FROM sessions");
    /* $pdo->exec("UPDATE ledger_entries SET posted = 1"); */
    function live(PDO $pdo) {
        $pdo->query("SELECT id FROM customers"); // was: SELECT id FROM payments
        return $pdo->query("SELECT id FROM orders")->fetchAll();
    }
""")}, [
    own("a.php", "read", "customers", 'FROM customers"'),
    own("a.php", "read", "orders", 'FROM orders"'),
    comm("a.php", ["coupons"], "// $pdo->query"),
    comm("a.php", ["sessions"], "# $pdo->query"),
    comm("a.php", ["ledger_entries"], "/* $pdo->exec"),
    comm("a.php", ["payments"], "was: SELECT"),
])

case("php08_comment_markers_in_strings", "php", "comment", {"a.php": php("""
    function live(PDO $pdo) {
        $pdo->query("SELECT id FROM orders WHERE note = 'a -- b' AND url = 'http://shop.test/c'");
        $pdo->query("SELECT id FROM invoices WHERE memo = '/* x */' AND tag = '#vip'");
        $pdo->query("SELECT id FROM customers"); // trailing comment
    }
""")}, [
    own("a.php", "read", "orders", "FROM orders"),
    own("a.php", "read", "invoices", "FROM invoices"),
    own("a.php", "read", "customers", "FROM customers"),
], note="Comment markers inside a string are not comments; excluding these would hide live code.")

case("php09_backtick_any", "php", "dynamic_table", {"a.php": php("""
    function browse(PDO $pdo) {
        $table = $_GET['table'];
        return $pdo->query("SELECT * FROM `$table`")->fetchAll();
    }
""")}, [
    anyt("a.php", "read", "FROM `$table`", "table name comes from $_GET"),
], tags=["defect:backtick_placeholder"],
     note="A backticked dynamic name must not come out as a table; it is reported as any table.")

case("php10_backtick_array_loop", "php", "dynamic_table", {"a.php": php("""
    function counts(PDO $pdo) {
        foreach (['orders', 'customers', 'invoices'] as $t) {
            $pdo->query("SELECT COUNT(*) FROM `$t`");
        }
    }
""")}, [
    cand("a.php", "read", ["orders", "customers", "invoices"], "FROM `$t`", "literal array loop"),
], tags=["defect:backtick_placeholder"])

case("php11_array_loop", "php", "dynamic_table", {"a.php": php("""
    function counts(PDO $pdo) {
        foreach (['orders', 'customers'] as $t) {
            $pdo->query("SELECT COUNT(*) FROM $t");
        }
    }
""")}, [cand("a.php", "read", ["orders", "customers"], "FROM $t", "literal array loop")])

case("php12_named_constant", "php", "dynamic_table", {"a.php": php("""
    const LEDGER_TABLE = 'ledger_entries';

    function postings(PDO $pdo) {
        return $pdo->query("SELECT * FROM " . LEDGER_TABLE . " WHERE posted = 1")->fetchAll();
    }
""")}, [own("a.php", "read", "ledger_entries", "FROM \" . LEDGER_TABLE", cert="resolved")])

case("php13_constant_dictionary", "php", "dynamic_table", {"a.php": php("""
    const REPORT_TABLES = ['sales' => 'orders', 'billing' => 'invoices'];

    function report(PDO $pdo, string $kind) {
        $t = REPORT_TABLES[$kind];
        return $pdo->query("SELECT COUNT(*) FROM $t")->fetchAll();
    }
""")}, [cand("a.php", "read", ["orders", "invoices"], "FROM $t", "constant dictionary values")])

case("php14_argument_traced", "php", "dynamic_table", {
    "lib.php": php("""
        function countRows(PDO $pdo, string $table) {
            return $pdo->query("SELECT COUNT(*) FROM $table")->fetchColumn();
        }
    """),
    "a.php": php("""
        require __DIR__ . '/lib.php';
        $n = countRows($pdo, 'orders');
    """),
    "b.php": php("""
        require __DIR__ . '/lib.php';
        $n = countRows($pdo, 'customers');
    """),
}, [
    own("lib.php", "read", "orders", "FROM $table", cert="traced", how="a.php passes 'orders'"),
    own("lib.php", "read", "customers", "FROM $table", cert="traced", how="b.php passes 'customers'"),
    via("a.php", "read", "orders", 1, "countRows($pdo, 'orders')", "countRows", "lib.php"),
    via("b.php", "read", "customers", 1, "countRows($pdo, 'customers')", "countRows", "lib.php"),
], note="Convention: the table decided by an argument is the callee's own, certainty traced; each caller gets a depth-1 via.")

case("php15_request_table", "php", "dynamic_table", {"a.php": php("""
    function describe(PDO $pdo) {
        $name = $_POST['name'];
        return $pdo->query("DESCRIBE " . $name)->fetchAll();
    }
""")}, [anyt("a.php", "read", "DESCRIBE", "table name comes from $_POST")])

case("php16_wrapped_literal", "php", "dynamic_table", {"a.php": php("""
    function tableName() {
        return 'shipments';
    }

    function shipments(PDO $pdo) {
        $t = tableName();
        return $pdo->query("SELECT * FROM $t")->fetchAll();
    }
""")}, [own("a.php", "read", "shipments", "FROM $t", cert="resolved")])

case("php17_unknown_origin", "php", "dynamic_table", {"a.php": php("""
    function peek(PDO $pdo, string $table) {
        return $pdo->query("SELECT * FROM $table LIMIT 1")->fetchAll();
    }
""")}, [unread("a.php", "FROM $table", "dynamic", "parameter with no call site in the corpus")])

case("php18_dynamic_where", "php", "dynamic_clause", {"a.php": php("""
    function byName(PDO $pdo, string $name) {
        return $pdo->query("SELECT id FROM orders WHERE name = '$name' AND total > " . $_GET['min'])->fetchAll();
    }
    function pick(PDO $pdo, array $ids) {
        return $pdo->query("UPDATE customers SET flag = 1 WHERE id IN (" . implode(',', $ids) . ")");
    }
""")}, [
    own("a.php", "read", "orders", "FROM orders"),
    own("a.php", "write", "customers", "UPDATE customers"),
], note="A dynamic value does not hide a table that is written in the statement.")

case("php19_ddl", "php", "ddl", {"a.php": php("""
    function migrate(PDO $pdo) {
        $pdo->exec("CREATE TABLE shipments (id INT PRIMARY KEY, order_id INT)");
        $pdo->exec("ALTER TABLE orders ADD COLUMN note VARCHAR(40)");
        $pdo->exec("RENAME TABLE legacy_orders TO archive_orders");
        $pdo->exec("CREATE TABLE order_copy LIKE orders");
        $pdo->exec("DROP TABLE IF EXISTS tmp_orders");
        $pdo->exec("CREATE INDEX idx_customer ON payments (customer_id)");
    }
""")}, [
    own("a.php", "write", "shipments", "CREATE TABLE shipments"),
    own("a.php", "write", "orders", "ALTER TABLE orders"),
    own("a.php", "write", "legacy_orders", "RENAME TABLE legacy_orders"),
    own("a.php", "write", "archive_orders", "RENAME TABLE legacy_orders"),
    own("a.php", "write", "order_copy", "CREATE TABLE order_copy"),
    own("a.php", "read", "orders", "CREATE TABLE order_copy"),
    own("a.php", "write", "tmp_orders", "DROP TABLE IF EXISTS"),
    own("a.php", "write", "payments", "CREATE INDEX"),
], tags=["defect:plain_ddl_command"],
     note="Plain DDL names its table. CREATE TABLE ... LIKE reads its source (decision 2026-10-03).")

case("php20_system_table", "php", "system", {"a.php": php("""
    function tables(PDO $pdo) {
        $pdo->query("SELECT table_name FROM information_schema.tables WHERE table_schema = 'shop'");
        return $pdo->query("SELECT id FROM orders")->fetchAll();
    }
""")}, [
    sysq("a.php", "read", "information_schema.tables", "information_schema.tables"),
    own("a.php", "read", "orders", 'FROM orders"'),
])

case("php21_cte", "php", "select", {"a.php": php("""
    function recent(PDO $pdo) {
        return $pdo->query("WITH recent AS (SELECT id, total FROM orders WHERE id > 5)
                            SELECT r.id FROM recent r JOIN customers c ON c.id = r.id")->fetchAll();
    }
""")}, [
    own("a.php", "read", "orders", "FROM orders"),
    own("a.php", "read", "customers", "JOIN customers"),
    nott("a.php", "WITH recent", "CTE name recent"),
])

case("php22_test_text_only", "php", "test_sql", {
    "OrderSqlTest.php": php("""
        class OrderSqlTest extends TestCase {
            public function testSqlText() {
                $sql = "SELECT id FROM orders WHERE id = 1";
                $this->assertStringContainsString('FROM orders', $sql);
            }
            public function testStubbedDb() {
                $db = new FakeDb();
                $db->query("INSERT INTO audit_log (message) VALUES ('x')");
                $this->assertCount(1, $db->calls);
            }
        }
    """),
}, [
    text("OrderSqlTest.php", "read", "orders", "SELECT id FROM orders"),
    own("OrderSqlTest.php", "write", "audit_log", "INSERT INTO audit_log"),
], note="A string only checked as text is text_only; a statement sent to a stubbed DB function is a written path and counts.")

case("php23_prose", "php", "not_sql", {"a.php": php("""
    $hint = "Select a customer from the list below";
    $done = "Update the order status when you are done";
    $help = "Delete the rows you do not need from view";
""")}, [
    nott("a.php", "Select a customer", "prose"),
    nott("a.php", "Update the order", "prose"),
    nott("a.php", "Delete the rows", "prose"),
])

case("php24_broken", "php", "unreadable", {"a.php": php("""
    function oops(PDO $pdo) {
        return $pdo->query("INSERT INTO (id, total VALUES (1")->fetchAll();
    }
""")}, [unread("a.php", "INSERT INTO (id", "broken", "no table can be taken")])

case("php25_rich", "php", "mixed", {"a.php": php("""
    function checkout(PDO $pdo, int $id) {
        $pdo->beginTransaction();
        $row = $pdo->query("SELECT total FROM orders WHERE id = $id")->fetch();
        $pdo->exec("INSERT INTO payments (order_id, amount) VALUES ($id, {$row['total']})");
        $pdo->exec("UPDATE orders SET status = 'paid' WHERE id = $id");
        $pdo->exec("INSERT INTO audit_log (message) SELECT CONCAT('paid ', id) FROM orders WHERE id = $id");
        $pdo->commit();
    }
""")}, [
    own("a.php", "read", "orders", "SELECT total FROM orders"),
    own("a.php", "write", "payments", "INSERT INTO payments"),
    own("a.php", "write", "orders", "UPDATE orders"),
    own("a.php", "write", "audit_log", "INSERT INTO audit_log"),
    own("a.php", "read", "orders", "SELECT CONCAT"),
])

case("php26_duplicate_key", "php", "write", {"a.php": php("""
    function bump(PDO $pdo, int $id) {
        $pdo->exec("INSERT INTO counters (id, n) VALUES ($id, 1) ON DUPLICATE KEY UPDATE n = n + 1");
        $pdo->exec("REPLACE INTO settings (k, v) VALUES ('a', 'b')");
    }
""")}, [
    own("a.php", "write", "counters", "INSERT INTO counters"),
    own("a.php", "write", "settings", "REPLACE INTO settings"),
])

# reference set (the answer is fixed, but implementations may reasonably differ)
case("php90_ref_partial", "php", "partial_read", {"a.php": php("""
    function filtered(PDO $pdo, string $where) {
        return $pdo->query("SELECT id FROM orders " . $where . " ORDER BY id")->fetchAll();
    }
""")}, [own("a.php", "read", "orders", "FROM orders", cert="direct")], set_="reference",
     note="Table written, the rest assembled at run time. Policy 2026-10-02 (partial read, 'candidate' certainty) is not settled for scoring.")

case("php91_ref_merge", "php", "dialect", {"a.php": php("""
    function upsert(PDO $pdo) {
        $pdo->exec("MERGE INTO customers AS t USING staging_customers AS s ON t.id = s.id
                    WHEN MATCHED THEN UPDATE SET t.name = s.name");
    }
""")}, [
    own("a.php", "write", "customers", "MERGE INTO customers"),
    own("a.php", "read", "staging_customers", "USING staging_customers"),
], set_="reference", note="Dialect statement; parsers differ.")

case("php92_ref_foreign_key", "php", "dialect", {"a.php": php("""
    function schema(PDO $pdo) {
        $pdo->exec("CREATE TABLE order_items (id INT, order_id INT,
                    FOREIGN KEY (order_id) REFERENCES orders (id))");
    }
""")}, [own("a.php", "write", "order_items", "CREATE TABLE order_items")], set_="reference",
     note="Whether the foreign-key target counts as a read is undecided; only the written table is fixed.")

# =====================================================================================
# Python
# =====================================================================================

case("py01_select", "python", "select", {"a.py": """
    def list_orders(conn):
        cur = conn.cursor()
        cur.execute("SELECT id, total FROM orders WHERE total > 10")
        return cur.fetchall()
"""}, [own("a.py", "read", "orders", "FROM orders")])

case("py02_adjacent_literals", "python", "select", {"a.py": """
    def joined(conn):
        return conn.execute(
            "SELECT o.id FROM orders o "
            "JOIN customers c ON c.id = o.customer_id "
            "WHERE c.active = 1"
        ).fetchall()
"""}, [
    own("a.py", "read", "orders", "SELECT o.id FROM orders"),
    own("a.py", "read", "customers", "JOIN customers"),
])

case("py03_fstring_value", "python", "dynamic_clause", {"a.py": """
    def one(conn, oid):
        return conn.execute(f"SELECT total FROM orders WHERE id = {oid}").fetchone()

    def named(conn, name):
        return conn.execute("SELECT id FROM customers WHERE name = '%s'" % name).fetchall()

    def fmt(conn, oid):
        return conn.execute("SELECT id FROM invoices WHERE id = {}".format(oid)).fetchall()
"""}, [
    own("a.py", "read", "orders", "FROM orders"),
    own("a.py", "read", "customers", "FROM customers"),
    own("a.py", "read", "invoices", "FROM invoices"),
])

case("py04_fstring_loop", "python", "dynamic_table", {"a.py": """
    def counts(conn):
        for t in ("orders", "customers"):
            conn.execute(f"SELECT COUNT(*) FROM {t}")
"""}, [cand("a.py", "read", ["orders", "customers"], "FROM {t}", "literal tuple loop")])

case("py05_named_constant", "python", "dynamic_table", {"a.py": """
    LEDGER = "ledger_entries"

    def postings(conn):
        return conn.execute(f"SELECT * FROM {LEDGER} WHERE posted = 1").fetchall()
"""}, [own("a.py", "read", "ledger_entries", "FROM {LEDGER}", cert="resolved")])

case("py06_class_constant_wrapped", "python", "dynamic_table", {"a.py": """
    class Invoices:
        TABLE = "invoices"

        def open(self, conn):
            return conn.execute(f"SELECT * FROM {self.TABLE} WHERE paid = 0").fetchall()

    def table_name():
        return "shipments"

    def shipped(conn):
        return conn.execute(f"SELECT * FROM {table_name()}").fetchall()
"""}, [
    own("a.py", "read", "invoices", "FROM {self.TABLE}", cert="resolved"),
    own("a.py", "read", "shipments", "FROM {table_name()}", cert="resolved"),
])

case("py07_dictionary", "python", "dynamic_table", {"a.py": """
    REPORT_TABLES = {"sales": "orders", "billing": "invoices"}

    def report(conn, kind):
        t = REPORT_TABLES[kind]
        return conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
"""}, [cand("a.py", "read", ["orders", "invoices"], "FROM {t}", "constant dictionary values")])

case("py08_literal_type", "python", "dynamic_table", {"a.py": """
    from typing import Literal

    def count(conn, table: Literal["orders", "customers"]):
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
"""}, [cand("a.py", "read", ["orders", "customers"], "FROM {table}", "Literal type")])

case("py09_argument_traced", "python", "dynamic_table", {
    "lib.py": """
        def count_rows(conn, table):
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    """,
    "a.py": """
        from lib import count_rows

        n = count_rows(conn, "orders")
    """,
    "b.py": """
        from lib import count_rows

        n = count_rows(conn, "customers")
    """,
}, [
    own("lib.py", "read", "orders", "FROM {table}", cert="traced", how="a.py passes 'orders'"),
    own("lib.py", "read", "customers", "FROM {table}", cert="traced", how="b.py passes 'customers'"),
    via("a.py", "read", "orders", 1, 'count_rows(conn, "orders")', "count_rows", "lib.py"),
    via("b.py", "read", "customers", 1, 'count_rows(conn, "customers")', "count_rows", "lib.py"),
], tags=["limit:no_import_follow"])

case("py10_external_table", "python", "dynamic_table", {"a.py": """
    import sys

    def dump(conn):
        name = sys.argv[1]
        return conn.execute(f"SELECT * FROM `{name}`").fetchall()
"""}, [anyt("a.py", "read", "FROM `{name}`", "table name comes from the command line")],
     tags=["defect:backtick_placeholder"])

case("py11_unknown_origin", "python", "dynamic_table", {"a.py": """
    def peek(conn, table):
        return conn.execute("SELECT * FROM %s LIMIT 1" % table).fetchall()
"""}, [unread("a.py", "FROM %s", "dynamic", "parameter with no call site in the corpus")])

case("py12_comments", "python", "comment", {"a.py": """
    # conn.execute("SELECT * FROM coupons")
    def live(conn):
        conn.execute("SELECT id FROM customers")  # was: SELECT id FROM payments
        conn.execute("SELECT id FROM orders WHERE note = 'a -- b' AND tag = '#vip'")
        # conn.execute("DELETE FROM sessions")
"""}, [
    own("a.py", "read", "customers", "FROM customers"),
    own("a.py", "read", "orders", "FROM orders"),
    comm("a.py", ["coupons"], "# conn.execute(\"SELECT * FROM coupons"),
    comm("a.py", ["payments"], "was: SELECT"),
    comm("a.py", ["sessions"], "# conn.execute(\"DELETE"),
])

case("py13_write", "python", "write", {"a.py": """
    def settle(conn, i):
        conn.execute("INSERT INTO payments (order_id) VALUES (?)", (i,))
        conn.execute("UPDATE invoices SET paid = 1 WHERE id = ?", (i,))
        conn.execute("DELETE FROM sessions WHERE order_id = ?", (i,))
        conn.execute("INSERT INTO search_index (order_id) SELECT id FROM orders")
"""}, [
    own("a.py", "write", "payments", "INSERT INTO payments"),
    own("a.py", "write", "invoices", "UPDATE invoices"),
    own("a.py", "write", "sessions", "DELETE FROM sessions"),
    own("a.py", "write", "search_index", "INSERT INTO search_index"),
    own("a.py", "read", "orders", "SELECT id FROM orders"),
])

case("py14_ddl", "python", "ddl", {"a.py": """
    def migrate(conn):
        conn.execute("CREATE TABLE shipments (id INT PRIMARY KEY, order_id INT)")
        conn.execute("ALTER TABLE orders ADD COLUMN note TEXT")
        conn.execute("RENAME TABLE legacy_orders TO archive_orders")
        conn.execute("CREATE TABLE order_copy LIKE orders")
        conn.execute("DROP TABLE IF EXISTS tmp_orders")
"""}, [
    own("a.py", "write", "shipments", "CREATE TABLE shipments"),
    own("a.py", "write", "orders", "ALTER TABLE orders"),
    own("a.py", "write", "legacy_orders", "RENAME TABLE"),
    own("a.py", "write", "archive_orders", "RENAME TABLE"),
    own("a.py", "write", "order_copy", "CREATE TABLE order_copy"),
    own("a.py", "read", "orders", "CREATE TABLE order_copy"),
    own("a.py", "write", "tmp_orders", "DROP TABLE IF EXISTS"),
], tags=["defect:plain_ddl_command"])

case("py15_cte_system", "python", "select", {"a.py": """
    def recent(conn):
        conn.execute("WITH recent AS (SELECT id FROM orders) SELECT * FROM recent")
        conn.execute("SELECT table_name FROM information_schema.columns")
"""}, [
    own("a.py", "read", "orders", "FROM orders"),
    nott("a.py", "WITH recent", "CTE name recent"),
    sysq("a.py", "read", "information_schema.columns", "information_schema.columns"),
])

case("py16_test_text_only", "python", "test_sql", {"test_orders.py": """
    def test_sql_text():
        sql = "SELECT id FROM orders WHERE id = 1"
        assert "FROM orders" in sql

    def test_stubbed(fake_db):
        fake_db.execute("INSERT INTO audit_log (message) VALUES ('x')")
        assert len(fake_db.calls) == 1
"""}, [
    text("test_orders.py", "read", "orders", "SELECT id FROM orders"),
    own("test_orders.py", "write", "audit_log", "INSERT INTO audit_log"),
])

case("py17_prose", "python", "not_sql", {"a.py": """
    HINT = "Select a customer from the list below"
    DONE = "Update the order status when you are done"
    HELP = "Delete the rows you do not need from view"
"""}, [
    nott("a.py", "Select a customer", "prose"),
    nott("a.py", "Update the order", "prose"),
    nott("a.py", "Delete the rows", "prose"),
])

case("py18_broken", "python", "unreadable", {"a.py": """
    def oops(conn):
        return conn.execute("INSERT INTO (id, total VALUES (1").fetchall()
"""}, [unread("a.py", "INSERT INTO (id", "broken", "no table can be taken")])

case("py19_escaped_quotes", "python", "escape", {"a.py": r"""
    def open_orders(conn):
        return conn.execute('SELECT id FROM orders WHERE status = \'open\'').fetchall()
"""}, [own("a.py", "read", "orders", "FROM orders WHERE status")])

case("py20_sqlalchemy_text", "python", "select", {"a.py": """
    from sqlalchemy import text

    def totals(session):
        return session.execute(text('''
            SELECT c.id, SUM(o.total)
            FROM customers c
            JOIN orders o ON o.customer_id = c.id
            GROUP BY c.id
        ''')).all()
"""}, [
    own("a.py", "read", "customers", "FROM customers c"),
    own("a.py", "read", "orders", "JOIN orders o"),
])

case("py90_ref_update_from", "python", "dialect", {"a.py": """
    def refresh(conn):
        conn.execute("UPDATE orders SET total = s.total FROM staging_orders s WHERE s.id = orders.id")
"""}, [
    own("a.py", "write", "orders", "UPDATE orders"),
    own("a.py", "read", "staging_orders", "FROM staging_orders"),
], set_="reference", note="PostgreSQL UPDATE ... FROM; parsers differ.")

# =====================================================================================
# Go
# =====================================================================================

case("go01_select", "go", "select", {"a.go": """
    package repo

    func ListOrders(db *sql.DB) {
        db.Query("SELECT id, total FROM orders WHERE total > 10")
    }
"""}, [own("a.go", "read", "orders", "FROM orders")])

case("go02_raw_string", "go", "select", {"a.go": """
    package repo

    func Totals(db *sql.DB) {
        db.QueryRow(`
            SELECT c.id, SUM(o.total)
            FROM customers c
            JOIN orders o ON o.customer_id = c.id
            GROUP BY c.id`)
    }
"""}, [
    own("a.go", "read", "customers", "FROM customers c"),
    own("a.go", "read", "orders", "JOIN orders o"),
])

case("go03_write", "go", "write", {"a.go": """
    package repo

    func Settle(db *sql.DB, id int) {
        db.Exec("INSERT INTO payments (order_id) VALUES (?)", id)
        db.Exec("UPDATE invoices SET paid = 1 WHERE id = ?", id)
        db.Exec("DELETE FROM sessions WHERE order_id = ?", id)
        db.Exec("INSERT INTO search_index (order_id) SELECT id FROM orders")
    }
"""}, [
    own("a.go", "write", "payments", "INSERT INTO payments"),
    own("a.go", "write", "invoices", "UPDATE invoices"),
    own("a.go", "write", "sessions", "DELETE FROM sessions"),
    own("a.go", "write", "search_index", "INSERT INTO search_index"),
    own("a.go", "read", "orders", "SELECT id FROM orders"),
])

case("go04_sprintf_argument", "go", "dynamic_table", {
    "lib.go": """
        package repo

        func CountRows(db *sql.DB, table string) {
            db.QueryRow(fmt.Sprintf("SELECT COUNT(*) FROM %s", table))
        }
    """,
    "a.go": """
        package repo

        func Orders(db *sql.DB) {
            CountRows(db, "orders")
        }
    """,
    "b.go": """
        package repo

        func Customers(db *sql.DB) {
            CountRows(db, "customers")
        }
    """,
}, [
    own("lib.go", "read", "orders", "FROM %s", cert="traced", how="a.go passes \"orders\""),
    own("lib.go", "read", "customers", "FROM %s", cert="traced", how="b.go passes \"customers\""),
    via("a.go", "read", "orders", 1, 'CountRows(db, "orders")', "CountRows", "lib.go"),
    via("b.go", "read", "customers", 1, 'CountRows(db, "customers")', "CountRows", "lib.go"),
])

case("go05_constant", "go", "dynamic_table", {"a.go": """
    package repo

    const ledgerTable = "ledger_entries"

    func Postings(db *sql.DB) {
        db.Query("SELECT * FROM " + ledgerTable + " WHERE posted = 1")
    }
"""}, [own("a.go", "read", "ledger_entries", "FROM \" + ledgerTable", cert="resolved")])

case("go06_slice_loop", "go", "dynamic_table", {"a.go": """
    package repo

    func Counts(db *sql.DB) {
        for _, t := range []string{"orders", "customers"} {
            db.QueryRow(fmt.Sprintf("SELECT COUNT(*) FROM %s", t))
        }
    }
"""}, [cand("a.go", "read", ["orders", "customers"], "FROM %s", "literal slice loop")])

case("go07_map_dictionary", "go", "dynamic_table", {"a.go": """
    package repo

    var reportTables = map[string]string{"sales": "orders", "billing": "invoices"}

    func Report(db *sql.DB, kind string) {
        t := reportTables[kind]
        db.QueryRow("SELECT COUNT(*) FROM " + t)
    }
"""}, [cand("a.go", "read", ["orders", "invoices"], "FROM \" + t", "constant map values")])

case("go08_request_table", "go", "dynamic_table", {"a.go": """
    package repo

    func Browse(db *sql.DB, r *http.Request) {
        db.Query("SELECT * FROM " + r.URL.Query().Get("table"))
    }
"""}, [anyt("a.go", "read", "r.URL.Query()", "table name comes from the request")])

case("go09_unknown_origin", "go", "dynamic_table", {"a.go": """
    package repo

    func Peek(db *sql.DB, table string) {
        db.Query("SELECT * FROM " + table + " LIMIT 1")
    }
"""}, [unread("a.go", "SELECT * FROM", "dynamic", "parameter with no call site in the corpus")])

case("go10_comments", "go", "comment", {"a.go": """
    package repo

    // db.Exec("DELETE FROM sessions")
    func Live(db *sql.DB) {
        db.Query("SELECT id FROM customers") // was: SELECT id FROM payments
        db.Query("SELECT id FROM orders WHERE url = 'http://shop.test/c' AND note = 'a -- b'")
        /* db.Exec("UPDATE ledger_entries SET posted = 1") */
    }
"""}, [
    own("a.go", "read", "customers", "FROM customers"),
    own("a.go", "read", "orders", "FROM orders"),
    comm("a.go", ["sessions"], "// db.Exec"),
    comm("a.go", ["payments"], "was: SELECT"),
    comm("a.go", ["ledger_entries"], "/* db.Exec"),
])

case("go11_ddl", "go", "ddl", {"a.go": """
    package repo

    func Migrate(db *sql.DB) {
        db.Exec("CREATE TABLE shipments (id INT PRIMARY KEY, order_id INT)")
        db.Exec("ALTER TABLE orders ADD COLUMN note TEXT")
        db.Exec("RENAME TABLE legacy_orders TO archive_orders")
        db.Exec("CREATE TABLE order_copy LIKE orders")
        db.Exec("DROP TABLE IF EXISTS tmp_orders")
    }
"""}, [
    own("a.go", "write", "shipments", "CREATE TABLE shipments"),
    own("a.go", "write", "orders", "ALTER TABLE orders"),
    own("a.go", "write", "legacy_orders", "RENAME TABLE"),
    own("a.go", "write", "archive_orders", "RENAME TABLE"),
    own("a.go", "write", "order_copy", "CREATE TABLE order_copy"),
    own("a.go", "read", "orders", "CREATE TABLE order_copy"),
    own("a.go", "write", "tmp_orders", "DROP TABLE IF EXISTS"),
], tags=["defect:plain_ddl_command"])

case("go12_system_cte", "go", "select", {"a.go": """
    package repo

    func Recent(db *sql.DB) {
        db.Query("WITH recent AS (SELECT id FROM orders) SELECT * FROM recent")
        db.Query("SELECT table_name FROM information_schema.tables")
    }
"""}, [
    own("a.go", "read", "orders", "FROM orders"),
    nott("a.go", "WITH recent", "CTE name recent"),
    sysq("a.go", "read", "information_schema.tables", "information_schema.tables"),
])

case("go13_test_text_only", "go", "test_sql", {"orders_sql_test.go": """
    package repo

    func TestSQLText(t *testing.T) {
        q := "SELECT id FROM orders WHERE id = 1"
        if !strings.Contains(q, "FROM orders") {
            t.Fatal("missing")
        }
    }

    func TestStubbed(t *testing.T) {
        fake := &FakeDB{}
        fake.Exec("INSERT INTO audit_log (message) VALUES ('x')")
    }
"""}, [
    text("orders_sql_test.go", "read", "orders", "SELECT id FROM orders"),
    own("orders_sql_test.go", "write", "audit_log", "INSERT INTO audit_log"),
])

case("go14_prose", "go", "not_sql", {"a.go": """
    package repo

    const hint = "Select a customer from the list below"
    const done = "Update the order status when you are done"
    const help = "Delete the rows you do not need from view"
"""}, [
    nott("a.go", "Select a customer", "prose"),
    nott("a.go", "Update the order", "prose"),
    nott("a.go", "Delete the rows", "prose"),
])

case("go15_broken", "go", "unreadable", {"a.go": """
    package repo

    func Oops(db *sql.DB) {
        db.Query("INSERT INTO (id, total VALUES (1")
    }
"""}, [unread("a.go", "INSERT INTO (id", "broken", "no table can be taken")])

case("go16_dynamic_where", "go", "dynamic_clause", {"a.go": """
    package repo

    func ByName(db *sql.DB, name string) {
        db.Query("SELECT id FROM orders WHERE name = '" + name + "'")
        db.Exec(fmt.Sprintf("UPDATE customers SET flag = 1 WHERE id = %d", 3))
    }
"""}, [
    own("a.go", "read", "orders", "FROM orders"),
    own("a.go", "write", "customers", "UPDATE customers"),
])

case("go90_ref_merge", "go", "dialect", {"a.go": """
    package repo

    func Upsert(db *sql.DB) {
        db.Exec("MERGE INTO customers AS t USING staging_customers AS s ON t.id = s.id WHEN MATCHED THEN UPDATE SET t.name = s.name")
    }
"""}, [
    own("a.go", "write", "customers", "MERGE INTO customers"),
    own("a.go", "read", "staging_customers", "USING staging_customers"),
], set_="reference", note="Dialect statement; parsers differ.")

# =====================================================================================
# Rust
# =====================================================================================

case("rs01_select", "rust", "select", {"a.rs": """
    pub fn list_orders(conn: &Connection) {
        conn.prepare("SELECT id, total FROM orders WHERE total > 10");
    }
"""}, [own("a.rs", "read", "orders", "FROM orders")])

case("rs02_raw_string", "rust", "select", {"a.rs": """
    pub async fn totals(pool: &PgPool) {
        sqlx::query(r#"
            SELECT c.id, SUM(o.total)
            FROM customers c
            JOIN orders o ON o.customer_id = c.id
            GROUP BY c.id"#)
            .fetch_all(pool)
            .await;
    }
"""}, [
    own("a.rs", "read", "customers", "FROM customers c"),
    own("a.rs", "read", "orders", "JOIN orders o"),
])

case("rs03_write", "rust", "write", {"a.rs": """
    pub fn settle(conn: &Connection, id: i64) {
        conn.execute("INSERT INTO payments (order_id) VALUES (?1)", [id]);
        conn.execute("UPDATE invoices SET paid = 1 WHERE id = ?1", [id]);
        conn.execute("DELETE FROM sessions WHERE order_id = ?1", [id]);
        conn.execute("INSERT INTO search_index (order_id) SELECT id FROM orders", []);
    }
"""}, [
    own("a.rs", "write", "payments", "INSERT INTO payments"),
    own("a.rs", "write", "invoices", "UPDATE invoices"),
    own("a.rs", "write", "sessions", "DELETE FROM sessions"),
    own("a.rs", "write", "search_index", "INSERT INTO search_index"),
    own("a.rs", "read", "orders", "SELECT id FROM orders"),
])

case("rs04_format_argument", "rust", "dynamic_table", {
    "lib.rs": """
        pub fn count_rows(conn: &Connection, table: &str) {
            conn.query_row(&format!("SELECT COUNT(*) FROM {}", table), [], |r| r.get(0));
        }
    """,
    "a.rs": """
        use crate::lib::count_rows;

        pub fn orders(conn: &Connection) {
            count_rows(conn, "orders");
        }
    """,
    "b.rs": """
        use crate::lib::count_rows;

        pub fn customers(conn: &Connection) {
            count_rows(conn, "customers");
        }
    """,
}, [
    own("lib.rs", "read", "orders", "FROM {}", cert="traced", how="a.rs passes \"orders\""),
    own("lib.rs", "read", "customers", "FROM {}", cert="traced", how="b.rs passes \"customers\""),
    via("a.rs", "read", "orders", 1, 'count_rows(conn, "orders")', "count_rows", "lib.rs"),
    via("b.rs", "read", "customers", 1, 'count_rows(conn, "customers")', "count_rows", "lib.rs"),
])

case("rs05_constant", "rust", "dynamic_table", {"a.rs": """
    const LEDGER: &str = "ledger_entries";

    pub fn postings(conn: &Connection) {
        conn.prepare(&format!("SELECT * FROM {} WHERE posted = 1", LEDGER));
    }
"""}, [own("a.rs", "read", "ledger_entries", "FROM {} WHERE posted", cert="resolved")])

case("rs06_array_loop", "rust", "dynamic_table", {"a.rs": """
    pub fn counts(conn: &Connection) {
        for t in ["orders", "customers"] {
            conn.query_row(&format!("SELECT COUNT(*) FROM {}", t), [], |r| r.get(0));
        }
    }
"""}, [cand("a.rs", "read", ["orders", "customers"], "FROM {}", "literal array loop")])

case("rs07_external_table", "rust", "dynamic_table", {"a.rs": """
    pub fn browse(conn: &Connection) {
        let name = std::env::args().nth(1).unwrap();
        conn.prepare(&format!("SELECT * FROM {}", name));
    }
"""}, [anyt("a.rs", "read", "FROM {}", "table name comes from the command line")])

case("rs08_unknown_origin", "rust", "dynamic_table", {"a.rs": """
    pub fn peek(conn: &Connection, table: &str) {
        conn.prepare(&format!("SELECT * FROM {} LIMIT 1", table));
    }
"""}, [unread("a.rs", "SELECT * FROM", "dynamic", "parameter with no call site in the corpus")])

case("rs09_comments", "rust", "comment", {"a.rs": """
    // conn.execute("DELETE FROM sessions", []);
    /// conn.execute("SELECT * FROM coupons", []);
    pub fn live(conn: &Connection) {
        conn.prepare("SELECT id FROM customers"); // was: SELECT id FROM payments
        conn.prepare("SELECT id FROM orders WHERE url = 'http://shop.test/c' AND note = 'a -- b'");
        /* conn.execute("UPDATE ledger_entries SET posted = 1", []); */
    }
"""}, [
    own("a.rs", "read", "customers", "FROM customers"),
    own("a.rs", "read", "orders", "FROM orders"),
    comm("a.rs", ["sessions"], "// conn.execute(\"DELETE"),
    comm("a.rs", ["coupons"], "/// conn.execute"),
    comm("a.rs", ["payments"], "was: SELECT"),
    comm("a.rs", ["ledger_entries"], "/* conn.execute"),
])

case("rs10_ddl", "rust", "ddl", {"a.rs": """
    pub fn migrate(conn: &Connection) {
        conn.execute("CREATE TABLE shipments (id INT PRIMARY KEY, order_id INT)", []);
        conn.execute("ALTER TABLE orders ADD COLUMN note TEXT", []);
        conn.execute("RENAME TABLE legacy_orders TO archive_orders", []);
        conn.execute("CREATE TABLE order_copy LIKE orders", []);
        conn.execute("DROP TABLE IF EXISTS tmp_orders", []);
    }
"""}, [
    own("a.rs", "write", "shipments", "CREATE TABLE shipments"),
    own("a.rs", "write", "orders", "ALTER TABLE orders"),
    own("a.rs", "write", "legacy_orders", "RENAME TABLE"),
    own("a.rs", "write", "archive_orders", "RENAME TABLE"),
    own("a.rs", "write", "order_copy", "CREATE TABLE order_copy"),
    own("a.rs", "read", "orders", "CREATE TABLE order_copy"),
    own("a.rs", "write", "tmp_orders", "DROP TABLE IF EXISTS"),
], tags=["defect:plain_ddl_command"])

case("rs11_system_cte", "rust", "select", {"a.rs": """
    pub fn recent(conn: &Connection) {
        conn.prepare("WITH recent AS (SELECT id FROM orders) SELECT * FROM recent");
        conn.prepare("SELECT table_name FROM information_schema.tables");
    }
"""}, [
    own("a.rs", "read", "orders", "FROM orders"),
    nott("a.rs", "WITH recent", "CTE name recent"),
    sysq("a.rs", "read", "information_schema.tables", "information_schema.tables"),
])

case("rs12_test_text_only", "rust", "test_sql", {"a.rs": """
    pub fn nothing() {}

    #[cfg(test)]
    mod tests {
        #[test]
        fn sql_text() {
            let sql = "SELECT id FROM orders WHERE id = 1";
            assert!(sql.contains("FROM orders"));
        }

        #[test]
        fn stubbed() {
            let fake = FakeConn::new();
            fake.execute("INSERT INTO audit_log (message) VALUES ('x')", []);
        }
    }
"""}, [
    text("a.rs", "read", "orders", "SELECT id FROM orders"),
    own("a.rs", "write", "audit_log", "INSERT INTO audit_log"),
])

case("rs13_prose", "rust", "not_sql", {"a.rs": """
    const HINT: &str = "Select a customer from the list below";
    const DONE: &str = "Update the order status when you are done";
    const HELP: &str = "Delete the rows you do not need from view";
"""}, [
    nott("a.rs", "Select a customer", "prose"),
    nott("a.rs", "Update the order", "prose"),
    nott("a.rs", "Delete the rows", "prose"),
])

case("rs14_broken", "rust", "unreadable", {"a.rs": """
    pub fn oops(conn: &Connection) {
        conn.prepare("INSERT INTO (id, total VALUES (1");
    }
"""}, [unread("a.rs", "INSERT INTO (id", "broken", "no table can be taken")])

case("rs15_sqlx_macro", "rust", "select", {"a.rs": """
    pub async fn one(pool: &PgPool, id: i64) {
        sqlx::query!("SELECT total FROM orders WHERE id = $1", id)
            .fetch_one(pool)
            .await;
    }
"""}, [own("a.rs", "read", "orders", "FROM orders")])

case("rs90_ref_builder", "rust", "query_builder", {"a.rs": """
    use diesel::prelude::*;

    diesel::table! {
        orders (id) {
            id -> Integer,
            customer_id -> Integer,
        }
    }

    pub fn save(conn: &mut PgConnection, customer_id: i64) {
        diesel::insert_into(orders::table).values(customer_id).execute(conn);
    }
"""}, [own("a.rs", "write", "orders", "diesel::insert_into(orders::table)")], set_="must",
     note="Query builder, no SQL string. Decided 2026-10-03: a builder that names the table counts as a table (the Rust adapter leaves it unresolved today).")

# =====================================================================================
# TypeScript
# =====================================================================================

case("ts01_select", "ts", "select", {"a.ts": """
    export async function listOrders(db: Db) {
      return db.query("SELECT id, total FROM orders WHERE total > 10");
    }
"""}, [own("a.ts", "read", "orders", "FROM orders")])

case("ts02_template_value", "ts", "dynamic_clause", {"a.ts": """
    export async function one(db: Db, id: number) {
      return db.query(`SELECT total FROM orders WHERE id = ${id}`);
    }

    export async function many(db: Db, ids: number[]) {
      return db.query(`
        SELECT c.id
        FROM customers c
        JOIN orders o ON o.customer_id = c.id
        WHERE o.id IN (${ids.join(",")})`);
    }
"""}, [
    own("a.ts", "read", "orders", "FROM orders WHERE id"),
    own("a.ts", "read", "customers", "FROM customers c"),
    own("a.ts", "read", "orders", "JOIN orders o"),
])

case("ts03_write", "ts", "write", {"a.ts": """
    export async function settle(db: Db, id: number) {
      await db.query("INSERT INTO payments (order_id) VALUES (?)", [id]);
      await db.query("UPDATE invoices SET paid = 1 WHERE id = ?", [id]);
      await db.query("DELETE FROM sessions WHERE order_id = ?", [id]);
      await db.query("INSERT INTO search_index (order_id) SELECT id FROM orders");
    }
"""}, [
    own("a.ts", "write", "payments", "INSERT INTO payments"),
    own("a.ts", "write", "invoices", "UPDATE invoices"),
    own("a.ts", "write", "sessions", "DELETE FROM sessions"),
    own("a.ts", "write", "search_index", "INSERT INTO search_index"),
    own("a.ts", "read", "orders", "SELECT id FROM orders"),
])

case("ts04_argument_traced", "ts", "dynamic_table", {
    "lib.ts": """
        export function countRows(db: Db, table: string) {
          return db.query(`SELECT COUNT(*) FROM ${table}`);
        }
    """,
    "a.ts": """
        import { countRows } from "./lib";

        export const n = countRows(db, "orders");
    """,
    "b.ts": """
        import { countRows } from "./lib";

        export const n = countRows(db, "customers");
    """,
}, [
    own("lib.ts", "read", "orders", "FROM ${table}", cert="traced", how="a.ts passes \"orders\""),
    own("lib.ts", "read", "customers", "FROM ${table}", cert="traced", how="b.ts passes \"customers\""),
    via("a.ts", "read", "orders", 1, 'countRows(db, "orders")', "countRows", "lib.ts"),
    via("b.ts", "read", "customers", 1, 'countRows(db, "customers")', "countRows", "lib.ts"),
])

case("ts05_constant", "ts", "dynamic_table", {"a.ts": """
    const LEDGER = "ledger_entries" as const;

    export function postings(db: Db) {
      return db.query(`SELECT * FROM ${LEDGER} WHERE posted = 1`);
    }
"""}, [own("a.ts", "read", "ledger_entries", "FROM ${LEDGER}", cert="resolved")])

case("ts06_union_type", "ts", "dynamic_table", {"a.ts": """
    type ReportTable = "orders" | "customers";

    export function count(db: Db, table: ReportTable) {
      return db.query(`SELECT COUNT(*) FROM ${table}`);
    }
"""}, [cand("a.ts", "read", ["orders", "customers"], "FROM ${table}", "literal union type")])

case("ts07_dictionary", "ts", "dynamic_table", {"a.ts": """
    const REPORT_TABLES = { sales: "orders", billing: "invoices" };

    export function report(db: Db, kind: "sales" | "billing") {
      const t = REPORT_TABLES[kind];
      return db.query(`SELECT COUNT(*) FROM ${t}`);
    }
"""}, [cand("a.ts", "read", ["orders", "invoices"], "FROM ${t}", "constant dictionary values")])

case("ts08_array_loop", "ts", "dynamic_table", {"a.ts": """
    export function counts(db: Db) {
      for (const t of ["orders", "customers"]) {
        db.query(`SELECT COUNT(*) FROM ${t}`);
      }
    }
"""}, [cand("a.ts", "read", ["orders", "customers"], "FROM ${t}", "literal array loop")])

case("ts09_request_table", "ts", "dynamic_table", {"a.ts": """
    export function browse(db: Db, req: Request) {
      return db.query(`SELECT * FROM ${req.query.table}`);
    }
"""}, [anyt("a.ts", "read", "FROM ${req.query.table}", "table name comes from the request")])

case("ts10_unknown_origin", "ts", "dynamic_table", {"a.ts": """
    export function peek(db: Db, table: string) {
      return db.query(`SELECT * FROM ${table} LIMIT 1`);
    }
"""}, [unread("a.ts", "SELECT * FROM", "dynamic", "parameter with no call site in the corpus")])

case("ts11_comments", "ts", "comment", {"a.ts": """
    // db.query("SELECT * FROM coupons");
    export function live(db: Db) {
      db.query("SELECT id FROM customers"); // was: SELECT id FROM payments
      db.query("SELECT id FROM orders WHERE url = 'http://shop.test/c' AND note = 'a -- b'");
      /* db.query("UPDATE ledger_entries SET posted = 1"); */
    }
"""}, [
    own("a.ts", "read", "customers", "FROM customers"),
    own("a.ts", "read", "orders", "FROM orders"),
    comm("a.ts", ["coupons"], "// db.query"),
    comm("a.ts", ["payments"], "was: SELECT"),
    comm("a.ts", ["ledger_entries"], "/* db.query"),
])

case("ts12_ddl", "ts", "ddl", {"a.ts": """
    export async function migrate(db: Db) {
      await db.query("CREATE TABLE shipments (id INT PRIMARY KEY, order_id INT)");
      await db.query("ALTER TABLE orders ADD COLUMN note TEXT");
      await db.query("RENAME TABLE legacy_orders TO archive_orders");
      await db.query("CREATE TABLE order_copy LIKE orders");
      await db.query("DROP TABLE IF EXISTS tmp_orders");
    }
"""}, [
    own("a.ts", "write", "shipments", "CREATE TABLE shipments"),
    own("a.ts", "write", "orders", "ALTER TABLE orders"),
    own("a.ts", "write", "legacy_orders", "RENAME TABLE"),
    own("a.ts", "write", "archive_orders", "RENAME TABLE"),
    own("a.ts", "write", "order_copy", "CREATE TABLE order_copy"),
    own("a.ts", "read", "orders", "CREATE TABLE order_copy"),
    own("a.ts", "write", "tmp_orders", "DROP TABLE IF EXISTS"),
], tags=["defect:plain_ddl_command"])

case("ts13_system_cte", "ts", "select", {"a.ts": """
    export function recent(db: Db) {
      db.query("WITH recent AS (SELECT id FROM orders) SELECT * FROM recent");
      db.query("SELECT table_name FROM information_schema.tables");
    }
"""}, [
    own("a.ts", "read", "orders", "FROM orders"),
    nott("a.ts", "WITH recent", "CTE name recent"),
    sysq("a.ts", "read", "information_schema.tables", "information_schema.tables"),
])

case("ts14_test_text_only", "ts", "test_sql", {"orders.test.ts": """
    test("sql text", () => {
      const sql = "SELECT id FROM orders WHERE id = 1";
      expect(sql).toContain("FROM orders");
    });

    test("stubbed", () => {
      const fake = new FakeDb();
      fake.query("INSERT INTO audit_log (message) VALUES ('x')");
    });
"""}, [
    text("orders.test.ts", "read", "orders", "SELECT id FROM orders"),
    own("orders.test.ts", "write", "audit_log", "INSERT INTO audit_log"),
])

case("ts15_prose", "ts", "not_sql", {"a.ts": """
    export const HINT = "Select a customer from the list below";
    export const DONE = "Update the order status when you are done";
    export const HELP = "Delete the rows you do not need from view";
"""}, [
    nott("a.ts", "Select a customer", "prose"),
    nott("a.ts", "Update the order", "prose"),
    nott("a.ts", "Delete the rows", "prose"),
])

case("ts16_broken", "ts", "unreadable", {"a.ts": """
    export function oops(db: Db) {
      return db.query("INSERT INTO (id, total VALUES (1");
    }
"""}, [unread("a.ts", "INSERT INTO (id", "broken", "no table can be taken")])

case("ts17_escaped_quotes", "ts", "escape", {"a.ts": r"""
    export function openOrders(db: Db) {
      return db.query('SELECT id FROM orders WHERE status = \'open\'');
    }
"""}, [own("a.ts", "read", "orders", "FROM orders WHERE status")])

case("ts90_ref_builder", "ts", "query_builder", {"a.ts": """
    export function listOrders(knex: Knex) {
      return knex("orders").select("id").where({ status: "open" });
    }
"""}, [own("a.ts", "read", "orders", 'knex("orders")')], set_="must",
     note="Query builder, no SQL string. Decided 2026-10-03: a builder that names the table counts as a table.")

# =====================================================================================
# SQL files
# =====================================================================================

case("sql01_ddl", "sql", "ddl", {"a.sql": """
    CREATE TABLE orders (id INT PRIMARY KEY, customer_id INT);
    ALTER TABLE orders ADD COLUMN note VARCHAR(40);
    RENAME TABLE legacy_orders TO archive_orders;
    CREATE TABLE order_copy LIKE orders;
    DROP TABLE IF EXISTS tmp_orders;
    CREATE INDEX idx_customer ON payments (customer_id);
"""}, [
    own("a.sql", "write", "orders", "CREATE TABLE orders"),
    own("a.sql", "write", "orders", "ALTER TABLE orders"),
    own("a.sql", "write", "legacy_orders", "RENAME TABLE"),
    own("a.sql", "write", "archive_orders", "RENAME TABLE"),
    own("a.sql", "write", "order_copy", "CREATE TABLE order_copy"),
    own("a.sql", "read", "orders", "CREATE TABLE order_copy"),
    own("a.sql", "write", "tmp_orders", "DROP TABLE IF EXISTS"),
    own("a.sql", "write", "payments", "CREATE INDEX"),
], tags=["defect:plain_ddl_command"])

case("sql02_comments", "sql", "comment", {"a.sql": """
    -- SELECT * FROM coupons;
    /* UPDATE ledger_entries SET posted = 1; */
    SELECT id FROM customers; -- was: SELECT id FROM payments
    SELECT id FROM orders WHERE note = 'a -- b' AND tag = '/* x */';
"""}, [
    own("a.sql", "read", "customers", "FROM customers"),
    own("a.sql", "read", "orders", "FROM orders"),
    comm("a.sql", ["coupons"], "-- SELECT * FROM coupons"),
    comm("a.sql", ["ledger_entries"], "/* UPDATE"),
    comm("a.sql", ["payments"], "was: SELECT"),
])

case("sql91_ref_hash_comment", "sql", "comment", {"a.sql": """
    # DELETE FROM sessions;
    SELECT id FROM orders;
"""}, [
    own("a.sql", "read", "orders", "FROM orders"),
    comm("a.sql", ["sessions"], "# DELETE FROM"),
], set_="reference",
     note="A hash line is a comment in MySQL only; other dialects read it differently.")

case("sql03_statements", "sql", "mixed", {"a.sql": """
    INSERT INTO search_index (order_id, total)
    SELECT id, total FROM orders;
    UPDATE invoices SET paid = 1 WHERE id IN (SELECT invoice_id FROM payments);
    DELETE FROM sessions WHERE expires < NOW();
    WITH recent AS (SELECT id FROM orders WHERE id > 5) SELECT * FROM recent;
    SELECT table_name FROM information_schema.tables;
"""}, [
    own("a.sql", "write", "search_index", "INSERT INTO search_index"),
    own("a.sql", "read", "orders", "SELECT id, total FROM orders"),
    own("a.sql", "write", "invoices", "UPDATE invoices"),
    own("a.sql", "read", "payments", "FROM payments"),
    own("a.sql", "write", "sessions", "DELETE FROM sessions"),
    own("a.sql", "read", "orders", "WITH recent"),
    nott("a.sql", "WITH recent", "CTE name recent"),
    sysq("a.sql", "read", "information_schema.tables", "information_schema.tables"),
])

case("sql90_ref_procedure", "sql", "unsupported", {"a.sql": """
    DELIMITER //
    CREATE PROCEDURE close_orders()
    BEGIN
      UPDATE orders SET status = 'closed' WHERE status = 'paid';
    END //
    DELIMITER ;
"""}, [own("a.sql", "write", "orders", "UPDATE orders")], set_="reference",
     note="Client directive and stored-procedure body; parsers differ widely.")

# =====================================================================================
# Call chains (depth 1 to 4), one family per language
# =====================================================================================


def _chain(lang, ext, depth):
    """Entry file l0 calls f1 (in l1) ... f<depth> (in l<depth>), which holds the SQL."""
    files = {}
    exp = []
    for k in range(depth + 1):
        name = f"l{k}.{ext}"
        last = k == depth
        if lang == "php":
            head = PHP + ("" if last else f"require __DIR__ . '/l{k + 1}.php';\n\n")
            if k == 0:
                body = "$rows = f1($pdo);\n"
            elif last:
                body = (
                    f"function f{k}(PDO $pdo) {{\n"
                    '    return $pdo->query("SELECT id FROM orders")->fetchAll();\n}\n'
                )
            else:
                body = f"function f{k}(PDO $pdo) {{\n    return f{k + 1}($pdo);\n}}\n"
            files[name] = head + body
            call = f"f{k + 1}($pdo)"
        elif lang == "python":
            head = "" if last else f"from l{k + 1} import f{k + 1}\n\n"
            if k == 0:
                body = "rows = f1(conn)\n"
            elif last:
                body = f'def f{k}(conn):\n    return conn.execute("SELECT id FROM orders").fetchall()\n'
            else:
                body = f"def f{k}(conn):\n    return f{k + 1}(conn)\n"
            files[name] = head + body
            call = f"f{k + 1}(conn)"
        elif lang == "go":
            head = "package repo\n\n"
            if k == 0:
                body = "func Entry(db *sql.DB) {\n    F1(db)\n}\n"
            elif last:
                body = f'func F{k}(db *sql.DB) {{\n    db.Query("SELECT id FROM orders")\n}}\n'
            else:
                body = f"func F{k}(db *sql.DB) {{\n    F{k + 1}(db)\n}}\n"
            files[name] = head + body
            call = f"F{k + 1}(db)"
        elif lang == "rust":
            head = "" if last else f"use crate::l{k + 1}::f{k + 1};\n\n"
            if k == 0:
                body = "pub fn entry(conn: &Connection) {\n    f1(conn);\n}\n"
            elif last:
                body = f'pub fn f{k}(conn: &Connection) {{\n    conn.prepare("SELECT id FROM orders");\n}}\n'
            else:
                body = f"pub fn f{k}(conn: &Connection) {{\n    f{k + 1}(conn);\n}}\n"
            files[name] = head + body
            call = f"f{k + 1}(conn)"
        else:  # ts
            head = "" if last else f'import {{ f{k + 1} }} from "./l{k + 1}";\n\n'
            if k == 0:
                body = "export const rows = f1(db);\n"
            elif last:
                body = f'export function f{k}(db: Db) {{\n  return db.query("SELECT id FROM orders");\n}}\n'
            else:
                body = f"export function f{k}(db: Db) {{\n  return f{k + 1}(db);\n}}\n"
            files[name] = head + body
            call = f"f{k + 1}(db)"
        if last:
            exp.append(own(name, "read", "orders", "FROM orders"))
        else:
            fn = call.split("(")[0]
            exp.append(via(name, "read", "orders", depth - k, call, fn, f"l{k + 1}.{ext}"))
    return files, exp


for _lang, _ext in (("php", "php"), ("python", "py"), ("go", "go"), ("rust", "rs"), ("ts", "ts")):
    for _d in (1, 2, 3, 4):
        _files, _exp = _chain(_lang, _ext, _d)
        _tags = ["limit:depth"] if _lang == "php" and _d >= 2 else []
        if _lang == "python":
            _tags = ["limit:no_import_follow"]
        case(f"{_lang}_chain{_d}", _lang, f"call_depth_{_d}", {k: v for k, v in _files.items()}, _exp, tags=_tags)

# =====================================================================================
# Resolution and output
# =====================================================================================


def _line_of(text_: str, anchor: str, where: str) -> int:
    hits = [i + 1 for i, ln in enumerate(text_.split("\n")) if anchor in ln]
    if not hits:
        raise SystemExit(f"anchor not found: {anchor!r} in {where}")
    if len(hits) > 1:
        raise SystemExit(f"anchor not unique ({hits}): {anchor!r} in {where}")
    return hits[0]


def build() -> tuple[dict[str, str], dict]:
    """Return ({relative output path: text}, answers document)."""
    out: dict[str, str] = {}
    entries = []
    for c in sorted(CASES, key=lambda x: x["id"]):
        base = f"{c['lang']}/{c['id']}"
        per_file: dict[str, dict] = {}
        for rel, body in sorted(c["files"].items()):
            path = f"{base}/{rel}"
            out[f"{CORPUS}/{path}"] = body
            e = {k: [] for k in KINDS}
            e.update(
                file=path,
                case=c["id"],
                lang=c["lang"],
                category=c["category"],
                set=c["set"],
                tags=c["tags"],
                note=c["note"],
            )
            per_file[rel] = e
        for kind, rel, f in c["exp"]:
            if rel not in per_file:
                raise SystemExit(f"{c['id']}: expectation for unknown file {rel}")
            text_ = c["files"][rel]
            line = _line_of(text_, f["anchor"], f"{c['id']}/{rel}")
            item = {k: v for k, v in f.items() if k not in ("anchor", "fn", "target", "how")}
            item["line"] = line
            if kind == "own" and f.get("how"):
                item["how"] = f["how"]
            if kind in ("via", "beyond_depth"):
                item["how"] = f"line {line} {f['fn']}() -> {c['lang']}/{c['id']}/{f['target']}"
            if kind == "own":
                item = {k: item[k] for k in ("table", "mode", "line", "certainty", "how") if k in item}
            per_file[rel][kind].append(item)
        for rel in sorted(per_file):
            e = per_file[rel]
            for k in KINDS:
                e[k].sort(key=lambda it: (it.get("line", 0), json.dumps(it, sort_keys=True)))
            e["has_sql"] = any(
                e[k] for k in ("own", "candidates", "any_table", "unreadable", "text_only", "system", "commented_out")
            ) or any(i.get("what") != "prose" for i in e["not_a_table"])
            entries.append(e)
    entries.sort(key=lambda e: e["file"])
    doc = {
        "corpus": "synthetic",
        "generated_by": "rewrite/truth/tools/make_synthetic.py",
        "root": CORPUS,
        "note": (
            "Answers are fixed by construction (the generator writes each file together with "
            "what it touches); no implementation was run to produce them."
        ),
        "conventions": {
            "depth": "via depth 1 = the callee holds the SQL; up to 3 required, deeper is beyond_depth",
            "certainty": "direct | resolved (same-file constant or literal) | traced (argument decided by call sites)",
            "commented_out": "not counted as a read or write",
            "create_table_like": "the source table is a read",
            "argument_decided_table": "own of the callee with certainty traced, plus a depth-1 via for each caller",
            "text_only": "SQL built as text and only checked; a statement sent to a stubbed DB function is counted",
            "system": "catalogue tables are listed apart from business tables",
            "set": "must = one correct answer; reference = answer fixed but policy or dialect leaves room",
        },
        "files": entries,
    }
    out["answers.json"] = json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    out[f"{CORPUS}/.omitnix.yaml"] = (
        "include:\n  - '**/*.php'\n  - '**/*.py'\n  - '**/*.go'\n  - '**/*.rs'\n"
        "  - '**/*.ts'\n  - '**/*.sql'\n"
    )
    out["README.md"] = readme(doc)
    return out, doc


def readme(doc: dict) -> str:
    files = doc["files"]
    by_case = {}
    for e in files:
        by_case.setdefault(e["case"], e)
    cases_by_set = Counter(e["set"] for e in by_case.values())
    cases_by_lang = Counter(e["lang"] for e in by_case.values())
    files_by_lang = Counter(e["lang"] for e in files)
    kind_counts = Counter()
    kind_must = Counter()
    for e in files:
        for k in KINDS:
            kind_counts[k] += len(e[k])
            if e["set"] == "must":
                kind_must[k] += len(e[k])
    cat_counts = Counter(e["category"] for e in by_case.values())
    tag_cases: dict[str, list[str]] = {}
    for e in by_case.values():
        for t in e["tags"]:
            tag_cases.setdefault(t, []).append(e["case"])
    lines = [
        "# Synthetic truth corpus",
        "",
        "Small invented repositories where the correct answer is fixed by how they are made.",
        "`rewrite/truth/tools/make_synthetic.py` writes each source file together with the list",
        "of what it touches, and finds the line numbers by searching the generated text. omitnix",
        "is never run to produce an answer. Every name is invented (orders, customers, ...).",
        "",
        "Regenerate: `python rewrite/truth/tools/make_synthetic.py` (add `--check` to confirm the",
        "files on disk are what the script produces). The output is deterministic.",
        "",
        "## Layout",
        "",
        "`corpus/<lang>/<case>/...` holds the sources (one directory per case, so calls between",
        "files stay inside the case). `corpus/.omitnix.yaml` includes all six extensions.",
        "Run an implementation on `corpus/` (omitnix needs `--all-files` because it is not a",
        "git repository). `answers.json` has one entry per file, in the shape used for the",
        "answers of real repositories: `own`, `via`, `candidates`, `any_table`, `commented_out`,",
        "`not_a_table`, `unreadable`, `text_only`, `system`, plus `beyond_depth` (calls deeper",
        "than 3, not required) and the corpus fields `case`, `lang`, `category`, `set`, `tags`.",
        "File paths in the answers are relative to `corpus/`. The conventions (depth, certainty,",
        "comments, LIKE, argument-decided names, text-only, system tables) are listed under",
        "`conventions` in `answers.json` and follow plan sections 14-16.",
        "",
        "## Counts",
        "",
        f"Cases: {len(by_case)} (must {cases_by_set['must']}, reference {cases_by_set['reference']}).",
        f"Source files: {len(files)}.",
        "",
        "By language (cases / files): "
        + ", ".join(f"{k} {cases_by_lang[k]} / {files_by_lang[k]}" for k in sorted(cases_by_lang))
        + ".",
        "",
        "Expected items (all / in the must set):",
        "",
    ]
    for k in KINDS:
        lines.append(f"{k}: {kind_counts[k]} / {kind_must[k]}")
        lines.append("")
    lines += [
        "Cases by category: "
        + ", ".join(f"{k} {cat_counts[k]}" for k in sorted(cat_counts))
        + ".",
        "",
        "## Patterns known to be Python problems",
        "",
        "Tagged in `answers.json` (`tags`). The answer here is what the code says, not what",
        "Python currently reports.",
        "",
    ]
    names = {
        "defect:backtick_placeholder": "a backticked dynamic table name must not come out as a table",
        "defect:php_escape": "a PHP escaped quote must be unescaped before the SQL is read",
        "defect:plain_ddl_command": "plain CREATE / ALTER / RENAME / DROP name their table",
        "limit:no_import_follow": "Python does not follow imports, so callers get no via",
        "limit:depth": "PHP follows one hop only",
    }
    for t in sorted(tag_cases):
        lines.append(f"{t}: {names.get(t, '')} ({len(tag_cases[t])} cases)")
        lines.append("")
    lines += [
        "## Must set and reference set",
        "",
        "must: one correct answer. reference: the answer is fixed, but a dialect or an",
        "undecided policy leaves room (partial read of a statement with a dynamic clause,",
        "MERGE, UPDATE ... FROM, foreign-key targets, stored-procedure bodies). Report",
        "reference results separately. Query builders that name the table (diesel, knex)",
        "are in the must set (decided 2026-10-03).",
        "",
        "## Independent check",
        "",
        "2026-10-03. 30 expectations drawn with a fixed seed (20261003): one per",
        "(language, kind) cell first, then random fill, from the 332 expectations of the",
        "earlier corpus (own, via, candidates, any_table, commented_out, not_a_table,",
        "unreadable, text_only, system, beyond_depth; all six languages). A second reader",
        "looked only at the generated source files, decided what each file touches, and",
        "only then compared with answers.json.",
        "",
        "Result: 29 agreed, 1 disagreement (tables, modes, lines, depths and classes all",
        "matched for the 29).",
        "",
        "Disagreement: sql02_comments counted the hash line `# DELETE FROM sessions` as a",
        "comment in the must set. A hash line is a comment in MySQL only; elsewhere it is",
        "not. Fixed in the generator: the line moved to a new reference case",
        "(sql91_ref_hash_comment); sql02_comments keeps only `--` and `/* */` comments.",
        "PHP is unaffected (a hash line is a comment in every PHP SQL context here).",
        "",
        "Limit: one reader of 30 of 332; call chains were read together with their case",
        "files because a depth cannot be judged from one file.",
        "",
        "## Not covered",
        "",
        "Columns (stage 2), HTML / PowerShell / Shell, TypeScript tsx, templated PHP, and the",
        "workspace-level behaviour (the golden cases cover those). The corpus is small and",
        "written by one author; pattern coverage is checked by the 30-expectation spot check",
        "in plan C3, not by this script.",
        "",
    ]
    return "\n".join(lines)


def write(out: dict[str, str]) -> None:
    for sub in (OUT_DIR / CORPUS,):
        if sub.exists():
            shutil.rmtree(sub)
    for rel, body in out.items():
        p = OUT_DIR / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="compare with the files on disk")
    args = ap.parse_args()
    out, doc = build()
    if args.check:
        bad = []
        for rel, body in out.items():
            p = OUT_DIR / rel
            if not p.exists() or p.read_bytes() != body.encode("utf-8"):
                bad.append(rel)
        on_disk = {
            str(p.relative_to(OUT_DIR)).replace("\\", "/")
            for p in (OUT_DIR / CORPUS).rglob("*")
            if p.is_file()
        }
        extra = sorted(on_disk - set(out))
        if bad or extra:
            print("differs:", bad, "extra:", extra)
            return 1
        print("up to date:", len(out), "files")
        return 0
    write(out)
    print("wrote", len(out), "files;", len(doc["files"]), "source files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
