#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""""Variant 4" baseline for Task 2A: GAT (Graph Attention Network) ported
from Task 1's gat_baseline.py, but with a COMPLETELY DIFFERENT graph -- a
gene<->condition bipartite network built from a compound-target network +
condition-condition similarity, NOT the STRING/YEASTRACT graph used by
Task 1's GAT. Evaluated on the EXACT SAME train/test split used for the LLM
(data/task2/hillenmeyer_phenotype.csv / hillenmeyer_direction.csv, "split"
column).

Design spec: docs/task_definitions.md Task 2A section 7 ("GAT（从T1移植，
训练型传统ML对照）" -- "同T1的图神经网络架构，图结构换成化合物结构相似性/靶点网络
（而非STRING/YEASTRACT）"), docs/prompt_optimization.md "变体4" T2A GAT entry.

Why this can't just import gat_baseline.py's graph: Task 1's graph is
gene<->gene (STRING PPI + YEASTRACT TF->target); Task 2A's natural graph is
gene<->condition (does this gene interact with this drug/stress), a
different node-type structure entirely (two node types: genes, conditions),
so the graph-construction step is rewritten from scratch; the GATConv
encoder + pair-classification head architecture is the part that is
"ported" from Task 1.

Graph construction (real data, no compound SMILES/structure available in
this repo -- see docs/task_definitions.md Task 2A decomposition-2 note: only
13/141 Hillenmeyer compounds match STITCH, only 7 at combined_score>=700, so
a target-network alone would leave >95% of condition nodes edgeless):
  - condition<->condition: top-8 neighbours per condition from
    data/knowledge/condition_similarity.json (functional/expression-response
    similarity over the yp_matrix_z_haphom columns -- this is the same
    "condition network" substitute already used project-wide for T2A's
    MultiXrank variant, see task_definitions.md's MultiXrank T2A entry).
  - gene<->condition ("target network"): STITCH compound-target edges
    (data/knowledge/stitch_compound_targets_hillenmeyer.json, mapped from
    compound name to context id via data/task2/decomp2_ctx_to_compound.json)
    -- real but EXTREMELY sparse (25/273 context ids have a compound-name
    mapping at all; only a handful of those have nonzero STITCH targets).
  - gene<->condition (train-interaction network): for TRAIN split rows with
    label==1 ("has phenotype" for DE / "Resistant" for DIR) ONLY, add an
    edge between that gene and that condition -- the standard bipartite
    "observed-interaction graph" construction used by graph-based
    collaborative filtering (e.g. LightGCN); this is legitimate (built only
    from train-split rows, exactly mirroring how gat_baseline.py's
    target-encoding features are fit-split-only) and, given how sparse the
    STITCH edges are, ends up being the dominant edge source in practice --
    reported honestly below and in task_results.md, since it changes what a
    win over LLM/Majority would mean (closer to "collaborative-filtering-
    style graph over train interactions" than "compound structure reasoning").

**Cold-start note (test genes have ZERO train-split rows, by construction
of this split -- see matrix_factorization_baseline.py's docstring for the
same structural fact)**: unlike a STRING-derived graph where a gene has real
biological edges regardless of whether it was ever tested, a TEST gene here
only gets a non-trivial degree if it happens to be a STITCH target of one of
the 7 compounds with usable target data. The overwhelming majority of test
genes are edgeless (or connected only via their own self-loop), so for them
the GAT's message passing collapses to "this gene's own learnable embedding
+ generic gene features" -- the model is EXPECTED to fall back heavily on
condition-side signal for those genes. This is reported as a finding, not
hidden.

Usage:
  python src/eval/gat_baseline_t2a.py --task de  --epochs 30 --json out/gat_t2a_de.json
  python src/eval/gat_baseline_t2a.py --task dir --epochs 30 --json out/gat_t2a_dir.json

Requires torch + torch_geometric (CPU; graph is a few thousand gene nodes +
273 condition nodes, tiny edge count -- full-graph forward pass is
milliseconds). No GPU / side-channel dispatch used.
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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import compute_metrics  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
KNOW = os.path.join(REPO, "data", "knowledge")
TASK2_DIR = os.path.join(REPO, "data", "task2")

TASK_CSV = {
    "de": os.path.join(TASK2_DIR, "hillenmeyer_phenotype.csv"),
    "dir": os.path.join(TASK2_DIR, "hillenmeyer_direction.csv"),
}
TASK_METRIC = {"de": "growth", "dir": "growth_dir"}
CONTEXTS_CSV = os.path.join(TASK2_DIR, "haphom_growth_contexts.csv")
CTX_TO_COMPOUND = os.path.join(TASK2_DIR, "decomp2_ctx_to_compound.json")
STITCH_TARGETS = os.path.join(KNOW, "stitch_compound_targets_hillenmeyer.json")
COND_SIM = os.path.join(KNOW, "condition_similarity.json")

CTX_PREFIX = "ctx::"  # namespace condition node ids so they never collide with gene ORFs


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


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph(rows, ctx_meta, k_cond_sim=8):
    ctx_to_compound = json.load(open(CTX_TO_COMPOUND, encoding="utf-8"))
    stitch_targets = json.load(open(STITCH_TARGETS, encoding="utf-8"))
    cond_sim = json.load(open(COND_SIM, encoding="utf-8"))

    # restrict condition NODES to the 273 contexts that actually appear in this
    # task's CSV (haphom_growth_contexts.csv covers ~7689 Hillenmeyer contexts
    # in total; the T2A DE/DIR CSVs only sample 273 of them -- keep the graph
    # scoped to the task, not the full compendium)
    task_contexts = sorted({ctx for _, ctx, _, _ in rows}, key=int)
    contexts = task_contexts
    ctx_ids = [CTX_PREFIX + c for c in contexts]
    ctx_set = set(contexts)

    genes = set()
    for pert, ctx, _, _ in rows:
        genes.add(pert)
    # extra genes from STITCH targets (relays, mirrors gat_baseline.py's convention)
    for compound, targets in stitch_targets.items():
        genes.update(targets)

    nodes = sorted(genes) + ctx_ids
    idx = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    n_genes = len(genes)

    edges = set()  # undirected (a,b) with a<b in node-index space

    # condition <-> condition (top-k similarity neighbours, restricted to the 273 T2A contexts)
    for c in contexts:
        neighbors = cond_sim.get(c, [])[:k_cond_sim]
        ci = idx[CTX_PREFIX + c]
        for nb in neighbors:
            if nb in ctx_set:
                ni = idx[CTX_PREFIX + nb]
                if ci != ni:
                    edges.add((min(ci, ni), max(ci, ni)))

    # gene <-> condition ("target network"): STITCH compound-target links
    n_stitch_edges = 0
    is_stitch_target = [0.0] * n
    for ctx_id, compound in ctx_to_compound.items():
        if ctx_id not in ctx_set:
            continue
        targets = stitch_targets.get(compound, [])
        if not targets:
            continue
        ci = idx[CTX_PREFIX + ctx_id]
        for g in targets:
            gi = idx[g]
            edges.add((min(ci, gi), max(ci, gi)))
            is_stitch_target[gi] = 1.0
            n_stitch_edges += 1

    # gene <-> condition (train-interaction network, TRAIN split label==1 rows only)
    n_interaction_edges = 0
    for pert, ctx, label, split in rows:
        if split != "train" or label != 1:
            continue
        if ctx not in ctx_set or pert not in idx:
            continue
        gi, ci = idx[pert], idx[CTX_PREFIX + ctx]
        if (min(gi, ci), max(gi, ci)) not in edges:
            n_interaction_edges += 1
        edges.add((min(gi, ci), max(gi, ci)))

    degree = [0] * n
    for a, b in edges:
        degree[a] += 1
        degree[b] += 1

    return nodes, idx, list(edges), n_genes, contexts, is_stitch_target, degree, \
        n_stitch_edges, n_interaction_edges


def build_features(nodes, idx, n_genes, contexts, ctx_meta, is_stitch_target, degree,
                    train_rows):
    mediums = sorted({m["medium"] for m in ctx_meta.values()})
    phenotypes = sorted({m["phenotype"] for m in ctx_meta.values()})
    collections = sorted({m["collection"] for m in ctx_meta.values()})

    def onehot(val, vocab):
        return [1.0 if val == v else 0.0 for v in vocab]

    # ---- context target-encoding (legit: context ids 100% shared train/test) ----
    global_rate = (sum(y for _, _, y in train_rows) / len(train_rows)) if train_rows else 0.5
    ctx_sum, ctx_cnt = {}, {}
    for _, c, y in train_rows:
        ctx_sum[c] = ctx_sum.get(c, 0) + y
        ctx_cnt[c] = ctx_cnt.get(c, 0) + 1
    alpha = 5.0

    def ctx_rate(c):
        s, cnt = ctx_sum.get(c, 0), ctx_cnt.get(c, 0)
        return (s + alpha * global_rate) / (cnt + alpha)

    # ---- gene target-encoding (Laplace-smoothed, TRAIN split only; near-uninformative
    # for test genes by construction -- zero train presence, see module docstring) ----
    pert_sum, pert_cnt = {}, {}
    for p, _, y in train_rows:
        pert_sum[p] = pert_sum.get(p, 0) + y
        pert_cnt[p] = pert_cnt.get(p, 0) + 1

    def pert_rate(p):
        s, cnt = pert_sum.get(p, 0), pert_cnt.get(p, 0)
        return (s + alpha * global_rate) / (cnt + alpha)

    n = len(nodes)
    gene_feat_dim = 3   # is_stitch_target, log1p(degree), pert_rate
    ctx_feat_dim = len(mediums) + len(phenotypes) + len(collections) + 3  # +log1p(num_tested),ctx_rate,log1p(degree)

    gene_feats = [[0.0] * gene_feat_dim for _ in range(n)]
    ctx_feats = [[0.0] * ctx_feat_dim for _ in range(n)]
    is_gene = [0.0] * n

    for i, node in enumerate(nodes):
        if not node.startswith(CTX_PREFIX):
            is_gene[i] = 1.0
            gene_feats[i] = [is_stitch_target[i], math.log1p(degree[i]), pert_rate(node)]
        else:
            ctx = node[len(CTX_PREFIX):]
            m = ctx_meta.get(ctx, {})
            num_tested = float(m.get("num_tested", 0) or 0)
            f = onehot(m.get("medium", ""), mediums)
            f += onehot(m.get("phenotype", ""), phenotypes)
            f += onehot(m.get("collection", ""), collections)
            f += [math.log1p(num_tested), ctx_rate(ctx), math.log1p(degree[i])]
            ctx_feats[i] = f

    return gene_feats, ctx_feats, is_gene, gene_feat_dim, ctx_feat_dim


# ---------------------------------------------------------------------------
# Model: type-specific input projections (gene / condition) -> shared hidden
# dim -> 2-layer GATConv over the merged bipartite+condition-condition graph
# ---------------------------------------------------------------------------

def make_model(n_nodes, gene_feat_dim, ctx_feat_dim, emb_dim=16, hidden=32, seed=0):
    import torch
    import torch.nn as nn
    from torch_geometric.nn import GATConv

    torch.manual_seed(seed)

    class GATLinkPredictorT2A(nn.Module):
        def __init__(self):
            super().__init__()
            self.node_emb = nn.Embedding(n_nodes, emb_dim)
            self.gene_proj = nn.Linear(emb_dim + gene_feat_dim, hidden)
            self.ctx_proj = nn.Linear(emb_dim + ctx_feat_dim, hidden)
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

        def encode(self, gene_feats, ctx_feats, is_gene, edge_index):
            emb = self.node_emb.weight
            x_gene = self.gene_proj(torch.cat([emb, gene_feats], dim=1))
            x_ctx = self.ctx_proj(torch.cat([emb, ctx_feats], dim=1))
            ig = is_gene.unsqueeze(1)
            x = ig * x_gene + (1 - ig) * x_ctx
            x = self.act(x)
            x = self.dropout(x)
            x = self.act(self.gat1(x, edge_index))
            x = self.dropout(x)
            x = self.gat2(x, edge_index)
            return x

        def predict(self, h, left_idx, right_idx):
            hl, hr = h[left_idx], h[right_idx]
            z = torch.cat([hl, hr, (hl - hr).abs()], dim=1)
            return self.head(z).squeeze(-1)

    return GATLinkPredictorT2A()


# ---------------------------------------------------------------------------
# Train / eval
# ---------------------------------------------------------------------------

def run(task, epochs=30, batch_size=4096, lr=0.01, seed=0, val_frac=0.1,
        patience=6, out_json=None, verbose=True):
    import torch
    import torch.nn.functional as F

    csv_path = TASK_CSV[task]
    rows = load_rows(csv_path)
    ctx_meta = load_context_meta()

    (nodes, idx, edges, n_genes, contexts, is_stitch_target, degree,
     n_stitch_edges, n_interaction_edges) = build_graph(rows, ctx_meta)
    n_nodes = len(nodes)
    if verbose:
        print(f"[gat_t2a] task={task} n_nodes={n_nodes} (genes={n_genes}, "
              f"contexts={len(contexts)}) n_edges={len(edges)} "
              f"(stitch_target_edges={n_stitch_edges}, "
              f"train_interaction_edges={n_interaction_edges})")

    train_rows_all = [(p, c, y) for p, c, y, s in rows if s == "train"]
    gene_feats_l, ctx_feats_l, is_gene_l, gfd, cfd = build_features(
        nodes, idx, n_genes, contexts, ctx_meta, is_stitch_target, degree, train_rows_all)

    gene_feats = torch.tensor(gene_feats_l, dtype=torch.float32)
    ctx_feats = torch.tensor(ctx_feats_l, dtype=torch.float32)
    is_gene = torch.tensor(is_gene_l, dtype=torch.float32)

    ei = torch.tensor(edges, dtype=torch.long).t().contiguous() if edges else torch.zeros((2, 0), dtype=torch.long)
    edge_index = torch.cat([ei, ei.flip(0)], dim=1) if ei.numel() else ei

    train_rows = [(p, c, y) for p, c, y, s in rows if s == "train"]
    test_rows = [(p, c, y) for p, c, y, s in rows if s == "test"]

    rng = random.Random(seed)
    train_shuf = train_rows[:]
    rng.shuffle(train_shuf)
    n_val = max(1, int(len(train_shuf) * val_frac))
    val_rows = train_shuf[:n_val]
    fit_rows = train_shuf[n_val:]

    def to_tensors(rr):
        li = torch.tensor([idx[p] for p, c, y in rr], dtype=torch.long)
        ri = torch.tensor([idx[CTX_PREFIX + c] for p, c, y in rr], dtype=torch.long)
        y = torch.tensor([y for p, c, y in rr], dtype=torch.float32)
        return li, ri, y

    fit_li, fit_ri, fit_y = to_tensors(fit_rows)
    val_li, val_ri, val_y = to_tensors(val_rows)
    test_li, test_ri, test_y = to_tensors(test_rows)

    n_pos = sum(y for _, _, y in fit_rows)
    n_neg = len(fit_rows) - n_pos
    pos_weight = torch.tensor([n_neg / max(n_pos, 1)], dtype=torch.float32)
    if verbose:
        print(f"[gat_t2a] fit={len(fit_rows)} val={len(val_rows)} test={len(test_rows)} "
              f"pos_weight={pos_weight.item():.3f}")

    model = make_model(n_nodes, gfd, cfd, seed=seed)
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
            h = model.encode(gene_feats, ctx_feats, is_gene, edge_index)
            logits = model.predict(h, fit_li[b], fit_ri[b])
            loss = F.binary_cross_entropy_with_logits(logits, fit_y[b], pos_weight=pos_weight)
            loss.backward()
            opt.step()
            total_loss += loss.item() * len(b)
        total_loss /= n_fit

        model.eval()
        with torch.no_grad():
            h = model.encode(gene_feats, ctx_feats, is_gene, edge_index)
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
        h = model.encode(gene_feats, ctx_feats, is_gene, edge_index)
        test_logits = model.predict(h, test_li, test_ri)
        test_preds = (torch.sigmoid(test_logits) >= 0.5).long().tolist()
    test_m = compute_metrics(test_preds, test_y.long().tolist(), TASK_METRIC[task])

    # cold-start diagnostic: how many test genes had ANY edge at all (degree>0)?
    test_pert_set = sorted(set(p for p, c, y in test_rows))
    n_isolated = sum(1 for p in test_pert_set if p in idx and degree[idx[p]] == 0)
    if verbose:
        print(f"[gat_t2a] TEST task={task} n={test_m['n_total']} "
              f"acc={test_m['acc_overall']} macro_f1={test_m['macro_f1']} mcc={test_m['mcc']}")
        print(f"[gat_t2a] cold-start diagnostic: {n_isolated}/{len(test_pert_set)} "
              f"test genes ({100*n_isolated/max(len(test_pert_set),1):.1f}%) have "
              f"ZERO edges in the gene<->condition graph (isolated nodes)")

    out = {
        "task": task, "seed": seed, "epochs_run": epoch, "best_val_macro_f1": best_val_f1,
        "n_nodes": n_nodes, "n_genes": n_genes, "n_contexts": len(contexts),
        "n_edges": len(edges), "n_stitch_edges": n_stitch_edges,
        "n_interaction_edges": n_interaction_edges,
        "n_fit": len(fit_rows), "n_val": len(val_rows), "n_test": len(test_rows),
        "n_test_genes_isolated": n_isolated, "n_test_genes_total": len(test_pert_set),
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
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=4096)
    ap.add_argument("--lr", type=float, default=0.01)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--patience", type=int, default=6)
    ap.add_argument("--json", default=None)
    args = ap.parse_args(argv)

    t0 = time.time()
    run(args.task, epochs=args.epochs, batch_size=args.batch_size, lr=args.lr,
        seed=args.seed, patience=args.patience, out_json=args.json)
    print(f"[gat_t2a] done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
