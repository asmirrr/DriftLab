from typer.testing import CliRunner
import json

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
