export function f1(db: Db) {
  return db.query("SELECT id FROM orders");
}
