export function countRows(db: Db, table: string) {
  return db.query(`SELECT COUNT(*) FROM ${table}`);
}
