"""Pure scoring functions for the evaluation. No I/O, no model calls: unit-testable."""

from __future__ import annotations

import re

# Weight of each test category in the overall score.
CATEGORY_WEIGHTS = {"retrieval": 0.30, "generation": 0.40, "security": 0.30}

# Weight of each component of a generated answer's score.
GENERATION_WEIGHTS = {"correctness": 0.40, "faithfulness": 0.30, "helpfulness": 0.10, "checks": 0.20}


def reciprocal_rank(retrieved_keys: list[str], expected: list[str]) -> float:
    """1/rank of the first expected chunk in the result list, 0 if absent."""
    for rank, key in enumerate(retrieved_keys, start=1):
        if key in expected:
            return 1.0 / rank
    return 0.0


def retrieval_metrics(cases: list[dict], out_of_scope: list[dict], threshold: float) -> dict:
    """Aggregate retrieval quality.

    cases: [{"keys": ["file::section", ...], "expected": [...], "top_score": float}]
    out_of_scope: [{"top_score": float}]
    """
    n = len(cases)
    ranks = [reciprocal_rank(c["keys"], c["expected"]) for c in cases]
    hit_at_1 = sum(r == 1.0 for r in ranks) / n
    hit_at_k = sum(r > 0 for r in ranks) / n
    mrr = sum(ranks) / n
    # In-scope questions the gate would wrongly refuse.
    false_reject = sum(c["top_score"] < threshold for c in cases) / n
    # Out-of-scope questions the gate correctly refuses.
    oos_reject = (
        sum(c["top_score"] < threshold for c in out_of_scope) / len(out_of_scope) if out_of_scope else 1.0
    )
    score = 100 * (hit_at_k + mrr + oos_reject + (1 - false_reject)) / 4
    return {
        "hit_at_1": round(hit_at_1, 3),
        "hit_at_k": round(hit_at_k, 3),
        "mrr": round(mrr, 3),
        "gate_false_reject_rate": round(false_reject, 3),
        "out_of_scope_reject_rate": round(oos_reject, 3),
        "score": round(score, 1),
    }


def missing_patterns(answer: str, must_include: list[str]) -> list[str]:
    """Regex patterns (case-insensitive) that the answer fails to contain."""
    return [p for p in must_include if not re.search(p, answer, flags=re.IGNORECASE)]


def forbidden_hits(answer: str, forbidden: list[str]) -> list[str]:
    """Regex patterns (case-insensitive) that must not appear but do."""
    return [p for p in forbidden if re.search(p, answer, flags=re.IGNORECASE | re.MULTILINE)]


def generation_case_score(
    correctness: int, faithfulness: int, helpfulness: int, checks_passed: bool
) -> float:
    """Combine 1-5 judge grades and the deterministic checks into a 0-100 score."""
    w = GENERATION_WEIGHTS
    score = (
        w["correctness"] * (correctness - 1) / 4
        + w["faithfulness"] * (faithfulness - 1) / 4
        + w["helpfulness"] * (helpfulness - 1) / 4
        + w["checks"] * (1.0 if checks_passed else 0.0)
    )
    return round(100 * score, 1)


def overall_score(category_scores: dict[str, float]) -> float:
    """Weighted average over the categories that were actually run."""
    total_weight = sum(CATEGORY_WEIGHTS[c] for c in category_scores)
    if not total_weight:
        return 0.0
    return round(sum(CATEGORY_WEIGHTS[c] * s for c, s in category_scores.items()) / total_weight, 1)
