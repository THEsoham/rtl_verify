"""
Agentic RTL Generation and Verification Framework
=================================================
Dual-agent adversarial verification framework using LangGraph,
Gemini (Designer), OpenAI (Verifier), real HDL execution, and Mutation Testing.
"""

from .designer import DesignerAgent
from .verifier import VerifierAgent
from .simulator import HDLSimulator, SimulationResult, BehavioralModuleSimulator
from .mutator import RTLMutator, Mutant, MutationResult
from .coverage import CoverageTracker, CoverageMetrics, analyze_coverage_fault_gap
from .fault_injection import ControlledFaultEngine, ControlledFault
from .graph import build_rtl_verification_graph, RTLState, run_failure_to_repair_demo
from .evaluation import ResearchEvaluator, BenchmarkMethodResult

__all__ = [
    "DesignerAgent",
    "VerifierAgent",
    "HDLSimulator",
    "SimulationResult",
    "BehavioralModuleSimulator",
    "RTLMutator",
    "Mutant",
    "MutationResult",
    "CoverageTracker",
    "CoverageMetrics",
    "analyze_coverage_fault_gap",
    "ControlledFaultEngine",
    "ControlledFault",
    "build_rtl_verification_graph",
    "RTLState",
    "run_failure_to_repair_demo",
    "ResearchEvaluator",
    "BenchmarkMethodResult",
]
