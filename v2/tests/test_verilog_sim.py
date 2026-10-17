"""Unit tests for VerilogSimulator."""

import os
import pytest
from v2.src.verilog_sim import VerilogSimulator, SimResult

SIM_PATH = r"d:\rtl-verification\tools\iverilog\app\bin\iverilog.exe"
VVP_PATH = r"d:\rtl-verification\tools\iverilog\app\bin\vvp.exe"


@pytest.fixture
def sim():
    return VerilogSimulator(iverilog_path=SIM_PATH, vvp_path=VVP_PATH)


def test_clean_combinational_sim(sim):
    dut = """
module TopModule (
    input a,
    input b,
    output y
);
    assign y = a ^ b;
endmodule
"""
    tb = """
`timescale 1ns/1ps
module tb;
    reg a, b;
    wire y;

    TopModule dut (.a(a), .b(b), .y(y));

    initial begin
        a = 0; b = 0; #10;
        if (y !== 0) $display("FAIL: 0^0 != 0");
        a = 0; b = 1; #10;
        if (y !== 1) $display("FAIL: 0^1 != 1");
        a = 1; b = 0; #10;
        if (y !== 1) $display("FAIL: 1^0 != 1");
        a = 1; b = 1; #10;
        if (y !== 0) $display("FAIL: 1^1 != 0");
        $display("ALL TESTS PASSED");
        $finish;
    end
endmodule
"""
    res = sim.compile_and_run(dut, tb)
    assert res.compile_ok
    assert res.sim_ok
    assert res.passed
    assert res.mismatches == 0
    assert "ALL TESTS PASSED" in res.sim_stdout


def test_failing_sim_detects_mismatch(sim):
    # Buggy DUT: AND instead of XOR
    dut = """
module TopModule (
    input a,
    input b,
    output y
);
    assign y = a & b;
endmodule
"""
    tb = """
`timescale 1ns/1ps
module tb;
    reg a, b;
    wire y;

    TopModule dut (.a(a), .b(b), .y(y));

    initial begin
        a = 0; b = 1; #10;
        if (y !== 1) $display("MISMATCH DETECTED: expected 1, got %b", y);
        $finish;
    end
endmodule
"""
    res = sim.compile_and_run(dut, tb)
    assert res.compile_ok
    assert not res.passed
    assert res.mismatches > 0


def test_syntax_error_compilation(sim):
    dut = "this is not valid verilog code;"
    tb = "module tb; endmodule"
    res = sim.compile_and_run(dut, tb)
    assert not res.compile_ok
    assert not res.passed
    assert len(res.compile_stderr) > 0


def test_contract_pass(sim):
    dut = "module TopModule(input a, output y); assign y = a; endmodule"
    tb = """`timescale 1ns/1ps
module tb;
    reg a; wire y;
    TopModule dut(.a(a), .y(y));
    initial begin
        a = 1; #10;
        $display("*** TEST RESULT: PASS ***");
        $finish;
    end
endmodule"""
    res = sim.compile_and_run(dut, tb, enforce_contract=True)
    assert res.compile_ok
    assert res.contract_valid
    assert res.passed
    assert res.contract_error == ""


def test_contract_fail(sim):
    dut = "module TopModule(input a, output y); assign y = a; endmodule"
    tb = """`timescale 1ns/1ps
module tb;
    reg a; wire y;
    TopModule dut(.a(a), .y(y));
    initial begin
        a = 1; #10;
        $display("*** TEST RESULT: FAIL ***");
        $finish;
    end
endmodule"""
    res = sim.compile_and_run(dut, tb, enforce_contract=True)
    assert res.compile_ok
    assert res.contract_valid
    assert not res.passed
    assert res.contract_error == ""


def test_contract_rejection_missing_status(sim):
    dut = "module TopModule(input a, output y); assign y = a; endmodule"
    # Doesn't print *** TEST RESULT: PASS *** or FAIL
    tb = """`timescale 1ns/1ps
module tb;
    reg a; wire y;
    TopModule dut(.a(a), .y(y));
    initial begin
        a = 1; #10;
        $display("Done without contract");
        $finish;
    end
endmodule"""
    res = sim.compile_and_run(dut, tb, enforce_contract=True)
    assert res.compile_ok
    assert not res.contract_valid
    assert "Missing" in res.contract_error
    assert not res.passed


def test_contract_rejection_multiple_status(sim):
    dut = "module TopModule(input a, output y); assign y = a; endmodule"
    # Prints both PASS and FAIL
    tb = """`timescale 1ns/1ps
module tb;
    reg a; wire y;
    TopModule dut(.a(a), .y(y));
    initial begin
        a = 1; #10;
        $display("*** TEST RESULT: PASS ***");
        $display("*** TEST RESULT: FAIL ***");
        $finish;
    end
endmodule"""
    res = sim.compile_and_run(dut, tb, enforce_contract=True)
    assert res.compile_ok
    assert not res.contract_valid
    assert "Both PASS and FAIL" in res.contract_error
    assert not res.passed

