#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ablation 1 -- Retrieval-only (no LLM call at all).

For each test case, predicts the MAJORITY true label among its retrieved_pairs
(the same Examples the LLM would have been shown), falling back to the task's
train-split majority class when retrieved_pairs is empty. This isolates "how
much of the LLM's score is just echoing the retrieved evidence's label
distribution" from "how much comes from the mechanistic reasoning on top of
it" -- see docs/prompt_optimization.md "消融 1 -- Retrieval-only".

Uses the SAME retrieval jsons (3 seeds) and compute_metrics()/load_truth() as
the main matrix, so numbers are on the same footing. Pure local script, no LLM,
runs in seconds.

Usage: python src/eval/retrieval_only_baseline.py [--seeds 0 1 2]
Writes data/ab/agg_retrieval_only.json.
"""
from __future__ import annotations
import argparse, csv, json, os, statistics as st
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
import sys; sys.path.insert(0, HERE)
from score import load_truth, compute_metrics

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
R = os.path.join(REPO, "data", "runs")
T = os.path.join(REPO, "data", "task2")
AB = os.path.join(REPO, "data", "ab")

# task key -> (score-task, retrieval tmpl, labels csv, readout col)
TASKS = {
    "T1a-DE":  ("de",         f"{R}/DE_retr_full_s{{s}}.json",   f"{R}/deleteome_DE.csv",          "gene"),
    "T1b-DIR": ("dir",        f"{R}/DIR_retr_full_s{{s}}.json",  f"{R}/deleteome_DIR.csv",         "gene"),
    "T2A-DE":  ("growth",     f"{T}/t2de_retr_full_s{{s}}.json", f"{T}/hillenmeyer_phenotype.csv", "context"),
    "T2A-DIR": ("growth_dir", f"{T}/t2dir_retr_full_s{{s}}.json",f"{T}/hillenmeyer_direction.csv", "context"),
}
KEYS = ["macro_f1", "mcc", "acc_overall", "answered_pct"]


def _train_majority(labels_csv: str) -> int:
    counts = Counter()
    with open(labels_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("split") == "train":
                counts[int(row["label"])] += 1
    return counts.most_common(1)[0][0] if counts else 0


def _predict(retrieval_json: str, fallback: int):
    with open(retrieval_json, "r", encoding="utf-8") as f:
        items = json.load(f)
    preds = []
    for item in items:
        pairs = item.get("retrieved_pairs", [])
        labels = [p[2] for p in pairs if len(p) > 2 and p[2] is not None]
        if labels:
            preds.append(Counter(labels).most_common(1)[0][0])
        else:
            preds.append(fallback)
    return preds


def _ms(vals):
    m = st.mean(vals); s = st.pstdev(vals) if len(vals) > 1 else 0.0
    return m, s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    args = ap.parse_args()

    out = {"method": "retrieval_only", "tasks": {}}
    print(f"\n===== Retrieval-only (majority vote over retrieved Examples), seeds {args.seeds} (mean±std) =====")
    print(f"{'task':10s} {'Macro-F1':>14s} {'MCC':>14s} {'Acc':>14s} {'Answered%':>13s}  n(test)")
    for tk, (stask, rtm, lab, rcol) in TASKS.items():
        fallback = _train_majority(lab)
        per = {k: [] for k in KEYS}; ntest = None
        for s in args.seeds:
            rj = rtm.format(s=s)
            preds = _predict(rj, fallback)
            truth = load_truth(rj, lab, readout_col=rcol)
            met = compute_metrics(preds, truth, stask)
            ntest = met["n_total"]
            for k in KEYS:
                per[k].append(met[k])
        agg = {k: _ms(per[k]) for k in KEYS}
        out["tasks"][tk] = {k: {"mean": round(agg[k][0], 4), "std": round(agg[k][1], 4)} for k in KEYS}
        out["tasks"][tk]["n_test"] = ntest
        out["tasks"][tk]["train_majority_fallback_label"] = fallback
        print(f"{tk:10s} "
              f"{agg['macro_f1'][0]:.3f}±{agg['macro_f1'][1]:.3f}  "
              f"{agg['mcc'][0]:.3f}±{agg['mcc'][1]:.3f}  "
              f"{agg['acc_overall'][0]:.3f}±{agg['acc_overall'][1]:.3f}  "
              f"{agg['answered_pct'][0]:.1f}±{agg['answered_pct'][1]:.1f}  {ntest}")
    with open(os.path.join(AB, "agg_retrieval_only.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {AB}/agg_retrieval_only.json")


if __name__ == "__main__":
    main()
