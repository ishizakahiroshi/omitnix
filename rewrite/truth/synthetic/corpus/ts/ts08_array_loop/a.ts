export function counts(db: Db) {
  for (const t of ["orders", "customers"]) {
    db.query(`SELECT COUNT(*) FROM ${t}`);
  }
}
