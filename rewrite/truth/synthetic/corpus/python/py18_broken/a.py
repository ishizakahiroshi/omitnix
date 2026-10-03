def oops(conn):
    return conn.execute("INSERT INTO (id, total VALUES (1").fetchall()
