from __future__ import annotations
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rtl_verify.verification.iverilog import CompileResult
    from rtl_verify.verification.coverage import CoverageReport

@dataclass
class ParsedSimResult:
    passed: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    errors: list[str]
    warnings: list[str]
    assertions_failed: list[str]
    simulation_time: str | None

class ResultParser:
    @staticmethod
    def parse_simulation_output(stdout: str, stderr: str) -> ParsedSimResult:
        passed = False
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        errors = []
        warnings = []
        assertions_failed = []
        simulation_time = None
        
        full_output = stdout + "\n" + stderr
        
        if "ALL TESTS PASSED" in full_output:
            passed = True
        elif "TESTS FAILED" in full_output or "$error" in full_output or "$fatal" in full_output:
            passed = False
            
        for line in full_output.splitlines():
            line = line.strip()
            if "ERROR:" in line or "FAIL:" in line or "$error" in line or "$fatal" in line:
                errors.append(line)
                failed_tests += 1
            if "WARNING:" in line or "$warning" in line:
                warnings.append(line)
            if "Assertion failed" in line or "assert" in line.lower() and "fail" in line.lower():
                assertions_failed.append(line)
                
            time_match = re.search(r'Time:\s*(\d+\s*\w*)', line)
            if time_match:
                simulation_time = time_match.group(1)
                
        total_tests = passed_tests + failed_tests
        
        return ParsedSimResult(
            passed=passed,
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            errors=errors,
            warnings=warnings,
            assertions_failed=assertions_failed,
            simulation_time=simulation_time
        )
        
    @staticmethod
    def extract_compile_errors(stderr: str) -> list[str]:
        _ERROR_PATTERNS = {"error", "syntax", "unknown", "undefined", "undeclared", "not found", "cannot"}
        return [
            line.strip()
            for line in stderr.splitlines()
            if any(pat in line.lower() for pat in _ERROR_PATTERNS)
        ]
        
    @staticmethod
    def build_designer_feedback(
        compile_result: CompileResult | None = None,
        sim_result: ParsedSimResult | None = None,
        coverage: CoverageReport | None = None,
    ) -> str:
        feedback = []
        
        if compile_result and not compile_result.success:
            feedback.append("Compilation Failed.")
            if compile_result.errors:
                feedback.append("Errors:")
                feedback.extend([f"- {err}" for err in compile_result.errors])
            else:
                feedback.append(compile_result.stderr)
            return "\n".join(feedback)
            
        if sim_result and not sim_result.passed:
            feedback.append("Simulation Failed.")
            if sim_result.errors:
                feedback.append("Errors found during simulation:")
                feedback.extend([f"- {err}" for err in sim_result.errors])
            if sim_result.assertions_failed:
                feedback.append("Assertion Failures:")
                feedback.extend([f"- {a}" for a in sim_result.assertions_failed])
        elif sim_result and sim_result.passed:
            feedback.append("Simulation Passed!")
            
        if coverage:
            if coverage.line_coverage is not None:
                feedback.append(f"Coverage: Line={coverage.line_coverage}%")
            if coverage.branch_coverage is not None:
                feedback.append(f"Coverage: Branch={coverage.branch_coverage}%")
            if coverage.uncovered_lines:
                feedback.append("Some lines remain uncovered. Consider adding tests for:")
                for f, l in coverage.uncovered_lines[:5]:
                    feedback.append(f"- {f}:{l}")
                    
        return "\n".join(feedback)
