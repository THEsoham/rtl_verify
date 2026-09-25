"""Main dashboard page — benchmark selection, run launcher, recent runs."""

from __future__ import annotations

import asyncio

from nicegui import ui, app
import structlog

from rtl_verify.database import get_session
from rtl_verify.models import Run, Benchmark, RunStatus
from rtl_verify.benchmarks.registry import BenchmarkRegistry
from rtl_verify.pipeline.orchestrator import PipelineOrchestrator, RunConfig
from rtl_verify.config import settings

log = structlog.get_logger()

DIFFICULTY_COLORS = {"easy": "green", "medium": "orange", "hard": "red"}
STATUS_COLORS = {
    "passed": "green", "running": "blue", "pending": "grey",
    "failed": "red", "iteration_limit": "amber", "error": "red",
}


def header_nav() -> None:
    """Shared header bar."""
    with ui.header().classes('items-center justify-between bg-[#1a1a2e]'):
        ui.link('RTL Design & Verification Framework', '/').classes(
            'text-2xl font-bold text-[#4fc3f7] no-underline'
        )
        with ui.row().classes('items-center gap-4'):
            ui.label('Ollama').classes('text-sm text-gray-400')
            status_dot = ui.icon('circle').classes('text-green-500 text-xs')


def sidebar() -> None:
    """Shared left navigation drawer."""
    with ui.left_drawer(value=True).classes('bg-[#16213e] text-white'):
        ui.label('Navigation').classes('text-xs text-gray-500 uppercase tracking-wide mb-2 px-2')
        for label, path, icon in [
            ('Dashboard', '/', 'dashboard'),
            ('Compare Runs', '/compare', 'compare_arrows'),
            ('Settings', '/settings', 'settings'),
        ]:
            with ui.link(target=path).classes(
                'flex items-center gap-3 py-2 px-3 rounded hover:bg-[#1a1a3e] '
                'text-gray-300 hover:text-[#4fc3f7] no-underline w-full'
            ):
                ui.icon(icon).classes('text-lg')
                ui.label(label).classes('text-sm')


@ui.page('/')
async def dashboard_page() -> None:
    header_nav()
    sidebar()

    registry = BenchmarkRegistry()
    specs = registry.load_all()

    with ui.column().classes('p-6 w-full max-w-6xl mx-auto'):
        # ── Benchmark cards ─────────────────────────────────────────────
        ui.label('Hardware Benchmarks').classes('text-xl font-bold mb-4')

        selected_benchmark: dict = {'spec': None}

        with ui.row().classes('w-full gap-4 flex-wrap'):
            for spec in specs:
                diff_color = DIFFICULTY_COLORS.get(spec.difficulty, 'grey')
                with ui.card().classes(
                    'p-4 w-64 cursor-pointer hover:ring-2 hover:ring-[#4fc3f7] transition-all'
                ) as card:
                    card.on('click', lambda s=spec: _select(s))
                    ui.label(spec.name).classes('text-lg font-bold')
                    with ui.row().classes('gap-2 mt-1'):
                        ui.badge(spec.category, color='blue')
                        ui.badge(spec.difficulty, color=diff_color)
                    desc_text = spec.description[:100] + '...' if len(spec.description) > 100 else spec.description
                    ui.label(desc_text).classes('text-sm text-gray-400 mt-2')

        # ── Launch panel (hidden until benchmark selected) ──────────────
        launch_panel = ui.card().classes('w-full mt-6 p-6')
        launch_panel.set_visibility(False)

        bench_label = ui.label()

        def _select(spec) -> None:
            selected_benchmark['spec'] = spec
            bench_label.text = f'Configure run for: {spec.name}'
            launch_panel.set_visibility(True)

        with launch_panel:
            bench_label.classes('text-lg font-bold mb-4')
            model_options = list(dict.fromkeys([settings.designer_model, 'qwen3.5:4b', 'qwen2.5-coder:7b', 'deepseek-coder-v2:16b', 'codellama:7b']))
            model_select = ui.select(
                model_options,
                value=settings.designer_model,
                label='LLM Model',
            ).classes('w-64')
            with ui.row().classes('w-full gap-8 mt-4'):
                with ui.column():
                    ui.label('Max Iterations').classes('text-sm text-gray-400')
                    iter_slider = ui.slider(min=1, max=20, value=settings.max_iterations).props('label-always').classes('w-48')
                with ui.column():
                    ui.label('Coverage Threshold (%)').classes('text-sm text-gray-400')
                    cov_slider = ui.slider(min=0, max=100, value=int(settings.coverage_threshold)).props('label-always').classes('w-48')
            mutation_check = ui.checkbox('Enable Mutation Testing').classes('mt-2')

            async def start_run() -> None:
                spec = selected_benchmark.get('spec')
                if spec is None:
                    ui.notify('Select a benchmark first', type='warning')
                    return

                config = RunConfig(
                    max_iterations=int(iter_slider.value),
                    coverage_threshold=float(cov_slider.value),
                    run_mutation_testing=mutation_check.value,
                    designer_model=model_select.value,
                    verifier_model=model_select.value,
                )

                # Create the Run record
                async with get_session() as session:
                    run = Run(
                        benchmark_id=0,  # Will be resolved by orchestrator
                        designer_model=config.designer_model or settings.designer_model,
                        verifier_model=config.verifier_model or settings.verifier_model,
                        status=RunStatus.PENDING,
                    )
                    session.add(run)
                    await session.flush()
                    run_id = run.id

                ui.notify(f'Starting run #{run_id}...', type='positive')

                # Launch pipeline in background
                orchestrator = PipelineOrchestrator(config=config)
                asyncio.create_task(orchestrator.run(spec, run_id=run_id))

                # Navigate to the iteration view
                ui.navigate.to(f'/run/{run_id}')

            ui.button('Start Run', on_click=start_run).props('color=primary icon=play_arrow').classes('mt-4')

        # ── Recent runs table ───────────────────────────────────────────
        ui.label('Recent Runs').classes('text-xl font-bold mt-8 mb-4')

        runs_columns = [
            {'name': 'id', 'label': 'Run', 'field': 'id', 'align': 'left'},
            {'name': 'benchmark', 'label': 'Benchmark', 'field': 'benchmark', 'align': 'left'},
            {'name': 'model', 'label': 'Model', 'field': 'model', 'align': 'left'},
            {'name': 'status', 'label': 'Status', 'field': 'status', 'align': 'left'},
            {'name': 'iterations', 'label': 'Iterations', 'field': 'iterations', 'align': 'center'},
            {'name': 'time', 'label': 'Time', 'field': 'time', 'align': 'center'},
        ]

        runs_table = ui.table(columns=runs_columns, rows=[], row_key='id').classes('w-full')
        runs_table.on('rowClick', lambda e: ui.navigate.to(f"/run/{e.args[1]['id']}"))

        async def refresh_runs() -> None:
            try:
                from sqlalchemy import select
                async with get_session() as session:
                    result = await session.execute(
                        select(Run).order_by(Run.started_at.desc()).limit(20)
                    )
                    runs = result.scalars().all()
                    rows = []
                    for r in runs:
                        rows.append({
                            'id': r.id,
                            'benchmark': f'Benchmark #{r.benchmark_id}',
                            'model': r.designer_model,
                            'status': r.status.value if r.status else 'unknown',
                            'iterations': r.total_iterations,
                            'time': f'{(r.finished_at - r.started_at).total_seconds():.0f}s' if r.finished_at and r.started_at else '—',
                        })
                    runs_table.rows = rows
                    runs_table.update()
            except Exception as e:
                log.warning("failed_to_load_runs", error=str(e))

        await refresh_runs()
        ui.timer(5.0, refresh_runs)
