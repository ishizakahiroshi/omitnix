<?php
const LEDGER_TABLE = 'ledger_entries';

function postings(PDO $pdo) {
    return $pdo->query("SELECT * FROM " . LEDGER_TABLE . " WHERE posted = 1")->fetchAll();
}
