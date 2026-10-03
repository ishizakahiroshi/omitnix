<?php
function oops(PDO $pdo) {
    return $pdo->query("INSERT INTO (id, total VALUES (1")->fetchAll();
}
