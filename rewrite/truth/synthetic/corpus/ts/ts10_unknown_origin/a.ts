export function peek(db: Db, table: string) {
  return db.query(`SELECT * FROM ${table} LIMIT 1`);
}
