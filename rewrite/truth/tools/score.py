"""Score an implementation of omitnix against the truth data.

An implementation is any command that behaves like ``omitnix`` (the same ``--cmd``
convention as ``rewrite/tools/run_golden.py``). The reference is not the Python output:
the answers are ``rewrite/truth/synthetic/answers.json`` (fixed by construction) and,
with ``--from-tests``, the claims people wrote by hand in the adapter tests
(``rewrite/truth/from-tests/``).

    python rewrite/truth/tools/score.py --cmd "python -m omitnix"
    python rewrite/truth/tools/score.py --cmd ./omitnix --from-tests --json out.json

What is scored on the synthetic corpus. The implementation is run on a copy of
``corpus/`` and its ``index.json`` is read; per file, the reported (mode, table) pairs
are compared with the expected ones.

* required: ``own`` (depth 0) and ``via`` up to depth 3. Recall is found / required.
* precision: reported pairs that are required or neutral / reported pairs. Neutral (never
  a false positive, never required): candidates' tables, ``beyond_depth``, ``text_only``,
  ``system`` and a via deeper than the depth being viewed. ``commented_out`` tables and
  CTE names (``not_a_table``) are forbidden: a hit is a false positive and is also counted
  as a leak.
* depth: recall for depth 0 (own), 1, 2, 3 separately; recall and precision cumulative
  for "own only", "up to 1", "up to 2", "up to 3".
* honesty: an item the file cannot give as a plain table (``any_table``, ``unreadable``,
  ``candidates``) passes when the file reports something unresolved (or, for candidates,
  all the candidate tables). Silently giving nothing fails.
* sets: ``must`` and ``reference`` are always reported apart; also per defect tag, per
  language and per category.

Only counts, case names and the invented table names of the answer files are printed;
the implementation's own output is never echoed. The answers must live under
``rewrite/truth/`` (a private repository must never be scored with this tool).
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

TRUTH = Path(__file__).resolve().parent.parent
SYNTHETIC = TRUTH / "synthetic"
FROM_TESTS = TRUTH / "from-tests"

Key = tuple[str, str, str]  # (file, mode, table)


def _norm(name: str) -> str:
    return name.strip().strip('`"[]').lower()


def _short(name: str) -> str:
    return _norm(name).rsplit(".", 1)[-1]


def run_implementation(command: list[str], root: Path) -> dict[str, Any]:
    """Run the command on ``root`` and return the parsed index. Never prints its output."""
    completed = subprocess.run(
        [*command, "--all-files", "--root", str(root)],
        cwd=root,
        capture_output=True,
        check=False,
    )
    index = root / ".omitnix" / "index.json"
    if not index.is_file():
        raise RuntimeError(f"the command wrote no index (exit {completed.returncode})")
    return json.loads(index.read_text(encoding="utf-8"))


def _records(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {record["path"]: record for record in index.get("files", [])}


def _reported(record: dict[str, Any] | None) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    if not record:
        return found
    for field, mode in (("reads", "read"), ("writes", "write")):
        item = record.get("fields", {}).get(field, {})
        if item.get("state") == "value":
            for table in item.get("value") or []:
                found.add((mode, _norm(str(table))))
    return found


def _unresolved(record: dict[str, Any] | None) -> bool:
    if not record:
        return False
    return bool(record.get("unresolved")) or record.get("status") in {"unresolved", "unknown"}


def _expected(entry: dict[str, Any]) -> dict[str, Any]:
    """Required (mode, table) -> depth; neutral tables; forbidden tables for one file."""
    required: dict[tuple[str, str], int] = {}
    for item in entry["own"]:
        required[(item["mode"], _norm(item["table"]))] = 0
    for item in entry["via"]:
        key = (item["mode"], _norm(item["table"]))
        required[key] = min(required.get(key, 9), item["depth"])
    neutral: set[str] = set()
    for item in entry["candidates"]:
        neutral.update(_norm(t) for t in item["tables"])
    for item in entry["beyond_depth"] + entry["text_only"] + entry["system"]:
        name = _norm(item["table"])
        neutral.update({name, name.rsplit(".", 1)[-1]})
    forbidden: set[str] = set()
    for item in entry["commented_out"]:
        forbidden.update(_norm(t) for t in item["tables"])
    for item in entry["not_a_table"]:
        what = item["what"]
        if what.startswith("CTE name "):
            forbidden.add(_norm(what[len("CTE name ") :]))
    forbidden -= {table for _, table in required}
    return {"required": required, "neutral": neutral, "forbidden": forbidden}


class Tally:
    """Counts for one group of files."""

    def __init__(self) -> None:
        self.files = 0
        self.required = defaultdict(int)  # depth -> n
        self.found = defaultdict(int)  # depth -> n
        self.reported_ok = defaultdict(int)  # cumulative k -> true positives
        self.reported_fp = 0
        self.leaks = 0
        self.honesty = defaultdict(lambda: [0, 0])  # class -> [passed, total]

    def add_pair(self, depth: int, found: bool) -> None:
        self.required[depth] += 1
        if found:
            self.found[depth] += 1

    def summary(self) -> dict[str, Any]:
        def ratio(a: int, b: int) -> float | None:
            return round(a / b, 4) if b else None

        out: dict[str, Any] = {"files": self.files}
        out["recall_by_depth"] = {
            str(d): {
                "found": self.found[d],
                "required": self.required[d],
                "recall": ratio(self.found[d], self.required[d]),
            }
            for d in range(4)
        }
        cumulative = {}
        for k in range(4):
            req = sum(self.required[d] for d in range(k + 1))
            fnd = sum(self.found[d] for d in range(k + 1))
            tp = self.reported_ok[k]
            cumulative[f"up_to_{k}"] = {
                "required": req,
                "found": fnd,
                "recall": ratio(fnd, req),
                "precision": ratio(tp, tp + self.reported_fp),
            }
        out["cumulative"] = cumulative
        out["false_positives"] = self.reported_fp
        out["leaks_commented_or_cte"] = self.leaks
        out["honesty"] = {
            name: {"passed": v[0], "total": v[1], "rate": ratio(v[0], v[1])}
            for name, v in sorted(self.honesty.items())
        }
        return out


def score_synthetic(index: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    records = _records(index)
    groups: dict[str, Tally] = defaultdict(Tally)
    per_file: list[dict[str, Any]] = []
    missing = 0

    for entry in answers["files"]:
        record = records.get(entry["file"])
        if record is None:
            missing += 1
        reported = _reported(record)
        exp = _expected(entry)
        required = exp["required"]
        names = [f"set:{entry['set']}", f"lang:{entry['lang']}", f"category:{entry['category']}"]
        names += [f"tag:{t}" for t in entry["tags"]] + ["all"]
        tallies = [groups[n] for n in names]
        for t in tallies:
            t.files += 1

        missed = []
        for (mode, table), depth in sorted(required.items()):
            hit = (mode, table) in reported
            for t in tallies:
                t.add_pair(depth, hit)
            if not hit:
                missed.append(f"{mode}:{table}@{depth}")
        fp = []
        leaks = 0
        for mode, table in sorted(reported):
            depth = required.get((mode, table))
            if depth is not None:
                for k in range(depth, 4):
                    for t in tallies:
                        t.reported_ok[k] += 1
                continue
            if table in exp["neutral"] or _short(table) in exp["neutral"]:
                continue
            fp.append(f"{mode}:{table}")
            forbidden = table in exp["forbidden"]
            leaks += forbidden
            for t in tallies:
                t.reported_fp += 1
                t.leaks += forbidden

        unresolved = _unresolved(record)
        for _item in entry["any_table"]:
            for t in tallies:
                t.honesty["any_table"][1] += 1
                t.honesty["any_table"][0] += unresolved
        for item in entry["unreadable"]:
            label = f"unreadable_{item['cls']}"
            for t in tallies:
                t.honesty[label][1] += 1
                t.honesty[label][0] += unresolved
        for item in entry["candidates"]:
            ok = unresolved or all(
                any((m, _norm(c)) in reported for m in ("read", "write")) for c in item["tables"]
            )
            for t in tallies:
                t.honesty["candidates"][1] += 1
                t.honesty["candidates"][0] += ok

        per_file.append(
            {
                "file": entry["file"],
                "set": entry["set"],
                "required": len(required),
                "found": len(required) - len(missed),
                "missed": missed,
                "false_positives": fp,
                "leaks": leaks,
                "reported_unresolved": unresolved,
            }
        )

    return {
        "missing_files": missing,
        "groups": {name: groups[name].summary() for name in sorted(groups)},
        "per_file": per_file,
    }


# ---- claims written by hand in the adapter tests --------------------------------------


def _config_yaml(config: dict[str, Any]) -> str:
    lines = ["include:", "  - '**/*'"]
    for key, name in (("authn", "authentication_functions"), ("authz", "authorization_functions")):
        values = config.get(key) or []
        if values:
            lines.append(f"{name}:")
            lines += [f"  - {json.dumps(v)}" for v in values]
    return "\n".join(lines) + "\n"


def _applicable(claim: dict[str, Any]) -> str | None:
    """None when the claim can be checked here, else the reason it is skipped."""
    config = claim["call"]["config"]
    if config.get("schema"):
        return "needs a schema snapshot"
    if config.get("in_scope"):
        return "needs a file scope"
    cap = claim.get("capability")
    kind = claim["kind"]
    if cap in {"READS", "WRITES"} and kind in {"values", "value_contains", "value_lacks"}:
        return None
    if cap is None and kind in {
        "code_present",
        "code_absent",
        "codes_exactly",
        "unresolved_empty",
    }:
        return None
    return "not about tables or reasons"


def _judge(claim: dict[str, Any], record: dict[str, Any] | None) -> bool:
    if record is None:
        return False
    kind = claim["kind"]
    if claim.get("capability") in {"READS", "WRITES"}:
        field = "reads" if claim["capability"] == "READS" else "writes"
        item = record.get("fields", {}).get(field, {})
        value = sorted(_norm(str(t)) for t in (item.get("value") or []))
        expected = claim["expected"]
        if kind == "values":
            return value == sorted(_norm(str(t)) for t in expected)
        if kind == "value_contains":
            return _norm(str(expected)) in value
        return _norm(str(expected)) not in value
    codes = sorted({u["code"] for u in record.get("unresolved", [])})
    if kind == "code_present":
        return claim["expected"] in codes
    if kind == "code_absent":
        return claim["expected"] not in codes
    if kind == "codes_exactly":
        return codes == sorted(set(claim["expected"]))
    return not codes


def score_from_tests(command: list[str]) -> dict[str, Any]:
    by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    skipped: dict[str, int] = defaultdict(int)
    failed: list[str] = []
    total = 0
    for path in sorted(FROM_TESTS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for claim in data["claims"]:
            reason = _applicable(claim)
            if reason:
                skipped[reason] += 1
                continue
            groups[json.dumps(claim["call"]["config"], sort_keys=True)].append(claim)
        for config_text, claims in sorted(groups.items()):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "r"
                shutil.copytree(FROM_TESTS / data["inputs_dir"], root)
                (root / ".omitnix.yaml").write_text(
                    _config_yaml(json.loads(config_text)), encoding="utf-8"
                )
                records = _records(run_implementation(command, root))
            for claim in claims:
                ok = _judge(claim, records.get(claim["call"]["file"]))
                label = f"{data['adapter']}:{claim.get('capability') or 'codes'}:{claim['kind']}"
                by_kind[label][1] += 1
                by_kind[label][0] += ok
                total += 1
                if not ok:
                    failed.append(f"{data['adapter']}/{claim['call']['file']}:{claim['line']}")
    passed = sum(v[0] for v in by_kind.values())
    return {
        "claims_checked": total,
        "passed": passed,
        "rate": round(passed / total, 4) if total else None,
        "skipped": dict(sorted(skipped.items())),
        "by_kind": {k: {"passed": v[0], "total": v[1]} for k, v in sorted(by_kind.items())},
        "failed": sorted(failed),
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:5.1f}%"


def text_report(result: dict[str, Any]) -> str:
    lines = []
    syn = result["synthetic"]
    lines.append(f"synthetic: files missing from the index: {syn['missing_files']}")
    lines.append("group                          files  recall d0/d1/d2/d3        "
                 "<=3 recall  <=3 prec  leaks")
    for name, g in syn["groups"].items():
        if name.startswith("category:") or name.startswith("lang:"):
            continue
        d = g["recall_by_depth"]
        c = g["cumulative"]["up_to_3"]
        depth_text = "/".join(_pct(d[str(i)]["recall"]).strip() for i in range(4))
        lines.append(
            f"{name:30} {g['files']:5}  {depth_text:24} {_pct(c['recall'])}  "
            f"{_pct(c['precision'])}  {g['leaks_commented_or_cte']}"
        )
    for name in ("all", "set:must", "set:reference"):
        honest = syn["groups"].get(name, {}).get("honesty", {})
        parts = [f"{k} {v['passed']}/{v['total']}" for k, v in honest.items()]
        lines.append(f"honesty {name}: " + ", ".join(parts))
    if "from_tests" in result:
        ft = result["from_tests"]
        lines.append(
            f"from-tests: {ft['passed']}/{ft['claims_checked']} claims pass "
            f"({_pct(ft['rate']).strip()}); skipped {sum(ft['skipped'].values())}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cmd", required=True, help='e.g. "python -m omitnix" or ./omitnix')
    parser.add_argument("--answers", default=str(SYNTHETIC / "answers.json"))
    parser.add_argument("--from-tests", action="store_true", help="also check the test claims")
    parser.add_argument("--json", help="write the full result (with per-file detail) here")
    args = parser.parse_args()

    answers_path = Path(args.answers).resolve()
    if TRUTH not in answers_path.parents:
        print("refusing: the answers must be under rewrite/truth/", file=sys.stderr)
        return 2
    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    command = shlex.split(args.cmd)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "corpus"
        shutil.copytree(answers_path.parent / answers["root"], root)
        index = run_implementation(command, root)
    result: dict[str, Any] = {"synthetic": score_synthetic(index, answers)}
    if args.from_tests:
        result["from_tests"] = score_from_tests(command)

    print(text_report(result))
    if args.json:
        Path(args.json).write_text(
            json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
