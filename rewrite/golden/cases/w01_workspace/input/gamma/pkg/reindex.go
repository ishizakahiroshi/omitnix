//go:build ignore

// Package reindex rebuilds the order search table.
package reindex

import "database/sql"

func Run(db *sql.DB) error {
	_, err := db.Exec("INSERT INTO search_index (order_id, term) SELECT id, name FROM orders")
	return err
}
