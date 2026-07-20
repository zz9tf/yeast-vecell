#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI entry for the yeast DE/DIR pipeline.

Mirrors VCWorld's stage layout, adapted for yeast genetic-perturbation data
(Deleteome). Subcommands:

    de|dir  prepare | retrieve | prompt | infer | infer-api
    single  prompt

Run from ``src/cli_pipeline``:  ``python cli.py de prepare ...``
"""

import argparse
import os
import sys

from stages.prepare import process_deleteome
from stages.retrieve import build_retrieval_results
from stages.prompt import generate_prompts
from stages.infer import run_inference
from stages.infer_api import run_inference_api
from stages.single_case.prompt import generate_single_case_prompt

# Repo root = two levels up from this file (src/cli_pipeline/cli.py).
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_DELETEOME = os.path.join(
    REPO_ROOT, "data", "perturbation",
    "deleteome_all_mutants_ex_wt_var_controls.txt")
DEFAULT_PERT_SIM = os.path.join(REPO_ROOT, "data", "knowledge", "perturbagen_similarity.json")
DEFAULT_GENE_SIM = os.path.join(REPO_ROOT, "data", "knowledge", "results_close_gene.json")
DEFAULT_GENE_DESC = os.path.join(REPO_ROOT, "data", "knowledge", "gene_desc.json")
DEFAULT_ALIAS = os.path.join(REPO_ROOT, "data", "knowledge", "gene_alias.json")


def _add_prepare_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--input", default=DEFAULT_DELETEOME,
                   help="Deleteome matrix (tab-delimited). Default: the bundled "
                        "deleteome_all_mutants_ex_wt_var_controls.txt")
    p.add_argument("--out-dir", required=True, help="Output directory for CSVs")
    p.add_argument("--name", required=True, help="Output file prefix -> {name}_DE.csv / {name}_DIR.csv")
    p.add_argument("--lfc", type=float, default=0.766,
                   help="|M| (log2 FC) threshold for DE (Deleteome native FC>1.7 => 0.766)")
    p.add_argument("--fdr", type=float, default=0.05,
                   help="p-value threshold for DE (applied to Deleteome raw p_value)")
    p.add_argument("--pval-neg", type=float, default=0.1,
                   help="Genes with p above this are eligible as DE negatives")
    p.add_argument("--n-neg", type=int, default=200, help="Negatives sampled per perturbagen")
    p.add_argument("--train-fraction", type=float, default=0.3, help="Train split fraction (by perturbagen)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-perts", type=int, default=None,
                   help="Optional cap on #perturbagens (subset for speed/smoke tests)")
    p.add_argument("--alias", default=DEFAULT_ALIAS,
                   help="Gene alias JSON to normalize perturbagens (standard name) -> "
                        "systematic ORF so they match the ORF-keyed knowledge assets. "
                        "Pass '' to disable normalization.")


def _add_retrieve_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--data-csv", required=True, help="Input CSV with pert/gene/label/split")
    p.add_argument("--pert-sim", default=DEFAULT_PERT_SIM,
                   help="Perturbagen similarity JSON {name:[name,...]} (optional; may be missing)")
    p.add_argument("--gene-sim", default=DEFAULT_GENE_SIM,
                   help="Gene similarity KG JSON {ORF:{direct_neighbors,two_hop_neighbors}} "
                        "(optional; may be missing)")
    p.add_argument("--out", required=True, help="Output retrieval JSON")
    p.add_argument("--budget", type=int, default=10)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--max-cases", type=int, default=None)
    p.add_argument("--case-split", default="test", choices=["train", "test"],
                   help="Which split to generate retrieval for")
    p.add_argument("--shuffle-labels", action="store_true",
                   help="Ablation: randomize example labels (reproduces VCWorld's random-label bug)")
    p.add_argument("--readout-col", default="gene",
                   help="Readout column in --data-csv (Task1='gene', Task2 growth='context')")


def _add_prompt_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--retrieval", required=True, help="Retrieval JSON from the retrieve stage")
    p.add_argument("--gene-desc", default=DEFAULT_GENE_DESC,
                   help="Gene/ORF description JSON (optional; also used for perturbagens by default)")
    p.add_argument("--pert-desc", default=None,
                   help="Perturbagen description JSON (defaults to --gene-desc)")
    p.add_argument("--template", default=None, help="Prompt template file (optional)")
    p.add_argument("--alias", default=DEFAULT_ALIAS,
                   help="Gene alias JSON, used to show perturbagens as 'STANDARD (ORF)' "
                        "for readability. Pass '' to disable.")
    p.add_argument("--out", required=True, help="Output prompts text file")
    p.add_argument("--context-idx", type=int, default=None,
                   help="Index into the template `contexts` list (default: random per case)")
    p.add_argument("--max-cases", type=int, default=None)
    p.add_argument("--seed", type=int, default=42)


def _add_infer_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--model", required=True, help="HF model path or name")
    p.add_argument("--prompts", required=True, help="Prompt text file")
    p.add_argument("--out", required=True, help="Output text file")
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--max-new-tokens", type=int, default=512)
    p.add_argument("--temperature", type=float, default=0.6)
    p.add_argument("--top-p", type=float, default=0.9)
    p.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float16", "float32"])
    p.add_argument("--device-map", default="auto")
    p.add_argument("--chat-template", default=None,
                   help="Optional chat template file to override tokenizer.chat_template")


def _add_infer_api_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--api-url", required=True, help="API endpoint URL")
    p.add_argument("--api-model", required=True, help="API model name")
    p.add_argument("--api-key", default=None, help="API key (or set LLM_DRUG_API_KEY)")
    p.add_argument("--prompts", required=True, help="Prompt text file")
    p.add_argument("--out", required=True, help="Output text file")
    p.add_argument("--max-new-tokens", type=int, default=512)
    p.add_argument("--temperature", type=float, default=0.6)
    p.add_argument("--top-p", type=float, default=0.9)
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--sleep-secs", type=float, default=0.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yeast-VCWorld DE/DIR pipeline CLI")
    task_sub = parser.add_subparsers(dest="task", required=True)

    for task_name in ("de", "dir"):
        task_parser = task_sub.add_parser(task_name)
        stage_sub = task_parser.add_subparsers(dest="stage", required=True)
        _add_prepare_args(stage_sub.add_parser("prepare"))
        _add_retrieve_args(stage_sub.add_parser("retrieve"))
        _add_prompt_args(stage_sub.add_parser("prompt"))
        _add_infer_args(stage_sub.add_parser("infer"))
        _add_infer_api_args(stage_sub.add_parser("infer-api"))

    single_p = task_sub.add_parser("single")
    single_stage = single_p.add_subparsers(dest="stage", required=True)
    sp = single_stage.add_parser("prompt")
    sp.add_argument("--pert", required=True, help="Perturbagen (deleted gene, standard name)")
    sp.add_argument("--gene", required=True, help="Readout ORF (systematic name)")
    sp.add_argument("--context", required=True, help="Context short-name (must exist in template `contexts`)")
    sp.add_argument("--mode", default="de", choices=["de", "dir"])
    sp.add_argument("--data-csv", required=True, help="CSV with pert/gene/label/split for retrieval")
    sp.add_argument("--gene-desc", default=DEFAULT_GENE_DESC)
    sp.add_argument("--pert-desc", default=None)
    sp.add_argument("--pert-sim", default=DEFAULT_PERT_SIM)
    sp.add_argument("--gene-sim", default=DEFAULT_GENE_SIM)
    sp.add_argument("--template", default=None)
    sp.add_argument("--out", required=True)
    sp.add_argument("--max-candidates", type=int, default=10)
    sp.add_argument("--budget", type=int, default=10)
    sp.add_argument("--case-split", default="train", choices=["train", "test", "all"])
    sp.add_argument("--seed", type=int, default=42)
    sp.add_argument("--llm-api-url", default=None, help="Optional LLM endpoint for similarity fallback")
    sp.add_argument("--llm-api-model", default=None)
    sp.add_argument("--llm-api-key", default=None)
    sp.add_argument("--llm-candidate-pool", type=int, default=80)
    sp.add_argument("--llm-timeout", type=int, default=60)
    return parser


def main(argv: list) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.task in ("de", "dir") and args.stage == "prepare":
        process_deleteome(
            input_path=args.input, output_dir=args.out_dir, name=args.name,
            lfc=args.lfc, fdr=args.fdr, pval_neg=args.pval_neg, n_neg=args.n_neg,
            train_fraction=args.train_fraction, seed=args.seed, max_perts=args.max_perts,
            alias_path=(args.alias or None),
        )
        return 0

    if args.task in ("de", "dir") and args.stage == "retrieve":
        build_retrieval_results(
            data_csv=args.data_csv, out_json=args.out,
            pert_sim_json=args.pert_sim, gene_sim_json=args.gene_sim,
            budget=args.budget, seed=args.seed, max_cases=args.max_cases,
            case_split=args.case_split, shuffle_labels=args.shuffle_labels,
            readout_col=args.readout_col,
        )
        return 0

    if args.task in ("de", "dir") and args.stage == "prompt":
        generate_prompts(
            task=args.task, retrieval_json=args.retrieval,
            gene_desc_json=args.gene_desc, pert_desc_json=args.pert_desc,
            template_file=args.template, output_file=args.out,
            context_idx=args.context_idx, max_cases=args.max_cases, seed=args.seed,
            alias_path=(args.alias or None),
        )
        return 0

    if args.task in ("de", "dir") and args.stage == "infer":
        run_inference(
            model_name=args.model, prompts_file=args.prompts, output_file=args.out,
            batch_size=args.batch_size, max_new_tokens=args.max_new_tokens,
            temperature=args.temperature, top_p=args.top_p, dtype=args.dtype,
            device_map=args.device_map, chat_template_path=args.chat_template,
        )
        return 0

    if args.task in ("de", "dir") and args.stage == "infer-api":
        run_inference_api(
            api_url=args.api_url, api_model=args.api_model, api_key=args.api_key,
            prompts_file=args.prompts, output_file=args.out,
            max_new_tokens=args.max_new_tokens, temperature=args.temperature,
            top_p=args.top_p, timeout=args.timeout, sleep_secs=args.sleep_secs,
        )
        return 0

    if args.task == "single" and args.stage == "prompt":
        case_split = "" if args.case_split == "all" else args.case_split
        generate_single_case_prompt(
            task=args.mode, pert=args.pert, gene=args.gene, context=args.context,
            data_csv=args.data_csv, gene_desc_json=args.gene_desc,
            pert_desc_json=args.pert_desc, pert_sim_json=args.pert_sim,
            gene_sim_json=args.gene_sim, template_file=args.template, output_file=args.out,
            max_candidates=args.max_candidates, budget=args.budget, case_split=case_split,
            seed=args.seed, llm_api_url=args.llm_api_url, llm_api_model=args.llm_api_model,
            llm_api_key=args.llm_api_key, llm_candidate_pool=args.llm_candidate_pool,
            llm_timeout=args.llm_timeout,
        )
        return 0

    parser.error("Unknown stage")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
