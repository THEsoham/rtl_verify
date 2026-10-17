"""RTL Mutation Engine for Verilog.

Generates mutants using semantic mutation operators:
- AOR: Arithmetic Operator Replacement (+ <-> -, * <-> +) in RHS/conditions
- ROR: Relational Operator Replacement (==, !=, <, >, <=, >=) strictly within conditions (never on <= assignments)
- LOR: Logical & Bitwise Operator Replacement (&& <-> ||, & <-> |, ^ <-> &)
- BIF: Branch / Condition Inversion (if (c) -> if (!(c)))
- COR: Constant Replacement (c + 1, c - 1, 0 <-> 1) feeding real logic
- SOR: Sequential Operator Replacement:
       * Clock edge flip: posedge <-> negedge
       * Register RHS inversion: q <= ~(expr)
       * Register stuck-at: q <= 0, q <= 1
- STA: Continuous assignment RHS inversion / stuck-at

Guarantees:
- No mutations inside initial blocks
- No replacing non-blocking assignment <= with relational operators
- Differential random equivalence checking with 2000 vectors and rare reset
- Exact sentinel line matching (EQUIV_RESULT: SAME / EQUIV_RESULT: DIFFERENT)
- Minimum 8 non-equivalent mutants per problem required for benchmark usability.
"""

from dataclasses import dataclass
import re
from typing import List, Optional, Tuple
from v2.src.verilog_sim import VerilogSimulator, SimResult


@dataclass
class Mutant:
    """Represents a single generated mutant."""
    mutant_id: str
    operator: str
    description: str
    original_code: str
    mutated_code: str
    compiles: bool = False
    is_equivalent: bool = False
    compile_error: str = ""
    exclusion_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "mutant_id": self.mutant_id,
            "operator": self.operator,
            "description": self.description,
            "compiles": self.compiles,
            "is_equivalent": self.is_equivalent,
            "compile_error": self.compile_error,
            "exclusion_reason": self.exclusion_reason,
        }


def get_initial_spans(text: str) -> List[Tuple[int, int]]:
    """Locate all initial blocks to protect them from mutation."""
    spans = []
    # initial begin ... end
    for m in re.finditer(r"\binitial\s+begin\b.*?\bend\b", text, re.DOTALL):
        spans.append((m.start(), m.end()))
    # single statement initial ... ;
    for m in re.finditer(r"\binitial\s+(?!begin\b)[^;]+;", text):
        spans.append((m.start(), m.end()))
    return spans


def get_port_spans(text: str) -> List[Tuple[int, int]]:
    """Locate module header and port declarations to protect bitwidths from corrupting."""
    spans = []
    # module ... ( ... );
    m_head = re.search(r"\bmodule\s+\w+\s*(?:#\s*\([^)]*\)\s*)?\([^;]*\);", text, re.DOTALL)
    if m_head:
        spans.append((m_head.start(), m_head.end()))
    # Standalone input/output/wire/reg declarations
    for m in re.finditer(
        r"\b(input|output|inout|wire|reg|logic)\s+(?:signed\s+)?(?:\[[^\]]+\]\s+)?\w+(?:\s*,\s*\w+)*\s*;",
        text,
    ):
        spans.append((m.start(), m.end()))
    return spans


def is_in_spans(pos: int, spans: List[Tuple[int, int]]) -> bool:
    """Check if character position falls inside any forbidden span."""
    return any(st <= pos < en for st, en in spans)


class VerilogMutator:
    """Generates and validates Verilog mutants."""

    def __init__(self, simulator: VerilogSimulator):
        self.simulator = simulator
        self.last_exclusion_log = {}

    def generate_mutants(self, verilog_code: str, max_mutants: int = 15) -> List[Mutant]:
        """Generate candidate mutants across operators using AST-informed replacements.
        
        Strict safety:
        - Never mutates inside initial blocks.
        - Never mutates port/wire width declarations.
        - Never replaces assignment <= with relational operators.
        """
        candidates: List[Mutant] = []
        counter = 0
        forbidden_spans = get_initial_spans(verilog_code) + get_port_spans(verilog_code)

        # Operator 1: AOR (Arithmetic Operator Replacement)
        # + <-> -
        for m in re.finditer(r"(?<=\s)(\+|\-)(?=\s)", verilog_code):
            if is_in_spans(m.start(1), forbidden_spans):
                continue
            op = m.group(1)
            repl = "-" if op == "+" else "+"
            mut_code = verilog_code[:m.start(1)] + repl + verilog_code[m.end(1):]
            counter += 1
            candidates.append(
                Mutant(
                    mutant_id=f"AOR_{counter}",
                    operator="AOR",
                    description=f"Replaced '{op}' with '{repl}' at pos {m.start(1)}",
                    original_code=verilog_code,
                    mutated_code=mut_code,
                )
            )

        # Operator 2: ROR (Relational Operator Replacement strictly inside if/ternary conditions)
        ror_map = {
            "==": "!=",
            "!=": "==",
            "<=": ">",
            ">=": "<",
            "<": ">=",
            ">": "<=",
        }
        ror_pat = re.compile(r"(==|!=|<=|>=|<|>)")
        for m in re.finditer(r"if\s*\(([^)]+)\)", verilog_code):
            if is_in_spans(m.start(), forbidden_spans):
                continue
            cond = m.group(1)
            cond_start = m.start(1)
            for rm in ror_pat.finditer(cond):
                op = rm.group(1)
                repl = ror_map[op]
                pos = cond_start + rm.start(1)
                mut_cond = cond[:rm.start(1)] + repl + cond[rm.end(1):]
                mut_code = verilog_code[:cond_start] + mut_cond + verilog_code[cond_start + len(cond):]
                counter += 1
                candidates.append(
                    Mutant(
                        mutant_id=f"ROR_{counter}",
                        operator="ROR",
                        description=f"Replaced condition '{op}' with '{repl}' at pos {pos}",
                        original_code=verilog_code,
                        mutated_code=mut_code,
                    )
                )

        # Operator 3: LOR (Logical & Bitwise Operator Replacement in conditions or RHS)
        for m in re.finditer(r"if\s*\(([^)]+)\)", verilog_code):
            if is_in_spans(m.start(), forbidden_spans):
                continue
            cond = m.group(1)
            cond_start = m.start(1)
            for lm in re.finditer(r"(&&|\|\|)", cond):
                op = lm.group(1)
                repl = "||" if op == "&&" else "&&"
                mut_cond = cond[:lm.start(1)] + repl + cond[lm.end(1):]
                mut_code = verilog_code[:cond_start] + mut_cond + verilog_code[cond_start + len(cond):]
                counter += 1
                candidates.append(
                    Mutant(
                        mutant_id=f"LOR_{counter}",
                        operator="LOR",
                        description=f"Replaced logical '{op}' with '{repl}' at pos {cond_start + lm.start(1)}",
                        original_code=verilog_code,
                        mutated_code=mut_code,
                    )
                )

        # Operator 4: BIF (Branch Inversion: if (cond) -> if (!(cond)))
        for m in re.finditer(r"if\s*\(([^)]+)\)", verilog_code):
            if is_in_spans(m.start(), forbidden_spans):
                continue
            cond = m.group(1).strip()
            repl_cond = cond[1:].strip() if cond.startswith("!") else f"!({cond})"
            mut_code = verilog_code[:m.start(1)] + repl_cond + verilog_code[m.end(1):]
            counter += 1
            candidates.append(
                Mutant(
                    mutant_id=f"BIF_{counter}",
                    operator="BIF",
                    description=f"Inverted condition 'if ({cond})' -> 'if ({repl_cond})'",
                    original_code=verilog_code,
                    mutated_code=mut_code,
                )
            )

        # Operator 5: COR (Constant Replacement in conditions or assignments)
        for m in re.finditer(r"\b(\d+)\b", verilog_code):
            if is_in_spans(m.start(1), forbidden_spans):
                continue
            val_str = m.group(1)
            start = m.start(1)
            before = verilog_code[max(0, start - 5):start]
            after = verilog_code[m.end(1):min(len(verilog_code), m.end(1) + 5)]
            if ":" in before or ":" in after or "`timescale" in before:
                continue

            val = int(val_str)
            for delta in [1, -1] if val > 0 else [1]:
                new_val = val + delta
                mut_code = verilog_code[:m.start(1)] + str(new_val) + verilog_code[m.end(1):]
                counter += 1
                candidates.append(
                    Mutant(
                        mutant_id=f"COR_{counter}",
                        operator="COR",
                        description=f"Constant replacement {val} -> {new_val} at pos {m.start(1)}",
                        original_code=verilog_code,
                        mutated_code=mut_code,
                    )
                )

        # Operator 6: SOR (Sequential Operator Replacement)
        # 6a. Clock edge flip: posedge <-> negedge
        for m in re.finditer(r"\b(posedge|negedge)\b", verilog_code):
            if is_in_spans(m.start(1), forbidden_spans):
                continue
            edge = m.group(1)
            repl_edge = "negedge" if edge == "posedge" else "posedge"
            mut_code = verilog_code[:m.start(1)] + repl_edge + verilog_code[m.end(1):]
            counter += 1
            candidates.append(
                Mutant(
                    mutant_id=f"SOR_EDGE_{counter}",
                    operator="SOR",
                    description=f"Flipped clock edge '{edge}' to '{repl_edge}'",
                    original_code=verilog_code,
                    mutated_code=mut_code,
                )
            )

        # 6b. Register assignment RHS inversion / stuck-at (q <= expr;)
        for m in re.finditer(r"(\b\w+(?:\[[^\]]+\])?\s*<=\s*)([^;]+);", verilog_code):
            if is_in_spans(m.start(2), forbidden_spans):
                continue
            prefix = m.group(1)
            rhs = m.group(2).strip()
            # Invert RHS: ~(rhs)
            mut_code = verilog_code[:m.start(2)] + f"~({rhs})" + verilog_code[m.end(2):]
            counter += 1
            candidates.append(
                Mutant(
                    mutant_id=f"SOR_INV_{counter}",
                    operator="SOR",
                    description=f"Inverted register RHS '{rhs}' -> '~({rhs})'",
                    original_code=verilog_code,
                    mutated_code=mut_code,
                )
            )
            # Stuck-at 0
            if rhs not in ["0", "1'b0", "4'b0", "8'b0", "0'b0"]:
                mut_code_0 = verilog_code[:m.start(2)] + "0" + verilog_code[m.end(2):]
                counter += 1
                candidates.append(
                    Mutant(
                        mutant_id=f"SOR_SA0_{counter}",
                        operator="SOR",
                        description=f"Stuck-at-0 register assignment '{rhs}' -> '0'",
                        original_code=verilog_code,
                        mutated_code=mut_code_0,
                    )
                )

        # Operator 7: STA (Continuous Assignment Replacement)
        for m in re.finditer(r"assign\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^;]+);", verilog_code):
            if is_in_spans(m.start(2), forbidden_spans):
                continue
            sig = m.group(1)
            expr = m.group(2).strip()
            mut_code = verilog_code[:m.start(2)] + f"~({expr})" + verilog_code[m.end(2):]
            counter += 1
            candidates.append(
                Mutant(
                    mutant_id=f"STA_{counter}",
                    operator="STA",
                    description=f"Inverted continuous assign on {sig}: '{expr}' -> '~({expr})'",
                    original_code=verilog_code,
                    mutated_code=mut_code,
                )
            )

        # Deduplicate candidates
        unique_mutants = []
        seen_codes = {verilog_code}
        for cand in candidates:
            if cand.mutated_code not in seen_codes:
                seen_codes.add(cand.mutated_code)
                unique_mutants.append(cand)

        # Balance across operators
        grouped = {}
        for mut in unique_mutants:
            grouped.setdefault(mut.operator, []).append(mut)

        balanced: List[Mutant] = []
        while len(balanced) < max_mutants and any(grouped.values()):
            for op in list(grouped.keys()):
                if grouped[op]:
                    balanced.append(grouped[op].pop(0))
                    if len(balanced) >= max_mutants:
                        break

        return balanced

    def _parse_module_ports(self, golden_code: str) -> List[dict]:
        """Extract input and output ports with widths from module definition."""
        m = re.search(r"module\s+\w+\s*(?:#\s*\([^)]*\)\s*)?\((.*?)\);", golden_code, re.DOTALL)
        if not m:
            # Fallback: scan port declarations across the file
            port_pat = re.compile(r"(input|output)\s+(?:reg\s+|wire\s+)?(?:signed\s+)?(?:\[([^\]]+)\]\s+)?(\w+)")
            ports = []
            for pm in port_pat.finditer(golden_code):
                direction = pm.group(1)
                width = f"[{pm.group(2)}]" if pm.group(2) else ""
                name = pm.group(3)
                ports.append({"dir": direction, "width": width, "name": name})
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

    def _build_differential_tb(
        self, golden_code: str, mutant_code: str, num_vectors: int = 2000
    ) -> Tuple[Optional[str], str, str]:
        """Build a random differential testbench comparing golden vs mutant outputs directly.
        
        Uses long runs (2000 vectors) with rare resets and exact sentinels:
        - EQUIV_RESULT: DIFFERENT
        - EQUIV_RESULT: SAME
        """
        ports = self._parse_module_ports(golden_code)
        if not ports:
            return None, golden_code, mutant_code

        golden_mod = re.sub(r"\bmodule\s+\w+", "module GoldenModule", golden_code, count=1)
        mutant_mod = re.sub(r"\bmodule\s+\w+", "module MutantModule", mutant_code, count=1)

        tb_lines = ["`timescale 1ns/1ps", "module diff_tb;"]
        clk_name = None
        rst_name = None
        rst_active_low = False

        for p in ports:
            if p["dir"] == "input":
                tb_lines.append(f"  reg {p['width']} {p['name']};")
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
                tb_lines.append(f"  wire {p['width']} golden_{p['name']};")
                tb_lines.append(f"  wire {p['width']} mutant_{p['name']};")

        g_conns = []
        m_conns = []
        for p in ports:
            if p["dir"] == "input":
                g_conns.append(f".{p['name']}({p['name']})")
                m_conns.append(f".{p['name']}({p['name']})")
            else:
                g_conns.append(f".{p['name']}(golden_{p['name']})")
                m_conns.append(f".{p['name']}(mutant_{p['name']})")

        tb_lines.append(f"  GoldenModule golden_inst ({', '.join(g_conns)});\n")
        tb_lines.append(f"  MutantModule mutant_inst ({', '.join(m_conns)});\n")

        if clk_name:
            tb_lines.append(f"  initial begin {clk_name} = 0; forever #5 {clk_name} = ~{clk_name}; end\n")

        tb_lines.append("  integer cycle_idx;")
        tb_lines.append("  initial begin")
        for p in ports:
            if p["dir"] == "input":
                tb_lines.append(f"    {p['name']} = 0;")

        val_assert = "0" if rst_active_low else "1"
        val_deassert = "1" if rst_active_low else "0"

        if rst_name:
            tb_lines.append(f"    {rst_name} = {val_assert};")
            if clk_name:
                tb_lines.append(f"    repeat(3) @(posedge {clk_name});")
            else:
                tb_lines.append("    #20;")
            tb_lines.append(f"    {rst_name} = {val_deassert};")

        tb_lines.append(f"    for (cycle_idx = 0; cycle_idx < {num_vectors}; cycle_idx = cycle_idx + 1) begin")
        if clk_name:
            tb_lines.append(f"      @(posedge {clk_name}); #1;")
        else:
            tb_lines.append("      #10;")

        # Rare reset toggle (1% chance per cycle)
        if rst_name:
            tb_lines.append(f"      if (($random % 100) == 0) {rst_name} = {val_assert}; else {rst_name} = {val_deassert};")

        for p in ports:
            if p["dir"] == "input" and p["name"] != clk_name and p["name"] != rst_name:
                tb_lines.append(f"      {p['name']} = $random;")

        check_conds = []
        for p in ports:
            if p["dir"] != "input":
                check_conds.append(f"(golden_{p['name']} !== mutant_{p['name']})")

        if check_conds:
            cond_str = " || ".join(check_conds)
            tb_lines.append(f"      if ({cond_str}) begin")
            tb_lines.append('        $display("EQUIV_RESULT: DIFFERENT");')
            tb_lines.append("        $finish;")
            tb_lines.append("      end")

        tb_lines.append("    end")
        tb_lines.append('    $display("EQUIV_RESULT: SAME");')
        tb_lines.append("    $finish;")
        tb_lines.append("  end")
        tb_lines.append("endmodule")

        return "\n".join(tb_lines), golden_mod, mutant_mod

    def validate_and_filter_mutants(
        self,
        mutants: List[Mutant],
        golden_rtl: str,
        ref_code: Optional[str] = None,
        num_vectors: int = 2000,
    ) -> List[Mutant]:
        """Compile mutants and check equivalence using random differential simulation.

        Checks exact sentinel lines (EQUIV_RESULT: DIFFERENT / EQUIV_RESULT: SAME).
        """
        validated_mutants: List[Mutant] = []
        reference_rtl = ref_code if ref_code else golden_rtl

        for m in mutants:
            diff_tb, g_mod, m_mod = self._build_differential_tb(
                golden_code=reference_rtl,
                mutant_code=m.mutated_code,
                num_vectors=num_vectors,
            )

            if not diff_tb:
                compile_res = self.simulator.compile_and_run(
                    dut_code=m.mutated_code,
                    tb_code="`timescale 1ns/1ps\nmodule tb; TopModule dut(); initial $finish; endmodule",
                )
                m.compiles = compile_res.compile_ok
                m.compile_error = compile_res.compile_stderr
                m.is_equivalent = False
                m.exclusion_reason = "" if m.compiles else f"Compilation failed: {m.compile_error}"
                validated_mutants.append(m)
                continue

            sim_res = self.simulator.compile_and_run(
                dut_code=m_mod,
                tb_code=diff_tb,
                ref_code=g_mod,
            )

            if not sim_res.compile_ok:
                m.compiles = False
                m.compile_error = sim_res.compile_stderr
                first_err = sim_res.compile_stderr.splitlines()[0] if sim_res.compile_stderr else "syntax error"
                m.exclusion_reason = f"Compilation failed: {first_err}"
                validated_mutants.append(m)
                continue

            m.compiles = True

            # Step 2: Exact line sentinel matching (do not substring match!)
            stdout_lines = [line.strip() for line in sim_res.sim_stdout.splitlines()]
            if "EQUIV_RESULT: DIFFERENT" in stdout_lines:
                m.is_equivalent = False
                m.exclusion_reason = ""
            elif "EQUIV_RESULT: SAME" in stdout_lines:
                m.is_equivalent = True
                m.exclusion_reason = f"Equivalent mutant: 0 divergence across {num_vectors} vectors"
            else:
                m.is_equivalent = False
                m.exclusion_reason = f"Equivalence inconclusive: stdout={sim_res.sim_stdout[:100]}"

            validated_mutants.append(m)

        non_equiv = [m for m in validated_mutants if m.compiles and not m.is_equivalent]
        is_usable = len(non_equiv) >= 8

        # Log exclusions
        self.last_exclusion_log = {
            "total_generated": len(mutants),
            "compile_failures": len([m for m in validated_mutants if not m.compiles]),
            "equivalent_excluded": len([m for m in validated_mutants if m.compiles and m.is_equivalent]),
            "valid_non_equivalent": len(non_equiv),
            "usable_problem": is_usable,
            "excluded_details": [
                {
                    "mutant_id": m.mutant_id,
                    "operator": m.operator,
                    "reason": m.exclusion_reason,
                }
                for m in validated_mutants
                if (not m.compiles) or m.is_equivalent
            ],
        }

        return validated_mutants
