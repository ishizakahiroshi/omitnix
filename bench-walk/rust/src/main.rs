//! Isolated benchmark: intentionally keep the insertion-order quadratic walk.
use std::cmp::Reverse;
use std::hint::black_box;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, Instant};

const BASE: &str = "374e5bb337ec0f7e0f4a47d97c70083a306eb1ed";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Range {
    start: usize,
    end: usize,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Stats {
    candidates: usize,
    comparisons: u64,
    remaining: usize,
}

fn sort_ranges(ranges: &mut [Range]) {
    ranges.sort_by_key(|range| (range.start, Reverse(range.end)));
}

// Do not reverse the accepted scan, index it, or replace it with a sweep.
// The input is opaque to the optimizer at the timed call site. Keeping this
// function out-of-line prevents constant-folding synthetic expected counts.
#[inline(never)]
fn walk(ranges: &[Range]) -> Stats {
    let mut accepted: Vec<Range> = Vec::new();
    let mut comparisons = 0_u64;
    for &candidate in ranges {
        let mut contained = false;
        for outer in &accepted {
            comparisons += 1;
            if outer.start <= candidate.start && candidate.end <= outer.end {
                contained = true;
                break;
            }
        }
        if !contained {
            accepted.push(candidate);
        }
    }
    black_box(&accepted);
    Stats {
        candidates: ranges.len(),
        comparisons,
        remaining: accepted.len(),
    }
}

fn walk_files(files: &[Vec<Range>]) -> Stats {
    let mut total = Stats::default();
    for ranges in files {
        // Byte ranges in different files are different coordinate spaces.
        let result = walk(black_box(ranges));
        total.candidates += result.candidates;
        total.comparisons += result.comparisons;
        total.remaining += result.remaining;
    }
    total
}

fn measure(mut operation: impl FnMut() -> Stats, expected: Option<Stats>) -> (Stats, Duration) {
    let warm = black_box(operation()); // Exactly one untimed warm-up.
    if let Some(expected) = expected {
        assert_eq!(warm, expected, "warm-up counts differ from the contract");
    }
    let mut best = Duration::MAX;
    for _ in 0..5 {
        let start = Instant::now();
        let result = operation();
        let elapsed = start.elapsed();
        black_box(result);
        assert_eq!(result, warm, "measured run changed operation counts");
        best = best.min(elapsed);
    }
    (warm, best)
}

fn disjoint(count: usize) -> Vec<Range> {
    (0..count)
        .map(|i| Range {
            start: i,
            end: i + 1,
        })
        .collect()
}

fn nested() -> Vec<Range> {
    let mut ranges = Vec::new();
    for i in 0..200 {
        let start = i * 1000;
        ranges.push(Range {
            start,
            end: start + 500,
        });
        for j in 0..20 {
            ranges.push(Range {
                start: start + 1 + j,
                end: start + 2 + j,
            });
        }
    }
    ranges
}

fn git(root: &Path, arguments: &[&str]) -> Result<Vec<u8>, String> {
    let output = Command::new("git")
        .current_dir(root)
        .args(arguments)
        .output()
        .map_err(|error| format!("cannot run git: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "git {:?} failed: {}",
            arguments,
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    Ok(output.stdout)
}

fn collect_strings(tree: &tree_sitter::Tree) -> Vec<Range> {
    let mut ranges = Vec::new();
    let mut cursor = tree.walk();
    loop {
        let node = cursor.node();
        // Exact grammar node names, matching Python sql.literal captures.
        // Visit children even for strings, so nested f-string literals remain
        // candidates to be filtered by the SAME timed containment walk.
        if matches!(node.kind(), "string" | "concatenated_string") {
            ranges.push(Range {
                start: node.start_byte(),
                end: node.end_byte(),
            });
        }
        if cursor.goto_first_child() {
            continue;
        }
        loop {
            if cursor.goto_next_sibling() {
                break;
            }
            if !cursor.goto_parent() {
                return ranges;
            }
        }
    }
}

fn parse_inputs(root: &Path) -> Result<Option<Vec<Vec<Range>>>, String> {
    let mut parser = tree_sitter::Parser::new();
    if let Err(error) = parser.set_language(&tree_sitter_python::LANGUAGE.into()) {
        eprintln!("Python tree-sitter binding initialization failed: {error}");
        return Ok(None);
    }
    let inventory = git(root, &["ls-tree", "-r", "--name-only", "-z", BASE])?;
    let mut files = Vec::new();
    let mut tracked = 0;
    let mut errors = Vec::new();
    for raw_path in inventory
        .split(|&byte| byte == 0)
        .filter(|path| !path.is_empty())
    {
        tracked += 1;
        let path = std::str::from_utf8(raw_path).map_err(|error| error.to_string())?;
        if !path.ends_with(".py") && !path.ends_with(".pyi") {
            continue;
        }
        // Read the pinned Git object, not a changed working-tree file.
        let source = git(root, &["show", &format!("{BASE}:{path}")])?;
        let tree = parser
            .parse(&source, None)
            .ok_or_else(|| format!("tree-sitter produced no tree for {path}"))?;
        if tree.root_node().has_error() {
            // Recovery trees are still real ASTs: count this file rather than
            // silently omit the repository's intentionally broken fixture.
            errors.push(path.to_owned());
        }
        let mut ranges = collect_strings(&tree);
        sort_ranges(&mut ranges); // Extraction and sorting are never timed.
        files.push(ranges);
    }
    if files.is_empty() {
        return Err("the pinned commit contains no supported .py/.pyi files".into());
    }
    eprintln!(
        "parse coverage: {} of {} tracked files (.py/.pyi); {} other-extension files excluded",
        files.len(),
        tracked,
        tracked - files.len()
    );
    for path in errors {
        eprintln!("tree-sitter recovery tree included: {path}");
    }
    Ok(Some(files))
}

fn main() -> Result<(), String> {
    // Generation and sorting happen before any warm-up or measured operation.
    let scenarios = [
        (
            "S",
            disjoint(825),
            Stats {
                candidates: 825,
                comparisons: 339_900,
                remaining: 825,
            },
        ),
        (
            "N",
            nested(),
            Stats {
                candidates: 4_200,
                comparisons: 421_900,
                remaining: 200,
            },
        ),
        (
            "M",
            disjoint(4_000),
            Stats {
                candidates: 4_000,
                comparisons: 7_998_000,
                remaining: 4_000,
            },
        ),
    ];
    for (name, mut ranges, expected) in scenarios {
        sort_ranges(&mut ranges);
        let (stats, elapsed) = measure(|| walk(black_box(&ranges)), Some(expected));
        println!(
            "walk rust {name} {} {} {} {:.1}",
            stats.candidates,
            stats.comparisons,
            stats.remaining,
            elapsed.as_secs_f64() * 1000.0
        );
    }
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    match parse_inputs(&root)? {
        Some(files) => {
            let (stats, elapsed) = measure(|| walk_files(black_box(&files)), None);
            println!(
                "parse rust ok {} {} {} {} {:.1}",
                files.len(),
                stats.candidates,
                stats.comparisons,
                stats.remaining,
                elapsed.as_secs_f64() * 1000.0
            );
        }
        None => println!("parse rust BINDING_FAILED"),
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn one_warm_up_and_exactly_five_measured_runs() {
        let mut calls = 0;
        let (result, _) = measure(
            || {
                calls += 1;
                walk(&[])
            },
            Some(Stats::default()),
        );
        assert_eq!(calls, 6);
        assert_eq!(result, Stats::default());
    }

    #[test]
    fn required_synthetic_counts() {
        for (mut ranges, expected) in [
            (
                disjoint(825),
                Stats {
                    candidates: 825,
                    comparisons: 339_900,
                    remaining: 825,
                },
            ),
            (
                nested(),
                Stats {
                    candidates: 4_200,
                    comparisons: 421_900,
                    remaining: 200,
                },
            ),
            (
                disjoint(4_000),
                Stats {
                    candidates: 4_000,
                    comparisons: 7_998_000,
                    remaining: 4_000,
                },
            ),
        ] {
            sort_ranges(&mut ranges);
            assert_eq!(walk(&ranges), expected);
        }
    }

    #[test]
    fn scan_starts_at_front_and_stops_on_first_container() {
        let ranges = [
            Range { start: 0, end: 1 },
            Range { start: 2, end: 10 },
            Range { start: 3, end: 4 },
        ];
        assert_eq!(
            walk(&ranges),
            Stats {
                candidates: 3,
                comparisons: 3,
                remaining: 2
            }
        );
    }

    #[test]
    fn sort_is_start_ascending_end_descending_and_duplicates_are_candidates() {
        let mut ranges = [
            Range { start: 1, end: 2 },
            Range { start: 0, end: 3 },
            Range { start: 0, end: 4 },
            Range { start: 0, end: 4 },
        ];
        sort_ranges(&mut ranges);
        assert_eq!(ranges[0], Range { start: 0, end: 4 });
        assert_eq!(ranges[1], Range { start: 0, end: 4 });
        assert_eq!(
            walk(&ranges),
            Stats {
                candidates: 4,
                comparisons: 3,
                remaining: 1
            }
        );
    }

    #[test]
    fn per_file_ranges_never_contain_other_files() {
        let files = vec![
            vec![Range { start: 0, end: 10 }],
            vec![Range { start: 0, end: 2 }],
        ];
        assert_eq!(
            walk_files(&files),
            Stats {
                candidates: 2,
                comparisons: 0,
                remaining: 2
            }
        );
    }

    #[test]
    fn tree_sitter_extracts_nested_string_nodes_without_regex() {
        let mut parser = tree_sitter::Parser::new();
        parser
            .set_language(&tree_sitter_python::LANGUAGE.into())
            .unwrap();
        let tree = parser.parse("value = ('one' 'two')\n", None).unwrap();
        assert!(!tree.root_node().has_error());
        let mut ranges = collect_strings(&tree);
        sort_ranges(&mut ranges);
        assert_eq!(
            walk(&ranges),
            Stats {
                candidates: 3,
                comparisons: 2,
                remaining: 1
            }
        );
    }
}
