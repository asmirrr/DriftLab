"""Backtest orchestration, independent of any AI audit."""

from dataclasses import dataclass
from datetime import date
from uuid import uuid4
import pandas as pd

from .config import RunConfig
from .data import DataError, PriceData, clean_prices
from .metrics import PerformanceMetrics, calculate_metrics, equity_curve
from .portfolio import PortfolioResult, build_portfolio, true_buy_and_hold_returns
from .signals import month_end_dates, trailing_momentum

RESEARCH_QUESTION = ("Among a user-supplied basket of liquid U.S. stocks, does a monthly-rebalanced, "
                     "equal-weighted portfolio that holds the top N stocks by trailing momentum outperform "
                     "an equal-weighted buy-and-hold portfolio of the same tickers after modeled transaction costs?")


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    config: RunConfig
    price_data: PriceData
    portfolio: PortfolioResult
    benchmark_returns: pd.Series
    strategy_metrics: PerformanceMetrics
    benchmark_metrics: PerformanceMetrics
    daily: pd.DataFrame

    def research_record(self) -> dict[str, object]:
        prices = self.price_data.prices
        return {"run_id": self.run_id, "research_question": RESEARCH_QUESTION,
                "requested_tickers": list(self.config.tickers), "valid_tickers": list(self.price_data.valid_tickers),
                "excluded_tickers": list(self.price_data.excluded_tickers), "data_source": "yfinance",
                "requested_start": self.config.start.isoformat(), "requested_end": self.config.end.isoformat(),
                "actual_start": prices.index[0].date().isoformat(), "actual_end": prices.index[-1].date().isoformat(),
                "strategy": {"name": "Top-N Trailing Momentum", "lookback_trading_days": self.config.lookback,
                             "holdings": self.config.holdings, "rebalance_frequency": "monthly",
                             "cost_bps": self.config.cost_bps, "long_only": True,
                             "weighting": "equal_weighted_target_weights"},
                "research_process": {"parameter_sets_tested": 1, "out_of_sample_test": False,
                                     "historical_constituents_used": False, "data_notes": list(self.price_data.notes) + [
                                         "Benchmark is true equal-weight buy-and-hold: capital is allocated once and holdings drift without rebalancing.",
                                         "Strategy target weights selected at month-end affect returns from the next trading day."]},
                "strategy_metrics": self.strategy_metrics.json_dict(), "benchmark_metrics": self.benchmark_metrics.json_dict(),
                "turnover": {"average_daily_turnover": self.strategy_metrics.average_daily_turnover,
                             "total_turnover": self.strategy_metrics.total_turnover,
                             "rebalance_events": self.strategy_metrics.rebalance_events}}


def run_backtest(config: RunConfig, source_prices: pd.DataFrame) -> BacktestResult:
    data = clean_prices(source_prices, config.tickers)
    prices = data.prices
    if len(prices) <= config.lookback:
        raise DataError(f"Insufficient common observations: need more than {config.lookback} trading days.")
    signals = trailing_momentum(prices, config.lookback)
    portfolio = build_portfolio(prices, signals, month_end_dates(prices.index), config.holdings, config.cost_bps)
    rebalance_costs = portfolio.turnover > 0
    if not rebalance_costs.any():
        raise DataError("No valid month-end allocation was available after the lookback period.")
    start = rebalance_costs[rebalance_costs].index[0]
    # Comparison begins at allocation close: strategy entry cost is retained;
    # both series have zero market return that day and begin market exposure next day.
    strategy_net = portfolio.net_returns.loc[start:]
    benchmark = true_buy_and_hold_returns(prices, start).loc[start:]
    turnover = portfolio.turnover.loc[start:]
    daily = pd.DataFrame({"strategy_gross_return": portfolio.gross_returns.loc[start:], "strategy_net_return": strategy_net,
                          "benchmark_return": benchmark, "turnover": turnover})
    daily["strategy_equity"] = equity_curve(daily["strategy_net_return"])
    daily["benchmark_equity"] = equity_curve(daily["benchmark_return"])
    daily.index.name = "date"
    event_count = int((portfolio.turnover.loc[start:] > 0).sum())
    return BacktestResult("run_" + pd.Timestamp.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:6], config, data,
                          portfolio, benchmark, calculate_metrics(strategy_net, turnover, event_count, len(data.valid_tickers)),
                          calculate_metrics(benchmark, pd.Series(0.0, index=benchmark.index), 0, len(data.valid_tickers)), daily)
