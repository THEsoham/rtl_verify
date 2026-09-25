from __future__ import annotations

from pathlib import Path
import pytest
from rtl_verify.pipeline.runner import SubprocessRunner


class TestSubprocessRunner:
    def test_to_wsl_path(self):
        win_path = Path("C:/Users/test/file.sv")
        wsl_path = SubprocessRunner.to_wsl_path(win_path)
        assert wsl_path == "/mnt/c/Users/test/file.sv"

    def test_to_wsl_path_backslash(self):
        win_path = Path("C:\\Users\\test\\file.sv")
        wsl_path = SubprocessRunner.to_wsl_path(win_path)
        assert wsl_path == "/mnt/c/Users/test/file.sv"

    def test_wsl_wrap(self):
        cmd = ["iverilog", "-o", "out.vvp", "test.sv"]
        wrapped = SubprocessRunner.wsl_wrap(cmd)
        assert wrapped[0] == "wsl"
        assert wrapped[1] == "iverilog"


@pytest.mark.asyncio
class TestIcarusVerilog:
    async def test_compile_valid(self, sample_rtl, sample_testbench, tmp_path):
        """Test compiling valid Verilog (requires WSL2 + iverilog)."""
        pytest.importorskip("asyncio")
        rtl_file = tmp_path / "design.sv"
        tb_file = tmp_path / "testbench.sv"
        rtl_file.write_text(sample_rtl)
        tb_file.write_text(sample_testbench)

        from rtl_verify.verification.iverilog import IcarusVerilog

        iv = IcarusVerilog()
        result = await iv.compile([rtl_file, tb_file], tmp_path / "out.vvp")
        # This will fail if WSL2/iverilog not installed, which is expected in CI
        # Mark as skip if not available
