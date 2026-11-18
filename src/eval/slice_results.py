#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slice the full-scale predictions by a metadata axis -> per-subset metrics.

Enriches the main 4x4 matrix (RESULTS.md) by re-scoring already-collected
predictions on interpretable subsets, so no new GPU inference is needed.

Axes implemented (zero extra curation):
  tf       — perturbagen is a TF (in YEASTRACT tf_targets) vs non-TF   [T1 de/dir]
  effsize  — |effect| tier of the readout (|M| for T1, |z| for T2)     [all tasks]

Usage:
  python src/eval/slice_results.py --axis tf --tasks T1a-DE T1b-DIR \
         --models qwen14b qwen7b llama8b qwen4b [--seeds 0 1 2]
Prints a per-(model, subset) mean±std table and writes data/runs/slice_<axis>.json.
"""
from __future__ import annotations
import argparse, json, os, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__)); import sys; sys.path.insert(0, HERE)
from score import load_predictions, load_truth, compute_metrics
from aggregate_seeds import TASKS, REPO, R  # reuse task templates

KNOW = os.path.join(REPO, "data", "knowledge")
KEYS = ["macro_f1", "mcc", "answered_pct"]


def _ms(v):
    return (st.mean(v), st.pstdev(v) if len(v) > 1 else 0.0)


def _retr_perts(rjson):
    """(pert, readout) per retrieval index, in order."""
    d = json.load(open(rjson, encoding="utf-8"))
    return [(str(x["test_case"]["pert"]), str(x["test_case"]["gene"])) for x in d]


def _tf_masks(perts):
    tf = set(json.load(open(os.path.join(KNOW, "tf_targets.json"), encoding="utf-8")))
    m = [p in tf for p, _ in perts]
    return {"TF-deletion": m, "non-TF": [not x for x in m]}


def _effsize_masks(perts, effmap, cuts):
    """Tier by |effect|. effmap: (pert,readout)->float; cuts ascending."""
    vals = [abs(effmap.get(pr, float("nan"))) for pr in perts]
    labels = [f"|eff|<{cuts[0]}"] + [f"{cuts[i]}-{cuts[i+1]}" for i in range(len(cuts) - 1)] + [f">{cuts[-1]}"]
    masks = {lb: [False] * len(vals) for lb in labels}
    for i, v in enumerate(vals):
        if v != v:  # nan
            continue
        b = 0
        while b < len(cuts) and v >= cuts[b]:
            b += 1
        masks[labels[b]][i] = True
    return masks


def _sub(preds, truth, mask, task):
    p = [x for x, m in zip(preds, mask) if m]
    t = [x for x, m in zip(truth, mask) if m]
    return compute_metrics(p, t, task)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--axis", required=True, choices=["tf", "effsize"])
    ap.add_argument("--tasks", nargs="+", default=["T1a-DE", "T1b-DIR"])
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    args = ap.parse_args()

    out = {"axis": args.axis, "tasks": {}}
    for tk in args.tasks:
        stask, ptm, rtm, lab, rcol = TASKS[tk]
        # subsets are defined per-seed by retrieval order; sizes are stable across seeds
        print(f"\n===== {tk}  axis={args.axis} =====")
        seed_perts = {s: _retr_perts(rtm.format(s=s)) for s in args.seeds}
        # build masks per seed
        if args.axis == "tf":
            seed_masks = {s: _tf_masks(seed_perts[s]) for s in args.seeds}
        else:
            raise SystemExit("effsize axis: run build step first (not wired here)")
        subsets = list(next(iter(seed_masks.values())).keys())
        n0 = {sub: sum(seed_masks[args.seeds[0]][sub]) for sub in subsets}
        print("  subset sizes (seed0): " + ", ".join(f"{k}={v}" for k, v in n0.items()))
        print(f"  {'model':10s} {'subset':14s} {'Macro-F1':>13s} {'MCC':>13s} {'Answered%':>12s}")
        out["tasks"][tk] = {"sizes": n0, "models": {}}
        seed_truth = {s: load_truth(rtm.format(s=s), lab, readout_col=rcol) for s in args.seeds}
        for m in args.models:
            per = {sub: {k: [] for k in KEYS} for sub in subsets}
            ok = True
            for s in args.seeds:
                p = ptm.format(m=m, s=s)
                if not os.path.exists(p):
                    ok = False; break
                preds = load_predictions(p, stask)
                truth = seed_truth[s]
                for sub in subsets:
                    met = _sub(preds, truth, seed_masks[s][sub], stask)
                    for k in KEYS:
                        per[sub][k].append(met[k])
            if not ok:
                print(f"  {m:10s} (preds missing)"); continue
            out["tasks"][tk]["models"][m] = {}
            for sub in subsets:
                agg = {k: _ms(per[sub][k]) for k in KEYS}
                out["tasks"][tk]["models"][m][sub] = {
                    k: {"mean": round(agg[k][0], 4), "std": round(agg[k][1], 4)} for k in KEYS}
                print(f"  {m:10s} {sub:14s} "
                      f"{agg['macro_f1'][0]:.3f}±{agg['macro_f1'][1]:.3f} "
                      f"{agg['mcc'][0]:.3f}±{agg['mcc'][1]:.3f} "
                      f"{agg['answered_pct'][0]:5.1f}±{agg['answered_pct'][1]:.1f}")
    dst = os.path.join(R, f"slice_{args.axis}.json")
    json.dump(out, open(dst, "w"), indent=2)
    print(f"\nwrote {dst}")


if __name__ == "__main__":
    main()
