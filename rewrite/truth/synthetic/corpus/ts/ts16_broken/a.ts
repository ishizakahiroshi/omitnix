export function oops(db: Db) {
  return db.query("INSERT INTO (id, total VALUES (1");
}
