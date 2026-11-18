#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变体4 (T2A only): 训练型矩阵分解对照 -- NRBdMF/SRMF 思路的低秩矩阵补全，在
与 LLM 完全同一个 train/test split 上训练和评测 T2A-DE / T2A-DIR。

跟 docs/prompt_optimization.md "变体4" 一节的通用设计（特征驱动的逻辑回归/随机森林，
适合 T1 那种"扰动子-基因对"结构）不同，T2A 天然是一个 **基因 x 条件** 矩阵（Hillenmeyer
2008 HOP，4554 基因 x 273 条件的 z-score 子矩阵），这正是 NRBdMF/SRMF 这类药物敏感性
预测 baseline 的标准输入形状，所以 T2A 专门实现矩阵分解版本，而不是套用通用特征分类器。

方法（细节见模块内 docstring 与函数注释）：
  1. 训练矩阵 = 只用 hillenmeyer_phenotype.csv 里 split=='train' 的 (gene, context) 格子，
     取值是原始 yp_matrix_z_haphom 的连续 z-score（不是阈值化后的 0/1）——直接对连续
     响应值做低秩重构，比对 0/1 label 做分解携带更多信息，这也是 SRMF 系论文的做法
     （先重构连续响应矩阵，再阈值化/取符号）。
  2. ALS（交替最小二乘，bias-augmented biased matrix factorization）手写实现，
     不依赖额外安装库。
  3. **关键结构限制（已用真实数据核实）**：本项目的 T2A split 是按基因整体切分
     （30%基因训练/70%基因测试，train/test 基因集合零重叠，273个条件在 train/test 里
     完全共享）——也就是说**每一个 test 基因都是行意义上的完全冷启动**，训练矩阵里
     不存在任何一行是 test 基因。标准 ALS 无法为这些行学出隐向量。
     处理方式（fold-in，不触碰任何 train/test label 本身）：对每个 test 基因，从
     yp_matrix_z_haphom 原始矩阵里找出该基因在 273 个 Hillenmeyer 条件下**既不在
     train 也不在 test 标签表里**的"未采样格子"（真实测量值，只是没被两份 label CSV
     采样进去），用这些格子的真实 z 值对固定的条件隐向量做一次岭回归 fold-in，解出
     该基因的隐向量，再预测 test 格子的分数。少数 pool 格子不足（<3个）的基因退化成
     "只用训练学到的条件偏置"（context-level fallback，不是全局常数）。
  4. 阈值/符号判定：DE 的连续分数阈值在训练内部划出的验证集上校准（不摸 test）；
     DIR 直接看分数符号（也在验证集上校准最优判定点，不假设精确为0）。

Usage:
  python src/eval/matrix_factorization_baseline.py
  python src/eval/matrix_factorization_baseline.py --json /path/to/out.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import compute_metrics  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
TASK2_DIR = os.path.join(REPO, "data", "task2")
RANK_CROSS_LAB = "/home/zhengz2/projects/yeast-rank-cross-lab"
RAW_MATRIX = f"{RANK_CROSS_LAB}/data/folder8_raw/yp_matrix_z_haphom_20221025.txt"

DE_CSV = os.path.join(TASK2_DIR, "hillenmeyer_phenotype.csv")
DIR_CSV = os.path.join(TASK2_DIR, "hillenmeyer_direction.csv")

RNG_SEED = 42
K = 25          # latent rank (light manual sweep over k in {8,15,25}, reg in {0.3,1,3}
                # on the gene-level calibration split; this combo had the best val
                # macro-F1 on both DE and DIR -- not an exhaustive grid search)
REG = 3.0       # L2 regularization (ridge) on factors/bias
N_ITER = 20     # ALS sweeps
MIN_POOL = 3    # min real "unsampled pool" cells needed for a test-gene fold-in


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------

def load_raw_matrix(context_ids: List[str]) -> pd.DataFrame:
    print(f"Loading raw z-score matrix: {RAW_MATRIX}", file=sys.stderr)
    t0 = time.time()
    mat = pd.read_csv(RAW_MATRIX, sep="\t", index_col=0)
    mat.columns = mat.columns.astype(str)
    mat = mat.reindex(columns=context_ids)
    print(f"  loaded {mat.shape} in {time.time()-t0:.1f}s, "
          f"restricted to {len(context_ids)} Hillenmeyer HOP columns", file=sys.stderr)
    return mat


def load_labels() -> Tuple[pd.DataFrame, pd.DataFrame]:
    de = pd.read_csv(DE_CSV, dtype={"context": str})
    dr = pd.read_csv(DIR_CSV, dtype={"context": str})
    return de, dr


# --------------------------------------------------------------------------
# ALS with bias terms:  score(g,c) = mu + bg[g] + bc[c] + U[g] . V[c]
# --------------------------------------------------------------------------

def als_fit(cells: List[Tuple[int, int, float]], n_genes: int, n_ctx: int,
            k: int = K, reg: float = REG, n_iter: int = N_ITER,
            seed: int = RNG_SEED) -> Dict:
    """cells: list of (gene_idx, ctx_idx, z_value) observed training entries."""
    rng = np.random.RandomState(seed)
    mu = float(np.mean([z for _, _, z in cells]))

    by_gene: Dict[int, List[Tuple[int, float]]] = {}
    by_ctx: Dict[int, List[Tuple[int, float]]] = {}
    for gi, ci, z in cells:
        by_gene.setdefault(gi, []).append((ci, z))
        by_ctx.setdefault(ci, []).append((gi, z))

    U = 0.05 * rng.randn(n_genes, k)
    V = 0.05 * rng.randn(n_ctx, k)
    bg = np.zeros(n_genes)
    bc = np.zeros(n_ctx)

    def solve_side(idx_list, other_factors, other_bias, k, reg):
        """Ridge-solve [bias, factor] jointly for one row given fixed other side."""
        cis = np.array([c for c, _ in idx_list])
        zs = np.array([z for _, z in idx_list])
        X = np.hstack([np.ones((len(cis), 1)), other_factors[cis]])
        y = zs - mu - other_bias[cis]
        A = X.T @ X + reg * np.eye(k + 1)
        b = X.T @ y
        theta = np.linalg.solve(A, b)
        return theta[0], theta[1:]

    for it in range(n_iter):
        for gi, obs in by_gene.items():
            b, u = solve_side(obs, V, bc, k, reg)
            bg[gi], U[gi] = b, u
        for ci, obs in by_ctx.items():
            b, v = solve_side(obs, U, bg, k, reg)
            bc[ci], V[ci] = b, v

    train_pred = np.array([mu + bg[gi] + bc[ci] + U[gi] @ V[ci] for gi, ci, _ in cells])
    train_true = np.array([z for _, _, z in cells])
    rmse = float(np.sqrt(np.mean((train_pred - train_true) ** 2)))
    print(f"  ALS done: k={k} reg={reg} iters={n_iter} train_rmse={rmse:.3f} "
          f"(train z std={train_true.std():.3f})", file=sys.stderr)

    return {"mu": mu, "U": U, "V": V, "bg": bg, "bc": bc, "k": k, "reg": reg}


def score_cell(model: Dict, gene_vec: Optional[np.ndarray], gene_bias: float,
               ci: int) -> float:
    return model["mu"] + gene_bias + model["bc"][ci] + (
        float(gene_vec @ model["V"][ci]) if gene_vec is not None else 0.0)


def fold_in_gene(model: Dict, pool_cells: List[Tuple[int, float]]) -> Tuple[np.ndarray, float]:
    """Ridge fold-in of one new gene's (factor, bias) given fixed context side."""
    k = model["k"]
    cis = np.array([c for c, _ in pool_cells])
    zs = np.array([z for _, z in pool_cells])
    X = np.hstack([np.ones((len(cis), 1)), model["V"][cis]])
    y = zs - model["mu"] - model["bc"][cis]
    A = X.T @ X + model["reg"] * np.eye(k + 1)
    b = X.T @ y
    theta = np.linalg.solve(A, b)
    return theta[1:], theta[0]


# --------------------------------------------------------------------------
# Main pipeline
# --------------------------------------------------------------------------

def build_indices(train_genes: List[str], contexts: List[str]):
    gene_idx = {g: i for i, g in enumerate(train_genes)}
    ctx_idx = {c: i for i, c in enumerate(contexts)}
    return gene_idx, ctx_idx


def run():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", default=None, help="optional path to dump raw metrics JSON")
    ap.add_argument("--k", type=int, default=K)
    ap.add_argument("--reg", type=float, default=REG)
    ap.add_argument("--n-iter", type=int, default=N_ITER)
    ap.add_argument("--no-foldin", action="store_true",
                     help="disable pool-cell fold-in entirely (strict cold-start: every "
                          "test gene falls back to context-bias-only prediction, no "
                          "per-gene side information at all)")
    args = ap.parse_args()

    de, dr = load_labels()
    contexts = sorted(de.context.unique().tolist(), key=int)
    assert set(contexts) == set(dr.context.unique().tolist()), \
        "DE/DIR context sets must match (both are the 273 Hillenmeyer HOP screens)"

    raw = load_raw_matrix(contexts)

    train_genes = sorted(de[de.split == "train"].pert.unique().tolist())
    test_genes_de = sorted(de[de.split == "test"].pert.unique().tolist())
    test_genes_dir = sorted(dr[dr.split == "test"].pert.unique().tolist())
    assert set(train_genes) & set(test_genes_de) == set(), "train/test genes must be disjoint"
    print(f"train genes={len(train_genes)} test genes (DE)={len(test_genes_de)} "
          f"test genes (DIR)={len(test_genes_dir)} contexts={len(contexts)}", file=sys.stderr)

    gene_idx, ctx_idx = build_indices(train_genes, contexts)

    # ---- training cells: exactly the train-split (gene, context) pairs from the
    # DE label CSV (superset of the DIR train rows), value = the *raw z-score*
    # at that cell (continuous, not the thresholded label). ----
    train_df = de[de.split == "train"]
    used_cells = set()  # (pert, context) pairs consumed by EITHER csv/split -> excluded from any fold-in pool
    cells = []
    for pert, ctx in zip(train_df.pert, train_df.context):
        used_cells.add((pert, ctx))
        z = raw.at[pert, ctx] if pert in raw.index else np.nan
        if pert in gene_idx and ctx in ctx_idx and not pd.isna(z):
            cells.append((gene_idx[pert], ctx_idx[ctx], float(z)))
    # also mark all test rows (both tasks) as "used", so fold-in pools never touch them
    for _df in (de, dr):
        for pert, ctx in zip(_df.pert, _df.context):
            used_cells.add((pert, ctx))

    print(f"training cells (train split, finite z): {len(cells)} / {len(train_df)} rows", file=sys.stderr)

    # ---- gene-level held-out calibration ----
    # IMPORTANT: threshold/cut must be calibrated on scores produced the SAME way test
    # scores are produced -- i.e. via fold-in on genes the model never trained on --
    # not on in-sample (directly-fit) gene factors. Folded-in factors are systematically
    # shrunk/noisier than in-sample factors (fewer, indirect observations feeding the
    # ridge solve), so calibrating on in-sample scores and applying the threshold to
    # folded-in test scores silently miscalibrates (verified empirically: it produced a
    # threshold that was too high for folded-in scores, tanking DE macro-F1 below
    # Majority despite a healthy MCC). Fix: hold out 15% of TRAIN GENES entirely, fit
    # ALS without them, fold them in with the exact same pool-cell procedure used for
    # test genes, and calibrate on THAT.
    rng = np.random.RandomState(RNG_SEED)
    genes_shuffled = list(train_genes)
    rng.shuffle(genes_shuffled)
    n_calib_val = int(0.15 * len(genes_shuffled))
    calib_val_genes = set(genes_shuffled[:n_calib_val])
    calib_fit_genes = set(genes_shuffled[n_calib_val:])

    fit_cells = [(gi, ci, z) for gi, ci, z in cells if train_genes[gi] in calib_fit_genes]
    print(f"Fitting ALS on {len(calib_fit_genes)}/{len(train_genes)} train genes "
          f"({len(fit_cells)} cells); {len(calib_val_genes)} genes held out entirely "
          f"for fold-in-calibrated threshold selection...", file=sys.stderr)
    model_cal = als_fit(fit_cells, len(train_genes), len(contexts),
                         k=args.k, reg=args.reg, n_iter=args.n_iter)

    def get_pool_cells_for(model_used_cells, gene: str) -> List[Tuple[int, float]]:
        if gene not in raw.index:
            return []
        row = raw.loc[gene]
        out = []
        for ctx in contexts:
            if (gene, ctx) in model_used_cells:
                continue
            v = row[ctx]
            if not pd.isna(v):
                out.append((ctx_idx[ctx], float(v)))
        return out

    # calib_val genes' own train rows are in `used_cells` (added earlier), so pool
    # cells naturally exclude the exact rows we are about to fold-in-predict.
    val_scores, val_true_z = [], []
    for gi, ci, z in cells:
        gene = train_genes[gi]
        if gene not in calib_val_genes:
            continue
        pool = get_pool_cells_for(used_cells, gene)
        if len(pool) < MIN_POOL:
            s = model_cal["mu"] + model_cal["bc"][ci]
        else:
            u, b = fold_in_gene(model_cal, pool)
            s = score_cell(model_cal, u, b, ci)
        val_scores.append(s)
        val_true_z.append(z)
    val_scores = np.array(val_scores)
    val_de_label = (np.abs(val_true_z) >= 2.0).astype(int)  # same rule as build_growth_labels.py

    best_thr, best_f1 = 0.0, -1.0
    for thr in np.arange(0.0, 3.5, 0.05):
        pred = (np.abs(val_scores) >= thr).astype(int)
        # cheap macro-F1 without full compute_metrics (binary, no abstain)
        tp = int(((pred == 1) & (val_de_label == 1)).sum())
        fp = int(((pred == 1) & (val_de_label == 0)).sum())
        fn = int(((pred == 0) & (val_de_label == 1)).sum())
        tn = int(((pred == 0) & (val_de_label == 0)).sum())
        f1p = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
        f1n = 2 * tn / (2 * tn + fn + fp) if (2 * tn + fn + fp) else 0.0
        macro = (f1p + f1n) / 2
        if macro > best_f1:
            best_f1, best_thr = macro, thr
    print(f"DE threshold calibrated on val: |score|>={best_thr:.2f} (val macro-F1={best_f1:.4f}, "
          f"n_val={len(val_scores)})", file=sys.stderr)

    # calibrate DIR sign-cut on val cells restricted to |z|>=2 (i.e. the DIR-relevant subset)
    pos_mask = np.abs(val_true_z) >= 2.0
    dir_scores = val_scores[pos_mask]
    dir_true = (np.array(val_true_z)[pos_mask] > 0).astype(int)  # 1=resistant
    best_cut, best_dir_f1 = 0.0, -1.0
    for cut in np.arange(-1.5, 1.5, 0.05):
        pred = (dir_scores > cut).astype(int)
        tp = int(((pred == 1) & (dir_true == 1)).sum())
        fp = int(((pred == 1) & (dir_true == 0)).sum())
        fn = int(((pred == 0) & (dir_true == 1)).sum())
        tn = int(((pred == 0) & (dir_true == 0)).sum())
        f1p = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
        f1n = 2 * tn / (2 * tn + fn + fp) if (2 * tn + fn + fp) else 0.0
        macro = (f1p + f1n) / 2
        if macro > best_dir_f1:
            best_dir_f1, best_cut = macro, cut
    print(f"DIR sign-cut calibrated on val: score>{best_cut:.2f}->Resistant "
          f"(val macro-F1={best_dir_f1:.4f}, n_val_pos={int(pos_mask.sum())})", file=sys.stderr)

    # ---- refit final model on ALL train cells (still zero test leakage) ----
    print("Refitting ALS on 100% of train cells for final test predictions...", file=sys.stderr)
    model = als_fit(cells, len(train_genes), len(contexts), k=args.k, reg=args.reg,
                     n_iter=args.n_iter)

    # ---- fold-in test genes (reuses get_pool_cells_for defined above) ----
    fold_in_cache: Dict[str, Tuple[Optional[np.ndarray], float, int]] = {}

    def gene_factor(gene: str):
        if gene in fold_in_cache:
            return fold_in_cache[gene]
        pool = [] if args.no_foldin else get_pool_cells_for(used_cells, gene)
        if len(pool) >= MIN_POOL:
            u, b = fold_in_gene(model, pool)
            fold_in_cache[gene] = (u, b, len(pool))
        else:
            fold_in_cache[gene] = (None, 0.0, len(pool))
        return fold_in_cache[gene]

    # ---- predict + score T2A-DE ----
    de_test = de[de.split == "test"]
    de_preds, de_truth = [], []
    n_foldin_de, n_fallback_de = 0, 0
    for pert, ctx, label in zip(de_test.pert, de_test.context, de_test.label):
        u, b, npool = gene_factor(pert)
        if u is not None:
            n_foldin_de += 1
        else:
            n_fallback_de += 1
        s = score_cell(model, u, b, ctx_idx[ctx])
        de_preds.append(1 if abs(s) >= best_thr else 0)
        de_truth.append(int(label))
    de_metrics = compute_metrics(de_preds, de_truth, "growth")
    print(f"\nT2A-DE test: n={len(de_truth)}  fold-in genes used for {n_foldin_de} rows, "
          f"fallback (context-bias-only) for {n_fallback_de} rows "
          f"({100*n_fallback_de/len(de_truth):.2f}%)", file=sys.stderr)
    print(json.dumps(de_metrics, indent=2))

    # ---- predict + score T2A-DIR ----
    dr_test = dr[dr.split == "test"]
    dir_preds, dir_truth = [], []
    n_foldin_dir, n_fallback_dir = 0, 0
    for pert, ctx, label in zip(dr_test.pert, dr_test.context, dr_test.label):
        u, b, npool = gene_factor(pert)
        if u is not None:
            n_foldin_dir += 1
        else:
            n_fallback_dir += 1
        s = score_cell(model, u, b, ctx_idx[ctx])
        dir_preds.append(1 if s > best_cut else 0)
        dir_truth.append(int(label))
    dir_metrics = compute_metrics(dir_preds, dir_truth, "growth_dir")
    print(f"\nT2A-DIR test: n={len(dir_truth)}  fold-in genes used for {n_foldin_dir} rows, "
          f"fallback (context-bias-only) for {n_fallback_dir} rows "
          f"({100*n_fallback_dir/len(dir_truth):.2f}%)", file=sys.stderr)
    print(json.dumps(dir_metrics, indent=2))

    out = {
        "config": {"k": args.k, "reg": args.reg, "n_iter": args.n_iter,
                    "de_threshold": best_thr, "dir_cut": best_cut,
                    "min_pool_for_foldin": MIN_POOL},
        "T2A-DE": {**de_metrics,
                    "n_foldin_rows": n_foldin_de, "n_fallback_rows": n_fallback_de,
                    "fallback_pct": round(100 * n_fallback_de / len(de_truth), 2)},
        "T2A-DIR": {**dir_metrics,
                     "n_foldin_rows": n_foldin_dir, "n_fallback_rows": n_fallback_dir,
                     "fallback_pct": round(100 * n_fallback_dir / len(dir_truth), 2)},
    }
    if args.json:
        with open(args.json, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\nWrote {args.json}", file=sys.stderr)
    return out


if __name__ == "__main__":
    run()
