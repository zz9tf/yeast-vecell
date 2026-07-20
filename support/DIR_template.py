# -*- coding: utf-8 -*-
"""Yeast DIR (direction-of-change) prompt template.

Among DE hits, predicts whether the readout ORF goes Increase or Decrease.
Same yeast ``contexts`` axis and 5-step scaffold as DE_template, with explicit
activator/repressor directional logic (the place YEASTRACT sign information pays
off). Markers kept exactly for infer.py parsing.
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
  *(Instruction: You MUST use the context description above AND enhance it with your internal knowledge of S. cerevisiae biology -- the deleted gene's pathway membership, complexes, epistasis, and the slow-growth confound of deletion strains.)*
- Evidence Set: {desc_obs}

Reasoning Guidelines:
Do not rely on superficial name matching. Perform a stepwise mechanistic simulation to deduce the net directionality (up/down) of the effect.

Output: Provide a structured analysis answering the following steps.

1) **Function & Analogue Identification:**
   State the molecular function of the deleted gene {{pert}} (pathway, complex, biological process). From the evidence set, identify analogue deletions in the *same pathway or complex*, and note whether {{gene}} is a co-functional / network neighbour and in which direction those analogues moved.

2) **Specificity & Relevance Analysis:**
   - **Specificity:** Would deleting {{pert}} act broadly (slow-growth / general stress) or specifically on {{gene}}'s regulators?
   - **Relevance:** Is {{gene}} plausibly downstream of {{pert}}'s pathway in a direction-determining way?

3) **Directional Cascade Simulation (pathways & transcription factors):**
   Trace the regulatory cascade. Deleting {{pert}} removes its function -> its pathway activity changes -> the activity of specific transcription factor(s) that regulate {{gene}} changes. Using YEASTRACT-style TF -> target logic, name the candidate TF(s) and whether the deletion raises or lowers their activity, and whether each TF is an **activator** or a **repressor** of {{gene}}.

4) **Regulatory Logic & Evidence Synthesis (deduce the direction):**
   - **Logic Construction:**
     - If the deletion lowers the activity of an *activator* of {{gene}} -> predict **Decrease**.
     - If the deletion lowers the activity of a *repressor* of {{gene}} -> predict **Increase**.
     - (And symmetrically if the deletion raises a TF's activity.)
   - **Evidence Support:** Cite analogue cases from the evidence set (with their true directions) that show a consistent direction.

5) **Final Deterministic Prediction:**
   Based on the causal logic above, determine the net direction.

   End your response with exactly one of the following options:
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
1)
2)
3)
4)
5)
[End of Output]"""


# Ordered [decrease_sentence, increase_sentence]; index == DIR label
# (DIR label = 1 iff M>0, i.e. Increase).
choices_dir = [
    "A) Deletion of this gene results in a decrease in expression of the readout gene.",
    "B) Deletion of this gene results in an increase in expression of the readout gene.",
]
