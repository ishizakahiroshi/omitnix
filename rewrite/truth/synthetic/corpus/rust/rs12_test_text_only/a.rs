pub fn nothing() {}

#[cfg(test)]
mod tests {
    #[test]
    fn sql_text() {
        let sql = "SELECT id FROM orders WHERE id = 1";
        assert!(sql.contains("FROM orders"));
    }

    #[test]
    fn stubbed() {
        let fake = FakeConn::new();
        fake.execute("INSERT INTO audit_log (message) VALUES ('x')", []);
    }
}
