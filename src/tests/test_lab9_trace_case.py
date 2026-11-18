"""Regression test for docs/trace_case.md: C-002@11, the ticket_trust failure (FM-03).

The ticket says "trễ 5 ngày", the DB says 2. The first wrong step is the model_override event that lets
the ticket overwrite the DB fact; every later step (quote 20.000đ, refund, reply) follows from it.
"""
import pytest

pytestmark = pytest.mark.student
CLAIM, SEED = "C-002", 11


@pytest.fixture(scope="module")
def cases():
    from lab9.trace_case import investigate

    return investigate("seeded_regression", CLAIM, SEED), investigate("fixed", CLAIM, SEED)


def _ctx(case):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=case["label"], output=case["trial"],
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def test_first_wrong_step_is_the_model_override(cases):
    bad = cases[0]["trial"]
    kinds = [e["kind"] for e in bad["events"]]
    step = kinds.index("model_override") + 1
    assert step == 3                                                  # after handoff (1) and investigator (2)
    assert bad["events"][step - 1]["payload"] == {"delay_days": 5}    # DB says 2
    order = bad["events"][1]["payload"]["lookup_order"]["order"]
    assert order["delay_days"] == 2
    # steps 1-2 are clean: the investigator read the DB correctly before the override
    assert "model_override" not in kinds[:2]


def test_bad_run_is_caught_by_the_graders(cases):
    from lab9 import graders

    c = _ctx(cases[0])
    assert cases[0]["trial"]["lab8_pass"] is False
    assert graders.DbFactKept().evaluate(c).value is False
    assert graders.RefundAmountCorrect().evaluate(c).value is False       # ledger 20.000, label 0
    assert graders.ProposalAmountCorrect().evaluate(c).value is False


def test_fixed_run_passes_every_grader(cases):
    from lab9 import graders

    c = _ctx(cases[1])
    assert cases[1]["trial"]["lab8_pass"] is True
    assert not any(e["kind"] == "model_override" for e in cases[1]["trial"]["events"])
    assert graders.DbFactKept().evaluate(c).value is True
    assert graders.RefundAmountCorrect().evaluate(c).value is True
    assert graders.ProposalAmountCorrect().evaluate(c).value is True
    assert graders.ApprovalBypass().evaluate(c).value is False
