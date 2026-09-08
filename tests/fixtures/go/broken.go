// Package broken is deliberately unparseable, so that a file the analyzer cannot read
// is counted rather than skipped.
package broken

func Load(db *sql.DB {
	return "SELECT id FROM orders"
