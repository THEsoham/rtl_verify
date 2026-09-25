from nicegui import ui

@ui.page('/settings')
async def settings_page():
    from rtl_verify.web.pages.dashboard import header_nav, sidebar
    header_nav()
    sidebar()
    
    with ui.column().classes('p-6 w-full max-w-4xl mx-auto'):
        ui.label('Settings').classes('text-2xl font-bold mb-6')
        
        with ui.card().classes('w-full p-6 mb-6'):
            ui.label('Ollama Connection').classes('text-xl font-bold mb-4')
            host = ui.input('Ollama Host', value='http://localhost:11434').classes('w-full mb-4')
            ui.button('Test Connection', color='primary')
            
        with ui.card().classes('w-full p-6 mb-6'):
            ui.label('Model Management').classes('text-xl font-bold mb-4')
            ui.label('Available Models:').classes('mb-2')
            ui.label('- qwen2.5-coder:7b').classes('ml-4 text-gray-400')
            ui.label('- deepseek-coder-v2:16b').classes('ml-4 text-gray-400 mb-4')
            
            with ui.row().classes('w-full items-center gap-2'):
                ui.input('Model Name').classes('flex-1')
                ui.button('Pull Model', color='secondary')
                
        with ui.card().classes('w-full p-6 mb-6'):
            ui.label('Default Parameters').classes('text-xl font-bold mb-4')
            ui.number('Max Iterations', value=10).classes('mb-2')
            ui.number('Coverage Threshold', value=80).classes('mb-2')
            
        ui.button('Save Settings', color='green').classes('w-full')
