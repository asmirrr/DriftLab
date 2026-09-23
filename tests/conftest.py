import numpy as np
import pandas as pd
import pytest
from driftlab.data import expected_sessions


@pytest.fixture
def prices() -> pd.DataFrame:
    index = expected_sessions(pd.Timestamp("2024-01-02"), pd.Timestamp("2024-05-20"))
    count = len(index)
    return pd.DataFrame({"AAA": 100 + np.arange(count) * 1.2, "BBB": 100 + np.arange(count) * 0.6,
                         "CCC": 100 + np.arange(count) * 0.2}, index=index)
