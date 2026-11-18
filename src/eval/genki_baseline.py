#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""""Variant 4" baseline for Task 1: GenKI-style VGAE (Variational Graph
Autoencoder) with a "virtual knockout" readout, evaluated on the EXACT SAME
train/test split used for the LLM (data/runs/deleteome_DE.csv /
deleteome_DIR.csv, "split" column).

Design rationale / method spec: docs/prompt_optimization.md "变体4" section,
docs/task_definitions.md Task 1 "7. 已知的pipeline变体" GenKI entry. Original
method: Yang et al. 2023, Nucleic Acids Research 51(13):6578-6592 -- train a
VGAE on a wild-type gene regulatory network + wild-type expression, then
simulate a knockout by removing the deleted gene from the graph and looking
at how much the VGAE's reconstruction of each other gene's representation
shifts. Genes with the largest shift are predicted DE.

What is genuinely different here from gat_baseline.py / multixrank_baseline.py
(both of which reuse the same curated STRING+YEASTRACT graph and train a
SUPERVISED classifier on (pert,gene)->label):
  1. Graph: NOT STRING/YEASTRACT. A co-expression network is derived directly
     from the wild-type-dominated expression data itself (see "GRN
     construction" below) -- this is what "推导出的GRN" (a GRN *derived from*
     the expression data) means for GenKI, as opposed to a database lookup.
  2. Node features: the gene's own baseline expression level/variability
     (mean, std of the microarray "A" -- average log2 intensity -- channel
     across ~1487 deletion experiments), not structural KG features
     (is_tf/is_esr/complex counts) as used by gat_baseline.py.
  3. Training objective: fully UNSUPERVISED (graph+attribute reconstruction
     only). The DE/DIR train-split labels are used ONLY post-hoc, to pick a
     scalar decision threshold on the unsupervised knockout-shift score --
     never to fit the encoder/decoder weights themselves. This is the
     structural hallmark of the GenKI approach (no label ever touches the
     representation-learning step) and is the main methodological contrast
     with the other three Variant-4 baselines.
  4. Readout: NOT a learned pair classifier. It is the model literally
     re-running its own encoder on a graph with the perturbed gene's outgoing
     edges removed and its own feature zeroed ("virtual knockout"), and
     scoring every other node by how much its latent representation moved.

GRN construction (approximation, documented honestly -- see module docstring
below the class definitions and the results write-up in task_results.md):
  The Deleteome raw matrix (data/perturbation/deleteome_all_mutants_ex_wt_var_
  controls.txt) does not ship a pure wild-type-only replicate set (the file
  name itself says "_ex_wt_var_controls", i.e. WT-vs-WT control arrays were
  excluded). What IS available for every one of the ~1487 deletion arrays is
  an "A" column: on a two-colour array, A = average log2 intensity of the
  mutant and WT channels for that reporter. Across ~1487 independent arrays,
  A is completely dominated by each gene's own typical transcript abundance
  (the single-gene deletion's effect on any one array's A value is a small
  perturbation on top of that baseline), so the ~1487-long A-profile per gene
  is used here as a WT-expression-level proxy, and the co-expression network
  is built from Pearson correlation between these per-gene A-profiles
  (mutual top-K nearest neighbours, K=15, |r| ranked). This is NOT the same
  computation used to derive DE/DIR labels (labels come from the M column
  after per-array normalisation + a p-value/|M| threshold; A is a different,
  much less label-informative axis), so this is not circular/leaking, but it
  is an approximation of "true" wild-type expression and is reported as such.

Usage:
  python src/eval/genki_baseline.py --task de  --json out/genki_de.json
  python src/eval/genki_baseline.py --task dir --json out/genki_dir.json

Requires torch + torch_geometric (CPU; graph is ~6-8k nodes / ~90k directed
kNN edges, full-graph forward pass is milliseconds; ~1.5k virtual-knockout
forward passes total across train+test perts, still seconds on CPU). No
GPU / side-channel dispatch used.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time

# Reproducibility fix (2026-07-22): torch's default multi-threaded CPU BLAS
# ops are NOT bit-reproducible across runs (floating-point non-associativity
# under thread scheduling races), which over ~60 training epochs compounds
# into materially different results even with an identical --seed (verified:
# two --seed 0 runs differed by macro_f1 .493 vs .4925, mcc .017 vs .025
# before this fix). Pinning to 1 thread before torch/numpy load their BLAS
# backend makes --seed fully reproducible (verified: identical results across
# repeated runs after this fix). Must be set before torch is imported anywhere
# below (torch is imported lazily inside functions), so this goes at module
# top right after `import os`.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import compute_metrics  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
PERT_DIR = os.path.join(REPO, "data", "perturbation")
RUNS = os.path.join(REPO, "data", "runs")
RAW_MATRIX = os.path.join(PERT_DIR, "deleteome_all_mutants_ex_wt_var_controls.txt")

TASK_CSV = {
    "de": os.path.join(RUNS, "deleteome_DE.csv"),
    "dir": os.path.join(RUNS, "deleteome_DIR.csv"),
}
TASK_METRIC = {"de": "de", "dir": "dir"}

K_NEIGHBORS = 15
EMB_DIM = 16
HIDDEN = 32
EPOCHS = 60
SEED = 0


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_rows(csv_path):
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append((row["pert"], row["gene"], int(row["label"]), row["split"]))
    return rows


def load_expression_profiles():
    """Return (genes: List[str], A: np.ndarray[n_genes, n_conditions])."""
    import pandas as pd

    cols = pd.read_csv(RAW_MATRIX, sep="\t", nrows=0).columns.tolist()
    n = len(cols)
    n_cond = (n - 3) // 3
    a_idx = [1] + [3 + 3 * c + 1 for c in range(n_cond)]  # systematicName + A cols
    a_cols = [cols[i] for i in a_idx]
    df = pd.read_csv(RAW_MATRIX, sep="\t", usecols=a_cols, skiprows=[1])
    df = df.groupby("systematicName").mean(numeric_only=True)
    return df.index.tolist(), df.values.astype("float32")


# ---------------------------------------------------------------------------
# GRN construction: mutual top-K correlation network over A-profiles
# ---------------------------------------------------------------------------

def build_coexpression_graph(genes, A, k=K_NEIGHBORS):
    import numpy as np

    Xc = A - A.mean(axis=1, keepdims=True)
    Xc = Xc / (Xc.std(axis=1, keepdims=True) + 1e-8)
    C = (Xc @ Xc.T) / Xc.shape[1]
    n = len(genes)
    np.fill_diagonal(C, 0.0)
    idx_top = np.argpartition(-np.abs(C), k, axis=1)[:, :k]
    edges = set()
    for i in range(n):
        for j in idx_top[i]:
            j = int(j)
            if i == j:
                continue
            edges.add((min(i, j), max(i, j)))
    return list(edges), C


# ---------------------------------------------------------------------------
# Model: 2-layer GCN encoder -> (mu, logvar); inner-product edge decoder +
# linear attribute decoder, trained jointly, fully unsupervised.
# ---------------------------------------------------------------------------

def make_model(n_nodes, feat_dim, emb_dim=EMB_DIM, hidden=HIDDEN, seed=SEED):
    import torch
    import torch.nn as nn
    from torch_geometric.nn import GCNConv

    torch.manual_seed(seed)
    torch.set_num_threads(1)  # belt-and-suspenders, see module-top env vars

    class GenKIVGAE(nn.Module):
        def __init__(self):
            super().__init__()
            self.node_emb = nn.Embedding(n_nodes, emb_dim)
            self.in_proj = nn.Linear(emb_dim + feat_dim, hidden)
            self.gcn1 = GCNConv(hidden, hidden)
            self.gcn_mu = GCNConv(hidden, hidden)
            self.gcn_logvar = GCNConv(hidden, hidden)
            self.act = nn.ReLU()
            self.attr_dec = nn.Linear(hidden, feat_dim)

        def encode(self, x_struct, edge_index):
            x = torch.cat([self.node_emb.weight, x_struct], dim=1)
            x = self.act(self.in_proj(x))
            x = self.act(self.gcn1(x, edge_index))
            mu = self.gcn_mu(x, edge_index)
            logvar = self.gcn_logvar(x, edge_index)
            return mu, logvar

        def reparameterize(self, mu, logvar):
            std = torch.exp(0.5 * logvar)
            return mu + torch.randn_like(std) * std

        def decode_edges(self, z, edge_index):
            src, dst = edge_index
            return (z[src] * z[dst]).sum(dim=-1)

        def decode_attr(self, z):
            return self.attr_dec(z)

    return GenKIVGAE()


def train_vgae(model, x_struct, edge_index, n_nodes, epochs=EPOCHS, lr=0.01, seed=SEED,
                verbose=True):
    import torch
    import torch.nn.functional as F
    from torch_geometric.utils import negative_sampling

    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    rng = torch.Generator().manual_seed(seed)
    for epoch in range(1, epochs + 1):
        model.train()
        opt.zero_grad()
        mu, logvar = model.encode(x_struct, edge_index)
        z = model.reparameterize(mu, logvar)

        pos_logits = model.decode_edges(z, edge_index)
        neg_edge_index = negative_sampling(
            edge_index, num_nodes=n_nodes, num_neg_samples=edge_index.size(1))
        neg_logits = model.decode_edges(z, neg_edge_index)
        edge_labels = torch.cat([torch.ones(pos_logits.size(0)),
                                  torch.zeros(neg_logits.size(0))])
        edge_logits = torch.cat([pos_logits, neg_logits])
        recon_loss = F.binary_cross_entropy_with_logits(edge_logits, edge_labels)

        kl_loss = -0.5 / n_nodes * torch.mean(
            torch.sum(1 + logvar - mu.pow(2) - logvar.exp(), dim=1))

        attr_pred = model.decode_attr(z)
        attr_loss = F.mse_loss(attr_pred, x_struct)

        loss = recon_loss + 0.001 * kl_loss + 0.5 * attr_loss
        loss.backward()
        opt.step()
        if verbose and (epoch % 10 == 0 or epoch == 1):
            print(f"  epoch {epoch:2d}  recon={recon_loss.item():.4f} "
                  f"kl={kl_loss.item():.4f} attr={attr_loss.item():.4f}")
    return model


# ---------------------------------------------------------------------------
# Virtual knockout
# ---------------------------------------------------------------------------

def knockout_edge_index(edge_index, node_idx):
    """Remove all edges where `node_idx` is the SOURCE (its outgoing
    regulatory/co-expression influence is deleted); edges where it is only a
    target are kept (other genes' influence on remaining nodes is untouched).
    """
    import torch

    src = edge_index[0]
    keep = src != node_idx
    return edge_index[:, keep]


def virtual_knockout_scores(model, x_struct, edge_index, mu_wt, attr_wt_dec, node_idx):
    """Return (delta_l2: Tensor[n_nodes], delta_attr: Tensor[n_nodes, feat_dim])
    -- shift in latent mu and in decoded attribute space for every node when
    `node_idx` is virtually knocked out (edges removed + feature zeroed)."""
    import torch

    x_ko = x_struct.clone()
    x_ko[node_idx] = 0.0
    ei_ko = knockout_edge_index(edge_index, node_idx)
    with torch.no_grad():
        mu_ko, _ = model.encode(x_ko, ei_ko)
        attr_ko_dec = model.decode_attr(mu_ko)
    delta_l2 = (mu_ko - mu_wt).pow(2).sum(dim=1).sqrt()
    delta_attr = attr_ko_dec - attr_wt_dec
    return delta_l2, delta_attr


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(task, epochs=EPOCHS, k=K_NEIGHBORS, seed=SEED, out_json=None, verbose=True,
        dump_preds=None):
    import numpy as np
    import torch

    csv_path = TASK_CSV[task]
    rows = load_rows(csv_path)

    genes, A = load_expression_profiles()
    gene_set_expr = set(genes)

    # node universe = genes with expression data UNION every pert/gene that
    # appears in the CSV (a handful of CSV IDs may not have raw-matrix rows;
    # those get mean-imputed features and are isolated / low-degree nodes).
    csv_nodes = set()
    for p, g, _, _ in rows:
        csv_nodes.add(p)
        csv_nodes.add(g)
    extra = sorted(csv_nodes - gene_set_expr)
    all_genes = genes + extra
    n = len(all_genes)
    idx = {g: i for i, g in enumerate(all_genes)}
    if verbose:
        print(f"[genki_baseline] task={task} n_nodes={n} "
              f"(expr-covered={len(genes)}, csv-only={len(extra)})")

    mean_A = A.mean(axis=1)
    std_A = A.std(axis=1)
    global_mean_A, global_std_A = float(mean_A.mean()), float(std_A.mean())

    edges, _C = build_coexpression_graph(genes, A, k=k)
    if verbose:
        print(f"[genki_baseline] co-expression graph: {len(edges)} undirected edge pairs "
              f"(top-{k} mutual |r| neighbours over {A.shape[1]} arrays)")

    # directed edge_index: co-expression treated as symmetric influence (both directions)
    ei = []
    for a, b in edges:
        ei.append((a, b))
        ei.append((b, a))
    edge_index = torch.tensor(ei, dtype=torch.long).t().contiguous()

    # node features: [z(mean_A), z(std_A)] using expr-covered genes' own stats;
    # csv-only genes (no expression row) get 0.0 (mean-imputed in z-space).
    mA = (mean_A - mean_A.mean()) / (mean_A.std() + 1e-8)
    sA = (std_A - std_A.mean()) / (std_A.std() + 1e-8)
    feats = np.zeros((n, 2), dtype="float32")
    for i, g in enumerate(genes):
        feats[i, 0] = mA[i]
        feats[i, 1] = sA[i]
    x_struct = torch.tensor(feats, dtype=torch.float32)

    model = make_model(n, x_struct.shape[1], seed=seed)
    t0 = time.time()
    train_vgae(model, x_struct, edge_index, n, epochs=epochs, seed=seed, verbose=verbose)
    if verbose:
        print(f"[genki_baseline] VGAE trained (unsupervised, no DE/DIR labels used) "
              f"in {time.time()-t0:.1f}s")

    model.eval()
    with torch.no_grad():
        mu_wt, _ = model.encode(x_struct, edge_index)
        attr_wt_dec = model.decode_attr(mu_wt)

    # cache virtual-knockout scores per unique pert (unsupervised -- safe to
    # compute for both train and test perts, no label ever enters this step)
    train_rows = [(p, g, y) for p, g, y, s in rows if s == "train"]
    test_rows = [(p, g, y) for p, g, y, s in rows if s == "test"]
    unique_perts = sorted(set(p for p, _, _ in train_rows) | set(p for p, _, _ in test_rows))
    unique_perts = [p for p in unique_perts if p in idx]
    if verbose:
        print(f"[genki_baseline] computing virtual knockouts for "
              f"{len(unique_perts)} unique perts...")
    t0 = time.time()
    l2_cache, attr_cache = {}, {}
    for ii, p in enumerate(unique_perts):
        pi = idx[p]
        delta_l2, delta_attr = virtual_knockout_scores(
            model, x_struct, edge_index, mu_wt, attr_wt_dec, pi)
        l2_cache[p] = delta_l2.numpy()
        attr_cache[p] = delta_attr[:, 0].numpy()  # dim 0 = mean_A channel
        if verbose and (ii + 1) % 100 == 0:
            print(f"  knockout {ii+1}/{len(unique_perts)}  "
                  f"({time.time()-t0:.1f}s elapsed)", flush=True)
    if verbose:
        print(f"[genki_baseline] knockouts computed in {time.time()-t0:.1f}s")

    def score_rows(rr):
        s_l2, s_attr, truth = [], [], []
        n_missing = 0
        for p, g, y in rr:
            if p not in l2_cache or g not in idx:
                n_missing += 1
                s_l2.append(0.0)
                s_attr.append(0.0)
                truth.append(y)
                continue
            gi = idx[g]
            s_l2.append(float(l2_cache[p][gi]))
            s_attr.append(float(attr_cache[p][gi]))
            truth.append(y)
        return np.array(s_l2), np.array(s_attr), np.array(truth), n_missing

    train_l2, train_attr, train_y, train_missing = score_rows(train_rows)
    test_l2, test_attr, test_y, test_missing = score_rows(test_rows)
    if verbose:
        print(f"[genki_baseline] train rows scored: {len(train_rows)} "
              f"({train_missing} missing pert/gene node), "
              f"test rows scored: {len(test_rows)} ({test_missing} missing)")

    # ---- DE threshold: sweep on TRAIN split only ----
    best_thr, best_f1 = 0.0, -1.0
    lo, hi = float(train_l2.min()), float(train_l2.max())
    for thr in np.linspace(lo, hi, 200):
        pred = (train_l2 >= thr).astype(int)
        tp = int(((pred == 1) & (train_y == 1)).sum())
        fp = int(((pred == 1) & (train_y == 0)).sum())
        fn = int(((pred == 0) & (train_y == 1)).sum())
        tn = int(((pred == 0) & (train_y == 0)).sum())
        f1p = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
        f1n = 2 * tn / (2 * tn + fn + fp) if (2 * tn + fn + fp) else 0.0
        macro = (f1p + f1n) / 2
        if macro > best_f1:
            best_f1, best_thr = macro, thr
    if verbose:
        print(f"[genki_baseline] DE threshold calibrated on TRAIN split: "
              f"l2>={best_thr:.4f} (train macro-F1={best_f1:.4f})")

    if task == "de":
        test_preds = (test_l2 >= best_thr).astype(int).tolist()
        test_m = compute_metrics(test_preds, test_y.astype(int).tolist(), "de")
        if dump_preds:
            cases = [{"pert": p, "gene": g, "true": int(y), "pred": int(pr)}
                     for (p, g, y), pr in zip(test_rows, test_preds)]
            os.makedirs(os.path.dirname(dump_preds), exist_ok=True) if os.path.dirname(dump_preds) else None
            with open(dump_preds, "w", encoding="utf-8") as f:
                json.dump(cases, f)
        out = {"task": "de", "n_nodes": n, "n_edges": len(edges),
               "n_train": len(train_rows), "n_test": len(test_rows),
               "train_missing_node": train_missing, "test_missing_node": test_missing,
               "de_threshold": float(best_thr), "train_calib_macro_f1": float(best_f1),
               "test_metrics": test_m}
        if verbose:
            print(f"[genki_baseline] TEST T1a-DE n={test_m['n_total']} "
                  f"acc={test_m['acc_overall']} macro_f1={test_m['macro_f1']} mcc={test_m['mcc']}")

    else:  # dir
        # sign of the decoded mean_A shift; calibrate the cut on TRAIN split
        best_cut, best_dir_f1 = 0.0, -1.0
        lo, hi = float(train_attr.min()), float(train_attr.max())
        for cut in np.linspace(lo, hi, 200):
            pred = (train_attr > cut).astype(int)
            tp = int(((pred == 1) & (train_y == 1)).sum())
            fp = int(((pred == 1) & (train_y == 0)).sum())
            fn = int(((pred == 0) & (train_y == 1)).sum())
            tn = int(((pred == 0) & (train_y == 0)).sum())
            f1p = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
            f1n = 2 * tn / (2 * tn + fn + fp) if (2 * tn + fn + fp) else 0.0
            macro = (f1p + f1n) / 2
            if macro > best_dir_f1:
                best_dir_f1, best_cut = macro, cut
        if verbose:
            print(f"[genki_baseline] DIR sign-cut calibrated on TRAIN split: "
                  f"decoded-attr-delta>{best_cut:.4f}->Increase "
                  f"(train macro-F1={best_dir_f1:.4f})")
        test_preds = (test_attr > best_cut).astype(int).tolist()
        test_m = compute_metrics(test_preds, test_y.astype(int).tolist(), "dir")
        if dump_preds:
            cases = [{"pert": p, "gene": g, "true": int(y), "pred": int(pr)}
                     for (p, g, y), pr in zip(test_rows, test_preds)]
            os.makedirs(os.path.dirname(dump_preds), exist_ok=True) if os.path.dirname(dump_preds) else None
            with open(dump_preds, "w", encoding="utf-8") as f:
                json.dump(cases, f)
        out = {"task": "dir", "n_nodes": n, "n_edges": len(edges),
               "n_train": len(train_rows), "n_test": len(test_rows),
               "train_missing_node": train_missing, "test_missing_node": test_missing,
               "dir_cut": float(best_cut), "train_calib_macro_f1": float(best_dir_f1),
               "test_metrics": test_m}
        if verbose:
            print(f"[genki_baseline] TEST T1b-DIR n={test_m['n_total']} "
                  f"acc={test_m['acc_overall']} macro_f1={test_m['macro_f1']} mcc={test_m['mcc']}")

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
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    ap.add_argument("--k", type=int, default=K_NEIGHBORS)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--json", default=None)
    ap.add_argument("--dump-preds", default=None,
                     help="also write per-case [{pert,gene,true,pred}] test predictions here "
                          "(used by decomposition slicing scripts)")
    args = ap.parse_args(argv)

    t0 = time.time()
    run(args.task, epochs=args.epochs, k=args.k, seed=args.seed, out_json=args.json,
        dump_preds=args.dump_preds)
    print(f"[genki_baseline] done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
