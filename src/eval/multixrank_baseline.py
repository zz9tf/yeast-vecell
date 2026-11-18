#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""""Variant 4" baseline: MultiXrank-style Random-Walk-with-Restart (RWR) proximity scores
fed into a supervised classifier (XGBoost), evaluated on the EXACT SAME train/test split
used for
the LLM (data/runs/deleteome_DE.csv / deleteome_DIR.csv, "split" column).

Design spec: docs/task_definitions.md Task 1 section 7 / docs/prompt_optimization.md
"变体4" -- guilt-by-association (McGary et al. 2007 style) supervised upgrade
(Baptista, Briere, Baudot 2024, BMC Bioinformatics 25:70).

Graph: reuses the exact same STRING+YEASTRACT graph construction as gat_baseline.py
(same nodes/edges) so the two "variant 4" methods are apples-to-apples on graph input.

RWR: personalized PageRank restarted at the `pert` node, evaluated at the `gene` node
(and vice versa, restart at gene evaluated at pert -- graph is undirected but RWR with
row-normalized transition is NOT symmetric, so both directions are informative features).
Only computed for the ~1.4k unique pert/gene nodes that actually appear as a query
endpoint in the CSV (not all ~7k graph nodes), since that's the only thing ever looked up
-- makes the O(iterations x nnz) power-iteration cost tractable without approximation.

Classifier: XGBoost on [rwr(pert->gene), rwr(gene->pert), common-neighbor count,
degree(pert), degree(gene), is_tf(pert/gene), is_esr(pert/gene), n_complex(pert/gene),
shared-complex flag] -- no LLM text, no target-encoding shortcut (that lookup-table
leakage risk is documented in gat_baseline.py's docstring; this script does NOT add it,
this is a deliberately "pure graph proximity" baseline for contrast).

Usage:
  python src/eval/multixrank_baseline.py --task de  --json data/runs/multixrank_baseline/multixrank_de.json
  python src/eval/multixrank_baseline.py --task dir --json data/runs/multixrank_baseline/multixrank_dir.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import compute_metrics  # noqa: E402
from gat_baseline import load_rows, load_knowledge, build_graph, TASK_CSV, TASK_METRIC  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))


def build_transition(edges, n_nodes):
    import numpy as np
    import scipy.sparse as sp

    src = [a for a, b in edges] + [b for a, b in edges]
    dst = [b for a, b in edges] + [a for a, b in edges]
    A = sp.csr_matrix((np.ones(len(src)), (src, dst)), shape=(n_nodes, n_nodes))
    deg = np.asarray(A.sum(axis=1)).flatten()
    deg[deg == 0] = 1.0
    Dinv = sp.diags(1.0 / deg)
    P = Dinv @ A  # row-normalized transition: P[i,j] = prob of moving i->j
    return A, P


def rwr_from_sources(P, source_idxs, n_nodes, restart_prob=0.15, n_iter=30):
    """Batched RWR: returns dict source_idx -> stationary-ish distribution (np.array),
    restarted at that single source node each time, power-iterated together as a
    (n_sources x n_nodes) matrix for speed."""
    import numpy as np

    m = len(source_idxs)
    r0 = np.zeros((m, P.shape[0]), dtype=np.float64)
    for i, s in enumerate(source_idxs):
        r0[i, s] = 1.0
    r = r0.copy()
    Pt = P.T.tocsr()  # so that r_next = r @ P  <=>  (Pt @ r.T).T
    for _ in range(n_iter):
        r = (1 - restart_prob) * (r @ P) + restart_prob * r0
    return r  # shape (m, n_nodes), row i = RWR dist restarted at source_idxs[i]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", required=True, choices=["de", "dir"])
    ap.add_argument("--json", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--restart-prob", type=float, default=0.15)
    ap.add_argument("--n-iter", type=int, default=30)
    ap.add_argument("--dump-preds", default=None,
                     help="also write per-case [{pert,gene,true,pred}] test predictions here "
                          "(used by decomposition slicing scripts)")
    args = ap.parse_args(argv)

    import numpy as np
    import math
    from xgboost import XGBClassifier

    t0 = time.time()
    csv_path = TASK_CSV[args.task]
    rows = load_rows(csv_path)
    close, tf_targets, esr, complex_members = load_knowledge()
    nodes, idx, edges, feats = build_graph(rows, close, tf_targets, esr, complex_members)
    n_nodes = len(nodes)
    print(f"[multixrank_baseline] task={args.task} nodes={n_nodes} edges={len(edges)}")

    A, P = build_transition(edges, n_nodes)
    is_tf = {n: feats[i][0] for i, n in enumerate(nodes)}
    is_esr = {n: feats[i][1] for i, n in enumerate(nodes)}
    log_ncomplex = {n: feats[i][2] for i, n in enumerate(nodes)}
    string_deg = {n: feats[i][3] for i, n in enumerate(nodes)}
    total_deg = {n: feats[i][4] for i, n in enumerate(nodes)}

    complex_sets = {g: set(cs) for g, cs in complex_members.items()}
    neighbor_sets = {}
    A_csr = A.tocsr()
    for i in range(n_nodes):
        neighbor_sets[i] = set(A_csr.indices[A_csr.indptr[i]:A_csr.indptr[i + 1]].tolist())

    query_nodes = sorted({idx[p] for p, g, y, s in rows} | {idx[g] for p, g, y, s in rows})
    print(f"[multixrank_baseline] computing RWR for {len(query_nodes)} query nodes "
          f"(restart_prob={args.restart_prob}, n_iter={args.n_iter}) ...")
    r = rwr_from_sources(P, query_nodes, n_nodes, args.restart_prob, args.n_iter)
    src_pos = {s: i for i, s in enumerate(query_nodes)}
    print(f"[multixrank_baseline] RWR done in {time.time() - t0:.1f}s")

    def feature_row(pert, gene):
        pi, gi = idx[pert], idx[gene]
        rwr_pg = r[src_pos[pi], gi]
        rwr_gp = r[src_pos[gi], pi]
        common_nb = len(neighbor_sets.get(pi, set()) & neighbor_sets.get(gi, set()))
        shared_complex = 1.0 if (complex_sets.get(pert, set()) &
                                  complex_sets.get(gene, set())) else 0.0
        return [
            math.log1p(rwr_pg * 1e6), math.log1p(rwr_gp * 1e6),
            math.log1p(common_nb),
            total_deg[pert], total_deg[gene],
            string_deg[pert], string_deg[gene],
            is_tf[pert], is_tf[gene],
            is_esr[pert], is_esr[gene],
            log_ncomplex[pert], log_ncomplex[gene],
            shared_complex,
        ]

    X, y, split, pg = [], [], [], []
    for pert, gene, label, s in rows:
        X.append(feature_row(pert, gene))
        y.append(label)
        split.append(s)
        pg.append((pert, gene))
    X = np.array(X, dtype=np.float64)
    y = np.array(y, dtype=np.int64)
    split = np.array(split)

    train_mask = split == "train"
    test_mask = split == "test"
    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]
    pg_test = [v for v, m in zip(pg, test_mask) if m]

    n_pos = int(y_train.sum())
    n_neg = len(y_train) - n_pos
    spw = n_neg / max(n_pos, 1)
    print(f"[multixrank_baseline] train={len(y_train)} test={len(y_test)} "
          f"scale_pos_weight={spw:.3f}")

    clf = XGBClassifier(
        n_estimators=300, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=spw, eval_metric="logloss",
        random_state=args.seed, n_jobs=8,
    )
    clf.fit(X_train, y_train)
    test_preds = clf.predict(X_test).tolist()
    test_m = compute_metrics(test_preds, y_test.tolist(), TASK_METRIC[args.task])
    print(f"[multixrank_baseline] TEST task={args.task} n={test_m['n_total']} "
          f"acc={test_m['acc_overall']} macro_f1={test_m['macro_f1']} mcc={test_m['mcc']}")

    if args.dump_preds:
        cases = [{"pert": p, "gene": g, "true": int(t), "pred": int(pr)}
                 for (p, g), t, pr in zip(pg_test, y_test.tolist(), test_preds)]
        os.makedirs(os.path.dirname(args.dump_preds), exist_ok=True) if os.path.dirname(args.dump_preds) else None
        with open(args.dump_preds, "w", encoding="utf-8") as f:
            json.dump(cases, f)
        print(f"wrote per-case preds: {args.dump_preds} ({len(cases)} cases)")

    out = {
        "task": args.task, "seed": args.seed,
        "restart_prob": args.restart_prob, "n_iter": args.n_iter,
        "n_nodes": n_nodes, "n_edges": len(edges),
        "n_train": len(y_train), "n_test": len(y_test),
        "test_metrics": test_m,
    }
    if args.json:
        os.makedirs(os.path.dirname(args.json), exist_ok=True) if os.path.dirname(args.json) else None
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"wrote {args.json}")
    print(f"[multixrank_baseline] done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
