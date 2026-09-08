-- One statement here cannot be read. The tables of the others must survive it, and the
-- statement that could not be read must be counted rather than passed over.

SELECT id FROM orders WHERE id = 1;

NOT SQL AT ALL ### ;

DELETE FROM audit_log WHERE id = 1;
