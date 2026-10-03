// db.query("SELECT * FROM coupons");
export function live(db: Db) {
  db.query("SELECT id FROM customers"); // was: SELECT id FROM payments
  db.query("SELECT id FROM orders WHERE url = 'http://shop.test/c' AND note = 'a -- b'");
  /* db.query("UPDATE ledger_entries SET posted = 1"); */
}
