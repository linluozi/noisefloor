import contextlib
import io
import json
import os
import tempfile
import unittest

from noisefloor.cli import main


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(argv)
    text = buf.getvalue()
    return rc, text, json.loads(text)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def write_json(self, name, obj):
        p = self.path(name)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        return p

    def test_gate_faster_and_certificate_verifies(self):
        a = [1000 + (i % 3) for i in range(30)]
        b = [500 + (i % 3) for i in range(30)]
        bp = self.write_json("base.json", a)
        cp = self.write_json("cand.json", b)
        cert = self.path("cert.json")
        rc, _, out = run(["gate", "--baseline", bp, "--candidate", cp,
                          "--target", "1.15", "--n-boot", "400",
                          "--no-power", "--json-out", cert])
        self.assertEqual(rc, 0)
        self.assertEqual(out["verdict"], "FASTER")
        self.assertGreater(out["speedup"], 1.5)
        rc2, _, v = run(["verify", cert])
        self.assertEqual(rc2, 0)
        self.assertTrue(v["valid"], v["problems"])

    def test_verify_detects_tampered_samples(self):
        a = [1000 + (i % 3) for i in range(30)]
        b = [500 + (i % 3) for i in range(30)]
        bp = self.write_json("base.json", a)
        cp = self.write_json("cand.json", b)
        cert = self.path("cert.json")
        run(["gate", "--baseline", bp, "--candidate", cp, "--no-power",
             "--n-boot", "300", "--json-out", cert])
        with open(cert, encoding="utf-8") as fh:
            payload = json.load(fh)
        payload["raw"]["candidate_ns"][0] += 1
        with open(cert, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        rc, _, v = run(["verify", cert])
        self.assertEqual(rc, 1)
        self.assertFalse(v["valid"])
        self.assertTrue(any("samples_sha256" in p for p in v["problems"]))

    def test_plan_reports_mde_and_required_n(self):
        import random
        rng = random.Random(3)
        samples = [max(1, int(rng.gauss(1000, 25))) for _ in range(30)]
        sp = self.write_json("samples.json", samples)
        rc, _, out = run(["plan", "--from-json", sp, "--target", "1.15",
                          "--power-trials", "40", "--power-boot", "200"])
        self.assertEqual(rc, 0)
        self.assertIn("mde", out)
        self.assertIn("required_n", out)
        self.assertEqual(out["observed"]["n"], 30)
        self.assertIn("raw_sha256", out)

    def test_aa_small_run(self):
        rc, _, out = run(["aa", "--trials", "12", "--rounds", "10",
                          "--terms", "300", "--n-boot", "100"])
        self.assertEqual(rc, 0)
        self.assertEqual(out["trials"], 12)
        self.assertLessEqual(out["false_positive_rate"], 1.0)

    def test_gate_rejects_bad_file(self):
        p = self.write_json("bad.json", {"nope": 1})
        with self.assertRaises(SystemExit):
            main(["gate", "--baseline", p, "--candidate", p])


if __name__ == "__main__":
    unittest.main(verbosity=2)
