from types import SimpleNamespace
import pytest

from driftlab.jev_audit import JevAuditError, audit_research_record, normalize_response


def _answer(**values):
    return SimpleNamespace(**values)


def test_mocked_jev_response_normalizes_and_low_confidence_is_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    response = SimpleNamespace(
        choices={"design_status": _answer(choice="exploratory_ready", confidence=0.4, probabilities={"exploratory_ready": 0.5}),
                 "result_label": _answer(choice="requires_validation", confidence=0.9, probabilities={"requires_validation": 1.0}),
                 "next_experiment": _answer(choice="out_of_sample_split", confidence=0.9, probabilities={"out_of_sample_split": 1.0})},
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
        audit_research_record({"run_id": "x"})


def test_research_record_state_has_no_price_history(prices, tmp_path) -> None:
    from datetime import date
    from driftlab.config import RunConfig
    from driftlab.engine import run_backtest
    record = run_backtest(RunConfig.create(["AAA", "BBB", "CCC"], date(2024, 1, 1), date(2025, 1, 1), 20, 2), prices).research_record()
    assert "prices" not in record
    assert "daily" not in record
