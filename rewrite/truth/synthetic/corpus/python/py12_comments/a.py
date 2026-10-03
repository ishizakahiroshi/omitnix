# conn.execute("SELECT * FROM coupons")
def live(conn):
    conn.execute("SELECT id FROM customers")  # was: SELECT id FROM payments
    conn.execute("SELECT id FROM orders WHERE note = 'a -- b' AND tag = '#vip'")
    # conn.execute("DELETE FROM sessions")
