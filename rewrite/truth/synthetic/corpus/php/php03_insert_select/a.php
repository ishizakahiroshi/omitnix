<?php
function reindex(PDO $pdo) {
    $pdo->exec("INSERT INTO search_index (order_id, total)
                SELECT id, total FROM orders");
}
