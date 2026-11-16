"""Pre-registered verdict rule, statistical power, and minimum detectable effect.

The rule is fixed *before* looking at the candidate's numbers:

* ``speedup = median(baseline) / median(candidate)`` (lower time is faster).
* 95% bootstrap CI of that ratio (percentile method, fixed seed).
* ``ci_low >= target``      -> ``FASTER``   (the claim is supported)
* ``ci_high <= 1.0``        -> ``SLOWER``   (a real regression)
* ``point >= target`` but the CI is too wide -> ``UNDERPOWERED``
* otherwise                 -> ``INDISTINGUISHABLE``

Statistical power is estimated by resampling the *observed* baseline samples,
so no distributional assumption is imposed.  ``effect`` is the hypothetical
speedup; the candidate arm is the baseline samples scaled by ``1/effect``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict

from .stats import median, percentile, rsd, speedup_ci, mannwhitney_u

__all__ = ["Verdict", "decide", "power_at", "mde", "required_n", "N_GRID",
           "EFFECT_GRID"]

N_GRID = (8, 12, 20, 30, 50, 80, 120, 200)
EFFECT_GRID = (1.02, 1.03, 1.05, 1.08, 1.12, 1.15, 1.20, 1.30, 1.50)


@dataclass
class Verdict:
    verdict: str
    speedup: float
    ci_low: float
    ci_high: float
    p_value: float
    target: float
    alpha: float
    n_baseline: int
    n_candidate: int
    rsd_baseline: float
    rsd_candidate: float
    required_n: int | None = None
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        rn = "" if self.required_n is None else f" required_n={self.required_n}"
        return (f"{self.verdict}: speedup={self.speedup:.4f} "
                f"CI95=[{self.ci_low:.4f}, {self.ci_high:.4f}] "
                f"p={self.p_value:.4g} target={self.target:.2f}{rn}")


def _armed(samples, effect, n, rng):
    """Resample n values from ``samples`` and rescale by 1/effect."""
    draw = rng.choices(samples, k=n)
    if effect == 1.0:
        return draw
    inv = 1.0 / effect
    return [x * inv for x in draw]


def power_at(baseline_samples, n: int, effect: float, trials: int = 150,
             n_boot: int = 300, alpha: float = 0.05, seed: int = 424242) -> float:
    """Estimated probability of calling FASTER when ``effect`` is the truth."""
    if len(baseline_samples) < 2:
        raise ValueError("need at least 2 baseline samples")
    rng = random.Random(seed)
    hits = 0
    for _ in range(int(trials)):
        a = rng.choices(list(baseline_samples), k=int(n))
        b = _armed(baseline_samples, effect, int(n), rng)
        ci = speedup_ci(a, b, n_boot=n_boot, alpha=alpha, seed=rng.randrange(1 << 30))
        if ci["low"] > 1.0:
            hits += 1
    return hits / float(trials)


def mde(baseline_samples, n: int | None = None, power: float = 0.80,
        trials: int = 150, n_boot: int = 300, seed: int = 424242):
    """Smallest effect on ``EFFECT_GRID`` detected with probability >= power."""
    n = int(n) if n is not None else len(baseline_samples)
    curve = {}
    for eff in EFFECT_GRID:
        p = power_at(baseline_samples, n, eff, trials=trials, n_boot=n_boot, seed=seed)
        curve[eff] = p
        if p >= power:
            return {"mde": eff, "n": n, "power": p, "curve": curve}
    return {"mde": None, "n": n, "power": curve.get(EFFECT_GRID[-1]),
            "curve": curve}


def required_n(baseline_samples, effect: float, power: float = 0.80,
               grid=N_GRID, trials: int = 150, n_boot: int = 300,
               seed: int = 424242):
    """Smallest n on ``grid`` reaching the target power at ``effect``."""
    curve = {}
    for n in grid:
        p = power_at(baseline_samples, n, effect, trials=trials, n_boot=n_boot,
                     seed=seed)
        curve[n] = p
        if p >= power:
            return {"n": n, "power": p, "curve": curve}
    return {"n": None, "power": curve[grid[-1]], "curve": curve}


def decide(baseline, candidate, target: float = 1.15, alpha: float = 0.05,
           n_boot: int = 2000, seed: int = 20261116, with_power: bool = True,
           power_trials: int = 150, power_boot: int = 300) -> Verdict:
    a = [float(x) for x in baseline]
    b = [float(x) for x in candidate]
    ci = speedup_ci(a, b, n_boot=n_boot, alpha=alpha, seed=seed)
    mw = mannwhitney_u(a, b)
    point, lo, hi = ci["point"], ci["low"], ci["high"]
    if lo >= target:
        verdict = "FASTER"
    elif hi <= 1.0:
        verdict = "SLOWER"
    elif point >= target:
        verdict = "UNDERPOWERED"
    else:
        verdict = "INDISTINGUISHABLE"

    need = None
    det = {}
    if verdict == "UNDERPOWERED" and with_power:
        rn = required_n(a, target, alpha=alpha, trials=power_trials,
                        n_boot=power_boot, seed=seed)
        need = rn["n"]
        det["power_curve"] = {str(k): v for k, v in rn["curve"].items()}
        det["power_at_observed_n"] = rn["power"]
    return Verdict(
        verdict=verdict, speedup=point, ci_low=lo, ci_high=hi,
        p_value=mw["p"], target=float(target), alpha=float(alpha),
        n_baseline=len(a), n_candidate=len(b),
        rsd_baseline=rsd(a), rsd_candidate=rsd(b),
        required_n=need, detail=det,
    )


def summarize(samples):
    s = sorted(float(x) for x in samples)
    p25, med, p75 = percentile(s, 25.0), percentile(s, 50.0), percentile(s, 75.0)
    return {"n": len(s), "p25": p25, "median": med, "p75": p75,
            "rsd": rsd(s), "min": s[0], "max": s[-1]}
