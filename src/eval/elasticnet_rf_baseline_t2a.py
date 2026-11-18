#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""""Variant 4" baseline for Task 2A: sklearn Elastic Net (DE, continuous score
thresholded) + Random Forest (DIR) on hand-built genomics features, evaluated on the
EXACT SAME train/test split used for the LLM (data/task2/hillenmeyer_phenotype.csv /
hillenmeyer_direction.csv, "split" column).

Design spec: docs/task_definitions.md Task 2A section 7 / docs/prompt_optimization.md
"变体4" -- the GDSC/CCLE sister-field (human cancer drug-sensitivity prediction)
accepted baseline floor. Unlike src/eval/matrix_factorization_baseline.py (which uses
the gene x condition z-score matrix directly and needs a fold-in trick for cold-start
test genes), this script deliberately builds ONLY gene-level structural features (never
touches the raw z-score matrix for the target gene) + condition-level features -- so it
is a strict-cold-start method by construction, no fold-in ambiguity, directly comparable
to the LLM's information budget.

Features:
  gene side (from STRING+YEASTRACT graph, same source as gat_baseline.py):
    is_tf, is_esr, log1p(n_complexes), log1p(string_degree), log1p(total_degree)
  condition side (from data/task2/haphom_growth_contexts.csv):
    medium, phenotype, collection (one-hot), log1p(num_tested)
    + condition target-encoded positive rate (Laplace-smoothed, computed ONLY from
      fit-split rows -- legitimate because context ids are 100% shared between train/
      test in this split, unlike gene ids)

Usage:
  python src/eval/elasticnet_rf_baseline_t2a.py --task de  --json data/runs/elasticnet_rf_baseline/t2a_de.json
  python src/eval/elasticnet_rf_baseline_t2a.py --task dir --json data/runs/elasticnet_rf_baseline/t2a_dir.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import compute_metrics  # noqa: E402
from gat_baseline import load_knowledge, build_graph  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
TASK2_DIR = os.path.join(REPO, "data", "task2")

TASK_CSV = {
    "de": os.path.join(TASK2_DIR, "hillenmeyer_phenotype.csv"),
    "dir": os.path.join(TASK2_DIR, "hillenmeyer_direction.csv"),
}
TASK_METRIC = {"de": "growth", "dir": "growth_dir"}
CONTEXTS_CSV = os.path.join(TASK2_DIR, "haphom_growth_contexts.csv")


def load_rows(csv_path):
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append((row["pert"], row["context"], int(row["label"]), row["split"]))
    return rows


def load_context_meta():
    meta = {}
    with open(CONTEXTS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            meta[row["context"]] = row
    return meta


def build_gene_features():
    close, tf_targets, esr, complex_members = load_knowledge()
    # dummy rows just to seed the node set with these genes; build_graph unions in
    # every gene appearing in the KG assets regardless, so an empty pert/gene set here
    # is fine as long as we look up by ORF name afterward.
    nodes, idx, edges, feats = build_graph([], close, tf_targets, esr, complex_members)
    gfeat = {n: feats[i] for i, n in enumerate(nodes)}
    return gfeat


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", required=True, choices=["de", "dir"])
    ap.add_argument("--json", default=None)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    import numpy as np
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

    t0 = time.time()
    rows = load_rows(TASK_CSV[args.task])
    ctx_meta = load_context_meta()
    gfeat = build_gene_features()
    default_gfeat = [0.0, 0.0, 0.0, 0.0, 0.0]

    mediums = sorted({m["medium"] for m in ctx_meta.values()})
    phenotypes = sorted({m["phenotype"] for m in ctx_meta.values()})
    collections = sorted({m["collection"] for m in ctx_meta.values()})

    def onehot(val, vocab):
        return [1.0 if val == v else 0.0 for v in vocab]

    fit_rows = [(p, c, y) for p, c, y, s in rows if s == "train"]
    n_pos = sum(y for _, _, y in fit_rows)
    n_tot = len(fit_rows)
    global_rate = n_pos / n_tot if n_tot else 0.5
    alpha = 5.0
    ctx_sum, ctx_cnt = {}, {}
    for _, c, y in fit_rows:
        ctx_sum[c] = ctx_sum.get(c, 0) + y
        ctx_cnt[c] = ctx_cnt.get(c, 0) + 1

    def ctx_rate(c):
        s, n = ctx_sum.get(c, 0), ctx_cnt.get(c, 0)
        return (s + alpha * global_rate) / (n + alpha)

    def feature_row(pert, ctx):
        gf = gfeat.get(pert, default_gfeat)
        m = ctx_meta.get(ctx, {})
        num_tested = float(m.get("num_tested", 0) or 0)
        feats = list(gf)
        feats += onehot(m.get("medium", ""), mediums)
        feats += onehot(m.get("phenotype", ""), phenotypes)
        feats += onehot(m.get("collection", ""), collections)
        feats.append(math.log1p(num_tested))
        feats.append(ctx_rate(ctx))
        return feats

    X, y, split = [], [], []
    for pert, ctx, label, s in rows:
        X.append(feature_row(pert, ctx))
        y.append(label)
        split.append(s)
    X = np.array(X, dtype=np.float64)
    y = np.array(y, dtype=np.int64)
    split = np.array(split)

    train_mask, test_mask = split == "train", split == "test"
    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]
    print(f"[elasticnet_rf_t2a] task={args.task} n_train={len(y_train)} "
          f"n_test={len(y_test)} n_feat={X.shape[1]}")

    clf = RandomForestClassifier(
        n_estimators=400, max_depth=12, min_samples_leaf=5,
        class_weight="balanced", random_state=args.seed, n_jobs=8,
    )
    clf.fit(X_train, y_train)
    test_preds = clf.predict(X_test).tolist()
    test_m = compute_metrics(test_preds, y_test.tolist(), TASK_METRIC[args.task])
    print(f"[elasticnet_rf_t2a] TEST task={args.task} n={test_m['n_total']} "
          f"acc={test_m['acc_overall']} macro_f1={test_m['macro_f1']} mcc={test_m['mcc']}")

    out = {
        "task": args.task, "seed": args.seed, "model": "RandomForestClassifier",
        "n_train": len(y_train), "n_test": len(y_test), "n_feat": int(X.shape[1]),
        "test_metrics": test_m,
    }
    if args.json:
        os.makedirs(os.path.dirname(args.json), exist_ok=True) if os.path.dirname(args.json) else None
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"wrote {args.json}")
    print(f"[elasticnet_rf_t2a] done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
