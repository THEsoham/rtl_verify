// STATUS: UNREVIEWED - Awaiting user review and test before running experiments.
// Testbench: fifo_sync self-checking testbench adhering to fixed verification contract.

`timescale 1ns/1ps

module tb;
    localparam DATA_WIDTH = 8;
    localparam FIFO_DEPTH = 16;
    localparam ALMOST_FULL_THRESH = 14;
    localparam ALMOST_EMPTY_THRESH = 2;

    reg                  clk;
    reg                  rst_n;
    reg                  wr_en;
    reg [DATA_WIDTH-1:0] wr_data;
    reg                  rd_en;

    wire [DATA_WIDTH-1:0] rd_data;
    wire                  full;
    wire                  empty;
    wire                  almost_full;
    wire                  almost_empty;
    wire [4:0]            count;

    integer errors = 0;
    integer i;

    TopModule #(
        .DATA_WIDTH(DATA_WIDTH),
        .FIFO_DEPTH(FIFO_DEPTH),
        .ALMOST_FULL_THRESH(ALMOST_FULL_THRESH),
        .ALMOST_EMPTY_THRESH(ALMOST_EMPTY_THRESH)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .wr_en(wr_en),
        .wr_data(wr_data),
        .rd_en(rd_en),
        .rd_data(rd_data),
        .full(full),
        .empty(empty),
        .almost_full(almost_full),
        .almost_empty(almost_empty),
        .count(count)
    );

    always #5 clk = ~clk;

    initial begin
        clk = 0;
        rst_n = 0;
        wr_en = 0;
        rd_en = 0;
        wr_data = 0;

        repeat (3) @(posedge clk);
        rst_n = 1;
        @(posedge clk); #1;

        // Check reset state
        if (!empty || full || count !== 5'd0 || !almost_empty) begin
            $display("ERROR: Initial reset flags wrong: empty=%b full=%b count=%d", empty, full, count);
            errors = errors + 1;
        end

        // Write 16 elements
        for (i = 0; i < 16; i = i + 1) begin
            @(posedge clk);
            wr_en   <= 1'b1;
            wr_data <= i + 8'h10;
            rd_en   <= 1'b0;
        end

        @(posedge clk);
        wr_en <= 1'b0;
        #1;

        if (!full || empty || count !== 5'd16 || !almost_full) begin
            $display("ERROR: After 16 writes, full=%b empty=%b count=%d", full, empty, count);
            errors = errors + 1;
        end

        // Overflow test: attempt write when full
        @(posedge clk);
        wr_en   <= 1'b1;
        wr_data <= 8'hFF;
        @(posedge clk);
        wr_en <= 1'b0;
        #1;
        if (count !== 5'd16 || !full) begin
            $display("ERROR: Overflow corrupted count=%d full=%b", count, full);
            errors = errors + 1;
        end

        // Read 16 elements and verify FIFO ordering
        @(posedge clk);
        rd_en <= 1'b1;
        wr_en <= 1'b0;
        for (i = 0; i < 16; i = i + 1) begin
            @(posedge clk); #1;
            if (rd_data !== (i + 8'h10)) begin
                $display("ERROR: Read index %0d expected %h, got %h", i, (i + 8'h10), rd_data);
                errors = errors + 1;
            end
        end
        rd_en <= 1'b0;
        #1;

        if (!empty || full || count !== 5'd0) begin
            $display("ERROR: After 16 reads, empty=%b full=%b count=%d", empty, full, count);
            errors = errors + 1;
        end

        // Simultaneous read and write test
        // First, write 1 item
        @(posedge clk);
        wr_en <= 1'b1;
        wr_data <= 8'hA1;
        @(posedge clk);
        wr_en <= 1'b0;
        #1;

        // Now assert both wr_en and rd_en
        @(posedge clk);
        wr_en <= 1'b1;
        wr_data <= 8'hB2;
        rd_en <= 1'b1;
        @(posedge clk); #1;
        if (rd_data !== 8'hA1) begin
            $display("ERROR: Simultaneous RW got read %h, expected 8'hA1", rd_data);
            errors = errors + 1;
        end
        if (count !== 5'd1) begin
            $display("ERROR: Simultaneous RW count=%d, expected 1", count);
            errors = errors + 1;
        end

        wr_en <= 1'b0;
        rd_en <= 1'b0;
        #20;

        if (errors == 0) begin
            $display("*** TEST RESULT: PASS ***");
        end else begin
            $display("*** TEST RESULT: FAIL ***");
        end
        $finish;
    end

endmodule
