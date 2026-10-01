#!/bin/sh
# Compile and run the standalone Java accepted-range walk benchmark.
set -eu
cd "$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
JAVA=${JAVA:-java}
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
"$JAVA" -Xmx256m -XX:ActiveProcessorCount=1 -m jdk.compiler/com.sun.tools.javac.Main -Xlint:all -Werror -d "$build_dir" Benchmark.java BenchmarkTests.java >&2
classpath="$build_dir"
if [ -n "${BENCH_TREESITTER_CLASSPATH:-}" ]; then
    classpath="$classpath:$BENCH_TREESITTER_CLASSPATH"
fi
if [ "${1:-}" = "--test" ]; then
    "$JAVA" -Xmx256m -XX:ActiveProcessorCount=1 -cp "$classpath" BenchmarkTests >&2
else
    "$JAVA" -Xmx256m -XX:ActiveProcessorCount=1 -cp "$classpath" Benchmark
fi
