#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 2B ``prepare`` retrofit: adapt gene-pair label CSVs to the shared
pert/gene/label/split schema so the existing (Task 1/2A) ``retrieve``/``prompt``
CLI stages can consume them unmodified.

Why an adapter instead of touching ``stages/retrieve.py``/``stages/prompt.py``:
those two stages already generalize the *readout* column name via
``--readout-col`` (Task1="gene", Task2A="context"), but they hard-code the
*perturbagen* column name to literally ``"pert"`` (``stages/retrieve.py``'s
``load_data`` does ``df["pert"]``). Task 2B's labels
(``src/task2/build_sga_labels.py`` output) use ``pertA``/``pertB`` instead of a
single ``pert``, because the perturbagen is itself a GENE PAIR, not one gene
plus a fixed readout. Renaming ``pertA -> pert`` and ``pertB -> gene`` is a
zero-information-loss relabeling (both are systematic ORFs; the retrieval
mining logic in ``stages/retrieve.py`` treats ``pert``'s "seen genes" and
``gene``'s "seen perts" symmetrically enough that this works), so the cheapest
correct fix is this adapter, not a new CLI code path.

Usage:
  python src/task2b/prepare_pairs.py \
      --de-csv data/task2/sga_DE.csv --dir-csv data/task2/sga_DIR.csv \
      --out-dir data/task2b --name sga

Produces ``{out_dir}/{name}_DE_pairs.csv`` / ``{name}_DIR_pairs.csv`` with
columns ``pert,gene,label,split`` (pert=Gene A / SGA query, gene=Gene B / SGA
array partner). ``--sample-n`` (per split, stratified by label) subsamples for
smoke tests / pilot runs -- the full sga_DE.csv is 958,464 rows (806,963 test),
far beyond what's practical to hand to an LLM without a sampling decision (see
docs/task_definitions.md Task 2B and the task-scale estimate in the handoff
report).
"""

import argparse
import os
from typing import Optional

import numpy as np
import pandas as pd


def _stratified_sample(df: pd.DataFrame, n: Optional[int], seed: int) -> pd.DataFrame:
    """Sample up to ``n`` rows per split, stratified by label (keeps class mix)."""
    if n is None:
        return df
    rng = np.random.RandomState(seed)
    parts = []
    for split, sdf in df.groupby("split"):
        for label, ldf in sdf.groupby("label"):
            k = min(n, len(ldf))
            idx = rng.choice(ldf.index.values, size=k, replace=False)
            parts.append(df.loc[idx])
    out = pd.concat(parts).sample(frac=1, random_state=seed) if parts else df.iloc[0:0]
    return out.reset_index(drop=True)


def adapt_pairs_csv(in_csv: str, out_csv: str, *,
                    sample_n: Optional[int] = None, seed: int = 42) -> pd.DataFrame:
    """Rename pertA/pertB -> pert/gene; optionally stratified-subsample per split."""
    df = pd.read_csv(in_csv)
    missing = {"pertA", "pertB", "label", "split"} - set(df.columns)
    if missing:
        raise ValueError(f"{in_csv}: missing expected columns {missing}")
    df = df.rename(columns={"pertA": "pert", "pertB": "gene"})
    df = df[["pert", "gene", "label", "split"]]
    if sample_n is not None:
        df = _stratified_sample(df, sample_n, seed)
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    df.to_csv(out_csv, index=False)
    return df


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Task 2B prepare: adapt sga_DE/DIR "
                                              "csv (pertA,pertB) to pert/gene schema")
    ap.add_argument("--de-csv", required=True, help="src/task2/build_sga_labels.py DE output")
    ap.add_argument("--dir-csv", required=True, help="src/task2/build_sga_labels.py DIR output")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--name", default="sga", help="output prefix -> {name}_DE_pairs.csv / _DIR_pairs.csv")
    ap.add_argument("--sample-n", type=int, default=None,
                    help="stratified cap per (split,label) cell; omit for full data")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    de_out = os.path.join(args.out_dir, f"{args.name}_DE_pairs.csv")
    dir_out = os.path.join(args.out_dir, f"{args.name}_DIR_pairs.csv")

    de_df = adapt_pairs_csv(args.de_csv, de_out, sample_n=args.sample_n, seed=args.seed)
    dir_df = adapt_pairs_csv(args.dir_csv, dir_out, sample_n=args.sample_n, seed=args.seed)

    print(f"[prepare_pairs] DE  -> {de_out}  rows={len(de_df)}  "
          f"(train={int((de_df.split=='train').sum())}, test={int((de_df.split=='test').sum())}, "
          f"pos={int((de_df.label==1).sum())}, neg={int((de_df.label==0).sum())})")
    print(f"[prepare_pairs] DIR -> {dir_out}  rows={len(dir_df)}  "
          f"(train={int((dir_df.split=='train').sum())}, test={int((dir_df.split=='test').sum())}, "
          f"pos={int((dir_df.label==1).sum())}, neg={int((dir_df.label==0).sum())})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
