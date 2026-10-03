"""Hand-authored controls: do not generate expected values from implementation output."""
import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
spec = importlib.util.spec_from_file_location("truth_score", TOOLS / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


def entry(**changes):
    out = dict(file="a.sql", set="must", lang="sql", category="control", tags=[])
    for key in ("own", "via", "candidates", "any_table", "commented_out", "not_a_table",
                "unreadable", "text_only", "system", "beyond_depth"):
        out[key] = []
    out.update(changes)
    return out


def record(reads=(), writes=(), unresolved=(), status="analyzed"):
    return dict(path="a.sql", status=status, fields={
        "reads": {"state": "value" if reads else "none_observed", "value": list(reads)},
        "writes": {"state": "value" if writes else "none_observed", "value": list(writes)},
    }, unresolved=list(unresolved))


def tally(e, r):
    return score.score_synthetic({"files": [] if r is None else [r]}, {"files": [e]})


def group(e, r):
    return tally(e, r)["groups"]["all"]


@pytest.mark.parametrize("depth", range(5))
def test_depth_presence_boundaries(depth):
    item = dict(mode="read", table="orders", line=1, depth=depth)
    e = entry(**{("own" if depth == 0 else "via" if depth <= 3 else "beyond_depth"): [item]})
    yes, no = group(e, record(["orders"])), group(e, record())
    for k in range(4):
        assert yes["cumulative"][f"up_to_{k}"]["required"] == int(depth <= k)
        assert yes["cumulative"][f"up_to_{k}"]["found"] == int(depth <= k)
        assert no["cumulative"][f"up_to_{k}"]["found"] == 0
    assert yes["false_positives"] == 0


def test_duplicate_occurrences_do_not_inflate_presence_recall():
    item = dict(mode="read", table="orders", line=1)
    e = entry(own=[item, dict(item, line=2)], via=[dict(item, depth=2)])
    g = group(e, record(["orders", "orders"]))
    assert g["cumulative"]["up_to_3"]["required"] == 1
    assert g["cumulative"]["up_to_3"]["found"] == 1


def test_duplicate_file_records_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        score._records({"files": [record(), record()]})


def test_missing_file_is_named_and_not_an_empty_success():
    result = tally(entry(), None)
    assert result["missing_files"] == 1
    assert result["missing_file_paths"] == ["a.sql"]


def test_wrong_mode_and_forbidden_tables_are_detected():
    e = entry(own=[dict(mode="read", table="orders", line=1)],
              commented_out=[dict(tables=["sessions"], line=2)],
              not_a_table=[dict(what="CTE name recent", line=3)])
    g = group(e, record(["sessions", "recent"], ["orders"]))
    assert g["cumulative"]["up_to_3"]["found"] == 0
    assert g["false_positives"] == 3
    assert g["leaks_commented_or_cte"] == 2


@pytest.mark.parametrize("kind", ["text_only", "system", "beyond_depth"])
def test_neutral_extras_are_mode_and_qualification_sensitive(kind):
    e = entry(**{kind: [dict(table="orders", mode="read", depth=4)]})
    assert group(e, record(["orders"]))["false_positives"] == 0
    assert group(e, record(writes=["orders"]))["false_positives"] == 1
    assert group(e, record(["invented.orders"]))["false_positives"] == 1


def test_forbidden_wins_over_neutral():
    e = entry(text_only=[dict(table="orders", mode="read")],
              commented_out=[dict(tables=["orders"])])
    assert group(e, record(["orders"]))["leaks_commented_or_cte"] == 1


def test_neutral_pairs_are_excluded_not_rewarded_in_precision():
    e = entry(own=[dict(table="orders", mode="read")],
              text_only=[dict(table="customers", mode="read")])
    c = group(e, record(["orders", "customers", "invented"]))["cumulative"]["up_to_3"]
    assert c["precision"] == 0.5
    assert c["precision_denominator"] == 2
    assert c["neutral_reported"] == 1


@pytest.mark.parametrize("status", ["unknown", "unclaimed"])
def test_unknown_and_unclaimed_cannot_supply_table_recall(status):
    e = entry(own=[dict(table="orders", mode="read")])
    r = record(["orders"], status=status)
    assert group(e, r)["cumulative"]["up_to_3"]["found"] == 0
    assert tally(e, r)[f"{status}_files"] == ["a.sql"]


@pytest.mark.parametrize("kind,code", [
    ("any_table", "dynamic_table_name"), ("unreadable_dynamic", "dynamic_table_name"),
    ("unreadable_broken", "sql_unreadable"), ("unreadable_unsupported", "sql_unsupported"),
    ("candidates_gap_disclosed", "dynamic_table_name"),
])
def test_honesty_requires_relevant_nonempty_reason(kind, code):
    if kind.startswith("unreadable_"):
        e = entry(unreadable=[dict(cls=kind.removeprefix("unreadable_"))])
    elif kind.startswith("candidates"):
        e = entry(candidates=[dict(mode="read", tables=["orders", "customers"])])
    else:
        e = entry(any_table=[dict(mode="read")])
    good = record(unresolved=[dict(code=code, detail="source table could not be resolved")],
                  status="unresolved")
    assert group(e, good)["honesty"][kind]["passed"] == 1
    for bad in (record(status="unresolved"), record(status="unknown"),
                record(unresolved=[dict(code="select_star", detail="columns unknown")]),
                record(unresolved=[dict(code=code, detail=" ")])):
        assert group(e, bad)["honesty"][kind]["passed"] == 0


def test_plain_candidate_tables_are_not_proven_candidate_resolution():
    e = entry(candidates=[dict(mode="read", tables=["orders", "customers"])])
    g = group(e, record(["orders", "customers"]))
    assert g["honesty"]["candidates_gap_disclosed"]["passed"] == 0
    assert tally(e, record())["measurement_limits"]["candidate_resolution"] == "not scored"


def claim(kind="values", expected=None, cap="READS"):
    return dict(kind=kind, expected=[] if expected is None else expected,
                capability=cap, call=dict(file="a.sql", config={}))


@pytest.mark.parametrize("bad", [None, {"path": "a.sql"}, record(status="unknown"),
                                  record(status="unclaimed")])
@pytest.mark.parametrize("c", [claim(), claim("code_absent", "dynamic_sql", None),
                               claim("unresolved_empty", None, None)])
def test_missing_or_unread_records_never_pass_negative_claims(c, bad):
    assert not score._judge(c, bad)


@pytest.mark.parametrize("state", ["out_of_scope", "not_configured", "missing"])
def test_table_field_state_is_not_an_observed_empty_list(state):
    r = record()
    r["fields"]["reads"] = {"state": state}
    assert not score._judge(claim(), r)


def test_exact_assertions_keep_case_order_and_duplicates():
    c = claim(expected=["orders"])
    assert score._judge(c, record(["orders"]))
    assert not score._judge(c, record(["ORDERS"]))
    assert not score._judge(c, record(["orders", "orders"]))
    assert not score._judge(claim(expected=["orders", "customers"]),
                            record(["customers", "orders"]))


@pytest.mark.parametrize("c,value", [
    (claim("values", "Orders", "SUMMARY"), "Orders"),
    (claim("value_contains", "Order", "SUMMARY"), "Orders"),
    (claim("value_lacks", "@param", "SUMMARY"), "Orders"),
    (claim("value_starts_with", "Order", "SUMMARY"), "Orders"),
    (claim("values", ["requireSession"], "AUTHENTICATION"), ["requireSession"]),
    (claim("value_contains", "/api/orders", "SCREEN_TO_API"), ["/api/orders"]),
])
def test_all_capabilities_and_value_kinds(c, value):
    assert score._applicable(c) is None
    r = record()
    r["fields"][c["capability"].lower()] = dict(state="value", value=value)
    assert score._judge(c, r)
    r["fields"][c["capability"].lower()] = dict(state="out_of_scope")
    assert not score._judge(c, r)


def test_detail_kinds_preserve_first_matching_reason_and_vacuous_all():
    r = record(unresolved=[dict(code="x", detail="first"), dict(code="x", detail="second")])
    c = claim("detail_contains", "first", None)
    c["detail_code"] = "x"
    assert score._judge(c, r)
    c["expected"] = "second"
    assert not score._judge(c, r)
    c["detail_code"] = None
    assert score._judge(c, r)
    assert score._judge(claim("details_nonempty", None, None), record())
    assert not score._judge(claim("details_nonempty", None, None),
                            record(unresolved=[dict(code="x", detail=" ")]))
    assert score._judge(claim("detail_lacks", "absent", None), r)


def test_unsupported_claims_fail_closed_and_remain_explicit():
    c = claim("future_kind", None, None)
    assert score._applicable(c) is not None
    with pytest.raises(ValueError, match="unsupported"):
        score._judge(c, record())


def test_must_and_reference_stay_separate():
    must = entry(own=[dict(mode="read", table="orders")])
    ref = deepcopy(must)
    ref.update(file="b.sql", set="reference")
    result = score.score_synthetic({"files": [record(["orders"])]}, {"files": [must, ref]})
    assert result["groups"]["set:must"]["cumulative"]["up_to_3"]["recall"] == 1
    assert result["groups"]["set:reference"]["cumulative"]["up_to_3"]["recall"] == 0


def test_scalar_empty_observation_uses_document_null_without_accepting_unknown():
    r = record()
    r["fields"]["summary"] = dict(state="none_observed", value=None)
    assert score._judge(claim("values", "", "SUMMARY"), r)
    r["fields"]["summary"] = dict(state="out_of_scope")
    assert not score._judge(claim("values", "", "SUMMARY"), r)


def test_invalid_via_depth_is_rejected_instead_of_lost_from_denominator():
    with pytest.raises(ValueError, match="via depth"):
        group(entry(via=[dict(mode="read", table="orders", depth=4)]), record())


@pytest.mark.parametrize("kind,expected,yes,no", [
    ("code_present", "dynamic_sql", ["dynamic_sql"], ["select_star"]),
    ("code_absent", "dynamic_sql", ["select_star"], ["dynamic_sql"]),
    ("codes_exactly", ["dynamic_sql"], ["dynamic_sql", "dynamic_sql"], ["select_star"]),
    ("unresolved_empty", None, [], ["select_star"]),
])
def test_reason_assertion_controls(kind, expected, yes, no):
    c = claim(kind, expected, None)
    def make(codes):
        return record(unresolved=[dict(code=code, detail="explanation") for code in codes])
    assert score._judge(c, make(yes))
    assert not score._judge(c, make(no))


def test_unknown_diagnostics_keep_named_file_and_missing_reason():
    r = record(status="unknown")
    out = tally(entry(), r)
    assert out["missing_files"] == 0
    assert out["unknown_files"] == ["a.sql"]
    assert out["unknown_without_reason"] == ["a.sql"]
    r["reason"] = "grammar could not read this file"
    assert tally(entry(), r)["unknown_without_reason"] == []


def test_candidate_wrong_mode_is_a_false_positive_not_an_answer():
    e = entry(candidates=[dict(mode="read", tables=["orders", "customers"])])
    g = group(e, record(writes=["orders", "customers"]))
    assert g["false_positives"] == 2
    assert g["honesty"]["candidates_gap_disclosed"]["passed"] == 0


@pytest.mark.parametrize("cap,field", [
    ("READS", {"state": "none_observed", "value": ["orders"]}),
    ("SUMMARY", {"state": "none_observed", "value": "Orders"}),
    ("SUMMARY", {"state": "none_observed", "value": ""}),
    ("READS", {"state": "none_observed", "value": None}),
    ("READS", {"state": "none_observed"}),
    ("READS", {"state": "value", "value": []}),
    ("SUMMARY", {"state": "value", "value": ""}),
    ("AUTHENTICATION", {"state": "not_configured", "value": ["requireSession"]}),
    ("AUTHORIZATION", {"state": "not_configured", "value": []}),
    ("AUTHENTICATION", {"state": "not_configured", "value": None}),
])
def test_contradictory_observation_states_never_pass_claims(cap, field):
    c = claim("values", "Orders" if cap == "SUMMARY" else ["orders"], cap)
    c["call"]["config"] = {"authn": [], "authz": []}
    if cap.startswith("AUTH"):
        c["expected"] = []  # old conversion concealed the supplied payload
    r = record()
    r["fields"][cap.lower()] = field
    assert not score._judge(c, r)


@pytest.mark.parametrize("cap,field,expected", [
    ("READS", {"state": "none_observed", "value": []}, []),
    ("SUMMARY", {"state": "none_observed", "value": None}, ""),
    ("READS", {"state": "value", "value": ["orders"]}, ["orders"]),
    ("SUMMARY", {"state": "value", "value": "Orders"}, "Orders"),
    ("AUTHENTICATION", {"state": "not_configured"}, []),
    ("AUTHORIZATION", {"state": "not_configured"}, []),
])
def test_valid_observation_state_conversions_are_preserved(cap, field, expected):
    c = claim("values", expected, cap)
    c["call"]["config"] = {"authn": [], "authz": []}
    r = record()
    r["fields"][cap.lower()] = field
    assert score._judge(c, r)
