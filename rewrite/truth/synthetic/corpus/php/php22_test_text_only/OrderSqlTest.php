<?php
class OrderSqlTest extends TestCase {
    public function testSqlText() {
        $sql = "SELECT id FROM orders WHERE id = 1";
        $this->assertStringContainsString('FROM orders', $sql);
    }
    public function testStubbedDb() {
        $db = new FakeDb();
        $db->query("INSERT INTO audit_log (message) VALUES ('x')");
        $this->assertCount(1, $db->calls);
    }
}
