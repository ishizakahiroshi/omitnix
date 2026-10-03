"""Score an implementation of omitnix against the truth data.

An implementation is any command that behaves like ``omitnix`` (the same ``--cmd``
convention as ``rewrite/tools/run_golden.py``). The reference is not the Python output:
the answers are ``rewrite/truth/synthetic/answers.json`` (fixed by construction) and,
with ``--from-tests``, the claims people wrote by hand in the adapter tests
(``rewrite/truth/from-tests/``).

    python rewrite/truth/tools/score.py --cmd "python -m omitnix"
    python rewrite/truth/tools/score.py --cmd ./omitnix --from-tests --json out.json

The synthetic metric is unique file/mode/table extraction presence, grouped by
expected minimum depth, not proof of source lines, call provenance or certainty.
The public index has no structured representation for those dimensions. Candidates
are never credited as proven answers; relevant reasons count only gap disclosure.
Neutral mode/table pairs (candidate possibilities, text-only, system, beyond-depth)
are excluded from precision, not added as true positives. Forbidden names take
precedence. Missing, unknown and unclaimed files remain visible. Must/reference
sets are separate. From-tests results measure literal assertion fidelity only;
the original assertions can encode product limitations rather than correct behavior.

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
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

TRUTH = Path(__file__).resolve().parent.parent
SYNTHETIC = TRUTH / "synthetic"
FROM_TESTS = TRUTH / "from-tests"

def _norm(name: str) -> str:
    return name.strip().strip('`"[]').lower()


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
    records = {}
    for record in index.get("files", []):
        path = record["path"]
        if path in records:
            raise ValueError(f"duplicate file record: {path}")
        records[path] = record
    return records


def _reported(record: dict[str, Any] | None) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    if not record or record.get("status") not in {"analyzed", "unresolved"}:
        return found
    for field, mode in (("reads", "read"), ("writes", "write")):
        item = record.get("fields", {}).get(field, {})
        if item.get("state") == "value":
            for table in item.get("value") or []:
                found.add((mode, _norm(str(table))))
    return found


def _reason(record: dict[str, Any] | None, code: str) -> bool:
    """A relevant, explained gap, not a file-level flag or unrelated column warning.

    This checks reason-code fidelity only. The current index has no structured
    source locations or per-statement identities, so attribution remains unscored.
    """
    if not record or record.get("status") not in {"analyzed", "unresolved"}:
        return False
    return any(u.get("code") == code and isinstance(u.get("detail"), str)
               and bool(u["detail"].strip()) for u in record.get("unresolved", []))


def _expected(entry: dict[str, Any]) -> dict[str, Any]:
    """Required (mode, table) -> depth; neutral tables; forbidden tables for one file."""
    required: dict[tuple[str, str], int] = {}
    for item in entry["own"]:
        required[(item["mode"], _norm(item["table"]))] = 0
    for item in entry["via"]:
        key = (item["mode"], _norm(item["table"]))
        if not 1 <= item["depth"] <= 3:
            raise ValueError("via depth must be 1..3; use beyond_depth for deeper calls")
        required[key] = min(required.get(key, 9), item["depth"])
    neutral: set[tuple[str, str]] = set()
    for item in entry["candidates"]:
        neutral.update((item["mode"], _norm(t)) for t in item["tables"])
    for item in entry["beyond_depth"] + entry["text_only"] + entry["system"]:
        name = _norm(item["table"])
        neutral.add((item["mode"], name))
        # The public index convention normalizes catalogue tables to bare names.
        # Do not extend that alias to arbitrary schema-qualified extra tables.
        if item in entry["system"]:
            neutral.add((item["mode"], name.rsplit(".", 1)[-1]))
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
        self.neutral_reported = defaultdict(int)
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
                "precision_numerator": tp,
                "precision_denominator": tp + self.reported_fp,
                "neutral_reported": self.neutral_reported[k],
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
    missing_paths = []

    for entry in answers["files"]:
        record = records.get(entry["file"])
        if record is None:
            missing_paths.append(entry["file"])
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
                for k in range(depth):
                    for t in tallies:
                        t.neutral_reported[k] += 1
                continue
            if (mode, table) in exp["neutral"] and table not in exp["forbidden"]:
                for t in tallies:
                    for k in range(4):
                        t.neutral_reported[k] += 1
                continue
            fp.append(f"{mode}:{table}")
            forbidden = table in exp["forbidden"]
            leaks += forbidden
            for t in tallies:
                t.reported_fp += 1
                t.leaks += forbidden

        honesty = []
        for _item in entry["any_table"]:
            honesty.append(("any_table", _reason(record, "dynamic_table_name")))
        for item in entry["unreadable"]:
            code = {"dynamic": "dynamic_table_name", "broken": "sql_unreadable",
                    "unsupported": "sql_unsupported"}[item["cls"]]
            honesty.append((f"unreadable_{item['cls']}", _reason(record, code)))
        for _item in entry["candidates"]:
            # Plain table fields cannot encode candidate certainty. A relevant gap
            # is useful disclosure, but never proof that all candidates were found.
            honesty.append(("candidates_gap_disclosed", _reason(record, "dynamic_table_name")))
        for label, ok in honesty:
            for t in tallies:
                t.honesty[label][1] += 1
                t.honesty[label][0] += ok

        per_file.append(
            {
                "file": entry["file"],
                "set": entry["set"],
                "required": len(required),
                "found": len(required) - len(missed),
                "missed": missed,
                "false_positives": fp,
                "leaks": leaks,
                "reported_unresolved": bool(record and record.get("unresolved")),
                "status": record.get("status") if record else "missing",
                "honesty": [{"kind": label, "passed": ok} for label, ok in honesty],
            }
        )

    return {
        "missing_files": len(missing_paths),
        "missing_file_paths": sorted(missing_paths),
        "unknown_files": sorted(p for p, r in records.items() if r.get("status") == "unknown"),
        "unclaimed_files": sorted(p for p, r in records.items() if r.get("status") == "unclaimed"),
        "unknown_without_reason": sorted(p for p, r in records.items()
                                         if r.get("status") == "unknown"
                                         and not str(r.get("reason") or "").strip()),
        "unexpected_files": sorted(set(records) - {e["file"] for e in answers["files"]}),
        "measurement_limits": {
            "recall": "unique file/mode/table presence, grouped by expected minimum depth",
            "depth_and_certainty_provenance": "not scored: absent from index schema",
            "source_lines": "not scored: absent from index schema",
            "candidate_resolution": "not scored",
            "reason_attribution": "file-level code/detail only; not per source statement",
            "neutral": "mode-matched pairs excluded from precision, never rewarded",
        },
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


VALUE_KINDS = {"values", "value_contains", "value_lacks", "value_starts_with"}
REASON_KINDS = {"code_present", "code_absent", "codes_exactly", "unresolved_empty",
                "detail_contains", "detail_lacks", "details_nonempty"}
CAPABILITIES = {"READS", "WRITES", "SUMMARY", "AUTHENTICATION", "AUTHORIZATION", "SCREEN_TO_API"}


def _applicable(claim: dict[str, Any]) -> str | None:
    """None when the claim can be checked here, else the visible skip reason."""
    config = claim["call"]["config"]
    if config.get("schema"):
        return "needs a schema snapshot"
    if config.get("in_scope") is not None:
        return "needs a file scope"
    if claim.get("capability") in CAPABILITIES and claim["kind"] in VALUE_KINDS:
        return None
    if claim.get("capability") is None and claim["kind"] in REASON_KINDS:
        return None
    return "unsupported claim kind or capability"


def _judge(claim: dict[str, Any], record: dict[str, Any] | None) -> bool:
    """Reproduce the literal assertion, including case, list order and multiplicity.

    Extraction fidelity is not the synthetic product contract. Empty assertions
    require a readable record and an observed field, never unknown/out-of-scope.
    """
    kind, cap = claim["kind"], claim.get("capability")
    if kind not in VALUE_KINDS | REASON_KINDS:
        raise ValueError(f"unsupported claim kind: {kind}")
    if not record or record.get("status") not in {"analyzed", "unresolved"}:
        return False
    expected = claim["expected"]
    if kind in VALUE_KINDS:
        if cap not in CAPABILITIES:
            raise ValueError(f"unsupported capability: {cap}")
        item = record.get("fields", {}).get(cap.lower(), {})
        state = item.get("state")
        if state == "not_configured" and cap in {"AUTHENTICATION", "AUTHORIZATION"}:
            config_key = "authn" if cap == "AUTHENTICATION" else "authz"
            if claim["call"]["config"].get(config_key) != []:
                return False
            value = []  # adapter's empty configured-name result, explicitly unconfigured
        elif state in {"value", "none_observed"} and "value" in item:
            value = item["value"]
        else:
            return False
        if cap == "SUMMARY":
            if state == "none_observed" and value is None:
                value = ""  # scalar empty string is serialized as null by the document contract
            if not isinstance(value, str):
                return False
        elif not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            return False
        if kind == "values":
            return value == expected
        if kind == "value_contains":
            return expected in value
        if kind == "value_lacks":
            return expected not in value
        return isinstance(value, str) and value.startswith(expected)
    reasons = record.get("unresolved")
    if not isinstance(reasons, list) or any(
        not isinstance(u, dict) or not isinstance(u.get("code"), str)
        or not isinstance(u.get("detail"), str) for u in reasons
    ):
        return False
    codes = {u["code"] for u in reasons}
    if kind == "code_present":
        return expected in codes
    if kind == "code_absent":
        return expected not in codes
    if kind == "codes_exactly":
        return codes == set(expected)
    if kind == "unresolved_empty":
        return not reasons
    if kind == "details_nonempty":
        return all(u["detail"].strip() for u in reasons)  # source assert is vacuous on []
    code = claim.get("detail_code")
    if code is None:
        text = " ".join(u["detail"] for u in reasons)
    else:
        selected = next((u for u in reasons if u["code"] == code), None)
        if selected is None:
            return False
        text = selected["detail"]
    return (expected in text) == (kind == "detail_contains")


def score_from_tests(command: list[str]) -> dict[str, Any]:
    by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    skipped: dict[str, int] = defaultdict(int)
    failed: list[str] = []
    total = 0
    population = []
    for path in sorted(FROM_TESTS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for number, claim in enumerate(data["claims"], 1):
            reason = _applicable(claim)
            population.append({"id": f"{data['adapter']}:{number}", "source": data["source"],
                               "test": claim["test"], "line": claim["line"],
                               "file": claim["call"]["file"], "kind": claim["kind"],
                               "capability": claim.get("capability"), "skip_reason": reason})
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
        "claims_population": len(population),
        "claims_checked": total,
        "claims_skipped": sum(skipped.values()),
        "population_by_kind": dict(sorted(Counter(c["kind"] for c in population).items())),
        "population": population,
        "interpretation": "literal test-assertion fidelity, not product correctness",
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
    lines.append("synthetic: extraction presence only; "
                 "provenance/lines/candidate certainty unscored")
    lines.append(f"synthetic: files missing from the index: {syn['missing_files']}")
    lines.append(f"unknown files: {len(syn['unknown_files'])}; "
                 f"unclaimed files: {len(syn['unclaimed_files'])}")
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
