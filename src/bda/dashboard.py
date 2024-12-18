#!/usr/bin/env python
from importlib.resources.abc import Traversable
from pathlib import Path
from collections import defaultdict

from dash import Dash, html, dcc, callback, Output, Input, dash_table
import plotly.graph_objects as go
import plotly.express as px
import statsmodels

import pandas as pd

import sys

if __name__ == "__main__":
    sys.path.append(str(Path(__file__).parent.parent))
from .delta_analyzer import AiderTestResult, parse_benchmark_source, compare_benchmark_runs
from .benchmark_analyzer import BenchmarkAnalyzer

app = Dash(__name__)

def create_dashboard(benchmark1: Traversable, benchmark2: Traversable, port: int = 8080):
    # Parse benchmark data
    benchmark_run_1 = {t.name: t for t in parse_benchmark_source(benchmark1)}
    benchmark_run_2 = {t.name: t for t in parse_benchmark_source(benchmark2)}

    # Get comparison results
    only_1, only_2, improved, worsened, stable = compare_benchmark_runs(
        benchmark_run_1, benchmark_run_2
    )

    # Create layout
    app.layout = html.Div([
        # Header
        html.H1('Benchmark Delta Dashboard', className='header'),

        # Benchmark Info
        html.Div([
            html.H2('Benchmark Information'),
            html.Div([
                html.Div([
                    html.H3('Baseline'),
                    html.P(f"Path: {benchmark1}"),
                    html.P(f"Tests: {len(benchmark_run_1)}"),
                ], className='info-box'),
                html.Div([
                    html.H3('Current'),
                    html.P(f"Path: {benchmark2}"),
                    html.P(f"Tests: {len(benchmark_run_2)}"),
                ], className='info-box'),
            ], className='info-container')
        ]),

        html.Div([
            html.H2('State Transition Analysis'),
            dcc.Graph(
                id='state-transition-sankey',
                figure=create_state_transition_sankey(benchmark_run_1, benchmark_run_2)
            ),
        ]),

        # Metrics Comparison
        html.Div([
            html.H2('Metrics Comparison'),
            dcc.Graph(
                id='metrics-comparison',
                figure=create_metrics_comparison(benchmark_run_1, benchmark_run_2)
            )
        ]),

        # Token Usage
        html.Div([
            html.H2('Token Usage'),
            create_token_usage_comparison(benchmark_run_1, benchmark_run_2)  # Use the returned Div directly
        ]),

        # TIOR vs. Errors
        html.Div([
            html.H2('TIOR vs. Errors'),
            dcc.Graph(
                id='tior-errors-scatter',
                figure=create_tior_vs_errors_scatter(benchmark_run_1, benchmark_run_2)
            )
        ]),

        # Token Ratio
        html.Div([
            html.H2('TIOR (Token I/O Ratio)'),
            dcc.Graph(
                id='token-ratio-bar-chart',
                figure=create_tior_bar_chart(benchmark_run_1, benchmark_run_2)
            )
        ]),

        # Detailed Test Results
        html.Div([
            html.H2('Detailed Test Results'),
            create_test_results_table(benchmark_run_1, benchmark_run_2)
        ]),
    ], className='container')

def create_metrics_comparison(run_1, run_2):
    """Create bar chart comparing various metrics"""

    metrics = {
        'Failed Tests': (sum(1 for t in run_1.values() if t.failed_attempt_count < 0),
                         sum(1 for t in run_2.values() if t.failed_attempt_count < 0)),
        'Failed Attempts': (sum(abs(t.failed_attempt_count) for t in run_1.values()),
                            sum(abs(t.failed_attempt_count) for t in run_2.values())),
        'Duration (minutes)': (sum(t.duration for t in run_1.values()) / 60,
                     sum(t.duration for t in run_2.values()) / 60),
        'Out Tokens (.5e-3)': (sum(t.received_tokens for t in run_1.values()) * .5e-3,
                     sum(t.received_tokens for t in run_2.values()) * .5e-3),
        'TIOR (1e-2)': (sum(t.sent_tokens / t.received_tokens for t in run_1.values() if t.received_tokens != 0) * 1e-2,
                     sum(t.sent_tokens / t.received_tokens for t in run_2.values() if t.received_tokens != 0) * 1e-2),
        'User Asks': (sum(t.user_ask_count for t in run_1.values()),
                      sum(t.user_ask_count for t in run_2.values())),
        'Errors (1e-1)': (sum(t.error_output_count for t in run_1.values()) * 1e-1,
                   sum(t.error_output_count for t in run_2.values()) * 1e-1),
        'CS Errors': (sum(t.cedarscript_errors for t in run_1.values()),
                      sum(t.cedarscript_errors for t in run_2.values())),
        'Syntax Errors': (sum(t.syntax_errors for t in run_1.values()),
                          sum(t.syntax_errors for t in run_2.values())),
        'Indentation Errors': (sum(t.indentation_errors for t in run_1.values()),
                          sum(t.indentation_errors for t in run_2.values())),
        'Timeouts': (sum(t.timeouts for t in run_1.values()),
                     sum(t.timeouts for t in run_2.values())),
    }

    fig = go.Figure(data=[
        go.Bar(name='Baseline', x=list(metrics.keys()), y=[m[0] for m in metrics.values()]),
        go.Bar(name='Current', x=list(metrics.keys()), y=[m[1] for m in metrics.values()])
    ])

    fig.update_layout(
        barmode='group',
        title_text="Key Metrics Comparison"
    )
    return fig

def create_tior_vs_errors_scatter(run_1, run_2):
    """Create a scatter plot with trend lines for TIOR vs. number of errors."""
    def calculate_tior(run):
        return {
            test_name: (test.sent_tokens / test.received_tokens if test.received_tokens != 0 else 0)
            for test_name, test in run.items()
        }

    tior_1 = calculate_tior(run_1)
    tior_2 = calculate_tior(run_2)

    df = pd.DataFrame({
        'Test': list(tior_1.keys()),
        'Baseline TIOR': list(tior_1.values()),
        'Current TIOR': [tior_2.get(test, 0) for test in tior_1.keys()],
        'Baseline Errors': [run_1[test].error_output_count for test in tior_1.keys()],
        'Current Errors': [run_2[test].error_output_count if test in run_2 else 0 for test in tior_1.keys()]
    })

    fig = px.scatter(
        df,
        x='Baseline TIOR',
        y='Baseline Errors',
        trendline='ols',
        title='TIOR vs. Errors (Baseline)',
        labels={'Baseline TIOR': 'Token Input/Output Ratio', 'Baseline Errors': 'Number of Errors'},
        hover_data=['Test']
    )

    fig.add_trace(
        px.scatter(
            df,
            x='Current TIOR',
            y='Current Errors',
            trendline='ols',
            title='TIOR vs. Errors (Current)',
            labels={'Current TIOR': 'Token Input/Output Ratio', 'Current Errors': 'Number of Errors'},
            hover_data=['Test']
        ).data[0]
    )

    fig.update_layout(
        title='TIOR vs. Errors with Trend Lines',
        xaxis_title='Token Input/Output Ratio',
        yaxis_title='Number of Errors',
        legend_title='Run'
    )

    return fig

def create_tior_bar_chart(run_1, run_2):
    """Create a bar chart for the ratio of sent_tokens to received_tokens."""
    def calculate_ratio(run):
        return {
            test_name: (test.sent_tokens / test.received_tokens if test.received_tokens != 0 else 0)
            for test_name, test in run.items()
        }

    ratio_1 = calculate_ratio(run_1)
    ratio_2 = calculate_ratio(run_2)

    df = pd.DataFrame({
        'Test': list(ratio_1.keys()),
        'Baseline Ratio': list(ratio_1.values()),
        'Current Ratio': [ratio_2.get(test, 0) for test in ratio_1.keys()]
    })

    fig = go.Figure(data=[
        go.Bar(name='Baseline', x=df['Test'], y=df['Baseline Ratio']),
        go.Bar(name='Current', x=df['Test'], y=df['Current Ratio'])
    ])

    fig.update_layout(
        barmode='group',
        title_text="TIOR (Token I/O Ratio)"
    )
    return fig


def create_token_usage_comparison(run_1, run_2):
    """Create two scatter plots comparing token usage for baseline and current runs"""
    # Create dataframes with error handling for missing values
    def create_df(run):
        return pd.DataFrame({
            'Test': list(run.keys()),
            'input': [t.sent_tokens for t in run.values()],
            'output': [t.received_tokens for t in run.values()],
            'Total Tokens': [t.sent_tokens + t.received_tokens for t in run.values()],
            'Errors': [t.error_output_count for t in run.values()]
        }).fillna(0)  # Handle any missing values

    df_baseline = create_df(run_1)
    df_current = create_df(run_2)

    # Get max values for consistent scaling
    max_input = max(df_baseline['input'].max(), df_current['input'].max())
    max_output = max(df_baseline['output'].max(), df_current['output'].max())
    max_total = max(df_baseline['Total Tokens'].max(), df_current['Total Tokens'].max())
    max_errors = max(df_baseline['Errors'].max(), df_current['Errors'].max())

    def create_scatter(df, title):
        return px.scatter(
            df,
            x='input',
            y='output',
            size='Total Tokens',
            size_max=30,  # Limit maximum bubble size
            color='Errors',
            range_color=[0, max_errors],  # Consistent color scale
            hover_data=['Test'],
            title=title,
            labels={
                'input': 'Input Tokens',
                'output': 'Output Tokens'
            }
        )

    # Create plots with consistent scales
    fig_baseline = create_scatter(df_baseline, 'Baseline Token Usage')
    fig_current = create_scatter(df_current, 'Current Token Usage')

    # Update layout for both plots
    for fig in [fig_baseline, fig_current]:
        fig.update_layout(
            showlegend=True,
            plot_bgcolor='white',
            width=1200,
            height=400,
            margin=dict(t=50, b=50, l=50, r=50),
            xaxis=dict(range=[0, max_input * 1.1]),  # Add 10% padding
            yaxis=dict(range=[0, max_output * 1.1])
        )
        fig.update_traces(
            marker=dict(line=dict(width=1, color='DarkSlateGrey')),
            selector=dict(mode='markers')
        )
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGrey')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGrey')

    return html.Div(children=[
        html.Div(children=[
            dcc.Graph(
                id='token-usage-baseline',
                figure=fig_baseline
            )
        ], className='six columns'),
        html.Div(children=[
            dcc.Graph(
                id='token-usage-current',
                figure=fig_current
            )
        ], className='six columns')
    ], className='row')


def create_token_usage_comparison_all(run_1, run_2):
    """Create scatter plot comparing token usage"""
    df = pd.DataFrame({
        'Test': list(run_1.keys()),
        'Sent (Baseline)': [t.sent_tokens for t in run_1.values()],
        'Received (Baseline)': [t.received_tokens for t in run_1.values()],
        'Sent (Current)': [run_2[k].sent_tokens if k in run_2 else 0 for k in run_1.keys()],
        'Received (Current)': [run_2[k].received_tokens if k in run_2 else 0 for k in run_1.keys()],
    })

    fig = px.scatter(
        df,
        x='Sent (Baseline)',
        y='Received (Baseline)',
        size='Sent (Current)',
        color='Received (Current)',
        hover_data=['Test']
    )

    fig.update_layout(title_text="Token Usage Distribution")
    return fig

def create_test_results_table(run_1, run_2):
    """Create an interactive table showing detailed test results with token ratios."""
    data = []
    for test in sorted(set(run_1.keys()) | set(run_2.keys())):
        tior_baseline = (run_1[test].sent_tokens / run_1[test].received_tokens
                          if test in run_1 and run_1[test].received_tokens != 0 else 0)
        tior_current = (run_2[test].sent_tokens / run_2[test].received_tokens
                         if test in run_2 and run_2[test].received_tokens != 0 else 0)
        tior_percent_change = ((tior_current - tior_baseline) / tior_baseline * 100
                          if tior_baseline != 0 else 'N/A')

        if test in run_1 and test in run_2:
            data.append({
                'Test Name': test,
                'Status': get_test_status(test, run_1, run_2),
                'Baseline Failed Attempts': f"{run_1[test].failed_attempt_count:+d}",
                'Current Failed Attempts': f"{run_2[test].failed_attempt_count:+d}",
                'Δ Duration': f"{run_2[test].duration - run_1[test].duration:+.2f}s",
                'Δ Out Token': f"{run_2[test].received_tokens - run_1[test].received_tokens:+d}",
                'Δ CS Errors': f"{run_2[test].cedarscript_errors - run_1[test].cedarscript_errors:+d}",
                'Δ Syntax Errors': f"{run_2[test].syntax_errors - run_1[test].syntax_errors:+d}",
                'Δ Errors': f"{run_2[test].error_output_count - run_1[test].error_output_count:+d}",
                'Δ TIOR': f"{tior_percent_change:.2f}%" if tior_percent_change != 'N/A' else 'N/A',
                'Baseline TIOR': f"{tior_baseline:.2f}",
                'Current TIOR': f"{tior_current:.2f}"
            })
        else:
            data.append({
                'Test Name': test,
                'Status': get_test_status(test, run_1, run_2),
                'Baseline Failed Attempts': 'N/A' if test not in run_1 else f"{run_1[test].failed_attempt_count:.2f}",
                'Current Failed Attempts': 'N/A' if test not in run_2 else f"{run_2[test].failed_attempt_count:.2f}",
                'Δ Duration': 'N/A',
                'Δ Out Token': 'N/A',
                'Δ CS Errors': 'N/A',
                'Δ Syntax Errors': 'N/A',
                'Δ Errors': 'N/A',
                'Δ TIOR': 'N/A',
                'Baseline TIOR': 'N/A' if test not in run_1 else f"{tior_baseline:.2f}",
                'Current TIOR': 'N/A' if test not in run_2 else f"{tior_current:.2f}"
            })

    return dash_table.DataTable(
        id='results-table',
        columns=[{'name': k, 'id': k} for k in data[0].keys()],
        data=data,
        style_table={'overflowX': 'auto'},
        style_cell={
            'textAlign': 'left',
            'padding': '12px',
            'whiteSpace': 'normal',
            'height': 'auto',
        },
        style_header={
            'backgroundColor': 'rgb(230, 230, 230)',
            'fontWeight': 'bold'
        },
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': 'rgb(248, 248, 248)'
            }
        ],
        filter_action="native",
        sort_action="native",
        sort_mode="multi",
        page_size=20
    )

def get_test_status(test, run_1, run_2):
    """Determine the status of a test between runs"""
    if test not in run_1:
        return "New"
    if test not in run_2:
        return "Missing"
    if run_1[test] == run_2[test]:
        return "Stable: OK" if run_1[test].failed_attempt_count >= 0 else "Stable: Failed"
    if run_1[test] > run_2[test]:
        return "Now Passed" if run_1[test].failed_attempt_count < 0 else "Minor Improvement"
    return "Now Failed" if run_2[test].failed_attempt_count < 0 else "Degraded"

def create_state_transition_sankey(run_1: dict, run_2: dict):
    # Helper function to get state
    def get_state(aider_test_result: AiderTestResult):
        if aider_test_result is None:
            return "Missing"
        if aider_test_result.norm_failed_attempts < 0:
            return "Failed"
        if aider_test_result.norm_failed_attempts == 0:
            return "Passed on first"
        return f"Passed after {aider_test_result.norm_failed_attempts}"

    # Define states and their colors
    states = ["Failed", "Missing", "Passed on first"] + [f"Passed after {i}" for i in range(1, 2)]
    colors = {
        "Failed": "#ff4444",
        "Missing": "#aaaaaa",
        "Passed on first": "#00cc00",
        "Passed after 1": "#F3E400",
        "Passed after 2": "#FFAC1E",
    }

    # Create node labels
    left_nodes = [f"Baseline: {state}" for state in states]
    right_nodes = [f"Current: {state}" for state in states]
    all_nodes = left_nodes + right_nodes

    # Create node index mapping
    node_mapping = {name: idx for idx, name in enumerate(all_nodes)}

    # Initialize flow tracking
    flows = defaultdict(int)

    # Calculate transitions for all unique test names
    for test in set(run_1.keys()) | set(run_2.keys()):
        state1 = get_state(run_1.get(test, None))
        state2 = get_state(run_2.get(test, None))

        flows[(f"Baseline: {state1}", f"Current: {state2}")] += 1

    # Prepare Sankey data
    source = []
    target = []
    value = []

    for (src, tgt), count in flows.items():
        if count > 0:  # Only add non-zero flows
            source.append(node_mapping[src])
            target.append(node_mapping[tgt])
            value.append(count)

    # Create node colors list
    node_colors = []
    for label in all_nodes:
        state = label.split(": ")[1]
        node_colors.append(colors[state])

    # Create the figure
    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=all_nodes,
            color=node_colors
        ),
        link=dict(
            source=source,
            target=target,
            value=value,
            color=[f"rgba(169, 169, 169, 0.3)"] * len(source)  # Semi-transparent gray links
        )
    )])

    # Update layout
    fig.update_layout(
        title_text="State Transitions Between Runs",
        font_size=10,
        height=600,
        margin=dict(t=25, l=25, r=25, b=25)
    )

    return fig

if __name__ == '__main__':
    import sys
    from dotenv import load_dotenv
    import os

    load_dotenv(verbose=True)

    match len(sys.argv):
        case 3:
            benchmark1 = Path(sys.argv[1])
            benchmark2 = Path(sys.argv[2])
        case 2:
            benchmark1 = 'perfect'
            benchmark2 = Path(sys.argv[1])
        case 1:
            benchmark1 = Path(os.getenv('benchmark1'))
            benchmark2 = os.getenv('benchmark2')
            if not benchmark2:
                benchmark2 = benchmark1
                benchmark1 = 'perfect'
            else:
                benchmark2 = Path(benchmark2)

    if not benchmark1 or not benchmark2:
        print(f"Usage: bda [benchmark-root-1] [benchmark-root-2]")
        print(f"Usage: benchmark1='<benchmark-root-1>' benchmark2='<benchmark-root-2>' bda")
        sys.exit(1)

    create_dashboard(benchmark1, benchmark2)
    app.run(debug=True)
