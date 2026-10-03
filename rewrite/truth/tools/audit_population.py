"""Enumerate the public audit population; no analyzer output supplies any answer.

The manifest is evidence to review, not an automated correctness verdict. Primary
source/answer review decisions are in docs/bot/truth-scoring-review/SOURCE_REVIEW.md.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

from score import _applicable

ROOT = Path(__file__).resolve().parents[3]
TRUTH = ROOT / "rewrite/truth"
OUT = ROOT / "docs/bot/truth-scoring-review/COVERAGE.json"
KINDS = ("own", "via", "candidates", "any_table", "commented_out", "not_a_table",
         "unreadable", "text_only", "system", "beyond_depth")


def legacy_skip(claim):
    """Applicability at instruction 1451cae (kept for the 97/95 denominator audit)."""
    config = claim["call"]["config"]
    if config.get("schema"):
        return "needs a schema snapshot"
    if config.get("in_scope"):
        return "needs a file scope"
    if (claim.get("capability") in {"READS", "WRITES"}
            and claim["kind"] in {"values", "value_contains", "value_lacks"}):
        return None
    if claim.get("capability") is None and claim["kind"] in {
        "code_present", "code_absent", "codes_exactly", "unresolved_empty"
    }:
        return None
    return "not about tables or reasons"


def build():
    answers = json.loads((TRUTH / "synthetic/answers.json").read_text())
    synthetic, claims, excluded, partial = [], [], [], []
    for e in answers["files"]:
        source = (TRUTH / "synthetic/corpus" / e["file"]).read_bytes()
        lines = source.decode().splitlines()
        items = []
        for kind in KINDS:
            for i, item in enumerate(e[kind], 1):
                items.append({"id": f"{e['file']}:{kind}:{i}", "kind": kind,
                              "expected": item, "source_line": lines[item["line"] - 1]})
        synthetic.append({"file": e["file"], "case": e["case"], "set": e["set"],
                          "lang": e["lang"], "category": e["category"],
                          "source_sha256": hashlib.sha256(source).hexdigest(), "items": items})
    for p in sorted((TRUTH / "from-tests").glob("*.json")):
        doc = json.loads(p.read_text())
        source = (ROOT / doc["source"]).read_text()
        tree = ast.parse(source)
        nodes = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        represented = set()
        for i, c in enumerate(doc["claims"], 1):
            claims.append({"id": f"{doc['adapter']}:{i}", "source": doc["source"],
                           "assertion_line": source.splitlines()[c["line"] - 1],
                           "claim": c, "original_skip": legacy_skip(c),
                           "current_skip": _applicable(c)})
            represented.add((c["test"], c["line"]))
            if c["kind"] == "details_nonempty":
                for n in ast.walk(nodes[c["test"]]):
                    if isinstance(n, ast.For) and n.lineno == c["line"]:
                        represented.update((c["test"], a.lineno) for a in ast.walk(n)
                                           if isinstance(a, ast.Assert))
        extracted_tests = {c["test"] for c in doc["claims"]}
        for skip in doc["not_extracted"]:
            excluded.append({"source": doc["source"], **skip})
        for name in sorted(extracted_tests):
            for a in ast.walk(nodes[name]):
                if isinstance(a, ast.Assert) and (name, a.lineno) not in represented:
                    partial.append({"source": doc["source"], "test": name,
                                    "line": a.lineno, "assertion": ast.unparse(a)})
    cases = {e["case"]: e for e in synthetic}
    return {
        "instruction_sha": "1451cae88b7f5f45ebd7077aaf2a880989e47298",
        "interpretation": "enumeration, not a correctness verdict or execution result",
        "counts": {"synthetic_files": len(synthetic), "synthetic_cases": len(cases),
                   "synthetic_items": sum(len(e["items"]) for e in synthetic),
                   "synthetic_categories": dict(sorted(Counter(
                       e["category"] for e in cases.values()).items())),
                   "synthetic_kinds": dict(sorted(Counter(
                       i["kind"] for e in synthetic for i in e["items"]).items())),
                   "extracted_claims": len(claims), "unextracted_tests": len(excluded),
                   "unrepresented_assertions_in_extracted_tests": len(partial)},
        "synthetic": synthetic, "claims": claims, "unextracted_tests": excluded,
        "unrepresented_assertions_in_extracted_tests": partial,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = json.dumps(build(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.check:
        if not OUT.exists() or OUT.read_bytes() != payload.encode():
            print("audit population differs")
            return 1
        print("audit population up to date")
    else:
        OUT.write_text(payload, encoding="utf-8", newline="\n")
        print("wrote audit population")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
