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
    return {"run_id": "x", "research_question": "q", "requested_tickers": ["AAA", "BBB"],
            "valid_tickers": ["AAA", "BBB"], "excluded_tickers": [], "data_source": "yfinance",
            "requested_start": "2024-01-01", "requested_end": "2024-02-01", "data_start": "2024-01-02",
            "data_end": "2024-01-31", "allocation_date": "2024-01-31", "performance_start": "2024-02-01",
            "strategy": {}, "research_process": {}, "strategy_metrics": {}, "benchmark_metrics": {}, "turnover": {}}


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
