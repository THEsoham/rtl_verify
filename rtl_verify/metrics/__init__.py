"""Metrics collection and cross-run comparison module.

Provides tools for querying and aggregating execution metrics, coverage statistics,
mutation scores, and generating side-by-side comparisons between runs and model configurations.
"""

from __future__ import annotations

from rtl_verify.metrics.collector import MetricsCollector
from rtl_verify.metrics.comparison import MetricsComparison
from rtl_verify.metrics.schemas import (
    ComparisonResult,
    ComparisonRow,
    IterationMetrics,
    RunSummary,
)

__all__ = [
    "ComparisonResult",
    "ComparisonRow",
    "IterationMetrics",
    "MetricsCollector",
    "MetricsComparison",
    "RunSummary",
]
