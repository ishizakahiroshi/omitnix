export function f3(db: Db) {
  return db.query("SELECT id FROM orders");
}
