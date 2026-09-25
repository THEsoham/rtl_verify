from __future__ import annotations

import pytest
from rtl_verify.pipeline.result_parser import ResultParser


class TestResultParser:
    def test_parse_all_passed(self):
        stdout = """Test 1: checking reset... OK
Test 2: checking enable... OK
ALL TESTS PASSED"""
        result = ResultParser.parse_simulation_output(stdout, "")
        assert result.passed is True

    def test_parse_tests_failed(self):
        stdout = """Test 1: checking reset... OK
ERROR: Expected count=10, got 5
TESTS FAILED: 1 errors"""
        result = ResultParser.parse_simulation_output(stdout, "")
        assert result.passed is False
        assert result.failed_tests >= 1

    def test_parse_fatal(self):
        stderr = "testbench.sv:42: $fatal: assertion failed"
        result = ResultParser.parse_simulation_output("", stderr)
        assert result.passed is False

    def test_extract_compile_errors(self):
        stderr = """design.sv:10: syntax error
design.sv:15: Unknown module type: foo"""
        errors = ResultParser.extract_compile_errors(stderr)
        assert len(errors) == 2

    def test_build_feedback_compile_error(self):
        from rtl_verify.verification.iverilog import CompileResult

        compile_result = CompileResult(
            success=False,
            stdout="",
            stderr="design.sv:10: syntax error",
            errors=["design.sv:10: syntax error"],
            warnings=[],
        )
        feedback = ResultParser.build_designer_feedback(compile_result=compile_result)
        assert "syntax error" in feedback
        assert "compile" in feedback.lower() or "compilation" in feedback.lower()


class TestBenchmarkRegistry:
    def test_load_all(self):
        from rtl_verify.benchmarks.registry import BenchmarkRegistry

        registry = BenchmarkRegistry()
        specs = registry.load_all()
        assert len(specs) >= 6

    def test_get_alu(self):
        from rtl_verify.benchmarks.registry import BenchmarkRegistry

        registry = BenchmarkRegistry()
        alu = registry.get("4-bit ALU")
        assert alu.category == "combinational"

    def test_to_prompt_description(self):
        from rtl_verify.benchmarks.registry import BenchmarkRegistry

        registry = BenchmarkRegistry()
        alu = registry.get("4-bit ALU")
        desc = alu.to_prompt_description()
        assert "opcode" in desc.lower()
        assert len(desc) > 100
