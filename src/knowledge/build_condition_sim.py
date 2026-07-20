#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build condition-condition similarity for Task2 (growth) retrieval.

Two growth screens are "similar" if their gene-deletion fitness profiles
correlate across the 4554-gene panel. Source = the yp_matrix_z_haphom matrix
(rows=genes, cols=screens, values=column-wise z-scores). We restrict to the 7689
growth screens (== context ids in haphom_growth_contexts.csv, which equal the yp
column headers) and output top-N most-correlated conditions per condition.

Output: data/knowledge/condition_similarity.json  {context_id: [context_id, ...]}
used as the ``--gene-sim`` (readout-neighbor) map for Task2 retrieval.
"""

import json
import os

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
YP = "/home/zhengz2/yeast-rank-cross-lab/data/folder8_raw/yp_matrix_z_haphom_20221025.txt"
CTX = os.path.join(REPO, "data", "task2", "haphom_growth_contexts.csv")
OUT = os.path.join(REPO, "data", "knowledge", "condition_similarity.json")
TOPN = 25


def main() -> None:
    growth = pd.read_csv(CTX)["context"].astype(str).tolist()
    gset = set(growth)
    usecols = lambda c: (str(c) in gset) or c in ("", "Unnamed: 0")
    print(f"Loading yp matrix (growth cols only) from {YP} ...")
    df = pd.read_csv(YP, sep="\t", index_col=0, usecols=usecols, low_memory=False)
    cols = [str(c) for c in df.columns]
    print(f"  genes={df.shape[0]}  growth screens={df.shape[1]}")

    X = df.values.astype(np.float32)                       # genes x screens
    mu = np.nanmean(X, axis=0)
    sd = np.nanstd(X, axis=0); sd[sd == 0] = 1.0
    Xs = np.nan_to_num((X - mu) / sd, nan=0.0)             # standardize, fill 0
    n = Xs.shape[0]
    C = (Xs.T @ Xs) / n                                    # ~Pearson between screens
    np.fill_diagonal(C, -np.inf)

    out = {}
    for j, cid in enumerate(cols):
        idx = np.argpartition(-C[j], TOPN)[:TOPN]
        idx = idx[np.argsort(-C[j][idx])]
        out[cid] = [cols[k] for k in idx]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f)
    print(f"Saved {OUT}: {len(out)} conditions, top-{TOPN} each")
    print(f"  sample {cols[0]} -> {out[cols[0]][:5]}")


if __name__ == "__main__":
    main()
