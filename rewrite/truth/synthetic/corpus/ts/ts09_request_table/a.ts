export function browse(db: Db, req: Request) {
  return db.query(`SELECT * FROM ${req.query.table}`);
}
