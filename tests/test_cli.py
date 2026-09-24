from typer.testing import CliRunner

from driftlab.cli import app


def test_cli_rejects_nonfinite_transaction_cost_before_data_download() -> None:
    result = CliRunner().invoke(app, ["run", "--tickers", "AAA BBB", "--holdings", "1", "--start", "2024-01-01", "--end", "2024-02-01", "--cost-bps", "nan"])
    assert result.exit_code == 2
    assert "finite nonnegative" in result.output
