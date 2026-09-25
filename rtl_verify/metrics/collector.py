"""Metrics collection and database aggregation service."""

from __future__ import annotations

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from rtl_verify.metrics.schemas import IterationMetrics, RunSummary
from rtl_verify.models import (
    Benchmark,
    CoverageReport,
    Iteration,
    IterationStatus,
    MutationResult,
    Run,
    RunMetric,
)

log = structlog.get_logger()


class MetricsCollector:
    """Queries and aggregates verification metrics from ORM database models."""

    async def get_run_summary(self, session: AsyncSession, run_id: int) -> RunSummary:
        """Fetch a complete RunSummary for a specific run ID.

        Joins Run with Benchmark and RunMetric, computing fallback metrics
        from individual iterations if aggregated RunMetric is not present.

        Raises:
            ValueError: If the run with the given ID does not exist.
        """
        stmt = (
            select(Run, Benchmark.name.label("benchmark_name"), RunMetric)
            .outerjoin(Benchmark, Run.benchmark_id == Benchmark.id)
            .outerjoin(RunMetric, Run.id == RunMetric.run_id)
            .where(Run.id == run_id)
        )
        result = await session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            log.warning("run_summary_not_found", run_id=run_id)
            raise ValueError(f"Run #{run_id} not found")

        run, benchmark_name, run_metric = row
        return await self._build_run_summary(session, run, benchmark_name, run_metric)

    async def get_iteration_metrics(
        self, session: AsyncSession, run_id: int
    ) -> list[IterationMetrics]:
        """Fetch all iteration metrics for a run, ordered by iteration number ascending.

        Left-joins Iterations with CoverageReport and MutationResult.
        """
        stmt = (
            select(
                Iteration.iteration_num,
                Iteration.status,
                Iteration.sim_passed,
                Iteration.designer_time_ms,
                Iteration.verifier_time_ms,
                Iteration.sim_time_ms,
                CoverageReport.line_coverage,
                CoverageReport.branch_coverage,
                MutationResult.mutation_score,
            )
            .outerjoin(CoverageReport, Iteration.id == CoverageReport.iteration_id)
            .outerjoin(MutationResult, Iteration.id == MutationResult.iteration_id)
            .where(Iteration.run_id == run_id)
            .order_by(Iteration.iteration_num.asc())
        )
        result = await session.execute(stmt)
        rows = result.all()

        return [
            IterationMetrics(
                iteration_num=row.iteration_num,
                status=row.status.value if hasattr(row.status, "value") else str(row.status),
                sim_passed=bool(row.sim_passed),
                designer_time_ms=row.designer_time_ms,
                verifier_time_ms=row.verifier_time_ms,
                sim_time_ms=row.sim_time_ms,
                line_coverage=row.line_coverage,
                branch_coverage=row.branch_coverage,
                mutation_score=row.mutation_score,
            )
            for row in rows
        ]

    async def get_all_runs(
        self, session: AsyncSession, benchmark_id: int | None = None
    ) -> list[RunSummary]:
        """Fetch summaries for all runs, optionally filtered by benchmark ID.

        Results are ordered by started_at descending.
        """
        stmt = (
            select(Run, Benchmark.name.label("benchmark_name"), RunMetric)
            .outerjoin(Benchmark, Run.benchmark_id == Benchmark.id)
            .outerjoin(RunMetric, Run.id == RunMetric.run_id)
        )
        if benchmark_id is not None:
            stmt = stmt.where(Run.benchmark_id == benchmark_id)

        stmt = stmt.order_by(desc(Run.started_at), desc(Run.id))
        result = await session.execute(stmt)
        rows = result.all()

        summaries: list[RunSummary] = []
        for run, benchmark_name, run_metric in rows:
            summaries.append(self._build_run_summary_fast(run, benchmark_name, run_metric))

        return summaries

    async def get_recent_runs(
        self, session: AsyncSession, limit: int = 10
    ) -> list[RunSummary]:
        """Fetch summaries for the most recent N runs, ordered by started_at descending."""
        stmt = (
            select(Run, Benchmark.name.label("benchmark_name"), RunMetric)
            .outerjoin(Benchmark, Run.benchmark_id == Benchmark.id)
            .outerjoin(RunMetric, Run.id == RunMetric.run_id)
            .order_by(desc(Run.started_at), desc(Run.id))
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = result.all()

        summaries: list[RunSummary] = []
        for run, benchmark_name, run_metric in rows:
            summaries.append(self._build_run_summary_fast(run, benchmark_name, run_metric))

        return summaries

    async def calculate_and_save_run_metrics(
        self, session: AsyncSession, run_id: int
    ) -> RunMetric | None:
        """Compute aggregated metrics from iterations and persist or update the RunMetric record."""
        run_stmt = select(Run).where(Run.id == run_id)
        run_res = await session.execute(run_stmt)
        run = run_res.scalar_one_or_none()
        if not run:
            log.warning("run_not_found_for_metric_calc", run_id=run_id)
            return None

        iter_stmt = (
            select(Iteration)
            .where(Iteration.run_id == run_id)
            .order_by(Iteration.iteration_num.asc())
        )
        iter_res = await session.execute(iter_stmt)
        iterations = list(iter_res.scalars().all())

        total_iterations = len(iterations) if iterations else (run.total_iterations or 0)
        final_status = run.status.value if hasattr(run.status, "value") else str(run.status)

        total_time_seconds: float | None = None
        if run.started_at and run.finished_at:
            total_time_seconds = round((run.finished_at - run.started_at).total_seconds(), 2)

        compilation_success_rate: float | None = None
        if total_iterations > 0:
            compiled_count = sum(
                1
                for it in iterations
                if it.status not in (
                    IterationStatus.COMPILE_FAIL_RTL,
                    IterationStatus.COMPILE_FAIL_TB,
                    IterationStatus.ERROR,
                )
            )
            compilation_success_rate = round((compiled_count / total_iterations) * 100.0, 2)

        final_line_coverage: float | None = None
        final_branch_coverage: float | None = None
        final_mutation_score: float | None = None

        cov_stmt = (
            select(CoverageReport)
            .join(Iteration, CoverageReport.iteration_id == Iteration.id)
            .where(Iteration.run_id == run_id)
            .order_by(desc(Iteration.iteration_num))
            .limit(1)
        )
        cov_res = await session.execute(cov_stmt)
        latest_cov = cov_res.scalar_one_or_none()
        if latest_cov:
            final_line_coverage = latest_cov.line_coverage
            final_branch_coverage = latest_cov.branch_coverage

        mut_stmt = (
            select(MutationResult)
            .join(Iteration, MutationResult.iteration_id == Iteration.id)
            .where(Iteration.run_id == run_id)
            .order_by(desc(Iteration.iteration_num))
            .limit(1)
        )
        mut_res = await session.execute(mut_stmt)
        latest_mut = mut_res.scalar_one_or_none()
        if latest_mut:
            final_mutation_score = latest_mut.mutation_score

        metric_stmt = select(RunMetric).where(RunMetric.run_id == run_id)
        metric_res = await session.execute(metric_stmt)
        metric = metric_res.scalar_one_or_none()

        if metric is None:
            metric = RunMetric(
                run_id=run_id,
                total_iterations=total_iterations,
                final_status=final_status,
                total_time_seconds=total_time_seconds,
                compilation_success_rate=compilation_success_rate,
                final_line_coverage=final_line_coverage,
                final_branch_coverage=final_branch_coverage,
                final_mutation_score=final_mutation_score,
            )
            session.add(metric)
        else:
            metric.total_iterations = total_iterations
            metric.final_status = final_status
            metric.total_time_seconds = total_time_seconds
            metric.compilation_success_rate = compilation_success_rate
            metric.final_line_coverage = final_line_coverage
            metric.final_branch_coverage = final_branch_coverage
            metric.final_mutation_score = final_mutation_score

        await session.flush()
        return metric

    async def _build_run_summary(
        self,
        session: AsyncSession,
        run: Run,
        benchmark_name: str | None,
        run_metric: RunMetric | None,
    ) -> RunSummary:
        """Construct a RunSummary with database fallback if RunMetric is incomplete."""
        status_str = run.status.value if hasattr(run.status, "value") else str(run.status)

        total_time: float | None = None
        if run_metric and run_metric.total_time_seconds is not None:
            total_time = run_metric.total_time_seconds
        elif run.started_at and run.finished_at:
            total_time = round((run.finished_at - run.started_at).total_seconds(), 2)

        total_iters = (
            run_metric.total_iterations
            if (run_metric and run_metric.total_iterations is not None)
            else (run.total_iterations or 0)
        )

        final_line_cov = run_metric.final_line_coverage if run_metric else None
        final_branch_cov = run_metric.final_branch_coverage if run_metric else None
        final_mut_score = run_metric.final_mutation_score if run_metric else None

        # Fallback queries if coverage or mutation score not recorded on RunMetric
        if final_line_cov is None or final_branch_cov is None:
            cov_stmt = (
                select(CoverageReport.line_coverage, CoverageReport.branch_coverage)
                .join(Iteration, CoverageReport.iteration_id == Iteration.id)
                .where(Iteration.run_id == run.id)
                .order_by(desc(Iteration.iteration_num))
                .limit(1)
            )
            cov_res = await session.execute(cov_stmt)
            latest_cov = cov_res.one_or_none()
            if latest_cov:
                if final_line_cov is None:
                    final_line_cov = latest_cov.line_coverage
                if final_branch_cov is None:
                    final_branch_cov = latest_cov.branch_coverage

        if final_mut_score is None:
            mut_stmt = (
                select(MutationResult.mutation_score)
                .join(Iteration, MutationResult.iteration_id == Iteration.id)
                .where(Iteration.run_id == run.id)
                .order_by(desc(Iteration.iteration_num))
                .limit(1)
            )
            mut_res = await session.execute(mut_stmt)
            latest_mut = mut_res.one_or_none()
            if latest_mut:
                final_mut_score = latest_mut.mutation_score

        return RunSummary(
            run_id=run.id,
            benchmark_name=benchmark_name or f"Benchmark #{run.benchmark_id}",
            designer_model=run.designer_model,
            verifier_model=run.verifier_model,
            status=status_str,
            total_iterations=total_iters,
            total_time_seconds=total_time,
            final_line_coverage=final_line_cov,
            final_branch_coverage=final_branch_cov,
            final_mutation_score=final_mut_score,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )

    def _build_run_summary_fast(
        self,
        run: Run,
        benchmark_name: str | None,
        run_metric: RunMetric | None,
    ) -> RunSummary:
        """Construct a RunSummary synchronously from pre-joined models."""
        status_str = run.status.value if hasattr(run.status, "value") else str(run.status)

        total_time: float | None = None
        if run_metric and run_metric.total_time_seconds is not None:
            total_time = run_metric.total_time_seconds
        elif run.started_at and run.finished_at:
            total_time = round((run.finished_at - run.started_at).total_seconds(), 2)

        total_iters = (
            run_metric.total_iterations
            if (run_metric and run_metric.total_iterations is not None)
            else (run.total_iterations or 0)
        )

        return RunSummary(
            run_id=run.id,
            benchmark_name=benchmark_name or f"Benchmark #{run.benchmark_id}",
            designer_model=run.designer_model,
            verifier_model=run.verifier_model,
            status=status_str,
            total_iterations=total_iters,
            total_time_seconds=total_time,
            final_line_coverage=run_metric.final_line_coverage if run_metric else None,
            final_branch_coverage=run_metric.final_branch_coverage if run_metric else None,
            final_mutation_score=run_metric.final_mutation_score if run_metric else None,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )
