//! Counts orders in a batch. Touches no database.

pub fn count(batch: &[u32]) -> usize {
    batch.len()
}
