# -*- coding: utf-8 -*-
"""Task2 (growth phenotype) DIR-analog prompt template — VARIANT A (mechanism-structured).

Branch A hypothesis (Task2A, mirrors the Task1 A branch): among phenotype hits,
the sensitive-vs-resistant call is where an explicit, CHECKABLE mechanism split
pays off, so v1's steps 2 ("Direction logic") and 3 ("Analogue check") are each
forced into a two-question format, with the analogue evidence cited by Example
number. Step 1 (Function of pert) and step 4 (Final call) are left narrative,
matching the "only steps 2/3 change" scope of the A-branch design.

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
You are Yeast-VCWorld, a causal reasoning engine for budding yeast. Task: given that deleting a gene DOES change growth under a condition, predict the DIRECTION by building an explicit, checkable chain from mechanism to cited evidence -- never by surface name matching.

Goal: Determine whether deleting {{pert}} (complete loss of function) makes S. cerevisiae MORE SENSITIVE or MORE RESISTANT under the condition described below (screen {{gene}}).

Input Data:
- Deleted gene / perturbagen ({{pert}}): {desc_pert}
- Growth condition (screen {{gene}}): {desc_gene}
- Assay context: {desc_context}
- Evidence Set: {desc_obs}

Output: Fill in the four steps below. Be concrete: name pathways and processes; cite Examples by their number.

1) **Function of {{pert}}** and its pathway/process.

2) **Direction logic -- answer BOTH sub-questions explicitly:**
   (a) Does losing {{pert}} impair a defence/tolerance/repair pathway that is needed to withstand this specific stress (-> predicts MORE SENSITIVE, worse fitness)? OR does it remove a target of the stressor, or a negative regulator of a resistance/bypass pathway, that the stress exploits or that constrains growth (-> predicts MORE RESISTANT, better fitness)? State which case applies and why.
   (b) Is there a competing, secondary consideration that could push the direction the other way (e.g. a strong general slow-growth confound that could look like sensitivity regardless of mechanism)? State it if so, otherwise say "none identified."

3) **Analogue check -- answer BOTH sub-questions explicitly, citing Evidence by number:**
   (a) List, BY EXAMPLE NUMBER, every Evidence entry that is either a functionally similar deletion or another deletion tested under this same/similar condition. For EACH cited number, state its true direction (Sensitive or Resistant).
   (b) Do the cited Examples AGREE or DISAGREE with the direction predicted in step 2? If they disagree, state which one you trust more and why.

4) **Final deterministic call.** Weigh step 2's mechanistic direction against step 3's cited evidence and decide.

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
