import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def prices() -> pd.DataFrame:
    index = pd.bdate_range("2024-01-01", periods=95)
    return pd.DataFrame({"AAA": 100 + np.arange(95) * 1.2, "BBB": 100 + np.arange(95) * 0.6,
                         "CCC": 100 + np.arange(95) * 0.2}, index=index)
