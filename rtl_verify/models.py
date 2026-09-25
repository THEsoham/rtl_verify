"""SQLAlchemy ORM models for persisting runs, iterations, and metrics."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Boolean,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# ── Enums ───────────────────────────────────────────────────────────────────────


class RunStatus(str, enum.Enum):
    """Status of a pipeline run."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ITERATION_LIMIT = "iteration_limit"
    ERROR = "error"


class IterationStatus(str, enum.Enum):
    """Outcome of a single design-verify iteration."""

    COMPILE_FAIL_RTL = "compile_fail_rtl"
    COMPILE_FAIL_TB = "compile_fail_tb"
    SIM_FAIL = "sim_fail"
    SIM_PASS = "sim_pass"
    ERROR = "error"


# ── Models ──────────────────────────────────────────────────────────────────────


class Benchmark(Base):
    """A hardware specification benchmark."""

    __tablename__ = "benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False)
    category = Column(String(64), nullable=False)  # combinational, sequential
    difficulty = Column(String(32), nullable=False)  # easy, medium, hard
    description = Column(Text, nullable=False)
    spec_yaml = Column(Text, nullable=False)  # Full YAML spec content

    runs = relationship("Run", back_populates="benchmark", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Benchmark {self.name!r} ({self.difficulty})>"


class Run(Base):
    """A complete pipeline execution for a benchmark."""

    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    benchmark_id = Column(Integer, ForeignKey("benchmarks.id"), nullable=False)
    designer_model = Column(String(128), nullable=False)
    verifier_model = Column(String(128), nullable=False)
    config_json = Column(Text, nullable=True)  # JSON-serialized RunConfig
    status = Column(Enum(RunStatus), default=RunStatus.PENDING, nullable=False)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    total_iterations = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    benchmark = relationship("Benchmark", back_populates="runs")
    iterations = relationship(
        "Iteration", back_populates="run", cascade="all, delete-orphan",
        order_by="Iteration.iteration_num",
    )
    metrics = relationship("RunMetric", back_populates="run", uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Run #{self.id} [{self.status.value}] on {self.benchmark_id}>"


class Iteration(Base):
    """A single design → verify → evaluate cycle within a run."""

    __tablename__ = "iterations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    iteration_num = Column(Integer, nullable=False)
    status = Column(Enum(IterationStatus), nullable=False)

    # Artifacts — stored as text (source code / log output)
    rtl_source = Column(Text, nullable=True)
    testbench_source = Column(Text, nullable=True)
    compile_stdout = Column(Text, nullable=True)
    compile_stderr = Column(Text, nullable=True)
    sim_stdout = Column(Text, nullable=True)
    sim_stderr = Column(Text, nullable=True)
    sim_passed = Column(Boolean, default=False)

    # Feedback sent to the Designer for the next iteration
    feedback = Column(Text, nullable=True)

    # Timing
    designer_time_ms = Column(Integer, nullable=True)
    verifier_time_ms = Column(Integer, nullable=True)
    sim_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    run = relationship("Run", back_populates="iterations")
    coverage = relationship(
        "CoverageReport", back_populates="iteration", uselist=False, cascade="all, delete-orphan"
    )
    mutation_result = relationship(
        "MutationResult", back_populates="iteration", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Iteration {self.iteration_num} [{self.status.value}] of Run {self.run_id}>"


class CoverageReport(Base):
    """Coverage data collected from a single iteration."""

    __tablename__ = "coverage_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    iteration_id = Column(Integer, ForeignKey("iterations.id"), unique=True, nullable=False)

    line_coverage = Column(Float, nullable=True)      # percentage
    branch_coverage = Column(Float, nullable=True)
    toggle_coverage = Column(Float, nullable=True)
    functional_coverage = Column(Float, nullable=True)

    # Raw Verilator coverage data (JSON or text)
    raw_data = Column(Text, nullable=True)

    iteration = relationship("Iteration", back_populates="coverage")

    def __repr__(self) -> str:
        return f"<Coverage line={self.line_coverage}% branch={self.branch_coverage}%>"


class MutationResult(Base):
    """Mutation testing results for a single iteration."""

    __tablename__ = "mutation_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    iteration_id = Column(Integer, ForeignKey("iterations.id"), unique=True, nullable=False)

    total_mutants = Column(Integer, default=0)
    killed = Column(Integer, default=0)
    survived = Column(Integer, default=0)
    timeout = Column(Integer, default=0)
    error = Column(Integer, default=0)
    mutation_score = Column(Float, nullable=True)  # killed / (total - error) * 100

    # Details: JSON list of {mutation_type, location, status}
    details_json = Column(Text, nullable=True)

    iteration = relationship("Iteration", back_populates="mutation_result")

    def __repr__(self) -> str:
        return f"<MutationResult score={self.mutation_score}% ({self.killed}/{self.total_mutants})>"


class RunMetric(Base):
    """Aggregated run-level metrics for cross-run comparison."""

    __tablename__ = "run_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("runs.id"), unique=True, nullable=False)

    total_iterations = Column(Integer, default=0)
    final_status = Column(String(32), nullable=True)
    total_time_seconds = Column(Float, nullable=True)
    compilation_success_rate = Column(Float, nullable=True)  # % of iterations that compiled
    final_line_coverage = Column(Float, nullable=True)
    final_branch_coverage = Column(Float, nullable=True)
    final_mutation_score = Column(Float, nullable=True)
    designer_total_tokens = Column(Integer, nullable=True)
    verifier_total_tokens = Column(Integer, nullable=True)

    run = relationship("Run", back_populates="metrics")

    def __repr__(self) -> str:
        return f"<RunMetric run={self.run_id} status={self.final_status}>"
