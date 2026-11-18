#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cheap, local, no-LLM baselines for the four main-matrix tasks.

Three families, all computed directly from the real label CSVs (no model
inference involved — everything here is either a fixed-class rule, a
uniform-random rule, or a lookup against real curated knowledge). Random and
Majority are the two standard "weak baseline" rows every task's Result table
carries (see docs/prompt_optimization.md "基线+消融标准套件" — they convey
different things: Majority is "always guess the fixed majority class",
Random is "guess uniformly at random, ignoring the label distribution
entirely", so a model beating Majority-Acc but not beating Random-macro-F1
would still be a red flag):

  1. Majority — for a task's test split, always predict the majority class.
     Acc(overall) = majority_ratio (by construction). macro-F1 is the
     analytic closed form for an always-same-class predictor (recall=1,
     precision=majority_ratio for the majority class; the minority class is
     never predicted so its F1=0). MCC=0 for any constant predictor (the
     confusion matrix always has one empty row/column so the numerator's
     tp*tn - fp*fn term vanishes along with the corresponding denominator
     factor) — we verify this numerically via score.compute_metrics rather
     than asserting it.

  2. Random — for every test case, draw a label uniformly at random from the
     task's two closed-set classes (0/1), independent of any input (no
     features, no label-distribution knowledge — this is what separates it
     from Majority). Acc(overall) has closed form 0.5 for any true label mix
     (a fair coin is right half the time no matter the truth's split), but
     macro-F1/MCC are nonlinear in the (tp,tn,fp,fn) counts so we don't just
     assert the textbook closed form — we Monte Carlo it (many independent
     random-label draws over the SAME real test split truth vector, scored
     with the SAME compute_metrics() used for the LLM and for Majority) and
     report mean +/- stdev across draws, which also empirically validates
     the Acc=0.5 closed form.

  3. YEASTRACT sign rule (T1b-DIR only) — data/knowledge/tf_targets.json is
     built from YEASTRACT (see src/knowledge/build_regulatory.py) and gives,
     per signature TF (192 of them), its known "activates" / "represses"
     target gene sets. For a (pert, gene) test case:
       - pert in tf_targets AND gene in tf_targets[pert]['activates']
         -> deleting an activator should lower the target's expression
         -> predict Decrease (label 0)
       - pert in tf_targets AND gene in tf_targets[pert]['represses']
         -> deleting a repressor should raise the target's expression
         -> predict Increase (label 1)
       - gene in BOTH activates and represses for that TF (contradictory
         annotation) -> abstain
       - otherwise (pert not a signature TF, or gene not a known target of
         that TF) -> abstain (None)
     This is scored with the SAME compute_metrics() used for the LLM, on
     the SAME test split, so it's a fair apples-to-apples baseline row.

Usage:
  python src/eval/baselines.py
  python src/eval/baselines.py --json /path/to/out.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import compute_metrics  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
KNOW = os.path.join(REPO, "data", "knowledge")

TASKS = {
    "T1a-DE": {
        "csv": os.path.join(REPO, "data", "runs", "deleteome_DE.csv"),
        "task": "de",
    },
    "T1b-DIR": {
        "csv": os.path.join(REPO, "data", "runs", "deleteome_DIR.csv"),
        "task": "dir",
    },
    "T2A-DE": {
        "csv": os.path.join(REPO, "data", "task2", "hillenmeyer_phenotype.csv"),
        "task": "growth",
    },
    "T2A-DIR": {
        "csv": os.path.join(REPO, "data", "task2", "hillenmeyer_direction.csv"),
        "task": "growth_dir",
    },
}


def load_test_rows(csv_path: str):
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["split"] == "test":
                rows.append((row["pert"], row.get("gene") or row.get("context"),
                             int(row["label"])))
    return rows


def majority_baseline(rows):
    """Always predict the test split's majority class. Returns compute_metrics
    output plus the raw majority-class stats used to derive it."""
    truth = [lab for _, _, lab in rows]
    n = len(truth)
    n_pos = sum(truth)
    n_neg = n - n_pos
    majority_label = 1 if n_pos >= n_neg else 0
    majority_ratio = max(n_pos, n_neg) / n if n else 0.0
    preds = [majority_label] * n
    return {
        "n_total": n,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "majority_label": majority_label,
        "majority_ratio": round(majority_ratio, 4),
    }, preds, truth


def random_baseline(rows, n_trials=200, seed=0):
    """Monte Carlo the uniform-random predictor: n_trials independent draws of
    a fresh random 0/1 label per test case, each scored against the SAME true
    labels with compute_metrics(); returns per-metric mean/stdev plus the
    single-trial predictions/truth (for a spot-check) and the raw per-trial
    metric lists."""
    import random

    truth = [lab for _, _, lab in rows]
    n = len(truth)
    rng = random.Random(seed)

    trials_metrics = []
    for _ in range(n_trials):
        preds = [rng.randint(0, 1) for _ in range(n)]
        trials_metrics.append((preds, truth))
    return trials_metrics, truth, n


def summarize_random_trials(trials_metrics, task):
    """Score every (preds, truth) trial with compute_metrics(task=...) and
    return {metric: (mean, stdev)} plus the list of raw metric dicts."""
    import statistics

    all_m = [compute_metrics(preds, truth, task) for preds, truth in trials_metrics]
    out = {}
    for key in ("acc_overall", "macro_f1", "mcc"):
        vals = [m[key] for m in all_m]
        out[key] = (round(statistics.mean(vals), 4),
                     round(statistics.pstdev(vals), 4) if len(vals) > 1 else 0.0)
    return out, all_m


def yeastract_sign_rule(rows, tf_targets):
    """Predict DIR label from YEASTRACT sign; abstain (None) when the rule
    can't determine a direction."""
    preds = []
    truth = []
    n_tf_pert = 0
    n_target_hit = 0
    n_conflict = 0
    for pert, gene, label in rows:
        truth.append(label)
        entry = tf_targets.get(pert)
        if entry is None:
            preds.append(None)
            continue
        n_tf_pert += 1
        activates = gene in entry.get("activates", [])
        represses = gene in entry.get("represses", [])
        if activates and represses:
            n_conflict += 1
            preds.append(None)
            continue
        if activates:
            n_target_hit += 1
            preds.append(0)  # lose an activator -> target expression Decrease
        elif represses:
            n_target_hit += 1
            preds.append(1)  # lose a repressor -> target expression Increase
        else:
            preds.append(None)
    stats = {
        "n_total": len(rows),
        "n_pert_is_signature_tf": n_tf_pert,
        "n_gene_is_known_target_with_unambiguous_sign": n_target_hit,
        "n_conflicting_sign_abstained": n_conflict,
    }
    return stats, preds, truth


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default=None, help="optional path to dump all results as JSON")
    args = ap.parse_args(argv)

    out = {}

    print("=" * 78)
    print("MAJORITY BASELINE (always predict the test split's majority class)")
    print("=" * 78)
    for name, cfg in TASKS.items():
        rows = load_test_rows(cfg["csv"])
        stats, preds, truth = majority_baseline(rows)
        m = compute_metrics(preds, truth, cfg["task"])
        print(f"\n--- {name} (test n={stats['n_total']}, "
              f"pos={stats['n_pos']}, neg={stats['n_neg']}) ---")
        print(f"  majority class = {stats['majority_label']} "
              f"(ratio={stats['majority_ratio']})")
        print(f"  Acc(overall)={m['acc_overall']}  macro-F1={m['macro_f1']}  "
              f"MCC={m['mcc']}  (f1_pos={m['f1_pos']}, f1_neg={m['f1_neg']})")
        out[f"{name}_majority"] = {"stats": stats, "metrics": m}

    print("\n" + "=" * 78)
    print("RANDOM BASELINE (uniform-random 0/1 per test case, Monte Carlo "
          "n_trials=200, seed=0)")
    print("=" * 78)
    for name, cfg in TASKS.items():
        rows = load_test_rows(cfg["csv"])
        trials_metrics, truth, n = random_baseline(rows, n_trials=200, seed=0)
        summary, all_m = summarize_random_trials(trials_metrics, cfg["task"])
        acc_mean, acc_sd = summary["acc_overall"]
        f1_mean, f1_sd = summary["macro_f1"]
        mcc_mean, mcc_sd = summary["mcc"]
        print(f"\n--- {name} (test n={n}, 200 Monte Carlo draws) ---")
        print(f"  Acc(overall)={acc_mean}+/-{acc_sd}  macro-F1={f1_mean}+/-{f1_sd}  "
              f"MCC={mcc_mean}+/-{mcc_sd}")
        out[f"{name}_random"] = {
            "n_trials": 200, "seed": 0, "n_total": n,
            "acc_overall_mean": acc_mean, "acc_overall_sd": acc_sd,
            "macro_f1_mean": f1_mean, "macro_f1_sd": f1_sd,
            "mcc_mean": mcc_mean, "mcc_sd": mcc_sd,
        }

    print("\n" + "=" * 78)
    print("YEASTRACT SIGN-RULE BASELINE (T1b-DIR only)")
    print("=" * 78)
    tf_targets = json.load(open(os.path.join(KNOW, "tf_targets.json"), encoding="utf-8"))
    rows = load_test_rows(TASKS["T1b-DIR"]["csv"])
    stats, preds, truth = yeastract_sign_rule(rows, tf_targets)
    m = compute_metrics(preds, truth, "dir")
    print(f"\n--- T1b-DIR (test n={stats['n_total']}) ---")
    print(f"  pert is a signature TF: {stats['n_pert_is_signature_tf']}")
    print(f"  of those, gene is a known target w/ unambiguous sign: "
          f"{stats['n_gene_is_known_target_with_unambiguous_sign']}")
    print(f"  conflicting sign (both activates & represses) -> abstained: "
          f"{stats['n_conflicting_sign_abstained']}")
    print(f"  Answered%={m['answered_pct']}  Acc(overall)={m['acc_overall']}  "
          f"Acc(answered)={m['acc_answered']}  macro-F1={m['macro_f1']}  MCC={m['mcc']}")
    out["T1b-DIR_yeastract_rule"] = {"stats": stats, "metrics": m}

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
