from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
import asyncio
import structlog
from rtl_verify.verification.iverilog import IcarusVerilog

log = structlog.get_logger()

@dataclass
class Mutation:
    mutation_id: int
    mutation_type: str  # operator, constant, signal
    original: str
    replacement: str
    line_number: int
    description: str

@dataclass 
class MutantResult:
    mutation: Mutation
    status: str  # killed, survived, timeout, error
    sim_output: str

@dataclass
class MutationTestResult:
    total: int
    killed: int
    survived: int  
    timeout: int
    error: int
    score: float  # killed / (total - error) * 100
    details: list[MutantResult]

class MutationEngine:
    def __init__(self, iverilog: IcarusVerilog):
        self.iverilog = iverilog
        self.arithmetic_swaps = {r'\+': '-', r'-': '+', r'\*': '/', r'/': '*'}
        self.bitwise_swaps = {r'&': '|', r'\|': '&', r'\^': '~^'}
        self.comparison_swaps = {r'==': '!=', r'!=': '==', r'<=': '>=', r'>=': '<=', r'<': '>', r'>': '<'}

    def generate_mutants(self, rtl_source: str) -> list[Mutation]:
        mutations = []
        mutation_id = 1
        lines = rtl_source.splitlines()
        
        for i, line in enumerate(lines, 1):
            if line.strip().startswith('//') or line.strip().startswith('/*'):
                continue
                
            # Arithmetic
            for op, rep in self.arithmetic_swaps.items():
                if re.search(op, line):
                    rep_val = rep.replace('\\', '')
                    mutations.append(Mutation(mutation_id, 'arithmetic', op.replace('\\', ''), rep_val, i, f"Changed {op.replace('\\', '')} to {rep_val}"))
                    mutation_id += 1
            
            # Comparison
            for op, rep in self.comparison_swaps.items():
                if op in line:
                    mutations.append(Mutation(mutation_id, 'comparison', op, rep, i, f"Changed {op} to {rep}"))
                    mutation_id += 1
                    
            # Conditional negation
            if 'if' in line and '(' in line and ')' in line:
                mutations.append(Mutation(mutation_id, 'conditional', 'if (', 'if (!(', i, "Negated condition"))
                mutation_id += 1
                
            # Constants
            if "1'b0" in line:
                mutations.append(Mutation(mutation_id, 'constant', "1'b0", "1'b1", i, "Flipped 1'b0 to 1'b1"))
                mutation_id += 1
            elif "1'b1" in line:
                mutations.append(Mutation(mutation_id, 'constant', "1'b1", "1'b0", i, "Flipped 1'b1 to 1'b0"))
                mutation_id += 1
                
        return mutations

    def apply_mutation(self, rtl_source: str, mutation: Mutation) -> str:
        lines = rtl_source.splitlines()
        idx = mutation.line_number - 1
        
        if mutation.mutation_type == 'conditional' and mutation.original == 'if (':
            lines[idx] = lines[idx].replace('if (', 'if (!(', 1)
            # Find the matching closing paren, but for simplicity we assume it's just basic regex replace
            lines[idx] = lines[idx].replace(')', '))', 1)
        else:
            lines[idx] = lines[idx].replace(mutation.original, mutation.replacement, 1)
            
        return '\n'.join(lines)

    async def run_mutation_testing(self, rtl_source: str, testbench_source: str, work_dir: Path) -> MutationTestResult:
        mutations = self.generate_mutants(rtl_source)
        results = []
        
        killed = 0
        survived = 0
        timeout = 0
        error = 0
        
        tb_path = work_dir / 'tb_mut.v'
        with open(tb_path, 'w') as f:
            f.write(testbench_source)
            
        for mut in mutations:
            mut_src = self.apply_mutation(rtl_source, mut)
            rtl_path = work_dir / f'mut_{mut.mutation_id}.v'
            out_path = work_dir / f'mut_{mut.mutation_id}.vvp'
            
            with open(rtl_path, 'w') as f:
                f.write(mut_src)
                
            comp_res = await self.iverilog.compile([rtl_path, tb_path], out_path)
            if not comp_res.success:
                results.append(MutantResult(mut, 'error', comp_res.stderr))
                error += 1
                continue
                
            sim_res = await self.iverilog.simulate(out_path, timeout=5)
            if sim_res.timeout_reached:
                results.append(MutantResult(mut, 'timeout', ''))
                timeout += 1
            elif not sim_res.passed:
                results.append(MutantResult(mut, 'killed', sim_res.stdout))
                killed += 1
            else:
                results.append(MutantResult(mut, 'survived', sim_res.stdout))
                survived += 1
                
        total = len(mutations)
        valid = total - error
        score = (killed / valid * 100) if valid > 0 else 0.0
        
        return MutationTestResult(
            total=total,
            killed=killed,
            survived=survived,
            timeout=timeout,
            error=error,
            score=score,
            details=results
        )
