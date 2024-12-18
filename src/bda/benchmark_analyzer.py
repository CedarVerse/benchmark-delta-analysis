#!/usr/bin/env python
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
import re
from importlib.resources.abc import Traversable
from os import getenv
from pathlib import Path
from dataclasses import dataclass

from bda.file_kit import find_files, find_aider_results
from dotenv import load_dotenv
import tarfile
import tempfile


@dataclass
class BenchmarkResult:
    duration: float
    success_rate: float
    total_tests: int
    passed_tests: int
    failed_tests: int
    failed_attempts: int
    total_sent_tokens: int
    total_received_tokens: int
    total_cost: float
    total_test_timeouts: int
    total_num_error_outputs: int
    total_num_user_asks: int
    total_num_exhausted_context_windows: int
    total_num_malformed_responses: int
    total_syntax_errors: int
    total_indentation_errors: int
    total_lazy_comments: int
    total_cedarscript_errors: int
    total_word_count: int
    test_stats: list[dict]


def archive2dir(archive_path: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="benchmark-", delete=False) as temp_dir:
        try:
            with tarfile.open(archive_path, 'r:bz2') as tar:
                tar.extractall(path=temp_dir)
            # Update benchmark_run_path to point to extracted contents
            extracted_contents = list(Path(temp_dir).iterdir())
            if len(extracted_contents) == 1 and extracted_contents[0].is_dir():
                return  extracted_contents[0]
            return Path(temp_dir)
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to extract archive: {e}")


class BenchmarkAnalyzer:
    def __init__(self, benchmark_run_path: Traversable):
        load_dotenv(verbose=True)
        self.must_delete_benchmark_dir = False
        self.is_perfect_run = str(benchmark_run_path) == 'perfect'
        if self.is_perfect_run:
            return

        self.benchmark_run_path = benchmark_run_path
        match self.benchmark_run_path:
            case Path() as path if not path.is_absolute():
                benchmark_root = getenv('benchmark_root')
            case _: benchmark_root = None

        if benchmark_root:
            benchmark_root = Path(benchmark_root)
            if not benchmark_root.is_absolute():
                benchmark_root = Path.cwd() / benchmark_root

            self.benchmark_run_path = benchmark_root / self.benchmark_run_path

        if isinstance(self.benchmark_run_path, Path) and not self.benchmark_run_path.exists():
            raise FileNotFoundError(f"Benchmark not found: {self.benchmark_run_path}")

    def __enter__(self) -> 'BenchmarkAnalyzer':
        # Support usage as a context manager
        # Determine if the path is a directory or an archive
        if not self.benchmark_run_path.is_dir():
            # Assume it's a tar.bz2 archive
            self.benchmark_run_path = archive2dir(self.benchmark_run_path)
            self.must_delete_benchmark_dir = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()

    def __del__(self) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        """Cleanup temporary directory if it exists"""
        if self.must_delete_benchmark_dir and  self.benchmark_run_path:
            shutil.rmtree(self.benchmark_run_path, ignore_errors=True)

    @staticmethod
    def create_perfect_result() -> BenchmarkResult:
        """Create an idealized perfect benchmark result."""
        return BenchmarkResult(
            duration=1.0,
            success_rate=100.0,
            total_tests=1,  # At least one test to avoid division by zero
            passed_tests=1,
            failed_tests=0,
            failed_attempts=0,
            total_sent_tokens=1,
            total_received_tokens=1,
            total_cost=0.0,
            total_test_timeouts=0,
            total_num_error_outputs=0,
            total_num_user_asks=0,
            total_num_exhausted_context_windows=0,
            total_num_malformed_responses=0,
            total_syntax_errors=0,
            total_indentation_errors=0,
            total_lazy_comments=0,
            total_cedarscript_errors=0,
            total_word_count=0,
            test_stats=[{
                'attempts': 0,
                'dir_name': 'perfect',
                'duration': 1.0,
                'sent_tokens': 1,
                'received_tokens': 1,
                'model': 'perfect',
                'edit_format': 'perfect',
                'cost': 0.0,
                'timeouts': 0,
                'error_outputs': 0,
                'user_asks': 0,
                'exhausted_context_windows': 0,
                'malformed_responses': 0,
                'syntax_errors': 0,
                'indentation_errors': 0,
                'lazy_comments': 0,
                'cedarscript_errors': 0,
                'words': 0
            }]
        )

    @staticmethod
    def aider_results_to_cols(json_file: Path) -> tuple:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return (data['model'], data['edit_format'], data['cost'],
                data['duration'], data['test_timeouts'], data['num_error_outputs'],
                data['num_user_asks'], data['num_exhausted_context_windows'],
                data['num_malformed_responses'], data['syntax_errors'],
                data['indentation_errors'], data['lazy_comments'])

    @staticmethod
    def format_duration(seconds: float) -> str:
        return str(timedelta(seconds=int(seconds)))

    @staticmethod
    def extract_word_count(root: Path) -> int:
        whitespace_pattern = re.compile(r'\s+')
        word_count = 0
        chunk_size = 1024 * 1024  # 1MB chunks

        files = [f for f in root.glob("*.py") if not f.name.endswith("_test.py")]

        for file_path in files:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Process file in chunks for memory efficiency
                while chunk := f.read(chunk_size):
                    # Process non-empty lines
                    lines = filter(None, (line.strip() for line in chunk.splitlines()))

                    # Count words using pre-compiled regex
                    word_count += sum(len(whitespace_pattern.split(line)) for line in lines)

        return word_count

    @staticmethod
    def extract_chat_history_counts(file_path: Path) -> tuple[int, int, int]:
        total_sent = total_received = cedarscript_error_count = 0

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '> Tokens:' in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part.lower().startswith(('sent', 'sent,', 'sent.')):
                            sent = parts[i-1]
                            multiplier = 1000 if 'k' in sent.lower() else 1000000 if 'm' in sent.lower() else 1
                            sent = sent.lower().replace('k', '').replace('m', '')
                            try:
                                total_sent += float(sent) * multiplier
                            except ValueError:
                                continue

                        if part.lower().startswith(('received', 'received,', 'received.')):
                            received = parts[i-1]
                            multiplier = 1000 if 'k' in received.lower() else 1000000 if 'm' in received.lower() else 1
                            received = received.lower().replace('k', '').replace('m', '')
                            try:
                                total_received += float(received) * multiplier
                            except ValueError:
                                continue

                if '<error-location>COMMAND #' in line:
                    cedarscript_error_count += 1

        return int(total_sent), int(total_received), cedarscript_error_count

    def analyze(self, print_output: bool = False) -> BenchmarkResult | None:
        if self.is_perfect_run:
            result = self.create_perfect_result()
            if print_output:
                self._print_results(result)
            return result

        i = total_word_count = total_duration = total_failed_attempts = failed_test_count = 0
        total_sent_tokens = total_received_tokens = total_cost = 0
        total_test_timeouts = total_num_error_outputs = total_num_user_asks = 0
        total_num_exhausted_context_windows = total_num_malformed_responses = 0
        total_syntax_errors = total_indentation_errors = total_lazy_comments = 0
        total_cedarscript_errors = 0
        detailed_results = []

        if print_output:
            print(f"# -dirname {self.benchmark_run_path.name} tests")
            print('failed-attempts (negative if all attempts failed), words, test-name, duration, sent_tokens, received_tokens, '
                  'model, edit_format, cost, test_timeouts, num_error_outputs, num_user_asks, num_exhausted_context_windows, '
                  'num_malformed_responses, syntax_errors, indentation_errors, lazy_comments, cedarscript_errors')

        for aider_json_file in find_aider_results(self.benchmark_run_path):
            i += 1
            test_folder: Path = aider_json_file.parent
            chat_history_file: Path = (test_folder / '.aider.chat.history.md').absolute()
            if not chat_history_file.exists():
                if test_folder.exists():
                    print(f"[analyze] File '{chat_history_file.name}' not found in {test_folder}")
                else:
                    print(f"[analyze] Test folder '{test_folder.name}' not found in {test_folder.parent}")
                return None
            word_count = self.extract_word_count(test_folder)
            total_word_count += word_count
            sent_tokens, received_tokens, test_cedarscript_errors = self.extract_chat_history_counts(chat_history_file)
            total_sent_tokens += sent_tokens
            total_received_tokens += received_tokens
            total_cedarscript_errors += test_cedarscript_errors

            with open(aider_json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                outcome = data['tests_outcomes']

            attempts = 0 if outcome == [True] else outcome.count(False)
            total_failed_attempts += attempts

            dir_name = test_folder.name
            if True not in outcome:
                attempts = -attempts
                failed_test_count += 1

            test_results = self.aider_results_to_cols(aider_json_file)
            (test_model, test_edit_format, test_cost, test_duration, test_timeouts,
             test_num_error_outputs, test_num_user_asks, test_num_exhausted_context_windows,
             test_num_malformed_responses, test_syntax_errors, test_indentation_errors,
             test_lazy_comments) = test_results

            # Update totals
            total_duration += float(test_duration)
            total_cost += float(test_cost)
            total_test_timeouts += test_timeouts
            total_num_error_outputs += test_num_error_outputs
            total_num_user_asks += test_num_user_asks
            total_num_exhausted_context_windows += test_num_exhausted_context_windows
            total_num_malformed_responses += test_num_malformed_responses
            total_syntax_errors += test_syntax_errors
            total_indentation_errors += test_indentation_errors
            total_lazy_comments += test_lazy_comments

            result_dict = {
                'attempts': attempts,
                'dir_name': dir_name,
                'duration': test_duration,
                'sent_tokens': sent_tokens,
                'received_tokens': received_tokens,
                'model': test_model,
                'edit_format': test_edit_format,
                'cost': test_cost,
                'timeouts': test_timeouts,
                'error_outputs': test_num_error_outputs,
                'user_asks': test_num_user_asks,
                'exhausted_context_windows': test_num_exhausted_context_windows,
                'malformed_responses': test_num_malformed_responses,
                'syntax_errors': test_syntax_errors,
                'indentation_errors': test_indentation_errors,
                'lazy_comments': test_lazy_comments,
                'cedarscript_errors': test_cedarscript_errors,
                'words': word_count
            }
            detailed_results.append(result_dict)

        success_rate = 100 * (i-failed_test_count) / i if i > 0 else 0

        result = BenchmarkResult(
            duration=total_duration,
            success_rate=success_rate,
            total_tests=i,
            passed_tests=i-failed_test_count,
            failed_tests=failed_test_count,
            failed_attempts=total_failed_attempts,
            total_sent_tokens=total_sent_tokens,
            total_received_tokens=total_received_tokens,
            total_cost=total_cost,
            total_test_timeouts=total_test_timeouts,
            total_num_error_outputs=total_num_error_outputs,
            total_num_user_asks=total_num_user_asks,
            total_num_exhausted_context_windows=total_num_exhausted_context_windows,
            total_num_malformed_responses=total_num_malformed_responses,
            total_syntax_errors=total_syntax_errors,
            total_indentation_errors=total_indentation_errors,
            total_lazy_comments=total_lazy_comments,
            total_cedarscript_errors=total_cedarscript_errors,
            total_word_count=total_word_count,
            test_stats=detailed_results
        )

        if print_output:
            self._print_results(result)

        return result

    def _print_results(self, result: BenchmarkResult):
        """Print formatted benchmark results."""
        print(f"# -dirname {self.benchmark_run_path.name if not self.is_perfect_run else 'perfect'} tests")
        print('failed-attempts (negative if all attempts failed), words, test-name, duration, sent_tokens, received_tokens, '
              'model, edit_format, cost, test_timeouts, num_error_outputs, num_user_asks, num_exhausted_context_windows, '
              'num_malformed_responses, syntax_errors, indentation_errors, lazy_comments, cedarscript_errors')

        for test in result.test_stats:
            print(
                f'{test["attempts"]:2d}, {test["words"]:5d}, {test["dir_name"]:25s}, {test["duration"]:7.3f}, '
                f'{test["sent_tokens"]:6d}, {test["received_tokens"]:07d}, '
                f'{test["model"]:25s}, {test["edit_format"]:25s}, {test["cost"]:0.3f}, '
                f'{test["timeouts"]:2d}, {test["error_outputs"]:2d}, {test["user_asks"]:2d}, '
                f'{test["exhausted_context_windows"]:2d}, {test["malformed_responses"]:2d}, '
                f'{test["syntax_errors"]:2d}, {test["indentation_errors"]:2d}, '
                f'{test["lazy_comments"]:2d}, {test["cedarscript_errors"]:2d}'
            )

        print('='*17)
        print(f'Words        : {result.total_word_count}')
        print(f'Duration     : {self.format_duration(result.duration)}')
        print(f'Success      : {result.success_rate:03.1f}% ( {result.passed_tests} / {result.total_tests} )')
        print('# duration_s, test_pass_count, test_failed_count, failed_attempts, total_sent_tokens, '
              'total_received_tokens, total_cost, total_test_timeouts, total_num_error_outputs, '
              'total_num_user_asks, total_num_exhausted_context_windows, total_num_malformed_responses, '
              'total_syntax_errors, total_indentation_errors, total_lazy_comments, total_cedarscript_errors, total_words')
        print(
            f'# {result.duration:03.3f}, {result.passed_tests:03d}, {result.failed_tests:03d}, '
            f'{result.failed_attempts:03d}, {result.total_sent_tokens:07d}, {result.total_received_tokens:07d}, '
            f'{result.total_cost:0.3f}, {result.total_test_timeouts:02d}, {result.total_num_error_outputs:02d}, '
            f'{result.total_num_user_asks:02d}, {result.total_num_exhausted_context_windows:02d}, '
            f'{result.total_num_malformed_responses:02d}, {result.total_syntax_errors:02d}, '
            f'{result.total_indentation_errors:02d}, {result.total_lazy_comments:02d}, '
            f'{result.total_cedarscript_errors:02d}, {result.total_word_count:02d}'
        )


def main():
    load_dotenv(verbose=True)
    match len(sys.argv):
        case 2:
            benchmark_path = sys.argv[1]
        case _:
            benchmark_path = getenv('benchmark_path')
    if not benchmark_path:
        print(f"Usage: {sys.argv[0]} [benchmark-path]")
        print(f"Usage: benchmark_path='<benchmark-path>' {sys.argv[0]}")
        sys.exit(1)

    with BenchmarkAnalyzer(benchmark_path) as analyzer:
        analyzer.analyze(print_output=True)


if __name__ == '__main__':
    main()
