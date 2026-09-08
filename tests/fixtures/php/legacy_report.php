<?php
/**
 * Holds a statement the SQL parser cannot read.
 *
 * The statement below is malformed on purpose. The point of the fixture is that an
 * unreadable statement is reported, not skipped: a file whose only query could not be
 * read must not look identical to a file that queries nothing.
 */

require_session();

$rows = $db->query('SELECT id FROM orders WHERE ((( id = 1');
