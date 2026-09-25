from __future__ import annotations

import asyncio
from pathlib import Path
import pytest
from rtl_verify.config import Settings


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_settings(tmp_path: Path):
    """Settings configured for testing with a temp work directory."""
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        work_dir=tmp_path / "workdir",
        log_level="DEBUG",
    )


@pytest.fixture
def sample_rtl():
    """A simple known-good Verilog module for testing."""
    return """
module counter (
    input wire clk,
    input wire rst_n,
    input wire enable,
    output reg [7:0] count
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count <= 8'b0;
        else if (enable)
            count <= count + 1;
    end
endmodule
"""


@pytest.fixture
def sample_testbench():
    """A simple testbench for the counter module."""
    return """
`timescale 1ns/1ps
module counter_tb;
    reg clk, rst_n, enable;
    wire [7:0] count;
    integer errors = 0;
    
    counter uut (.clk(clk), .rst_n(rst_n), .enable(enable), .count(count));
    
    initial clk = 0;
    always #5 clk = ~clk;
    
    initial begin
        rst_n = 0; enable = 0;
        #20 rst_n = 1;
        #10 enable = 1;
        #100;
        if (count != 8'd10) begin
            $display("ERROR: Expected count=10, got %d", count);
            errors = errors + 1;
        end
        #10;
        if (errors == 0)
            $display("ALL TESTS PASSED");
        else
            $display("TESTS FAILED: %0d errors", errors);
        $finish;
    end
endmodule
"""


@pytest.fixture
def sample_spec_yaml():
    """A minimal benchmark spec YAML string."""
    return """
name: "Test Counter"
category: "sequential"
difficulty: "easy"
description: |
  A simple 8-bit counter with enable and active-low reset.
ports:
  inputs:
    - { name: "clk", width: 1, description: "Clock" }
    - { name: "rst_n", width: 1, description: "Active-low reset" }
    - { name: "enable", width: 1, description: "Count enable" }
  outputs:
    - { name: "count", width: 8, description: "Counter value" }
requirements:
  - "Increment count on each clock when enabled"
  - "Reset count to 0 on active-low reset"
verification_hints:
  - "Test reset"
  - "Test enable/disable"
"""
