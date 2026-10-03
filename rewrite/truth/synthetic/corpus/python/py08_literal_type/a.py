from typing import Literal

def count(conn, table: Literal["orders", "customers"]):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
