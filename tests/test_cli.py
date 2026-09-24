from typer.testing import CliRunner
import json
import pytest

from driftlab.cli import app
from driftlab.data import clean_prices


def test_cli_rejects_nonfinite_transaction_cost_before_data_download() -> None:
    result = CliRunner().invoke(app, ["run", "--tickers", "AAA BBB", "--holdings", "1", "--start", "2024-01-01", "--end", "2024-02-01", "--cost-bps", "nan"])
    assert result.exit_code == 2
    assert "finite nonnegative" in result.output


def test_cli_records_failed_jev_serialization_without_touching_baseline(prices, tmp_path, monkeypatch) -> None:
    import driftlab.cli as cli
    monkeypatch.setattr(cli, "fetch_prices", lambda tickers, start, end: clean_prices(prices, tickers, start, end))
    monkeypatch.setattr(cli, "audit_research_record", lambda record: {"bad": float("nan")})
    result = CliRunner().invoke(app, ["run", "--tickers", "AAA BBB CCC", "--start", "2024-01-02", "--end", "2024-05-20", "--lookback", "20", "--holdings", "2", "--output-dir", str(tmp_path), "--audit-with-jev"])
    assert result.exit_code == 0
    report = next(tmp_path.glob("*_report.md")).read_text(encoding="utf-8")
    assert "Jev audit was unavailable" in report
    record = json.loads(next(tmp_path.glob("*_research_record.json")).read_text(encoding="utf-8"))
    assert record["strategy_metrics"]["cumulative_return"] is not None


@pytest.mark.parametrize("failure", ["http_403", "timeout"])
def test_direct_provider_failure_preserves_quantitative_artifacts(prices, tmp_path, monkeypatch, failure) -> None:
    import httpx2
    import typesafe_sdk
    import driftlab.cli as cli

    real_client = typesafe_sdk.TypeSafeClient
    before = {}
    calls = []
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-test-key")
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    monkeypatch.setattr(cli, "fetch_prices", lambda tickers, start, end: clean_prices(prices, tickers, start, end))

    def handler(request):
        calls.append(str(request.url))
        # All four baseline artifacts must already be durable before HTTP.
        before.update({path: path.read_bytes() for path in tmp_path.iterdir()})
        assert len(before) == 4
        if failure == "timeout":
            raise httpx2.ReadTimeout("offline timeout", request=request)
        return httpx2.Response(403, json={"error": "offline denied"})

    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient",
                        lambda **kwargs: real_client(**kwargs, transport=httpx2.MockTransport(handler)))
    result = CliRunner().invoke(app, ["run", "--tickers", "AAA BBB CCC", "--start", "2024-01-02",
                                    "--end", "2024-05-20", "--lookback", "20", "--holdings", "2",
                                    "--output-dir", str(tmp_path), "--audit-with-jev"])
    assert result.exit_code == 0, result.output
    assert calls == ["https://api.typesafe.ai/v1/systemone"]
    assert "offline-test-key" not in result.output
    assert not list(tmp_path.glob("*_jev_audit.json"))
    for path, original in before.items():
        if path.suffix != ".md":
            assert path.read_bytes() == original
        else:
            report = path.read_text(encoding="utf-8")
            assert "Jev audit was unavailable" in report
            # Only the advisory section may change, not quantitative reporting.
            assert path.read_bytes().split(b"## Jev Research Audit")[0] == original.split(b"## Jev Research Audit")[0]
