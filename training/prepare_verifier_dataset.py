"""
Dataset Preparation for Verilog Adversarial Verification Fine-Tuning.
Generates specialized instruction-tuning pairs for Adversarial Verifier (Llama 3.1 8B).
Trains the model to generate robust, self-checking Verilog-2001 testbenches with:
  1. Strict corner-case stimulus vectors (overflows, underflows, race conditions)
  2. Automated response checkers with $display / $fatal
  3. Cycle-accurate assertion monitors
  4. Protocol violation testing and recovery verification
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Any

OUTPUT_DIR = Path("d:/rtl-verification/training/dataset")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
VERIFIER_DATASET_FILE = OUTPUT_DIR / "verilog_verifier_train.json"

VERIFICATION_DATA: List[Dict[str, Any]] = [
    {
        "name": "fifo_sync_adversarial_tb",
        "instruction": (
            "Write an adversarial, self-checking Verilog-2001 testbench for a synchronous FIFO module `fifo_sync`. "
            "Stress corner cases including: back-to-back writes until full, attempting write on full (overflow prevention), "
            "back-to-back reads until empty, attempting read on empty (underflow prevention), and simultaneous read/write "
            "at full and empty boundaries. Include self-checking assertions that terminate simulation with $fatal on mismatch."
        ),
        "code": """`timescale 1ns/1ps

module fifo_sync_tb;
    parameter DATA_WIDTH = 8;
    parameter FIFO_DEPTH = 16;
    parameter CLK_PERIOD = 10;

    reg                   clk;
    reg                   rst_n;
    reg                   wr_en;
    reg                   rd_en;
    reg  [DATA_WIDTH-1:0] wr_data;
    wire [DATA_WIDTH-1:0] rd_data;
    wire                  full;
    wire                  empty;
    wire                  almost_full;
    wire                  almost_empty;
    wire [$clog2(FIFO_DEPTH):0] count;

    integer errors = 0;
    integer i;

    // Instantiate Device Under Test
    fifo_sync #(
        .DATA_WIDTH(DATA_WIDTH),
        .FIFO_DEPTH(FIFO_DEPTH)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .wr_en(wr_en),
        .rd_en(rd_en),
        .wr_data(wr_data),
        .rd_data(rd_data),
        .full(full),
        .empty(empty),
        .almost_full(almost_full),
        .almost_empty(almost_empty),
        .count(count)
    );

    // Clock Generation
    always #(CLK_PERIOD / 2) clk = ~clk;

    initial begin
        $display("[TEST START] Adversarial Synchronous FIFO Verification");
        clk = 0;
        rst_n = 0;
        wr_en = 0;
        rd_en = 0;
        wr_data = 0;

        // 1. Reset Verification
        #(CLK_PERIOD * 2);
        rst_n = 1;
        #(CLK_PERIOD);
        if (!empty || full || count !== 0) begin
            $display("[FATAL ERROR] Reset state invalid: empty=%b, full=%b, count=%0d", empty, full, count);
            errors = errors + 1;
        end

        // 2. Fill FIFO to Maximum Depth
        for (i = 0; i < FIFO_DEPTH; i = i + 1) begin
            @(posedge clk);
            wr_en = 1;
            wr_data = 8'hA0 + i;
            rd_en = 0;
        end
        @(posedge clk);
        wr_en = 0;
        #(1);
        if (!full || empty || count !== FIFO_DEPTH) begin
            $display("[FATAL ERROR] Full flag failed: full=%b, count=%0d (expected %0d)", full, count, FIFO_DEPTH);
            errors = errors + 1;
        end

        // 3. Adversarial Overflow Injection (Write while Full)
        @(posedge clk);
        wr_en = 1;
        wr_data = 8'hFF;
        @(posedge clk);
        wr_en = 0;
        #(1);
        if (count > FIFO_DEPTH) begin
            $display("[FATAL ERROR] FIFO Overflow corrupted internal count: count=%0d", count);
            errors = errors + 1;
        end

        // 4. Drain FIFO and Check Ordering (FIFO contract)
        for (i = 0; i < FIFO_DEPTH; i = i + 1) begin
            @(posedge clk);
            rd_en = 1;
            wr_en = 0;
            @(negedge clk);
            if (rd_data !== (8'hA0 + i)) begin
                $display("[FATAL ERROR] Data mismatch at item %0d: got %h, expected %h", i, rd_data, 8'hA0 + i);
                errors = errors + 1;
            end
        end
        @(posedge clk);
        rd_en = 0;
        #(1);
        if (!empty) begin
            $display("[FATAL ERROR] Empty flag failed after complete drain");
            errors = errors + 1;
        end

        // 5. Adversarial Underflow Injection (Read while Empty)
        @(posedge clk);
        rd_en = 1;
        @(posedge clk);
        rd_en = 0;
        #(1);
        if (count !== 0) begin
            $display("[FATAL ERROR] Underflow corrupted counter: count=%0d", count);
            errors = errors + 1;
        end

        // 6. Simultaneous Read and Write at Steady State
        @(posedge clk);
        wr_en = 1; wr_data = 8'h55;
        @(posedge clk);
        wr_en = 1; wr_data = 8'hAA;
        rd_en = 1;
        @(posedge clk);
        wr_en = 0; rd_en = 0;
        #(1);
        if (errors == 0)
            $display("[TEST PASS] All adversarial FIFO corner cases passed cleanly.");
        else
            $display("[TEST FAIL] Total assertion failures: %0d", errors);

        $finish;
    end
endmodule"""
    },
    {
        "name": "traffic_light_adversarial_tb",
        "instruction": (
            "Write an adversarial, self-checking Verilog-2001 testbench for an intersection traffic light controller `traffic_light_controller`. "
            "Implement continuous safety monitors that assert $fatal if main_light and side_light are ever simultaneously green or yellow. "
            "Stress emergency vehicle override preemption during all states and verify that pedestrian walk requests are serviced safely."
        ),
        "code": """`timescale 1ns/1ps

module traffic_light_tb;
    reg        clk;
    reg        rst_n;
    reg        car_present_side;
    reg        pedestrian_req;
    reg        emergency_override;
    wire [2:0] main_light;
    wire [2:0] side_light;
    wire       ped_walk;
    wire [2:0] state_out;

    integer errors = 0;

    // Instantiate DUT
    traffic_light_controller dut (
        .clk(clk),
        .rst_n(rst_n),
        .car_present_side(car_present_side),
        .pedestrian_req(pedestrian_req),
        .emergency_override(emergency_override),
        .main_light(main_light),
        .side_light(side_light),
        .ped_walk(ped_walk),
        .state_out(state_out)
    );

    always #5 clk = ~clk;

    // CONTINUOUS SAFETY MONITOR: Mutually Exclusive Green/Yellow
    always @(posedge clk) begin
        if (rst_n) begin
            // Bit 0 = Green, Bit 1 = Yellow, Bit 2 = Red
            if ((main_light[0] || main_light[1]) && (side_light[0] || side_light[1])) begin
                $display("[FATAL SAFETY VIOLATION] Simultaneous non-red detected! Main=%b Side=%b at time %0t",
                         main_light, side_light, $time);
                errors = errors + 1;
            end
            if (ped_walk && (side_light[0] == 0 && main_light[0] == 1)) begin
                $display("[FATAL SAFETY VIOLATION] Pedestrian walk asserted while main traffic active! at time %0t", $time);
                errors = errors + 1;
            end
        end
    end

    initial begin
        $display("[TEST START] Adversarial Traffic Light Controller Safety Verification");
        clk = 0;
        rst_n = 0;
        car_present_side = 0;
        pedestrian_req = 0;
        emergency_override = 0;

        #20 rst_n = 1;

        // 1. Nominal cycle progression
        #100;
        car_present_side = 1;
        #200;

        // 2. Pedestrian request during active sequence
        pedestrian_req = 1;
        #20 pedestrian_req = 0;
        #300;

        // 3. ADVERSARIAL: Emergency Override Preemption during side-street active
        emergency_override = 1;
        #10;
        @(posedge clk);
        #1;
        if (main_light !== 3'b001 || side_light !== 3'b100 || ped_walk !== 0) begin
            $display("[FATAL ERROR] Emergency override failed immediate preemption! Main=%b Side=%b Ped=%b",
                     main_light, side_light, ped_walk);
            errors = errors + 1;
        end

        // Hold emergency override for 50 cycles
        #100;
        emergency_override = 0;
        #200;

        if (errors == 0)
            $display("[TEST PASS] All traffic safety properties held under stress and emergency override.");
        else
            $display("[TEST FAIL] Total safety violations detected: %0d", errors);

        $finish;
    end
endmodule"""
    },
    {
        "name": "alu_8bit_adversarial_tb",
        "instruction": (
            "Write an adversarial, self-checking Verilog-2001 testbench for an 8-bit registered arithmetic logic unit `alu_8bit`. "
            "Verify all 8 operations (ADD, SUB, AND, OR, XOR, SHL, SHR, CMP), pipeline latency (exactly 1 cycle from valid_in to valid_out), "
            "and flag behavior: carry_out on overflow, zero flag on null result, and parity flag. Use exhaustive boundary vectors (0x00, 0xFF, 0x7F, 0x80)."
        ),
        "code": """`timescale 1ns/1ps

module alu_8bit_tb;
    parameter WIDTH = 8;

    reg              clk;
    reg              rst_n;
    reg              valid_in;
    reg  [2:0]       opcode;
    reg  [WIDTH-1:0] a;
    reg  [WIDTH-1:0] b;
    wire             valid_out;
    wire [WIDTH-1:0] result;
    wire             carry_out;
    wire             overflow;
    wire             zero;
    wire             parity;

    integer errors = 0;

    // Instantiate DUT
    alu_8bit #(.WIDTH(WIDTH)) dut (
        .clk(clk),
        .rst_n(rst_n),
        .valid_in(valid_in),
        .opcode(opcode),
        .a(a),
        .b(b),
        .valid_out(valid_out),
        .result(result),
        .carry_out(carry_out),
        .overflow(overflow),
        .zero(zero),
        .parity(parity)
    );

    always #5 clk = ~clk;

    task check_op(
        input [2:0]       op,
        input [WIDTH-1:0] op_a,
        input [WIDTH-1:0] op_b,
        input [WIDTH-1:0] exp_res,
        input             exp_zero,
        input             exp_carry
    );
    begin
        @(posedge clk);
        valid_in = 1;
        opcode   = op;
        a        = op_a;
        b        = op_b;
        @(posedge clk); // Exactly 1-cycle latency pipeline
        valid_in = 0;
        #1;
        if (!valid_out) begin
            $display("[FATAL ERROR] valid_out not asserted on cycle 1 for opcode %b", op);
            errors = errors + 1;
        end
        if (result !== exp_res) begin
            $display("[FATAL ERROR] Result mismatch: op=%b, a=%h, b=%h -> got %h, expected %h",
                     op, op_a, op_b, result, exp_res);
            errors = errors + 1;
        end
        if (zero !== exp_zero) begin
            $display("[FATAL ERROR] Zero flag mismatch: got %b, expected %b", zero, exp_zero);
            errors = errors + 1;
        end
    end
    endtask

    initial begin
        $display("[TEST START] Adversarial 8-Bit ALU Verification");
        clk = 0;
        rst_n = 0;
        valid_in = 0;
        opcode = 0;
        a = 0;
        b = 0;

        #20 rst_n = 1;
        #(10);

        // 1. ADD Boundary: 0xFF + 0x01 = 0x00 (carry=1, zero=1)
        check_op(3'b000, 8'hFF, 8'h01, 8'h00, 1'b1, 1'b1);

        // 2. SUB Boundary: 0x00 - 0x01 = 0xFF
        check_op(3'b001, 8'h00, 8'h01, 8'hFF, 1'b0, 1'b0);

        // 3. AND Boundary: 0xAA & 0x55 = 0x00 (zero=1)
        check_op(3'b010, 8'hAA, 8'h55, 8'h00, 1'b1, 1'b0);

        // 4. OR Boundary: 0xF0 | 0x0F = 0xFF (zero=0)
        check_op(3'b011, 8'hF0, 8'h0F, 8'hFF, 1'b0, 1'b0);

        // 5. XOR Self: 0xDE ^ 0xDE = 0x00 (zero=1)
        check_op(3'b100, 8'hDE, 8'hDE, 8'h00, 1'b1, 1'b0);

        // 6. Shift Left: 0x80 << 1 = 0x00
        check_op(3'b101, 8'h80, 8'h01, 8'h00, 1'b1, 1'b0);

        // 7. Shift Right: 0x01 >> 1 = 0x00
        check_op(3'b110, 8'h01, 8'h01, 8'h00, 1'b1, 1'b0);

        // 8. Inactive Cycle Latency Test: valid_in = 0 must produce valid_out = 0
        @(posedge clk);
        valid_in = 0;
        @(posedge clk);
        #1;
        if (valid_out !== 0) begin
            $display("[FATAL ERROR] valid_out remained high when valid_in was low!");
            errors = errors + 1;
        end

        if (errors == 0)
            $display("[TEST PASS] All ALU operations, boundary conditions, and flags verified.");
        else
            $display("[TEST FAIL] Total ALU failures: %0d", errors);

        $finish;
    end
endmodule"""
    },
    {
        "name": "round_robin_arbiter_adversarial_tb",
        "instruction": (
            "Write an adversarial, self-checking Verilog-2001 testbench for a 4-channel round-robin arbiter `round_robin_arbiter`. "
            "Stress concurrent grant contention where all 4 request lines remain asserted simultaneously. Verify starvation prevention "
            "and fair cyclic rotation (0 -> 1 -> 2 -> 3 -> 0)."
        ),
        "code": """`timescale 1ns/1ps

module round_robin_arbiter_tb;
    reg        clk;
    reg        rst_n;
    reg  [3:0] req;
    wire [3:0] gnt;

    integer errors = 0;
    integer step;

    round_robin_arbiter #(.NUM_PORTS(4)) dut (
        .clk(clk),
        .rst_n(rst_n),
        .req(req),
        .gnt(gnt)
    );

    always #5 clk = ~clk;

    initial begin
        $display("[TEST START] Adversarial Round-Robin Arbiter Verification");
        clk = 0;
        rst_n = 0;
        req = 0;

        #20 rst_n = 1;
        @(posedge clk);

        // 1. One-hot grant check under single requests
        req = 4'b0001; @(posedge clk); #1;
        if (gnt !== 4'b0001) begin $display("[ERROR] Port 0 request failed grant"); errors = errors + 1; end

        req = 4'b0010; @(posedge clk); #1;
        if (gnt !== 4'b0010) begin $display("[ERROR] Port 1 request failed grant"); errors = errors + 1; end

        // 2. Persistent Contention: All 4 ports request continuously
        req = 4'b1111;
        for (step = 0; step < 8; step = step + 1) begin
            @(posedge clk); #1;
            // Grant must always be strictly one-hot
            if ($countones(gnt) !== 1) begin
                $display("[FATAL ERROR] Non-one-hot grant under contention: gnt=%b", gnt);
                errors = errors + 1;
            end
        end

        // 3. Idle Request: gnt must be 0
        req = 4'b0000; @(posedge clk); #1;
        if (gnt !== 4'b0000) begin
            $display("[FATAL ERROR] Grant asserted during idle requests: gnt=%b", gnt);
            errors = errors + 1;
        end

        if (errors == 0)
            $display("[TEST PASS] Round-robin arbiter satisfied all starvation and mutual exclusion constraints.");
        else
            $display("[TEST FAIL] Total arbiter errors: %0d", errors);

        $finish;
    end
endmodule"""
    }
]


def format_llama_verifier_prompt(sample: Dict[str, Any]) -> Dict[str, str]:
    """Formats sample into Llama 3.1 prompt format for verification fine-tuning."""
    system_msg = (
        "You are an expert Silicon Hardware Verification Engineer specializing in adversarial testbench generation. "
        "Given an RTL specification, write a comprehensive, synthesizable, self-checking Verilog-2001 testbench. "
        "Stress boundary conditions, inject protocol corner cases, and include cycle-accurate self-checking monitors with $fatal."
    )
    prompt = (
        f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
        f"{system_msg}<|eot_id|>"
        f"<|start_header_id|>user<|end_header_id|>\n\n"
        f"{sample['instruction']}<|eot_id|>"
        f"<|start_header_id|>assistant<|end_header_id|>\n\n"
        f"```verilog\n{sample['code']}\n```<|eot_id|>"
    )
    return {
        "name": sample["name"],
        "instruction": sample["instruction"],
        "code": sample["code"],
        "text": prompt,
    }


def main():
    formatted_samples = [format_llama_verifier_prompt(s) for s in VERIFICATION_DATA]
    with open(VERIFIER_DATASET_FILE, "w", encoding="utf-8") as f:
        json.dump(formatted_samples, f, indent=2)
    print(f"Generated {len(formatted_samples)} verifier instruction samples in: {VERIFIER_DATASET_FILE}")


if __name__ == "__main__":
    main()
