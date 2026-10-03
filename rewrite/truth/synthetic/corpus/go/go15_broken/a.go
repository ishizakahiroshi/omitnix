package repo

func Oops(db *sql.DB) {
    db.Query("INSERT INTO (id, total VALUES (1")
}
