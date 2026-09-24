from datetime import date
import pandas as pd
import pytest

from driftlab.config import RunConfig
from driftlab.data import DataError
from driftlab.engine import run_backtest


def test_engine_builds_artifacts_and_is_causal(prices: pd.DataFrame) -> None:
    config = RunConfig.create(["AAA", "BBB", "CCC"], date(2024, 1, 2), date(2024, 5, 20), lookback=20, holdings=2)
    baseline = run_backtest(config, prices)
    assert {"strategy_gross_return", "strategy_net_return", "benchmark_return", "strategy_equity", "benchmark_equity", "turnover"} <= set(baseline.daily)
    assert {"run_id", "valid_tickers", "strategy_metrics", "benchmark_metrics", "turnover"} <= set(baseline.research_record())
    changed = prices.copy()
    changed.iloc[-1] *= 50
    altered = run_backtest(config, changed)
    pd.testing.assert_frame_equal(baseline.daily.iloc[:-1], altered.daily.iloc[:-1])
    pd.testing.assert_frame_equal(baseline.portfolio.target_weights.iloc[:-1], altered.portfolio.target_weights.iloc[:-1])
    pd.testing.assert_frame_equal(baseline.portfolio.held_weights.iloc[:-1], altered.portfolio.held_weights.iloc[:-1])
    pd.testing.assert_series_equal(baseline.portfolio.turnover.iloc[:-1], altered.portfolio.turnover.iloc[:-1])
    pd.testing.assert_frame_equal(baseline.portfolio.rebalances.iloc[:-len(baseline.price_data.valid_tickers)], altered.portfolio.rebalances.iloc[:-len(altered.price_data.valid_tickers)])


def test_engine_rejects_insufficient_data() -> None:
    config = RunConfig.create(["AAA", "BBB"], date(2024, 1, 2), date(2024, 1, 4), lookback=20, holdings=1)
    prices = pd.DataFrame({"AAA": [1, 2], "BBB": [1, 2]}, index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"]))
    with pytest.raises(DataError, match="Insufficient"):
        run_backtest(config, prices)


def test_configured_end_makes_terminal_month_and_extension_invariant(prices: pd.DataFrame) -> None:
    config = RunConfig.create(["AAA", "BBB", "CCC"], date(2024, 1, 2), date(2024, 5, 20), lookback=20, holdings=2)
    baseline = run_backtest(config, prices)
    extension_dates = pd.bdate_range("2024-05-20", periods=10)
    extended = pd.concat([prices, pd.DataFrame({column: prices.iloc[-1][column] * (1 + .01 * pd.RangeIndex(len(extension_dates))) for column in prices.columns}, index=extension_dates)])
    altered = run_backtest(config, extended)
    pd.testing.assert_frame_equal(baseline.daily, altered.daily, check_freq=False)
    pd.testing.assert_frame_equal(baseline.portfolio.rebalances, altered.portfolio.rebalances)
