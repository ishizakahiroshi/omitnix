export function f4(db: Db) {
  return db.query("SELECT id FROM orders");
}
