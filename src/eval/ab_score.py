#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Score the T1/T2A A/B prompt-ablation predictions (Qwen2.5-14B only) -> mean±std.

Usage: python src/eval/ab_score.py [--seeds 0 1 2]
Prints a per-task, per-branch table (Macro-F1 / MCC / Acc / Answered% as
mean±std over seeds) and writes data/ab/agg_ab.json. Reuses the SAME
compute_metrics() / load_truth() as the main matrix's aggregate_seeds.py so
the numbers are on the same footing as the v1 rows in task_results.md.
"""
from __future__ import annotations
import argparse, json, os, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
import sys; sys.path.insert(0, HERE)
from score import load_predictions, load_truth, compute_metrics

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
R = os.path.join(REPO, "data", "runs")
T = os.path.join(REPO, "data", "task2")
AB = os.path.join(REPO, "data", "ab")

# task key -> (score-task, retrieval tmpl, labels csv, readout col)
TASKS = {
    "T1a-DE":  ("de",         f"{R}/DE_retr_full_s{{s}}.json",   f"{R}/deleteome_DE.csv",         "gene"),
    "T1b-DIR": ("dir",        f"{R}/DIR_retr_full_s{{s}}.json",  f"{R}/deleteome_DIR.csv",        "gene"),
    "T2A-DE":  ("growth",     f"{T}/t2de_retr_full_s{{s}}.json", f"{T}/hillenmeyer_phenotype.csv","context"),
    "T2A-DIR": ("growth_dir", f"{T}/t2dir_retr_full_s{{s}}.json",f"{T}/hillenmeyer_direction.csv","context"),
}
# task key -> ab_dispatch.py TASKS prefix
PRED_PREFIX = {"T1a-DE": "DE", "T1b-DIR": "DIR", "T2A-DE": "t2de", "T2A-DIR": "t2dir"}
KEYS = ["macro_f1", "mcc", "acc_overall", "answered_pct"]


def _ms(vals):
    m = st.mean(vals); s = st.pstdev(vals) if len(vals) > 1 else 0.0
    return m, s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--branches", nargs="+", default=["A", "B"])
    ap.add_argument("--out", default="agg_ab.json",
                     help="output filename under data/ab/ (default agg_ab.json; pass a "
                          "distinct name when scoring a different branch set so it doesn't "
                          "clobber an earlier run's aggregate file)")
    args = ap.parse_args()

    out = {"model": "qwen14b", "branches": {}}
    for br in args.branches:
        print(f"\n===== branch {br} : Qwen2.5-14B, seeds {args.seeds} (mean±std) =====")
        print(f"{'task':10s} {'Macro-F1':>14s} {'MCC':>14s} {'Acc':>14s} {'Answered%':>13s}  n(test)")
        out["branches"][br] = {}
        for tk, (stask, rtm, lab, rcol) in TASKS.items():
            per = {k: [] for k in KEYS}; ntest = None; ok = True
            for s in args.seeds:
                p = os.path.join(AB, f"{PRED_PREFIX[tk]}-{br}_pred_s{s}.txt")
                if not os.path.exists(p):
                    ok = False; break
                preds = load_predictions(p, stask)
                truth = load_truth(rtm.format(s=s), lab, readout_col=rcol)
                met = compute_metrics(preds, truth, stask)
                ntest = met["n_total"]
                for k in KEYS:
                    per[k].append(met[k])
            if not ok:
                print(f"{tk:10s} (predictions not ready: {p})"); continue
            agg = {k: _ms(per[k]) for k in KEYS}
            out["branches"][br][tk] = {k: {"mean": round(agg[k][0], 4), "std": round(agg[k][1], 4)} for k in KEYS}
            out["branches"][br][tk]["n_test"] = ntest
            print(f"{tk:10s} "
                  f"{agg['macro_f1'][0]:.3f}±{agg['macro_f1'][1]:.3f}  "
                  f"{agg['mcc'][0]:.3f}±{agg['mcc'][1]:.3f}  "
                  f"{agg['acc_overall'][0]:.3f}±{agg['acc_overall'][1]:.3f}  "
                  f"{agg['answered_pct'][0]:.1f}±{agg['answered_pct'][1]:.1f}  {ntest}")
    with open(os.path.join(AB, args.out), "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {AB}/{args.out}")


if __name__ == "__main__":
    main()
