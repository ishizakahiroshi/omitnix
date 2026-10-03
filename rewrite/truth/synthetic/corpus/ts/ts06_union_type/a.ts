type ReportTable = "orders" | "customers";

export function count(db: Db, table: ReportTable) {
  return db.query(`SELECT COUNT(*) FROM ${table}`);
}
