<?php
function bump(PDO $pdo, int $id) {
    $pdo->exec("INSERT INTO counters (id, n) VALUES ($id, 1) ON DUPLICATE KEY UPDATE n = n + 1");
    $pdo->exec("REPLACE INTO settings (k, v) VALUES ('a', 'b')");
}
