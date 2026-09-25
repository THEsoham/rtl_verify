"""Coverage dashboard page — gauges, trends, and threshold indicators."""

from __future__ import annotations

from nicegui import ui
import structlog
from sqlalchemy import select

from rtl_verify.database import get_session
from rtl_verify.models import Run, Iteration, CoverageReport
from rtl_verify.web.components.charts import coverage_gauge, coverage_trend_chart
from rtl_verify.config import settings

log = structlog.get_logger()


@ui.page('/run/{run_id}/coverage')
async def coverage_page(run_id: int) -> None:
    from rtl_verify.web.pages.dashboard import header_nav, sidebar
    header_nav()
    sidebar()

    # Load coverage data
    coverage_data = []
    async with get_session() as session:
        run = await session.get(Run, run_id)
        result = await session.execute(
            select(Iteration, CoverageReport)
            .outerjoin(CoverageReport, CoverageReport.iteration_id == Iteration.id)
            .where(Iteration.run_id == run_id)
            .order_by(Iteration.iteration_num)
        )
        for it, cov in result.all():
            coverage_data.append({
                'iteration': it.iteration_num,
                'line': cov.line_coverage if cov else None,
                'branch': cov.branch_coverage if cov else None,
                'toggle': cov.toggle_coverage if cov else None,
            })

    with ui.column().classes('p-6 w-full max-w-6xl mx-auto'):
        with ui.row().classes('items-center gap-4 mb-6'):
            ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to(f'/run/{run_id}')).props('flat')
            ui.label(f'Coverage — Run #{run_id}').classes('text-2xl font-bold')

        # Latest coverage values
        latest = next((d for d in reversed(coverage_data) if d['line'] is not None), None)

        if not latest:
            ui.label('No coverage data collected for this run.').classes('text-gray-400 text-lg')
            ui.label('Coverage requires Verilator and is collected on passing iterations.').classes('text-sm text-gray-500')
            return

        # ── Gauges ──────────────────────────────────────────────────────
        ui.label('Current Coverage').classes('text-lg font-bold mb-4')
        with ui.row().classes('gap-6 mb-8'):
            coverage_gauge(latest.get('line', 0) or 0, 'Line Coverage')
            coverage_gauge(latest.get('branch', 0) or 0, 'Branch Coverage')
            coverage_gauge(latest.get('toggle', 0) or 0, 'Toggle Coverage')

        # Threshold indicator
        threshold = settings.coverage_threshold
        meets = (latest.get('line', 0) or 0) >= threshold
        color = 'green' if meets else 'red'
        icon = 'check_circle' if meets else 'cancel'
        with ui.row().classes('items-center gap-2 mb-6'):
            ui.icon(icon).classes(f'text-{color}-500 text-xl')
            ui.label(
                f'Threshold: {threshold}% — '
                f'{"Met" if meets else "Not met"} (line coverage: {latest.get("line", 0):.1f}%)'
            ).classes(f'text-{color}-500')

        # ── Trend chart ─────────────────────────────────────────────────
        ui.label('Coverage Trend').classes('text-lg font-bold mb-4')
        coverage_trend_chart(coverage_data)
