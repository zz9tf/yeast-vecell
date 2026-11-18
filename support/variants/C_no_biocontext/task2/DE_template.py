# Ablation C — w/o Biocontext (T2A DE-analog). Same 4-step scaffold and
# Examples block as support/task2/DE_template.py, but ALL functional/context
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
            "deletions in the same condition) identified only by ORF/condition "
            "name, with no description attached")

prompt_yeast_DE = f"""[Start of Prompt]
You are Yeast-VCWorld, a causal reasoning engine for budding yeast. Task: predict whether deleting a gene produces a GROWTH PHENOTYPE under a given condition.

Goal: Determine whether deleting {{pert}} (complete loss of function) measurably changes the growth/fitness of S. cerevisiae under the condition described below (screen {{gene}}).

Input Data:
- Deleted gene / perturbagen ({{pert}}): {desc_pert}
- Growth condition (screen {{gene}}): {desc_gene}
- Assay context: {desc_context}
- Evidence Set: {desc_obs}

Reason stepwise (do not pattern-match names). No functional or condition descriptions are available for this case -- base your reasoning only on the bare identifiers and the true-labelled Examples:
1) **Function of {{pert}}**: state that no functional description is available; note anything the ORF name or Examples suggest.
2) **Relevance to the condition**: without descriptions, state your uncertainty about whether {{pert}} plausibly interacts with condition {{gene}}, based only on Examples' patterns.
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
