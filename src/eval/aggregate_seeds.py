#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Score a model's full-scale predictions over 4 tasks x 3 seeds -> mean±std.

Usage: python src/eval/aggregate_seeds.py --model llama8b [--seeds 0 1 2]
Prints a per-task table (Macro-F1 / MCC / Acc / Answered% as mean±std) and
writes data/runs/agg_<model>.json.
"""
from __future__ import annotations
import argparse, json, os, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
import sys; sys.path.insert(0, HERE)
from score import load_predictions, load_truth, compute_metrics

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
R = os.path.join(REPO, "data", "runs"); T = os.path.join(REPO, "data", "task2")

# task key -> (score-task, pred tmpl, retrieval tmpl, labels csv, readout col)
TASKS = {
    "T1a-DE":     ("de",         f"{R}/DE_pred_{{m}}_s{{s}}.txt",   f"{R}/DE_retr_full_s{{s}}.json",   f"{R}/deleteome_DE.csv",        "gene"),
    "T1b-DIR":    ("dir",        f"{R}/DIR_pred_{{m}}_s{{s}}.txt",  f"{R}/DIR_retr_full_s{{s}}.json",  f"{R}/deleteome_DIR.csv",       "gene"),
    "T2A-DE":     ("growth",     f"{T}/t2de_pred_{{m}}_s{{s}}.txt", f"{T}/t2de_retr_full_s{{s}}.json", f"{T}/hillenmeyer_phenotype.csv","context"),
    "T2A-DIR":    ("growth_dir", f"{T}/t2dir_pred_{{m}}_s{{s}}.txt",f"{T}/t2dir_retr_full_s{{s}}.json",f"{T}/hillenmeyer_direction.csv","context"),
}
KEYS = ["macro_f1", "mcc", "acc_overall", "answered_pct"]


def _ms(vals):
    m = st.mean(vals); s = st.pstdev(vals) if len(vals) > 1 else 0.0
    return m, s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    args = ap.parse_args()

    out = {"model": args.model, "tasks": {}}
    print(f"\n===== {args.model} : full-scale, seeds {args.seeds} (mean±std) =====")
    print(f"{'task':10s} {'Macro-F1':>14s} {'MCC':>14s} {'Acc':>14s} {'Answered%':>13s}  n(test)")
    for tk, (stask, ptm, rtm, lab, rcol) in TASKS.items():
        per = {k: [] for k in KEYS}; ntest = None; ok = True
        for s in args.seeds:
            p = ptm.format(m=args.model, s=s)
            if not os.path.exists(p):
                ok = False; break
            preds = load_predictions(p, stask)
            truth = load_truth(rtm.format(s=s), lab, readout_col=rcol)
            met = compute_metrics(preds, truth, stask)
            ntest = met["n_total"]
            for k in KEYS:
                per[k].append(met[k])
        if not ok:
            print(f"{tk:10s} (predictions not ready)"); continue
        agg = {k: _ms(per[k]) for k in KEYS}
        out["tasks"][tk] = {k: {"mean": round(agg[k][0], 4), "std": round(agg[k][1], 4)} for k in KEYS}
        out["tasks"][tk]["n_test"] = ntest
        print(f"{tk:10s} "
              f"{agg['macro_f1'][0]:.3f}±{agg['macro_f1'][1]:.3f}  "
              f"{agg['mcc'][0]:.3f}±{agg['mcc'][1]:.3f}  "
              f"{agg['acc_overall'][0]:.3f}±{agg['acc_overall'][1]:.3f}  "
              f"{agg['answered_pct'][0]:.1f}±{agg['answered_pct'][1]:.1f}  {ntest}")
    with open(os.path.join(R, f"agg_{args.model}.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {R}/agg_{args.model}.json")


if __name__ == "__main__":
    main()
