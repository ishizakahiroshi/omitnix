export function f2(db: Db) {
  return db.query("SELECT id FROM orders");
}
