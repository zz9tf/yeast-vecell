#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a single-case prompt for an out-of-dataset (pert, gene) query.

Yeast port of VCWorld's single-case path. Differences from the human original:
  - drug -> perturbagen (deleted gene) naming; cell-line -> ``contexts``.
  - the human ``gene_aliases`` map is removed (yeast alias normalization is a
    separate step; see prepare.py identifier note).
  - all JSONs are optional (missing -> {}), matching the rest of the pipeline.
Like VCWorld's single path (and unlike the buggy bulk path it replaces), the
retrieved examples already carry the TRUE train label.
"""

from __future__ import annotations

import difflib
import json
import os
import random
import sys
from typing import Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from ..prompt import (
    load_template_vars,
    get_description,
    _default_template_path,
    _label_to_result,
)


def _load_json(path: Optional[str]) -> Dict[str, str]:
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[single-case] WARNING: JSON unavailable ({path}): {exc}", file=sys.stderr)
        return {}


def _load_similarity_json(path: Optional[str]) -> Dict[str, List[str]]:
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[single-case] WARNING: similarity JSON unavailable ({path}): {exc}",
              file=sys.stderr)
        return {}
    out: Dict[str, List[str]] = {}
    for key, vals in raw.items():
        if not vals:
            out[key] = []
            continue
        if isinstance(vals, dict):
            merged: List[str] = []
            for field in ("direct_neighbors", "neighbors", "close_genes",
                          "similar_genes", "top_genes", "two_hop_neighbors"):
                candidates = vals.get(field)
                if isinstance(candidates, list):
                    merged.extend(str(v) for v in candidates)
            out[key] = merged if merged else [str(v) for v in vals.values()]
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


def _load_csv_pairs(path: str) -> List[Tuple[str, str, int, str]]:
    pairs: List[Tuple[str, str, int, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        idx_pert = header.index("pert")
        idx_gene = header.index("gene")
        idx_label = header.index("label")
        idx_split = header.index("split")
        for line in f:
            if not line.strip():
                continue
            cols = line.rstrip("\n").split(",")
            if len(cols) <= max(idx_pert, idx_gene, idx_label, idx_split):
                continue
            pairs.append((cols[idx_pert], cols[idx_gene], int(cols[idx_label]), cols[idx_split]))
    return pairs


def _casefold_map(keys: List[str]) -> Dict[str, str]:
    return {k.strip().lower(): k for k in keys}


def _normalize_key(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _normalize_map(keys: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key in keys:
        norm = _normalize_key(key)
        if norm and norm not in out:
            out[norm] = key
    return out


def _name_similarity(a: str, b: str) -> float:
    na, nb = _normalize_key(a), _normalize_key(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _token_overlap(query_desc: str, cand_desc: str) -> float:
    q = set(query_desc.lower().split())
    c = set(cand_desc.lower().split())
    if not q or not c:
        return 0.0
    return len(q & c) / len(q | c)


def _resolve_via_json(name: str, sim: Dict[str, List[str]], max_candidates: int) -> Optional[List[str]]:
    """Case-insensitive / alphanumeric-normalized lookup in a similarity map."""
    if not sim:
        return None
    key = _casefold_map(list(sim.keys())).get(name.strip().lower())
    if not key:
        key = _normalize_map(list(sim.keys())).get(_normalize_key(name))
    if not key:
        return None
    sims = [s for s in sim.get(key, []) if s][:max_candidates]
    if name not in sims:
        sims.insert(0, name)
    return sims[:max_candidates]


def _pick_similar_by_heuristic(name: str, desc_map: Dict[str, str], top_k: int) -> List[str]:
    query_desc = desc_map.get(name, "")
    scored = []
    for cand, desc in desc_map.items():
        score = 0.7 * _name_similarity(name, cand) + \
                0.3 * (_token_overlap(query_desc, desc) if query_desc else 0.0)
        scored.append((cand, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    picks = [cand for cand, _ in scored[:top_k]]
    if name not in picks:
        picks.insert(0, name)
    return picks[:top_k]


# ---- optional LLM-ranked fallback (OpenAI-compatible endpoint) --------------
def _resolve_api_key(cli_key: Optional[str]) -> str:
    if cli_key:
        return cli_key
    return os.getenv("LLM_DRUG_API_KEY") or os.getenv("API_KEY") or ""


def _post_json(url: str, payload: dict, api_key: str, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        detail = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        raise RuntimeError(f"API HTTPError: {e.code} {detail}") from e
    except URLError as e:
        raise RuntimeError(f"API URLError: {e.reason}") from e


def _llm_rank(*, query_name: str, query_desc: str, candidates: List[Tuple[str, str]],
              top_k: int, api_url: str, api_model: str, api_key: str, timeout: int,
              kind: str) -> List[str]:
    if not candidates:
        return []
    cand_lines = []
    for name, desc in candidates:
        d = desc.replace("\n", " ").strip()
        if len(d) > 240:
            d = d[:240] + "..."
        cand_lines.append(f"- {name}: {d}")
    goal = ("shared pathway / complex and genetic-interaction profile"
            if kind == "pert" else "co-function and pathway relevance")
    system_prompt = ("You are a yeast (S. cerevisiae) molecular biologist. Return only a "
                     "JSON array of names, no explanations.")
    user_prompt = (f"Query: {query_name}\nDescription: {query_desc}\n\n"
                   f"Select the {top_k} most similar candidates by {goal}. "
                   "Return a JSON array of candidate names, most similar first.\n\n"
                   "Candidates:\n" + "\n".join(cand_lines))
    payload = {"model": api_model,
               "messages": [{"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}],
               "temperature": 0.0, "top_p": 1.0, "max_tokens": 512}
    try:
        resp = _post_json(api_url, payload, api_key, timeout)
        content = resp["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return [str(x) for x in parsed][:top_k]
    except Exception as exc:  # noqa: BLE001 - fallback is best-effort
        print(f"[single-case] LLM fallback failed: {exc}", file=sys.stderr)
    return []


def _find_similar(name: str, desc_map: Dict[str, str], sim: Dict[str, List[str]],
                  max_candidates: int, kind: str, *, llm_api_url, llm_api_model,
                  llm_api_key, llm_candidate_pool, llm_timeout) -> List[str]:
    via_json = _resolve_via_json(name, sim, max_candidates)
    if via_json is not None:
        return via_json
    if llm_api_url and llm_api_model and desc_map:
        query_desc = desc_map.get(name, name)
        scored = sorted(((c, _token_overlap(query_desc, d)) for c, d in desc_map.items()),
                        key=lambda x: x[1], reverse=True)[:llm_candidate_pool]
        cands = [(c, desc_map.get(c, "")) for c, _ in scored]
        print(f"[single-case] LLM fallback for {kind} '{name}' (pool={len(cands)})",
              file=sys.stderr)
        ranked = _llm_rank(query_name=name, query_desc=query_desc, candidates=cands,
                           top_k=max_candidates, api_url=llm_api_url, api_model=llm_api_model,
                           api_key=_resolve_api_key(llm_api_key), timeout=llm_timeout, kind=kind)
        if ranked:
            if name not in ranked:
                ranked.insert(0, name)
            return ranked[:max_candidates]
    if desc_map:
        return _pick_similar_by_heuristic(name, desc_map, max_candidates)
    return [name]


def _collect_retrieved_pairs(data_csv: str, close_perts: List[str], close_genes: List[str],
                             budget: int, case_split: str, seed: int) -> List[Tuple[str, str, int]]:
    rows = _load_csv_pairs(data_csv)
    close_pert_set = {d.strip().lower() for d in close_perts}
    close_gene_set = {g.strip().lower() for g in close_genes}
    pairs: List[Tuple[str, str, int]] = []
    for pert, gene, label, split in rows:
        if case_split and split != case_split:
            continue
        if pert.strip().lower() in close_pert_set or gene.strip().lower() in close_gene_set:
            pairs.append((pert, gene, label))
    if len(pairs) > budget:
        pairs = random.Random(seed).sample(pairs, budget)
    return pairs


def generate_single_case_prompt(*, task: str, pert: str, gene: str, context: str,
                                data_csv: str, output_file: str,
                                gene_desc_json: Optional[str] = None,
                                pert_desc_json: Optional[str] = None,
                                pert_sim_json: Optional[str] = None,
                                gene_sim_json: Optional[str] = None,
                                template_file: Optional[str] = None,
                                max_candidates: int = 10, budget: int = 10,
                                case_split: str = "", seed: int = 42,
                                llm_api_url: Optional[str] = None,
                                llm_api_model: Optional[str] = None,
                                llm_api_key: Optional[str] = None,
                                llm_candidate_pool: int = 80,
                                llm_timeout: int = 60) -> None:
    random.seed(seed)

    gene_desc = _load_json(gene_desc_json)
    pert_desc = _load_json(pert_desc_json) if pert_desc_json else gene_desc
    pert_sim = _load_similarity_json(pert_sim_json)
    gene_sim = _load_similarity_json(gene_sim_json)

    close_perts = _find_similar(pert, pert_desc, pert_sim, max_candidates, "pert",
                                llm_api_url=llm_api_url, llm_api_model=llm_api_model,
                                llm_api_key=llm_api_key, llm_candidate_pool=llm_candidate_pool,
                                llm_timeout=llm_timeout)
    close_genes = _find_similar(gene, gene_desc, gene_sim, max_candidates, "gene",
                                llm_api_url=llm_api_url, llm_api_model=llm_api_model,
                                llm_api_key=llm_api_key, llm_candidate_pool=llm_candidate_pool,
                                llm_timeout=llm_timeout)

    retrieved_pairs = _collect_retrieved_pairs(data_csv, close_perts, close_genes,
                                               budget, case_split, seed)

    if template_file is None:
        template_file = _default_template_path(task)
    tmpl_vars = load_template_vars(template_file)

    contexts: List[Tuple[str, str]] = tmpl_vars.get("contexts") or tmpl_vars.get("cell_lines", [])
    if not contexts:
        raise RuntimeError("`contexts` not found in template file")
    context_short, context_desc = contexts[0]
    for name, desc in contexts:
        if name.strip().lower() == context.strip().lower():
            context_short, context_desc = name, desc
            break

    choices = tmpl_vars.get("choices_de", []) if task == "de" else tmpl_vars.get("choices_dir", [])
    prompt_template = ((tmpl_vars.get("prompt_yeast_DE", "") or tmpl_vars.get("prompt_vcworld_DE", ""))
                       if task == "de"
                       else (tmpl_vars.get("prompt_yeast_DIR", "") or tmpl_vars.get("prompt_vcworld_DIR", "")))
    if not prompt_template:
        raise RuntimeError(f"prompt template for {task} not found in template file")

    if not retrieved_pairs:
        obs = "No similar experimental observations available for context."
    else:
        blocks = []
        for i, (p2, g2, label) in enumerate(retrieved_pairs[:budget]):
            block = (f"Example {i + 1}:\n"
                     f"- Perturbagen (deletion): {p2}\n"
                     f"- Readout gene (ORF): {g2}\n"
                     f"- Perturbagen Description: {get_description(p2, pert_desc, 'Perturbagen')}\n"
                     f"- Readout Gene Description: {get_description(g2, gene_desc, 'Gene')}")
            result = _label_to_result(label, choices)
            if result:
                block += f"\n- Result: {result}"
            blocks.append(block)
        obs = "\n\n".join(blocks)

    filled = prompt_template.format(
        pert=pert, gene=gene,
        pert_desc=get_description(pert, pert_desc, "Perturbagen"),
        gene_desc=get_description(gene, gene_desc, "Gene"),
        context_short=context_short, context_desc=context_desc, obs=obs,
    )

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"=== Prompt 1 ({pert} | {gene}) ===\n")
        f.write(filled)
        f.write("\n\n" + "=" * 80 + "\n\n")

    print(f"Saved single-case prompt: {output_file}")
    if not retrieved_pairs:
        print("Warning: no retrieved pairs found; prompt will have empty context.")
