test("sql text", () => {
  const sql = "SELECT id FROM orders WHERE id = 1";
  expect(sql).toContain("FROM orders");
});

test("stubbed", () => {
  const fake = new FakeDb();
  fake.query("INSERT INTO audit_log (message) VALUES ('x')");
});
