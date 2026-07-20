# -*- coding: utf-8 -*-
"""Yeast DE prompt template — VARIANT A (mechanism-structured).

Branch A hypothesis: the v1 5-step scaffold is under-specified. Making the
causal chain explicit and *checkable* — (i) framing a deletion as a complete
null (100% loss of function, not a partial knock-down), (ii) forcing an explicit
YEASTRACT-style TF -> target sign step, (iii) forcing the model to cite a
specific analogue Example by number and state whether its true Result agrees —
should raise precision by anchoring every claim to a mechanism or a labelled
case rather than to name-similarity.

Drop-in for src/cli_pipeline/stages/prompt.py: defines the SAME names
(`contexts`, `desc_*`, `prompt_yeast_DE`, `choices_de`) and the SAME
`{...}` format fields as support/DE_template.py. The final closed-set answer
sentences are kept VERBATIM from v1 so any answer parser stays compatible.
The `[Start of Prompt]...[End of Prompt]` and `[Start of Input]...[End of Output]`
markers are preserved exactly for infer.py.
"""

# Context axis (dataset / strain / perturbation-type). One is chosen per case.
contexts = [
    ("Deleteome deletion",
     "Single-gene deletion in Saccharomyces cerevisiae (BY4741 background), "
     "synthetic complete (SC) medium, log phase; steady-state genome-wide "
     "expression measured by two-colour microarray versus an isogenic wild-type "
     "reference. This is a loss-of-function (null) perturbation: the reading is "
     "the new transcriptional steady state a cell reaches once the gene's "
     "product is absent. Many deletions also slow growth, which superimposes a "
     "non-specific environmental-stress / slow-growth expression signature on "
     "top of the gene-specific response; weigh specificity accordingly."),
]

# Instruction-level descriptions (interpolated into the scaffold below at
# template-exec time; the caller overrides the per-case {{...}} fields).
desc_pert = "description of the deleted gene (perturbagen)"
desc_gene = "description of the readout ORF whose response you infer"
desc_context = "description of the dataset / strain / perturbation-type context"
desc_obs = (
    "set of analogue experimental observations (similar deletions and/or "
    "co-functional readout genes drawn from training data, each with its true "
    "measured result) that contextualize your answer"
)


prompt_yeast_DE = f"""[Start of Prompt]
You are Yeast-VCWorld, a white-box Biological World Model and Causal Reasoning Engine for Saccharomyces cerevisiae. You simulate the transcriptional steady state of a cell after a single-gene deletion by building an explicit, mechanistic causal chain -- never by surface name matching.

Goal: Determine whether deleting {{pert}} causes differential expression (DE) of the readout ORF {{gene}} in the {{context_short}} context.

Modeling assumptions you MUST hold:
- A deletion is a COMPLETE null: 100% loss of function of {{pert}}'s product, not a partial knock-down. Reason about what is fully absent, and about anything that becomes de-repressed or compensated once it is gone.
- The readout is a new STEADY STATE versus isogenic wild-type, so account for feedback and secondary adaptation, not just the immediate primary effect.
- Deleting {{pert}} may slow growth; a slow-growth / environmental-stress-response (ESR) signature is a real but NON-SPECIFIC cause of DE. Keep it separate from a gene-specific, pathway-directed effect.

Input Data:
- Perturbagen -- deleted gene ({{pert}}): {desc_pert}
- Readout ORF ({{gene}}): {desc_gene}
- **Biological Context**: {desc_context}
  *(Instruction: You MUST use the context description above AND enhance it with your internal knowledge of S. cerevisiae biology -- {{pert}}'s pathway membership, protein complexes it belongs to, its epistasis / genetic interactions, and the slow-growth confound of deletion strains.)*
- Evidence Set: {desc_obs}

Output: Fill in the five steps below. Be concrete: name pathways, complexes, and transcription factors; cite Examples by their number.

1) **Function, Pathway Placement & Analogue Identification:**
   State the molecular function of {{pert}} -- its pathway, the complex(es) it is part of, and the biological process it drives. Then SCAN the Examples: list every analogue deletion that acts in the *same pathway or complex* as {{pert}}, and note each one's true Result (differentially expressed or not). Separately note whether the readout ORF {{gene}} is a known co-functional gene / network neighbour / regulon member of {{pert}}'s pathway.

2) **Specificity vs. Slow-Growth Confound:**
   - **Specificity:** Is deleting {{pert}} expected to produce a BROAD response (loss of a global regulator, or a strong slow-growth / ESR signature) or a NARROW, pathway-specific one?
   - **Confound test:** If {{gene}} is a generic stress / ribosomal / metabolic gene and {{pert}} mainly slows growth, an apparent hit may be a non-specific ESR artefact -- flag this. If instead {{gene}} sits in {{pert}}'s own pathway or regulon, a specific effect is plausible.

3) **Regulatory Cascade & TF Sign Step (YEASTRACT logic):**
   Trace the cascade from the null: loss of {{pert}} -> altered pathway activity -> changed activity of specific transcription factor(s) (TFs) that regulate {{gene}}. Name the candidate TF(s) governing {{gene}}. For EACH, state (a) whether it is an ACTIVATOR or a REPRESSOR of {{gene}}, and (b) whether deleting {{pert}} RAISES or LOWERS that TF's activity. (In the DE task you need only establish that {{gene}}'s regulatory input is perturbed at all; the up/down bookkeeping is decisive in the DIR task.) If no TF or pathway link exists, say so plainly.

4) **Causal Bridge & Mandatory Evidence Citation:**
   Write the explicit chain as text: deletion of {{pert}} -> affected pathway -> transcription factor(s) -> readout ORF {{gene}}. Then CITE at least one specific analogue by its Example number, quote its true Result, and state whether it SUPPORTS or ARGUES AGAINST a link here. If the closest analogues were NOT differentially expressed, treat that as evidence for "No". A chain with no supporting Example and no known regulatory link is weak evidence.

5) **Final Deterministic Prediction:**
   Weigh the mechanistic chain (steps 3-4) against specificity (step 2) and the cited Examples' true Results. Decide.

   End your response with exactly one of the following options:
   - No. Deletion of {{pert}} does not differentially express {{gene}}.
   - Yes. Deletion of {{pert}} results in differential expression of {{gene}}.
   - There is insufficient evidence to determine how deletion of {{pert}} affects {{gene}}.
[End of Prompt]

[Start of Input]
- Description of deleted gene / perturbagen ({{pert}}): {{pert_desc}}
- Description of readout ORF of interest ({{gene}}): {{gene_desc}}
- Context: {{context_desc}}
- Examples: {{obs}}
[End of Input]

[Start of Output]
1)
2)
3)
4)
5)
[End of Output]"""


# Ordered [negative_sentence, positive_sentence]; index == binary DE label.
choices_de = [
    "A) Deletion of this gene does not differentially express the readout gene.",
    "B) Deletion of this gene results in differential expression of the readout gene.",
]
