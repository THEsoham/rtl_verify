"""
RTL Mutation Testing Engine
===========================
Generates and evaluates deliberate, syntactically-valid faults in synthesizable
Verilog RTL to measure verification testbench quality and fault detection capability.

Mutation Operators:
  1. AOR (Arithmetic Operator Replacement): + <-> -, * <-> /
  2. ROR (Relational Operator Replacement): == <-> !=, < <-> <=, > <-> >=
  3. COR (Conditional / Logical Operator Replacement): && <-> ||, & <-> |
  4. BIF (Bit Inversion / Condition Negation): enable <-> !enable
  5. OFF (Off-by-one Constants & Boundaries): FIFO_DEPTH <-> FIFO_DEPTH-1, count+1 <-> count+2
  6. RST (Reset State Corruption): count <= 0 <-> count <= 1
  7. STA (Stuck-At Fault): force signal / flag stuck-at constant 0 or 1
  8. MOR (Mode / Operation Replacement): shift left <-> shift right, opcode swap

Provides individual mutant reporting with line locations, diffs, survival status,
detecting assertions, and breakdowns across operator and functional fault categories.
Requires the baseline unmutated RTL to pass simulation before mutation testing begins.
Excludes uncompilable mutants from score calculation rather than calling them killed.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from .simulator import HDLSimulator, SimulationResult


@dataclass
class Mutant:
    mutant_id: str
    operator: str           # e.g., "AOR", "ROR", "COR", "BIF", "OFF", "RST", "STA", "MOR"
    category: str           # e.g., "Arithmetic", "Relational", "Logical", "Control", "Boundary", "Reset", "Stuck-At"
    line_number: int
    original_code: str
    mutated_code: str
    full_mutated_rtl: str
    description: str
    killed: bool = False
    killer_error: Optional[str] = None
    killer_assertion: Optional[str] = None
    failing_cycle: Optional[int] = None
    is_valid_compile: bool = True
    compile_error: Optional[str] = None


@dataclass
class MutationResult:
    total_mutants: int
    valid_mutants: int
    killed_mutants: int
    survived_mutants: int
    uncompilable_mutants: int
    mutation_score: float
    baseline_passed: bool = True
    baseline_error: Optional[str] = None
    mutants: List[Mutant] = field(default_factory=list)
    breakdown_by_category: Dict[str, Dict[str, int]] = field(default_factory=dict)
    breakdown_by_operator: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def summary(self) -> str:
        if not self.baseline_passed:
            return f"Baseline Simulation Failed: {self.baseline_error} (Mutation Testing Aborted)"
        uncomp_str = f", {self.uncompilable_mutants} excluded uncompilable" if self.uncompilable_mutants > 0 else ""
        return (
            f"Mutation Score: {self.mutation_score:.1f}% "
            f"({self.killed_mutants}/{self.valid_mutants} killed out of {self.valid_mutants} valid mutants, "
            f"{self.survived_mutants} survived{uncomp_str})"
        )


class RTLMutator:
    """
    Standardized RTL Mutation Testing Engine.
    Generates syntax-valid mutated RTL variants and evaluates testbench fault detection rate.
    Strictly validates baseline unmutated RTL before testing, and excludes uncompilable mutants.
    """

    OPERATOR_CATEGORIES = {
        "AOR": "Arithmetic",
        "ROR": "Relational",
        "COR": "Logical",
        "BIF": "Control",
        "OFF": "Boundary",
        "RST": "Reset",
        "STA": "Stuck-At",
        "MOR": "Control",
    }

    def __init__(self, simulator: Optional[HDLSimulator] = None):
        self.simulator = simulator or HDLSimulator()

    def generate_benchmark_mutants(self, benchmark_name: str, rtl_code: str) -> List[Mutant]:
        """
        Generate standardized 10 mutants for research benchmark modules.
        Guarantees identical number of mutants and operator diversity across benchmarks.
        """
        b_name = benchmark_name.lower()
        if "fifo" in b_name:
            return self._generate_fifo_mutants(rtl_code)
        elif "traffic" in b_name:
            return self._generate_traffic_light_mutants(rtl_code)
        elif "alu" in b_name:
            return self._generate_alu_mutants(rtl_code)
        else:
            return self.generate_generic_mutants(rtl_code, max_mutants=10)

    # ──────────────────────────────────────────────────────────────────────────
    # Standardized 10 Mutants: FIFO Buffer
    # ──────────────────────────────────────────────────────────────────────────
    def _generate_fifo_mutants(self, rtl: str) -> List[Mutant]:
        lines = rtl.splitlines()

        specs = [
            {
                "id": "MUT_FIFO_01_AOR",
                "op": "AOR",
                "cat": "Arithmetic",
                "pat": r"count\s*<=\s*count\s*\+\s*1|wr_ptr\s*<=\s*wr_ptr\s*\+\s*1",
                "fallback_pat": r"\+\s*(?:1'b1|1|5'd1)",
                "sub_fn": lambda line: re.sub(r"(\+\s*(?:1'b1|1|5'd1))", "- 1'b1", line, count=1),
                "desc": "Arithmetic Operator Replacement: Replaced count/pointer increment (+) with decrement (-)",
            },
            {
                "id": "MUT_FIFO_02_ROR",
                "op": "ROR",
                "cat": "Relational",
                "pat": r"full\s*=\s*\(?count\s*==|assign\s+full\s*=",
                "fallback_pat": r"==\s*(?:FIFO_DEPTH|DEPTH|16)",
                "sub_fn": lambda line: re.sub(r"==", "!=", line, count=1),
                "desc": "Relational Operator Replacement: Inverted full flag comparison (== to !=)",
            },
            {
                "id": "MUT_FIFO_03_COR",
                "op": "COR",
                "cat": "Logical",
                "pat": r"wr_en\s*&&\s*!full",
                "fallback_pat": r"&&\s*!full",
                "sub_fn": lambda line: re.sub(r"&&", "||", line, count=1),
                "desc": "Logical Operator Replacement: Changed write gating condition from && to ||",
            },
            {
                "id": "MUT_FIFO_04_BIF",
                "op": "BIF",
                "cat": "Control",
                "pat": r"if\s*\(!rst_n\)|if\s*\(rst_n\s*==\s*1'b0\)",
                "fallback_pat": r"!\s*rst_n",
                "sub_fn": lambda line: re.sub(r"!\s*rst_n", "rst_n", line, count=1),
                "desc": "Bit Inversion / Control Fault: Inverted active-low reset polarity condition",
            },
            {
                "id": "MUT_FIFO_05_OFF",
                "op": "OFF",
                "cat": "Boundary",
                "pat": r"count\s*==\s*FIFO_DEPTH|count\s*>=\s*FIFO_DEPTH",
                "fallback_pat": r"FIFO_DEPTH|DEPTH",
                "sub_fn": lambda line: re.sub(r"\b(FIFO_DEPTH|DEPTH)\b", r"(\1 - 1)", line, count=1),
                "desc": "Off-by-One Boundary Constant: Full flag asserted at depth-1 (count==15 instead of 16)",
            },
            {
                "id": "MUT_FIFO_06_OFF",
                "op": "OFF",
                "cat": "Boundary",
                "pat": r"count\s*<=\s*count\s*\+\s*(?:1'b1|1)",
                "fallback_pat": r"\+\s*(?:1'b1|1)",
                "sub_fn": lambda line: re.sub(r"(\+\s*)(?:1'b1|1)", r"\g<1>2'b10", line, count=1),
                "desc": "Off-by-One Constant Mutation: Counter step increment modified from 1 to 2",
            },
            {
                "id": "MUT_FIFO_07_RST",
                "op": "RST",
                "cat": "Reset",
                "pat": r"count\s*<=\s*(?:5'[bdh]0|0\b)",
                "fallback_pat": r"count\s*<=",
                "sub_fn": lambda line: re.sub(r"(\bcount\s*<=\s*)(?:5'[bdh]0|0\b|5'd0)", r"\g<1>5'd1", line, count=1),
                "desc": "Reset State Corruption: Asynchronous reset initializes counter to 1 instead of 0",
            },
            {
                "id": "MUT_FIFO_08_STA",
                "op": "STA",
                "cat": "Stuck-At",
                "pat": r"assign\s+full\s*=",
                "fallback_pat": r"full\s*<=",
                "sub_fn": lambda line: re.sub(r"(=|<=)\s*.*?;", r"\1 1'b0;", line, count=1),
                "desc": "Stuck-At Fault: Forced FIFO full status flag stuck-at-0",
            },
            {
                "id": "MUT_FIFO_09_COR",
                "op": "COR",
                "cat": "Logical",
                "pat": r"rd_en\s*&&\s*!empty|wr_en\s*&&\s*rd_en",
                "fallback_pat": r"&&\s*!empty",
                "sub_fn": lambda line: re.sub(r"&&", "||", line, count=1),
                "desc": "Logical Condition Corruption: Read gating condition modified (&& to ||)",
            },
            {
                "id": "MUT_FIFO_10_ROR",
                "op": "ROR",
                "cat": "Relational",
                "pat": r"empty\s*=\s*\(?count\s*==\s*0|assign\s+empty\s*=",
                "fallback_pat": r"==\s*(?:0|5'd0|5'b0)",
                "sub_fn": lambda line: re.sub(r"==\s*(?:0|5'[bdh]0)", "<= 1", line, count=1) if "==" in line else re.sub(r"=", "= (count <= 1); //", line, count=1),
                "desc": "Relational Operator Replacement: Empty asserted when count <= 1 (premature empty)",
            },
        ]

        return self._build_mutants_from_specs(lines, specs, module_name="fifo_sync")

    # ──────────────────────────────────────────────────────────────────────────
    # Standardized 10 Mutants: Traffic Light Controller FSM
    # ──────────────────────────────────────────────────────────────────────────
    def _generate_traffic_light_mutants(self, rtl: str) -> List[Mutant]:
        lines = rtl.splitlines()

        specs = [
            {
                "id": "MUT_TLC_01_AOR",
                "op": "AOR",
                "cat": "Arithmetic",
                "pat": r"timer\s*<=\s*timer\s*\+\s*1",
                "fallback_pat": r"\+\s*1",
                "sub_fn": lambda line: re.sub(r"(\+\s*1)", "- 1", line, count=1),
                "desc": "Arithmetic Operator Replacement: Timer increment (+) replaced with decrement (-)",
            },
            {
                "id": "MUT_TLC_02_ROR",
                "op": "ROR",
                "cat": "Relational",
                "pat": r"timer\s*>=\s*(?:MAIN_GREEN_CYCLES|10|\w+)",
                "fallback_pat": r">=\s*(?:MAIN_GREEN|10)",
                "sub_fn": lambda line: re.sub(r">=", "<", line, count=1),
                "desc": "Relational Operator Replacement: Inverted green duration comparison (>= to <)",
            },
            {
                "id": "MUT_TLC_03_COR",
                "op": "COR",
                "cat": "Logical",
                "pat": r"if\s*\(\s*emergency_override\s*\)|else\s+if\s*\(\s*emergency_override\s*\)",
                "fallback_pat": r"\bemergency_override\b(?!\s*[,;)])",
                "sub_fn": lambda line: re.sub(r"(\bemergency_override\b)", r"(\1 && !car_present_side)", line, count=1),
                "desc": "Logical Operator Replacement: Emergency preemption blocked if side car present",
            },
            {
                "id": "MUT_TLC_04_BIF",
                "op": "BIF",
                "cat": "Control",
                "pat": r"if\s*\(\s*pedestrian_req\s*\)",
                "fallback_pat": r"pedestrian_req",
                "sub_fn": lambda line: re.sub(r"(\bpedestrian_req\b)", r"(!\1)", line, count=1),
                "desc": "Bit Inversion / Control Fault: Inverted pedestrian walk button condition (!)",
            },
            {
                "id": "MUT_TLC_05_OFF",
                "op": "OFF",
                "cat": "Boundary",
                "pat": r"timer\s*>=\s*(?:YELLOW_CYCLES|3)",
                "fallback_pat": r"YELLOW_CYCLES|3",
                "sub_fn": lambda line: re.sub(r">=\s*(?:YELLOW_CYCLES|3)", ">= 1", line, count=1),
                "desc": "Off-by-Constant Boundary Mutation: Yellow light interval shortened from 3 to 1 cycle",
            },
            {
                "id": "MUT_TLC_06_RST",
                "op": "RST",
                "cat": "Reset",
                "pat": r"state\s*<=\s*(?:S_MAIN_GREEN|3'b000|0\b)",
                "fallback_pat": r"state\s*<=",
                "sub_fn": lambda line: re.sub(r"(state\s*<=\s*)(?:S_MAIN_GREEN|3'b000|0\b)", r"\g<1>3'd4", line, count=1),
                "desc": "Reset State Corruption: FSM resets to hazardous intermediate side yellow state (state 4)",
            },
            {
                "id": "MUT_TLC_07_STA",
                "op": "STA",
                "cat": "Stuck-At",
                "pat": r"side_light\s*<=\s*3'b100|side_light\s*<=",
                "fallback_pat": r"side_light\s*<=",
                "sub_fn": lambda line: re.sub(r"(side_light\s*<=\s*)(?:3'b100|3'b000|3'd4|0)", r"\g<1>3'b001", line, count=1),
                "desc": "Stuck-At Fault: Side light forced stuck-at Green (violates mutual exclusion invariant)",
            },
            {
                "id": "MUT_TLC_08_BIF",
                "op": "BIF",
                "cat": "Control",
                "pat": r"if\s*\(.*car_present_side|car_present_side\s*\|\|",
                "fallback_pat": r"\bcar_present_side\b(?!\s*[,;)])",
                "sub_fn": lambda line: re.sub(r"(\bcar_present_side\b)", r"(!\1)", line, count=1),
                "desc": "Bit Inversion: Inverted side street vehicle detection sensor signal",
            },
            {
                "id": "MUT_TLC_09_STA",
                "op": "STA",
                "cat": "Stuck-At",
                "pat": r"assign\s+emergency_active\s*=|emergency_active\s*<=",
                "fallback_pat": r"emergency_active",
                "sub_fn": lambda line: re.sub(r"(=|<=)\s*.*?;", r"\1 1'b0;", line, count=1),
                "desc": "Stuck-At Fault: Emergency override output forced stuck-at-0",
            },
            {
                "id": "MUT_TLC_10_ROR",
                "op": "ROR",
                "cat": "Relational",
                "pat": r"timer\s*>=\s*(?:ALL_RED_CYCLES|2)",
                "fallback_pat": r"ALL_RED_CYCLES|2",
                "sub_fn": lambda line: re.sub(r">=\s*(?:ALL_RED_CYCLES|2)", ">= 1", line, count=1),
                "desc": "Relational Operator Replacement: All-red intersection clearance interval cut to 1 cycle",
            },
        ]

        return self._build_mutants_from_specs(lines, specs, module_name="traffic_light")

    # ──────────────────────────────────────────────────────────────────────────
    # Standardized 10 Mutants: 8-Bit Registered ALU
    # ──────────────────────────────────────────────────────────────────────────
    def _generate_alu_mutants(self, rtl: str) -> List[Mutant]:
        lines = rtl.splitlines()

        specs = [
            {
                "id": "MUT_ALU_01_AOR",
                "op": "AOR",
                "cat": "Arithmetic",
                "pat": r"3'b000.*operand_a\s*\+\s*operand_b|operand_a\s*\+\s*operand_b",
                "fallback_pat": r"operand_a\s*\+\s*operand_b",
                "sub_fn": lambda line: re.sub(r"operand_a\s*\+\s*operand_b", "operand_a - operand_b", line, count=1),
                "desc": "Arithmetic Operator Replacement: ADD opcode executed as subtraction (-)",
            },
            {
                "id": "MUT_ALU_02_AOR",
                "op": "AOR",
                "cat": "Arithmetic",
                "pat": r"3'b001.*operand_a\s*-\s*operand_b|operand_a\s*-\s*operand_b",
                "fallback_pat": r"operand_a\s*-\s*operand_b",
                "sub_fn": lambda line: re.sub(r"operand_a\s*-\s*operand_b", "operand_a + operand_b", line, count=1),
                "desc": "Arithmetic Operator Replacement: SUB opcode executed as addition (+)",
            },
            {
                "id": "MUT_ALU_03_COR",
                "op": "COR",
                "cat": "Logical",
                "pat": r"3'b010.*operand_a\s*&\s*operand_b|operand_a\s*&\s*operand_b",
                "fallback_pat": r"operand_a\s*&\s*operand_b",
                "sub_fn": lambda line: re.sub(r"operand_a\s*&\s*operand_b", "operand_a | operand_b", line, count=1),
                "desc": "Logical Operator Replacement: Bitwise AND opcode executed as bitwise OR (|)",
            },
            {
                "id": "MUT_ALU_04_COR",
                "op": "COR",
                "cat": "Logical",
                "pat": r"3'b011.*operand_a\s*\|\s*operand_b|operand_a\s*\|\s*operand_b",
                "fallback_pat": r"operand_a\s*\|\s*operand_b",
                "sub_fn": lambda line: re.sub(r"operand_a\s*\|\s*operand_b", "operand_a ^ operand_b", line, count=1),
                "desc": "Logical Operator Replacement: Bitwise OR opcode executed as bitwise XOR (^)",
            },
            {
                "id": "MUT_ALU_05_MOR",
                "op": "MOR",
                "cat": "Control",
                "pat": r"3'b101.*operand_a\s*<<|operand_a\s*<<",
                "fallback_pat": r"<<",
                "sub_fn": lambda line: re.sub(r"<<", ">>", line, count=1),
                "desc": "Mode / Operation Replacement: Shift Left opcode inverted to Shift Right (>>)",
            },
            {
                "id": "MUT_ALU_06_STA",
                "op": "STA",
                "cat": "Stuck-At",
                "pat": r"assign\s+zero\s*=|zero\s*<=",
                "fallback_pat": r"zero\s*=",
                "sub_fn": lambda line: re.sub(r"(=|<=)\s*.*?;", r"\1 1'b0;", line, count=1),
                "desc": "Stuck-At Fault: Output zero flag forced stuck-at-0",
            },
            {
                "id": "MUT_ALU_07_STA",
                "op": "STA",
                "cat": "Stuck-At",
                "pat": r"assign\s+carry_out\s*=|carry_out\s*<=",
                "fallback_pat": r"carry_out\s*=",
                "sub_fn": lambda line: re.sub(r"(=|<=)\s*.*?;", r"\1 1'b0;", line, count=1),
                "desc": "Stuck-At Fault: Arithmetic carry_out flag forced stuck-at-0",
            },
            {
                "id": "MUT_ALU_08_ROR",
                "op": "ROR",
                "cat": "Relational",
                "pat": r"result\s*==\s*(?:8'b0|8'h00|0)|result_reg\s*==\s*0",
                "fallback_pat": r"==\s*(?:8'b0|8'h00|0)",
                "sub_fn": lambda line: re.sub(r"==", "!=", line, count=1),
                "desc": "Relational Operator Replacement: Inverted zero flag equality comparison (== to !=)",
            },
            {
                "id": "MUT_ALU_09_OFF",
                "op": "OFF",
                "cat": "Boundary",
                "pat": r"operand_b\[2:0\]",
                "fallback_pat": r"\[2:0\]",
                "sub_fn": lambda line: re.sub(r"\[2:0\]", "[1:0]", line, count=1),
                "desc": "Off-by-One / Boundary Fault: Barrel shifter operand truncated to [1:0] (max shift 3)",
            },
            {
                "id": "MUT_ALU_10_RST",
                "op": "RST",
                "cat": "Reset",
                "pat": r"result\s*<=\s*(?:8'h00|8'b0|0\b)",
                "fallback_pat": r"result\s*<=",
                "sub_fn": lambda line: re.sub(r"(\bresult\s*<=\s*)(?:8'[bdh]00?|0\b)", r"\g<1>8'h01", line, count=1),
                "desc": "Reset State Corruption: Pipeline output register resets to 0x01 instead of 0x00",
            },
        ]

        return self._build_mutants_from_specs(lines, specs, module_name="alu_8bit")

    def _build_mutants_from_specs(
        self, lines: List[str], specs: List[Dict[str, Any]], module_name: str = "top"
    ) -> List[Mutant]:
        """
        Builds mutants preserving original RTL lines, indentation, and signal names.
        Mutates only the intended operator on the target line.
        If a pattern is not found, never overwrites arbitrary lines.
        """
        mutants = []

        for s in specs:
            target_idx = None

            # Primary search
            for i, l in enumerate(lines):
                if re.search(s["pat"], l, re.IGNORECASE):
                    target_idx = i
                    break

            # Fallback search if primary pattern was not matched
            if target_idx is None and "fallback_pat" in s:
                for i, l in enumerate(lines):
                    if re.search(s["fallback_pat"], l, re.IGNORECASE):
                        target_idx = i
                        break

            # If still not found, do NOT corrupt arbitrary lines
            if target_idx is None:
                # Mark as unapplicable for this specific RTL code
                mutants.append(Mutant(
                    mutant_id=s["id"],
                    operator=s["op"],
                    category=s["cat"],
                    line_number=0,
                    original_code="// Pattern not found in candidate RTL",
                    mutated_code="// Unapplicable mutant",
                    full_mutated_rtl="\n".join(lines),
                    description=s["desc"],
                    killed=False,
                    is_valid_compile=False,
                    compile_error="Target pattern not present in candidate RTL"
                ))
                continue

            orig_line = lines[target_idx]
            sub_fn = s.get("sub_fn")
            if sub_fn:
                mut_line = sub_fn(orig_line)
            else:
                mut_line = orig_line

            # Append mutant identification comment for transparent traceability
            if not mut_line.endswith(f"// {s['id']}"):
                mut_line = f"{mut_line.rstrip()} // {s['id']}"

            mutated_lines = list(lines)
            mutated_lines[target_idx] = mut_line
            full_mutated = "\n".join(mutated_lines)

            # Compiler check using Verilator
            is_valid, errs = self.simulator.validate_verilog(full_mutated, module_name=module_name)

            mutants.append(Mutant(
                mutant_id=s["id"],
                operator=s["op"],
                category=s["cat"],
                line_number=target_idx + 1,
                original_code=orig_line.strip(),
                mutated_code=mut_line.strip(),
                full_mutated_rtl=full_mutated,
                description=s["desc"],
                is_valid_compile=is_valid,
                compile_error=errs[0] if (not is_valid and errs) else None,
            ))

        return mutants

    def generate_generic_mutants(self, rtl_code: str, max_mutants: int = 10) -> List[Mutant]:
        """Generic fallback mutant generator for arbitrary synthesizable Verilog modules."""
        mutants: List[Mutant] = []
        lines = rtl_code.splitlines()

        for idx, line in enumerate(lines):
            line_num = idx + 1
            stripped = line.strip()

            if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
                continue

            # AOR: + <-> -
            if " + " in line:
                m_line = line.replace(" + ", " - ", 1)
                mutants.append(self._create_generic_mutant("AOR", line_num, line, m_line, lines, idx, "Arithmetic (+ to -)"))
            elif " - " in line:
                m_line = line.replace(" - ", " + ", 1)
                mutants.append(self._create_generic_mutant("AOR", line_num, line, m_line, lines, idx, "Arithmetic (- to +)"))

            # ROR: == <-> !=
            if " == " in line:
                m_line = line.replace(" == ", " != ", 1)
                mutants.append(self._create_generic_mutant("ROR", line_num, line, m_line, lines, idx, "Relational (== to !=)"))

            # COR: && <-> ||
            if " && " in line:
                m_line = line.replace(" && ", " || ", 1)
                mutants.append(self._create_generic_mutant("COR", line_num, line, m_line, lines, idx, "Logical (&& to ||)"))

            # BIF: if (cond) -> if (!cond)
            if "if (" in line and "!" not in line:
                m_line = re.sub(r'if\s*\((.*?)\)', r'if (!(\1))', line, count=1)
                if m_line != line:
                    mutants.append(self._create_generic_mutant("BIF", line_num, line, m_line, lines, idx, "Control (Inverted condition)"))

            # OFF: 4'hF -> 4'hE or 15 -> 14
            if "4'hF" in line or "15" in line:
                m_line = line.replace("4'hF", "4'hE", 1).replace("15", "14", 1)
                mutants.append(self._create_generic_mutant("OFF", line_num, line, m_line, lines, idx, "Boundary (Off-by-one)"))

            # RST: reset corrupt
            if "<= 0" in line:
                m_line = line.replace("<= 0", "<= 1", 1)
                mutants.append(self._create_generic_mutant("RST", line_num, line, m_line, lines, idx, "Reset state corrupted"))

            # STA: stuck-at
            if "assign " in line and ";" in line:
                m_line = re.sub(r'=\s*[^;]+;', '= 1\'b0;', line, count=1)
                mutants.append(self._create_generic_mutant("STA", line_num, line, m_line, lines, idx, "Stuck-at constant 0"))

            if len(mutants) >= max_mutants:
                break

        return mutants[:max_mutants]

    def _create_generic_mutant(
        self,
        operator: str,
        line_num: int,
        orig_line: str,
        mut_line: str,
        lines: List[str],
        line_idx: int,
        description: str
    ) -> Mutant:
        mutated_lines = list(lines)
        mutated_lines[line_idx] = mut_line
        full_code = "\n".join(mutated_lines)
        cat = self.OPERATOR_CATEGORIES.get(operator, "General")
        mid = f"MUT_{operator}_{line_num:02d}_{abs(hash(mut_line)) % 1000:03d}"
        is_valid, errs = self.simulator.validate_verilog(full_code)
        return Mutant(
            mutant_id=mid,
            operator=operator,
            category=cat,
            line_number=line_num,
            original_code=orig_line.strip(),
            mutated_code=mut_line.strip(),
            full_mutated_rtl=full_code,
            description=description,
            is_valid_compile=is_valid,
            compile_error=errs[0] if (not is_valid and errs) else None,
        )

    def evaluate_testbench(
        self,
        rtl_code: str,
        testbench_code: str,
        module_name: str = "top",
        stimulus_mode: str = "adversarial",
        max_mutants: int = 10
    ) -> MutationResult:
        """
        Evaluate testbench fault detection on standardized mutants.
        
        Strict Evaluation Protocol:
        1. Validate candidate RTL and testbench with compiler.
        2. Require original unmutated baseline simulation to PASS (no assertion failures).
        3. Exclude uncompilable mutants from score denominator (never count compile error as killed).
        4. Count a mutant as KILLED if and only if baseline passed, simulation executed (cycles > 0),
           and that specific mutant produced a functional assertion mismatch during actual simulation.
        """
        # Step 1: Pre-simulation Baseline Check
        baseline_res = self.simulator.run_simulation(
            rtl_code,
            testbench_code,
            module_name=module_name,
            stimulus_mode=stimulus_mode
        )

        if baseline_res.is_compile_error:
            err = baseline_res.errors[0] if baseline_res.errors else "Compiler syntax error"
            return MutationResult(
                total_mutants=0,
                valid_mutants=0,
                killed_mutants=0,
                survived_mutants=0,
                uncompilable_mutants=0,
                mutation_score=0.0,
                baseline_passed=False,
                baseline_error=f"Unmutated baseline failed compiler validation: {err}",
                mutants=[],
            )

        if not baseline_res.success:
            err = baseline_res.errors[0] if baseline_res.errors else "Functional assertion failure"
            return MutationResult(
                total_mutants=0,
                valid_mutants=0,
                killed_mutants=0,
                survived_mutants=0,
                uncompilable_mutants=0,
                mutation_score=0.0,
                baseline_passed=False,
                baseline_error=f"Unmutated baseline failed simulation at cycle {baseline_res.failing_cycle}: {err}",
                mutants=[],
            )

        # Baseline passed! Now generate and evaluate mutants
        mutants = self.generate_benchmark_mutants(module_name, rtl_code)
        if not mutants:
            mutants = self.generate_generic_mutants(rtl_code, max_mutants=max_mutants)

        valid_mutants = []
        uncompilable_count = 0
        killed_count = 0
        operator_stats: Dict[str, Dict[str, int]] = {}
        category_stats: Dict[str, Dict[str, int]] = {}

        for mutant in mutants:
            op = mutant.operator
            cat = mutant.category

            # Step 2: Validate mutant synthesizability & syntax
            if not mutant.is_valid_compile:
                mutant.killed = False
                mutant.killer_error = f"Invalid experiment (uncompilable mutant): {mutant.compile_error}"
                uncompilable_count += 1
                continue

            valid_mutants.append(mutant)

            if op not in operator_stats:
                operator_stats[op] = {"total": 0, "killed": 0, "survived": 0}
            operator_stats[op]["total"] += 1

            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "killed": 0, "survived": 0}
            category_stats[cat]["total"] += 1

            # Step 3: Run simulation against the mutant with the EXACT same testbench
            sim_res = self.simulator.run_simulation(
                mutant.full_mutated_rtl,
                testbench_code,
                module_name=module_name,
                stimulus_mode=stimulus_mode
            )

            # If simulation experienced a compile error, exclude it from calculation
            if sim_res.is_compile_error:
                mutant.is_valid_compile = False
                mutant.killed = False
                mutant.compile_error = sim_res.errors[0] if sim_res.errors else "Simulation compile error"
                mutant.killer_error = f"Invalid experiment: {mutant.compile_error}"
                valid_mutants.pop()
                uncompilable_count += 1
                operator_stats[op]["total"] -= 1
                category_stats[cat]["total"] -= 1
                continue

            # Step 4: A mutant is KILLED if and only if simulation detected an assertion error
            if not sim_res.success and sim_res.cycles_simulated > 0 and not sim_res.is_compile_error:
                mutant.killed = True
                mutant.killer_error = sim_res.errors[0] if sim_res.errors else "Assertion violation"
                mutant.killer_assertion = sim_res.failing_assertion or "assertion_mismatch"
                mutant.failing_cycle = sim_res.failing_cycle
                killed_count += 1
                operator_stats[op]["killed"] += 1
                category_stats[cat]["killed"] += 1
            else:
                mutant.killed = False
                operator_stats[op]["survived"] += 1
                category_stats[cat]["survived"] += 1

        n_valid = len(valid_mutants)
        survived_count = n_valid - killed_count
        score = (killed_count / max(1, n_valid)) * 100.0 if n_valid > 0 else 0.0

        return MutationResult(
            total_mutants=len(mutants),
            valid_mutants=n_valid,
            killed_mutants=killed_count,
            survived_mutants=survived_count,
            uncompilable_mutants=uncompilable_count,
            mutation_score=score,
            baseline_passed=True,
            mutants=mutants,
            breakdown_by_category=category_stats,
            breakdown_by_operator=operator_stats,
        )
