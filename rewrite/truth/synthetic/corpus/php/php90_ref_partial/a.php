<?php
function filtered(PDO $pdo, string $where) {
    return $pdo->query("SELECT id FROM orders " . $where . " ORDER BY id")->fetchAll();
}
