from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import httpx
import structlog
from jinja2 import Environment, FileSystemLoader

from rtl_verify.config import settings

log = structlog.get_logger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class BaseAgent:
    """Base class for LLM agents."""

    def __init__(self, model: str):
        self.model = model
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(PROMPTS_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _render_template(self, template_name: str, **kwargs: Any) -> str:
        """Render a Jinja2 prompt template."""
        template = self.jinja_env.get_template(template_name)
        return template.render(**kwargs)

    def _extract_code_block(self, response: str, language: str = "verilog") -> str:
        """Extract code from a markdown code block, handling reasoning tokens and unclosed blocks."""
        # 1. Remove <think>...</think> blocks from reasoning models (e.g., Qwen 3.5, DeepSeek)
        cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r"^<think>.*", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = cleaned.strip()

        # 2. Try specific language first, e.g. ```verilog, ```systemverilog, ```sv (closed or EOF)
        pattern = r"```(?:verilog|systemverilog|sv)\s*(.*?)(?:```|$)"
        match = re.search(pattern, cleaned, re.DOTALL | re.IGNORECASE)
        if match and match.group(1).strip():
            return match.group(1).strip()
            
        # 3. Try generic code block
        pattern_generic = r"```\w*\s*(.*?)(?:```|$)"
        match_generic = re.search(pattern_generic, cleaned, re.DOTALL)
        if match_generic and match_generic.group(1).strip():
            return match_generic.group(1).strip()

        # 4. Try extracting from first 'module' to last 'endmodule'
        module_pattern = r"(module\s+\w+.*?endmodule)"
        module_match = re.search(module_pattern, cleaned, re.DOTALL)
        if module_match:
            return module_match.group(1).strip()

        # 5. Fallback to raw response
        return cleaned

    async def generate(self, prompt: str, system: str | None = None) -> tuple[str, int]:
        """Send a generation request to the Ollama API."""
        start_time = time.perf_counter()
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 4096,
            }
        }
        if system:
            payload["system"] = system

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{settings.ollama_host}/api/generate",
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                result_text = data.get("response", "")
                if not result_text and "thinking" in data:
                    result_text = data.get("thinking", "")
        except Exception as e:
            log.error("ollama_generate_failed", error=str(e), model=self.model)
            raise

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        log.info("ollama_generate_success", model=self.model, elapsed_ms=elapsed_ms)
        
        return result_text, elapsed_ms

    async def chat(self, messages: list[dict], system: str | None = None) -> tuple[str, int]:
        """Send a chat request to the Ollama API."""
        start_time = time.perf_counter()
        
        if system:
            # Prepend system message if provided
            messages = [{"role": "system", "content": system}] + messages
            
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.2
            }
        }

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{settings.ollama_host}/api/chat",
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                result_text = data.get("message", {}).get("content", "")
                if not result_text and "message" in data and "thinking" in data.get("message", {}):
                    result_text = data.get("message", {}).get("thinking", "")
        except Exception as e:
            log.error("ollama_chat_failed", error=str(e), model=self.model)
            raise

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        log.info("ollama_chat_success", model=self.model, elapsed_ms=elapsed_ms)
        
        return result_text, elapsed_ms
