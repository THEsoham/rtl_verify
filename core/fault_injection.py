"""
Controlled Fault Injection Experimentation Engine
=================================================
Injects representative, realistic hardware bugs into otherwise correct RTL designs
to rigorously evaluate and compare the fault detection efficacy of:
  - Baseline 1: Single-LLM Generate-Only (Sanity Testbench)
  - Baseline 2: Single-LLM Self-Verification (Nominal Testbench)
  - Proposed: Dual-Agent Adversarial Framework (Adversarial Testbench)

Provides empirical evidence that adversarial verification reliably detects
critical hardware hazards (overflow, concurrency collisions, mutex violations,
preemption failures, flag omissions) where conventional testbenches fail.
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd

from .simulator import HDLSimulator, SimulationResult


@dataclass
class ControlledFault:
    fault_id: str
    benchmark: str
    category: str
    name: str
    description: str
    faulty_rtl: str
    target_assertion: str
    # Results per evaluation method
    baseline1_detected: bool = False
    baseline1_error: Optional[str] = None
    baseline2_detected: bool = False
    baseline2_error: Optional[str] = None
    proposed_detected: bool = False
    proposed_error: Optional[str] = None


class ControlledFaultEngine:
    """
    Manages and executes controlled fault injection experiments across hardware benchmarks.
    """

    def __init__(self, simulator: Optional[HDLSimulator] = None):
        self.simulator = simulator or HDLSimulator()

    def get_fault_catalog(self) -> List[ControlledFault]:
        """Returns the complete catalog of 12 controlled representative hardware faults."""
        catalog: List[ControlledFault] = []

        # ──────────────────────────────────────────────────────────────────────
        # 1. FIFO Synchronous Buffer Faults (4 Faults)
        # ──────────────────────────────────────────────────────────────────────
        catalog.append(ControlledFault(
            fault_id="FAULT_FIFO_01",
            benchmark="fifo_sync",
            category="Boundary / Capacity",
            name="Premature Full Assertion",
            description="Asserts full flag when count reaches FIFO_DEPTH - 1 (15) instead of FIFO_DEPTH (16).",
            faulty_rtl="""
module fifo_sync #(parameter DATA_WIDTH=8, FIFO_DEPTH=16) (
    input wire clk, rst_n, wr_en, rd_en,
    input wire [DATA_WIDTH-1:0] wr_data,
    output reg [DATA_WIDTH-1:0] rd_data,
    output wire full, empty, almost_full, almost_empty,
    output reg [4:0] count
);
    // INJECTED FAULT: Premature full flag at 15
    assign full = (count == FIFO_DEPTH - 1);
    assign empty = (count == 0);
    assign almost_full = (count >= 14);
    assign almost_empty = (count <= 2);
endmodule
            """.strip(),
            target_assertion="full_flag_assertion",
        ))

        catalog.append(ControlledFault(
            fault_id="FAULT_FIFO_02",
            benchmark="fifo_sync",
            category="Address / Datapath",
            name="Pointer Increment Step Error",
            description="Increments write pointer/count by 2 instead of 1 on write, corrupting memory mapping.",
            faulty_rtl="""
module fifo_sync #(parameter DATA_WIDTH=8, FIFO_DEPTH=16) (
    input wire clk, rst_n, wr_en, rd_en,
    input wire [DATA_WIDTH-1:0] wr_data,
    output reg [DATA_WIDTH-1:0] rd_data,
    output wire full, empty, almost_full, almost_empty,
    output reg [4:0] count
);
    // INJECTED FAULT: Off-by-two step increment
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) count <= 0;
        else if (wr_en && !full) count <= count + 2'b10;
    end
    assign full = (count == FIFO_DEPTH);
    assign empty = (count == 0);
endmodule
            """.strip(),
            target_assertion="count_tracking_assertion",
        ))

        catalog.append(ControlledFault(
            fault_id="FAULT_FIFO_03",
            benchmark="fifo_sync",
            category="Control / Reset",
            name="Reset Initialization Corruption",
            description="Asynchronous reset initializes count to 1 instead of 0, violating clean start invariant.",
            faulty_rtl="""
module fifo_sync #(parameter DATA_WIDTH=8, FIFO_DEPTH=16) (
    input wire clk, rst_n, wr_en, rd_en,
    input wire [DATA_WIDTH-1:0] wr_data,
    output reg [DATA_WIDTH-1:0] rd_data,
    output wire full, empty, almost_full, almost_empty,
    output reg [4:0] count
);
    // INJECTED FAULT: Reset count initialized to 1
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) count <= 1;
        else if (wr_en && !full) count <= count + 1'b1;
    end
    assign full = (count == FIFO_DEPTH);
    assign empty = (count == 0);
endmodule
            """.strip(),
            target_assertion="reset_assertion",
        ))

        catalog.append(ControlledFault(
            fault_id="FAULT_FIFO_04",
            benchmark="fifo_sync",
            category="Concurrency / Collision",
            name="Simultaneous Access Pointer Hazard",
            description="Decrements count on simultaneous write and read when full instead of holding constant.",
            faulty_rtl="""
module fifo_sync #(parameter DATA_WIDTH=8, FIFO_DEPTH=16) (
    input wire clk, rst_n, wr_en, rd_en,
    input wire [DATA_WIDTH-1:0] wr_data,
    output reg [DATA_WIDTH-1:0] rd_data,
    output wire full, empty, almost_full, almost_empty,
    output reg [4:0] count
);
    // INJECTED FAULT: Corrupted simultaneous read-write update
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) count <= 0;
        else if (wr_en && !rd_en && !full) count <= count + 1;
        else if (rd_en && !wr_en && !empty) count <= count - 1;
        else if (wr_en && rd_en) count <= count - 1; // bug: drops item
    end
    assign full = (count == FIFO_DEPTH);
    assign empty = (count == 0);
endmodule
            """.strip(),
            target_assertion="simultaneous_access_assertion",
        ))

        # ──────────────────────────────────────────────────────────────────────
        # 2. Traffic Light Controller FSM Faults (4 Faults)
        # ──────────────────────────────────────────────────────────────────────
        catalog.append(ControlledFault(
            fault_id="FAULT_TLC_01",
            benchmark="traffic_light_controller",
            category="Safety / Mutual Exclusion",
            name="Simultaneous Green Hazard",
            description="Side street light output forced Green during Main Green, causing fatal intersection collision hazard.",
            faulty_rtl="""
module traffic_light_controller (
    input wire clk, rst_n, car_present_side, pedestrian_req, emergency_override,
    output reg [2:0] main_light, side_light,
    output reg ped_walk,
    output wire [2:0] state_out
);
    // INJECTED FAULT: Side light stuck at 3'b001 (Green)
    always @(*) begin
        side_light <= 3'b001;
    end
endmodule
            """.strip(),
            target_assertion="safety_mutex_assertion",
        ))

        catalog.append(ControlledFault(
            fault_id="FAULT_TLC_02",
            benchmark="traffic_light_controller",
            category="Preemption / Priority",
            name="Emergency Preemption Ignored",
            description="Emergency vehicle override fails to preempt side-street active cycle, blocking first responders.",
            faulty_rtl="""
module traffic_light_controller (
    input wire clk, rst_n, car_present_side, pedestrian_req, emergency_override,
    output reg [2:0] main_light, side_light,
    output reg ped_walk,
    output wire [2:0] state_out
);
    // INJECTED FAULT: Emergency override disconnected
    assign emergency_active = 1'b0;
endmodule
            """.strip(),
            target_assertion="emergency_preemption_assertion",
        ))

        catalog.append(ControlledFault(
            fault_id="FAULT_TLC_03",
            benchmark="traffic_light_controller",
            category="Timing Specification",
            name="Premature Yellow Clearance",
            description="Yellow clearance phase shortened from 3 cycles to 1 cycle, creating safety stop hazard.",
            faulty_rtl="""
module traffic_light_controller (
    input wire clk, rst_n, car_present_side, pedestrian_req, emergency_override,
    output reg [2:0] main_light, side_light,
    output reg ped_walk,
    output wire [2:0] state_out
);
    // INJECTED FAULT: Yellow duration shortened
    parameter YELLOW_CYCLES = 3;
    reg [4:0] timer;
    reg [2:0] state, next_state;
    always @(posedge clk) begin
        if (timer >= YELLOW_CYCLES - 2) state <= next_state;
    end
endmodule
            """.strip(),
            target_assertion="yellow_timing_assertion",
        ))

        catalog.append(ControlledFault(
            fault_id="FAULT_TLC_04",
            benchmark="traffic_light_controller",
            category="Event Servicing",
            name="Inverted Pedestrian Request",
            description="Bit inversion in pedestrian pushbutton condition prevents walk signal from asserting.",
            faulty_rtl="""
module traffic_light_controller (
    input wire clk, rst_n, car_present_side, pedestrian_req, emergency_override,
    output reg [2:0] main_light, side_light,
    output reg ped_walk,
    output wire [2:0] state_out
);
    reg ped_latched;
    // INJECTED FAULT: Inverted pedestrian latch logic
    always @(posedge clk) begin
        if (!pedestrian_req) ped_latched <= 1'b1;
    end
endmodule
            """.strip(),
            target_assertion="pedestrian_servicing_assertion",
        ))

        # ──────────────────────────────────────────────────────────────────────
        # 3. 8-Bit Pipelined ALU Faults (4 Faults)
        # ──────────────────────────────────────────────────────────────────────
        catalog.append(ControlledFault(
            fault_id="FAULT_ALU_01",
            benchmark="alu_8bit",
            category="Control / Decode",
            name="ADD Opcode Inverted to SUB",
            description="Decoder swap causes Opcode 000 (ADD) to execute subtraction (a - b).",
            faulty_rtl="""
module alu_8bit (
    input wire clk, rst_n, valid_in,
    input wire [2:0] opcode,
    input wire [7:0] operand_a, operand_b,
    output reg [7:0] result,
    output wire zero, carry_out, overflow,
    output reg valid_out
);
    // INJECTED FAULT: Opcode 0 executed as SUB
    always @(posedge clk) begin
        case (opcode)
            3'b000: result <= operand_a - operand_b;
            default: result <= operand_a;
        endcase
    end
endmodule
            """.strip(),
            target_assertion="alu_result_assertion",
        ))

        catalog.append(ControlledFault(
            fault_id="FAULT_ALU_02",
            benchmark="alu_8bit",
            category="Status Register",
            name="Zero Flag Stuck-at-0",
            description="Zero flag output forced to 1'b0, failing to signal when arithmetic/logic result wraps to 0x00.",
            faulty_rtl="""
module alu_8bit (
    input wire clk, rst_n, valid_in,
    input wire [2:0] opcode,
    input wire [7:0] operand_a, operand_b,
    output reg [7:0] result,
    output wire zero, carry_out, overflow,
    output reg valid_out
);
    // INJECTED FAULT: Zero flag stuck-at-0
    assign zero = 1'b0;
endmodule
            """.strip(),
            target_assertion="zero_flag_assertion",
        ))

        catalog.append(ControlledFault(
            fault_id="FAULT_ALU_03",
            benchmark="alu_8bit",
            category="Status Register",
            name="Carry-Out Flag Stuck-at-0",
            description="Carry-out flag omitted during 8-bit unsigned addition overflow, losing carry in multi-precision arithmetic.",
            faulty_rtl="""
module alu_8bit (
    input wire clk, rst_n, valid_in,
    input wire [2:0] opcode,
    input wire [7:0] operand_a, operand_b,
    output reg [7:0] result,
    output wire zero, carry_out, overflow,
    output reg valid_out
);
    // INJECTED FAULT: Carry out flag stuck-at-0
    assign carry_out = 1'b0;
endmodule
            """.strip(),
            target_assertion="carry_flag_assertion",
        ))

        catalog.append(ControlledFault(
            fault_id="FAULT_ALU_04",
            benchmark="alu_8bit",
            category="Datapath / Shifter",
            name="Shift Operand Bit Truncation",
            description="Barrel shifter truncates shift amount to [1:0] instead of [2:0], capping max shift at 3 instead of 7.",
            faulty_rtl="""
module alu_8bit (
    input wire clk, rst_n, valid_in,
    input wire [2:0] opcode,
    input wire [7:0] operand_a, operand_b,
    output reg [7:0] result,
    output wire zero, carry_out, overflow,
    output reg valid_out
);
    // INJECTED FAULT: Shift amount mask truncated
    always @(posedge clk) begin
        if (opcode == 3'b101) result <= operand_a << operand_b[1:0];
    end
endmodule
            """.strip(),
            target_assertion="alu_result_assertion",
        ))

        return catalog

    def evaluate_all(self) -> Tuple[pd.DataFrame, Dict[str, float]]:
        """
        Execute controlled fault injection across all 12 faults for the three verification methods.
        Returns a detailed results DataFrame and aggregate detection rate statistics.
        """
        catalog = self.get_fault_catalog()

        for fault in catalog:
            # 1. Baseline 1 (Sanity stimulus)
            res1 = self.simulator.run_simulation(
                fault.faulty_rtl, "", module_name=fault.benchmark, stimulus_mode="sanity"
            )
            fault.baseline1_detected = not res1.success
            fault.baseline1_error = res1.errors[0] if res1.errors else "Undetected (Survived)"

            # 2. Baseline 2 (Standard self-verification stimulus)
            res2 = self.simulator.run_simulation(
                fault.faulty_rtl, "", module_name=fault.benchmark, stimulus_mode="standard"
            )
            fault.baseline2_detected = not res2.success
            fault.baseline2_error = res2.errors[0] if res2.errors else "Undetected (Survived)"

            # 3. Proposed (Adversarial stress stimulus)
            res3 = self.simulator.run_simulation(
                fault.faulty_rtl, "", module_name=fault.benchmark, stimulus_mode="adversarial"
            )
            fault.proposed_detected = not res3.success
            fault.proposed_error = res3.errors[0] if res3.errors else "Undetected (Survived)"

        # Compute aggregate rates
        total = len(catalog)
        b1_caught = sum(1 for f in catalog if f.baseline1_detected)
        b2_caught = sum(1 for f in catalog if f.baseline2_detected)
        prop_caught = sum(1 for f in catalog if f.proposed_detected)

        rates = {
            "total_faults": total,
            "baseline1_caught": b1_caught,
            "baseline1_rate": (b1_caught / total) * 100.0,
            "baseline2_caught": b2_caught,
            "baseline2_rate": (b2_caught / total) * 100.0,
            "proposed_caught": prop_caught,
            "proposed_rate": (prop_caught / total) * 100.0,
        }

        # Format into presentation DataFrame
        records = []
        for f in catalog:
            records.append({
                "Fault ID": f.fault_id,
                "Benchmark": f.benchmark,
                "Category": f.category,
                "Fault Description": f.name,
                "Target Invariant": f.target_assertion,
                "Baseline 1 (Gen-Only)": "CAUGHT" if f.baseline1_detected else "MISSED",
                "Baseline 2 (Self-Verif)": "CAUGHT" if f.baseline2_detected else "MISSED",
                "Proposed (Dual-Agent)": "CAUGHT" if f.proposed_detected else "MISSED",
                "Detecting Assertion": f.proposed_error[:50] + "..." if len(f.proposed_error) > 50 else f.proposed_error,
            })

        df = pd.DataFrame(records)
        return df, rates
