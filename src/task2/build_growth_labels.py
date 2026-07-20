#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build Task 2 (perturbation -> growth phenotype, framing A) DE/DIR-analog label CSVs.

Mirrors the Task 1 Deleteome ``prepare`` stage
(``src/cli_pipeline/stages/prepare.py``) as closely as the data allows, so the
downstream retrieve/prompt/infer pipeline stays data-agnostic:

    Task 1 (expression):  pert = deleted gene   | gene    = readout ORF  | label = DE hit
    Task 2 (growth, this):pert = deleted gene   | context = screen/condition | label = phenotype hit

INPUT DATA (read-only; lives in the user's separate ``yeast-rank-cross-lab``
repo, never copied wholesale here because the raw matrix is ~600-900 MB):

  - ``yp_matrix_z_haphom_20221025.txt`` — 4,554 genes (rows, systematic ORF
    names -- already the canonical key, no alias mapping needed) x 14,484
    genome-scale knockout screens (columns, screen ids). Values are
    **column-wise z-scores relative to the estimated mode** of a "cleaned but
    unnormalized" phenotypic fitness/growth score. This assembles the
    "hap"/"hom" (haploid + homozygous diploid, i.e. non-essential-gene)
    deletion-collection screens curated by yeastphenome.org from >100
    published chemogenomic papers (Hillenmeyer 2008's HOP arm is 273 of these
    14,484 columns; see ``data/perturbation/hillenmeyer2008/``).
  - ``yp_screens_haphom_20221025.txt`` — per-screen metadata: id, name,
    collection, phenotype, conditionset (the actual condition, e.g. a
    chemical + dose), medium, paper, pmid, num_tested.

We restrict to screens whose ``phenotype`` field contains "growth" (colony
size / pooled culture / spot assay / exponential rate / ...), which is the
same filter ``yeast-rank-cross-lab/src/features/build_fixed_panels.py`` uses
to build its ``growth_panel_matrix.pkl`` (we recompute from the raw txt
here instead of depending on that pickle, so this builder has no dependency
on the other repo's derived artifacts, only its raw inputs).

A parallel "het" (heterozygous, essential-gene, HIP-style) matrix also
exists at ``yp_het/yp_matrix_het_z_20221018.txt`` (4,554/5,639 genes x 7,011
screens) but is NOT the same screen population as the growth/haphom matrix
(different collection, different gene panel scope -- see the Task 2 report
for the full comparison). This builder uses haphom/growth as the primary
Task 2-A source per the project's decision; a ``--matrix het`` mode is
provided for symmetry/experimentation but is not the default.

LABELING RULE (documented threshold choice):
  - Values here are already column-wise z-scores (mode-relative). Under a
    standard-normal null this is directly comparable to a two-tailed p-value
    cutoff: |z| >= 2.0 corresponds to ~nominal p < 0.05 (two-tailed), which
    is also the range of cutoffs (z ~ 2-3) commonly used to call chemogenomic
    fitness-defect "hits" in this literature (Hillenmeyer 2008, Pierce 2007).
    Empirically on this matrix, |z| >= 2.0 flags 4.66% of all measured cells
    as hits (close to the 5% nominal rate), with a median of 208 hits per
    gene (mean 331, max 2,665 of ~7,689 growth screens) -- i.e. not
    pathologically skewed by a handful of universally-sick strains. Default:
    ``--threshold 2.0``; ``--threshold 3.0`` is offered as a stricter option
    (1.56% hit rate) if a cleaner/lower-noise label set is wanted at the cost
    of fewer positives.
  - DE-analog label = 1 if |z| >= threshold, else sampled from a confident
    negative pool (|z| < --neg-threshold, default 0.25), capped at --n-neg
    (default 200) per perturbagen -- mirroring Task 1's negative-sampling
    convention exactly. All positives are kept (no cap), also mirroring
    Task 1.
  - DIR-analog label (direction), restricted to DE-analog positives only:
    label = 1 if z > 0 ("more resistant" / fitter than the panel mode in
    that condition), label = 0 if z < 0 ("more sensitive" / fitness defect).
    CAVEAT: yeastphenome.org harmonizes gene identifiers across its >100
    source papers, but does NOT independently re-verify that every source
    paper's raw score orientation follows the "higher = fitter" convention.
    This is the standard convention for growth/fitness-ratio phenotypes and
    should hold for the overwhelming majority of the ~7,689 growth-labeled
    screens, but has not been manually re-checked screen-by-screen here.
    Treat DIR as "above-mode vs below-mode" with a strong prior that this
    equals "resistant vs sensitive", not an independently-audited ground
    truth per screen.

SPLIT: by perturbagen (gene), 30% train / 70% test, seed 42 -- identical
convention to Task 1 (``train_fraction=0.3, seed=42``), so a perturbagen's
rows never straddle train/test.

OUTPUTS (written only here, under yeast-vecell/data/task2/):
  - ``{name}_growth_phenotype.csv``  columns: pert, context, label, split
  - ``{name}_growth_direction.csv``  columns: pert, context, label, split
  - ``{name}_growth_contexts.csv``   side table: context, conditionset,
    medium, phenotype, collection, paper, pmid, num_tested (for building
    human-readable condition descriptions later, analogous to Task 1's
    gene_desc.json).

Idempotent: if all three output files already exist, the run is skipped
(prints a message) unless ``--force`` is given. Same inputs + same CLI args
+ same seed always reproduce byte-identical positive/negative rows (numpy
``default_rng(seed)`` consumed in fixed row order).
"""

import argparse
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd

RANK_CROSS_LAB = "/home/zhengz2/yeast-rank-cross-lab"  # READ-ONLY, never write here.
DEFAULT_MATRIX = f"{RANK_CROSS_LAB}/data/folder8_raw/yp_matrix_z_haphom_20221025.txt"
DEFAULT_META = f"{RANK_CROSS_LAB}/data/folder8_raw/yp_screens_haphom_20221025.txt"
HET_MATRIX = f"{RANK_CROSS_LAB}/data/folder8_raw/yp_het/yp_matrix_het_z_20221018.txt"
HET_META = f"{RANK_CROSS_LAB}/data/folder8_raw/yp_het/yp_screens_het_20221018.txt"

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "data", "task2"))


def load_growth_matrix(matrix_path: str, meta_path: str) -> pd.DataFrame:
    """Load the z-scored perturbation x screen matrix, restricted to columns
    whose screen metadata `phenotype` contains "growth" (case-insensitive).

    Returns a DataFrame: index = perturbagen (systematic ORF), columns =
    screen id (str), values = column-wise mode-relative z-score (float),
    NaN where untested.
    """
    print(f"Loading matrix: {matrix_path}", file=sys.stderr)
    mat = pd.read_csv(matrix_path, sep="\t", index_col=0)
    mat.columns = mat.columns.astype(str)
    print(f"  raw shape: {mat.shape[0]} genes x {mat.shape[1]} screens", file=sys.stderr)

    meta = pd.read_csv(meta_path, sep="\t", dtype=str)
    is_growth = meta["phenotype"].str.contains("growth", case=False, na=False)
    growth_ids = [c for c in meta.loc[is_growth, "id"].tolist() if c in mat.columns]
    print(f"  growth-phenotype screens: {len(growth_ids)}/{mat.shape[1]}", file=sys.stderr)

    growth = mat[growth_ids]
    growth_meta = meta[meta["id"].isin(growth_ids)].set_index("id").reindex(growth_ids)
    return growth, growth_meta


def build_labels(
    growth: pd.DataFrame,
    *,
    threshold: float,
    neg_threshold: float,
    n_neg: int,
    train_fraction: float,
    seed: int,
):
    genes = growth.index.tolist()
    contexts = growth.columns.tolist()
    vals = growth.values.astype(np.float64)
    n_genes, n_ctx = vals.shape

    abs_vals = np.abs(vals)
    finite = ~np.isnan(vals)
    pos_mask = finite & (abs_vals >= threshold)
    neg_pool_mask = finite & (abs_vals < neg_threshold)

    # ---- split perturbagens 30/70, seed 42 (mirrors Task 1 exactly) ----
    perts_shuffled = list(genes)
    rng_split = np.random.RandomState(seed)
    rng_split.shuffle(perts_shuffled)
    n_train = int(len(perts_shuffled) * train_fraction)
    train_set = set(perts_shuffled[:n_train])
    print(f"Split: {len(train_set)} train / {len(perts_shuffled) - len(train_set)} test "
          f"perturbagens (train_fraction={train_fraction}, seed={seed})", file=sys.stderr)

    rng_neg = np.random.default_rng(seed)

    phen_rows = []  # (pert, context, label, split)
    dir_rows = []   # (pert, context, label, split)

    for gi, gene in enumerate(genes):
        split = "train" if gene in train_set else "test"
        row = vals[gi]

        pos_idx = np.nonzero(pos_mask[gi])[0]
        for ci in pos_idx:
            phen_rows.append((gene, contexts[ci], 1, split))
            dir_rows.append((gene, contexts[ci], 1 if row[ci] > 0 else 0, split))

        neg_idx = np.nonzero(neg_pool_mask[gi])[0]
        if len(neg_idx) > 0:
            k = min(n_neg, len(neg_idx))
            chosen = rng_neg.choice(neg_idx, size=k, replace=False)
            for ci in chosen:
                phen_rows.append((gene, contexts[ci], 0, split))

    phen_df = pd.DataFrame(phen_rows, columns=["pert", "context", "label", "split"])
    dir_df = pd.DataFrame(dir_rows, columns=["pert", "context", "label", "split"])
    return phen_df, dir_df, len(genes), len(contexts)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matrix", default=DEFAULT_MATRIX,
                    help="perturbation x screen z-score matrix (tab-delimited, read-only)")
    ap.add_argument("--meta", default=DEFAULT_META,
                    help="screen metadata file (tab-delimited, read-only)")
    ap.add_argument("--use-het", action="store_true",
                    help="use the het (HIP, essential-gene, heterozygous) matrix instead of "
                         "the default haphom/growth matrix")
    ap.add_argument("--name", default="haphom_growth",
                    help="output file prefix (default: haphom_growth)")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--threshold", type=float, default=2.0,
                    help="|z| >= threshold => growth-phenotype positive (default 2.0, "
                         "~nominal two-tailed p<0.05; empirically 4.66%% hit rate)")
    ap.add_argument("--neg-threshold", type=float, default=0.25,
                    help="|z| < neg-threshold => confident-negative pool (default 0.25)")
    ap.add_argument("--n-neg", type=int, default=200,
                    help="max sampled negatives per perturbagen (default 200, mirrors Task 1)")
    ap.add_argument("--train-fraction", type=float, default=0.3,
                    help="fraction of perturbagens assigned to train (default 0.3 => 30/70)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--force", action="store_true", help="recompute even if outputs exist")
    args = ap.parse_args()

    if args.use_het and args.matrix == DEFAULT_MATRIX:
        args.matrix, args.meta = HET_MATRIX, HET_META
        if args.name == "haphom_growth":
            args.name = "het_growth"

    os.makedirs(args.out_dir, exist_ok=True)
    phen_path = os.path.join(args.out_dir, f"{args.name}_phenotype.csv")
    dir_path = os.path.join(args.out_dir, f"{args.name}_direction.csv")
    ctx_path = os.path.join(args.out_dir, f"{args.name}_contexts.csv")

    if not args.force and all(os.path.exists(p) for p in (phen_path, dir_path, ctx_path)):
        print(f"All outputs already exist under {args.out_dir} (name={args.name}); "
              f"skipping (use --force to rebuild).")
        return

    print(f"\n{'=' * 20} Task 2 growth labels: '{args.name}' {'=' * 20}", file=sys.stderr)
    growth, growth_meta = load_growth_matrix(args.matrix, args.meta)

    phen_df, dir_df, n_genes, n_ctx = build_labels(
        growth,
        threshold=args.threshold,
        neg_threshold=args.neg_threshold,
        n_neg=args.n_neg,
        train_fraction=args.train_fraction,
        seed=args.seed,
    )

    phen_df.to_csv(phen_path, index=False)
    dir_df.to_csv(dir_path, index=False)

    ctx_out = growth_meta.reset_index().rename(columns={"id": "context"})
    keep_cols = [c for c in ["context", "conditionset", "medium", "phenotype", "collection",
                              "paper", "pmid", "num_tested"] if c in ctx_out.columns]
    ctx_out[keep_cols].to_csv(ctx_path, index=False)

    n_pos = int((phen_df["label"] == 1).sum())
    n_neg_out = int((phen_df["label"] == 0).sum())
    n_res = int((dir_df["label"] == 1).sum())
    n_sens = int((dir_df["label"] == 0).sum())
    print(f"\nPerturbagens (genes): {n_genes} | Contexts (growth screens): {n_ctx}")
    print(f"Saved phenotype CSV: {phen_path}  (rows={len(phen_df)}, "
          f"phenotype={n_pos}, no_phenotype={n_neg_out})")
    print(f"Saved direction  CSV: {dir_path}  (rows={len(dir_df)}, "
          f"resistant={n_res}, sensitive={n_sens})")
    print(f"Saved contexts   CSV: {ctx_path}  (rows={len(ctx_out)})")
    print("Done.")


if __name__ == "__main__":
    main()
