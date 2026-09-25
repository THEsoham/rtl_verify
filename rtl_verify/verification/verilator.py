from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
import structlog
from rtl_verify.config import settings
from rtl_verify.pipeline.runner import SubprocessRunner
from rtl_verify.verification.iverilog import CompileResult, SimResult

log = structlog.get_logger()

@dataclass
class LintResult:
    success: bool
    warnings: list[str]
    errors: list[str]
    stdout: str
    stderr: str

@dataclass
class CoverageData:
    line_coverage: float | None
    branch_coverage: float | None
    toggle_coverage: float | None
    raw_text: str

class Verilator:
    async def lint(self, sources: list[Path]) -> LintResult:
        cmd = ['verilator', '--lint-only', '-Wall', '--language', '1800-2012']
        for src in sources:
            cmd.append(SubprocessRunner.to_wsl_path(src))
            
        res = await SubprocessRunner.run(cmd)
        
        errors = [line for line in res.stderr.splitlines() if "%Error:" in line]
        warnings = [line for line in res.stderr.splitlines() if "%Warning:" in line]
        
        return LintResult(
            success=res.returncode == 0,
            warnings=warnings,
            errors=errors,
            stdout=res.stdout,
            stderr=res.stderr
        )

    async def compile_sim(self, sources: list[Path], output_dir: Path, top_module: str, coverage: bool = True) -> CompileResult:
        cmd = ['verilator', '--cc', '--exe', '--build', '-Wall']
        if coverage:
            cmd.append('--coverage')
            
        cmd.extend(['-o', 'V' + top_module])
        cmd.extend(['--Mdir', SubprocessRunner.to_wsl_path(output_dir)])
        cmd.extend(['--top-module', top_module])
        
        for src in sources:
            cmd.append(SubprocessRunner.to_wsl_path(src))
            
        res = await SubprocessRunner.run(cmd)
        success = res.returncode == 0
        errors = [line for line in res.stderr.splitlines() if "error" in line.lower()]
        warnings = [line for line in res.stderr.splitlines() if "warning" in line.lower()]
        
        return CompileResult(
            success=success,
            stdout=res.stdout,
            stderr=res.stderr,
            errors=errors,
            warnings=warnings
        )

    async def run_sim(self, binary: Path, timeout: int | None = None) -> SimResult:
        bin_wsl = SubprocessRunner.to_wsl_path(binary)
        # Note: Assuming binary path includes directory
        cmd = [bin_wsl]
        
        res = await SubprocessRunner.run(cmd, timeout=timeout)
        
        passed = False
        full_out = res.stdout + "\n" + res.stderr
        if "ALL TESTS PASSED" in full_out:
            passed = True
            
        errors = [line for line in full_out.splitlines() if "error" in line.lower()]
        
        return SimResult(
            success=res.returncode == 0 and not res.timed_out,
            stdout=res.stdout,
            stderr=res.stderr,
            passed=passed,
            test_count=0,
            error_count=len(errors),
            errors=errors,
            timeout_reached=res.timed_out
        )

    async def collect_coverage(self, coverage_dat: Path) -> CoverageData:
        dat_wsl = SubprocessRunner.to_wsl_path(coverage_dat)
        cmd = ['verilator_coverage', '--annotate', SubprocessRunner.to_wsl_path(coverage_dat.parent), dat_wsl]
        
        res = await SubprocessRunner.run(cmd)
        
        line_cov = None
        branch_cov = None
        toggle_cov = None
        
        # Simple extraction using regex. Note: actual parsing may vary based on exact output
        line_match = re.search(r'Line Coverage:\s*([\d\.]+)%', res.stdout)
        if line_match:
            line_cov = float(line_match.group(1))
            
        branch_match = re.search(r'Branch Coverage:\s*([\d\.]+)%', res.stdout)
        if branch_match:
            branch_cov = float(branch_match.group(1))
            
        return CoverageData(
            line_coverage=line_cov,
            branch_coverage=branch_cov,
            toggle_coverage=toggle_cov,
            raw_text=res.stdout + "\n" + res.stderr
        )
