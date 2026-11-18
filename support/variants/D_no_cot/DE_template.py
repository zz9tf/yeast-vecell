# -*- coding: utf-8 -*-
"""Ablation D — w/o CoT (T1 DE). Same Input Data / Biological Context / Evidence
Set as support/DE_template.py (full biocontext kept), but the 5-step reasoning
scaffold is removed: the model is instructed to answer immediately with only
the final closed-set sentence, no intermediate numbered steps. Tests whether
requiring explicit chain-of-thought reasoning has any edge over a direct call.
Final-answer vocabulary kept VERBATIM identical to v1/A/B so score.py needs no
changes. Markers kept exactly so infer.py can parse each block.
"""

contexts = [
    ("Deleteome deletion",
     "Single-gene deletion in Saccharomyces cerevisiae (BY4741 background), "
     "synthetic complete (SC) medium, log phase; steady-state genome-wide "
     "expression measured by two-colour microarray versus an isogenic wild-type "
     "reference. This is a loss-of-function (null) perturbation: the reading is "
     "the new transcriptional steady state a cell reaches once the gene's "
     "product is absent. Many deletions also slow growth, which superimposes a "
     "non-specific environmental-stress / slow-growth expression signature on "
     "top of the gene-specific response; weigh specificity accordingly."),
]

desc_pert = "description of the deleted gene (perturbagen)"
desc_gene = "description of the readout ORF whose response you infer"
desc_context = "description of the dataset / strain / perturbation-type context"
desc_obs = (
    "set of analogue experimental observations (similar deletions and/or "
    "co-functional readout genes drawn from training data, each with its true "
    "measured result) that contextualize your answer"
)


prompt_yeast_DE = f"""[Start of Prompt]
You are Yeast-VCWorld, a white-box Biological World Model and Causal Reasoning Engine for Saccharomyces cerevisiae. Your task is to simulate and predict the transcriptional response of the cell to a single-gene deletion.

Goal: Determine whether deleting {{pert}} (loss of function) causes differential expression (DE) of the readout ORF {{gene}} in the {{context_short}} context.

Input Data:
- Perturbagen -- deleted gene ({{pert}}): {desc_pert}
- Readout ORF ({{gene}}): {desc_gene}
- **Biological Context**: {desc_context}
  *(Instruction: You MUST use the context description above AND your internal knowledge of S. cerevisiae biology -- the deleted gene's pathway membership, complexes, epistasis/genetic interactions, and the slow-growth confound of deletion strains -- to make your call.)*
- Evidence Set: {desc_obs}

Reasoning Guidelines:
Do not rely on superficial name matching. Internally consider the deleted gene's function, its downstream regulatory cascade, and the analogue Examples above -- but do NOT write out that reasoning. Respond with ONLY your final deterministic prediction, in the exact closed-set format below, and nothing else.

Output: Respond with exactly one of the following options and nothing else (no numbered steps, no explanation):
- No. Deletion of {{pert}} does not differentially express {{gene}}.
- Yes. Deletion of {{pert}} results in differential expression of {{gene}}.
- There is insufficient evidence to determine how deletion of {{pert}} affects {{gene}}.
[End of Prompt]

[Start of Input]
- Description of deleted gene / perturbagen ({{pert}}): {{pert_desc}}
- Description of readout ORF of interest ({{gene}}): {{gene_desc}}
- Context: {{context_desc}}
- Examples: {{obs}}
[End of Input]

[Start of Output]
[End of Output]"""


# Ordered [negative_sentence, positive_sentence]; index == binary DE label.
choices_de = [
    "A) Deletion of this gene does not differentially express the readout gene.",
    "B) Deletion of this gene results in differential expression of the readout gene.",
]
