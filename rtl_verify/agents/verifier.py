from __future__ import annotations

import structlog

from rtl_verify.agents.base import BaseAgent
from rtl_verify.config import settings

log = structlog.get_logger(__name__)


class VerifierAgent(BaseAgent):
    """Agent responsible for generating and refining verification testbenches."""

    def __init__(self, model: str | None = None):
        super().__init__(model=model or settings.verifier_model)

    async def generate_testbench(
        self, 
        spec_description: str, 
        rtl_source: str, 
        module_name: str, 
        ports: dict | None = None
    ) -> tuple[str, int]:
        """Generate a verification testbench for the given RTL."""
        system_prompt = self._render_template("verifier_system.j2")
        prompt = self._render_template(
            "verifier_generate_tb.j2",
            spec_description=spec_description,
            rtl_source=rtl_source,
            module_name=module_name,
            ports=ports
        )

        response_text, elapsed_ms = await self.generate(prompt=prompt, system=system_prompt)
        testbench_source = self._extract_code_block(response_text)
        
        return testbench_source, elapsed_ms

    async def refine_testbench(
        self, 
        spec_description: str, 
        rtl_source: str, 
        previous_tb: str, 
        error_output: str
    ) -> tuple[str, int]:
        """Fix a testbench that failed to compile or run."""
        system_prompt = self._render_template("verifier_system.j2")
        prompt = self._render_template(
            "verifier_refine_tb.j2",
            spec_description=spec_description,
            rtl_source=rtl_source,
            previous_tb=previous_tb,
            error_output=error_output
        )

        response_text, elapsed_ms = await self.generate(prompt=prompt, system=system_prompt)
        testbench_source = self._extract_code_block(response_text)
        
        return testbench_source, elapsed_ms
