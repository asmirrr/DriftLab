"""Optional, strictly bounded TypeSafe Jev methodology audit."""

import json
import math
import os
from datetime import date
from typing import Any, Mapping

GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/typesafe"
MODEL = "typesafe-ai/jev"
CONFIDENCE_THRESHOLD = 0.65
MAX_RECORD_BYTES = 50_000
POLICY_NOTE = "Jev output is a structured research-workflow aid, not financial advice, a trading instruction, or evidence of future performance."
_REQUIRED_RECORD_KEYS = {"run_id", "research_question", "requested_tickers", "valid_tickers", "excluded_tickers", "data_source", "requested_start", "requested_end", "data_start", "data_end", "allocation_date", "performance_start", "actual_start", "actual_end", "strategy", "research_process", "strategy_metrics", "benchmark_metrics", "turnover", "metadata"}
_METRIC_KEYS = {"cumulative_return", "annualized_return", "annualized_volatility", "sharpe_ratio", "maximum_drawdown", "average_daily_turnover", "total_turnover", "rebalance_events", "investable_trading_days", "valid_tickers"}
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


def _number(value: Any, allow_null: bool = False) -> bool:
    return (allow_null and value is None) or (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value))


def _iso_date(value: Any) -> date:
    if not isinstance(value, str):
        raise JevAuditError("Jev audit dates must be ISO YYYY-MM-DD strings.")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise JevAuditError("Jev audit dates must be ISO YYYY-MM-DD strings.") from error


def _exact_object(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise JevAuditError(f"Jev audit {label} has an invalid schema.")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise JevAuditError(f"Jev audit {label} must be a list of nonempty strings.")
    return value


def _validate_metrics(value: Any, label: str) -> None:
    metrics = _exact_object(value, _METRIC_KEYS, label)
    nullable = {"annualized_return", "annualized_volatility", "sharpe_ratio"}
    for key in _METRIC_KEYS - {"rebalance_events", "investable_trading_days", "valid_tickers"}:
        if not _number(metrics[key], key in nullable):
            raise JevAuditError(f"Jev audit {label}.{key} must be finite numeric data or null where allowed.")
    for key in {"rebalance_events", "investable_trading_days", "valid_tickers"}:
        if not isinstance(metrics[key], int) or isinstance(metrics[key], bool) or metrics[key] < 0:
            raise JevAuditError(f"Jev audit {label}.{key} must be a nonnegative integer.")


def validate_research_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Accept only the compact, factual DriftLab record schema."""
    if not isinstance(record, Mapping) or set(record) != _REQUIRED_RECORD_KEYS:
        raise JevAuditError("Jev audit requires a complete DriftLab research record with no unsupported fields.")
    if not _finite_json(record):
        raise JevAuditError("Jev audit record contains non-finite values.")
    for key in {"run_id", "research_question", "data_source"}:
        if not isinstance(record[key], str) or not record[key]:
            raise JevAuditError(f"Jev audit {key} must be a nonempty string.")
    if record["data_source"] != "yfinance":
        raise JevAuditError("Jev audit record data_source must be yfinance.")
    requested = _string_list(record["requested_tickers"], "requested_tickers")
    valid = _string_list(record["valid_tickers"], "valid_tickers")
    excluded = _string_list(record["excluded_tickers"], "excluded_tickers") if record["excluded_tickers"] else []
    if len(set(requested)) != len(requested) or set(valid) | set(excluded) != set(requested) or set(valid) & set(excluded):
        raise JevAuditError("Jev audit ticker lists must be a disjoint partition of requested tickers.")
    requested_start, requested_end, data_start, data_end, allocation, performance, actual_start, actual_end = (
        _iso_date(record[key]) for key in ("requested_start", "requested_end", "data_start", "data_end", "allocation_date", "performance_start", "actual_start", "actual_end"))
    if not requested_start < requested_end or not data_start <= allocation < performance <= data_end or actual_start != performance or actual_end != data_end:
        raise JevAuditError("Jev audit record date boundaries are inconsistent.")
    strategy = _exact_object(record["strategy"], {"name", "lookback_trading_days", "holdings", "rebalance_frequency", "cost_bps", "long_only", "weighting"}, "strategy")
    if strategy["name"] != "Top-N Trailing Momentum" or strategy["rebalance_frequency"] != "monthly" or strategy["weighting"] != "equal_weighted_target_weights" or strategy["long_only"] is not True or not isinstance(strategy["lookback_trading_days"], int) or strategy["lookback_trading_days"] < 1 or not isinstance(strategy["holdings"], int) or not 1 <= strategy["holdings"] <= len(requested) or not _number(strategy["cost_bps"]) or strategy["cost_bps"] < 0:
        raise JevAuditError("Jev audit strategy configuration is invalid.")
    process = _exact_object(record["research_process"], {"parameter_sets_tested", "out_of_sample_test", "historical_constituents_used", "data_notes"}, "research_process")
    if not isinstance(process["parameter_sets_tested"], int) or process["parameter_sets_tested"] < 1 or not isinstance(process["out_of_sample_test"], bool) or not isinstance(process["historical_constituents_used"], bool):
        raise JevAuditError("Jev audit research_process is invalid.")
    _string_list(process["data_notes"], "research_process.data_notes")
    _validate_metrics(record["strategy_metrics"], "strategy_metrics")
    _validate_metrics(record["benchmark_metrics"], "benchmark_metrics")
    turnover = _exact_object(record["turnover"], {"average_daily_turnover", "total_turnover", "rebalance_events"}, "turnover")
    if not _number(turnover["average_daily_turnover"], True) or not _number(turnover["total_turnover"]) or not isinstance(turnover["rebalance_events"], int) or turnover["rebalance_events"] < 0:
        raise JevAuditError("Jev audit turnover is invalid.")
    metadata = _exact_object(record["metadata"], {"python_version", "package_versions", "code_version", "parameter_sets_tested_scope"}, "metadata")
    if not all(isinstance(metadata[key], str) and metadata[key] for key in {"python_version", "code_version", "parameter_sets_tested_scope"}) or metadata["parameter_sets_tested_scope"] != "configurations evaluated in this invocation only" or not isinstance(metadata["package_versions"], Mapping) or set(metadata["package_versions"]) != {"numpy", "pandas", "typesafe-sdk", "yfinance"} or not all(isinstance(key, str) and isinstance(value, str) and value for key, value in metadata["package_versions"].items()):
        raise JevAuditError("Jev audit metadata is invalid.")
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
    if not isinstance(values, Mapping):
        raise JevAuditError("Jev returned invalid answer probabilities.")
    normalized = {str(key): value for key, value in values.items()}
    valid = set(normalized) == expected and all(_number(value) and 0 <= value <= 1 for value in normalized.values())
    if not valid or not math.isclose(sum(normalized.values()), 1.0, abs_tol=1e-6):
        raise JevAuditError("Jev returned invalid answer probabilities.")
    return {key: float(value) for key, value in normalized.items()}


def _choice(answer: Any, allowed: set[str]) -> dict[str, Any]:
    value, confidence = answer.choice, answer.confidence
    if value not in allowed or not _number(confidence) or not 0 <= confidence <= 1:
        raise JevAuditError("Jev returned an invalid Choice answer.")
    probabilities = _probabilities(answer.probabilities, allowed)
    if value not in {key for key, probability in probabilities.items() if math.isclose(probability, max(probabilities.values()), abs_tol=1e-9)}:
        raise JevAuditError("Jev Choice does not agree with its probability distribution.")
    return {"raw_choice": value, "display_value": value if confidence >= CONFIDENCE_THRESHOLD else "Ambiguous — no automated conclusion assigned.", "confidence": float(confidence), "probabilities": probabilities}


def normalize_response(response: Any, run_id: str) -> dict[str, Any]:
    try:
        design = _choice(response.choices["design_status"], _CHOICES["design_status"])
        result = _choice(response.choices["result_label"], _CHOICES["result_label"])
        next_experiment = _choice(response.choices["next_experiment"], _CHOICES["next_experiment"])
        score = response.scores["overfitting_risk"]
        noul = response.nouls["survivorship_bias_material"].noul
    except (AttributeError, KeyError, TypeError) as error:
        raise JevAuditError("Jev response did not contain all required typed answers.") from error
    values = (score.score, score.confidence, noul)
    if not all(_number(value) for value in values) or not 0 <= score.score <= 2 or not 0 <= score.confidence <= 1 or not 0 <= noul <= 1:
        raise JevAuditError("Jev returned an out-of-range Score, confidence, or Noul probability.")
    probabilities = _probabilities(score.probabilities, {"0", "1", "2"})
    expected_score = sum(int(level) * probability for level, probability in probabilities.items())
    if not math.isclose(float(score.score), expected_score, abs_tol=1e-6):
        raise JevAuditError("Jev Score does not agree with its probability distribution.")
    legend = {str(key): value for key, value in score.legend.items()} if isinstance(score.legend, Mapping) else {}
    if set(legend) != {"0", "1", "2"} or not _finite_json(legend):
        raise JevAuditError("Jev returned an invalid Score legend.")
    returned_model = getattr(response, "model", None)
    if not isinstance(returned_model, str) or not returned_model:
        raise JevAuditError("Jev response did not identify its model.")
    label = ("low", "medium", "high")[round(score.score)]
    normalized = {"run_id": run_id, "provider": "TypeSafe Jev via Vercel AI Gateway", "requested_model": MODEL, "returned_model": returned_model, "audit_status": "completed", "confidence_threshold": CONFIDENCE_THRESHOLD, "answers": {"design_status": design, "result_label": result, "overfitting_risk": {"score": float(score.score), "derived_label": label, "confidence": float(score.confidence), "probabilities": probabilities, "legend": legend}, "survivorship_bias_material": {"probability": float(noul)}, "next_experiment": next_experiment}, "policy_note": POLICY_NOTE}
    if not _finite_json(normalized):
        raise JevAuditError("Jev response cannot be serialized safely.")
    return normalized


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
