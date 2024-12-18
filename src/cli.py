from importlib.resources.abc import Traversable

from version import __version__
import argparse
import sys
import os
from pathlib import Path

def show_dashboard(run1: Traversable, run2: Traversable, port: int = 8050):
    from bda import app, create_dashboard
    create_dashboard(run1, run2, port=port)
    app.run(debug=True)

def show_info(run: Path):
    from bda import show_info
    show_info(run)

def show_delta(run1: Path, run2: Path):
    from bda import show_delta
    show_delta(run1, run2)

def create_parser():
    parser = argparse.ArgumentParser(
        description="Analyze and compare Aider benchmark runs"
    )

    # Create mutually exclusive group for modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dashboard",
        action="store_true",
        help="Launch interactive web dashboard"
    )
    mode_group.add_argument(
        "--info",
        action="store_true",
        help="Show information about a single run"
    )

    # Optional benchmark arguments - we'll handle defaults ourselves
    parser.add_argument(
        "benchmarks",
        nargs="*",
        type=str,
        help="Benchmark run(s) to analyze. Can point to a folder or a tar-bzip2 archive; Can be specified via environment variables benchmark1 and benchmark2"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8050,
        help="Port for dashboard web server (default: 8050)"
    )

    return parser

def main():
    parser = create_parser()
    from util.cli_kit import get_benchmark_args
    mode, benchmark1, benchmark2, port = get_benchmark_args(parser)

    if not benchmark1 or not benchmark2 and mode != 'info':
        parser.error(
            "Benchmarks must be specified either as arguments or via environment variables:\n"
            f"  bda [benchmark-root-1] [benchmark-root-2]\n"
            f"  benchmark1='<benchmark-root-1>' benchmark2='<benchmark-root-2>' bda"
        )

    match mode:
        case 'info':
            show_info(Path(benchmark1))
        case 'dashboard':
            show_dashboard(Path(benchmark1), Path(benchmark2), port)
        case _:  # delta mode
            show_delta(Path(benchmark1), Path(benchmark2))

    return 0

if __name__ == "__main__":
    sys.exit(main())
