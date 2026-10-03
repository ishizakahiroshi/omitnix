REPORT_TABLES = {"sales": "orders", "billing": "invoices"}

def report(conn, kind):
    t = REPORT_TABLES[kind]
    return conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
