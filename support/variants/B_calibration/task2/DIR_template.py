# -*- coding: utf-8 -*-
"""Task2 (growth phenotype) DIR-analog prompt template — VARIANT B (calibration / few-shot-centric).

Branch B hypothesis (Task2A, mirrors the Task1 B branch): among phenotype hits,
sensitive-vs-resistant is best read off the TRUE directions of same-condition /
same-function analogue Examples, with {{pert}}'s function used only as a light
adjustment. v1's 4-step scaffold is compressed to 3 steps: Examples prior vote
(majority direction among same-condition / same-function neighbour deletions)
-> light mechanistic adjustment (does Function of pert give a reason to deviate
from the majority) -> calibrated decision. Output adds `Confidence:` / `Final:`
fields, matching the Task1 B branch's tighter, more parseable format.

Drop-in for src/cli_pipeline/stages/prompt.py: defines the SAME names
(`contexts`, `readout_line_label`, `readout_desc_label`, `desc_*`,
`prompt_yeast_DIR`, `choices_dir`) and the SAME `{...}` format fields as
support/task2/DIR_template.py. Closed-set answer sentences kept VERBATIM from
v1. Markers preserved exactly for infer.py / infer_vllm.py.
"""

contexts = [
    ("yeast deletion growth screens",
     "Genome-wide single-gene-deletion growth-phenotype screens in S. cerevisiae "
     "(yeastphenome compendium, homozygous/HOP). Readout = relative fitness of the "
     "deletion strain vs wild-type under a defined chemical/environmental condition."),
]

# Examples-block wording (read by stages/prompt.py) — readout is a condition.
readout_line_label = "Condition (screen)"
readout_desc_label = "Condition Description"

desc_pert = "description of the deleted gene (perturbagen)"
desc_gene = "description of the growth condition / screen"
desc_context = "description of the assay platform"
desc_obs = ("analogue observations: functionally similar deletions and/or other "
            "deletions in the same/similar condition, to contextualize the direction")

prompt_yeast_DIR = f"""[Start of Prompt]
You are Yeast-VCWorld, a calibrated predictor of the direction (sensitive vs resistant) of growth phenotypes in S. cerevisiae deletion screens. You decide the direction by voting with true-labelled same-condition / same-function analogue Examples, using {{pert}}'s function as a light adjustment.

Goal: This deletion of {{pert}} is already known to cause a growth phenotype under the condition described below (screen {{gene}}). Determine whether it is MORE SENSITIVE or MORE RESISTANT.

Key fact about this task -- read carefully:
- The Examples are TRUE-LABELLED, same-condition / same-function observations carrying their real direction (Sensitive or Resistant). Functionally similar deletions and deletions tested under the same condition tend to move in consistent directions, so the closest analogues are your best evidence. ANCHOR on them; use {{pert}}'s function to adjust.

Input Data:
- Deleted gene / perturbagen ({{pert}}): {desc_pert}
- Growth condition (screen {{gene}}): {desc_gene}
- Assay context: {desc_context}
- Evidence Set: {desc_obs}

Output: Answer these three short steps, then a confidence and a final line. Be brief and concrete.

1) **Examples prior vote:**
   Among the Examples, tally how many went Sensitive vs Resistant. Then pick the 1-3 CLOSEST analogues (same pathway/process as {{pert}}, or the same/similar condition as {{gene}}) and report their true directions. Their majority direction is your prior.

2) **Mechanistic adjustment (brief):**
   In 1-2 sentences: does {{pert}}'s known function give a specific reason to DEVIATE from the step-1 majority (e.g. it directly buffers/repairs damage from this stress -> deviate toward Sensitive if the majority said Resistant; or it is the stress's direct target / a negative regulator of a resistance pathway -> deviate toward Resistant if the majority said Sensitive)? If no such reason exists, say so and keep the prior unchanged.

3) **Calibrated direction:**
   Combine the prior vote (step 1) with the adjustment (step 2). If they conflict, trust the closest same-condition/same-function Examples unless the mechanistic reason from step 2 is decisive.

Confidence: state High, Medium, or Low, based on how consistent the closest analogues were and how clear the mechanistic adjustment is.

End your response with exactly one of the following options:
- Sensitive. Deletion of {{pert}} makes the cell more sensitive under this condition.
- Resistant. Deletion of {{pert}} makes the cell more resistant under this condition.
- There is insufficient evidence to determine whether deletion of {{pert}} increases sensitivity or resistance under this condition.
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

choices_dir = [
    "A) Deletion of this gene makes the cell more sensitive under the condition.",
    "B) Deletion of this gene makes the cell more resistant under the condition.",
]
