export async function migrate(db: Db) {
  await db.query("CREATE TABLE shipments (id INT PRIMARY KEY, order_id INT)");
  await db.query("ALTER TABLE orders ADD COLUMN note TEXT");
  await db.query("RENAME TABLE legacy_orders TO archive_orders");
  await db.query("CREATE TABLE order_copy LIKE orders");
  await db.query("DROP TABLE IF EXISTS tmp_orders");
}
