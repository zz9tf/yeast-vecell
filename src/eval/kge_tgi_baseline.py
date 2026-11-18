#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""""Variant 4" baseline for Task 1: a KGE-TGI-style Multi-subgraph GCN link
classifier, evaluated on the EXACT SAME train/test split used for the LLM
(data/runs/deleteome_DE.csv / deleteome_DIR.csv, "split" column).

Design rationale / method spec: docs/prompt_optimization.md "变体4" section,
docs/task_definitions.md Task 1 "7. 已知的pipeline变体" KGE-TGI entry.
Original method: Wu et al. 2023, PLOS Computational Biology 19(6):e1011207 --
split a heterogeneous KG by relation type and run a SEPARATE graph
convolution over each relation-specific subgraph, then combine the
relation-specific node embeddings for a joint "does this edge exist, and
what sign" classification. We move from their TRRUST (human, curated)
TF->target database to YEASTRACT (data/knowledge/tf_targets.json), which
already ships exactly two typed relations per TF -- 'activates' and
'represses' -- a direct match for "existence + direction jointly".

What is genuinely different here from gat_baseline.py / multixrank_baseline.py
/ genki_baseline.py:
  1. Graph: ONLY the YEASTRACT TF->target KG (data/knowledge/tf_targets.json),
     split into TWO typed, DIRECTED subgraphs (activates, represses) -- NOT
     merged into one undirected graph the way gat_baseline.py combines
     STRING+YEASTRACT, and NOT STRING at all (no PPI/co-expression signal).
  2. Encoder: two INDEPENDENT stacks of GCNConv, one per relation type, whose
     outputs are concatenated per node ("multi-subgraph GCN" -- literally
     the architecture name in the paper) rather than one shared attention
     layer over a single relation-agnostic adjacency (GAT's design).
  3. Task head: still a supervised (pert,gene) pair classifier trained end to
     end on the DE/DIR train-split labels (this part IS shared in spirit
     with gat_baseline.py -- both are "train a link classifier on the same
     split" -- the difference this variant is meant to isolate is purely
     "does relation-typed multi-subgraph convolution over a clean, curated
     TF->target KG do better/worse than a single merged STRING+YEASTRACT
     graph", not "supervised vs unsupervised", which is GenKI's axis).

Node features: is_tf, log1p(activates-subgraph in/out degree), log1p(
represses-subgraph in/out degree) + the SAME train-only Laplace-smoothed
target-encoding features used by gat_baseline.py (empirical positive rate of
this node when it plays the pert/gene role, computed only from train-split
rows) so that the "does the graph representation add anything on top of the
base-rate lookup" question is asked on a level playing field with GAT/
MultiXrank rather than being answered by "we forgot to give it the same
base-rate feature" (see gat_baseline.py's own Gene-majority caveat).

Usage:
  python src/eval/kge_tgi_baseline.py --task de  --epochs 40 --json out/kge_de.json
  python src/eval/kge_tgi_baseline.py --task dir --epochs 40 --json out/kge_dir.json

Requires torch + torch_geometric (CPU; TF->target KG alone is far smaller
than the STRING+YEASTRACT union used by gat_baseline.py). No GPU / side-
channel dispatch used.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
import time

# Reproducibility fix (2026-07-22): same issue as genki_baseline.py -- torch's
# default multi-threaded CPU BLAS is not bit-reproducible across runs, and
# compounds over 40 epochs + early stopping into materially different results
# even with an identical --seed (verified: two --seed 0 --task dir runs
# differed by macro_f1 .642 vs .692, mcc .327 vs .428, early-stop epoch 22 vs
# 40, before this fix). Pinning to 1 thread before torch loads its BLAS
# backend makes --seed fully reproducible (verified identical across repeats
# after this fix). Must be set before torch is imported anywhere below.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import compute_metrics  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
KNOW = os.path.join(REPO, "data", "knowledge")
RUNS = os.path.join(REPO, "data", "runs")

TASK_CSV = {
    "de": os.path.join(RUNS, "deleteome_DE.csv"),
    "dir": os.path.join(RUNS, "deleteome_DIR.csv"),
}
TASK_METRIC = {"de": "de", "dir": "dir"}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_rows(csv_path):
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append((row["pert"], row["gene"], int(row["label"]), row["split"]))
    return rows


def load_tf_targets():
    return json.load(open(os.path.join(KNOW, "tf_targets.json"), encoding="utf-8"))


# ---------------------------------------------------------------------------
# Graph construction: two relation-typed DIRECTED subgraphs (TF -> target)
# ---------------------------------------------------------------------------

def build_relation_graphs(rows, tf_targets):
    node_ids = set()
    for pert, gene, _, _ in rows:
        node_ids.add(pert)
        node_ids.add(gene)
    node_ids.update(tf_targets.keys())
    for v in tf_targets.values():
        node_ids.update(v.get("activates", []))
        node_ids.update(v.get("represses", []))

    nodes = sorted(node_ids)
    idx = {g: i for i, g in enumerate(nodes)}
    n = len(nodes)

    act_edges, rep_edges = [], []
    for tf, v in tf_targets.items():
        ti = idx[tf]
        for tgt in v.get("activates", []):
            gi = idx[tgt]
            if ti != gi:
                act_edges.append((ti, gi))
        for tgt in v.get("represses", []):
            gi = idx[tgt]
            if ti != gi:
                rep_edges.append((ti, gi))

    is_tf = [0.0] * n
    for tf in tf_targets:
        is_tf[idx[tf]] = 1.0

    act_out_deg, act_in_deg = [0] * n, [0] * n
    for a, b in act_edges:
        act_out_deg[a] += 1
        act_in_deg[b] += 1
    rep_out_deg, rep_in_deg = [0] * n, [0] * n
    for a, b in rep_edges:
        rep_out_deg[a] += 1
        rep_in_deg[b] += 1

    feats = []
    for i in range(n):
        feats.append([
            is_tf[i],
            math.log1p(act_out_deg[i]), math.log1p(act_in_deg[i]),
            math.log1p(rep_out_deg[i]), math.log1p(rep_in_deg[i]),
        ])

    return nodes, idx, act_edges, rep_edges, feats


# ---------------------------------------------------------------------------
# Model: two independent GCNConv stacks (one per relation), concatenated
# ---------------------------------------------------------------------------

def make_model(n_nodes, feat_dim, emb_dim=16, hidden=24, seed=0):
    import torch
    import torch.nn as nn
    from torch_geometric.nn import GCNConv

    torch.manual_seed(seed)
    torch.set_num_threads(1)  # belt-and-suspenders, see module-top env vars

    class MultiSubgraphGCN(nn.Module):
        def __init__(self):
            super().__init__()
            self.node_emb = nn.Embedding(n_nodes, emb_dim)
            self.in_proj = nn.Linear(emb_dim + feat_dim, hidden)
            self.act = nn.ReLU()
            self.dropout = nn.Dropout(0.2)

            # relation-specific subgraph 1: "activates"
            self.gcn_act1 = GCNConv(hidden, hidden)
            self.gcn_act2 = GCNConv(hidden, hidden)
            # relation-specific subgraph 2: "represses"
            self.gcn_rep1 = GCNConv(hidden, hidden)
            self.gcn_rep2 = GCNConv(hidden, hidden)

            self.combine = nn.Linear(hidden * 2, hidden)
            self.head = nn.Sequential(
                nn.Linear(hidden * 3, hidden),
                nn.ELU(),
                nn.Dropout(0.2),
                nn.Linear(hidden, 1),
            )

        def encode(self, x_struct, act_edge_index, rep_edge_index):
            x0 = torch.cat([self.node_emb.weight, x_struct], dim=1)
            x0 = self.dropout(self.act(self.in_proj(x0)))

            h_act = self.act(self.gcn_act1(x0, act_edge_index))
            h_act = self.dropout(h_act)
            h_act = self.gcn_act2(h_act, act_edge_index)

            h_rep = self.act(self.gcn_rep1(x0, rep_edge_index))
            h_rep = self.dropout(h_rep)
            h_rep = self.gcn_rep2(h_rep, rep_edge_index)

            h = self.combine(torch.cat([h_act, h_rep], dim=1))
            return h

        def predict(self, h, left_idx, right_idx):
            hl, hr = h[left_idx], h[right_idx]
            z = torch.cat([hl, hr, (hl - hr).abs()], dim=1)
            return self.head(z).squeeze(-1)

    return MultiSubgraphGCN()


# ---------------------------------------------------------------------------
# Train / eval
# ---------------------------------------------------------------------------

def run(task, epochs=40, batch_size=4096, lr=0.01, seed=0, val_frac=0.1,
        patience=6, out_json=None, verbose=True, dump_preds=None):
    import torch
    import torch.nn.functional as F

    csv_path = TASK_CSV[task]
    rows = load_rows(csv_path)
    tf_targets = load_tf_targets()
    nodes, idx, act_edges, rep_edges, feats = build_relation_graphs(rows, tf_targets)
    n_nodes = len(nodes)
    if verbose:
        print(f"[kge_tgi_baseline] task={task} nodes={n_nodes} "
              f"activates_edges={len(act_edges)} represses_edges={len(rep_edges)}")

    def to_edge_index(edges):
        if not edges:
            return torch.zeros((2, 0), dtype=torch.long)
        return torch.tensor(edges, dtype=torch.long).t().contiguous()

    act_edge_index = to_edge_index(act_edges)
    rep_edge_index = to_edge_index(rep_edges)
    x_struct = torch.tensor(feats, dtype=torch.float32)

    train_rows = [(p, g, y) for p, g, y, s in rows if s == "train"]
    test_rows = [(p, g, y) for p, g, y, s in rows if s == "test"]

    rng = random.Random(seed)
    train_rows_shuf = train_rows[:]
    rng.shuffle(train_rows_shuf)
    n_val = max(1, int(len(train_rows_shuf) * val_frac))
    val_rows = train_rows_shuf[:n_val]
    fit_rows = train_rows_shuf[n_val:]

    def to_tensors(rr):
        li = torch.tensor([idx[p] for p, g, y in rr], dtype=torch.long)
        ri = torch.tensor([idx[g] for p, g, y in rr], dtype=torch.long)
        y = torch.tensor([y for p, g, y in rr], dtype=torch.float32)
        return li, ri, y

    fit_li, fit_ri, fit_y = to_tensors(fit_rows)
    val_li, val_ri, val_y = to_tensors(val_rows)
    test_li, test_ri, test_y = to_tensors(test_rows)

    # target-encoding features, TRAIN-fit-split only (mirrors gat_baseline.py)
    global_rate = (sum(y for _, _, y in fit_rows) / len(fit_rows)) if fit_rows else 0.5
    pert_sum, pert_cnt, gene_sum, gene_cnt = {}, {}, {}, {}
    for p, g, y in fit_rows:
        pert_sum[p] = pert_sum.get(p, 0) + y
        pert_cnt[p] = pert_cnt.get(p, 0) + 1
        gene_sum[g] = gene_sum.get(g, 0) + y
        gene_cnt[g] = gene_cnt.get(g, 0) + 1
    alpha = 5.0
    extra_feats = []
    for node in nodes:
        pc, ps = pert_cnt.get(node, 0), pert_sum.get(node, 0)
        gc, gs = gene_cnt.get(node, 0), gene_sum.get(node, 0)
        rate_pert = (ps + alpha * global_rate) / (pc + alpha)
        rate_gene = (gs + alpha * global_rate) / (gc + alpha)
        extra_feats.append([rate_pert, rate_gene, math.log1p(pc), math.log1p(gc)])
    x_struct = torch.cat([x_struct, torch.tensor(extra_feats, dtype=torch.float32)], dim=1)
    if verbose:
        print(f"[kge_tgi_baseline] added target-encoding features (fit-only), "
              f"global_rate={global_rate:.4f}, x_struct dim={x_struct.shape[1]}")

    n_pos = sum(y for _, _, y in fit_rows)
    n_neg = len(fit_rows) - n_pos
    pos_weight = torch.tensor([n_neg / max(n_pos, 1)], dtype=torch.float32)

    model = make_model(n_nodes, x_struct.shape[1], seed=seed)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)

    best_val_f1, best_state, bad_epochs = -1.0, None, 0
    n_fit = len(fit_rows)
    epoch = 0

    for epoch in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(n_fit)
        total_loss = 0.0
        for start in range(0, n_fit, batch_size):
            b = perm[start:start + batch_size]
            opt.zero_grad()
            h = model.encode(x_struct, act_edge_index, rep_edge_index)
            logits = model.predict(h, fit_li[b], fit_ri[b])
            loss = F.binary_cross_entropy_with_logits(logits, fit_y[b], pos_weight=pos_weight)
            loss.backward()
            opt.step()
            total_loss += loss.item() * len(b)
        total_loss /= n_fit

        model.eval()
        with torch.no_grad():
            h = model.encode(x_struct, act_edge_index, rep_edge_index)
            val_logits = model.predict(h, val_li, val_ri)
            val_preds = (torch.sigmoid(val_logits) >= 0.5).long().tolist()
        val_m = compute_metrics(val_preds, val_y.long().tolist(), TASK_METRIC[task])
        if verbose:
            print(f"  epoch {epoch:2d}  loss={total_loss:.4f}  "
                  f"val_macroF1={val_m['macro_f1']:.4f}  val_mcc={val_m['mcc']:.4f}")

        if val_m["macro_f1"] > best_val_f1:
            best_val_f1 = val_m["macro_f1"]
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            bad_epochs = 0
        else:
            bad_epochs += 1
            if bad_epochs >= patience:
                if verbose:
                    print(f"  early stop at epoch {epoch} (best val macro_f1={best_val_f1:.4f})")
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    model.eval()
    with torch.no_grad():
        h = model.encode(x_struct, act_edge_index, rep_edge_index)
        test_logits = model.predict(h, test_li, test_ri)
        test_preds = (torch.sigmoid(test_logits) >= 0.5).long().tolist()
    test_m = compute_metrics(test_preds, test_y.long().tolist(), TASK_METRIC[task])
    if verbose:
        print(f"[kge_tgi_baseline] TEST task={task} n={test_m['n_total']} "
              f"acc={test_m['acc_overall']} macro_f1={test_m['macro_f1']} mcc={test_m['mcc']}")

    if dump_preds:
        cases = [{"pert": p, "gene": g, "true": int(y), "pred": int(pr)}
                 for (p, g, y), pr in zip(test_rows, test_preds)]
        os.makedirs(os.path.dirname(dump_preds), exist_ok=True) if os.path.dirname(dump_preds) else None
        with open(dump_preds, "w", encoding="utf-8") as f:
            json.dump(cases, f)
        if verbose:
            print(f"wrote per-case preds: {dump_preds} ({len(cases)} cases)")

    out = {
        "task": task, "seed": seed, "epochs_run": epoch, "best_val_macro_f1": best_val_f1,
        "n_nodes": n_nodes, "n_activates_edges": len(act_edges), "n_represses_edges": len(rep_edges),
        "n_fit": len(fit_rows), "n_val": len(val_rows), "n_test": len(test_rows),
        "test_metrics": test_m,
    }
    if out_json:
        os.makedirs(os.path.dirname(out_json), exist_ok=True) if os.path.dirname(out_json) else None
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        if verbose:
            print(f"wrote {out_json}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", required=True, choices=["de", "dir"])
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch-size", type=int, default=4096)
    ap.add_argument("--lr", type=float, default=0.01)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--patience", type=int, default=6)
    ap.add_argument("--json", default=None)
    ap.add_argument("--dump-preds", default=None,
                     help="also write per-case [{pert,gene,true,pred}] test predictions here "
                          "(used by decomposition slicing scripts)")
    args = ap.parse_args(argv)

    t0 = time.time()
    run(args.task, epochs=args.epochs, batch_size=args.batch_size, lr=args.lr,
        seed=args.seed, patience=args.patience, out_json=args.json,
        dump_preds=args.dump_preds)
    print(f"[kge_tgi_baseline] done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
