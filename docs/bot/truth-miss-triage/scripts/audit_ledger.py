"""Read-only population/count check. Never changes product, answers, or scoring results."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

COLUMNS = [
    "case", "file", "table", "mode", "required_or_reference", "expected_depth",
    "category", "tags", "cause_class", "disclosed", "evidence", "group_id",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-json", type=Path, required=True)
    parser.add_argument("--ledger", type=Path)
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent.parent
    root = directory.parents[2]
    ledger = args.ledger or directory / "MISSES.csv"
    score = json.loads(args.score_json.read_text(encoding="utf-8"))["synthetic"]
    answers = json.loads(
        (root / "rewrite/truth/synthetic/answers.json").read_text(encoding="utf-8")
    )
    by_file = {entry["file"]: entry for entry in answers["files"]}
    with ledger.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == COLUMNS, reader.fieldnames
        rows = list(reader)
    expected = set()
    for record in score["per_file"]:
        for missed in record["missed"]:
            mode, rest = missed.split(":", 1)
            table, depth = rest.rsplit("@", 1)
            expected.add((record["file"], mode, table, depth))
        for extra in record["false_positives"]:
            mode, table = extra.split(":", 1)
            expected.add((record["file"], mode, table, ""))
    actual = [(r["file"], r["mode"], r["table"], r["expected_depth"]) for r in rows]
    assert len(actual) == len(set(actual)), "duplicate ledger keys"
    assert set(actual) == expected, {
        "missing": sorted(expected - set(actual)), "extra": sorted(set(actual) - expected),
    }
    for row in rows:
        entry = by_file[row["file"]]
        assert row["case"] == entry["case"]
        assert row["category"] == entry["category"]
        assert row["tags"] == ";".join(entry["tags"])
        assert row["required_or_reference"] == (
            "required" if entry["set"] == "must" else "reference"
        )
        assert row["cause_class"] in "ABCDE" and len(row["cause_class"]) == 1
        assert row["disclosed"].startswith(("yes:", "no:"))
        assert row["evidence"] and row["group_id"]
    misses = [row for row in rows if row["expected_depth"] != ""]
    false_positives = [row for row in rows if row["expected_depth"] == ""]
    baseline = score["groups"]["all"]["cumulative"]["up_to_3"]
    required = score["groups"]["set:must"]["cumulative"]["up_to_3"]
    assert (baseline["found"], baseline["required"], len(misses), len(false_positives)) == (
        118, 242, 124, 3,
    )
    assert (required["found"], required["required"]) == (114, 232)
    counts = Counter(row["group_id"] for row in misses)
    all_found, required_found = baseline["found"], required["found"]
    projection = []
    for group in sorted(counts, key=lambda name: (-counts[name], name)):
        selected = [row for row in misses if row["group_id"] == group]
        classes = {row["cause_class"] for row in selected}
        assert len(classes) == 1, (group, classes)
        gain_required = sum(row["required_or_reference"] == "required" for row in selected)
        all_found += len(selected)
        required_found += gain_required
        projection.append({
            "group": group, "class": next(iter(classes)),
            "estimated_recovery_total": len(selected),
            "estimated_recovery_required": gain_required,
            "estimated_cumulative_total": all_found,
            "estimated_cumulative_required": required_found,
            "estimated_total_recall_percent": round(all_found / 242 * 100, 4),
            "estimated_required_recall_percent": round(required_found / 232 * 100, 4),
        })
    no_b = [row for row in misses if row["cause_class"] != "B"]
    print(json.dumps({
        "interpretation": "Baseline measured; all recoveries are unimplemented estimates",
        "rows": len(rows), "misses": len(misses), "false_positives": len(false_positives),
        "measured_baseline_total": baseline, "measured_baseline_required": required,
        "misses_by_class": dict(sorted(Counter(r["cause_class"] for r in misses).items())),
        "false_positives_by_class": dict(Counter(r["cause_class"] for r in false_positives)),
        "false_positive_groups": dict(Counter(r["group_id"] for r in false_positives)),
        "disclosed_by_class": {
            cls: {"yes": sum(r["cause_class"] == cls and r["disclosed"].startswith("yes:")
                             for r in misses),
                  "no": sum(r["cause_class"] == cls and r["disclosed"].startswith("no:")
                            for r in misses)} for cls in "ABCDE"
        },
        "estimated_no_B_ceiling_total": 118 + len(no_b),
        "estimated_no_B_ceiling_required": 114 + sum(
            row["required_or_reference"] == "required" for row in no_b
        ),
        "required_95_percent_target": 221,
        "projection": projection,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
