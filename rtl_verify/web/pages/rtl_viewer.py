from nicegui import ui
from rtl_verify.web.components.code_editor import code_display

@ui.page('/run/{run_id}/rtl')
async def rtl_viewer_page(run_id: str):
    from rtl_verify.web.pages.dashboard import header_nav, sidebar
    header_nav()
    sidebar()
    
    with ui.column().classes('p-6 w-full max-w-6xl mx-auto'):
        with ui.row().classes('w-full justify-between items-center mb-4'):
            ui.label(f'RTL Viewer - Run {run_id}').classes('text-2xl font-bold')
            ui.button('Download RTL')
            
        with ui.row().classes('w-full gap-4'):
            # Pane left
            with ui.column().classes('w-1/4'):
                ui.select([1, 2], value=1, label='Iteration')
                
            # Pane right
            with ui.column().classes('w-3/4'):
                code_display('module test();\nendmodule', language='verilog', max_height='600px')
                
                with ui.card().classes('w-full mt-4 bg-gray-900 border border-yellow-500'):
                    ui.label('Lint Warnings').classes('text-yellow-500 font-bold mb-2')
                    ui.label('No warnings found.').classes('text-gray-300 text-sm')
