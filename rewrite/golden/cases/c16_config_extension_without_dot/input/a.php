<?php
/**
 * Rebuild the search index overnight.
 */

$db->query('INSERT INTO search_index (order_id) SELECT id FROM orders');
