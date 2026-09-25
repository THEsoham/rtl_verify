#!/usr/bin/env python3
"""CLI tool to run benchmarks from the command line."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Reconfigure stdout/stderr for utf-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rtl_verify.benchmarks.registry import BenchmarkRegistry
from rtl_verify.pipeline.orchestrator import PipelineOrchestrator, RunConfig
from rtl_verify.database import init_db
from rtl_verify.config import settings
from rich.console import Console
from rich.table import Table

console = Console()

def parse_args():
    parser = argparse.ArgumentParser(description='RTL Verify Benchmark Runner')
    parser.add_argument('--benchmark', '-b', type=str, help='Benchmark name (e.g., alu, counter)')
    parser.add_argument('--all', action='store_true', help='Run all benchmarks')
    parser.add_argument('--list', action='store_true', help='List available benchmarks')
    parser.add_argument('--model', '-m', type=str, default=None, help='LLM model name')
    parser.add_argument('--max-iterations', type=int, default=10, help='Max iterations')
    parser.add_argument('--coverage-threshold', type=float, default=80.0, help='Coverage threshold %')
    parser.add_argument('--mutation', action='store_true', help='Enable mutation testing')
    return parser.parse_args()

async def run_single(registry: BenchmarkRegistry, name: str, config: RunConfig):
    spec = registry.get(name)
    console.print(f"\n[bold blue]Running benchmark: {spec.name}[/bold blue]")
    console.print(f"  Category: {spec.category} | Difficulty: {spec.difficulty}")
    
    orchestrator = PipelineOrchestrator(config=config)
    
    async def progress_callback(message, iteration_result):
        if iteration_result:
            status_color = 'green' if iteration_result.sim_passed else 'red'
            console.print(f"  [{status_color}]Iter {iteration_result.iteration_num}: {iteration_result.status}[/{status_color}]")
        else:
            console.print(f"  {message}")
    
    result = await orchestrator.run(spec, on_progress=progress_callback)
    
    console.print(f"\n[bold]Result: {result.status}[/bold]")
    console.print(f"  Iterations: {result.total_iterations}")
    console.print(f"  Time: {result.total_time_seconds:.1f}s")
    return result

async def main_async():
    args = parse_args()
    settings.ensure_work_dir()
    await init_db()
    
    registry = BenchmarkRegistry()
    
    if args.list:
        table = Table(title="Available Benchmarks")
        table.add_column("Name")
        table.add_column("Category")
        table.add_column("Difficulty")
        for spec in registry.load_all():
            table.add_row(spec.name, spec.category, spec.difficulty)
        console.print(table)
        return
    
    config = RunConfig(
        max_iterations=args.max_iterations,
        coverage_threshold=args.coverage_threshold,
        run_mutation_testing=args.mutation,
        designer_model=args.model,
        verifier_model=args.model,
    )
    
    if args.all:
        results = []
        for name in registry.list_names():
            result = await run_single(registry, name, config)
            results.append((name, result))
        
        # Summary table
        table = Table(title="\nBenchmark Results")
        table.add_column("Benchmark")
        table.add_column("Status")
        table.add_column("Iterations")
        table.add_column("Time (s)")
        for name, result in results:
            status_style = 'green' if result.status == 'passed' else 'red'
            table.add_row(name, f"[{status_style}]{result.status}[/{status_style}]", str(result.total_iterations), f"{result.total_time_seconds:.1f}")
        console.print(table)
    elif args.benchmark:
        await run_single(registry, args.benchmark, config)
    else:
        console.print("[red]Specify --benchmark NAME or --all. Use --list to see available benchmarks.[/red]")

def main():
    asyncio.run(main_async())

if __name__ == '__main__':
    main()
