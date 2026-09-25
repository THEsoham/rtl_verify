"""Comparison analytics page — compare multiple runs side-by-side."""

from __future__ import annotations

from nicegui import ui
import structlog

from rtl_verify.database import get_session
from rtl_verify.metrics.collector import MetricsCollector
from rtl_verify.metrics.comparison import MetricsComparison
from rtl_verify.web.components.charts import comparison_bar_chart, comparison_radar_chart

log = structlog.get_logger()
collector = MetricsCollector()
comparator = MetricsComparison()


@ui.page('/compare')
async def comparison_page() -> None:
    from rtl_verify.web.pages.dashboard import header_nav, sidebar
    header_nav()
    sidebar()

    # Load all runs
    async with get_session() as session:
        all_runs = await collector.get_all_runs(session)

    with ui.column().classes('p-6 w-full max-w-6xl mx-auto'):
        ui.label('Run Comparison').classes('text-2xl font-bold mb-6')

        if not all_runs:
            ui.label('No runs available yet. Start a benchmark run from the dashboard.').classes('text-gray-400')
            return

        # ── Run selector ────────────────────────────────────────────────
        ui.label('Select runs to compare:').classes('text-sm text-gray-400 mb-2')

        run_options = {r.run_id: f'Run #{r.run_id} — {r.benchmark_name} ({r.designer_model}) [{r.status}]' for r in all_runs}
        selected_runs = ui.select(
            options=run_options,
            multiple=True,
            label='Select Runs',
        ).classes('w-full mb-4')

        results_container = ui.column().classes('w-full')

        async def compare() -> None:
            results_container.clear()
            ids = selected_runs.value
            if not ids or len(ids) < 2:
                ui.notify('Select at least 2 runs to compare', type='warning')
                return

            async with get_session() as session:
                comparison = await comparator.compare_runs(session, list(ids))

            with results_container:
                # ── Summary table ───────────────────────────────────────
                ui.label('Comparison Table').classes('text-lg font-bold mb-4')

                columns = [{'name': 'metric', 'label': 'Metric', 'field': 'metric', 'align': 'left'}]
                for rs in comparison.run_summaries:
                    columns.append({
                        'name': f'run_{rs.run_id}',
                        'label': f'Run #{rs.run_id}',
                        'field': f'run_{rs.run_id}',
                        'align': 'center',
                    })

                rows = []
                for row in comparison.comparison_table:
                    r = {'metric': row.metric_name}
                    for run_id, val in row.values.items():
                        display = f'{val:.1f}' if isinstance(val, float) else str(val) if val is not None else '—'
                        r[f'run_{run_id}'] = display
                    rows.append(r)

                ui.table(columns=columns, rows=rows, row_key='metric').classes('w-full mb-8')

                # ── Charts ──────────────────────────────────────────────
                labels = [f'Run #{rs.run_id}' for rs in comparison.run_summaries]

                ui.label('Iterations to Complete').classes('text-lg font-bold mb-2')
                iters_vals = [rs.total_iterations for rs in comparison.run_summaries]
                comparison_bar_chart(labels, 'Iterations', iters_vals)

                if any(rs.final_line_coverage for rs in comparison.run_summaries):
                    ui.label('Final Coverage').classes('text-lg font-bold mt-6 mb-2')
                    cov_vals = [rs.final_line_coverage or 0 for rs in comparison.run_summaries]
                    comparison_bar_chart(labels, 'Line Coverage (%)', cov_vals)

                # Radar chart
                metrics_for_radar = {}
                for rs in comparison.run_summaries:
                    metrics_for_radar.setdefault('Iterations', []).append(rs.total_iterations)
                    metrics_for_radar.setdefault('Coverage', []).append(rs.final_line_coverage or 0)
                    metrics_for_radar.setdefault('Mutation Score', []).append(rs.final_mutation_score or 0)

                if len(labels) >= 2:
                    ui.label('Multi-Dimensional Comparison').classes('text-lg font-bold mt-6 mb-2')
                    comparison_radar_chart(labels, metrics_for_radar)

        ui.button('Compare Selected', on_click=compare).props('color=primary icon=compare_arrows').classes('mb-6')
