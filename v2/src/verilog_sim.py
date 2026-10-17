"""Verilog simulation module using Icarus Verilog (iverilog + vvp).

Executes native Verilog RTL and testbenches without behavioral mocks.
Parses compiler errors, simulation status, warnings, and mismatch metrics.
"""

from dataclasses import dataclass, field
import os
import re
import subprocess
import tempfile
import time
from typing import List, Optional


@dataclass
class SimResult:
    """Structured outcome of a Verilog compilation and simulation."""
    compile_ok: bool
    sim_ok: bool
    passed: bool
    mismatches: int = 0
    total_samples: int = 0
    compile_stderr: str = ""
    sim_stdout: str = ""
    sim_stderr: str = ""
    warnings: List[str] = field(default_factory=list)
    duration_sec: float = 0.0
    timed_out: bool = False
    contract_valid: bool = True
    contract_error: str = ""

    def to_dict(self) -> dict:
        return {
            "compile_ok": self.compile_ok,
            "sim_ok": self.sim_ok,
            "passed": self.passed,
            "mismatches": self.mismatches,
            "total_samples": self.total_samples,
            "compile_stderr": self.compile_stderr,
            "sim_stdout": self.sim_stdout,
            "sim_stderr": self.sim_stderr,
            "warnings": self.warnings,
            "duration_sec": round(self.duration_sec, 4),
            "timed_out": self.timed_out,
            "contract_valid": self.contract_valid,
            "contract_error": self.contract_error,
        }


class VerilogSimulator:
    """Manages Icarus Verilog compilation and execution."""

    def __init__(
        self,
        iverilog_path: str = r"d:\rtl-verification\tools\iverilog\app\bin\iverilog.exe",
        vvp_path: str = r"d:\rtl-verification\tools\iverilog\app\bin\vvp.exe",
        flags: Optional[List[str]] = None,
        timeout_sec: float = 30.0,
    ):
        self.iverilog_path = os.path.normpath(iverilog_path)
        self.vvp_path = os.path.normpath(vvp_path)
        self.flags = flags if flags is not None else ["-g2012"]
        self.timeout_sec = timeout_sec

        if not os.path.isfile(self.iverilog_path):
            raise FileNotFoundError(f"iverilog binary not found: {self.iverilog_path}")
        if not os.path.isfile(self.vvp_path):
            raise FileNotFoundError(f"vvp binary not found: {self.vvp_path}")

    def compile_and_run(
        self,
        dut_code: str,
        tb_code: str,
        ref_code: Optional[str] = None,
        extra_files: Optional[List[str]] = None,
        enforce_contract: bool = False,
    ) -> SimResult:
        """Compile and simulate Verilog RTL against a testbench.

        Args:
            dut_code: The candidate Verilog RTL under test.
            tb_code: The Verilog / SystemVerilog testbench.
            ref_code: Optional golden reference Verilog code (e.g. RefModule).
            extra_files: Optional list of additional Verilog source files.
            enforce_contract: If True, enforce strict testbench contract (self-checking,
                             exact single PASS/FAIL line, ends with $finish).

        Returns:
            SimResult object with execution details and mismatch metrics.
        """
        start_time = time.time()

        with tempfile.TemporaryDirectory() as tmpdir:
            dut_path = os.path.join(tmpdir, "dut.v")
            tb_path = os.path.join(tmpdir, "tb.v")
            out_vvp = os.path.join(tmpdir, "sim.vvp")

            with open(dut_path, "w", encoding="utf-8") as f:
                f.write(dut_code)
            with open(tb_path, "w", encoding="utf-8") as f:
                f.write(tb_code)

            source_files = [tb_path, dut_path]

            if ref_code:
                ref_path = os.path.join(tmpdir, "ref.v")
                with open(ref_path, "w", encoding="utf-8") as f:
                    f.write(ref_code)
                source_files.append(ref_path)

            if extra_files:
                source_files.extend(extra_files)

            # Step 1: Compile
            compile_cmd = [self.iverilog_path] + self.flags + ["-o", out_vvp] + source_files
            try:
                comp_res = subprocess.run(
                    compile_cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_sec,
                )
            except subprocess.TimeoutExpired:
                return SimResult(
                    compile_ok=False,
                    sim_ok=False,
                    passed=False,
                    compile_stderr="Compilation timed out.",
                    duration_sec=time.time() - start_time,
                    timed_out=True,
                    contract_valid=False,
                    contract_error="Compilation timed out",
                )

            # Extract compiler warnings
            warnings = []
            for line in comp_res.stderr.splitlines():
                if "warning:" in line.lower():
                    warnings.append(line.strip())

            if comp_res.returncode != 0:
                return SimResult(
                    compile_ok=False,
                    sim_ok=False,
                    passed=False,
                    compile_stderr=comp_res.stderr.strip(),
                    warnings=warnings,
                    duration_sec=time.time() - start_time,
                    contract_valid=False,
                    contract_error="Compilation failed",
                )

            # Step 2: Simulate with vvp
            sim_cmd = [self.vvp_path, out_vvp]
            try:
                sim_res = subprocess.run(
                    sim_cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_sec,
                    cwd=tmpdir,
                )
            except subprocess.TimeoutExpired:
                return SimResult(
                    compile_ok=True,
                    sim_ok=False,
                    passed=False,
                    compile_stderr=comp_res.stderr.strip(),
                    sim_stderr="Simulation timed out.",
                    warnings=warnings,
                    duration_sec=time.time() - start_time,
                    timed_out=True,
                    contract_valid=False,
                    contract_error="Simulation timed out or hung without calling $finish",
                )

            for line in sim_res.stderr.splitlines():
                if "warning:" in line.lower():
                    warnings.append(line.strip())

            # Step 3: Parse simulation results
            if enforce_contract:
                passed, mismatches, total_samples, contract_valid, contract_error = self._parse_contract_output(
                    sim_res.stdout, sim_res.stderr, sim_res.returncode
                )
            else:
                passed, mismatches, total_samples = self._parse_simulation_output(
                    sim_res.stdout, sim_res.stderr, sim_res.returncode
                )
                contract_valid = True
                contract_error = ""

            return SimResult(
                compile_ok=True,
                sim_ok=(sim_res.returncode == 0),
                passed=passed,
                mismatches=mismatches,
                total_samples=total_samples,
                compile_stderr=comp_res.stderr.strip(),
                sim_stdout=sim_res.stdout.strip(),
                sim_stderr=sim_res.stderr.strip(),
                warnings=warnings,
                duration_sec=time.time() - start_time,
                contract_valid=contract_valid,
                contract_error=contract_error,
            )

    def _parse_contract_output(
        self, stdout: str, stderr: str, returncode: int
    ) -> tuple[bool, int, int, bool, str]:
        """Strict parser for fixed testbench contract.
        
        Contract rules:
        1. Testbench must finish with $finish cleanly.
        2. Must print EXACTLY ONE line stating status:
           '*** TEST RESULT: PASS ***' or '*** TEST RESULT: FAIL ***'
        3. Anything ambiguous or outside the contract is rejected as invalid.
        """
        # Rule 1: Must end with $finish
        finish_called = ("$finish called" in stdout.lower()) or ("$finish" in stdout.lower())
        if returncode != 0 or not finish_called:
            return (False, 1, 0, False, "Contract violation: Simulation did not finish cleanly with $finish")

        pass_matches = len(re.findall(r"\*\*\*\s*TEST RESULT:\s*PASS\s*\*\*\*", stdout, re.IGNORECASE))
        fail_matches = len(re.findall(r"\*\*\*\s*TEST RESULT:\s*FAIL\s*\*\*\*", stdout, re.IGNORECASE))

        if pass_matches == 1 and fail_matches == 0:
            return (True, 0, 1, True, "")
        elif fail_matches >= 1 and pass_matches == 0:
            return (False, fail_matches, 1, True, "")
        elif pass_matches > 0 and fail_matches > 0:
            return (False, 1, 0, False, "Contract violation: Both PASS and FAIL status lines printed")
        elif pass_matches > 1:
            return (False, 1, 0, False, "Contract violation: Multiple PASS status lines printed")
        else:
            return (False, 1, 0, False, "Contract violation: Missing exact '*** TEST RESULT: PASS ***' or '*** TEST RESULT: FAIL ***' line")

    def _parse_simulation_output(
        self, stdout: str, stderr: str, returncode: int
    ) -> tuple[bool, int, int]:
        """Parse simulation stdout/stderr to determine pass/fail and mismatches."""
        mismatches = 0
        total_samples = 0
        explicit_pass = False
        explicit_fail = False

        # Pattern 1: VerilogEval benchmark standard
        # "Mismatches: 0 in 20 samples" or "Mismatches: 5 in 20 samples"
        m = re.search(r"Mismatches:\s*(\d+)\s*in\s*(\d+)\s*samples", stdout, re.IGNORECASE)
        if m:
            mismatches = int(m.group(1))
            total_samples = int(m.group(2))
            return (mismatches == 0, mismatches, total_samples)

        # Pattern 2: "Total mismatched samples is X out of Y samples"
        m = re.search(r"Total mismatched samples is\s*(\d+)\s*out of\s*(\d+)", stdout, re.IGNORECASE)
        if m:
            mismatches = int(m.group(1))
            total_samples = int(m.group(2))
            return (mismatches == 0, mismatches, total_samples)

        # Pattern 3: Explicit testbench assertions / prints
        stdout_upper = stdout.upper()
        if "TEST PASSED" in stdout_upper or "ALL TESTS PASSED" in stdout_upper or "VERIFICATION PASSED" in stdout_upper:
            explicit_pass = True
        if "TEST FAILED" in stdout_upper or "VERIFICATION FAILED" in stdout_upper or "MISMATCH DETECTED" in stdout_upper:
            explicit_fail = True

        # Check for error keyword counts
        error_count = len(re.findall(r"\bERROR\b|\bFAIL\b|\bMISMATCH\b", stdout_upper))

        if explicit_fail or error_count > 0:
            return (False, max(error_count, 1), total_samples)
        if explicit_pass and returncode == 0:
            return (True, 0, total_samples)

        # If clean exit with no failure keywords
        if returncode == 0 and "$finish called" in stdout.lower():
            return (True, 0, total_samples)

        return (returncode == 0 and not explicit_fail, error_count, total_samples)
