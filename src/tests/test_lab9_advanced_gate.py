"""M5-M7 extra checks on gate.integrity_check / gate.slice_check: traps beyond the four public ones.
Run: python -m pytest -q -m student -o addopts= -k advanced"""
import copy

import pytest

pytestmark = pytest.mark.student


def _rows(n_items=4, seeds=(1, 2)):
    return [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "cost": 1.0,
             "slices": ["money_movement"] if i < 2 else []} for i in range(n_items) for s in seeds]


def _report(rows=None, metrics=None, seeds=(1, 2), items=4, failures=()):
    rows = _rows() if rows is None else rows
    return {"manifest": {"eval_set_sha": "x", "items": items, "seeds": list(seeds)}, "rows": rows,
            "metrics": {"pass_rate": 1.0} if metrics is None else metrics, "evaluator_failures": list(failures)}


SPEC = {"eval_set_version": "v2",
        "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True,
                     "threshold": {"min": 0.8, "no_significant_drop": True}}],
        "slices": [{"name": "money_movement", "metric": "pass_rate", "min": 0.9,
                    "no_significant_drop": True, "blocking": True}]}


@pytest.fixture(scope="module")
def gate():
    from lab9 import gate

    return gate


def test_clean_report_has_no_problems(gate):
    base = _report()
    assert gate.integrity_check(base, base, SPEC, SPEC) == []


def test_duplicated_rows_keep_the_count_but_are_caught(gate):
    base = _report()
    rows = copy.deepcopy(base["rows"])
    rows[-1] = copy.deepcopy(rows[0])                 # drop a failing row, duplicate a good one: count unchanged
    assert any("duplicated" in p for p in gate.integrity_check(_report(rows), base, SPEC))


def test_evaluator_failures_on_a_green_run(gate):
    base = _report()
    assert any("evaluator failure" in p for p in gate.integrity_check(_report(failures=["E-001@1:Grader:boom"]), base, SPEC))


def test_slice_relabelled_out_of_the_slice(gate):
    base = _report()
    rows = copy.deepcopy(base["rows"])
    for r in rows:
        if r["item_id"] == "E-000":
            r["slices"] = []
    assert any("slice tags" in p for p in gate.integrity_check(_report(rows), base, SPEC))


def test_hand_edited_metric_block(gate):
    base = _report()
    rows = copy.deepcopy(base["rows"])
    rows[0]["pass_rate"] = False
    rows[1]["pass_rate"] = False
    edited = _report(rows, {"pass_rate": 1.0})        # rows say 0.75, the block says 1.0
    assert any("pass_rate reported 1.0" in p for p in gate.integrity_check(edited, base, SPEC))


def test_inf_metric(gate):
    base = _report()
    assert gate.integrity_check(_report(metrics={"pass_rate": float("inf")}), base, SPEC)


def test_ratchet_blocks_each_way_of_loosening(gate):
    base = _report()
    for edit in (lambda s: s["metrics"][0]["threshold"].pop("no_significant_drop"),
                 lambda s: s["metrics"][0].update(blocking=False),
                 lambda s: s["metrics"].clear(),
                 lambda s: s["slices"][0].update(min=0.5),
                 lambda s: s["slices"][0].update(blocking=False),
                 lambda s: s.update(slices=[])):
        loose = copy.deepcopy(SPEC)
        edit(loose)
        assert gate.integrity_check(base, base, loose, SPEC), edit


def test_ratchet_allows_stricter_and_new_eval_version(gate):
    base = _report()
    strict = copy.deepcopy(SPEC)
    strict["metrics"][0]["threshold"]["min"] = 0.95
    assert gate.integrity_check(base, base, strict, SPEC) == []
    loose = copy.deepcopy(SPEC)
    loose["metrics"][0]["threshold"]["min"] = 0.1
    loose["eval_set_version"] = "v3"                   # a new eval set restarts the ratchet
    assert gate.integrity_check(base, base, loose, SPEC) == []


def test_slice_check_blocks_a_small_slice_hidden_by_a_good_average(gate):
    base = _report()
    rows = copy.deepcopy(base["rows"])
    for r in rows:
        if r["item_id"] == "E-001" and r["seed"] == 1:
            r["pass_rate"] = False                     # overall 7/8 = 0.875, slice 3/4 = 0.75
    blocked, lines = gate.slice_check(_report(rows, {"pass_rate": 0.875}), base, SPEC)
    assert blocked == ["slice:money_movement/pass_rate"] and lines


def test_slice_with_no_rows_left_is_blocked(gate):
    base = _report()
    rows = [r for r in base["rows"] if "money_movement" not in r["slices"]]
    blocked, _ = gate.slice_check(_report(rows), base, SPEC)
    assert blocked == ["slice:money_movement/pass_rate"]
