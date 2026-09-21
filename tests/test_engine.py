from datetime import date
import pandas as pd
import pytest

from driftlab.config import RunConfig
from driftlab.data import DataError
from driftlab.engine import run_backtest


def test_engine_builds_artifacts_and_is_causal(prices: pd.DataFrame) -> None:
    config = RunConfig.create(["AAA", "BBB", "CCC"], date(2024, 1, 1), date(2025, 1, 1), lookback=20, holdings=2)
    baseline = run_backtest(config, prices)
    assert {"strategy_gross_return", "strategy_net_return", "benchmark_return", "strategy_equity", "benchmark_equity", "turnover"} <= set(baseline.daily)
    assert {"run_id", "valid_tickers", "strategy_metrics", "benchmark_metrics", "turnover"} <= set(baseline.research_record())
    changed = prices.copy()
    changed.iloc[-1] *= 50
    altered = run_backtest(config, changed)
    pd.testing.assert_frame_equal(baseline.daily.iloc[:-1], altered.daily.iloc[:-1])


def test_engine_rejects_insufficient_data() -> None:
    config = RunConfig.create(["AAA", "BBB"], date(2024, 1, 1), date(2024, 2, 1), lookback=20, holdings=1)
    prices = pd.DataFrame({"AAA": [1, 2], "BBB": [1, 2]}, index=pd.bdate_range("2024-01-01", periods=2))
    with pytest.raises(DataError, match="Insufficient"):
        run_backtest(config, prices)
