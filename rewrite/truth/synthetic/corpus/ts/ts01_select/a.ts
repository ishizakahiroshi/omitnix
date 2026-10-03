export async function listOrders(db: Db) {
  return db.query("SELECT id, total FROM orders WHERE total > 10");
}
