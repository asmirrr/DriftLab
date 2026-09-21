"""Stable artifact writers and human-facing report rendering."""

import json
from pathlib import Path
from typing import Any
from .engine import BacktestResult, RESEARCH_QUESTION


def _fmt(value: float | None, percent: bool = False) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2%}" if percent else f"{value:.2f}"


def write_artifacts(result: BacktestResult, output_dir: Path, audit: dict[str, Any] | None = None,
                    audit_error: str | None = None) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / result.run_id
    paths = {"daily": prefix.with_name(prefix.name + "_daily.csv"),
             "rebalances": prefix.with_name(prefix.name + "_rebalances.csv"),
             "record": prefix.with_name(prefix.name + "_research_record.json"),
             "report": prefix.with_name(prefix.name + "_report.md")}
    result.daily.reset_index().to_csv(paths["daily"], index=False)
    result.portfolio.rebalances.to_csv(paths["rebalances"], index=False)
    record = result.research_record()
    paths["record"].write_text(json.dumps(record, indent=2, allow_nan=False), encoding="utf-8")
    if audit is not None:
        paths["audit"] = prefix.with_name(prefix.name + "_jev_audit.json")
        paths["audit"].write_text(json.dumps(audit, indent=2, allow_nan=False), encoding="utf-8")
    paths["report"].write_text(render_report(result, paths, audit, audit_error), encoding="utf-8")
    return paths


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

Requested range: {config.start} to {config.end}. Analyzed range: {result.daily.index[0].date()} to {result.daily.index[-1].date()}. Signal: {config.lookback}-trading-day trailing momentum; Top {config.holdings}; monthly rebalance; {config.cost_bps:g} bps per turnover unit.

## Universe and Data

Requested: {', '.join(config.tickers)}. Valid: {', '.join(result.price_data.valid_tickers)}. Excluded: {', '.join(result.price_data.excluded_tickers) or 'None'}. Data source: yfinance adjusted-close data.

## Methodology

At each last actual trading day of a month, DriftLab ranks available trailing momentum and assigns equal target weights to the top assets. Alphabetical ticker order breaks tied signals. A selection uses prices available at that close and affects returns only from the following trading day, preventing look-ahead. Initial cash-to-portfolio allocation is included in turnover and costs.

The benchmark is **true equal-weight buy-and-hold**: equal capital is invested once at the initial investable date, positions then drift with price changes, and it is never rebalanced. This differs from applying fixed equal weights every day, which would implicitly rebalance.

## Strategy vs Benchmark

| Metric | Momentum Strategy | Equal-Weight Buy & Hold |
|---|---:|---:|
{rows}

## Turnover and Costs

Strategy turnover: {s.total_turnover:.4f}; average daily turnover: {s.average_daily_turnover:.6f}; rebalance events: {s.rebalance_events}. Costs equal turnover × {config.cost_bps:g}/10,000 and apply only on rebalance events.

## Jev Research Audit

{audit_section}

## Limitations and Caveats

Historical performance does not predict future performance. yfinance data may have quality, coverage, adjustment, and availability limitations. A current hand-selected ticker list can create survivorship and selection bias; a small universe is not representative of the full market. Transaction-cost modeling is simplified and omits real execution frictions. Testing many variants can overfit historical data. A separate out-of-sample test is necessary before stronger interpretation. DriftLab provides no investment advice. Jev output is a methodology aid, not a market forecast or investment recommendation.

## Reproducibility

Artifacts: {', '.join(path.name for path in paths.values())}.

```bash
{command}
```
"""
