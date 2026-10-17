// STATUS: UNREVIEWED - Awaiting user review and test before running experiments.
// Testbench: alu_8bit self-checking testbench adhering to fixed verification contract.

`timescale 1ns/1ps

module tb;
    localparam WIDTH = 8;

    reg             clk;
    reg             rst_n;
    reg             valid_in;
    reg [2:0]       opcode;
    reg [WIDTH-1:0] operand_a;
    reg [WIDTH-1:0] operand_b;

    wire [WIDTH-1:0] result;
    wire             zero;
    wire             carry_out;
    wire             overflow;
    wire             valid_out;

    integer errors = 0;

    TopModule #(.WIDTH(WIDTH)) dut (
        .clk(clk),
        .rst_n(rst_n),
        .valid_in(valid_in),
        .opcode(opcode),
        .operand_a(operand_a),
        .operand_b(operand_b),
        .result(result),
        .zero(zero),
        .carry_out(carry_out),
        .overflow(overflow),
        .valid_out(valid_out)
    );

    always #5 clk = ~clk;

    task check_alu;
        input [2:0]       op;
        input [WIDTH-1:0] a;
        input [WIDTH-1:0] b;
        input [WIDTH-1:0] exp_res;
        input             exp_zero;
        input             exp_co;
        input             exp_ovf;
        begin
            @(posedge clk);
            valid_in  <= 1'b1;
            opcode    <= op;
            operand_a <= a;
            operand_b <= b;
            @(posedge clk); #1;
            if (!valid_out) begin
                $display("ERROR: valid_out not asserted at cycle %0t", $time);
                errors = errors + 1;
            end
            if (result !== exp_res) begin
                $display("ERROR: op=%0d a=%h b=%h got res=%h exp=%h", op, a, b, result, exp_res);
                errors = errors + 1;
            end
            if (zero !== exp_zero) begin
                $display("ERROR: op=%0d a=%h b=%h got zero=%b exp=%b", op, a, b, zero, exp_zero);
                errors = errors + 1;
            end
            if (carry_out !== exp_co) begin
                $display("ERROR: op=%0d a=%h b=%h got carry_out=%b exp=%b", op, a, b, carry_out, exp_co);
                errors = errors + 1;
            end
            if (overflow !== exp_ovf) begin
                $display("ERROR: op=%0d a=%h b=%h got overflow=%b exp=%b", op, a, b, overflow, exp_ovf);
                errors = errors + 1;
            end
        end
    endtask

    initial begin
        clk = 0;
        rst_n = 0;
        valid_in = 0;
        opcode = 0;
        operand_a = 0;
        operand_b = 0;

        repeat (3) @(posedge clk);
        rst_n = 1;
        @(posedge clk); #1;
        if (result !== 8'h00 || zero !== 1'b1 || valid_out !== 1'b0) begin
            $display("ERROR: Reset values incorrect");
            errors = errors + 1;
        end

        // 000: ADD
        check_alu(3'd0, 8'd10, 8'd20, 8'd30, 1'b0, 1'b0, 1'b0);
        check_alu(3'd0, 8'hFF, 8'd1,  8'h00, 1'b1, 1'b1, 1'b0); // zero & carry
        check_alu(3'd0, 8'h7F, 8'd1,  8'h80, 1'b0, 1'b0, 1'b1); // signed overflow

        // 001: SUB
        check_alu(3'd1, 8'd25, 8'd15, 8'd10, 1'b0, 1'b0, 1'b0);
        check_alu(3'd1, 8'd10, 8'd10, 8'd0,  1'b1, 1'b0, 1'b0); // zero
        check_alu(3'd1, 8'h80, 8'd1,  8'h7F, 1'b0, 1'b0, 1'b1); // signed overflow underflow

        // 010: AND
        check_alu(3'd2, 8'hAA, 8'h55, 8'h00, 1'b1, 1'b0, 1'b0);
        check_alu(3'd2, 8'hFF, 8'h0F, 8'h0F, 1'b0, 1'b0, 1'b0);

        // 011: OR
        check_alu(3'd3, 8'hAA, 8'h55, 8'hFF, 1'b0, 1'b0, 1'b0);

        // 100: XOR
        check_alu(3'd4, 8'hFF, 8'hFF, 8'h00, 1'b1, 1'b0, 1'b0);

        // 101: SHL
        check_alu(3'd5, 8'h01, 8'd3,  8'h08, 1'b0, 1'b0, 1'b0);

        // 110: SHR
        check_alu(3'd6, 8'h80, 8'd3,  8'h10, 1'b0, 1'b0, 1'b0);

        // 111: PASS_A
        check_alu(3'd7, 8'h42, 8'hFF, 8'h42, 1'b0, 1'b0, 1'b0);

        @(posedge clk);
        valid_in <= 1'b0;
        @(posedge clk); #1;
        if (valid_out !== 1'b0) begin
            $display("ERROR: valid_out did not drop");
            errors = errors + 1;
        end

        #20;
        if (errors == 0) begin
            $display("*** TEST RESULT: PASS ***");
        end else begin
            $display("*** TEST RESULT: FAIL ***");
        end
        $finish;
    end

endmodule
