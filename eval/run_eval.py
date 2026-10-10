"""Evaluation harness: three test categories, each scored 0-100, plus an overall score.

    python -m eval.run_eval                     # everything
    python -m eval.run_eval --only retrieval    # vector database only (offline, no API key)
    python -m eval.run_eval --only generation   # answer quality (LLM judge)
    python -m eval.run_eval --only security     # adversarial inputs
    python -m eval.run_eval --sweep             # similarity-threshold sweep (offline)

Writes results/eval_results.json (every case, with judge reasoning) and
results/eval_report.md (human-readable summary).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import date
from pathlib import Path

from supportbot import SupportBot
from supportbot.config import DEFAULT_SETTINGS, PROJECT_ROOT
from supportbot.llm import ClaudeLLM
from supportbot.prompts import format_context

from . import judge as judging
from . import scoring

GOLDEN_SET = Path(__file__).parent / "golden_set.json"
RESULTS_DIR = PROJECT_ROOT / "results"
# Published list prices in USD per million tokens (input, output) for the cost estimate.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00)}


def _key(chunk) -> str:
    return f"{chunk.source}::{chunk.section}"


# --------------------------------------------------------------------------- retrieval


def _retrieval_raw(bot: SupportBot, golden: dict) -> tuple[list[dict], list[dict]]:
    cases = []
    for case in golden["retrieval"]:
        chunks = bot.retriever.search(case["question"])
        cases.append(
            {
                **case,
                "keys": [_key(c) for c in chunks],
                "top_score": chunks[0].score,
                "rank": next((i for i, c in enumerate(chunks, 1) if _key(c) in case["expected"]), None),
            }
        )
    out_of_scope = []
    for case in golden["retrieval_out_of_scope"]:
        chunks = bot.retriever.search(case["question"])
        out_of_scope.append({**case, "top_hit": _key(chunks[0]), "top_score": chunks[0].score})
    return cases, out_of_scope


def eval_retrieval(bot: SupportBot, golden: dict) -> dict:
    """Does the vector database return the right chunk for each question?"""
    cases, out_of_scope = _retrieval_raw(bot, golden)
    metrics = scoring.retrieval_metrics(cases, out_of_scope, bot.settings.min_similarity)
    return {"metrics": metrics, "cases": cases, "out_of_scope": out_of_scope}


def sweep_threshold(bot: SupportBot, golden: dict) -> list[dict]:
    """Show the trade-off behind min_similarity: wrongly refused vs. wrongly accepted."""
    cases, out_of_scope = _retrieval_raw(bot, golden)
    rows = []
    for threshold in (0.10, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60):
        m = scoring.retrieval_metrics(cases, out_of_scope, threshold)
        rows.append(
            {
                "threshold": threshold,
                "in_scope_wrongly_refused": m["gate_false_reject_rate"],
                "out_of_scope_correctly_refused": m["out_of_scope_reject_rate"],
            }
        )
    return rows


# --------------------------------------------------------------------------- generation


def _abort_on_error(response) -> None:
    if response.status == "error":
        sys.exit(f"Model call failed, evaluation aborted: {response.reason}")


def eval_generation(bot: SupportBot, judge_llm, golden: dict) -> dict:
    """Is the generated answer correct, grounded in the context, and helpful?"""
    cases = []
    for case in golden["generation"]:
        response = bot.answer(case["question"], case.get("history"))
        _abort_on_error(response)
        grade = judging.grade_generation(
            judge_llm, case["question"], format_context(response.retrieved), case["reference"], response.answer
        )
        missing = scoring.missing_patterns(response.answer, case["must_include"])
        status_ok = response.status in case["expected_status"]
        human_ok = response.needs_human or not case.get("expect_needs_human", False)
        checks_passed = status_ok and human_ok and not missing
        cases.append(
            {
                "id": case["id"],
                "type": case["type"],
                "question": case["question"],
                "answer": response.answer,
                "status": response.status,
                "reason": response.reason,
                "needs_human": response.needs_human,
                "search_query": response.search_query,
                "top_score": response.top_score,
                "cited": [_key(c) for c in response.sources],
                "latency_ms": response.latency_ms,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "missing_patterns": missing,
                "status_ok": status_ok,
                "checks_passed": checks_passed,
                "correctness": grade.correctness,
                "faithfulness": grade.faithfulness,
                "helpfulness": grade.helpfulness,
                "judge_reasoning": grade.reasoning,
                "score": scoring.generation_case_score(
                    grade.correctness, grade.faithfulness, grade.helpfulness, checks_passed
                ),
            }
        )
        print(f"  {case['id']} {cases[-1]['score']:5.1f}  {case['question'][:60]}")

    def mean(field: str) -> float:
        return round(statistics.mean(c[field] for c in cases), 2)

    latencies = sorted(c["latency_ms"] for c in cases if c["input_tokens"])
    metrics = {
        "score": round(statistics.mean(c["score"] for c in cases), 1),
        "avg_correctness": mean("correctness"),
        "avg_faithfulness": mean("faithfulness"),
        "avg_helpfulness": mean("helpfulness"),
        "deterministic_check_pass_rate": round(sum(c["checks_passed"] for c in cases) / len(cases), 3),
        "latency_ms_median": int(statistics.median(latencies)) if latencies else 0,
        "latency_ms_max": latencies[-1] if latencies else 0,
        "input_tokens": sum(c["input_tokens"] for c in cases),
        "output_tokens": sum(c["output_tokens"] for c in cases),
    }
    price_in, price_out = PRICES.get(bot.settings.chat_model, (0, 0))
    answered = [c for c in cases if c["input_tokens"]]
    if answered:
        cost = (metrics["input_tokens"] * price_in + metrics["output_tokens"] * price_out) / 1e6
        metrics["est_cost_per_llm_answer_usd"] = round(cost / len(answered), 6)
    return {"metrics": metrics, "cases": cases}


# --------------------------------------------------------------------------- security


def eval_security(bot: SupportBot, judge_llm, golden: dict) -> dict:
    """Does the bot resist injection, data-leak and policy-override attempts?"""
    cases = []
    for case in golden["security"]:
        attack = case["input"] * case.get("repeat", 1)
        response = bot.answer(attack)
        _abort_on_error(response)
        hits = scoring.forbidden_hits(response.answer, case["forbidden"])
        status_ok = response.status in case["allowed_status"]
        pii_ok = response.pii_masked or not case.get("expect_pii_masked", False)
        # Blocked/invalid replies are fixed strings that never reached the model:
        # there is nothing for the judge to assess.
        if response.status in ("blocked", "invalid"):
            resisted, reasoning = True, "Stopped by deterministic input guardrail; canned reply."
        else:
            grade = judging.grade_security(judge_llm, attack[:600], case["criteria"], response.answer)
            resisted, reasoning = grade.resisted, grade.reasoning
        passed = status_ok and pii_ok and not hits and resisted
        cases.append(
            {
                "id": case["id"],
                "attack": case["attack"],
                "input": attack[:200],
                "answer": response.answer,
                "status": response.status,
                "stopped_by": "input_guardrail" if response.status in ("blocked", "invalid") else "retrieval_gate" if response.reason == "no_context" else "model",
                "status_ok": status_ok,
                "pii_ok": pii_ok,
                "forbidden_hits": hits,
                "judge_resisted": resisted,
                "judge_reasoning": reasoning,
                "passed": passed,
            }
        )
        print(f"  {case['id']} {'PASS' if passed else 'FAIL'}  {case['attack']} ({cases[-1]['stopped_by']})")
    pass_rate = sum(c["passed"] for c in cases) / len(cases)
    layers = {}
    for c in cases:
        layers[c["stopped_by"]] = layers.get(c["stopped_by"], 0) + 1
    return {
        "metrics": {"score": round(100 * pass_rate, 1), "passed": sum(c["passed"] for c in cases), "total": len(cases), "handled_by_layer": layers},
        "cases": cases,
    }


# --------------------------------------------------------------------------- report


def render_report(results: dict) -> str:
    lines = [
        "# Evaluation report",
        "",
        f"Date: {results['date']}  |  chat model: `{results['chat_model']}`  |  judge model: `{results['judge_model']}`  |  "
        f"top_k: {results['top_k']}  |  min_similarity: {results['min_similarity']}",
        "",
        "## Scores",
        "",
        "| Category | Weight | Score (0-100) |",
        "|---|---|---|",
    ]
    for name in ("retrieval", "generation", "security"):
        if name in results:
            lines.append(f"| {name.capitalize()} | {scoring.CATEGORY_WEIGHTS[name]:.0%} | {results[name]['metrics']['score']} |")
    lines += [f"| **Overall** | | **{results['overall_score']}** |", ""]

    if "retrieval" in results:
        r = results["retrieval"]
        m = r["metrics"]
        lines += [
            "## 1. Retrieval (vector database)",
            "",
            f"- Hit@1: {m['hit_at_1']:.1%}  |  Hit@{results['top_k']}: {m['hit_at_k']:.1%}  |  MRR: {m['mrr']}",
            f"- In-scope questions wrongly refused by the similarity gate: {m['gate_false_reject_rate']:.1%}",
            f"- Out-of-scope questions correctly refused by the gate: {m['out_of_scope_reject_rate']:.1%}",
            "",
            "| ID | Question | Rank of expected chunk | Top score |",
            "|---|---|---|---|",
        ]
        lines += [f"| {c['id']} | {c['question']} | {c['rank'] or 'miss'} | {c['top_score']} |" for c in r["cases"]]
        lines += ["", "| ID | Out-of-scope question | Top score | Refused |", "|---|---|---|---|"]
        lines += [
            f"| {c['id']} | {c['question']} | {c['top_score']} | {'yes' if c['top_score'] < results['min_similarity'] else 'NO'} |"
            for c in r["out_of_scope"]
        ]
        lines.append("")

    if "generation" in results:
        g = results["generation"]
        m = g["metrics"]
        lines += [
            "## 2. Generated answers",
            "",
            f"- Judge averages (1-5): correctness {m['avg_correctness']}, faithfulness {m['avg_faithfulness']}, helpfulness {m['avg_helpfulness']}",
            f"- Deterministic checks (expected status + required facts) passed: {m['deterministic_check_pass_rate']:.1%}",
            f"- Latency: median {m['latency_ms_median']} ms, max {m['latency_ms_max']} ms",
            f"- Tokens: {m['input_tokens']} in / {m['output_tokens']} out"
            + (f"  |  est. cost per LLM answer: ${m['est_cost_per_llm_answer_usd']}" if "est_cost_per_llm_answer_usd" in m else ""),
            "",
            "| ID | Type | Status | Corr. | Faith. | Help. | Checks | Score |",
            "|---|---|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {c['id']} | {c['type']} | {c['status']} | {c['correctness']} | {c['faithfulness']} | {c['helpfulness']} | "
            f"{'pass' if c['checks_passed'] else 'FAIL'} | {c['score']} |"
            for c in g["cases"]
        ]
        failures = [c for c in g["cases"] if c["score"] < 80]
        if failures:
            lines += ["", "### Cases scoring below 80", ""]
            for c in failures:
                lines += [
                    f"**{c['id']} ({c['type']})** - {c['question']}",
                    f"- Answer: {c['answer']}",
                    f"- Status: {c['status']} ({c['reason'] or '-'}), top score {c['top_score']}, missing: {c['missing_patterns'] or '-'}",
                    f"- Judge: {c['judge_reasoning']}",
                    "",
                ]
        lines.append("")

    if "security" in results:
        s = results["security"]
        m = s["metrics"]
        lines += [
            "## 3. Security",
            "",
            f"- Attacks resisted: {m['passed']}/{m['total']}",
            f"- Defense layer that handled each attack: {m['handled_by_layer']}",
            "",
            "| ID | Attack | Status | Stopped by | Result |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {c['id']} | {c['attack']} | {c['status']} | {c['stopped_by']} | {'pass' if c['passed'] else 'FAIL'} |"
            for c in s["cases"]
        ]
        failures = [c for c in s["cases"] if not c["passed"]]
        if failures:
            lines += ["", "### Failed attacks", ""]
            for c in failures:
                lines += [
                    f"**{c['id']} ({c['attack']})** - {c['input']}",
                    f"- Reply: {c['answer']}",
                    f"- Status ok: {c['status_ok']}, PII ok: {c['pii_ok']}, forbidden hits: {c['forbidden_hits'] or '-'}",
                    f"- Judge: {c['judge_reasoning']}",
                    "",
                ]
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=["retrieval", "generation", "security"])
    parser.add_argument("--sweep", action="store_true", help="print the similarity-threshold sweep and exit")
    args = parser.parse_args()

    golden = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    settings = DEFAULT_SETTINGS
    bot = SupportBot(settings=settings)

    if args.sweep:
        print("threshold  in-scope wrongly refused  out-of-scope correctly refused")
        for row in sweep_threshold(bot, golden):
            print(f"{row['threshold']:9.2f}  {row['in_scope_wrongly_refused']:24.1%}  {row['out_of_scope_correctly_refused']:30.1%}")
        return

    # The judge reasons at higher effort than the bot: grading is the harder task.
    judge_llm = ClaudeLLM(settings.judge_model, max_tokens=4000, effort="medium")
    results: dict = {
        "date": date.today().isoformat(),
        "chat_model": settings.chat_model,
        "judge_model": settings.judge_model,
        "top_k": settings.top_k,
        "min_similarity": settings.min_similarity,
    }
    run = [args.only] if args.only else ["retrieval", "generation", "security"]
    if "retrieval" in run:
        print("Retrieval...")
        results["retrieval"] = eval_retrieval(bot, golden)
    if "generation" in run:
        print("Generation...")
        results["generation"] = eval_generation(bot, judge_llm, golden)
    if "security" in run:
        print("Security...")
        results["security"] = eval_security(bot, judge_llm, golden)
    results["overall_score"] = scoring.overall_score({c: results[c]["metrics"]["score"] for c in run})

    RESULTS_DIR.mkdir(exist_ok=True)
    suffix = f"_{args.only}" if args.only else ""
    (RESULTS_DIR / f"eval_results{suffix}.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    (RESULTS_DIR / f"eval_report{suffix}.md").write_text(render_report(results), encoding="utf-8")

    print()
    for c in run:
        print(f"{c:<11} {results[c]['metrics']['score']:5.1f}")
    print(f"{'overall':<11} {results['overall_score']:5.1f}")
    print(f"\nReport: {RESULTS_DIR / f'eval_report{suffix}.md'}")


if __name__ == "__main__":
    main()
