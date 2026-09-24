from datetime import date

import pandas as pd
import pytest

from driftlab.config import RunConfig
from driftlab.engine import run_backtest
from driftlab.reporting import update_jev_artifacts, write_baseline_artifacts


def _result(prices):
    return run_backtest(RunConfig.create(["AAA", "BBB", "CCC"], date(2024, 1, 2), date(2024, 5, 20), 20, 2), prices)


def test_baseline_artifacts_exist_before_jev_failure(prices, tmp_path, monkeypatch) -> None:
    result = _result(prices)
    paths = write_baseline_artifacts(result, tmp_path)
    before = {name: path.read_bytes() for name, path in paths.items()}
    import driftlab.reporting as reporting
    monkeypatch.setattr(reporting, "render_report", lambda *args: (_ for _ in ()).throw(RuntimeError("report failure")))
    with pytest.raises(RuntimeError, match="report failure"):
        update_jev_artifacts(result, paths, {"answers": {}})
    assert {name: path.read_bytes() for name, path in paths.items()} == before


def test_report_documents_target_weight_and_benchmark_cost_conventions(prices, tmp_path) -> None:
    paths = write_baseline_artifacts(_result(prices), tmp_path)
    report = paths["report"].read_text(encoding="utf-8")
    assert "constant-target-weight approximation" in report
    assert "benchmark has no modeled entry cost" in report
    assert "end exclusive" in report
