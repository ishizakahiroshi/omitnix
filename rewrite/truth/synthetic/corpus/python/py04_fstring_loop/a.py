def counts(conn):
    for t in ("orders", "customers"):
        conn.execute(f"SELECT COUNT(*) FROM {t}")
