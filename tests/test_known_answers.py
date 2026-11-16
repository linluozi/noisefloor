"""Known-answer tests cross-checked by an independent reviewer.

The expected values below were produced by a separate pure-Python
implementation (midrank Mann-Whitney U, tie correction, continuity
correction) in an independent read-only review of this repository; they are
*not* copied from this package's own output.
"""

import unittest

from noisefloor.stats import mannwhitney_u, percentile, speedup_ci


class TestMannWhitneyKnownAnswers(unittest.TestCase):
    def test_separated_arms(self):
        r = mannwhitney_u([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
        self.assertEqual(r["u1"], 0.0)
        self.assertEqual(r["u"], 0.0)
        self.assertAlmostEqual(r["z"], -2.506718, places=5)
        self.assertAlmostEqual(r["p"], 0.01218578, places=7)

    def test_tied_arms_continuity_correction_collapses_to_one(self):
        r = mannwhitney_u([1, 2, 3, 4, 5], [1, 2, 3, 4, 6])
        self.assertEqual(r["u1"], 12.0)
        self.assertEqual(r["u"], 12.0)
        self.assertAlmostEqual(r["z"], 0.0, places=12)
        self.assertAlmostEqual(r["p"], 1.0, places=12)

    def test_uncorrected_z_is_documented_variant(self):
        # without the continuity correction the same data gives z=0.105736
        from collections import Counter
        import math
        a, b = [1, 2, 3, 4, 5], [1, 2, 3, 4, 6]
        combined = a + b
        n1, n2, n = len(a), len(b), len(a) + len(b)
        from noisefloor.stats import _rankdata
        r1 = sum(_rankdata(combined)[:n1])
        u1 = r1 - n1 * (n1 + 1) / 2.0
        tie = sum(t ** 3 - t for t in Counter(combined).values())
        sigma = math.sqrt((n1 * n2 / 12.0) * ((n + 1) - tie / float(n * (n - 1))))
        self.assertAlmostEqual((u1 - n1 * n2 / 2.0) / sigma, -0.105736, places=5)


class TestBootstrapConventions(unittest.TestCase):
    def test_type7_percentile(self):
        # Hyndman-Fan type 7 interpolation, as used for the bootstrap CI
        self.assertAlmostEqual(percentile([1.0, 2.0, 3.0, 4.0, 5.0], 2.5),
                               1.1, places=12)
        self.assertAlmostEqual(percentile([1.0, 2.0, 3.0, 4.0, 5.0], 97.5),
                               4.9, places=12)

    def test_bootstrap_ci_orientation(self):
        # speedup is median(baseline)/median(candidate): a 2x faster candidate
        # must put the CI above 1.0, and swapping the arms must invert it
        a = [1000, 1002, 998, 1004, 996, 1001, 999, 1003]
        b = [500, 501, 499, 502, 498, 500.5, 499.5, 501.5]
        fwd = speedup_ci(a, b, n_boot=600, seed=17)
        rev = speedup_ci(b, a, n_boot=600, seed=17)
        self.assertGreater(fwd["low"], 1.9)
        self.assertLess(rev["high"], 0.53)
        self.assertAlmostEqual(fwd["point"] * rev["point"], 1.0, places=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
