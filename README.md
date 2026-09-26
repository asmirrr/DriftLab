# DriftLab

## What It Is

DriftLab is a local-first Python CLI for reproducible historical momentum research. It is an educational research tool, not a prediction, trading, brokerage, portfolio-management, or investment-advice product.

## Research Question

Among a user-supplied basket of liquid U.S. stocks, does a monthly-rebalanced equal-weighted portfolio of the top N trailing-momentum names outperform an equal-weighted buy-and-hold portfolio of the same tickers after modeled transaction costs?

## Why This Is Not a Prediction Tool

Historical exploratory results do not predict future performance. DriftLab never generates trading instructions or recommendations.

## Current Research Status

The deterministic engine is audit-closed for exploratory research; this is not validation of a general investment edge. The saved six-ticker experiment (AAPL, MSFT, NVDA, AMZN, GOOGL, META) is an **exploratory historical result requiring out-of-sample validation**, not evidence that the strategy generally outperforms its benchmark.

The [research record](outputs/run_20260924_163918_e71aba_research_record.json) records `parameter_sets_tested = 1`, `out_of_sample_test = false`, and `historical_constituents_used = false`. The parameter count covers this invocation only, not the researcher's entire search history.

The [completed direct TypeSafe audit](outputs/run_20260924_163918_e71aba_jev_audit.json) returned `jev-1.13.0`:

| Assessment | Saved result |
|---|---|
| Design status | `exploratory_ready`, confidence 0.99 |
| Result label | Raw `requires_validation`; confidence 0.41, so no automated conclusion assigned |
| Overfitting risk | Numeric Score 0.97; derived label medium; medium-level probability 0.95, confidence 0.92 |
| Survivorship bias materiality | Probability 0.75 |
| Suggested next experiment | `out_of_sample_split`, probability 0.83, confidence 0.78 |

These are advisory model assessments of the supplied record, not independent validation, financial advice, or proof of future performance. Probabilities and confidence are distinct fields.

## Methodology

Trailing momentum is price today divided by price `lookback` trading days ago, minus one. On each completed calendar month's last available trading session, DriftLab ranks available signals and uses alphabetical ticker order to break ties. A decision made at that close affects returns only from the following session. A terminal decision without a following in-range session is not executed. Transaction cost is turnover multiplied by basis points divided by 10,000; the initial cash-to-portfolio allocation is charged.

`--start` is inclusive and `--end` is exclusive. DriftLab records data dates, allocation date, and performance-return dates separately. Annualized return includes entry costs in compounded performance but uses only subsequent market-return days as its period count. The allocation-close cost affects cumulative return and drawdown; that initialization row is excluded from volatility and Sharpe. Maximum drawdown starts from initial capital of 1.0.

DriftLab downloads yfinance with `auto_adjust=False` and requires `Adj Close`; it never substitutes raw `Close`. Every adjusted close must be finite and positive. It rejects both missing expected NYSE sessions and unexpected weekend, holiday, or non-session rows, and does not fill observations. The built-in calendar includes regular closures plus documented exceptional full-day closures through January 9, 2025; future exceptional closures require a calendar update.

The final valid universe is fixed before signals are calculated. DriftLab uses the common contiguous window for those tickers, so a ticker that appears only later can move the analysis start. If fewer than the requested holdings have a usable signal at a rebalance, it holds every eligible ticker at equal weight.

Strategy weights are constant targets between scheduled rebalances. This is an approximation: DriftLab does not trade to maintain those targets as prices drift, so it omits any maintenance turnover and costs.

The benchmark is **true equal-weight buy-and-hold**: equal capital is allocated once at the allocation date; positions then drift and are never rebalanced. This is deliberately different from applying constant equal weights each day, which would imply rebalancing. The benchmark has no modeled entry cost, so the comparison is net strategy performance against gross buy-and-hold performance.

## Installation

Python 3.11 or newer and `uv` are required for the commands below. From the repository directory in PowerShell, install the locked environment and test dependencies:

```powershell
uv sync --frozen --extra dev
```

## Running a Backtest

```powershell
uv run --frozen python -m driftlab run --tickers AAPL MSFT NVDA AMZN GOOGL META --start 2020-01-01 --end 2026-01-01 --lookback 126 --holdings 3 --rebalance monthly --cost-bps 10
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

Each run writes daily returns/equity/turnover CSV, a complete rebalance ledger CSV, compact factual research-record JSON, and a Markdown report **before** Jev is called. With `run --audit-with-jev`, successful audit JSON or a failure note is added and the report is updated when writing remains available. Quantitative CSVs and research-record JSON are not rewritten by the audit.

The standalone `audit` command writes only `<run_id>_jev_audit.json`; it does not refresh the original Markdown report. The saved report for the experiment above therefore still describes its earlier Vercel failure; the separate audit JSON records the later direct TypeSafe success. Historical artifacts are preserved.

Score/probability inconsistencies remain rejected at the existing `1e-6` absolute tolerance. The terminal rejection includes a narrow diagnostic with raw numeric tokens, parsed values, weighted expectation, difference, model, and available request ID; no credentials, headers, or research record are included. An earlier inconsistent live response is covered by an offline regression test.

## Understanding the Metrics

Annualized return converts the observed compounded result to a 252-trading-day rate. The allocation-close entry cost affects cumulative return and drawdown; volatility and Sharpe use only subsequent actual market-return observations. Sharpe ratio is return per unit of volatility assuming zero risk-free rate. Maximum drawdown is the deepest peak-to-trough equity decline.

## Why Jev Is Used

Jev classifies documented research-process limitations and suggests one next experiment. It never calculates, forecasts, chooses securities, changes parameters, or executes an action.

## Confidence Policy

Choice answers with confidence below 0.65 display as “Ambiguous — no automated conclusion assigned.” Score results retain their numeric 0–2 position, probabilities, and confidence; Score confidence below 0.65 requires caution. Noul is displayed as a probability without a forced binary conclusion.

`parameter_sets_tested` in the research record means configurations evaluated in this DriftLab invocation only. It does not establish the complete historical search performed by a researcher.

## Research Limitations

- The small, hand-selected current ticker universe creates selection and survivorship bias; historical constituents were not used.
- No out-of-sample validation has been performed for the saved experiment. Testing further variants on the same history can compound overfitting.
- Fixed basis-point costs simplify execution frictions. Constant target weights omit maintenance trading and its costs; benchmark entry is cost-free.
- yfinance coverage, adjustments, availability, and revisions limit data quality and reproducibility; repeating a download need not reproduce the same inputs.
- The calendar models regular holidays and an explicit list of extraordinary closures ending January 9, 2025. It is not an automatically updated exchange calendar; unlisted closures require review and a calendar update, not price filling.

Documentation caveat: the report template and existing reports still say extraordinary closures are unmodeled. That wording is stale; the explicit list in `data.py` is the implemented behavior. No production code or historical report was changed in this documentation pass.

## Development and Tests

```powershell
uv run --frozen pytest -q
uv run --frozen python -m driftlab --help
```

The current suite has 45 offline tests; no market downloads or Jev credentials are needed. SDK tests use mocked responses, including the observed inconsistent Score 0.97 with probabilities 0.03/0.96/0.01 and its consistent 0.98 counterpart. Passing software tests establishes implementation checks, not out-of-sample strategy validity.

## Next Research Step

Pre-specify an out-of-sample validation protocol before inspecting holdout results: freeze the universe, signal lookback, holdings count, costs, benchmark, date boundaries, warm-up treatment, and evaluation criteria. Use a development period for choices, then evaluate once on an untouched holdout. Already-inspected history cannot become independent validation merely by relabeling it.

The CLI does not currently automate a development/holdout split or record an out-of-sample test as completed. This is planned research work, not an existing validated result. Any later parameter, cost, or universe sensitivity studies should be specified separately and tracked; Jev never launches them.

## Disclaimer

DriftLab is educational software for historical research. It provides no investment advice.
