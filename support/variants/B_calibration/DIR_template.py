# -*- coding: utf-8 -*-
"""Yeast DIR prompt template — VARIANT B (calibration / few-shot-centric).

Branch B hypothesis (direction): among DE hits, the up/down call can be read
off the TRUE directions of same-context analogue Examples -- co-regulated genes
and same-pathway deletions move together -- so the model should vote with the
closest labelled analogues first and use the activator/repressor sign rule only
as a tie-breaker. Leaner than v1, tighter output, ends in a stated confidence.

Drop-in for src/cli_pipeline/stages/prompt.py: defines the SAME names
(`contexts`, `desc_*`, `prompt_yeast_DIR`, `choices_dir`) and the SAME
`{...}` format fields as support/DIR_template.py. Final closed-set answer
sentences kept VERBATIM from v1. Markers preserved exactly for infer.py.
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
You are Yeast-VCWorld, a calibrated predictor of the **direction** of transcriptional change after single-gene deletions in Saccharomyces cerevisiae. You decide Increase vs Decrease by voting with true-labelled same-context analogues, using the activator/repressor sign rule as a tie-breaker.

Goal: This readout ORF {{gene}} is already known to be differentially expressed after deleting {{pert}} in the {{context_short}} context. Determine whether it goes **Increase** or **Decrease**.

Key fact about this task -- read carefully:
- You CANNOT see the fold-change; only its sign is being asked.
- The Examples are TRUE-LABELLED, same-context observations carrying their real direction (Increase or Decrease). Co-regulated genes and same-pathway deletions move in consistent directions, so the closest analogues are your best evidence. ANCHOR on them; use mechanism to break ties.

Input Data:
- Perturbagen -- deleted gene ({{pert}}): {desc_pert}
- Readout ORF ({{gene}}): {desc_gene}
- **Biological Context**: {desc_context}
- Evidence Set: {desc_obs}

Output: Answer these three short steps, then a confidence and a final line. Be brief and concrete.

1) **Directional vote from the Examples:**
   Among the Examples, tally how many went Increase vs Decrease. Then pick the 1-3 CLOSEST analogues (same pathway/complex as {{pert}}, or the same/similar readout as {{gene}}) and report their true directions. Their modal direction is your prior.

2) **Sign-rule tie-breaker (brief):**
   In 1-2 sentences apply the anchor rule for a complete null: losing an ACTIVATOR of {{gene}} -> Decrease; losing a REPRESSOR of {{gene}} -> Increase. Also note the slow-growth default if relevant (ESR/stress genes tend UP, ribosome-biogenesis/growth genes tend DOWN). Use this only to confirm or break a tie in step 1.

3) **Calibrated direction:**
   Combine the vote (step 1) with the sign rule (step 2). If they conflict, trust the closest same-context analogues unless the sign rule is unambiguous.

Confidence: state High, Medium, or Low, based on how consistent the closest analogues were and how clear the sign rule is.

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
Confidence:
Final:
[End of Output]"""


# Ordered [decrease_sentence, increase_sentence]; index == DIR label
# (DIR label = 1 iff M>0, i.e. Increase).
choices_dir = [
    "A) Deletion of this gene results in a decrease in expression of the readout gene.",
    "B) Deletion of this gene results in an increase in expression of the readout gene.",
]
