import math
import pandas as pd
from driftlab.metrics import calculate_metrics, equity_curve


def test_metrics_and_equity_curve() -> None:
    returns = pd.Series([0.1, -0.1])
    turnover = pd.Series([0.0, 0.0])
    metric = calculate_metrics(returns, turnover, 0, 2)
    assert equity_curve(returns).tolist() == [1.1, 0.9900000000000001]
    assert math.isclose(metric.cumulative_return, -0.01)
    assert math.isclose(metric.maximum_drawdown, -0.1)


def test_zero_volatility_sharpe_is_nan() -> None:
    metric = calculate_metrics(pd.Series([0.0, 0.0]), pd.Series([0.0, 0.0]), 0, 2)
    assert math.isnan(metric.sharpe_ratio)


def test_risk_metrics_exclude_synthetic_initialization_return() -> None:
    stored = pd.Series([0.0, 0.125, 0.125])
    metric = calculate_metrics(stored, pd.Series([0.0, 0.0, 0.0]), 0, 2,
                               annualization_days=2, risk_returns=stored.iloc[1:])
    assert metric.annualized_volatility == 0.0
    assert math.isnan(metric.sharpe_ratio)
