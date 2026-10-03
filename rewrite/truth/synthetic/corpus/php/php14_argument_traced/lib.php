<?php
function countRows(PDO $pdo, string $table) {
    return $pdo->query("SELECT COUNT(*) FROM $table")->fetchColumn();
}
