#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare DE/DIR CSV datasets from the Deleteome perturbation matrix.

This is the yeast port of VCWorld's ``prepare`` stage. VCWorld starts from raw
single-cell ``.h5ad`` counts and runs scanpy ``rank_genes_groups`` (Wilcoxon vs
DMSO) to derive per-(drug, gene) log-fold-changes and p-values. Deleteome
already ships those values (channel M = log2(mutant/WT), p = p-value per
gene x deletion-strain), so we skip scanpy entirely and just threshold.

Deleteome file format (tab-delimited, verified):
  - header row 1: condition names, each repeated 3x, e.g. "swd1-del vs. wt".
  - header row 2: "dataType" then the sub-labels "M A p_value" per condition.
  - columns 1-3: reporterId, systematicName, geneSymbol.
  - then every condition contributes 3 columns: M, A (intensity), p_value.

IDENTIFIER NOTE (important, recorded here and logged at runtime):
  - The perturbagen ``pert`` is a *lowercase standard gene name* (e.g. "swd1"),
    parsed from the deletion-strain condition token.
  - The readout ``gene`` is a *systematic ORF name* (column 2 systematicName,
    e.g. "YFL039C" / "Q0010").
  These two namespaces are NOT unified here on purpose. A later
  alias-normalization step (separate work) will map standard <-> systematic
  names so retrieval/description lookups line up. Do NOT block on it.
"""

import os
import re
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

# The 3 internal control comparisons (matA background, BY4743, YPD) that must be
# skipped. They are identified structurally: a *deletion* strain's left-hand-side
# token (before " vs") always contains "-del"; the control comparisons never do
# (their LHS is "wt-matA" / "wt-by4743" / "wt-ypd"). This structural rule is
# safer than a substring match on "wt-matA", because 11 real deletion strains
# (e.g. "swd1-del-matA vs. wt-matA") also contain the literal "wt-matA", and real
# genes WTM1/WTM2 give "wtm1-del vs. wt" / "wtm2-del vs. wt".
_VS_SPLIT = re.compile(r"\s+vs", flags=re.IGNORECASE)


def _lhs(condition: str) -> str:
    """Left-hand side of a Deleteome condition, e.g. 'swd1-del-matA'."""
    return _VS_SPLIT.split(condition, maxsplit=1)[0].strip()


def _is_control(condition: str) -> bool:
    """True for the 3 internal control comparisons (no '-del' on the LHS)."""
    return "-del" not in _lhs(condition).lower()


def parse_perturbagen(condition: str) -> str:
    """Standard (lowercase) gene name of the deleted gene from a condition token.

    'ptc1-del vs. wt'              -> 'ptc1'
    'swd1-del-matA vs. wt-matA'    -> 'swd1'
    'atg4-del-1 vs. wt'            -> 'atg4'
    """
    return _lhs(condition).split("-del")[0].strip().lower()


def _read_deleteome(path: str) -> Tuple[pd.DataFrame, List[str]]:
    """Return (data_df without the 2 header rows, list of condition names).

    ``data_df`` columns are positional integers: 0=reporterId, 1=systematicName,
    2=geneSymbol, then M/A/p triples per condition.
    """
    with open(path, "r", encoding="utf-8") as f:
        row1 = f.readline().rstrip("\n").split("\t")
    condition_names = row1[3:][0::3]  # every 3rd column, starting at the 4th
    # skiprows=[0,1] drops the condition-name row and the "dataType/M/A/p" row.
    df = pd.read_csv(path, sep="\t", skiprows=[0, 1], header=None, low_memory=False)
    return df, condition_names


def process_deleteome(
    *,
    input_path: str,
    output_dir: str,
    name: str,
    lfc: float = 0.766,
    fdr: float = 0.05,
    pval_neg: float = 0.1,
    n_neg: int = 200,
    train_fraction: float = 0.3,
    seed: int = 42,
    max_perts: Optional[int] = None,
) -> None:
    """Build ``{name}_DE.csv`` and ``{name}_DIR.csv`` from the Deleteome matrix.

    DE label = 1 if (p < fdr) and (|M| > lfc). Deleteome's native call is
    FC > 1.7 & p < 0.05, i.e. |M| > ~0.766, so those are the defaults.
    DE label = 0 sampled (n_neg per perturbagen, seeded) from genes with p > pval_neg.
    DIR label = 1 if M > 0 else 0, among DE hits only.
    Perturbagens are split train/test by ``train_fraction`` (0.3 => 30% train).
    """
    print(f"\n{'=' * 20} Deleteome -> DE/DIR for '{name}' {'=' * 20}")
    print(f"Reading matrix: {input_path}")
    df, condition_names = _read_deleteome(input_path)
    n_rows = len(df)
    print(f"Loaded {n_rows} readout genes x {len(condition_names)} conditions")
    print("IDENTIFIER NAMESPACES: pert = lowercase standard gene name "
          "(e.g. 'swd1'); readout gene = systematic ORF name (column 2, "
          "e.g. 'YFL039C'). Alias unification is a separate later step.")

    systematic_names = df.iloc[:, 1].astype(str).values  # readout gene = ORF

    # ---- Identify deletion perturbagens (skip the 3 controls) --------------
    deletion_conditions: List[Tuple[int, str, str]] = []  # (col_index, cond, pert)
    controls: List[str] = []
    for i, cond in enumerate(condition_names):
        if _is_control(cond):
            controls.append(cond)
            continue
        m_col = 3 + 3 * i  # M is the first of each condition's 3 columns
        deletion_conditions.append((m_col, cond, parse_perturbagen(cond)))
    print(f"Deletion perturbagens: {len(deletion_conditions)} | "
          f"skipped controls: {controls}")

    if max_perts is not None and max_perts < len(deletion_conditions):
        deletion_conditions = deletion_conditions[:max_perts]
        print(f"[subset] limited to first {max_perts} perturbagens for speed")

    # ---- train/test split by perturbagen -----------------------------------
    perts = [p for (_, _, p) in deletion_conditions]
    perts_shuffled = perts.copy()
    rng_split = np.random.RandomState(seed)
    rng_split.shuffle(perts_shuffled)
    n_train = int(len(perts_shuffled) * train_fraction)
    train_set = set(perts_shuffled[:n_train])
    print(f"Split: {len(train_set)} train / "
          f"{len(perts_shuffled) - len(train_set)} test perturbagens "
          f"(train_fraction={train_fraction}, seed={seed})")

    # ---- label every (pert, readout gene) cell -----------------------------
    rng_neg = np.random.default_rng(seed)
    de_records: List[dict] = []   # positives + sampled negatives
    dir_records: List[dict] = []  # positives only, with direction

    for m_col, cond, pert in deletion_conditions:
        m = pd.to_numeric(df.iloc[:, m_col], errors="coerce").values      # logFC
        p = pd.to_numeric(df.iloc[:, m_col + 2], errors="coerce").values  # p_value
        valid = ~np.isnan(m) & ~np.isnan(p)
        split = "train" if pert in train_set else "test"

        # positive DE hits: significant p AND large |M|
        pos_mask = valid & (p < fdr) & (np.abs(m) > lfc)
        pos_idx = np.nonzero(pos_mask)[0]
        for gi in pos_idx:
            de_records.append({"pert": pert, "gene": systematic_names[gi],
                               "label": 1, "split": split})
            dir_records.append({"pert": pert, "gene": systematic_names[gi],
                                "label": 1 if m[gi] > 0 else 0, "split": split})

        # negative DE examples: clearly non-significant (p > pval_neg), sampled
        neg_candidates = np.nonzero(valid & (p > pval_neg))[0]
        if len(neg_candidates) > 0:
            k = min(n_neg, len(neg_candidates))
            chosen = rng_neg.choice(neg_candidates, size=k, replace=False)
            for gi in chosen:
                de_records.append({"pert": pert, "gene": systematic_names[gi],
                                   "label": 0, "split": split})

    de_df = pd.DataFrame(de_records, columns=["pert", "gene", "label", "split"])
    dir_df = pd.DataFrame(dir_records, columns=["pert", "gene", "label", "split"])

    os.makedirs(output_dir, exist_ok=True)
    de_path = os.path.join(output_dir, f"{name}_DE.csv")
    dir_path = os.path.join(output_dir, f"{name}_DIR.csv")
    de_df.to_csv(de_path, index=False)
    dir_df.to_csv(dir_path, index=False)

    n_pos = int((de_df["label"] == 1).sum())
    n_neg_out = int((de_df["label"] == 0).sum())
    print(f"Saved DE  CSV: {de_path}  "
          f"(rows={len(de_df)}, pos={n_pos}, neg={n_neg_out})")
    print(f"Saved DIR CSV: {dir_path}  "
          f"(rows={len(dir_df)}, up={int((dir_df['label'] == 1).sum())}, "
          f"down={int((dir_df['label'] == 0).sum())})")
    print("Done.")
