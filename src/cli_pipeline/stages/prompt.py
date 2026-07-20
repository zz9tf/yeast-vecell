#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate prompts from retrieval results and a yeast template.

Ported from VCWorld's ``prompt`` stage. Key yeast changes:
  - The template exposes ``contexts`` (list of (short, description) for the
    dataset / perturbation-type) in place of VCWorld's hard-coded ``cell_lines``.
  - The "Examples" block is built from ``retrieved_pairs`` = ``[pert, gene, label]``
    using the TRUE label (mapped to a result sentence), never ``random.choice``.
  - Description JSONs are optional: a missing file degrades to "not found" text
    rather than crashing (the yeast knowledge JSONs may not exist yet).

The ``[Start of Prompt]...[End of Prompt]`` (system) and
``[Start of Input]...[End of Output]`` (user) markers are preserved exactly so
``infer.py`` can parse each block.
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

try:  # `utils` is a sibling package when run from src/cli_pipeline (via cli.py)
    from utils.alias import load_alias, display_name
except ImportError:  # pragma: no cover - allow importing as a package
    from cli_pipeline.utils.alias import load_alias, display_name


def load_template_vars(template_file: str) -> Dict[str, Any]:
    with open(template_file, "r", encoding="utf-8") as f:
        content = f.read()
    # Defaults so a template that references these in an f-string won't NameError.
    exec_globals: Dict[str, Any] = {
        "desc_pert": "description of the deleted gene (perturbagen)",
        "desc_gene": "description of the readout ORF whose response you infer",
        "desc_context": "description of the dataset / strain / perturbation-type context",
        "desc_obs": (
            "set of analogue experimental observations (similar deletions / "
            "co-functional readout genes) that contextualize your answer"
        ),
    }
    exec_locals: Dict[str, Any] = {}
    exec(content, exec_globals, exec_locals)
    return exec_locals


def load_json(path: Optional[str]) -> Dict[str, Any]:
    """Load a description JSON; a missing/unreadable file yields {}."""
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[prompt] WARNING: description JSON unavailable ({path}): {exc}. "
              f"Descriptions will fall back to 'not found'.")
        return {}


def get_description(name: str, desc_map: Dict[str, str], label: str) -> str:
    if name in desc_map:
        return desc_map[name]
    clean = name.strip().lower()
    for key, val in desc_map.items():
        if clean == key.strip().lower():
            return val
    return f"{label} '{name}' description not found"


def _label_to_result(label: int, choices: List[str]) -> Optional[str]:
    """Map a TRUE binary label to its result sentence.

    ``choices`` is ordered [negative_sentence, positive_sentence]; index == label.
    DE:  0 -> "does not impact", 1 -> "differential expression".
    DIR: 0 -> "decrease",        1 -> "increase".
    """
    if not choices:
        return None
    idx = 0 if int(label) <= 0 else 1
    if idx < len(choices):
        return choices[idx]
    return None


def format_observations(pairs: List[List], pert_desc: Dict[str, str],
                        gene_desc: Dict[str, str], choices: Optional[List[str]],
                        alias: Optional[Dict] = None, max_examples: int = 10) -> str:
    """Build the few-shot "Examples" block using the pairs' TRUE labels."""
    if not pairs:
        return "No similar experimental observations available for context."

    observations = []
    for i, pair in enumerate(pairs[:max_examples]):
        # pairs are [pert, gene, label]; tolerate a legacy [pert, gene].
        pert2, gene2 = pair[0], pair[1]
        label = pair[2] if len(pair) > 2 else None
        # look up descriptions by the raw (ORF) key; show a readable name.
        pdesc = get_description(pert2, pert_desc, "Perturbagen")
        gdesc = get_description(gene2, gene_desc, "Gene")
        pert2_show = display_name(pert2, alias) if alias else pert2
        obs_text = (
            f"Example {i + 1}:\n"
            f"- Perturbagen (deletion): {pert2_show}\n"
            f"- Readout gene (ORF): {gene2}\n"
            f"- Perturbagen Description: {pdesc}\n"
            f"- Readout Gene Description: {gdesc}"
        )
        if choices is not None and label is not None:
            result = _label_to_result(label, choices)
            if result:
                obs_text += f"\n- Result: {result}"
        observations.append(obs_text)
    return "\n\n".join(observations)


def _default_template_path(task: str) -> str:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if task == "de":
        return os.path.join(base_dir, "support", "DE_template.py")
    return os.path.join(base_dir, "support", "DIR_template.py")


def generate_prompts(*, task: str, retrieval_json: str,
                     gene_desc_json: Optional[str] = None,
                     pert_desc_json: Optional[str] = None,
                     template_file: Optional[str] = None, output_file: str,
                     context_idx: Optional[int] = None,
                     max_cases: Optional[int] = None, seed: int = 42,
                     alias_path: Optional[str] = None) -> None:
    import random
    random.seed(seed)

    retrieval = load_json(retrieval_json)
    gene_desc = load_json(gene_desc_json)
    # In yeast one description set serves both roles (perturbagen == deleted gene,
    # readout == ORF); default the perturbagen map to the gene map if unset.
    pert_desc = load_json(pert_desc_json) if pert_desc_json else gene_desc
    # Alias map is only for human-readable display ('STANDARD (ORF)'); all lookups
    # still use the raw ORF key (perturbagens are ORF-normalized in prepare).
    alias = load_alias(alias_path) if alias_path else {}

    if template_file is None:
        template_file = _default_template_path(task)
    tmpl_vars = load_template_vars(template_file)

    contexts: List[Tuple[str, str]] = tmpl_vars.get("contexts") or tmpl_vars.get("cell_lines", [])
    if not contexts:
        raise RuntimeError("`contexts` (or legacy `cell_lines`) not found in template file")

    choices_de = tmpl_vars.get("choices_de", [])
    choices_dir = tmpl_vars.get("choices_dir", [])
    prompt_de = (tmpl_vars.get("prompt_yeast_DE", "")
                 or tmpl_vars.get("prompt_vcworld_DE", ""))
    prompt_dir = (tmpl_vars.get("prompt_yeast_DIR", "")
                  or tmpl_vars.get("prompt_vcworld_DIR", ""))

    if task == "de":
        prompt_template = prompt_de
        choices = choices_de
    else:
        prompt_template = prompt_dir
        choices = choices_dir

    if not prompt_template:
        raise RuntimeError(f"prompt template for {task} not found in template file")

    cases = retrieval
    if max_cases is not None and max_cases < len(cases):
        cases = cases[:max_cases]

    with open(output_file, "w", encoding="utf-8") as f:
        for i, item in enumerate(cases):
            tc = item["test_case"]
            # accept both {"pert":..} (yeast) and legacy {"drug":..}
            pert = str(tc.get("pert", tc.get("drug", ""))).strip()
            gene = str(tc["gene"]).strip()
            retrieved_pairs = item.get("retrieved_pairs", [])

            if context_idx is None:
                idx = random.randint(0, len(contexts) - 1)
            else:
                idx = context_idx
            context_short, context_desc = contexts[idx]

            obs = format_observations(retrieved_pairs, pert_desc, gene_desc,
                                      choices, alias)

            pert_show = display_name(pert, alias) if alias else pert
            filled = prompt_template.format(
                pert=pert_show,
                gene=gene,
                pert_desc=get_description(pert, pert_desc, "Perturbagen"),
                gene_desc=get_description(gene, gene_desc, "Gene"),
                context_short=context_short,
                context_desc=context_desc,
                obs=obs,
            )

            f.write(f"=== Prompt {i + 1} ({pert_show} | {gene}) ===\n")
            f.write(filled)
            f.write("\n\n" + "=" * 80 + "\n\n")

    print(f"Saved prompts: {output_file} (count: {len(cases)})")
