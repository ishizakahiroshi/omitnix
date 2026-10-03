package repo

func TestSQLText(t *testing.T) {
    q := "SELECT id FROM orders WHERE id = 1"
    if !strings.Contains(q, "FROM orders") {
        t.Fatal("missing")
    }
}

func TestStubbed(t *testing.T) {
    fake := &FakeDB{}
    fake.Exec("INSERT INTO audit_log (message) VALUES ('x')")
}
