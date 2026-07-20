# Task2 (growth phenotype) DE-analog template.
# Readout is a CONDITION (screen), not a gene: does deleting {pert} change growth
# under condition {gene}? The condition's text is injected via {gene_desc}
# (built from haphom_growth_contexts.csv). Drop-in for stages/prompt.py.

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
You are Yeast-VCWorld, a causal reasoning engine for budding yeast. Task: predict whether deleting a gene produces a GROWTH PHENOTYPE under a given condition.

Goal: Determine whether deleting {{pert}} (complete loss of function) measurably changes the growth/fitness of S. cerevisiae under the condition described below (screen {{gene}}).

Input Data:
- Deleted gene / perturbagen ({{pert}}): {desc_pert}
- Growth condition (screen {{gene}}): {desc_gene}
- Assay context: {desc_context}
- Evidence Set: {desc_obs}

Reason stepwise (do not pattern-match names):
1) **Function of {{pert}}**: what pathway/process does its product serve?
2) **Relevance to the condition**: is that pathway required to tolerate/adapt to this specific stress or drug? (e.g. deleting a gene that buffers the drug's target -> sensitivity; deleting a negative regulator of a resistance pathway -> resistance; core essential-adjacent genes -> broad slow-growth.)
3) **Analogue check**: do the evidence examples (functionally similar deletions, or other deletions in this same condition) show a phenotype?
4) **Final deterministic call.**

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
4)
[End of Output]"""

choices_de = [
    "A) Deletion of this gene does not cause a growth phenotype under the condition.",
    "B) Deletion of this gene causes a growth phenotype under the condition.",
]
