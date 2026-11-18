# -*- coding: utf-8 -*-
"""Ablation C — w/o Biocontext (T1 DE). Same 5-step scaffold and Examples block
as support/DE_template.py, but ALL functional/context descriptions are blanked
(the caller points --gene-desc/--pert-desc at a nonexistent JSON so
get_description() falls back to "description not found" for every case AND
every Example, and the hard-coded context paragraph below is stripped too).
Tests whether the model's score depends on the biological description text
itself, or only on the bare ORF identifiers + Examples' true labels.
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
            "true measured result) -- identified only by ORF name, with no "
            "functional description attached")


prompt_yeast_DE = f"""[Start of Prompt]
You are Yeast-VCWorld, a white-box Biological World Model and Causal Reasoning Engine for Saccharomyces cerevisiae. Your task is to simulate and predict the transcriptional response of the cell to a single-gene deletion.

Goal: Determine whether deleting {{pert}} (loss of function) causes differential expression (DE) of the readout ORF {{gene}} in the {{context_short}} context.

Input Data:
- Perturbagen -- deleted gene ({{pert}}): {desc_pert}
- Readout ORF ({{gene}}): {desc_gene}
- **Biological Context**: {desc_context}
  *(Instruction: No functional description or context paragraph is provided for this case. You do NOT have access to internal knowledge lookups for this specific gene here -- base your reasoning ONLY on the bare ORF identifiers below and the true-labelled Examples, not on any biological knowledge you might otherwise recall.)*
- Evidence Set: {desc_obs}

Reasoning Guidelines:
Do not rely on superficial name matching. Since no functional descriptions are available, reason primarily from the pattern of true labels among the Examples (and any similarity implied by the retrieval itself), while still walking through the steps below.

Output: Provide a structured analysis answering the following steps.

1) **Function & Analogue Identification:**
   You have no functional description for {{pert}} in this case -- state that explicitly. From the evidence set, identify which analogue deletions (by ORF name only) might plausibly relate to {{pert}}, and note whether the readout ORF {{gene}} appears among them.

2) **Specificity & Relevance Analysis:**
   - **Specificity:** Without a functional description, can you tell whether this deletion is likely broad (slow-growth / general stress) or narrow? State your uncertainty honestly.
   - **Relevance:** Based only on identifiers and Examples, is there any indication {{gene}} is linked to {{pert}}?

3) **Downstream Cascade Simulation (pathways & transcription factors):**
   Without functional/context descriptions, you cannot name a specific pathway or transcription factor with confidence. State this limitation, and instead rely on the label pattern in the Examples.

4) **Causal Bridge & Evidence Synthesis:**
   Construct your best-effort causal chain given the missing information. Cite specific analogue cases from the evidence set (matching the deletion's true result) that support (or bound) this link.

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
# Kept VERBATIM identical to support/DE_template.py so score.py needs no changes.
choices_de = [
    "A) Deletion of this gene does not differentially express the readout gene.",
    "B) Deletion of this gene results in differential expression of the readout gene.",
]
