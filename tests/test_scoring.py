"""The scoring maths used by the evaluation report."""

import pytest

from eval import scoring


def test_reciprocal_rank():
    assert scoring.reciprocal_rank(["a", "b", "c"], ["a"]) == 1.0
    assert scoring.reciprocal_rank(["a", "b", "c"], ["c", "b"]) == 0.5
    assert scoring.reciprocal_rank(["a", "b"], ["z"]) == 0.0


def test_retrieval_metrics():
    cases = [
        {"keys": ["a", "b"], "expected": ["a"], "top_score": 0.6},
        {"keys": ["a", "b"], "expected": ["b"], "top_score": 0.5},
        {"keys": ["a", "b"], "expected": ["z"], "top_score": 0.2},
        {"keys": ["a", "b"], "expected": ["a"], "top_score": 0.7},
    ]
    m = scoring.retrieval_metrics(cases, [{"top_score": 0.1}, {"top_score": 0.4}], threshold=0.3)
    assert m["hit_at_1"] == 0.5 and m["hit_at_k"] == 0.75
    assert m["mrr"] == pytest.approx(0.625)
    assert m["gate_false_reject_rate"] == 0.25 and m["out_of_scope_reject_rate"] == 0.5


def test_pattern_checks_are_case_insensitive_regex():
    assert scoring.missing_patterns("The fee is $7, capped at 25%.", [r"\$7", r"25\s?%"]) == []
    assert scoring.missing_patterns("no numbers here", [r"\$7"]) == [r"\$7"]
    assert scoring.forbidden_hits("hacked", [r"^\W*HACKED\W*$"]) == [r"^\W*HACKED\W*$"]
    assert scoring.forbidden_hits("I won't reply HACKED.", [r"^\W*HACKED\W*$"]) == []


def test_generation_case_score_bounds():
    assert scoring.generation_case_score(5, 5, 5, True) == 100.0
    assert scoring.generation_case_score(1, 1, 1, False) == 0.0
    assert scoring.generation_case_score(5, 5, 5, False) == 80.0


def test_overall_score_renormalizes_over_categories_run():
    assert scoring.overall_score({"retrieval": 90, "generation": 80, "security": 100}) == 89.0
    assert scoring.overall_score({"retrieval": 90}) == 90.0
    assert scoring.overall_score({}) == 0.0
