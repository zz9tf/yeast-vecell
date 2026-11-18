# -*- coding: utf-8 -*-
"""Ablation D — w/o CoT (T1 DIR). Same Input Data / Biological Context /
Evidence Set as support/DIR_template.py (full biocontext kept), but the 5-step
reasoning scaffold is removed: direct final-answer call only. Final-answer
vocabulary kept VERBATIM identical to v1/A/B. Markers kept exactly.
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
desc_gene = "description of the readout ORF whose direction of change you infer"
desc_context = "description of the dataset / strain / perturbation-type context"
desc_obs = (
    "set of analogue experimental observations (similar deletions and/or "
    "co-functional readout genes drawn from training data, each with its true "
    "measured direction) that contextualize your answer"
)


prompt_yeast_DIR = f"""[Start of Prompt]
You are Yeast-VCWorld, a white-box Biological World Model and Causal Reasoning Engine for Saccharomyces cerevisiae. Your task is to simulate and predict the **direction** of the transcriptional response of the cell to a single-gene deletion.

Goal: Determine whether deleting {{pert}} (loss of function) causes an **Increase** or a **Decrease** in expression of the readout ORF {{gene}} in the {{context_short}} context.

Input Data:
- Perturbagen -- deleted gene ({{pert}}): {desc_pert}
- Readout ORF ({{gene}}): {desc_gene}
- **Biological Context**: {desc_context}
  *(Instruction: You MUST use the context description above AND your internal knowledge of S. cerevisiae biology -- the deleted gene's pathway membership, complexes, epistasis, and the slow-growth confound of deletion strains -- to make your call.)*
- Evidence Set: {desc_obs}

Reasoning Guidelines:
Do not rely on superficial name matching. Internally consider the deleted gene's function, the regulatory cascade, TF activator/repressor logic, and the analogue Examples above -- but do NOT write out that reasoning. Respond with ONLY your final deterministic prediction, in the exact closed-set format below, and nothing else.

Output: Respond with exactly one of the following options and nothing else (no numbered steps, no explanation):
- Decrease. Deletion of {{pert}} results in a decrease in expression of {{gene}}.
- Increase. Deletion of {{pert}} results in an increase in expression of {{gene}}.
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


# Ordered [decrease_sentence, increase_sentence]; index == DIR label.
choices_dir = [
    "A) Deletion of this gene results in a decrease in expression of the readout gene.",
    "B) Deletion of this gene results in an increase in expression of the readout gene.",
]
