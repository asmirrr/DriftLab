"""Optional, strictly bounded TypeSafe Jev methodology audit."""

import json
import math
import os
from typing import Any, Mapping

GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/typesafe"
MODEL = "typesafe-ai/jev"
CONFIDENCE_THRESHOLD = 0.65
MAX_RECORD_BYTES = 50_000
POLICY_NOTE = "Jev output is a structured research-workflow aid, not financial advice, a trading instruction, or evidence of future performance."
_REQUIRED_RECORD_KEYS = {"run_id", "research_question", "requested_tickers", "valid_tickers", "excluded_tickers", "data_source", "requested_start", "requested_end", "data_start", "data_end", "allocation_date", "performance_start", "strategy", "research_process", "strategy_metrics", "benchmark_metrics", "turnover"}
_CHOICES = {"design_status": {"insufficient", "exploratory_ready", "validation_ready"}, "result_label": {"inconclusive", "exploratory_signal", "requires_validation"}, "next_experiment": {"out_of_sample_split", "parameter_sensitivity", "cost_sensitivity", "universe_expansion"}}


class JevAuditError(RuntimeError):
    """An optional audit could not be completed safely."""


def _finite_json(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _finite_json(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_finite_json(item) for item in value)
    return value is None or isinstance(value, (str, int, bool))


def validate_research_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Accept only compact factual records produced by DriftLab."""
    if not isinstance(record, Mapping) or not _REQUIRED_RECORD_KEYS.issubset(record):
        raise JevAuditError("Jev audit requires a complete DriftLab research record.")
    unexpected = set(record) - _REQUIRED_RECORD_KEYS - {"actual_start", "actual_end"}
    if unexpected:
        raise JevAuditError("Jev audit record contains unsupported fields.")
    if not _finite_json(record):
        raise JevAuditError("Jev audit record contains non-finite values.")
    try:
        encoded = json.dumps(record, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise JevAuditError("Jev audit record must contain JSON-native values.") from error
    if len(encoded) > MAX_RECORD_BYTES:
        raise JevAuditError("Jev audit record exceeds the compact-state size limit.")
    return dict(record)


def build_questions() -> dict[str, Any]:
    from typesafe_sdk import Choice, Noul, Score
    return {
        "design_status": Choice(instructions="Classify whether this backtest design is sufficiently specified to support the stated level of historical interpretation.", criteria={"insufficient": "Important setup facts are missing or the design cannot support a meaningful exploratory comparison.", "exploratory_ready": "Rule, universe, date range, benchmark, rebalancing, and cost assumptions are stated, but validation remains incomplete.", "validation_ready": "Research is fully specified and includes meaningful validation or out-of-sample testing."}),
        "result_label": Choice(instructions="Based only on the supplied historical record, which cautious research label is most appropriate? Do not infer or claim future performance.", criteria={"inconclusive": "The record does not support a meaningful historical edge claim or unresolved limitations dominate.", "exploratory_signal": "The outcome may justify further research but does not support a persistent investment-edge claim.", "requires_validation": "Historical results are notable enough to test further, but validation is necessary before further interpretation."}),
        "overfitting_risk": Score(instructions="Assess apparent overfitting risk from the supplied research-process metadata only.", criteria=["low: parameters were pre-specified and a meaningful independent validation process was used.", "medium: a small or limited parameter search occurred, but validation is incomplete.", "high: multiple strategy variants, parameters, or selection choices were tested without a defined validation process."]),
        "survivorship_bias_material": Noul(instructions="Is survivorship bias a material limitation if the stock universe uses current tickers rather than historical index constituents?"),
        "next_experiment": Choice(instructions="Choose the single next experiment that would most improve the credibility of the research record.", criteria={"out_of_sample_split": "Choose parameters using a development period, then evaluate once on a held-out period.", "parameter_sensitivity": "Test nearby predefined values for momentum lookback and holding count.", "cost_sensitivity": "Repeat under multiple realistic transaction-cost assumptions.", "universe_expansion": "Test a broader pre-specified universe to reduce dependence on a handpicked basket."}),
    }


def _probabilities(values: Mapping[Any, Any], expected: set[str]) -> dict[str, float]:
    normalized = {str(key): value for key, value in values.items()}
    valid = set(normalized) == expected and all(isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1 for value in normalized.values())
    if not valid or not math.isclose(sum(normalized.values()), 1.0, abs_tol=1e-6):
        raise JevAuditError("Jev returned invalid answer probabilities.")
    return {key: float(value) for key, value in normalized.items()}


def _choice(answer: Any, allowed: set[str]) -> dict[str, Any]:
    value, confidence = answer.choice, answer.confidence
    if value not in allowed or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise JevAuditError("Jev returned an invalid Choice answer.")
    return {"raw_choice": value, "display_value": value if confidence >= CONFIDENCE_THRESHOLD else "Ambiguous — no automated conclusion assigned.", "confidence": float(confidence), "probabilities": _probabilities(answer.probabilities, allowed)}


def normalize_response(response: Any, run_id: str) -> dict[str, Any]:
    try:
        design = _choice(response.choices["design_status"], _CHOICES["design_status"])
        result = _choice(response.choices["result_label"], _CHOICES["result_label"])
        next_experiment = _choice(response.choices["next_experiment"], _CHOICES["next_experiment"])
        score = response.scores["overfitting_risk"]
        noul = response.nouls["survivorship_bias_material"].noul
    except (AttributeError, KeyError) as error:
        raise JevAuditError("Jev response did not contain all required typed answers.") from error
    values = (score.score, score.confidence, noul)
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values) or not 0 <= score.score <= 2 or not 0 <= score.confidence <= 1 or not 0 <= noul <= 1:
        raise JevAuditError("Jev returned an out-of-range Score, confidence, or Noul probability.")
    probabilities = _probabilities(score.probabilities, {"0", "1", "2"})
    legend = {str(key): value for key, value in score.legend.items()}
    if set(legend) != {"0", "1", "2"}:
        raise JevAuditError("Jev returned an invalid Score legend.")
    label = ("low", "medium", "high")[round(score.score)]
    return {"run_id": run_id, "provider": "TypeSafe Jev via Vercel AI Gateway", "audit_status": "completed", "confidence_threshold": CONFIDENCE_THRESHOLD, "answers": {"design_status": design, "result_label": result, "overfitting_risk": {"score": float(score.score), "derived_label": label, "confidence": float(score.confidence), "probabilities": probabilities, "legend": legend}, "survivorship_bias_material": {"probability": float(noul)}, "next_experiment": next_experiment}, "policy_note": POLICY_NOTE}


def audit_research_record(record: Mapping[str, Any]) -> dict[str, Any]:
    state = validate_research_record(record)
    key = os.getenv("AI_GATEWAY_API_KEY")
    if not key:
        raise JevAuditError("Jev audit requested, but AI_GATEWAY_API_KEY is not set. Set it in your environment or a local .env file, then rerun with --audit-with-jev.")
    try:
        from typesafe_sdk import RetryPolicy, TypeSafeClient
        with TypeSafeClient(api_key=key, base_url=GATEWAY_BASE_URL, model=MODEL, timeout=30.0, retry=RetryPolicy(max_retries=0)) as client:
            response = client.system_one(state, build_questions())
        return normalize_response(response, str(state["run_id"]))
    except JevAuditError:
        raise
    except Exception as error:
        raise JevAuditError(f"Jev audit was unavailable: {error}") from error
