<?php
function browse(PDO $pdo) {
    $table = $_GET['table'];
    return $pdo->query("SELECT * FROM `$table`")->fetchAll();
}
