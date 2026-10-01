# Java containment-walk benchmark

Standalone Java benchmark based on commit
374e5bb337ec0f7e0f4a47d97c70083a306eb1ed. Only bench-walk/java/ is added.
The program does not import omitnix, modify product code, or call build_report.

## Run

From the repository root, using a Java 21+ runtime with the jdk.compiler module:

    ./bench-walk/java/run.sh > bench-walk/java/RESULT.txt
    ./bench-walk/java/run.sh --test

Set JAVA if the executable is not named java. The runner compiles through
jdk.compiler/com.sun.tools.javac.Main, so a separate javac launcher is unnecessary.
Compilation and tests write to stderr; compilation is outside all walk timers.
Temporary classes are removed when the runner exits. Set TMPDIR to a writable
directory with sufficient space if needed. JVM flags are -Xmx256m and
-XX:ActiveProcessorCount=1, for both compilation and the measured JVM.

The normal program emits exactly four stdout lines: S, N, M, then either the
real parse result or exactly parse java BINDING_FAILED. Counter checks are explicit
AssertionErrors and remain active without the -ea flag. Numeric output uses
Locale.ROOT and milliseconds with one decimal place.

## Algorithm and timing

Generate every range and sort by start ascending, end descending before timing.
For each candidate scan accepted ranges from the front in insertion order, count
one comparison for each whole containment predicate, stop at the first match,
and append only when none contains it:

    outer.start <= candidate.start && candidate.end <= outer.end

No reverse scan, accepted-list filtering, pre-check, or alternate algorithm is
used. One complete warm-up is followed by five measured repetitions. Report the
minimum duration; assert counters after the warm-up and every measured run.
System.nanoTime encloses only walk. Input generation, sorting, parser setup,
parsing, tree traversal, Git reads, cross-file summation, printing, and counter
assertions are outside the timed regions.

Required synthetic datasets and asserted candidates / comparisons / remaining:
- S: (i, i+1), i=0..824: 825 / 339900 / 825
- N: i=0..199, outer (i*1000, i*1000+500), and twenty inner ranges
  (i*1000+1+j, i*1000+2+j), j=0..19: 4200 / 421900 / 200
- M: (i, i+1), i=0..3999: 4000 / 7998000 / 4000

## Actual tree-sitter attempt and coverage

The implementation uses the real Tree Sitter NG Java/JNI API through reflection;
reflection allows the synthetic benchmark to run when native dependencies are
missing. It does not substitute regex extraction or a different parser.
Dependencies are pinned in dependencies.txt:
- io.github.bonede:tree-sitter:0.26.6
- io.github.bonede:tree-sitter-python:0.25.0

With these JARs and their native libraries available, set
BENCH_TREESITTER_CLASSPATH to the two JAR paths separated by a colon and run the
same command. Dependencies are not downloaded automatically by run.sh.

The intended parser coverage is every tracked .py and .pyi blob at the fixed
base commit (67 .py plus one .pyi). Enumerate all 158 tracked paths with git
ls-tree, then read matching original blobs with git show BASE:path, ignoring
worktree changes and the benchmark itself. Other extensions (90 files) are
outside this Python-grammar coverage. Collect actual string and
concatenated_string nodes, including nested strings in interpolations. Include
recovery trees and files with zero captured nodes; do not silently discard them.
Binary concatenation expressions and non-string node types are not captured.

Sort candidates separately per file. The same walk starts with an empty accepted
list for each file, so byte offsets from different files are never compared.
The parse benchmark warms the entire corpus once, then makes five passes. Each
pass sums its per-file walk durations; output the minimum total and aggregate
candidates, comparisons, and remaining counts, asserting repeatability.

For the recorded run, NO source files were parsed. There was no installed
org.treesitter.TSParser class. An actual attempt to download the pinned core JAR
from Maven Central returned HTTP 403, so native preparation could not finish.
The measured program then independently confirmed ClassNotFoundException and
emitted the required BINDING_FAILED fourth line. The successful native parsing
path remains unverified; no parse counts or parse timings were invented.

Dependency documentation:
- https://github.com/bonede/tree-sitter-ng
- https://central.sonatype.com/artifact/io.github.bonede/tree-sitter/0.26.6
- https://central.sonatype.com/artifact/io.github.bonede/tree-sitter-python

## Recorded runtime and checks

OpenJDK 21.0.12.1+1-1-deb13u1-Debian, OpenJDK 64-Bit Server VM, Linux amd64.
The installed compiler module reports javac 21.0.12.1. This stripped runtime
lacks usable --release metadata for source-file launch, so run.sh uses the
compiler module directly without --release. GCC is not used by these checks.

Compilation passed with -Xlint:all -Werror. Ten standalone checks passed:
S/N/M counts, front-first early break, sort order, empty input, equality,
exactly one warm-up plus five walks, per-file state isolation, and rejecting
incorrect expected counters. The normal stdout was checked to contain exactly
four correctly formatted lines. Shell syntax, Git whitespace checks, and the
structural secrets scan passed; private watchlists were unavailable.

RESULT.txt contains only actual measured stdout. These observations include JVM
JIT behavior after exactly the requested single warm-up on shared cloud hardware.
They are not a cross-language ranking. No product test/gate/dogfood command ran.
