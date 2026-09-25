"""Cross-run and model-level comparison services."""

from __future__ import annotations

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from rtl_verify.metrics.collector import MetricsCollector
from rtl_verify.metrics.schemas import ComparisonResult, ComparisonRow, RunSummary
from rtl_verify.models import (
    Benchmark,
    CoverageReport,
    Iteration,
    IterationStatus,
    MutationResult,
    Run,
    RunMetric,
    RunStatus,
)

log = structlog.get_logger()


class MetricsComparison:
    """Provides side-by-side comparison across individual runs or model configurations."""

    def __init__(self, collector: MetricsCollector | None = None) -> None:
        self.collector = collector or MetricsCollector()

    async def compare_runs(
        self, session: AsyncSession, run_ids: list[int]
    ) -> ComparisonResult:
        """Compare multiple runs side-by-side.

        Builds comparison rows for:
        - Status
        - Total Iterations
        - Total Time (s)
        - Compilation Success Rate (%)
        - Final Line Coverage (%)
        - Final Branch Coverage (%)
        - Final Mutation Score (%)
        - Designer Tokens
        - Verifier Tokens
        """
        if not run_ids:
            return ComparisonResult(run_summaries=[], comparison_table=[])

        # Query all requested runs joined with benchmark and metrics
        stmt = (
            select(Run, Benchmark.name.label("benchmark_name"), RunMetric)
            .outerjoin(Benchmark, Run.benchmark_id == Benchmark.id)
            .outerjoin(RunMetric, Run.id == RunMetric.run_id)
            .where(Run.id.in_(run_ids))
        )
        result = await session.execute(stmt)
        rows = result.all()

        run_map: dict[int, tuple[Run, str | None, RunMetric | None]] = {
            row[0].id: row for row in rows
        }

        # Query iteration details as fallback for runs without RunMetric
        missing_metric_run_ids = [
            rid for rid in run_ids if rid in run_map and run_map[rid][2] is None
        ]
        iter_map: dict[int, list[Iteration]] = {}
        if missing_metric_run_ids:
            iter_stmt = (
                select(Iteration)
                .where(Iteration.run_id.in_(missing_metric_run_ids))
                .order_by(Iteration.run_id, Iteration.iteration_num.asc())
            )
            iter_res = await session.execute(iter_stmt)
            for it in iter_res.scalars().all():
                iter_map.setdefault(it.run_id, []).append(it)

        # Initialize metric row dictionaries
        status_vals: dict[int | str, float | str | None] = {}
        iters_vals: dict[int | str, float | str | None] = {}
        time_vals: dict[int | str, float | str | None] = {}
        comp_vals: dict[int | str, float | str | None] = {}
        line_cov_vals: dict[int | str, float | str | None] = {}
        branch_cov_vals: dict[int | str, float | str | None] = {}
        mut_vals: dict[int | str, float | str | None] = {}
        designer_tok_vals: dict[int | str, float | str | None] = {}
        verifier_tok_vals: dict[int | str, float | str | None] = {}

        run_summaries: list[RunSummary] = []

        for rid in run_ids:
            if rid not in run_map:
                log.warning("comparison_run_id_not_found", run_id=rid)
                status_vals[rid] = None
                iters_vals[rid] = None
                time_vals[rid] = None
                comp_vals[rid] = None
                line_cov_vals[rid] = None
                branch_cov_vals[rid] = None
                mut_vals[rid] = None
                designer_tok_vals[rid] = None
                verifier_tok_vals[rid] = None
                continue

            run, b_name, r_metric = run_map[rid]
            summary = await self.collector._build_run_summary(session, run, b_name, r_metric)
            run_summaries.append(summary)

            # Extract metric values
            status_vals[rid] = summary.status
            iters_vals[rid] = summary.total_iterations
            time_vals[rid] = summary.total_time_seconds

            # Compilation success rate
            if r_metric and r_metric.compilation_success_rate is not None:
                comp_vals[rid] = r_metric.compilation_success_rate
            else:
                iters = iter_map.get(rid, [])
                if iters:
                    compiled = sum(
                        1
                        for it in iters
                        if it.status not in (
                            IterationStatus.COMPILE_FAIL_RTL,
                            IterationStatus.COMPILE_FAIL_TB,
                            IterationStatus.ERROR,
                        )
                    )
                    comp_vals[rid] = round((compiled / len(iters)) * 100.0, 2)
                else:
                    comp_vals[rid] = None

            line_cov_vals[rid] = summary.final_line_coverage
            branch_cov_vals[rid] = summary.final_branch_coverage
            mut_vals[rid] = summary.final_mutation_score
            designer_tok_vals[rid] = r_metric.designer_total_tokens if r_metric else None
            verifier_tok_vals[rid] = r_metric.verifier_total_tokens if r_metric else None

        comparison_table = [
            ComparisonRow(metric_name="Status", values=status_vals),
            ComparisonRow(metric_name="Total Iterations", values=iters_vals),
            ComparisonRow(metric_name="Total Time (s)", values=time_vals),
            ComparisonRow(metric_name="Compilation Success Rate (%)", values=comp_vals),
            ComparisonRow(metric_name="Final Line Coverage (%)", values=line_cov_vals),
            ComparisonRow(metric_name="Final Branch Coverage (%)", values=branch_cov_vals),
            ComparisonRow(metric_name="Final Mutation Score (%)", values=mut_vals),
            ComparisonRow(metric_name="Designer Tokens", values=designer_tok_vals),
            ComparisonRow(metric_name="Verifier Tokens", values=verifier_tok_vals),
        ]

        return ComparisonResult(
            run_summaries=run_summaries,
            comparison_table=comparison_table,
        )

    async def compare_models(
        self, session: AsyncSession, benchmark_id: int
    ) -> ComparisonResult:
        """Group all runs for a benchmark by (designer_model, verifier_model) pair and compare averages."""
        stmt = (
            select(Run, Benchmark.name.label("benchmark_name"), RunMetric)
            .outerjoin(Benchmark, Run.benchmark_id == Benchmark.id)
            .outerjoin(RunMetric, Run.id == RunMetric.run_id)
            .where(Run.benchmark_id == benchmark_id)
            .order_by(desc(Run.started_at), desc(Run.id))
        )
        result = await session.execute(stmt)
        rows = result.all()

        if not rows:
            return ComparisonResult(run_summaries=[], comparison_table=[])

        run_summaries: list[RunSummary] = []
        # Group data by (designer_model, verifier_model)
        groups: dict[str, list[tuple[Run, RunMetric | None]]] = {}

        for run, benchmark_name, run_metric in rows:
            summary = self.collector._build_run_summary_fast(run, benchmark_name, run_metric)
            run_summaries.append(summary)

            group_key = f"{run.designer_model} / {run.verifier_model}"
            groups.setdefault(group_key, []).append((run, run_metric))

        # Compute averages for each model pair group
        total_runs_vals: dict[int | str, float | str | None] = {}
        pass_rate_vals: dict[int | str, float | str | None] = {}
        avg_iters_vals: dict[int | str, float | str | None] = {}
        avg_time_vals: dict[int | str, float | str | None] = {}
        avg_comp_vals: dict[int | str, float | str | None] = {}
        avg_line_cov_vals: dict[int | str, float | str | None] = {}
        avg_branch_cov_vals: dict[int | str, float | str | None] = {}
        avg_mutation_vals: dict[int | str, float | str | None] = {}
        avg_des_tok_vals: dict[int | str, float | str | None] = {}
        avg_ver_tok_vals: dict[int | str, float | str | None] = {}

        for group_name, run_list in groups.items():
            total_runs = len(run_list)
            passed_runs = sum(
                1
                for r, _ in run_list
                if (
                    r.status == RunStatus.PASSED
                    or (hasattr(r.status, "value") and r.status.value == "passed")
                    or str(r.status) == "passed"
                )
            )
            pass_rate = round((passed_runs / total_runs) * 100.0, 2)

            iterations_list = [
                rm.total_iterations if (rm and rm.total_iterations is not None) else (r.total_iterations or 0)
                for r, rm in run_list
            ]
            avg_iters = (
                round(sum(iterations_list) / len(iterations_list), 2)
                if iterations_list
                else None
            )

            times_list: list[float] = []
            for r, rm in run_list:
                if rm and rm.total_time_seconds is not None:
                    times_list.append(rm.total_time_seconds)
                elif r.started_at and r.finished_at:
                    times_list.append((r.finished_at - r.started_at).total_seconds())
            avg_time = (
                round(sum(times_list) / len(times_list), 2) if times_list else None
            )

            comp_rates = [
                rm.compilation_success_rate
                for _, rm in run_list
                if (rm and rm.compilation_success_rate is not None)
            ]
            avg_comp_rate = (
                round(sum(comp_rates) / len(comp_rates), 2) if comp_rates else None
            )

            line_covs = [
                rm.final_line_coverage
                for _, rm in run_list
                if (rm and rm.final_line_coverage is not None)
            ]
            avg_line_cov = (
                round(sum(line_covs) / len(line_covs), 2) if line_covs else None
            )

            branch_covs = [
                rm.final_branch_coverage
                for _, rm in run_list
                if (rm and rm.final_branch_coverage is not None)
            ]
            avg_branch_cov = (
                round(sum(branch_covs) / len(branch_covs), 2) if branch_covs else None
            )

            mutation_scores = [
                rm.final_mutation_score
                for _, rm in run_list
                if (rm and rm.final_mutation_score is not None)
            ]
            avg_mut_score = (
                round(sum(mutation_scores) / len(mutation_scores), 2)
                if mutation_scores
                else None
            )

            des_tokens = [
                rm.designer_total_tokens
                for _, rm in run_list
                if (rm and rm.designer_total_tokens is not None)
            ]
            avg_des_tokens = (
                round(sum(des_tokens) / len(des_tokens), 1) if des_tokens else None
            )

            ver_tokens = [
                rm.verifier_total_tokens
                for _, rm in run_list
                if (rm and rm.verifier_total_tokens is not None)
            ]
            avg_ver_tokens = (
                round(sum(ver_tokens) / len(ver_tokens), 1) if ver_tokens else None
            )

            total_runs_vals[group_name] = total_runs
            pass_rate_vals[group_name] = pass_rate
            avg_iters_vals[group_name] = avg_iters
            avg_time_vals[group_name] = avg_time
            avg_comp_vals[group_name] = avg_comp_rate
            avg_line_cov_vals[group_name] = avg_line_cov
            avg_branch_cov_vals[group_name] = avg_branch_cov
            avg_mutation_vals[group_name] = avg_mut_score
            avg_des_tok_vals[group_name] = avg_des_tokens
            avg_ver_tok_vals[group_name] = avg_ver_tokens

        comparison_table = [
            ComparisonRow(metric_name="Total Runs", values=total_runs_vals),
            ComparisonRow(metric_name="Pass Rate (%)", values=pass_rate_vals),
            ComparisonRow(metric_name="Avg Iterations", values=avg_iters_vals),
            ComparisonRow(metric_name="Avg Total Time (s)", values=avg_time_vals),
            ComparisonRow(metric_name="Avg Compilation Success Rate (%)", values=avg_comp_vals),
            ComparisonRow(metric_name="Avg Line Coverage (%)", values=avg_line_cov_vals),
            ComparisonRow(metric_name="Avg Branch Coverage (%)", values=avg_branch_cov_vals),
            ComparisonRow(metric_name="Avg Mutation Score (%)", values=avg_mutation_vals),
            ComparisonRow(metric_name="Avg Designer Tokens", values=avg_des_tok_vals),
            ComparisonRow(metric_name="Avg Verifier Tokens", values=avg_ver_tok_vals),
        ]

        return ComparisonResult(
            run_summaries=run_summaries,
            comparison_table=comparison_table,
        )
