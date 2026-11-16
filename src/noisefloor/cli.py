"""Command line interface: ``python -m noisefloor``."""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import __version__
from .gate import decide, mde, required_n, summarize
from .harness import ab, canonical_json, content_hash, measure


def _load_samples(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        for key in ("baseline_ns", "samples_ns", "samples", "raw"):
            if key in data and isinstance(data[key], list):
                return [int(x) for x in data[key]]
        raise SystemExit(f"{path}: no sample list found (keys: {sorted(data)})")
    if isinstance(data, list):
        return [int(x) for x in data]
    raise SystemExit(f"{path}: unsupported JSON top level {type(data).__name__}")


def _workload(n_terms=3000):
    def fn():
        return sum(i * i for i in range(n_terms))
    return fn


def _write(path, payload):
    text = canonical_json(payload)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return content_hash(payload)


def cmd_aa(args):
    fn = _workload(args.terms)
    rng_trials = []

    def sampler():
        return measure(fn, n=args.rounds, warmup=1)

    for i in range(args.trials):
        a = sampler()
        b = sampler()
        v = decide(a, b, target=args.target, alpha=args.alpha,
                   seed=args.seed + i, n_boot=args.n_boot, with_power=False)
        rng_trials.append({"verdict": v.verdict, "speedup": v.speedup,
                           "ci_low": v.ci_low, "ci_high": v.ci_high})
    fp = sum(1 for t in rng_trials if t["verdict"] == "FASTER")
    result = {
        "trials": args.trials, "n_per_arm": args.rounds, "target": args.target,
        "alpha": args.alpha, "false_positive_rate": fp / float(args.trials),
        "false_positives": fp,
        "verdicts": {v: sum(1 for t in rng_trials if t["verdict"] == v)
                     for v in sorted({t["verdict"] for t in rng_trials})},
        "speedup_median": sorted(t["speedup"] for t in rng_trials)[len(rng_trials) // 2],
        "speedup_min": min(t["speedup"] for t in rng_trials),
        "speedup_max": max(t["speedup"] for t in rng_trials),
    }
    payload = {"tool": "noisefloor", "version": __version__, "kind": "aa",
               "result": result, "trials_raw": rng_trials}
    payload["samples_sha256"] = content_hash(rng_trials)
    if args.json_out:
        _write(args.json_out, payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_gate(args):
    base = _load_samples(args.baseline)
    cand = _load_samples(args.candidate)
    v = decide(base, cand, target=args.target, alpha=args.alpha, seed=args.seed,
               n_boot=args.n_boot, with_power=not args.no_power,
               power_trials=args.power_trials, power_boot=args.power_boot)
    result = {"verdict": v.verdict, "speedup": v.speedup, "ci_low": v.ci_low,
              "ci_high": v.ci_high, "p_value": v.p_value, "target": v.target,
              "required_n": v.required_n, "detail": v.detail,
              "baseline": summarize(base), "candidate": summarize(cand)}
    payload = {"tool": "noisefloor", "version": __version__, "kind": "gate",
               "params": {"target": args.target, "alpha": args.alpha,
                          "seed": args.seed, "n_boot": args.n_boot},
               "raw": {"baseline_ns": base, "candidate_ns": cand},
               "result": result}
    payload["samples_sha256"] = content_hash(payload["raw"])
    payload["certificate_sha256"] = content_hash(
        {k: payload[k] for k in ("tool", "version", "kind", "params", "raw", "result")})
    if args.json_out:
        _write(args.json_out, payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if v.verdict in ("FASTER", "SLOWER", "INDISTINGUISHABLE",
                             "UNDERPOWERED") else 1


def cmd_plan(args):
    samples = _load_samples(args.from_json)
    job = {"n": args.runs or len(samples), "power": args.power,
           "trials": args.power_trials, "n_boot": args.power_boot,
           "seed": args.seed}
    out = {
        "observed": summarize(samples),
        "mde": mde(samples, n=job["n"], power=args.power,
                   trials=args.power_trials, n_boot=args.power_boot,
                   seed=args.seed),
        "required_n": required_n(samples, effect=args.target, power=args.power,
                                 trials=args.power_trials,
                                 n_boot=args.power_boot, seed=args.seed),
        "target": args.target,
    }
    out["raw_sha256"] = content_hash([int(x) for x in samples])
    if args.json_out:
        _write(args.json_out, out)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_verify(args):
    with open(args.certificate, "r", encoding="utf-8") as fh:
        cert = json.load(fh)
    raw = cert.get("raw", {})
    problems = []
    if cert.get("kind") == "gate" and raw:
        if content_hash(raw) != cert.get("samples_sha256"):
            problems.append("samples_sha256 mismatch")
        v = decide(raw["baseline_ns"], raw["candidate_ns"],
                   target=cert["params"]["target"], alpha=cert["params"]["alpha"],
                   seed=cert["params"]["seed"], n_boot=cert["params"]["n_boot"],
                   with_power=False)
        if v.verdict != cert["result"]["verdict"]:
            problems.append(f"verdict mismatch: {v.verdict} != {cert['result']['verdict']}")
        for key, got in (("speedup", v.speedup), ("ci_low", v.ci_low),
                         ("ci_high", v.ci_high)):
            want = cert["result"][key]
            if abs(got - want) > 1e-12:
                problems.append(f"{key} mismatch: {got} != {want}")
    elif cert.get("kind") == "aa":
        if content_hash(cert.get("trials_raw", [])) != cert.get("samples_sha256"):
            problems.append("samples_sha256 mismatch")
    else:
        problems.append("unsupported certificate kind")
    out = {"valid": not problems, "problems": problems,
           "certificate": args.certificate, "tool": cert.get("tool"),
           "version": cert.get("version"), "kind": cert.get("kind"),
           "checked_at_unix": time.time()}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if not problems else 1


def build_parser():
    p = argparse.ArgumentParser(
        prog="noisefloor",
        description="Measure the noise floor of a benchmark before claiming a speedup.")
    p.add_argument("--version", action="version", version=f"noisefloor {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("aa", help="A/A false-positive calibration on a built-in workload")
    a.add_argument("--trials", type=int, default=200)
    a.add_argument("--rounds", type=int, default=30, help="samples per arm per trial")
    a.add_argument("--terms", type=int, default=3000, help="workload size")
    a.add_argument("--target", type=float, default=1.15)
    a.add_argument("--alpha", type=float, default=0.05)
    a.add_argument("--n-boot", type=int, default=400)
    a.add_argument("--seed", type=int, default=20261116)
    a.add_argument("--json-out", default=None)
    a.set_defaults(func=cmd_aa)

    g = sub.add_parser("gate", help="verdict for a two-arm sample file pair")
    g.add_argument("--baseline", required=True)
    g.add_argument("--candidate", required=True)
    g.add_argument("--target", type=float, default=1.15)
    g.add_argument("--alpha", type=float, default=0.05)
    g.add_argument("--n-boot", type=int, default=2000)
    g.add_argument("--seed", type=int, default=20261116)
    g.add_argument("--no-power", action="store_true")
    g.add_argument("--power-trials", type=int, default=150)
    g.add_argument("--power-boot", type=int, default=300)
    g.add_argument("--json-out", default=None)
    g.set_defaults(func=cmd_gate)

    pl = sub.add_parser("plan", help="MDE and required n from observed samples")
    pl.add_argument("--from-json", required=True)
    pl.add_argument("--target", type=float, default=1.15)
    pl.add_argument("--runs", type=int, default=0)
    pl.add_argument("--power", type=float, default=0.80)
    pl.add_argument("--power-trials", type=int, default=150)
    pl.add_argument("--power-boot", type=int, default=300)
    pl.add_argument("--seed", type=int, default=424242)
    pl.add_argument("--json-out", default=None)
    pl.set_defaults(func=cmd_plan)

    v = sub.add_parser("verify", help="recompute a certificate from its raw samples")
    v.add_argument("certificate")
    v.set_defaults(func=cmd_verify)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
