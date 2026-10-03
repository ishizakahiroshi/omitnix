def test_sql_text():
    sql = "SELECT id FROM orders WHERE id = 1"
    assert "FROM orders" in sql

def test_stubbed(fake_db):
    fake_db.execute("INSERT INTO audit_log (message) VALUES ('x')")
    assert len(fake_db.calls) == 1
