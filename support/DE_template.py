# -*- coding: utf-8 -*-
"""Yeast DE (differential-expression) prompt template.

Replaces VCWorld's human ``cell_lines`` with a ``contexts`` list describing the
dataset / perturbation-type, and rewrites the 5-step reasoning scaffold in yeast
(S. cerevisiae) terms. The ``[Start of Prompt]...[End of Prompt]`` and
``[Start of Input]...[End of Output]`` markers are kept exactly so infer.py can
parse each block.
"""

# Context axis (dataset / strain / perturbation-type). One is chosen per case.
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

# Instruction-level descriptions (interpolated into the scaffold below at
# template-exec time; the caller overrides the per-case {{...}} fields).
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
  *(Instruction: You MUST use the context description above AND enhance it with your internal knowledge of S. cerevisiae biology -- the deleted gene's pathway membership, complexes, epistasis/genetic interactions, and the slow-growth confound of deletion strains.)*
- Evidence Set: {desc_obs}

Reasoning Guidelines:
Do not rely on superficial name matching. Perform a stepwise mechanistic simulation as follows.

Output: Provide a structured analysis answering the following steps.

1) **Function & Analogue Identification:**
   State the molecular function of the deleted gene {{pert}} (pathway, complex, biological process). From the evidence set, identify analogue deletions that act in the *same pathway or complex* as {{pert}}, and note whether the readout ORF {{gene}} is a known co-functional / network neighbour.

2) **Specificity & Relevance Analysis:**
   - **Specificity:** Is deleting {{pert}} expected to give a broad response (e.g. a slow-growth / general environmental-stress signature, or loss of a global regulator) or a narrow, gene-specific one?
   - **Relevance:** Is {{gene}} plausibly downstream of {{pert}}'s pathway, or is any apparent link more likely a non-specific slow-growth artefact?

3) **Downstream Cascade Simulation (pathways & transcription factors):**
   Trace the regulatory cascade from the deletion. Loss of {{pert}} perturbs its pathway, which changes the activity of specific transcription factors (TFs). Using YEASTRACT-style TF -> target logic, name the candidate TF(s) that regulate {{gene}} and whether the deletion would raise or lower their activity.

4) **Causal Bridge & Evidence Synthesis:**
   Construct the explicit causal chain: deletion of {{pert}} -> affected pathway -> transcription factor(s) -> target ORF {{gene}}. Cite specific analogue cases from the evidence set (matching the deletion's true result) that support (or bound) this link.

5) **Final Deterministic Prediction:**
   Based on the analysis above, decide whether deleting {{pert}} differentially expresses {{gene}}.

   End your response with exactly one of the following options:
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
1)
2)
3)
4)
5)
[End of Output]"""


# Ordered [negative_sentence, positive_sentence]; index == binary DE label.
choices_de = [
    "A) Deletion of this gene does not differentially express the readout gene.",
    "B) Deletion of this gene results in differential expression of the readout gene.",
]
