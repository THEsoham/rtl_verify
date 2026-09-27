"""
Designer Agent (Gemini-Powered)
===============================
Generates synthesizable Verilog/SystemVerilog RTL from hardware specifications,
analyzes compiler/lint diagnostic errors, and repairs RTL iteratively based on
adversarial verification feedback.
"""

import os
import re
from typing import Optional, Dict, Any, List
from google import genai
from google.genai import types
from google.genai import errors as genai_errors


class DesignerAgent:
    """
    RTL Designer Agent powered by Google Gemini.
    """

    MODELS = [
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.8-flash",
    ]

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment or .env file.")

        self.client = genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(
                async_client_args={"trust_env": False},
                client_args={"trust_env": False},
            ),
        )
        self.history: List[Dict[str, str]] = []

    def _call_gemini(self, prompt: str, system_prompt: str = "") -> str:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        for model_name in self.MODELS:
            for attempt in range(1, 3):
                try:
                    resp = self.client.models.generate_content(
                        model=model_name,
                        contents=full_prompt,
                    )
                    if resp.text:
                        return resp.text
                except (genai_errors.ServerError, genai_errors.ClientError):
                    break
        raise RuntimeError("All Gemini models unavailable for Designer Agent.")

    def _extract_verilog(self, text: str) -> str:
        """Extract clean Verilog code block from model response."""
        match = re.search(r'```(?:verilog|systemverilog)?\s*(module\b.*?endmodule)', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # Fallback to direct module block
        match = re.search(r'(module\s+[a-zA-Z0-9_]+\s*\(.*?endmodule)', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    def generate_initial_rtl(self, spec: Dict[str, Any]) -> str:
        """Generate first synthesizable RTL candidate from specification."""
        system_prompt = (
            "You are an expert Silicon Hardware RTL Design Engineer. "
            "You write clean, synthesizable, production-quality Verilog-2001 code. "
            "Follow synchronous design best practices: use non-blocking assignments (<=) for sequential logic, "
            "avoid combinational loops and latches, and ensure all interface ports match specifications exactly."
        )

        prompt = f"""
HARDWARE SPECIFICATION:
Module Name: {spec.get('name', 'top')}
Title: {spec.get('title', '')}
Description: {spec.get('description', '')}

PORTS:
{spec.get('ports', [])}

REQUIREMENTS:
{spec.get('requirements', [])}

TASK:
Write the complete, synthesizable Verilog module for this hardware design.
Only return the Verilog code inside a ```verilog code block. Do not include markdown preamble.
"""
        response_text = self._call_gemini(prompt, system_prompt)
        rtl = self._extract_verilog(response_text)
        self.history.append({"action": "initial_generation", "rtl": rtl})
        return rtl

    def repair_rtl(self, spec: Dict[str, Any], current_rtl: str, feedback: str, iteration: int) -> str:
        """Repair RTL based on compiler diagnostics or adversarial testbench failure feedback."""
        system_prompt = (
            "You are a Senior Silicon RTL Design Lead debugging an RTL module failure. "
            "Analyze the failure diagnostics, identify the precise logical flaw or race condition, "
            "and produce an updated, repaired Verilog implementation that satisfies all specification requirements."
        )

        prompt = f"""
SPECIFICATION:
Module Name: {spec.get('name', 'top')}
Description: {spec.get('description', '')}

CURRENT RTL CODE:
```verilog
{current_rtl}
```

VERIFICATION FAILURE FEEDBACK & BUG REPORT:
{feedback}

REPAIR INSTRUCTIONS (Iteration {iteration}):
1. Carefully diagnose the exact line and condition causing the failure.
2. Fix the bug without breaking existing functionality.
3. Ensure the module remains strictly synthesizable and cycle-accurate.
4. Return ONLY the complete updated Verilog code inside a ```verilog code block.
"""
        response_text = self._call_gemini(prompt, system_prompt)
        repaired_rtl = self._extract_verilog(response_text)
        self.history.append({
            "action": f"repair_iter_{iteration}",
            "feedback": feedback,
            "rtl": repaired_rtl,
        })
        return repaired_rtl

    def generate_self_verification_testbench(self, spec: Dict[str, Any], rtl_code: str = "") -> str:
        """
        Generate a self-verification testbench using the same Gemini model that designed the RTL.
        In the single-agent baseline, the designer verifies its own design with standard stimulus.
        """
        system_prompt = (
            "You are a hardware design engineer writing a verification testbench for your own RTL design. "
            "Write a standard, self-checking Verilog-2001 testbench that instantiates the module, "
            "drives clock and reset, applies nominal stimulus, and checks output responses."
        )

        prompt = f"""
SPECIFICATION:
Module Name: {spec.get('name', 'top')}
Description: {spec.get('description', '')}

PORTS:
{spec.get('ports', [])}

REQUIREMENTS:
{spec.get('requirements', [])}

CANDIDATE RTL:
```verilog
{rtl_code}
```

TASK:
Write a complete, self-checking Verilog testbench for `{spec.get('name', 'top')}`.
Instantiate the module under test, generate clock and reset signals, apply stimulus vectors, and use $display/$finish.
Return ONLY the Verilog testbench code inside a ```verilog code block.
"""
        response_text = self._call_gemini(prompt, system_prompt)
        return self._extract_verilog(response_text)

