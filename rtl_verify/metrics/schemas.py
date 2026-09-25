"""Pydantic models for metric data transfer and reporting."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IterationMetrics(BaseModel):
    """Metrics captured for a single design-verify iteration."""

    model_config = ConfigDict(from_attributes=True)

    iteration_num: int = Field(..., description="Iteration number (1-based)")
    status: str = Field(..., description="Status string of the iteration outcome")
    sim_passed: bool = Field(default=False, description="Whether simulation passed")
    designer_time_ms: int | None = Field(default=None, description="Time spent by designer model in ms")
    verifier_time_ms: int | None = Field(default=None, description="Time spent by verifier model in ms")
    sim_time_ms: int | None = Field(default=None, description="Time spent in simulation execution in ms")
    line_coverage: float | None = Field(default=None, description="Line coverage percentage (0-100)")
    branch_coverage: float | None = Field(default=None, description="Branch coverage percentage (0-100)")
    mutation_score: float | None = Field(default=None, description="Mutation score percentage (0-100)")


class RunSummary(BaseModel):
    """High-level summary of a pipeline run execution."""

    model_config = ConfigDict(from_attributes=True)

    run_id: int = Field(..., description="Unique database identifier for the run")
    benchmark_name: str = Field(..., description="Name of the benchmark executed")
    designer_model: str = Field(..., description="LLM model identifier used for RTL design")
    verifier_model: str = Field(..., description="LLM model identifier used for verification")
    status: str = Field(..., description="Final status of the run (e.g. passed, failed, running)")
    total_iterations: int = Field(default=0, description="Total number of iterations executed")
    total_time_seconds: float | None = Field(default=None, description="Total elapsed time in seconds")
    final_line_coverage: float | None = Field(default=None, description="Final line coverage percentage")
    final_branch_coverage: float | None = Field(default=None, description="Final branch coverage percentage")
    final_mutation_score: float | None = Field(default=None, description="Final mutation score percentage")
    started_at: datetime | None = Field(default=None, description="Timestamp when the run started")
    finished_at: datetime | None = Field(default=None, description="Timestamp when the run finished")


class ComparisonRow(BaseModel):
    """One row in a side-by-side comparison table."""

    model_config = ConfigDict(from_attributes=True)

    metric_name: str = Field(..., description="Display label for the metric")
    values: dict[int | str, float | str | None] = Field(
        default_factory=dict,
        description="Map from column key (run_id or model configuration name) to metric value",
    )


class ComparisonResult(BaseModel):
    """Aggregated comparison report containing run summaries and side-by-side metrics."""

    model_config = ConfigDict(from_attributes=True)

    run_summaries: list[RunSummary] = Field(
        default_factory=list,
        description="List of individual run summaries participating in the comparison",
    )
    comparison_table: list[ComparisonRow] = Field(
        default_factory=list,
        description="Structured rows for rendering comparison tables",
    )
