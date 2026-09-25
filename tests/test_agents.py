from __future__ import annotations

import pytest
from rtl_verify.agents.base import BaseAgent


class TestBaseAgent:
    def test_extract_code_block_verilog(self):
        """Test extraction of Verilog code from markdown code blocks."""
        response = """Here is the RTL:
```verilog
module test;
endmodule
```
This implements the spec."""
        agent = BaseAgent.__new__(BaseAgent)  # create without __init__
        result = agent._extract_code_block(response, "verilog")
        assert "module test" in result
        assert "endmodule" in result
        assert "Here is" not in result

    def test_extract_code_block_systemverilog(self):
        response = "```systemverilog\nmodule foo;\nendmodule\n```"
        agent = BaseAgent.__new__(BaseAgent)
        result = agent._extract_code_block(response, "verilog")
        assert "module foo" in result

    def test_extract_code_block_no_block(self):
        """If no code block, return raw response."""
        response = "module raw;\nendmodule"
        agent = BaseAgent.__new__(BaseAgent)
        result = agent._extract_code_block(response, "verilog")
        assert result == response

    def test_extract_code_block_multiple(self):
        """If multiple code blocks, return the first verilog one."""
        response = """```python
print("hi")
```
```verilog
module correct;
endmodule
```"""
        agent = BaseAgent.__new__(BaseAgent)
        result = agent._extract_code_block(response, "verilog")
        assert "module correct" in result
