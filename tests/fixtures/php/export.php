<?php
/**
 * Export one table as CSV.
 */

require_session();

$sql = 'SELECT * FROM ' . $table . ' WHERE owner = ?';
$rows = $db->query($sql);
