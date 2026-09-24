from types import SimpleNamespace
import json
import pytest

from driftlab.jev_audit import JevAuditError, audit_research_record, normalize_response, validate_research_record


def _answer(**values):
    return SimpleNamespace(**values)


def test_mocked_jev_response_normalizes_and_low_confidence_is_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    response = SimpleNamespace(
        choices={"design_status": _answer(choice="exploratory_ready", confidence=0.4, probabilities={"exploratory_ready": 0.5, "validation_ready": 0.3, "insufficient": 0.2}),
                 "result_label": _answer(choice="requires_validation", confidence=0.9, probabilities={"requires_validation": 0.8, "exploratory_signal": 0.1, "inconclusive": 0.1}),
                 "next_experiment": _answer(choice="out_of_sample_split", confidence=0.9, probabilities={"out_of_sample_split": 0.7, "cost_sensitivity": 0.1, "parameter_sensitivity": 0.1, "universe_expansion": 0.1})},
        scores={"overfitting_risk": _answer(score=1.1, confidence=0.7, probabilities={0: 0, 1: .9, 2: .1}, legend={0: "low", 1: "medium", 2: "high"})},
        nouls={"survivorship_bias_material": _answer(noul=.94)},
        model="typesafe-ai/jev",
    )
    normalized = normalize_response(response, "run_x")
    assert normalized["answers"]["design_status"]["display_value"].startswith("Ambiguous")
    assert normalized["answers"]["survivorship_bias_material"]["probability"] == .94
    assert normalized["answers"]["overfitting_risk"]["score"] == 1.1


def test_missing_gateway_key_is_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    with pytest.raises(JevAuditError, match="AI_GATEWAY_API_KEY"):
        audit_research_record(_valid_record())


def _valid_record() -> dict:
    metrics = {"cumulative_return": 0.0, "annualized_return": 0.0, "annualized_volatility": 0.0,
               "sharpe_ratio": None, "maximum_drawdown": 0.0, "average_daily_turnover": 0.0,
               "total_turnover": 0.0, "rebalance_events": 1, "investable_trading_days": 1, "valid_tickers": 2}
    return {"run_id": "x", "research_question": "q", "requested_tickers": ["AAA", "BBB"],
            "valid_tickers": ["AAA", "BBB"], "excluded_tickers": [], "data_source": "yfinance",
            "requested_start": "2024-01-01", "requested_end": "2024-02-02", "data_start": "2024-01-02",
            "data_end": "2024-02-01", "allocation_date": "2024-01-31", "performance_start": "2024-02-01",
            "actual_start": "2024-02-01", "actual_end": "2024-02-01",
            "strategy": {"name": "Top-N Trailing Momentum", "lookback_trading_days": 20, "holdings": 1,
                         "rebalance_frequency": "monthly", "cost_bps": 0.0, "long_only": True,
                         "weighting": "equal_weighted_target_weights"},
            "research_process": {"parameter_sets_tested": 1, "out_of_sample_test": False,
                                 "historical_constituents_used": False, "data_notes": ["note"]},
            "strategy_metrics": metrics, "benchmark_metrics": dict(metrics),
            "turnover": {"average_daily_turnover": 0.0, "total_turnover": 0.0, "rebalance_events": 1},
            "metadata": {"python_version": "3.14", "package_versions": {"numpy": "2", "pandas": "3", "typesafe-sdk": "0.7", "yfinance": "1"}, "code_version": "0.1.0", "parameter_sets_tested_scope": "configurations evaluated in this invocation only"}}


def test_research_record_state_has_no_price_history(prices, tmp_path) -> None:
    from datetime import date
    from driftlab.config import RunConfig
    from driftlab.engine import run_backtest
    record = run_backtest(RunConfig.create(["AAA", "BBB", "CCC"], date(2024, 1, 2), date(2024, 5, 20), 20, 2), prices).research_record()
    assert "prices" not in record
    assert "daily" not in record


def test_jev_validation_rejects_nonfinite_record_and_out_of_range_response() -> None:
    record = _valid_record()
    record["turnover"] = {"bad": float("nan")}
    with pytest.raises(JevAuditError, match="non-finite"):
        validate_research_record(record)
    malformed = SimpleNamespace(choices={}, scores={}, nouls={})
    with pytest.raises(JevAuditError, match="required typed answers"):
        normalize_response(malformed, "run_x")
    response = SimpleNamespace(
        choices={"design_status": _answer(choice="exploratory_ready", confidence=1.1, probabilities={"exploratory_ready": 1, "validation_ready": 0, "insufficient": 0}),
                 "result_label": _answer(choice="inconclusive", confidence=1, probabilities={"inconclusive": 1, "exploratory_signal": 0, "requires_validation": 0}),
                 "next_experiment": _answer(choice="cost_sensitivity", confidence=1, probabilities={"out_of_sample_split": 0, "parameter_sensitivity": 0, "cost_sensitivity": 1, "universe_expansion": 0})},
        scores={"overfitting_risk": _answer(score=1, confidence=1, probabilities={0: 0, 1: 1, 2: 0}, legend={0: "low", 1: "medium", 2: "high"})},
        nouls={"survivorship_bias_material": _answer(noul=.5)},
    )
    with pytest.raises(JevAuditError, match="invalid Choice"):
        normalize_response(response, "run_x")


def test_jev_record_schema_rejects_null_or_smuggled_nested_payload() -> None:
    record = _valid_record()
    record["strategy"] = None
    with pytest.raises(JevAuditError, match="invalid schema"):
        validate_research_record(record)
    record = _valid_record()
    record["strategy_metrics"]["raw_prices"] = [1, 2, 3]
    with pytest.raises(JevAuditError, match="invalid schema"):
        validate_research_record(record)


def test_jev_response_rejects_probability_contradictions_and_unsafe_legend() -> None:
    def response():
        return SimpleNamespace(
            model="typesafe-ai/jev",
            choices={"design_status": _answer(choice="exploratory_ready", confidence=1, probabilities={"exploratory_ready": .1, "validation_ready": .9, "insufficient": 0}),
                     "result_label": _answer(choice="inconclusive", confidence=1, probabilities={"inconclusive": 1, "exploratory_signal": 0, "requires_validation": 0}),
                     "next_experiment": _answer(choice="cost_sensitivity", confidence=1, probabilities={"out_of_sample_split": 0, "parameter_sensitivity": 0, "cost_sensitivity": 1, "universe_expansion": 0})},
            scores={"overfitting_risk": _answer(score=0, confidence=1, probabilities={0: 0, 1: 1, 2: 0}, legend={0: "low", 1: "medium", 2: "high"})},
            nouls={"survivorship_bias_material": _answer(noul=.5)},
        )
    with pytest.raises(JevAuditError, match="Choice does not agree"):
        normalize_response(response(), "run_x")
    valid = response()
    valid.choices["design_status"].probabilities = {"exploratory_ready": 1, "validation_ready": 0, "insufficient": 0}
    with pytest.raises(JevAuditError, match="Score does not agree"):
        normalize_response(valid, "run_x")
    valid.scores["overfitting_risk"].score = 1
    valid.scores["overfitting_risk"].legend["bad"] = float("nan")
    with pytest.raises(JevAuditError, match="invalid Score legend"):
        normalize_response(valid, "run_x")


def test_installed_typesafe_sdk_uses_mocked_http_and_parses_typed_response() -> None:
    import httpx2
    from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient

    captured = {}
    def handler(request):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx2.Response(200, json={"model": "typesafe-ai/jev", "usage": {}, "answers": {
            "choice": {"type": "choice", "choice": "yes", "confidence": .9, "probabilities": {"yes": .9, "no": .1}}}})

    with TypeSafeClient(api_key="test-key", base_url="https://ai-gateway.vercel.sh/typesafe", model="typesafe-ai/jev",
                        retry=RetryPolicy(max_retries=0), transport=httpx2.MockTransport(handler)) as client:
        response = client.system_one({"run_id": "x"}, {"choice": Choice(instructions="test", criteria={"yes": "yes", "no": "no"})})
    assert captured["url"].startswith("https://ai-gateway.vercel.sh/typesafe")
    assert captured["authorization"] == "Bearer test-key"
    assert captured["body"]["model"] == "typesafe-ai/jev"
    assert response.choices["choice"].choice == "yes"


def test_audit_adapter_rejects_contradictory_mocked_sdk_http_response(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx2
    import typesafe_sdk
    real_client = typesafe_sdk.TypeSafeClient
    body = {"model": "typesafe-ai/jev", "usage": {}, "answers": {
        "design_status": {"type": "choice", "choice": "exploratory_ready", "confidence": 1, "probabilities": {"insufficient": 0, "exploratory_ready": .1, "validation_ready": .9}},
        "result_label": {"type": "choice", "choice": "inconclusive", "confidence": 1, "probabilities": {"inconclusive": 1, "exploratory_signal": 0, "requires_validation": 0}},
        "next_experiment": {"type": "choice", "choice": "cost_sensitivity", "confidence": 1, "probabilities": {"out_of_sample_split": 0, "parameter_sensitivity": 0, "cost_sensitivity": 1, "universe_expansion": 0}},
        "overfitting_risk": {"type": "score", "score": 1, "confidence": 1, "legend": {"0": "low", "1": "medium", "2": "high"}, "probabilities": {"0": 0, "1": 1, "2": 0}},
        "survivorship_bias_material": {"type": "noul", "noul": .5},
    }}
    def handler(request):
        return httpx2.Response(200, json=body)
    def client_factory(**kwargs):
        return real_client(**kwargs, transport=httpx2.MockTransport(handler))
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "offline-test-key")
    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", client_factory)
    with pytest.raises(JevAuditError, match="Choice does not agree"):
        audit_research_record(_valid_record())
