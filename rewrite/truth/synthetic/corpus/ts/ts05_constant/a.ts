const LEDGER = "ledger_entries" as const;

export function postings(db: Db) {
  return db.query(`SELECT * FROM ${LEDGER} WHERE posted = 1`);
}
