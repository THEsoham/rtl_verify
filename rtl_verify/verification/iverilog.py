from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import structlog
from rtl_verify.config import settings
from rtl_verify.pipeline.runner import SubprocessRunner

log = structlog.get_logger()

@dataclass
class CompileResult:
    success: bool
    stdout: str
    stderr: str
    errors: list[str]
    warnings: list[str]

@dataclass
class SimResult:
    success: bool
    stdout: str
    stderr: str
    passed: bool
    test_count: int
    error_count: int
    errors: list[str]
    timeout_reached: bool

class IcarusVerilog:
    async def compile(self, sources: list[Path], output: Path, include_dirs: list[Path] | None = None) -> CompileResult:
        cmd = ['iverilog', '-g2012', '-Wall']
        
        if include_dirs:
            for d in include_dirs:
                d_wsl = SubprocessRunner.to_wsl_path(d)
                cmd.extend(['-I', d_wsl])
                
        out_wsl = SubprocessRunner.to_wsl_path(output)
        cmd.extend(['-o', out_wsl])
        
        for src in sources:
            cmd.append(SubprocessRunner.to_wsl_path(src))
            
        res = await SubprocessRunner.run(cmd)
        
        success = res.returncode == 0
        errors = [line for line in res.stderr.splitlines() if "error" in line.lower() or "syntax" in line.lower()]
        warnings = [line for line in res.stderr.splitlines() if "warning" in line.lower()]
        
        return CompileResult(
            success=success,
            stdout=res.stdout,
            stderr=res.stderr,
            errors=errors,
            warnings=warnings
        )

    async def simulate(self, vvp_file: Path, timeout: int | None = None) -> SimResult:
        vvp_wsl = SubprocessRunner.to_wsl_path(vvp_file)
        cmd = ['vvp', vvp_wsl]
        
        res = await SubprocessRunner.run(cmd, timeout=timeout)
        
        full_out = res.stdout + "\n" + res.stderr
        passed = False
        if "ALL TESTS PASSED" in full_out:
            passed = True
        elif "TESTS FAILED" in full_out or "$error" in full_out or "$fatal" in full_out:
            passed = False
            
        errors = []
        error_count = 0
        for line in full_out.splitlines():
            if "ERROR:" in line or "FAIL:" in line or "$error" in line or "$fatal" in line:
                errors.append(line.strip())
                error_count += 1
                
        return SimResult(
            success=res.returncode == 0 and not res.timed_out,
            stdout=res.stdout,
            stderr=res.stderr,
            passed=passed,
            test_count=0, # Parse from output if applicable
            error_count=error_count,
            errors=errors,
            timeout_reached=res.timed_out
        )
