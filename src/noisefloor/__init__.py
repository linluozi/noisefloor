"""noisefloor — measure the noise floor of a benchmark before claiming a speedup.

Public API::

    from noisefloor import decide, ab, mde, required_n, aa_calibration

    payload = ab(baseline_fn, candidate_fn, rounds=30)
    verdict = decide(payload["baseline_ns"], payload["candidate_ns"], target=1.15)
    print(verdict)          # FASTER / SLOWER / INDISTINGUISHABLE / UNDERPOWERED
"""

from .gate import (Verdict, decide, mde, power_at, required_n, summarize,
                   EFFECT_GRID, N_GRID)
from .harness import ab, canonical_json, content_hash, measure
from .stats import (mannwhitney_u, median, normal_cdf, percentile, quartiles,
                    rsd, speedup_ci)

__version__ = "0.1.0"

__all__ = [
    "Verdict", "decide", "mde", "power_at", "required_n", "summarize",
    "EFFECT_GRID", "N_GRID", "ab", "measure", "canonical_json", "content_hash",
    "mannwhitney_u", "median", "normal_cdf", "percentile", "quartiles", "rsd",
    "speedup_ci", "aa_calibration", "__version__",
]


def aa_calibration(sampler, n: int = 30, trials: int = 200, target: float = 1.15,
                   alpha: float = 0.05, seed: int = 20261116, **decide_kw):
    """A/A calibration: run the *same* implementation as both arms.

    ``sampler()`` must return a list of raw samples for one arm of size ``n``
    (both arms are drawn from the same underlying process).  The false-positive
    rate is the share of trials where the rule nevertheless reports FASTER.
    A trustworthy harness keeps this near ``alpha`` for ``target == 1.0``; with
    a non-trivial ``target`` it must stay well below ``alpha``.
    """
    import random
    rng = random.Random(seed)
    decide_kw.setdefault("with_power", False)
    fp = 0
    verdicts = {}
    for _ in range(int(trials)):
        a = list(sampler())
        b = list(sampler())
        v = decide(a, b, target=target, alpha=alpha,
                   seed=rng.randrange(1 << 30), **decide_kw)
        verdicts[v.verdict] = verdicts.get(v.verdict, 0) + 1
        if v.verdict == "FASTER":
            fp += 1
    return {"trials": int(trials), "n": int(n), "target": float(target),
            "alpha": float(alpha), "false_positive_rate": fp / float(trials),
            "false_positives": fp, "verdicts": verdicts, "seed": int(seed)}
