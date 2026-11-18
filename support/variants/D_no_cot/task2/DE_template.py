# Ablation D — w/o CoT (T2A DE-analog). Same Input Data as
# support/task2/DE_template.py (full biocontext kept), but the 4-step
# reasoning scaffold is removed: direct final-answer call only.

contexts = [
    ("yeast deletion growth screens",
     "Genome-wide single-gene-deletion growth-phenotype screens in S. cerevisiae "
     "(yeastphenome compendium, homozygous/HOP). Readout = relative fitness of the "
     "deletion strain vs wild-type under a defined chemical/environmental condition; a "
     "'growth phenotype' means the deletion measurably changes growth (sensitivity or "
     "resistance) in that condition."),
]

readout_line_label = "Condition (screen)"
readout_desc_label = "Condition Description"

desc_pert = "description of the deleted gene (perturbagen)"
desc_gene = "description of the growth condition / screen"
desc_context = "description of the assay platform"
desc_obs = ("analogue observations: functionally similar deletions and/or other "
            "deletions in the same condition, to contextualize your answer")

prompt_yeast_DE = f"""[Start of Prompt]
You are Yeast-VCWorld, a causal reasoning engine for budding yeast. Task: predict whether deleting a gene produces a GROWTH PHENOTYPE under a given condition.

Goal: Determine whether deleting {{pert}} (complete loss of function) measurably changes the growth/fitness of S. cerevisiae under the condition described below (screen {{gene}}).

Input Data:
- Deleted gene / perturbagen ({{pert}}): {desc_pert}
- Growth condition (screen {{gene}}): {desc_gene}
- Assay context: {desc_context}
- Evidence Set: {desc_obs}

Internally consider the deleted gene's pathway, its relevance to the condition, and the Examples above -- but do NOT write out that reasoning. Respond with ONLY your final deterministic call, nothing else.

Output: Respond with exactly one of the following options and nothing else (no numbered steps, no explanation):
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
[End of Output]"""

choices_de = [
    "A) Deletion of this gene does not cause a growth phenotype under the condition.",
    "B) Deletion of this gene causes a growth phenotype under the condition.",
]
