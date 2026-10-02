"""Build a query."""

def f(t):
    require_session()
    apply_visibility_filter(t)
    cur.execute("SELECT id FROM " + t)
