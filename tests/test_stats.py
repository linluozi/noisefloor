import math
import unittest

from noisefloor.stats import (mannwhitney_u, median, normal_cdf, percentile,
                              quartiles, rsd, speedup_ci)


class TestPercentile(unittest.TestCase):
    def test_known_values(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        self.assertAlmostEqual(percentile(xs, 0), 1.0)
        self.assertAlmostEqual(percentile(xs, 25), 1.75)
        self.assertAlmostEqual(percentile(xs, 50), 2.5)
        self.assertAlmostEqual(percentile(xs, 75), 3.25)
        self.assertAlmostEqual(percentile(xs, 100), 4.0)

    def test_single(self):
        self.assertEqual(percentile([7.0], 90), 7.0)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            percentile([], 50)

    def test_median_and_quartiles(self):
        self.assertEqual(median([3, 1, 2]), 2.0)
        p25, med, p75 = quartiles([1, 2, 3, 4, 5])
        self.assertEqual((p25, med, p75), (2.0, 3.0, 4.0))


class TestRsd(unittest.TestCase):
    def test_constant(self):
        self.assertAlmostEqual(rsd([5, 5, 5, 5]), 0.0)

    def test_known(self):
        # sample stdev of [2,4,4,4,5,5,7,9] is 2.138..., mean 5
        self.assertAlmostEqual(rsd([2, 4, 4, 4, 5, 5, 7, 9]),
                               2.138089935299395 / 5.0, places=12)


class TestSpeedupCi(unittest.TestCase):
    def test_point_is_ratio_of_medians(self):
        a = [100, 102, 104, 106, 108]
        b = [50, 51, 52, 53, 54]
        ci = speedup_ci(a, b, n_boot=200, seed=7)
        self.assertAlmostEqual(ci["point"], 104 / 52, places=12)

    def test_deterministic(self):
        a = [100, 103, 97, 101, 99, 105, 98, 102]
        b = [88, 91, 86, 90, 89, 93, 87, 92]
        c1 = speedup_ci(a, b, n_boot=300, seed=11)
        c2 = speedup_ci(a, b, n_boot=300, seed=11)
        self.assertEqual(c1, c2)
        c3 = speedup_ci(a, b, n_boot=300, seed=12)
        self.assertNotEqual(c1["low"], c3["low"])

    def test_clear_shift_excludes_one(self):
        a = [1000, 1010, 990, 1005, 995, 1002, 998, 1008]
        b = [500, 505, 495, 502, 498, 501, 499, 504]
        ci = speedup_ci(a, b, n_boot=500, seed=3)
        self.assertGreater(ci["low"], 1.9)

    def test_basic_method_reflects(self):
        a = [100, 101, 102, 103, 104, 105, 106, 107]
        b = [98, 99, 100, 101, 102, 103, 104, 105]
        p = speedup_ci(a, b, n_boot=300, seed=5, method="percentile")
        q = speedup_ci(a, b, n_boot=300, seed=5, method="basic")
        self.assertAlmostEqual(q["low"], 2 * p["point"] - p["high"], places=12)
        self.assertAlmostEqual(q["high"], 2 * p["point"] - p["low"], places=12)

    def test_needs_two_samples(self):
        with self.assertRaises(ValueError):
            speedup_ci([1], [2, 3])


class TestMannWhitney(unittest.TestCase):
    def test_fully_separated(self):
        r = mannwhitney_u([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
        self.assertEqual(r["u"], 0.0)
        self.assertEqual(r["u1"], 0.0)
        self.assertLess(r["p"], 0.02)

    def test_identical_samples(self):
        r = mannwhitney_u([1, 2, 3], [1, 2, 3])
        self.assertAlmostEqual(r["p"], 1.0)
        self.assertAlmostEqual(r["z"], 0.0)

    def test_second_case_documented(self):
        r = mannwhitney_u([1, 2, 3, 4, 5], [1, 2, 3, 4, 6])
        # ties on four values; the single 6 keeps the statistic small but nonzero
        self.assertGreaterEqual(r["p"], 0.3)

    def test_normal_cdf(self):
        self.assertAlmostEqual(normal_cdf(0.0), 0.5, places=15)
        self.assertAlmostEqual(normal_cdf(1.959963984540054), 0.975, places=9)
        self.assertAlmostEqual(normal_cdf(-1.959963984540054), 0.025, places=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
