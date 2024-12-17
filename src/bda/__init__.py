from version import __version__

from .dashboard import app, create_dashboard
from .benchmark_analyzer import BenchmarkAnalyzer
from .delta_analyzer import main as show_delta


__all__ = [
    "__version__", "create_dashboard", "show_info", "show_delta"
]

def show_info(benchmark_path: str):
    with BenchmarkAnalyzer(benchmark_path) as analyzer:
        analyzer.analyze(print_output=True)
