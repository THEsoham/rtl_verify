// STATUS: UNREVIEWED - Awaiting user review and test before running experiments.
// Module: fifo_sync (TopModule)
// Specification: Synchronous FIFO with status flags and boundary protection.

`timescale 1ns/1ps

module TopModule #(
    parameter DATA_WIDTH = 8,
    parameter FIFO_DEPTH = 16,
    parameter ALMOST_FULL_THRESH = 14,
    parameter ALMOST_EMPTY_THRESH = 2
)(
    input  wire                  clk,
    input  wire                  rst_n,
    input  wire                  wr_en,
    input  wire [DATA_WIDTH-1:0] wr_data,
    input  wire                  rd_en,
    output reg  [DATA_WIDTH-1:0] rd_data,
    output wire                  full,
    output wire                  empty,
    output wire                  almost_full,
    output wire                  almost_empty,
    output reg  [4:0]            count
);

    localparam ADDR_WIDTH = 4; // $clog2(16)

    reg [DATA_WIDTH-1:0] mem [0:FIFO_DEPTH-1];
    reg [ADDR_WIDTH-1:0] wr_ptr;
    reg [ADDR_WIDTH-1:0] rd_ptr;

    assign full         = (count == FIFO_DEPTH);
    assign empty        = (count == 5'd0);
    assign almost_full  = (count >= ALMOST_FULL_THRESH);
    assign almost_empty = (count <= ALMOST_EMPTY_THRESH);

    wire do_wr = wr_en && (!full || rd_en);
    wire do_rd = rd_en && !empty;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr  <= {ADDR_WIDTH{1'b0}};
            rd_ptr  <= {ADDR_WIDTH{1'b0}};
            count   <= 5'd0;
            rd_data <= {DATA_WIDTH{1'b0}};
        end else begin
            case ({wr_en && !full, rd_en && !empty})
                2'b10: begin // Write only
                    mem[wr_ptr] <= wr_data;
                    wr_ptr      <= wr_ptr + 1'b1;
                    count       <= count + 1'b1;
                end
                2'b01: begin // Read only
                    rd_data <= mem[rd_ptr];
                    rd_ptr  <= rd_ptr + 1'b1;
                    count   <= count - 1'b1;
                end
                2'b11: begin // Simultaneous read and write
                    mem[wr_ptr] <= wr_data;
                    rd_data     <= mem[rd_ptr];
                    wr_ptr      <= wr_ptr + 1'b1;
                    rd_ptr      <= rd_ptr + 1'b1;
                    // count remains unchanged
                end
                default: begin
                    // No valid operation or illegal overflow/underflow request
                end
            endcase
        end
    end

endmodule
