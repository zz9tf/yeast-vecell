#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""""Variant 4" baseline for Task 1: a trained lightweight GAT (Graph Attention Network)
link-predictor, evaluated on the EXACT SAME train/test split used for the LLM
(data/runs/deleteome_DE.csv / deleteome_DIR.csv, "split" column), so its Macro-F1/MCC
is directly comparable to the numbers in docs/task_results.md.

Design rationale and method spec: docs/prompt_optimization.md "变体4" section. This
mirrors VCWorld's (ICLR 2026) own self-built GAT baseline (fusing their knowledge graph,
trained on the same train/test split as the zero-shot LLM pipeline) -- the point is to
answer "is the graph structure itself doing the work, or is LLM reasoning adding value
on top of it", not to build a SOTA GNN.

Graph construction (mirrors VCWorld Appendix B.2's "integrate multiple KG sources into
one connected graph", our sources = STRING + YEASTRACT instead of PubChem/DrugBank/GO/
UniProt/Reactome):
  - nodes: every gene ORF that appears as `pert` or `gene` in the DE/DIR CSVs, unioned
    with every gene appearing in the KG assets below (extra nodes act as message-passing
    relays even if they're never a (pert,gene) query themselves).
  - edges (undirected, two edge "families" merged into one simple graph -- lightweight,
    not a heterogeneous GNN):
      * STRING direct_neighbors from data/knowledge/results_close_gene.json
      * YEASTRACT TF->target from data/knowledge/tf_targets.json ('targets' list, sign
        dropped -- edge existence only, GAT is not told activates/represses)

Node features (deliberately simple/structural -- "lightweight" baseline, NOT LLM-derived
embeddings):
  - is_tf                 : gene is one of the 192 YEASTRACT signature TFs
  - is_esr                : gene is in the Gasch 2000 ESR set (esr_genes_gasch2000.json)
  - log1p(n_complexes)    : how many ComplexPortal complexes the gene belongs to
  - log1p(string_degree)  : # STRING direct neighbors
  - log1p(total_degree)   : degree in the merged STRING+YEASTRACT graph built above
  - train_rate_as_pert, train_rate_as_gene (Laplace-smoothed empirical positive rate of
    this node when it plays the pert / gene role, computed ONLY from the fit-split rows
    -- standard "target encoding", legitimate because it never touches val/test labels)
  - log1p(train_count_as_pert), log1p(train_count_as_gene) (confidence weight for the
    two rates above)
  concatenated with a learnable per-node nn.Embedding (standard "shallow embedding +
  GNN refinement" link-prediction setup) so nodes with identical structural features but
  different identity aren't forced to collapse to the same representation.

  IMPORTANT CAVEAT (found during a leakage sanity-check on the first pass without the
  target-encoding features): a trivial baseline that just predicts "this readout gene's
  train-split majority label, no graph, no model at all" already beats the plain
  STRING/TF/ESR-feature GAT (see docs/task_results.md T1a-DE / T1b-DIR notes) -- this
  dataset has strong per-gene base rates (some genes are near-always DE regardless of
  which gene was deleted, e.g. constitutively stress-responsive ones), so a model that
  can't represent that basic per-node prior loses to a one-line lookup table. Adding
  train_rate_as_pert/train_rate_as_gene as explicit input features (rather than hoping
  the learnable nn.Embedding infers the same statistic implicitly via SGD) is the fix,
  reported as a labeled row (not swapped in silently) since it changes what the model's
  win over LLM/baselines would actually mean -- it's no longer "graph reasoning beats
  LLM reasoning", it's closer to "train-set base-rate lookup (+ some graph refinement)
  beats it", a materially weaker/different claim.

Task head: for a (pert, gene) pair, gather the two nodes' final GAT-refined embeddings
h_pert, h_gene, feed [h_pert, h_gene, |h_pert-h_gene|] into a 2-layer MLP -> sigmoid ->
binary label (DE: DE/non-DE; DIR: Increase/Decrease, trained + evaluated only on the
DIR CSV's own rows, which are already the DE-positive subset).

Usage:
  python src/eval/gat_baseline.py --task de  --epochs 30 --json out/gat_de.json
  python src/eval/gat_baseline.py --task dir --epochs 30 --json out/gat_dir.json

Requires torch + torch_geometric (CPU is enough; graph is ~6-8k nodes / ~250k edges,
full-graph forward pass is milliseconds). No GPU / side-channel dispatch used.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time

# Reproducibility fix (2026-07-24): same CPU-thread nondeterminism bug found in
# genki_baseline.py/kge_tgi_baseline.py (torch's default multi-threaded CPU BLAS
# ops are not bit-reproducible across runs) -- confirmed here too (a same-seed
# rerun with --dump-preds gave macro_f1/mcc differing from the recorded main-
# table numbers by up to ~.04). Must be set before torch is imported anywhere
# below (torch is imported lazily inside functions), so this goes at module
# top right after `import os`. NOTE: this fix was applied AFTER the main-table
# GAT numbers (data/runs/gat_baseline/gat_{de,dir}_seed{0,1,2}.json) were
# recorded -- those were not regenerated, see docs/task_results.md caveat.
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


def load_knowledge():
    close = json.load(open(os.path.join(KNOW, "results_close_gene.json"), encoding="utf-8"))
    tf_targets = json.load(open(os.path.join(KNOW, "tf_targets.json"), encoding="utf-8"))
    esr = json.load(open(os.path.join(KNOW, "esr_genes_gasch2000.json"), encoding="utf-8"))
    complex_members = json.load(open(os.path.join(KNOW, "complex_members_complexportal.json"),
                                      encoding="utf-8"))
    return close, tf_targets, esr, complex_members


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph(rows, close, tf_targets, esr, complex_members):
    import math

    node_ids = set()
    for pert, gene, _, _ in rows:
        node_ids.add(pert)
        node_ids.add(gene)
    node_ids.update(close.keys())
    for v in close.values():
        node_ids.update(v.get("direct_neighbors", []))
        node_ids.update(v.get("two_hop_neighbors", []))
    node_ids.update(tf_targets.keys())
    for v in tf_targets.values():
        node_ids.update(v.get("targets", []))
    node_ids.update(esr.keys())
    node_ids.update(complex_members.keys())

    nodes = sorted(node_ids)
    idx = {g: i for i, g in enumerate(nodes)}
    n = len(nodes)

    edge_set = set()
    string_degree = [0] * n
    for g, v in close.items():
        gi = idx[g]
        for nb in v.get("direct_neighbors", []):
            ni = idx[nb]
            if gi == ni:
                continue
            edge_set.add((min(gi, ni), max(gi, ni)))
            string_degree[gi] += 1
    for tf, v in tf_targets.items():
        ti = idx[tf]
        for tgt in v.get("targets", []):
            gi = idx[tgt]
            if ti == gi:
                continue
            edge_set.add((min(ti, gi), max(ti, gi)))

    edges = list(edge_set)
    degree = [0] * n
    for a, b in edges:
        degree[a] += 1
        degree[b] += 1

    is_tf = [0.0] * n
    for tf in tf_targets:
        is_tf[idx[tf]] = 1.0
    is_esr = [0.0] * n
    for g in esr:
        is_esr[idx[g]] = 1.0
    n_complex = [0] * n
    for g, cs in complex_members.items():
        n_complex[idx[g]] = len(cs)

    feats = []
    for i in range(n):
        feats.append([
            is_tf[i],
            is_esr[i],
            math.log1p(n_complex[i]),
            math.log1p(string_degree[i]),
            math.log1p(degree[i]),
        ])

    return nodes, idx, edges, feats


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def make_model(n_nodes, feat_dim, emb_dim=16, hidden=32, seed=0):
    import torch
    import torch.nn as nn
    from torch_geometric.nn import GATConv

    torch.manual_seed(seed)

    class GATLinkPredictor(nn.Module):
        def __init__(self):
            super().__init__()
            self.node_emb = nn.Embedding(n_nodes, emb_dim)
            self.in_proj = nn.Linear(emb_dim + feat_dim, hidden)
            self.gat1 = GATConv(hidden, hidden, heads=4, concat=False, dropout=0.2)
            self.gat2 = GATConv(hidden, hidden, heads=4, concat=False, dropout=0.2)
            self.act = nn.ELU()
            self.dropout = nn.Dropout(0.2)
            self.head = nn.Sequential(
                nn.Linear(hidden * 3, hidden),
                nn.ELU(),
                nn.Dropout(0.2),
                nn.Linear(hidden, 1),
            )

        def encode(self, x_struct, edge_index):
            x = torch.cat([self.node_emb.weight, x_struct], dim=1)
            x = self.act(self.in_proj(x))
            x = self.dropout(x)
            x = self.act(self.gat1(x, edge_index))
            x = self.dropout(x)
            x = self.gat2(x, edge_index)
            return x

        def predict(self, h, left_idx, right_idx):
            hl, hr = h[left_idx], h[right_idx]
            z = torch.cat([hl, hr, (hl - hr).abs()], dim=1)
            return self.head(z).squeeze(-1)

    return GATLinkPredictor()


# ---------------------------------------------------------------------------
# Train / eval
# ---------------------------------------------------------------------------

def run(task, epochs=30, batch_size=4096, lr=0.01, seed=0, val_frac=0.1,
        patience=6, out_json=None, verbose=True, dump_preds=None):
    import torch
    import torch.nn.functional as F
    torch.set_num_threads(1)  # belt-and-suspenders, see module-top env vars

    csv_path = TASK_CSV[task]
    rows = load_rows(csv_path)
    close, tf_targets, esr, complex_members = load_knowledge()
    nodes, idx, edges, feats = build_graph(rows, close, tf_targets, esr, complex_members)
    n_nodes = len(nodes)
    if verbose:
        print(f"[gat_baseline] task={task} nodes={n_nodes} edges={len(edges)}")

    edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
    # undirected: add both directions
    edge_index = torch.cat([edge_index, edge_index.flip(0)], dim=1)
    x_struct = torch.tensor(feats, dtype=torch.float32)

    train_rows = [(p, g, y) for p, g, y, s in rows if s == "train"]
    test_rows = [(p, g, y) for p, g, y, s in rows if s == "test"]

    import random
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

    # ---- target-encoding features, computed ONLY from fit_rows (never val/test labels) ----
    import math as _math
    global_rate = (sum(y for _, _, y in fit_rows) / len(fit_rows)) if fit_rows else 0.5
    pert_sum, pert_cnt = {}, {}
    gene_sum, gene_cnt = {}, {}
    for p, g, y in fit_rows:
        pert_sum[p] = pert_sum.get(p, 0) + y
        pert_cnt[p] = pert_cnt.get(p, 0) + 1
        gene_sum[g] = gene_sum.get(g, 0) + y
        gene_cnt[g] = gene_cnt.get(g, 0) + 1
    alpha = 5.0  # Laplace smoothing strength toward global_rate
    extra_feats = []
    for node in nodes:
        pc = pert_cnt.get(node, 0)
        ps = pert_sum.get(node, 0)
        gc = gene_cnt.get(node, 0)
        gs = gene_sum.get(node, 0)
        rate_pert = (ps + alpha * global_rate) / (pc + alpha)
        rate_gene = (gs + alpha * global_rate) / (gc + alpha)
        extra_feats.append([rate_pert, rate_gene, _math.log1p(pc), _math.log1p(gc)])
    x_struct = torch.cat([x_struct, torch.tensor(extra_feats, dtype=torch.float32)], dim=1)
    if verbose:
        print(f"[gat_baseline] added target-encoding features (fit-only), "
              f"global_rate={global_rate:.4f}, x_struct dim={x_struct.shape[1]}")

    n_pos = sum(y for _, _, y in fit_rows)
    n_neg = len(fit_rows) - n_pos
    pos_weight = torch.tensor([n_neg / max(n_pos, 1)], dtype=torch.float32)
    if verbose:
        print(f"[gat_baseline] fit={len(fit_rows)} val={len(val_rows)} "
              f"test={len(test_rows)} pos_weight={pos_weight.item():.3f}")

    model = make_model(n_nodes, x_struct.shape[1], seed=seed)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)

    best_val_f1 = -1.0
    best_state = None
    bad_epochs = 0
    n_fit = len(fit_rows)

    for epoch in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(n_fit)
        total_loss = 0.0
        for start in range(0, n_fit, batch_size):
            b = perm[start:start + batch_size]
            opt.zero_grad()
            h = model.encode(x_struct, edge_index)
            logits = model.predict(h, fit_li[b], fit_ri[b])
            loss = F.binary_cross_entropy_with_logits(logits, fit_y[b], pos_weight=pos_weight)
            loss.backward()
            opt.step()
            total_loss += loss.item() * len(b)
        total_loss /= n_fit

        model.eval()
        with torch.no_grad():
            h = model.encode(x_struct, edge_index)
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
        h = model.encode(x_struct, edge_index)
        test_logits = model.predict(h, test_li, test_ri)
        test_probs = torch.sigmoid(test_logits)
        test_preds = (test_probs >= 0.5).long().tolist()
    test_m = compute_metrics(test_preds, test_y.long().tolist(), TASK_METRIC[task])
    if verbose:
        print(f"[gat_baseline] TEST task={task} n={test_m['n_total']} "
              f"acc={test_m['acc_overall']} macro_f1={test_m['macro_f1']} mcc={test_m['mcc']}")

    if dump_preds:
        # test_rows == [(pert, gene, true_label)], same order as test_preds
        # (both derived from to_tensors(test_rows) without reshuffling).
        cases = [{"pert": p, "gene": g, "true": int(y), "pred": int(pr)}
                 for (p, g, y), pr in zip(test_rows, test_preds)]
        os.makedirs(os.path.dirname(dump_preds), exist_ok=True) if os.path.dirname(dump_preds) else None
        with open(dump_preds, "w", encoding="utf-8") as f:
            json.dump(cases, f)
        if verbose:
            print(f"wrote per-case preds: {dump_preds} ({len(cases)} cases)")

    out = {
        "task": task, "seed": seed, "epochs_run": epoch, "best_val_macro_f1": best_val_f1,
        "n_nodes": n_nodes, "n_edges": len(edges),
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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", required=True, choices=["de", "dir"])
    ap.add_argument("--epochs", type=int, default=30)
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
    print(f"[gat_baseline] done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
