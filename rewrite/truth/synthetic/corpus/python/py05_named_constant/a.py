LEDGER = "ledger_entries"

def postings(conn):
    return conn.execute(f"SELECT * FROM {LEDGER} WHERE posted = 1").fetchall()
