"""Application configuration via environment variables and .env file."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Ollama ──────────────────────────────────────────────────────────────
    ollama_host: str = "http://localhost:11434"
    designer_model: str = "qwen2.5-coder:7b"
    verifier_model: str = "qwen2.5-coder:7b"

    # ── Pipeline defaults ───────────────────────────────────────────────────
    max_iterations: int = 10
    max_tb_fix_iterations: int = 3
    coverage_threshold: float = 80.0
    mutation_score_threshold: float = 60.0
    simulation_timeout_seconds: int = 30

    # ── Verification tools (names or full paths; resolved inside WSL2) ─────
    iverilog_path: str = "iverilog"
    vvp_path: str = "vvp"
    verilator_path: str = "verilator"

    # ── Database ────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./workdir/rtl_verify.db"

    # ── Working directory ───────────────────────────────────────────────────
    work_dir: Path = Path("./workdir")

    # ── Logging ─────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── Execution environment ───────────────────────────────────────────────
    use_wsl: bool = True  # Whether to run verification tools via WSL2

    def ensure_work_dir(self) -> Path:
        """Create the working directory tree if it does not exist."""
        runs_dir = self.work_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        return self.work_dir

    def run_dir(self, run_id: int) -> Path:
        """Return (and create) the directory for a specific pipeline run."""
        p = self.work_dir / "runs" / str(run_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def iteration_dir(self, run_id: int, iteration: int) -> Path:
        """Return (and create) the directory for a specific iteration."""
        p = self.run_dir(run_id) / f"iter_{iteration:03d}"
        p.mkdir(parents=True, exist_ok=True)
        return p


# Singleton – import this from anywhere.
settings = Settings()
