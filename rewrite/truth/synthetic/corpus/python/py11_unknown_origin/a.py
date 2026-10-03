def peek(conn, table):
    return conn.execute("SELECT * FROM %s LIMIT 1" % table).fetchall()
