// Read and stamp the audit trail.

const axios = require("axios");
const { db } = require("./db");

async function recent(limit) {
  await axios.get("/api/audit");
  return db.execute(`SELECT * FROM audit_log ORDER BY id DESC LIMIT ${limit}`);
}

async function search(pattern) {
  // A percent sign here is a LIKE wildcard, not a value filled in elsewhere.
  return db.execute("SELECT id FROM audit_log WHERE actor LIKE '%draft%'");
}

module.exports = { recent, search, pattern: null };
