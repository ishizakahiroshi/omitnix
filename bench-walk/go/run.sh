#!/bin/sh
# Keep compiler output out of the four-line benchmark stdout contract.
set -eu
cd "$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
GO=${GO:-go}
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
if "$GO" mod tidy >&2 && "$GO" build -p 1 -tags treesitter -o "$build_dir/benchmark" . >&2; then
    :
else
    printf '%s\n' 'Native tree-sitter build failed; running the required binding-failure fallback.' >&2
    "$GO" build -p 1 -o "$build_dir/benchmark" . >&2
fi
"$build_dir/benchmark"
