"""Pull the expectations people wrote by hand out of the adapter tests.

A test such as

    result = analyze("orders_list.go")
    assert values(result, Capability.READS) == ["customers", "orders"]

says "this input, read with this configuration, must give exactly these tables". That is
a human-written expectation, independent of any language. This script finds every such
assertion by reading the test files as syntax trees (nothing is run to produce the
expectation), copies the input file, and writes the claim down as data.

What it takes, where VAR was assigned from ``analyze("literal", literal keyword
arguments)`` earlier in the same test (a name bound to ``values(...)``, ``codes(...)`` or
a joined detail text works wherever the call itself does):

    values        ``values(VAR, Capability.X) == literal`` (or ``VAR.values[Capability.X]``)
    codes_exactly ``codes(VAR) == literal``
    code_present / code_absent      ``CODE in / not in codes(VAR)``
    value_contains / value_lacks    ``"x" in / not in values(VAR, Capability.X)``; for a
                  string value such as the summary this is a substring test
    value_starts_with               ``VAR.values[Capability.X].startswith("x")``
    detail_contains / detail_lacks  ``"x" in / not in " ".join(i.detail for i in
                  VAR.unresolved)``, or in ``next(i.detail ... if i.code == "c")``
                  (``detail_code`` names the code; the first such item is read)
    unresolved_empty                ``not VAR.unresolved`` / ``VAR.unresolved == []``
    details_nonempty                ``for i in VAR.unresolved: assert i.detail.strip()``,
                  also over a tuple of file names

``a and b`` asserts split into one claim per part; a part that is not a literal (for
example a checkout path) is left out, the others are kept. Locals bound to a literal
(``schema = frozenset({...})``) can be used as keyword arguments.

Every test that yields none of these is listed with the reason. Nothing is dropped
silently.

    python rewrite/truth/tools/extract_from_tests.py            # write
    python rewrite/truth/tools/extract_from_tests.py --verify   # also re-run on Python
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TESTS = ROOT / "tests"
OUT = ROOT / "rewrite" / "truth" / "from-tests"
sys.path.insert(0, str(ROOT))

TEST_FILES = sorted(TESTS.glob("test_adapter_*.py")) + [TESTS / "test_php_adapter.py"]


def literal(node: ast.AST, names: dict[str, object]) -> object:
    """Evaluate a literal, allowing known module-level names and ``set()``/``frozenset()``."""
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in {"set", "frozenset"} and not node.args:
            return []
        if node.func.id in {"set", "frozenset"} and len(node.args) == 1:
            return literal(node.args[0], names)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [literal(e, names) for e in node.elts]
    return ast.literal_eval(node)


def capability_of(node: ast.AST) -> str | None:
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Capability"
    ):
        return node.attr
    return None


def module_names(tree: ast.Module, module) -> dict[str, object]:
    """Names usable inside a literal: module-level constants and imported code strings."""
    names: dict[str, object] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            if isinstance(target, ast.Name):
                try:
                    names[target.id] = literal(stmt.value, names)
                except (ValueError, TypeError, SyntaxError, KeyError):
                    pass
        if isinstance(stmt, ast.ImportFrom) and stmt.module and stmt.module.startswith("omitnix"):
            imported = importlib.import_module(stmt.module)
            for alias in stmt.names:
                value = getattr(imported, alias.name, None)
                if isinstance(value, str):
                    names[alias.asname or alias.name] = value
    return names


def helper_defaults(tree: ast.Module, names: dict[str, object]) -> dict[str, object]:
    """Keyword defaults of the module's ``analyze`` helper (authn / authz / schema)."""
    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef) and stmt.name == "analyze":
            out: dict[str, object] = {}
            args = stmt.args
            for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
                if default is None:
                    continue
                try:
                    out[arg.arg] = literal(default, names)
                except (ValueError, TypeError, SyntaxError, KeyError):
                    pass  # e.g. a Path constant: not part of the claim
            return out
    return {}


def analyze_call(node: ast.AST, names, defaults) -> dict | None:
    """``analyze("rel", authn=(...), ...)`` -> {"file": rel, "config": {...}}."""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "analyze"
        and node.args
    ):
        return None
    try:
        rel = ast.literal_eval(node.args[0])
        config = dict(defaults)
        for kw in node.keywords:
            config[kw.arg] = literal(kw.value, names)
    except (ValueError, TypeError, SyntaxError, KeyError):
        return None
    return {"file": rel, "config": config}


def is_parametrized(func: ast.FunctionDef) -> bool:
    return any("parametrize" in ast.unparse(d) for d in func.decorator_list)


def stubs_python(func: ast.FunctionDef) -> bool:
    """A test that replaces part of the Python adapter cannot be run by another language."""
    return any(a.arg == "monkeypatch" for a in func.args.args)


def reason_for_skip(func: ast.FunctionDef) -> str:
    body = ast.unparse(func)
    if is_parametrized(func):
        return "parametrized: the inputs come from a table in the decorator"
    if ".capabilities" in body or "ADAPTER.extensions" in body:
        return "declares the adapter's own capabilities; Python object"
    if "unknown_reason" in body or "GrammarUnavailable" in body or "monkeypatch" in body:
        return "needs a stubbed or missing grammar, or checks Python's reason text"
    if "build_report" in body or "load_config" in body:
        return "builds a report through Python objects (covered by the golden cases)"
    if "Status." in body or "FieldState" in body:
        return "checks a Python enum on a record"
    if "perf_counter" in body or "_seconds_to_analyze" in body:
        return "a timing ratio on generated input, not an expectation about a file"
    if body.count("analyze(") >= 2:
        return "compares two analysis results with each other; no literal to extract"
    if "tmp_path" in body and "write_text" in body:
        return "writes its own input file inside the test (tmp_path); no fixture file to copy"
    if "read_sql" in body or "looks_like_sql" in body or "hides_a_table_reference" in body:
        return "calls an internal Python helper, not the adapter on a file"
    return "no literal expectation in the supported forms"


def _name(node: ast.AST, ident: str) -> bool:
    return isinstance(node, ast.Name) and node.id == ident


def _unresolved_of(node: ast.AST, resolve) -> dict | None:
    """``R.unresolved`` -> the call that made R."""
    if isinstance(node, ast.Attribute) and node.attr == "unresolved":
        return resolve(node.value)
    return None


def _detail_source(node: ast.AST, resolve) -> tuple[dict, str | None] | None:
    """Text built from the details of a result's unresolved items.

    ``" ".join(item.detail for item in R.unresolved)`` is every detail;
    ``next(item.detail for item in R.unresolved if item.code == "c")`` is the first one
    with that code. Returns (call, code or None).
    """
    if not (isinstance(node, ast.Call) and len(node.args) == 1):
        return None
    gen = node.args[0]
    if not (isinstance(gen, ast.GeneratorExp) and len(gen.generators) == 1):
        return None
    comp = gen.generators[0]
    elt = gen.elt
    if not (isinstance(elt, ast.Attribute) and elt.attr == "detail"):
        return None
    call = _unresolved_of(comp.iter, resolve)
    if call is None:
        return None
    func = node.func
    if (
        isinstance(func, ast.Attribute)
        and func.attr == "join"
        and isinstance(func.value, ast.Constant)
        and func.value.value == " "
        and not comp.ifs
    ):
        return call, None
    if isinstance(func, ast.Name) and func.id == "next" and len(comp.ifs) == 1:
        cond = comp.ifs[0]
        if (
            isinstance(cond, ast.Compare)
            and isinstance(cond.ops[0], ast.Eq)
            and isinstance(cond.left, ast.Attribute)
            and cond.left.attr == "code"
        ):
            return call, ast.literal_eval(cond.comparators[0])
    return None


def extract_function(func: ast.FunctionDef, names, defaults) -> list[dict]:
    env: dict[str, dict] = {}
    claims: list[dict] = []
    codes_vars: dict[str, dict] = {}
    values_vars: dict[str, tuple[dict, str]] = {}
    detail_vars: dict[str, tuple[dict, str | None]] = {}
    local = dict(names)
    nodes = sorted(
        (n for n in ast.walk(func) if isinstance(n, (ast.Assign, ast.Assert, ast.For))),
        key=lambda n: (n.lineno, n.col_offset),
    )

    def result_of(node: ast.AST) -> dict | None:
        if isinstance(node, ast.Name):
            return env.get(node.id)
        return analyze_call(node, local, defaults)

    def values_of(node: ast.AST) -> tuple[dict, str] | None:
        """``values(R, Capability.X)`` / ``R.values[Capability.X]`` / a variable holding one."""
        if isinstance(node, ast.Name):
            return values_vars.get(node.id)
        if (
            isinstance(node, ast.Call)
            and _name(node.func, "values")
            and len(node.args) == 2
        ):
            src, cap = node.args
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "values"
        ):
            src, cap = node.value.value, node.slice
        else:
            return None
        call, key = result_of(src), capability_of(cap)
        return (call, key) if call is not None and key is not None else None

    def codes_of(node: ast.AST) -> dict | None:
        if isinstance(node, ast.Name):
            return codes_vars.get(node.id)
        if isinstance(node, ast.Call) and _name(node.func, "codes") and len(node.args) == 1:
            return result_of(node.args[0])
        return None

    def detail_of(node: ast.AST) -> tuple[dict, str | None] | None:
        if isinstance(node, ast.Name):
            return detail_vars.get(node.id)
        return _detail_source(node, result_of)

    def add(claim: dict, call: dict, node: ast.AST, **extra) -> None:
        claim.update(call=call, test=func.name, line=node.lineno, **extra)
        claims.append(claim)

    def from_compare(test: ast.Compare, node: ast.AST) -> None:
        if len(test.ops) != 1:
            return
        op, left, right = test.ops[0], test.left, test.comparators[0]
        if isinstance(op, ast.Eq):
            if (vv := values_of(left)) is not None:
                add(
                    {"kind": "values", "capability": vv[1], "expected": literal(right, local)},
                    vv[0],
                    node,
                )
            elif (cc := codes_of(left)) is not None:
                expected = sorted(literal(right, local))
                add({"kind": "codes_exactly", "capability": None, "expected": expected}, cc, node)
            elif (un := _unresolved_of(left, result_of)) is not None:
                if literal(right, local) == []:
                    claim = {"kind": "unresolved_empty", "capability": None, "expected": None}
                    add(claim, un, node)
            elif (
                isinstance(left, ast.Call)
                and _name(left.func, "len")
                and len(left.args) == 1
                and (un := _unresolved_of(left.args[0], result_of)) is not None
                and literal(right, local) == 0
            ):
                add({"kind": "unresolved_empty", "capability": None, "expected": None}, un, node)
            return
        if not isinstance(op, (ast.In, ast.NotIn)):
            return
        needle = literal(left, local)
        if not isinstance(needle, str):
            return
        positive = isinstance(op, ast.In)
        if (cc := codes_of(right)) is not None:
            kind = "code_present" if positive else "code_absent"
            add({"kind": kind, "capability": None, "expected": needle}, cc, node)
        elif (vv := values_of(right)) is not None:
            kind = "value_contains" if positive else "value_lacks"
            add({"kind": kind, "capability": vv[1], "expected": needle}, vv[0], node)
        elif (dd := detail_of(right)) is not None:
            kind = "detail_contains" if positive else "detail_lacks"
            add({"kind": kind, "capability": None, "expected": needle}, dd[0], node,
                detail_code=dd[1])

    def from_test(test: ast.AST, node: ast.AST) -> None:
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
            for part in test.values:
                from_test(part, node)
        elif isinstance(test, ast.Compare):
            try:
                from_compare(test, node)
            except (ValueError, TypeError, SyntaxError, KeyError):
                pass  # one conjunct that is not a literal does not lose the others
        elif (
            isinstance(test, ast.Call)
            and isinstance(test.func, ast.Attribute)
            and test.func.attr == "startswith"
            and len(test.args) == 1
            and (vv := values_of(test.func.value)) is not None
        ):
            try:
                prefix = ast.literal_eval(test.args[0])
            except (ValueError, SyntaxError):
                return
            add({"kind": "value_starts_with", "capability": vv[1], "expected": prefix}, vv[0], node)
        elif isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            if (un := _unresolved_of(test.operand, result_of)) is not None:
                add({"kind": "unresolved_empty", "capability": None, "expected": None}, un, node)
            elif (vv := values_of(test.operand)) is not None:
                add({"kind": "values", "capability": vv[1], "expected": []}, vv[0], node)
            elif (cc := codes_of(test.operand)) is not None:
                add({"kind": "codes_exactly", "capability": None, "expected": []}, cc, node)

    def from_for(node: ast.For) -> None:
        """``for item in R.unresolved: assert item.detail.strip()`` (also over a tuple of files)."""
        if "detail.strip()" not in ast.unparse(node):
            return
        inner = [n for n in ast.walk(node) if isinstance(n, ast.For)]
        for loop in inner:
            if loop is node and isinstance(node.iter, (ast.Tuple, ast.List)):
                continue
            files = [None]
            if isinstance(node.iter, (ast.Tuple, ast.List)) and isinstance(node.target, ast.Name):
                files = [ast.literal_eval(e) for e in node.iter.elts]
            for rel in files:
                sub = {node.target.id: ast.Constant(rel)} if rel is not None else {}
                it = loop.iter
                if isinstance(it, ast.Attribute) and it.attr == "unresolved":
                    src = it.value
                    if isinstance(src, ast.Call) and src.args and isinstance(src.args[0], ast.Name):
                        if src.args[0].id in sub:
                            src = ast.Call(
                                func=src.func,
                                args=[sub[src.args[0].id], *src.args[1:]],
                                keywords=src.keywords,
                            )
                    call = result_of(src)
                    if call is not None:
                        add({"kind": "details_nonempty", "capability": None, "expected": None},
                            call, loop)
            return

    for node in nodes:
        if isinstance(node, ast.For):
            try:
                from_for(node)
            except (ValueError, TypeError, SyntaxError, KeyError):
                pass
            continue
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            target, value = node.targets[0].id, node.value
            call = analyze_call(value, local, defaults)
            if call is not None:
                env[target] = call
            elif (cc := codes_of(value)) is not None and not isinstance(value, ast.Name):
                codes_vars[target] = cc
            elif (vv := values_of(value)) is not None and not isinstance(value, ast.Name):
                values_vars[target] = vv
            elif (dd := _detail_source(value, result_of)) is not None:
                detail_vars[target] = dd
            else:
                try:
                    local[target] = literal(value, local)
                except (ValueError, TypeError, SyntaxError, KeyError):
                    pass
            continue
        from_test(node.test, node)
    return claims

def tuple_to_list(value):
    if isinstance(value, (tuple, set, frozenset)):
        return [tuple_to_list(v) for v in value]
    if isinstance(value, list):
        return [tuple_to_list(v) for v in value]
    return value


def extract_file(path: Path) -> dict:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    module = importlib.import_module(f"tests.{path.stem}")
    names = module_names(tree, module)
    defaults = helper_defaults(tree, names)
    adapter = path.stem.removeprefix("test_adapter_").removeprefix("test_").removesuffix("_adapter")
    claims, skipped = [], []
    tests = [
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]
    for func in tests:
        skip = is_parametrized(func) or stubs_python(func)
        found = [] if skip else extract_function(func, names, defaults)
        if found:
            claims.extend(found)
        else:
            skipped.append({"test": func.name, "reason": reason_for_skip(func)})
    for claim in claims:
        claim["expected"] = tuple_to_list(claim["expected"])
        claim["call"]["config"] = tuple_to_list(claim["call"]["config"])
    return {
        "adapter": adapter,
        "source": f"tests/{path.name}",
        "tests_in_file": len(tests),
        "tests_extracted": len({c["test"] for c in claims}),
        "claims": claims,
        "not_extracted": skipped,
    }


def fixtures_dir(adapter: str) -> Path | None:
    for name in (adapter, f"{adapter}_adapter"):
        if (TESTS / "fixtures" / name).is_dir():
            return TESTS / "fixtures" / name
    return None


def verify(path: Path, doc: dict) -> dict:
    """Re-run every claim through the Python adapter's own helper, without pytest."""
    module = importlib.import_module(f"tests.{path.stem}")
    helper = getattr(module, "analyze", None)
    passed, failed, errors = 0, [], []
    for claim in doc["claims"]:
        call = claim["call"]
        kwargs = {}
        for key, val in call["config"].items():
            if isinstance(val, list):
                kwargs[key] = frozenset(val) if key in {"schema", "in_scope"} else tuple(val)
            else:
                kwargs[key] = val
        try:
            result = helper(call["file"], **kwargs)
        except Exception as exc:  # noqa: BLE001 - reported, not hidden
            errors.append({"test": claim["test"], "error": type(exc).__name__})
            continue
        found = {item.code for item in result.unresolved}
        kind = claim["kind"]
        if kind.startswith("value"):
            cap = getattr(module.Capability, claim["capability"])
            actual = result.values.get(cap)
            if not isinstance(actual, str):
                actual = list(actual or [])
            if kind == "values":
                ok = actual == claim["expected"]
            elif kind == "value_contains":
                ok = claim["expected"] in actual
            elif kind == "value_lacks":
                ok = claim["expected"] not in actual
            else:
                ok = isinstance(actual, str) and actual.startswith(claim["expected"])
        elif kind == "codes_exactly":
            ok = sorted(found) == claim["expected"]
        elif kind == "code_present":
            ok = claim["expected"] in found
        elif kind == "code_absent":
            ok = claim["expected"] not in found
        elif kind in {"detail_contains", "detail_lacks"}:
            code = claim.get("detail_code")
            if code is None:
                text = " ".join(item.detail for item in result.unresolved)
            else:
                text = next(item.detail for item in result.unresolved if item.code == code)
            ok = (claim["expected"] in text) == (kind == "detail_contains")
        elif kind == "unresolved_empty":
            ok = not result.unresolved
        else:  # details_nonempty
            ok = all(item.detail.strip() for item in result.unresolved)
        if ok:
            passed += 1
        else:
            failed.append({"test": claim["test"], "line": claim["line"]})
    return {"passed": passed, "failed": failed, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    summary = []
    for path in TEST_FILES:
        doc = extract_file(path)
        fx = fixtures_dir(doc["adapter"])
        # A claim's file can include another fixture without that helper itself
        # having an analyze() assertion (PHP summary.php -> common/reports.php).
        # Preserve the public fixture context, never the product's inferred output.
        copied = []
        claimed = {claim["call"]["file"] for claim in doc["claims"]}
        if fx is not None:
            for src in sorted(fx.rglob("*")):
                if src.is_file():
                    rel = src.relative_to(fx).as_posix()
                    dest = OUT / "inputs" / doc["adapter"] / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dest)
                    copied.append(rel)
        doc["support_inputs"] = sorted(set(copied) - claimed)
        doc["inputs_dir"] = f"inputs/{doc['adapter']}"
        if args.verify:
            doc["verified_on_python"] = verify(path, doc)
        (OUT / f"{doc['adapter']}.json").write_text(
            json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        summary.append(doc)
    total_tests = sum(d["tests_in_file"] for d in summary)
    total_ext = sum(d["tests_extracted"] for d in summary)
    total_claims = sum(len(d["claims"]) for d in summary)
    print(f"tests {total_tests}  extracted {total_ext}  claims {total_claims}")
    for d in summary:
        line = (
            f"  {d['adapter']:8} tests {d['tests_in_file']:3}"
            f"  extracted {d['tests_extracted']:3}  claims {len(d['claims']):3}"
        )
        if args.verify:
            v = d["verified_on_python"]
            line += f"  python pass {v['passed']} fail {len(v['failed'])} error {len(v['errors'])}"
        print(line)
    if args.verify and any(d["verified_on_python"]["failed"]
                           or d["verified_on_python"]["errors"] for d in summary):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
