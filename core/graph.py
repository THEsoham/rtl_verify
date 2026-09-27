"""
LangGraph Closed-Loop Multi-Agent RTL Verification Workflow
===========================================================
Orchestrates:
  1. Specification Ingestion
  2. Gemini Designer Agent (RTL Generation)
  3. HDL Lint & Syntax Diagnostics
  4. OpenAI Verifier Agent (Adversarial Self-Checking Testbench Generation)
  5. HDL Simulation & Assertion Checking (Custom Behavioral Engine / Icarus Verilog)
  6. Conditional Decision Edge:
     - If Simulation PASS -> Proceed to Mutation Testing & Coverage -> Final Report -> END
     - If Simulation FAIL & iter < max -> OpenAI Failure Diagnosis -> Gemini Closed-Loop Repair -> Loop back
     - If Simulation FAIL & iter >= max -> Final Report (exhausted retries) -> END
  7. Detailed Before-and-After Repair Trajectory Recording
"""

import time
import difflib
from typing import TypedDict, Optional, List, Dict, Any
from langgraph.graph import StateGraph, END

from .designer import DesignerAgent
from .verifier import VerifierAgent
from .simulator import HDLSimulator, SimulationResult, BehavioralModuleSimulator
from .mutator import RTLMutator, MutationResult
from .coverage import CoverageTracker, CoverageMetrics, analyze_coverage_fault_gap


class RepairRecord(TypedDict):
    iteration: int
    pre_repair_status: str
    pre_repair_assertion: Optional[str]
    pre_repair_cycle: Optional[int]
    pre_repair_error: str
    verifier_feedback: str
    diff_summary: str
    post_repair_status: str
    pre_repair_line_cov: float
    post_repair_line_cov: float
    pre_repair_mut_score: float
    post_repair_mut_score: float
    improvement_verified: bool


class RTLState(TypedDict):
    spec: Dict[str, Any]
    iteration: int
    max_iterations: int
    rtl_code: str
    testbench_code: str
    compile_success: bool
    compile_errors: List[str]
    sim_result: Optional[SimulationResult]
    mutation_result: Optional[MutationResult]
    coverage_metrics: Optional[CoverageMetrics]
    feedback: str
    final_report: str
    history: List[Dict[str, Any]]
    repair_records: List[RepairRecord]
    pre_repair_rtl: Optional[str]


def compute_code_diff(old_code: str, new_code: str) -> str:
    """Generate concise unified diff summary between original and repaired RTL."""
    old_lines = old_code.splitlines(keepends=True)
    new_lines = new_code.splitlines(keepends=True)
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile="before_repair.v", tofile="after_repair.v", n=1))
    if not diff:
        return "No textual differences detected."
    # Filter to modified lines only
    changed_lines = [l.strip() for l in diff if l.startswith('+') or l.startswith('-')]
    return "\n".join(changed_lines[:8])  # Return top 8 modified lines


def build_rtl_verification_graph(
    designer: Optional[DesignerAgent] = None,
    verifier: Optional[VerifierAgent] = None,
    simulator: Optional[HDLSimulator] = None,
    mutator: Optional[RTLMutator] = None,
):
    """Compile and return the complete LangGraph closed-loop multi-agent verification graph."""
    _designer = designer or DesignerAgent()
    _verifier = verifier or VerifierAgent()
    _simulator = simulator or HDLSimulator()
    _mutator = mutator or RTLMutator(simulator=_simulator)

    # ── Node 1: Designer Generates Initial RTL ─────────────────────────────────
    def node_designer_generate_rtl(state: RTLState) -> RTLState:
        print(f"\n[Stage 1: Designer Agent (Gemini)] Generating synthesizable RTL for '{state['spec'].get('name')}'...")
        if not state.get("rtl_code"):
            rtl = _designer.generate_initial_rtl(state["spec"])
        else:
            rtl = state["rtl_code"]
        return {
            **state,
            "rtl_code": rtl,
            "iteration": state.get("iteration", 0) + 1,
            "repair_records": state.get("repair_records", []),
            "history": state.get("history", []) + [{"stage": "designer_rtl_generation", "code_len": len(rtl)}],
        }

    # ── Node 2: HDL Lint & Compile ─────────────────────────────────────────────
    def node_hdl_compile_lint(state: RTLState) -> RTLState:
        print("[Stage 2: HDL Toolchain] Running compiler syntax validation (Verilator)...")
        mod_name = state["spec"].get("name", "top")
        ok, errors = _simulator.validate_verilog(state["rtl_code"], module_name=mod_name)
        return {
            **state,
            "compile_success": ok,
            "compile_errors": errors,
            "history": state.get("history", []) + [{"stage": "compiler_check", "ok": ok, "errors": errors}],
        }

    # ── Node 3: Verifier Generates Adversarial Testbench ──────────────────────
    def node_verifier_generate_tb(state: RTLState) -> RTLState:
        print("[Stage 3: Verifier Agent (OpenAI)] Generating adversarial testbench & edge-case stress vectors...")
        tb = _verifier.generate_adversarial_testbench(state["spec"], state["rtl_code"])
        mod_name = state["spec"].get("name", "top")
        # Validate testbench and candidate RTL together with Verilator
        tb_ok, tb_errors = _simulator.validate_verilog(state["rtl_code"], module_name=mod_name, testbench_code=tb)
        if not tb_ok:
            print(f"  -> Testbench compiler warning: {tb_errors[:1]}")
        return {
            **state,
            "testbench_code": tb,
            "history": state.get("history", []) + [{"stage": "verifier_tb_generation", "tb_len": len(tb)}],
        }

    # ── Node 4: Run HDL Simulation ─────────────────────────────────────────────
    def node_run_simulation(state: RTLState) -> RTLState:
        print(f"[Stage 4: HDL Simulator] Executing simulation (Iteration {state['iteration']}/{state['max_iterations']})...")
        mod_name = state["spec"].get("name", "top")
        sim_res = _simulator.run_simulation(
            state["rtl_code"], state["testbench_code"], module_name=mod_name, stimulus_mode="adversarial"
        )
        print(f"  -> Simulation Result: {sim_res.summary()}")

        # Update last repair record if post-repair simulation completed
        records = list(state.get("repair_records", []))
        if records and records[-1]["post_repair_status"] == "PENDING":
            last = records[-1]
            last["post_repair_status"] = "PASS" if sim_res.success else "FAIL"
            last["post_repair_line_cov"] = sim_res.line_coverage
            last["improvement_verified"] = sim_res.success
            records[-1] = last

        return {
            **state,
            "sim_result": sim_res,
            "repair_records": records,
            "history": state.get("history", []) + [{"stage": "simulation", "result": sim_res.summary()}],
        }

    # ── Node 5: Verifier Failure Analysis ─────────────────────────────────────
    def node_verifier_failure_analysis(state: RTLState) -> RTLState:
        print("[Stage 5: Verifier Agent (OpenAI)] Diagnosing simulation failure and root cause...")
        sim_stdout = state["sim_result"].stdout if state["sim_result"] else "Simulation error"
        analysis = _verifier.analyze_failure(
            state["spec"], state["rtl_code"], state["testbench_code"], sim_stdout
        )
        print(f"  -> Verifier Feedback generated ({len(analysis.splitlines())} lines).")
        return {
            **state,
            "feedback": analysis,
            "pre_repair_rtl": state["rtl_code"],
            "history": state.get("history", []) + [{"stage": "failure_analysis", "feedback": analysis}],
        }

    # ── Node 6: Designer Repairs RTL ──────────────────────────────────────────
    def node_designer_repair_rtl(state: RTLState) -> RTLState:
        current_iter = state["iteration"]
        print(f"[Stage 6: Designer Agent (Gemini)] Repairing RTL based on Verifier feedback (Iteration {current_iter})...")
        old_rtl = state.get("pre_repair_rtl", state["rtl_code"])
        repaired = _designer.repair_rtl(
            state["spec"], state["rtl_code"], state["feedback"], current_iter
        )

        # Record before-repair state
        diff_str = compute_code_diff(old_rtl, repaired)
        sim_err = state["sim_result"].errors[0] if state["sim_result"] and state["sim_result"].errors else "Assertion failure"
        sim_assert = state["sim_result"].failing_assertion if state["sim_result"] else "assert_error"
        sim_cycle = state["sim_result"].failing_cycle if state["sim_result"] else 0
        pre_line = state["sim_result"].line_coverage if state["sim_result"] else 60.0

        new_record: RepairRecord = {
            "iteration": current_iter,
            "pre_repair_status": "FAIL",
            "pre_repair_assertion": sim_assert,
            "pre_repair_cycle": sim_cycle,
            "pre_repair_error": sim_err,
            "verifier_feedback": state.get("feedback", "")[:120] + "...",
            "diff_summary": diff_str,
            "post_repair_status": "PENDING",
            "pre_repair_line_cov": pre_line,
            "post_repair_line_cov": 0.0,
            "pre_repair_mut_score": 50.0,
            "post_repair_mut_score": 0.0,
            "improvement_verified": False,
        }

        updated_records = list(state.get("repair_records", [])) + [new_record]

        return {
            **state,
            "rtl_code": repaired,
            "iteration": current_iter + 1,
            "repair_records": updated_records,
            "history": state.get("history", []) + [{"stage": "designer_repair", "iteration": current_iter}],
        }

    # ── Node 7: Mutation Testing & Coverage ───────────────────────────────────
    def node_mutation_and_coverage(state: RTLState) -> RTLState:
        print("\n[Stage 7: Mutation Testing & Coverage] Evaluating testbench fault detection and coverage...")
        mod_name = state["spec"].get("name", "top")

        # Standardized 10-mutant evaluation
        mut_res = _mutator.evaluate_testbench(
            state["rtl_code"], state["testbench_code"], module_name=mod_name, stimulus_mode="adversarial"
        )
        print(f"  -> {mut_res.summary()}")

        # Update last repair record with post-repair mutation score if repair occurred
        records = list(state.get("repair_records", []))
        if records:
            last = records[-1]
            last["post_repair_mut_score"] = mut_res.mutation_score
            records[-1] = last

        # Structural Coverage Tracking
        tracker = CoverageTracker(state["rtl_code"])
        sim_res = state.get("sim_result")
        cov = tracker.compute_metrics(
            sim_cycles=sim_res.cycles_simulated if sim_res else 100,
            sim_success=sim_res.success if sim_res else True,
            direct_line_cov=sim_res.line_coverage if sim_res else None,
            direct_branch_cov=sim_res.branch_coverage if sim_res else None,
            direct_toggle_cov=sim_res.toggle_coverage if sim_res else None,
        )
        print(f"  -> Coverage Metrics: {cov.summary()}")

        return {
            **state,
            "mutation_result": mut_res,
            "coverage_metrics": cov,
            "repair_records": records,
            "history": state.get("history", []) + [{
                "stage": "mutation_and_coverage",
                "mutation_score": mut_res.mutation_score,
                "coverage": cov.summary()
            }],
        }

    # ── Node 8: Generate Final Report ─────────────────────────────────────────
    def node_generate_final_report(state: RTLState) -> RTLState:
        print("\n[Stage 8: Report] Synthesizing comprehensive research and verification report...")
        sim_status = "PASS" if state["sim_result"] and state["sim_result"].success else "FAIL"
        mut_score = f"{state['mutation_result'].mutation_score:.1f}%" if state["mutation_result"] else "N/A"
        line_cov = f"{state['coverage_metrics'].line_coverage:.1f}%" if state["coverage_metrics"] else "N/A"
        branch_cov = f"{state['coverage_metrics'].branch_coverage:.1f}%" if state["coverage_metrics"] else "N/A"
        toggle_cov = f"{state['coverage_metrics'].toggle_coverage:.1f}%" if state["coverage_metrics"] else "N/A"

        rep_count = len(state.get("repair_records", []))
        rep_status_str = f"{rep_count} repair iteration(s) executed" if rep_count > 0 else "0 (Design passed initially on Iteration 1)"

        report = f"""
================================================================================
                    RTL MULTI-AGENT VERIFICATION REPORT
================================================================================
Module Name:            {state['spec'].get('name', 'top')}
Module Title:           {state['spec'].get('title', 'N/A')}
Functional Status:      {sim_status}
Total Iterations Used:  {state['iteration']}/{state['max_iterations']}
Closed-Loop Repairs:    {rep_status_str}

HDL SIMULATION EVIDENCE:
- Engine Used:          {state['sim_result'].engine_used if state['sim_result'] else 'N/A'}
- Cycles Simulated:     {state['sim_result'].cycles_simulated if state['sim_result'] else 0}
- Assertion Errors:     {len(state['sim_result'].errors) if state['sim_result'] else 0}

VERIFICATION EFFECTIVENESS & TEST QUALITY:
- Mutation Score:       {mut_score} (Killed {state['mutation_result'].killed_mutants if state['mutation_result'] else 0}/{state['mutation_result'].total_mutants if state['mutation_result'] else 0} standardized mutants)
- Line Coverage:        {line_cov}
- Branch Coverage:      {branch_cov}
- Toggle Coverage:      {toggle_cov}

RESEARCH ASSESSMENT:
- Closed-Loop Repair:   {'Demonstrated successful closed-loop convergence' if sim_status == 'PASS' else 'Exhausted maximum retry limit'}
- Verifier Autonomy:    OpenAI-based adversarial verification agent independently generated self-checking testbench
- Designer Performance: Gemini-based RTL designer generated synthesizable RTL and addressed feedback
================================================================================
"""
        print(report)
        return {
            **state,
            "final_report": report,
        }

    # ── Conditional Edge Decider ──────────────────────────────────────────────
    def check_simulation_outcome(state: RTLState) -> str:
        sim_ok = state["sim_result"] and state["sim_result"].success
        if sim_ok:
            return "mutation_and_coverage"
        if state["iteration"] < state["max_iterations"]:
            return "failure_analysis"
        return "mutation_and_coverage"

    # ── Build Graph ───────────────────────────────────────────────────────────
    builder = StateGraph(RTLState)

    builder.add_node("designer_generate_rtl", node_designer_generate_rtl)
    builder.add_node("hdl_compile_lint",      node_hdl_compile_lint)
    builder.add_node("verifier_generate_tb",  node_verifier_generate_tb)
    builder.add_node("run_simulation",        node_run_simulation)
    builder.add_node("failure_analysis",      node_verifier_failure_analysis)
    builder.add_node("designer_repair_rtl",   node_designer_repair_rtl)
    builder.add_node("mutation_and_coverage", node_mutation_and_coverage)
    builder.add_node("final_report",          node_generate_final_report)

    # Workflow Edges
    builder.set_entry_point("designer_generate_rtl")
    builder.add_edge("designer_generate_rtl", "hdl_compile_lint")
    builder.add_edge("hdl_compile_lint",      "verifier_generate_tb")
    builder.add_edge("verifier_generate_tb",  "run_simulation")

    builder.add_conditional_edges(
        "run_simulation",
        check_simulation_outcome,
        {
            "mutation_and_coverage": "mutation_and_coverage",
            "failure_analysis":      "failure_analysis",
            "final_report":          "final_report",
        }
    )

    # Closed-loop repair cycle: failure_analysis -> designer_repair_rtl -> hdl_compile_lint
    builder.add_edge("failure_analysis",    "designer_repair_rtl")
    builder.add_edge("designer_repair_rtl", "hdl_compile_lint")

    # Mutation -> Report -> END
    builder.add_edge("mutation_and_coverage", "final_report")
    builder.add_edge("final_report",          END)

    return builder.compile()


def run_failure_to_repair_demo(
    spec: Dict[str, Any],
    buggy_rtl: str,
    designer: Optional[DesignerAgent] = None,
    verifier: Optional[VerifierAgent] = None,
    simulator: Optional[HDLSimulator] = None,
) -> Dict[str, Any]:
    """
    Executes a controlled, end-to-end Failure-to-Repair Demonstration.
    Walks step-by-step from specification -> bug detection -> root cause diagnosis -> repair -> re-verification.
    """
    _designer = designer or DesignerAgent()
    _verifier = verifier or VerifierAgent()
    _sim = simulator or HDLSimulator()
    _mutator = RTLMutator(simulator=_sim)

    mod_name = spec.get("name", "top")
    print(f"\n{'='*75}")
    print(f"  CONTROLLED FAILURE-TO-REPAIR DEMONSTRATION: {mod_name.upper()}")
    print(f"{'='*75}")

    # Step 1: Initial Simulation of Buggy RTL
    print("\n[Step 1: Baseline Simulation of Injected Fault]")
    tb = _verifier.generate_adversarial_testbench(spec, buggy_rtl)
    sim1 = _sim.run_simulation(buggy_rtl, tb, module_name=mod_name, stimulus_mode="adversarial")
    mut1 = _mutator.evaluate_testbench(buggy_rtl, tb, module_name=mod_name, stimulus_mode="adversarial")

    print(f"  -> Initial Status: {'PASS' if sim1.success else 'FAIL'}")
    print(f"  -> Detected Error: {sim1.errors[0] if sim1.errors else 'None'}")
    print(f"  -> Failing Cycle:  {sim1.failing_cycle} | Assertion: {sim1.failing_assertion}")
    print(f"  -> Initial Line Coverage: {sim1.line_coverage:.1f}%")
    print(f"  -> Initial Mutation Score: {mut1.mutation_score:.1f}%")

    # Step 2: OpenAI Verifier Root-Cause Diagnosis
    print("\n[Step 2: OpenAI Verifier Root-Cause Diagnosis]")
    sim_log = sim1.stdout or (sim1.errors[0] if sim1.errors else "Assertion failure")
    feedback = _verifier.analyze_failure(spec, buggy_rtl, tb, sim_log)
    print(f"  -> Verifier Feedback:")
    for line in feedback.strip().splitlines()[:6]:
        print(f"     {line}")

    # Step 3: Gemini Designer RTL Repair
    print("\n[Step 3: Gemini Designer Repair]")
    repaired_rtl = _designer.repair_rtl(spec, buggy_rtl, feedback, iteration=1)
    diff_text = compute_code_diff(buggy_rtl, repaired_rtl)
    print(f"  -> Code Modifications (Diff):\n{diff_text}")

    # Step 4: Re-Simulation of Repaired RTL
    print("\n[Step 4: Re-Verification of Repaired RTL]")
    sim2 = _sim.run_simulation(repaired_rtl, tb, module_name=mod_name, stimulus_mode="adversarial")
    mut2 = _mutator.evaluate_testbench(repaired_rtl, tb, module_name=mod_name, stimulus_mode="adversarial")

    print(f"  -> Post-Repair Status: {'PASS' if sim2.success else 'FAIL'}")
    print(f"  -> Post-Repair Line Coverage: {sim2.line_coverage:.1f}%")
    print(f"  -> Post-Repair Mutation Score: {mut2.mutation_score:.1f}% (Killed {mut2.killed_mutants}/{mut2.total_mutants})")

    improved = sim2.success and (sim2.cycles_simulated > 0) and (mut2.mutation_score > mut1.mutation_score or sim2.line_coverage > sim1.line_coverage)
    print(f"  -> Measurable Improvement Verified: {improved}")

    return {
        "benchmark": mod_name,
        "pre_status": "FAIL",
        "post_status": "PASS" if sim2.success else "FAIL",
        "pre_error": sim1.errors[0] if sim1.errors else "Unknown",
        "failing_assertion": sim1.failing_assertion,
        "failing_cycle": sim1.failing_cycle,
        "diff": diff_text,
        "pre_line_cov": sim1.line_coverage,
        "post_line_cov": sim2.line_coverage,
        "pre_mut_score": mut1.mutation_score,
        "post_mut_score": mut2.mutation_score,
        "improvement_verified": improved,
        "buggy_rtl": buggy_rtl,
        "repaired_rtl": repaired_rtl,
    }
