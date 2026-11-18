# Task 2B (genetic interaction, double perturbation) DIR-analog template: among
# T2B-DE positives (pair DOES show a significant genetic interaction), predict
# the SIGN -- negative/aggravating (pathway redundancy: synthetic lethal/sick)
# vs positive/alleviating (pathway buffering: suppression/epistatic masking).
# Drop-in for stages/prompt.py (readout renamed A/B; see DE_template.py header
# for the column-mapping convention).

contexts = [
    ("Costanzo 2016 SGA E-MAP (essential-gene query subset)",
     "Genome-scale Synthetic Genetic Array (SGA) double-mutant fitness screen in "
     "S. cerevisiae (Costanzo lab thecellmap.org network). Genetic-interaction "
     "score (epsilon, eps) = observed double-mutant fitness minus the fitness "
     "expected under independence; eps < 0 = negative/aggravating interaction "
     "(double mutant sicker than expected, up to synthetic lethality), eps > 0 = "
     "positive/alleviating interaction (double mutant healthier than expected, "
     "e.g. epistatic masking/suppression). This slice is restricted to an "
     "essential-gene query set (ExE+ExN), not a genome-wide random sample."),
]

# Examples-block wording (read by stages/prompt.py) -- readout is gene B.
readout_line_label = "Gene B (query x array partner)"
readout_desc_label = "Gene B Description"

desc_pert = "description of Gene A (the SGA query gene)"
desc_gene = "description of Gene B (the SGA array partner gene)"
desc_context = "description of the SGA E-MAP screen and its coverage caveats"
desc_obs = ("analogue observations: other interacting gene pairs involving A or B "
            "(or their functional/network neighbors), with the known sign of the "
            "interaction, to contextualize the direction for THIS pair")

prompt_yeast_DIR = f"""[Start of Prompt]
You are Yeast-VCWorld, a causal reasoning engine for budding yeast. Task: given that two genes DO show a significant genetic interaction when both perturbed, predict the SIGN of that interaction.

Goal: Determine whether the double perturbation of {{pert}} (Gene A) and {{gene}} (Gene B) is a NEGATIVE (aggravating; synthetic lethal/sick) or POSITIVE (alleviating; suppressive/epistatic-masking) genetic interaction.

Input Data:
- Gene A (query, {{pert}}): {desc_pert}
- Gene B (array partner, {{gene}}): {desc_gene}
- Screen context: {desc_context}
- Evidence Set: {desc_obs}

Reason stepwise (do not pattern-match names):
1) **Function & pathway/complex membership of A and B.**
2) **Redundancy vs buffering logic**: are A and B in the SAME pathway/complex or two PARALLEL/compensatory pathways converging on the same essential process? Same-pathway/complex redundancy (both needed for one essential function, each can partly substitute) predicts a NEGATIVE interaction -- losing both removes the function entirely (synthetic lethal/sick), worse than the multiplicative expectation. Parallel/compensatory pathways where one gene's loss is normally buffered by, or epistatic to, the other's pathway (e.g. B acts downstream of A in the same linear pathway, or B's loss only matters when A's repressive/damaging effect is active) predicts a POSITIVE interaction -- the double mutant is no worse (or better) than the single worse mutant, because the effects mask rather than compound.
3) **Analogue check**: what sign do similar pairs (sharing A, sharing B, or connecting their functional neighbors) show in the evidence?
4) **Final deterministic call.**

End your response with exactly one of the following options:
- Negative. The double deletion shows a negative (synthetic lethal/sick) genetic interaction.
- Positive. The double deletion shows a positive (alleviating/suppressive) genetic interaction.
- There is insufficient evidence to determine the sign of this genetic interaction.
[End of Prompt]

[Start of Input]
- Gene A ({{pert}}): {{pert_desc}}
- Gene B ({{gene}}): {{gene_desc}}
- Screen context: {{context_desc}}
- Examples: {{obs}}
[End of Input]

[Start of Output]
1)
2)
3)
4)
[End of Output]"""

choices_dir = [
    "A) The double deletion shows a negative (synthetic lethal/sick) genetic interaction.",
    "B) The double deletion shows a positive (alleviating/suppressive) genetic interaction.",
]
