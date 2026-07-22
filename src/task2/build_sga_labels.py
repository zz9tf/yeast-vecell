#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build Task 2B (genetic interaction, double perturbation) DE/DIR label CSVs.

Mirrors ``build_growth_labels.py`` (Task 2A) as closely as the data allows:

    Task 1 (expression):    pert = deleted gene         | gene    = readout ORF | label = DE hit
    Task 2A (growth):       pert = deleted gene         | context = screen/condition | label = phenotype hit
    Task 2B (this, GI):     pertA, pertB = gene pair     | (no context axis)     | T2B-DE = has GI, T2B-DIR = sign

INPUT DATA (read-only; lives in the separate ``yeast-rank-cross-lab`` repo):

  - ``folder1_GI_raw/Genetic.interaction.score.tsv`` -- Costanzo-lab SGA
    E-MAP matrix. Rows = query strain ID (``ORF_tsqNNNN`` for temperature-
    sensitive query alleles), columns = array strain ID (``ORF_tsaNNNN`` for
    TS array alleles or ``ORF_dmaNNNN`` for deletion-mutant array alleles).
    Value = genetic interaction score (epsilon, ``eps``). Multiple alleles
    per gene exist on both axes (e.g. YAL033W has 2 query alleles here), so
    this builder first collapses to **gene-level** scores by averaging all
    allele x allele measurements for a given (query gene, array gene) pair
    (``groupby(gene).mean()`` on both axes), matching how Costanzo-style
    papers report gene-level networks derived from allele-level E-MAPs.

  ⚠️ **This local matrix is NOT the full genome-scale ~23M-pair Costanzo
  2016 network** (that full network's ~0.8% GI-positive rate is cited in
  ``docs/task_definitions.md`` Task 2B "6. 怎么说明结果更好" from the paper
  text, not from this file). This file is a smaller query x array E-MAP
  subset (4,939 query genes x 4,450 array genes after gene-level collapse,
  ~10.0M of 22.0M gene-pair cells measured, i.e. 45.5% coverage) already
  enriched for genetic-interaction screening design -- empirically **7.15%**
  of measured gene pairs clear the |eps| >= 0.08 threshold here (not 0.8%).
  Treat the ~0.8%/99.2% figure in the task-definition doc as describing the
  full published network's rarity, and this builder's ~7%/93% as the rarity
  *within this locally-available subset* -- both numbers are real, they just
  describe different populations. This discrepancy should be reconciled in
  ``docs/task_definitions.md``/``docs/data_sources.md`` once this builder is
  reviewed (not done automatically here, out of scope for this script).

LABELING RULE (documented threshold choice, no independent significance/
p-value recheck -- this matrix has no companion p-value file, only the
score):
  - T2B-DE label = 1 ("significant interaction") if |eps| >= --threshold
    (default 0.08, the standard Costanzo-lab E-MAP/SGA convention for a
    "confident" interaction call in this literature); label = 0 sampled
    from a confident-negative pool (|eps| < --neg-threshold, default 0.02),
    capped at --n-neg per query gene (mirrors Task 1/2A negative sampling).
  - T2B-DIR label, restricted to T2B-DE positives only: label = 1
    ("positive"/alleviating, eps > 0) else 0 ("negative"/aggravating,
    eps < 0).

SPLIT: by **gene**, not by pair (30% train / 70% test, seed 42, identical
convention to Task 1/2A) -- a gene's split assignment is fixed once, and a
pair (A, B) is kept only if both A and B fall in the same split (train-train
or test-test); cross-split pairs (~2 x 0.3 x 0.7 = 42% of pairs) are
**dropped**, not assigned to either split, to avoid a gene straddling both
splits via different partners. This is a real design difference from Task
1/2A (which only ever split on a single perturbagen axis, never had to
reconcile two entities appearing in the same row against two different
splits) -- printed to stderr as a dropped-pair count.

OUTPUTS (written under yeast-vecell/data/task2/):
  - ``sga_DE.csv``   columns: pertA, pertB, label, split
  - ``sga_DIR.csv``  columns: pertA, pertB, label, split   (DE-positive subset only)

Idempotent: skipped if both outputs exist, unless --force.
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

RANK_CROSS_LAB = "/home/zhengz2/yeast-rank-cross-lab"  # READ-ONLY, never write here.
DEFAULT_MATRIX = f"{RANK_CROSS_LAB}/data/folder1_GI_raw/Genetic.interaction.score.tsv"

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "data", "task2"))


def _to_orf(strain_id: str) -> str:
    """'YAL033W_tsq2933' -> 'YAL033W' (strip the trailing _<library><id> tag)."""
    return strain_id.rsplit("_", 1)[0]


def load_gene_level_matrix(matrix_path: str) -> pd.DataFrame:
    """Load the allele-level query x array eps matrix and collapse to gene
    level by averaging over all allele pairs sharing the same (query gene,
    array gene). Returns a DataFrame: index = query gene ORF, columns =
    array gene ORF, values = mean eps (float, NaN where no allele pair
    measured)."""
    print(f"Loading matrix: {matrix_path}", file=sys.stderr)
    mat = pd.read_csv(matrix_path, sep="\t", index_col=0)
    print(f"  raw (allele-level) shape: {mat.shape[0]} query alleles x "
          f"{mat.shape[1]} array alleles", file=sys.stderr)

    mat.index = pd.Index([_to_orf(x) for x in mat.index])
    mat.columns = pd.Index([_to_orf(x) for x in mat.columns])
    gene_mat = mat.T.groupby(level=0).mean().T.groupby(level=0).mean()
    print(f"  gene-level shape: {gene_mat.shape[0]} query genes x "
          f"{gene_mat.shape[1]} array genes", file=sys.stderr)
    return gene_mat


def build_labels(
    gene_mat: pd.DataFrame,
    *,
    threshold: float,
    neg_threshold: float,
    n_neg: int,
    train_fraction: float,
    seed: int,
):
    query_genes = gene_mat.index.tolist()
    array_genes = gene_mat.columns.tolist()
    vals = gene_mat.values.astype(np.float64)
    n_q, n_a = vals.shape

    abs_vals = np.abs(vals)
    finite = ~np.isnan(vals)
    pos_mask = finite & (abs_vals >= threshold)
    neg_pool_mask = finite & (abs_vals < neg_threshold)

    # ---- split genes 30/70, seed 42 (same convention as Task 1/2A) ----
    all_genes = sorted(set(query_genes) | set(array_genes))
    rng_split = np.random.RandomState(seed)
    shuffled = list(all_genes)
    rng_split.shuffle(shuffled)
    n_train = int(len(shuffled) * train_fraction)
    train_set = set(shuffled[:n_train])
    print(f"Split: {len(train_set)} train / {len(shuffled) - len(train_set)} test "
          f"genes (train_fraction={train_fraction}, seed={seed})", file=sys.stderr)

    def pair_split(g1: str, g2: str):
        g1_train, g2_train = g1 in train_set, g2 in train_set
        if g1_train and g2_train:
            return "train"
        if not g1_train and not g2_train:
            return "test"
        return None  # cross-split pair, dropped

    rng_neg = np.random.default_rng(seed)

    de_rows = []   # (pertA, pertB, label, split)
    dir_rows = []  # (pertA, pertB, label, split)
    n_dropped_pos = 0
    n_dropped_neg = 0

    for qi, qgene in enumerate(query_genes):
        row = vals[qi]

        pos_idx = np.nonzero(pos_mask[qi])[0]
        for ai in pos_idx:
            agene = array_genes[ai]
            split = pair_split(qgene, agene)
            if split is None:
                n_dropped_pos += 1
                continue
            de_rows.append((qgene, agene, 1, split))
            dir_rows.append((qgene, agene, 1 if row[ai] > 0 else 0, split))

        neg_idx = np.nonzero(neg_pool_mask[qi])[0]
        if len(neg_idx) > 0:
            k = min(n_neg, len(neg_idx))
            chosen = rng_neg.choice(neg_idx, size=k, replace=False)
            for ai in chosen:
                agene = array_genes[ai]
                split = pair_split(qgene, agene)
                if split is None:
                    n_dropped_neg += 1
                    continue
                de_rows.append((qgene, agene, 0, split))

    print(f"Dropped cross-split pairs: {n_dropped_pos} positive, {n_dropped_neg} "
          f"sampled-negative (kept genes' split fixed, no pair straddles train/test)",
          file=sys.stderr)

    de_df = pd.DataFrame(de_rows, columns=["pertA", "pertB", "label", "split"])
    dir_df = pd.DataFrame(dir_rows, columns=["pertA", "pertB", "label", "split"])
    return de_df, dir_df, len(all_genes)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matrix", default=DEFAULT_MATRIX,
                    help="query x array genetic-interaction score matrix (tab-delimited, "
                         "read-only)")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--threshold", type=float, default=0.08,
                    help="|eps| >= threshold => T2B-DE positive (default 0.08, standard "
                         "Costanzo-lab E-MAP/SGA 'confident interaction' convention)")
    ap.add_argument("--neg-threshold", type=float, default=0.02,
                    help="|eps| < neg-threshold => confident-negative pool (default 0.02)")
    ap.add_argument("--n-neg", type=int, default=200,
                    help="max sampled negatives per query gene (default 200, mirrors "
                         "Task 1/2A)")
    ap.add_argument("--train-fraction", type=float, default=0.3,
                    help="fraction of genes assigned to train (default 0.3 => 30/70)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--force", action="store_true", help="recompute even if outputs exist")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    de_path = os.path.join(args.out_dir, "sga_DE.csv")
    dir_path = os.path.join(args.out_dir, "sga_DIR.csv")

    if not args.force and os.path.exists(de_path) and os.path.exists(dir_path):
        print(f"Both outputs already exist under {args.out_dir}; skipping "
              f"(use --force to rebuild).")
        return

    print(f"\n{'=' * 20} Task 2B genetic-interaction labels {'=' * 20}", file=sys.stderr)
    gene_mat = load_gene_level_matrix(args.matrix)

    de_df, dir_df, n_genes = build_labels(
        gene_mat,
        threshold=args.threshold,
        neg_threshold=args.neg_threshold,
        n_neg=args.n_neg,
        train_fraction=args.train_fraction,
        seed=args.seed,
    )

    de_df.to_csv(de_path, index=False)
    dir_df.to_csv(dir_path, index=False)

    n_pos = int((de_df["label"] == 1).sum())
    n_neg_out = int((de_df["label"] == 0).sum())
    n_dir_pos = int((dir_df["label"] == 1).sum())
    n_dir_neg = int((dir_df["label"] == 0).sum())
    print(f"\nGenes (union of query+array, split axis): {n_genes}")
    print(f"Saved T2B-DE  CSV: {de_path}  (rows={len(de_df)}, "
          f"has_interaction={n_pos}, no_interaction={n_neg_out}, "
          f"pos_rate={n_pos/len(de_df)*100:.2f}%)")
    print(f"Saved T2B-DIR CSV: {dir_path}  (rows={len(dir_df)}, "
          f"positive={n_dir_pos}, negative={n_dir_neg}, "
          f"pos_rate={n_dir_pos/len(dir_df)*100:.2f}%)"
          if len(dir_df) else f"Saved T2B-DIR CSV: {dir_path}  (rows=0)")
    print("Done.")


if __name__ == "__main__":
    main()
