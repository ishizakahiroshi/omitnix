<?php
function peek(PDO $pdo, string $table) {
    return $pdo->query("SELECT * FROM $table LIMIT 1")->fetchAll();
}
