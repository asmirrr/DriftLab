"""Optional TypeSafe Jev methodology audit; never part of financial calculations."""

from dataclasses import dataclass
import os
from typing import Any

GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/typesafe"
MODEL = "typesafe-ai/jev"
CONFIDENCE_THRESHOLD = 0.65
POLICY_NOTE = "Jev output is a structured research-workflow aid, not financial advice, a trading instruction, or evidence of future performance."


class JevAuditError(RuntimeError):
    """An optional audit could not be completed."""


def build_questions() -> dict[str, Any]:
    from typesafe_sdk import Choice, Noul, Score
    return {
        "design_status": Choice(instructions="Classify whether this backtest design is sufficiently specified to support the stated level of historical interpretation.", criteria={
            "insufficient": "Important setup facts are missing or the design cannot support a meaningful exploratory comparison.",
            "exploratory_ready": "Rule, universe, date range, benchmark, rebalancing, and cost assumptions are stated, but validation remains incomplete.",
            "validation_ready": "Research is fully specified and includes meaningful validation or out-of-sample testing."}),
        "result_label": Choice(instructions="Based only on the supplied historical record, which cautious research label is most appropriate? Do not infer or claim future performance.", criteria={
            "inconclusive": "The record does not support a meaningful historical edge claim or unresolved limitations dominate.",
            "exploratory_signal": "The outcome may justify further research but does not support a persistent investment-edge claim.",
            "requires_validation": "Historical results are notable enough to test further, but validation is necessary before further interpretation."}),
        "overfitting_risk": Score(instructions="Assess apparent overfitting risk from the supplied research-process metadata only.", criteria=[
            "low: parameters were pre-specified and a meaningful independent validation process was used.",
            "medium: a small or limited parameter search occurred, but validation is incomplete.",
            "high: multiple strategy variants, parameters, or selection choices were tested without a defined validation process."]),
        "survivorship_bias_material": Noul(instructions="Is survivorship bias a material limitation if the stock universe uses current tickers rather than historical index constituents?"),
        "next_experiment": Choice(instructions="Choose the single next experiment that would most improve the credibility of the research record.", criteria={
            "out_of_sample_split": "Choose parameters using a development period, then evaluate once on a held-out period.",
            "parameter_sensitivity": "Test nearby predefined values for momentum lookback and holding count.",
            "cost_sensitivity": "Repeat under multiple realistic transaction-cost assumptions.",
            "universe_expansion": "Test a broader pre-specified universe to reduce dependence on a handpicked basket."}),
    }


def _choice(answer: Any) -> dict[str, Any]:
    value, confidence = answer.choice, answer.confidence
    return {"raw_choice": value, "display_value": value if confidence >= CONFIDENCE_THRESHOLD else "Ambiguous — no automated conclusion assigned.",
            "confidence": confidence, "probabilities": dict(answer.probabilities)}


def normalize_response(response: Any, run_id: str) -> dict[str, Any]:
    design = _choice(response.choices["design_status"])
    result = _choice(response.choices["result_label"])
    next_experiment = _choice(response.choices["next_experiment"])
    score = response.scores["overfitting_risk"]
    # Jev Score is numerical (0=low, 1=medium, 2=high), possibly fractional.
    score_label = ["low", "medium", "high"][min(2, max(0, round(score.score)))]
    return {"run_id": run_id, "provider": "TypeSafe Jev via Vercel AI Gateway", "audit_status": "completed",
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "answers": {"design_status": design, "result_label": result,
                        "overfitting_risk": {"score": score.score, "derived_label": score_label,
                                             "confidence": score.confidence, "probabilities": dict(score.probabilities),
                                             "legend": dict(score.legend)},
                        "survivorship_bias_material": {"probability": response.nouls["survivorship_bias_material"].noul},
                        "next_experiment": next_experiment}, "policy_note": POLICY_NOTE}


def audit_research_record(record: dict[str, Any]) -> dict[str, Any]:
    key = os.getenv("AI_GATEWAY_API_KEY")
    if not key:
        raise JevAuditError("Jev audit requested, but AI_GATEWAY_API_KEY is not set. Set it in your environment or a local .env file, then rerun with --audit-with-jev.")
    try:
        from typesafe_sdk import RetryPolicy, TypeSafeClient
        with TypeSafeClient(api_key=key, base_url=GATEWAY_BASE_URL, model=MODEL,
                            timeout=30.0, retry=RetryPolicy(max_retries=0)) as client:
            response = client.system_one(record, build_questions())
        return normalize_response(response, str(record["run_id"]))
    except Exception as error:
        raise JevAuditError(f"Jev audit was unavailable: {error}") from error
