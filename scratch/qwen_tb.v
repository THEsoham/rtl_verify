`timescale 1ns/1ps

module tb;
    // 1. Declare inputs as regs, outputs as wires
    reg clk;
    reg reset;
    wire [3:0] q;

    // 2. Instantiate TopModule dut ( ... );
    TopModule dut (
        .clk(clk),
        .reset(reset),
        .q(q)
    );

    // 3. Stimulus & self-checking:
    integer errors = 0;
    initial begin
        // Test reset functionality
        reset <= 1;
        #10;
        if (q != 4'b0001) begin
            errors = errors + 1;
        end

        // Test counting from 1 to 10
        reset <= 0;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        if (q != 4'b1000) begin
            errors = errors + 1;
        end

        // Test counting beyond 10
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        if (q != 4'b1000) begin
            errors = errors + 1;
        end

        // Test counting from 10 to 1
        reset <= 1;
        #10;
        reset <= 0;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        if (q != 4'b0001) begin
            errors = errors + 1;
        end

        // Test counting beyond 1
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        clk <= 1;
        #10;
        clk <= 0;
        #10;
        if (q != 4'b0001) begin
            errors = errors + 1;
        end

        // Print test result
        if (errors == 0) begin
            $display("*** TEST RESULT: PASS ***");
        end else begin
            $display("*** TEST RESULT: FAIL ***");
        end

        // Terminate simulation
        $finish;
    end

endmodule