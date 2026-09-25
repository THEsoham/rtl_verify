"""Iteration timeline page — the most important view in the application."""

from __future__ import annotations

from nicegui import ui
import structlog
from sqlalchemy import select

from rtl_verify.database import get_session
from rtl_verify.models import Run, Iteration, RunStatus, IterationStatus
from rtl_verify.web.components.code_editor import code_display
from rtl_verify.web.components.timeline import iteration_timeline

log = structlog.get_logger()

STATUS_ICON = {
    IterationStatus.COMPILE_FAIL_RTL: ('error', 'red'),
    IterationStatus.COMPILE_FAIL_TB: ('warning', 'orange'),
    IterationStatus.SIM_FAIL: ('cancel', 'red'),
    IterationStatus.SIM_PASS: ('check_circle', 'green'),
    IterationStatus.ERROR: ('report', 'red'),
}


@ui.page('/run/{run_id}')
async def iteration_page(run_id: int) -> None:
    from rtl_verify.web.pages.dashboard import header_nav, sidebar
    header_nav()
    sidebar()

    # Load run info
    async with get_session() as session:
        run = await session.get(Run, run_id)
        if not run:
            ui.label(f'Run #{run_id} not found').classes('text-red-500 text-xl p-6')
            return
        result = await session.execute(
            select(Iteration)
            .where(Iteration.run_id == run_id)
            .order_by(Iteration.iteration_num)
        )
        iterations = list(result.scalars().all())

    with ui.column().classes('p-6 w-full max-w-7xl mx-auto'):
        # ── Header ──────────────────────────────────────────────────────
        with ui.row().classes('w-full justify-between items-center mb-6'):
            ui.label(f'Run #{run_id}').classes('text-2xl font-bold')
            status_val = run.status.value if run.status else 'unknown'
            color = 'green' if status_val == 'passed' else 'blue' if status_val == 'running' else 'red'
            ui.badge(status_val.upper(), color=color).classes('text-lg')
            ui.label(f'Iterations: {run.total_iterations}').classes('text-gray-400')

            with ui.row().classes('gap-2'):
                ui.button('RTL', on_click=lambda: ui.navigate.to(f'/run/{run_id}/rtl')).props('outline size=sm')
                ui.button('Verification', on_click=lambda: ui.navigate.to(f'/run/{run_id}/verification')).props('outline size=sm')
                ui.button('Coverage', on_click=lambda: ui.navigate.to(f'/run/{run_id}/coverage')).props('outline size=sm')

        if not iterations:
            if run.status == RunStatus.RUNNING:
                ui.label('Pipeline is running — waiting for first iteration...').classes('text-gray-400 text-lg')
                ui.spinner('dots', size='lg')
            else:
                ui.label('No iterations recorded.').classes('text-gray-400')

            # Auto-refresh while running
            async def poll():
                async with get_session() as s:
                    r = await s.get(Run, run_id)
                    res = await s.execute(
                        select(Iteration).where(Iteration.run_id == run_id)
                    )
                    new_iters = res.scalars().all()
                if new_iters or (r and r.status != RunStatus.RUNNING):
                    ui.navigate.reload()

            ui.timer(3.0, poll)
            return

        # ── Main layout ─────────────────────────────────────────────────
        selected = {'num': iterations[-1].iteration_num}  # Select latest by default

        with ui.row().classes('w-full gap-6'):
            # Timeline (left)
            with ui.card().classes('w-72 p-4 shrink-0'):
                ui.label('Iterations').classes('text-lg font-bold mb-3')
                for it in iterations:
                    icon_name, icon_color = STATUS_ICON.get(
                        it.status, ('help', 'grey')
                    )
                    is_selected = it.iteration_num == selected['num']
                    bg = 'bg-[#1a1a3e]' if is_selected else ''

                    with ui.row().classes(
                        f'items-center gap-3 py-2 px-3 rounded cursor-pointer '
                        f'hover:bg-[#1a1a3e] {bg} w-full'
                    ).on('click', lambda n=it.iteration_num: _select_iter(n)):
                        ui.icon(icon_name).classes(f'text-{icon_color}-500')
                        ui.label(f'Iter {it.iteration_num}').classes('font-medium')
                        if it.sim_passed:
                            ui.badge('PASS', color='green').classes('ml-auto')
                        elif it.status == IterationStatus.SIM_FAIL:
                            ui.badge('FAIL', color='red').classes('ml-auto')

            # Detail panel (right)
            detail_container = ui.column().classes('flex-1')

        def _select_iter(num: int) -> None:
            selected['num'] = num
            _render_details()

        def _render_details() -> None:
            detail_container.clear()
            it = next((i for i in iterations if i.iteration_num == selected['num']), None)
            if not it:
                return

            with detail_container:
                icon_name, icon_color = STATUS_ICON.get(it.status, ('help', 'grey'))
                with ui.row().classes('items-center gap-3 mb-4'):
                    ui.icon(icon_name).classes(f'text-{icon_color}-500 text-2xl')
                    ui.label(f'Iteration {it.iteration_num}').classes('text-xl font-bold')
                    ui.badge(it.status.value.replace('_', ' ').upper(), color=icon_color)

                with ui.row().classes('gap-4 text-sm text-gray-400 mb-4'):
                    if it.designer_time_ms:
                        ui.label(f'Designer: {it.designer_time_ms}ms')
                    if it.verifier_time_ms:
                        ui.label(f'Verifier: {it.verifier_time_ms}ms')
                    if it.sim_time_ms:
                        ui.label(f'Simulation: {it.sim_time_ms}ms')

                with ui.tabs().classes('w-full') as tabs:
                    t_rtl = ui.tab('RTL')
                    t_tb = ui.tab('Testbench')
                    t_comp = ui.tab('Compile')
                    t_sim = ui.tab('Simulation')
                    t_fb = ui.tab('Feedback')

                with ui.tab_panels(tabs, value=t_rtl).classes('w-full'):
                    with ui.tab_panel(t_rtl):
                        if it.rtl_source:
                            code_display(it.rtl_source, language='verilog')
                        else:
                            ui.label('No RTL generated').classes('text-gray-500')

                    with ui.tab_panel(t_tb):
                        if it.testbench_source:
                            code_display(it.testbench_source, language='verilog')
                        else:
                            ui.label('No testbench generated').classes('text-gray-500')

                    with ui.tab_panel(t_comp):
                        output = (it.compile_stdout or '') + '\n' + (it.compile_stderr or '')
                        code_display(output.strip() or 'No compile output', language='text')

                    with ui.tab_panel(t_sim):
                        output = (it.sim_stdout or '') + '\n' + (it.sim_stderr or '')
                        code_display(output.strip() or 'No simulation output', language='text')

                    with ui.tab_panel(t_fb):
                        if it.feedback:
                            ui.markdown(it.feedback)
                        else:
                            ui.label('No feedback (final iteration)').classes('text-gray-500')

        _render_details()

        # Auto-refresh while run is active
        if run.status == RunStatus.RUNNING:
            async def poll_iterations():
                async with get_session() as s:
                    r = await s.get(Run, run_id)
                    res = await s.execute(
                        select(Iteration).where(Iteration.run_id == run_id)
                    )
                    new_iters = list(res.scalars().all())
                if len(new_iters) > len(iterations) or (r and r.status != RunStatus.RUNNING):
                    ui.navigate.reload()

            ui.timer(3.0, poll_iterations)
