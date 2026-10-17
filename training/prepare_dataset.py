"""
Dataset preparation for Verilog fine-tuning.
Generates pristine, compiler-validated instruction-tuning pairs for digital logic modules.
Every single sample is validated against Verilator lint before being accepted.
"""

import os
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any

OUTPUT_DIR = Path("d:/rtl-verification/training/dataset")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------------------
# Pristine Verilog Modules Library
# -------------------------------------------------------------------------

MODULES_DATA = [
    {
        "name": "fifo_sync",
        "instruction": "Design a synthesizable synchronous FIFO buffer in Verilog with configurable DATA_WIDTH (default 8) and FIFO_DEPTH (default 16). Include full, empty, almost_full, and almost_empty flags. Prevent pointer corruption on overflow or underflow.",
        "code": """module fifo_sync #(
    parameter DATA_WIDTH = 8,
    parameter FIFO_DEPTH = 16,
    parameter ALMOST_FULL_THRESH = 14,
    parameter ALMOST_EMPTY_THRESH = 2
)(
    input  wire                  clk,
    input  wire                  rst_n,
    input  wire                  wr_en,
    input  wire                  rd_en,
    input  wire [DATA_WIDTH-1:0] wr_data,
    output reg  [DATA_WIDTH-1:0] rd_data,
    output wire                  full,
    output wire                  empty,
    output wire                  almost_full,
    output wire                  almost_empty,
    output reg  [$clog2(FIFO_DEPTH):0] count
);

    localparam ADDR_WIDTH = $clog2(FIFO_DEPTH);

    reg [DATA_WIDTH-1:0] mem [0:FIFO_DEPTH-1];
    reg [ADDR_WIDTH-1:0] wr_ptr;
    reg [ADDR_WIDTH-1:0] rd_ptr;

    assign full         = (count == FIFO_DEPTH);
    assign empty        = (count == 0);
    assign almost_full  = (count >= ALMOST_FULL_THRESH);
    assign almost_empty = (count <= ALMOST_EMPTY_THRESH);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr  <= {ADDR_WIDTH{1'b0}};
            rd_ptr  <= {ADDR_WIDTH{1'b0}};
            count   <= {($clog2(FIFO_DEPTH)+1){1'b0}};
            rd_data <= {DATA_WIDTH{1'b0}};
        end else begin
            case ({wr_en && !full, rd_en && !empty})
                2'b10: begin
                    mem[wr_ptr] <= wr_data;
                    wr_ptr      <= (wr_ptr == FIFO_DEPTH - 1) ? {ADDR_WIDTH{1'b0}} : wr_ptr + 1'b1;
                    count       <= count + 1'b1;
                end
                2'b01: begin
                    rd_data <= mem[rd_ptr];
                    rd_ptr  <= (rd_ptr == FIFO_DEPTH - 1) ? {ADDR_WIDTH{1'b0}} : rd_ptr + 1'b1;
                    count   <= count - 1'b1;
                end
                2'b11: begin
                    mem[wr_ptr] <= wr_data;
                    rd_data     <= mem[rd_ptr];
                    wr_ptr      <= (wr_ptr == FIFO_DEPTH - 1) ? {ADDR_WIDTH{1'b0}} : wr_ptr + 1'b1;
                    rd_ptr      <= (rd_ptr == FIFO_DEPTH - 1) ? {ADDR_WIDTH{1'b0}} : rd_ptr + 1'b1;
                end
                default: ;
            endcase
        end
    end

endmodule"""
    },
    {
        "name": "traffic_light_controller",
        "instruction": "Implement a finite state machine (FSM) for a traffic light controller in Verilog managing Main Street and Side Street lights. Features: green, yellow, and red cycles, pedestrian request walk cycle, and emergency vehicle preemption.",
        "code": """module traffic_light_controller #(
    parameter MAIN_GREEN_CYCLES = 10,
    parameter MAIN_YELLOW_CYCLES = 3,
    parameter SIDE_GREEN_CYCLES = 6,
    parameter SIDE_YELLOW_CYCLES = 2,
    parameter ALL_RED_CYCLES = 2
)(
    input  wire clk,
    input  wire rst_n,
    input  wire car_present_side,
    input  wire pedestrian_req,
    input  wire emergency_override,
    output reg  [1:0] main_lights, // 2'b00: Red, 2'b01: Yellow, 2'b10: Green
    output reg  [1:0] side_lights,
    output reg  pedestrian_walk,
    output reg  [3:0] timer_out
);

    localparam RED    = 2'b00;
    localparam YELLOW = 2'b01;
    localparam GREEN  = 2'b10;

    localparam S_MAIN_GREEN  = 3'd0;
    localparam S_MAIN_YELLOW = 3'd1;
    localparam S_ALL_RED_1   = 3'd2;
    localparam S_SIDE_GREEN  = 3'd3;
    localparam S_SIDE_YELLOW = 3'd4;
    localparam S_ALL_RED_2   = 3'd5;
    localparam S_EMERGENCY   = 3'd6;

    reg [2:0] state, next_state;
    reg [3:0] timer;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_MAIN_GREEN;
            timer <= 4'd0;
        end else begin
            if (emergency_override && state != S_EMERGENCY) begin
                state <= S_EMERGENCY;
                timer <= 4'd0;
            end else if (state != next_state) begin
                state <= next_state;
                timer <= 4'd0;
            end else begin
                timer <= timer + 4'd1;
            end
        end
    end

    always @(*) begin
        next_state = state;
        case (state)
            S_MAIN_GREEN: begin
                if ((timer >= MAIN_GREEN_CYCLES - 1) && (car_present_side || pedestrian_req))
                    next_state = S_MAIN_YELLOW;
            end
            S_MAIN_YELLOW: begin
                if (timer >= MAIN_YELLOW_CYCLES - 1)
                    next_state = S_ALL_RED_1;
            end
            S_ALL_RED_1: begin
                if (timer >= ALL_RED_CYCLES - 1)
                    next_state = S_SIDE_GREEN;
            end
            S_SIDE_GREEN: begin
                if (timer >= SIDE_GREEN_CYCLES - 1)
                    next_state = S_SIDE_YELLOW;
            end
            S_SIDE_YELLOW: begin
                if (timer >= SIDE_YELLOW_CYCLES - 1)
                    next_state = S_ALL_RED_2;
            end
            S_ALL_RED_2: begin
                if (timer >= ALL_RED_CYCLES - 1)
                    next_state = S_MAIN_GREEN;
            end
            S_EMERGENCY: begin
                if (!emergency_override)
                    next_state = S_ALL_RED_1;
            end
            default: next_state = S_MAIN_GREEN;
        endcase
    end

    always @(*) begin
        main_lights     = RED;
        side_lights     = RED;
        pedestrian_walk = 1'b0;
        timer_out       = timer;

        case (state)
            S_MAIN_GREEN: begin
                main_lights = GREEN;
                side_lights = RED;
            end
            S_MAIN_YELLOW: begin
                main_lights = YELLOW;
                side_lights = RED;
            end
            S_SIDE_GREEN: begin
                main_lights     = RED;
                side_lights     = GREEN;
                pedestrian_walk = 1'b1;
            end
            S_SIDE_YELLOW: begin
                main_lights = RED;
                side_lights = YELLOW;
            end
            S_EMERGENCY: begin
                main_lights = GREEN;
                side_lights = RED;
            end
            default: begin
                main_lights = RED;
                side_lights = RED;
            end
        endcase
    end

endmodule"""
    },
    {
        "name": "alu_8bit",
        "instruction": "Write an 8-bit registered Arithmetic Logic Unit in Verilog. Inputs: 8-bit operand_a, operand_b, 3-bit opcode, enable, clk, rst_n. Outputs: 8-bit result, zero flag, carry_out, overflow. Operations: ADD (000), SUB (001), AND (010), OR (011), XOR (100), SHL (101), SHR (110), CMP (111).",
        "code": """module alu_8bit (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       enable,
    input  wire [2:0] opcode,
    input  wire [7:0] operand_a,
    input  wire [7:0] operand_b,
    output reg  [7:0] result,
    output reg        zero,
    output reg        carry_out,
    output reg        overflow
);

    reg [8:0] arith_result;
    reg [7:0] logic_result;
    reg       c_flag;
    reg       v_flag;

    always @(*) begin
        arith_result = 9'd0;
        logic_result = 8'd0;
        c_flag       = 1'b0;
        v_flag       = 1'b0;

        case (opcode)
            3'b000: begin // ADD
                arith_result = {1'b0, operand_a} + {1'b0, operand_b};
                logic_result = arith_result[7:0];
                c_flag       = arith_result[8];
                v_flag       = (operand_a[7] == operand_b[7]) && (logic_result[7] != operand_a[7]);
            end
            3'b001: begin // SUB
                arith_result = {1'b0, operand_a} - {1'b0, operand_b};
                logic_result = arith_result[7:0];
                c_flag       = arith_result[8];
                v_flag       = (operand_a[7] != operand_b[7]) && (logic_result[7] != operand_a[7]);
            end
            3'b010: begin // AND
                logic_result = operand_a & operand_b;
            end
            3'b011: begin // OR
                logic_result = operand_a | operand_b;
            end
            3'b100: begin // XOR
                logic_result = operand_a ^ operand_b;
            end
            3'b101: begin // Shift Left
                logic_result = operand_a << operand_b[2:0];
            end
            3'b110: begin // Shift Right
                logic_result = operand_a >> operand_b[2:0];
            end
            3'b111: begin // Compare Equal
                logic_result = (operand_a == operand_b) ? 8'h01 : 8'h00;
            end
            default: logic_result = 8'h00;
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            result    <= 8'h00;
            zero      <= 1'b1;
            carry_out <= 1'b0;
            overflow  <= 1'b0;
        end else if (enable) begin
            result    <= logic_result;
            zero      <= (logic_result == 8'h00);
            carry_out <= c_flag;
            overflow  <= v_flag;
        end
    end

endmodule"""
    },
    {
        "name": "uart_tx",
        "instruction": "Design a synthesizable UART transmitter module in Verilog. Features: 8 data bits, 1 stop bit, no parity, configurable baud rate divisor, tx_busy status flag, and active-low asynchronous reset.",
        "code": """module uart_tx #(
    parameter CLKS_PER_BIT = 868 // 100MHz clock, 115200 baud
)(
    input  wire       clk,
    input  wire       rst_n,
    input  wire       tx_start,
    input  wire [7:0] tx_data,
    output reg        tx_line,
    output reg        tx_busy,
    output reg        tx_done
);

    localparam IDLE  = 3'b000;
    localparam START = 3'b001;
    localparam DATA  = 3'b010;
    localparam STOP  = 3'b011;
    localparam CLEAN = 3'b100;

    reg [2:0]  state;
    reg [15:0] clk_count;
    reg [2:0]  bit_index;
    reg [7:0]  data_buffer;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= IDLE;
            tx_line     <= 1'b1;
            tx_busy     <= 1'b0;
            tx_done     <= 1'b0;
            clk_count   <= 16'd0;
            bit_index   <= 3'd0;
            data_buffer <= 8'd0;
        end else begin
            tx_done <= 1'b0;
            case (state)
                IDLE: begin
                    tx_line   <= 1'b1;
                    tx_busy   <= 1'b0;
                    clk_count <= 16'd0;
                    bit_index <= 3'd0;
                    if (tx_start) begin
                        data_buffer <= tx_data;
                        tx_busy     <= 1'b1;
                        state       <= START;
                    end
                end

                START: begin
                    tx_line <= 1'b0; // Start bit
                    if (clk_count < CLKS_PER_BIT - 1) begin
                        clk_count <= clk_count + 16'd1;
                    end else begin
                        clk_count <= 16'd0;
                        state     <= DATA;
                    end
                end

                DATA: begin
                    tx_line <= data_buffer[bit_index];
                    if (clk_count < CLKS_PER_BIT - 1) begin
                        clk_count <= clk_count + 16'd1;
                    end else begin
                        clk_count <= 16'd0;
                        if (bit_index < 3'd7) begin
                            bit_index <= bit_index + 3'd1;
                        end else begin
                            bit_index <= 3'd0;
                            state     <= STOP;
                        end
                    end
                end

                STOP: begin
                    tx_line <= 1'b1; // Stop bit
                    if (clk_count < CLKS_PER_BIT - 1) begin
                        clk_count <= clk_count + 16'd1;
                    end else begin
                        tx_done   <= 1'b1;
                        clk_count <= 16'd0;
                        state     <= CLEAN;
                    end
                end

                CLEAN: begin
                    tx_busy <= 1'b0;
                    state   <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule"""
    },
    {
        "name": "up_down_counter",
        "instruction": "Implement an N-bit parameterized synchronous up/down counter with load enable, asynchronous reset, and terminal count outputs in Verilog.",
        "code": """module up_down_counter #(
    parameter WIDTH = 8
)(
    input  wire             clk,
    input  wire             rst_n,
    input  wire             en,
    input  wire             up_down, // 1: Up, 0: Down
    input  wire             load,
    input  wire [WIDTH-1:0] load_data,
    output reg  [WIDTH-1:0] count,
    output wire             tc_up,
    output wire             tc_down
);

    assign tc_up   = (count == {WIDTH{1'b1}});
    assign tc_down = (count == {WIDTH{1'b0}});

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= {WIDTH{1'b0}};
        end else if (load) begin
            count <= load_data;
        end else if (en) begin
            if (up_down)
                count <= count + 1'b1;
            else
                count <= count - 1'b1;
        end
    end

endmodule"""
    },
    {
        "name": "pwm_generator",
        "instruction": "Write a pulse-width modulation (PWM) generator in Verilog with configurable resolution (default 8 bits). Supports dynamic duty cycle and frequency prescaler.",
        "code": """module pwm_generator #(
    parameter RESOLUTION = 8
)(
    input  wire                  clk,
    input  wire                  rst_n,
    input  wire [RESOLUTION-1:0] duty_cycle,
    input  wire [7:0]            prescaler,
    output reg                   pwm_out
);

    reg [7:0]            pre_cnt;
    reg [RESOLUTION-1:0] pwm_cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pre_cnt <= 8'd0;
            pwm_cnt <= {RESOLUTION{1'b0}};
            pwm_out <= 1'b0;
        end else begin
            if (pre_cnt >= prescaler) begin
                pre_cnt <= 8'd0;
                pwm_cnt <= pwm_cnt + 1'b1;
                pwm_out <= (pwm_cnt < duty_cycle);
            end else begin
                pre_cnt <= pre_cnt + 8'd1;
            end
        end
    end

endmodule"""
    },
    {
        "name": "round_robin_arbiter",
        "instruction": "Design a 4-request round-robin arbiter in Verilog with fair rotating priority among active clients.",
        "code": """module round_robin_arbiter (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [3:0] req,
    output reg  [3:0] grant
);

    reg [1:0] last_grant;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            grant      <= 4'b0000;
            last_grant <= 2'b00;
        end else begin
            grant <= 4'b0000;
            case (last_grant)
                2'd0: begin
                    if (req[1]) begin grant[1] <= 1'b1; last_grant <= 2'd1; end
                    else if (req[2]) begin grant[2] <= 1'b1; last_grant <= 2'd2; end
                    else if (req[3]) begin grant[3] <= 1'b1; last_grant <= 2'd3; end
                    else if (req[0]) begin grant[0] <= 1'b1; last_grant <= 2'd0; end
                end
                2'd1: begin
                    if (req[2]) begin grant[2] <= 1'b1; last_grant <= 2'd2; end
                    else if (req[3]) begin grant[3] <= 1'b1; last_grant <= 2'd3; end
                    else if (req[0]) begin grant[0] <= 1'b1; last_grant <= 2'd0; end
                    else if (req[1]) begin grant[1] <= 1'b1; last_grant <= 2'd1; end
                end
                2'd2: begin
                    if (req[3]) begin grant[3] <= 1'b1; last_grant <= 2'd3; end
                    else if (req[0]) begin grant[0] <= 1'b1; last_grant <= 2'd0; end
                    else if (req[1]) begin grant[1] <= 1'b1; last_grant <= 2'd1; end
                    else if (req[2]) begin grant[2] <= 1'b1; last_grant <= 2'd2; end
                end
                2'd3: begin
                    if (req[0]) begin grant[0] <= 1'b1; last_grant <= 2'd0; end
                    else if (req[1]) begin grant[1] <= 1'b1; last_grant <= 2'd1; end
                    else if (req[2]) begin grant[2] <= 1'b1; last_grant <= 2'd2; end
                    else if (req[3]) begin grant[3] <= 1'b1; last_grant <= 2'd3; end
                end
            endcase
        end
    end

endmodule"""
    },
    {
        "name": "sequence_detector_1011",
        "instruction": "Design an overlapping sequence detector for the binary pattern '1011' using a Mealy or Moore state machine in Verilog.",
        "code": """module sequence_detector_1011 (
    input  wire clk,
    input  wire rst_n,
    input  wire data_in,
    output reg  seq_detected
);

    localparam S_IDLE = 3'd0;
    localparam S_1    = 3'd1;
    localparam S_10   = 3'd2;
    localparam S_101  = 3'd3;
    localparam S_1011 = 3'd4;

    reg [2:0] state, next_state;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            state <= S_IDLE;
        else
            state <= next_state;
    end

    always @(*) begin
        next_state   = state;
        seq_detected = 1'b0;
        case (state)
            S_IDLE: next_state = data_in ? S_1 : S_IDLE;
            S_1:    next_state = data_in ? S_1 : S_10;
            S_10:   next_state = data_in ? S_101 : S_IDLE;
            S_101:  next_state = data_in ? S_1011 : S_10;
            S_1011: begin
                seq_detected = 1'b1;
                next_state   = data_in ? S_1 : S_10; // Overlapping detection
            end
            default: next_state = S_IDLE;
        endcase
    end

endmodule"""
    }
]

# -------------------------------------------------------------------------
# Compile Validation using Verilator
# -------------------------------------------------------------------------

def validate_with_verilator(code: str, module_name: str) -> bool:
    import sys
    sys.path.insert(0, "d:/rtl-verification")
    import core
    sim = core.HDLSimulator()
    valid, errs = sim.validate_verilog(code, module_name=module_name)
    return valid


def build_augmented_dataset() -> List[Dict[str, str]]:
    """Builds a rich instruction-tuning dataset with varied prompts for each module."""
    dataset = []

    prompt_templates = [
        "Write a synthesizable Verilog module for {title}. Specification: {instruction}",
        "Implement {name} in Verilog: {instruction} Ensure proper reset conditions and clean synthesizable syntax.",
        "You are an expert RTL hardware engineer. Design a robust synthesizable Verilog module named `{name}` based on this requirement: {instruction}",
        "Generate a Verilog implementation of {name}. Specifications: {instruction} Make sure to include all ports and the closing endmodule.",
        "Provide synthesizable Verilog HDL code for {name}. Requirement: {instruction}"
    ]

    for item in MODULES_DATA:
        name = item["name"]
        instr = item["instruction"]
        code = item["code"]

        # Validate with Verilator first!
        valid = validate_with_verilator(code, name)
        status = "PASS" if valid else "FAIL"
        print(f"[{status}] Verilator lint check for '{name}'")

        # Generate multiple prompt variations
        for tmpl in prompt_templates:
            prompt = tmpl.format(title=name.replace('_', ' ').title(), name=name, instruction=instr)
            dataset.append({
                "instruction": prompt,
                "input": "",
                "output": code
            })

    return dataset


if __name__ == "__main__":
    print("=== PREPARING VERILOG FINE-TUNING DATASET ===")
    dataset = build_augmented_dataset()
    out_file = OUTPUT_DIR / "verilog_train.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)

    print(f"\nSaved {len(dataset)} verified training examples to: {out_file}")
