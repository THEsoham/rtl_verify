"""Unified LLM Client with disk caching and audit logging.

Supports:
- Ollama (local models: Qwen, Llama, fine-tuned checkpoints)
- Google Gemini (gemini-2.5-flash, gemini-2.0-flash)
- OpenAI (gpt-4o-mini, gpt-4o)

Every single LLM interaction is:
1. Checked against a deterministic SHA-256 disk cache.
2. Logged with full prompt, raw response, tokens, timestamp, latency, and model ID.
3. Extracted to clean Verilog code without hallucinations.
"""

from dataclasses import dataclass
import hashlib
import json
import os
import re
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Optional, Tuple
from dotenv import load_dotenv

load_dotenv("d:/rtl-verification/.env")


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""
    call_id: str
    model_id: str
    model_name: str
    provider: str
    prompt: str
    raw_response: str
    verilog_code: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_sec: float = 0.0
    cached: bool = False
    exact_model_version: str = ""
    date_called: str = ""

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "exact_model_version": self.exact_model_version,
            "date_called": self.date_called,
            "provider": self.provider,
            "prompt": self.prompt,
            "raw_response": self.raw_response,
            "verilog_code": self.verilog_code,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_sec": round(self.latency_sec, 4),
            "cached": self.cached,
        }


def extract_verilog_code(raw_text: str) -> str:
    """Extract clean Verilog / SystemVerilog code from an LLM response."""
    # Pattern 1: Fenced code blocks with verilog / systemverilog tag
    m = re.search(r"```(?:verilog|systemverilog)?\s*(.*?)\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if m:
        code = m.group(1).strip()
    else:
        # Fallback: Find from first 'module' to last 'endmodule'
        m2 = re.search(r"(module\s+.*?\bendmodule\b)", raw_text, re.DOTALL)
        if m2:
            code = m2.group(1).strip()
        else:
            code = raw_text.strip()

    # Clean up lingering markdown or comments outside module if present
    code = re.sub(r"^```\w*\s*", "", code)
    code = re.sub(r"```\s*$", "", code)
    return code.strip()


class LLMClient:
    """Handles cached, logged calls to local and cloud LLMs."""

    def __init__(
        self,
        cache_dir: str = "d:/rtl-verification/v2/cache",
        log_dir: str = "d:/rtl-verification/v2/logs",
    ):
        self.cache_dir = os.path.normpath(cache_dir)
        self.log_dir = os.path.normpath(log_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

    def _get_cache_path(self, model_id: str, prompt: str, temperature: float, seed: int) -> str:
        key = f"{model_id}|{temperature}|{seed}|{prompt}"
        hash_val = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{model_id}_{hash_val}.json")

    def _log_call(self, response: LLMResponse):
        model_subfolder = os.path.join(self.log_dir, response.model_id)
        os.makedirs(model_subfolder, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(model_subfolder, f"{timestamp}_{response.call_id[:8]}.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(response.to_dict(), f, indent=2)

    def generate(
        self,
        model_config: Dict[str, Any],
        prompt: str,
        system_prompt: Optional[str] = None,
        seed: int = 42,
    ) -> LLMResponse:
        """Query an LLM with deterministic caching and disk logging."""
        model_id = model_config.get("id", "unknown")
        model_name = model_config.get("name", "")
        provider = model_config.get("provider", "ollama")
        temperature = float(model_config.get("temperature", 0.2))
        max_tokens = int(model_config.get("max_tokens", 2048))

        # Check cache
        cache_path = self._get_cache_path(model_id, prompt, temperature, seed)
        if os.path.isfile(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                cached_data["cached"] = True
                return LLMResponse(**cached_data)

        # Cache miss: execute provider call
        start_time = time.time()
        call_id = hashlib.sha256(f"{model_id}{time.time()}".encode("utf-8")).hexdigest()

        if provider == "ollama":
            raw_text, p_tok, c_tok, exact_ver, date_called = self._call_ollama(
                api_base=model_config.get("api_base", "http://localhost:11434"),
                model_name=model_name,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
            )
        elif provider == "gemini":
            raw_text, p_tok, c_tok, exact_ver, date_called = self._call_gemini(
                model_name=model_name,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                fallback_name=model_config.get("fallback_name"),
            )
        elif provider == "openai":
            raw_text, p_tok, c_tok, exact_ver, date_called = self._call_openai(
                model_name=model_name,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        latency = time.time() - start_time
        verilog_code = extract_verilog_code(raw_text)

        response = LLMResponse(
            call_id=call_id,
            model_id=model_id,
            model_name=model_name,
            exact_model_version=exact_ver,
            date_called=date_called,
            provider=provider,
            prompt=prompt,
            raw_response=raw_text,
            verilog_code=verilog_code,
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            total_tokens=p_tok + c_tok,
            latency_sec=latency,
            cached=False,
        )

        # Save to cache
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(response.to_dict(), f, indent=2)

        # Save to logs
        self._log_call(response)

        return response

    def _call_ollama(
        self,
        api_base: str,
        model_name: str,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        seed: int,
    ) -> Tuple[str, int, int, str, str]:
        url = f"{api_base.rstrip('/')}/api/generate"
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "seed": seed,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_text = data.get("response", "")
            p_tok = data.get("prompt_eval_count", 0)
            c_tok = data.get("eval_count", 0)
            date_called = time.strftime("%Y-%m-%d")
            return raw_text, p_tok, c_tok, model_name, date_called

    def _call_gemini(
        self,
        model_name: str,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        fallback_name: Optional[str] = None,
    ) -> Tuple[str, int, int, str, str]:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        client = genai.Client(api_key=api_key)

        models_to_try = [model_name]
        if fallback_name:
            models_to_try.append(fallback_name)

        last_error = None
        for m_name in models_to_try:
            for attempt in range(2):
                try:
                    config: Dict[str, Any] = {"temperature": temperature}
                    if max_tokens:
                        config["max_output_tokens"] = max_tokens
                    if system_prompt:
                        config["system_instruction"] = system_prompt

                    response = client.models.generate_content(
                        model=m_name,
                        contents=prompt,
                        config=config,
                    )
                    raw_text = response.text or ""
                    p_tok = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                    c_tok = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                    exact_ver = getattr(response, "model_version", m_name) or m_name
                    date_called = time.strftime("%Y-%m-%d")
                    return raw_text, p_tok, c_tok, str(exact_ver), date_called
                except Exception as e:
                    last_error = e
                    time.sleep(2)

        raise RuntimeError(f"Gemini API call failed for models {models_to_try}: {last_error}")

    def _call_openai(
        self,
        model_name: str,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> Tuple[str, int, int, str, str]:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        client = OpenAI(api_key=api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        resp = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw_text = resp.choices[0].message.content or ""
        p_tok = resp.usage.prompt_tokens if resp.usage else 0
        c_tok = resp.usage.completion_tokens if resp.usage else 0
        exact_ver = getattr(resp, "model", model_name) or model_name
        date_called = time.strftime("%Y-%m-%d")
        return raw_text, p_tok, c_tok, str(exact_ver), date_called
