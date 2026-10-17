"""Experiment Pipeline for Cross-Family RTL Verification.

Implements conditions:
- Condition A: Self-test (G tests G's design)
- Condition B: Same-family adversarial test with design access (G' tests G's design with spec+RTL)
- Condition B': Same-family adversarial test without design access (G' tests G's design with spec only)
- Condition C: Cross-family adversarial test with design access (T tests G's design with spec+RTL)
- Condition C': Cross-family adversarial test without design access (T tests G's design with spec only)
- Condition D: Compute-matched self-test baseline (G tests G's design with budget matched to C)

Enforces:
- Fixed testbench contract (self-checking, single status line, $finish).
- Non-vacuity gate: valid testbenches must FAIL on a known-wrong (inverted-output) gate design.
- Reusable candidate RTL generation: RTL generated once per (problem, generator) and reused across conditions.
- 4-state inequality check logging.
"""

from dataclasses import dataclass, field
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from v2.src.llm_client import LLMClient, LLMResponse
from v2.src.verilog_sim import VerilogSimulator, SimResult
from v2.src.mutator import VerilogMutator, Mutant
from v2.src.problems import Problem


# Prompt Templates
PROMPT_RTL_DESIGN = """You are an expert digital ASIC and FPGA Verilog design engineer.
Implement the module 'TopModule' satisfying the exact specification below.

SPECIFICATION:
{spec}

RULES:
1. Write clean, synthesizable, standard Verilog (IEEE 1364-2001/2005 or SystemVerilog 2012).
2. The module name MUST be 'TopModule'.
3. Output ONLY the module code enclosed in a ```verilog ... ``` code block.
4. Ensure all port names and bit-widths match the specification exactly.
"""

PROMPT_RTL_RETRY = """Your previous Verilog implementation failed compilation or simulation with Icarus Verilog:
{error}

Please fix the error and write ONLY the corrected Verilog code for 'TopModule'.
Enclose your code in a ```verilog ... ``` code block.

SPECIFICATION (for reference):
{spec}
"""

CONTRACT_INSTRUCTIONS = """STRICT TESTBENCH CONTRACT REQUIREMENTS:
1. The testbench module MUST be named 'tb'.
2. The design under test MUST be instantiated as 'TopModule dut ( ... );'.
3. The testbench MUST be self-checking.
4. When simulation completes, it MUST print EXACTLY ONE of the following status lines:
   $display("*** TEST RESULT: PASS ***"); // if all tests pass
   $display("*** TEST RESULT: FAIL ***"); // if any check fails or mismatch is detected
   Do NOT print this exact string anywhere else in the code.
5. Standard Mismatch Reporting: Whenever an assertion check fails, print the standard mismatch line before FAIL:
   $display("MISMATCH: cycle=%0d time=%0t signal=<name> expected=%h actual=%h", cycle_count, $time, expected_val, actual_val);
6. The simulation MUST terminate cleanly with $finish;
7. Output ONLY the testbench code enclosed in a ```verilog ... ``` block.
8. Stimulus guidance: Keep stimulus concise (5-20 meaningful test vectors or a bounded loop). Do NOT repeat hundreds of unrolled lines. End promptly with $finish; and endmodule.
9. Drive ONLY input ports: Declare inputs as regs, outputs as wires. Only assign values to input regs. Do NOT drive DUT outputs or internal variables.
10. 4-State Output Equality: Always use `!==` (case inequality) for output assertions against expected values (e.g. `if (out !== expected) begin $display("MISMATCH: cycle=%0d time=%0t signal=out expected=%h actual=%h", cycle_count, $time, expected, out); errors = errors + 1; end`). Do NOT use `!=` or `==`.

Example structure:
```verilog
`timescale 1ns/1ps
module tb;
    // 1. Declare inputs as regs, outputs as wires
    // 2. Instantiate TopModule dut ( ... );
    // 3. Stimulus & self-checking:
    integer errors = 0;
    integer cycle_count = 0;
    initial begin
        // Apply stimulus and verify outputs
        // If an output is wrong:
        //   $display("MISMATCH: cycle=%0d time=%0t signal=out expected=%h actual=%h", cycle_count, $time, expected, out);
        //   errors = errors + 1;
        #10;
        if (errors == 0) begin
            $display("*** TEST RESULT: PASS ***");
        end else begin
            $display("*** TEST RESULT: FAIL ***");
        end
        $finish;
    end
endmodule
```"""

PROMPT_TB_SELF = """You are an RTL verification engineer.
Write a comprehensive, self-checking Verilog testbench named 'tb' to thoroughly verify the module 'TopModule'.

{contract}

SPECIFICATION:
{spec}

CANDIDATE RTL:
```verilog
{rtl}
```
"""

PROMPT_TB_ADVERSARIAL_SPEC_RTL = """You are an adversarial hardware verification red-team engineer.
Your goal is to FIND FLAWS and EXPOSE BUGS in the candidate RTL implementation shown below.
Do not assume the design is correct. Specifically test boundary conditions, off-by-one errors,
corner cases, overflow, and illegal transitions.

{contract}

SPECIFICATION:
{spec}

CANDIDATE RTL TO ATTACK:
```verilog
{rtl}
```
"""

PROMPT_TB_ADVERSARIAL_SPEC_ONLY = """You are an adversarial hardware verification red-team engineer.
Your goal is to write a rigorous, self-checking testbench based STRICTLY on the specification below.
Do not see or rely on the implementation. Write tests covering all functional requirements, edge cases,
and corner conditions.

{contract}

SPECIFICATION:
{spec}
"""

PROMPT_TB_RETRY = """Your previous testbench failed compilation, violated the contract, or was vacuous:
{error}

Please fix the error and write ONLY the corrected testbench.
Remember the strict contract:
- Module name MUST be 'tb'.
- Instantiate 'TopModule dut ( ... );'.
- Must be self-checking using '!==' for assertions.
- Drive ONLY input ports (regs). Do NOT assign to DUT outputs or internal variables.
- Keep stimulus concise (5-20 test vectors or a loop).
- Must print EXACTLY ONE line on completion:
  $display("*** TEST RESULT: PASS ***"); OR $display("*** TEST RESULT: FAIL ***");
- Must end with $finish; and endmodule.

SPECIFICATION OF TopModule (for reference):
{spec}

Now write ONLY the corrected testbench `module tb; ... endmodule` verifying TopModule:
"""

PROMPT_TB_TEMPLATE_SELF = """You are an RTL verification engineer writing testbench stimulus for TopModule.
The framework supplies the module shell, clock (clk), reset (reset), and DUT instance.
You must provide ONLY procedural stimulus and assertion statements to insert into an 'initial begin ... end' block.

RULES:
1. Drive inputs: e.g. 'in = 0; #10;'
2. Assert outputs: use 'if (out !== expected) begin $display("MISMATCH: cycle=%0d time=%0t signal=out expected=%h actual=%h", cycle_count, $time, expected, out); errors = errors + 1; end'
3. Write concise, meaningful stimulus (5-20 test vectors or a bounded loop).
4. Do NOT declare modules, ports, or use 'assign'. Do NOT assign to output wires.
5. Output ONLY the procedural statements enclosed in a ```verilog ... ``` code block.

SPECIFICATION:
{spec}

CANDIDATE RTL:
```verilog
{rtl}
```
"""

PROMPT_TB_TEMPLATE_ADVERSARIAL_SPEC_RTL = """You are an adversarial hardware verification red-team engineer.
Your goal is to FIND FLAWS and EXPOSE BUGS in the candidate RTL implementation shown below.
The framework supplies the module shell, clock (clk), reset (reset), and DUT instance.
You must provide ONLY procedural stimulus and assertion statements to insert into an 'initial begin ... end' block.

RULES:
1. Drive inputs: e.g. 'in = 0; #10;'
2. Assert outputs: use 'if (out !== expected) begin $display("MISMATCH: cycle=%0d time=%0t signal=out expected=%h actual=%h", cycle_count, $time, expected, out); errors = errors + 1; end'
3. Test boundary conditions, off-by-one errors, corner cases, and overflow.
4. Do NOT declare modules, ports, or use 'assign'. Do NOT assign to output wires.
5. Output ONLY the procedural statements enclosed in a ```verilog ... ``` code block.

SPECIFICATION:
{spec}

CANDIDATE RTL TO ATTACK:
```verilog
{rtl}
```
"""

PROMPT_TB_TEMPLATE_ADVERSARIAL_SPEC_ONLY = """You are an adversarial hardware verification red-team engineer.
Your goal is to write rigorous stimulus based STRICTLY on the specification below.
The framework supplies the module shell, clock (clk), reset (reset), and DUT instance.
You must provide ONLY procedural stimulus and assertion statements to insert into an 'initial begin ... end' block.

RULES:
1. Drive inputs: e.g. 'in = 0; #10;'
2. Assert outputs: use 'if (out !== expected) begin $display("MISMATCH: cycle=%0d time=%0t signal=out expected=%h actual=%h", cycle_count, $time, expected, out); errors = errors + 1; end'
3. Test all requirements, edge cases, and reset conditions.
4. Do NOT declare modules, ports, or use 'assign'. Do NOT assign to output wires.
5. Output ONLY the procedural statements enclosed in a ```verilog ... ``` code block.

SPECIFICATION:
{spec}
"""

PROMPT_TB_TEMPLATE_RETRY = """Your previous testbench stimulus produced a compilation or simulation error:
{error}

Please fix the error and write ONLY the corrected stimulus statements for TopModule.
Output ONLY Verilog statements enclosed in a ```verilog ... ``` code block.

SPECIFICATION (for reference):
{spec}
"""


def parse_ports_from_verilog(golden_code: str) -> List[dict]:
    """Extract port definitions with widths and directions."""
    m = re.search(r"module\s+\w+\s*(?:#\s*\([^)]*\)\s*)?\((.*?)\);", golden_code, re.DOTALL)
    if not m:
        port_pat = re.compile(r"(input|output)\s+(?:reg\s+|wire\s+)?(?:signed\s+)?(?:\[([^\]]+)\]\s+)?(\w+)")
        ports = []
        for pm in port_pat.finditer(golden_code):
            ports.append({"dir": pm.group(1), "width": f"[{pm.group(2)}]" if pm.group(2) else "", "name": pm.group(3)})
        return ports

    header = m.group(1)
    items = re.split(r",(?![^\[]*\])", header)
    ports = []
    current_dir = "input"
    for item in items:
        item = item.strip()
        if not item:
            continue
        pm = re.match(r"(input|output|inout)?\s*(?:wire|reg)?\s*(\[[^\]]+\])?\s*(\w+)", item)
        if pm:
            pdir = pm.group(1) or current_dir
            current_dir = pdir
            pwidth = pm.group(2) or ""
            pname = pm.group(3)
            ports.append({"dir": pdir, "width": pwidth, "name": pname})
    return ports


def build_testbench_template_scaffold(golden_rtl: str, stimulus_body: str) -> str:
    """Build a complete testbench around model-supplied stimulus and assertions."""
    ports = parse_ports_from_verilog(golden_rtl)
    clk_name = None
    rst_name = None
    rst_active_low = False

    lines = ["`timescale 1ns/1ps", "module tb;"]
    conns = []
    for p in ports:
        if p["dir"] == "input":
            lines.append(f"  reg {p['width']} {p['name']};")
            pname_lower = p["name"].lower()
            if pname_lower in ["clk", "clock"]:
                clk_name = p["name"]
            elif pname_lower in ["rst_n", "resetn"]:
                rst_name = p["name"]
                rst_active_low = True
            elif pname_lower in ["rst", "reset"]:
                rst_name = p["name"]
                rst_active_low = False
        else:
            lines.append(f"  wire {p['width']} {p['name']};")
        conns.append(f".{p['name']}({p['name']})")

    lines.append(f"  TopModule dut ({', '.join(conns)});\n")
    if clk_name:
        lines.append(f"  initial begin {clk_name} = 0; forever #5 {clk_name} = ~{clk_name}; end\n")

    lines.append("  integer errors = 0;\n")
    lines.append("  integer cycle_count = 0;\n")
    if clk_name:
        lines.append(f"  always @(posedge {clk_name}) cycle_count = cycle_count + 1;\n")
    else:
        lines.append("  always #10 cycle_count = cycle_count + 1;\n")
    lines.append("  initial begin")
    for p in ports:
        if p["dir"] == "input":
            lines.append(f"    {p['name']} = 0;")

    val_assert = "0" if rst_active_low else "1"
    val_deassert = "1" if rst_active_low else "0"
    if rst_name:
        lines.append(f"    {rst_name} = {val_assert};")
        if clk_name:
            lines.append(f"    repeat(2) @(posedge {clk_name});")
        else:
            lines.append("    #15;")
        lines.append(f"    {rst_name} = {val_deassert};")
        if clk_name:
            lines.append(f"    @(posedge {clk_name}); #1;")

    # Clean stimulus
    clean_stim = stimulus_body.strip()
    clean_stim = re.sub(r"^\s*module\s+\w+.*?;", "", clean_stim, flags=re.DOTALL)
    clean_stim = re.sub(r"^\s*initial\s+begin", "", clean_stim)
    clean_stim = re.sub(r"end\s+endmodule\s*$", "", clean_stim)
    clean_stim = re.sub(r"endmodule\s*$", "", clean_stim)
    clean_stim = re.sub(r"\$finish\s*;", "", clean_stim)

    # Strip duplicate declarations and illegal assignments to output wires
    for p in ports:
        pname = p["name"]
        clean_stim = re.sub(rf"\b(reg|wire|logic)\s+(?:\[[^\]]+\]\s+)?{pname}\s*;", "", clean_stim)
        if p["dir"] == "output":
            clean_stim = re.sub(rf"\bassign\s+{pname}\s*=\s*[^;]+;", "", clean_stim)
            clean_stim = re.sub(rf"\b{pname}\s*=\s*[^;]+;", "", clean_stim)
    clean_stim = re.sub(r"\b(integer|int)\s+(errors|cycle_count)\s*=\s*0\s*;", "", clean_stim)
    clean_stim = re.sub(r"\bassign\s+(\w+)\s*=\s*", r"\1 = ", clean_stim)

    # Standardize assertions in stimulus to print standard MISMATCH line
    if "MISMATCH:" not in clean_stim:
        def _repl_stim(m):
            sig = m.group(1)
            exp = m.group(2)
            return f'if ({sig} !== {exp}) begin $display("MISMATCH: cycle=%0d time=%0t signal={sig} expected=%h actual=%h", cycle_count, $time, {exp}, {sig}); errors = errors + 1; end'
        clean_stim = re.sub(
            r"if\s*\(\s*(\w+)\s*!==\s*([^)]+)\)\s*(?:begin\s*)?errors\s*=\s*errors\s*\+\s*1\s*;?",
            _repl_stim,
            clean_stim,
        )

    lines.append(f"    // Model-generated stimulus:\n{clean_stim}\n")
    lines.append("    #20;")
    lines.append("    if (errors == 0) begin")
    lines.append('      $display("*** TEST RESULT: PASS ***");')
    lines.append("    end else begin")
    lines.append('      $display("*** TEST RESULT: FAIL ***");')
    lines.append("    end")
    lines.append("    $finish;")
    lines.append("  end")
    lines.append("endmodule")
    return "\n".join(lines)


def extract_first_mismatch(sim_stdout: str, golden_rtl: str = "") -> Dict[str, Any]:
    """Extract first mismatch details purely from real simulator output.
    
    No regex on testbench source code.
    No default time=10.
    Classification rules use hardware semantics (cycle, reset state, rollover boundary)
    without fixed time thresholds.
    """
    m = re.search(
        r"MISMATCH:\s*(?:cycle=(\d+))?\s*(?:time=(\d+))?\s*(?:signal=(\w+))?\s*(?:expected=([0-9a-fxz_]+))?\s*(?:actual=([0-9a-fxz_]+))?",
        sim_stdout,
        re.IGNORECASE,
    )
    cycle = None
    mismatch_time = None
    signal = None
    expected = None
    actual = None
    raw_line = ""

    if m:
        cycle = int(m.group(1)) if m.group(1) is not None else None
        mismatch_time = int(m.group(2)) if m.group(2) is not None else None
        signal = m.group(3) if m.group(3) else "out"
        expected = m.group(4) if m.group(4) else None
        actual = m.group(5) if m.group(5) else None
        raw_line = m.group(0)
    else:
        for line in sim_stdout.splitlines():
            if any(k in line.lower() for k in ["error", "mismatch", "fail"]) and "test result" not in line.lower():
                raw_line = line.strip()
                break

        m_tm = re.search(r"(?:at\s+time|time\s*[:=]?)\s*(\d+)", sim_stdout, re.IGNORECASE)
        if m_tm:
            mismatch_time = int(m_tm.group(1))
        else:
            m_fin = re.search(r"\$finish called at\s+(\d+)", sim_stdout)
            if m_fin:
                mismatch_time = int(m_fin.group(1))

        m_exp = re.search(r"(?:expected|exp)\s*[:=]?\s*([0-9a-fxz_]+)", sim_stdout, re.IGNORECASE)
        if m_exp:
            expected = m_exp.group(1)
        m_act = re.search(r"(?:actual|got)\s*[:=]?\s*([0-9a-fxz_]+)", sim_stdout, re.IGNORECASE)
        if m_act:
            actual = m_act.group(1)

        m_sig = re.search(r"(?:signal|sig|port)\s*[:=]?\s*(\w+)", sim_stdout, re.IGNORECASE)
        signal = m_sig.group(1) if m_sig else "out"

        if mismatch_time is not None:
            cycle = mismatch_time // 10000

    is_seq = any(kw in golden_rtl.lower() for kw in ["posedge", "negedge", "clk", "clock"])
    has_rst = any(kw in golden_rtl.lower() for kw in ["reset", "rst", "areset", "clear"])

    if not is_seq:
        category = "other"
    elif cycle == 0 or (mismatch_time is not None and mismatch_time == 0):
        category = "wrong_initial_value"
    elif any(k in raw_line.lower() for k in ["wrap", "rollover", "terminal", "count10", "count1k", "count15", "timer"]) or (
        str(expected).lower() in ["9", "10", "15", "0", "1000"] and any(kw in golden_rtl.lower() for kw in ["count", "timer"])
    ):
        category = "wrong_wrap_value"
    elif has_rst and (any(k in raw_line.lower() for k in ["rst", "reset"]) or (cycle is not None and cycle in [1, 2])):
        category = "wrong_reset_behavior"
    elif is_seq:
        category = "off_by_one_timing"
    else:
        category = "other"

    return {
        "cycle": cycle,
        "time": mismatch_time,
        "signal": signal,
        "expected": expected,
        "actual": actual,
        "category": category,
        "raw_line": raw_line if raw_line else "No mismatch line in simulator output",
    }


def sanitize_testbench(code: str) -> str:
    """Ensure testbench has timescale and clean formatting with standardized mismatch instrumentation."""
    code = code.strip()
    if not code.startswith("`timescale"):
        code = "`timescale 1ns/1ps\n" + code

    # Inject cycle counter and standard MISMATCH line on assertions if not present
    if "MISMATCH:" not in code:
        if "cycle_count" not in code:
            code = re.sub(r"(\binteger\s+errors\s*=\s*0\s*;)", r"\1\n    integer cycle_count = 0;", code)
            code = re.sub(r"(#\d+\s*;)", r"\1 cycle_count = cycle_count + 1;", code)

        def _add_mismatch_display(m):
            sig = m.group(1)
            exp = m.group(2)
            return f'if ({sig} !== {exp}) begin $display("MISMATCH: cycle=%0d time=%0t signal={sig} expected=%h actual=%h", cycle_count, $time, {exp}, {sig}); errors = errors + 1; end'

        code = re.sub(
            r"if\s*\(\s*(\w+)\s*!==\s*([^)]+)\)\s*(?:begin\s*)?errors\s*=\s*errors\s*\+\s*1\s*;?",
            _add_mismatch_display,
            code,
        )
    return code


def build_inverted_gate(golden_rtl: str) -> Optional[str]:
    """Build a known-wrong design that inverts all output ports for non-vacuity checking."""
    m_decl = re.search(r"\bmodule\s+(\w+)\s*(?:#\s*\([^)]*\)\s*)?\((.*?)\);", golden_rtl, re.DOTALL)
    if not m_decl:
        return None
    orig_name = m_decl.group(1)
    header = m_decl.group(2)

    port_pat = re.compile(r"(input|output|inout)\s+(?:reg\s+|wire\s+)?(?:signed\s+)?(?:\[([^\]]+)\]\s+)?(\w+)")
    ports = []
    for item in re.split(r",(?![^\[]*\])", header):
        item = item.strip()
        pm = port_pat.match(item)
        if pm:
            ports.append({
                "dir": pm.group(1),
                "width": f"[{pm.group(2)}]" if pm.group(2) else "",
                "name": pm.group(3),
            })

    top_lines = ["module TopModule ("]
    port_decls = [f"  {p['dir']} {p['width']} {p['name']}" for p in ports]
    top_lines.append(",\n".join(port_decls))
    top_lines.append(");\n")

    conns = []
    for p in ports:
        if p["dir"] == "input":
            conns.append(f".{p['name']}({p['name']})")
        else:
            top_lines.append(f"  wire {p['width']} g_{p['name']};")
            top_lines.append(f"  assign {p['name']} = ~g_{p['name']};\n")
            conns.append(f".{p['name']}(g_{p['name']})")

    top_lines.append(f"  GoldenRef ref_inst ({', '.join(conns)});\n")
    top_lines.append("endmodule\n")

    golden_ref = re.sub(r"\bmodule\s+" + orig_name, "module GoldenRef", golden_rtl, count=1)
    return "\n".join(top_lines) + "\n" + golden_ref


@dataclass
class TrialResult:
    """Outcome of one experimental trial under a condition."""
    problem_id: str
    condition: str
    generator_id: str
    tester_id: str
    seed: int
    arm: str = "freeform"  # "freeform" or "template"

    # RTL Generation
    design_code: str = ""
    design_compiled: bool = False
    design_passed_golden_tb: bool = False
    design_sim_mismatches: int = 0
    generator_retries: int = 0
    generator_retry_tokens: int = 0

    # Testbench Generation & Contract
    test_code: str = ""
    test_compiled: bool = False
    test_contract_valid: bool = False
    test_contract_error: str = ""
    test_passed_golden_rtl: bool = False  # Validity gate: compiled & contract valid & passes golden RTL & non-vacuous
    test_vacuous: bool = False            # True if testbench passed on known-wrong inverted design
    uses_4state_inequality: bool = True   # True if testbench checks outputs with !==
    false_rejection: bool = False
    tester_retries: int = 0
    tester_retry_tokens: int = 0

    # Natural Bug Evaluation (only when design_passed_golden_tb is False)
    natural_bug_tested: bool = False
    natural_bug_escaped: bool = False  # true if valid test reported PASS on naturally buggy design

    # Mutation Testing (on non-equivalent mutants of golden RTL)
    problem_mutants_total: int = 0
    mutants_total: int = 0
    mutants_killed: int = 0
    mutation_score: float = 0.0

    # Phase A2: Auditing & Traceability
    golden_sim_stdout: str = ""
    mutant_list: List[Dict[str, Any]] = field(default_factory=list)
    designs_used: Dict[str, str] = field(default_factory=dict)
    first_mismatch: Dict[str, Any] = field(default_factory=dict)

    # Metadata & Tokens
    generator_model_version: str = ""
    tester_model_version: str = ""
    trial_date: str = ""
    generator_tokens: int = 0
    tester_tokens: int = 0
    total_tokens: int = 0
    duration_sec: float = 0.0

    def to_dict(self) -> dict:
        return {
            "problem_id": self.problem_id,
            "condition": self.condition,
            "generator_id": self.generator_id,
            "tester_id": self.tester_id,
            "generator_model_version": self.generator_model_version,
            "tester_model_version": self.tester_model_version,
            "trial_date": self.trial_date,
            "seed": self.seed,
            "arm": self.arm,
            "design_code": self.design_code,
            "design_compiled": self.design_compiled,
            "design_passed_golden_tb": self.design_passed_golden_tb,
            "generator_retries": self.generator_retries,
            "generator_retry_tokens": self.generator_retry_tokens,
            "test_code": self.test_code,
            "test_compiled": self.test_compiled,
            "test_contract_valid": self.test_contract_valid,
            "test_contract_error": self.test_contract_error,
            "test_passed_golden_rtl": self.test_passed_golden_rtl,
            "test_vacuous": self.test_vacuous,
            "uses_4state_inequality": self.uses_4state_inequality,
            "false_rejection": self.false_rejection,
            "tester_retries": self.tester_retries,
            "tester_retry_tokens": self.tester_retry_tokens,
            "natural_bug_tested": self.natural_bug_tested,
            "natural_bug_escaped": self.natural_bug_escaped,
            "problem_mutants_total": self.problem_mutants_total,
            "mutants_total": self.mutants_total,
            "mutants_killed": self.mutants_killed,
            "mutation_score": round(self.mutation_score, 4),
            "golden_sim_stdout": self.golden_sim_stdout,
            "mutant_list": self.mutant_list,
            "designs_used": self.designs_used,
            "first_mismatch": self.first_mismatch,
            "generator_tokens": self.generator_tokens,
            "tester_tokens": self.tester_tokens,
            "total_tokens": self.total_tokens,
            "duration_sec": round(self.duration_sec, 4),
        }


class ExperimentPipeline:
    """Coordinates execution of cross-family verification experiments."""

    def __init__(
        self,
        llm_client: LLMClient,
        simulator: VerilogSimulator,
        mutator: VerilogMutator,
    ):
        self.llm_client = llm_client
        self.simulator = simulator
        self.mutator = mutator

    def generate_candidate_design(
        self,
        problem: Problem,
        gen_model_config: Dict[str, Any],
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Generate candidate RTL design once per (problem, generator) with 1 retry rule."""
        prompt_rtl = PROMPT_RTL_DESIGN.format(spec=problem.prompt_spec)
        resp_rtl = self.llm_client.generate(gen_model_config, prompt_rtl, seed=seed)
        candidate_rtl = resp_rtl.verilog_code
        generator_tokens = resp_rtl.total_tokens
        gen_retries = 0
        gen_retry_tokens = 0

        sim_ground_truth = self.simulator.compile_and_run(
            dut_code=candidate_rtl,
            tb_code=problem.golden_tb,
            ref_code=problem.golden_rtl,
        )

        if not sim_ground_truth.compile_ok:
            gen_retries = 1
            prompt_rtl_retry = PROMPT_RTL_RETRY.format(
                error=sim_ground_truth.compile_stderr,
                spec=problem.prompt_spec,
            )
            resp_rtl_retry = self.llm_client.generate(gen_model_config, prompt_rtl_retry, seed=seed + 1000)
            gen_retry_tokens = resp_rtl_retry.total_tokens
            generator_tokens += gen_retry_tokens
            candidate_rtl = resp_rtl_retry.verilog_code

            sim_ground_truth = self.simulator.compile_and_run(
                dut_code=candidate_rtl,
                tb_code=problem.golden_tb,
                ref_code=problem.golden_rtl,
            )

        return {
            "candidate_rtl": candidate_rtl,
            "design_compiled": sim_ground_truth.compile_ok,
            "design_passed_golden_tb": sim_ground_truth.passed and (sim_ground_truth.mismatches == 0),
            "design_sim_mismatches": sim_ground_truth.mismatches,
            "generator_retries": gen_retries,
            "generator_retry_tokens": gen_retry_tokens,
            "generator_tokens": generator_tokens,
            "generator_model_version": resp_rtl.exact_model_version,
            "generator_date": resp_rtl.date_called,
        }

    def _generate_testbench_with_retry(
        self,
        model_config: Dict[str, Any],
        initial_prompt: str,
        problem: Problem,
        golden_as_dut: str,
        seed: int,
    ) -> Tuple[str, SimResult, int, int, int, bool, str, str]:
        """Generate testbench with 1 retry rule and validate against golden RTL & non-vacuity gate.
        
        Returns:
            (tb_code, sim_val, retries, initial_tokens, retry_tokens, test_vacuous, exact_version, date_called)
        """
        resp_tb = self.llm_client.generate(model_config, initial_prompt, seed=seed)
        tb_code = sanitize_testbench(resp_tb.verilog_code)
        initial_tokens = resp_tb.total_tokens
        retries = 0
        retry_tokens = 0
        exact_version = resp_tb.exact_model_version
        date_called = resp_tb.date_called

        # Step 1: Validate against golden RTL enforcing contract
        sim_val = self.simulator.compile_and_run(
            dut_code=golden_as_dut,
            tb_code=tb_code,
            enforce_contract=True,
        )

        # Retry rule: exactly 1 retry for compile or contract failure
        if not sim_val.compile_ok or not sim_val.contract_valid:
            retries = 1
            err_msg = sim_val.compile_stderr if not sim_val.compile_ok else sim_val.contract_error
            retry_prompt = PROMPT_TB_RETRY.format(error=err_msg, spec=problem.prompt_spec)
            resp_retry = self.llm_client.generate(model_config, retry_prompt, seed=seed + 2000)
            retry_tokens = resp_retry.total_tokens

            tb_retry = sanitize_testbench(resp_retry.verilog_code)
            sim_retry = self.simulator.compile_and_run(
                dut_code=golden_as_dut,
                tb_code=tb_retry,
                enforce_contract=True,
            )
            tb_code = tb_retry
            sim_val = sim_retry

        # Step 2: Non-vacuity gate check
        test_vacuous = False
        if sim_val.compile_ok and sim_val.contract_valid and sim_val.passed:
            inv_gate = build_inverted_gate(problem.golden_rtl)
            if inv_gate:
                sim_inv = self.simulator.compile_and_run(
                    dut_code=inv_gate,
                    tb_code=tb_code,
                    enforce_contract=True,
                )
                if sim_inv.passed:
                    # Testbench passed on a known-wrong inverted design -> VACUOUS
                    test_vacuous = True
                    sim_val.contract_valid = False
                    sim_val.passed = False
                    sim_val.contract_error = "Vacuous testbench: passed on inverted output design"

        return tb_code, sim_val, retries, initial_tokens, retry_tokens, test_vacuous, exact_version, date_called

    def _generate_template_testbench_with_retry(
        self,
        model_config: Dict[str, Any],
        initial_prompt: str,
        problem: Problem,
        golden_as_dut: str,
        seed: int,
    ) -> Tuple[str, SimResult, int, int, int, bool, str, str]:
        """Generate stimulus statements, scaffold into testbench template, and validate."""
        resp_tb = self.llm_client.generate(model_config, initial_prompt, seed=seed)
        stim_code = resp_tb.verilog_code
        tb_code = build_testbench_template_scaffold(problem.golden_rtl, stim_code)
        initial_tokens = resp_tb.total_tokens
        retries = 0
        retry_tokens = 0
        exact_version = resp_tb.exact_model_version
        date_called = resp_tb.date_called

        # Validate against golden RTL enforcing contract
        sim_val = self.simulator.compile_and_run(
            dut_code=golden_as_dut,
            tb_code=tb_code,
            enforce_contract=True,
        )

        # Retry rule: exactly 1 retry for compile or contract failure
        if not sim_val.compile_ok or not sim_val.contract_valid:
            retries = 1
            err_msg = sim_val.compile_stderr if not sim_val.compile_ok else sim_val.contract_error
            retry_prompt = PROMPT_TB_TEMPLATE_RETRY.format(error=err_msg, spec=problem.prompt_spec)
            resp_retry = self.llm_client.generate(model_config, retry_prompt, seed=seed + 2000)
            retry_tokens = resp_retry.total_tokens

            stim_retry = resp_retry.verilog_code
            tb_retry = build_testbench_template_scaffold(problem.golden_rtl, stim_retry)
            sim_retry = self.simulator.compile_and_run(
                dut_code=golden_as_dut,
                tb_code=tb_retry,
                enforce_contract=True,
            )
            tb_code = tb_retry
            sim_val = sim_retry

        # Non-vacuity gate check
        test_vacuous = False
        if sim_val.compile_ok and sim_val.contract_valid and sim_val.passed:
            inv_gate = build_inverted_gate(problem.golden_rtl)
            if inv_gate:
                sim_inv = self.simulator.compile_and_run(
                    dut_code=inv_gate,
                    tb_code=tb_code,
                    enforce_contract=True,
                )
                if sim_inv.passed:
                    test_vacuous = True
                    sim_val.contract_valid = False
                    sim_val.passed = False
                    sim_val.contract_error = "Vacuous testbench: passed on inverted output design"

        return tb_code, sim_val, retries, initial_tokens, retry_tokens, test_vacuous, exact_version, date_called

    def run_problem_condition(
        self,
        problem: Problem,
        condition: str,
        gen_model_config: Dict[str, Any],
        test_model_config: Dict[str, Any],
        precomputed_mutants: Optional[List[Mutant]] = None,
        candidate_design: Optional[Dict[str, Any]] = None,
        seed: int = 42,
        arm: str = "freeform",
    ) -> TrialResult:
        """Run a single experimental trial on one problem under a specific condition."""
        start_time = time.time()
        gen_id = gen_model_config["id"]
        test_id = test_model_config["id"]

        # Step 0: Phase A1 Hard check for >= 8 non-equivalent mutants
        problem_mutants_total = 0
        valid_mutants = []
        mutant_records = []
        if precomputed_mutants is not None:
            valid_mutants = [m for m in precomputed_mutants if m.compiles and not m.is_equivalent]
            problem_mutants_total = len(valid_mutants)
            for m in precomputed_mutants:
                mutant_records.append({
                    "id": m.mutant_id,
                    "operator": m.operator,
                    "description": m.description,
                    "compiles": m.compiles,
                    "is_equivalent": m.is_equivalent,
                    "how_decided": "2000-vector differential simulation with rare reset" if m.compiles else "compile failure",
                    "exclusion_reason": m.exclusion_reason,
                })
            if problem_mutants_total < 8:
                raise ValueError(
                    f"[HARD CHECK FAILED - A1] Problem '{problem.problem_id}' has only {problem_mutants_total} "
                    f"non-equivalent mutants (< 8 minimum required). Benchmark run halts loudly for this problem!"
                )

        # Step 1: RTL Generation (Reused once per problem & generator)
        if candidate_design is not None:
            candidate_rtl = candidate_design["candidate_rtl"]
            design_compiled = candidate_design["design_compiled"]
            design_correct = candidate_design["design_passed_golden_tb"]
            design_mismatches = candidate_design.get("design_sim_mismatches", 0)
            gen_retries = candidate_design.get("generator_retries", 0)
            gen_retry_tokens = candidate_design.get("generator_retry_tokens", 0)
            generator_tokens = candidate_design.get("generator_tokens", 0)
        else:
            cand = self.generate_candidate_design(problem, gen_model_config, seed=seed)
            candidate_rtl = cand["candidate_rtl"]
            design_compiled = cand["design_compiled"]
            design_correct = cand["design_passed_golden_tb"]
            design_mismatches = cand.get("design_sim_mismatches", 0)
            gen_retries = cand.get("generator_retries", 0)
            gen_retry_tokens = cand.get("generator_retry_tokens", 0)
            generator_tokens = cand.get("generator_tokens", 0)

        # Step 2: Testbench Generation and Validity Gate with Contract Enforcement & Non-vacuity
        golden_as_dut = problem.golden_rtl.replace("RefModule", "TopModule")
        tester_tokens = 0
        total_tester_retries = 0
        total_tester_retry_tokens = 0
        candidate_testbenches: List[str] = []
        sim_val_results: List[SimResult] = []
        is_vacuous_any = False

        tester_model_version = ""
        tester_date = ""

        if arm == "template":
            # Template Arm execution
            if condition == "A":
                p_tb = PROMPT_TB_TEMPLATE_SELF.format(spec=problem.prompt_spec, rtl=candidate_rtl)
                tb, sim_val, r_cnt, init_tok, r_tok, vac, exact_v, d_cal = self._generate_template_testbench_with_retry(
                    gen_model_config, p_tb, problem, golden_as_dut, seed=seed
                )
            elif condition in ["B", "C"]:
                p_tb = PROMPT_TB_TEMPLATE_ADVERSARIAL_SPEC_RTL.format(spec=problem.prompt_spec, rtl=candidate_rtl)
                tb, sim_val, r_cnt, init_tok, r_tok, vac, exact_v, d_cal = self._generate_template_testbench_with_retry(
                    test_model_config, p_tb, problem, golden_as_dut, seed=seed
                )
            elif condition in ["B_prime", "C_prime"]:
                p_tb = PROMPT_TB_TEMPLATE_ADVERSARIAL_SPEC_ONLY.format(spec=problem.prompt_spec)
                tb, sim_val, r_cnt, init_tok, r_tok, vac, exact_v, d_cal = self._generate_template_testbench_with_retry(
                    test_model_config, p_tb, problem, golden_as_dut, seed=seed
                )
            elif condition == "D":
                p_tb = PROMPT_TB_TEMPLATE_SELF.format(spec=problem.prompt_spec, rtl=candidate_rtl)
                tb, sim_val, r_cnt, init_tok, r_tok, vac, exact_v, d_cal = self._generate_template_testbench_with_retry(
                    gen_model_config, p_tb, problem, golden_as_dut, seed=seed + 500
                )
            else:
                raise ValueError(f"Unknown condition: {condition}")
            candidate_testbenches.append(tb)
            sim_val_results.append(sim_val)
            tester_tokens += init_tok + r_tok
            total_tester_retries += r_cnt
            total_tester_retry_tokens += r_tok
            is_vacuous_any = vac
            tester_model_version = exact_v
            tester_date = d_cal
        else:
            # Free-form Arm execution
            if condition == "A":
                p_tb = PROMPT_TB_SELF.format(
                    contract=CONTRACT_INSTRUCTIONS,
                    spec=problem.prompt_spec,
                    rtl=candidate_rtl,
                )
                tb, sim_val, r_cnt, init_tok, r_tok, vac, exact_v, d_cal = self._generate_testbench_with_retry(
                    gen_model_config, p_tb, problem, golden_as_dut, seed=seed
                )
                candidate_testbenches.append(tb)
                sim_val_results.append(sim_val)
                tester_tokens += init_tok + r_tok
                total_tester_retries += r_cnt
                total_tester_retry_tokens += r_tok
                is_vacuous_any = vac
                tester_model_version = exact_v
                tester_date = d_cal

            elif condition in ["B", "C"]:
                p_tb = PROMPT_TB_ADVERSARIAL_SPEC_RTL.format(
                    contract=CONTRACT_INSTRUCTIONS,
                    spec=problem.prompt_spec,
                    rtl=candidate_rtl,
                )
                tb, sim_val, r_cnt, init_tok, r_tok, vac, exact_v, d_cal = self._generate_testbench_with_retry(
                    test_model_config, p_tb, problem, golden_as_dut, seed=seed
                )
                candidate_testbenches.append(tb)
                sim_val_results.append(sim_val)
                tester_tokens += init_tok + r_tok
                total_tester_retries += r_cnt
                total_tester_retry_tokens += r_tok
                is_vacuous_any = vac
                tester_model_version = exact_v
                tester_date = d_cal

            elif condition in ["B_prime", "C_prime"]:
                p_tb = PROMPT_TB_ADVERSARIAL_SPEC_ONLY.format(
                    contract=CONTRACT_INSTRUCTIONS,
                    spec=problem.prompt_spec,
                )
                tb, sim_val, r_cnt, init_tok, r_tok, vac, exact_v, d_cal = self._generate_testbench_with_retry(
                    test_model_config, p_tb, problem, golden_as_dut, seed=seed
                )
                candidate_testbenches.append(tb)
                sim_val_results.append(sim_val)
                tester_tokens += init_tok + r_tok
                total_tester_retries += r_cnt
                total_tester_retry_tokens += r_tok
                is_vacuous_any = vac
                tester_model_version = exact_v
                tester_date = d_cal

            elif condition == "D":
                p_tb = PROMPT_TB_SELF.format(
                    contract=CONTRACT_INSTRUCTIONS,
                    spec=problem.prompt_spec,
                    rtl=candidate_rtl,
                )
                tb, sim_val, r_cnt, init_tok, r_tok, vac, exact_v, d_cal = self._generate_testbench_with_retry(
                    gen_model_config, p_tb, problem, golden_as_dut, seed=seed + 500
                )
                candidate_testbenches.append(tb)
                sim_val_results.append(sim_val)
                tester_tokens += init_tok + r_tok
                total_tester_retries += r_cnt
                total_tester_retry_tokens += r_tok
                is_vacuous_any = vac
                tester_model_version = exact_v
                tester_date = d_cal
            else:
                raise ValueError(f"Unknown condition: {condition}")

        primary_tb = candidate_testbenches[0]
        primary_sim_val = sim_val_results[0]

        test_compiled = primary_sim_val.compile_ok
        test_contract_valid = primary_sim_val.contract_valid
        test_contract_error = primary_sim_val.contract_error
        # A testbench is VALID only if it compiles, follows the contract, passes golden RTL, and is non-vacuous
        test_passed_golden_rtl = primary_sim_val.compile_ok and primary_sim_val.contract_valid and primary_sim_val.passed
        false_rejection = primary_sim_val.compile_ok and primary_sim_val.contract_valid and not primary_sim_val.passed

        # Check 4-state inequality usage: !==
        uses_4state = "!==" in primary_tb

        # First Mismatch Extraction (Phase C4)
        first_mm = {}
        if not test_passed_golden_rtl:
            first_mm = extract_first_mismatch(primary_sim_val.sim_stdout, problem.golden_rtl)

        # Step 3: Natural Bug Detection
        # If candidate RTL was naturally buggy (failed golden testbench), does primary_tb catch it?
        natural_bug_tested = False
        natural_bug_escaped = False

        if not design_correct and test_passed_golden_rtl:
            natural_bug_tested = True
            escaped_all = True
            for tb in candidate_testbenches:
                sim_bug_check = self.simulator.compile_and_run(
                    dut_code=candidate_rtl,
                    tb_code=tb,
                    enforce_contract=True,
                )
                if not sim_bug_check.passed or sim_bug_check.mismatches > 0:
                    escaped_all = False
                    break
            natural_bug_escaped = escaped_all

        # Step 4: Mutation Testing (only for valid non-vacuous testbenches)
        mutants_evaluated = 0
        mutants_killed = 0

        if test_passed_golden_rtl and valid_mutants:
            mutants_evaluated = len(valid_mutants)
            for mut in valid_mutants:
                killed_by_any = False
                for tb in candidate_testbenches:
                    sim_mut = self.simulator.compile_and_run(
                        dut_code=mut.mutated_code,
                        tb_code=tb,
                        enforce_contract=True,
                    )
                    # Requirement 6: A mutant counts as killed ONLY if the testbench compiles, follows the contract, does not time out, and prints FAIL
                    if sim_mut.compile_ok and sim_mut.contract_valid and not sim_mut.timed_out and not sim_mut.passed:
                        killed_by_any = True
                        break

                if killed_by_any:
                    mutants_killed += 1

        ms = mutants_killed / max(1, mutants_evaluated) if mutants_evaluated > 0 else 0.0

        inv_gate = build_inverted_gate(problem.golden_rtl) or ""
        designs_used = {
            "candidate_rtl": candidate_rtl,
            "golden_rtl": problem.golden_rtl,
            "inverted_gate": inv_gate,
        }

        return TrialResult(
            problem_id=problem.problem_id,
            condition=condition,
            generator_id=gen_id,
            tester_id=test_id,
            generator_model_version=candidate_design.get("generator_model_version", "") if candidate_design else "",
            tester_model_version=tester_model_version,
            trial_date=tester_date or (candidate_design.get("generator_date", "") if candidate_design else time.strftime("%Y-%m-%d")),
            seed=seed,
            arm=arm,
            design_code=candidate_rtl,
            design_compiled=design_compiled,
            design_passed_golden_tb=design_correct,
            design_sim_mismatches=design_mismatches,
            generator_retries=gen_retries,
            generator_retry_tokens=gen_retry_tokens,
            test_code=primary_tb,
            test_compiled=test_compiled,
            test_contract_valid=test_contract_valid,
            test_contract_error=test_contract_error,
            test_passed_golden_rtl=test_passed_golden_rtl,
            test_vacuous=is_vacuous_any,
            uses_4state_inequality=uses_4state,
            false_rejection=false_rejection,
            tester_retries=total_tester_retries,
            tester_retry_tokens=total_tester_retry_tokens,
            natural_bug_tested=natural_bug_tested,
            natural_bug_escaped=natural_bug_escaped,
            problem_mutants_total=problem_mutants_total,
            mutants_total=mutants_evaluated,
            mutants_killed=mutants_killed,
            mutation_score=ms,
            golden_sim_stdout=primary_sim_val.sim_stdout,
            mutant_list=mutant_records,
            designs_used=designs_used,
            first_mismatch=first_mm,
            generator_tokens=generator_tokens,
            tester_tokens=tester_tokens,
            total_tokens=generator_tokens + tester_tokens,
            duration_sec=time.time() - start_time,
        )
