#!/usr/bin/env python3
"""Real-hardware demo: a genuine optimization vs an A/A sham, in one run.

Writes ``evidence/demo_real.json`` containing the raw samples, the verdicts,
and the measured noise floor (MDE / required n) of this harness.

Run from the repository root:

    PYTHONPATH=src python3 bench/demo.py
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from noisefloor import (ab, canonical_json, content_hash, decide, mde,  # noqa: E402
                        required_n, summarize)

ROUNDS = 30
WARMUP = 3
TARGET = 1.15
SEED = 20261116

# ---------------------------------------------------------------- workload ---
DATA = list(range(50000))
QUERIES = [(i * 7919) % 100000 for i in range(3000)]  # ~half hit, half miss
DATA_SET = set(DATA)


def baseline():
    """Linear membership scan over a list: O(len(DATA)) per query."""
    return sum(1 for q in QUERIES if q in DATA)


def candidate():
    """Same answers, via a hash index built once outside the timed region."""
    return sum(1 for q in QUERIES if q in DATA_SET)


# --------------------------------------------------------------- sham A/A ---
def sham_a():
    return baseline()


def sham_b():
    return baseline()


def main():
    assert baseline() == candidate(), "the two arms must compute the same answer"

    real = ab(baseline, candidate, rounds=ROUNDS, warmup=WARMUP)
    sham = ab(sham_a, sham_b, rounds=ROUNDS, warmup=WARMUP)

    real_v = decide(real["baseline_ns"], real["candidate_ns"], target=TARGET,
                    seed=SEED, n_boot=2000, with_power=False)
    sham_v = decide(sham["baseline_ns"], sham["candidate_ns"], target=TARGET,
                    seed=SEED, n_boot=2000, with_power=False)

    floor = mde(sham["baseline_ns"], n=ROUNDS, power=0.80, trials=120,
                n_boot=250, seed=SEED)
    need = required_n(sham["baseline_ns"], effect=TARGET, power=0.80,
                      trials=120, n_boot=250, seed=SEED)

    out = {
        "tool": "noisefloor-demo",
        "ran_at_unix": time.time(),
        "params": {"rounds": ROUNDS, "warmup": WARMUP, "target": TARGET,
                   "seed": SEED},
        "workload": {
            "description": "membership in a 50k list (baseline) vs the same "
                           "memberships through a prebuilt set (candidate)",
            "queries": len(QUERIES),
            "answers_equal": True,
        },
        "real_optimization": {
            "raw": {"baseline_ns": real["baseline_ns"],
                    "candidate_ns": real["candidate_ns"]},
            "baseline": summarize(real["baseline_ns"]),
            "candidate": summarize(real["candidate_ns"]),
            "verdict": real_v.as_dict(),
        },
        "sham_aa": {
            "raw": {"baseline_ns": sham["baseline_ns"],
                    "candidate_ns": sham["candidate_ns"]},
            "baseline": summarize(sham["baseline_ns"]),
            "candidate": summarize(sham["candidate_ns"]),
            "verdict": sham_v.as_dict(),
        },
        "noise_floor": {
            "mde_at_n_equals_rounds": floor,
            "required_n_for_target": need,
        },
        "raw_sha256": content_hash({"real": {"b": real["baseline_ns"], "c": real["candidate_ns"]},
                                    "sham": {"b": sham["baseline_ns"], "c": sham["candidate_ns"]}}),
    }
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dest = os.path.join(here, "evidence", "demo_real.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(out) + "\n")
    print(canonical_json({
        "real": {"verdict": real_v.verdict, "speedup": round(real_v.speedup, 4),
                 "ci": [round(real_v.ci_low, 4), round(real_v.ci_high, 4)]},
        "sham": {"verdict": sham_v.verdict, "speedup": round(sham_v.speedup, 4),
                 "ci": [round(sham_v.ci_low, 4), round(sham_v.ci_high, 4)]},
        "mde": floor["mde"], "required_n": need["n"],
        "rsd_sham": [round(sham_v.rsd_baseline, 5), round(sham_v.rsd_candidate, 5)],
        "wrote": dest,
    }))


if __name__ == "__main__":
    main()
