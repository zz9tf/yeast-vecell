#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI entry for the Task 2B (genetic interaction, gene-pair) pipeline.

Reuses ``src/cli_pipeline/stages/retrieve.py`` and ``.../stages/prompt.py``
UNMODIFIED (see ``src/task2b/prepare_pairs.py`` docstring for why this is safe:
the pair CSVs are relabeled ``pertA/pertB -> pert/gene`` so those stages' own
generic ``--readout-col`` mechanism, already built for Task 2A, is all that's
needed). Only ``prepare`` is Task-2B-specific (thin adapter, not a rebuild of
the labeling logic that already lives in ``src/task2/build_sga_labels.py``).

IMPORTANT retrieval-evidence choice (avoids a labeled leakage documented in
docs/task_definitions.md Task 2B point 2): T2B's OWN labels come from the
Costanzo SGA E-MAP matrix, and ``data/knowledge/perturbagen_similarity.json``
(the default Task 1/2A ``--pert-sim``) is ALSO derived from Costanzo SGA
profile similarity -- using it here would let retrieval evidence leak
information correlated with the very labels being predicted. This CLI's
default therefore points BOTH ``--pert-sim`` and ``--gene-sim`` at
``results_close_gene.json`` (STRING functional-association network, an
independent source, keyed by ORF on both axes since gene A and gene B are both
genes here) and does NOT expose the SGA-similarity file as an option.

Run from repo root:
    python src/task2b/cli.py prepare --de-csv ... --dir-csv ... --out-dir data/task2b
    python src/task2b/cli.py de  retrieve --data-csv data/task2b/sga_DE_pairs.csv  --out ...
    python src/task2b/cli.py de  prompt   --retrieval ... --out ...
    python src/task2b/cli.py dir retrieve --data-csv data/task2b/sga_DIR_pairs.csv --out ...
    python src/task2b/cli.py dir prompt   --retrieval ... --out ...
"""

import argparse
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CLI_PIPELINE_DIR = os.path.join(REPO_ROOT, "src", "cli_pipeline")
sys.path.insert(0, CLI_PIPELINE_DIR)  # so `from stages... / from utils...` resolve, same as cli_pipeline/cli.py

from stages.retrieve import build_retrieval_results  # noqa: E402
from stages.prompt import generate_prompts  # noqa: E402
from prepare_pairs import main as _prepare_main  # noqa: E402

DEFAULT_GENE_SIM = os.path.join(REPO_ROOT, "data", "knowledge", "results_close_gene.json")
DEFAULT_GENE_DESC = os.path.join(REPO_ROOT, "data", "knowledge", "gene_desc.json")
DEFAULT_ALIAS = os.path.join(REPO_ROOT, "data", "knowledge", "gene_alias.json")
DEFAULT_TEMPLATE_DIR = os.path.join(REPO_ROOT, "support", "task2b")


def _add_retrieve_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--data-csv", required=True,
                   help="pert/gene/label/split CSV from prepare_pairs.py "
                        "({name}_DE_pairs.csv or {name}_DIR_pairs.csv)")
    p.add_argument("--pert-sim", default=DEFAULT_GENE_SIM,
                   help="Similarity map for Gene A (default: STRING results_close_gene.json, "
                        "NOT the SGA-derived perturbagen_similarity.json -- see module docstring)")
    p.add_argument("--gene-sim", default=DEFAULT_GENE_SIM,
                   help="Similarity map for Gene B (default: STRING results_close_gene.json)")
    p.add_argument("--out", required=True)
    p.add_argument("--budget", type=int, default=10)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--max-cases", type=int, default=None)
    p.add_argument("--case-split", default="test", choices=["train", "test"])
    p.add_argument("--shuffle-labels", action="store_true")


def _add_prompt_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--retrieval", required=True)
    p.add_argument("--gene-desc", default=DEFAULT_GENE_DESC)
    p.add_argument("--pert-desc", default=None)
    p.add_argument("--template", default=None,
                   help="defaults to support/task2b/{DE,DIR}_template.py by task")
    p.add_argument("--alias", default=DEFAULT_ALIAS)
    p.add_argument("--out", required=True)
    p.add_argument("--context-idx", type=int, default=None)
    p.add_argument("--max-cases", type=int, default=None)
    p.add_argument("--seed", type=int, default=42)


def _default_template(task: str) -> str:
    return os.path.join(DEFAULT_TEMPLATE_DIR, "DE_template.py" if task == "de" else "DIR_template.py")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Task 2B (genetic interaction) pipeline CLI")
    top = parser.add_subparsers(dest="task", required=True)

    prep = top.add_parser("prepare", help="adapt sga_DE/DIR.csv -> pert/gene schema (see prepare_pairs.py)")
    prep.add_argument("--de-csv", required=True)
    prep.add_argument("--dir-csv", required=True)
    prep.add_argument("--out-dir", required=True)
    prep.add_argument("--name", default="sga")
    prep.add_argument("--sample-n", type=int, default=None)
    prep.add_argument("--seed", type=int, default=42)

    for task_name in ("de", "dir"):
        task_parser = top.add_parser(task_name)
        stage_sub = task_parser.add_subparsers(dest="stage", required=True)
        _add_retrieve_args(stage_sub.add_parser("retrieve"))
        _add_prompt_args(stage_sub.add_parser("prompt"))

    return parser


def main(argv: list) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.task == "prepare":
        return _prepare_main([
            "--de-csv", args.de_csv, "--dir-csv", args.dir_csv,
            "--out-dir", args.out_dir, "--name", args.name,
            *(["--sample-n", str(args.sample_n)] if args.sample_n is not None else []),
            "--seed", str(args.seed),
        ])

    if args.task in ("de", "dir") and args.stage == "retrieve":
        build_retrieval_results(
            data_csv=args.data_csv, out_json=args.out,
            pert_sim_json=args.pert_sim, gene_sim_json=args.gene_sim,
            budget=args.budget, seed=args.seed, max_cases=args.max_cases,
            case_split=args.case_split, shuffle_labels=args.shuffle_labels,
            readout_col="gene",
        )
        return 0

    if args.task in ("de", "dir") and args.stage == "prompt":
        template_file = args.template or _default_template(args.task)
        generate_prompts(
            task=args.task, retrieval_json=args.retrieval,
            gene_desc_json=args.gene_desc, pert_desc_json=args.pert_desc,
            template_file=template_file, output_file=args.out,
            context_idx=args.context_idx, max_cases=args.max_cases, seed=args.seed,
            alias_path=(args.alias or None),
        )
        return 0

    parser.error("Unknown stage")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
