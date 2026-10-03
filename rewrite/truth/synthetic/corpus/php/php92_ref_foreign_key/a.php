<?php
function schema(PDO $pdo) {
    $pdo->exec("CREATE TABLE order_items (id INT, order_id INT,
                FOREIGN KEY (order_id) REFERENCES orders (id))");
}
