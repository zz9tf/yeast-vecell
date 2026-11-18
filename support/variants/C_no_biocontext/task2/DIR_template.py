# Ablation C — w/o Biocontext (T2A DIR-analog). Same 4-step scaffold and
# Examples block as support/task2/DIR_template.py, but ALL functional/context
# descriptions are blanked (caller points --gene-desc/--pert-desc at a
# nonexistent JSON so get_description() falls back everywhere).

contexts = [
    ("yeast deletion growth screens",
     "No additional assay/context description is provided beyond the case "
     "identifiers below."),
]

readout_line_label = "Condition (screen)"
readout_desc_label = "Condition Description"

desc_pert = "NOT PROVIDED -- only the deleted gene's systematic ORF name is given."
desc_gene = "NOT PROVIDED -- only the condition/screen identifier is given, no description."
desc_context = "NOT PROVIDED -- no assay context description is available."
desc_obs = ("analogue observations (functionally similar deletions and/or other "
            "deletions in the same/similar condition) identified only by "
            "ORF/condition name, with no description attached")

prompt_yeast_DIR = f"""[Start of Prompt]
You are Yeast-VCWorld, a causal reasoning engine for budding yeast. Task: given that deleting a gene DOES change growth under a condition, predict the DIRECTION.

Goal: Determine whether deleting {{pert}} (complete loss of function) makes S. cerevisiae MORE SENSITIVE or MORE RESISTANT under the condition described below (screen {{gene}}).

Input Data:
- Deleted gene / perturbagen ({{pert}}): {desc_pert}
- Growth condition (screen {{gene}}): {desc_gene}
- Assay context: {desc_context}
- Evidence Set: {desc_obs}

Reason stepwise (do not pattern-match names). No functional or condition descriptions are available for this case -- base your reasoning only on the bare identifiers and the true-labelled Examples:
1) **Function of {{pert}}**: state that no functional description is available.
2) **Direction logic**: without descriptions, you cannot reason about specific defence/tolerance pathways -- rely on the direction pattern shown by the Examples instead.
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
