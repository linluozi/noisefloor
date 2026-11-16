"""Measurement harness: alternating A/B timing with raw-sample retention."""

from __future__ import annotations

import hashlib
import json
import time

__all__ = ["measure", "ab", "canonical_json", "content_hash"]


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def measure(fn, n: int = 30, warmup: int = 3, clock=time.perf_counter_ns):
    """Return ``n`` raw per-call durations (ns) after ``warmup`` untimed calls."""
    if n <= 0:
        raise ValueError("n must be positive")
    for _ in range(max(0, int(warmup))):
        fn()
    samples = []
    for _ in range(int(n)):
        t0 = clock()
        fn()
        samples.append(int(clock() - t0))
    return samples


def ab(fn_base, fn_cand, rounds: int = 30, warmup: int = 3, clock=time.perf_counter_ns):
    """Alternate baseline/candidate *within* each round to spread drift.

    Returns a dict with the raw per-round samples for both arms (warmup runs
    are executed but never recorded) plus a content hash of the samples.
    """
    if rounds <= 0:
        raise ValueError("rounds must be positive")
    for _ in range(max(0, int(warmup))):
        fn_base()
        fn_cand()
    a, b = [], []
    for _ in range(int(rounds)):
        t0 = clock()
        fn_base()
        a.append(int(clock() - t0))
        t0 = clock()
        fn_cand()
        b.append(int(clock() - t0))
    payload = {"rounds": int(rounds), "warmup": int(warmup), "baseline_ns": a,
               "candidate_ns": b}
    payload["samples_sha256"] = content_hash({"baseline_ns": a, "candidate_ns": b})
    return payload
