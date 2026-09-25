from nicegui import ui

def metric_card(title: str, value: str | float, subtitle: str = '', icon: str = 'analytics', color: str = 'primary') -> ui.card:
    """A card displaying a single metric with title, value, and optional subtitle."""
    with ui.card().classes('p-4 w-48') as card:
        ui.icon(icon).classes(f'text-{color} text-2xl')
        ui.label(title).classes('text-sm text-gray-400')
        ui.label(str(value)).classes('text-2xl font-bold')
        if subtitle:
            ui.label(subtitle).classes('text-xs text-gray-500')
    return card
