"""
Benchmark specifications loader.
"""

import json
from pathlib import Path
from typing import Dict, Any, List

BENCHMARK_DIR = Path(__file__).parent


def load_benchmark(name: str) -> Dict[str, Any]:
    """Load a benchmark specification JSON by name."""
    path = BENCHMARK_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Benchmark '{name}' not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_benchmarks() -> List[str]:
    """List all available benchmark names."""
    return [p.stem for p in BENCHMARK_DIR.glob("*.json")]
