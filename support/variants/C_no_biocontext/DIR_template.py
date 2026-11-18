# -*- coding: utf-8 -*-
"""Ablation C — w/o Biocontext (T1 DIR). Same 5-step scaffold and Examples block
as support/DIR_template.py, but ALL functional/context descriptions are blanked
(the caller points --gene-desc/--pert-desc at a nonexistent JSON so
get_description() falls back to "description not found" everywhere, including
inside every Example, and the hard-coded context paragraph below is stripped).
Markers kept exactly so infer.py can parse each block.
"""

contexts = [
    ("Deleteome deletion",
     "No additional biological/experimental context description is provided "
     "beyond the case identifiers below."),
]

desc_pert = ("NOT PROVIDED -- you are given only the deleted gene's systematic "
             "ORF name, no functional description.")
desc_gene = ("NOT PROVIDED -- you are given only the readout ORF's systematic "
             "name, no functional description.")
desc_context = "NOT PROVIDED -- no dataset/context description is available."
desc_obs = ("set of analogue experimental observations (similar deletions and/or "
            "co-functional readout genes drawn from training data, each with its "
            "true measured direction) -- identified only by ORF name, with no "
            "functional description attached")


prompt_yeast_DIR = f"""[Start of Prompt]
You are Yeast-VCWorld, a white-box Biological World Model and Causal Reasoning Engine for Saccharomyces cerevisiae. Your task is to simulate and predict the **direction** of the transcriptional response of the cell to a single-gene deletion.

Goal: Determine whether deleting {{pert}} (loss of function) causes an **Increase** or a **Decrease** in expression of the readout ORF {{gene}} in the {{context_short}} context.

Input Data:
- Perturbagen -- deleted gene ({{pert}}): {desc_pert}
- Readout ORF ({{gene}}): {desc_gene}
- **Biological Context**: {desc_context}
  *(Instruction: No functional description or context paragraph is provided for this case. You do NOT have access to internal knowledge lookups for this specific gene here -- base your reasoning ONLY on the bare ORF identifiers below and the true-labelled Examples, not on any biological knowledge you might otherwise recall.)*
- Evidence Set: {desc_obs}

Reasoning Guidelines:
Do not rely on superficial name matching. Since no functional descriptions are available, reason primarily from the pattern of true directions among the Examples, while still walking through the steps below.

Output: Provide a structured analysis answering the following steps.

1) **Function & Analogue Identification:**
   You have no functional description for {{pert}} in this case -- state that explicitly. From the evidence set, identify which analogue deletions (by ORF name only) might plausibly relate to {{pert}}, and note which direction those analogues moved.

2) **Specificity & Relevance Analysis:**
   - **Specificity:** Without a functional description, can you tell whether this deletion is likely broad or narrow in its effect? State your uncertainty honestly.
   - **Relevance:** Based only on identifiers and Examples, is there any indication {{gene}} is linked to {{pert}} in a direction-determining way?

3) **Directional Cascade Simulation (pathways & transcription factors):**
   Without functional/context descriptions, you cannot name a specific pathway or transcription factor with confidence. State this limitation, and instead rely on the direction pattern in the Examples.

4) **Regulatory Logic & Evidence Synthesis (deduce the direction):**
   Construct your best-effort logic given the missing information. Cite analogue cases from the evidence set (with their true directions) that show a consistent direction.

5) **Final Deterministic Prediction:**
   Based on the logic above, determine the net direction.

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


# Ordered [decrease_sentence, increase_sentence]; index == DIR label. VERBATIM
# identical to support/DIR_template.py.
choices_dir = [
    "A) Deletion of this gene results in a decrease in expression of the readout gene.",
    "B) Deletion of this gene results in an increase in expression of the readout gene.",
]
