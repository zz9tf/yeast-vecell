#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build retrieval results JSON for (perturbagen, gene) pairs.

Ported from VCWorld's ``retrieve`` stage. Two yeast adaptations:

  1. TRUE-LABEL FIX (the important one). Upstream ``retrieved_pairs`` are
     ``[drug, gene]`` with NO label, so the downstream prompt stage fills each
     in-context "Result:" line with a *random* choice -- the few-shot examples
     carry no information. Here every retrieved analogue pair carries the real
     train label it was mined from:  ``retrieved_pairs = [[pert, gene, label], ...]``.
     A ``--shuffle-labels`` switch preserves the random-label behaviour as an
     ablation.

  2. Similarity JSONs are optional / may not exist yet. ``load_similarity_json``
     returns an empty dict for a missing file (retrieval then falls back to the
     perturbagen's own seen genes / the gene's own seen perturbagens from train).

Perturbagen-similarity JSON schema:  {name: [name, ...]}
Gene-similarity (KG) JSON schema:     {ORF: {"direct_neighbors": [...],
                                             "two_hop_neighbors": [...]}}
"""

import json
import random
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def load_data(csv_file: str, readout_col: str = "gene") -> Dict[str, List[dict]]:
    """Load (pert, readout, label, split). ``readout_col`` is the readout column
    name (Task1 = 'gene'; Task2 = 'context'); stored internally under 'gene'."""
    df = pd.read_csv(csv_file)
    # vectorized (Task2 CSVs are millions of rows; iterrows is far too slow).
    perts = df["pert"].astype(str).tolist()
    genes = df[readout_col].astype(str).tolist()
    labels = df["label"].astype(int).tolist()
    splits = df["split"].astype(str).tolist()
    data: Dict[str, List[dict]] = {"train": [], "test": []}
    for p, g, lab, s in zip(perts, genes, labels, splits):
        data.setdefault(s, []).append({"pert": p, "gene": g, "label": lab, "split": s})
    return data


def load_similarity_json(path: Optional[str]) -> Dict[str, List[str]]:
    """Tolerant loader (same shapes VCWorld accepts) + missing-file defence.

    Accepts:
      - {key: ["x", ...]}
      - {key: [{"Drug"/"Gene": "..."}, ...]}
      - KG dicts {key: {"direct_neighbors": [...], "two_hop_neighbors": [...]}}
    A missing / empty path yields {} so callers can degrade gracefully.
    """
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[retrieve] WARNING: similarity JSON unavailable ({path}): {exc}. "
              f"Continuing with empty similarity map.")
        return {}

    out: Dict[str, List[str]] = {}
    for key, vals in raw.items():
        if not vals:
            out[key] = []
            continue
        if isinstance(vals, dict):
            # KG dict: prefer direct neighbors, then two-hop, then anything list-y.
            merged: List[str] = []
            for field in ("direct_neighbors", "neighbors", "close_genes",
                          "similar_genes", "top_genes", "two_hop_neighbors"):
                candidates = vals.get(field)
                if isinstance(candidates, list):
                    merged.extend(str(v) for v in candidates)
            if merged:
                # de-duplicate, keep order (direct before two-hop)
                seen = set()
                out[key] = [x for x in merged if not (x in seen or seen.add(x))]
            else:
                out[key] = [str(v) for v in vals.values()]
            continue
        if isinstance(vals, list):
            if isinstance(vals[0], dict):
                if "Drug" in vals[0]:
                    out[key] = [v.get("Drug") for v in vals if v.get("Drug")]
                elif "Gene" in vals[0]:
                    out[key] = [v.get("Gene") for v in vals if v.get("Gene")]
                else:
                    out[key] = [str(v) for v in vals]
            else:
                out[key] = [str(v) for v in vals]
            continue
        out[key] = [str(vals)]
    return out


def build_seen_structures(
    train_data: List[dict],
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], Dict[Tuple[str, str], int]]:
    """From train only: pert->[genes], gene->[perts], and (pert,gene)->label."""
    seen: Dict[str, List[str]] = {}
    seen_gene: Dict[str, List[str]] = {}
    label_map: Dict[Tuple[str, str], int] = {}
    for item in train_data:
        pert = item["pert"]
        gene = item["gene"]
        seen.setdefault(pert, [])
        if gene not in seen[pert]:
            seen[pert].append(gene)
        seen_gene.setdefault(gene, [])
        if pert not in seen_gene[gene]:
            seen_gene[gene].append(pert)
        # keep the first label seen for a (pert, gene) train pair
        label_map.setdefault((pert, gene), item["label"])
    return seen, seen_gene, label_map


def get_pert_gene_pairs(*, pert: str, gene: str, close_perts: List[str],
                        close_genes: List[str], seen: Dict[str, List[str]],
                        seen_gene: Dict[str, List[str]], budget: int,
                        seed: int = 0) -> List[List[str]]:
    """Assemble analogue (pert, gene) evidence pairs from train, budget-capped.

    Priority tiers mirror VCWorld's heuristic (renamed drug -> pert):
      * same-pert pairs where the readout gene is a network neighbor,
      * same-gene pairs where the perturbagen is similar,
      * "both-similar" pairs (similar pert x neighbor gene),
      * backfill from the query's own seen genes/perts, then similar-pert genes.
    Returns 2-element ``[pert, gene]`` pairs; labels are attached by the caller.
    """
    np.random.seed(seed)
    pert_pairs: List[List[str]] = []
    gene_pairs: List[List[str]] = []

    if pert in seen:
        for gene2 in close_genes:
            if gene2 in seen[pert]:
                pert_pairs.append([pert, gene2])
    elif gene in seen_gene:
        for pert2 in close_perts:
            if pert2 in seen_gene[gene]:
                gene_pairs.append([pert2, gene])

    if len(pert_pairs) > budget:
        pert_pairs = [pert_pairs[i] for i in np.random.choice(len(pert_pairs), budget, replace=False)]
    if len(gene_pairs) > budget:
        gene_pairs = [gene_pairs[i] for i in np.random.choice(len(gene_pairs), budget, replace=False)]

    both_pairs: List[List[str]] = []
    for pert2 in close_perts:
        for gene2 in close_genes:
            if pert2 in seen and gene2 in seen[pert2]:
                both_pairs.append([pert2, gene2])
    if len(both_pairs) > budget:
        both_pairs = [both_pairs[i] for i in np.random.choice(len(both_pairs), budget, replace=False)]

    cur_pert_pairs: List[List[str]] = []
    cur_gene_pairs: List[List[str]] = []
    pert_budget = budget - len(pert_pairs)
    gene_budget = budget - len(gene_pairs)

    if pert in seen and pert_budget > 0:
        for gene2 in seen[pert]:
            cur_pert_pairs.append([pert, gene2])
        if len(cur_pert_pairs) > pert_budget:
            cur_pert_pairs = [cur_pert_pairs[i] for i in np.random.choice(len(cur_pert_pairs), pert_budget, replace=False)]
    elif gene in seen_gene and gene_budget > 0:
        for pert2 in seen_gene[gene]:
            cur_gene_pairs.append([pert2, gene])
        if len(cur_gene_pairs) > gene_budget:
            cur_gene_pairs = [cur_gene_pairs[i] for i in np.random.choice(len(cur_gene_pairs), gene_budget, replace=False)]

    pert_pairs.extend(cur_pert_pairs)
    gene_pairs.extend(cur_gene_pairs)

    cur_pert_pairs = []
    cur_gene_pairs = []
    pert_budget = budget - len(pert_pairs)
    gene_budget = budget - len(gene_pairs)

    if pert_budget > 0:
        for pert2 in close_perts:
            if pert2 not in seen:
                continue
            for gene2 in seen[pert2]:
                cur_pert_pairs.append([pert2, gene2])
        if len(cur_pert_pairs) > pert_budget:
            cur_pert_pairs = [cur_pert_pairs[i] for i in np.random.choice(len(cur_pert_pairs), pert_budget, replace=False)]
    elif gene_budget > 0:
        for gene2 in close_genes:
            if gene2 not in seen_gene:
                continue
            for pert2 in seen_gene[gene2]:
                cur_gene_pairs.append([pert2, gene2])
        if len(cur_gene_pairs) > gene_budget:
            cur_gene_pairs = [cur_gene_pairs[i] for i in np.random.choice(len(cur_gene_pairs), gene_budget, replace=False)]

    pert_pairs.extend(cur_pert_pairs)
    gene_pairs.extend(cur_gene_pairs)

    return pert_pairs + gene_pairs + both_pairs


def _attach_labels(pairs: List[List[str]], label_map: Dict[Tuple[str, str], int],
                   *, shuffle_labels: bool, rng: random.Random) -> List[List]:
    """Attach the TRUE train label to each [pert, gene] pair.

    Every retrieved pair is mined from the train ``seen`` structures, so its
    label is in ``label_map``. Deduplicate while preserving order. With
    ``shuffle_labels`` the label is randomized (ablation of the true-label fix).
    """
    out: List[List] = []
    used = set()
    for pert2, gene2 in pairs:
        key = (pert2, gene2)
        if key in used:
            continue
        used.add(key)
        label = int(label_map.get(key, 0))
        if shuffle_labels:
            label = rng.randint(0, 1)
        out.append([pert2, gene2, label])
    return out


def build_retrieval_results(*, data_csv: str, out_json: str,
                            pert_sim_json: Optional[str] = None,
                            gene_sim_json: Optional[str] = None,
                            budget: int = 10, seed: int = 0,
                            max_cases: Optional[int] = None,
                            case_split: str = "test",
                            shuffle_labels: bool = False,
                            readout_col: str = "gene") -> None:
    data = load_data(data_csv, readout_col=readout_col)
    train_data = data.get("train", [])
    eval_data = data.get(case_split, [])

    pert_similarity = load_similarity_json(pert_sim_json)
    gene_similarity = load_similarity_json(gene_sim_json)
    if not pert_similarity:
        print("[retrieve] NOTE: no perturbagen-similarity map; using train "
              "co-occurrence fallbacks only.")
    if not gene_similarity:
        print("[retrieve] NOTE: no gene-similarity map; using train "
              "co-occurrence fallbacks only.")

    seen, seen_gene, label_map = build_seen_structures(train_data)
    label_rng = random.Random(seed)

    unique_cases = []
    seen_pairs = set()
    for item in eval_data:
        key = (item["pert"], item["gene"])
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        unique_cases.append(item)

    if max_cases and max_cases < len(unique_cases):
        random.seed(seed)
        unique_cases = random.sample(unique_cases, max_cases)

    results = []
    for item in unique_cases:
        pert = item["pert"]
        gene = item["gene"]
        close_perts = pert_similarity.get(pert, [])[:budget]
        close_genes = gene_similarity.get(gene, [])[:budget]
        raw_pairs = get_pert_gene_pairs(
            pert=pert, gene=gene, close_perts=close_perts, close_genes=close_genes,
            seen=seen, seen_gene=seen_gene, budget=budget, seed=seed,
        )
        retrieved = _attach_labels(raw_pairs, label_map,
                                   shuffle_labels=shuffle_labels, rng=label_rng)
        results.append({
            "test_case": {"pert": pert, "gene": gene},
            "retrieved_pairs": retrieved,  # [[pert, gene, label], ...]
        })

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    n_with_ev = sum(1 for r in results if r["retrieved_pairs"])
    print(f"Saved retrieval results: {out_json} "
          f"(cases={len(results)}, with-evidence={n_with_ev}, "
          f"shuffle_labels={shuffle_labels})")
