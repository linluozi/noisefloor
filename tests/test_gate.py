import random
import unittest

from noisefloor import aa_calibration, decide, mde, power_at, required_n
from noisefloor.gate import EFFECT_GRID


def scaled(samples, effect):
    return [x / effect for x in samples]


class TestVerdictRule(unittest.TestCase):
    def test_faster(self):
        a = [1000 + (i % 3) for i in range(40)]
        b = [500 + (i % 3) for i in range(40)]
        v = decide(a, b, target=1.15, n_boot=800, seed=1, with_power=False)
        self.assertEqual(v.verdict, "FASTER")
        self.assertGreater(v.ci_low, 1.15)
        self.assertGreater(v.speedup, 1.9)

    def test_slower(self):
        a = [500 + (i % 3) for i in range(40)]
        b = [1000 + (i % 3) for i in range(40)]
        v = decide(a, b, target=1.15, n_boot=800, seed=1, with_power=False)
        self.assertEqual(v.verdict, "SLOWER")
        self.assertLess(v.ci_high, 1.0)

    def test_indistinguishable_when_same_arm(self):
        a = [1000 + (i % 7) for i in range(40)]
        v = decide(a, list(a), target=1.15, n_boot=800, seed=1, with_power=False)
        self.assertEqual(v.verdict, "INDISTINGUISHABLE")
        self.assertAlmostEqual(v.speedup, 1.0, places=12)

    def test_underpowered_reports_required_n(self):
        rng = random.Random(99)
        noisy = [max(1.0, rng.gauss(1000, 60)) for _ in range(20)]
        # candidate = truth of a 1.50x speedup, but the arm is tiny and noisy
        v = decide(noisy, scaled(noisy, 1.50), target=1.15, n_boot=600, seed=2,
                   with_power=True, power_trials=60, power_boot=200)
        self.assertIn(v.verdict, ("UNDERPOWERED", "FASTER"))
        if v.verdict == "UNDERPOWERED":
            self.assertIsNotNone(v.required_n)
            self.assertGreaterEqual(v.required_n, 8)


class TestCalibration(unittest.TestCase):
    def test_aa_false_positive_rate_at_declared_alpha(self):
        rng = random.Random(20261116)

        def sampler():
            return [rng.gauss(1000.0, 30.0) for _ in range(30)]

        rep = aa_calibration(sampler, n=30, trials=200, target=1.0, alpha=0.05,
                             n_boot=400, seed=7)
        # a correctly calibrated rule rejects a true null ~5% of the time
        self.assertLessEqual(rep["false_positive_rate"], 0.12)
        self.assertEqual(rep["trials"], 200)

    def test_aa_is_deterministic(self):
        def make():
            rng = random.Random(4)

            def sampler():
                return [rng.gauss(1000.0, 30.0) for _ in range(20)]

            return sampler

        r1 = aa_calibration(make(), n=20, trials=60, target=1.0, n_boot=200, seed=3)
        r2 = aa_calibration(make(), n=20, trials=60, target=1.0, n_boot=200, seed=3)
        self.assertEqual(r1, r2)

    def test_aa_never_claims_target_above_null(self):
        rng = random.Random(11)

        def sampler():
            return [rng.gauss(1000.0, 40.0) for _ in range(30)]

        rep = aa_calibration(sampler, n=30, trials=120, target=1.15, alpha=0.05,
                             n_boot=300, seed=9)
        self.assertLessEqual(rep["false_positive_rate"], 0.05)


class TestPower(unittest.TestCase):
    def setUp(self):
        rng = random.Random(1234)
        # ~12% per-sample RSD: large enough that a 1.02x shift is not trivially
        # detectable at n=40, which is what makes the power curves informative
        self.base = [max(1.0, rng.gauss(1000, 120)) for _ in range(40)]

    def test_power_monotone_in_effect(self):
        big = power_at(self.base, 40, 1.30, trials=80, n_boot=200, seed=5)
        small = power_at(self.base, 40, 1.02, trials=80, n_boot=200, seed=5)
        self.assertGreater(big, small)

    def test_power_monotone_in_n(self):
        n_small = power_at(self.base, 8, 1.15, trials=80, n_boot=200, seed=6)
        n_big = power_at(self.base, 120, 1.15, trials=80, n_boot=200, seed=6)
        self.assertGreaterEqual(n_big, n_small)

    def test_mde_finds_smallest_effect(self):
        r = mde(self.base, n=120, power=0.8, trials=80, n_boot=200, seed=7)
        self.assertIn(r["mde"], list(EFFECT_GRID) + [None])
        if r["mde"] is not None:
            self.assertAlmostEqual(r["curve"][r["mde"]], r["power"], places=12)

    def test_required_n_decreases_as_effect_grows(self):
        big = required_n(self.base, 1.50, power=0.8, trials=60, n_boot=200, seed=8)
        small = required_n(self.base, 1.05, power=0.8, trials=60, n_boot=200, seed=8)
        if big["n"] is not None and small["n"] is not None:
            self.assertLessEqual(big["n"], small["n"])

    def test_summarize_quartiles(self):
        from noisefloor import summarize
        s = summarize([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        self.assertEqual(s["n"], 10)
        self.assertEqual(s["median"], 5.5)
        self.assertLess(s["p25"], s["median"])
        self.assertLess(s["median"], s["p75"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
