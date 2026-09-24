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


def test_december_2021_later_session_removal_rejects_instead_of_moving_rebalance() -> None:
    from driftlab.data import expected_sessions
    index = expected_sessions(pd.Timestamp("2021-10-01"), pd.Timestamp("2022-01-04"))
    prices = pd.DataFrame({"AAA": 100.0, "BBB": 90.0}, index=index)
    prices.loc["2021-12-29":, "BBB"] = 150.0
    config = RunConfig.create(["AAA", "BBB"], date(2021, 10, 1), date(2022, 1, 4), lookback=5, holdings=1)
    complete = run_backtest(config, prices)
    assert pd.Timestamp("2021-12-31") in set(complete.portfolio.rebalances["rebalance_date"])
    with pytest.raises(DataError, match="Missing expected NYSE"):
        run_backtest(config, prices.drop(pd.Timestamp("2021-12-31")))


def test_future_window_removal_rejects_instead_of_rewriting_history(prices: pd.DataFrame) -> None:
    config = RunConfig.create(["AAA", "BBB", "CCC"], date(2024, 1, 2), date(2024, 5, 20), lookback=20, holdings=2)
    with pytest.raises(DataError, match="Missing expected NYSE"):
        run_backtest(config, prices.drop(prices.loc["2024-03-28":"2024-04-03"].index))


def test_extreme_finite_cost_rejects_nonpositive_equity(prices: pd.DataFrame) -> None:
    config = RunConfig.create(["AAA", "BBB", "CCC"], date(2024, 1, 2), date(2024, 5, 20), lookback=20, holdings=2, cost_bps=10_000)
    with pytest.raises(DataError, match="nonpositive portfolio equity"):
        run_backtest(config, prices)


def test_unavailable_ticker_is_excluded_and_reduced_holdings_are_equal_weighted(prices: pd.DataFrame) -> None:
    supplied = prices.copy()
    supplied["CCC"] = float("nan")
    config = RunConfig.create(["AAA", "BBB", "CCC"], date(2024, 1, 2), date(2024, 5, 20), lookback=20, holdings=3)
    result = run_backtest(config, supplied)
    assert result.price_data.excluded_tickers == ("CCC",)
    weights = result.portfolio.target_weights.loc[result.allocation_date]
    assert weights.to_dict() == {"AAA": .5, "BBB": .5}


def test_rebalance_events_come_from_ledger_even_when_later_turnover_is_zero(prices: pd.DataFrame) -> None:
    config = RunConfig.create(["AAA", "BBB", "CCC"], date(2024, 1, 2), date(2024, 5, 20), lookback=20, holdings=1)
    result = run_backtest(config, prices)
    ledger_events = result.portfolio.rebalances["rebalance_date"].nunique()
    positive_turnover_events = int((result.daily["turnover"] > 0).sum())
    assert result.strategy_metrics.rebalance_events == ledger_events
    assert ledger_events > positive_turnover_events
