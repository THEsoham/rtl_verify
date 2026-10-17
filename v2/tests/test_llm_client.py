"""Unit tests for LLMClient and Verilog code extraction."""

import json
import os
import tempfile
from v2.src.llm_client import LLMClient, extract_verilog_code, LLMResponse


def test_extract_verilog_fenced():
    raw = """
Here is the Verilog implementation:

```verilog
module TopModule (
    input a,
    output y
);
    assign y = ~a;
endmodule
```

Let me know if you need changes.
"""
    code = extract_verilog_code(raw)
    assert code.startswith("module TopModule")
    assert code.endswith("endmodule")
    assert "assign y = ~a;" in code


def test_extract_verilog_systemverilog_tag():
    raw = """
```systemverilog
module stimulus_gen ();
    initial begin
        $finish;
    end
endmodule
```
"""
    code = extract_verilog_code(raw)
    assert "module stimulus_gen" in code
    assert "endmodule" in code


def test_extract_verilog_unfenced():
    raw = """
module TopModule (input clk);
endmodule
"""
    code = extract_verilog_code(raw)
    assert code == "module TopModule (input clk);\nendmodule"


def test_llm_client_caching():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = os.path.join(tmpdir, "cache")
        log_dir = os.path.join(tmpdir, "logs")
        client = LLMClient(cache_dir=cache_dir, log_dir=log_dir)

        # Prepopulate cache
        model_config = {"id": "test-model", "temperature": 0.2}
        prompt = "Write an inverter"
        cache_path = client._get_cache_path("test-model", prompt, 0.2, 42)

        fake_resp = LLMResponse(
            call_id="call-123",
            model_id="test-model",
            model_name="test-model-v1",
            provider="mock",
            prompt=prompt,
            raw_response="```verilog\nmodule TopModule();\nendmodule\n```",
            verilog_code="module TopModule();\nendmodule",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            latency_sec=0.1,
            cached=False,
        )

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(fake_resp.to_dict(), f)

        # Generate should hit cache
        res = client.generate(model_config, prompt, seed=42)
        assert res.cached
        assert res.verilog_code == "module TopModule();\nendmodule"
        assert res.total_tokens == 30
