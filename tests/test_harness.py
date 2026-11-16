import json
import os
import tempfile
import unittest

from noisefloor.harness import ab, canonical_json, content_hash, measure


class CountingClock:
    """Deterministic nanosecond clock: each call advances by 1000 ns."""

    def __init__(self):
        self.t = 0

    def __call__(self):
        self.t += 1000
        return self.t


class TestMeasure(unittest.TestCase):
    def test_records_n_samples_and_excludes_warmup(self):
        calls = []

        def fn():
            calls.append(1)

        samples = measure(fn, n=10, warmup=4, clock=CountingClock())
        self.assertEqual(len(samples), 10)
        self.assertEqual(len(calls), 14)

    def test_rejects_bad_n(self):
        with self.assertRaises(ValueError):
            measure(lambda: None, n=0)


class TestAb(unittest.TestCase):
    def test_alternates_and_retains_raw(self):
        order = []

        def base():
            order.append("a")

        def cand():
            order.append("b")

        payload = ab(base, cand, rounds=5, warmup=2, clock=CountingClock())
        self.assertEqual(len(payload["baseline_ns"]), 5)
        self.assertEqual(len(payload["candidate_ns"]), 5)
        # warmup runs each arm, then strict alternation
        self.assertEqual(order[:4], ["a", "b", "a", "b"])
        self.assertEqual(order[4:], ["a", "b"] * 5)

    def test_samples_hash_binds_the_raw_arrays(self):
        payload = ab(lambda: None, lambda: None, rounds=3, warmup=0,
                     clock=CountingClock())
        expected = content_hash({"baseline_ns": payload["baseline_ns"],
                                 "candidate_ns": payload["candidate_ns"]})
        self.assertEqual(payload["samples_sha256"], expected)

    def test_hash_is_stable_across_processes(self):
        obj = {"b": [3, 2, 1], "a": "x"}
        self.assertEqual(content_hash(obj), content_hash({"a": "x", "b": [3, 2, 1]}))

    def test_empty_rounds_rejected(self):
        with self.assertRaises(ValueError):
            ab(lambda: None, lambda: None, rounds=0)


class TestCanonicalJson(unittest.TestCase):
    def test_sorted_and_compact(self):
        self.assertEqual(canonical_json({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_json_roundtrip(self):
        payload = {"baseline_ns": [1, 2], "candidate_ns": [3]}
        self.assertEqual(json.loads(canonical_json(payload)), payload)

    def test_tempfile_write_read(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.json")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(canonical_json([1, 2, 3]))
            with open(p, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), [1, 2, 3])


if __name__ == "__main__":
    unittest.main(verbosity=2)
