export function recent(db: Db) {
  db.query("WITH recent AS (SELECT id FROM orders) SELECT * FROM recent");
  db.query("SELECT table_name FROM information_schema.tables");
}
