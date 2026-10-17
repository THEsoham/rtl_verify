// STATUS: UNREVIEWED - Awaiting user review and test before running experiments.
// Module: alu_8bit (TopModule)
// Specification: 8-bit registered ALU with 8 opcodes, flags, and 1-cycle pipeline latency.

`timescale 1ns/1ps

module TopModule #(
    parameter WIDTH = 8
)(
    input  wire             clk,
    input  wire             rst_n,
    input  wire             valid_in,
    input  wire [2:0]       opcode,
    input  wire [WIDTH-1:0] operand_a,
    input  wire [WIDTH-1:0] operand_b,
    output reg  [WIDTH-1:0] result,
    output reg              zero,
    output reg              carry_out,
    output reg              overflow,
    output reg              valid_out
);

    wire [WIDTH:0] add_ext = {1'b0, operand_a} + {1'b0, operand_b};
    wire [WIDTH:0] sub_ext = {1'b0, operand_a} - {1'b0, operand_b};

    always @(posedge clk) begin
        if (!rst_n) begin
            result    <= {WIDTH{1'b0}};
            zero      <= 1'b1;
            carry_out <= 1'b0;
            overflow  <= 1'b0;
            valid_out <= 1'b0;
        end else if (valid_in) begin
            valid_out <= 1'b1;
            case (opcode)
                3'b000: begin // ADD
                    result    <= add_ext[WIDTH-1:0];
                    carry_out <= add_ext[WIDTH];
                    overflow  <= (~(operand_a[7] ^ operand_b[7])) & (operand_a[7] ^ add_ext[7]);
                    zero      <= (add_ext[WIDTH-1:0] == {WIDTH{1'b0}});
                end
                3'b001: begin // SUB
                    result    <= sub_ext[WIDTH-1:0];
                    carry_out <= sub_ext[WIDTH];
                    overflow  <= (operand_a[7] ^ operand_b[7]) & (operand_a[7] ^ sub_ext[7]);
                    zero      <= (sub_ext[WIDTH-1:0] == {WIDTH{1'b0}});
                end
                3'b010: begin // AND
                    result    <= operand_a & operand_b;
                    carry_out <= 1'b0;
                    overflow  <= 1'b0;
                    zero      <= ((operand_a & operand_b) == {WIDTH{1'b0}});
                end
                3'b011: begin // OR
                    result    <= operand_a | operand_b;
                    carry_out <= 1'b0;
                    overflow  <= 1'b0;
                    zero      <= ((operand_a | operand_b) == {WIDTH{1'b0}});
                end
                3'b100: begin // XOR
                    result    <= operand_a ^ operand_b;
                    carry_out <= 1'b0;
                    overflow  <= 1'b0;
                    zero      <= ((operand_a ^ operand_b) == {WIDTH{1'b0}});
                end
                3'b101: begin // SHL
                    result    <= operand_a << operand_b[2:0];
                    carry_out <= 1'b0;
                    overflow  <= 1'b0;
                    zero      <= ((operand_a << operand_b[2:0]) == {WIDTH{1'b0}});
                end
                3'b110: begin // SHR
                    result    <= operand_a >> operand_b[2:0];
                    carry_out <= 1'b0;
                    overflow  <= 1'b0;
                    zero      <= ((operand_a >> operand_b[2:0]) == {WIDTH{1'b0}});
                end
                3'b111: begin // PASS_A
                    result    <= operand_a;
                    carry_out <= 1'b0;
                    overflow  <= 1'b0;
                    zero      <= (operand_a == {WIDTH{1'b0}});
                end
                default: begin
                    result    <= {WIDTH{1'b0}};
                    carry_out <= 1'b0;
                    overflow  <= 1'b0;
                    zero      <= 1'b1;
                end
            endcase
        end else begin
            valid_out <= 1'b0;
        end
    end

endmodule
