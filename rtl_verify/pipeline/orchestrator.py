from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Awaitable

import structlog

from rtl_verify.config import settings
from rtl_verify.agents.designer import DesignerAgent
from rtl_verify.agents.verifier import VerifierAgent
from rtl_verify.verification.iverilog import IcarusVerilog, CompileResult, SimResult
from rtl_verify.verification.verilator import Verilator
from rtl_verify.verification.mutation import MutationEngine, MutationTestResult
from rtl_verify.verification.coverage import CoverageCollector, CoverageReport
from rtl_verify.pipeline.result_parser import ResultParser, ParsedSimResult
from rtl_verify.pipeline.runner import SubprocessRunner
from rtl_verify.benchmarks.registry import BenchmarkSpec
from rtl_verify.database import get_session
from rtl_verify.models import (
    Run,
    Iteration,
    CoverageReport as CoverageReportModel,
    MutationResult as MutationResultModel,
    RunMetric,
    RunStatus,
    IterationStatus,
)

log = structlog.get_logger()


@dataclass
class RunConfig:
    """Configuration for a single pipeline run."""

    max_iterations: int = 10
    max_tb_fix_iterations: int = 3
    coverage_threshold: float = 80.0
    run_mutation_testing: bool = False  # Expensive, opt-in
    mutation_score_threshold: float = 60.0
    simulation_timeout: int = 30
    designer_model: str | None = None  # None = use settings default
    verifier_model: str | None = None


@dataclass
class IterationResult:
    """Result of a single design-verify iteration."""

    iteration_num: int
    status: str  # compile_fail_rtl, compile_fail_tb, sim_fail, sim_pass
    rtl_source: str
    testbench_source: str | None
    compile_stdout: str
    compile_stderr: str
    sim_stdout: str | None
    sim_stderr: str | None
    sim_passed: bool
    coverage: CoverageReport | None
    mutation_result: MutationTestResult | None
    feedback: str | None
    designer_time_ms: int
    verifier_time_ms: int
    sim_time_ms: int


@dataclass
class PipelineResult:
    """Result of a complete pipeline run."""

    run_id: int
    status: str  # passed, failed, iteration_limit, error
    total_iterations: int
    iterations: list[IterationResult]
    final_rtl: str | None
    final_testbench: str | None
    total_time_seconds: float
    error_message: str | None = None


# Callback type for real-time UI updates
ProgressCallback = Callable[[str, IterationResult | None], Awaitable[None]] | None


class PipelineOrchestrator:
    def __init__(self, config: RunConfig | None = None):
        self.config = config or RunConfig()
        self.designer = DesignerAgent(model=self.config.designer_model)
        self.verifier = VerifierAgent(model=self.config.verifier_model)
        self.iverilog = IcarusVerilog()
        self.verilator = Verilator()
        self.mutation_engine = MutationEngine(self.iverilog)
        # FIX: CoverageCollector requires a Verilator instance
        self.coverage_collector = CoverageCollector(verilator=self.verilator)
        self.result_parser = ResultParser()

    async def run(
        self,
        spec: BenchmarkSpec,
        run_id: int | None = None,
        on_progress: ProgressCallback = None,
    ) -> PipelineResult:
        """Execute the full design-verify-feedback loop."""
        start_time = time.time()

        # 1. Create or update a Run record in the DB
        # FIX: Use started_at / finished_at (not start_time / end_time)
        async with get_session() as session:
            if run_id is None:
                new_run = Run(
                    benchmark_id=spec.id or 0,
                    designer_model=self.config.designer_model or settings.designer_model,
                    verifier_model=self.config.verifier_model or settings.verifier_model,
                    status=RunStatus.RUNNING,
                )
                session.add(new_run)
                await session.commit()
                run_id = new_run.id
            else:
                db_run = await session.get(Run, run_id)
                if db_run:
                    db_run.status = RunStatus.RUNNING
                    await session.commit()

        log.info("starting_pipeline_run", run_id=run_id, benchmark=spec.name)

        if on_progress:
            await on_progress("Started run", None)

        # 2. Create working directory
        run_work_dir = settings.run_dir(run_id)
        run_work_dir.mkdir(parents=True, exist_ok=True)

        iterations: list[IterationResult] = []
        final_rtl = None
        final_testbench = None
        run_status = RunStatus.FAILED
        error_msg = None

        previous_feedback: str | None = None
        previous_rtl: str | None = None

        try:
            for iteration_num in range(1, self.config.max_iterations + 1):
                iter_dir = settings.iteration_dir(run_id, iteration_num)
                iter_dir.mkdir(parents=True, exist_ok=True)

                log.info("starting_iteration", run_id=run_id, iteration_num=iteration_num)
                if on_progress:
                    await on_progress(f"Starting iteration {iteration_num}", None)

                iter_result = await self._run_iteration(
                    spec=spec,
                    iteration_num=iteration_num,
                    work_dir=iter_dir,
                    previous_feedback=previous_feedback,
                    previous_rtl=previous_rtl,
                )

                iterations.append(iter_result)
                final_rtl = iter_result.rtl_source
                final_testbench = iter_result.testbench_source

                await self._save_iteration(run_id, iter_result)

                if on_progress:
                    await on_progress(f"Completed iteration {iteration_num}", iter_result)

                if iter_result.status == "sim_pass":
                    # Check coverage and mutation score thresholds
                    cov_passed = True
                    mut_passed = True

                    if iter_result.coverage:
                        cov_passed = iter_result.coverage.meets_threshold(
                            self.config.coverage_threshold
                        )

                    if iter_result.mutation_result:
                        # FIX: MutationTestResult uses .score, not .mutation_score
                        mut_passed = (
                            iter_result.mutation_result.score
                            >= self.config.mutation_score_threshold
                        )

                    if cov_passed and mut_passed:
                        run_status = RunStatus.PASSED
                        log.info("run_passed_all_thresholds", run_id=run_id)
                        break
                    else:
                        log.info(
                            "run_sim_passed_but_thresholds_failed",
                            run_id=run_id,
                            cov_passed=cov_passed,
                            mut_passed=mut_passed,
                        )

                previous_feedback = iter_result.feedback
                previous_rtl = iter_result.rtl_source
            else:
                log.info("run_iteration_limit_reached", run_id=run_id)
                run_status = RunStatus.ITERATION_LIMIT

        except Exception as e:
            log.exception("run_error", run_id=run_id, error=str(e))
            run_status = RunStatus.ERROR
            error_msg = str(e)

        total_time = time.time() - start_time
        await self._finalize_run(run_id, run_status.value, iterations, total_time, error_msg)

        if on_progress:
            await on_progress(f"Run finished with status {run_status.value}", None)

        return PipelineResult(
            run_id=run_id,
            status=run_status.value,
            total_iterations=len(iterations),
            iterations=iterations,
            final_rtl=final_rtl,
            final_testbench=final_testbench,
            total_time_seconds=total_time,
            error_message=error_msg,
        )

    async def _run_iteration(
        self,
        spec: BenchmarkSpec,
        iteration_num: int,
        work_dir: Path,
        previous_feedback: str | None = None,
        previous_rtl: str | None = None,
    ) -> IterationResult:
        """Execute a single iteration of the design-verify loop."""

        # FINE-TUNE: Use to_prompt_description() for a richer, structured prompt
        spec_description = spec.to_prompt_description()
        # Build port dict for agents (port_name -> dict with direction, width, description)
        ports_dict = {}
        for p in spec.input_ports:
            ports_dict[p.name] = {
                "direction": "input",
                "width": p.width,
                "description": p.description or "",
            }
        for p in spec.output_ports:
            ports_dict[p.name] = {
                "direction": "output",
                "width": p.width,
                "description": p.description or "",
            }

        # ── Designer ──────────────────────────────────────────────────────────
        designer_start = time.time()
        if iteration_num == 1 or previous_rtl is None:
            # FIX: correct method name + pass ports and requirements
            rtl_source, _ = await self.designer.generate_rtl(
                spec_description=spec_description,
                ports=ports_dict,
                requirements=spec.requirements,
            )
        else:
            # FIX: correct method name + pass spec_description
            rtl_source, _ = await self.designer.fix_rtl(
                spec_description=spec_description,
                previous_rtl=previous_rtl,
                feedback=previous_feedback or "Unknown error, please review.",
            )
        designer_time = int((time.time() - designer_start) * 1000)

        rtl_file = work_dir / "design.sv"
        rtl_file.write_text(rtl_source, encoding="utf-8")

        # ── Fast Verilator lint ───────────────────────────────────────────────
        # FIX: lint() takes a list[Path], not (file, work_dir)
        lint_result = await self.verilator.lint(sources=[rtl_file])
        if not lint_result.success:
            feedback = ResultParser.build_designer_feedback(
                compile_result=CompileResult(
                    success=False,
                    stdout=lint_result.stdout,
                    stderr=lint_result.stderr,
                    errors=lint_result.errors,
                    warnings=lint_result.warnings,
                )
            )
            return IterationResult(
                iteration_num=iteration_num,
                status="compile_fail_rtl",
                rtl_source=rtl_source,
                testbench_source=None,
                compile_stdout=lint_result.stdout,
                compile_stderr=lint_result.stderr,
                sim_stdout=None,
                sim_stderr=None,
                sim_passed=False,
                coverage=None,
                mutation_result=None,
                feedback=feedback,
                designer_time_ms=designer_time,
                verifier_time_ms=0,
                sim_time_ms=0,
            )

        # ── Verifier generates testbench ──────────────────────────────────────
        verifier_start = time.time()
        module_name_match = re.search(r"module\s+(\w+)", rtl_source)
        module_name = module_name_match.group(1) if module_name_match else "unknown_module"

        # FIX: correct method name + correct arg order (spec_description first)
        testbench_source, _ = await self.verifier.generate_testbench(
            spec_description=spec_description,
            rtl_source=rtl_source,
            module_name=module_name,
            ports=ports_dict,
        )
        verifier_time = int((time.time() - verifier_start) * 1000)

        tb_file = work_dir / "testbench.sv"
        tb_file.write_text(testbench_source, encoding="utf-8")

        # ── Compile RTL + testbench with iverilog ─────────────────────────────
        # FIX: compile() second arg is output *file* path, not a directory
        vvp_file = work_dir / "sim.vvp"
        compile_result = await self.iverilog.compile(
            sources=[rtl_file, tb_file],
            output=vvp_file,
        )
        compile_stdout = compile_result.stdout
        compile_stderr = compile_result.stderr

        if not compile_result.success:
            fixed_tb, fixed = await self._try_fix_testbench(
                spec, spec_description, ports_dict, rtl_source,
                testbench_source, compile_result, work_dir, module_name,
            )
            if fixed:
                testbench_source = fixed_tb
                # Re-compile with the fixed testbench
                tb_file.write_text(testbench_source, encoding="utf-8")
                vvp_file = work_dir / "sim.vvp"
                compile_result = await self.iverilog.compile(
                    sources=[rtl_file, tb_file],
                    output=vvp_file,
                )
                compile_stdout = compile_result.stdout
                compile_stderr = compile_result.stderr
                if not compile_result.success:
                    fixed = False

            if not fixed:
                feedback = ResultParser.build_designer_feedback(compile_result=compile_result)
                return IterationResult(
                    iteration_num=iteration_num,
                    status="compile_fail_tb",
                    rtl_source=rtl_source,
                    testbench_source=testbench_source,
                    compile_stdout=compile_stdout,
                    compile_stderr=compile_stderr,
                    sim_stdout=None,
                    sim_stderr=None,
                    sim_passed=False,
                    coverage=None,
                    mutation_result=None,
                    feedback=feedback,
                    designer_time_ms=designer_time,
                    verifier_time_ms=verifier_time,
                    sim_time_ms=0,
                )

        # ── Simulate ──────────────────────────────────────────────────────────
        # FIX: simulate() takes (vvp_file, timeout) — no work_dir arg
        sim_start = time.time()
        sim_result_raw = await self.iverilog.simulate(
            vvp_file=vvp_file,
            timeout=self.config.simulation_timeout,
        )
        sim_time = int((time.time() - sim_start) * 1000)

        sim_stdout = sim_result_raw.stdout
        sim_stderr = sim_result_raw.stderr

        # FIX: correct method name parse_simulation_output(stdout, stderr)
        parsed_sim = ResultParser.parse_simulation_output(sim_stdout, sim_stderr)

        if not parsed_sim.passed:
            # FIX: build_designer_feedback takes objects, not raw strings
            feedback = ResultParser.build_designer_feedback(sim_result=parsed_sim)
            return IterationResult(
                iteration_num=iteration_num,
                status="sim_fail",
                rtl_source=rtl_source,
                testbench_source=testbench_source,
                compile_stdout=compile_stdout,
                compile_stderr=compile_stderr,
                sim_stdout=sim_stdout,
                sim_stderr=sim_stderr,
                sim_passed=False,
                coverage=None,
                mutation_result=None,
                feedback=feedback,
                designer_time_ms=designer_time,
                verifier_time_ms=verifier_time,
                sim_time_ms=sim_time,
            )

        # ── Simulation passed — optional coverage + mutation testing ──────────
        coverage_report: CoverageReport | None = None
        mutation_result: MutationTestResult | None = None
        feedback_parts: list[str] = []

        # Coverage
        # FIX: collect() takes (rtl_sources: list[Path], work_dir) — not 4 args
        try:
            coverage_report = await self.coverage_collector.collect(
                rtl_sources=[rtl_file],
                work_dir=work_dir,
            )
            if coverage_report and not coverage_report.meets_threshold(
                self.config.coverage_threshold
            ):
                feedback_parts.append(
                    f"Simulation passed, but coverage is only "
                    f"{coverage_report.line_coverage:.1f}% "
                    f"(threshold {self.config.coverage_threshold}%).\n"
                    "Please add more robust assertions or vary inputs to cover edge cases."
                )
                # FINE-TUNE: Surface uncovered lines to the designer
                if coverage_report.uncovered_lines:
                    lines_preview = "\n".join(
                        f"  - {fn}:{ln}"
                        for fn, ln in coverage_report.uncovered_lines[:8]
                    )
                    feedback_parts.append(f"Uncovered lines:\n{lines_preview}")
        except Exception as e:
            log.warning("coverage_collection_failed", error=str(e))

        # Mutation Testing
        if self.config.run_mutation_testing:
            try:
                # FIX: method is run_mutation_testing(rtl_source, tb_source, work_dir)
                #      It takes source strings, not file paths
                mutation_result = await self.mutation_engine.run_mutation_testing(
                    rtl_source=rtl_source,
                    testbench_source=testbench_source,
                    work_dir=work_dir,
                )
                # FIX: MutationTestResult uses .score (not .mutation_score)
                if mutation_result and mutation_result.score < self.config.mutation_score_threshold:
                    feedback_parts.append(
                        f"Mutation testing score is {mutation_result.score:.1f}% "
                        f"(threshold {self.config.mutation_score_threshold}%).\n"
                        f"Killed {mutation_result.killed}/{mutation_result.total} mutants.\n"
                        "The testbench may not be catching subtle design bugs. "
                        "Please strengthen assertions."
                    )
            except Exception as e:
                log.warning("mutation_testing_failed", error=str(e))

        # FINE-TUNE: Include coverage data in feedback even on pass
        final_feedback: str | None = None
        if feedback_parts:
            final_feedback = "\n\n".join(feedback_parts)
        elif coverage_report:
            # Provide informational feedback via build_designer_feedback
            final_feedback = ResultParser.build_designer_feedback(
                sim_result=parsed_sim,
                coverage=coverage_report,
            )

        return IterationResult(
            iteration_num=iteration_num,
            status="sim_pass",
            rtl_source=rtl_source,
            testbench_source=testbench_source,
            compile_stdout=compile_stdout,
            compile_stderr=compile_stderr,
            sim_stdout=sim_stdout,
            sim_stderr=sim_stderr,
            sim_passed=True,
            coverage=coverage_report,
            mutation_result=mutation_result,
            feedback=final_feedback,
            designer_time_ms=designer_time,
            verifier_time_ms=verifier_time,
            sim_time_ms=sim_time,
        )

    async def _try_fix_testbench(
        self,
        spec: BenchmarkSpec,
        spec_description: str,
        ports_dict: dict,
        rtl_source: str,
        testbench: str,
        compile_result: CompileResult,
        work_dir: Path,
        module_name: str,
    ) -> tuple[str, bool]:
        """Attempt to fix a testbench that failed to compile. Returns (fixed_tb, success)."""
        current_tb = testbench
        error_output = compile_result.stdout + "\n" + compile_result.stderr

        rtl_file = work_dir / "design.sv"
        tb_file = work_dir / "testbench.sv"
        vvp_file = work_dir / "sim.vvp"

        for fix_iter in range(self.config.max_tb_fix_iterations):
            log.info("fixing_testbench", fix_iter=fix_iter + 1)
            # FIX: correct method name + pass spec_description
            fixed_tb, _ = await self.verifier.refine_testbench(
                spec_description=spec_description,
                rtl_source=rtl_source,
                previous_tb=current_tb,
                error_output=error_output,
            )
            current_tb = fixed_tb
            tb_file.write_text(current_tb, encoding="utf-8")

            compile_result = await self.iverilog.compile(
                sources=[rtl_file, tb_file],
                output=vvp_file,
            )
            error_output = compile_result.stdout + "\n" + compile_result.stderr

            if compile_result.success:
                log.info("testbench_fixed")
                return current_tb, True

        log.warning("testbench_fix_failed")
        return current_tb, False

    async def _save_iteration(self, run_id: int, result: IterationResult) -> None:
        """Persist an iteration result to the database."""
        async with get_session() as session:
            try:
                # FIX: Use correct IterationStatus enum values
                status_map = {
                    "compile_fail_rtl": IterationStatus.COMPILE_FAIL_RTL,
                    "compile_fail_tb": IterationStatus.COMPILE_FAIL_TB,
                    "sim_fail": IterationStatus.SIM_FAIL,
                    "sim_pass": IterationStatus.SIM_PASS,
                }

                # FIX: Use correct ORM field names (testbench_source, compile_stdout,
                #      compile_stderr, sim_stdout, sim_stderr, sim_passed)
                db_iter = Iteration(
                    run_id=run_id,
                    iteration_num=result.iteration_num,
                    status=status_map.get(result.status, IterationStatus.COMPILE_FAIL_RTL),
                    rtl_source=result.rtl_source,
                    testbench_source=result.testbench_source,
                    compile_stdout=result.compile_stdout,
                    compile_stderr=result.compile_stderr,
                    sim_stdout=result.sim_stdout,
                    sim_stderr=result.sim_stderr,
                    sim_passed=result.sim_passed,
                    designer_time_ms=result.designer_time_ms,
                    verifier_time_ms=result.verifier_time_ms,
                    sim_time_ms=result.sim_time_ms,
                    feedback=result.feedback,
                )
                session.add(db_iter)
                await session.flush()  # populate db_iter.id

                if result.coverage:
                    # FIX: functional_coverage, not fsm_coverage
                    cov_model = CoverageReportModel(
                        iteration_id=db_iter.id,
                        line_coverage=result.coverage.line_coverage,
                        branch_coverage=result.coverage.branch_coverage,
                        toggle_coverage=result.coverage.toggle_coverage,
                        functional_coverage=result.coverage.functional_coverage,
                    )
                    session.add(cov_model)

                if result.mutation_result:
                    # FIX: ORM fields are killed/survived (not killed_mutants/survived_mutants)
                    #      MutationTestResult fields are total/killed/survived/timeout/error/score
                    mut_model = MutationResultModel(
                        iteration_id=db_iter.id,
                        total_mutants=result.mutation_result.total,
                        killed=result.mutation_result.killed,
                        survived=result.mutation_result.survived,
                        timeout=result.mutation_result.timeout,
                        error=result.mutation_result.error,
                        mutation_score=result.mutation_result.score,
                    )
                    session.add(mut_model)

                await session.commit()
            except Exception as e:
                log.error("save_iteration_failed", run_id=run_id, error=str(e))
                await session.rollback()

    async def _finalize_run(
        self,
        run_id: int,
        status: str,
        results: list[IterationResult],
        total_time: float,
        error_msg: str | None = None,
    ) -> None:
        """Update the Run record with final status and compute aggregated metrics."""
        async with get_session() as session:
            try:
                db_run = await session.get(Run, run_id)
                if not db_run:
                    log.error("run_not_found_for_finalize", run_id=run_id)
                    return

                # FIX: Use correct ORM field names (finished_at, error_message)
                from datetime import datetime, timezone

                db_run.status = RunStatus(status)
                db_run.finished_at = datetime.now(timezone.utc)
                db_run.total_iterations = len(results)
                if error_msg:
                    db_run.error_message = error_msg

                # FIX: RunMetric has specific scalar fields — not a generic key-value store.
                #      Compute aggregated metrics and store in a single RunMetric row.
                if results:
                    total_designer_ms = sum(r.designer_time_ms for r in results)
                    total_verifier_ms = sum(r.verifier_time_ms for r in results)
                    total_sim_ms = sum(r.sim_time_ms for r in results)

                    compiled_ok = sum(
                        1 for r in results
                        if r.status not in ("compile_fail_rtl", "compile_fail_tb")
                    )
                    compile_success_rate = (compiled_ok / len(results)) * 100

                    last_pass = next(
                        (r for r in reversed(results) if r.status == "sim_pass"), None
                    )
                    final_line_cov = (
                        last_pass.coverage.line_coverage
                        if last_pass and last_pass.coverage
                        else None
                    )
                    final_branch_cov = (
                        last_pass.coverage.branch_coverage
                        if last_pass and last_pass.coverage
                        else None
                    )
                    final_mut_score = (
                        last_pass.mutation_result.score
                        if last_pass and last_pass.mutation_result
                        else None
                    )

                    run_metric = RunMetric(
                        run_id=run_id,
                        total_iterations=len(results),
                        final_status=status,
                        total_time_seconds=total_time,
                        compilation_success_rate=compile_success_rate,
                        final_line_coverage=final_line_cov,
                        final_branch_coverage=final_branch_cov,
                        final_mutation_score=final_mut_score,
                    )
                    session.add(run_metric)

                await session.commit()
            except Exception as e:
                log.error("finalize_run_failed", run_id=run_id, error=str(e))
                await session.rollback()
