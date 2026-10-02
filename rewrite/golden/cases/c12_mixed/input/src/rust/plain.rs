//! Forwards a batch to a loader. Touches no database.

pub fn run(batch: &[u32]) {
    helper.load(batch);
}
