<?php
function migrate(PDO $pdo) {
    $pdo->exec("CREATE TABLE shipments (id INT PRIMARY KEY, order_id INT)");
    $pdo->exec("ALTER TABLE orders ADD COLUMN note VARCHAR(40)");
    $pdo->exec("RENAME TABLE legacy_orders TO archive_orders");
    $pdo->exec("CREATE TABLE order_copy LIKE orders");
    $pdo->exec("DROP TABLE IF EXISTS tmp_orders");
    $pdo->exec("CREATE INDEX idx_customer ON payments (customer_id)");
}
