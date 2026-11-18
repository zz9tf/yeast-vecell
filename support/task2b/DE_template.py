# Task 2B (genetic interaction, double perturbation) DE-analog template:
# T2B-DE = does the gene pair (A, B) show a statistically significant genetic
# interaction at all (Yes/No)? This is the "association-strength" gate before
# T2B-DIR judges its sign. Drop-in for stages/prompt.py (readout renamed A/B).
#
# COLUMN MAPPING (see src/task2b/prepare_pairs.py): the shared pert/gene CSV
# schema is reused unmodified -- pert = gene A (SGA query, essential-gene TS
# allele), gene = gene B (SGA array, deletion or TS allele). No separate
# `context` axis exists for T2B (single fixed SGA-screen context, same
# convention as Task 1's Deleteome context).

contexts = [
    ("Costanzo 2016 SGA E-MAP (essential-gene query subset)",
     "Genome-scale Synthetic Genetic Array (SGA) double-mutant fitness screen in "
     "S. cerevisiae (Costanzo lab thecellmap.org network). Each double mutant's "
     "colony-growth fitness is compared to the fitness expected if the two single "
     "mutants combined independently (multiplicative/log-additive null model); the "
     "deviation is the genetic-interaction score (epsilon, eps). This particular "
     "local slice queries essential genes via temperature-sensitive (TS) alleles "
     "(restrictive temperature = full loss of function) against an array of "
     "non-essential deletions and other TS essential alleles -- it is the ExE+ExN "
     "sub-network, not a genome-wide random sample (see docs/task_definitions.md "
     "Task 2B for the coverage caveat)."),
]

# Examples-block wording (read by stages/prompt.py) -- readout is gene B, not a
# transcript/condition.
readout_line_label = "Gene B (query x array partner)"
readout_desc_label = "Gene B Description"

desc_pert = "description of Gene A (the SGA query gene)"
desc_gene = "description of Gene B (the SGA array partner gene)"
desc_context = "description of the SGA E-MAP screen and its coverage caveats"
desc_obs = ("analogue observations: other gene pairs involving A or B (or their "
            "functional/network neighbors) with a known genetic-interaction call, "
            "to contextualize whether THIS pair is likely to interact")

prompt_yeast_DE = f"""[Start of Prompt]
You are Yeast-VCWorld, a causal reasoning engine for budding yeast. Task: predict whether two genes, when both perturbed together (double mutant), show a STATISTICALLY SIGNIFICANT GENETIC INTERACTION.

Goal: Determine whether the double perturbation of {{pert}} (Gene A) and {{gene}} (Gene B) produces a fitness deviation from the null expectation (independent, log-additive combination of the two single-mutant fitnesses) that is large enough to call a significant genetic interaction -- in either direction (aggravating/negative or alleviating/positive). This is a gate: do NOT judge the sign here, only whether an interaction exists at all.

Input Data:
- Gene A (query, {{pert}}): {desc_pert}
- Gene B (array partner, {{gene}}): {desc_gene}
- Screen context: {desc_context}
- Evidence Set: {desc_obs}

Reason stepwise (do not pattern-match names):
1) **Function & pathway/complex membership of A and B**: what process does each gene's product serve? Are they annotated in the same pathway, protein complex, or biological process?
2) **Network/functional relatedness**: are A and B connected in known interaction networks (physical, genetic, co-expression) or STRING-style functional association -- directly, or via a short number of intermediate steps? Closer functional relatedness raises the prior that perturbing both together produces a NON-additive (interacting) phenotype; genes in unrelated/independent pathways more often combine additively (no significant interaction).
3) **Analogue check**: do the evidence examples (other pairs sharing A, sharing B, or connecting functional neighbors of A/B) show confirmed interactions? A gene that is a hub (many known interactions) raises the prior of an interaction with a new partner too.
4) **Final deterministic call.**

End your response with exactly one of the following options:
- No. This gene pair does not show a significant genetic interaction.
- Yes. This gene pair shows a significant genetic interaction.
- There is insufficient evidence to determine whether this gene pair shows a significant genetic interaction.
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

choices_de = [
    "A) This gene pair does not show a significant genetic interaction.",
    "B) This gene pair shows a significant genetic interaction.",
]
