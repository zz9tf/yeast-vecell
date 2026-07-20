# -*- coding: utf-8 -*-
"""Yeast DE prompt template — VARIANT B (calibration / few-shot-centric).

Branch B hypothesis: the model never sees raw effect sizes or the |logFC| / FDR
cutoff that defines a DE hit, so "is this differentially expressed?" is really
"does this clear the same-context threshold?" -- a CALIBRATION question. The
labelled analogue Examples are the only in-context evidence of where that
threshold sits and how permissive this dataset is, so the prompt makes the model
ANCHOR on the Examples' true Results (base rate + closest-analogue vote) and use
mechanism only as a light adjustment. Reasoning is deliberately LEANER than v1
and the output is tighter and more parseable, ending in a stated confidence.

Drop-in for src/cli_pipeline/stages/prompt.py: defines the SAME names
(`contexts`, `desc_*`, `prompt_yeast_DE`, `choices_de`) and the SAME
`{...}` format fields as support/DE_template.py. Final closed-set answer
sentences kept VERBATIM from v1 so any answer parser stays compatible.
Markers preserved exactly for infer.py.
"""

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

desc_pert = "description of the deleted gene (perturbagen)"
desc_gene = "description of the readout ORF whose response you infer"
desc_context = "description of the dataset / strain / perturbation-type context"
desc_obs = (
    "set of analogue experimental observations (similar deletions and/or "
    "co-functional readout genes drawn from training data, each with its true "
    "measured result) that contextualize your answer"
)


prompt_yeast_DE = f"""[Start of Prompt]
You are Yeast-VCWorld, a calibrated predictor of transcriptional responses to single-gene deletions in Saccharomyces cerevisiae. You decide whether a readout ORF clears the (unseen) differential-expression threshold, by calibrating against labelled same-context Examples.

Goal: Determine whether deleting {{pert}} causes differential expression (DE) of the readout ORF {{gene}} in the {{context_short}} context.

Key fact about this task -- read carefully:
- You CANNOT see effect sizes, fold-changes, or the exact statistical cutoff that defines a DE hit. "Differentially expressed" means "the change clears this dataset's threshold".
- The Examples are TRUE-LABELLED observations from the SAME context. They are your calibration set: they reveal how permissive the threshold is here and how deletions like {{pert}} tend to behave on readouts like {{gene}}. ANCHOR on them. Use mechanism only to nudge off that anchor, not to override a clear analogue signal.

Input Data:
- Perturbagen -- deleted gene ({{pert}}): {desc_pert}
- Readout ORF ({{gene}}): {desc_gene}
- **Biological Context**: {desc_context}
- Evidence Set: {desc_obs}

Output: Answer these three short steps, then a confidence and a final line. Be brief and concrete.

1) **Calibrate from the Examples:**
   Tally the Examples by their true Result -- how many were differentially expressed vs not. State that base rate in one phrase (mostly-DE / mixed / mostly-not). Then pick the 1-3 CLOSEST analogues (same pathway/complex as {{pert}}, or the same/similar readout as {{gene}}) and report what they did. This closest-analogue vote is your prior.

2) **Mechanistic adjustment (brief):**
   In 1-3 sentences: does {{pert}}'s known biology push {{gene}} ABOVE the threshold (a direct pathway / regulon link, or a strong slow-growth signature that would move a generic stress/growth gene) or leave it BELOW (no plausible route, a purely non-specific link)? Adjust the step-1 prior up or down accordingly.

3) **Calibrated decision:**
   Combine the analogue vote (step 1) with the adjustment (step 2). If they conflict, trust the same-context Examples unless mechanism is decisive.

Confidence: state High, Medium, or Low, based on how consistent the closest analogues were and how clear the mechanism is.

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
Confidence:
Final:
[End of Output]"""


# Ordered [negative_sentence, positive_sentence]; index == binary DE label.
choices_de = [
    "A) Deletion of this gene does not differentially express the readout gene.",
    "B) Deletion of this gene results in differential expression of the readout gene.",
]
