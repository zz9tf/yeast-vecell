# Ablation D — w/o CoT (T2A DIR-analog). Same Input Data as
# support/task2/DIR_template.py (full biocontext kept), but the 4-step
# reasoning scaffold is removed: direct final-answer call only.

contexts = [
    ("yeast deletion growth screens",
     "Genome-wide single-gene-deletion growth-phenotype screens in S. cerevisiae "
     "(yeastphenome compendium, homozygous/HOP). Readout = relative fitness of the "
     "deletion strain vs wild-type under a defined chemical/environmental condition."),
]

readout_line_label = "Condition (screen)"
readout_desc_label = "Condition Description"

desc_pert = "description of the deleted gene (perturbagen)"
desc_gene = "description of the growth condition / screen"
desc_context = "description of the assay platform"
desc_obs = ("analogue observations: functionally similar deletions and/or other "
            "deletions in the same/similar condition, to contextualize the direction")

prompt_yeast_DIR = f"""[Start of Prompt]
You are Yeast-VCWorld, a causal reasoning engine for budding yeast. Task: given that deleting a gene DOES change growth under a condition, predict the DIRECTION.

Goal: Determine whether deleting {{pert}} (complete loss of function) makes S. cerevisiae MORE SENSITIVE or MORE RESISTANT under the condition described below (screen {{gene}}).

Input Data:
- Deleted gene / perturbagen ({{pert}}): {desc_pert}
- Growth condition (screen {{gene}}): {desc_gene}
- Assay context: {desc_context}
- Evidence Set: {desc_obs}

Internally consider the deleted gene's pathway, whether losing it impairs a defence/tolerance pathway (-> sensitive) or removes a target/negative-regulator (-> resistant), and the Examples above -- but do NOT write out that reasoning. Respond with ONLY your final deterministic call, nothing else.

Output: Respond with exactly one of the following options and nothing else (no numbered steps, no explanation):
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
[End of Output]"""

choices_dir = [
    "A) Deletion of this gene makes the cell more sensitive under the condition.",
    "B) Deletion of this gene makes the cell more resistant under the condition.",
]
