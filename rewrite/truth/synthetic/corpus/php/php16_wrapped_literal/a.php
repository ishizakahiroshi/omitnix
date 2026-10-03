<?php
function tableName() {
    return 'shipments';
}

function shipments(PDO $pdo) {
    $t = tableName();
    return $pdo->query("SELECT * FROM $t")->fetchAll();
}
