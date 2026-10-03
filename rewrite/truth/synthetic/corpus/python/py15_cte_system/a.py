def recent(conn):
    conn.execute("WITH recent AS (SELECT id FROM orders) SELECT * FROM recent")
    conn.execute("SELECT table_name FROM information_schema.columns")
