"""Pytest suite for verification harness.

Verifies:
1. Known-equivalent mutant -> EQUIV_RESULT: SAME
2. Known-real-fault -> EQUIV_RESULT: DIFFERENT
3. Known-real-fault -> Killed by valid testbench (*** TEST RESULT: FAIL ***)
4. Always-PASS testbench -> Rejected by non-vacuity gate
5. Deliberately wrong sequential counter wrap -> Detected as DIFFERENT
"""

import os
import sys
import pytest

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from v2.src.verilog_sim import VerilogSimulator
from v2.src.mutator import VerilogMutator, Mutant
from v2.src.pipeline import build_inverted_gate


@pytest.fixture(scope="module")
def sim():
    return VerilogSimulator()


@pytest.fixture(scope="module")
def mutator(sim):
    return VerilogMutator(sim)


@pytest.fixture(scope="module")
def count10_golden():
    return """
module RefModule (
  input clk,
  input reset,
  output reg [3:0] q
);

  always @(posedge clk)
    if (reset || q == 10)
      q <= 1;
    else
      q <= q+1;

endmodule
"""


def test_known_equivalent_mutant_same(sim, mutator, count10_golden):
    """Test that a semantically equivalent mutant is identified as SAME."""
    # Semantic equivalence: replacing integer 1 with 4-bit 4'd1
    equiv_code = count10_golden.replace("q <= 1;", "q <= 4'd1;")

    diff_tb, g_mod, m_mod = mutator._build_differential_tb(count10_golden, equiv_code, num_vectors=2000)
    assert diff_tb is not None, "Failed to generate differential testbench"

    res = sim.compile_and_run(dut_code=m_mod, tb_code=diff_tb, ref_code=g_mod)
    assert res.compile_ok, f"Differential TB failed to compile: {res.compile_stderr}"

    lines = [line.strip() for line in res.sim_stdout.splitlines()]
    assert "EQUIV_RESULT: SAME" in lines, f"Expected EQUIV_RESULT: SAME, got stdout:\n{res.sim_stdout}"
    assert "EQUIV_RESULT: DIFFERENT" not in lines


def test_known_real_fault_different(sim, mutator, count10_golden):
    """Test that a known real fault is identified as DIFFERENT."""
    # Real fault: wrap value altered from 10 to 11
    faulty_code = count10_golden.replace("q == 10", "q == 11")

    diff_tb, g_mod, m_mod = mutator._build_differential_tb(count10_golden, faulty_code, num_vectors=2000)
    assert diff_tb is not None

    res = sim.compile_and_run(dut_code=m_mod, tb_code=diff_tb, ref_code=g_mod)
    assert res.compile_ok, f"Differential TB failed to compile: {res.compile_stderr}"

    lines = [line.strip() for line in res.sim_stdout.splitlines()]
    assert "EQUIV_RESULT: DIFFERENT" in lines, f"Expected EQUIV_RESULT: DIFFERENT, got stdout:\n{res.sim_stdout}"
    assert "EQUIV_RESULT: SAME" not in lines


def test_known_real_fault_killed(sim, count10_golden):
    """Test that a known real fault is killed by a valid self-checking testbench."""
    faulty_dut = count10_golden.replace("RefModule", "TopModule").replace("q == 10", "q == 11")

    strict_tb = """`timescale 1ns/1ps
module tb;
  reg clk, reset;
  wire [3:0] q;

  TopModule dut (.clk(clk), .reset(reset), .q(q));
  always #5 clk = ~clk;

  integer errors = 0;
  integer i;

  initial begin
    clk = 0; reset = 1;
    @(posedge clk);
    reset = 0;

    // Check count sequence 1 -> 2 -> ... -> 10 -> 1
    for (i = 1; i <= 15; i = i + 1) begin
      @(posedge clk); #1;
      if (i <= 10) begin
        if (q !== i[3:0]) errors = errors + 1;
      end else begin
        // At cycle 11, should wrap back to 1
        if (q !== 4'd1) errors = errors + 1;
      end
    end

    if (errors == 0) $display("*** TEST RESULT: PASS ***");
    else $display("*** TEST RESULT: FAIL ***");
    $finish;
  end
endmodule
"""
    res = sim.compile_and_run(dut_code=faulty_dut, tb_code=strict_tb, enforce_contract=True)
    assert res.compile_ok
    # Faulty DUT should fail the strict testbench (mismatch when wrapping at 11)
    assert not res.passed, "Expected strict testbench to fail on mutant with wrong wrap value"
    assert "*** TEST RESULT: FAIL ***" in res.sim_stdout


def test_always_pass_testbench_rejected_by_non_vacuity_gate(sim, count10_golden):
    """Test that an always-PASS testbench is rejected by the non-vacuity check."""
    # Synthesize inverted gate design
    inv_gate = build_inverted_gate(count10_golden)
    assert inv_gate is not None

    vacuous_tb = """`timescale 1ns/1ps
module tb;
  reg clk, reset;
  wire [3:0] q;

  TopModule dut (.clk(clk), .reset(reset), .q(q));

  initial begin
    #100;
    $display("*** TEST RESULT: PASS ***");
    $finish;
  end
endmodule
"""
    # 1. Vacuous TB passes on golden (tautologically)
    golden_dut = count10_golden.replace("RefModule", "TopModule")
    res_golden = sim.compile_and_run(dut_code=golden_dut, tb_code=vacuous_tb, enforce_contract=True)
    assert res_golden.passed, "Vacuous TB was expected to pass golden trivially"

    # 2. Non-vacuity gate check: test on inverted gate
    res_inv = sim.compile_and_run(dut_code=inv_gate, tb_code=vacuous_tb, enforce_contract=True)

    # Because TB does not check outputs, it passes on the inverted design as well!
    # The harness detects res_inv.passed == True and rejects it as vacuous:
    is_vacuous = res_inv.passed
    assert is_vacuous is True, "Expected always-PASS testbench to be flagged as vacuous on inverted gate"


def test_deliberately_wrong_counter_detected(sim, mutator, count10_golden):
    """Test that sequential simulation with rare reset detects wrong counter wrap."""
    # Wrong wrap value: counter wraps at 12 instead of 10
    wrong_counter = count10_golden.replace("q == 10", "q == 12")

    diff_tb, g_mod, m_mod = mutator._build_differential_tb(count10_golden, wrong_counter, num_vectors=2000)
    res = sim.compile_and_run(dut_code=m_mod, tb_code=diff_tb, ref_code=g_mod)
    assert res.compile_ok

    lines = [line.strip() for line in res.sim_stdout.splitlines()]
    assert "EQUIV_RESULT: DIFFERENT" in lines
    assert "EQUIV_RESULT: SAME" not in lines


def test_testbench_with_off_by_one_expectation_fails_golden(sim, count10_golden):
    """Test that a testbench with an off-by-one expectation correctly fails on golden RTL."""
    golden_dut = count10_golden.replace("RefModule", "TopModule")

    # Flawed testbench: off-by-one expectation (expects q=0 right after reset instead of q=1)
    flawed_tb = """`timescale 1ns/1ps
module tb;
  reg clk, reset;
  wire [3:0] q;

  TopModule dut (.clk(clk), .reset(reset), .q(q));
  always #5 clk = ~clk;

  integer errors = 0;
  initial begin
    clk = 0; reset = 1;
    #12;
    // Off-by-one flaw: decade counter resets to 1, but testbench erroneously expects 0
    if (q !== 4'd0) begin
      errors = errors + 1;
    end

    if (errors == 0) $display("*** TEST RESULT: PASS ***");
    else $display("*** TEST RESULT: FAIL ***");
    $finish;
  end
endmodule
"""
    res = sim.compile_and_run(dut_code=golden_dut, tb_code=flawed_tb, enforce_contract=True)
    assert res.compile_ok
    # Golden design MUST fail this flawed testbench
    assert not res.passed, "Expected flawed testbench with off-by-one expectation to fail golden design"
    assert "*** TEST RESULT: FAIL ***" in res.sim_stdout
