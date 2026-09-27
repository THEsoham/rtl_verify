"""
Verification Agent (OpenAI-Powered Adversarial Verifier)
======================================================
Independently analyzes the hardware specification and RTL code, creates adversarial
testbenches and edge-case stress vectors designed to expose bugs, and produces
diagnostic feedback rather than simply declaring the RTL correct.
"""

import os
import re
from typing import Optional, Dict, Any, List
from openai import OpenAI
import httpx
from google import genai
from google.genai import types as genai_types
from google.genai import errors as genai_errors


class VerifierAgent:
    """
    OpenAI-based Adversarial Verification Agent.
    """

    def __init__(self, openai_api_key: Optional[str] = None, gemini_api_key: Optional[str] = None):
        self.openai_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.gemini_key = gemini_api_key or os.getenv("GEMINI_API_KEY")

        self.openai_client = None
        if self.openai_key and self.openai_key.startswith("sk-"):
            self.openai_client = OpenAI(
                api_key=self.openai_key,
                http_client=httpx.Client(trust_env=False)
            )

        self.gemini_client = None
        if self.gemini_key:
            self.gemini_client = genai.Client(
                api_key=self.gemini_key,
                http_options=genai_types.HttpOptions(
                    async_client_args={"trust_env": False},
                    client_args={"trust_env": False},
                ),
            )

    def _call_llm(self, prompt: str, system_prompt: str) -> str:
        # Try OpenAI first if available
        if self.openai_client:
            for model_name in ["gpt-4o-mini", "gpt-4o"]:
                try:
                    resp = self.openai_client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.2,
                        max_tokens=2500,
                    )
                    content = resp.choices[0].message.content
                    if content:
                        return content
                except Exception as e:
                    pass

        # Fallback to Gemini with adversarial verifier persona
        if self.gemini_client:
            full_prompt = f"{system_prompt}\n\n{prompt}"
            for m in ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]:
                try:
                    resp = self.gemini_client.models.generate_content(
                        model=m,
                        contents=full_prompt,
                    )
                    if resp.text:
                        return resp.text
                except Exception:
                    continue

        raise RuntimeError("No LLM client available for Verification Agent.")

    def _extract_verilog(self, text: str) -> str:
        """Extract clean testbench Verilog code block."""
        match = re.search(r'```(?:verilog|systemverilog)?\s*(module\b.*?endmodule)', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        match = re.search(r'(module\s+[a-zA-Z0-9_]+_tb\b.*?endmodule)', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    def generate_adversarial_testbench(self, spec: Dict[str, Any], rtl_code: str) -> str:
        """
        Generate an adversarial, self-checking Verilog testbench targeting boundary
        conditions, race conditions, simultaneous events, and edge cases.
        """
        system_prompt = (
            "You are a Principal Hardware Verification Engineer specializing in Adversarial Testing. "
            "Your objective is to find bugs and break candidate RTL designs by creating rigorous, "
            "self-checking Verilog testbenches. "
            "DO NOT assume the RTL is correct. Target corner cases: reset assertion during active cycles, "
            "maximum boundary overflow/underflow, simultaneous read/write operations, back-to-back toggling, "
            "and invalid input combinations. Use $fatal or $error on mismatches."
        )

        prompt = f"""
HARDWARE SPECIFICATION:
Name: {spec.get('name', 'top')}
Description: {spec.get('description', '')}
Ports: {spec.get('ports', [])}
Requirements: {spec.get('requirements', [])}

CANDIDATE RTL UNDER TEST (DUT):
```verilog
{rtl_code}
```

TASK:
Write a complete, self-checking Verilog testbench module `{spec.get('name', 'top')}_tb`.
Requirements:
1. Instantiate the DUT with all port connections.
2. Generate clock (period 10 units) and asynchronous/synchronous reset sequences.
3. Apply adversarial stimulus vectors covering:
   - Reset release timing and boundary states
   - Edge-case transitions (max capacity, overflow, underflow)
   - Rapid multi-cycle operations
4. Implement self-checking assertions that compare DUT outputs against expected behavior.
5. Print [PASS] or [FAIL] with diagnostic details.
6. End with $finish.
Only return the Verilog testbench code inside a ```verilog code block.
"""
        response_text = self._call_llm(prompt, system_prompt)
        return self._extract_verilog(response_text)

    def analyze_failure(self, spec: Dict[str, Any], rtl_code: str, testbench_code: str, sim_stdout: str) -> str:
        """
        Produce a precise, structured root-cause diagnostic report when simulation fails.
        """
        system_prompt = (
            "You are an expert Silicon Debug and Verification Engineer. "
            "Analyze the simulation log failure, trace the mismatch to the specific line or signal in the DUT, "
            "and produce concise, actionable feedback for the Designer Agent to fix the defect."
        )

        prompt = f"""
SPECIFICATION:
Name: {spec.get('name', 'top')}

RTL UNDER TEST:
```verilog
{rtl_code}
```

SIMULATION LOG & ASSERTION FAILURES:
{sim_stdout}

TASK:
Provide a concise failure diagnosis:
1. Root Cause Analysis: Which signal or logic path failed?
2. Failing Condition: What clock cycle and input condition triggered the mismatch?
3. Actionable Fix: Exactly what logic modification is needed in the RTL to resolve this issue?
"""
        return self._call_llm(prompt, system_prompt)
