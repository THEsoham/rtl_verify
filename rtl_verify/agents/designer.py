from __future__ import annotations

import structlog

from rtl_verify.agents.base import BaseAgent
from rtl_verify.config import settings

log = structlog.get_logger(__name__)


class DesignerAgent(BaseAgent):
    """Agent responsible for generating and fixing RTL code."""

    def __init__(self, model: str | None = None):
        super().__init__(model=model or settings.designer_model)

    async def generate_rtl(
        self, 
        spec_description: str, 
        ports: dict | None = None, 
        requirements: list[str] | None = None
    ) -> tuple[str, int]:
        """Generate initial RTL from a specification."""
        system_prompt = self._render_template("designer_system.j2")
        prompt = self._render_template(
            "designer_generate.j2",
            spec_description=spec_description,
            ports=ports,
            requirements=requirements
        )

        response_text, elapsed_ms = await self.generate(prompt=prompt, system=system_prompt)
        verilog_source = self._extract_code_block(response_text)
        
        return verilog_source, elapsed_ms

    async def fix_rtl(
        self, 
        spec_description: str, 
        previous_rtl: str, 
        feedback: str
    ) -> tuple[str, int]:
        """Fix RTL based on verification feedback."""
        system_prompt = self._render_template("designer_system.j2")
        prompt = self._render_template(
            "designer_fix.j2",
            spec_description=spec_description,
            previous_rtl=previous_rtl,
            feedback=feedback
        )

        response_text, elapsed_ms = await self.generate(prompt=prompt, system=system_prompt)
        verilog_source = self._extract_code_block(response_text)
        
        return verilog_source, elapsed_ms
