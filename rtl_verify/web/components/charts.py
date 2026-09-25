from nicegui import ui

def coverage_trend_chart(iterations: list[dict]) -> ui.echart:
    """Line chart showing coverage metrics across iterations."""
    x_data = [f"It {it['iteration_num']}" for it in iterations]
    line_data = [it.get('line_coverage', 0) for it in iterations]
    
    options = {
        'backgroundColor': '#1a1a2e',
        'title': {'text': 'Coverage Trend', 'textStyle': {'color': '#fff'}},
        'tooltip': {'trigger': 'axis'},
        'xAxis': {'type': 'category', 'data': x_data, 'axisLabel': {'color': '#fff'}},
        'yAxis': {'type': 'value', 'max': 100, 'axisLabel': {'color': '#fff'}},
        'series': [
            {'name': 'Line Coverage', 'data': line_data, 'type': 'line', 'smooth': True, 'itemStyle': {'color': '#4fc3f7'}}
        ]
    }
    return ui.echart(options).classes('w-full h-64')

def comparison_bar_chart(run_labels: list[str], metric_name: str, values: list[float]) -> ui.echart:
    """Bar chart comparing a metric across runs."""
    options = {
        'backgroundColor': '#1a1a2e',
        'title': {'text': metric_name, 'textStyle': {'color': '#fff'}},
        'tooltip': {'trigger': 'axis'},
        'xAxis': {'type': 'category', 'data': run_labels, 'axisLabel': {'color': '#fff'}},
        'yAxis': {'type': 'value', 'axisLabel': {'color': '#fff'}},
        'series': [
            {'data': values, 'type': 'bar', 'itemStyle': {'color': '#66bb6a'}}
        ]
    }
    return ui.echart(options).classes('w-full h-64')

def comparison_radar_chart(run_labels: list[str], metrics: dict[str, list[float]]) -> ui.echart:
    """Radar chart for multi-dimensional comparison."""
    # Assuming metrics is {metric_name: [value_for_run1, value_for_run2, ...]}
    indicator = [{'name': name, 'max': 100} for name in metrics.keys()]
    series_data = []
    
    for i, run_label in enumerate(run_labels):
        run_values = [metrics[name][i] for name in metrics.keys()]
        series_data.append({'name': run_label, 'value': run_values})

    options = {
        'backgroundColor': '#1a1a2e',
        'title': {'text': 'Multi-dimensional Comparison', 'textStyle': {'color': '#fff'}},
        'tooltip': {},
        'legend': {'data': run_labels, 'textStyle': {'color': '#fff'}, 'bottom': 0},
        'radar': {'indicator': indicator},
        'series': [{'type': 'radar', 'data': series_data}]
    }
    return ui.echart(options).classes('w-full h-96')

def coverage_gauge(value: float, title: str = 'Coverage') -> ui.echart:
    """Circular gauge showing a coverage percentage."""
    options = {
        'backgroundColor': '#1a1a2e',
        'series': [
            {
                'type': 'gauge',
                'progress': {'show': True, 'width': 10},
                'axisLine': {'lineStyle': {'width': 10}},
                'axisTick': {'show': False},
                'splitLine': {'show': False},
                'axisLabel': {'show': False},
                'detail': {'valueAnimation': True, 'formatter': '{value}%', 'color': '#fff'},
                'data': [{'value': value, 'name': title}],
                'title': {'textStyle': {'color': '#fff'}}
            }
        ]
    }
    return ui.echart(options).classes('w-64 h-64')
