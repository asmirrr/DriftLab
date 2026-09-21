import math
import pandas as pd
from driftlab.portfolio import build_portfolio, select_weights, true_buy_and_hold_returns


def test_selection_weights_and_tie_break() -> None:
    weights = select_weights(pd.Series({"BBB": 0.2, "AAA": 0.2, "CCC": 0.1}), 2)
    assert weights.to_dict() == {"BBB": 0.5, "AAA": 0.5, "CCC": 0.0}
    assert weights.sum() == 1.0


def test_new_selection_has_next_day_effect_and_cost_on_rebalance() -> None:
    index = pd.bdate_range("2024-01-01", periods=4)
    prices = pd.DataFrame({"AAA": [100, 100, 110, 121], "BBB": [100, 100, 100, 100]}, index=index)
    signals = pd.DataFrame({"AAA": [float("nan"), 1, 1, 1], "BBB": [float("nan"), 0, 0, 0]}, index=index)
    result = build_portfolio(prices, signals, pd.DatetimeIndex([index[1]]), 1, 10)
    assert result.turnover.loc[index[1]] == 1.0
    assert result.net_returns.loc[index[1]] == -0.001
    assert result.gross_returns.loc[index[1]] == 0.0
    assert math.isclose(result.gross_returns.loc[index[2]], 0.1)
    assert result.turnover.drop(index[1]).sum() == 0


def test_true_buy_and_hold_drifts() -> None:
    index = pd.bdate_range("2024-01-01", periods=3)
    prices = pd.DataFrame({"AAA": [100, 200, 200], "BBB": [100, 100, 100]}, index=index)
    returns = true_buy_and_hold_returns(prices, index[0])
    assert math.isclose(returns.iloc[1], 0.5)
