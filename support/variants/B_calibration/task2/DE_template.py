# -*- coding: utf-8 -*-
"""Task2 (growth phenotype) DE-analog prompt template — VARIANT B (calibration / few-shot-centric).

Branch B hypothesis (Task2A, mirrors the Task1 B branch): whether a phenotype
"counts" is itself a calibration question (the model never sees the raw fitness
z-score cutoff), so the labelled analogue Examples are the best available signal
of the base rate and of how similar deletions/conditions behave. v1's 4-step
scaffold is compressed to 3 steps: Examples prior vote (majority phenotype
among same-condition / same-function neighbour deletions) -> light mechanistic
adjustment (does Function of pert give a reason to deviate from the majority)
-> calibrated decision. Output adds `Confidence:` / `Final:` fields, matching
the Task1 B branch's tighter, more parseable format.

Drop-in for src/cli_pipeline/stages/prompt.py: defines the SAME names
(`contexts`, `readout_line_label`, `readout_desc_label`, `desc_*`,
`prompt_yeast_DE`, `choices_de`) and the SAME `{...}` format fields as
support/task2/DE_template.py. Closed-set answer sentences kept VERBATIM from
v1. Markers preserved exactly for infer.py / infer_vllm.py.
"""

contexts = [
    ("yeast deletion growth screens",
     "Genome-wide single-gene-deletion growth-phenotype screens in S. cerevisiae "
     "(yeastphenome compendium, homozygous/HOP). Readout = relative fitness of the "
     "deletion strain vs wild-type under a defined chemical/environmental condition; a "
     "'growth phenotype' means the deletion measurably changes growth (sensitivity or "
     "resistance) in that condition."),
]

# Examples-block wording (read by stages/prompt.py) — readout is a condition, not a gene.
readout_line_label = "Condition (screen)"
readout_desc_label = "Condition Description"

desc_pert = "description of the deleted gene (perturbagen)"
desc_gene = "description of the growth condition / screen"
desc_context = "description of the assay platform"
desc_obs = ("analogue observations: functionally similar deletions and/or other "
            "deletions in the same condition, to contextualize your answer")

prompt_yeast_DE = f"""[Start of Prompt]
You are Yeast-VCWorld, a calibrated predictor of growth phenotypes in S. cerevisiae deletion screens. You decide whether a deletion clears the (unseen) fitness-change threshold for a condition, by calibrating against labelled same-condition / same-function Examples.

Goal: Determine whether deleting {{pert}} (complete loss of function) measurably changes the growth/fitness of S. cerevisiae under the condition described below (screen {{gene}}).

Key fact about this task -- read carefully:
- You CANNOT see the raw fitness z-score or the exact statistical cutoff that defines a phenotype hit. "Growth phenotype" means "the fitness change clears this screen's threshold".
- The Examples are TRUE-LABELLED observations -- functionally similar deletions and/or other deletions tested in this same condition. They are your calibration set: they reveal how permissive the threshold is here and how deletions like {{pert}} tend to behave. ANCHOR on them. Use {{pert}}'s function only to nudge off that anchor, not to override a clear majority signal.

Input Data:
- Deleted gene / perturbagen ({{pert}}): {desc_pert}
- Growth condition (screen {{gene}}): {desc_gene}
- Assay context: {desc_context}
- Evidence Set: {desc_obs}

Output: Answer these three short steps, then a confidence and a final line. Be brief and concrete.

1) **Examples prior vote:**
   Tally the Examples by their true Result -- how many showed a phenotype vs no-phenotype. State that base rate in one phrase (mostly-phenotype / mixed / mostly-none). Then pick the 1-3 CLOSEST analogues (same pathway/process as {{pert}}, or the same condition as {{gene}}) and report what they did. This closest-analogue majority is your prior.

2) **Mechanistic adjustment (brief):**
   In 1-3 sentences: does {{pert}}'s known function give a specific reason to DEVIATE from the step-1 majority (e.g. it directly buffers/targets this stress and the majority didn't capture that; or it looks unrelated to this condition despite what the majority suggests)? If no such reason exists, say so and keep the prior unchanged.

3) **Calibrated decision:**
   Combine the prior vote (step 1) with the adjustment (step 2). If they conflict, trust the same-condition/same-function Examples unless the mechanistic reason from step 2 is decisive.

Confidence: state High, Medium, or Low, based on how consistent the closest analogues were and how clear the mechanistic adjustment is.

End your response with exactly one of the following options:
- No. Deletion of {{pert}} does not cause a growth phenotype under this condition.
- Yes. Deletion of {{pert}} causes a growth phenotype under this condition.
- There is insufficient evidence to determine whether deletion of {{pert}} causes a growth phenotype under this condition.
[End of Prompt]

[Start of Input]
- Deleted gene ({{pert}}): {{pert_desc}}
- Growth condition (screen {{gene}}): {{gene_desc}}
- Assay context: {{context_desc}}
- Examples: {{obs}}
[End of Input]

[Start of Output]
1)
2)
3)
Confidence:
Final:
[End of Output]"""

choices_de = [
    "A) Deletion of this gene does not cause a growth phenotype under the condition.",
    "B) Deletion of this gene causes a growth phenotype under the condition.",
]
