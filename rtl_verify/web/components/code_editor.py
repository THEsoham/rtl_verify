from nicegui import ui

def code_display(code: str, language: str = 'verilog', max_height: str = '500px') -> ui.element:
    """Display syntax-highlighted code using NiceGUI's ui.code()."""
    return ui.code(code, language=language).classes('w-full').style(f'max-height: {max_height}; overflow-y: auto;')
