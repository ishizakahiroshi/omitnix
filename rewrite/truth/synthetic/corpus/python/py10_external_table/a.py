import sys

def dump(conn):
    name = sys.argv[1]
    return conn.execute(f"SELECT * FROM `{name}`").fetchall()
