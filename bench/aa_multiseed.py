#!/usr/bin/env python3
"""Multi-seed A/A calibration: how noisy is a 200-trial calibration itself?

A single 200-trial A/A run estimates the false-positive rate with a standard
error of ~1.5 percentage points, so one run must not be quoted as *the*
calibration.  This script repeats it across seeds and reports the pooled rate.

    PYTHONPATH=src python3 bench/aa_multiseed.py
"""

from __future__ import annotations

import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from noisefloor import canonical_json, content_hash, decide, measure  # noqa: E402

SEEDS = (20261116, 1, 999, 20270101, 7, 123)
TRIALS = 200
ROUNDS = 30
TERMS = 3000


def workload():
    return sum(i * i for i in range(TERMS))


def cp_interval(k, n, alpha=0.05):
    """Clopper-Pearson interval via bisection on the binomial CDF (no scipy).

    The PMF is evaluated in log space with lgamma to avoid float overflow at
    n = 1200.
    """
    def logpmf(i, p):
        return (math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
                + i * math.log(p) + (n - i) * math.log1p(-p))

    def cdf(p):
        return sum(math.exp(logpmf(i, p)) for i in range(0, k + 1))

    def sf(p):
        return sum(math.exp(logpmf(i, p)) for i in range(k, n + 1))

    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if cdf(mid) > alpha / 2:
            lo = mid
        else:
            hi = mid
    lower = 0.0 if k == 0 else (lo + hi) / 2
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if sf(mid) > alpha / 2:
            hi = mid
        else:
            lo = mid
    upper = 1.0 if k == n else (lo + hi) / 2
    return (min(lower, upper), max(lower, upper))


def main():
    runs = []
    for seed in SEEDS:
        fp = 0
        for i in range(TRIALS):
            a = measure(workload, n=ROUNDS, warmup=1)
            b = measure(workload, n=ROUNDS, warmup=1)
            v = decide(a, b, target=1.0, alpha=0.05, seed=seed + i,
                       n_boot=400, with_power=False)
            if v.verdict == "FASTER":
                fp += 1
        runs.append({"seed": seed, "trials": TRIALS,
                     "false_positives": fp, "false_positive_rate": fp / TRIALS})
        print(f"seed={seed} FASTER={fp}/{TRIALS} = {fp / TRIALS:.1%}", flush=True)

    k = sum(r["false_positives"] for r in runs)
    n = sum(r["trials"] for r in runs)
    lo, hi = cp_interval(k, n)
    out = {
        "tool": "noisefloor-multiseed-aa",
        "ran_at_unix": time.time(),
        "workload": {"terms": TERMS, "n_per_arm": ROUNDS, "warmup": 1},
        "target": 1.0, "alpha": 0.05, "n_boot": 400,
        "runs": runs,
        "pooled": {"false_positives": k, "trials": n,
                   "false_positive_rate": k / n,
                   "cp95": [lo, hi]},
        "spread_min": min(r["false_positive_rate"] for r in runs),
        "spread_max": max(r["false_positive_rate"] for r in runs),
    }
    out["runs_sha256"] = content_hash(runs)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dest = os.path.join(here, "evidence", "aa_multiseed.json")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(out) + "\n")
    print(canonical_json({"pooled": out["pooled"], "spread": [out["spread_min"],
                                                             out["spread_max"]],
                          "wrote": dest}))


if __name__ == "__main__":
    main()
