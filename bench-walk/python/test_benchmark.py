"""Standalone checks: no omitnix imports, report generation, or product test suite."""

import unittest
from pathlib import Path
from unittest.mock import patch

import benchmark


class WalkTests(unittest.TestCase):
    def test_exact_synthetic_counts(self):
        for label, candidates, expected in benchmark.synthetic_cases():
            with self.subTest(case=label):
                self.assertEqual(len(candidates), expected[0])
                self.assertEqual(benchmark.walk(candidates), expected[1:])

    def test_front_to_back_order_and_early_break(self):
        candidates = [(0, 10), (20, 30), (40, 50), (1, 2)]
        # 0 + 1 + 2 + 1. A reverse scan would incorrectly give 6 comparisons.
        self.assertEqual(benchmark.walk(candidates), (4, 3))

    def test_sort_starts_ascending_ends_descending(self):
        self.assertEqual(benchmark.prepare([(3, 4), (1, 2), (1, 8)]), [(1, 8), (1, 2), (3, 4)])

    def test_equal_bounds_are_contained(self):
        self.assertEqual(benchmark.walk([(0, 1), (0, 1)]), (1, 1))

    def test_empty_input(self):
        self.assertEqual(benchmark.walk([]), (0, 0))

    def test_measure_warms_once_then_runs_five_times(self):
        with patch.object(benchmark, "walk", wraps=benchmark.walk) as mocked:
            self.assertGreaterEqual(benchmark.measure([[(0, 1)]], (0, 1))[2], 0)
            self.assertEqual(mocked.call_count, 6)

    def test_measure_resets_accepted_per_file(self):
        self.assertGreaterEqual(benchmark.measure([[(0, 1)], [(0, 1)]], (0, 2))[2], 0)

    def test_bad_expected_counter_is_rejected(self):
        with self.assertRaises(AssertionError):
            benchmark.measure([[(0, 1)]], (1, 1))


class ParseCorpusTests(unittest.TestCase):
    def test_fixed_commit_coverage_and_counters(self):
        try:
            batches = benchmark.parse_batches(Path(__file__).resolve().parents[2])
        except benchmark.BindingUnavailable as exc:
            self.skipTest(str(exc))
        self.assertEqual(len(batches), 110)
        self.assertEqual(sum(map(len, batches)), 4104)
        results = [benchmark.walk(candidates) for candidates in batches]
        self.assertEqual(sum(item[0] for item in results), 334231)
        self.assertEqual(sum(item[1] for item in results), 3881)


if __name__ == "__main__":
    unittest.main()
