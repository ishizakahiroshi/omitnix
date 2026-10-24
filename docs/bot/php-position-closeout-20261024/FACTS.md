# P-20261024-004 omitnix: verified inputs

- Behavior baseline: `d68b101425f2b599156d4521e6e7025f1b151d6b`.
- Existing C2 code: `a9a55f2823384b9f8c138ccabe4de00416409b89`.
- PHP remains wholly unknown when tree-sitter reports an error. The C2 change adds
  the first ERROR/MISSING position, 1-based, with UTF-8 character columns.
- Local Python 3.14, tree-sitter 0.26.0 / PHP grammar 0.24.1: 408 pytest tests passed.
  This describes local execution, not CI or your execution environment.
- Independent local review exercised 11 invented position/Unicode/error cases without
  finding a blocking production defect. It also confirmed that the four new generic
  tests all skip when the cast/match premise no longer holds. Fix this test weakness.
- The C2 golden changes concern PHP reasons and nondeterministic workspace timings:
  19 cases, 28 files. Do not regenerate or revise their expected behavior for this task.
- c22 on a tracked-only checkout lacks `build/sub/b.dat` and `build/sub/deep/c.dat`.
  Its expected coverage is seven unclaimed files; actual coverage is five. The generic
  `build/` ignore pattern omits these inputs. The generator is the content authority.
- Five experimental rewrite implementations are local-only resources. The conductor
  will check those separately. Do not claim this request validates them.
- Upstream context: https://github.com/tree-sitter/tree-sitter-php/issues/308 and
  https://github.com/tree-sitter/tree-sitter-php/pull/309 . Neither changes the decision
  to keep unknown-file handling. No upstream contribution is requested.
