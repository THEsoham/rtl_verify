from nicegui import ui
from typing import Callable

def iteration_timeline(iterations: list, selected: int, on_select: Callable) -> ui.element:
    """Vertical timeline showing iteration nodes with status colors."""
    with ui.column().classes('w-full items-center') as timeline_container:
        for it in iterations:
            color = 'green' if it.get('status') == 'pass' else ('red' if it.get('status') == 'fail' else 'yellow')
            
            with ui.row().classes('items-center cursor-pointer mb-2').on('click', lambda i=it['iteration_num']: on_select(i)):
                with ui.element('div').classes(f'w-8 h-8 rounded-full flex items-center justify-center bg-{color}-500 text-white font-bold'):
                    ui.label(str(it['iteration_num']))
                with ui.column().classes('ml-4'):
                    ui.label(f"Iteration {it['iteration_num']}").classes('font-semibold')
                    ui.label(it.get('status', 'unknown')).classes('text-xs text-gray-400')
                    
            if it != iterations[-1]:
                ui.element('div').classes('h-8 border-l-2 border-gray-600')
                
    return timeline_container
