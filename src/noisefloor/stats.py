"""Dependency-free statistics used by :mod:`noisefloor`.

Everything here is deterministic given an explicit seed so that a certificate
can be re-computed byte-for-byte on another machine.
"""

from __future__ import annotations

import math
import random

__all__ = [
    "percentile",
    "median",
    "quartiles",
    "rsd",
    "speedup_ci",
    "mannwhitney_u",
    "normal_cdf",
]


def percentile(sorted_xs, q: float) -> float:
    """Linear-interpolation percentile (same convention as numpy's default)."""
    n = len(sorted_xs)
    if n == 0:
        raise ValueError("percentile() of empty sequence")
    if n == 1:
        return float(sorted_xs[0])
    if not 0.0 <= q <= 100.0:
        raise ValueError("q must be in [0, 100]")
    idx = (n - 1) * q / 100.0
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return float(sorted_xs[int(idx)])
    frac = idx - lo
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * frac


def _sorted(xs):
    xs = [float(x) for x in xs]
    if not xs:
        raise ValueError("empty sample")
    return sorted(xs)


def median(xs) -> float:
    return percentile(_sorted(xs), 50.0)


def quartiles(xs):
    s = _sorted(xs)
    return percentile(s, 25.0), percentile(s, 50.0), percentile(s, 75.0)


def rsd(xs) -> float:
    """Relative standard deviation (stdev / mean), 0.0 when mean is 0."""
    vals = [float(x) for x in xs]
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    if mean == 0.0:
        return 0.0
    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(var) / abs(mean)


def speedup_ci(a, b, n_boot: int = 2000, alpha: float = 0.05, seed: int = 20261116,
               method: str = "percentile"):
    """Bootstrap CI for ``speedup = median(a) / median(b)``.

    ``a`` is the baseline arm, ``b`` the candidate arm; both are raw per-run
    timings in the same unit (lower is faster).  The CI is the ``alpha``/2 and
    ``1 - alpha/2`` percentiles of the bootstrap distribution of the ratio of
    medians (percentile method) or its reflection about the point estimate
    (``method="basic"``).
    """
    if method not in ("percentile", "basic"):
        raise ValueError("method must be 'percentile' or 'basic'")
    sa, sb = _sorted(a), _sorted(b)
    if len(sa) < 2 or len(sb) < 2:
        raise ValueError("need at least 2 samples per arm")
    point = percentile(sa, 50.0) / percentile(sb, 50.0)
    rng = random.Random(seed)
    na, nb = len(sa), len(sb)
    ratios = []
    for _ in range(int(n_boot)):
        ra = sorted(rng.choices(sa, k=na))
        rb = sorted(rng.choices(sb, k=nb))
        m = percentile(rb, 50.0)
        ratios.append(percentile(ra, 50.0) / m if m else float("inf"))
    ratios.sort()
    lo = percentile(ratios, 100.0 * (alpha / 2.0))
    hi = percentile(ratios, 100.0 * (1.0 - alpha / 2.0))
    if method == "basic":
        lo, hi = 2.0 * point - hi, 2.0 * point - lo
    return {"point": point, "low": lo, "high": hi, "n_boot": int(n_boot),
            "alpha": float(alpha), "seed": int(seed), "method": method}


def _rankdata(xs):
    """Average ranks, 1-based, ties share the mean rank."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def mannwhitney_u(a, b):
    """Two-sided Mann-Whitney U with tie correction and continuity correction."""
    a = [float(x) for x in a]
    b = [float(x) for x in b]
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        raise ValueError("empty arm")
    combined = a + b
    ranks = _rankdata(combined)
    r1 = sum(ranks[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)
    n = n1 + n2
    mu = n1 * n2 / 2.0
    # tie correction
    from collections import Counter
    tie_sum = sum(t ** 3 - t for t in Counter(combined).values())
    sigma_sq = (n1 * n2 / 12.0) * ((n + 1) - tie_sum / float(n * (n - 1)))
    if sigma_sq <= 0:
        return {"u": u, "u1": u1, "z": 0.0, "p": 1.0, "n1": n1, "n2": n2}
    sigma = math.sqrt(sigma_sq)
    diff = u1 - mu
    cc = 0.5 if diff > 0 else (-0.5 if diff < 0 else 0.0)
    z = (diff - cc) / sigma
    p = 2.0 * (1.0 - normal_cdf(abs(z)))
    return {"u": u, "u1": u1, "z": z, "p": min(1.0, max(0.0, p)), "n1": n1, "n2": n2}


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
