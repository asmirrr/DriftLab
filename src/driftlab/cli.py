"""Typer command line interface."""

from datetime import date
import json
from pathlib import Path
import typer
from dotenv import load_dotenv

from .config import ConfigurationError, RunConfig
from .data import DataError, fetch_prices
from .engine import run_backtest
from .jev_audit import JevAuditError, audit_research_record
from .reporting import update_jev_artifacts, write_baseline_artifacts

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _fail(message: str) -> None:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(2)


def _parse_date(value: str, option: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        _fail(f"{option} must be an ISO date in YYYY-MM-DD format.")
        raise error


@app.command(context_settings={"allow_extra_args": True})
def run(
    context: typer.Context,
    tickers: str = typer.Option(..., "--tickers", help="First ticker; add remaining tickers separated by spaces."),
    start: str = typer.Option(..., "--start"), end: str = typer.Option(..., "--end"),
    lookback: int = typer.Option(126, "--lookback"), holdings: int = typer.Option(3, "--holdings"),
    rebalance: str = typer.Option("monthly", "--rebalance"), cost_bps: float = typer.Option(10.0, "--cost-bps"),
    output_dir: Path = typer.Option(Path("outputs"), "--output-dir"),
    audit_with_jev: bool = typer.Option(False, "--audit-with-jev"),
) -> None:
    """Run a deterministic historical momentum study."""
    try:
        config = RunConfig.create([tickers, *context.args], _parse_date(start, "--start"), _parse_date(end, "--end"), lookback, holdings, rebalance, cost_bps)
        data = fetch_prices(config.tickers, config.start, config.end)
        result = run_backtest(config, data.prices)
    except (ConfigurationError, DataError) as error:
        _fail(str(error))
    paths = write_baseline_artifacts(result, output_dir)
    audit = None
    audit_error = None
    if audit_with_jev:
        load_dotenv()
        try:
            audit = audit_research_record(result.research_record())
        except Exception as error:
            audit_error = str(error)
            typer.secho(f"Warning: {audit_error}", fg=typer.colors.YELLOW, err=True)
        try:
            paths = update_jev_artifacts(result, paths, audit, audit_error)
        except Exception as error:
            audit_error = f"Jev artifact update failed: {error}"
            typer.secho(f"Warning: {audit_error}", fg=typer.colors.YELLOW, err=True)
    typer.echo("DriftLab — Momentum Research Run\n")
    typer.echo("Universe requested: " + ", ".join(config.tickers))
    typer.echo("Universe used: " + ", ".join(result.price_data.valid_tickers))
    typer.echo(f"Period used: {result.daily.index[0].date()} to {result.daily.index[-1].date()}")
    typer.echo(f"Signal: {config.lookback}-trading-day trailing momentum")
    typer.echo(f"Portfolio: Top {config.holdings} assets, equal target weights, monthly rebalance")
    typer.echo(f"Estimated cost: {config.cost_bps:g} bps per unit of turnover\n")
    typer.echo(f"Annualized return: {result.strategy_metrics.annualized_return:.2%} (strategy), {result.benchmark_metrics.annualized_return:.2%} (buy-and-hold)")
    typer.echo("\nArtifacts saved:")
    for path in paths.values():
        typer.echo(f"  {path}")


@app.command()
def audit(research_record: Path) -> None:
    """Audit a saved research record without downloading data or rerunning a backtest."""
    load_dotenv()
    try:
        record = json.loads(research_record.read_text(encoding="utf-8"))
        result = audit_research_record(record)
    except (OSError, json.JSONDecodeError, JevAuditError) as error:
        _fail(str(error))
    target = research_record.with_name(research_record.stem.replace("_research_record", "") + "_jev_audit.json")
    target.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    typer.echo(f"Jev audit saved: {target}")
