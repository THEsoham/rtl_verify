import subprocess
import os

code = """`timescale 1ns/1ps
module tb;
    reg clk;
    reg reset;
    wire [3:0] q;

    TopModule dut (
        .clk(clk),
        .reset(reset),
        .q(q)
    );

    integer errors = 0;
    initial begin
        reset <= 1;
        #10;
        $display("At t=%0t: reset=%b clk=%b q=%b", $time, reset, clk, q);
        $display("Evaluating (q != 4'b0001): %b", (q != 4'b0001));
        if (q != 4'b0001) errors = errors + 1;

        reset <= 0;
        repeat (7) begin
            clk <= 1; #10; clk <= 0; #10;
        end
        $display("At t=%0t: reset=%b clk=%b q=%b", $time, reset, clk, q);
        $display("Evaluating (q != 4'b1000): %b", (q != 4'b1000));
        if (q != 4'b1000) errors = errors + 1;

        repeat (5) begin
            clk <= 1; #10; clk <= 0; #10;
        end
        $display("At t=%0t: reset=%b clk=%b q=%b", $time, reset, clk, q);

        reset <= 1;
        #10;
        reset <= 0;
        repeat (7) begin
            clk <= 1; #10; clk <= 0; #10;
        end
        $display("At t=%0t: reset=%b clk=%b q=%b", $time, reset, clk, q);
        $display("Evaluating (q != 4'b0001): %b", (q != 4'b0001));
        if (q != 4'b0001) errors = errors + 1;

        $display("Final errors: %0d", errors);
        $finish;
    end
endmodule
"""
os.makedirs("scratch", exist_ok=True)
with open("scratch/qwen_trace.v", "w") as f:
    f.write(code)

subprocess.run(["tools/iverilog/app/bin/iverilog.exe", "-o", "scratch/trace.vvp", "scratch/qwen_trace.v", "scratch/top.v"])
sim = subprocess.run(["tools/iverilog/app/bin/vvp.exe", "scratch/trace.vvp"], capture_output=True, text=True)
print(sim.stdout)
