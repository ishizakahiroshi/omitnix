<?php
function describe(PDO $pdo) {
    $name = $_POST['name'];
    return $pdo->query("DESCRIBE " . $name)->fetchAll();
}
