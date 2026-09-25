from nicegui import ui

@ui.page('/run/{run_id}/verification')
async def verification_page(run_id: str):
    from rtl_verify.web.pages.dashboard import header_nav, sidebar
    header_nav()
    sidebar()
    
    with ui.column().classes('p-6 w-full max-w-6xl mx-auto'):
        ui.label(f'Verification Results - Run {run_id}').classes('text-2xl font-bold mb-6')
        
        ui.select([1, 2], value=2, label='Iteration')
        
        with ui.card().classes('w-full mt-4'):
            ui.label('Test Results').classes('text-xl font-bold mb-2')
            columns = [
                {'name': 'test', 'label': 'Test Case', 'field': 'test'},
                {'name': 'status', 'label': 'Status', 'field': 'status'},
                {'name': 'time', 'label': 'Time', 'field': 'time'},
            ]
            rows = [
                {'test': 'test_reset', 'status': 'PASS', 'time': '10ms'},
                {'test': 'test_compute', 'status': 'PASS', 'time': '40ms'},
            ]
            ui.table(columns=columns, rows=rows, row_key='test').classes('w-full')
            
        with ui.card().classes('w-full mt-4'):
            ui.label('Assertions').classes('text-xl font-bold mb-2')
            ui.label('All assertions passed.').classes('text-green-500')
