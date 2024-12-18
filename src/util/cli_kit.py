from dotenv import load_dotenv
import os

def get_benchmark_args(parser):
    load_dotenv(verbose=True)
    args = parser.parse_args()

    if args.info:
        if len(args.benchmarks) != 1:
            parser.error("--info requires exactly one benchmark")
        return 'info', args.benchmarks[0], None

    # Handle benchmark arguments
    match len(args.benchmarks):
        case 2:
            b1, b2 = args.benchmarks
        case 1:
            b1, b2 = 'perfect', args.benchmarks[0]
        case 0:
            b1 = os.getenv('benchmark1')
            b2 = os.getenv('benchmark2')
            if not b2:
                b2 = b1
                b1 = 'perfect'
        case _:
            parser.error("Too many benchmark arguments")

    mode = 'dashboard' if args.dashboard else 'delta'
    return mode, b1, b2, args.port

