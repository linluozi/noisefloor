#!/usr/bin/env python3
"""Re-analyse the raw same-tree samples of linluozi/pr-evidence-recheck.

This does not re-run that tool: it reads its retained raw per-round samples
(``evidence/<dataset>.json`` -> ``scales``) and asks a new question -- *could
that 15-sample-per-arm harness have resolved the effects it was judging?*
The output is the measured statistical power / minimum detectable effect of
that harness on those exact samples.

Obtain the source tree first (github.com:443 is blocked on the build host, so
use SSH):

    git clone --depth=1 git@github-linluozi:linluozi/pr-evidence-recheck.git /tmp/prrecheck-src
    PYTHONPATH=src python3 bench/replay_prrecheck.py --source /tmp/prrecheck-src
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from noisefloor import canonical_json, content_hash, decide, mde, required_n, summarize  # noqa: E402

DATASETS = ("attrs-1660", "attrs-1660-flat", "croniter-298", "jsonpatch-274")
TRIALS = 80
N_BOOT_POWER = 200
N_GRID = (8, 12, 20, 30, 50, 80, 120)


def analyse(dataset, payload, seed):
    scales = payload["scales"]
    per_scale = {}
    for name, arms in sorted(scales.items()):
        base, cand = arms["baseline_ns"], arms["candidate_ns"]
        v130 = decide(base, cand, target=1.30, seed=seed, n_boot=2000,
                      with_power=False)
        v115 = decide(base, cand, target=1.15, seed=seed, n_boot=2000,
                      with_power=False)
        per_scale[name] = {
            "n_per_arm": len(base),
            "baseline": summarize(base),
            "candidate": summarize(cand),
            "median_speedup": v130.speedup,
            "ci95": [v130.ci_low, v130.ci_high],
            "p_value": v130.p_value,
            "verdict_target_1.30": v130.verdict,
            "verdict_target_1.15": v115.verdict,
        }
    # the heaviest scale is the most representative of a real production run
    heaviest = max(scales, key=lambda k: sorted(scales[k]["baseline_ns"])[len(scales[k]["baseline_ns"]) // 2])
    pooled = [int(x) for x in scales[heaviest]["baseline_ns"]]
    floor = mde(pooled, n=15, power=0.80, trials=TRIALS, n_boot=N_BOOT_POWER,
                seed=seed)
    need130 = required_n(pooled, 1.30, grid=N_GRID, trials=TRIALS,
                         n_boot=N_BOOT_POWER, seed=seed)
    need115 = required_n(pooled, 1.15, grid=N_GRID, trials=TRIALS,
                         n_boot=N_BOOT_POWER, seed=seed)
    return {
        "source_verdict": payload.get("verdict"),
        "source_reps": payload.get("reps"),
        "per_scale": per_scale,
        "noise_floor_from_pooled_baseline": {
            "heaviest_scale": heaviest,
            "n_pooled": len(pooled),
            "rsd_pooled": summarize(pooled)["rsd"],
            "mde_at_n15": floor["mde"],
            "power_curve_mde": {str(k): v for k, v in floor["curve"].items()},
            "required_n_for_1.30": need130["n"],
            "required_n_for_1.15": need115["n"],
        },
        "samples_sha256": content_hash({k: v["baseline_ns"] for k, v in scales.items()}),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="/tmp/prrecheck-src")
    ap.add_argument("--seed", type=int, default=20261116)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = {"tool": "noisefloor-replay", "ran_at_unix": time.time(),
           "source": args.source, "seed": args.seed, "datasets": {}}
    for ds in DATASETS:
        path = os.path.join(args.source, "evidence", ds + ".json")
        if not os.path.exists(path):
            out["datasets"][ds] = {"error": "missing " + path}
            continue
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        out["datasets"][ds] = analyse(ds, payload, args.seed)

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dest = args.out or os.path.join(here, "evidence", "replay_prrecheck.json")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(out) + "\n")
    slim = {ds: {"speedups": {s: round(v["median_speedup"], 4)
                              for s, v in d.get("per_scale", {}).items()},
                 "verdict_1.30": {s: v["verdict_target_1.30"]
                                  for s, v in d.get("per_scale", {}).items()},
                 "required_n_1.30": d.get("noise_floor_from_pooled_baseline", {}).get("required_n_for_1.30"),
                 "mde": d.get("noise_floor_from_pooled_baseline", {}).get("mde_at_n15")}
            for ds, d in out["datasets"].items()}
    print(canonical_json(slim, ))
    print("wrote", dest)


if __name__ == "__main__":
    main()
