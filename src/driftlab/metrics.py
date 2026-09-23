"""Performance metrics with no rounding during calculation."""

from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PerformanceMetrics:
    cumulative_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    maximum_drawdown: float
    average_daily_turnover: float
    total_turnover: float
    rebalance_events: int
    investable_trading_days: int
    valid_tickers: int

    def json_dict(self) -> dict[str, float | int | None]:
        return {key: (None if isinstance(value, float) and not np.isfinite(value) else value)
                for key, value in asdict(self).items()}


def equity_curve(returns: pd.Series) -> pd.Series:
    return (1.0 + returns).cumprod()


def maximum_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return float("nan")
    with_initial_capital = pd.concat([pd.Series([1.0]), equity.reset_index(drop=True)], ignore_index=True)
    return float((with_initial_capital / with_initial_capital.cummax() - 1.0).min())


def calculate_metrics(returns: pd.Series, turnover: pd.Series, rebalance_events: int,
                      valid_tickers: int, annualization_days: int | None = None) -> PerformanceMetrics:
    count = len(returns)
    equity = equity_curve(returns)
    cumulative = float(equity.iloc[-1] - 1.0) if count else float("nan")
    periods = count if annualization_days is None else annualization_days
    annualized = float((1.0 + cumulative) ** (252 / periods) - 1.0) if periods and cumulative > -1 else float("nan")
    volatility = float(returns.std(ddof=1) * np.sqrt(252)) if count > 1 else float("nan")
    daily_std = returns.std(ddof=1)
    sharpe = float(returns.mean() / daily_std * np.sqrt(252)) if count > 1 and daily_std != 0 else float("nan")
    return PerformanceMetrics(cumulative, annualized, volatility, sharpe, maximum_drawdown(equity),
                              float(turnover.mean()) if count else float("nan"), float(turnover.sum()),
                              rebalance_events, periods, valid_tickers)
