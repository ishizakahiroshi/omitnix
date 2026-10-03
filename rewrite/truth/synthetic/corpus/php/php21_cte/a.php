<?php
function recent(PDO $pdo) {
    return $pdo->query("WITH recent AS (SELECT id, total FROM orders WHERE id > 5)
                        SELECT r.id FROM recent r JOIN customers c ON c.id = r.id")->fetchAll();
}
