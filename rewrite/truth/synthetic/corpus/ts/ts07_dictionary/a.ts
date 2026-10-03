const REPORT_TABLES = { sales: "orders", billing: "invoices" };

export function report(db: Db, kind: "sales" | "billing") {
  const t = REPORT_TABLES[kind];
  return db.query(`SELECT COUNT(*) FROM ${t}`);
}
