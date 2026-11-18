# -*- coding: utf-8 -*-
"""Task2 (growth phenotype) DE-analog prompt template — VARIANT A (mechanism-structured).

Branch A hypothesis (Task2A, mirrors the Task1 A branch): the v1 4-step scaffold's
steps 2 ("Relevance to condition") and 3 ("Analogue check") are under-specified
narrative asks. Forcing each into an explicit, CHECKABLE two-question format —
and requiring the analogue evidence to be cited by Example number — should raise
precision the same way it did for Task1's TF-sign / evidence-citation steps.
Step 1 (Function of pert) and step 4 (Final call) are left narrative, matching
the "only steps 2/3 change" scope of the A-branch design.

Drop-in for src/cli_pipeline/stages/prompt.py: defines the SAME names
(`contexts`, `readout_line_label`, `readout_desc_label`, `desc_*`,
`prompt_yeast_DE`, `choices_de`) and the SAME `{...}` format fields as
support/task2/DE_template.py. The closed-set answer sentences are kept
VERBATIM from v1 so score.py's parser stays compatible. The
`[Start of Prompt]...[End of Prompt]` and `[Start of Input]...[End of Output]`
markers are preserved exactly for infer.py / infer_vllm.py.
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
You are Yeast-VCWorld, a causal reasoning engine for budding yeast. Task: predict whether deleting a gene produces a GROWTH PHENOTYPE under a given condition, by building an explicit, checkable chain from pathway function to condition relevance to cited evidence -- never by surface name matching.

Goal: Determine whether deleting {{pert}} (complete loss of function) measurably changes the growth/fitness of S. cerevisiae under the condition described below (screen {{gene}}).

Input Data:
- Deleted gene / perturbagen ({{pert}}): {desc_pert}
- Growth condition (screen {{gene}}): {desc_gene}
- Assay context: {desc_context}
- Evidence Set: {desc_obs}

Output: Fill in the four steps below. Be concrete: name pathways and processes; cite Examples by their number.

1) **Function of {{pert}}**: What pathway/process does its product serve? Note any complex(es) it belongs to and its broad essentiality (core-essential-adjacent vs dispensable).

2) **Relevance to condition -- answer BOTH sub-questions explicitly:**
   (a) Is {{pert}}'s pathway REQUIRED to tolerate or adapt to this specific stress/condition (loss -> expected sensitivity), or does it act as a NEGATIVE REGULATOR of a resistance pathway / the direct target of the stressor (loss -> expected resistance), or is it UNRELATED to this condition's mechanism (loss -> no expected phenotype)? State which of the three applies and why.
   (b) Given that classification, do you expect a growth phenotype (Yes/No) under this condition specifically -- as opposed to a generic slow-growth effect that would show up under any condition?

3) **Analogue check -- answer BOTH sub-questions explicitly, citing Evidence by number:**
   (a) List, BY EXAMPLE NUMBER, every Evidence entry that is either (i) a functionally similar deletion (same pathway/process as {{pert}}) or (ii) another deletion tested under this same condition. For EACH cited number, state its true Result (phenotype or no-phenotype).
   (b) Do the cited Examples SUPPORT or ARGUE AGAINST a phenotype here? If no Evidence entry is a close functional or same-condition match, say so explicitly -- that absence is itself weak evidence.

4) **Final deterministic call.** Weigh step 2's mechanistic call against step 3's cited evidence and decide.

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
