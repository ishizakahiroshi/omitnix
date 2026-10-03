<?php
require __DIR__ . '/l2.php';

function f1(PDO $pdo) {
    return f2($pdo);
}
