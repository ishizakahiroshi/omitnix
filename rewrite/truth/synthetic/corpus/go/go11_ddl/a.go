package repo

func Migrate(db *sql.DB) {
    db.Exec("CREATE TABLE shipments (id INT PRIMARY KEY, order_id INT)")
    db.Exec("ALTER TABLE orders ADD COLUMN note TEXT")
    db.Exec("RENAME TABLE legacy_orders TO archive_orders")
    db.Exec("CREATE TABLE order_copy LIKE orders")
    db.Exec("DROP TABLE IF EXISTS tmp_orders")
}
