"""Unit tests for VerilogMutator."""

import pytest
from v2.src.verilog_sim import VerilogSimulator
from v2.src.mutator import VerilogMutator, Mutant

SIM_PATH = r"d:\rtl-verification\tools\iverilog\app\bin\iverilog.exe"
VVP_PATH = r"d:\rtl-verification\tools\iverilog\app\bin\vvp.exe"


@pytest.fixture
def mutator():
    sim = VerilogSimulator(iverilog_path=SIM_PATH, vvp_path=VVP_PATH)
    return VerilogMutator(sim)


def test_mutant_generation(mutator):
    code = """
module TopModule (
    input clk,
    input rst,
    input [7:0] a,
    input [7:0] b,
    output reg [7:0] y
);
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            y <= 8'd0;
        end else if (a == b) begin
            y <= a + b;
        end else begin
            y <= a - b;
        end
    end
endmodule
"""
    mutants = mutator.generate_mutants(code, max_mutants=8)
    assert len(mutants) > 0
    operators = {m.operator for m in mutants}
    # Should generate multiple diverse operators (AOR, ROR, etc.)
    assert len(operators) >= 2


def test_mutant_validation_and_equivalence(mutator):
    golden_rtl = """
module TopModule (
    input a,
    input b,
    output y
);
    assign y = a ^ b;
endmodule
"""
    # Golden testbench
    golden_tb = """
`timescale 1ns/1ps
module tb;
    reg a, b;
    wire y;

    TopModule dut (.a(a), .b(b), .y(y));

    initial begin
        a = 0; b = 0; #10;
        if (y !== 0) $display("MISMATCH");
        a = 0; b = 1; #10;
        if (y !== 1) $display("MISMATCH");
        a = 1; b = 0; #10;
        if (y !== 1) $display("MISMATCH");
        a = 1; b = 1; #10;
        if (y !== 0) $display("MISMATCH");
        $finish;
    end
endmodule
"""
    mutants = mutator.generate_mutants(golden_rtl, max_mutants=5)
    validated = mutator.validate_and_filter_mutants(mutants, golden_rtl)
    assert len(validated) > 0
    # Every mutant should compile and be flagged non-equivalent via differential simulation
    for m in validated:
        assert m.compiles
        assert not m.is_equivalent
    assert "total_generated" in mutator.last_exclusion_log
    assert mutator.last_exclusion_log["valid_non_equivalent"] == len(validated)
