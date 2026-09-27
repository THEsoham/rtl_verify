"""
Agentic RTL Generation & Adversarial Verification - Main Experiment Runner
==========================================================================
Executes the complete research evaluation suite:
  1. Closed-Loop LangGraph Pipeline Execution (Gemini Designer + OpenAI Verifier)
  2. Controlled Failure-to-Repair Demonstration (with before/after state and diffs)
  3. Controlled Hardware Fault Injection Experiments (12 representative faults)
  4. Comparative Benchmark Matrix across 3 Methodologies:
     - Baseline 1: Single-LLM Generate-Only
     - Baseline 2: Single-LLM Self-Verification
     - Proposed: Dual-Agent Adversarial Framework
  5. Multi-panel publication-quality visualizations (research_evaluation.png)
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent / ".env")

from core import (
    DesignerAgent,
    VerifierAgent,
    HDLSimulator,
    RTLMutator,
    CoverageTracker,
    build_rtl_verification_graph,
    RTLState,
    run_failure_to_repair_demo,
    ControlledFaultEngine,
    ResearchEvaluator,
)
from benchmarks import load_benchmark, list_benchmarks


def main():
    print("=" * 78)
    print("   AGENTIC RTL GENERATION & ADVERSARIAL VERIFICATION RESEARCH FRAMEWORK")
    print("   Gemini Designer + OpenAI Verifier + Real HDL Execution + Mutation Testing")
    print("=" * 78)

    # 1. Initialize Agents & Simulation Layer
    print("\n[Stage 0: Initialization]")
    designer = DesignerAgent()
    verifier = VerifierAgent()
    simulator = HDLSimulator()
    mutator = RTLMutator(simulator=simulator)

    print("  -> RTL Designer Agent:      Google Gemini (gemini-3.1-flash-lite / gemini-3.5-flash-lite)")
    print("  -> Adversarial Verifier:    OpenAI (gpt-4o-mini)")
    print(f"  -> Execution Layer:         {'Native Icarus/Verilator Toolchain' if simulator.has_native_simulator() else 'Cycle-Accurate Behavioral Simulation Engine'}")
    print("  -> Mutation Testing Engine: Standardized 10-mutant suite (AOR, ROR, COR, BIF, OFF, RST, STA, MOR)")
    print("  -> Orchestration Engine:    LangGraph Closed-Loop StateGraph")

    # 2. Closed-Loop Dual-Agent Pipeline Execution on FIFO
    print("\n" + "=" * 78)
    print("   PHASE 1: CLOSED-LOOP DUAL-AGENT PIPELINE EXECUTION (FIFO BENCHMARK)")
    print("=" * 78)
    spec_fifo = load_benchmark("fifo_sync")

    graph = build_rtl_verification_graph(
        designer=designer,
        verifier=verifier,
        simulator=simulator,
        mutator=mutator,
    )

    initial_state: RTLState = {
        "spec": spec_fifo,
        "iteration": 0,
        "max_iterations": 3,
        "rtl_code": "",
        "testbench_code": "",
        "compile_success": False,
        "compile_errors": [],
        "sim_result": None,
        "mutation_result": None,
        "coverage_metrics": None,
        "feedback": "",
        "final_report": "",
        "history": [],
        "repair_records": [],
        "pre_repair_rtl": None,
    }

    final_state = graph.invoke(initial_state)

    # 3. Controlled Failure-to-Repair Demonstration
    print("\n" + "=" * 78)
    print("   PHASE 2: CONTROLLED FAILURE-TO-REPAIR TRAJECTORY DEMONSTRATION")
    print("=" * 78)
    buggy_fifo_code = """
module fifo_sync #(parameter DATA_WIDTH=8, FIFO_DEPTH=16) (
    input wire clk, rst_n, wr_en, rd_en,
    input wire [DATA_WIDTH-1:0] wr_data,
    output reg [DATA_WIDTH-1:0] rd_data,
    output wire full, empty, almost_full, almost_empty,
    output reg [4:0] count
);
    reg [DATA_WIDTH-1:0] mem [0:FIFO_DEPTH-1];
    reg [3:0] wr_ptr, rd_ptr;

    // INJECTED BOUNDARY DEFECT: Premature full flag at 15 instead of 16
    assign full = (count == FIFO_DEPTH - 1);
    assign empty = (count == 0);
    assign almost_full = (count >= 14);
    assign almost_empty = (count <= 2);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr <= 0; rd_ptr <= 0; count <= 0; rd_data <= 0;
        end else begin
            if (wr_en && !full && (!rd_en || empty)) begin
                mem[wr_ptr] <= wr_data;
                wr_ptr <= wr_ptr + 1'b1;
                count <= count + 1'b1;
            end else if (rd_en && !empty && (!wr_en || full)) begin
                rd_data <= mem[rd_ptr];
                rd_ptr <= rd_ptr + 1'b1;
                count <= count - 1'b1;
            end else if (wr_en && rd_en && !full && !empty) begin
                mem[wr_ptr] <= wr_data;
                wr_ptr <= wr_ptr + 1'b1;
                rd_data <= mem[rd_ptr];
                rd_ptr <= rd_ptr + 1'b1;
            end
        end
    end
endmodule
    """.strip()

    repair_demo = run_failure_to_repair_demo(
        spec=spec_fifo,
        buggy_rtl=buggy_fifo_code,
        designer=designer,
        verifier=verifier,
        simulator=simulator,
    )

    # 4. Comparative Research Evaluation across All Benchmarks
    print("\n" + "=" * 78)
    print("   PHASE 3: RIGOROUS THREE-METHODOLOGY BENCHMARK COMPARISON")
    print("=" * 78)
    evaluator = ResearchEvaluator(designer=designer, verifier=verifier, simulator=simulator)
    df_consolidated, df_mutants, df_faults = evaluator.run_complete_evaluation(
        benchmark_names=["fifo_sync", "traffic_light", "alu_8bit"]
    )

    # 5. Display Consolidated Results
    print("\n" + "=" * 78)
    print("               CONSOLIDATED RESEARCH RESULTS TABLE")
    print("=" * 78)
    print(df_consolidated.to_string(index=False))

    # 6. Display Controlled Fault Injection Results
    print("\n" + "=" * 78)
    print("            CONTROLLED FAULT INJECTION DETECTION TABLE (12 DEFECTS)")
    print("=" * 78)
    cols_fault = ["Fault ID", "Benchmark", "Category", "Fault Description", "Baseline 1 (Gen-Only)", "Baseline 2 (Self-Verif)", "Proposed (Dual-Agent)"]
    print(df_faults[cols_fault].to_string(index=False))

    # 7. Display Sample of Detailed Mutant-Level Report
    print("\n" + "=" * 78)
    print("           STANDARDIZED MUTANT-LEVEL TRACEABILITY REPORT (SAMPLE)")
    print("=" * 78)
    cols_mut = ["Mutant ID", "Benchmark", "Operator", "Category", "Line", "Baseline 1", "Baseline 2", "Proposed", "Detecting Assertion"]
    print(df_mutants[cols_mut].head(15).to_string(index=False))

    # 8. Generate Multi-Panel Publication Figures
    print("\n[Plotting] Generating publication-grade research figures...")
    evaluator.plot_comparative_charts(df_consolidated, df_faults, output_path="research_evaluation.png")

    print("\n" + "=" * 78)
    print("   RESEARCH EVALUATION RUN COMPLETE | ALL RESULTS FULLY EXECUTABLE")
    print("=" * 78)


if __name__ == "__main__":
    main()
