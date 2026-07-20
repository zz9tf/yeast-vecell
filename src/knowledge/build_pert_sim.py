#!/usr/bin/env python3
"""
build_pert_sim.py — build perturbagen_similarity.json for yeast-vecell.

Asset: for each S. cerevisiae gene (keyed by systematic ORF name), the top-N genes
whose GENETIC-INTERACTION PROFILE is most similar (Pearson correlation of the
gene x gene genetic-interaction-score matrix). This doubles as "analogue
perturbation" retrieval for the DE/DIR pipeline (Phase 3, PLAN.md).

Source data (already local, per project note — NOT downloaded from
thecellmap.org / boonelab in this run):
    /home/zhengz2/yeast-rank-cross-lab/data/folder1_GI_raw/Genetic.interaction.score.tsv
    (124MB; documented by its own header as:
       row:    Query Strain ID   [standardSystematicName_libraryIdentifier]
       column: Array Strain ID   [standardSystematicName_libraryIdentifier]
       value:  Genetic interaction score (epsilon)
     This is Costanzo et al. 2016 Science, "A global genetic interaction network
     maps a wiring diagram of cellular function" (the raw SGA epsilon score
     matrix; equivalent in content to the boonelab supplement's Data File S2
     "Raw genetic interaction datasets: Matrix format").
     5346 query-allele rows x 4684 array-allele columns; strain IDs carry a
     library suffix after the systematic name (_tsq###/_sn###/_S### for
     query alleles = essential TS-query / non-essential deletion-query /
     other; _tsa###/_dma### for array alleles = essential TS-array /
     non-essential deletion-array). Systematic ORF name = substring before
     the first "_" (ORF names never contain "_").

Method
------
1. Parse row/column labels -> systematic ORF name (strip library suffix).
2. Aggregate replicate alleles of the same gene by nanmean, separately for
   rows (query side) and columns (array side), producing a
   gene(query) x gene(array) epsilon-score matrix (~4939 x 4450 after
   aggregation; union of query/array universes = 5707 genes, overlap 3682).
3. "Genetic interaction profile" of a gene = its row (as query, measured
   against the array collection) when it was screened as a query. Pairwise
   similarity = Pearson correlation between two genes' query profiles,
   computed EXACTLY over the pairwise-complete (shared non-missing array
   columns) subset via the sufficient-statistics / matmul identity:
       n(i,j)      = mask_i . mask_j                (shared column count)
       sum_x(i,j)  = (x_i*mask_i) . mask_j
       sum_x2(i,j) = (x_i^2*mask_i) . mask_j
       sum_xy(i,j) = (x_i*mask_i) . (x_j*mask_j)
       r = (n*sum_xy - sum_x*sum_y) / sqrt((n*sum_x2-sum_x^2)*(n*sum_y2-sum_y^2))
   (sum_y, sum_y2 obtained by transposing the sum_x, sum_x2 matrices — the
   identity is symmetric in the two indices.) This is the same result you'd
   get from `pandas.DataFrame.corr()` pairwise-complete, just vectorized as
   4 matmuls so the full ~4939x4939 matrix is computed in a couple of
   seconds instead of a Python double loop. No shortcuts/approximations are
   taken in the correlation itself.
4. Overall matrix nan-fraction ~54% (block-structured: ExE/ExN/NxN screens
   don't share the same query x array combinations), so a MINIMUM SHARED
   OVERLAP threshold (--min-overlap, default 50) is required before two
   genes' correlation is trusted; pairs below threshold are excluded as
   neighbor candidates (this mirrors Costanzo et al.'s own practice of only
   trusting profile correlations backed by enough shared measurements).
5. Genes that were ONLY ever screened as an array strain (never as a query;
   ~768 genes) have no query-profile row. For those, and only those, we
   fall back to the symmetric computation on the ARRAY side (correlate
   their columns against all other array columns) so they still get a
   neighbor list. This fallback is clearly separable in the output (see
   `--stats` sidecar) but not distinguished per-key in the JSON itself
   (schema is fixed by the task spec).
6. Output: top --top-n (default 25) neighbors per gene, ranked by
   correlation descending, self excluded.

Usage:
    python build_pert_sim.py [--top-n 25] [--min-overlap 50] \
        [--gi-file /path/to/Genetic.interaction.score.tsv] \
        [--out /home/zhengz2/yeast-vecell/data/knowledge/perturbagen_similarity.json]

Idempotent: re-running with the same inputs/args overwrites the same output
deterministically (no randomness anywhere in the pipeline).
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_GI_FILE = "/home/zhengz2/yeast-rank-cross-lab/data/folder1_GI_raw/Genetic.interaction.score.tsv"
DEFAULT_OUT = "/home/zhengz2/yeast-vecell/data/knowledge/perturbagen_similarity.json"


def orf_of(label: str) -> str:
    """Systematic ORF name = substring before the first underscore.
    Systematic ORF names (e.g. YFL039C, YBR058C-A) never contain '_'."""
    return label.split("_", 1)[0]


def load_matrix(path: str) -> pd.DataFrame:
    t0 = time.time()
    df = pd.read_csv(path, sep="\t", index_col=0, na_values=["NA"])
    print(f"[load] {df.shape} in {time.time()-t0:.1f}s", file=sys.stderr)
    return df


def aggregate_to_genes(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse replicate alleles (rows and columns) of the same gene via nanmean."""
    row_genes = pd.Index([orf_of(r) for r in df.index])
    col_genes = pd.Index([orf_of(c) for c in df.columns])
    df2 = df.copy()
    df2.index = row_genes
    df2.columns = col_genes
    agg_rows = df2.groupby(level=0).mean()
    agg = agg_rows.T.groupby(level=0).mean().T
    print(f"[aggregate] {df.shape} alleles -> {agg.shape} genes "
          f"({agg.index.size} query genes x {agg.columns.size} array genes)",
          file=sys.stderr)
    return agg


def exact_pairwise_corr(M: np.ndarray):
    """Exact pairwise-complete-observations Pearson correlation between ROWS of M,
    vectorized via matmul sufficient statistics. Returns (corr, count) both
    shape (n_rows, n_rows)."""
    mask = (~np.isnan(M)).astype(np.float64)
    Xf = np.nan_to_num(M, nan=0.0)
    X2f = Xf * Xf

    A = Xf @ mask.T     # A[i,j]  = sum over shared cols of x_i
    B = X2f @ mask.T     # B[i,j]  = sum over shared cols of x_i^2
    C = mask @ mask.T    # C[i,j]  = n shared cols
    D = Xf @ Xf.T        # D[i,j]  = sum over shared cols of x_i*x_j

    num = C * D - A * A.T
    denx = C * B - A * A
    deny = C * B.T - A.T * A.T
    with np.errstate(invalid="ignore", divide="ignore"):
        denom = np.sqrt(np.clip(denx * deny, 0, None))
        corr = np.where(denom > 1e-9, num / np.where(denom == 0, 1, denom), np.nan)
    np.fill_diagonal(corr, np.nan)
    np.fill_diagonal(C, 0)
    return corr, C


def top_neighbors(genes: np.ndarray, corr: np.ndarray, count: np.ndarray,
                   min_overlap: int, top_n: int) -> dict:
    out = {}
    n = len(genes)
    for i in range(n):
        c = corr[i]
        ov = count[i]
        valid = (ov >= min_overlap) & np.isfinite(c)
        if not valid.any():
            out[genes[i]] = []
            continue
        scores = np.where(valid, c, -np.inf)
        order = np.argsort(-scores)[:top_n]
        order = [j for j in order if np.isfinite(scores[j])]
        out[genes[i]] = [str(genes[j]) for j in order]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gi-file", default=DEFAULT_GI_FILE)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--top-n", type=int, default=25)
    ap.add_argument("--min-overlap", type=int, default=50,
                     help="minimum shared non-missing array-columns required to trust a correlation")
    args = ap.parse_args()

    gi_path = Path(args.gi_file)
    if not gi_path.exists():
        print(f"ERROR: genetic interaction file not found: {gi_path}", file=sys.stderr)
        sys.exit(1)

    df = load_matrix(str(gi_path))
    agg = aggregate_to_genes(df)  # query genes (rows) x array genes (cols)

    query_genes = agg.index.to_numpy()
    array_genes = agg.columns.to_numpy()

    # --- primary network: query-profile correlation (covers genes screened as query) ---
    t0 = time.time()
    corr_q, count_q = exact_pairwise_corr(agg.values.astype(np.float64))
    print(f"[primary corr] query x query {corr_q.shape} in {time.time()-t0:.1f}s", file=sys.stderr)
    primary = top_neighbors(query_genes, corr_q, count_q, args.min_overlap, args.top_n)

    # --- fallback network: array-profile correlation, for array-only genes ---
    query_set = set(query_genes.tolist())
    array_only = [g for g in array_genes.tolist() if g not in query_set]
    result = dict(primary)
    n_fallback = 0
    if array_only:
        t0 = time.time()
        Mt = agg.values.T.astype(np.float64)  # array genes x query genes
        corr_a, count_a = exact_pairwise_corr(Mt)
        print(f"[fallback corr] array x array {corr_a.shape} in {time.time()-t0:.1f}s", file=sys.stderr)
        fallback_all = top_neighbors(array_genes, corr_a, count_a, args.min_overlap, args.top_n)
        for g in array_only:
            result[g] = fallback_all.get(g, [])
            n_fallback += 1

    n_empty = sum(1 for v in result.values() if len(v) == 0)
    print(f"[summary] genes with neighbors: {len(result)} "
          f"(primary/query-profile: {len(primary)}, array-profile fallback: {n_fallback}); "
          f"genes with 0 neighbors after min-overlap filter: {n_empty}", file=sys.stderr)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=1, sort_keys=True)
    print(f"[write] {out_path} ({len(result)} genes)", file=sys.stderr)


if __name__ == "__main__":
    main()
