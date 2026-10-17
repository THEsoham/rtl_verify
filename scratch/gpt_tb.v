`timescale 1ns/1ps

module tb;
    reg clk;
    reg reset;
    wire [3:0] q;

    // Instantiate TopModule dut
    TopModule dut (
        .clk(clk),
        .reset(reset),
        .q(q)
    );

    // Clock generation: 10ns period
    always #5 clk = ~clk;

    integer errors = 0;
    integer i;

    initial begin
        clk = 0;
        reset = 1;

        // Test 1: Reset behavior
        // At the first positive edge with reset=1, q should become 1.
        #12;
        if (q !== 4'd1) begin
            $display("ERROR: Reset failed. Expected q=1, got q=%d", q);
            errors = errors + 1;
        end

        // Release reset
        reset = 0;
        #2;

        // Test 2: Sequential counting through the full decade cycle (1 to 10 and wrap to 1)
        // Expected sequence after reset release:
        // Current: 1
        // Clock 1: 2
        // Clock 2: 3
        // Clock 3: 4
        // Clock 4: 5
        // Clock 5: 6
        // Clock 6: 7
        // Clock 7: 8
        // Clock 8: 9
        // Clock 9: 10 (4'b1010)
        // Clock 10: 1 (wrapped)

        for (i = 2; i <= 10; i = i + 1) begin
            @(posedge clk);
            #1; // Wait slightly past posedge to sample updated Q
            if (q !== i[3:0]) begin
                $display("ERROR: Count mismatch during increment. Expected %d, got %d", i, q);
                errors = errors + 1;
            end
        end

        // Clock 10 should wrap back to 1
        @(posedge clk);
        #1;
        if (q !== 4'd1) begin
            $display("ERROR: Wrap-around failed after 10. Expected 1, got %d", q);
            errors = errors + 1;
        end

        // Test 3: Asynchronous/Synchronous reset interruption during count
        @(posedge clk);
        #1; // q should be 2 now
        reset = 1;
        @(posedge clk);
        #1;
        if (q !== 4'd1) begin
            $display("ERROR: Synchronous reset during count failed. Expected 1, got %d", q);
            errors = errors + 1;
        end

        // Final result reporting
        if (errors == 0) begin
            $display("*** TEST RESULT: PASS ***");
        end else begin
            $display("*** TEST RESULT: FAIL ***");
        end

        $finish;
    end

endmodule