"""Stable artifact writers and human-facing report rendering."""

import json
import math
from pathlib import Path
from typing import Any

from .engine import BacktestResult, RESEARCH_QUESTION


def _fmt(value: float | None, percent: bool = False) -> str:
    if value is None or not math.isfinite(value):
        return "N/A"
    return f"{value:.2%}" if percent else f"{value:.2f}"


def artifact_paths(result: BacktestResult, output_dir: Path) -> dict[str, Path]:
    prefix = output_dir / result.run_id
    return {"daily": prefix.with_name(prefix.name + "_daily.csv"),
            "rebalances": prefix.with_name(prefix.name + "_rebalances.csv"),
            "record": prefix.with_name(prefix.name + "_research_record.json"),
            "report": prefix.with_name(prefix.name + "_report.md")}


def _write_text_atomically(path: Path, content: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def write_baseline_artifacts(result: BacktestResult, output_dir: Path) -> dict[str, Path]:
    """Persist all deterministic artifacts before any optional Jev invocation."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = artifact_paths(result, output_dir)
    result.daily.reset_index().to_csv(paths["daily"], index=False)
    result.portfolio.rebalances.to_csv(paths["rebalances"], index=False)
    _write_text_atomically(paths["record"], json.dumps(result.research_record(), indent=2, allow_nan=False))
    _write_text_atomically(paths["report"], render_report(result, paths, None, None))
    return paths


def update_jev_artifacts(result: BacktestResult, paths: dict[str, Path], audit: dict[str, Any] | None,
                         audit_error: str | None = None) -> dict[str, Path]:
    """Add a Jev result or failure note without rewriting deterministic artifacts."""
    updated = dict(paths)
    if audit is not None:
        audit_path = paths["record"].with_name(paths["record"].name.replace("_research_record.json", "_jev_audit.json"))
        _write_text_atomically(audit_path, json.dumps(audit, indent=2, allow_nan=False))
        updated["audit"] = audit_path
    _write_text_atomically(paths["report"], render_report(result, updated, audit, audit_error))
    return updated


def write_artifacts(result: BacktestResult, output_dir: Path, audit: dict[str, Any] | None = None,
                    audit_error: str | None = None) -> dict[str, Path]:
    """Compatibility wrapper for callers that do not need staged persistence."""
    paths = write_baseline_artifacts(result, output_dir)
    return update_jev_artifacts(result, paths, audit, audit_error) if (audit is not None or audit_error) else paths


def render_report(result: BacktestResult, paths: dict[str, Path], audit: dict[str, Any] | None,
                  audit_error: str | None) -> str:
    s, b, config = result.strategy_metrics, result.benchmark_metrics, result.config
    metrics = [("Annualized return", s.annualized_return, b.annualized_return, True),
               ("Annualized volatility", s.annualized_volatility, b.annualized_volatility, True),
               ("Sharpe ratio", s.sharpe_ratio, b.sharpe_ratio, False),
               ("Maximum drawdown", s.maximum_drawdown, b.maximum_drawdown, True),
               ("Cumulative return", s.cumulative_return, b.cumulative_return, True),
               ("Total turnover", s.total_turnover, b.total_turnover, False)]
    rows = "\n".join(f"| {name} | {_fmt(float(left), pct)} | {_fmt(float(right), pct)} |" for name, left, right, pct in metrics)
    audit_section = "No Jev audit was run."
    if audit_error:
        audit_section = f"The quantitative backtest completed, but the Jev audit was unavailable: {audit_error}"
    elif audit:
        a = audit["answers"]
        score_caution = " Interpret with caution: low-confidence structured assessment." if a["overfitting_risk"]["confidence"] < 0.65 else ""
        audit_section = ("TypeSafe Jev was used only to classify research-process limitations and recommend a next experiment. "
                         "It did not calculate prices, returns, metrics, holdings, or trading actions.\n\n"
                         "| Audit item | Structured result | Confidence |\n|---|---:|---:|\n"
                         f"| Design status | {a['design_status']['display_value']} | {a['design_status']['confidence']:.2f} |\n"
                         f"| Historical-result label | {a['result_label']['display_value']} | {a['result_label']['confidence']:.2f} |\n"
                         f"| Apparent overfitting risk | {a['overfitting_risk']['derived_label']} ({a['overfitting_risk']['score']:.2f}){score_caution} | {a['overfitting_risk']['confidence']:.2f} |\n"
                         f"| Survivorship-bias materiality | {a['survivorship_bias_material']['probability']:.1%} probability | N/A |\n"
                         f"| Recommended next experiment | {a['next_experiment']['display_value']} | {a['next_experiment']['confidence']:.2f} |\n\n"
                         f"**Policy note:** {audit['policy_note']}")
    command = f"python -m driftlab run --tickers {' '.join(config.tickers)} --start {config.start} --end {config.end} --lookback {config.lookback} --holdings {config.holdings} --rebalance monthly --cost-bps {config.cost_bps}"
    return f"""# DriftLab Momentum Research Report

## Research Question

{RESEARCH_QUESTION}

## Historical Setup

Requested data range: [{config.start}, {config.end}) (end exclusive). Available data range: {result.price_data.prices.index[0].date()} to {result.price_data.prices.index[-1].date()}. Allocation decision date: {result.allocation_date.date()}; performance-return dates: {result.performance_start.date()} to {result.price_data.prices.index[-1].date()}. Signal: {config.lookback}-trading-day trailing momentum; Top {config.holdings}; monthly rebalance; {config.cost_bps:g} bps per turnover unit.

## Universe and Data

Requested: {', '.join(config.tickers)}. Valid: {', '.join(result.price_data.valid_tickers)}. Excluded: {', '.join(result.price_data.excluded_tickers) or 'None'}. Data source: yfinance `Adj Close` with `auto_adjust=False`; raw `Close` is rejected. DriftLab rejects missing expected regular NYSE sessions and does not fill prices.

## Methodology

At each completed calendar month's last available trading session, DriftLab ranks trailing momentum and assigns equal target weights to the top assets. Alphabetical ticker order breaks tied signals. A selection uses prices available at that close and affects returns only from the following trading session, preventing same-day look-ahead. A terminal decision without a following in-range session is not executed. Initial cash-to-portfolio allocation is included in turnover and costs.

The strategy is a **constant-target-weight approximation**: target weights remain fixed between scheduled rebalances. It does not model maintenance trades that would be required to keep actual holdings at those target weights as prices move, and it therefore omits those maintenance costs.

The benchmark is **true equal-weight buy-and-hold**: equal capital is invested once at the allocation date, positions then drift with price changes, and it is never rebalanced. The benchmark has no modeled entry cost, while the strategy includes its entry transaction cost; the comparison is net strategy performance versus gross buy-and-hold performance.

## Strategy vs Benchmark

| Metric | Momentum Strategy | Equal-Weight Buy & Hold |
|---|---:|---:|
{rows}

Annualized return uses only the {s.investable_trading_days} market-return observations after allocation. The allocation-close cost is included in cumulative return, volatility, Sharpe ratio, and drawdown.

## Turnover and Costs

Strategy turnover: {s.total_turnover:.4f}; average daily turnover: {s.average_daily_turnover:.6f}; executed rebalance decisions: {s.rebalance_events}. Costs equal turnover × {config.cost_bps:g}/10,000 and apply only on ledgered allocation decisions.

## Jev Research Audit

{audit_section}

## Limitations and Caveats

Historical performance does not predict future performance. yfinance data may have quality, coverage, adjustment, and availability limitations. The regular-session calendar does not model extraordinary exchange closures. A current hand-selected ticker list can create survivorship and selection bias; a small universe is not representative of the full market. Transaction-cost modeling is simplified and omits real execution frictions. Testing many variants can overfit historical data. A separate out-of-sample test is necessary before stronger interpretation. DriftLab provides no investment advice. Jev output is a methodology aid, not a market forecast or investment recommendation.

## Reproducibility

Artifacts: {', '.join(path.name for path in paths.values())}.

```bash
{command}
```
"""
