pub fn migrate(conn: &Connection) {
    conn.execute("CREATE TABLE shipments (id INT PRIMARY KEY, order_id INT)", []);
    conn.execute("ALTER TABLE orders ADD COLUMN note TEXT", []);
    conn.execute("RENAME TABLE legacy_orders TO archive_orders", []);
    conn.execute("CREATE TABLE order_copy LIKE orders", []);
    conn.execute("DROP TABLE IF EXISTS tmp_orders", []);
}
