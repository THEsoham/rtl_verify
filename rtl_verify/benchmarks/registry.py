"""Benchmark specification loader, parser, and registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

log = structlog.get_logger(__name__)


@dataclass
class PortDef:
    """Hardware module port definition."""

    name: str
    width: int
    description: str
    direction: str  # 'input' or 'output'

    @property
    def is_vector(self) -> bool:
        """Return True if port bit-width is greater than 1."""
        return self.width > 1

    @property
    def range_spec(self) -> str:
        """Return Verilog range string, e.g. '[7:0]' or '1-bit'."""
        if self.width > 1:
            return f"[{self.width - 1}:0]"
        return "1-bit"


@dataclass
class BenchmarkSpec:
    """Complete specification of a hardware benchmark design."""

    name: str
    category: str  # 'combinational', 'sequential'
    difficulty: str  # 'easy', 'medium', 'hard'
    description: str
    ports: list[PortDef]
    requirements: list[str]
    verification_hints: list[str] = field(default_factory=list)
    raw_yaml: str = ""
    id: int | None = None  # Database primary key, set after DB lookup

    @property
    def input_ports(self) -> list[PortDef]:
        """Return all input ports."""
        return [p for p in self.ports if p.direction == "input"]

    @property
    def output_ports(self) -> list[PortDef]:
        """Return all output ports."""
        return [p for p in self.ports if p.direction == "output"]

    def to_prompt_description(self) -> str:
        """Format the spec as a clear, structured natural language description for LLM prompts."""
        lines: list[str] = [
            f"# Module Specification: `{self.name}`",
            f"- **Category:** {self.category.capitalize()}",
            f"- **Difficulty:** {self.difficulty.capitalize()}",
            "",
            "## Description",
            self.description.strip(),
            "",
            "## Port Interface",
            "| Port Name | Direction | Bit Width | Description |",
            "| :--- | :--- | :--- | :--- |",
        ]

        for port in self.ports:
            bit_width_str = f"[{port.width - 1}:0]" if port.width > 1 else "1-bit"
            lines.append(
                f"| `{port.name}` | {port.direction} | {bit_width_str} | {port.description} |"
            )

        lines.append("")
        lines.append("## Functional Requirements")
        for idx, req in enumerate(self.requirements, 1):
            lines.append(f"{idx}. {req}")

        if self.verification_hints:
            lines.append("")
            lines.append("## Verification Hints & Corner Cases")
            for hint in self.verification_hints:
                lines.append(f"- {hint}")

        return "\n".join(lines)


class BenchmarkRegistry:
    """Registry managing loading, caching, and querying of benchmark specifications."""

    def __init__(self, specs_dir: Path | None = None) -> None:
        """Initialize the benchmark registry.

        Args:
            specs_dir: Directory containing YAML specification files.
                       Defaults to the 'specs/' subdirectory adjacent to this file.
        """
        if specs_dir is None:
            self.specs_dir = Path(__file__).resolve().parent / "specs"
        else:
            self.specs_dir = Path(specs_dir)
        self._specs: dict[str, BenchmarkSpec] = {}

    def load_all(self) -> list[BenchmarkSpec]:
        """Load all benchmark specifications from the specs directory.

        Returns:
            List of all loaded BenchmarkSpec instances.
        """
        if not self.specs_dir.exists() or not self.specs_dir.is_dir():
            log.warning("Specs directory does not exist", path=str(self.specs_dir))
            return []

        self._specs.clear()
        yaml_files = sorted(
            list(self.specs_dir.glob("*.yaml")) + list(self.specs_dir.glob("*.yml"))
        )

        for file_path in yaml_files:
            try:
                spec = self._parse_yaml(file_path)
                self._specs[spec.name] = spec
                log.debug("Loaded benchmark spec", name=spec.name, path=str(file_path))
            except Exception as exc:
                log.error("Failed to parse benchmark spec", path=str(file_path), error=str(exc))
                raise

        log.info("Loaded benchmark specifications", count=len(self._specs))
        return list(self._specs.values())

    def get(self, name: str) -> BenchmarkSpec:
        """Retrieve a benchmark specification by module name.

        Args:
            name: Name of the benchmark (e.g. 'alu', 'fifo', 'uart_tx').

        Returns:
            The BenchmarkSpec instance.

        Raises:
            KeyError: If the benchmark name is not found.
        """
        if not self._specs:
            self.load_all()

        if name not in self._specs:
            # Check case-insensitive match
            for k, v in self._specs.items():
                if k.lower() == name.lower():
                    return v
            # Check substring/keyword match (e.g. '4-bit ALU' matches 'alu')
            clean_name = name.lower().replace("-", " ").replace("_", " ")
            for k, v in self._specs.items():
                clean_k = k.lower().replace("-", " ").replace("_", " ")
                if clean_k in clean_name or clean_name in clean_k:
                    return v
                if clean_k in clean_name.split() or any(word in clean_name.split() for word in clean_k.split()):
                    return v
            available = list(self._specs.keys())
            raise KeyError(
                f"Benchmark '{name}' not found in registry. Available benchmarks: {available}"
            )

        return self._specs[name]

    def list_names(self) -> list[str]:
        """List all available benchmark names.

        Returns:
            Sorted list of benchmark names.
        """
        if not self._specs:
            self.load_all()

        return sorted(self._specs.keys())

    @staticmethod
    def _parse_yaml(path: Path) -> BenchmarkSpec:
        """Parse a YAML specification file into a BenchmarkSpec instance.

        Args:
            path: Path to the YAML file.

        Returns:
            Parsed BenchmarkSpec instance.
        """
        content = path.read_text(encoding="utf-8")
        data: dict[str, Any] = yaml.safe_load(content) or {}

        ports: list[PortDef] = []
        ports_data = data.get("ports", {})

        if isinstance(ports_data, dict):
            for inp in ports_data.get("inputs", []):
                ports.append(
                    PortDef(
                        name=inp["name"],
                        width=int(inp.get("width", 1)),
                        description=inp.get("description", ""),
                        direction="input",
                    )
                )
            for outp in ports_data.get("outputs", []):
                ports.append(
                    PortDef(
                        name=outp["name"],
                        width=int(outp.get("width", 1)),
                        description=outp.get("description", ""),
                        direction="output",
                    )
                )
        elif isinstance(ports_data, list):
            for p in ports_data:
                ports.append(
                    PortDef(
                        name=p["name"],
                        width=int(p.get("width", 1)),
                        description=p.get("description", ""),
                        direction=p.get("direction", "input"),
                    )
                )

        return BenchmarkSpec(
            name=data["name"],
            category=data.get("category", "combinational"),
            difficulty=data.get("difficulty", "easy"),
            description=data.get("description", "").strip(),
            ports=ports,
            requirements=data.get("requirements", []),
            verification_hints=data.get("verification_hints", []),
            raw_yaml=content,
        )
