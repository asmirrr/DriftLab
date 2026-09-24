# DriftLab

## What It Is

DriftLab is a local-first Python CLI for reproducible historical momentum research. It is an educational research tool, not a prediction, trading, brokerage, portfolio-management, or investment-advice product.

## Research Question

Among a user-supplied basket of liquid U.S. stocks, does a monthly-rebalanced equal-weighted portfolio of the top N trailing-momentum names outperform an equal-weighted buy-and-hold portfolio of the same tickers after modeled transaction costs?

## Why This Is Not a Prediction Tool

Historical exploratory results do not predict future performance. DriftLab never generates trading instructions or recommendations.

## Methodology

Trailing momentum is price today divided by price `lookback` trading days ago, minus one. On each completed calendar month's last available trading session, DriftLab ranks available signals and uses alphabetical ticker order to break ties. A decision made at that close affects returns only from the following session. A terminal decision without a following in-range session is not executed. Transaction cost is turnover multiplied by basis points divided by 10,000; the initial cash-to-portfolio allocation is charged.

`--start` is inclusive and `--end` is exclusive. DriftLab records the data range, allocation-decision date, and performance-return dates separately. Annualized return uses only market-return days after allocation, while the allocation-close cost remains in cumulative return, volatility, Sharpe ratio, and drawdown. Maximum drawdown starts from initial capital of 1.0.

DriftLab downloads yfinance with `auto_adjust=False` and requires `Adj Close`; it never substitutes raw `Close`. Every adjusted close must be finite and positive. It rejects both missing expected NYSE sessions and unexpected weekend, holiday, or non-session rows, and does not fill observations. The built-in calendar includes regular closures plus documented exceptional full-day closures through January 9, 2025; future exceptional closures require a calendar update.

The final valid universe is fixed before signals are calculated. DriftLab uses the common contiguous window for those tickers, so a ticker that appears only later can move the analysis start. If fewer than the requested holdings have a usable signal at a rebalance, it holds every eligible ticker at equal weight.

Strategy weights are constant targets between scheduled rebalances. This is an approximation: DriftLab does not trade to maintain those targets as prices drift, so it omits any maintenance turnover and costs.

The benchmark is **true equal-weight buy-and-hold**: equal capital is allocated once at the allocation date; positions then drift and are never rebalanced. This is deliberately different from applying constant equal weights each day, which would imply rebalancing. The benchmark has no modeled entry cost, so the comparison is net strategy performance against gross buy-and-hold performance.

## Installation

Python 3.11 or newer is required. On PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Running a Backtest

```powershell
python -m driftlab run --tickers AAPL MSFT NVDA AMZN GOOGL META --start 2020-01-01 --end 2026-01-01 --lookback 126 --holdings 3 --rebalance monthly --cost-bps 10
```

## Running a Jev Audit

Jev reviews only the completed compact research record. Python exclusively owns prices, returns, metrics, selection, weights, and costs. Jev cannot modify a run or automatically perform its suggested experiment.

```powershell
$env:TYPESAFE_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'TypeSafe API key' -AsSecureString)).Password
uv run --frozen python -m driftlab run --tickers AAPL MSFT NVDA AMZN GOOGL META --start 2020-01-01 --end 2026-01-01 --lookback 126 --holdings 3 --rebalance monthly --cost-bps 10 --audit-with-jev
```

Direct TypeSafe is the current Jev provider. `TYPESAFE_API_KEY` is needed only for `run --audit-with-jev` or the standalone `audit` command; the deterministic backtest requires no Jev credential. You can also put the key in a local, Git-ignored `.env` file. `AI_GATEWAY_API_KEY` is not used.

Verified against the [official Python SDK documentation](https://docs.typesafe.ai/sdk/python/api/clients/sync) and installed `typesafe-sdk` 0.7.0: the adapter constructs `TypeSafeClient(api_key=key, base_url="https://api.typesafe.ai", model="jev-latest", timeout=30.0, retry=RetryPolicy(max_retries=0))` and calls `system_one(state, questions)`, issuing `POST https://api.typesafe.ai/v1/systemone` with Bearer authentication. No dependency upgrade is needed. The base URL and model are explicit, so `TYPESAFE_BASE_URL` and `TYPESAFE_DEFAULT_MODEL` do not override this adapter. Routing remains confined to `jev_audit.py`.

`jev-latest` is the [current SDK default alias](https://docs.typesafe.ai/concepts/system-one), not an immutable version pin. Audit JSON retains both the requested alias and the returned model identifier; the alias may change over time. Jev is an advisory methodology audit, never part of portfolio calculation. A missing key or failed audit does not invalidate or remove deterministic outputs. Audit an existing record without data download:

```powershell
uv run --frozen python -m driftlab audit outputs\<run_id>_research_record.json
```

## Output Files

Each run writes daily returns/equity/turnover CSV, a complete rebalance ledger CSV, compact factual research-record JSON, and a Markdown report **before** Jev is called. A successful audit also writes Jev audit JSON. Failed Jev attempts are recorded in the report when report writing remains available. Jev failures, malformed responses, serialization failures, and report-update failures cannot remove or rewrite those baseline quantitative artifacts.

## Understanding the Metrics

Annualized return converts the observed compounded result to a 252-trading-day rate. The allocation-close entry cost affects cumulative return and drawdown; volatility and Sharpe use only subsequent actual market-return observations. Sharpe ratio is return per unit of volatility assuming zero risk-free rate. Maximum drawdown is the deepest peak-to-trough equity decline.

## Why Jev Is Used

Jev classifies documented research-process limitations and suggests one next experiment. It never calculates, forecasts, chooses securities, changes parameters, or executes an action.

## Confidence Policy

Choice answers below 0.65 display as “Ambiguous — no automated conclusion assigned.” Score results retain their numeric 0–2 position, probabilities, and confidence; scores below 0.65 require caution. Noul is displayed as a probability without a forced binary conclusion.

`parameter_sets_tested` in the research record means configurations evaluated in this DriftLab invocation only. It does not establish the complete historical search performed by a researcher.

## Research Limitations

Historical performance does not predict future performance. Prototype yfinance data may have quality, coverage, adjustment, and availability limitations. A current hand-selected ticker list can create survivorship and selection bias. A small universe is not representative of the full market. Simplified costs omit real execution frictions. Testing many variants can overfit historical data. A separate out-of-sample test is necessary before stronger interpretation. The tool provides no investment advice. Jev is a methodology aid, not a market forecast or investment recommendation.

## Development and Tests

```powershell
pytest -q
python -m driftlab --help
```

## Next Experiments

1. Compare 63-, 126-, and 252-trading-day momentum windows.
2. Compare top-1, top-3, and top-5 portfolio sizes.
3. Test several cost assumptions, such as 5, 10, 25, and 50 basis points.
4. Add a time-based development versus holdout split.
5. Add SPY as a separate informational benchmark.
6. Test a broader pre-specified universe.
7. Replace prototype data ingestion with a more controlled provider and dataset.

## Disclaimer

DriftLab is educational software for historical research. It provides no investment advice.
