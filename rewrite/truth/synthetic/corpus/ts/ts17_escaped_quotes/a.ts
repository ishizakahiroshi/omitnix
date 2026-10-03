export function openOrders(db: Db) {
  return db.query('SELECT id FROM orders WHERE status = \'open\'');
}
