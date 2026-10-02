-- Retire the audit trail and fold what it recorded into the search table.

ALTER TABLE audit_log ADD COLUMN seen TINYINT NOT NULL DEFAULT 0;

INSERT INTO search_index (order_id, term)
  SELECT id, actor FROM audit_log;

TRUNCATE TABLE audit_log;

DROP TABLE audit_log;
