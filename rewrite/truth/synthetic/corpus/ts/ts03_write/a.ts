export async function settle(db: Db, id: number) {
  await db.query("INSERT INTO payments (order_id) VALUES (?)", [id]);
  await db.query("UPDATE invoices SET paid = 1 WHERE id = ?", [id]);
  await db.query("DELETE FROM sessions WHERE order_id = ?", [id]);
  await db.query("INSERT INTO search_index (order_id) SELECT id FROM orders");
}
