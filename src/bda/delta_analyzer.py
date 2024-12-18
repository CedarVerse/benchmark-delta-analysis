#!/usr/bin/env python
"""
This script compares two benchmark run dir and analyzes the changes in test performance.
It categorizes tests as improved, worsened, stable, or present in only one of the benchmark runs.
"""
from dataclasses import dataclass
import os
import subprocess
from collections import Counter
from functools import total_ordering
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import NamedTuple, Union

from datetime import timedelta
import sys
from dotenv import load_dotenv

if __name__ == "__main__":
    sys.path.append(str(Path(__file__).parent.parent))
from .benchmark_analyzer import BenchmarkAnalyzer


def _get_visual_indicator(percent_change: float | None) -> str:
    """Generate a visual indicator string based on percentage change."""
    if percent_change is None:
        return ""
    if percent_change == 0:
        return ""
    # Convert to absolute value to determine length, but keep sign for direction
    abs_change = abs(percent_change)
    indicator_length = min(20, max(1, int(abs_change / 10)))  # 1 char per 10% change, max 20
    return " " + ("+" if percent_change > 0 else "-") * indicator_length

def _get_token_change_indicators(test_1: 'AiderTestResult', test_2: 'AiderTestResult') -> tuple[str, str]:
    """Generate visual indicators for token changes between two test runs.

    Returns:
        tuple containing:
            - Left-aligned received tokens indicator in parentheses
            - Right-aligned sent tokens indicator in parentheses
    """
    sent_change = ((test_2.sent_tokens - test_1.sent_tokens) * 100 / test_1.sent_tokens) if test_1.sent_tokens else 0
    recv_change = ((test_2.received_tokens - test_1.received_tokens) * 100 / test_1.received_tokens) if test_1.received_tokens else 0

    # Generate the indicators (about 5% change per character, so 20 chars = ~100% change)
    sent_indicator = "+" * min(20, max(1, int(abs(sent_change) / 5)))
    recv_indicator = "-" * min(20, max(1, int(abs(recv_change) / 5)))

    # Right-align received tokens indicator (pad left with spaces)
    recv_col = f"({recv_indicator:>20})"

    # Left-align sent tokens indicator (pad right with spaces)
    sent_col = f"({sent_indicator:<20})"

    return recv_col, sent_col  # received tokens first, then sent tokens


@dataclass
class StatusPrinter:
    test_count: int

    def __call__(self, prefix: str, count: int, indent: str = "", suffix: str = "") -> None:
        """Print a status line with consistent formatting."""
        if count == 0:
            return
        current_percent = count * 100 / self.test_count
        print(f"{indent}{prefix}: {count:3d} ({current_percent:3.0f}%){_get_visual_indicator(current_percent)}{suffix}")


def main(run1path: Traversable, run2path: Traversable):
    """
    Main function to compare two benchmark runs and print the analysis.

    Args:
    benchmark1 (Traversable): Path to the first benchmark run.
    benchmark2 (Traversable): Path to the second benchmark run.

    This function parses both benchmark runs, compares them, and prints a detailed analysis
    of how tests have changed between the two runs. It categorizes tests as improved,
    worsened, stable, or present in only one run, and provides a summary count for each category and sub-category.
    """
    print(f"--- {run1path.name}")
    print(f"+++ {run2path.name}")
    print("# ============= Failed Attempts per Test =============")
    print("# N >= 0: It eventually passed after N failed attempts")
    print("# N < 0 : All attempts failed and the limit was reached")
    benchmark_run_1 = {t.name: t for t in parse_benchmark_source(run1path)}
    benchmark_run_2 = {t.name: t for t in parse_benchmark_source(run2path)}

    (
        test_names_only_1, test_names_only_2, test_names_improved, test_names_worsened, test_names_stable
    ) = compare_benchmark_runs(benchmark_run_1, benchmark_run_2)

    test_names_only_1_passed = [t for t in test_names_only_1 if benchmark_run_1[t].failed_attempt_count >= 0]
    if test_names_only_1_passed:
        print()
        print(f"@@ REMOVED ({len(test_names_only_1_passed)} PASSED) @@")
        for test_name in test_names_only_1_passed:
            failed_attempt_count = benchmark_run_1[test_name].failed_attempt_count
            print(f"<{'-' if failed_attempt_count < 0 else '+'}{test_name}: {failed_attempt_count}")

    test_names_only_1_failed = [t for t in test_names_only_1 if benchmark_run_1[t].failed_attempt_count < 0]
    if test_names_only_1_failed:
        print()
        print(f"@@ REMOVED ({len(test_names_only_1_failed)} FAILED) @@")
        for test_name in test_names_only_1_failed:
            failed_attempt_count = benchmark_run_1[test_name].failed_attempt_count
            print(f"<{'-' if failed_attempt_count < 0 else '+'}{test_name}: {failed_attempt_count}")

    test_names_only_2_passed = [t for t in test_names_only_2 if benchmark_run_2[t].failed_attempt_count >= 0]
    if test_names_only_2_passed:
        print()
        print(f"@@ NEW ({len(test_names_only_2_passed)} PASSED) @@")
        for test_name in test_names_only_2_passed:
            failed_attempt_count = benchmark_run_2[test_name].failed_attempt_count
            print(f">{'-' if failed_attempt_count < 0 else '+'}{test_name}: {failed_attempt_count}")

    test_names_only_2_failed = [t for t in test_names_only_2 if benchmark_run_2[t].failed_attempt_count < 0]
    if test_names_only_2_failed:
        print()
        print(f"@@ NEW ({len(test_names_only_2_failed)} FAILED) @@")
        for test_name in test_names_only_2_failed:
            failed_attempt_count = benchmark_run_2[test_name].failed_attempt_count
            print(f">{'-' if failed_attempt_count < 0 else '+'}{test_name}: {failed_attempt_count}")

    test_names_improved_now_passes = [t for t in test_names_improved if benchmark_run_1[t].failed_attempt_count < 0]
    now_passed_count = len(test_names_improved_now_passes)
    if test_names_improved_now_passes:
        print()
        print(f"@@ Improved, now PASSED ({now_passed_count}) @@")
        print_test_line('++', test_names_improved_now_passes, benchmark_run_1, benchmark_run_2)

    test_names_improved_minor = [t for t in test_names_improved if benchmark_run_1[t].failed_attempt_count >= 0]
    if test_names_improved_minor:
        print()
        print(f"@@ Improved, minor ({len(test_names_improved_minor)}) @@")
        print_test_line('+', test_names_improved_minor, benchmark_run_1, benchmark_run_2)

    test_names_worsened_now_fails = [t for t in test_names_worsened if benchmark_run_2[t].failed_attempt_count < 0]
    now_failed_count = len(test_names_worsened_now_fails)
    if test_names_worsened_now_fails:
        print()
        print(f"@@ Worsened, now FAILED ({now_failed_count}) @@")
        print_test_line('--', test_names_worsened_now_fails, benchmark_run_1, benchmark_run_2)

    test_names_worsened_minor = [t for t in test_names_worsened if benchmark_run_2[t].failed_attempt_count >= 0]
    if test_names_worsened_minor:
        print()
        print(f"@@ Worsened, still PASSED ({len(test_names_worsened_minor)}) @@")
        print_test_line('-', test_names_worsened_minor, benchmark_run_1, benchmark_run_2)

    test_names_stable_passed = [t for t in test_names_stable if benchmark_run_1[t].failed_attempt_count >= 0]
    if test_names_stable_passed:
        print()
        print(f"@@ Stable: PASSED ({len(test_names_stable_passed)}) @@")
        print_test_line('=+', test_names_stable_passed, benchmark_run_1, benchmark_run_2)

    test_names_stable_failed = [t for t in test_names_stable if benchmark_run_1[t].failed_attempt_count < 0]
    if test_names_stable_failed:
        print()
        print(f"@@ Stable: FAILED ({len(test_names_stable_failed)}) @@")
        print_test_line('=-', test_names_stable_failed, benchmark_run_1, benchmark_run_2)

    print()
    print(f"--- {run1path.name}")
    print(f"+++ {run2path.name}")
    printer = StatusPrinter(len(benchmark_run_2))
    printer(
        "@@ NPNF-Delta ",
        now_passed_count - now_failed_count,
        suffix=" @@"
    )
    if now_passed_count - now_failed_count == 0:
        print("@@ NPNF-Delta :   0 ( Both are equivalent ) @@")
    print("@@ ============= TEST STATUS CHANGES ============ @@")
    if test_names_only_1:
        printer("< REMOVED     ", len(test_names_only_1))
        printer("< +       PASS", len(test_names_only_1_passed))
        printer("< -       FAIL", len(test_names_only_1_failed))
    if test_names_only_2:
        printer("> NEW         ", len(test_names_only_2))
        printer("> +       PASS", len(test_names_only_2_passed))
        printer("> -       FAIL", len(test_names_only_2_failed))
    if test_names_stable:
        printer("# STABLE      ", len(test_names_stable))
        printer("#+        PASS", len(test_names_stable_passed))
        printer("#-        FAIL", len(test_names_stable_failed))
    if test_names_improved:
        printer("+ IMPROVED    ", len(test_names_improved))
        printer("++    Now PASS", now_passed_count)
        printer("+        Minor", len(test_names_improved_minor))
    if test_names_worsened:
        printer("- WORSENED    ", len(test_names_worsened))
        printer("--    Now FAIL", now_failed_count)
        printer("-        Minor", len(test_names_worsened_minor))

    test_count_delta = len(benchmark_run_2) - len(benchmark_run_1)
    # Calculate totals for each run
    sent_tokens_1 = sum(t.sent_tokens for t in benchmark_run_1.values())
    received_tokens_1 = sum(t.received_tokens for t in benchmark_run_1.values())
    duration_1 = sum(t.duration for t in benchmark_run_1.values())
    sent_tokens_2 = sum(t.sent_tokens for t in benchmark_run_2.values())
    received_tokens_2 = sum(t.received_tokens for t in benchmark_run_2.values())
    cost_1 = sum(t.cost for t in benchmark_run_1.values())
    cost_2 = sum(t.cost for t in benchmark_run_2.values())
    timeouts_1 = sum(t.timeouts for t in benchmark_run_1.values())
    timeouts_2 = sum(t.timeouts for t in benchmark_run_2.values())
    error_outputs_1 = sum(t.error_output_count for t in benchmark_run_1.values())
    error_outputs_2 = sum(t.error_output_count for t in benchmark_run_2.values())
    user_asks_1 = sum(t.user_ask_count for t in benchmark_run_1.values())
    user_asks_2 = sum(t.user_ask_count for t in benchmark_run_2.values())
    context_exhausts_1 = sum(t.exhausted_context_window_count for t in benchmark_run_1.values())
    context_exhausts_2 = sum(t.exhausted_context_window_count for t in benchmark_run_2.values())
    malformed_1 = sum(t.malformed_responses for t in benchmark_run_1.values())
    malformed_2 = sum(t.malformed_responses for t in benchmark_run_2.values())
    syntax_errors_1 = sum(t.syntax_errors for t in benchmark_run_1.values())
    syntax_errors_2 = sum(t.syntax_errors for t in benchmark_run_2.values())
    indent_errors_1 = sum(t.indentation_errors for t in benchmark_run_1.values())
    indent_errors_2 = sum(t.indentation_errors for t in benchmark_run_2.values())
    lazy_comments_1 = sum(t.lazy_comments for t in benchmark_run_1.values())
    lazy_comments_2 = sum(t.lazy_comments for t in benchmark_run_2.values())
    cedarscript_errors_1 = sum(t.cedarscript_errors for t in benchmark_run_1.values())
    cedarscript_errors_2 = sum(t.cedarscript_errors for t in benchmark_run_2.values())
    duration_2 = sum(t.duration for t in benchmark_run_2.values())

    max_failed_attempt_1, attempt_counts_1 = _get_attempt_limit_and_normalized_counts(benchmark_run_1)
    max_failed_attempt_2, attempt_counts_2 = _get_attempt_limit_and_normalized_counts(benchmark_run_2)

    print()
    print("@@ ============ Success Distribution =========== @@")
    all_attempt_counts = sorted(set(attempt_counts_1.keys()) | set(attempt_counts_2.keys()))
    for attempt_count in all_attempt_counts:
        count_1 = attempt_counts_1.get(attempt_count, 0)
        count_2 = attempt_counts_2.get(attempt_count, 0)
        if count_1 == 0 and count_2 == 0:
            continue
        count_diff = count_2 - count_1
        percent_change = (count_diff * 100 / count_1) if count_1 else None
        if attempt_count < 0:
            prefix = f"#              FAIL"
        else:
            prefix = f"#          Pass {attempt_count+1:3d}"

        print(f"{prefix}: {count_2:10d} {f'({count_diff:+10d}, {percent_change:+4.0f}%){_get_visual_indicator(percent_change)}' if count_1 else 'N/A'}")

    # TODO Print model and edit_format for each run (just take the first value)
    # Get model and edit format from first test in each run (they should be the same for all tests in a run)
    model_1 = next(iter(benchmark_run_1.values())).model if benchmark_run_1 else "N/A"
    model_2 = next(iter(benchmark_run_2.values())).model if benchmark_run_2 else "N/A"
    edit_format_1 = next(iter(benchmark_run_1.values())).edit_format if benchmark_run_1 else "N/A"
    edit_format_2 = next(iter(benchmark_run_2.values())).edit_format if benchmark_run_2 else "N/A"
    print("@@ ================== METRICS  ================= @@")
    print(f"# MODEL            : {model_2.split('/')[-1]:>10} {'(was ' + model_1.split('/')[-1] + ')' if model_1 != model_2 else ''}")
    print(f"# EDIT FORMAT      : {edit_format_2:>10} {'(was ' + edit_format_1 + ')' if edit_format_1 != edit_format_2 else ''}")
    print(f"# TOTAL TEST COUNT : {len(benchmark_run_2):10d} {f'({test_count_delta:+10d}, {test_count_delta*100/len(benchmark_run_1):+4.0f}%){_get_visual_indicator(test_count_delta*100/len(benchmark_run_1) if test_count_delta else None)}' if test_count_delta else ''}")
    print(f"# Max attempt count: {max_failed_attempt_2:10d}{f" ({max_failed_attempt_2 - max_failed_attempt_1:+d})" if max_failed_attempt_2 != max_failed_attempt_1 else ""}")
    print(f"# DURATION hh:mm:ss:    {str(timedelta(seconds=int(duration_2)))} ({'-' if duration_2 < duration_1 else '+'}  {str(timedelta(seconds=int(abs(duration_2 - duration_1))))}, {(duration_2 - duration_1)*100/duration_1:+4.0f}%){_get_visual_indicator((duration_2 - duration_1)*100/duration_1)}")
    print(f"# COST ($)         : {cost_2:10,.2f} {f'({cost_2 - cost_1:+10,.2f}, {(cost_2 - cost_1)*100/cost_1:+4.0f}%){_get_visual_indicator((cost_2 - cost_1)*100/cost_1)}' if cost_1 else 'N/A'}")
    print(f"# TOKENS SENT      : {sent_tokens_2:10,} ({sent_tokens_2 - sent_tokens_1:+10,}, {(sent_tokens_2 - sent_tokens_1)*100/sent_tokens_1:+4.0f}%){_get_visual_indicator((sent_tokens_2 - sent_tokens_1)*100/sent_tokens_1)}")
    print(f"# TOKENS RECEIVED  : {received_tokens_2:10,} ({received_tokens_2 - received_tokens_1:+10,}, {(received_tokens_2 - received_tokens_1)*100/received_tokens_1:+4.0f}%){_get_visual_indicator((received_tokens_2 - received_tokens_1)*100/received_tokens_1)}")
    print_metric_diff("CEDARSCRIPT ERR. ", cedarscript_errors_1, cedarscript_errors_2)
    print_metric_diff("ERROR OUTPUTS    ", error_outputs_1, error_outputs_2)
    print_metric_diff("MALFORMED        ", malformed_1, malformed_2)
    print_metric_diff("SYNTAX ERRORS    ", syntax_errors_1, syntax_errors_2)
    print_metric_diff("INDENT ERRORS    ", indent_errors_1, indent_errors_2)
    print_metric_diff("LAZY COMMENTS    ", lazy_comments_1, lazy_comments_2)
    print_metric_diff("USER ASKS        ", user_asks_1, user_asks_2)
    print_metric_diff("CONTEXT EXHAUSTS ", context_exhausts_1, context_exhausts_2)
    print_metric_diff("TIMEOUTS         ", timeouts_1, timeouts_2)


def print_test_line(prefix: str, tests_names, benchmark_run_1, benchmark_run_2):
    for test_name in tests_names:
        failed_attempts_1 = benchmark_run_1[test_name].failed_attempt_count
        failed_attempts_2 = benchmark_run_2[test_name].failed_attempt_count
        failed_attempt_delta = "          " if failed_attempts_1 == 0 and failed_attempts_2 == 0 else f"[{failed_attempts_1:2} -> {failed_attempts_2:2}]"
        sent_ind, recv_ind = _get_token_change_indicators(benchmark_run_1[test_name], benchmark_run_2[test_name])
        word_count = benchmark_run_1[test_name].word_count
        cedarscript_errors_1 = benchmark_run_1[test_name].cedarscript_errors
        cedarscript_errors_2 = benchmark_run_2[test_name].cedarscript_errors
        cedarscript_delta = cedarscript_errors_2 - cedarscript_errors_1
        cedarscript_delta = f"[{cedarscript_delta:+3d}]" if cedarscript_delta else "     "
        print(
            f"{prefix} {failed_attempt_delta} {sent_ind} {recv_ind} "
            f"{cedarscript_delta} {word_count:5d} {test_name}")


def print_metric_diff(metric_name, value_run_1, value_run_2):
    print(
        f"# {metric_name}: {value_run_2:10d} {f"({value_run_2 - value_run_1:+10d}, {(value_run_2 - value_run_1) * 100 / value_run_1:+4.0f}%){_get_visual_indicator((value_run_2 - value_run_1) * 100 / value_run_1 if value_run_1 else None)}" if value_run_1 else 'N/A'}")


@total_ordering
class AiderTestResult(NamedTuple):
    """
    Represents the result of a benchmark test that may require multiple attempts to pass.

    This class tracks various metrics about test execution and provides normalized comparison
    of test results based on the number of failed attempts. The comparison logic treats all
    negative failed_attempt_count values (representing tests that hit max attempts) as equal,
    and considers them worse than any successful test (zero or positive failed_attempt_count).
    """

    failed_attempt_count: int
    word_count: int = 0
    name: str = ''
    duration: float = 0
    sent_tokens: int = 0
    received_tokens: int = 0
    model: str = ''
    edit_format: str = ''
    cost: float = 0
    timeouts: int = 0
    error_output_count: int = 0
    user_ask_count: int = 0
    exhausted_context_window_count: int = 0
    malformed_responses: int = 0
    syntax_errors: int = 0
    indentation_errors: int = 0
    lazy_comments: int = 0
    cedarscript_errors: int = 0

    def __int__(self) -> int:
        """
        Returns the raw failed_attempt_count value.

        A positive value indicates the number of failed attempts before success.
        Zero indicates success on first try.
        A negative value indicates the test never succeeded (hit max attempts).
        """
        return self.failed_attempt_count

    @property
    def norm_failed_attempts(self) -> int:
        """
        Returns a normalized version of failed_attempt_count for comparison purposes.

        All negative values are normalized to -1 since they represent the same state
        (test never passed within max attempts). Zero and positive values remain unchanged.

        Returns:
            int: -1 if failed_attempt_count is negative, otherwise the actual failed_attempt_count
        """
        return self._normalize_attempts(self.failed_attempt_count)

    @staticmethod
    def _normalize_attempts(value: int) -> int:
        """
        Normalizes the failed attempts count by converting all negative values to -1.

        Args:
            value: The raw failed attempts count

        Returns:
            int: -1 if value is negative, otherwise the original value
        """
        return -1 if value < 0 else value

    def __eq__(self, other: Union['AiderTestResult', int]) -> bool:
        """
        Compares this result with another result or an integer.

        Uses normalized failed attempts count where all negative values are treated as equal.
        Can compare against either another AiderTestResult instance or an integer.

        Args:
            other: Another AiderTestResult instance or an integer to compare with

        Returns:
            bool: True if the normalized failed attempts are equal, False otherwise
        """
        if isinstance(other, (int, AiderTestResult)):
            other_val = other.norm_failed_attempts if isinstance(other, AiderTestResult) else self._normalize_attempts(other)
            return self.norm_failed_attempts == other_val
        return False

    def __lt__(self, other: Union['AiderTestResult', int]) -> bool:
        """
        Determines if this result is "less than" another result or integer.

        Uses normalized failed attempts count where all negative values are treated as equal.
        A result with fewer failed attempts is considered "less than" one with more attempts.
        Any successful test (>= 0) is considered "less than" any failed test (< 0).

        Args:
            other: Another AiderTestResult instance or an integer to compare with

        Returns:
            bool: True if this result should be considered better than the other, False otherwise
        """
        if not isinstance(other, (int, AiderTestResult)):
            return NotImplemented

        other_val = other.norm_failed_attempts if isinstance(other, AiderTestResult) else self._normalize_attempts(other)
        self_val = self.norm_failed_attempts

        # If one is negative and the other isn't, the non-negative is "less than" (better)
        if (self_val < 0) != (other_val < 0):
            return self_val >= 0

        # Otherwise, normal comparison (works for both-negative and both-non-negative cases)
        return self_val < other_val

    # ATTENTION: __gt__ should not be required, but if not provided, the superclass method will be called,
    # causing incorrect comparisons.
    def __gt__(self, other: Union['AiderTestResult', int]) -> bool:
        if isinstance(other, (int, AiderTestResult)):
            return other < self
        return NotImplemented

def _get_attempt_limit_and_normalized_counts(benchmark_run: dict[str, AiderTestResult]) -> tuple[int | None, Counter]:
    result = Counter([t.failed_attempt_count for t in benchmark_run.values()])
    """
    Process and normalize the failed attempt counts from a benchmark run.

    Args:
    benchmark_run (dict[str, AiderTestResult]): Dictionary mapping test names to their results

    Returns:
    tuple[int | None, Counter]: A tuple containing:
    - The absolute value of the failure limit (if any tests hit it), or None
    - A Counter object containing:
    * Counts of tests with 0 or more failed attempts (these eventually passed)
    * Count of tests with -1 failed attempts (these never passed, hitting the failure limit)
    Note: All tests that hit the failure limit are normalized to count -1,
    regardless of the actual negative value used in the input
    """
    # Find the negative value (if any) and its count
    negative_value = next((k for k in result.keys() if k < 0), None)
    if negative_value is None:
        return 0, result
    # Get the count of tests with this negative value
    max_failed_attempts = result[negative_value]
    # Remove the original negative value from counter
    del result[negative_value]
    # Add the count to -1 in the counter
    result[-1] = max_failed_attempts
    return abs(negative_value), result


def parse_benchmark_source(benchmark_path: Traversable) -> list[AiderTestResult]:
    """
    Parse a benchmark run dir and extract test results.

    Args:
    benchmark_dir (Traversable): Path to the benchmark run dir.

    Returns:
    List[AiderTestResult]: A list of test results
    """
    with BenchmarkAnalyzer(benchmark_path) as analyzer:
        benchmark_results = analyzer.analyze(print_output=False)

    results = []
    for result_dict in benchmark_results.test_stats:
        # Convert the dictionary to match AiderTestResult format
        test_result = AiderTestResult(
            failed_attempt_count=result_dict['attempts'],
            word_count=result_dict['words'],
            name=result_dict['dir_name'],
            duration=result_dict['duration'],
            sent_tokens=result_dict['sent_tokens'],
            received_tokens=result_dict['received_tokens'],
            model=result_dict['model'],
            edit_format=result_dict['edit_format'],
            cost=result_dict['cost'],
            timeouts=result_dict['timeouts'],
            error_output_count=result_dict['error_outputs'],
            user_ask_count=result_dict['user_asks'],
            exhausted_context_window_count=result_dict['exhausted_context_windows'],
            malformed_responses=result_dict['malformed_responses'],
            syntax_errors=result_dict['syntax_errors'],
            indentation_errors=result_dict['indentation_errors'],
            lazy_comments=result_dict['lazy_comments'],
            cedarscript_errors=result_dict['cedarscript_errors']
        )
        results.append(test_result)

    return results


def compare_benchmark_runs(benchmark_run_1: dict[str, AiderTestResult], benchmark_run_2: dict[str, AiderTestResult]) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """
    Compare two benchmark run dirs and categorize the changes.

    Args:
    benchmark_run_1 (dict[str, AiderTestResult]): First test result from first benchmark run, where keys are test names.
    benchmark_run_2 (dict[str, AiderTestResult]): Second test result from first benchmark run, in the same format as above.

    Returns:
    tuple[list[str], list[str], list[str], list[str], list[str]]: A tuple containing lists of:
        - tests only in benchmark_run_1
        - tests only in benchmark_run_2
        - improved tests
        - worsened tests
        - stable tests

    Tests are categorized based on their presence in the runs and changes in failed attempt counts.
    Negative failed run counts indicate the limit of failed attempts was reached and the test didn't pass.
    """
    only_1 = []
    only_2 = []
    improved = []
    worsened = []
    stable = []

    all_test_names = set(benchmark_run_1.keys()) | set(benchmark_run_2.keys())

    for test_name in sorted(all_test_names):
        test_from_run_1 = benchmark_run_1.get(test_name)
        test_from_run_2 = benchmark_run_2.get(test_name)

        if test_from_run_1 is None:
            only_2.append(test_name)
            continue
        if test_from_run_2 is None:
            only_1.append(test_name)
            continue
        if test_from_run_1 == test_from_run_2:
            stable.append(test_name)
            continue
        if test_from_run_2 < test_from_run_1:
            improved.append(test_name)
            continue
        worsened.append(test_name)

    return only_1, only_2, improved, worsened, stable


if __name__ == "__main__":
    load_dotenv(verbose=True)

    match len(sys.argv):
        case 3:
            benchmark1 = sys.argv[1]
            benchmark2 = sys.argv[2]
        case 2:
            benchmark1 = 'perfect'
            benchmark2 = sys.argv[1]
        case 1:
            benchmark1 = os.getenv('benchmark1')
            benchmark2 = os.getenv('benchmark2')
            if not benchmark2:
                benchmark2 = benchmark1
                benchmark1 = 'perfect'

    if not benchmark1 or not benchmark2:
        print(f"Usage: {sys.argv[0]} [benchmark-root-1] [benchmark-root-2]")
        print(f"Usage: benchmark1='<benchmark-root-1>' benchmark2='<benchmark-root-2>' {sys.argv[0]}")
        sys.exit(1)

    main(benchmark1, benchmark2)
