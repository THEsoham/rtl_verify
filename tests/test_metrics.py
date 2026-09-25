from __future__ import annotations

import pytest
from rtl_verify.metrics.schemas import IterationMetrics, RunSummary, ComparisonRow


class TestMetricSchemas:
    def test_iteration_metrics_creation(self):
        m = IterationMetrics(
            iteration_num=1,
            status="sim_pass",
            sim_passed=True,
            designer_time_ms=1500,
            line_coverage=85.0,
        )
        assert m.iteration_num == 1
        assert m.sim_passed is True

    def test_run_summary_creation(self):
        s = RunSummary(
            run_id=1,
            benchmark_name="ALU",
            designer_model="qwen:7b",
            verifier_model="qwen:7b",
            status="passed",
            total_iterations=3,
            total_time_seconds=45.2,
        )
        assert s.run_id == 1
        assert s.status == "passed"

    def test_comparison_row(self):
        row = ComparisonRow(
            metric_name="Line Coverage",
            values={1: 85.0, 2: 92.0, 3: None},
        )
        assert row.values[1] == 85.0
        assert row.values[3] is None
