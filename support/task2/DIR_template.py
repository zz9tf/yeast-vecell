# Task2 (growth phenotype) DIR-analog template: among phenotype hits, does the
# deletion make the strain MORE SENSITIVE or MORE RESISTANT under the condition?
# label 1 = resistant (z>0), 0 = sensitive (z<0). Drop-in for stages/prompt.py.

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
You are Yeast-VCWorld, a causal reasoning engine for budding yeast. Task: given that deleting a gene DOES change growth under a condition, predict the DIRECTION.

Goal: Determine whether deleting {{pert}} (complete loss of function) makes S. cerevisiae MORE SENSITIVE or MORE RESISTANT under the condition described below (screen {{gene}}).

Input Data:
- Deleted gene / perturbagen ({{pert}}): {desc_pert}
- Growth condition (screen {{gene}}): {desc_gene}
- Assay context: {desc_context}
- Evidence Set: {desc_obs}

Reason stepwise (do not pattern-match names):
1) **Function of {{pert}}** and its pathway.
2) **Direction logic**: does losing {{pert}} impair a defence/tolerance pathway needed under this stress (-> MORE SENSITIVE, worse fitness) or remove a target/negative-regulator that the stress exploits (-> MORE RESISTANT, better fitness)? A deletion that cripples the drug's own target or a bypass often confers resistance; loss of a buffering/repair pathway confers sensitivity.
3) **Analogue check**: what direction do similar deletions / the same condition's examples show?
4) **Final deterministic call.**

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
4)
[End of Output]"""

choices_dir = [
    "A) Deletion of this gene makes the cell more sensitive under the condition.",
    "B) Deletion of this gene makes the cell more resistant under the condition.",
]
