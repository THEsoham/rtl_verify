`timescale 1ns/1ps

module tb;
    // 1. Declare inputs as regs, outputs as wires
    reg        clk;
    reg        reset;
    wire [3:0] q;

    // 2. Instantiate TopModule dut
    TopModule dut (
        .clk(clk),
        .reset(reset),
        .q(q)
    );

    // Clock generation: 10ns period
    always #5 clk = ~clk;

    // 3. Stimulus & self-checking
    integer errors = 0;
    integer i;

    initial begin
        // Initialize signals
        clk = 0;
        reset = 0;

        // Apply reset
        @(posedge clk);
        reset = 1;
        @(posedge clk);
        
        // Check reset value (should be 1)
        if (q !== 4'd1) begin
            $display("Time %0t: Reset error. Expected q = 1, got q = %0d", $time, q);
            errors = errors + 1;
        end

        // Release reset
        reset = 0;

        // Verify sequence: counter should count 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 1 -> ...
        // We will check two full cycles of the decade counter (20 cycles total)
        for (i = 1; i <= 20; i = i + 1) begin
            @(posedge clk);
            #1; // Small delay to sample after clock edge
            
            // Expected value calculation (1 to 10 repeating)
            // Using modulo arithmetic mapping: 1, 2, ..., 10
            // ((i - 1) % 10) + 1
            $display("Time %0t: Cycle %0d, q = %0d", $time, i, q);
        end

        // Let's do a rigorous check over a specific set of expected values
        // Reset again to start a clean sequence
        @(posedge clk);
        reset = 1;
        @(posedge clk);
        reset = 0;

        // Expected sequence starting right after reset release:
        // After reset is high at clock N, at clock N+1 q is 1.
        // Let's trace step by step:
        // T0 (reset=1 posedge): q <= 1
        // T1 (reset=0 posedge): q <= 2
        // T2 (posedge): q <= 3
        // T3 (posedge): q <= 4
        // T4 (posedge): q <= 5
        // T5 (posedge): q <= 6
        // T6 (posedge): q <= 7
        // T7 (posedge): q <= 8
        // T8 (posedge): q <= 9
        // T9 (posedge): q <= 10
        // T10 (posedge): q <= 1

        @(posedge clk); #1; if (q !== 4'd2) errors = errors + 1;
        @(posedge clk); #1; if (q !== 4'd3) errors = errors + 1;
        @(posedge clk); #1; if (q !== 4'd4) errors = errors + 1;
        @(posedge clk); #1; if (q !== 4'd5) errors = errors + 1;
        @(posedge clk); #1; if (q !== 4'd6) errors = errors + 1;
        @(posedge clk); #1; if (q !== 4'd7) errors = errors + 1;
        @(posedge clk); #1; if (q !== 4'd8) errors = errors + 1;
        @(posedge clk); #1; if (q !== 4'd9) errors = errors + 1;
        @(posedge clk); #1; if (q !== 4'd10) errors = errors + 1;
        @(posedge clk); #1; if (q !== 4'd1) errors = errors + 1;

        // Test asynchronous/synchronous reset assertion in the middle of counting
        @(posedge clk);
        reset = 1;
        @(posedge clk);
        #1;
        if (q !== 4'd1) begin
            $display("Time %0t: Mid-stream reset error. Expected q = 1, got q = %0d", $time, q);
            errors = errors + 1;
        end

        // Final result evaluation
        if (errors == 0) begin
            $display("*** TEST RESULT: PASS ***");
        end else begin
            $display("*** TEST RESULT: FAIL ***");
        end
        $finish;
    end

endmodule