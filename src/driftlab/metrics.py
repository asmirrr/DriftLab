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
    return float((equity / equity.cummax() - 1.0).min())


def calculate_metrics(returns: pd.Series, turnover: pd.Series, rebalance_events: int,
                      valid_tickers: int) -> PerformanceMetrics:
    count = len(returns)
    equity = equity_curve(returns)
    cumulative = float(equity.iloc[-1] - 1.0) if count else float("nan")
    annualized = float((1.0 + cumulative) ** (252 / count) - 1.0) if count else float("nan")
    volatility = float(returns.std(ddof=1) * np.sqrt(252)) if count > 1 else float("nan")
    daily_std = returns.std(ddof=1)
    sharpe = float(returns.mean() / daily_std * np.sqrt(252)) if count > 1 and daily_std != 0 else float("nan")
    return PerformanceMetrics(cumulative, annualized, volatility, sharpe, maximum_drawdown(equity),
                              float(turnover.mean()) if count else float("nan"), float(turnover.sum()),
                              rebalance_events, count, valid_tickers)
