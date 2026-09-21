import math
import pandas as pd
from driftlab.signals import trailing_momentum


def test_trailing_momentum_is_known_and_no_future_data() -> None:
    prices = pd.DataFrame({"AAA": [100, 110, 121, 133.1]}, index=pd.bdate_range("2024-01-01", periods=4))
    result = trailing_momentum(prices, 2)
    assert result.iloc[0, 0] != result.iloc[0, 0]
    assert math.isclose(result.iloc[2, 0], 0.21)
    changed = prices.copy()
    changed.iloc[-1] = 10000
    assert trailing_momentum(changed, 2).iloc[2, 0] == result.iloc[2, 0]
